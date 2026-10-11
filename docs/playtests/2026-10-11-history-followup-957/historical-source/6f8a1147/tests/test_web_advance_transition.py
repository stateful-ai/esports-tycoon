"""The pre-advance copy distinguishes season rollover from a weekly tick."""

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import new_campaign
from esports_sim.web import server


@pytest.mark.parametrize("phase", ["regular", "playoffs", "offseason"])
def test_state_exposes_next_transition_without_mutating_campaign(game_data, phase):
    gs = new_campaign(game_data, seed=2040)
    gs.phase = phase
    gs.season = 3
    game = server._Game(game_data, "NEXTS", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    before = gs.model_dump_json()
    try:
        transition = server.state()["advance_transition"]
        if phase == "offseason":
            assert transition["label"] == "Start Season 4"
            assert "Season 4, Week 1" in transition["notice"]
            assert "weekly training, sponsor income and payroll do not run" in transition["notice"]
        else:
            assert transition == {"label": "Advance Week", "notice": ""}
        assert gs.model_dump_json() == before
    finally:
        server._ctx.reset(token)
