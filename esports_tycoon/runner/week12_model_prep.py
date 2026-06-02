"""Week-12 model-prep artifact derived from the Week-11 RL dataset."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from esports_tycoon.runner.week11_match_sim import (
    WEEK11_TRAINING_DATASET_FILENAME,
    Week11TrainingDataset,
    Week11TrainingSample,
)

WEEK12_MODEL_PREP_FILENAME = "week12_model_prep.json"
WEEK12_SHADOW_ROLLOUT_FILENAME = "week12_shadow_rollout.json"

Week12TrainingMode = Literal[
    "behavior_clone_warm_start",
    "objective_pressure_tuning",
    "risk_regularization",
    "trait_policy_finetune",
    "shadow_rollout",
]
Week12ReadinessBand = Literal["collect_more_replay", "coach_review", "ready_for_shadow"]


@dataclass(frozen=True)
class Week12ModelPrepTarget:
    """One player-policy target prepared for future Scenario/RL training."""

    agent_id: str
    from_policy_id: str
    candidate_policy_id: str
    source_drill_id: str
    sample_count: int
    reward_total: int
    reward_mean_x100: int
    risk_index: int
    objective_pressure: int
    component_totals: dict[str, int]
    dominant_failure_mode: str
    risk_spike_count: int
    epoch_delta: int
    priority_score: int
    training_mode: Week12TrainingMode
    readiness_band: Week12ReadinessBand
    scenario_model_slot: str
    rl_objective: str
    evaluation_gate: str
    prompt_seed: str


@dataclass(frozen=True)
class Week12ModelPrep:
    """Model-lab handoff that turns offline samples into trainable policy targets."""

    sim_id: str
    selected_plan: str
    outcome_id: str
    result_tier: str
    dataset_sample_count: int
    targets: tuple[Week12ModelPrepTarget, ...]
    prep_notes: tuple[str, ...]
    next_hook: str


def _mean_int(values: list[int]) -> int:
    if not values:
        return 0
    return (sum(values) + len(values) // 2) // len(values)


def _mean_x100(values: list[int]) -> int:
    if not values:
        return 0
    total = sum(value * 100 for value in values)
    if total >= 0:
        return (total + len(values) // 2) // len(values)
    return -((-total + len(values) // 2) // len(values))


def _training_mode(
    *,
    reward_mean_x100: int,
    risk_index: int,
    objective_pressure: int,
    epoch_delta: int,
) -> Week12TrainingMode:
    if risk_index >= 58:
        return "risk_regularization"
    if objective_pressure < 60:
        return "objective_pressure_tuning"
    if reward_mean_x100 <= 0:
        return "behavior_clone_warm_start"
    if epoch_delta >= 4:
        return "trait_policy_finetune"
    return "shadow_rollout"


def _readiness_band(
    *,
    sample_count: int,
    reward_mean_x100: int,
    risk_index: int,
) -> Week12ReadinessBand:
    if sample_count < 2:
        return "collect_more_replay"
    if reward_mean_x100 < 0 or risk_index >= 70:
        return "coach_review"
    return "ready_for_shadow"


def _rl_objective(mode: Week12TrainingMode) -> str:
    return {
        "behavior_clone_warm_start": "clone stable replay actions before reward tuning",
        "objective_pressure_tuning": "raise objective pressure without breaking default integrity",
        "risk_regularization": "penalize overpeek states and late trade windows",
        "trait_policy_finetune": "fine tune the trait policy on high-reward transitions",
        "shadow_rollout": "run the candidate policy beside the deterministic policy",
    }[mode]


def _evaluation_gate(mode: Week12TrainingMode) -> str:
    return {
        "behavior_clone_warm_start": "offline reward_mean_x100 >= 0",
        "objective_pressure_tuning": "objective_pressure >= 65 across held-out replay frames",
        "risk_regularization": "risk_index <= 55 while preserving trade_window",
        "trait_policy_finetune": "candidate beats deterministic reward total in shadow replay",
        "shadow_rollout": "no regression against deterministic replay telemetry",
    }[mode]


def _prompt_seed(agent_id: str, mode: Week12TrainingMode) -> str:
    return (
        f"{agent_id} 5v5 tactical shooter policy: {mode.replace('_', ' ')}, "
        "team-first spacing, trait-aware tempo, readable broadcast actions"
    )


def _component_totals(samples: list[Week11TrainingSample]) -> dict[str, int]:
    totals = {
        "round_win": 0,
        "trade_quality": 0,
        "utility_timing": 0,
        "space_gained": 0,
        "overpeek_penalty": 0,
        "default_integrity": 0,
    }
    for sample in samples:
        for key in totals:
            totals[key] += int(sample.reward_components.get(key, 0))
    return totals


def _dominant_failure_mode(
    *,
    component_totals: dict[str, int],
    risk_spike_count: int,
    objective_pressure: int,
) -> str:
    if component_totals.get("overpeek_penalty", 0) < 0:
        return "overpeek_penalty"
    if risk_spike_count:
        return "risk_spike"
    if objective_pressure < 60:
        return "objective_pressure"
    weakest = min(component_totals, key=lambda key: component_totals[key])
    if component_totals[weakest] <= 0:
        return weakest
    return "none"


def resolve_week12_model_prep(dataset: Week11TrainingDataset) -> Week12ModelPrep:
    """Aggregate the offline RL dataset into model-prep targets for Week 12."""
    samples_by_agent: dict[str, list[Week11TrainingSample]] = defaultdict(list)
    for sample in dataset.samples:
        samples_by_agent[sample.agent_id].append(sample)

    targets: list[Week12ModelPrepTarget] = []
    for target in dataset.policy_targets:
        agent_id = str(target.get("agent_id", ""))
        samples = samples_by_agent.get(agent_id, [])
        rewards = [sample.reward for sample in samples]
        risk_values = [sample.telemetry.risk_index for sample in samples]
        objective_values = [sample.telemetry.objective_pressure for sample in samples]
        epoch_delta = int(target.get("epoch_delta", 0))
        reward_mean_x100 = _mean_x100(rewards)
        risk_index = _mean_int(risk_values)
        objective_pressure = _mean_int(objective_values)
        component_totals = _component_totals(samples)
        risk_spike_count = len([sample for sample in samples if sample.telemetry.risk_index >= 58])
        dominant_failure_mode = _dominant_failure_mode(
            component_totals=component_totals,
            risk_spike_count=risk_spike_count,
            objective_pressure=objective_pressure,
        )
        mode = _training_mode(
            reward_mean_x100=reward_mean_x100,
            risk_index=risk_index,
            objective_pressure=objective_pressure,
            epoch_delta=epoch_delta,
        )
        readiness_band = _readiness_band(
            sample_count=len(samples),
            reward_mean_x100=reward_mean_x100,
            risk_index=risk_index,
        )
        candidate_policy_id = str(target.get("to_policy_id", ""))
        priority_score = (
            epoch_delta * 20
            + max(0, 60 - objective_pressure)
            + max(0, risk_index - 45)
            + max(0, 100 - reward_mean_x100)
        )
        targets.append(
            Week12ModelPrepTarget(
                agent_id=agent_id,
                from_policy_id=str(target.get("from_policy_id", "")),
                candidate_policy_id=candidate_policy_id,
                source_drill_id=str(target.get("source_drill_id", "")),
                sample_count=len(samples),
                reward_total=sum(rewards),
                reward_mean_x100=reward_mean_x100,
                risk_index=risk_index,
                objective_pressure=objective_pressure,
                component_totals=component_totals,
                dominant_failure_mode=dominant_failure_mode,
                risk_spike_count=risk_spike_count,
                epoch_delta=epoch_delta,
                priority_score=priority_score,
                training_mode=mode,
                readiness_band=readiness_band,
                scenario_model_slot=f"scenario://week12/{agent_id}/{candidate_policy_id}",
                rl_objective=_rl_objective(mode),
                evaluation_gate=_evaluation_gate(mode),
                prompt_seed=_prompt_seed(agent_id, mode),
            )
        )

    return Week12ModelPrep(
        sim_id=dataset.sim_id,
        selected_plan=dataset.selected_plan,
        outcome_id=dataset.outcome_id,
        result_tier=dataset.result_tier,
        dataset_sample_count=len(dataset.samples),
        targets=tuple(sorted(targets, key=lambda item: (-item.priority_score, item.agent_id))),
        prep_notes=(
            "Model prep aggregates offline RL samples into trainable player-policy targets.",
            "scenario_model_slot is a placeholder until Scenario-authenticated model ids are attached.",
            "Epoch delta remains a skill proxy; future learned policies can replace candidate_policy_id.",
        ),
        next_hook="Week 12 opens with model-prep targets ready for shadow rollout or training.",
    )


def _model_prep_target_to_dict(target: Week12ModelPrepTarget) -> dict[str, Any]:
    return {
        "agent_id": target.agent_id,
        "from_policy_id": target.from_policy_id,
        "candidate_policy_id": target.candidate_policy_id,
        "source_drill_id": target.source_drill_id,
        "sample_count": target.sample_count,
        "reward_total": target.reward_total,
        "reward_mean_x100": target.reward_mean_x100,
        "risk_index": target.risk_index,
        "objective_pressure": target.objective_pressure,
        "component_totals": dict(target.component_totals),
        "dominant_failure_mode": target.dominant_failure_mode,
        "risk_spike_count": target.risk_spike_count,
        "epoch_delta": target.epoch_delta,
        "priority_score": target.priority_score,
        "training_mode": target.training_mode,
        "readiness_band": target.readiness_band,
        "scenario_model_slot": target.scenario_model_slot,
        "rl_objective": target.rl_objective,
        "evaluation_gate": target.evaluation_gate,
        "prompt_seed": target.prompt_seed,
    }


def week12_model_prep_to_dict(prep: Week12ModelPrep) -> dict[str, Any]:
    """Dictionary form used by JSON export and the Week-12 model lab."""
    return {
        "artifact_type": "week12_model_prep",
        "checkpoint": "week12_model_prep",
        "schema_version": 1,
        "source_artifact": WEEK11_TRAINING_DATASET_FILENAME,
        "source_artifacts": {
            "week11_training_dataset": WEEK11_TRAINING_DATASET_FILENAME,
        },
        "week": 12,
        "route": "/week12/model-prep",
        "sim_id": prep.sim_id,
        "selected_plan": prep.selected_plan,
        "outcome_id": prep.outcome_id,
        "result_tier": prep.result_tier,
        "dataset_sample_count": prep.dataset_sample_count,
        "target_count": len(prep.targets),
        "targets": [_model_prep_target_to_dict(target) for target in prep.targets],
        "prep_contract": {
            "format": "model_prep_batch_v1",
            "source_dataset_format": "offline_rl_transition_v1",
            "target_unit": "targets[]",
            "model_reference_field": "targets[].scenario_model_slot",
            "candidate_policy_field": "targets[].candidate_policy_id",
            "training_modes": [
                "behavior_clone_warm_start",
                "objective_pressure_tuning",
                "risk_regularization",
                "trait_policy_finetune",
                "shadow_rollout",
            ],
            "evaluation_fields": [
                "sample_count",
                "reward_mean_x100",
                "risk_index",
                "objective_pressure",
                "component_totals",
                "dominant_failure_mode",
                "risk_spike_count",
                "evaluation_gate",
            ],
        },
        "prep_notes": list(prep.prep_notes),
        "next_hook": prep.next_hook,
        "stops_before": "week12_shadow_rollout",
        "next_artifact": WEEK12_SHADOW_ROLLOUT_FILENAME,
    }


def render_week12_model_prep_json(prep: Week12ModelPrep) -> str:
    """Canonical JSON export for the Week-12 model-prep batch."""
    return json.dumps(
        {"week12_model_prep": week12_model_prep_to_dict(prep)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


def week12_model_prep_from_json(text: str) -> Week12ModelPrep:
    """Parse a written ``week12_model_prep.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week12_model_prep JSON is malformed") from exc
    prep = data.get("week12_model_prep") if isinstance(data, dict) else None
    if not isinstance(prep, dict):
        raise ValueError("week12_model_prep JSON must contain a week12_model_prep object")
    if prep.get("source_artifact") != WEEK11_TRAINING_DATASET_FILENAME:
        raise ValueError("week12_model_prep source_artifact must be week11_training_dataset.json")
    targets_raw = prep.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ValueError("week12_model_prep JSON must include targets")
    if prep.get("next_artifact") not in (None, WEEK12_SHADOW_ROLLOUT_FILENAME):
        raise ValueError("week12_model_prep next_artifact must be null or week12_shadow_rollout.json")
    targets = tuple(
        Week12ModelPrepTarget(
            agent_id=str(target.get("agent_id", "")),
            from_policy_id=str(target.get("from_policy_id", "")),
            candidate_policy_id=str(target.get("candidate_policy_id", "")),
            source_drill_id=str(target.get("source_drill_id", "")),
            sample_count=int(target.get("sample_count", 0)),
            reward_total=int(target.get("reward_total", 0)),
            reward_mean_x100=int(target.get("reward_mean_x100", 0)),
            risk_index=int(target.get("risk_index", 0)),
            objective_pressure=int(target.get("objective_pressure", 0)),
            component_totals={
                str(key): int(value)
                for key, value in target.get("component_totals", {}).items()
                if isinstance(key, str) and isinstance(value, int)
            }
            if isinstance(target.get("component_totals"), dict)
            else {},
            dominant_failure_mode=str(target.get("dominant_failure_mode", "")),
            risk_spike_count=int(target.get("risk_spike_count", 0)),
            epoch_delta=int(target.get("epoch_delta", 0)),
            priority_score=int(target.get("priority_score", 0)),
            training_mode=(
                target.get("training_mode")
                if target.get("training_mode")
                in (
                    "behavior_clone_warm_start",
                    "objective_pressure_tuning",
                    "risk_regularization",
                    "trait_policy_finetune",
                    "shadow_rollout",
                )
                else "shadow_rollout"
            ),
            readiness_band=(
                target.get("readiness_band")
                if target.get("readiness_band")
                in ("collect_more_replay", "coach_review", "ready_for_shadow")
                else "collect_more_replay"
            ),
            scenario_model_slot=str(target.get("scenario_model_slot", "")),
            rl_objective=str(target.get("rl_objective", "")),
            evaluation_gate=str(target.get("evaluation_gate", "")),
            prompt_seed=str(target.get("prompt_seed", "")),
        )
        for target in targets_raw
        if isinstance(target, dict)
    )
    return Week12ModelPrep(
        sim_id=str(prep.get("sim_id", "")),
        selected_plan=str(prep.get("selected_plan", "")),
        outcome_id=str(prep.get("outcome_id", "")),
        result_tier=str(prep.get("result_tier", "")),
        dataset_sample_count=int(prep.get("dataset_sample_count", 0)),
        targets=targets,
        prep_notes=tuple(str(item) for item in prep.get("prep_notes", []) if isinstance(item, str)),
        next_hook=str(prep.get("next_hook", "")),
    )
