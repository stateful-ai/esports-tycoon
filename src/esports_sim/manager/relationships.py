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


def key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def get(gs: GameState, a: str, b: str) -> float:
    return gs.relationships.get(key(a, b), 50.0)


def _set(gs: GameState, a: str, b: str, value: float) -> None:
    gs.relationships[key(a, b)] = round(min(100.0, max(0.0, value)), 1)


def affinity_target(pa: Player, pb: Player) -> float:
    """Where a pair naturally settles after enough time together."""
    target = 58.0  # shared reps breed mild friendship by default
    tags_a, tags_b = set(pa.personality_tags), set(pb.personality_tags)
    for t1, t2, delta in _CLASH + _KINDRED:
        if (t1 in tags_a and t2 in tags_b) or (t2 in tags_a and t1 in tags_b):
            target += delta
    return float(min(95.0, max(15.0, target)))


def weekly_tick(gs: GameState, rng: np.random.Generator, user_won: bool) -> None:
    """Drift every teammate pair toward its affinity target; results add
    a shared push (winning together bonds, losing grates). Crossing the
    friendship/feud bars makes news once per crossing."""
    for tid in sorted(gs.teams):
        roster = sorted(gs.teams[tid].player_ids)
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
                if tid == gs.user_team_id:
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
            if team_id == gs.user_team_id:
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
