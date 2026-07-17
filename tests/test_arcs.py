"""Relationship arcs (manager/arcs.py): the scarce team list, the new org
grudge / spotlight-friction signals, the bounded effects, and the rare
inbox moment.

All tests construct their conditions directly on a fresh campaign state
(the module is a pure deterministic reader, so mutate-then-read is the
whole contract), except the hands-off test which advances real weeks."""

from __future__ import annotations

import pytest

from esports_sim.manager import arcs, development, inbox, market, promises, relationships
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState, StatSnap
from esports_sim.registry import GameData
from esports_sim.schemas.common import Playstyle


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=321)


def _snap(season: int, week: int, rating: float) -> StatSnap:
    return StatSnap(
        season=season, week=week, maps=2, rating=rating, acs=200.0,
        kd=1.0, kast_pct=70.0, kills=30, deaths=30,
    )


def _rel(gs: GameState, a: str, b: str, value: float) -> None:
    gs.relationships[relationships.key(a, b)] = value


# ---------------------------------------------------------------------------
# Pair arcs, priority, cap


def test_team_arcs_priority_order_and_cap(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    r = sorted(gs.teams[tid].player_ids)
    _rel(gs, r[0], r[1], 10.0)   # pair grudge
    _rel(gs, r[0], r[2], 5.0)    # second pair grudge
    _rel(gs, r[2], r[3], 20.0)   # friction
    gs.mentorships[r[4]] = r[3]
    _rel(gs, r[3], r[4], 85.0)   # registered mentor bond
    rows = arcs.team_arcs(gs, tid)
    assert len(rows) == arcs.MAX_ARCS  # 4 candidates, capped at 3
    assert [row["kind"] for row in rows] == ["grudge", "grudge", "friction"]
    # Deterministic: a second read returns the same rows.
    assert arcs.team_arcs(gs, tid) == rows
    # Every row is grounded: real handles, one ASCII sentence.
    for row in rows:
        assert row["text"].isascii()
        assert all(h in row["text"] for h in row["handles"])


def test_mentor_bond_requires_registered_mentorship_and_bar(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    r = sorted(gs.teams[tid].player_ids)
    # High relationship alone is not a team-list mentor bond...
    _rel(gs, r[0], r[1], 90.0)
    assert arcs.team_arcs(gs, tid) == []
    # ...the registered contract plus the bar is.
    gs.mentorships[r[1]] = r[0]
    rows = arcs.team_arcs(gs, tid)
    assert [row["kind"] for row in rows] == ["mentor_bond"]
    assert rows[0]["source"] == "mentorship"
    assert set(rows[0]["pids"]) == {r[0], r[1]}
    # Below the bar the contract is still just a contract.
    _rel(gs, r[0], r[1], relationships.MENTOR_BOND_BAR - 1.0)
    assert arcs.team_arcs(gs, tid) == []


def test_spotlight_friction_needs_shared_role_decline_and_no_warmth(
    campaign: GameState,
) -> None:
    gs = campaign
    tid = gs.user_team_id
    ra, rb = sorted(gs.teams[tid].player_ids)[:2]
    for pid in (ra, rb):
        gs.players[pid].playstyle = Playstyle.ENTRY
        gs.stat_history[pid] = [
            _snap(gs.season, 1, 1.10), _snap(gs.season, 2, 0.85),
        ]
    _rel(gs, ra, rb, 40.0)
    rows = arcs.team_arcs(gs, tid)
    assert [row["kind"] for row in rows] == ["friction"]
    assert rows[0]["source"] == "form"
    assert "entry" in rows[0]["text"]
    # Friendly pairs handle sharing the spotlight.
    _rel(gs, ra, rb, 60.0)
    assert arcs.team_arcs(gs, tid) == []
    # One of them climbing kills the arc too.
    _rel(gs, ra, rb, 40.0)
    gs.stat_history[rb] = [_snap(gs.season, 1, 0.9), _snap(gs.season, 2, 1.2)]
    assert arcs.team_arcs(gs, tid) == []


# ---------------------------------------------------------------------------
# Org grudges: broken promises and long benchings


def test_broken_promise_becomes_org_grudge_with_inbox_moment(
    campaign: GameState,
) -> None:
    gs = campaign
    tid = gs.user_team_id
    pid = gs.teams[tid].player_ids[0]
    pr = promises.create_promise(gs, tid, pid, "make_captain", duration=4)
    promises.resolve_promise(gs, pr, success=False)
    assert pr.status == "broken" and pr.weeks_left == 4

    rows = arcs.org_grudges(gs, tid)
    assert [row["source"] for row in rows] == ["promise"]
    assert "captaincy" in rows[0]["text"]

    # Freshly broken -> exactly one formation moment this tick...
    moments = arcs.weekly_moments(gs, tid, gs.season, gs.week)
    assert [m["phase"] for m in moments] == ["formed"]
    # ...which the inbox surfaces as one bounded talk item.
    gs.set_acting(tid)
    items = inbox._arc_items(gs, gs.season, gs.week)
    gs.set_acting(None)
    assert len(items) == 1
    _prio, item = items[0]
    assert item.category == "talk"
    assert "grudge" in item.title.lower()
    # A week later the moment is gone but the grudge still stands.
    pr.weeks_left = 3
    assert arcs.weekly_moments(gs, tid, gs.season, gs.week) == []
    assert arcs.org_grudges(gs, tid)


def _bench_setup(gs: GameState, played_weeks: int) -> tuple[str, str]:
    """Give the user team a 6th, clearly-starter-quality player who never
    dressed, and mark the team's first `played_weeks` fixtures played.
    Returns (team_id, benched_pid)."""
    tid = gs.user_team_id
    team = gs.teams[tid]
    star = max(gs.roster(tid), key=lambda p: market.player_quality(p))
    bench_pid = sorted(gs.free_agent_ids)[0]
    bench = gs.players[bench_pid]
    bench.attributes = {k: min(99.0, v + 5.0) for k, v in star.attributes.items()}
    bench.form = 50.0
    bench.confidence = 50.0
    bench.tenure_weeks = 40
    team.player_ids.append(bench_pid)
    gs.free_agent_ids.remove(bench_pid)
    # A regular elsewhere once upon a time — never dressed THIS season.
    gs.stat_history[bench_pid] = [_snap(0, 1, 1.05)]
    fixtures = sorted(
        (f for f in gs.fixtures if tid in (f.team_a, f.team_b)),
        key=lambda f: (f.week, f.id),
    )
    weeks_marked: list[int] = []
    for f in fixtures:  # mark played until `played_weeks` DISTINCT weeks
        if f.week not in weeks_marked:
            if len(weeks_marked) == played_weeks:
                break
            weeks_marked.append(f.week)
        f.played = True
    assert len(weeks_marked) == played_weeks
    gs.week = weeks_marked[-1]
    return tid, bench_pid


def test_long_benching_of_a_good_starter_forms_a_grudge(campaign: GameState) -> None:
    gs = campaign
    tid, pid = _bench_setup(gs, arcs.BENCH_ARC_WEEKS)
    assert arcs.bench_grudge_weeks(gs, tid, pid) == arcs.BENCH_ARC_WEEKS
    rows = arcs.org_grudges(gs, tid)
    assert [row["source"] for row in rows] == ["bench"]
    assert gs.players[pid].handle in rows[0]["text"]
    # The streak crossed the bar on this exact played week -> formation.
    moments = arcs.weekly_moments(gs, tid, gs.season, gs.week)
    assert [(m["phase"], m["pid"]) for m in moments] == [("formed", pid)]


def test_bench_grudge_needs_a_real_bench_and_starter_quality(
    campaign: GameState,
) -> None:
    gs = campaign
    tid, pid = _bench_setup(gs, arcs.BENCH_ARC_WEEKS)
    # Drop back to a five-man roster: a missed week now means unavailable,
    # not benched — the arc must vanish.
    dropped = next(p for p in gs.teams[tid].player_ids if p != pid)
    gs.teams[tid].player_ids.remove(dropped)
    assert arcs.bench_grudge_weeks(gs, tid, pid) == 0
    gs.teams[tid].player_ids.append(dropped)
    # A bench-quality body has no claim to the five either.
    gs.players[pid].attributes = {
        k: max(1.0, v - 40.0) for k, v in gs.players[pid].attributes.items()
    }
    assert arcs.bench_grudge_weeks(gs, tid, pid) == 0


def test_bench_grudge_cools_when_they_dress_again(campaign: GameState) -> None:
    gs = campaign
    tid, pid = _bench_setup(gs, arcs.BENCH_ARC_WEEKS + 1)
    # They dressed the most recent played week after 4 straight on the bench.
    gs.stat_history[pid].append(_snap(gs.season, gs.week, 1.1))
    assert arcs.bench_grudge_weeks(gs, tid, pid) == 0
    assert arcs.org_grudges(gs, tid) == []
    moments = arcs.weekly_moments(gs, tid, gs.season, gs.week)
    assert [(m["phase"], m["pid"]) for m in moments] == [("resolved", pid)]
    assert "back in the lineup" in moments[0]["text"]


# ---------------------------------------------------------------------------
# Bounded effects through existing channels


def test_renewal_bias_is_bounded_and_zero_by_default(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    r = sorted(gs.teams[tid].player_ids)
    # No arcs: exact no-op for everyone (the hands-off guarantee).
    for pid in r:
        assert arcs.renewal_bias(gs, pid, tid) == 0.0
    # An org grudge makes staying expensive.
    pr = promises.create_promise(gs, tid, r[0], "play_time", target_value=50, duration=4)
    promises.resolve_promise(gs, pr, success=False)
    assert arcs.renewal_bias(gs, r[0], tid) == arcs.GRUDGE_RENEWAL_BIAS
    # A bonded mentorship softens the table for both sides of it.
    gs.mentorships[r[2]] = r[1]
    _rel(gs, r[1], r[2], 80.0)
    assert arcs.renewal_bias(gs, r[1], tid) == arcs.MENTOR_BOND_RENEWAL_BIAS
    assert arcs.renewal_bias(gs, r[2], tid) == arcs.MENTOR_BOND_RENEWAL_BIAS
    # Off-roster players never carry a bias.
    fa = sorted(gs.free_agent_ids)[0]
    assert arcs.renewal_bias(gs, fa, tid) == 0.0


def test_grudge_raises_the_renewal_ask(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    pid = gs.teams[tid].player_ids[0]
    p = gs.players[pid]
    morale, confidence = p.morale, p.confidence
    gs.set_acting(tid)
    base_salary, _ = market.contract_demands(gs, pid, "renew")
    pr = promises.create_promise(gs, tid, pid, "make_captain", duration=4)
    promises.resolve_promise(gs, pr, success=False)
    # Undo the promise's own morale/confidence fallout so the ONLY delta
    # left on the table is the arcs renewal bias.
    p.morale, p.confidence = morale, confidence
    grudge_salary, _ = market.contract_demands(gs, pid, "renew")
    gs.set_acting(None)
    assert grudge_salary > base_salary


def test_mentor_bond_deepens_ceiling_growth(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    mentor_id, pro_id = gs.teams[tid].player_ids[:2]
    mentor, pro = gs.players[mentor_id], gs.players[pro_id]
    mentor.age, pro.age = 30, 18
    keys = sorted(mentor.attributes)
    for k in keys:
        mentor.attributes[k] = 70.0
        pro.attributes[k] = 55.0
    best = keys[:2]
    for k in best:
        mentor.attributes[k] = 95.0
        pro.skill_potential[k] = 70.0
    gs.mentorships[pro_id] = mentor_id

    plain = gs.model_copy(deep=True)
    bonded = gs.model_copy(deep=True)
    _rel(plain, mentor_id, pro_id, 50.0)
    _rel(bonded, mentor_id, pro_id, 85.0)
    development.apply_mentorship_growth(plain)
    development.apply_mentorship_growth(bonded)

    lift_plain = sum(plain.players[pro_id].skill_potential[k] - 70.0 for k in best)
    lift_bonded = sum(bonded.players[pro_id].skill_potential[k] - 70.0 for k in best)
    assert lift_plain > 0.0
    assert lift_bonded == pytest.approx(lift_plain * arcs.MENTOR_BOND_STEP_MULT)


# ---------------------------------------------------------------------------
# Hands-off safety


def test_hands_off_campaign_has_no_org_arcs_or_bias(game_data: GameData) -> None:
    gs = new_campaign(game_data, seed=77)
    for _ in range(2):
        advance_week(gs, game_data)
    tid = gs.user_team_id
    assert arcs.org_grudges(gs, tid) == []
    assert arcs.weekly_moments(gs, tid, gs.season, gs.week) == []
    for pid in gs.teams[tid].player_ids:
        assert arcs.renewal_bias(gs, pid, tid) == 0.0
