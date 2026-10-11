"""Profile development scopes: dated evidence, legacy gaps, private feedback.

Regression sources added during the local automated-test suspension. These
use stored snapshots only; no weekly simulation is needed.
"""
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.development_path import report_view
from esports_sim.manager.state import DevSnap
from esports_sim.schemas import Player
from esports_sim.schemas.common import Playstyle, Role
from esports_sim.schemas.player import BadgeDevelopmentEvent, DevelopmentWeek
from esports_sim.web import server


def snap(season=2, week=4, ca=52.2, attributes=None):
    return DevSnap(season=season, week=week, ca=ca, confidence=50, form=50,
                   morale=50, followers=1000, attributes=attributes or {})


@pytest.mark.parametrize("points,status,available,elapsed,delta", [
    ([], "no_observations", False, None, None),
    ([snap()], "first_observation", False, None, None),
    ([snap(), snap()], "first_observation", False, None, None),
    ([snap(week=4), snap(week=5)], "steady", True, 1, 0.0),
    ([snap(week=4), snap(week=9, ca=53.2)], "grown", True, 5, 1.0),
    ([snap(week=9, ca=51.2), snap(week=4)], "regressed", True, 5, -1.0),
    ([snap(season=1, week=20), snap(season=2, week=4)], "steady", True, None, 0.0),
])
def test_comparison_requires_distinct_dated_endpoints(points, status, available, elapsed, delta):
    result = server._profile_development_comparison(points)
    assert result["status"] == status
    assert result["comparison_available"] is available
    assert result["elapsed_weeks"] == elapsed
    assert result["overall_delta"] == delta
    assert result["tracked_points"] == len(points)
    if points:
        dates = sorted((point.season, point.week) for point in points)
        assert (result["start"]["season"], result["start"]["week"]) == dates[0]
        assert (result["end"]["season"], result["end"]["week"]) == dates[-1]


def test_current_season_skills_do_not_borrow_prior_season_or_missing_baselines():
    gs = SimpleNamespace(season=2, dev_history={"p": [
        snap(season=1, attributes={"aim_precision": 40}),
        snap(week=0),  # Old save has CA but no skill baseline.
        snap(week=4, attributes={"aim_precision": 60}),
    ]})
    result = server._profile_season_growth(gs, "p")
    assert result["comparison"]["status"] == "first_observation"
    assert result["changes"] == []
    assert not result["attribute_comparison_available"]
    gs.dev_history["p"].append(snap(week=9, attributes={"aim_precision": 61, "game_sense": 50}))
    result = server._profile_season_growth(gs, "p")
    assert result["comparison"]["start"]["week"] == 4
    assert result["comparison"]["end"]["week"] == 9
    assert result["comparison"]["elapsed_weeks"] == 5
    assert result["changes"] == [{"key": "aim_precision", "delta": 1.0, "value": 61}]
    assert result["has_measurable_change"]
    assert all(point["season"] == 2 for point in result["series"])
    gs.season = 3
    result = server._profile_season_growth(gs, "p")
    assert result["series"] == []
    assert result["comparison"]["status"] == "no_observations"


def test_real_flat_skills_and_disjoint_keys_have_different_availability():
    gs = SimpleNamespace(season=2, dev_history={"p": [
        snap(week=4, attributes={"aim_precision": 60}),
        snap(week=5, attributes={"aim_precision": 60}),
    ]})
    flat = server._profile_season_growth(gs, "p")
    assert flat["attribute_comparison_available"]
    assert not flat["has_measurable_change"]
    assert flat["changes"][0]["delta"] == 0
    gs.dev_history["p"][-1] = snap(week=5, attributes={"game_sense": 60})
    disjoint = server._profile_season_growth(gs, "p")
    assert not disjoint["attribute_comparison_available"]
    assert disjoint["changes"] == []


def test_owned_weekly_sources_are_authoritative_private_and_separate_from_stats(monkeypatch):
    p = Player(id="p", handle="Nightsurge", role=Role.DUELIST,
               playstyle=Playstyle.ENTRY, attributes={"aim_precision": 60})
    p.development_progress.latest = DevelopmentWeek(
        season=2, week=4, focus="tactical", intensity="light", maps=0,
        practice_gains={"aim_precision": 0.31}, scrim_gains={"aim_precision": 0.01},
        badge_tracking=True, badge_gains={"aim_precision": -0.5},
        badge_events=[
            BadgeDevelopmentEvent(badge="clutch_master", action="earned", skills={"aim_precision": 0.5}),
            BadgeDevelopmentEvent(badge="choker", action="lost", skills={"aim_precision": -1.0}),
        ],
        factors=["Stored practice feedback"], career_event="Stored career event",
    )
    gs = SimpleNamespace(season=2, players={"p": p}, dev_history={"p": [snap()]},
                         stat_history={"p": []})
    monkeypatch.setattr(server.staff_mod, "analytics_tier", lambda _: 0)
    own = server._profile_charts(gs, "p", True)
    assert own["performance"] is None
    assert own["development"] == [snap().model_dump()]
    assert own["development_latest_week"] == report_view(p)
    assert own["development_latest_week"]["maps"] == 0
    assert own["development_latest_week"]["sources"]["practice_gains"]["overall_gain"] == 0.31
    assert own["development_latest_week"]["sources"]["badge_gains"] == {
        "overall_gain": -0.5, "skills": {"aim_precision": -0.5},
    }
    assert own["development_latest_week"]["badge_tracking"] is True
    assert own["development_latest_week"]["badge_events"] == [
        {"badge": "clutch_master", "action": "earned", "name": "Clutch Master",
         "skills": {"aim_precision": 0.5}, "overall_gain": 0.5},
        {"badge": "choker", "action": "lost", "name": "Choker",
         "skills": {"aim_precision": -1.0}, "overall_gain": -1.0},
    ]
    rival = server._profile_charts(gs, "p", False)
    for key in ("development", "development_comparison", "season_growth", "development_latest_week"):
        assert rival[key] is None
    p.development_progress.latest = None
    assert server._profile_charts(gs, "p", True)["development_latest_week"] is None
    monkeypatch.setattr(server.staff_mod, "analytics_tier", lambda _: 2)
    assert server._profile_charts(gs, "p", False)["performance"] == []


@pytest.mark.parametrize("tracked", [False, True])
def test_profile_preserves_legacy_badge_attribution_vs_tracked_zero(tracked, monkeypatch):
    p = Player(id="p", handle="Nightsurge", role=Role.DUELIST,
               playstyle=Playstyle.ENTRY, attributes={"aim_precision": 60})
    p.development_progress.latest = DevelopmentWeek(season=2, week=4, badge_tracking=tracked)
    gs = SimpleNamespace(season=2, players={"p": p}, dev_history={}, stat_history={})
    monkeypatch.setattr(server.staff_mod, "analytics_tier", lambda _: 0)
    latest = server._profile_charts(gs, "p", True)["development_latest_week"]
    assert latest["badge_tracking"] is tracked
    assert latest["badge_events"] == []
    assert latest["sources"]["badge_gains"] == {"overall_gain": 0.0, "skills": {}}
