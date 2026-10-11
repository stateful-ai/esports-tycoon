"""Season comparisons require an earlier observation, independently of weekly gains."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.development_path import report_view
from esports_sim.manager.state import DevSnap, GameState
from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Playstyle, Role
from esports_sim.schemas.player import DevelopmentWeek
from esports_sim.web import server


def snapshot(week, ca=52.2, attributes=None, season=2):
    return DevSnap(season=season, week=week, ca=ca, confidence=50, form=50,
                   morale=50, followers=0, attributes=attributes or {})


def world(snaps):
    player = Player(id="p", handle="Prospect", role=Role.DUELIST,
                    playstyle=Playstyle.ENTRY, attributes={"game_sense": 52.2})
    player.development_progress.latest = DevelopmentWeek(
        season=2, week=4, focus="tactical", intensity="light", maps=0,
        practice_gains={"game_sense": 0.67, "positioning": 0.85, "utility_usage": 1.56},
        scrim_gains={"game_sense": 0.01},
    )
    gs = GameState(seed=2038, season=2, week=5, user_team_id="team",
                   teams={"team": Team(id="team", name="Team", tag="T", player_ids=["p"])},
                   players={"p": player}, dev_history={"p": snaps})
    return gs, player


@pytest.mark.parametrize("snaps", [
    [snapshot(4, attributes={"game_sense": 52.2})],
    [snapshot(20, ca=50, attributes={"game_sense": 50}, season=1),
     snapshot(4, attributes={"game_sense": 52.2})],
])
def test_first_current_season_observation_does_not_claim_zero_growth(snaps):
    gs, player = world(snaps)
    before = gs.model_dump_json()
    report = server._development_report(gs, "team", {})
    row = report["players"][0]
    assert row["comparison_available"] is False
    assert row["overall_delta"] is None
    assert row["status"] == "first_observation"
    assert row["overall_start"] == row["overall_current"] == 52.2
    assert row["attribute_tracking"] is True
    assert row["changes"] == []
    assert row["latest_week"] == report_view(player)
    assert row["latest_week"]["sources"]["practice_gains"]["skills"]["utility_usage"] == 1.56
    assert report["overall_delta"] is None
    assert report["compared_players"] == report["steady"] == 0
    assert report["first_observations"] == 1
    assert gs.model_dump_json() == before


def test_two_flat_observations_are_a_measured_zero():
    gs, _ = world([snapshot(3, attributes={"game_sense": 52.2}),
                   snapshot(4, attributes={"game_sense": 52.2})])
    report = server._development_report(gs, "team", {})
    row = report["players"][0]
    assert row["comparison_available"] is True
    assert row["overall_delta"] == 0.0
    assert row["status"] == "steady"
    assert row["attribute_tracking"] is True and row["changes"] == []
    assert report["overall_delta"] == 0.0
    assert report["compared_players"] == report["steady"] == 1
    assert report["first_observations"] == 0


def test_legacy_attribute_unavailability_preserves_measured_overall_growth():
    gs, _ = world([snapshot(3, ca=51.8), snapshot(4, attributes={"game_sense": 52.2})])
    row = server._development_report(gs, "team", {})["players"][0]
    assert row["comparison_available"] is True
    assert row["overall_delta"] == 0.4 and row["status"] == "grown"
    assert row["attribute_tracking"] is False and row["changes"] == []


def test_first_observation_does_not_dilute_compared_squad_growth():
    gs, _ = world([snapshot(4, attributes={"game_sense": 52.2})])
    gs.players["veteran"] = gs.players["p"].model_copy(update={"id": "veteran", "handle": "Veteran"})
    gs.teams["team"].player_ids.append("veteran")
    gs.dev_history["veteran"] = [snapshot(0, ca=70), snapshot(4, ca=71)]
    report = server._development_report(gs, "team", {})
    assert report["overall_delta"] == 1.0
    assert report["compared_players"] == report["grown"] == report["first_observations"] == 1
    assert report["steady"] == 0
    assert report["players"][0]["id"] == "veteran"
