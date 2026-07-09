"""Loop iteration 3: richer match stats, relationship friction/results,
talk-to-relationship coupling, and free-agent competition.

The stats are derived purely from the event log (no new events), so the
golden fixture is byte-identical; everything else is manager-layer and
never runs inside the match gates.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import market, relationships, talk
from esports_sim.manager import new_campaign
from esports_sim.manager.relationships import affinity_target
from esports_sim.registry import load_all
from esports_sim.sim import simulate_match_result
from esports_sim.sim.stats import compute_match_stats

A, B = "team_nexus", "team_vanguard"


def _campaign(seed: int = 9):
    gd = load_all()
    return gd, new_campaign(gd, seed=seed)


# -- richer stats -------------------------------------------------------------

def test_richer_stats_derived_from_log() -> None:
    gd = load_all()
    res = simulate_match_result(gd, A, B, "haven", 42)
    team_of = {pid: t for t in (A, B) for pid in gd.teams[t].player_ids}
    st = compute_match_stats(res.events, team_of)
    tot = lambda f: sum(getattr(l, f) for l in st.lines.values())  # noqa: E731
    # Every opening duel produces exactly one first-kill and one first-death.
    assert tot("first_kills") == tot("first_deaths") > 0
    assert tot("multikills") > 0
    assert tot("clutches") > 0  # 1vX round wins happen
    # Without team_of, clutches can't be reconstructed but nothing else moves.
    st0 = compute_match_stats(res.events)
    assert sum(l.clutches for l in st0.lines.values()) == 0
    assert sum(l.multikills for l in st0.lines.values()) == tot("multikills")


def test_clutch_requires_surviving_to_win() -> None:
    """A post-plant round can detonate for the attackers after their last man
    dies — a win, but not a clutch. The isolated player is only credited if
    they were still alive at round end."""
    from esports_sim.schemas.events import (
        KillEvent, MatchEndEvent, MatchStartEvent, RoundEndEvent,
        RoundStartEvent, SpikePlantEvent,
    )

    team_of = {"a1": "A", "a2": "A", "a3": "A", "d1": "D", "d2": "D", "d3": "D"}

    def clutches(last_man_dies: bool) -> int:
        ev = [
            MatchStartEvent(match_id="m", map_id="haven", team_a_id="A", team_b_id="D", seed=1),
            RoundStartEvent(round_num=1, attacking_team_id="A", defending_team_id="D"),
            KillEvent(killer_id="d1", victim_id="a1", weapon_id="vandal"),
            KillEvent(killer_id="d1", victim_id="a2", weapon_id="vandal"),  # a3 isolated 1v3
            SpikePlantEvent(player_id="a3", callout_id="site"),
        ]
        if last_man_dies:
            ev.append(KillEvent(killer_id="d2", victim_id="a3", weapon_id="vandal"))
            reason = "spike_detonation"  # still an A win
        else:
            ev += [
                KillEvent(killer_id="a3", victim_id="d1", weapon_id="vandal"),
                KillEvent(killer_id="a3", victim_id="d2", weapon_id="vandal"),
                KillEvent(killer_id="a3", victim_id="d3", weapon_id="vandal"),
            ]
            reason = "elim"
        ev.append(RoundEndEvent(round_num=1, winner_id="A", reason=reason))
        ev.append(MatchEndEvent(match_id="m", winner_id="A", score_a=1, score_b=0))
        st = compute_match_stats(ev, team_of)
        return st.lines["a3"].clutches

    assert clutches(last_man_dies=True) == 0  # died before detonation -> no clutch
    assert clutches(last_man_dies=False) == 1  # survived the 1v3 -> clutch


# -- relationships: role friction --------------------------------------------

def test_two_spotlight_players_clash_more() -> None:
    """Two players sharing a spotlight playstyle settle lower than a
    complementary pairing, all else equal."""
    _, gs = _campaign()
    a, b, c = (gs.players[p] for p in list(gs.players)[:3])
    for p in (a, b, c):
        p.personality_tags = []  # isolate the playstyle effect
    a.playstyle = b.playstyle = "entry"
    c.playstyle = "support"
    assert affinity_target(a, b) < affinity_target(a, c)


# -- relationships: AI teams ride their own results --------------------------

def test_ai_chemistry_responds_to_results() -> None:
    _, gs = _campaign()
    ai = next(t for t in sorted(gs.teams) if t != gs.user_team_id)
    roster = sorted(gs.teams[ai].player_ids)
    pair = (roster[0], roster[1])

    def drift(win: bool) -> float:
        relationships._set(gs, *pair, 50.0)
        relationships.weekly_tick(
            gs, np.random.default_rng(0), user_won=False,
            won_by_team={ai: win},
        )
        return relationships.get(gs, *pair)

    assert drift(True) > drift(False)  # winning bonds, losing grates


# -- talk colours the captain relationship -----------------------------------

def test_positive_talk_bonds_player_with_captain() -> None:
    _, gs = _campaign()
    team = gs.teams[gs.user_team_id]
    roster = team.player_ids
    team.captain_id = roster[0]
    target = roster[1]
    gs.players[target].morale = 40.0  # surfaces the morale topic (has "reassure")
    before = relationships.get(gs, target, team.captain_id)
    ok, _msg, _fx = talk.resolve(gs, target, "reassure")
    assert ok
    assert relationships.get(gs, target, team.captain_id) > before


# -- free-agent competition --------------------------------------------------

def test_ai_poaches_a_premium_free_agent() -> None:
    """A clearly-better free agent gets signed by a rival AI org (a full team
    swaps its weakest same-role player), so the user competes for top talent
    instead of grabbing it uncontested; the signer's roster stays at five."""
    gd, gs = _campaign()
    for t in gs.teams:
        gs.teams[t].balance = 5_000_000  # nobody is priced out
    # A premium FA, clearly the best available.
    fa = gs.players[gs.free_agent_ids[0]]
    fa.playstyle = "entry"
    for k in list(fa.attributes):
        fa.attributes[k] = 85.0
    market.ai_poach_free_agents(gs, gd, np.random.default_rng(2))
    assert fa.id not in gs.free_agent_ids  # the premium FA is off the market
    signer = next(
        t for t in gs.teams if fa.id in gs.teams[t].player_ids
    )
    assert signer != gs.user_team_id
    assert len(gs.teams[signer].player_ids) == market.ROSTER_SIZE


def test_poach_reserves_severance_and_never_strands() -> None:
    """A team that can cover the sign but NOT the sign plus the dropped
    player's severance must not poach and strand itself at four players."""
    gd, gs = _campaign()
    target = next(t for t in sorted(gs.teams) if t != gs.user_team_id)
    for t in gs.teams.values():
        t.balance = 0  # price every other org out so `target` is the only suitor
    team = gs.teams[target]
    victim = gs.players[team.player_ids[0]]
    fa = gs.players[gs.free_agent_ids[0]]
    fa.playstyle = victim.playstyle
    for k in list(fa.attributes):
        fa.attributes[k] = 85.0  # premium, clear quality gap over the victim
    ask = market.asking_salary(fa)
    victim.salary = ask  # severance = 6*ask, so it eats past the sign reserve
    team.balance = ask * 12  # enough for the sign alone, not sign + severance
    market.ai_poach_free_agents(gs, gd, np.random.default_rng(2))
    assert len(team.player_ids) == market.ROSTER_SIZE  # never left at four
