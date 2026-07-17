"""Parallel scouting lanes and team-vs-player intel (F4/F5).

This module replaces the old single-slot ``campaign._tick_scouting`` with two
*standing directives* per human manager that advance every week without a
re-pick:

* the **pro** lane — either ``scout_opponents`` (auto-rotates onto the next
  unplayed fixture opponent, feeding the prep edge) or
  ``fill_gap:<role>:<caliber>`` (a continuous free-agent market sweep that
  rebuilds a recommended shortlist);
* the **amateur** lane — ``track_academy`` (deep-dives the affiliate roster /
  scans the youth market).

Team-playbook reads are FAST (a week of VOD yields last-week identity) and
decay on a meta patch (:func:`decay_on_patch`); player evaluation is SLOW with
uncertainty bands that narrow per tier, and the deepest tier is a
scout-precision-gated role-fit projection (:func:`role_fit_projection`).

Everything here is rng-free: progress is derived from stable counts and every
iteration is ``sorted``.  The shared ``gs.scout_progress`` book is still the
sink (opponent team keys, ``player:<pid>``, ``market``), so
``preparation.PrepEvidence.scouting_confidence`` keeps reading the same keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from esports_sim.manager import (
    academy,
    development,
    economy,
    knowledge,
    market,
    role_fit,
    staff,
    staff_effects,
)

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.campaign import WeekReport
    from esports_sim.manager.state import GameState


# -- lane vocabulary ---------------------------------------------------------
PRO_DIRECTIVES = ("scout_opponents", "fill_gap")
AMATEUR_DIRECTIVES = ("track_academy",)
# Perceived-quality floor a shortlist candidate must clear per caliber tag.
CALIBER_FLOOR: dict[str, float] = {
    "star": 78.0,
    "tier1": 68.0,
    "starter": 58.0,
    "tier2": 50.0,
    "any": 0.0,
}
SHORTLIST_SIZE = 6
# A week of tape yields last-week identity — the fast read starts near full and
# only erodes on meta patches (decay_on_patch), never on time alone.
PLAYBOOK_FRESH = 0.85
# Broad youth/amateur-market survey sink when a manager has no tier-2 affiliate.
AMATEUR_SURVEY_KEY = "youth"

_DIRECTIVE_MENU = {
    "pro": list(PRO_DIRECTIVES),
    "amateur": list(AMATEUR_DIRECTIVES),
    "calibers": sorted(CALIBER_FLOOR),
}


# ---------------------------------------------------------------------------
# Weekly orchestration


def tick(gs: "GameState", report: "WeekReport") -> None:
    """Advance every human manager's two scouting lanes for the week.

    Replaces ``campaign._tick_scouting``.  Each manager advances its pro and
    amateur lanes independently into the shared scout-progress book, rebuilds
    the ``fill_gap`` shortlist, and refreshes the fast team-playbook overlay.
    A manager with NO standing directive falls back to the legacy single slot
    (``gs.scout_targets``) so the decision-env/RL path stays intact.
    """
    for tid in sorted(gs.human_team_ids):
        gs.set_acting(tid)
        _tick_one(gs, tid, report)
    gs.set_acting(None)


def _tick_one(gs: "GameState", tid: str, report: "WeekReport") -> None:
    lanes = gs.scout_lanes_by.get(tid) or {}
    pro = lanes.get("pro")
    amateur = lanes.get("amateur")
    if not pro and not amateur:
        # No standing directive: honour the legacy single slot as a fallback.
        _advance_legacy(gs, report)
        return
    if pro:
        _advance_pro_lane(gs, tid, pro, report)
    if amateur:
        _advance_amateur_lane(gs, tid, amateur, report)


def _advance_pro_lane(
    gs: "GameState", tid: str, directive: str, report: "WeekReport"
) -> None:
    if directive == "scout_opponents":
        _advance_opponents(gs, tid, report)
    elif directive.startswith("fill_gap"):
        _advance_fill_gap(gs, tid, directive, report)
    else:
        # Migrated legacy value (a bare rival id or "match:<fid>").
        _advance_generic(gs, tid, "pro", directive, report, "team")


def _advance_amateur_lane(
    gs: "GameState", tid: str, directive: str, report: "WeekReport"
) -> None:
    if directive == "track_academy":
        _advance_academy(gs, tid, report)
    else:
        # Migrated legacy value ("player:<pid>" or "market").
        kind = "market" if directive == "market" else "player"
        _advance_generic(gs, tid, "amateur", directive, report, kind)


# ---------------------------------------------------------------------------
# Pro lane: opponents / fill-gap


def _advance_opponents(gs: "GameState", tid: str, report: "WeekReport") -> None:
    """Steadily cover the next unplayed opponent and refresh the fast read."""
    opp = _next_opponent(gs, tid)
    if opp is None:
        return
    mult = _scout_speed(gs, "team")
    _advance_target(gs, report, opp, mult)
    _refresh_playbook(gs, tid, opp)


def _advance_fill_gap(
    gs: "GameState", tid: str, directive: str, report: "WeekReport"
) -> None:
    """Sweep the free-agent market and rebuild the recommendation shortlist."""
    mult = _scout_speed(gs, "market")
    _advance_target(gs, report, "market", mult)
    parts = directive.split(":")
    role = parts[1] if len(parts) > 1 else ""
    caliber = parts[2] if len(parts) > 2 else "any"
    before = gs.scout_shortlist_by.get(tid, [])
    shortlist = _build_shortlist(gs, tid, role, caliber)
    gs.scout_shortlist_by[tid] = shortlist
    if shortlist and not before:
        gs.push_private_news(
            f"Market sweep: your scouts have a shortlist of {len(shortlist)} "
            f"{role or 'target'} option(s) to fill the gap."
        )


def _build_shortlist(
    gs: "GameState", tid: str, role: str, caliber: str
) -> list[str]:
    """Recommended market targets: role/caliber-matched, best perceived first.

    Reuses ``delegation.matching_players`` (the department's policy pool) as a
    priority seed when auto-scouting is on, then widens to a full role scan so
    the sweep still surfaces options with delegation off."""
    from esports_sim.manager import delegation  # lazy: avoids any import cycle

    floor = CALIBER_FLOOR.get(caliber, 0.0)
    own = set(gs.teams[tid].player_ids)
    pool: list[str] = list(delegation.matching_players(gs, tid))
    seed = set(pool)
    for pid in sorted(gs.players):
        if pid not in seed:
            pool.append(pid)
    rows: list[tuple[str, float]] = []
    for pid in pool:
        if pid in own:
            continue
        p = gs.players.get(pid)
        if p is None:
            continue
        if role and str(p.role) != role:
            continue
        q = market.perceived_quality(gs, tid, p)
        if q < floor:
            continue
        rows.append((pid, q))
    rows.sort(key=lambda row: (-row[1], row[0]))
    return [pid for pid, _ in rows[:SHORTLIST_SIZE]]


# ---------------------------------------------------------------------------
# Amateur lane: academy / youth


def _academy_candidates(gs: "GameState", tid: str) -> list[str]:
    affiliate = academy.affiliate_for(gs, tid)
    if not affiliate:
        return []
    team = gs.teams.get(affiliate)
    if team is None:
        return []
    return sorted(pid for pid in team.player_ids if pid in gs.players)


def _advance_academy(gs: "GameState", tid: str, report: "WeekReport") -> None:
    """Deep-dive the least-booked affiliate player, or scan the youth market."""
    mult = _scout_speed(gs, "player")
    cands = _academy_candidates(gs, tid)
    prog = gs.scout_progress
    if cands:
        target = min(cands, key=lambda pid: (prog.get(f"player:{pid}", 0.0), pid))
        _advance_target(gs, report, f"player:{target}", mult)
        return
    # No tier-2 affiliate: broad, slow scan of the youth/amateur market.
    from esports_sim.manager import campaign as _c

    cur = prog.get(AMATEUR_SURVEY_KEY, 0.0)
    after = min(_c.SCOUT_SURVEY_CAP, round(cur + _c.SCOUT_WEEKLY_GAIN * mult * 0.6, 2))
    prog[AMATEUR_SURVEY_KEY] = after
    staff.add_contribution(
        gs, gs.acting_team_id, "analyst", "scouting_progress", after - cur
    )


# ---------------------------------------------------------------------------
# Legacy single-slot fallback (byte-identical to the old _tick_scouting_one)


def _advance_legacy(gs: "GameState", report: "WeekReport") -> None:
    target = gs.scout_target
    if not target:
        return
    mult = staff.scout_multiplier(gs) * economy.facility_scout_mult(gs)
    if _advance_target(gs, report, target, mult):
        gs.scout_target = None


def _advance_generic(
    gs: "GameState",
    tid: str,
    lane: str,
    target: str,
    report: "WeekReport",
    kind: str,
) -> None:
    """Advance a migrated legacy-style directive stored in a lane, clearing the
    lane when a one-shot assignment (a match attend) completes."""
    mult = _scout_speed(gs, kind)
    if _advance_target(gs, report, target, mult):
        lanes = gs.scout_lanes_by.setdefault(tid, {})
        lanes[lane] = None


def _advance_target(
    gs: "GameState", report: "WeekReport", target: str, mult: float
) -> bool:
    """Advance one assignment into the acting manager's scout-progress book.

    Returns ``True`` when the assignment is a completed/invalid one-shot (a
    match attend, or a vanished fixture) that the caller should clear.  Ported
    verbatim from the old ``campaign._tick_scouting_one`` so the legacy slot
    stays byte-identical."""
    from esports_sim.manager import campaign as _c

    prog = gs.scout_progress

    if target.startswith("match:"):
        fid = target[len("match:"):]
        fx = next((f for f in report.fixtures if f.id == fid and f.played), None)
        if fx is None:
            if not any(f.id == fid for f in gs.fixtures):
                gs.push_private_news(
                    "Scouted fixture is off the calendar — the scout needs "
                    "a new assignment."
                )
                return True
            return False
        gained = min(_c.SCOUT_MATCH_CAP, round(_c.SCOUT_MATCH_INTEL * mult, 2))
        prog[target] = gained
        staff.add_contribution(
            gs, gs.acting_team_id, "analyst", "scouting_progress", gained
        )
        for observed_tid in (fx.team_a, fx.team_b):
            team = gs.teams.get(observed_tid)
            if team is None:
                continue
            for dial in ("aggression", "pace", "eco_greed", "map_control"):
                prog[f"matchobs:{fid}:{observed_tid}:{dial}"] = float(
                    getattr(team.tactics, dial)
                )
            prog[
                f"matchobs:{fid}:{observed_tid}:site:{team.tactics.site_focus}"
            ] = 1.0
        names = []
        for other in (fx.team_a, fx.team_b):
            if other == gs.acting_team_id or other not in gs.teams:
                continue
            cur = prog.get(other, 0.0)
            prog[other] = min(_c.SCOUT_MATCH_CAP, round(cur + gained, 2))
            names.append(gs.teams[other].name)
        if names:
            gs.push_private_news(
                f"Match intel: your scout's report from "
                f"{gs.teams[fx.team_a].name} vs {gs.teams[fx.team_b].name} "
                f"is in — coverage of {' and '.join(names)} jumps."
            )
        return True

    if target.startswith("player:"):
        pid = target[len("player:"):]
        p = gs.players.get(pid)
        if p is None:
            return True
        cur = prog.get(target, 0.0)
        gain = min(
            _c.SCOUT_PLAYER_WEEK_CAP,
            _c.SCOUT_WEEKLY_GAIN * _c.SCOUT_PLAYER_MULT * mult,
        )
        played = any(
            pid in st.lines
            for fid in report.match_stats
            for st in report.match_stats[fid]
        )
        if played:
            gain += _c.SCOUT_LIVE_WATCH_BONUS
        after = min(_c.SCOUT_DEEP_CAP, round(cur + gain, 2))
        prog[target] = after
        staff.add_contribution(
            gs, gs.acting_team_id, "analyst", "scouting_progress", after - cur
        )
        if after >= 1.0 and cur < 1.0:
            gs.push_private_news(
                f"The full book on {p.handle} is compiled — style, "
                "mentality, ceiling, the lot."
            )
        return False

    if target != "market" and target not in gs.teams:
        return False
    cur = prog.get(target, 0.0)
    gain = _c.SCOUT_WEEKLY_GAIN * mult
    if target == "market":
        gain *= 0.6
    after = min(_c.SCOUT_SURVEY_CAP, round(cur + gain, 2))
    prog[target] = after
    staff.add_contribution(
        gs, gs.acting_team_id, "analyst", "scouting_progress", after - cur
    )
    if after >= _c.SCOUT_SURVEY_CAP and cur < _c.SCOUT_SURVEY_CAP:
        label = (
            "the free-agent market"
            if target == "market"
            else gs.teams[target].name
        )
        gs.push_private_news(f"Broad scouting survey of {label} complete.")
    return False


# ---------------------------------------------------------------------------
# Team-playbook overlay (F5 fast read)


def _refresh_playbook(gs: "GameState", tid: str, opp_tid: str) -> None:
    """Stamp the fast last-week identity read for one opponent."""
    book = gs.scout_playbook_by.setdefault(tid, {})
    prior = float(book.get(opp_tid, {}).get("value", 0.0))
    book[opp_tid] = {
        "value": round(max(prior, PLAYBOOK_FRESH), 2),
        "as_of_week": gs.season * 100 + gs.week,
        "as_of_patch": len(gs.patch_history),
    }


def team_playbook_read(gs: "GameState", team_id: str, opp_tid: str) -> float:
    """Current fast team-identity confidence for an opponent (0.0 if none).

    Distinct from the one-shot match-attend intel: this overlay is refreshed by
    a standing ``scout_opponents`` directive and decays on meta patches."""
    entry = gs.scout_playbook_by.get(team_id, {}).get(opp_tid)
    if not entry:
        return 0.0
    return float(entry.get("value", 0.0))


def decay_on_patch(gs: "GameState") -> None:
    """A balance patch dates every stored team-playbook read (mirrors
    ``knowledge.on_patch`` KEEP factor, sorted, rng-free)."""
    keep = knowledge.PATCH_PLAYBOOK_KEEP
    patch_idx = len(gs.patch_history)
    for tid in sorted(gs.scout_playbook_by):
        book = gs.scout_playbook_by[tid]
        for opp in sorted(book):
            entry = book[opp]
            entry["value"] = round(float(entry.get("value", 0.0)) * keep, 2)
            entry["as_of_patch"] = patch_idx


# ---------------------------------------------------------------------------
# Serializers (server-side; JS renders, never computes — invariant 4)


def scout_desk_view(gs: "GameState", team_id: str) -> dict:
    """Two-lane scout desk: pro (directive + auto-rotating opponent +
    shortlist) and amateur (directive + academy/youth), plus recommended deep
    dives and player-eval uncertainty ranges.  Keeps ``target``/``target_kind``
    defaulted for back-compat with the old single-slot view."""
    lanes = gs.scout_lanes_by.get(team_id) or {}
    prog = gs.scout_progress_by.get(team_id, {})

    pro: dict = {
        "directive": lanes.get("pro"),
        "opponent": None,
        "shortlist": [],
    }
    opp = _next_opponent(gs, team_id)
    if opp is not None and opp in gs.teams:
        pro["opponent"] = {
            "team_id": opp,
            "name": gs.teams[opp].name,
            "progress": round(prog.get(opp, 0.0), 2),
            "playbook": round(team_playbook_read(gs, team_id, opp), 2),
        }
    shortlist = list(gs.scout_shortlist_by.get(team_id, []))
    for pid in shortlist:
        p = gs.players.get(pid)
        if p is None:
            continue
        pro["shortlist"].append(
            {
                "player_id": pid,
                "handle": p.handle,
                "role": str(p.role),
                "quality": round(market.perceived_quality(gs, team_id, p), 1),
            }
        )

    amateur: dict = {
        "directive": lanes.get("amateur"),
        "academy": [],
        "youth_progress": round(prog.get(AMATEUR_SURVEY_KEY, 0.0), 2),
    }
    for pid in _academy_candidates(gs, team_id):
        p = gs.players.get(pid)
        if p is None:
            continue
        amateur["academy"].append(
            {
                "player_id": pid,
                "handle": p.handle,
                "role": str(p.role),
                "progress": round(prog.get(f"player:{pid}", 0.0), 2),
            }
        )

    player_evals = []
    for pid in shortlist[:SHORTLIST_SIZE]:
        p = gs.players.get(pid)
        if p is None:
            continue
        depth = market.scouting_progress_for(gs, team_id, p)
        rep = development.scout_report(gs, p, depth)
        player_evals.append(
            {
                "player_id": pid,
                "handle": p.handle,
                "role": str(p.role),
                "ca_stars": rep["ca_stars"],
                "pa_projection": rep["pa_projection"],
                "progress": rep["progress"],
            }
        )

    legacy = gs.scout_targets.get(team_id) or ""
    return {
        "team_id": team_id,
        "pro": pro,
        "amateur": amateur,
        "recommended": _recommended_dives(gs, team_id, shortlist),
        "player_evals": player_evals,
        "directives": _DIRECTIVE_MENU,
        "target": legacy,
        "target_kind": _legacy_kind(legacy),
    }


def _recommended_dives(
    gs: "GameState", team_id: str, shortlist: list[str]
) -> list[dict]:
    """The department's suggested deep-dive assignments: the best perceived,
    not-yet-fully-booked players across the shortlist and the academy."""
    prog = gs.scout_progress_by.get(team_id, {})
    pool = [
        pid
        for pid in list(shortlist) + _academy_candidates(gs, team_id)
        if pid in gs.players
    ]
    ranked = sorted(
        set(pool),
        key=lambda pid: (-market.perceived_quality(gs, team_id, gs.players[pid]), pid),
    )
    recs: list[dict] = []
    for pid in ranked:
        depth = prog.get(f"player:{pid}", 0.0)
        if depth >= 1.0:
            continue
        p = gs.players[pid]
        recs.append(
            {
                "player_id": pid,
                "handle": p.handle,
                "role": str(p.role),
                "depth": round(depth, 2),
                "assignment": f"player:{pid}",
            }
        )
        if len(recs) >= 4:
            break
    return recs


def role_fit_projection(
    gs: "GameState", viewer_tid: str, pid: str, slot: str
) -> dict:
    """F5 deepest tier: a scout-precision-gated 'how good at OUR <slot>' read.

    ``slot`` is a role (duelist/controller/...) or a style (igl/awper/...).
    The projected fit sits inside an uncertainty band that narrows with the
    viewer's information depth and analyst quality."""
    p = gs.players.get(pid)
    if p is None:
        return {
            "player_id": pid,
            "slot": slot,
            "fit": 0.0,
            "band": [0.0, 0.0],
            "progress": 0.0,
            "precision": 1.0,
        }
    progress = market.scouting_progress_for(gs, viewer_tid, p)
    sm = _analyst_precision(gs, viewer_tid)
    center = _slot_ability(p, slot)
    known = {str(p.role), str(p.playstyle)}
    comfort = (
        role_fit.assignment_comfort(p)
        if slot in known
        else role_fit.NEW_ASSIGNMENT_COMFORT
    )
    factor = 0.80 + 0.20 * comfort / 100.0
    raw = development.overall(p)
    fit = raw + (center - raw) * factor
    half = (18.0 * (1.0 - progress) + 4.0 / sm) / 2.0
    lo = max(1.0, round(fit - half, 1))
    hi = min(99.0, round(fit + half, 1))
    return {
        "player_id": pid,
        "slot": slot,
        "fit": round(fit, 1),
        "band": [lo, hi],
        "progress": round(progress, 2),
        "precision": round(sm, 2),
    }


# ---------------------------------------------------------------------------
# Small deterministic helpers


def _next_opponent(gs: "GameState", tid: str) -> str | None:
    """The other team in this manager's next unplayed fixture (sorted)."""
    upcoming = sorted(
        (f for f in gs.fixtures if not f.played and tid in (f.team_a, f.team_b)),
        key=lambda f: (f.week, f.id),
    )
    for f in upcoming:
        opp = f.team_b if f.team_a == tid else f.team_a
        if opp in gs.teams:
            return opp
    return None


def _scout_speed(gs: "GameState", kind: str) -> float:
    """Analyst + facility scouting speed for a lane, with the analyst trait
    bonus keyed on lane ``kind`` (mirrors ``staff.scout_multiplier`` without
    depending on the legacy single-slot ``gs.scout_target``)."""
    analyst = gs.staff.get("analyst")
    base = 1.0
    if analyst is not None:
        score = staff_effects.role_effect_score(analyst)
        traits = set(analyst.traits)
        if kind == "market" and "talent_spotter" in traits:
            score *= 1.08
        elif kind in ("team", "player") and "opponent_specialist" in traits:
            score *= 1.08
        base = 1.0 + score / 100.0
    return base * economy.facility_scout_mult(gs)


def _analyst_precision(gs: "GameState", tid: str) -> float:
    """Acting-independent analyst quality multiplier (1.0 .. ~1.9)."""
    analyst = gs.staff_by.get(tid, {}).get("analyst")
    if analyst is None:
        return 1.0
    return 1.0 + staff_effects.role_effect_score(analyst) / 100.0


def _slot_ability(p, slot: str) -> float:
    """Weighted ability for an arbitrary role/style slot (role_fit weights)."""
    weights: dict[str, float] = {}
    source = role_fit.ROLE_WEIGHTS.get(slot) or role_fit.STYLE_WEIGHTS.get(slot)
    if source:
        for attr, weight in source.items():
            weights[attr] = weights.get(attr, 0.0) + weight
    if not weights:
        return development.overall(p)
    return sum(p.attr(attr) * weight for attr, weight in weights.items()) / sum(
        weights.values()
    )


def _legacy_kind(target: str) -> str:
    if not target:
        return ""
    if target.startswith("player:"):
        return "player"
    if target.startswith("match:"):
        return "match"
    if target == "market":
        return "market"
    return "team"
