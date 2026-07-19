"""Structural validation for a causal match experiment artifact directory."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


OUTCOME_FIELDS = (
    "winner_id",
    "weak_win",
    "weak_score",
    "strong_score",
    "weak_round_margin",
    "absolute_round_margin",
    "total_rounds",
    "close_match",
    "overtime",
    "weak_attack_rounds",
    "weak_attack_wins",
    "weak_defense_rounds",
    "weak_defense_wins",
    "weak_kills",
    "strong_kills",
    "weak_trades",
    "strong_trades",
    "weak_utility_uses",
    "strong_utility_uses",
    "weak_failed_utility",
    "strong_failed_utility",
    "weak_plants",
    "strong_plants",
    "weak_defuses",
    "strong_defuses",
    "weak_timeouts",
    "weak_halftime_talks",
    "weak_touchline_shouts",
    "end_reason_elim",
    "end_reason_detonation",
    "end_reason_defuse",
    "end_reason_time",
    "match_max_tick",
)


def _is_neutral_control(version_id: str) -> bool:
    exact = {
        "normalized_65v85__weak_overall__65",
        "normalized_65v85__prep_edge__0",
        "normalized_65v85__counter_edge__0",
        "normalized_65v85__agent_mastery__75",
        "normalized_65v85__map_mastery__75",
        "normalized_65v85__form__50",
        "normalized_65v85__morale__50",
        "normalized_65v85__stamina__100",
        "normalized_65v85__confidence__50",
        "normalized_65v85__chemistry_neutral__65",
        "normalized_65v85__focus_target__none",
        "normalized_65v85__agent_selection__auto",
        "normalized_65v85__agent_selection__comfort_lock",
        "normalized_65v85__roster_shape__balanced",
        "normalized_65v85__coach_quality__50",
        "normalized_65v85__halftime_talk__none",
        "normalized_65v85__touchline_shout__none",
    }
    if version_id in exact:
        return True
    if version_id.startswith("normalized_65v85__skill_") and version_id.endswith("__65"):
        return True
    if version_id.startswith("normalized_65v85__tactic_") and version_id.endswith("__50"):
        return True
    return False


def validate(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    dataset = directory / "matches.csv"
    expected_per_cell = int(manifest["seeds_per_cell"])
    expected_matches = int(manifest["planned_matches"])
    expected_cells = int(manifest["planned_cells"])

    row_keys: set[tuple[str, str]] = set()
    duplicate_row_keys: list[str] = []
    cell_seed_indexes: dict[str, set[int]] = {}
    versions: set[str] = set()
    maps: set[str] = set()
    swaps: set[int] = set()
    blocks: set[int] = set()
    anchor: dict[tuple[str, int, int], tuple[str, ...]] = {}
    neutral_rows: list[tuple[str, tuple[str, int, int], tuple[str, ...]]] = []
    rows = 0

    with dataset.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing_fields = sorted(set(OUTCOME_FIELDS) - set(reader.fieldnames or ()))
        if missing_fields:
            raise ValueError(f"dataset is missing outcome fields: {missing_fields}")
        for row in reader:
            rows += 1
            key = (row["cell_id"], row["seed_index"])
            if key in row_keys:
                duplicate_row_keys.append(f"{key[0]} seed_index={key[1]}")
            row_keys.add(key)
            cell_seed_indexes.setdefault(row["cell_id"], set()).add(int(row["seed_index"]))
            versions.add(row["version_id"])
            maps.add(row["map_id"])
            swaps.add(int(row["identity_swap"]))
            blocks.add(int(row["seed_block"]))

            paired_key = (row["map_id"], int(row["identity_swap"]), int(row["seed"]))
            outcome = tuple(row[field] for field in OUTCOME_FIELDS)
            if row["version_id"] == "normalized_65v85__weak_overall__65":
                anchor[paired_key] = outcome
            if _is_neutral_control(row["version_id"]):
                neutral_rows.append((row["version_id"], paired_key, outcome))

    required_indexes = set(range(expected_per_cell))
    incomplete_cells = {
        cell_id: sorted(required_indexes - indexes)
        for cell_id, indexes in cell_seed_indexes.items()
        if indexes != required_indexes
    }
    neutral_mismatches: list[str] = []
    for version_id, paired_key, outcome in neutral_rows:
        if paired_key not in anchor:
            neutral_mismatches.append(f"{version_id}: missing anchor {paired_key}")
        elif outcome != anchor[paired_key]:
            neutral_mismatches.append(f"{version_id}: outcome drift {paired_key}")

    failures: list[str] = []
    if rows != expected_matches:
        failures.append(f"rows {rows} != planned {expected_matches}")
    if len(cell_seed_indexes) != expected_cells:
        failures.append(f"cells {len(cell_seed_indexes)} != planned {expected_cells}")
    if duplicate_row_keys:
        failures.append(f"duplicate row keys: {len(duplicate_row_keys)}")
    if incomplete_cells:
        failures.append(f"incomplete cells: {len(incomplete_cells)}")
    if manifest.get("errors"):
        failures.append(f"manifest errors: {len(manifest['errors'])}")
    if neutral_mismatches:
        failures.append(f"neutral-control mismatches: {len(neutral_mismatches)}")

    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "matches": rows,
        "cells": len(cell_seed_indexes),
        "versions": len(versions),
        "maps": sorted(maps),
        "identity_swaps": sorted(swaps),
        "seed_blocks": sorted(blocks),
        "duplicate_row_keys": duplicate_row_keys[:20],
        "incomplete_cells": dict(list(incomplete_cells.items())[:20]),
        "neutral_control_rows_compared": len(neutral_rows),
        "neutral_control_mismatches": neutral_mismatches[:20],
        "simulation_errors": manifest.get("errors", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = validate(args.directory)
    destination = args.directory / "validation.json"
    destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
