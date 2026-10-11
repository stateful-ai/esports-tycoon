"""Club academy controls share the live move contract, including stale reads."""

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException

from esports_sim.manager import academy, market
from esports_sim.manager.campaign import new_campaign
from esports_sim.web import server


def _academy_world(game_data):
    gs = new_campaign(game_data, seed=2038)
    tid = gs.user_team_id
    gs.set_acting(tid)
    academy.seed_affiliates(gs)
    affiliate = gs.teams[gs.academy_affiliates[tid]]
    pid = affiliate.player_ids[0]
    gs.academy_player_rights[pid] = tid
    return gs, tid, affiliate, pid


def _add_player(gs, team):
    pid = gs.free_agent_ids.pop(0)
    team.player_ids.append(pid)
    return pid


@pytest.mark.parametrize(
    "blocker, expected",
    [
        ("depth", "affiliate must retain at least 5 players"),
        ("full", "first-team roster is full (10)"),
        ("closed", "Playoff rosters are frozen until the offseason."),
        ("rights", "another parent organization holds this player's pathway rights"),
        ("allowed", ""),
    ],
)
def test_club_promotion_availability_matches_live_validation(game_data, blocker, expected):
    gs, tid, affiliate, pid = _academy_world(game_data)
    if blocker != "depth":
        _add_player(gs, affiliate)
    if blocker == "full":
        while len(gs.teams[tid].player_ids) < market.ROSTER_MAX:
            _add_player(gs, gs.teams[tid])
    elif blocker == "closed":
        gs.phase = "playoffs"
    elif blocker == "rights":
        gs.academy_player_rights.pop(pid)

    # Other Club views can initialize their own defaults on the first read.
    server._club_view(gs)
    before = gs.model_dump_json()
    view = server._club_view(gs)["academy"]
    row = next(p for p in view["roster"] if p["id"] == pid)
    allowed, reason = academy.can_move(
        gs, tid, pid, "promote", window_check=server._academy_move_window
    )
    assert row["promote"] == {"allowed": allowed, "reason": reason}
    assert reason == expected
    assert allowed == (blocker == "allowed")
    assert f"Affiliate: {len(affiliate.player_ids)} players" in view["movement_detail"]
    assert "at least 5 players" in view["movement_detail"]
    assert "send-down can add affiliate depth" in view["movement_detail"]
    assert gs.model_dump_json() == before


@pytest.mark.parametrize("blocker", ["depth", "full", "closed", "allowed"])
def test_club_send_downs_use_server_candidates_and_live_validation(game_data, blocker):
    gs, tid, affiliate, _ = _academy_world(game_data)
    team = gs.teams[tid]
    pid = team.player_ids[0]
    gs.players[pid].age = academy.ACADEMY_MAX_AGE
    veteran = team.player_ids[1]
    gs.players[veteran].age = academy.ACADEMY_MAX_AGE + 1
    if blocker != "depth":
        _add_player(gs, team)
    if blocker == "full":
        while len(affiliate.player_ids) < market.ROSTER_MAX:
            _add_player(gs, affiliate)
    elif blocker == "closed":
        gs.phase = "playoffs"
    view = server._club_view(gs)["academy"]
    candidates = {row["id"]: row for row in view["send_down_roster"]}
    assert veteran not in candidates
    allowed, reason = academy.can_move(
        gs, tid, pid, "send_down", window_check=server._academy_move_window
    )
    assert candidates[pid]["send_down"] == {"allowed": allowed, "reason": reason}
    assert allowed == (blocker == "allowed")
    if blocker == "depth":
        assert reason == "first team must retain at least 5 players"
    elif blocker == "full":
        assert reason == "affiliate roster is full (10)"
    elif blocker == "closed":
        assert reason == "Playoff rosters are frozen until the offseason."


def test_stale_promotion_rejects_without_mutation_or_accepted_telemetry(game_data, tmp_path):
    gs, tid, affiliate, pid = _academy_world(game_data)
    extra = _add_player(gs, affiliate)
    row = next(p for p in server._club_view(gs)["academy"]["roster"] if p["id"] == pid)
    assert row["promote"]["allowed"]
    affiliate.player_ids.remove(extra)
    game = server._Game(game_data, "ACADEMY", gs=gs)
    game.save_path = tmp_path / "campaign.json"
    token = server._ctx.set(server._ReqCtx(game, tid))
    before = gs.model_dump_json()
    try:
        with pytest.raises(HTTPException) as error:
            server.academy_move(server.AcademyMoveBody(player_id=pid, direction="promote"))
        assert error.value.status_code == 422
        assert error.value.detail == "affiliate must retain at least 5 players"
        assert gs.model_dump_json() == before
        assert not game.dirty
        current = next(
            p for p in server._club_view(gs)["academy"]["roster"] if p["id"] == pid
        )
        assert current["promote"] == {"allowed": False, "reason": error.value.detail}
    finally:
        server._ctx.reset(token)


def test_no_affiliate_has_no_move_candidates(game_data):
    gs, tid, _, _ = _academy_world(game_data)
    gs.academy_affiliates.pop(tid)
    view = server._club_view(gs)["academy"]
    assert view["roster"] == view["send_down_roster"] == []
    assert view["movement_detail"] == "Organization has no academy affiliate."
