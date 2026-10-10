"""Accepted web choices survive the flat scalar ledger and save roundtrip."""
import json

import pytest
from fastapi import HTTPException

from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState
from esports_sim.web import server


@pytest.fixture
def ctx(game_data):
    gs = new_campaign(game_data, seed=321)
    game = server._Game(game_data, "CHOIC", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    yield gs
    server._ctx.reset(token)


def test_lineup_normalized_choices_clear_absent_and_save(ctx, tmp_path):
    gs = ctx
    picks = gs.teams[gs.user_team_id].player_ids[:5]
    server.set_lineup(server.LineupBody(lineup_ids=["stale", *picks], agents={picks[0]: "harbor"}))
    params = gs.action_log[-1].params
    assert json.loads(params["lineup_ids"]) == picks
    assert json.loads(params["agent_choices"]) == {picks[0]: "harbor"}
    assert params["player_ids"] == "null"
    server.set_lineup(server.LineupBody(agents={}, lineup_ids=[]))
    assert gs.action_log[-1].params["agent_choices"] == "{}"
    assert gs.action_log[-1].params["lineup_ids"] == "[]"
    server.set_lineup(server.LineupBody())
    assert gs.action_log[-1].params["agent_choices"] == "null"
    path = tmp_path / "save.json"
    gs.save(path)
    assert GameState.load(path).action_log == gs.action_log


def test_rejected_mixed_lineup_is_atomic(ctx):
    gs = ctx
    team = gs.teams[gs.user_team_id]
    before = gs.model_dump(mode="json")
    with pytest.raises(HTTPException):
        server.set_lineup(server.LineupBody(agents={team.player_ids[0]: "harbor"}, player_ids=team.player_ids[:4]))
    assert gs.model_dump(mode="json") == before


def test_per_map_choices_and_alternate_human(ctx):
    gs = ctx
    other = next(t for t in gs.teams if t != gs.user_team_id)
    gs.human_team_ids.append(other)
    token = server._ctx.set(server._ReqCtx(server._ctx.get().game, other))
    try:
        picks = gs.teams[other].player_ids[:5]
        fx = gs.team_fixture(other)
        server.set_lineup(server.LineupBody(player_ids=picks, fixture_id=fx.id, map_id=fx.maps[0]))
        row = gs.action_log[-1]
        assert row.team_id == other
        assert json.loads(row.params["player_ids"]) == picks
        assert row.params["lineup_ids"] == "null"
    finally:
        server._ctx.reset(token)


def test_gameplan_applied_dials_override_and_rejection(ctx):
    gs = ctx
    picks = gs.teams[gs.user_team_id].player_ids[:5]
    server.set_gameplan(server.GamePlanBody(aggression=999, pace=-5, starter_ids=picks, team_talk="reassure"))
    params = gs.action_log[-1].params
    assert params["aggression"] == "100.0"
    assert params["pace"] == "0.0"
    assert params["util_discipline"] == ""
    assert params["team_talk"] == "reassure"
    assert json.loads(params["starter_ids"]) == picks
    before = gs.model_dump(mode="json")
    with pytest.raises(HTTPException):
        server.set_gameplan(server.GamePlanBody(starter_ids=["stale"] * 5))
    assert gs.model_dump(mode="json") == before
    server.set_gameplan(server.GamePlanBody())
    assert gs.action_log[-1].params["starter_ids"] == "[]"
    assert gs.action_log[-1].params["team_talk"] == ""
    server.set_gameplan(server.GamePlanBody(clear=True))
    assert gs.action_log[-1].kind == "clear_game_plan"
    assert gs.game_plan is None


def test_agent_map_encoding_has_stable_order_and_rejects_foreign_ids(ctx):
    gs = ctx
    a, b = gs.teams[gs.user_team_id].player_ids[:2]
    server.set_lineup(server.LineupBody(agents={b: "harbor", a: "omen"}))
    first = gs.action_log[-1].params
    server.set_lineup(server.LineupBody(agents={a: "omen", b: "harbor"}))
    assert gs.action_log[-1].params == first
    before = gs.model_dump(mode="json")
    with pytest.raises(HTTPException):
        server.set_lineup(server.LineupBody(agents={"foreign_player": "harbor"}))
    assert gs.model_dump(mode="json") == before


@pytest.mark.parametrize("body", [
    {"aggression": float("nan")}, {"team_talk": "free text"},
    {"focus_target": "foreign_player"}, {"site_focus": "unknown"},
])
def test_invalid_gameplan_records_no_choice(ctx, body):
    before = ctx.model_dump(mode="json")
    with pytest.raises(HTTPException):
        server.set_gameplan(server.GamePlanBody(**body))
    assert ctx.model_dump(mode="json") == before

