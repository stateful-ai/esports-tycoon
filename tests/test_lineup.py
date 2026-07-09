"""Weekly lineup: per-player agent locks reach the match engine, and an unset
lineup is an exact no-op (the whole golden/balance stack runs unset teams, so
the default MUST field exactly what the pre-lineup engine did).
"""

from __future__ import annotations

import hashlib

from esports_sim.registry import load_all
from esports_sim.sim import lineup, simulate_match
from esports_sim.sim.engine import _MatchSim

A, B, MAP = "team_nexus", "team_vanguard", "lotus"


def _fielded_agents(gd, team_id: str) -> dict[str, str]:
    """The agent each starter actually locks when the engine is built."""
    sim = _MatchSim(gd, A, B, MAP, seed=7)
    return {pid: st.agent_id for pid, st in sim.p.items() if st.team_id == team_id}


def _log_hash(gd) -> str:
    h = hashlib.sha256()
    for e in simulate_match(gd, A, B, MAP, 7):
        h.update(e.model_dump_json().encode())
    return h.hexdigest()


def test_default_lineup_matches_auto_pick():
    """No lineup set → every starter is on their auto-picked agent, and the
    starter set is the whole roster (the historical behaviour)."""
    gd = load_all()
    fielded = _fielded_agents(gd, A)
    assert set(fielded) == set(gd.teams[A].player_ids)
    for pid, agent in fielded.items():
        assert agent == lineup.auto_pick_agent(gd.players[pid], gd.agents)


def test_agent_lock_is_fielded():
    """An explicit lock overrides the auto pick for that player only."""
    gd = load_all()
    # apex auto-picks omen (mastery 92); force sova instead.
    apex = gd.players["apex"]
    assert lineup.auto_pick_agent(apex, gd.agents) == "omen"
    gd.teams[A].lineup.agents["apex"] = "sova"
    fielded = _fielded_agents(gd, A)
    assert fielded["apex"] == "sova"
    # Teammates are untouched.
    assert fielded["phantom"] == lineup.auto_pick_agent(gd.players["phantom"], gd.agents)


def test_off_pool_lock_honoured():
    """A coach may flex a player onto an agent outside their pool."""
    gd = load_all()
    gd.teams[A].lineup.agents["phantom"] = "cypher"  # not in phantom's pool
    assert _fielded_agents(gd, A)["phantom"] == "cypher"


def test_unset_lineup_is_byte_identical():
    """Touching the lineup schema must not perturb a default match's log."""
    gd_a = load_all()
    gd_b = load_all()
    # A lock that we then clear must leave no residue.
    gd_b.teams[A].lineup.agents["apex"] = "sova"
    gd_b.teams[A].lineup.agents.clear()
    assert _log_hash(gd_a) == _log_hash(gd_b)


def test_lock_changes_the_log():
    """The lock actually reaches the engine — a different agent yields a
    different event stream (so the feature isn't silently inert)."""
    gd_default = load_all()
    gd_locked = load_all()
    gd_locked.teams[A].lineup.agents["vortex"] = "reyna"  # vortex auto-picks jett
    assert lineup.auto_pick_agent(gd_default.players["vortex"], gd_default.agents) == "jett"
    assert _log_hash(gd_default) != _log_hash(gd_locked)


def test_resolve_starters_intersects_roster():
    """A stale id in the starter list is dropped; an empty list = whole roster."""
    gd = load_all()
    team = gd.teams[A]
    assert lineup.resolve_starters(team) == sorted(team.player_ids)
    team.lineup.starters = ["apex", "ghost", "does_not_exist"]
    assert lineup.resolve_starters(team) == ["apex", "ghost"]
