"""Actionable review advice follows the next selected lineup, not match history."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import new_campaign
from esports_sim.manager.campaign import _fixture_plans, dressed_for, projected_dressed_for
from esports_sim.manager.state import Fixture, GamePlan, MatchReview, ReviewPoint, StaffMember
from esports_sim.web import server


@pytest.mark.parametrize("second_manager", [False, True])
@pytest.mark.parametrize("developing", [False, True])
@pytest.mark.parametrize("selection", [
    "bench", "selected", "rotation", "one_match_in", "one_match_out",
    "map_beats_plan", "stale_plan", "invalid_plan", "automatic", "no_fixture",
])
def test_review_advice_follows_live_selection(game_data, monkeypatch, selection, developing, second_manager):
    gs = new_campaign(game_data, seed=2038)
    tid = next(t for t in gs.teams if t != gs.user_team_id) if second_manager else gs.user_team_id
    if second_manager:
        gs.human_team_ids.append(tid)
    gs.set_acting(tid)
    team = gs.teams[tid]
    extra = gs.players[team.player_ids[0]].model_copy(deep=True, update={"id": "review_sub", "handle": "ReviewSub"})
    gs.players[extra.id] = extra
    team.player_ids.append(extra.id)
    five = team.player_ids[:5]
    team.lineup_ids = list(five)
    pid = extra.id
    with_sub = [pid, *five[:4]]
    fx = Fixture(id="upcoming", week=gs.week, team_a=tid,
                 team_b=next(t for t in gs.teams if t != tid), maps=["ascent", "lotus", "split"], best_of=3)
    gs.fixtures = [] if selection == "no_fixture" else [fx]
    gs.tournament_rosters[tid] = list(team.player_ids)
    if selection in {"selected", "one_match_out"}:
        team.lineup_ids = with_sub
    if selection in {"rotation", "map_beats_plan"}:
        gs.map_lineups[f"{tid}|{fx.id}|ascent"] = with_sub
    if selection in {"one_match_in", "one_match_out", "map_beats_plan", "stale_plan", "invalid_plan"}:
        gs.game_plans_by[tid] = GamePlan(
            fixture_id="old" if selection == "stale_plan" else fx.id,
            starter_ids=five if selection in {"one_match_out", "map_beats_plan"}
            else [pid] * 5 if selection == "invalid_plan" else with_sub,
        )
    if selection == "automatic":
        team.lineup_ids = []
        # Pick someone the authoritative fallback selected; no saved preference.
        pid = dressed_for(gs, tid, fx, "ascent")[0]
    monkeypatch.setattr(server, "_player_developing", lambda *_: (developing, [80, 90]))
    gs.staff["coach"] = StaffMember(id="co", name="Coach", role="coach", quality=85, salary=1, specialty="team")
    gs.last_review_by[tid] = MatchReview(fixture_id="historical", team_id=tid, breaking=[
        ReviewPoint(code="player_under", category="player", tone="bad", player_id=pid, value=.72, lever_code="player_form")
    ])
    gs.facilities
    before = gs.model_dump_json()
    view = server._last_match_review(gs)
    assert gs.model_dump_json() == before
    assert view["breaking"][0]["player_id"] == pid
    assert "0.72" in view["breaking"][0]["detail"]
    text = view["levers"][0]["text"]
    if selection in {"selected", "one_match_in", "automatic"}:
        assert "already" not in text
        assert "mentor" in text if developing else "bench or agent" in text
    else:
        assert "already" in text and "consider a bench" not in text
        assert "rotating out on some maps" in text if selection in {"rotation", "map_beats_plan"} else "outside your default five" in text if selection == "no_fixture" else "out of the next fixture" in text
        assert "mentor" in text if developing else "training and agent fit" in text
    # Projection equals what sim installs, including explicit-map precedence.
    _, plans = _fixture_plans(gs, fx)
    projected = gs.model_copy(deep=True)
    for map_id in fx.maps:
        if tid in plans:
            projected.map_lineups.setdefault(f"{tid}|{fx.id}|{map_id}", plans[tid])
        assert projected_dressed_for(gs, tid, fx, map_id) == dressed_for(projected, tid, fx, map_id)
