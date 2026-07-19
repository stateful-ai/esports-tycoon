"""Durable operations for the seeded match-experiment MCP server."""

from __future__ import annotations

import csv
from dataclasses import asdict, replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Literal

if str(Path(__file__).resolve().parents[3]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.causal_match_experiment import experiment_variants
from scripts.causal_match_supplement import supplement_variants
from scripts.roster_fit_series_experiment import (
    DIALS as ROSTER_FIT_DIALS,
    FORMATS as ROSTER_FIT_FORMATS,
    POLES as ROSTER_FIT_POLES,
    PROFILES as ROSTER_FIT_PROFILES,
)
from scripts.roster_pack_tactics_experiment import (
    DEFAULT_TEAMS as PACK_TACTICS_DEFAULT_TEAMS,
    DIALS as PACK_TACTICS_DIALS,
    FORMATS as PACK_TACTICS_FORMATS,
    POLES as PACK_TACTICS_POLES,
)
from esports_sim.registry.rosters import load_roster_pack


Suite = Literal["core", "mechanisms"]
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNS_DIR = REPO_ROOT / "runs" / "mcp-experiments"
ALL_MAPS = ("ascent", "bind", "haven", "lotus", "split")
SCRIPTS = {
    "core": REPO_ROOT / "scripts" / "causal_match_experiment.py",
    "mechanisms": REPO_ROOT / "scripts" / "causal_match_supplement.py",
}
ROSTER_FIT_SCRIPT = REPO_ROOT / "scripts" / "roster_fit_series_experiment.py"
PACK_TACTICS_SCRIPT = REPO_ROOT / "scripts" / "roster_pack_tactics_experiment.py"
_ACTIVE_PROCESSES: dict[int, subprocess.Popen[str]] = {}

# Decision-facing neutral/current comparators. These are exposed through the
# catalog and used by summarize_experiment unless a caller supplies overrides.
DEFAULT_BASELINES: dict[str, str] = {
    "symmetry_baseline": "identical",
    "weak_overall": "65",
    "agent_mastery": "75",
    "agent_selection": "auto",
    "chemistry_complex_system": "65",
    "chemistry_neutral": "65",
    "coach_quality": "50",
    "confidence": "50",
    "counter_edge": "0",
    "focus_target": "none",
    "form": "50",
    "halftime_talk": "none",
    "igl_experience": "100",
    "map_mastery": "75",
    "mental_bundle": "65",
    "micro_bundle": "65",
    "morale": "50",
    "prep_edge": "0",
    "role_assignment": "rotated",
    "role_comfort": "100",
    "roster_shape": "balanced",
    "shared_language": "50",
    "stamina": "100",
    "tactical_bundle": "65",
    "touchline_shout": "none",
    "tactic_aggression": "50",
    "tactic_eco_greed": "50",
    "tactic_map_control": "50",
    "tactic_pace": "50",
    "tactic_util_discipline": "50",
}
DEFAULT_BASELINES.update({
    factor: "65"
    for factor in (
        "skill_aim_precision", "skill_aim_reactivity", "skill_clutch_factor",
        "skill_comms_quality", "skill_composure", "skill_game_sense",
        "skill_movement", "skill_positioning", "skill_tilt_resistance",
        "skill_utility_usage",
    )
})
FACTOR_DESCRIPTIONS = {
    "symmetry_baseline": (
        "Mirrors every mechanically relevant player and team field across both sides. "
        "Use equal weak_quality and strong_quality to measure the 50% symmetry control."
    ),
    "shared_language": (
        "Weak-team shared fluency. Numeric levels set every weak-team player to "
        "that fluency in one common language; no_common gives each player a unique language."
    ),
}
OUTCOME_DEFINITIONS = {
    "rounds_won_added": "mean paired treatment weak_score minus baseline weak_score",
    "opponent_rounds_denied": "mean paired baseline strong_score minus treatment strong_score",
    "round_margin_improvement": "rounds_won_added plus opponent_rounds_denied",
    "weak_win_effect_pp": "paired treatment minus baseline weak win rate, in percentage points",
}


class ExperimentMcpError(ValueError):
    """A user-correctable experiment request or artifact error."""


def _runs_dir() -> Path:
    return Path(os.environ.get("ESPORTS_EXPERIMENT_RUNS_DIR", DEFAULT_RUNS_DIR))


def _script_command(
    suite: Suite,
    *,
    factors: list[str] | None = None,
    levels: dict[str, list[str | float]] | None = None,
    weak_quality: float | None = None,
    strong_quality: float | None = None,
    context: str = "",
) -> list[str]:
    command = [sys.executable, str(SCRIPTS[suite])]
    if factors:
        command += ["--factors", ",".join(factors)]
    if levels:
        command += ["--levels-json", json.dumps(levels, separators=(",", ":"))]
    if weak_quality is not None:
        command += ["--weak-quality", str(weak_quality)]
    if strong_quality is not None:
        command += ["--strong-quality", str(strong_quality)]
    if context:
        command += ["--context", context]
    return command


def _describe(
    suite: Suite,
    *,
    factors: list[str] | None = None,
    levels: dict[str, list[str | float]] | None = None,
    weak_quality: float | None = None,
    strong_quality: float | None = None,
    context: str = "",
) -> dict[str, Any]:
    variants = experiment_variants() if suite == "core" else supplement_variants()
    selected_factors = set(factors or [])
    if selected_factors:
        unknown = selected_factors - {variant.factor for variant in variants}
        if unknown:
            raise ExperimentMcpError(f"unknown factors: {sorted(unknown)}")
        variants = [variant for variant in variants if variant.factor in selected_factors]
    levels = levels or {}
    rebuilt = []
    for factor in dict.fromkeys(variant.factor for variant in variants):
        templates = [variant for variant in variants if variant.factor == factor]
        if factor not in levels:
            rebuilt.extend(templates)
            continue
        values = levels[factor]
        if not values:
            raise ExperimentMcpError(f"levels for {factor} must be non-empty")
        is_numeric = all(template.level_numeric is not None for template in templates)
        if is_numeric:
            rebuilt.extend(
                replace(templates[0], level=f"{float(value):g}", level_numeric=float(value))
                for value in values
            )
        else:
            by_level = {template.level: template for template in templates}
            unknown_levels = {str(value) for value in values} - set(by_level)
            if unknown_levels:
                raise ExperimentMcpError(f"unknown levels for {factor}: {sorted(unknown_levels)}")
            rebuilt.extend(by_level[str(value)] for value in values)
    chosen_context = context or (
        f"normalized_{weak_quality:g}v{strong_quality:g}"
        if weak_quality is not None and strong_quality is not None else ""
    )
    selected = [
        replace(
            variant,
            weak_quality=weak_quality if weak_quality is not None else variant.weak_quality,
            strong_quality=strong_quality if strong_quality is not None else variant.strong_quality,
            context=chosen_context or variant.context,
        )
        for variant in rebuilt
    ]
    unique = {
        (variant.context, variant.factor, variant.level): variant for variant in selected
    }
    return {"suite": suite, "design": [asdict(variant) for variant in unique.values()]}


def get_experiment_catalog() -> dict[str, Any]:
    """Return every registered intervention and its standard levels."""
    suites: dict[str, Any] = {}
    for suite in ("core", "mechanisms"):
        design = _describe(suite)["design"]
        factors: dict[str, Any] = {}
        for variant in design:
            item = factors.setdefault(
                variant["factor"],
                {
                    "factor": variant["factor"],
                    "kind": "numeric" if variant["level_numeric"] is not None else "categorical",
                    "levels": [],
                    "contexts": [],
                    "baseline_level": DEFAULT_BASELINES.get(variant["factor"]),
                    "description": FACTOR_DESCRIPTIONS.get(variant["factor"], ""),
                },
            )
            if variant["level"] not in item["levels"]:
                item["levels"].append(variant["level"])
            if variant["context"] not in item["contexts"]:
                item["contexts"].append(variant["context"])
        suites[suite] = {"factors": list(factors.values())}
    return {
        "design": "paired one-factor-at-a-time",
        "pairing_keys": ["map_id", "identity_swap", "seed"],
        "maps": list(ALL_MAPS),
        "outcomes": OUTCOME_DEFINITIONS,
        "suites": suites,
        "series_suites": {
            "roster_fit": {
                "design": (
                    "same-roster paired series: neutral control versus one "
                    "designated-team tactics-dial treatment"
                ),
                "profiles": list(ROSTER_FIT_PROFILES),
                "dials": list(ROSTER_FIT_DIALS),
                "poles": list(ROSTER_FIT_POLES),
                "formats": list(ROSTER_FIT_FORMATS),
                "baseline": "all tactics dials at 50",
                "outcomes": {
                    "series_win_lift_pp": "paired treatment minus control series win rate",
                    "rounds_won_added_per_map": "paired treatment minus control rounds won",
                    "fit_interaction": "aligned-roster lift minus mismatched-roster lift",
                },
            },
            "roster_pack_tactics": {
                "design": (
                    "mirror an authored roster-pack team, then compare neutral "
                    "control against one designated-team dial treatment"
                ),
                "default_pack": "vct-2021",
                "default_teams": list(PACK_TACTICS_DEFAULT_TEAMS),
                "dials": list(PACK_TACTICS_DIALS),
                "poles": list(PACK_TACTICS_POLES),
                "formats": list(PACK_TACTICS_FORMATS),
                "baseline": "both copies of the authored roster use tactics 50",
                "outcomes": {
                    "series_win_lift_pp": "paired treatment minus control series win rate",
                    "rounds_won_added": "paired treatment minus control rounds won",
                    "round_margin_lift": "paired treatment minus control round margin",
                },
            }
        },
        "guidance": (
            "Use core for overall, individual skills, prep/counter-strat, mastery, "
            "state, tactics, chemistry, and coaching. Use mechanisms for language, "
            "role comfort/assignment, IGL experience, and equal-sized skill bundles."
        ),
    }


def preview_experiment(
    suite: Suite,
    factors: list[str] | None = None,
    levels: dict[str, list[str | float]] | None = None,
    maps: list[str] | None = None,
    seed_blocks: list[int] | None = None,
    seeds_per_cell: int = 30,
    weak_quality: float | None = None,
    strong_quality: float | None = None,
    context: str = "",
    limit_cells: int = 0,
) -> dict[str, Any]:
    """Validate a design and estimate its cells, matches, and output shape."""
    maps = maps or list(ALL_MAPS)
    unknown_maps = set(maps) - set(ALL_MAPS)
    if unknown_maps:
        raise ExperimentMcpError(f"unknown maps: {sorted(unknown_maps)}")
    if seeds_per_cell < 1:
        raise ExperimentMcpError("seeds_per_cell must be positive")
    seed_blocks = seed_blocks or ([0, 10000, 20000] if suite == "core" else [30000, 40000, 50000])
    if len(seed_blocks) != len(set(seed_blocks)):
        raise ExperimentMcpError("seed_blocks must be unique")
    described = _describe(
        suite,
        factors=factors,
        levels=levels,
        weak_quality=weak_quality,
        strong_quality=strong_quality,
        context=context,
    )
    versions = len(described["design"])
    cells = versions * len(maps) * 2 * len(seed_blocks)
    if limit_cells:
        cells = min(cells, limit_cells)
    selected_factors = {row["factor"] for row in described["design"]}
    return {
        "valid": True,
        "suite": suite,
        "versions": versions,
        "cells": cells,
        "matches": cells * seeds_per_cell,
        "maps": maps,
        "identity_swaps": [0, 1],
        "seed_blocks": seed_blocks,
        "seeds_per_cell": seeds_per_cell,
        "baselines": {
            factor: DEFAULT_BASELINES[factor]
            for factor in sorted(selected_factors)
            if factor in DEFAULT_BASELINES
        },
        "design": described["design"],
    }


def start_experiment(
    name: str,
    suite: Suite,
    factors: list[str] | None = None,
    levels: dict[str, list[str | float]] | None = None,
    maps: list[str] | None = None,
    seed_blocks: list[int] | None = None,
    seeds_per_cell: int = 30,
    workers: int = 14,
    weak_quality: float | None = None,
    strong_quality: float | None = None,
    context: str = "",
    minutes: float = 0.0,
    limit_cells: int = 0,
) -> dict[str, Any]:
    """Launch a validated experiment in the background and return its run id."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ExperimentMcpError("name must be 1-64 letters, numbers, dashes, or underscores")
    if workers < 1 or workers > 64:
        raise ExperimentMcpError("workers must be between 1 and 64")
    preview = preview_experiment(
        suite, factors, levels, maps, seed_blocks, seeds_per_cell,
        weak_quality, strong_quality, context, limit_cells,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{name}"
    run_dir = _runs_dir() / run_id
    if run_dir.exists():
        raise ExperimentMcpError(f"run already exists: {run_id}")
    run_dir.mkdir(parents=True)
    command = _script_command(
        suite,
        factors=factors,
        levels=levels,
        weak_quality=weak_quality,
        strong_quality=strong_quality,
        context=context,
    )
    command += [
        "--out", str(run_dir),
        "--workers", str(workers),
        "--seeds-per-cell", str(seeds_per_cell),
        "--seed-blocks", ",".join(str(value) for value in preview["seed_blocks"]),
        "--maps", *preview["maps"],
    ]
    if limit_cells:
        command += ["--limit-cells", str(limit_cells)]
    if suite == "core" and minutes:
        command += ["--minutes", str(minutes)]
    request = {
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "request": {
            "name": name, "suite": suite, "factors": factors, "levels": levels,
            "weak_quality": weak_quality, "strong_quality": strong_quality,
            "context": context, "workers": workers, "minutes": minutes,
        },
        "preview": preview,
        "command": command,
    }
    (run_dir / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    log_handle = (run_dir / "run.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )
    _ACTIVE_PROCESSES[process.pid] = process
    log_handle.close()
    job = {"run_id": run_id, "pid": process.pid, "status": "launched"}
    (run_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    return {**job, "output_dir": str(run_dir), "preview": preview}


def preview_roster_fit_series(
    series: int = 100,
    profiles: list[str] | None = None,
    dials: list[str] | None = None,
    poles: list[float] | None = None,
    quality: float = 75.0,
    base_seed: int = 240000,
) -> dict[str, Any]:
    """Validate and size the paired roster-composition by game-plan design."""
    if series < 1:
        raise ExperimentMcpError("series must be positive")
    profiles = profiles or list(ROSTER_FIT_PROFILES)
    dials = dials or list(ROSTER_FIT_DIALS)
    poles = poles or list(ROSTER_FIT_POLES)
    unknown_profiles = set(profiles) - set(ROSTER_FIT_PROFILES)
    unknown_dials = set(dials) - set(ROSTER_FIT_DIALS)
    if unknown_profiles:
        raise ExperimentMcpError(f"unknown roster profiles: {sorted(unknown_profiles)}")
    if unknown_dials:
        raise ExperimentMcpError(f"unknown tactics dials: {sorted(unknown_dials)}")
    if len(profiles) != len(set(profiles)):
        raise ExperimentMcpError("profiles must be unique")
    if len(dials) != len(set(dials)):
        raise ExperimentMcpError("dials must be unique")
    if len(poles) != len(set(poles)):
        raise ExperimentMcpError("poles must be unique")
    if not poles or not all(0.0 <= value <= 100.0 and value != 50.0 for value in poles):
        raise ExperimentMcpError("poles must be between 0 and 100 and cannot be neutral 50")
    if not 25.0 <= quality <= 85.0:
        raise ExperimentMcpError("quality must be between 25 and 85")
    tasks = series * len(profiles) * len(dials)
    return {
        "valid": True,
        "suite": "roster_fit_series",
        "series_per_cell": series,
        "profiles": profiles,
        "dials": dials,
        "poles": poles,
        "formats": list(ROSTER_FIT_FORMATS),
        "quality": quality,
        "base_seed": base_seed,
        "task_cells": tasks,
        "simulated_maps": tasks * len(ALL_MAPS) * (1 + len(poles)),
        "map_dataset_rows": tasks * len(poles) * len(ALL_MAPS) * 2,
        "series_rows": tasks * len(poles) * len(ROSTER_FIT_FORMATS),
        "baseline": "both identical-composition teams neutral at every tactics dial",
        "treatment": "change exactly one designated-team dial; everything else paired",
        "pairing_keys": ["dial", "roster_profile", "treatment_value", "series_index"],
    }


def start_roster_fit_series(
    name: str,
    series: int = 100,
    profiles: list[str] | None = None,
    dials: list[str] | None = None,
    poles: list[float] | None = None,
    quality: float = 75.0,
    base_seed: int = 240000,
    workers: int = 14,
) -> dict[str, Any]:
    """Launch the paired roster-fit series design asynchronously."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ExperimentMcpError("name must be 1-64 letters, numbers, dashes, or underscores")
    if workers < 1 or workers > 64:
        raise ExperimentMcpError("workers must be between 1 and 64")
    preview = preview_roster_fit_series(
        series, profiles, dials, poles, quality, base_seed
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{name}"
    run_dir = _runs_dir() / run_id
    if run_dir.exists():
        raise ExperimentMcpError(f"run already exists: {run_id}")
    run_dir.mkdir(parents=True)
    command = [
        sys.executable,
        str(ROSTER_FIT_SCRIPT),
        "--out",
        str(run_dir),
        "--series",
        str(series),
        "--quality",
        str(quality),
        "--base-seed",
        str(base_seed),
        "--workers",
        str(workers),
        "--profiles",
        *preview["profiles"],
        "--dials",
        *preview["dials"],
        "--poles",
        *(str(value) for value in preview["poles"]),
    ]
    request = {
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "request": {
            "name": name,
            "suite": "roster_fit_series",
            "series": series,
            "profiles": profiles,
            "dials": dials,
            "poles": poles,
            "quality": quality,
            "base_seed": base_seed,
            "workers": workers,
        },
        "preview": preview,
        "command": command,
    }
    (run_dir / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    log_handle = (run_dir / "run.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )
    _ACTIVE_PROCESSES[process.pid] = process
    log_handle.close()
    job = {"run_id": run_id, "pid": process.pid, "status": "launched"}
    (run_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    return {**job, "output_dir": str(run_dir), "preview": preview}


def preview_roster_pack_tactics_series(
    pack_id: str = "vct-2021",
    series: int = 30,
    teams: list[str] | None = None,
    dials: list[str] | None = None,
    poles: list[float] | None = None,
    seed_base: int = 910000,
) -> dict[str, Any]:
    """Validate and size a real-roster mirrored tactics experiment."""
    if series < 1:
        raise ExperimentMcpError("series must be positive")
    try:
        pack = load_roster_pack(pack_id)
    except (FileNotFoundError, ValueError) as exc:
        raise ExperimentMcpError(str(exc)) from exc
    tier_one = sorted(team.id for team in pack.teams.values() if team.tier == 1)
    if teams == ["all"]:
        teams = tier_one
    elif teams is None:
        teams = (
            list(PACK_TACTICS_DEFAULT_TEAMS)
            if pack_id == "vct-2021"
            else tier_one[: min(6, len(tier_one))]
        )
    dials = dials or list(PACK_TACTICS_DIALS)
    poles = poles or list(PACK_TACTICS_POLES)
    unknown_teams = set(teams) - set(tier_one)
    unknown_dials = set(dials) - set(PACK_TACTICS_DIALS)
    if unknown_teams:
        raise ExperimentMcpError(f"unknown tier-one pack teams: {sorted(unknown_teams)}")
    if unknown_dials:
        raise ExperimentMcpError(f"unknown tactics dials: {sorted(unknown_dials)}")
    if not teams or len(teams) != len(set(teams)):
        raise ExperimentMcpError("teams must be non-empty and unique")
    if not dials or len(dials) != len(set(dials)):
        raise ExperimentMcpError("dials must be non-empty and unique")
    if len(poles) != len(set(poles)) or not all(
        0.0 <= value <= 100.0 and value != 50.0 for value in poles
    ):
        raise ExperimentMcpError(
            "poles must be unique, between 0 and 100, and cannot be neutral 50"
        )
    tasks = series * len(teams)
    return {
        "valid": True,
        "suite": "roster_pack_tactics_series",
        "pack_id": pack_id,
        "series_per_cell": series,
        "teams": teams,
        "dials": dials,
        "poles": poles,
        "formats": list(PACK_TACTICS_FORMATS),
        "seed_base": seed_base,
        "task_cells": tasks,
        "simulated_maps": tasks * len(ALL_MAPS) * (1 + len(dials) * len(poles)),
        "map_dataset_rows": tasks * len(dials) * len(poles) * len(ALL_MAPS),
        "series_rows": tasks * len(dials) * len(poles) * len(PACK_TACTICS_FORMATS),
        "baseline": "mechanically mirrored authored roster; both teams neutral",
        "treatment": "change exactly one designated-team dial",
        "pairing_keys": ["source_team_id", "dial", "pole", "series_index"],
    }


def start_roster_pack_tactics_series(
    name: str,
    pack_id: str = "vct-2021",
    series: int = 30,
    teams: list[str] | None = None,
    dials: list[str] | None = None,
    poles: list[float] | None = None,
    seed_base: int = 910000,
    workers: int = 14,
) -> dict[str, Any]:
    """Launch a mirrored authored-roster tactics experiment asynchronously."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ExperimentMcpError("name must be 1-64 letters, numbers, dashes, or underscores")
    if workers < 1 or workers > 64:
        raise ExperimentMcpError("workers must be between 1 and 64")
    preview = preview_roster_pack_tactics_series(
        pack_id, series, teams, dials, poles, seed_base
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{name}"
    run_dir = _runs_dir() / run_id
    if run_dir.exists():
        raise ExperimentMcpError(f"run already exists: {run_id}")
    run_dir.mkdir(parents=True)
    command = [
        sys.executable, str(PACK_TACTICS_SCRIPT),
        "--output", str(run_dir),
        "--pack", preview["pack_id"],
        "--series", str(series),
        "--seed-base", str(seed_base),
        "--workers", str(workers),
        "--teams", *preview["teams"],
        "--dials", *preview["dials"],
        "--poles", *(str(value) for value in preview["poles"]),
    ]
    request = {
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "request": {
            "name": name, "suite": "roster_pack_tactics_series",
            "pack_id": pack_id, "series": series, "teams": teams,
            "dials": dials, "poles": poles, "seed_base": seed_base,
            "workers": workers,
        },
        "preview": preview,
        "command": command,
    }
    (run_dir / "request.json").write_text(
        json.dumps(request, indent=2), encoding="utf-8"
    )
    log_handle = (run_dir / "run.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _ACTIVE_PROCESSES[process.pid] = process
    log_handle.close()
    job = {"run_id": run_id, "pid": process.pid, "status": "launched"}
    (run_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    return {**job, "output_dir": str(run_dir), "preview": preview}


def get_experiment(run_id: str) -> dict[str, Any]:
    """Read the request, live manifest, and tail of one experiment log."""
    run_dir = _runs_dir() / run_id
    if not run_dir.is_dir():
        raise ExperimentMcpError(f"unknown run: {run_id}")
    result: dict[str, Any] = {"run_id": run_id, "output_dir": str(run_dir)}
    for name in ("request", "job", "manifest", "validation"):
        path = run_dir / f"{name}.json"
        if path.is_file():
            result[name] = json.loads(path.read_text(encoding="utf-8"))
    job = result.get("job", {})
    process = _ACTIVE_PROCESSES.get(job.get("pid"))
    if process is not None:
        returncode = process.poll()
        result["process"] = {
            "running": returncode is None,
            "returncode": returncode,
        }
        if returncode is not None:
            _ACTIVE_PROCESSES.pop(process.pid, None)
    log_path = run_dir / "run.log"
    if log_path.is_file():
        result["log_tail"] = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
    return result


def list_experiments() -> dict[str, Any]:
    """List experiment runs newest first with compact status metadata."""
    root = _runs_dir()
    if not root.is_dir():
        return {"runs": []}
    runs = []
    for path in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True):
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        runs.append({
            "run_id": path.name,
            "status": manifest.get("status", "launched"),
            "completed_matches": manifest.get(
                "completed_matches",
                manifest.get("completed_simulated_maps", manifest.get("simulated_maps", 0)),
            ),
            "planned_matches": manifest.get(
                "planned_matches",
                manifest.get("planned_simulated_maps", manifest.get("simulated_maps")),
            ),
        })
    return {"runs": runs}


def validate_experiment(run_id: str) -> dict[str, Any]:
    """Check completeness, duplicate pairing keys, and per-cell seed counts."""
    run_dir = _runs_dir() / run_id
    request_path = run_dir / "request.json"
    dataset_path = run_dir / "matches.csv"
    if not request_path.is_file() or not dataset_path.is_file():
        raise ExperimentMcpError("run does not yet have a request and matches.csv")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    expected_per_cell = int(request["preview"]["seeds_per_cell"])
    cells: dict[str, int] = {}
    keys: set[tuple[str, str, str, str, str]] = set()
    duplicates = 0
    rows = 0
    with dataset_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            cells[row["cell_id"]] = cells.get(row["cell_id"], 0) + 1
            key = (row["version_id"], row["map_id"], row["identity_swap"], row["seed_block"], row["seed"])
            duplicates += int(key in keys)
            keys.add(key)
    incomplete = {cell: count for cell, count in cells.items() if count != expected_per_cell}
    expected_rows = int(request["preview"]["matches"])
    validation = {
        "valid": not duplicates and not incomplete and rows == expected_rows,
        "rows": rows,
        "expected_rows": expected_rows,
        "cells": len(cells),
        "expected_cells": request["preview"]["cells"],
        "duplicate_pairing_keys": duplicates,
        "incomplete_cells": incomplete,
    }
    (run_dir / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    return validation


def validate_roster_fit_series(run_id: str) -> dict[str, Any]:
    """Validate series/map grains and the control-treatment pairing contract."""
    run_dir = _runs_dir() / run_id
    request_path = run_dir / "request.json"
    series_path = run_dir / "series.csv"
    maps_path = run_dir / "series_maps.csv"
    if not request_path.is_file() or not series_path.is_file() or not maps_path.is_file():
        raise ExperimentMcpError(
            "run does not yet have request.json, series.csv, and series_maps.csv"
        )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    preview = request["preview"]
    series_keys: set[tuple[str, str, str, str, str]] = set()
    duplicate_series = 0
    series_rows = 0
    with series_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            series_rows += 1
            key = (
                row["dial"],
                row["roster_profile"],
                row["treatment_value"],
                row["best_of"],
                row["series_index"],
            )
            duplicate_series += int(key in series_keys)
            series_keys.add(key)

    map_keys: set[tuple[str, str, str]] = set()
    map_pairs: dict[tuple[str, str], dict[str, tuple[str, str]]] = {}
    duplicate_maps = 0
    map_rows = 0
    with maps_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            map_rows += 1
            key = (row["comparison_id"], row["map_index"], row["arm"])
            duplicate_maps += int(key in map_keys)
            map_keys.add(key)
            pair_key = (row["comparison_id"], row["map_index"])
            map_pairs.setdefault(pair_key, {})[row["arm"]] = (
                row["map_id"],
                row["match_seed"],
            )
    incomplete_pairs = sum(
        1
        for arms in map_pairs.values()
        if set(arms) != {"control", "treatment"}
        or arms["control"] != arms["treatment"]
    )
    validation = {
        "valid": (
            series_rows == int(preview["series_rows"])
            and map_rows == int(preview["map_dataset_rows"])
            and duplicate_series == 0
            and duplicate_maps == 0
            and incomplete_pairs == 0
        ),
        "series_rows": series_rows,
        "expected_series_rows": preview["series_rows"],
        "map_rows": map_rows,
        "expected_map_rows": preview["map_dataset_rows"],
        "duplicate_series_keys": duplicate_series,
        "duplicate_map_keys": duplicate_maps,
        "incomplete_or_misaligned_map_pairs": incomplete_pairs,
    }
    (run_dir / "validation.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8"
    )
    return validation


def validate_roster_pack_tactics_series(run_id: str) -> dict[str, Any]:
    """Validate real-roster series/map grains and paired treatment rows."""
    run_dir = _runs_dir() / run_id
    request_path = run_dir / "request.json"
    series_path = run_dir / "series.csv"
    maps_path = run_dir / "maps.csv"
    if not request_path.is_file() or not series_path.is_file() or not maps_path.is_file():
        raise ExperimentMcpError(
            "run does not yet have request.json, series.csv, and maps.csv"
        )
    preview = json.loads(request_path.read_text(encoding="utf-8"))["preview"]
    series_keys: set[tuple[str, str, str, str, str]] = set()
    map_keys: set[tuple[str, str]] = set()
    duplicate_series = duplicate_maps = series_rows = map_rows = 0
    with series_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            series_rows += 1
            key = (
                row["source_team_id"], row["dial"], row["pole"],
                row["best_of"], row["series_index"],
            )
            duplicate_series += int(key in series_keys)
            series_keys.add(key)
    with maps_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            map_rows += 1
            key = (row["comparison_id"], row["map_index"])
            duplicate_maps += int(key in map_keys)
            map_keys.add(key)
    validation = {
        "valid": (
            series_rows == int(preview["series_rows"])
            and map_rows == int(preview["map_dataset_rows"])
            and duplicate_series == 0
            and duplicate_maps == 0
        ),
        "series_rows": series_rows,
        "expected_series_rows": preview["series_rows"],
        "map_rows": map_rows,
        "expected_map_rows": preview["map_dataset_rows"],
        "duplicate_series_keys": duplicate_series,
        "duplicate_map_keys": duplicate_maps,
    }
    (run_dir / "validation.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8"
    )
    return validation


def summarize_roster_fit_series(run_id: str) -> dict[str, Any]:
    """Read the paired effect and aligned-versus-mismatched interaction summary."""
    path = _runs_dir() / run_id / "summary.json"
    if not path.is_file():
        raise ExperimentMcpError(f"run has no summary.json: {run_id}")
    return {"run_id": run_id, **json.loads(path.read_text(encoding="utf-8"))}


def summarize_roster_pack_tactics_series(run_id: str) -> dict[str, Any]:
    """Return per-team causal effects and authored roster features."""
    run_dir = _runs_dir() / run_id
    summary_path = run_dir / "summary.csv"
    feature_path = run_dir / "team_features.json"
    if not summary_path.is_file() or not feature_path.is_file():
        raise ExperimentMcpError(
            f"run has no summary.csv and team_features.json: {run_id}"
        )
    with summary_path.open(newline="", encoding="utf-8") as handle:
        effects = list(csv.DictReader(handle))
    return {
        "run_id": run_id,
        "effects": effects,
        "team_features": json.loads(feature_path.read_text(encoding="utf-8")),
    }


def _level_text(value: str | float) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):g}"
    return str(value)


def summarize_experiment(
    run_id: str,
    baselines: dict[str, str | float] | None = None,
) -> dict[str, Any]:
    """Return level outcomes and paired rounds won above explicit baselines."""
    dataset_path = _runs_dir() / run_id / "matches.csv"
    if not dataset_path.is_file():
        raise ExperimentMcpError(f"run has no matches.csv: {run_id}")
    groups: dict[tuple[str, str, str], dict[str, float]] = {}
    paired: dict[tuple[str, str, str], dict[tuple[str, str, str], dict[str, float]]] = {}
    with dataset_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["context"], row["factor"], row["level"])
            group = groups.setdefault(
                key,
                {"matches": 0, "wins": 0, "margin": 0, "weak_score": 0, "strong_score": 0},
            )
            group["matches"] += 1
            group["wins"] += int(row["weak_win"])
            group["margin"] += float(row["weak_round_margin"])
            group["weak_score"] += float(row["weak_score"])
            group["strong_score"] += float(row["strong_score"])
            pair_key = (row["map_id"], row["identity_swap"], row["seed"])
            paired.setdefault(key, {})[pair_key] = {
                "weak_score": float(row["weak_score"]),
                "strong_score": float(row["strong_score"]),
                "weak_round_margin": float(row["weak_round_margin"]),
                "weak_win": float(row["weak_win"]),
            }
    summaries = []
    for (context, factor, level), values in sorted(groups.items()):
        n = values["matches"]
        summaries.append({
            "context": context, "factor": factor, "level": level,
            "matches": int(n), "weak_win_rate": values["wins"] / n,
            "mean_weak_round_margin": values["margin"] / n,
            "mean_weak_rounds_won": values["weak_score"] / n,
            "mean_strong_rounds_won": values["strong_score"] / n,
        })
    spans = []
    factor_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in summaries:
        factor_groups.setdefault((row["context"], row["factor"]), []).append(row)
    for (context, factor), rows in sorted(factor_groups.items()):
        wins = [row["weak_win_rate"] for row in rows]
        margins = [row["mean_weak_round_margin"] for row in rows]
        spans.append({
            "context": context, "factor": factor,
            "win_rate_span": max(wins) - min(wins),
            "round_margin_span": max(margins) - min(margins),
        })
    persisted_baselines: dict[str, str | float] = {}
    request_path = dataset_path.parent / "request.json"
    if request_path.is_file():
        request = json.loads(request_path.read_text(encoding="utf-8"))
        persisted_baselines = request.get("preview", {}).get("baselines", {})
    requested_baselines = {
        factor: _level_text(value)
        for factor, value in {**persisted_baselines, **(baselines or {})}.items()
    }
    baseline_effects = []
    baseline_issues = []
    for (context, factor), rows in sorted(factor_groups.items()):
        levels = {row["level"] for row in rows}
        baseline = requested_baselines.get(factor, DEFAULT_BASELINES.get(factor))
        if baseline is None:
            baseline_issues.append({
                "context": context,
                "factor": factor,
                "issue": "no default baseline; pass baselines to summarize_experiment",
            })
            continue
        if baseline not in levels:
            baseline_issues.append({
                "context": context,
                "factor": factor,
                "baseline_level": baseline,
                "available_levels": sorted(levels),
                "issue": "baseline level was not included in this run",
            })
            continue
        baseline_rows = paired[(context, factor, baseline)]
        for treatment in sorted(levels - {baseline}):
            treatment_rows = paired[(context, factor, treatment)]
            common = sorted(set(baseline_rows) & set(treatment_rows))
            if not common:
                baseline_issues.append({
                    "context": context,
                    "factor": factor,
                    "baseline_level": baseline,
                    "treatment_level": treatment,
                    "issue": "baseline and treatment have no shared pairing keys",
                })
                continue
            rounds_added = sum(
                treatment_rows[key]["weak_score"] - baseline_rows[key]["weak_score"]
                for key in common
            ) / len(common)
            rounds_denied = sum(
                baseline_rows[key]["strong_score"] - treatment_rows[key]["strong_score"]
                for key in common
            ) / len(common)
            margin = sum(
                treatment_rows[key]["weak_round_margin"] - baseline_rows[key]["weak_round_margin"]
                for key in common
            ) / len(common)
            win_pp = 100 * sum(
                treatment_rows[key]["weak_win"] - baseline_rows[key]["weak_win"]
                for key in common
            ) / len(common)
            baseline_effects.append({
                "context": context,
                "factor": factor,
                "baseline_level": baseline,
                "treatment_level": treatment,
                "paired_matches": len(common),
                "rounds_won_added": rounds_added,
                "opponent_rounds_denied": rounds_denied,
                "round_margin_improvement": margin,
                "weak_win_effect_pp": win_pp,
                "margin_reconciliation_error": margin - rounds_added - rounds_denied,
            })
    return {
        "run_id": run_id,
        "outcome_definitions": OUTCOME_DEFINITIONS,
        "summaries": summaries,
        "baseline_effects": baseline_effects,
        "baseline_issues": baseline_issues,
        "factor_spans": spans,
    }
