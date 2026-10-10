from __future__ import annotations

import pytest

from esports_sim.manager import new_campaign, promises
from esports_sim.schemas.promise import ManagerPromise


@pytest.fixture
def world(game_data):
    return new_campaign(game_data, seed=2038, user_team_id="team_nexus")


def promise_for(gs, **updates):
    promise = ManagerPromise(
        id="assessment", team_id=gs.user_team_id,
        player_id=gs.teams[gs.user_team_id].player_ids[0],
        promise_type="play_time", target_value=60,
        initial_duration=8, weeks_left=1, dressed_count=5,
        created_week=1, created_season=1,
    ).model_copy(update=updates)
    gs.promises = [promise]
    return promise


@pytest.mark.parametrize("dressed,remaining,played,expected", [
    (5, 1, True, "kept"), (5, 1, False, "kept"),
    (4, 1, True, "kept"), (4, 1, False, "broken"),
    (3, 2, True, "active"), (3, 2, False, "broken"),
    (5, 2, True, "active"), (5, 2, False, "active"),
])
def test_next_evaluation_matches_actual_evaluator(world, dressed, remaining, played, expected):
    pr = promise_for(world, dressed_count=dressed, weeks_left=remaining)
    before = world.model_dump_json()
    assessment = promises.play_time_assessment(world, pr)
    assert world.model_dump_json() == before
    assert assessment["window_weeks"] == 8
    assert assessment["required_dressed_weeks"] == 5  # ceil(8 * 60%)
    assert assessment["next_dressed_status" if played else "next_not_dressed_status"] == expected
    promises.weekly_tick(world, {pr.team_id: {pr.player_id} if played else set()})
    assert pr.status == expected
    assert pr.dressed_count == dressed + int(played)


@pytest.mark.parametrize("target,required", [("60", 5), (None, 8), ("unknown", 8), (0, 0)])
def test_target_coercion_matches_evaluator(world, target, required):
    pr = promise_for(world, target_value=target)
    assessment = promises.play_time_assessment(world, pr)
    assert assessment["required_dressed_weeks"] == required
    promises.weekly_tick(world, {})
    assert pr.status == assessment["next_not_dressed_status"]


@pytest.mark.parametrize("season,week,created_season,created_week", [(1, 9, 1, 2), (2, 2, 1, 3)])
def test_legacy_window_reconstruction_matches_next_tick(world, season, week, created_season, created_week):
    world.season, world.week = season, week
    pr = promise_for(world, initial_duration=0, created_season=created_season, created_week=created_week)
    before = world.model_dump_json()
    assessment = promises.play_time_assessment(world, pr)
    assert world.model_dump_json() == before
    promises.weekly_tick(world, {})
    assert pr.initial_duration == assessment["window_weeks"]
    assert pr.status == assessment["next_not_dressed_status"]


def test_week_is_one_credit_even_if_many_maps_and_bye_still_uses_deadline(world):
    pr = promise_for(world, weeks_left=3, dressed_count=3)
    promises.weekly_tick(world, {pr.team_id: {pr.player_id, pr.player_id}})
    assert (pr.dressed_count, pr.weeks_left) == (4, 2)
    promises.weekly_tick(world, {})
    assert (pr.dressed_count, pr.weeks_left, pr.status) == (4, 1, "active")


def test_historical_and_unknown_promises_are_not_reassessed(world):
    for updates in ({"status": "kept"}, {"status": "broken"}, {"promise_type": "unknown"}):
        pr = promise_for(world, **updates)
        before = pr.model_dump()
        assert promises.play_time_assessment(world, pr) is None
        assert pr.model_dump() == before


def test_both_public_surfaces_serialize_the_same_pure_assessment(world, game_data):
    pytest.importorskip("fastapi")
    from esports_sim.web import server
    pr = promise_for(world)
    token = server._ctx.set(server._ReqCtx(server._Game(game_data, "PROMC", gs=world), world.user_team_id))
    try:
        # Bind the same acting manager before taking the purity snapshot.
        server.S.require_gs()
        # Existing roster/profile readers lazily initialize scouting maps.
        server.roster(world.user_team_id)
        server.player_profile(pr.player_id)
        before = world.model_dump_json()
        roster_pr = server.roster(world.user_team_id)["promises"][0]
        profile_pr = server.player_profile(pr.player_id)["player"]["promises"][0]
        assert roster_pr == profile_pr
        assert roster_pr["play_time_assessment"] == promises.play_time_assessment(world, pr)
        assert world.model_dump_json() == before
        a = roster_pr["play_time_assessment"]
        assert "60% of 8 window weeks" in a["target_label"]
        assert "5/8" in a["progress_label"]
        assert "62.5%" in a["progress_label"]
        assert "next weekly evaluation" in a["deadline_label"]
        assert a["fulfillment_percent"] == 100
    finally:
        server._ctx.reset(token)
