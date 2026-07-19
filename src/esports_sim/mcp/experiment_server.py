"""MCP server for designing, launching, and auditing causal match experiments."""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from esports_sim.registry import experiment_mcp_ops as ops


mcp = FastMCP(
    "ESports Match Experiment Lab",
    instructions=(
        "Design deterministic paired match experiments without writing a new harness. "
        "Read the catalog, preview the requested suite, then launch it. Reuse maps, "
        "identity swaps, and seed blocks across treatment levels. Poll get_experiment, "
        "validate before analysis, and use summarize_experiment for paired rounds won "
        "above an explicit baseline. Use the roster-fit series tools when the question "
        "is whether one dial treatment helps a roster archetype relative to its neutral control."
    ),
    json_response=True,
)


@mcp.resource("experiment://catalog")
def experiment_catalog() -> str:
    """Registered causal interventions, standard levels, maps, and pairing keys."""
    return json.dumps(ops.get_experiment_catalog(), indent=2)


@mcp.resource("experiment://run/{run_id}")
def experiment_run(run_id: str) -> str:
    """Request, manifest, validation, and log tail for one experiment run."""
    return json.dumps(ops.get_experiment(run_id), indent=2)


@mcp.tool()
def get_experiment_catalog() -> dict[str, Any]:
    """List registered factors and standard levels in the core and mechanisms suites."""
    return ops.get_experiment_catalog()


@mcp.tool()
def preview_experiment(
    suite: Literal["core", "mechanisms"],
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
    """Validate and size a paired one-factor-at-a-time match design."""
    return ops.preview_experiment(
        suite, factors, levels, maps, seed_blocks, seeds_per_cell,
        weak_quality, strong_quality, context, limit_cells,
    )


@mcp.tool()
def start_experiment(
    name: str,
    suite: Literal["core", "mechanisms"],
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
    """Launch a validated experiment asynchronously and return a pollable run id."""
    return ops.start_experiment(
        name, suite, factors, levels, maps, seed_blocks, seeds_per_cell, workers,
        weak_quality, strong_quality, context, minutes, limit_cells,
    )


@mcp.tool()
def preview_roster_fit_series(
    series: int = 100,
    profiles: list[str] | None = None,
    dials: list[str] | None = None,
    poles: list[float] | None = None,
    quality: float = 75.0,
    base_seed: int = 240000,
) -> dict[str, Any]:
    """Size a same-roster neutral-control versus one-dial-treatment series design."""
    return ops.preview_roster_fit_series(
        series, profiles, dials, poles, quality, base_seed
    )


@mcp.tool()
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
    """Launch paired BO3/BO5 roster-composition by game-plan experiments."""
    return ops.start_roster_fit_series(
        name, series, profiles, dials, poles, quality, base_seed, workers
    )


@mcp.tool()
def preview_roster_pack_tactics_series(
    pack_id: str = "vct-2021",
    series: int = 30,
    teams: list[str] | None = None,
    dials: list[str] | None = None,
    poles: list[float] | None = None,
    seed_base: int = 910000,
) -> dict[str, Any]:
    """Size a mirrored real-roster neutral-control versus dial-treatment design."""
    return ops.preview_roster_pack_tactics_series(
        pack_id, series, teams, dials, poles, seed_base
    )


@mcp.tool()
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
    """Launch paired BO3/BO5 tactics experiments on authored roster-pack teams."""
    return ops.start_roster_pack_tactics_series(
        name, pack_id, series, teams, dials, poles, seed_base, workers
    )


@mcp.tool()
def list_experiments() -> dict[str, Any]:
    """List experiment runs newest first with completion status."""
    return ops.list_experiments()


@mcp.tool()
def get_experiment(run_id: str) -> dict[str, Any]:
    """Poll one run's request, live manifest, validation, and log tail."""
    return ops.get_experiment(run_id)


@mcp.tool()
def validate_experiment(run_id: str) -> dict[str, Any]:
    """Validate row count, cell completeness, and unique causal pairing keys."""
    return ops.validate_experiment(run_id)


@mcp.tool()
def validate_roster_fit_series(run_id: str) -> dict[str, Any]:
    """Validate roster-fit series rows and exact control-treatment map pairing."""
    return ops.validate_roster_fit_series(run_id)


@mcp.tool()
def validate_roster_pack_tactics_series(run_id: str) -> dict[str, Any]:
    """Validate real-roster series rows and unique paired map comparisons."""
    return ops.validate_roster_pack_tactics_series(run_id)


@mcp.tool()
def summarize_experiment(
    run_id: str,
    baselines: dict[str, str | float] | None = None,
) -> dict[str, Any]:
    """Summarize paired rounds added versus catalog defaults or supplied baselines."""
    return ops.summarize_experiment(run_id, baselines)


@mcp.tool()
def summarize_roster_fit_series(run_id: str) -> dict[str, Any]:
    """Return series win lift, rounds added, and fit interaction estimates."""
    return ops.summarize_roster_fit_series(run_id)


@mcp.tool()
def summarize_roster_pack_tactics_series(run_id: str) -> dict[str, Any]:
    """Return per-team rounds added plus authored roster feature metadata."""
    return ops.summarize_roster_pack_tactics_series(run_id)


def main() -> None:
    """Run the Experiment Lab MCP over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
