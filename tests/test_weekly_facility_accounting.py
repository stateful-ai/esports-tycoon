"""Actual settlement accounting, per-seat reporting, and unchanged game effects."""
from __future__ import annotations

import pytest

from esports_sim.manager import campaign, economy, sponsors
from esports_sim.manager.state import SponsorDeal, SponsorDemand


@pytest.mark.parametrize("facilities", [
    {}, {"marketing_office": 1},
    {"training_center": 3, "analytics_suite": 2, "marketing_office": 2},
])
def test_settlement_classifies_actual_charge_and_preserves_net_contract(game_data, facilities):
    gs = campaign.new_campaign(game_data, seed=4306)
    gs.facilities = facilities
    gs.sponsor = SponsorDeal(name="Legacy", kind="steady", weekly=5000, weeks_left=8)
    gs.sponsor_slots["jersey"] = SponsorDeal(
        name="Current", kind="performance", weekly=12000, per_win=3000, weeks_left=8,
    )
    legacy = gs.model_copy(deep=True)
    before = gs.teams[gs.user_team_id].balance
    settled = sponsors.weekly_settlement(gs, True)
    assert settled.income == 20000
    assert settled.facility_upkeep == economy.facility_weekly_upkeep(facilities)
    assert settled.net == gs.teams[gs.user_team_id].balance - before
    assert sponsors.weekly_tick(legacy, True) == settled.net
    assert gs.model_dump_json() == legacy.model_dump_json()


@pytest.mark.parametrize("negative_adjustment", [False, True])
def test_advance_preserves_complete_state_and_reconciles_each_human(game_data, monkeypatch, negative_adjustment):
    gs = campaign.new_campaign(game_data, seed=4307)
    other = next(tid for tid in sorted(gs.teams) if tid != gs.user_team_id)
    gs.human_team_ids.append(other)
    gs.facilities_by[gs.user_team_id] = {"marketing_office": 1}
    gs.facilities_by[other] = {"training_center": 3, "analytics_suite": 2}
    for tid in gs.human_team_ids:
        gs.set_acting(tid)
        gs.sponsor_slots["jersey"] = SponsorDeal(
            name="Testworks", kind="steady", weekly=5000, weeks_left=10,
        )
        if negative_adjustment:
            # A real missed accepted obligation at this tick's named fixture.
            fixture = next(f for f in gs.fixtures if tid in (f.team_a, f.team_b))
            fixture.week = gs.week
            gs.sponsor_demands.append(SponsorDemand(
                id=f"missed-{tid}", brand="Testworks", slot="jersey",
                kind="field_rookie", fixture_id=fixture.id, opponent_id=other,
                player_id="missing", issued_season=gs.season, issued_week=gs.week,
                deadline_week=gs.week, reward=10000, penalty=20000, status="accepted",
            ))
    gs.set_acting(None)
    baseline = gs.model_copy(deep=True)
    # Reproduce the previous report classification while executing precisely
    # the same settlement. Complete GameState equality also covers RNG-driven
    # downstream offers, training, social state and all balances.
    real_settlement = sponsors.weekly_settlement
    with monkeypatch.context() as old:
        def previous_classification(world, won):
            actual = real_settlement(world, won)
            return sponsors.WeeklySettlement(income=actual.net, facility_upkeep=0)
        old.setattr(sponsors, "weekly_settlement", previous_classification)
        old_report = campaign.advance_week(baseline, game_data)
    actual_charges = {}
    def capture_settlement(world, won):
        team = world.teams[world.acting_team_id]
        before = team.balance
        actual = real_settlement(world, won)
        assert team.balance - before == actual.net
        actual_charges[world.acting_team_id] = actual.facility_upkeep
        return actual
    monkeypatch.setattr(sponsors, "weekly_settlement", capture_settlement)
    report = campaign.advance_week(gs, game_data)
    assert gs.model_dump_json() == baseline.model_dump_json()
    for tid in gs.human_team_ids:
        upkeep = actual_charges[tid]
        assert report.facility_upkeep_by[tid] == upkeep
        assert report.income_by[tid] == old_report.income_by[tid] + upkeep
        assert report.expenses_by[tid] == old_report.expenses_by[tid] + upkeep
        assert report.income_by[tid] - report.expenses_by[tid] == (
            old_report.income_by[tid] - old_report.expenses_by[tid]
        )
        if negative_adjustment:
            assert gs.sponsor_demands_by[tid][0].status == "missed"
    assert report.user_income == report.income_by[gs.user_team_id]
    assert report.user_expenses == report.expenses_by[gs.user_team_id]

    import esports_sim.web.server as server
    game = server._Game(game_data, "ACCOUNTING", gs=gs)
    game.last_report = report
    for tid in gs.human_team_ids:
        server._ctx.set(server._ReqCtx(game, tid))
        view = server._report_view(report, gs, tid)
        assert view["user_facility_upkeep"] == actual_charges[tid]
        assert view["user_income"] == report.income_by[tid]
        assert view["user_expenses"] == report.expenses_by[tid]
        assert server.last_week_report()["report"] == view
        finances = server.finances()
        assert finances["last_week_income"] == view["user_income"]
        assert finances["last_week_expenses"] == view["user_expenses"]
        assert finances["last_week_facility_upkeep"] == view["user_facility_upkeep"]
