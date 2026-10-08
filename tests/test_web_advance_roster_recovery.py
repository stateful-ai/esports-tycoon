"""Short rosters get browser recovery guidance without advancing the campaign."""

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException

from esports_sim.manager import market
from esports_sim.manager.campaign import new_campaign
from esports_sim.web import server


@pytest.mark.parametrize("count", [4, 3])
def test_short_roster_rejection_points_to_market_without_mutation(game_data, tmp_path, count):
    gs = new_campaign(game_data, seed=2038)
    tid = gs.user_team_id
    gs.teams[tid].player_ids = gs.teams[tid].player_ids[:count]
    game = server._Game(game_data, "HINTS", gs=gs)
    game.save_path = tmp_path / "campaign.json"
    token = server._ctx.set(server._ReqCtx(game, tid))
    before = gs.model_dump_json()
    try:
        with pytest.raises(HTTPException) as error:
            server.advance()
        assert error.value.status_code == 409
        assert "Market → Players" in error.value.detail
        assert f"sign {5 - count} more free" in error.value.detail
        assert "try Advance Week again" in error.value.detail
        assert "sign action" not in error.value.detail
        assert gs.model_dump_json() == before
        assert not game.ready and not game.dirty
        # The shared manager check still offers the CLI's actionable sign hint.
        assert "the sign action lists free agents" in market.roster_ready(gs, tid)[1]
    finally:
        server._ctx.reset(token)
