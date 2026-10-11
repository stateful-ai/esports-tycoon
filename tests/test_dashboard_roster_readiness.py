"""Dashboard readiness must agree with the advance gate, even for healthy players."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import market
from esports_sim.manager.campaign import new_campaign
from esports_sim.web import server


@pytest.mark.parametrize("count", [4, 5])
@pytest.mark.parametrize("second_human", [False, True])
def test_dashboard_readiness_matches_live_advance_gate(game_data, count, second_human):
    gs = new_campaign(game_data, seed=2038)
    tid = gs.user_team_id
    if second_human:
        tid = next(t for t in sorted(gs.teams) if t != tid)
        gs.human_team_ids.append(tid)
    gs.teams[tid].player_ids = gs.teams[tid].player_ids[:count]
    game = server._Game(game_data, "READY", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, tid))
    try:
        before_roster = list(gs.teams[tid].player_ids)
        before_actions = list(gs.action_log)
        view = server.state()
        assert view["roster_readiness"] == {
            "ready": count >= market.ROSTER_MIN,
            "reason": market.roster_ready(gs, tid)[1],
            "count": count,
            "minimum": market.ROSTER_MIN,
            "shortfall": max(0, market.ROSTER_MIN - count),
        }
        assert view["user_team"]["id"] == tid
        assert not any(p["burnout"] for p in view["rotation"])
        assert gs.teams[tid].player_ids == before_roster
        assert gs.action_log == before_actions
    finally:
        server._ctx.reset(token)
