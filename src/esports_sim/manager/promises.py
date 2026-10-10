from __future__ import annotations
import hashlib
import inspect
import math
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState
    from esports_sim.schemas.promise import ManagerPromise


def _play_time_duration(gs: GameState, promise: ManagerPromise, *, ticking: bool = False) -> int:
    """Original window, including the evaluator's legacy-save reconstruction.

    During evaluation weeks_left has already been decremented. Read-only views
    call before that decrement, so omit its compensating +1.
    """
    if promise.initial_duration > 0:
        return promise.initial_duration
    curr_week = getattr(gs, "week", 1)
    curr_season = getattr(gs, "season", 1)
    try:
        from esports_sim.manager.schedule import regular_season_weeks
        n_weeks = regular_season_weeks(gs.teams_per_region) if hasattr(gs, "teams_per_region") else 12
    except Exception:
        n_weeks = 12
    weeks_passed = max(0, curr_week - promise.created_week + (curr_season - promise.created_season) * n_weeks)
    return promise.weeks_left + weeks_passed + int(ticking)


def _play_time_requirement(duration: int, target_value: str | int | None) -> tuple[int, int]:
    target = target_value if target_value is not None else 100
    if isinstance(target, str):
        try:
            target = int(target)
        except ValueError:
            target = 100
    return target, math.ceil(duration * target / 100.0)


def _play_time_result(dressed: int, remaining: int, required: int) -> str:
    if dressed + remaining < required:
        return "broken"
    if remaining <= 0:
        return "kept" if dressed >= required else "broken"
    return "active"


def play_time_assessment(gs: GameState, promise: ManagerPromise) -> dict | None:
    """Pure public assessment using the same window, threshold and deadline rules.

    Resolved promises retain their recorded outcome; their weeks_left is a
    history-retention timer, not a deadline. Unknown types remain untouched.
    """
    if promise.promise_type != "play_time" or promise.status != "active":
        return None
    duration = _play_time_duration(gs, promise)
    target, required = _play_time_requirement(duration, promise.target_value)
    dressed = promise.dressed_count
    needed = max(0, required - dressed)
    remaining = promise.weeks_left
    percent = round(dressed / duration * 100, 1) if duration > 0 else None
    fulfillment = min(100, max(0, round(dressed / required * 100))) if required > 0 else 100
    next_dressed = _play_time_result(dressed + 1, remaining - 1, required)
    next_benched = _play_time_result(dressed, remaining - 1, required)
    week_word = "week" if duration == 1 else "weeks"
    deadline = (
        "Deadline: at the next weekly evaluation."
        if remaining <= 1 else f"Deadline: after {remaining} more weekly evaluations."
    )
    outcomes = {"active": "promise stays active", "kept": "promise kept", "broken": "promise broken"}
    return {
        "window_weeks": duration,
        "target_percent": target,
        "required_dressed_weeks": required,
        "dressed_weeks": dressed,
        "dressed_percent": percent,
        "additional_dressed_weeks_needed": needed,
        "evaluations_left": remaining,
        "fulfillment_percent": fulfillment,
        "next_dressed_status": next_dressed,
        "next_not_dressed_status": next_benched,
        "target_label": f"Target: {target}% of {duration} window {week_word}, rounded up = {required} dressed weeks.",
        "progress_label": f"Progress: {dressed}/{duration} window weeks dressed" + (f" ({percent:g}%)." if percent is not None else ".") + f" {needed} more needed to reach {required}.",
        "deadline_label": deadline,
        "counting_label": "Each weekly evaluation counts at most once: dress for at least one played map to earn credit. Weeks without a played map still use time.",
        "next_evaluation_label": f"Next evaluation: if dressed, {dressed + 1}/{required} required weeks ({outcomes[next_dressed]}); if not dressed, {dressed}/{required} ({outcomes[next_benched]}).",
    }

def create_promise(
    gs: GameState,
    team_id: str,
    player_id: str,
    promise_type: str,
    target_value: int = 0,
    duration: int = 0,
    *,
    source: str = "talk",
) -> ManagerPromise:
    """Construct a ManagerPromise and append it to gs.promises. Return the promise.

    THE single creation path for every promise doorway (talk, llm, and the
    deterministic negotiation/transfer/bench/leadership seams). ``source``
    records provenance for inbox copy + dedup. The id is a blake2b hash of
    (season | week | player | type) so it is replay-stable and independent of
    ``len(gs.promises)`` (which desyncs across prunes). If a duplicate active
    promise exists for the same player, type and target_value, its duration is
    updated in place instead of appending a second entry.
    """
    from esports_sim.schemas.promise import ManagerPromise

    # Find if duplicate exists (matching type, player, and target_value if specified)
    existing = None
    for p in gs.promises:
        if p.player_id == player_id and p.promise_type == promise_type and p.status == "active":
            if p.target_value == target_value:
                existing = p
                break

    if existing is not None:
        existing.weeks_left = duration
        return existing

    season = getattr(gs, "season", 1)
    week = getattr(gs, "week", 1)
    promise_id = hashlib.blake2b(
        f"{season}|{week}|{player_id}|{promise_type}".encode("utf-8")
    ).hexdigest()[:16]
    promise = ManagerPromise(
        id=promise_id,
        team_id=team_id,
        player_id=player_id,
        promise_type=promise_type,
        target_value=target_value,
        weeks_left=duration,
        created_week=week,
        created_season=season,
        status="active",
        dressed_count=0,
        initial_duration=duration,
        source=source,
    )
    gs.promises.append(promise)

    return promise


def offer_from_negotiation(
    gs: GameState, team_id: str, player_id: str, role: str, weeks: int
) -> ManagerPromise | None:
    """F3 SEAM A: a settled contract that concedes a starter seat implies a
    play-time commitment. Returns the created ``play_time`` promise (target ~60,
    duration capped at 8 weeks, source='negotiation') when ``role == 'starter'``,
    else None so renewals that don't concede a seat don't spam promises."""
    if role != "starter":
        return None
    duration = max(1, min(int(weeks), 8))
    return create_promise(
        gs, team_id, player_id, "play_time",
        target_value=60, duration=duration, source="negotiation",
    )


def offer_from_transfer_reset(
    gs: GameState, team_id: str, player_id: str
) -> ManagerPromise:
    """F3 SEAM B: withdrawing/repairing a transfer request implies a fresh
    play-time reset promise (target ~60, source='transfer_request')."""
    return create_promise(
        gs, team_id, player_id, "play_time",
        target_value=60, duration=6, source="transfer_request",
    )


def offer_from_leadership(
    gs: GameState, team_id: str, player_id: str
) -> ManagerPromise:
    """F3 SEAM D: the captaincy doorway creates a ``make_captain`` promise
    (source='leadership') that resolves through the existing culture leadership
    path once the player becomes captain."""
    return create_promise(
        gs, team_id, player_id, "make_captain",
        target_value=0, duration=8, source="leadership",
    )


def resolve_promise(gs: GameState, promise: ManagerPromise, success: bool) -> None:
    """Resolve a promise and apply morale/chemistry effects."""
    from esports_sim.manager import locker_room

    if success:
        promise.status = "kept"
        player = gs.players.get(promise.player_id)
        if player:
            player.morale = round(min(100.0, player.morale + 10.0), 1)
        team = gs.teams.get(promise.team_id)
        if team:
            role = locker_room.get_hierarchy_role(gs, promise.player_id, promise.team_id)
            if role in ("incumbent_leader", "leader"):
                team.chemistry = round(min(100.0, team.chemistry + 15.0), 1)
            else:
                team.chemistry = round(min(100.0, team.chemistry + 5.0), 1)
    else:
        promise.status = "broken"
        player = gs.players.get(promise.player_id)
        if player:
            from esports_sim.manager import personality
            p_axes = personality.axes(player)
            ego = p_axes.get("ego", 50.0)
            prof = p_axes.get("professionalism", 50.0)
            mult = max(0.1, 1.0 + (ego - 50.0) / 100.0 - (prof - 50.0) / 100.0)
            drop = 25.0 * mult
            player.morale = round(max(0.0, player.morale - drop), 1)
            player.confidence = round(max(0.0, player.confidence - 15.0), 1)
        
        team = gs.teams.get(promise.team_id)
        if team:
            team.chemistry = round(max(0.0, team.chemistry - 8.0), 1)
            if promise.player_id in team.player_ids:
                role = locker_room.get_hierarchy_role(gs, promise.player_id, promise.team_id)
                if role in ("leader", "incumbent_leader", "council_member", "influential", "key_influencer", "loyal_lieutenant", "volatile_rebel"):
                    for mate in gs.roster(promise.team_id):
                        if mate.id != promise.player_id:
                            from esports_sim.manager import relationships
                            rel = relationships.get(gs, mate.id, promise.player_id)
                            rel_threshold = 50.0
                            if rel >= rel_threshold:
                                mate.morale = round(max(0.0, mate.morale - 20.0), 1)
                            else:
                                mate.morale = round(max(0.0, mate.morale - 3.0), 1)

    promise.weeks_left = 4


def weekly_tick(gs: GameState, week_dressed: dict[str, set[str]]) -> None:
    """Evaluate active manager promises, decrement duration, and clean up expired ones."""
    for promise in gs.promises:
        promise.weeks_left -= 1

    for promise in list(gs.promises):
        if promise.status != "active":
            continue

        if promise.player_id not in gs.players:
            resolve_promise(gs, promise, success=False)
            continue

        if promise.promise_type == "play_time":
            if promise.initial_duration <= 0:
                promise.initial_duration = _play_time_duration(gs, promise, ticking=True)

            played = week_dressed.get(promise.team_id, set())
            if promise.player_id in played:
                promise.dressed_count += 1

            _, required = _play_time_requirement(promise.initial_duration, promise.target_value)
            outcome = _play_time_result(promise.dressed_count, promise.weeks_left, required)
            if outcome != "active":
                resolve_promise(gs, promise, success=(outcome == "kept"))

        elif promise.promise_type == "make_captain":
            team = gs.teams.get(promise.team_id)
            if team and team.captain_id == promise.player_id:
                resolve_promise(gs, promise, success=True)
            elif promise.weeks_left <= 0:
                resolve_promise(gs, promise, success=False)

        elif promise.promise_type == "renew_contract":
            if promise.weeks_left <= 0:
                resolve_promise(gs, promise, success=False)

    gs.promises = [p for p in gs.promises if (p.status == "active" or p.weeks_left > 0) and p.player_id in gs.players]
