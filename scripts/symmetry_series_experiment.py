"""Measure how best-of-three and best-of-five series filter match randomness."""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from hashlib import blake2b
import json
import os
from pathlib import Path
import time
from typing import Any

try:
    from scripts.causal_match_experiment import (
        ALL_MAPS,
        Cell,
        TEAM_A,
        TEAM_B,
        Variant,
        run_cell,
    )
except ModuleNotFoundError:  # Direct ``python scripts\...`` invocation.
    from causal_match_experiment import (  # type: ignore[no-redef]
        ALL_MAPS,
        Cell,
        TEAM_A,
        TEAM_B,
        Variant,
        run_cell,
    )


def _stable_seed(series_seed: int, map_id: str) -> int:
    digest = blake2b(
        f"symmetry-series:{series_seed}:{map_id}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") % 2_000_000_000


def _map_order(series_seed: int) -> list[str]:
    return sorted(
        ALL_MAPS,
        key=lambda map_id: blake2b(
            f"symmetry-series-order:{series_seed}:{map_id}".encode("utf-8"),
            digest_size=8,
        ).digest(),
    )


def run_series(task: tuple[int, int, int, float]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    series_index, best_of, series_seed, quality = task
    identity_swap = series_index % 2
    wins_needed = best_of // 2 + 1
    designated_team_id = TEAM_B if identity_swap else TEAM_A
    wins = 0
    losses = 0
    map_rows: list[dict[str, Any]] = []
    order = _map_order(series_seed)
    variant = Variant(
        priority=0,
        factor="symmetry_baseline",
        level="identical",
        context=f"equal_{quality:g}v{quality:g}_bo{best_of}",
        weak_quality=quality,
        strong_quality=quality,
    )
    for map_index, map_id in enumerate(order[:best_of]):
        cell = Cell(
            variant=variant,
            map_id=map_id,
            identity_swap=identity_swap,
            seed_block=_stable_seed(series_seed, map_id),
            seeds_per_cell=1,
        )
        match = run_cell(cell)[0]
        wins += int(match["weak_win"])
        losses += int(not match["weak_win"])
        map_rows.append({
            "series_index": series_index,
            "series_seed": series_seed,
            "best_of": best_of,
            "map_index": map_index,
            "map_id": map_id,
            "match_seed": match["seed"],
            "identity_swap": identity_swap,
            "designated_team_id": designated_team_id,
            "designated_win": match["weak_win"],
            "designated_score": match["weak_score"],
            "opponent_score": match["strong_score"],
            "designated_round_margin": match["weak_round_margin"],
        })
        if wins == wins_needed or losses == wins_needed:
            break
    return ({
        "series_index": series_index,
        "series_seed": series_seed,
        "best_of": best_of,
        "quality": quality,
        "identity_swap": identity_swap,
        "designated_team_id": designated_team_id,
        "map_order": ",".join(order),
        "maps_played": len(map_rows),
        "designated_map_wins": wins,
        "opponent_map_wins": losses,
        "designated_series_win": int(wins == wins_needed),
        "designated_total_round_margin": sum(row["designated_round_margin"] for row in map_rows),
    }, map_rows)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--series", type=int, default=300)
    parser.add_argument("--base-seed", type=int, default=120000)
    parser.add_argument("--quality", type=float, default=75.0)
    parser.add_argument("--workers", type=int, default=min(14, os.cpu_count() or 1))
    args = parser.parse_args()
    if args.series < 1:
        raise SystemExit("--series must be positive")
    args.out.mkdir(parents=True, exist_ok=True)
    series_path = args.out / "series.csv"
    maps_path = args.out / "series_maps.csv"
    if series_path.exists() or maps_path.exists():
        raise SystemExit(f"refusing to overwrite existing series artifacts in {args.out}")

    tasks = [
        (index, best_of, args.base_seed + index, args.quality)
        for best_of in (3, 5)
        for index in range(args.series)
    ]
    started = time.monotonic()
    series_rows: list[dict[str, Any]] = []
    map_rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for series, maps in pool.map(run_series, tasks, chunksize=1):
            series_rows.append(series)
            map_rows.extend(maps)
    series_rows.sort(key=lambda row: (row["best_of"], row["series_index"]))
    map_rows.sort(key=lambda row: (row["best_of"], row["series_index"], row["map_index"]))
    _write_csv(series_path, series_rows)
    _write_csv(maps_path, map_rows)
    elapsed = time.monotonic() - started
    manifest = {
        "status": "complete",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "design": "paired identical-team BO3 and BO5 series",
        "series_per_format": args.series,
        "formats": [3, 5],
        "base_seed": args.base_seed,
        "quality": args.quality,
        "workers": args.workers,
        "series_rows": len(series_rows),
        "map_rows": len(map_rows),
        "elapsed_seconds": elapsed,
        "map_pool": list(ALL_MAPS),
        "identity_assignment": "alternates by series index",
        "seed_contract": "same series seed, map order, and per-map seeds across BO3 and BO5",
        "files": {"series": str(series_path.resolve()), "maps": str(maps_path.resolve())},
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
