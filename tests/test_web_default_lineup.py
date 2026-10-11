"""Club default picks reflect the campaign's effective five after roster churn."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import default_five, dressed_for, new_campaign
from esports_sim.manager.state import GameState, ManagerSeat
from esports_sim.web import server


@pytest.mark.parametrize("second_human", [False, True])
@pytest.mark.parametrize("selection", ["partial", "valid", "auto", "stale"])
def test_resolved_default_matches_header_and_map(
    game_data, tmp_path, second_human, selection
):
    gs = new_campaign(game_data, seed=2038)
    tid = gs.user_team_id
    if second_human:
        tid = next(t for t in sorted(gs.teams) if t != tid)
        gs.human_team_ids.append(tid)
        gs.managers["second"] = ManagerSeat(id="second", name="Second", team_id=tid)
    team = gs.teams[tid]
    extra = gs.free_agent_ids.pop(0)
    team.player_ids.append(extra)
    picks = team.player_ids[:3]
    if selection == "valid":
        picks = team.player_ids[:5]
    elif selection == "auto":
        picks = []
    elif selection == "stale":
        picks = ["departed", picks[0], picks[0], picks[1]]
    team.lineup_ids = list(picks)
    game = server._Game(game_data, "FIVE", gs=gs)
    game.save_path = tmp_path / "campaign.json"
    token = server._ctx.set(server._ReqCtx(game, tid))
    try:
        before = team.model_dump_json()
        payload = server.roster(tid)
        resolved = default_five(gs, tid)
        assert payload["lineup_ids"] == picks
        assert payload["effective_lineup_ids"] == resolved
        assert payload["team"]["starter_ids"] == resolved
        assert {p["id"] for p in payload["players"] if p["starter"]} == set(resolved)
        kept = set(picks) & set(resolved)
        assert payload["default_lineup_selection"] == {
            "saved_count": len(kept), "automatic_count": 5 - len(kept)
        }
        fx = next(f for f in gs.fixtures if tid in (f.team_a, f.team_b) and not f.played)
        map_id = fx.maps[0]
        assert dressed_for(gs, tid, fx, map_id) == resolved
        assert team.model_dump_json() == before

        # Per-map picks never change the default selection displayed by Club.
        override = team.player_ids[-5:]
        gs.map_lineups[f"{tid}|{fx.id}|{map_id}"] = override
        assert dressed_for(gs, tid, fx, map_id) == override
        assert server.roster(tid)["effective_lineup_ids"] == resolved

        server.set_lineup(server.LineupBody(lineup_ids=resolved))
        game.save(force=True)
        game.gs = GameState.load(game.save_path)
        saved = server.roster(tid)
        assert saved["effective_lineup_ids"] == resolved
        assert saved["default_lineup_selection"]["automatic_count"] == 0
        server.set_lineup(server.LineupBody(lineup_ids=[]))
        game.save(force=True)
        game.gs = GameState.load(game.save_path)
        cleared = server.roster(tid)
        assert cleared["lineup_ids"] == []
        assert cleared["effective_lineup_ids"] == default_five(game.gs, tid)
        assert cleared["default_lineup_selection"] == {"saved_count": 0, "automatic_count": 5}

        rival = next(t for t in gs.teams if t != tid)
        assert server.roster(rival)["default_lineup_selection"] is None
    finally:
        server._ctx.reset(token)
