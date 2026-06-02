"""Week-12 RL training queue derived from shadow rollout decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from esports_tycoon.runner.week12_shadow_rollout import (
    WEEK12_SHADOW_ROLLOUT_FILENAME,
    WEEK12_TRAINING_QUEUE_FILENAME,
    Week12ShadowRollout,
    Week12ShadowTrial,
)

Week12QueueAction = Literal[
    "promote_scrim_policy",
    "train_shadow_candidate",
    "coach_review_gate",
    "collect_replay_batch",
]
Week12QueueStatus = Literal[
    "ready_for_scrim",
    "queued_for_training",
    "blocked_by_review",
    "needs_replay",
]


@dataclass(frozen=True)
class Week12TrainingQueueJob:
    """One future RL job or gate produced from a shadow-rollout trial."""

    job_id: str
    agent_id: str
    candidate_policy_id: str
    scenario_model_slot: str
    source_decision: str
    queue_action: Week12QueueAction
    queue_status: Week12QueueStatus
    learning_phase: str
    epoch_budget: int
    rollout_episode_budget: int
    replay_batch_target: int
    reward_weight_x100: int
    risk_penalty_x100: int
    objective_weight_x100: int
    exploration_rate_x100: int
    priority_score: int
    approval_gate: str
    stop_condition: str
    scenario_asset_slot: str
    coach_note: str


@dataclass(frozen=True)
class Week12TrainingQueue:
    """Queue contract that a future RL runner or Scenario model tuner can consume."""

    sim_id: str
    selected_plan: str
    outcome_id: str
    result_tier: str
    jobs: tuple[Week12TrainingQueueJob, ...]
    queue_summary: tuple[str, ...]
    next_hook: str


def _queue_action(trial: Week12ShadowTrial) -> Week12QueueAction:
    return {
        "promote_to_scrim": "promote_scrim_policy",
        "shadow_again": "train_shadow_candidate",
        "hold_for_review": "coach_review_gate",
        "collect_more_replay": "collect_replay_batch",
    }.get(trial.decision, "train_shadow_candidate")


def _queue_status(action: Week12QueueAction) -> Week12QueueStatus:
    return {
        "promote_scrim_policy": "ready_for_scrim",
        "train_shadow_candidate": "queued_for_training",
        "coach_review_gate": "blocked_by_review",
        "collect_replay_batch": "needs_replay",
    }[action]


def _learning_phase(action: Week12QueueAction, trial: Week12ShadowTrial) -> str:
    if action == "promote_scrim_policy":
        return "scrim promotion audit"
    if action == "collect_replay_batch":
        return "offline replay collection"
    if action == "coach_review_gate":
        return "coach-gated safety review"
    if trial.training_mode == "risk_regularization":
        return "risk-penalized policy tuning"
    if trial.training_mode == "objective_pressure_tuning":
        return "objective pressure reinforcement"
    return "shadow candidate fine tune"


def _epoch_budget(action: Week12QueueAction, trial: Week12ShadowTrial) -> int:
    if action == "promote_scrim_policy":
        return max(1, min(4, trial.episodes // 2))
    if action == "collect_replay_batch":
        return 0
    if action == "coach_review_gate":
        return max(1, min(3, max(1, trial.episodes // 3)))
    reward_pressure = max(0, 2 - trial.reward_delta)
    risk_pressure = max(0, trial.risk_delta)
    return max(2, min(10, 2 + reward_pressure + risk_pressure + trial.objective_delta // 3))


def _replay_batch_target(action: Week12QueueAction, trial: Week12ShadowTrial) -> int:
    if action == "collect_replay_batch":
        return max(12, trial.episodes * 4)
    if action == "coach_review_gate":
        return max(4, trial.episodes)
    return max(6, trial.episodes * 2)


def _reward_weight_x100(action: Week12QueueAction, trial: Week12ShadowTrial) -> int:
    if action == "collect_replay_batch":
        return 80
    return 100 + max(0, 2 - trial.reward_delta) * 15


def _risk_penalty_x100(action: Week12QueueAction, trial: Week12ShadowTrial) -> int:
    if action == "promote_scrim_policy":
        return 80 + max(0, trial.risk_delta) * 8
    if action == "coach_review_gate":
        return 135 + max(0, trial.risk_delta) * 12
    if action == "collect_replay_batch":
        return 100
    return 105 + max(0, trial.risk_delta) * 10


def _objective_weight_x100(action: Week12QueueAction, trial: Week12ShadowTrial) -> int:
    if action == "collect_replay_batch":
        return 90
    return 100 + max(0, 3 - trial.objective_delta) * 10


def _exploration_rate_x100(action: Week12QueueAction, trial: Week12ShadowTrial) -> int:
    if action == "promote_scrim_policy":
        return 4
    if action == "collect_replay_batch":
        return 0
    if action == "coach_review_gate":
        return 6
    return 8 + max(0, 2 - trial.reward_delta) * 2


def _priority_score(action: Week12QueueAction, trial: Week12ShadowTrial) -> int:
    action_base = {
        "promote_scrim_policy": 92,
        "train_shadow_candidate": 78,
        "coach_review_gate": 68,
        "collect_replay_batch": 58,
    }[action]
    return max(
        0,
        action_base
        + trial.reward_delta * 4
        + trial.objective_delta * 2
        - max(0, trial.risk_delta) * 6,
    )


def _approval_gate(action: Week12QueueAction, trial: Week12ShadowTrial) -> str:
    if action == "promote_scrim_policy":
        return "coach approves scrim block after one non-regressing replay audit"
    if action == "collect_replay_batch":
        return "minimum replay_batch_target samples attached to the same scenario model slot"
    if action == "coach_review_gate":
        return "coach clears risk note before any additional epochs run"
    return "candidate reward delta >= 2 and risk delta <= 0 in the next shadow rollout"


def _stop_condition(action: Week12QueueAction, trial: Week12ShadowTrial) -> str:
    if action == "promote_scrim_policy":
        return "stop after scrim audit export; do not mutate policy weights"
    if action == "collect_replay_batch":
        return "stop before training until replay_batch_target is met"
    if action == "coach_review_gate":
        return "stop before rollout until the review gate is cleared"
    return (
        "stop if held-out reward regresses below baseline or risk rises above "
        f"{max(0, trial.risk_delta) + 55}"
    )


def _coach_note(action: Week12QueueAction, trial: Week12ShadowTrial) -> str:
    if action == "promote_scrim_policy":
        return f"{trial.agent_id} can be trialed in scrim with live rollback enabled."
    if action == "collect_replay_batch":
        return f"{trial.agent_id} needs more replay before model updates are meaningful."
    if action == "coach_review_gate":
        return f"{trial.agent_id} needs coach review: {trial.decision_reason}."
    return f"{trial.agent_id} stays in shadow tuning with {trial.training_mode}."


def _job_for_trial(trial: Week12ShadowTrial) -> Week12TrainingQueueJob:
    action = _queue_action(trial)
    epoch_budget = _epoch_budget(action, trial)
    return Week12TrainingQueueJob(
        job_id=f"week12:{trial.agent_id}:{action}:{trial.candidate_policy_id}",
        agent_id=trial.agent_id,
        candidate_policy_id=trial.candidate_policy_id,
        scenario_model_slot=trial.scenario_model_slot,
        source_decision=trial.decision,
        queue_action=action,
        queue_status=_queue_status(action),
        learning_phase=_learning_phase(action, trial),
        epoch_budget=epoch_budget,
        rollout_episode_budget=max(2, trial.episodes + max(0, epoch_budget - 1)),
        replay_batch_target=_replay_batch_target(action, trial),
        reward_weight_x100=_reward_weight_x100(action, trial),
        risk_penalty_x100=_risk_penalty_x100(action, trial),
        objective_weight_x100=_objective_weight_x100(action, trial),
        exploration_rate_x100=_exploration_rate_x100(action, trial),
        priority_score=_priority_score(action, trial),
        approval_gate=_approval_gate(action, trial),
        stop_condition=_stop_condition(action, trial),
        scenario_asset_slot=(
            f"scenario://week12/assets/{trial.agent_id}/{trial.candidate_policy_id}/training-queue"
        ),
        coach_note=_coach_note(action, trial),
    )


def resolve_week12_training_queue(rollout: Week12ShadowRollout) -> Week12TrainingQueue:
    """Resolve a deterministic queue of RL jobs from shadow-rollout decisions."""
    jobs = tuple(
        sorted(
            (_job_for_trial(trial) for trial in rollout.trials),
            key=lambda job: (-job.priority_score, job.agent_id),
        )
    )
    train_count = len([job for job in jobs if job.queue_action == "train_shadow_candidate"])
    promote_count = len([job for job in jobs if job.queue_action == "promote_scrim_policy"])
    gate_count = len(
        [job for job in jobs if job.queue_status in ("blocked_by_review", "needs_replay")]
    )
    summary_lines = [
        f"{train_count} policies are queued for additional RL-style tuning.",
        f"{promote_count} policies can move into scrim promotion audits.",
        f"{gate_count} jobs are gated by coach review or replay collection.",
        "Jobs expose reward/risk/objective weights so learned players can replace heuristics later.",
    ]
    if promote_count > train_count:
        summary_lines[0], summary_lines[1] = summary_lines[1], summary_lines[0]
    return Week12TrainingQueue(
        sim_id=rollout.sim_id,
        selected_plan=rollout.selected_plan,
        outcome_id=rollout.outcome_id,
        result_tier=rollout.result_tier,
        jobs=jobs,
        queue_summary=tuple(summary_lines),
        next_hook="Future RL runners consume training_queue_batch_v1 before policy weights are changed.",
    )


def _training_queue_job_to_dict(job: Week12TrainingQueueJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "agent_id": job.agent_id,
        "candidate_policy_id": job.candidate_policy_id,
        "scenario_model_slot": job.scenario_model_slot,
        "source_decision": job.source_decision,
        "queue_action": job.queue_action,
        "queue_status": job.queue_status,
        "learning_phase": job.learning_phase,
        "epoch_budget": job.epoch_budget,
        "rollout_episode_budget": job.rollout_episode_budget,
        "replay_batch_target": job.replay_batch_target,
        "reward_weight_x100": job.reward_weight_x100,
        "risk_penalty_x100": job.risk_penalty_x100,
        "objective_weight_x100": job.objective_weight_x100,
        "exploration_rate_x100": job.exploration_rate_x100,
        "priority_score": job.priority_score,
        "approval_gate": job.approval_gate,
        "stop_condition": job.stop_condition,
        "scenario_asset_slot": job.scenario_asset_slot,
        "coach_note": job.coach_note,
    }


def week12_training_queue_to_dict(queue: Week12TrainingQueue) -> dict[str, Any]:
    """Dictionary form used by JSON export and the Week-12 training ops page."""
    return {
        "artifact_type": "week12_training_queue",
        "checkpoint": "week12_training_queue",
        "schema_version": 1,
        "source_artifact": WEEK12_SHADOW_ROLLOUT_FILENAME,
        "source_artifacts": {
            "week12_shadow_rollout": WEEK12_SHADOW_ROLLOUT_FILENAME,
        },
        "week": 12,
        "route": "/week12/training-queue",
        "sim_id": queue.sim_id,
        "selected_plan": queue.selected_plan,
        "outcome_id": queue.outcome_id,
        "result_tier": queue.result_tier,
        "job_count": len(queue.jobs),
        "jobs": [_training_queue_job_to_dict(job) for job in queue.jobs],
        "training_queue_contract": {
            "format": "training_queue_batch_v1",
            "source_shadow_rollout_format": "shadow_rollout_batch_v1",
            "job_unit": "jobs[]",
            "model_reference_field": "jobs[].scenario_model_slot",
            "scenario_asset_field": "jobs[].scenario_asset_slot",
            "policy_reference_field": "jobs[].candidate_policy_id",
            "rl_budget_fields": [
                "epoch_budget",
                "rollout_episode_budget",
                "replay_batch_target",
            ],
            "rl_weight_fields": [
                "reward_weight_x100",
                "risk_penalty_x100",
                "objective_weight_x100",
                "exploration_rate_x100",
            ],
            "queue_actions": [
                "promote_scrim_policy",
                "train_shadow_candidate",
                "coach_review_gate",
                "collect_replay_batch",
            ],
        },
        "queue_summary": list(queue.queue_summary),
        "next_hook": queue.next_hook,
        "stops_before": "week12_rl_runner",
        "next_artifact": None,
    }


def render_week12_training_queue_json(queue: Week12TrainingQueue) -> str:
    """Canonical JSON export for the Week-12 training queue."""
    return json.dumps(
        {"week12_training_queue": week12_training_queue_to_dict(queue)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


def week12_training_queue_from_json(text: str) -> Week12TrainingQueue:
    """Parse a written ``week12_training_queue.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week12_training_queue JSON is malformed") from exc
    queue = data.get("week12_training_queue") if isinstance(data, dict) else None
    if not isinstance(queue, dict):
        raise ValueError("week12_training_queue JSON must contain a week12_training_queue object")
    if queue.get("source_artifact") != WEEK12_SHADOW_ROLLOUT_FILENAME:
        raise ValueError("week12_training_queue source_artifact must be week12_shadow_rollout.json")
    jobs_raw = queue.get("jobs")
    if not isinstance(jobs_raw, list) or not jobs_raw:
        raise ValueError("week12_training_queue JSON must include jobs")
    if queue.get("next_artifact") is not None:
        raise ValueError("week12_training_queue next_artifact must be null")
    jobs = tuple(
        Week12TrainingQueueJob(
            job_id=str(job.get("job_id", "")),
            agent_id=str(job.get("agent_id", "")),
            candidate_policy_id=str(job.get("candidate_policy_id", "")),
            scenario_model_slot=str(job.get("scenario_model_slot", "")),
            source_decision=str(job.get("source_decision", "")),
            queue_action=(
                job.get("queue_action")
                if job.get("queue_action")
                in (
                    "promote_scrim_policy",
                    "train_shadow_candidate",
                    "coach_review_gate",
                    "collect_replay_batch",
                )
                else "train_shadow_candidate"
            ),
            queue_status=(
                job.get("queue_status")
                if job.get("queue_status")
                in (
                    "ready_for_scrim",
                    "queued_for_training",
                    "blocked_by_review",
                    "needs_replay",
                )
                else "queued_for_training"
            ),
            learning_phase=str(job.get("learning_phase", "")),
            epoch_budget=int(job.get("epoch_budget", 0)),
            rollout_episode_budget=int(job.get("rollout_episode_budget", 0)),
            replay_batch_target=int(job.get("replay_batch_target", 0)),
            reward_weight_x100=int(job.get("reward_weight_x100", 0)),
            risk_penalty_x100=int(job.get("risk_penalty_x100", 0)),
            objective_weight_x100=int(job.get("objective_weight_x100", 0)),
            exploration_rate_x100=int(job.get("exploration_rate_x100", 0)),
            priority_score=int(job.get("priority_score", 0)),
            approval_gate=str(job.get("approval_gate", "")),
            stop_condition=str(job.get("stop_condition", "")),
            scenario_asset_slot=str(job.get("scenario_asset_slot", "")),
            coach_note=str(job.get("coach_note", "")),
        )
        for job in jobs_raw
        if isinstance(job, dict)
    )
    return Week12TrainingQueue(
        sim_id=str(queue.get("sim_id", "")),
        selected_plan=str(queue.get("selected_plan", "")),
        outcome_id=str(queue.get("outcome_id", "")),
        result_tier=str(queue.get("result_tier", "")),
        jobs=jobs,
        queue_summary=tuple(
            str(item) for item in queue.get("queue_summary", []) if isinstance(item, str)
        ),
        next_hook=str(queue.get("next_hook", "")),
    )
