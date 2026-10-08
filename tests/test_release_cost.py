"""The roster preview and release debit share the contract severance rule."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import market, new_campaign
from esports_sim.web import server


@pytest.mark.parametrize("release_fee,expected", [(78_000, 78_000), (0, 39_000)])
def test_roster_release_cost_matches_debit(game_data, release_fee, expected):
    gs = new_campaign(game_data, seed=2038, user_team_id="team_nexus")
    team = gs.teams[gs.user_team_id]
    player = gs.players[team.player_ids[0]]
    player.salary = 6_500
    player.release_fee = release_fee
    game = server._Game(game_data, "RELEASE-COST-TEST", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    gs.set_acting(gs.user_team_id)
    before = gs.model_dump_json()
    assert market.release_cost(player) == expected
    assert gs.model_dump_json() == before
    try:
        view = server.roster(team.id)
    finally:
        server._ctx.reset(token)
    cost = next(p["release_cost"] for p in view["players"] if p["id"] == player.id)
    assert cost == expected
    balance = team.balance
    ok, message = market.release_player(gs, team.id, player.id)
    assert ok, message
    assert balance - team.balance == cost
    assert f"severance {cost:,} cr" in message
