"""Persistent memory — players and orgs remember, via the chronicle.

A memory is not new state: it is a SELECTION over the chronicle (the
same way stats are a selection over the match log). This module owns the
selectors and the small, bounded effects memories have on the campaign:

- A player remembers their debut, their titles, their milestones, and
  being released — and it moves renewal talks and 1:1s a nudge (the
  talks doctrine: a memory is a nudge, not a lever).
- An org remembers a returning manager — the board's starting patience
  shifts with how the last era ended.

Everything derives on read; nothing here writes the chronicle.
"""

from __future__ import annotations

from esports_sim.manager.state import ChronicleEntry, GameState

MEMORY_CAP = 10

# Bias contributions (career-loyalty points, clamped to +/-10 total).
_DEBUT_HERE = 4.0
_TITLE_HERE = 3.0
_MILESTONE_HERE = 1.0
_RELEASED_HERE = -6.0
_RENEWED_HERE = 1.0
BIAS_CAP = 10.0


def memories_for(
    gs: GameState, pid: str, cap: int = MEMORY_CAP, *, include_relationships: bool = True
) -> list[ChronicleEntry]:
    """A player's defining memories: their chronicle entries, most
    important first, recency breaking ties. Capped — people keep the
    landmarks, not the noise."""
    mine = [
        e for e in gs.chronicle
        if e.player_id == pid
        and (include_relationships or e.kind != "relationship")
    ]
    mine.sort(key=lambda e: (-e.importance, -e.season, -e.week, e.id))
    return mine[:cap]


def team_titles(gs: GameState, tid: str) -> list[ChronicleEntry]:
    return [
        e
        for e in gs.chronicle
        if e.team_id == tid
        and e.kind in ("regional_title", "masters_title", "champions_title")
    ]


def loyalty_bias(gs: GameState, pid: str, tid: str) -> float:
    """How this player's history with THIS org tilts contract talks,
    in [-BIAS_CAP, +BIAS_CAP]. Zero for a blank slate: a player with no
    history here negotiates on the numbers alone."""
    bias = 0.0
    title_seasons = {e.season for e in team_titles(gs, tid)}
    for e in memories_for(gs, pid, cap=MEMORY_CAP * 2):
        if e.kind == "debut" and e.team_id == tid:
            bias += _DEBUT_HERE
        elif e.kind == "milestone" and e.team_id == tid:
            bias += _MILESTONE_HERE
        elif e.kind == "release" and e.team_id == tid:
            bias += _RELEASED_HERE
        elif e.kind == "renewal" and e.team_id == tid:
            bias += _RENEWED_HERE
        elif e.kind == "award" and e.team_id == tid and e.season in title_seasons:
            bias += _TITLE_HERE  # an award in a title season binds hardest
    return float(max(-BIAS_CAP, min(BIAS_CAP, bias)))


def memory_lines(
    gs: GameState, pid: str, *, include_relationships: bool = True
) -> list[str]:
    """Display strings for profiles/talks ("remembers ...")."""
    out = []
    for e in memories_for(gs, pid, include_relationships=include_relationships):
        out.append(f"S{e.season}: {e.text}")
    return out


def board_posture(gs: GameState, manager_id: str, tid: str) -> float:
    """Patience adjustment when a manager RETURNS to an org, from how
    the last era there ended: titles won together warm the room, a past
    dismissal from this exact boardroom cools it. Zero for a first
    meeting."""
    delta = 0.0
    for e in gs.chronicle:
        if e.manager_id != manager_id or e.team_id != tid:
            continue
        if e.kind in ("regional_title", "masters_title", "champions_title"):
            delta += 4.0
        elif e.kind == "dismissal":
            delta -= 5.0
        elif e.kind == "appointment":
            delta += 1.0  # they know you; the interview is shorter
    return float(max(-10.0, min(10.0, delta)))
