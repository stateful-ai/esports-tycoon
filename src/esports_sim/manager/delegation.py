"""Staff policies that automate chores without inventing extra resources."""

from __future__ import annotations

from typing import TYPE_CHECKING

from esports_sim.manager import market, training
from esports_sim.manager.state import DelegationPolicy, DelegationReport
from esports_sim.schemas.common import Region, Role

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState


ALERT_LEVELS = ("all_matches", "shortlist", "tier1_ready")
TIER1_READY_QUALITY = 65.0
SHORTLIST_QUALITY = 56.0
REPORT_CAP = 16


def policy_for(gs: "GameState", team_id: str) -> DelegationPolicy:
    return gs.delegation_policies_by.get(team_id, DelegationPolicy())


def configure(gs: "GameState", team_id: str, values: dict) -> DelegationPolicy:
    """Validate and persist a complete staff policy for one human seat."""
    if team_id not in gs.teams:
        raise ValueError("unknown team")
    policy = DelegationPolicy.model_validate(values)
    if policy.renewal_salary_min > policy.renewal_salary_max:
        raise ValueError("renewal salary minimum cannot exceed the maximum")
    if policy.scout_region not in {str(region) for region in Region}:
        raise ValueError("unknown scouting region")
    roles = sorted(set(policy.scout_roles))
    if not roles or any(role not in {str(item) for item in Role} for role in roles):
        raise ValueError("choose at least one valid scouting role")
    if policy.alert_level not in ALERT_LEVELS:
        raise ValueError("unknown prospect alert threshold")
    policy.scout_roles = roles
    gs.delegation_policies_by[team_id] = policy
    return policy


def pick_training_focus(gs: "GameState", team_id: str, roster, rng) -> str:
    """Return this week's human focus, letting the coach choose when asked.

    Delegation uses the existing roster-aware AI coaching read and the week's
    campaign RNG. With the policy off this is an exact no-op: the manager's
    persisted focus is returned without drawing randomness.
    """
    current = gs.training_focus.get(team_id, "tactical")
    if not policy_for(gs, team_id).auto_training:
        return current
    focus = training.ai_pick_focus(roster, rng, gs.teams[team_id])
    gs.training_focus[team_id] = focus
    return focus


def _core_ids(gs: "GameState", team_id: str) -> set[str]:
    team = gs.teams[team_id]
    explicit = [pid for pid in team.lineup_ids if pid in team.player_ids]
    ranked = sorted(
        team.player_ids,
        key=lambda pid: (-market.player_quality(gs.players[pid]), pid),
    )
    core = explicit[:5]
    for pid in ranked:
        if pid not in core:
            core.append(pid)
        if len(core) == 5:
            break
    core.extend(
        pid
        for pid in team.player_ids
        if gs.players[pid].roster_role == "starter" and pid not in core
    )
    return set(core)


def _player_region(gs: "GameState", player_id: str) -> str | None:
    owner = market.team_of(gs, player_id)
    player = gs.players[player_id]
    return str(gs.teams[owner].region) if owner in gs.teams else str(player.region)


def matching_players(gs: "GameState", team_id: str) -> list[str]:
    policy = policy_for(gs, team_id)
    if not policy.auto_scout:
        return []
    own = set(gs.teams[team_id].player_ids)
    return [
        pid
        for pid in sorted(gs.players)
        if pid not in own
        and gs.players[pid].age <= policy.scout_max_age
        and str(gs.players[pid].role) in policy.scout_roles
        and _player_region(gs, pid) == policy.scout_region
    ]


def _readiness(gs: "GameState", team_id: str, player_id: str) -> tuple[str, float]:
    progress = gs.scout_progress_by.get(team_id, {}).get(f"player:{player_id}", 0.0)
    quality = market.perceived_quality(gs, team_id, gs.players[player_id])
    if progress >= 0.50 and quality >= TIER1_READY_QUALITY:
        return "tier1_ready", quality
    if progress >= 0.35 and quality >= SHORTLIST_QUALITY:
        return "shortlist", quality
    return "monitoring", quality


def _alert_ready(level: str, readiness: str, progress: float) -> bool:
    if level == "tier1_ready":
        return readiness == "tier1_ready"
    if level == "shortlist":
        return readiness in ("shortlist", "tier1_ready")
    return progress >= 0.25


def begin_week(gs: "GameState") -> None:
    """Renew eligible starters and point the existing scout desk at its queue.

    AI clubs keep their existing renewal/market logic. This feature is a human
    workload control, and uses the same salary and one-target scouting paths a
    hands-on manager uses rather than adding a competitive resource.
    """
    for team_id in sorted(gs.human_team_ids):
        policy = policy_for(gs, team_id)
        report = DelegationReport(season=gs.season, week=gs.week)
        team = gs.teams[team_id]
        if policy.auto_renew_core:
            core = _core_ids(gs, team_id)
            for player_id in sorted(core):
                player = gs.players.get(player_id)
                if (
                    player is None
                    or not 0 < player.contract_weeks_left <= policy.renewal_trigger_weeks
                ):
                    continue
                salary = market.renewal_salary(gs, team_id, player_id)
                if not policy.renewal_salary_min <= salary <= policy.renewal_salary_max:
                    report.exceptions.append(
                        f"{player.handle}: {salary:,}/wk is outside the delegated band"
                    )
                    continue
                if team.balance < salary * 8:
                    report.exceptions.append(
                        f"{player.handle}: need {salary * 8:,} cr for the wage cushion"
                    )
                    continue
                ok, reason = market.renew_contract(
                    gs, team_id, player_id, salary=salary
                )
                if ok:
                    report.renewed_player_ids.append(player_id)
                else:
                    report.exceptions.append(f"{player.handle}: {reason}")

        matches = matching_players(gs, team_id)
        if policy.auto_scout and matches:
            progress = gs.scout_progress_by.setdefault(team_id, {})
            # Route the department's recruit deep-dive through the standing
            # AMATEUR lane (scouting.tick reads scout_lanes_by now) instead of
            # clobbering the single scout_targets slot the RL/decision-env path
            # still owns. The pro lane stays free for the manager's own
            # opponent/fill-gap directive.
            lane = gs.scout_lanes_by.setdefault(team_id, {})
            current = lane.get("amateur")
            current_pid = (
                current.removeprefix("player:")
                if current and current.startswith("player:")
                else ""
            )
            if (
                current_pid not in matches
                or progress.get(f"player:{current_pid}", 0.0) >= 1.0
            ):
                current_pid = min(
                    matches,
                    key=lambda pid: (progress.get(f"player:{pid}", 0.0), pid),
                )
                lane["amateur"] = f"player:{current_pid}"
            report.scout_player_id = current_pid

        rows = gs.delegation_reports_by.setdefault(team_id, [])
        previous_exceptions = list(rows[-1].exceptions) if rows else []
        rows.append(report)
        del rows[:-REPORT_CAP]
        if report.exceptions and report.exceptions != previous_exceptions:
            gs.push_private_news(
                "Delegation exceptions: " + "; ".join(report.exceptions), owner=team_id
            )


def finalize_week(gs: "GameState") -> None:
    """Emit only alerts that cross the configured manager-information bar."""
    for team_id in sorted(gs.human_team_ids):
        policy = policy_for(gs, team_id)
        if not policy.auto_scout:
            continue
        reports = gs.delegation_reports_by.get(team_id, [])
        if not reports or (reports[-1].season, reports[-1].week) != (gs.season, gs.week):
            continue
        alerted = set(gs.delegation_alerted_players_by.get(team_id, []))
        progress = gs.scout_progress_by.get(team_id, {})
        for player_id in matching_players(gs, team_id):
            if player_id in alerted:
                continue
            readiness, quality = _readiness(gs, team_id, player_id)
            seen = progress.get(f"player:{player_id}", 0.0)
            if not _alert_ready(policy.alert_level, readiness, seen):
                continue
            player = gs.players[player_id]
            message = (
                f"Staff alert: {player.handle} is {readiness.replace('_', ' ')} "
                f"on the current {seen:.0%} scouting book."
            )
            reports[-1].alerts.append(message)
            gs.push_private_news(message, owner=team_id)
            alerted.add(player_id)
        gs.delegation_alerted_players_by[team_id] = sorted(alerted)


def _active_amateur_pid(gs: "GameState", team_id: str) -> str:
    """The player the auto-scout lane is currently deep-diving, if any.

    Reads the standing amateur lane (where begin_week now parks the recruit)
    and falls back to the legacy single slot for pre-migration saves."""
    lane = gs.scout_lanes_by.get(team_id) or {}
    value = lane.get("amateur") or ""
    if not value.startswith("player:"):
        value = gs.scout_targets.get(team_id, "") or ""
    return value.removeprefix("player:") if value.startswith("player:") else ""


def view(gs: "GameState", team_id: str) -> dict:
    policy = policy_for(gs, team_id)
    matches = matching_players(gs, team_id)
    latest = gs.delegation_reports_by.get(team_id, [])[-1:]
    return {
        "policy": policy.model_dump(mode="json"),
        "regions": [str(region) for region in Region],
        "roles": [str(role) for role in Role],
        "alert_levels": list(ALERT_LEVELS),
        "matching_count": len(matches),
        "active_scout_player_id": _active_amateur_pid(gs, team_id),
        "latest_report": latest[0].model_dump(mode="json") if latest else None,
    }
