"""Series-card readback stays fixture-scoped and preserves saved intent."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import campaign, series_management
from esports_sim.manager.state import Fixture, GameState, SeriesDirective
from esports_sim.web import server


@pytest.fixture
def series(game_data, tmp_path):
    gs = campaign.new_campaign(game_data, seed=2038)
    tid = gs.user_team_id
    team = gs.teams[tid]
    sixth = gs.free_agent_ids.pop(0)
    team.player_ids.append(sixth)
    team.lineup_ids = team.player_ids[:5]
    gs.tournament_rosters[tid] = team.lineup_ids + [sixth]
    fixture = Fixture(id="saved-series", week=gs.week, stage="semi", best_of=3,
                      team_a=tid, team_b=next(t for t in gs.teams if t != tid),
                      maps=sorted(game_data.maps)[:3])
    gs.fixtures = [fixture]
    game = server._Game(game_data, "CARD", gs=gs)
    game.save_path = tmp_path / "campaign.json"
    token = server._ctx.set(server._ReqCtx(game, tid))
    try:
        yield gs, game, fixture, sixth, team.lineup_ids[-1]
    finally:
        server._ctx.reset(token)


@pytest.mark.parametrize("substitution", [False, True])
def test_saved_card_readback_and_unchanged_save(series, substitution):
    gs, game, fixture, incoming, outgoing = series
    body = server.SeriesDirectiveBody(
        fixture_id=fixture.id, trigger="after_loss", response="stabilize",
        substitute_in=incoming if substitution else None,
        substitute_out=outgoing if substitution else None,
    )
    assert server.series_directive(body)["ok"]
    before = gs.model_dump_json()
    first = server._club_view(gs)["series"]
    assert first["directive"] == body.model_dump(exclude={"clear"})
    assert first["substitute_handles"] == (
        {incoming: gs.players[incoming].handle, outgoing: gs.players[outgoing].handle}
        if substitution else {}
    )
    assert server._club_view(gs)["series"] == first
    assert gs.model_dump_json() == before
    assert server.series_directive(server.SeriesDirectiveBody(**first["directive"]))["ok"]
    game.save(force=True)
    saved = GameState.load(game.save_path)
    assert saved.series_directives_by == gs.series_directives_by
    assert saved.teams[gs.user_team_id].lineup_ids == gs.teams[gs.user_team_id].lineup_ids
    assert len(saved.action_log) == 2
    assert saved.action_log[-1].params == saved.action_log[-2].params


@pytest.mark.parametrize("fixture_state", ["different", "played", "absent", "past"])
def test_stale_card_is_not_applied_to_next_editor(series, fixture_state):
    gs, _, fixture, incoming, outgoing = series
    gs.series_directives_by[gs.user_team_id] = SeriesDirective(
        fixture_id="old-series" if fixture_state == "different" else fixture.id,
        trigger="always", response="press", substitute_in=incoming, substitute_out=outgoing,
    )
    if fixture_state == "played":
        fixture.played = True
    elif fixture_state == "absent":
        gs.fixtures = []
    elif fixture_state == "past":
        gs.week = fixture.week + 1
    before = gs.model_dump_json()
    view = server._club_view(gs)["series"]
    assert view["directive"] is None
    assert view["substitute_handles"] == {}
    assert gs.model_dump_json() == before


@pytest.mark.parametrize("availability", ["now_starter", "departed", "missing"])
def test_unavailable_saved_player_remains_honest_readback(series, availability):
    gs, _, fixture, incoming, outgoing = series
    tid = gs.user_team_id
    assert series_management.set_directive(gs, tid, fixture.id,
        trigger="after_loss", response="stabilize",
        substitute_in=incoming, substitute_out=outgoing)[0]
    if availability == "now_starter":
        gs.teams[tid].lineup_ids = [incoming, *gs.teams[tid].lineup_ids[:-1]]
    else:
        gs.teams[tid].player_ids.remove(incoming)
        if availability == "missing":
            del gs.players[incoming]
    before = gs.model_dump_json()
    view = server._club_view(gs)["series"]
    assert view["directive"]["substitute_in"] == incoming
    assert incoming not in view["bench_ids"]
    assert view["substitute_handles"][incoming] == (
        None if availability == "missing" else gs.players[incoming].handle
    )
    assert gs.model_dump_json() == before
