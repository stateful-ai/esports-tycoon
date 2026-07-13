from __future__ import annotations
import inspect
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState
    from esports_sim.schemas.promise import ManagerPromise

# Module level tracker for playtime promises to maintain precise statistics
_playtime_tracker: dict[str, dict[str, int]] = {}


def create_promise(gs: GameState, team_id: str, player_id: str, promise_type: str, target_value: int = 0, duration: int = 0) -> ManagerPromise:
    """Construct a ManagerPromise and append it to gs.promises. Return the promise.

    If a duplicate active promise exists for the same player, type and target_value, update its duration.
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

    promise_id = f"p_{len(gs.promises)}_{player_id}_{promise_type}"
    promise = ManagerPromise(
        id=promise_id,
        team_id=team_id,
        player_id=player_id,
        promise_type=promise_type,
        target_value=target_value,
        weeks_left=duration,
        created_week=getattr(gs, "week", 1),
        created_season=getattr(gs, "season", 1),
        status="active"
    )
    gs.promises.append(promise)

    # Initialize tracking
    _playtime_tracker[promise_id] = {
        "dressed_count": 0,
        "weeks_passed": 0,
        "initial_duration": duration
    }

    return promise


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

    if promise.id in _playtime_tracker:
        _playtime_tracker.pop(promise.id, None)


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
            if promise.id not in _playtime_tracker:
                curr_week = getattr(gs, "week", 1)
                curr_season = getattr(gs, "season", 1)
                p_week = promise.created_week
                p_season = promise.created_season
                try:
                    from esports_sim.manager.schedule import regular_season_weeks
                    n_weeks = regular_season_weeks(gs.teams_per_region) if hasattr(gs, "teams_per_region") else 12
                except Exception:
                    n_weeks = 12
                weeks_passed = max(0, curr_week - p_week + (curr_season - p_season) * n_weeks)
                initial_duration = promise.weeks_left + weeks_passed + 1
                _playtime_tracker[promise.id] = {
                    "dressed_count": 0,
                    "weeks_passed": weeks_passed,
                    "initial_duration": initial_duration
                }

            played = week_dressed.get(promise.team_id, set())
            if promise.player_id in played:
                _playtime_tracker[promise.id]["dressed_count"] += 1
            _playtime_tracker[promise.id]["weeks_passed"] += 1

            # Compute required dressed weeks
            target = promise.target_value if promise.target_value is not None else 100
            if isinstance(target, str):
                try:
                    target = int(target)
                except ValueError:
                    target = 100
            
            D = _playtime_tracker[promise.id]["initial_duration"]
            import math
            R = math.ceil(D * target / 100.0)

            dressed_count = _playtime_tracker[promise.id]["dressed_count"]
            weeks_left = promise.weeks_left

            if dressed_count + weeks_left < R:
                resolve_promise(gs, promise, success=False)
            elif weeks_left <= 0:
                resolve_promise(gs, promise, success=(dressed_count >= R))

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
