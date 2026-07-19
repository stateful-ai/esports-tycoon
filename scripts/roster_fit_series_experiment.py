"""Measure whether tuning one tactics dial to roster composition wins series.

Every cell starts from two mechanically identical 75-overall teams with neutral
tactics. The treatment changes exactly one dial on the designated team while
the roster, opponent, map order, identity orientation, and match seeds remain
fixed. The same five map outcomes produce paired BO3 and BO5 results.

Roster archetypes deliberately reverse the attributes used by the engine's
shared tactics-fit layer: fraggers have elite aim/reactivity/movement and weak
sense/utility/comms; tacticians are the inverse; mixed uses two fraggers and
three tacticians; balanced keeps every match attribute at the target quality.
Every player keeps the same arithmetic overall.
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from hashlib import blake2b
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time
from typing import Any, Iterable

from esports_sim.registry import load_all
from esports_sim.schemas import AgentMastery, MapMastery, TeamLineup, TeamTactics
from esports_sim.sim import simulate_match_result
from esports_sim.sim import tactics_fit

try:
    from scripts.causal_match_experiment import (
        ALL_MAPS,
        ATTRIBUTE_IDS,
        TEAM_A,
        TEAM_B,
        _mirror_team_match_inputs,
    )
except ModuleNotFoundError:  # Direct script invocation.
    from causal_match_experiment import (  # type: ignore[no-redef]
        ALL_MAPS,
        ATTRIBUTE_IDS,
        TEAM_A,
        TEAM_B,
        _mirror_team_match_inputs,
    )


DIALS = tuple(tactics_fit.DIAL_FIT_ATTRS)
PROFILES = ("balanced", "fraggers", "tacticians", "mixed")
POLES = (0.0, 100.0)
FORMATS = (3, 5)
BASE_QUALITY = 75.0
_BASE_GAME_DATA: Any | None = None

FRAGGER_ATTRS = {
    "aim_precision": 90.0,
    "aim_reactivity": 90.0,
    "movement": 90.0,
    "game_sense": 50.0,
    "utility_usage": 50.0,
    "comms_quality": 50.0,
    "positioning": 82.5,
    "clutch_factor": 82.5,
    "tilt_resistance": 82.5,
    "composure": 82.5,
}
TACTICIAN_ATTRS = {
    "aim_precision": 50.0,
    "aim_reactivity": 50.0,
    "movement": 50.0,
    "game_sense": 90.0,
    "utility_usage": 90.0,
    "comms_quality": 90.0,
    "positioning": 82.5,
    "clutch_factor": 82.5,
    "tilt_resistance": 82.5,
    "composure": 82.5,
}


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], text=True, encoding="utf-8", errors="replace"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _stable_seed(series_seed: int, map_id: str) -> int:
    digest = blake2b(
        f"roster-fit-series:{series_seed}:{map_id}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") % 2_000_000_000


def _map_order(series_seed: int) -> list[str]:
    return sorted(
        ALL_MAPS,
        key=lambda map_id: blake2b(
            f"roster-fit-order:{series_seed}:{map_id}".encode("utf-8"),
            digest_size=8,
        ).digest(),
    )


def _scaled_profile(values: dict[str, float], quality: float) -> dict[str, float]:
    """Shift an authored 75-overall shape without changing its deviations."""
    shift = quality - BASE_QUALITY
    scaled = {
        attr: max(0.0, min(100.0, value + shift))
        for attr, value in values.items()
    }
    if not math.isclose(statistics.fmean(scaled.values()), quality, abs_tol=1e-9):
        raise ValueError("quality shift clipped the roster shape; choose 25 <= quality <= 85")
    return scaled


def _profile_players(profile: str, quality: float) -> list[dict[str, float]]:
    balanced = {attr: float(quality) for attr in ATTRIBUTE_IDS}
    fraggers = _scaled_profile(FRAGGER_ATTRS, quality)
    tacticians = _scaled_profile(TACTICIAN_ATTRS, quality)
    if profile == "balanced":
        return [balanced.copy() for _ in range(5)]
    if profile == "fraggers":
        return [fraggers.copy() for _ in range(5)]
    if profile == "tacticians":
        return [tacticians.copy() for _ in range(5)]
    if profile == "mixed":
        return [
            fraggers.copy(),
            fraggers.copy(),
            tacticians.copy(),
            tacticians.copy(),
            tacticians.copy(),
        ]
    raise ValueError(f"unknown roster profile: {profile}")


def _normalized_game_data(profile: str, quality: float) -> Any:
    global _BASE_GAME_DATA
    if _BASE_GAME_DATA is None:
        _BASE_GAME_DATA = load_all()
    gd = _BASE_GAME_DATA.model_copy(deep=True)
    authored = _profile_players(profile, quality)
    for team_id in (TEAM_A, TEAM_B):
        team = gd.teams[team_id]
        team.chemistry = 65.0
        team.tactics = TeamTactics()
        team.lineup = TeamLineup()
        for index, pid in enumerate(team.player_ids):
            player = gd.players[pid]
            player.attributes = authored[index].copy()
            player.form = 50.0
            player.morale = 50.0
            player.stamina = 100.0
            player.confidence = 50.0
            player.personality_tags = []
            original = sorted(
                player.agent_pool,
                key=lambda mastery: (-mastery.mastery, mastery.agent_id),
            )
            player.agent_pool = [
                AgentMastery(
                    agent_id=mastery.agent_id,
                    mastery=75.0 if mastery_index == 0 else 60.0,
                )
                for mastery_index, mastery in enumerate(original)
            ]
            player.map_pool = [
                MapMastery(map_id=map_id, mastery=75.0) for map_id in ALL_MAPS
            ]
    # Copy every mechanically relevant player/team field from A to B while
    # preserving stable ids. This makes the baseline truly same-team, not just
    # equal-overall: roles, playstyles, agent pools, captaincy, and lineups all
    # match before the one-dial treatment is applied.
    _mirror_team_match_inputs(gd)
    return gd


def _profile_fit(gd: Any, team_id: str, dial: str, pole: float) -> float:
    roster = [gd.players[pid] for pid in gd.teams[team_id].player_ids]
    side: tactics_fit.Pole = "high" if pole > 50.0 else "low"
    edge = tactics_fit.dial_pole_edge(roster, dial, side)
    if side == "high" and dial in tactics_fit.CHEM_GATED:
        edge += tactics_fit.chem_edge(gd.teams[team_id].chemistry)
    return edge


def _simulate_map(
    gd: Any,
    designated_team_id: str,
    opponent_team_id: str,
    map_id: str,
    seed: int,
) -> dict[str, Any]:
    result = simulate_match_result(
        gd,
        TEAM_A,
        TEAM_B,
        map_id,
        seed,
        capture_control_events=False,
    )
    designated_score = result.score_a if designated_team_id == TEAM_A else result.score_b
    opponent_score = result.score_b if designated_team_id == TEAM_A else result.score_a
    return {
        "designated_win": int(result.winner_id == designated_team_id),
        "designated_score": designated_score,
        "opponent_score": opponent_score,
        "designated_round_margin": designated_score - opponent_score,
    }


def _series_metrics(rows: list[dict[str, Any]], best_of: int) -> dict[str, float | int]:
    chosen = rows[:best_of]
    wins = sum(int(row["designated_win"]) for row in chosen)
    return {
        "series_win": int(wins >= best_of // 2 + 1),
        "maps_won": wins,
        "mean_rounds_won": statistics.fmean(float(row["designated_score"]) for row in chosen),
        "mean_opponent_rounds": statistics.fmean(float(row["opponent_score"]) for row in chosen),
        "mean_round_margin": statistics.fmean(
            float(row["designated_round_margin"]) for row in chosen
        ),
    }


def run_task(
    task: tuple[str, str, int, int, float, tuple[float, ...]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    dial, profile, series_index, series_seed, quality, poles = task
    identity_swap = series_index % 2
    designated_team_id = TEAM_B if identity_swap else TEAM_A
    opponent_team_id = TEAM_A if identity_swap else TEAM_B
    order = _map_order(series_seed)
    control_gd = _normalized_game_data(profile, quality)
    control_maps: list[dict[str, Any]] = []
    for map_index, map_id in enumerate(order):
        match_seed = _stable_seed(series_seed, map_id)
        control_maps.append({
            "map_index": map_index,
            "map_id": map_id,
            "match_seed": match_seed,
            **_simulate_map(
                control_gd,
                designated_team_id,
                opponent_team_id,
                map_id,
                match_seed,
            ),
        })

    series_rows: list[dict[str, Any]] = []
    map_rows: list[dict[str, Any]] = []
    for pole in poles:
        fit_edge = _profile_fit(control_gd, designated_team_id, dial, pole)
        treatment_gd = control_gd.model_copy(deep=True)
        setattr(treatment_gd.teams[designated_team_id].tactics, dial, pole)
        treatment_maps: list[dict[str, Any]] = []
        comparison_id = f"{dial}:{profile}:{pole:g}:{series_index}"
        for control in control_maps:
            treated = {
                "map_index": control["map_index"],
                "map_id": control["map_id"],
                "match_seed": control["match_seed"],
                **_simulate_map(
                    treatment_gd,
                    designated_team_id,
                    opponent_team_id,
                    str(control["map_id"]),
                    int(control["match_seed"]),
                ),
            }
            treatment_maps.append(treated)
            common = {
                "comparison_id": comparison_id,
                "dial": dial,
                "roster_profile": profile,
                "treatment_value": pole,
                "quality": quality,
                "series_index": series_index,
                "series_seed": series_seed,
                "identity_swap": identity_swap,
                "designated_team_id": designated_team_id,
                "opponent_team_id": opponent_team_id,
                "expected_fit_edge": fit_edge,
                "map_index": control["map_index"],
                "map_id": control["map_id"],
                "match_seed": control["match_seed"],
            }
            map_rows.append({
                **common,
                "arm": "control",
                **{
                    key: control[key]
                    for key in (
                        "designated_win",
                        "designated_score",
                        "opponent_score",
                        "designated_round_margin",
                    )
                },
            })
            map_rows.append({
                **common,
                "arm": "treatment",
                **{
                    key: treated[key]
                    for key in (
                        "designated_win",
                        "designated_score",
                        "opponent_score",
                        "designated_round_margin",
                    )
                },
            })

        for best_of in FORMATS:
            control = _series_metrics(control_maps, best_of)
            treatment = _series_metrics(treatment_maps, best_of)
            series_rows.append({
                "comparison_id": comparison_id,
                "dial": dial,
                "roster_profile": profile,
                "treatment_value": pole,
                "best_of": best_of,
                "quality": quality,
                "series_index": series_index,
                "series_seed": series_seed,
                "identity_swap": identity_swap,
                "designated_team_id": designated_team_id,
                "expected_fit_edge": fit_edge,
                "control_series_win": control["series_win"],
                "treatment_series_win": treatment["series_win"],
                "series_win_lift": int(treatment["series_win"]) - int(control["series_win"]),
                "control_maps_won": control["maps_won"],
                "treatment_maps_won": treatment["maps_won"],
                "maps_won_added": int(treatment["maps_won"]) - int(control["maps_won"]),
                "rounds_won_added_per_map": float(treatment["mean_rounds_won"]) - float(control["mean_rounds_won"]),
                "opponent_rounds_denied_per_map": float(control["mean_opponent_rounds"]) - float(treatment["mean_opponent_rounds"]),
                "round_margin_added_per_map": float(treatment["mean_round_margin"]) - float(control["mean_round_margin"]),
            })
    return series_rows, map_rows, 5 * (1 + len(poles))


def _mean_ci(values: Iterable[float], scale: float = 1.0) -> tuple[float, float, float]:
    vals = [float(value) for value in values]
    mean = statistics.fmean(vals) * scale
    if len(vals) < 2:
        return mean, mean, mean
    half = 1.96 * statistics.stdev(vals) / math.sqrt(len(vals)) * scale
    return mean, mean - half, mean + half


def _summaries(series_rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, float, int], list[dict[str, Any]]] = {}
    for row in series_rows:
        key = (
            str(row["dial"]),
            str(row["roster_profile"]),
            float(row["treatment_value"]),
            int(row["best_of"]),
        )
        groups.setdefault(key, []).append(row)
    effects = []
    for (dial, profile, pole, best_of), rows in sorted(groups.items()):
        win, win_lo, win_hi = _mean_ci(
            (float(row["series_win_lift"]) for row in rows), 100.0
        )
        rounds, rounds_lo, rounds_hi = _mean_ci(
            float(row["rounds_won_added_per_map"]) for row in rows
        )
        margin, margin_lo, margin_hi = _mean_ci(
            float(row["round_margin_added_per_map"]) for row in rows
        )
        effects.append({
            "dial": dial,
            "roster_profile": profile,
            "treatment_value": pole,
            "best_of": best_of,
            "series": len(rows),
            "expected_fit_edge": statistics.fmean(
                float(row["expected_fit_edge"]) for row in rows
            ),
            "control_win_rate": statistics.fmean(
                float(row["control_series_win"]) for row in rows
            ),
            "treatment_win_rate": statistics.fmean(
                float(row["treatment_series_win"]) for row in rows
            ),
            "series_win_lift_pp": win,
            "series_win_lift_ci_low": win_lo,
            "series_win_lift_ci_high": win_hi,
            "rounds_won_added_per_map": rounds,
            "rounds_won_added_ci_low": rounds_lo,
            "rounds_won_added_ci_high": rounds_hi,
            "round_margin_added_per_map": margin,
            "round_margin_added_ci_low": margin_lo,
            "round_margin_added_ci_high": margin_hi,
        })

    by_key = {
        (
            str(row["dial"]),
            str(row["roster_profile"]),
            float(row["treatment_value"]),
            int(row["best_of"]),
            int(row["series_index"]),
        ): row
        for row in series_rows
    }
    interactions = []
    all_poles = sorted({float(row["treatment_value"]) for row in series_rows})
    all_dials = sorted({str(row["dial"]) for row in series_rows})
    all_formats = sorted({int(row["best_of"]) for row in series_rows})
    for dial in all_dials:
        aligned = "fraggers" if dial in {"aggression", "pace"} else "tacticians"
        mismatched = "tacticians" if aligned == "fraggers" else "fraggers"
        if not all(
            profile in {str(row["roster_profile"]) for row in series_rows}
            for profile in (aligned, mismatched)
        ):
            continue
        for pole in all_poles:
            for best_of in all_formats:
                indices = sorted({
                    int(row["series_index"])
                    for row in series_rows
                    if row["dial"] == dial
                    and float(row["treatment_value"]) == pole
                    and int(row["best_of"]) == best_of
                })
                win_diffs = [
                    float(by_key[(dial, aligned, pole, best_of, index)]["series_win_lift"])
                    - float(by_key[(dial, mismatched, pole, best_of, index)]["series_win_lift"])
                    for index in indices
                ]
                round_diffs = [
                    float(by_key[(dial, aligned, pole, best_of, index)]["rounds_won_added_per_map"])
                    - float(by_key[(dial, mismatched, pole, best_of, index)]["rounds_won_added_per_map"])
                    for index in indices
                ]
                win, win_lo, win_hi = _mean_ci(win_diffs, 100.0)
                rounds, rounds_lo, rounds_hi = _mean_ci(round_diffs)
                interactions.append({
                    "dial": dial,
                    "treatment_value": pole,
                    "best_of": best_of,
                    "aligned_profile": aligned,
                    "mismatched_profile": mismatched,
                    "series": len(indices),
                    "fit_interaction_win_pp": win,
                    "fit_interaction_win_ci_low": win_lo,
                    "fit_interaction_win_ci_high": win_hi,
                    "fit_interaction_rounds_per_map": rounds,
                    "fit_interaction_rounds_ci_low": rounds_lo,
                    "fit_interaction_rounds_ci_high": rounds_hi,
                })
    return {"effects": effects, "fit_interactions": interactions}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--series", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=240000)
    parser.add_argument("--quality", type=float, default=BASE_QUALITY)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument("--dials", nargs="+", choices=DIALS, default=list(DIALS))
    parser.add_argument("--poles", nargs="+", type=float, default=list(POLES))
    parser.add_argument("--workers", type=int, default=min(14, os.cpu_count() or 1))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.series < 1:
        raise SystemExit("--series must be positive")
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    if not all(0.0 <= pole <= 100.0 and pole != 50.0 for pole in args.poles):
        raise SystemExit("--poles must be between 0 and 100 and cannot be neutral 50")
    if len(args.poles) != len(set(args.poles)):
        raise SystemExit("--poles must be unique")
    args.out.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        "series": args.out / "series.csv",
        "maps": args.out / "series_maps.csv",
        "summary": args.out / "summary.json",
        "manifest": args.out / "manifest.json",
    }
    if any(path.exists() for path in artifact_paths.values()):
        raise SystemExit(f"refusing to overwrite roster-fit artifacts in {args.out}")

    tasks = [
        (
            dial,
            profile,
            index,
            args.base_seed + index,
            args.quality,
            tuple(args.poles),
        )
        for dial in args.dials
        for profile in args.profiles
        for index in range(args.series)
    ]
    started = time.monotonic()
    running_manifest = {
        "status": "running",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "design": "paired control-versus-one-dial-treatment roster-fit series",
        "planned_tasks": len(tasks),
        "completed_tasks": 0,
        "planned_simulated_maps": len(tasks) * 5 * (1 + len(args.poles)),
        "completed_simulated_maps": 0,
    }
    _write_json_atomic(artifact_paths["manifest"], running_manifest)
    series_rows: list[dict[str, Any]] = []
    map_rows: list[dict[str, Any]] = []
    simulated_maps = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for completed, (task_series, task_maps, task_simulations) in enumerate(
            pool.map(run_task, tasks, chunksize=1),
            start=1,
        ):
            series_rows.extend(task_series)
            map_rows.extend(task_maps)
            simulated_maps += task_simulations
            if completed % 25 == 0 or completed == len(tasks):
                _write_json_atomic(
                    artifact_paths["manifest"],
                    {
                        **running_manifest,
                        "completed_tasks": completed,
                        "completed_simulated_maps": simulated_maps,
                        "elapsed_seconds": time.monotonic() - started,
                    },
                )
    series_rows.sort(
        key=lambda row: (
            row["dial"],
            row["roster_profile"],
            row["treatment_value"],
            row["best_of"],
            row["series_index"],
        )
    )
    map_rows.sort(
        key=lambda row: (
            row["dial"],
            row["roster_profile"],
            row["treatment_value"],
            row["series_index"],
            row["map_index"],
            row["arm"],
        )
    )
    _write_csv(artifact_paths["series"], series_rows)
    _write_csv(artifact_paths["maps"], map_rows)
    summary = {
        "status": "complete",
        "outcome_definitions": {
            "series_win_lift_pp": "paired treatment series win minus control series win, percentage points",
            "rounds_won_added_per_map": "paired treatment designated score minus control designated score, averaged over the fixed BO3 or BO5 map set",
            "fit_interaction": "aligned-roster treatment lift minus mismatched-roster treatment lift on the same series seeds",
        },
        **_summaries(series_rows),
    }
    _write_json_atomic(artifact_paths["summary"], summary)
    elapsed = time.monotonic() - started
    manifest = {
        "status": "complete",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "design": "paired control-versus-one-dial-treatment roster-fit series",
        "series_per_cell": args.series,
        "formats": list(FORMATS),
        "profiles": args.profiles,
        "dials": args.dials,
        "poles": args.poles,
        "quality": args.quality,
        "base_seed": args.base_seed,
        "workers": args.workers,
        "series_rows": len(series_rows),
        "map_dataset_rows": len(map_rows),
        "simulated_maps": simulated_maps,
        "elapsed_seconds": elapsed,
        "map_pool": list(ALL_MAPS),
        "pairing_contract": (
            "control and treatment reuse roster, opponent, identity orientation, "
            "five-map order, and per-map seed; treatment changes one designated-team dial"
        ),
        "overall_contract": "every player and both teams have the requested arithmetic overall",
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_dirty": bool(_git_value("status", "--porcelain")),
        "files": {key: str(path.resolve()) for key, path in artifact_paths.items()},
    }
    _write_json_atomic(artifact_paths["manifest"], manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
