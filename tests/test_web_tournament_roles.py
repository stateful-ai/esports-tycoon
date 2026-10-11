"""Tournament eligibility exposes promises without redefining selected players."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import default_five, dressed_for, new_campaign
from esports_sim.web import server


@pytest.mark.parametrize("second_human", [False, True])
@pytest.mark.parametrize("automatic", [False, True])
def test_registration_roles_are_promises_independent_of_selection(
    game_data, second_human, automatic
):
    gs = new_campaign(game_data, seed=2038)
    tid = gs.user_team_id
    if second_human:
        tid = next(t for t in sorted(gs.teams) if t != tid)
        gs.human_team_ids.append(tid)
    gs.set_acting(tid)
    team = gs.teams[tid]
    extra = gs.free_agent_ids.pop(0)
    team.player_ids.append(extra)
    team.lineup_ids = [] if automatic else team.player_ids[-5:]
    selected = default_five(gs, tid)
    benched = next(pid for pid in team.player_ids if pid not in selected)
    gs.players[benched].roster_role = "starter"
    gs.players[selected[0]].roster_role = "bench"
    fixture = gs.team_fixture(tid)
    assert fixture is not None
    override = [benched, *selected[1:]]
    gs.map_lineups[f"{tid}|{fixture.id}|{fixture.maps[0]}"] = override
    # Club serializers initialize unrelated view defaults on first read.
    server._club_view(gs)
    before = gs.model_dump_json()
    view = server._club_view(gs)
    roles = {p["id"]: p["role"] for p in view["registration"]["players"]}
    assert set(roles) == set(team.player_ids)
    assert roles[benched] == "starter"
    assert roles[selected[0]] == "bench"
    assert default_five(gs, tid) == selected
    assert dressed_for(gs, tid, fixture, fixture.maps[0]) == override
    assert server._club_view(gs) == view
    assert gs.model_dump_json() == before
