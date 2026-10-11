"""Resolved prize reporting reconciles actual payouts, without paying twice."""
from collections import defaultdict
from types import SimpleNamespace

import pytest

from esports_sim.manager import campaign, economy, sponsors, state
from esports_sim.registry import load_all
from esports_sim.web import server


@pytest.mark.parametrize("phase", ["placement", "regional", "masters", "champions", "none"])
def test_resolved_prizes_reconcile_all_manager_incomes(monkeypatch, phase):
    gd = load_all()
    gs = campaign.new_campaign(gd, seed=2038)
    regions = [gs.standings_order(str(r)) for r in gs.league_regions]
    gs.human_team_ids = [t for region in regions for t in region]
    gs.fixtures = []
    gs.week = 14 if phase == "placement" else 20
    gs.phase = "regular" if phase in ("placement", "none") else "playoffs"
    expected = defaultdict(int)

    def fixture(stage, a, b, suffix):
        gs.fixtures.append(state.Fixture(
            id=f"s1{suffix}", stage=stage, week=gs.week - 1,
            team_a=a, team_b=b, winner_id=a, played=True,
        ))

    if phase == "placement":
        for region in regions:
            expected.update(dict(zip(region[:4], [120_000, 70_000, 40_000, 25_000])))
    elif phase == "regional":
        for r, region in zip(gs.league_regions, regions):
            prefix = str(r)[:2]
            fixture("semi", region[0], region[2], prefix + "semi0")
            fixture("semi", region[1], region[3], prefix + "semi1")
            fixture("final", region[0], region[1], prefix + "final")
            expected[region[0]] = state.PRIZE_REGIONAL_CHAMPION
            expected[region[1]] = state.PRIZE_REGIONAL_FINAL_LOSER
            expected[region[2]] = expected[region[3]] = state.PRIZE_REGIONAL_SEMI_LOSER
    elif phase in ("masters", "champions"):
        ids = gs.human_team_ids[:8]
        gs.masters_seeds = ids[:6]
        prefix = "masters" if phase == "masters" else "champ"
        fixture(prefix + "_final", ids[0], ids[1], prefix + "final")
        fixture(prefix + "_sf", ids[0], ids[2], prefix + "sf0")
        fixture(prefix + "_sf", ids[1], ids[3], prefix + "sf1")
        fixture(prefix + "_qf", ids[2], ids[4], prefix + "qf0")
        fixture(prefix + "_qf", ids[3], ids[5], prefix + "qf1")
        amounts = (
            [state.PRIZE_CHAMPION, state.PRIZE_FINAL_LOSER, state.PRIZE_SEMI_LOSER,
             state.PRIZE_SEMI_LOSER, state.PRIZE_MASTERS_QF_LOSER, state.PRIZE_MASTERS_QF_LOSER]
            if phase == "masters" else
            [state.PRIZE_CHAMPIONS_WINNER, state.PRIZE_CHAMPIONS_RUNNER_UP,
             state.PRIZE_CHAMPIONS_SF_LOSER, state.PRIZE_CHAMPIONS_SF_LOSER,
             state.PRIZE_CHAMPIONS_QF_LOSER, state.PRIZE_CHAMPIONS_QF_LOSER]
        )
        expected.update(dict(zip(ids, amounts)))

    ordinary = defaultdict(int)
    original_finance = campaign.apply_weekly_finance
    def finance(team, *args, **kwargs):
        result = original_finance(team, *args, **kwargs)
        ordinary[team.id] += result[0]
        return result
    monkeypatch.setattr(campaign, "apply_weekly_finance", finance)
    for name in ("settle_demands", "weekly_tick"):
        original = getattr(sponsors, name)
        def wrap(gs, *args, _original=original, **kwargs):
            tid = gs.acting_team_id
            result = _original(gs, *args, **kwargs)
            ordinary[tid] += result
            return result
        monkeypatch.setattr(sponsors, name, wrap)

    # Observe exactly the phase-transition boundary, independently of weekly
    # expenses (including the separate facility-upkeep reporting defect).
    before, after = {}, {}
    original_ranks, original_solvency = campaign._update_world_ranks, economy.check_solvency
    def ranks(gs):
        original_ranks(gs)
        before.update({tid: gs.teams[tid].balance for tid in gs.human_team_ids})
    def solvency(gs):
        after.update({tid: gs.teams[tid].balance for tid in gs.human_team_ids})
        original_solvency(gs)
    monkeypatch.setattr(campaign, "_update_world_ranks", ranks)
    monkeypatch.setattr(economy, "check_solvency", solvency)

    report = campaign.advance_week(gs, gd)
    for tid in gs.human_team_ids:
        assert after[tid] - before[tid] == expected[tid]
        assert report.income_by[tid] == ordinary[tid] + expected[tid]
        award_notes = [n for n in report.notes if n.startswith(gs.teams[tid].name + " received ")]
        assert len(award_notes) == bool(expected[tid])
        if expected[tid]:
            assert f"{expected[tid]:,} cr" in award_notes[0]
    assert report.user_income == report.income_by[gs.user_team_id]
    state_before = gs.model_dump_json()
    report_before = repr(report)
    monkeypatch.setattr(server, "S", SimpleNamespace(prev_positions={}))
    for tid in gs.human_team_ids:
        first = server._report_view(report, gs, tid)
        assert first == server._report_view(report, gs, tid)
        assert first["user_income"] == ordinary[tid] + expected[tid]
    assert gs.model_dump_json() == state_before
    assert repr(report) == report_before
