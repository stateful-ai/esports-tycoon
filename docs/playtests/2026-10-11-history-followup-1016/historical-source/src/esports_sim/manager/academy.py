"""Academy and affiliate operations.

The campaign already simulates a complete Challengers (tier-2) circuit.  This
module lets tier-1 organizations use those teams as real affiliates instead of
creating a second, hidden youth league.  All selection and progression is
draw-free: stable ids, the campaign seed, and played box scores are the only
inputs.

Persisted state is deliberately small and save-friendly::

    academy_affiliates: dict[parent_team_id, affiliate_team_id]
    academy_levels: dict[parent_team_id, int]          # 0..3
    academy_reports_by: dict[parent_team_id, list[dict]]

The view functions return plain dictionaries so the web layer remains a thin
consumer of campaign state.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from esports_sim.manager import development

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState


ACADEMY_MAX_AGE = 23
ACADEMY_MAX_LEVEL = 3
REPORT_LIMIT = 32
WEEKLY_GAIN_CAP = 0.14  # F1: prospects actually develop from affiliate minutes
UPGRADE_COST = {1: 120_000, 2: 300_000, 3: 650_000}

WindowCheck = Callable[["GameState", str], bool | tuple[bool, str]]


def _stable_int(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big")


def _state_map(gs: "GameState", name: str) -> dict:
    value = getattr(gs, name, None)
    if not isinstance(value, dict):
        raise AttributeError(f"GameState must define {name} as a dict")
    return value


def _level(gs: "GameState", parent_tid: str) -> int:
    raw = _state_map(gs, "academy_levels").get(parent_tid, 0)
    return max(0, min(ACADEMY_MAX_LEVEL, int(raw)))


def _roster_limits() -> tuple[int, int]:
    # Lazy import keeps academy independent from market's transfer workflow and
    # leaves room for market to call these APIs later without an import cycle.
    from esports_sim.manager.market import ROSTER_MAX, ROSTER_MIN

    return ROSTER_MIN, ROSTER_MAX


def _append_report(gs: "GameState", parent_tid: str, report: dict[str, Any]) -> None:
    reports = _state_map(gs, "academy_reports_by").setdefault(parent_tid, [])
    reports.append(report)
    del reports[:-REPORT_LIMIT]


def _has_report(
    gs: "GameState", parent_tid: str, kind: str, *, affiliate_id: str = ""
) -> bool:
    reports = _state_map(gs, "academy_reports_by").get(parent_tid, [])
    return any(
        report.get("kind") == kind
        and int(report.get("season", -1)) == gs.season
        and (not affiliate_id or report.get("affiliate_id") == affiliate_id)
        and (kind != "weekly" or int(report.get("week", -1)) == gs.week)
        for report in reports
    )


def seed_affiliates(gs: "GameState") -> dict[str, str]:
    """Pair every tier-1 organization with a same-region tier-2 side.

    Each affiliate is used once before any is reused.  Reuse is unavoidable in
    the default 8x6 regional shape; the round-robin assignment keeps shared
    affiliates balanced to within one parent.
    """
    mapping = _state_map(gs, "academy_affiliates")
    levels = _state_map(gs, "academy_levels")
    reports = _state_map(gs, "academy_reports_by")
    rights = _state_map(gs, "academy_player_rights")

    seeded: dict[str, str] = {}
    regions = sorted({str(team.region) for team in gs.teams.values()})
    for region in regions:
        parents = sorted(
            team.id
            for team in gs.teams.values()
            if team.tier == 1 and str(team.region) == region
        )
        affiliates = sorted(
            team.id
            for team in gs.teams.values()
            if team.tier == 2 and str(team.region) == region
        )
        if not affiliates:
            continue
        for index, parent_tid in enumerate(parents):
            seeded[parent_tid] = affiliates[index % len(affiliates)]
            levels.setdefault(parent_tid, 1)
            reports.setdefault(parent_tid, [])

    # Re-seeding heals stale mappings after imported-world shape changes while
    # retaining no entry for a region that has no development circuit.
    mapping.clear()
    mapping.update(seeded)
    for parent_tid in sorted(set(levels) - set(seeded)):
        levels.pop(parent_tid, None)
    for parent_tid in sorted(set(reports) - set(seeded)):
        reports.pop(parent_tid, None)
    # Compact worlds can have more parent orgs than Challengers teams. Split
    # promotion rights across the parents attached to that shared affiliate;
    # every player has exactly one owner, so parents cannot steal prospects.
    parents_by_affiliate: dict[str, list[str]] = {}
    for parent_tid, affiliate_tid in sorted(seeded.items()):
        parents_by_affiliate.setdefault(affiliate_tid, []).append(parent_tid)
    valid_players = {
        pid for affiliate_tid in parents_by_affiliate
        for pid in gs.teams[affiliate_tid].player_ids
    }
    for pid in sorted(set(rights) - valid_players):
        rights.pop(pid, None)
    for affiliate_tid, parents in sorted(parents_by_affiliate.items()):
        parents = sorted(parents)
        for index, pid in enumerate(sorted(gs.teams[affiliate_tid].player_ids)):
            if rights.get(pid) not in parents:
                rights[pid] = parents[index % len(parents)]
    return dict(mapping)


def affiliate_for(gs: "GameState", parent_tid: str) -> str | None:
    """Return the tier-2 affiliate id for ``parent_tid``, if one exists."""
    affiliate_tid = _state_map(gs, "academy_affiliates").get(parent_tid)
    if not affiliate_tid:
        return None
    parent = gs.teams.get(parent_tid)
    affiliate = gs.teams.get(affiliate_tid)
    if (
        parent is None
        or affiliate is None
        or parent.tier != 1
        or affiliate.tier != 2
        or parent.region != affiliate.region
    ):
        return None
    return affiliate_tid


def academy_view(gs: "GameState", parent_tid: str) -> dict[str, Any]:
    """Serialize one organization's academy without exposing rival state."""
    parent = gs.teams.get(parent_tid)
    affiliate_tid = affiliate_for(gs, parent_tid)
    if parent is None or affiliate_tid is None:
        return {
            "parent_id": parent_tid,
            "affiliate_id": None,
            "level": 0,
            "roster": [],
            "reports": [],
        }

    affiliate = gs.teams[affiliate_tid]
    roster: list[dict[str, Any]] = []
    for pid in sorted(affiliate.player_ids):
        player = gs.players.get(pid)
        if player is None:
            continue
        stats = gs.player_stats.get(pid)
        pa_low, pa_high = development.potential_projection(player, own=True)
        roster.append(
            {
                "id": pid,
                "handle": player.handle,
                "age": player.age,
                "role": str(player.role),
                "roster_role": player.roster_role,
                "ability": round(development.overall(player), 1),
                "potential_band": [round(pa_low, 1), round(pa_high, 1)],
                "maps": stats.maps if stats is not None else 0,
                "rating": round(stats.rating, 2) if stats is not None else 0.0,
                "owned": gs.academy_player_rights.get(pid) == parent_tid,
            }
        )
    roster.sort(
        key=lambda row: (-row["potential_band"][1], -row["ability"], row["id"])
    )

    reports = _state_map(gs, "academy_reports_by").get(parent_tid, [])
    return {
        "parent_id": parent_tid,
        "parent_name": parent.name,
        "affiliate_id": affiliate_tid,
        "affiliate_name": affiliate.name,
        "level": _level(gs, parent_tid),
        "roster": roster,
        "reports": [dict(report) for report in reports[-8:]],
        "next_upgrade_cost": UPGRADE_COST.get(_level(gs, parent_tid) + 1),
    }


def upgrade(gs: "GameState", parent_tid: str) -> tuple[bool, str]:
    """Invest one tier in scouting reach, intake slots, and coaching gains."""
    if affiliate_for(gs, parent_tid) is None:
        return False, "organization has no academy affiliate"
    level = _level(gs, parent_tid)
    target = level + 1
    cost = UPGRADE_COST.get(target)
    if cost is None:
        return False, "academy program is already at maximum level"
    team = gs.teams[parent_tid]
    if team.balance < cost:
        return False, f"need {cost:,} cr to upgrade the academy program"
    team.balance -= cost
    gs.academy_levels[parent_tid] = target
    gs.push_news(
        f"{team.name} expand their academy program to level {target} ({cost:,} cr)."
    )
    return True, f"academy program upgraded to level {target}"


def _window_result(
    gs: "GameState", parent_tid: str, window_check: WindowCheck | None
) -> tuple[bool, str]:
    if window_check is None:
        return True, ""
    result = window_check(gs, parent_tid)
    if isinstance(result, tuple):
        return bool(result[0]), str(result[1])
    return (True, "") if result else (False, "academy moves are not allowed now")


def can_move(
    gs: "GameState",
    parent_tid: str,
    player_id: str,
    direction: str,
    *,
    window_check: WindowCheck | None = None,
) -> tuple[bool, str]:
    """Validate a promotion or send-down without mutating the campaign."""
    affiliate_tid = affiliate_for(gs, parent_tid)
    if affiliate_tid is None:
        return False, "organization has no academy affiliate"
    if direction not in ("promote", "send_down"):
        return False, "direction must be promote or send_down"
    ok, why = _window_result(gs, parent_tid, window_check)
    if not ok:
        return False, why
    player = gs.players.get(player_id)
    if player is None:
        return False, "unknown player"

    parent = gs.teams[parent_tid]
    affiliate = gs.teams[affiliate_tid]
    roster_min, roster_max = _roster_limits()
    if direction == "promote":
        if player_id not in affiliate.player_ids:
            return False, "player is not on the academy affiliate"
        if gs.academy_player_rights.get(player_id) != parent_tid:
            return False, "another parent organization holds this player's pathway rights"
        if len(affiliate.player_ids) - 1 < roster_min:
            return False, f"affiliate must retain at least {roster_min} players"
        if len(parent.player_ids) + 1 > roster_max:
            return False, f"first-team roster is full ({roster_max})"
    else:
        if player_id not in parent.player_ids:
            return False, "player is not on the first-team roster"
        if player.age > ACADEMY_MAX_AGE:
            return False, f"only players age {ACADEMY_MAX_AGE} or younger can be sent down"
        if len(parent.player_ids) - 1 < roster_min:
            return False, f"first team must retain at least {roster_min} players"
        if len(affiliate.player_ids) + 1 > roster_max:
            return False, f"affiliate roster is full ({roster_max})"
    return True, ""


def _remove_stale_lineups(gs: "GameState", source_tid: str, player_id: str) -> None:
    source = gs.teams[source_tid]
    source.lineup_ids = [pid for pid in source.lineup_ids if pid != player_id]
    source.lineup.starters = [pid for pid in source.lineup.starters if pid != player_id]
    source.lineup.agents.pop(player_id, None)
    for key in sorted(gs.map_lineups):
        if key.startswith(f"{source_tid}|"):
            gs.map_lineups[key] = [pid for pid in gs.map_lineups[key] if pid != player_id]


def _prune_mentorships(gs: "GameState", player_id: str) -> None:
    mentorships = getattr(gs, "mentorships", None)
    if not isinstance(mentorships, dict):
        return
    mentorships.pop(player_id, None)
    for protege_id in sorted(list(mentorships)):
        if mentorships[protege_id] == player_id:
            mentorships.pop(protege_id, None)


def move_player(
    gs: "GameState",
    parent_tid: str,
    player_id: str,
    direction: str,
    *,
    window_check: WindowCheck | None = None,
) -> tuple[bool, str]:
    """Promote or send down a player, retaining their existing contract."""
    ok, why = can_move(
        gs, parent_tid, player_id, direction, window_check=window_check
    )
    if not ok:
        return False, why

    affiliate_tid = affiliate_for(gs, parent_tid)
    assert affiliate_tid is not None  # proven by can_move
    source_tid, target_tid = (
        (affiliate_tid, parent_tid)
        if direction == "promote"
        else (parent_tid, affiliate_tid)
    )
    source = gs.teams[source_tid]
    target = gs.teams[target_tid]
    player = gs.players[player_id]

    source.player_ids.remove(player_id)
    target.player_ids.append(player_id)
    _remove_stale_lineups(gs, source_tid, player_id)
    if source.captain_id == player_id:
        source.captain_id = min(source.player_ids, default=None)
    if target.captain_id is None:
        target.captain_id = player_id
    player.roster_role = "bench" if direction == "promote" else "academy"
    if direction == "promote":
        gs.academy_player_rights.pop(player_id, None)
    else:
        gs.academy_player_rights[player_id] = parent_tid
    _prune_mentorships(gs, player_id)

    verb = "promoted" if direction == "promote" else "sent down"
    _append_report(
        gs,
        parent_tid,
        {
            "kind": "move",
            "season": gs.season,
            "week": gs.week,
            "parent_id": parent_tid,
            "affiliate_id": affiliate_tid,
            "player_id": player_id,
            "direction": direction,
        },
    )
    if gs.is_human(parent_tid):
        gs.push_private_news(
            f"{player.handle} has been {verb} within the {gs.teams[parent_tid].name} academy system.",
            owner=parent_tid,
        )
    return True, f"{verb} {player.handle}"


def _prospect_key(gs: "GameState", parent_tid: str, player_id: str) -> tuple:
    player = gs.players[player_id]
    ability = development.overall(player)
    potential = development.potential_of(player)
    # Upside is primary, but a prospect who is already close to tier-2 minutes
    # is more useful than an equally promising raw project.
    value = potential + ability * 0.20 - player.age * 0.40
    tie = _stable_int(gs.seed, gs.season, "academy-intake", parent_tid, player_id)
    return (-value, tie, player_id)


def offseason_intake(gs: "GameState") -> list[dict[str, Any]]:
    """Place young free agents into affiliates using the same rules for AI.

    A level grants one intake slot (level 1) up to three (level 3).  Slots are
    allocated in rounds so a level-3 academy cannot consume the whole pool
    before level-1 organizations get a chance.  Parent priority rotates by a
    stable season hash, giving scarce prospect classes long-run parity.
    """
    _, roster_max = _roster_limits()
    parents = [
        parent_tid
        for parent_tid in sorted(_state_map(gs, "academy_affiliates"))
        if affiliate_for(gs, parent_tid) is not None
        and _level(gs, parent_tid) > 0
        and not _has_report(gs, parent_tid, "intake")
    ]
    parents.sort(
        key=lambda tid: (_stable_int(gs.seed, gs.season, "academy-order", tid), tid)
    )
    eligible = {
        pid
        for pid in gs.free_agent_ids
        if pid in gs.players and gs.players[pid].age <= ACADEMY_MAX_AGE
    }
    added_by: dict[str, list[str]] = {tid: [] for tid in parents}

    for slot in range(ACADEMY_MAX_LEVEL):
        for parent_tid in parents:
            if _level(gs, parent_tid) <= slot or not eligible:
                continue
            affiliate_tid = affiliate_for(gs, parent_tid)
            assert affiliate_tid is not None
            affiliate = gs.teams[affiliate_tid]
            if len(affiliate.player_ids) >= roster_max:
                continue
            candidates = set(eligible)
            rookie_ids = {
                pid for pid in eligible
                if "rookie" in gs.players[pid].personality_tags
            }
            if len(rookie_ids) == 1:
                # The announced rookie class must remain visible to the open
                # market; academies can draft around its final representative.
                candidates -= rookie_ids
            if not candidates:
                continue
            player_id = min(
                candidates, key=lambda pid: _prospect_key(gs, parent_tid, pid)
            )
            player = gs.players[player_id]
            affiliate.player_ids.append(player_id)
            gs.academy_player_rights[player_id] = parent_tid
            eligible.remove(player_id)
            gs.free_agent_ids.remove(player_id)

            from esports_sim.manager import market

            player.salary = player.salary or market.asking_salary(player)
            player.contract_weeks_left = max(player.contract_weeks_left, 40)
            player.tenure_weeks = 0
            player.morale = min(100.0, player.morale + 4.0)
            market.seed_existing_contract_terms(gs, affiliate_tid, player, "academy")
            added_by[parent_tid].append(player_id)

    reports: list[dict[str, Any]] = []
    for parent_tid in parents:
        affiliate_tid = affiliate_for(gs, parent_tid)
        assert affiliate_tid is not None
        report = {
            "kind": "intake",
            "season": gs.season,
            "week": gs.week,
            "parent_id": parent_tid,
            "affiliate_id": affiliate_tid,
            "player_ids": added_by[parent_tid],
        }
        _append_report(gs, parent_tid, report)
        reports.append(report)
        if added_by[parent_tid] and gs.is_human(parent_tid):
            handles = ", ".join(gs.players[pid].handle for pid in added_by[parent_tid])
            gs.push_private_news(
                f"Academy intake: {handles} join {gs.teams[affiliate_tid].name}.",
                owner=parent_tid,
            )
    return reports


def ai_manage(gs: "GameState") -> None:
    """Deterministic AI academy investment and one-for-one promotion parity.

    AI first teams stay lean at five: a clearly better owned prospect may
    replace the weakest incumbent during an open market window. Rich clubs
    periodically invest using the same costs as humans.
    """
    from esports_sim.manager import market

    if not bool(market.market_window_status(gs)["open"]):
        return
    for parent_tid in sorted(gs.academy_affiliates):
        if gs.is_human(parent_tid):
            continue
        affiliate_tid = affiliate_for(gs, parent_tid)
        if affiliate_tid is None:
            continue
        team = gs.teams[parent_tid]
        level = _level(gs, parent_tid)
        target_level = level + 1
        cost = UPGRADE_COST.get(target_level)
        if (
            cost is not None
            and team.balance >= cost * 3
            and _stable_int(gs.seed, gs.season, parent_tid, "academy-upgrade") % 3 == 0
        ):
            upgrade(gs, parent_tid)

        prospects = [
            gs.players[pid]
            for pid in gs.teams[affiliate_tid].player_ids
            if gs.academy_player_rights.get(pid) == parent_tid
        ]
        if not prospects:
            continue
        prospect = max(
            prospects,
            key=lambda p: (development.overall(p), development.potential_of(p), p.id),
        )
        if len(team.player_ids) < market.ROSTER_MIN:
            move_player(gs, parent_tid, prospect.id, "promote")
            continue
        weakest = min(
            (gs.players[pid] for pid in team.player_ids),
            key=lambda p: (market.retention_value(gs, parent_tid, p.id), p.id),
        )
        if development.overall(prospect) < development.overall(weakest) + 5.0:
            continue
        ok, _ = market.release_player(gs, parent_tid, weakest.id)
        if ok:
            move_player(gs, parent_tid, prospect.id, "promote")


def _played_lines(gs: "GameState", affiliate_tid: str) -> tuple[dict[str, list[float]], int, int]:
    by_player: dict[str, list[float]] = {}
    series = wins = 0
    for fixture in sorted(gs.fixtures, key=lambda item: item.id):
        if (
            fixture.week != gs.week
            or fixture.tier != 2
            or not fixture.played
            or affiliate_tid not in (fixture.team_a, fixture.team_b)
        ):
            continue
        series += 1
        wins += int(fixture.winner_id == affiliate_tid)
        for result in fixture.results:
            for line in sorted(result.lines, key=lambda item: item.player_id):
                if line.player_id in gs.teams[affiliate_tid].player_ids:
                    by_player.setdefault(line.player_id, []).append(line.rating)
    return by_player, wins, series


def weekly_tick(gs: "GameState") -> list[dict[str, Any]]:
    """Apply a bounded coaching bonus from actual affiliate match minutes."""
    parents_by_affiliate: dict[str, list[str]] = {}
    for parent_tid in sorted(_state_map(gs, "academy_affiliates")):
        affiliate_tid = affiliate_for(gs, parent_tid)
        if affiliate_tid is not None:
            parents_by_affiliate.setdefault(affiliate_tid, []).append(parent_tid)

    reports_out: list[dict[str, Any]] = []
    for affiliate_tid in sorted(parents_by_affiliate):
        parents = sorted(parents_by_affiliate[affiliate_tid])
        if any(_has_report(gs, tid, "weekly", affiliate_id=affiliate_tid) for tid in parents):
            continue
        lines_by_player, wins, series = _played_lines(gs, affiliate_tid)
        gains_by_parent: dict[str, dict[str, float]] = {tid: {} for tid in parents}
        used_by_parent: dict[str, int] = {tid: 0 for tid in parents}
        win_rate = wins / max(series, 1)
        for player_id in sorted(lines_by_player):
            owner = gs.academy_player_rights.get(player_id)
            if owner not in gains_by_parent:
                continue
            used_by_parent[owner] += 1
            level = _level(gs, owner)
            if level <= 0:
                continue
            player = gs.players[player_id]
            ratings = lines_by_player[player_id]
            mean_rating = sum(ratings) / len(ratings)
            gain = min(
                WEEKLY_GAIN_CAP,
                0.01
                * level
                * min(len(ratings), 3)
                * (0.85 + 0.10 * mean_rating + 0.10 * win_rate),
            )
            applied = 0.0
            # F1: spread the affiliate-minutes bump across the 3 weakest attrs
            # (was 2) so a developing prospect closes more of their gap.
            weakest = sorted(
                player.attributes, key=lambda attr: (player.attributes[attr], attr)
            )[:3]
            for attr_id in weakest:
                current = player.attr(attr_id)
                ceiling = development.development_ceiling(player, attr_id)
                updated = round(min(current + gain, max(current, ceiling)), 2)
                player.attributes[attr_id] = updated
                applied += updated - current
            if applied > 0:
                gains_by_parent[owner][player_id] = round(applied, 2)

        for parent_tid in parents:
            report = {
                "kind": "weekly",
                "season": gs.season,
                "week": gs.week,
                "parent_id": parent_tid,
                "affiliate_id": affiliate_tid,
                "level": _level(gs, parent_tid),
                "series": series,
                "wins": wins,
                "players_used": used_by_parent[parent_tid],
                "gains": dict(gains_by_parent[parent_tid]),
            }
            _append_report(gs, parent_tid, report)
            reports_out.append(report)
    return reports_out
