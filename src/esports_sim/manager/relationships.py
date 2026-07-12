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


def language_overlap(pa: Player, pb: Player) -> float:
    """How well two players can actually talk, 0..1: the best shared
    language, at the weaker speaker's fluency (a fluent/broken pair runs
    at broken). 0 = no common tongue. Players without language data (old
    saves pre-heal) read as neutral 0.6 so nothing shifts until the
    backfill has run."""
    if not pa.languages or not pb.languages:
        return 0.6
    best = 0.0
    for la in pa.languages:
        for lb in pb.languages:
            if la.lang == lb.lang:
                best = max(best, min(la.level, lb.level) / 100.0)
    return best


def team_comms_cohesion(gs: GameState, team_id: str) -> float:
    """Roster-wide comms read, 0-100: mean pairwise language overlap.
    Serialized for the roster page; the same overlap already shapes each
    pair's affinity target, which is how it reaches chemistry (and from
    there, the engine's existing chemistry channel)."""
    roster = sorted(gs.teams[team_id].player_ids)
    if len(roster) < 2:
        return 100.0
    pairs = [
        language_overlap(gs.players[a], gs.players[b])
        for i, a in enumerate(roster)
        for b in roster[i + 1:]
        if a in gs.players and b in gs.players
    ]
    return round(100.0 * sum(pairs) / max(len(pairs), 1), 1)


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
    # Comms: pairs who share a fluent tongue settle a shade warmer; a pair
    # with no common language never fully gels (-6 at zero overlap, +4 at
    # native/native). Flows into team chemistry via the mean-relationship
    # chase below — the engine's existing chemistry channel, no new reach.
    target += (language_overlap(pa, pb) - 0.6) * 10.0
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


def locker_room_fit(gs: GameState, pid: str, team_id: str) -> dict[str, object]:
    """Read a player's existing history with a prospective locker room.

    A player has no opinion about strangers (50, professional courtesy), but
    old teammates carry their relationship across moves.  This is deliberately
    a pure read: market, contract, and transfer code can all make the same
    decision without adding another mutable personality system.
    """
    mates = [
        mate_id for mate_id in sorted(gs.teams[team_id].player_ids)
        if mate_id != pid and mate_id in gs.players
    ]
    values = [(mate_id, get(gs, pid, mate_id)) for mate_id in mates]
    average = sum(value for _, value in values) / len(values) if values else 50.0
    friends = [mate_id for mate_id, value in values if value >= FRIEND_BAR]
    feuds = [mate_id for mate_id, value in values if value <= FEUD_BAR]
    worst_id, worst = min(values, key=lambda item: (item[1], item[0]), default=(None, 50.0))
    return {
        "average": round(average, 1),
        "friends": friends,
        "feuds": feuds,
        "worst_id": worst_id,
        "worst": round(worst, 1),
    }


def signing_veto(gs: GameState, pid: str, team_id: str) -> str | None:
    """A player will not voluntarily join an active locker-room feud."""
    fit = locker_room_fit(gs, pid, team_id)
    if fit["feuds"]:
        rival = gs.players[fit["worst_id"]]
        return f"{gs.players[pid].handle} refuses to share a locker room with {rival.handle}"
    return None


def renewal_veto(gs: GameState, pid: str, team_id: str) -> str | None:
    """An unhappy player in a sustained feud will not extend their deal."""
    fit = locker_room_fit(gs, pid, team_id)
    if fit["feuds"] and (fit["average"] <= 42.0 or gs.players[pid].morale <= 40.0):
        rival = gs.players[fit["worst_id"]]
        return f"{gs.players[pid].handle} will not renew while {rival.handle} remains"
    return None


def contract_fit_multiplier(gs: GameState, pid: str, team_id: str) -> float:
    """Salary multiplier from team history, capped to keep the market sane."""
    fit = locker_room_fit(gs, pid, team_id)
    # +/- 15% between a toxic and a beloved group; neutral history is exact 1.
    return 1.0 - max(-0.15, min(0.15, (float(fit["average"]) - 50.0) * 0.005))


def transfer_reaction(gs: GameState, pid: str, from_team_id: str, to_team_id: str) -> str | None:
    """Apply the immediate human consequence of a forced transfer.

    A fee can compel a move that a free agent would refuse.  Feuding arrivals
    lose morale, while a move between bitter rival orgs additionally gives an
    ambitious player a short-term prove-them-wrong confidence spark.
    """
    from esports_sim.manager import personality, rivalries

    p = gs.players[pid]
    fit = locker_room_fit(gs, pid, to_team_id)
    rivalry_heat = rivalries.get(gs, from_team_id, to_team_id)
    morale_delta = 6.0
    notes: list[str] = []
    if fit["friends"]:
        morale_delta += min(5.0, 2.0 * len(fit["friends"]))
        notes.append("reunites with a trusted teammate")
    if fit["feuds"]:
        morale_delta -= min(18.0, 8.0 + 4.0 * len(fit["feuds"]))
        rival = gs.players[fit["worst_id"]]
        notes.append(f"is furious about joining {rival.handle}")
    if rivalry_heat >= rivalries.RIVALRY_BAR:
        morale_delta -= min(8.0, rivalry_heat / 12.5)
        # Ambitious personalities can channel a hostile move into focus; this
        # is campaign confidence, never match-engine randomness.
        spark = max(0.0, personality.dev(p, "ambition")) * 8.0
        if spark:
            p.confidence = round(min(100.0, p.confidence + spark), 1)
            notes.append("takes the rivalry move personally")
    p.morale = round(min(100.0, max(0.0, p.morale + morale_delta)), 1)
    return "; ".join(notes) if notes else None


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
