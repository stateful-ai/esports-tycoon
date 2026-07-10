"""Pairwise player relationships — the chemistry graph under the scalar.

Every pair of teammates carries a relationship (0-100, 50 = professional
courtesy). Time together drifts it toward a trait-driven affinity target
(clash pairs sour, kindred spirits bond — the tone/cast "everyone exists
to clash with someone" discipline, now mechanical). Team chemistry stops
being a free-floating scalar: it chases the roster's mean relationship.
Relationships OUTLIVE rosters — sell someone's best friend and the friend
remembers; meet an old teammate across the server and there's history.

Deterministic: drift comes from trait math; jitter from the weekly rng.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.state import GameState
from esports_sim.schemas import Player

# Trait pairs that spark or grate. Symmetric; first match wins per pair.
_CLASH: list[tuple[str, str, float]] = [
    ("hot_head", "hot_head", -14.0),
    ("hot_head", "perfectionist", -10.0),
    ("volatile", "reliable", -6.0),
    ("mercenary", "loyal", -8.0),
    ("streamer", "quiet", -5.0),
    ("independent", "shotcaller", -6.0),
]
_KINDRED: list[tuple[str, str, float]] = [
    ("team_player", "team_player", 10.0),
    ("leader", "rookie", 8.0),
    ("veteran", "rookie", 6.0),
    ("analytical", "student", 8.0),
    ("calm", "hot_head", 5.0),  # the steady hand that cools the fuse
    ("quiet", "reliable", 4.0),
]

FRIEND_BAR = 78.0
FEUD_BAR = 26.0

# Playstyles that compete for the spotlight: two players who both want to
# be the star entry / AWPer / shotcaller grate on each other — one role,
# one slot, egos included.
_SPOTLIGHT_STYLES = {"entry", "awper", "igl"}
_SPOTLIGHT_FRICTION = 7.0


def key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def get(gs: GameState, a: str, b: str) -> float:
    return gs.relationships.get(key(a, b), 50.0)


def _set(gs: GameState, a: str, b: str, value: float) -> None:
    gs.relationships[key(a, b)] = round(min(100.0, max(0.0, value)), 1)


def nudge(gs: GameState, a: str, b: str, delta: float) -> None:
    """Public entry point for other modules (talk, events) to shift a pair's
    relationship by `delta`, clamped to [0, 100]."""
    _set(gs, a, b, get(gs, a, b) + delta)


def affinity_target(pa: Player, pb: Player) -> float:
    """Where a pair naturally settles after enough time together."""
    from esports_sim.manager import personality

    target = 58.0  # shared reps breed mild friendship by default
    tags_a, tags_b = set(pa.personality_tags), set(pb.personality_tags)
    for t1, t2, delta in _CLASH + _KINDRED:
        if (t1 in tags_a and t2 in tags_b) or (t2 in tags_a and t1 in tags_b):
            target += delta
    # Two players chasing the same spotlight role rub each other wrong.
    if (
        str(pa.playstyle) == str(pb.playstyle)
        and str(pa.playstyle) in _SPOTLIGHT_STYLES
    ):
        target -= _SPOTLIGHT_FRICTION
    # The continuous layer under the tags (manager/personality.py):
    # sociable pairs bond above the default, two big egos grate, and a
    # professionalism gulf (the grinder and the slacker) wears. Every
    # term is an exact no-op for a 50/50 neutral pair.
    ax_a, ax_b = personality.axes(pa), personality.axes(pb)
    target += (ax_a["sociability"] + ax_b["sociability"] - 100.0) * 0.05
    target -= (
        max(0.0, ax_a["ego"] - 60.0) + max(0.0, ax_b["ego"] - 60.0)
    ) * 0.10
    target -= abs(ax_a["professionalism"] - ax_b["professionalism"]) * 0.04
    return float(min(95.0, max(15.0, target)))


def weekly_tick(
    gs: GameState,
    rng: np.random.Generator,
    user_won: bool,
    won_by_team: dict[str, bool] | None = None,
) -> None:
    """Drift every teammate pair toward its affinity target; results add
    a shared push (winning together bonds, losing grates). Crossing the
    friendship/feud bars makes news once per crossing.

    `won_by_team` (team_id -> won this week) lets every org's chemistry ride
    its own results, not just the user's; without it only the user team gets
    the win/loss push (the legacy behaviour)."""
    for tid in sorted(gs.teams):
        roster = sorted(gs.teams[tid].player_ids)
        if won_by_team is not None:
            won = won_by_team.get(tid)
        else:
            won = user_won if tid == gs.user_team_id else None
        for i, a in enumerate(roster):
            for b in roster[i + 1:]:
                pa, pb = gs.players[a], gs.players[b]
                cur = get(gs, a, b)
                target = affinity_target(pa, pb)
                if won is True:
                    target += 4.0
                elif won is False:
                    target -= 3.0
                nxt = cur + (target - cur) * 0.08 + float(rng.normal(0, 0.6))
                _set(gs, a, b, nxt)
                if gs.is_human(tid):
                    if cur < FRIEND_BAR <= nxt:
                        gs.push_news(
                            f"{pa.handle} and {pb.handle} have become inseparable."
                        )
                    elif nxt <= FEUD_BAR < cur:
                        gs.push_news(
                            f"Friction between {pa.handle} and {pb.handle} "
                            f"is now impossible to miss."
                        )
        # Chemistry chases the roster's mean relationship.
        if len(roster) >= 2:
            pairs = [
                get(gs, a, b)
                for i, a in enumerate(roster)
                for b in roster[i + 1:]
            ]
            mean_rel = sum(pairs) / len(pairs)
            team = gs.teams[tid]
            team.chemistry = round(
                min(100.0, max(0.0, team.chemistry + (mean_rel - team.chemistry) * 0.15)),
                1,
            )
    _prune(gs)


def on_departure(gs: GameState, pid: str, team_id: str) -> None:
    """A player leaves a roster: close friends left behind take it hard.
    The relationship entries survive — history matters later."""
    p = gs.players.get(pid)
    if p is None:
        return
    for mate_id in gs.teams[team_id].player_ids:
        if mate_id == pid or mate_id not in gs.players:
            continue
        if get(gs, pid, mate_id) >= FRIEND_BAR:
            mate = gs.players[mate_id]
            mate.morale = round(max(0.0, mate.morale - 5.0), 1)
            if gs.is_human(team_id):
                gs.push_news(
                    f"{mate.handle} takes {p.handle}'s departure hard."
                )


def duos_and_feuds(gs: GameState, team_id: str) -> dict[str, list[tuple[str, str]]]:
    """Named duos/feuds on one roster, for the roster page."""
    roster = sorted(gs.teams[team_id].player_ids)
    out: dict[str, list[tuple[str, str]]] = {"duos": [], "feuds": []}
    for i, a in enumerate(roster):
        for b in roster[i + 1:]:
            rel = get(gs, a, b)
            if rel >= FRIEND_BAR:
                out["duos"].append((a, b))
            elif rel <= FEUD_BAR:
                out["feuds"].append((a, b))
    return out


def _prune(gs: GameState, cap: int = 800) -> None:
    """Keep the graph sparse: drop the least-informative entries (closest
    to neutral) once the dict outgrows the cap."""
    if len(gs.relationships) <= cap:
        return
    by_info = sorted(
        gs.relationships.items(), key=lambda kv: abs(kv[1] - 50.0)
    )
    for k, _ in by_info[: len(gs.relationships) - cap]:
        del gs.relationships[k]
