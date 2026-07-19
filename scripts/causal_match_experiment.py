"""Generate an analysis-ready causal dataset from the deterministic match sim.

The design uses one-factor-at-a-time interventions over a normalized synthetic
65-vs-85 matchup.  Every treatment reuses the same map, roster identity, and
seed as its control.  Separated seed blocks make it possible to test whether
effect rankings reproduce out of sample instead of depending on one seed run.

Typical long run (about 45 minutes on a 16-thread workstation)::

    .venv-win\\Scripts\\python.exe scripts\\causal_match_experiment.py \
        --minutes 40 --workers 14

Artifacts are written beneath ``runs/`` and are safe to resume by passing the
same ``--out`` directory.  The match dataset is append-only while the run is in
progress; completed cells are detected from their deterministic ``cell_id``.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable

from esports_sim.policy import CoachProfile
from esports_sim.registry import load_all
from esports_sim.schemas import AgentMastery, MapMastery, TeamLineup, TeamTactics
from esports_sim.sim import TeamMatchPlan, simulate_match_result
from esports_sim.sim import constants as C
from esports_sim.sim.lineup import auto_pick_agent


TEAM_A = "team_nexus"
TEAM_B = "team_vanguard"
ALL_MAPS = ("ascent", "bind", "haven", "lotus", "split")
ATTRIBUTE_IDS = (
    "aim_precision",
    "aim_reactivity",
    "movement",
    "game_sense",
    "utility_usage",
    "positioning",
    "clutch_factor",
    "tilt_resistance",
    "composure",
    "comms_quality",
)
TACTIC_DIALS = (
    "aggression",
    "pace",
    "util_discipline",
    "eco_greed",
    "map_control",
)

_BASE_GAME_DATA: Any | None = None


@dataclass(frozen=True)
class Variant:
    priority: int
    factor: str
    level: str
    level_numeric: float | None = None
    context: str = "normalized_65v85"
    weak_quality: float = 65.0
    strong_quality: float = 85.0

    @property
    def version_id(self) -> str:
        return f"{self.context}__{self.factor}__{self.level}"


@dataclass(frozen=True)
class Cell:
    variant: Variant
    map_id: str
    identity_swap: int
    seed_block: int
    seeds_per_cell: int

    @property
    def weak_team_id(self) -> str:
        return TEAM_B if self.identity_swap else TEAM_A

    @property
    def strong_team_id(self) -> str:
        return TEAM_A if self.identity_swap else TEAM_B

    @property
    def cell_id(self) -> str:
        return (
            f"{self.variant.version_id}__{self.map_id}__swap{self.identity_swap}"
            f"__seed{self.seed_block}"
        )


def _numeric_variants(
    priority: int,
    factor: str,
    values: Iterable[float],
    *,
    context: str = "normalized_65v85",
) -> list[Variant]:
    return [
        Variant(
            priority=priority,
            factor=factor,
            level=f"{value:g}",
            level_numeric=float(value),
            context=context,
        )
        for value in values
    ]


def experiment_variants() -> list[Variant]:
    """Ordered design: core talent/plan levers first, texture levers second."""
    variants: list[Variant] = []

    # A single-version symmetry control for measuring the engine's irreducible
    # coin-flip baseline. The caller must set equal weak/strong quality.
    variants.append(Variant(0, "symmetry_baseline", "identical"))

    # Directly maps the user's concern: hold the favorite at 85 and trace the
    # underdog's full talent-response curve through and beyond 65 overall.
    variants += _numeric_variants(0, "weak_overall", (45, 55, 65, 70, 75, 80, 85))

    # Campaign preparation reaches the match engine through these bounded plan
    # inputs.  Negative counter values represent a confidently wrong read.
    variants += _numeric_variants(0, "prep_edge", (0, C.PREP_EDGE_CAP / 2, C.PREP_EDGE_CAP))
    variants += _numeric_variants(
        0, "counter_edge", (-C.COUNTER_STRAT_CAP, 0, C.COUNTER_STRAT_CAP)
    )

    # One skill at a time, with all other skills held at 65 for the underdog.
    for attr_id in ATTRIBUTE_IDS:
        variants += _numeric_variants(0, f"skill_{attr_id}", (45, 65, 85))

    variants += _numeric_variants(0, "agent_mastery", (25, 50, 75, 95))
    variants += _numeric_variants(0, "map_mastery", (25, 50, 75, 95))
    variants += _numeric_variants(0, "form", (20, 50, 80))
    variants += _numeric_variants(0, "morale", (20, 50, 80))
    variants += _numeric_variants(0, "stamina", (40, 70, 100))
    variants += _numeric_variants(0, "confidence", (20, 50, 80))

    # Tactical identity and conditional execution quality.
    for dial in TACTIC_DIALS:
        variants += _numeric_variants(1, f"tactic_{dial}", (0, 25, 50, 75, 100))
    variants += _numeric_variants(1, "chemistry_neutral", (20, 65, 100))
    variants += _numeric_variants(
        1,
        "chemistry_complex_system",
        (20, 65, 100),
        context="normalized_65v85_complex_system",
    )

    # Categorical management choices.
    variants += [
        Variant(1, "focus_target", level)
        for level in ("none", "captain", "highest_id")
    ]
    variants += [
        Variant(1, "agent_selection", level)
        for level in ("auto", "comfort_lock", "unfamiliar_same_role")
    ]
    variants += [
        Variant(1, "roster_shape", level)
        for level in ("balanced", "one_star", "two_stars")
    ]
    variants += _numeric_variants(1, "coach_quality", (20, 50, 80))
    variants += [
        Variant(1, "halftime_talk", level)
        for level in ("none", "reassure", "challenge", "demand_more")
    ]
    variants += [
        Variant(1, "touchline_shout", level)
        for level in ("none", "focus", "play_safe", "encourage", "demand_effort")
    ]
    return variants


def experiment_cells(
    maps: Iterable[str], seed_blocks: Iterable[int], seeds_per_cell: int,
    variants: Iterable[Variant] | None = None,
) -> list[Cell]:
    """Round-robin versions within priorities so a timed run has broad coverage."""
    cells: list[Cell] = []
    variants = list(variants or experiment_variants())
    for priority in sorted({v.priority for v in variants}):
        tier = [v for v in variants if v.priority == priority]
        for map_id in maps:
            for identity_swap in (0, 1):
                for seed_block in seed_blocks:
                    for variant in tier:
                        cells.append(
                            Cell(
                                variant=variant,
                                map_id=map_id,
                                identity_swap=identity_swap,
                                seed_block=seed_block,
                                seeds_per_cell=seeds_per_cell,
                            )
                        )
    return cells


def _set_uniform_quality(gd: Any, team_id: str, quality: float) -> None:
    for pid in gd.teams[team_id].player_ids:
        player = gd.players[pid]
        player.attributes = {attr_id: float(quality) for attr_id in ATTRIBUTE_IDS}


def _normalize_game_data(cell: Cell) -> Any:
    global _BASE_GAME_DATA
    if _BASE_GAME_DATA is None:
        _BASE_GAME_DATA = load_all()
    gd = _BASE_GAME_DATA.model_copy(deep=True)
    weak_id = cell.weak_team_id
    strong_id = cell.strong_team_id

    for team_id in (TEAM_A, TEAM_B):
        team = gd.teams[team_id]
        team.chemistry = 65.0
        team.tactics = TeamTactics()
        team.lineup = TeamLineup()
        for pid in team.player_ids:
            player = gd.players[pid]
            player.form = 50.0
            player.morale = 50.0
            player.stamina = 100.0
            player.confidence = 50.0
            player.personality_tags = []

            original = sorted(player.agent_pool, key=lambda m: (-m.mastery, m.agent_id))
            player.agent_pool = [
                AgentMastery(agent_id=mastery.agent_id, mastery=75.0 if i == 0 else 60.0)
                for i, mastery in enumerate(original)
            ]
            player.map_pool = [
                MapMastery(map_id=map_id, mastery=75.0) for map_id in ALL_MAPS
            ]

    _set_uniform_quality(gd, weak_id, cell.variant.weak_quality)
    _set_uniform_quality(gd, strong_id, cell.variant.strong_quality)
    return gd


def _mirror_team_match_inputs(gd: Any) -> None:
    """Make TEAM_B mechanically identical to TEAM_A while preserving ids."""
    source_team = gd.teams[TEAM_A]
    target_team = gd.teams[TEAM_B]
    source_ids = list(source_team.player_ids)
    target_ids = list(target_team.player_ids)
    if len(source_ids) != len(target_ids):
        raise ValueError("symmetry baseline requires equal roster sizes")
    player_ids = dict(zip(source_ids, target_ids))

    for source_id, target_id in zip(source_ids, target_ids):
        source = gd.players[source_id]
        identity = gd.players[target_id]
        mirrored = source.model_copy(deep=True)
        mirrored.id = target_id
        mirrored.handle = identity.handle
        mirrored.real_name = identity.real_name
        gd.players[target_id] = mirrored

    mirrored_team = source_team.model_copy(deep=True)
    mirrored_team.id = target_team.id
    mirrored_team.name = target_team.name
    mirrored_team.tag = target_team.tag
    mirrored_team.player_ids = target_ids
    mirrored_team.captain_id = player_ids[source_team.captain_id]
    mirrored_team.lineup_ids = [player_ids[pid] for pid in source_team.lineup_ids]
    mirrored_team.igl_experience = {
        player_ids[pid]: value for pid, value in source_team.igl_experience.items()
    }
    mirrored_team.lineup.starters = [
        player_ids[pid] for pid in source_team.lineup.starters
    ]
    mirrored_team.lineup.agents = {
        player_ids[pid]: agent_id
        for pid, agent_id in source_team.lineup.agents.items()
    }
    gd.teams[TEAM_B] = mirrored_team


def _replace_agent_mastery(player: Any, agent_id: str, value: float) -> None:
    found = False
    updated: list[AgentMastery] = []
    for mastery in player.agent_pool:
        if mastery.agent_id == agent_id:
            updated.append(AgentMastery(agent_id=agent_id, mastery=value))
            found = True
        else:
            updated.append(mastery)
    if not found:
        updated.append(AgentMastery(agent_id=agent_id, mastery=value))
    player.agent_pool = updated


def _set_map_mastery(player: Any, map_id: str, value: float) -> None:
    player.map_pool = [
        MapMastery(map_id=m.map_id, mastery=value if m.map_id == map_id else m.mastery)
        for m in player.map_pool
    ]


def _unfamiliar_same_role_agent(gd: Any, player: Any) -> str:
    known = {mastery.agent_id for mastery in player.agent_pool}
    candidates = sorted(
        agent.id
        for agent in gd.agents.values()
        if agent.role == player.role and agent.id not in known
    )
    if not candidates:
        candidates = sorted(agent_id for agent_id in gd.agents if agent_id not in known)
    return candidates[0] if candidates else sorted(gd.agents)[0]


def _build_cell_inputs(cell: Cell) -> tuple[Any, dict[str, TeamMatchPlan], dict[str, Any]]:
    gd = _normalize_game_data(cell)
    weak_id = cell.weak_team_id
    strong_id = cell.strong_team_id
    variant = cell.variant
    factor = variant.factor
    value = variant.level_numeric

    plan_values: dict[str, Any] = {}
    agent_mode = "auto"
    roster_shape = "balanced"

    if factor == "symmetry_baseline":
        if variant.weak_quality != variant.strong_quality:
            raise ValueError("symmetry baseline requires equal weak and strong quality")
        _mirror_team_match_inputs(gd)
    elif factor == "weak_overall":
        assert value is not None
        _set_uniform_quality(gd, weak_id, value)
    elif factor.startswith("skill_"):
        assert value is not None
        attr_id = factor.removeprefix("skill_")
        for pid in gd.teams[weak_id].player_ids:
            gd.players[pid].attributes[attr_id] = value
    elif factor == "prep_edge":
        plan_values["prep_edge"] = float(value)
    elif factor == "counter_edge":
        plan_values["counter_edge"] = float(value)
    elif factor.startswith("tactic_"):
        assert value is not None
        dial = factor.removeprefix("tactic_")
        setattr(gd.teams[weak_id].tactics, dial, value)
    elif factor == "chemistry_neutral":
        gd.teams[weak_id].chemistry = float(value)
    elif factor == "chemistry_complex_system":
        gd.teams[weak_id].chemistry = float(value)
        gd.teams[weak_id].tactics.map_control = 100.0
        gd.teams[weak_id].tactics.util_discipline = 100.0
    elif factor == "focus_target":
        if variant.level == "captain":
            plan_values["focus_target"] = gd.teams[strong_id].captain_id
        elif variant.level == "highest_id":
            plan_values["focus_target"] = sorted(gd.teams[strong_id].player_ids)[-1]
    elif factor == "agent_mastery":
        assert value is not None
        locks: dict[str, str] = {}
        for pid in gd.teams[weak_id].player_ids:
            player = gd.players[pid]
            agent_id = auto_pick_agent(player, gd.agents)
            locks[pid] = agent_id
            _replace_agent_mastery(player, agent_id, value)
        gd.teams[weak_id].lineup.agents = locks
        agent_mode = "comfort_lock"
    elif factor == "map_mastery":
        assert value is not None
        for pid in gd.teams[weak_id].player_ids:
            _set_map_mastery(gd.players[pid], cell.map_id, value)
    elif factor == "agent_selection":
        agent_mode = variant.level
        if variant.level != "auto":
            locks = {}
            for pid in gd.teams[weak_id].player_ids:
                player = gd.players[pid]
                if variant.level == "comfort_lock":
                    locks[pid] = auto_pick_agent(player, gd.agents)
                else:
                    locks[pid] = _unfamiliar_same_role_agent(gd, player)
            gd.teams[weak_id].lineup.agents = locks
    elif factor in {"form", "morale", "stamina", "confidence"}:
        assert value is not None
        for pid in gd.teams[weak_id].player_ids:
            setattr(gd.players[pid], factor, value)
    elif factor == "roster_shape":
        roster_shape = variant.level
        pids = sorted(gd.teams[weak_id].player_ids)
        qualities = {
            "balanced": [65, 65, 65, 65, 65],
            "one_star": [85, 60, 60, 60, 60],
            "two_stars": [80, 80, 55, 55, 55],
        }[variant.level]
        for pid, quality in zip(pids, qualities):
            gd.players[pid].attributes = {
                attr_id: float(quality) for attr_id in ATTRIBUTE_IDS
            }
    elif factor == "coach_quality":
        assert value is not None
        plan_values["coach"] = CoachProfile(
            id=f"{weak_id}:experiment-coach",
            quality=value,
            tactical_knowledge=value,
            analysis=value,
            people_management=value,
            motivation=value,
            adaptability=value,
            system_fit=value,
        )
    elif factor == "halftime_talk" and variant.level != "none":
        plan_values["halftime_talk"] = variant.level
    elif factor == "touchline_shout" and variant.level != "none":
        plan_values["shouts"] = {"loss_streak_3": variant.level}

    plans = {weak_id: TeamMatchPlan(**plan_values)} if plan_values else {}
    plan = plans.get(weak_id)
    inputs = {
        "weak_team_id": weak_id,
        "strong_team_id": strong_id,
        "weak_quality": _team_quality(gd, weak_id),
        "strong_quality": _team_quality(gd, strong_id),
        "weak_chemistry": gd.teams[weak_id].chemistry,
        "weak_form": _team_field_mean(gd, weak_id, "form"),
        "weak_morale": _team_field_mean(gd, weak_id, "morale"),
        "weak_stamina": _team_field_mean(gd, weak_id, "stamina"),
        "weak_confidence": _team_field_mean(gd, weak_id, "confidence"),
        "weak_agent_mode": agent_mode,
        "weak_roster_shape": roster_shape,
        "weak_prep_edge": plan.prep_edge if plan else 0.0,
        "weak_counter_edge": plan.counter_edge if plan else 0.0,
        "weak_focus_target": plan.focus_target if plan else "",
        "weak_coach_quality": plan.coach.quality if plan and plan.coach else 50.0,
        "weak_halftime_talk": plan.halftime_talk if plan and plan.halftime_talk else "none",
        "weak_touchline_shout": (
            plan.shouts.get("loss_streak_3", "none") if plan else "none"
        ),
    }
    for dial in TACTIC_DIALS:
        inputs[f"weak_tactic_{dial}"] = getattr(gd.teams[weak_id].tactics, dial)
    return gd, plans, inputs


def _team_quality(gd: Any, team_id: str) -> float:
    values = [
        sum(gd.players[pid].attributes.values()) / len(gd.players[pid].attributes)
        for pid in gd.teams[team_id].player_ids
    ]
    return sum(values) / len(values)


def _team_field_mean(gd: Any, team_id: str, field: str) -> float:
    values = [getattr(gd.players[pid], field) for pid in gd.teams[team_id].player_ids]
    return sum(values) / len(values)


def _summarize_match(
    cell: Cell,
    seed_index: int,
    seed: int,
    gd: Any,
    plans: dict[str, TeamMatchPlan],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    result = simulate_match_result(
        gd,
        TEAM_A,
        TEAM_B,
        cell.map_id,
        seed,
        plans=plans or None,
        capture_control_events=False,
    )
    weak_id = cell.weak_team_id
    strong_id = cell.strong_team_id
    player_team = {
        pid: team_id
        for team_id in (TEAM_A, TEAM_B)
        for pid in gd.teams[team_id].player_ids
    }
    round_attacker = ""
    weak_attack_rounds = weak_attack_wins = 0
    weak_defense_rounds = weak_defense_wins = 0
    weak_kills = strong_kills = weak_trades = strong_trades = 0
    weak_utility = strong_utility = weak_failed_utility = strong_failed_utility = 0
    weak_plants = strong_plants = weak_defuses = strong_defuses = 0
    weak_timeouts = weak_talks = weak_shouts = 0
    reasons = {"elim": 0, "spike_detonation": 0, "spike_defused": 0, "time": 0}
    max_tick = 0

    for event in result.events:
        max_tick = max(max_tick, int(event.tick))
        if event.type == "round.start":
            round_attacker = event.attacking_team_id
        elif event.type == "round.end":
            reasons[event.reason] += 1
            if round_attacker == weak_id:
                weak_attack_rounds += 1
                weak_attack_wins += int(event.winner_id == weak_id)
            else:
                weak_defense_rounds += 1
                weak_defense_wins += int(event.winner_id == weak_id)
        elif event.type == "round.kill":
            killer_team = player_team[event.killer_id]
            if killer_team == weak_id:
                weak_kills += 1
                weak_trades += int(event.is_trade)
            else:
                strong_kills += 1
                strong_trades += int(event.is_trade)
        elif event.type == "round.utility_used":
            team_id = player_team[event.player_id]
            if team_id == weak_id:
                weak_utility += 1
                weak_failed_utility += int(event.failed)
            else:
                strong_utility += 1
                strong_failed_utility += int(event.failed)
        elif event.type == "round.spike_plant":
            if player_team[event.player_id] == weak_id:
                weak_plants += 1
            else:
                strong_plants += 1
        elif event.type == "round.spike_defuse":
            if player_team[event.player_id] == weak_id:
                weak_defuses += 1
            else:
                strong_defuses += 1
        elif event.type == "round.timeout" and event.team_id == weak_id:
            weak_timeouts += 1
        elif event.type == "round.halftime_talk" and event.team_id == weak_id:
            weak_talks += 1
        elif event.type == "round.touchline_shout" and event.team_id == weak_id:
            weak_shouts += 1

    weak_score = result.score_a if weak_id == TEAM_A else result.score_b
    strong_score = result.score_b if weak_id == TEAM_A else result.score_a
    total_rounds = weak_score + strong_score
    row: dict[str, Any] = {
        "cell_id": cell.cell_id,
        "version_id": cell.variant.version_id,
        "priority": cell.variant.priority,
        "context": cell.variant.context,
        "factor": cell.variant.factor,
        "level": cell.variant.level,
        "level_numeric": "" if cell.variant.level_numeric is None else cell.variant.level_numeric,
        "map_id": cell.map_id,
        "identity_swap": cell.identity_swap,
        "seed_block": cell.seed_block,
        "seed_index": seed_index,
        "seed": seed,
        **inputs,
        "winner_id": result.winner_id,
        "weak_win": int(result.winner_id == weak_id),
        "weak_score": weak_score,
        "strong_score": strong_score,
        "weak_round_margin": weak_score - strong_score,
        "absolute_round_margin": abs(weak_score - strong_score),
        "total_rounds": total_rounds,
        "close_match": int(abs(weak_score - strong_score) <= 2),
        "overtime": int(total_rounds > 24),
        "weak_attack_rounds": weak_attack_rounds,
        "weak_attack_wins": weak_attack_wins,
        "weak_defense_rounds": weak_defense_rounds,
        "weak_defense_wins": weak_defense_wins,
        "weak_kills": weak_kills,
        "strong_kills": strong_kills,
        "weak_trades": weak_trades,
        "strong_trades": strong_trades,
        "weak_utility_uses": weak_utility,
        "strong_utility_uses": strong_utility,
        "weak_failed_utility": weak_failed_utility,
        "strong_failed_utility": strong_failed_utility,
        "weak_plants": weak_plants,
        "strong_plants": strong_plants,
        "weak_defuses": weak_defuses,
        "strong_defuses": strong_defuses,
        "weak_timeouts": weak_timeouts,
        "weak_halftime_talks": weak_talks,
        "weak_touchline_shouts": weak_shouts,
        "end_reason_elim": reasons["elim"],
        "end_reason_detonation": reasons["spike_detonation"],
        "end_reason_defuse": reasons["spike_defused"],
        "end_reason_time": reasons["time"],
        "match_max_tick": max_tick,
    }
    return row


def run_cell(cell: Cell) -> list[dict[str, Any]]:
    gd, plans, inputs = _build_cell_inputs(cell)
    return [
        _summarize_match(
            cell,
            seed_index,
            cell.seed_block
            + seed_index
            + (
                cell.identity_swap * cell.seeds_per_cell
                if cell.variant.factor == "symmetry_baseline"
                else 0
            ),
            gd,
            plans,
            inputs,
        )
        for seed_index in range(cell.seeds_per_cell)
    ]


def _completed_cells(dataset_path: Path, seeds_per_cell: int) -> set[str]:
    if not dataset_path.exists():
        return set()
    counts: dict[str, int] = {}
    with dataset_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cell_id = row["cell_id"]
            counts[cell_id] = counts.get(cell_id, 0) + 1
    return {cell_id for cell_id, count in counts.items() if count >= seeds_per_cell}


def _write_summary(dataset_path: Path, summary_path: Path) -> None:
    groups: dict[tuple[str, ...], dict[str, float]] = {}
    keys = (
        "version_id",
        "factor",
        "level",
        "map_id",
        "identity_swap",
        "seed_block",
    )
    with dataset_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = tuple(row[k] for k in keys)
            group = groups.setdefault(
                key,
                {
                    "matches": 0,
                    "weak_wins": 0,
                    "weak_round_margin_sum": 0,
                    "close_matches": 0,
                    "overtimes": 0,
                },
            )
            group["matches"] += 1
            group["weak_wins"] += int(row["weak_win"])
            group["weak_round_margin_sum"] += int(row["weak_round_margin"])
            group["close_matches"] += int(row["close_match"])
            group["overtimes"] += int(row["overtime"])

    fields = list(keys) + [
        "matches",
        "weak_wins",
        "weak_win_rate",
        "mean_weak_round_margin",
        "close_match_rate",
        "overtime_rate",
    ]
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key, group in sorted(groups.items()):
            n = group["matches"]
            writer.writerow(
                {
                    **dict(zip(keys, key)),
                    "matches": int(n),
                    "weak_wins": int(group["weak_wins"]),
                    "weak_win_rate": group["weak_wins"] / n,
                    "mean_weak_round_margin": group["weak_round_margin_sum"] / n,
                    "close_match_rate": group["close_matches"] / n,
                    "overtime_rate": group["overtimes"] / n,
                }
            )


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], text=True, encoding="utf-8", errors="replace"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="artifact directory (resumable)")
    parser.add_argument("--minutes", type=float, default=0.0, help="submission time budget; 0 runs the full design")
    parser.add_argument("--workers", type=int, default=min(14, os.cpu_count() or 1))
    parser.add_argument("--seeds-per-cell", type=int, default=30)
    parser.add_argument(
        "--seed-blocks",
        default="0,10000,20000",
        help="comma-separated starting seeds",
    )
    parser.add_argument("--maps", nargs="+", choices=ALL_MAPS, default=list(ALL_MAPS))
    parser.add_argument("--limit-cells", type=int, default=0, help="smoke/debug limit")
    parser.add_argument("--factors", default="", help="comma-separated factor ids")
    parser.add_argument(
        "--levels-json",
        default="{}",
        help="JSON object mapping factor ids to selected or custom levels",
    )
    parser.add_argument("--weak-quality", type=float)
    parser.add_argument("--strong-quality", type=float)
    parser.add_argument("--context", default="")
    parser.add_argument("--describe", action="store_true")
    return parser.parse_args()


def _selected_variants(args: argparse.Namespace) -> list[Variant]:
    variants = experiment_variants()
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
                replace(
                    templates[0],
                    level=f"{float(value):g}",
                    level_numeric=float(value),
                )
                for value in values
            )
        else:
            by_level = {template.level: template for template in templates}
            unknown_levels = {str(value) for value in values} - set(by_level)
            if unknown_levels:
                raise SystemExit(f"unknown levels for {factor}: {sorted(unknown_levels)}")
            rebuilt.extend(by_level[str(value)] for value in values)
    variants = rebuilt

    context = args.context or (
        f"normalized_{args.weak_quality:g}v{args.strong_quality:g}"
        if args.weak_quality is not None and args.strong_quality is not None
        else ""
    )
    return [
        replace(
            variant,
            weak_quality=(
                args.weak_quality if args.weak_quality is not None else variant.weak_quality
            ),
            strong_quality=(
                args.strong_quality if args.strong_quality is not None else variant.strong_quality
            ),
            context=context or variant.context,
        )
        for variant in variants
    ]


def main() -> int:
    args = parse_args()
    variants = _selected_variants(args)
    if args.describe:
        print(json.dumps({"suite": "core", "design": [asdict(v) for v in variants]}, indent=2))
        return 0
    seed_blocks = tuple(int(value) for value in args.seed_blocks.split(","))
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or Path("runs") / f"causal-match-{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "matches.csv"
    summary_path = out_dir / "cell_summary.csv"
    manifest_path = out_dir / "manifest.json"

    cells = experiment_cells(args.maps, seed_blocks, args.seeds_per_cell, variants)
    if args.limit_cells:
        cells = cells[: args.limit_cells]
    completed = _completed_cells(dataset_path, args.seeds_per_cell)
    pending = [cell for cell in cells if cell.cell_id not in completed]

    manifest: dict[str, Any] = {
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "git_sha": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "python": sys.version,
        "command": sys.argv,
        "maps": list(args.maps),
        "seed_blocks": list(seed_blocks),
        "seeds_per_cell": args.seeds_per_cell,
        "workers": args.workers,
        "minutes": args.minutes,
        "versions": len(variants),
        "planned_cells": len(cells),
        "planned_matches": len(cells) * args.seeds_per_cell,
        "resumed_completed_cells": len(completed),
        "constants": {
            "prep_edge_cap": C.PREP_EDGE_CAP,
            "counter_strat_cap": C.COUNTER_STRAT_CAP,
            "counter_strat_span": C.COUNTER_STRAT_SPAN,
            "focus_target_edge": C.FOCUS_TARGET_EDGE,
            "focus_off_malus": C.FOCUS_OFF_MALUS,
            "duel_elo_scale": C.DUEL_ELO_SCALE,
            "day_form_base_sigma": C.DAY_FORM_BASE_SIGMA,
            "team_form_sigma": C.TEAM_FORM_SIGMA,
            "exec_mod_cap": C.EXEC_MOD_CAP,
        },
        "design": [asdict(variant) for variant in variants],
        "output_files": {
            "matches": str(dataset_path.resolve()),
            "cell_summary": str(summary_path.resolve()),
        },
    }
    _write_manifest(manifest_path, manifest)

    deadline = time.monotonic() + args.minutes * 60 if args.minutes > 0 else None
    started = time.monotonic()
    rows_written = 0
    cells_written = 0
    next_progress_cell = 1
    errors: list[str] = []
    writer: csv.DictWriter[str] | None = None
    dataset_handle = dataset_path.open("a", newline="", encoding="utf-8")
    try:
        in_flight: dict[Any, Cell] = {}
        cell_iter = iter(pending)
        submission_open = True
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            while submission_open or in_flight:
                while submission_open and len(in_flight) < args.workers * 2:
                    if deadline is not None and time.monotonic() >= deadline:
                        submission_open = False
                        break
                    try:
                        cell = next(cell_iter)
                    except StopIteration:
                        submission_open = False
                        break
                    in_flight[pool.submit(run_cell, cell)] = cell

                if not in_flight:
                    break
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    cell = in_flight.pop(future)
                    try:
                        rows = future.result()
                    except Exception as exc:  # preserve the rest of a long run
                        errors.append(f"{cell.cell_id}: {type(exc).__name__}: {exc}")
                        print(f"ERROR {errors[-1]}", flush=True)
                        continue
                    if rows and writer is None:
                        writer = csv.DictWriter(dataset_handle, fieldnames=list(rows[0]))
                        if dataset_path.stat().st_size == 0:
                            writer.writeheader()
                    assert writer is not None
                    writer.writerows(rows)
                    dataset_handle.flush()
                    rows_written += len(rows)
                    cells_written += 1

                elapsed = time.monotonic() - started
                if cells_written >= next_progress_cell:
                    rate = rows_written / max(elapsed, 0.001)
                    print(
                        f"progress cells={cells_written}/{len(pending)} "
                        f"matches={rows_written} rate={rate:.1f}/s "
                        f"elapsed={elapsed / 60:.1f}m errors={len(errors)}",
                        flush=True,
                    )
                    next_progress_cell = max(4, cells_written + max(1, args.workers))
    finally:
        dataset_handle.close()

    if dataset_path.exists() and dataset_path.stat().st_size:
        _write_summary(dataset_path, summary_path)
    elapsed = time.monotonic() - started
    final_completed = _completed_cells(dataset_path, args.seeds_per_cell)
    manifest.update(
        {
            "status": "complete" if len(final_completed) >= len(cells) else "time_budget_complete",
            "finished_at_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": elapsed,
            "new_cells": cells_written,
            "new_matches": rows_written,
            "completed_cells": len(final_completed),
            "completed_matches": len(final_completed) * args.seeds_per_cell,
            "errors": errors,
        }
    )
    _write_manifest(manifest_path, manifest)
    print(
        f"finished status={manifest['status']} matches={manifest['completed_matches']} "
        f"cells={manifest['completed_cells']} elapsed={elapsed / 60:.1f}m "
        f"out={out_dir.resolve()}",
        flush=True,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
