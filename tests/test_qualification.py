"""Public qualification bounds and grounded match-preview stakes."""

import pytest

from esports_sim.manager.narrative import match_preview
from esports_sim.manager.qualification import qualification_statuses
from esports_sim.manager.state import Fixture, GameState, TeamRecord
from esports_sim.schemas import Team


def league(wins=(12, 11, 9, 7, 4, 3, 3, 3)):
    teams = {str(i): Team(id=str(i), name=f"Team {i}", tag=f"T{i}") for i in range(len(wins))}
    fixtures = [Fixture(id=f"s1w14m{i}", week=14, team_a=str(i), team_b=str(i + 1))
                for i in range(0, len(wins), 2)]
    return GameState(seed=2038, week=14, user_team_id="1", teams=teams,
                     standings={str(i): TeamRecord(wins=w, losses=13-w) for i, w in enumerate(wins)},
                     fixtures=fixtures)


def statuses(gs):
    return qualification_statuses(gs, str(gs.teams["0"].region))


def test_final_week_clinched_fixture_has_seeding_stakes_and_is_pure():
    gs = league()
    before = gs.model_dump_json()
    expected = {str(i): "secured" if i < 4 else "eliminated" for i in range(8)}
    assert statuses(gs) == expected
    preview = match_preview(gs, gs.fixtures[0], "1", named_subject=True)
    assert preview == ["Team 1 have already secured a top-four playoff berth; "
                       "this match counts toward the final league order and playoff seeding."]
    assert match_preview(gs, gs.fixtures[0], "1", named_subject=True) == preview
    assert statuses(gs) == expected
    assert gs.model_dump_json() == before


def test_tied_ceilings_remain_contested_despite_current_round_difference():
    gs = league((12, 11, 9, 5, 4, 3, 3, 3))
    gs.standings["3"].rounds_won = 999
    assert statuses(gs)["3"] == "contested"  # fifth can tie fourth's floor
    assert statuses(gs)["4"] == "contested"  # fourth does not strictly exceed fifth's ceiling
    assert any("tighten" in line for line in match_preview(gs, gs.fixtures[1], "3"))
    assert any("back toward" in line for line in match_preview(gs, gs.fixtures[2], "4"))


def test_eliminated_preview_does_not_offer_a_qualification_comeback():
    gs = league()
    preview = match_preview(gs, gs.fixtures[2], "4", named_subject=True)
    assert preview == ["Team 4 can no longer reach the top-four playoff places; "
                       "this match still counts toward the final league record."]


def test_actual_unequal_remaining_games_control_qualification():
    gs = league((12, 11, 9, 7, 4, 3, 3, 3))
    assert statuses(gs)["4"] == "eliminated"
    gs.fixtures += [Fixture(id=f"s1extra{i}", week=14+i, team_a="4", team_b="5") for i in range(2)]
    assert statuses(gs)["4"] == "contested"  # ceiling 7 rather than guessed one week left
    assert statuses(gs)["3"] == "contested"
    assert statuses(gs)["2"] == "secured"


@pytest.mark.parametrize("changes", [
    {"played": True}, {"stage": "semi"}, {"bracket": "masters"}, {"tier": 2},
])
def test_played_and_nonregular_fixtures_do_not_inflate_ceiling(changes):
    gs = league()
    gs.fixtures += [Fixture(id=f"ignored{i}", week=15+i, team_a="4", team_b="5", **changes)
                    for i in range(10)]
    assert statuses(gs)["4"] == "eliminated"


def test_region_tier_and_competition_cut_are_isolated():
    gs = league()
    region = str(gs.teams["0"].region)
    other = next(r for r in ("americas", "emea", "pacific") if r != region)
    for tid, team_region, tier in [("foreign", other, 1), ("challenger", region, 2)]:
        gs.teams[tid] = Team(id=tid, name=tid, tag="OTH", region=team_region, tier=tier)
        gs.standings[tid] = TeamRecord(wins=99)
        gs.fixtures += [Fixture(id=f"cross{tid}{i}", week=15+i, team_a="4", team_b=tid)
                        for i in range(10)]
    assert statuses(gs)["4"] == "eliminated"
    assert set(statuses(gs)) == {str(i) for i in range(8)}
    assert qualification_statuses(gs, region, tier=2, cut=1) == {"challenger": "secured"}
    assert qualification_statuses(gs, region, cut=1)["1"] == "contested"
    assert qualification_statuses(gs, region, cut=0) == {}


@pytest.mark.parametrize("changes", [{"played": True}, {"stage": "semi"}, {"bracket": "masters"}])
def test_preview_does_not_attach_regular_qualification_to_other_fixtures(changes):
    gs = league()
    fixture = gs.fixtures[0].model_copy(update=changes)
    assert match_preview(gs, fixture, "1") == []


def test_challengers_preview_has_no_fictional_top_four_playoffs():
    gs = league()
    for team in gs.teams.values():
        team.tier = 2
    for fixture in gs.fixtures:
        fixture.tier = 2
    assert match_preview(gs, gs.fixtures[0], "1") == []


def test_outside_regular_season_no_qualification_bounds():
    gs = league()
    gs.phase = "playoffs"
    assert statuses(gs) == {}
    assert match_preview(gs, gs.fixtures[0], "1") == []


def test_web_elimination_badges_share_preview_bounds():
    pytest.importorskip("fastapi")
    from esports_sim.web.server import _eliminated_teams
    gs = league()
    assert _eliminated_teams(gs, str(gs.teams["0"].region)) == {
        tid for tid, status in statuses(gs).items() if status == "eliminated"
    }
