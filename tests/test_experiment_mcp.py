"""Design, background execution, and stdio coverage for Experiment Lab MCP."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import time

import pytest

from esports_sim.registry import experiment_mcp_ops as ops


def test_catalog_and_equal_talent_preview_are_discoverable() -> None:
    catalog = ops.get_experiment_catalog()
    core = {item["factor"] for item in catalog["suites"]["core"]["factors"]}
    mechanisms = {
        item["factor"] for item in catalog["suites"]["mechanisms"]["factors"]
    }
    assert {
        "symmetry_baseline", "weak_overall", "prep_edge", "counter_edge",
        "skill_aim_precision",
    } <= core
    assert {"shared_language", "role_comfort", "role_assignment", "micro_bundle"} <= mechanisms
    language = next(
        item for item in catalog["suites"]["mechanisms"]["factors"]
        if item["factor"] == "shared_language"
    )
    assert language["baseline_level"] == "50"
    assert set(language["levels"]) == {"no_common", "20", "50", "75", "100"}
    assert "rounds_won_added" in catalog["outcomes"]
    roster_fit = catalog["series_suites"]["roster_fit"]
    assert set(roster_fit["profiles"]) == {
        "balanced", "fraggers", "tacticians", "mixed"
    }
    assert set(roster_fit["dials"]) == {
        "aggression", "pace", "util_discipline", "map_control"
    }
    pack_tactics = catalog["series_suites"]["roster_pack_tactics"]
    assert pack_tactics["default_pack"] == "vct-2021"
    assert "team_sentinels" in pack_tactics["default_teams"]

    preview = ops.preview_experiment(
        "core",
        factors=["prep_edge", "counter_edge"],
        maps=["haven"],
        seed_blocks=[70000, 80000],
        seeds_per_cell=5,
        weak_quality=75,
        strong_quality=75,
        context="equal_75v75",
    )
    assert preview["versions"] == 6
    assert preview["cells"] == 24
    assert preview["matches"] == 120
    assert preview["baselines"] == {"counter_edge": "0", "prep_edge": "0"}
    assert {row["context"] for row in preview["design"]} == {"equal_75v75"}

    series_preview = ops.preview_roster_fit_series(
        series=10,
        profiles=["fraggers", "tacticians"],
        dials=["aggression"],
        poles=[0, 100],
    )
    assert series_preview["simulated_maps"] == 300
    assert series_preview["map_dataset_rows"] == 400
    assert series_preview["series_rows"] == 80

    pack_preview = ops.preview_roster_pack_tactics_series(
        series=10,
        teams=["team_sentinels", "team_gambit_esports"],
        dials=["pace"],
        poles=[0, 100],
    )
    assert pack_preview["simulated_maps"] == 300
    assert pack_preview["map_dataset_rows"] == 200
    assert pack_preview["series_rows"] == 80


def test_background_smoke_run_validates_and_summarizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESPORTS_EXPERIMENT_RUNS_DIR", str(tmp_path))
    launched = ops.start_experiment(
        "smoke",
        "core",
        factors=["prep_edge"],
        levels={"prep_edge": [0]},
        maps=["haven"],
        seed_blocks=[91000],
        seeds_per_cell=1,
        workers=1,
        weak_quality=75,
        strong_quality=75,
        context="equal_75v75_smoke",
        limit_cells=1,
    )
    manifest = tmp_path / launched["run_id"] / "manifest.json"
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if manifest.is_file() and json.loads(manifest.read_text(encoding="utf-8")).get("status") != "running":
            break
        time.sleep(0.1)
    assert manifest.is_file()
    assert ops.validate_experiment(launched["run_id"])["valid"] is True
    summary = ops.summarize_experiment(launched["run_id"])
    assert summary["summaries"][0]["matches"] == 1


def test_summary_reports_paired_rounds_added_for_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESPORTS_EXPERIMENT_RUNS_DIR", str(tmp_path))
    run_id = "language-summary"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    rows = [
        ("50", "haven", "0", "101", 10, 13, 0),
        ("50", "haven", "1", "102", 9, 13, 0),
        ("100", "haven", "0", "101", 12, 11, 1),
        ("100", "haven", "1", "102", 10, 12, 0),
    ]
    with (run_dir / "matches.csv").open("w", newline="", encoding="utf-8") as handle:
        handle.write(
            "context,factor,level,map_id,identity_swap,seed,weak_score,strong_score,"
            "weak_win,weak_round_margin\n"
        )
        for level, map_id, identity_swap, seed, weak, strong, win in rows:
            handle.write(
                f"equal_75v75,shared_language,{level},{map_id},{identity_swap},{seed},"
                f"{weak},{strong},{win},{weak - strong}\n"
            )

    summary = ops.summarize_experiment(run_id)
    effect = summary["baseline_effects"][0]
    assert effect["baseline_level"] == "50"
    assert effect["treatment_level"] == "100"
    assert effect["paired_matches"] == 2
    assert effect["rounds_won_added"] == pytest.approx(1.5)
    assert effect["opponent_rounds_denied"] == pytest.approx(1.5)
    assert effect["round_margin_improvement"] == pytest.approx(3.0)
    assert effect["margin_reconciliation_error"] == pytest.approx(0.0)


def test_stdio_mcp_exposes_experiment_tools(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    env["ESPORTS_EXPERIMENT_RUNS_DIR"] = str(tmp_path)

    async def scenario() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "esports_sim.mcp.experiment_server"],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                assert {
                    "get_experiment_catalog", "preview_experiment", "start_experiment",
                    "list_experiments", "get_experiment", "validate_experiment",
                    "summarize_experiment",
                    "preview_roster_fit_series", "start_roster_fit_series",
                    "validate_roster_fit_series", "summarize_roster_fit_series",
                    "preview_roster_pack_tactics_series",
                    "start_roster_pack_tactics_series",
                    "validate_roster_pack_tactics_series",
                    "summarize_roster_pack_tactics_series",
                } <= names
                result = await session.call_tool(
                    "preview_experiment",
                    arguments={
                        "suite": "mechanisms",
                        "factors": ["shared_language"],
                        "maps": ["haven"],
                        "seed_blocks": [92000],
                        "seeds_per_cell": 2,
                        "weak_quality": 75,
                        "strong_quality": 75,
                        "context": "equal_75v75_protocol",
                    },
                )
                assert result.isError is not True
                payload = json.loads(result.content[0].text)
                assert payload["matches"] == 20

    asyncio.run(scenario())
