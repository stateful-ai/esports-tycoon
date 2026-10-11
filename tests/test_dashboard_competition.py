"""Dashboard competition follows the acting manager's tier, like the recap.

Authored for the competition-tier fix; local execution intentionally UNRUN
under the user's waiver. These tests do not advance or simulate a campaign.
"""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import new_campaign
from esports_sim.manager import career
from esports_sim.web import server


@pytest.mark.parametrize("tier", [1, 2])
@pytest.mark.parametrize("mode", ["sandbox", "legacy"])
def test_dashboard_competition_matches_acting_manager_and_recap(game_data, tier, mode):
    gs = new_campaign(game_data, seed=2071, mode=mode)
    tid = next(t for t in sorted(gs.teams) if gs.teams[t].tier == tier)
    team = gs.teams[tid]
    peers = sorted(t for t in gs.teams
                   if gs.teams[t].tier == tier and gs.teams[t].region == team.region)
    # Place the acting manager below the top four without running matches.
    for i, peer in enumerate(t for t in peers if t != tid):
        gs.standings[peer].wins = 10 - i
        gs.standings[peer].losses = 0
    gs.standings[tid].wins = 0
    gs.standings[tid].losses = 2
    if tid not in gs.human_team_ids:
        gs.human_team_ids.append(tid)
    if gs.seat_for_session(tid) is None:
        career.create_seat(gs, tid, "Competition Manager")
    game = server._Game(game_data, "COMP", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, tid))
    before = gs.model_dump_json()
    try:
        view = server.state()
        competition = view["competition_table"]
        order = gs.standings_order(str(team.region), tier=tier)
        assert competition["tier"] == tier
        assert competition["region"] == str(team.region)
        name = "Challengers" if tier == 2 else "league"
        assert competition["label"] == f"{str(team.region).upper()} {name} (Tier {tier})"
        assert [r["id"] for r in competition["rows"]] == order
        assert [r["team_id"] for r in view["standings_top"]] == order[:4]
        assert tid not in order[:4]
        assert server._league_position(gs, tid) == {"pos": order.index(tid) + 1, "of": len(order)}
        for row in competition["rows"]:
            assert row["diff"] == gs.standings[row["id"]].diff
        # Season retains both regional divisions and its existing Tier 1 table.
        region = next(r for r in server.standings()["regions"] if r["region"] == str(team.region))
        assert [r["id"] for r in region["rows"]] == gs.standings_order(str(team.region), tier=1)
        assert [r["id"] for r in region["tier2_rows"]] == gs.standings_order(str(team.region), tier=2)
        assert gs.model_dump_json() == before
    finally:
        server._ctx.reset(token)


def test_competition_handles_empty_and_missing_team_without_mutation(game_data):
    gs = new_campaign(game_data, seed=2071)
    gs.standings.clear()
    before = gs.model_dump_json()
    assert server._competition_table(gs, gs.user_team_id)["rows"] == []
    assert server._league_position(gs, gs.user_team_id) is None
    assert server._competition_table(gs, "missing_team") is None
    assert gs.model_dump_json() == before


def test_legacy_save_default_tier_is_used_for_competition(game_data):
    gs = new_campaign(game_data, seed=2071)
    payload = gs.model_dump(mode="json")
    payload["teams"][gs.user_team_id].pop("tier")
    restored = type(gs).model_validate(payload)
    assert server._competition_table(restored, restored.user_team_id)["tier"] == 1


def test_active_draft_keeps_its_short_state_contract(game_data):
    gs = new_campaign(game_data, seed=2071, fantasy_draft=True)
    game = server._Game(game_data, "DRAFT", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    try:
        view = server.state()
        assert view["draft_active"] is True
        assert "competition_table" not in view
    finally:
        server._ctx.reset(token)
