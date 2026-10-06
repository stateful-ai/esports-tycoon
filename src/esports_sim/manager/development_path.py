"""Development evidence, practice feedback, and bounded career turning points.

Match contributions are judged per round and relative to opposition, with
assists, objectives, trades and survival credited alongside kills. One map
cannot establish a career trend. All clubs use the same rules; only owning
managers receive news. RNG belongs to a player/week-specific subtree.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import development
from esports_sim.schemas import Player
from esports_sim.schemas.player import DevelopmentWeek

TREND_WEIGHT = 0.25
TREND_GROWTH_SPAN = 0.30
FOCUS_TRANSFER_MULT = 1.25
EVENT_MIN_WEEKS = 4
EVENT_COOLDOWN = 6


def begin_week(gs) -> None:
    for pid in sorted(gs.players):
        p = gs.players[pid]
        p.development_progress.latest = DevelopmentWeek(season=gs.season, week=gs.week)


def record_gains(p: Player, source: str, before: dict[str, float]) -> None:
    week = p.development_progress.latest
    if week is None:
        return
    gains = getattr(week, source)
    for aid in sorted(p.attributes):
        delta = round(p.attr(aid) - before.get(aid, p.attr(aid)), 2)
        if delta:
            gains[aid] = round(gains.get(aid, 0.0) + delta, 2)


def performance_score(p: Player, line, n_rounds: int, opponent_quality: float) -> float:
    """Role-inclusive impact versus an ability-adjusted per-round expectation."""
    if n_rounds <= 0 or not (line.kills or line.deaths or line.assists or line.survived
                             or line.plants or line.defuses):
        return 0.0
    clutches = line.clutch_1v1 + line.clutch_1v2 + line.clutch_1v3
    impact = (line.kills + 0.8 * line.assists + 0.6 * line.trade_kills
              + 0.5 * line.first_kills + 0.7 * (line.plants + line.defuses)
              + 1.5 * clutches + 0.15 * line.survived)
    ability_edge = float(np.clip((development.overall(p) - opponent_quality) * 0.006, -0.15, 0.15))
    expected = 0.90 + ability_edge
    return float(np.clip((impact / n_rounds - expected) / 0.55, -1.0, 1.0))


def observe_match(p: Player, score: float, n_rounds: int) -> None:
    week = p.development_progress.latest
    if week is not None and n_rounds > 0:
        week.maps += 1
        week.rounds += n_rounds
        week.performance_total += score * n_rounds


def update_trends(gs) -> None:
    """One bounded update per week, independent of the fixture/map count."""
    for pid in sorted(gs.players):
        progress = gs.players[pid].development_progress
        week = progress.latest
        if week is None:
            continue
        if week.rounds:
            score = week.performance_total / week.rounds
            progress.momentum = round((1 - TREND_WEIGHT) * progress.momentum + TREND_WEIGHT * score, 4)
            progress.performance_weeks += 1
        else:
            progress.momentum = round(progress.momentum * 0.9, 4)
        progress.event_cooldown = max(0, progress.event_cooldown - 1)


def practice_feedback(p: Player, focus: str, attrs: list[str]) -> tuple[float, list[str]]:
    """The same factors drive training and explain it in the report."""
    week = p.development_progress.latest
    factors = []
    momentum = p.development_progress.momentum
    mult = 1.0 + TREND_GROWTH_SPAN * momentum
    if momentum >= 0.2:
        factors.append("Strong match performances are accelerating learning")
    elif momentum <= -0.2:
        factors.append("Poor match performances are slowing learning; useful practice still counts")
    if week and any(week.match_gains.get(a, 0.0) > 0 for a in attrs):
        mult *= FOCUS_TRANSFER_MULT
        factors.append(f"{focus.capitalize()} practice reinforces skills used in matches")
    # A gradual fatigue penalty makes intensity a contextual decision, instead
    # of a free 40% boost until the old cliff at 35 condition.
    fatigue = float(np.interp(p.stamina, [0, 35, 65, 100], [0.25, 0.4, 0.85, 1.0]))
    mult *= fatigue
    if p.stamina < 65:
        factors.append("Tired legs are reducing practice quality; ease intensity or rest")
    if p.stream_load >= 40:
        factors.append("Streaming is taking time away from practice")
    return mult, factors


def career_turning_points(gs, tree) -> list[dict]:
    """Rare, earned revisions to headroom; never delete existing skill."""
    events = []
    for tid in sorted(gs.teams):
        for p in sorted(gs.roster(tid), key=lambda p: p.id):
            progress = p.development_progress
            week = progress.latest
            if (week is None or not week.maps or progress.event_cooldown
                    or progress.performance_weeks < EVENT_MIN_WEEKS
                    or p.age >= development.decline_age(p)):
                continue
            # Practice can open a new path even when every drilled skill is at
            # its current ceiling. Requiring a gain would trap those players.
            trained = bool(week.practice_skills)
            rng = tree.derive("season", gs.season, "week", gs.week, "career_path", p.id)
            roll = float(rng.random())
            old_shift = progress.ceiling_shift
            if (trained and p.stamina >= 50 and progress.momentum >= 0.3
                    and old_shift < 6 and roll < 0.06):
                progress.ceiling_shift = round(min(6.0, old_shift + float(rng.uniform(1.2, 2.4))), 2)
                before = dict(p.attributes)
                # Reward the ACTUAL plan, rather than an unrelated random skill.
                for aid in sorted(week.practice_skills):
                    cap = development.development_ceiling(p, aid)
                    gain = float(rng.uniform(0.4, 0.8)) * min(1.0, 22.0 / max(p.age, 1))
                    cur = p.attr(aid)
                    p.attributes[aid] = round(min(max(cur, cap), cur + gain), 2)
                record_gains(p, "event_gains", before)
                message = (f"{p.handle} has a career breakthrough: {week.focus} practice and "
                           "sustained match performances are opening new room to grow.")
                kind = "career_breakthrough"
            elif (trained and progress.momentum <= -0.3 and old_shift > -6
                  and roll < 0.035):
                progress.ceiling_shift = round(max(-6.0, old_shift - float(rng.uniform(1.2, 2.4))), 2)
                message = (f"{p.handle}'s development has stalled after sustained underperformance. "
                           "Current skills are intact; review the plan, support and playing time.")
                kind = "career_stall"
            else:
                continue
            week.career_event = message
            progress.event_cooldown = EVENT_COOLDOWN
            events.append({"team_id": tid, "player_id": p.id, "kind": kind, "headline": message})
            if gs.is_human(tid):
                gs.push_private_news(message, owner=tid)
    return events


def report_view(p: Player) -> dict | None:
    """Observed progress only: no hidden disposition or exact career ceiling."""
    week = p.development_progress.latest
    if week is None:
        return None
    n_attrs = max(len(p.attributes), 1)
    sources = {
        key: {"overall_gain": round(sum(getattr(week, key).values()) / n_attrs, 2),
              "skills": dict(sorted(getattr(week, key).items()))}
        for key in ("practice_gains", "match_gains", "scrim_gains", "event_gains")
    }
    momentum = p.development_progress.momentum
    return {"season": week.season, "week": week.week, "focus": week.focus,
            "intensity": week.intensity, "maps": week.maps,
            "trend": "thriving" if momentum >= 0.2 else "struggling" if momentum <= -0.2 else "settling",
            "sources": sources, "factors": list(week.factors), "career_event": week.career_event}
