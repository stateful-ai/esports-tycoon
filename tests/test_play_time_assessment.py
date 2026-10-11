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
        assert "60% of the original 8-week promise" in a["target_label"]
        assert "5 accumulated dressed-week credits; 5 required" in a["progress_label"]
        assert "Target reached" in a["progress_label"]
        assert "dressed_percent" not in a
        assert "next weekly evaluation" in a["deadline_label"]
        assert a["fulfillment_percent"] == 100
    finally:
        server._ctx.reset(token)


@pytest.mark.parametrize("reset_duration", [1, 4, 6])
def test_repeating_late_promise_keeps_original_requirement_and_accumulated_credits(world, reset_duration):
    tid = world.user_team_id
    pid = world.teams[tid].player_ids[0]
    pr = promises.create_promise(world, tid, pid, "play_time", target_value=60, duration=4)
    for week in (1, 2, 3):
        world.week = week
        promises.weekly_tick(world, {tid: {pid}})
    assert (pr.initial_duration, pr.dressed_count, pr.weeks_left, pr.status) == (4, 3, 1, "active")
    world.week = 4
    original = pr.model_dump()
    repeated = promises.create_promise(world, tid, pid, "play_time", target_value=60, duration=reset_duration)
    assert repeated is pr
    assert pr.model_dump() == {**original, "weeks_left": reset_duration}

    # Every forecast is checked against the real evaluator, including enough
    # credited appearances to exceed the original basis after an extension.
    for elapsed in range(reset_duration):
        before = world.model_dump_json()
        a = promises.play_time_assessment(world, pr)
        assert world.model_dump_json() == before
        assert a["target_basis_weeks"] == 4
        assert a["required_dressed_weeks"] == 3
        assert a["dressed_weeks"] == 3 + elapsed
        assert a["evaluations_left"] == reset_duration - elapsed
        assert "original 4-week promise" in a["target_label"]
        assert f"{3 + elapsed} accumulated dressed-week credits; 3 required" in a["progress_label"]
        assert "Target reached" in a["progress_label"]
        assert "window weeks dressed" not in a["progress_label"]
        assert "%" not in a["progress_label"]
        assert "Repeating this promise resets evaluations left" in a["counting_label"]
        assert a["fulfillment_percent"] == 100
        promises.weekly_tick(world, {tid: {pid}})
        assert pr.status == a["next_dressed_status"]
        world.week += 1
    assert pr.status == "kept"
    assert pr.initial_duration == 4
    assert pr.dressed_count == 3 + reset_duration
    assert promises.play_time_assessment(world, pr) is None


def test_legacy_reconstructed_basis_is_labeled_as_inferred(world):
    world.week = 9
    pr = promise_for(world, initial_duration=0, created_week=2)
    a = promises.play_time_assessment(world, pr)
    assert a["target_basis_inferred"] is True
    assert "reconstructed 8-week target basis" in a["target_label"]
    assert "original 8-week promise" not in a["target_label"]
    promises.weekly_tick(world, {})
    assert pr.initial_duration == a["target_basis_weeks"]


def test_public_duplicate_action_returns_retained_target_and_reset_deadline(world, game_data):
    pytest.importorskip("fastapi")
    from esports_sim.web import server
    pr = promise_for(world, initial_duration=4, dressed_count=5, weeks_left=1)
    token = server._ctx.set(server._ReqCtx(server._Game(game_data, "RENEW", gs=world), world.user_team_id))
    try:
        original = pr.model_dump()
        result = server.promise_action(server.PromiseBody(kind="bench_minutes", player_id=pr.player_id))
        assert pr.model_dump() == {**original, "weeks_left": 6}
        assert "3 dressed-week credits" in result["message"]
        assert "original 4-week promise" in result["message"]
        assert "after 6 more weekly evaluations" in result["message"]
        roster = next(p for p in server.roster(world.user_team_id)["promises"] if p["id"] == pr.id)
        profile = server.player_profile(pr.player_id)["player"]["promises"][0]
        assert roster == profile
        a = roster["play_time_assessment"]
        assert "5 accumulated dressed-week credits; 3 required" in a["progress_label"]
        assert "Target reached" in a["progress_label"]
        assert "125%" not in str(a)
    finally:
        server._ctx.reset(token)


@pytest.mark.parametrize("played,expected", [(False, "broken"), (True, "active")])
def test_final_scheduled_evaluation_distinguishes_earlier_break(world, played, expected):
    pr = promise_for(world, dressed_count=3, weeks_left=2)
    a = promises.play_time_assessment(world, pr)
    assert "Final scheduled evaluation: after 2" in a["deadline_label"]
    assert "can break earlier" in a["deadline_label"]
    assert "If not dressed next evaluation, it breaks then" in a["deadline_label"]
    assert "Even if dressed" not in a["deadline_label"]
    promises.weekly_tick(world, {pr.team_id: {pr.player_id} if played else set()})
    assert pr.status == expected == a["next_dressed_status" if played else "next_not_dressed_status"]


@pytest.mark.parametrize("season,week,created_season,created_week", [(1, 9, 1, 2), (2, 2, 1, 3)])
def test_legacy_renewal_freezes_inferred_basis_before_reset_and_survives_reload(world, season, week, created_season, created_week):
    from esports_sim.manager.state import GameState
    world.season, world.week = season, week
    pr = promise_for(world, initial_duration=0, created_season=created_season, created_week=created_week)
    original = pr.model_dump()
    a = promises.play_time_assessment(world, pr)
    repeated = promises.create_promise(world, pr.team_id, pr.player_id, "play_time", target_value=60, duration=6)
    assert repeated is pr
    assert pr.model_dump() == {**original, "initial_duration": a["target_basis_weeks"], "weeks_left": 6}
    world = GameState.model_validate_json(world.model_dump_json())
    pr = world.promises[0]
    for _ in range(6):
        forecast = promises.play_time_assessment(world, pr)
        assert forecast["target_basis_weeks"] == a["target_basis_weeks"]
        assert forecast["required_dressed_weeks"] == a["required_dressed_weeks"]
        promises.weekly_tick(world, {})
        assert pr.status == forecast["next_not_dressed_status"]
        world.week += 1
        if pr.status != "active":
            break
    assert pr.status == ("kept" if pr.dressed_count >= a["required_dressed_weeks"] else "broken")


@pytest.mark.parametrize("kind", ["make_captain", "unknown"])
def test_legacy_duration_is_not_frozen_for_other_promise_types(world, kind):
    pr = promise_for(world, initial_duration=0, promise_type=kind)
    before = pr.model_dump()
    promises.create_promise(world, pr.team_id, pr.player_id, kind, target_value=60, duration=6)
    assert pr.model_dump() == {**before, "weeks_left": 6}


def test_public_legacy_renewal_retains_pre_action_requirement(world, game_data):
    pytest.importorskip("fastapi")
    from esports_sim.web import server
    world.week = 9
    pr = promise_for(world, initial_duration=0, created_week=2)
    original = promises.play_time_assessment(world, pr)
    token = server._ctx.set(server._ReqCtx(server._Game(game_data, "LEGACY", gs=world), world.user_team_id))
    try:
        result = server.promise_action(server.PromiseBody(kind="bench_minutes", player_id=pr.player_id))
        assert "5 dressed-week credits" in result["message"]
        roster = server.roster(world.user_team_id)["promises"][0]
        profile = server.player_profile(pr.player_id)["player"]["promises"][0]
        assert roster == profile
        assert (pr.initial_duration, pr.weeks_left, pr.dressed_count) == (8, 6, 5)
        assert roster["play_time_assessment"]["required_dressed_weeks"] == original["required_dressed_weeks"]
    finally:
        server._ctx.reset(token)
