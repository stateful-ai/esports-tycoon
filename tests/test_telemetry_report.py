"""Usage-report regressions over saved decisions, without season simulation."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from esports_sim.manager.state import ActionRecord, GameState


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "telemetry_report.py"
count_dials = runpy.run_path(str(SCRIPT))["game_plan_dial_count"]
DIALS = ("aggression", "pace", "util_discipline", "eco_greed", "map_control")


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, 0),
        ({dial: "None" for dial in DIALS}, 0),
        ({"pace": "", "aggression": "None", "site_focus": "a"}, 0),
        ({"pace": "50.0"}, 1),
        ({"pace": "0", "aggression": "100", "util_discipline": "70.0"}, 3),
        ({"n_dials": "2"}, 2),
        ({"n_dials": "0"}, 0),
        ({"n_dials": "5"}, 5),
        ({"pace": "50", "n_dials": "0"}, 1),
        ({"pace": "None", "n_dials": "3"}, 0),
        ({"pace": "", "n_dials": "1"}, 0),
        ({"pace": "junk", "aggression": "nan", "eco_greed": "inf"}, 0),
        ({"pace": "-1", "aggression": "101", "map_control": "50"}, 1),
    ],
)
def test_game_plan_dial_count(params, expected):
    assert count_dials(params) == expected


@pytest.mark.parametrize("value", ["None", "", "junk", "-1", "6", "1.5", "inf"])
def test_malformed_legacy_summary_is_not_an_override(value):
    assert count_dials({"n_dials": value}) == 0


def test_cli_reports_mixed_web_and_mcp_plans(tmp_path):
    plans = [
        ("agent", {dial: "None" for dial in DIALS}),
        ("agent", {"pace": "40.0", "util_discipline": "70.0"}),
        ("agent", {"aggression": "50.0", "n_dials": "0"}),
        ("web", {"n_dials": "2"}),
        ("web", {"n_dials": "0", "site_focus": "a"}),
        ("web", {"n_dials": "malformed"}),
    ]
    gs = GameState(seed=1, user_team_id="test", action_log=[
        ActionRecord(
            season=1, week=1, phase="regular", manager_id="mgr_test",
            team_id="test", kind="set_game_plan", source=source, params=params,
        )
        for source, params in plans
    ])
    gs.save(tmp_path / "campaign_test.json")
    before = (tmp_path / "campaign_test.json").read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True, text=True, check=True,
    )
    assert "telemetry report: 1 saves, 6 recorded actions" in result.stdout
    assert "game plans: 6 set; 3 carried dial overrides (50%)" in result.stdout
    assert "sources: agent 3, web 3" in result.stdout
    assert result.stdout.isascii()
    assert (tmp_path / "campaign_test.json").read_bytes() == before
