"""Pending team moments point to their current browser home without ticking."""

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException

from esports_sim.manager import flavor_events, new_campaign
from esports_sim.rng.tree import RngTree
from esports_sim.web import server


@pytest.mark.parametrize("action,retry", [
    (server.advance, "Advance Week"),
    (server.sim_ahead_action, "Sim Ahead"),
])
def test_pending_flavor_recovery_names_current_dashboard_without_mutation(
    game_data, tmp_path, action, retry,
):
    gs = new_campaign(game_data, seed=2038)
    tid = gs.user_team_id
    gs.flavor_events_by[tid] = flavor_events._build_event(
        gs, tid, RngTree(gs.seed).derive("test", "flavor", gs.week, tid),
    )
    game = server._Game(game_data, "FLAVORHINT", gs=gs)
    game.save_path = tmp_path / "campaign.json"
    token = server._ctx.set(server._ReqCtx(game, tid))
    before = gs.model_dump_json()
    try:
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.status_code == 409
        assert "Dashboard → Needs you → Team moment" in error.value.detail
        assert "choosing a response" in error.value.detail
        assert f"try {retry} again" in error.value.detail
        assert "Action required" not in error.value.detail
        assert gs.model_dump_json() == before
        assert not game.ready and not game.dirty
        assert not game.save_path.exists()
    finally:
        server._ctx.reset(token)
