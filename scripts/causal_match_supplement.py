"""Targeted causal sweep for language, role fit, IGL reps, and skill bundles.

This companion to ``causal_match_experiment.py`` fills mechanisms that the
original normalized 65-vs-85 matrix did not manipulate explicitly.  It runs
the same paired seeds in both a large talent-gap context (65 vs 85) and a close
context (75 vs 80), where bounded management effects can move win probability.
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict, replace
from datetime import UTC, datetime
import itertools
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Iterable

from esports_sim.manager import development, role_fit
from esports_sim.schemas import LanguageSkill, Playstyle, Role

try:
    from scripts.causal_match_experiment import (
        ALL_MAPS,
        ATTRIBUTE_IDS,
        Cell,
        Variant,
        _normalize_game_data,
        _summarize_match,
        _team_field_mean,
        _team_quality,
    )
except ModuleNotFoundError:  # Direct ``python scripts\...`` invocation.
    from causal_match_experiment import (  # type: ignore[no-redef]
        ALL_MAPS,
        ATTRIBUTE_IDS,
        Cell,
        Variant,
        _normalize_game_data,
        _summarize_match,
        _team_field_mean,
        _team_quality,
    )


MICRO_ATTRS = ("aim_precision", "aim_reactivity", "movement")
TACTICAL_ATTRS = ("game_sense", "utility_usage", "positioning")
MENTAL_ATTRS = ("clutch_factor", "tilt_resistance", "composure")


def supplement_variants() -> list[Variant]:
    variants: list[Variant] = []
    contexts = (
        ("normalized_65v85_supplement", 65.0, 85.0),
        ("normalized_75v80_supplement", 75.0, 80.0),
    )
    for context, weak_quality, strong_quality in contexts:
        def numeric(factor: str, values: Iterable[float]) -> None:
            variants.extend(
                Variant(
                    priority=0,
                    factor=factor,
                    level=f"{value:g}",
                    level_numeric=float(value),
                    context=context,
                    weak_quality=weak_quality,
                    strong_quality=strong_quality,
                )
                for value in values
            )

        variants.append(
            Variant(
                0,
                "shared_language",
                "no_common",
                None,
                context,
                weak_quality,
                strong_quality,
            )
        )
        numeric("shared_language", (20, 50, 75, 100))
        numeric("role_comfort", (40, 60, 80, 100))
        numeric("igl_experience", (40, 60, 80, 100))
        variants.extend(
            Variant(
                0,
                "role_assignment",
                level,
                None,
                context,
                weak_quality,
                strong_quality,
            )
            for level in ("aligned", "rotated", "worst_fit")
        )
        numeric("micro_bundle", (45, 65, 85))
        numeric("tactical_bundle", (45, 65, 85))
        numeric("mental_bundle", (45, 65, 85))
    return variants


def supplement_cells(
    maps: Iterable[str], seed_blocks: Iterable[int], seeds_per_cell: int,
    variants: Iterable[Variant] | None = None,
) -> list[Cell]:
    return [
        Cell(variant, map_id, identity_swap, seed_block, seeds_per_cell)
        for map_id in maps
        for identity_swap in (0, 1)
        for seed_block in seed_blocks
        for variant in list(variants or supplement_variants())
    ]


def _apply_role_fit_view(gd: Any, team_id: str) -> None:
    for pid in gd.teams[team_id].player_ids:
        player = gd.players[pid]
        raw = development.overall(player)
        delta = role_fit.current_ability(player) - raw
        player.attributes = {
            attr_id: max(1.0, min(99.0, value + delta))
            for attr_id, value in player.attributes.items()
        }


def _assignment_shape(player: Any, quality: float) -> dict[str, float]:
    weights: dict[str, float] = {}
    for source, multiplier in (
        (role_fit.ROLE_WEIGHTS.get(str(player.role), {}), 1.0),
        (role_fit.STYLE_WEIGHTS.get(str(player.playstyle), {}), 0.55),
    ):
        for attr_id, weight in source.items():
            weights[attr_id] = weights.get(attr_id, 0.0) + weight * multiplier
    values = [weights.get(attr_id, 0.0) for attr_id in ATTRIBUTE_IDS]
    center = sum(values) / len(values)
    span = max(max(values) - center, center - min(values), 1.0)
    shaped = {
        attr_id: quality + (weights.get(attr_id, 0.0) - center) / span * 18.0
        for attr_id in ATTRIBUTE_IDS
    }
    correction = quality - sum(shaped.values()) / len(shaped)
    return {attr_id: value + correction for attr_id, value in shaped.items()}


def _role_assignment(gd: Any, team_id: str, mode: str, quality: float) -> None:
    pids = sorted(gd.teams[team_id].player_ids)
    assignments = [(gd.players[pid].role, gd.players[pid].playstyle) for pid in pids]
    for pid in pids:
        gd.players[pid].attributes = _assignment_shape(gd.players[pid], quality)

    if mode == "aligned":
        chosen = assignments
    elif mode == "rotated":
        chosen = assignments[1:] + assignments[:1]
    else:
        def total_fit(permutation: tuple[tuple[Role, Playstyle], ...]) -> float:
            total = 0.0
            for pid, (role, style) in zip(pids, permutation):
                probe = gd.players[pid].model_copy(update={"role": role, "playstyle": style})
                total += role_fit.weighted_ability(probe)
            return total

        chosen = list(min(itertools.permutations(assignments), key=total_fit))

    for pid, (role, style) in zip(pids, chosen):
        player = gd.players[pid]
        player.role = role
        player.playstyle = style
        player.role_style_comfort = {role_fit.assignment_key(player): 100.0}
    _apply_role_fit_view(gd, team_id)


def _inputs(gd: Any, cell: Cell, language_mode: str = "baseline") -> dict[str, Any]:
    weak_id = cell.weak_team_id
    strong_id = cell.strong_team_id
    values = {
        "weak_team_id": weak_id,
        "strong_team_id": strong_id,
        "weak_quality": _team_quality(gd, weak_id),
        "strong_quality": _team_quality(gd, strong_id),
        "weak_chemistry": gd.teams[weak_id].chemistry,
        "weak_form": _team_field_mean(gd, weak_id, "form"),
        "weak_morale": _team_field_mean(gd, weak_id, "morale"),
        "weak_stamina": _team_field_mean(gd, weak_id, "stamina"),
        "weak_confidence": _team_field_mean(gd, weak_id, "confidence"),
        "weak_agent_mode": "auto",
        "weak_roster_shape": "balanced",
        "weak_prep_edge": 0.0,
        "weak_counter_edge": 0.0,
        "weak_focus_target": "",
        "weak_coach_quality": 50.0,
        "weak_halftime_talk": "none",
        "weak_touchline_shout": "none",
        "weak_language_mode": language_mode,
        "weak_assignment_comfort": sum(
            role_fit.assignment_comfort(gd.players[pid])
            for pid in gd.teams[weak_id].player_ids
        ) / len(gd.teams[weak_id].player_ids),
        "weak_igl_experience": role_fit.igl_experience(
            gd.teams[weak_id], gd.teams[weak_id].captain_id
        ),
    }
    for dial in ("aggression", "pace", "util_discipline", "eco_greed", "map_control"):
        values[f"weak_tactic_{dial}"] = getattr(gd.teams[weak_id].tactics, dial)
    return values


def build_supplement_inputs(cell: Cell) -> tuple[Any, dict[str, Any]]:
    gd = _normalize_game_data(cell)
    weak_id = cell.weak_team_id
    strong_id = cell.strong_team_id
    factor = cell.variant.factor
    value = cell.variant.level_numeric
    language_mode = "baseline"

    # Hold language constant outside the language treatment so the role and
    # bundle cells isolate only their named mechanism.
    for pid in gd.teams[weak_id].player_ids + gd.teams[strong_id].player_ids:
        gd.players[pid].languages = [LanguageSkill(lang="en", level=100.0)]

    if factor == "shared_language":
        language_mode = cell.variant.level
        pids = sorted(gd.teams[weak_id].player_ids)
        if cell.variant.level == "no_common":
            for index, pid in enumerate(pids):
                gd.players[pid].languages = [
                    LanguageSkill(lang=f"unique_{index}", level=100.0)
                ]
        else:
            assert value is not None
            for pid in pids:
                gd.players[pid].languages = [LanguageSkill(lang="en", level=value)]
    elif factor == "role_comfort":
        assert value is not None
        for pid in gd.teams[weak_id].player_ids:
            player = gd.players[pid]
            player.role_style_comfort = {role_fit.assignment_key(player): value}
        _apply_role_fit_view(gd, weak_id)
    elif factor == "igl_experience":
        assert value is not None
        captain = gd.teams[weak_id].captain_id
        gd.teams[weak_id].igl_experience = {captain: value}
    elif factor == "role_assignment":
        _role_assignment(gd, weak_id, cell.variant.level, cell.variant.weak_quality)
    elif factor.endswith("_bundle"):
        assert value is not None
        attrs = {
            "micro_bundle": MICRO_ATTRS,
            "tactical_bundle": TACTICAL_ATTRS,
            "mental_bundle": MENTAL_ATTRS,
        }[factor]
        for pid in gd.teams[weak_id].player_ids:
            for attr_id in attrs:
                gd.players[pid].attributes[attr_id] = value

    return gd, _inputs(gd, cell, language_mode)


def run_supplement_cell(cell: Cell) -> list[dict[str, Any]]:
    gd, inputs = build_supplement_inputs(cell)
    return [
        _summarize_match(
            cell,
            seed_index,
            cell.seed_block + seed_index,
            gd,
            {},
            inputs,
        )
        for seed_index in range(cell.seeds_per_cell)
    ]


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--workers", type=int, default=min(14, os.cpu_count() or 1))
    parser.add_argument("--seeds-per-cell", type=int, default=30)
    parser.add_argument("--seed-blocks", default="30000,40000,50000")
    parser.add_argument("--maps", nargs="+", choices=ALL_MAPS, default=list(ALL_MAPS))
    parser.add_argument("--limit-cells", type=int, default=0)
    parser.add_argument("--factors", default="", help="comma-separated factor ids")
    parser.add_argument(
        "--levels-json", default="{}",
        help="JSON object mapping factor ids to selected or custom levels",
    )
    parser.add_argument("--weak-quality", type=float)
    parser.add_argument("--strong-quality", type=float)
    parser.add_argument("--context", default="")
    parser.add_argument("--describe", action="store_true")
    return parser.parse_args()


def _selected_variants(args: argparse.Namespace) -> list[Variant]:
    variants = supplement_variants()
    factors = {value for value in args.factors.split(",") if value}
    if factors:
        unknown = factors - {variant.factor for variant in variants}
        if unknown:
            raise SystemExit(f"unknown factors: {sorted(unknown)}")
        variants = [variant for variant in variants if variant.factor in factors]
    overrides = json.loads(args.levels_json)
    if not isinstance(overrides, dict):
        raise SystemExit("--levels-json must be a JSON object")
    rebuilt: list[Variant] = []
    for factor in dict.fromkeys(variant.factor for variant in variants):
        templates = [variant for variant in variants if variant.factor == factor]
        if factor not in overrides:
            rebuilt.extend(templates)
            continue
        values = overrides[factor]
        if not isinstance(values, list) or not values:
            raise SystemExit(f"levels for {factor} must be a non-empty list")
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
                raise SystemExit(f"unknown levels for {factor}: {sorted(unknown_levels)}")
            rebuilt.extend(by_level[str(value)] for value in values)
    context = args.context or (
        f"normalized_{args.weak_quality:g}v{args.strong_quality:g}_mechanisms"
        if args.weak_quality is not None and args.strong_quality is not None else ""
    )
    selected = [
        replace(
            variant,
            weak_quality=args.weak_quality if args.weak_quality is not None else variant.weak_quality,
            strong_quality=args.strong_quality if args.strong_quality is not None else variant.strong_quality,
            context=context or variant.context,
        )
        for variant in rebuilt
    ]
    # Default supplement variants contain two talent contexts. A custom matchup
    # intentionally collapses those into one context, so remove duplicate levels.
    unique: dict[tuple[str, str, str], Variant] = {}
    for variant in selected:
        unique[(variant.context, variant.factor, variant.level)] = variant
    return list(unique.values())


def main() -> int:
    args = parse_args()
    variants = _selected_variants(args)
    if args.describe:
        print(json.dumps({"suite": "mechanisms", "design": [asdict(v) for v in variants]}, indent=2))
        return 0
    if args.out is None:
        raise SystemExit("--out is required unless --describe is used")
    blocks = tuple(int(value) for value in args.seed_blocks.split(","))
    cells = supplement_cells(args.maps, blocks, args.seeds_per_cell, variants)
    if args.limit_cells:
        cells = cells[: args.limit_cells]
    args.out.mkdir(parents=True, exist_ok=True)
    dataset_path = args.out / "matches.csv"
    manifest_path = args.out / "manifest.json"
    if dataset_path.exists():
        raise SystemExit(f"refusing to overwrite existing dataset: {dataset_path}")

    started = time.monotonic()
    manifest = {
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "git_sha": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "maps": list(args.maps),
        "seed_blocks": list(blocks),
        "seeds_per_cell": args.seeds_per_cell,
        "workers": args.workers,
        "versions": len(variants),
        "planned_cells": len(cells),
        "planned_matches": len(cells) * args.seeds_per_cell,
        "design": [asdict(variant) for variant in variants],
        "errors": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    rows_written = 0
    cells_written = 0
    errors: list[str] = []
    writer: csv.DictWriter[str] | None = None
    with dataset_path.open("w", newline="", encoding="utf-8") as handle:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending: dict[Any, Cell] = {}
            iterator = iter(cells)
            open_submission = True
            while open_submission or pending:
                while open_submission and len(pending) < args.workers * 2:
                    try:
                        cell = next(iterator)
                    except StopIteration:
                        open_submission = False
                        break
                    pending[pool.submit(run_supplement_cell, cell)] = cell
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    cell = pending.pop(future)
                    try:
                        rows = future.result()
                    except Exception as exc:
                        errors.append(f"{cell.cell_id}: {type(exc).__name__}: {exc}")
                        print(f"ERROR {errors[-1]}", flush=True)
                        continue
                    if writer is None:
                        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                        writer.writeheader()
                    writer.writerows(rows)
                    handle.flush()
                    rows_written += len(rows)
                    cells_written += 1
                    if cells_written <= 3 or cells_written % 140 == 0:
                        elapsed = time.monotonic() - started
                        print(
                            f"progress cells={cells_written}/{len(cells)} "
                            f"matches={rows_written} rate={rows_written/max(elapsed, .001):.1f}/s",
                            flush=True,
                        )

    manifest.update(
        {
            "status": "complete" if not errors and cells_written == len(cells) else "failed",
            "finished_at_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": time.monotonic() - started,
            "completed_cells": cells_written,
            "completed_matches": rows_written,
            "errors": errors,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("status", "completed_cells", "completed_matches", "elapsed_seconds", "errors")}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
