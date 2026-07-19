"""Paired tactics experiments over authored teams from a roster pack.

Each source roster is mirrored mechanically onto a second team.  Control maps
keep both copies at neutral tactics; treatment maps change exactly one dial on
one copy.  Map order, seeds, roster, agents, and designated-side orientation
stay paired, so the delta estimates the causal effect of that dial for that
real roster rather than the team's raw quality.
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from hashlib import blake2b
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
from typing import Any, Iterable

from esports_sim.registry import load_all
from esports_sim.registry.rosters import RosterPack, load_roster_pack
from esports_sim.schemas import TeamTactics
from esports_sim.sim import simulate_match_result, tactics_fit


ALL_MAPS = ("ascent", "bind", "haven", "lotus", "split")
FORMATS = (3, 5)
POLES = (0.0, 100.0)
DIALS = tuple(tactics_fit.DIAL_POLE_FIT_ATTRS)
DEFAULT_TEAMS = (
    "team_furia_esports",
    "team_team_envy",
    "team_sentinels",
    "team_gambit_esports",
    "team_nuturn_gaming",
    "team_zeta_division",
)
_PACKS: dict[str, RosterPack] = {}
_BASE_GAME_DATA: Any | None = None


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], text=True, encoding="utf-8", errors="replace"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _stable_seed(pack_id: str, team_id: str, series_seed: int, map_id: str) -> int:
    digest = blake2b(
        f"pack-tactics:{pack_id}:{team_id}:{series_seed}:{map_id}".encode(),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") % 2_000_000_000


def _map_order(pack_id: str, team_id: str, series_seed: int) -> list[str]:
    return sorted(
        ALL_MAPS,
        key=lambda map_id: blake2b(
            f"pack-order:{pack_id}:{team_id}:{series_seed}:{map_id}".encode(),
            digest_size=8,
        ).digest(),
    )


def _pack(pack_id: str) -> RosterPack:
    if pack_id not in _PACKS:
        _PACKS[pack_id] = load_roster_pack(pack_id)
    return _PACKS[pack_id]


def _remap_team(team: Any, player_ids: dict[str, str], team_id: str) -> Any:
    remapped = team.model_copy(deep=True)
    remapped.id = team_id
    remapped.player_ids = [player_ids[pid] for pid in team.player_ids]
    remapped.captain_id = (
        player_ids[team.captain_id] if team.captain_id is not None else None
    )
    remapped.lineup_ids = [
        player_ids[pid] for pid in team.lineup_ids if pid in player_ids
    ]
    remapped.igl_experience = {
        player_ids[pid]: value
        for pid, value in team.igl_experience.items()
        if pid in player_ids
    }
    remapped.lineup.starters = [
        player_ids[pid] for pid in team.lineup.starters if pid in player_ids
    ]
    remapped.lineup.agents = {
        player_ids[pid]: agent_id
        for pid, agent_id in team.lineup.agents.items()
        if pid in player_ids
    }
    remapped.tactics = TeamTactics()
    return remapped


def mirrored_pack_game_data(pack_id: str, source_team_id: str) -> tuple[Any, str, str]:
    """Install a real pack roster and an exact mechanical mirror into GameData."""
    global _BASE_GAME_DATA
    if _BASE_GAME_DATA is None:
        _BASE_GAME_DATA = load_all()
    gd = _BASE_GAME_DATA.model_copy(deep=True)
    pack = _pack(pack_id)
    source_team = pack.teams[source_team_id]
    real_id = source_team.id
    mirror_id = f"experiment_mirror_{source_team.id}"
    real_map = {pid: pid for pid in source_team.player_ids}
    mirror_map = {pid: f"experiment_mirror_{pid}" for pid in source_team.player_ids}

    for source_pid in source_team.player_ids:
        source_player = pack.players[source_pid]
        gd.players[source_pid] = source_player.model_copy(deep=True)
        mirrored = source_player.model_copy(deep=True)
        mirrored.id = mirror_map[source_pid]
        gd.players[mirrored.id] = mirrored

    gd.teams[real_id] = _remap_team(source_team, real_map, real_id)
    gd.teams[mirror_id] = _remap_team(source_team, mirror_map, mirror_id)
    gd.teams[mirror_id].name = f"{source_team.name} mirror"
    gd.teams[mirror_id].tag = f"{source_team.tag}M"
    return gd, real_id, mirror_id


def _team_features(pack_id: str, team_id: str) -> dict[str, Any]:
    pack = _pack(pack_id)
    team = pack.teams[team_id]
    players = [pack.players[pid] for pid in team.player_ids]
    attr_ids = sorted({attr for player in players for attr in player.attributes})
    means = {
        attr: statistics.fmean(player.attr(attr) for player in players)
        for attr in attr_ids
    }
    playstyles: dict[str, int] = {}
    roles: dict[str, int] = {}
    for player in players:
        playstyles[str(player.playstyle)] = playstyles.get(str(player.playstyle), 0) + 1
        roles[str(player.role)] = roles.get(str(player.role), 0) + 1
    return {
        "team_id": team.id,
        "team_name": team.name,
        "region": str(team.region),
        "chemistry": team.chemistry,
        "overall": statistics.fmean(
            statistics.fmean(player.attributes.values()) for player in players
        ),
        "attribute_means": means,
        "playstyles": playstyles,
        "roles": roles,
        "players": [player.handle for player in players],
    }


def _fit_edges(gd: Any, team_id: str, dial: str) -> tuple[float, float]:
    roster = [gd.players[pid] for pid in gd.teams[team_id].player_ids]
    if hasattr(tactics_fit, "dial_pole_edge"):
        low = tactics_fit.dial_pole_edge(roster, dial, "low")
        high = tactics_fit.dial_pole_edge(roster, dial, "high")
        high += (
            tactics_fit.chem_edge(gd.teams[team_id].chemistry)
            if dial in tactics_fit.CHEM_GATED
            else 0.0
        )
        return low, high
    attrs = tactics_fit.DIAL_FIT_ATTRS[dial]
    edge = tactics_fit.fit_edge(
        tactics_fit.player_fit(player.attr(attr) for attr in attrs)
        for player in roster
    )
    high = edge + (
        tactics_fit.chem_edge(gd.teams[team_id].chemistry)
        if dial in tactics_fit.CHEM_GATED
        else 0.0
    )
    return edge, high


def _simulate_map(
    gd: Any,
    team_a: str,
    team_b: str,
    designated_team: str,
    map_id: str,
    seed: int,
) -> dict[str, int]:
    result = simulate_match_result(
        gd, team_a, team_b, map_id, seed, capture_control_events=False
    )
    designated_score = result.score_a if designated_team == team_a else result.score_b
    opponent_score = result.score_b if designated_team == team_a else result.score_a
    return {
        "designated_win": int(result.winner_id == designated_team),
        "designated_score": designated_score,
        "opponent_score": opponent_score,
        "designated_round_margin": designated_score - opponent_score,
    }


def _series_metrics(rows: list[dict[str, Any]], best_of: int) -> dict[str, float | int]:
    wins_needed = best_of // 2 + 1
    wins = losses = rounds_for = rounds_against = maps = 0
    for row in rows[:best_of]:
        if wins >= wins_needed or losses >= wins_needed:
            break
        maps += 1
        wins += int(row["designated_win"])
        losses += 1 - int(row["designated_win"])
        rounds_for += int(row["designated_score"])
        rounds_against += int(row["opponent_score"])
    return {
        "series_win": int(wins >= wins_needed),
        "maps_won": wins,
        "maps_lost": losses,
        "maps_played": maps,
        "rounds_won": rounds_for,
        "rounds_lost": rounds_against,
        "round_margin": rounds_for - rounds_against,
        "round_margin_per_map": (rounds_for - rounds_against) / maps,
    }


def run_task(task: tuple[str, str, int, int, tuple[str, ...], tuple[float, ...]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pack_id, source_team_id, series_index, seed_base, dials, poles = task
    series_seed = seed_base + series_index
    gd, real_id, mirror_id = mirrored_pack_game_data(pack_id, source_team_id)
    designated = mirror_id if series_index % 2 else real_id
    opponent = real_id if designated == mirror_id else mirror_id
    map_order = _map_order(pack_id, source_team_id, series_seed)
    seeds = {
        map_id: _stable_seed(pack_id, source_team_id, series_seed, map_id)
        for map_id in map_order
    }
    control_maps = [
        _simulate_map(gd, real_id, mirror_id, designated, map_id, seeds[map_id])
        for map_id in map_order
    ]

    map_rows: list[dict[str, Any]] = []
    series_rows: list[dict[str, Any]] = []
    for dial in dials:
        low_edge, high_edge = _fit_edges(gd, designated, dial)
        for pole in poles:
            treatment = gd.model_copy(deep=True)
            setattr(treatment.teams[designated].tactics, dial, pole)
            treatment_maps = [
                _simulate_map(
                    treatment, real_id, mirror_id, designated, map_id, seeds[map_id]
                )
                for map_id in map_order
            ]
            comparison_id = f"{source_team_id}:{dial}:{pole:g}:{series_index}"
            for map_index, (control, treated) in enumerate(
                zip(control_maps, treatment_maps)
            ):
                map_rows.append(
                    {
                        "comparison_id": comparison_id,
                        "pack_id": pack_id,
                        "source_team_id": source_team_id,
                        "series_index": series_index,
                        "series_seed": series_seed,
                        "map_index": map_index,
                        "map_id": map_order[map_index],
                        "match_seed": seeds[map_order[map_index]],
                        "dial": dial,
                        "pole": pole,
                        "designated_identity": "mirror" if designated == mirror_id else "real",
                        "fit_edge_low": low_edge,
                        "fit_edge_high": high_edge,
                        "control_win": control["designated_win"],
                        "treatment_win": treated["designated_win"],
                        "map_win_lift": treated["designated_win"] - control["designated_win"],
                        "control_round_margin": control["designated_round_margin"],
                        "treatment_round_margin": treated["designated_round_margin"],
                        "round_margin_lift": treated["designated_round_margin"] - control["designated_round_margin"],
                        "rounds_won_added": treated["designated_score"] - control["designated_score"],
                    }
                )
            for best_of in FORMATS:
                control = _series_metrics(control_maps, best_of)
                treated = _series_metrics(treatment_maps, best_of)
                series_rows.append(
                    {
                        "comparison_id": comparison_id,
                        "pack_id": pack_id,
                        "source_team_id": source_team_id,
                        "series_index": series_index,
                        "series_seed": series_seed,
                        "best_of": best_of,
                        "dial": dial,
                        "pole": pole,
                        "designated_identity": "mirror" if designated == mirror_id else "real",
                        "fit_edge_low": low_edge,
                        "fit_edge_high": high_edge,
                        "control_series_win": control["series_win"],
                        "treatment_series_win": treated["series_win"],
                        "series_win_lift": treated["series_win"] - control["series_win"],
                        "control_rounds_won": control["rounds_won"],
                        "treatment_rounds_won": treated["rounds_won"],
                        "rounds_won_added": treated["rounds_won"] - control["rounds_won"],
                        "control_round_margin": control["round_margin"],
                        "treatment_round_margin": treated["round_margin"],
                        "round_margin_lift": treated["round_margin"] - control["round_margin"],
                        "control_maps_played": control["maps_played"],
                        "treatment_maps_played": treated["maps_played"],
                    }
                )
    return map_rows, series_rows


def _mean_ci(values: Iterable[float]) -> tuple[float, float, float]:
    vals = list(values)
    mean = statistics.fmean(vals) if vals else 0.0
    if len(vals) < 2:
        return mean, mean, mean
    half = 1.96 * statistics.stdev(vals) / len(vals) ** 0.5
    return mean, mean - half, mean + half


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, float, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row["source_team_id"]), str(row["dial"]),
            float(row["pole"]), int(row["best_of"]),
        )
        grouped.setdefault(key, []).append(row)
    summaries = []
    for (team_id, dial, pole, best_of), group in sorted(grouped.items()):
        win = _mean_ci(float(row["series_win_lift"]) * 100.0 for row in group)
        rounds = _mean_ci(float(row["rounds_won_added"]) for row in group)
        margin = _mean_ci(float(row["round_margin_lift"]) for row in group)
        summaries.append(
            {
                "source_team_id": team_id,
                "dial": dial,
                "pole": pole,
                "best_of": best_of,
                "n": len(group),
                "series_win_lift_pp": win[0],
                "series_win_lift_ci_low": win[1],
                "series_win_lift_ci_high": win[2],
                "rounds_won_added": rounds[0],
                "rounds_won_added_ci_low": rounds[1],
                "rounds_won_added_ci_high": rounds[2],
                "round_margin_lift": margin[0],
                "round_margin_lift_ci_low": margin[1],
                "round_margin_lift_ci_high": margin[2],
                "fit_edge": statistics.fmean(
                    float(row["fit_edge_low"] if pole < 50 else row["fit_edge_high"])
                    for row in group
                ),
            }
        )
    return summaries


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _validate_rows(
    map_rows: list[dict[str, Any]],
    series_rows: list[dict[str, Any]],
    expected_maps: int,
    expected_series: int,
) -> dict[str, Any]:
    map_keys = {
        (str(row["comparison_id"]), int(row["map_index"])) for row in map_rows
    }
    series_keys = {
        (str(row["comparison_id"]), int(row["best_of"])) for row in series_rows
    }
    validation = {
        "valid": (
            len(map_rows) == expected_maps
            and len(series_rows) == expected_series
            and len(map_keys) == len(map_rows)
            and len(series_keys) == len(series_rows)
        ),
        "map_rows": len(map_rows),
        "expected_map_rows": expected_maps,
        "unique_map_keys": len(map_keys),
        "series_rows": len(series_rows),
        "expected_series_rows": expected_series,
        "unique_series_keys": len(series_keys),
    }
    if not validation["valid"]:
        raise RuntimeError(f"experiment row validation failed: {validation}")
    return validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", default="vct-2021")
    parser.add_argument("--teams", nargs="+", default=list(DEFAULT_TEAMS))
    parser.add_argument("--dials", nargs="+", default=list(DIALS))
    parser.add_argument("--poles", nargs="+", type=float, default=list(POLES))
    parser.add_argument("--series", type=int, default=20)
    parser.add_argument("--seed-base", type=int, default=910_000)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = load_roster_pack(args.pack)
    teams = sorted(pack.teams) if args.teams == ["all"] else args.teams
    missing = sorted(set(teams) - set(pack.teams))
    if missing:
        raise ValueError(f"unknown teams in {args.pack}: {', '.join(missing)}")
    invalid_dials = sorted(set(args.dials) - set(tactics_fit.DIAL_FIT_ATTRS))
    if invalid_dials:
        raise ValueError(f"unknown tactics dials: {', '.join(invalid_dials)}")
    if args.series < 1:
        raise ValueError("--series must be positive")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path("runs/mcp-experiments") / f"{stamp}-pack-tactics-{args.pack}"
    output.mkdir(parents=True, exist_ok=True)
    occupied = [
        name for name in ("maps.csv", "series.csv", "summary.csv", "manifest.json")
        if (output / name).exists()
    ]
    if occupied:
        raise FileExistsError(
            f"output already contains experiment artifacts: {', '.join(occupied)}"
        )
    tasks = [
        (args.pack, team_id, index, args.seed_base, tuple(args.dials), tuple(args.poles))
        for team_id in teams
        for index in range(args.series)
    ]
    started = time.perf_counter()
    map_rows: list[dict[str, Any]] = []
    series_rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for maps, series in pool.map(run_task, tasks, chunksize=1):
            map_rows.extend(maps)
            series_rows.extend(series)
    map_rows.sort(key=lambda row: (row["comparison_id"], row["map_index"]))
    series_rows.sort(key=lambda row: (row["comparison_id"], row["best_of"]))
    summaries = _summaries(series_rows)
    features = [_team_features(args.pack, team_id) for team_id in teams]
    expected_map_rows = len(tasks) * len(args.dials) * len(args.poles) * len(ALL_MAPS)
    expected_series_rows = (
        len(tasks) * len(args.dials) * len(args.poles) * len(FORMATS)
    )
    validation = _validate_rows(
        map_rows, series_rows, expected_map_rows, expected_series_rows
    )

    _write_csv(output / "maps.csv", map_rows)
    _write_csv(output / "series.csv", series_rows)
    _write_csv(output / "summary.csv", summaries)
    (output / "team_features.json").write_text(
        json.dumps(features, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "validation.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "status": "complete",
        "design": "paired neutral-control versus one-dial treatment on mirrored authored rosters",
        "pack": args.pack,
        "teams": teams,
        "dials": args.dials,
        "poles": args.poles,
        "series_per_cell": args.series,
        "formats": list(FORMATS),
        "maps": list(ALL_MAPS),
        "map_rows": len(map_rows),
        "series_rows": len(series_rows),
        "actual_map_simulations": len(tasks) * (1 + len(args.dials) * len(args.poles)) * len(ALL_MAPS),
        "completed_simulated_maps": len(tasks) * (1 + len(args.dials) * len(args.poles)) * len(ALL_MAPS),
        "planned_simulated_maps": len(tasks) * (1 + len(args.dials) * len(args.poles)) * len(ALL_MAPS),
        "elapsed_seconds": time.perf_counter() - started,
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_status": _git_value("status", "--short"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(output), **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
