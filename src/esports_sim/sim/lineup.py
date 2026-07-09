"""Weekly lineup resolution — which five start and which agent each locks in.

Single source of truth shared by two callers, so they can never disagree:

* the match engine (`sim/engine.py`), which fields the resolved lineup, and
* the web serializer (`web/server.py`), which shows an owner their locks and
  shows a *scouted* rival exactly what the engine will field.

An empty `TeamLineup` — the default on every team — resolves to the whole
roster, each player on their best-mastery agent. That is byte-identical to the
pre-lineup engine (`_pick_agent` + `sorted(player_ids)`), so a default team
keeps the golden and balance gates stable. Only an explicit coach choice
(a starter list or an agent lock) changes the resolved output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # imports only for typing — avoids any runtime import cycle
    from esports_sim.schemas.agent import Agent
    from esports_sim.schemas.player import Player
    from esports_sim.schemas.team import Team


def auto_pick_agent(pl: "Player", agents: dict[str, "Agent"]) -> str:
    """Highest-mastery agent the player knows; fall back to a role default, then
    the alphabetically-first agent. Byte-identical to the engine's historical
    `_pick_agent`, so the automatic path never moves the golden."""
    pool = sorted(pl.agent_pool, key=lambda m: (-m.mastery, m.agent_id))
    for m in pool:
        if m.agent_id in agents:
            return m.agent_id
    by_role = sorted(a.id for a in agents.values() if a.role == pl.role)
    return by_role[0] if by_role else sorted(agents)[0]


def resolve_agent(team: "Team", pl: "Player", agents: dict[str, "Agent"]) -> str:
    """The agent this player locks: the coach's explicit assignment when it is a
    real agent id, otherwise the automatic pick. Off-pool locks are honoured on
    purpose (the coach can flex a player onto an unfamiliar agent) — the engine's
    agent-mastery duel bonus then reads 0, which is the natural cost."""
    assigned = team.lineup.agents.get(pl.id)
    if assigned and assigned in agents:
        return assigned
    return auto_pick_agent(pl, agents)


def resolve_starters(team: "Team") -> list[str]:
    """The player ids that start, sorted for deterministic iteration. Honours an
    explicit starter list (intersected with the current roster so a stale id
    can't sneak in) and otherwise starts the whole roster — identical to the
    engine's historical `sorted(player_ids)`."""
    roster = set(team.player_ids)
    chosen = [pid for pid in team.lineup.starters if pid in roster]
    return sorted(chosen) if chosen else sorted(team.player_ids)
