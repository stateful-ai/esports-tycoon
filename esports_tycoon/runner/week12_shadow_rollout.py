"""Week-12 shadow rollout artifact for candidate player policies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from esports_tycoon.runner.week12_model_prep import (
    WEEK12_MODEL_PREP_FILENAME,
    Week12ModelPrep,
    Week12ModelPrepTarget,
)

WEEK12_SHADOW_ROLLOUT_FILENAME = "week12_shadow_rollout.json"
WEEK12_TRAINING_QUEUE_FILENAME = "week12_training_queue.json"

Week12ShadowDecision = Literal[
    "promote_to_scrim",
    "shadow_again",
    "hold_for_review",
    "collect_more_replay",
]
Week12EvaluationResult = Literal["pass", "watch", "fail"]


@dataclass(frozen=True)
class Week12ShadowTrial:
    """One deterministic shadow comparison between baseline and candidate policy."""

    agent_id: str
    candidate_policy_id: str
    scenario_model_slot: str
    training_mode: str
    readiness_band: str
    episodes: int
    baseline_reward: int
    candidate_reward: int
    reward_delta: int
    risk_delta: int
    objective_delta: int
    evaluation_result: Week12EvaluationResult
    decision: Week12ShadowDecision
    decision_reason: str
    next_training_hook: str


@dataclass(frozen=True)
class Week12ShadowRollout:
    """A model-ready shadow rollout batch derived from Week-12 model prep."""

    sim_id: str
    selected_plan: str
    outcome_id: str
    result_tier: str
    trials: tuple[Week12ShadowTrial, ...]
    rollout_summary: tuple[str, ...]
    next_hook: str


def _objective_delta(target: Week12ModelPrepTarget) -> int:
    base = max(1, target.epoch_delta)
    if target.training_mode == "objective_pressure_tuning":
        base += max(1, (65 - target.objective_pressure + 9) // 10)
    if target.training_mode == "trait_policy_finetune":
        base += 2
    if target.readiness_band == "collect_more_replay":
        base -= 1
    return max(0, min(12, base))


def _risk_delta(target: Week12ModelPrepTarget) -> int:
    if target.training_mode == "risk_regularization":
        return -min(14, target.epoch_delta * 2 + max(0, target.risk_index - 50) // 4)
    if target.readiness_band == "coach_review":
        return -min(6, max(1, target.epoch_delta))
    if target.training_mode == "shadow_rollout":
        return -min(4, max(1, target.epoch_delta))
    return min(5, max(0, target.risk_index - 55) // 5)


def _decision(
    *,
    target: Week12ModelPrepTarget,
    reward_delta: int,
    risk_delta: int,
    objective_delta: int,
) -> tuple[Week12EvaluationResult, Week12ShadowDecision, str]:
    if target.readiness_band == "collect_more_replay":
        return (
            "fail",
            "collect_more_replay",
            "sample count is too low for a promotion decision",
        )
    if target.readiness_band == "coach_review" and reward_delta < 2:
        return (
            "watch",
            "hold_for_review",
            "candidate needs coach review before scrim promotion",
        )
    if reward_delta >= 2 and risk_delta <= 0 and objective_delta >= 1:
        return (
            "pass",
            "promote_to_scrim",
            "candidate improves reward while holding risk stable",
        )
    if reward_delta >= 0:
        return (
            "watch",
            "shadow_again",
            "candidate is non-regressing but needs another shadow batch",
        )
    return (
        "fail",
        "hold_for_review",
        "candidate regresses against deterministic replay reward",
    )


def _trial_for_target(target: Week12ModelPrepTarget) -> Week12ShadowTrial:
    objective_delta = _objective_delta(target)
    risk_delta = _risk_delta(target)
    readiness_penalty = 2 if target.readiness_band == "collect_more_replay" else 0
    reward_delta = (
        target.epoch_delta
        + objective_delta // 2
        + max(0, -risk_delta) // 3
        - max(0, risk_delta)
        - readiness_penalty
    )
    baseline_reward = target.reward_total
    candidate_reward = baseline_reward + reward_delta
    evaluation_result, decision, decision_reason = _decision(
        target=target,
        reward_delta=reward_delta,
        risk_delta=risk_delta,
        objective_delta=objective_delta,
    )
    return Week12ShadowTrial(
        agent_id=target.agent_id,
        candidate_policy_id=target.candidate_policy_id,
        scenario_model_slot=target.scenario_model_slot,
        training_mode=target.training_mode,
        readiness_band=target.readiness_band,
        episodes=max(2, target.sample_count + target.epoch_delta),
        baseline_reward=baseline_reward,
        candidate_reward=candidate_reward,
        reward_delta=reward_delta,
        risk_delta=risk_delta,
        objective_delta=objective_delta,
        evaluation_result=evaluation_result,
        decision=decision,
        decision_reason=decision_reason,
        next_training_hook=(
            f"{target.agent_id}:{decision}:{target.candidate_policy_id}:"
            f"episodes={max(2, target.sample_count + target.epoch_delta)}"
        ),
    )


def resolve_week12_shadow_rollout(model_prep: Week12ModelPrep) -> Week12ShadowRollout:
    """Resolve deterministic shadow trials from Week-12 model-prep targets."""
    trials = tuple(_trial_for_target(target) for target in model_prep.targets)
    promote_count = len([trial for trial in trials if trial.decision == "promote_to_scrim"])
    watch_count = len([trial for trial in trials if trial.evaluation_result == "watch"])
    return Week12ShadowRollout(
        sim_id=model_prep.sim_id,
        selected_plan=model_prep.selected_plan,
        outcome_id=model_prep.outcome_id,
        result_tier=model_prep.result_tier,
        trials=trials,
        rollout_summary=(
            f"{promote_count} candidate policies are ready for scrim promotion.",
            f"{watch_count} candidates stay in shadow evaluation.",
            "Scenario model slots remain placeholders until authenticated model ids are attached.",
        ),
        next_hook="Week 12 can branch into model training, coach review, or scrim promotion.",
    )


def _shadow_trial_to_dict(trial: Week12ShadowTrial) -> dict[str, Any]:
    return {
        "agent_id": trial.agent_id,
        "candidate_policy_id": trial.candidate_policy_id,
        "scenario_model_slot": trial.scenario_model_slot,
        "training_mode": trial.training_mode,
        "readiness_band": trial.readiness_band,
        "episodes": trial.episodes,
        "baseline_reward": trial.baseline_reward,
        "candidate_reward": trial.candidate_reward,
        "reward_delta": trial.reward_delta,
        "risk_delta": trial.risk_delta,
        "objective_delta": trial.objective_delta,
        "evaluation_result": trial.evaluation_result,
        "decision": trial.decision,
        "decision_reason": trial.decision_reason,
        "next_training_hook": trial.next_training_hook,
    }


def week12_shadow_rollout_to_dict(rollout: Week12ShadowRollout) -> dict[str, Any]:
    """Dictionary form used by JSON export and the shadow-rollout page."""
    return {
        "artifact_type": "week12_shadow_rollout",
        "checkpoint": "week12_shadow_rollout",
        "schema_version": 1,
        "source_artifact": WEEK12_MODEL_PREP_FILENAME,
        "source_artifacts": {
            "week12_model_prep": WEEK12_MODEL_PREP_FILENAME,
        },
        "week": 12,
        "route": "/week12/shadow-rollout",
        "sim_id": rollout.sim_id,
        "selected_plan": rollout.selected_plan,
        "outcome_id": rollout.outcome_id,
        "result_tier": rollout.result_tier,
        "trial_count": len(rollout.trials),
        "trials": [_shadow_trial_to_dict(trial) for trial in rollout.trials],
        "rollout_contract": {
            "format": "shadow_rollout_batch_v1",
            "source_model_prep_format": "model_prep_batch_v1",
            "trial_unit": "trials[]",
            "candidate_policy_field": "trials[].candidate_policy_id",
            "model_reference_field": "trials[].scenario_model_slot",
            "promotion_field": "trials[].decision",
            "evaluation_fields": [
                "baseline_reward",
                "candidate_reward",
                "reward_delta",
                "risk_delta",
                "objective_delta",
            ],
        },
        "rollout_summary": list(rollout.rollout_summary),
        "next_hook": rollout.next_hook,
        "stops_before": "week12_training_queue",
        "next_artifact": WEEK12_TRAINING_QUEUE_FILENAME,
    }


def render_week12_shadow_rollout_json(rollout: Week12ShadowRollout) -> str:
    """Canonical JSON export for the Week-12 shadow rollout."""
    return json.dumps(
        {"week12_shadow_rollout": week12_shadow_rollout_to_dict(rollout)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


def week12_shadow_rollout_from_json(text: str) -> Week12ShadowRollout:
    """Parse a written ``week12_shadow_rollout.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week12_shadow_rollout JSON is malformed") from exc
    rollout = data.get("week12_shadow_rollout") if isinstance(data, dict) else None
    if not isinstance(rollout, dict):
        raise ValueError("week12_shadow_rollout JSON must contain a week12_shadow_rollout object")
    if rollout.get("source_artifact") != WEEK12_MODEL_PREP_FILENAME:
        raise ValueError("week12_shadow_rollout source_artifact must be week12_model_prep.json")
    trials_raw = rollout.get("trials")
    if not isinstance(trials_raw, list) or not trials_raw:
        raise ValueError("week12_shadow_rollout JSON must include trials")
    if rollout.get("next_artifact") not in (None, WEEK12_TRAINING_QUEUE_FILENAME):
        raise ValueError(
            "week12_shadow_rollout next_artifact must be null or week12_training_queue.json"
        )
    trials = tuple(
        Week12ShadowTrial(
            agent_id=str(trial.get("agent_id", "")),
            candidate_policy_id=str(trial.get("candidate_policy_id", "")),
            scenario_model_slot=str(trial.get("scenario_model_slot", "")),
            training_mode=str(trial.get("training_mode", "")),
            readiness_band=str(trial.get("readiness_band", "")),
            episodes=int(trial.get("episodes", 0)),
            baseline_reward=int(trial.get("baseline_reward", 0)),
            candidate_reward=int(trial.get("candidate_reward", 0)),
            reward_delta=int(trial.get("reward_delta", 0)),
            risk_delta=int(trial.get("risk_delta", 0)),
            objective_delta=int(trial.get("objective_delta", 0)),
            evaluation_result=(
                trial.get("evaluation_result")
                if trial.get("evaluation_result") in ("pass", "watch", "fail")
                else "watch"
            ),
            decision=(
                trial.get("decision")
                if trial.get("decision")
                in ("promote_to_scrim", "shadow_again", "hold_for_review", "collect_more_replay")
                else "shadow_again"
            ),
            decision_reason=str(trial.get("decision_reason", "")),
            next_training_hook=str(trial.get("next_training_hook", "")),
        )
        for trial in trials_raw
        if isinstance(trial, dict)
    )
    return Week12ShadowRollout(
        sim_id=str(rollout.get("sim_id", "")),
        selected_plan=str(rollout.get("selected_plan", "")),
        outcome_id=str(rollout.get("outcome_id", "")),
        result_tier=str(rollout.get("result_tier", "")),
        trials=trials,
        rollout_summary=tuple(
            str(item) for item in rollout.get("rollout_summary", []) if isinstance(item, str)
        ),
        next_hook=str(rollout.get("next_hook", "")),
    )
