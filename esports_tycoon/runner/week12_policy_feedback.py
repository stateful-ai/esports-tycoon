"""Week-12 policy feedback derived from queue jobs and replay samples."""

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
from esports_tycoon.runner.week12_training_queue import (
    WEEK12_TRAINING_QUEUE_FILENAME,
    Week12TrainingQueue,
    Week12TrainingQueueJob,
)

Week12FeedbackPolarity = Literal["positive", "watch", "negative"]


@dataclass(frozen=True)
class Week12ReplayAnnotation:
    """One replay-tick explanation attached to a policy-feedback item."""

    tick: int
    round_id: int
    action: str
    reward: int
    target_zone: str
    risk_index: int
    label: str
    polarity: Week12FeedbackPolarity
    source_sample_id: str


@dataclass(frozen=True)
class Week12PolicyFeedbackItem:
    """Coach-facing feedback for one queued candidate policy."""

    feedback_id: str
    agent_id: str
    candidate_policy_id: str
    queue_action: str
    queue_status: str
    source_job_id: str
    scenario_model_slot: str
    scenario_asset_slot: str
    sample_count: int
    matched_ticks: tuple[int, ...]
    matched_rounds: tuple[int, ...]
    transition_ids: tuple[str, ...]
    evidence_clip: dict[str, Any]
    missing_evidence_reason: str
    sample_credit_assignment: dict[str, Any]
    focus_component: str
    component_totals: dict[str, int]
    reward_total: int
    risk_peak: int
    objective_mean: int
    policy_weight_snapshot: dict[str, int]
    sample_warning: str
    coach_action: str
    player_feedback: str
    next_drill_hook: str
    replay_annotations: tuple[Week12ReplayAnnotation, ...]


@dataclass(frozen=True)
class Week12PolicyFeedback:
    """Feedback batch that joins queue decisions to concrete replay evidence."""

    sim_id: str
    selected_plan: str
    outcome_id: str
    result_tier: str
    items: tuple[Week12PolicyFeedbackItem, ...]
    feedback_summary: tuple[str, ...]
    next_hook: str


def _mean_int(values: list[int]) -> int:
    if not values:
        return 0
    return (sum(values) + len(values) // 2) // len(values)


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


def _focus_component(
    *,
    samples: list[Week11TrainingSample],
    component_totals: dict[str, int],
    job: Week12TrainingQueueJob,
) -> str:
    if not samples:
        return "replay_collection"
    if component_totals.get("overpeek_penalty", 0) < 0:
        return "overpeek_penalty"
    if job.queue_status == "blocked_by_review":
        return "coach_review"
    if any(sample.telemetry.risk_index >= 58 for sample in samples):
        return "risk_index"
    if _mean_int([sample.telemetry.objective_pressure for sample in samples]) < 60:
        return "objective_pressure"
    weakest = min(component_totals, key=lambda key: component_totals[key])
    if component_totals[weakest] <= 0:
        return weakest
    return max(component_totals, key=lambda key: component_totals[key])


def _sample_warning(job: Week12TrainingQueueJob, samples: list[Week11TrainingSample]) -> str:
    if not samples:
        return "no replay samples matched this queued policy"
    if len(samples) < job.replay_batch_target:
        return f"{len(samples)} of {job.replay_batch_target} requested replay samples are attached"
    return ""


def _missing_evidence_reason(
    job: Week12TrainingQueueJob,
    samples: list[Week11TrainingSample],
) -> str:
    if not samples:
        return (
            f"{job.agent_id} has no matching Week 11 transition for "
            f"{job.candidate_policy_id}"
        )
    if len(samples) < job.replay_batch_target:
        missing = job.replay_batch_target - len(samples)
        return f"{missing} more replay transition(s) needed for the requested batch target"
    return ""


def _coach_action(job: Week12TrainingQueueJob, focus_component: str) -> str:
    if job.queue_action == "promote_scrim_policy":
        return "run one annotated scrim audit with rollback armed before promotion"
    if job.queue_action == "collect_replay_batch":
        return f"collect {job.replay_batch_target} replay transitions before training"
    if job.queue_action == "coach_review_gate":
        return f"clear the {focus_component} review gate before any rollout"
    return f"train {job.epoch_budget} epochs with {focus_component} weighting and replay validation"


def _player_feedback(focus_component: str, job: Week12TrainingQueueJob) -> str:
    feedback = {
        "overpeek_penalty": "delay first-contact swings until the trade partner is in range",
        "risk_index": "lower exposed contact windows while preserving the planned pressure",
        "objective_pressure": "turn the read into site pressure earlier in the round",
        "utility_timing": "spend utility before the contact tick instead of after it",
        "trade_quality": "hold the crossfire until the second body can trade",
        "space_gained": "convert first information into map control before resetting",
        "default_integrity": "keep the default shape intact while calling the rotate",
        "round_win": "preserve the terminal habit that converted the replay round",
        "coach_review": "explain the decision branch before repeating the policy",
        "replay_collection": "attach more replay before this policy learns from the queue",
    }
    return f"{job.agent_id}: {feedback.get(focus_component, 'repeat annotated replay before tuning')}"


def _next_drill_hook(job: Week12TrainingQueueJob, focus_component: str) -> str:
    if job.queue_action == "promote_scrim_policy":
        return f"scrim:{job.agent_id}:{job.candidate_policy_id}:rollback-audit"
    if job.queue_action == "collect_replay_batch":
        return f"replay:{job.agent_id}:{job.replay_batch_target}:attach-before-training"
    if job.queue_action == "coach_review_gate":
        return f"coach-review:{job.agent_id}:{focus_component}:clear-gate"
    return f"drill:{job.agent_id}:{focus_component}:{job.epoch_budget}-epochs"


def _annotation_label(sample: Week11TrainingSample, focus_component: str) -> str:
    if sample.reward < 0:
        return f"{focus_component} regression"
    if sample.telemetry.risk_index >= 58:
        return "risk spike"
    if sample.reward > 0:
        return f"{focus_component} conversion"
    return f"{focus_component} decision"


def _annotation_polarity(sample: Week11TrainingSample) -> Week12FeedbackPolarity:
    if sample.reward < 0 or sample.telemetry.risk_index >= 70:
        return "negative"
    if sample.telemetry.risk_index >= 58 or sample.reward == 0:
        return "watch"
    return "positive"


def _replay_annotations(
    samples: list[Week11TrainingSample],
    *,
    focus_component: str,
) -> tuple[Week12ReplayAnnotation, ...]:
    ranked = sorted(
        samples,
        key=lambda sample: (
            sample.reward < 0,
            sample.telemetry.risk_index,
            abs(sample.reward),
            -sample.tick,
        ),
        reverse=True,
    )
    annotations = []
    for sample in ranked[:3]:
        target_zone = str(sample.observation_features.get("target_zone", "unknown"))
        annotations.append(
            Week12ReplayAnnotation(
                tick=sample.tick,
                round_id=sample.round_id,
                action=sample.action,
                reward=sample.reward,
                target_zone=target_zone,
                risk_index=sample.telemetry.risk_index,
                label=_annotation_label(sample, focus_component),
                polarity=_annotation_polarity(sample),
                source_sample_id=sample.sample_id,
            )
        )
    return tuple(sorted(annotations, key=lambda item: item.tick))


def _policy_weight_snapshot(job: Week12TrainingQueueJob) -> dict[str, int]:
    return {
        "reward_weight_x100": job.reward_weight_x100,
        "risk_penalty_x100": job.risk_penalty_x100,
        "objective_weight_x100": job.objective_weight_x100,
        "exploration_rate_x100": job.exploration_rate_x100,
    }


def _evidence_score(
    job: Week12TrainingQueueJob,
    sample: Week11TrainingSample,
) -> tuple[int, int, int, int, int]:
    if job.queue_action == "promote_scrim_policy":
        return (
            int(sample.reward > 0),
            sample.telemetry.objective_pressure,
            100 - sample.telemetry.risk_index,
            sample.reward,
            -sample.tick,
        )
    if job.queue_action == "coach_review_gate":
        return (
            sample.telemetry.risk_index,
            abs(sample.reward),
            100 - sample.telemetry.objective_pressure,
            int(sample.reward < 0),
            -sample.tick,
        )
    weighted_pressure = (
        max(0, -sample.reward) * job.reward_weight_x100
        + sample.telemetry.risk_index * job.risk_penalty_x100
        + max(0, 70 - sample.telemetry.objective_pressure) * job.objective_weight_x100
    )
    if job.queue_action == "collect_replay_batch":
        weighted_pressure += job.replay_batch_target * 10
    return (
        weighted_pressure,
        sample.telemetry.risk_index,
        abs(sample.reward),
        sample.telemetry.objective_pressure,
        -sample.tick,
    )


def _evidence_sample(
    job: Week12TrainingQueueJob,
    samples: list[Week11TrainingSample],
) -> Week11TrainingSample | None:
    if not samples:
        return None
    return max(samples, key=lambda sample: _evidence_score(job, sample))


def _selection_reason(job: Week12TrainingQueueJob) -> str:
    return {
        "promote_scrim_policy": "best positive replay tick for scrim audit",
        "train_shadow_candidate": "highest weighted replay weakness for training",
        "coach_review_gate": "highest-risk replay tick for coach review",
        "collect_replay_batch": "available replay tick plus missing batch target",
    }.get(job.queue_action, "weighted replay evidence")


def _evidence_clip(
    job: Week12TrainingQueueJob,
    samples: list[Week11TrainingSample],
) -> dict[str, Any]:
    sample = _evidence_sample(job, samples)
    if sample is None:
        return {
            "status": "missing",
            "source_job_id": job.job_id,
            "desired_sample_profile": (
                f"{job.agent_id} transitions with {job.queue_action} context "
                f"and {job.replay_batch_target} replay samples"
            ),
        }
    return {
        "status": "attached",
        "source_job_id": job.job_id,
        "source_sample_id": sample.sample_id,
        "tick": sample.tick,
        "round_id": sample.round_id,
        "action": sample.action,
        "reward": sample.reward,
        "target_zone": str(sample.observation_features.get("target_zone", "unknown")),
        "selection_reason": _selection_reason(job),
        "telemetry": {
            "space_control": sample.telemetry.space_control,
            "utility_pressure": sample.telemetry.utility_pressure,
            "trade_window": sample.telemetry.trade_window,
            "risk_index": sample.telemetry.risk_index,
            "objective_pressure": sample.telemetry.objective_pressure,
        },
    }


def _sample_credit_assignment(
    job: Week12TrainingQueueJob,
    samples: list[Week11TrainingSample],
    component_totals: dict[str, int],
) -> dict[str, Any]:
    return {
        "source_job_id": job.job_id,
        "agent_id": job.agent_id,
        "source_sample_ids": [sample.sample_id for sample in samples],
        "reward_component_deltas": dict(component_totals),
        "transition_count": len(samples),
    }


def _feedback_item(
    job: Week12TrainingQueueJob,
    samples: list[Week11TrainingSample],
) -> Week12PolicyFeedbackItem:
    component_totals = _component_totals(samples)
    focus_component = _focus_component(
        samples=samples,
        component_totals=component_totals,
        job=job,
    )
    matched_ticks = tuple(sample.tick for sample in samples)
    matched_rounds = tuple(sorted({sample.round_id for sample in samples}))
    transition_ids = tuple(sample.sample_id for sample in samples)
    risk_peak = max((sample.telemetry.risk_index for sample in samples), default=0)
    objective_mean = _mean_int([sample.telemetry.objective_pressure for sample in samples])
    return Week12PolicyFeedbackItem(
        feedback_id=f"week12-feedback:{job.agent_id}:{job.candidate_policy_id}",
        agent_id=job.agent_id,
        candidate_policy_id=job.candidate_policy_id,
        queue_action=job.queue_action,
        queue_status=job.queue_status,
        source_job_id=job.job_id,
        scenario_model_slot=job.scenario_model_slot,
        scenario_asset_slot=job.scenario_asset_slot.replace(
            "/training-queue",
            "/policy-feedback",
        ),
        sample_count=len(samples),
        matched_ticks=matched_ticks,
        matched_rounds=matched_rounds,
        transition_ids=transition_ids,
        evidence_clip=_evidence_clip(job, samples),
        missing_evidence_reason=_missing_evidence_reason(job, samples),
        sample_credit_assignment=_sample_credit_assignment(job, samples, component_totals),
        focus_component=focus_component,
        component_totals=component_totals,
        reward_total=sum(sample.reward for sample in samples),
        risk_peak=risk_peak,
        objective_mean=objective_mean,
        policy_weight_snapshot=_policy_weight_snapshot(job),
        sample_warning=_sample_warning(job, samples),
        coach_action=_coach_action(job, focus_component),
        player_feedback=_player_feedback(focus_component, job),
        next_drill_hook=_next_drill_hook(job, focus_component),
        replay_annotations=_replay_annotations(samples, focus_component=focus_component),
    )


def resolve_week12_policy_feedback(
    queue: Week12TrainingQueue,
    dataset: Week11TrainingDataset,
) -> Week12PolicyFeedback:
    """Join training-queue decisions to replay samples for coachable policy feedback."""
    samples_by_agent: dict[str, list[Week11TrainingSample]] = defaultdict(list)
    for sample in dataset.samples:
        samples_by_agent[sample.agent_id].append(sample)

    items = tuple(
        _feedback_item(job, samples_by_agent.get(job.agent_id, []))
        for job in queue.jobs
    )
    review_count = len(
        [item for item in items if item.queue_status in ("blocked_by_review", "needs_replay")]
    )
    annotation_count = sum(len(item.replay_annotations) for item in items)
    ready_count = len([item for item in items if item.queue_status == "ready_for_scrim"])
    return Week12PolicyFeedback(
        sim_id=queue.sim_id,
        selected_plan=queue.selected_plan,
        outcome_id=queue.outcome_id,
        result_tier=queue.result_tier,
        items=tuple(sorted(items, key=lambda item: (item.queue_status != "ready_for_scrim", item.agent_id))),
        feedback_summary=(
            f"{len(items)} queued policies now have coach-facing feedback.",
            f"{annotation_count} replay ticks are annotated for player review.",
            f"{review_count} policies remain gated by review or replay coverage.",
            f"{ready_count} policies can enter scrim feedback with rollback language attached.",
        ),
        next_hook="Policy feedback is the human-readable gate before future learned players mutate weights.",
    )


def _annotation_to_dict(annotation: Week12ReplayAnnotation) -> dict[str, Any]:
    return {
        "tick": annotation.tick,
        "round_id": annotation.round_id,
        "action": annotation.action,
        "reward": annotation.reward,
        "target_zone": annotation.target_zone,
        "risk_index": annotation.risk_index,
        "label": annotation.label,
        "polarity": annotation.polarity,
        "source_sample_id": annotation.source_sample_id,
    }


def _feedback_item_to_dict(item: Week12PolicyFeedbackItem) -> dict[str, Any]:
    return {
        "feedback_id": item.feedback_id,
        "agent_id": item.agent_id,
        "candidate_policy_id": item.candidate_policy_id,
        "queue_action": item.queue_action,
        "queue_status": item.queue_status,
        "source_job_id": item.source_job_id,
        "scenario_model_slot": item.scenario_model_slot,
        "scenario_asset_slot": item.scenario_asset_slot,
        "sample_count": item.sample_count,
        "matched_ticks": list(item.matched_ticks),
        "matched_rounds": list(item.matched_rounds),
        "transition_ids": list(item.transition_ids),
        "evidence_clip": dict(item.evidence_clip),
        "missing_evidence_reason": item.missing_evidence_reason,
        "sample_credit_assignment": dict(item.sample_credit_assignment),
        "focus_component": item.focus_component,
        "component_totals": dict(item.component_totals),
        "reward_total": item.reward_total,
        "risk_peak": item.risk_peak,
        "objective_mean": item.objective_mean,
        "policy_weight_snapshot": dict(item.policy_weight_snapshot),
        "sample_warning": item.sample_warning,
        "coach_action": item.coach_action,
        "player_feedback": item.player_feedback,
        "next_drill_hook": item.next_drill_hook,
        "replay_annotations": [
            _annotation_to_dict(annotation)
            for annotation in item.replay_annotations
        ],
    }


def week12_policy_feedback_to_dict(feedback: Week12PolicyFeedback) -> dict[str, Any]:
    """Dictionary form used by JSON export and the Week-12 feedback page."""
    return {
        "artifact_type": "week12_policy_feedback",
        "checkpoint": "week12_policy_feedback",
        "schema_version": 1,
        "source_artifact": WEEK12_TRAINING_QUEUE_FILENAME,
        "source_artifacts": {
            "week12_training_queue": WEEK12_TRAINING_QUEUE_FILENAME,
            "week11_training_dataset": WEEK11_TRAINING_DATASET_FILENAME,
        },
        "week": 12,
        "route": "/week12/policy-feedback",
        "sim_id": feedback.sim_id,
        "selected_plan": feedback.selected_plan,
        "outcome_id": feedback.outcome_id,
        "result_tier": feedback.result_tier,
        "feedback_count": len(feedback.items),
        "items": [_feedback_item_to_dict(item) for item in feedback.items],
        "policy_feedback_contract": {
            "format": "policy_feedback_batch_v1",
            "source_queue_format": "training_queue_batch_v1",
            "source_dataset_format": "offline_rl_transition_v1",
            "feedback_unit": "items[]",
            "replay_annotation_unit": "items[].replay_annotations[]",
            "coach_action_field": "items[].coach_action",
            "player_feedback_field": "items[].player_feedback",
            "rl_weight_snapshot_field": "items[].policy_weight_snapshot",
            "transition_reference_field": "items[].transition_ids",
            "evidence_clip_field": "items[].evidence_clip",
            "credit_assignment_field": "items[].sample_credit_assignment",
            "scenario_asset_field": "items[].scenario_asset_slot",
        },
        "feedback_summary": list(feedback.feedback_summary),
        "next_hook": feedback.next_hook,
        "stops_before": "week12_rl_runner",
        "next_artifact": None,
    }


def render_week12_policy_feedback_json(feedback: Week12PolicyFeedback) -> str:
    """Canonical JSON export for the Week-12 policy feedback batch."""
    return json.dumps(
        {"week12_policy_feedback": week12_policy_feedback_to_dict(feedback)},
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"


def _int_tuple_from_any(data: Any) -> tuple[int, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(int(item) for item in data if isinstance(item, int))


def _str_tuple_from_any(data: Any) -> tuple[str, ...]:
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data if isinstance(item, str))


def _int_dict_from_any(data: Any) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    return {str(key): int(value) for key, value in data.items() if isinstance(value, int)}


def _dict_from_any(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    return dict(data)


def _annotation_from_any(data: Any) -> Week12ReplayAnnotation | None:
    if not isinstance(data, dict):
        return None
    polarity = data.get("polarity")
    if polarity not in ("positive", "watch", "negative"):
        polarity = "watch"
    return Week12ReplayAnnotation(
        tick=int(data.get("tick", 0)),
        round_id=int(data.get("round_id", 0)),
        action=str(data.get("action", "")),
        reward=int(data.get("reward", 0)),
        target_zone=str(data.get("target_zone", "")),
        risk_index=int(data.get("risk_index", 0)),
        label=str(data.get("label", "")),
        polarity=polarity,
        source_sample_id=str(data.get("source_sample_id", "")),
    )


def week12_policy_feedback_from_json(text: str) -> Week12PolicyFeedback:
    """Parse a written ``week12_policy_feedback.json`` artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("week12_policy_feedback JSON is malformed") from exc
    feedback = data.get("week12_policy_feedback") if isinstance(data, dict) else None
    if not isinstance(feedback, dict):
        raise ValueError("week12_policy_feedback JSON must contain a week12_policy_feedback object")
    if feedback.get("source_artifact") != WEEK12_TRAINING_QUEUE_FILENAME:
        raise ValueError("week12_policy_feedback source_artifact must be week12_training_queue.json")
    items_raw = feedback.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise ValueError("week12_policy_feedback JSON must include items")
    if feedback.get("next_artifact") is not None:
        raise ValueError("week12_policy_feedback next_artifact must be null")
    items = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        annotations = tuple(
            annotation
            for annotation in (
                _annotation_from_any(raw)
                for raw in item.get("replay_annotations", [])
            )
            if annotation is not None
        )
        items.append(
            Week12PolicyFeedbackItem(
                feedback_id=str(item.get("feedback_id", "")),
                agent_id=str(item.get("agent_id", "")),
                candidate_policy_id=str(item.get("candidate_policy_id", "")),
                queue_action=str(item.get("queue_action", "")),
                queue_status=str(item.get("queue_status", "")),
                source_job_id=str(item.get("source_job_id", "")),
                scenario_model_slot=str(item.get("scenario_model_slot", "")),
                scenario_asset_slot=str(item.get("scenario_asset_slot", "")),
                sample_count=int(item.get("sample_count", 0)),
                matched_ticks=_int_tuple_from_any(item.get("matched_ticks")),
                matched_rounds=_int_tuple_from_any(item.get("matched_rounds")),
                transition_ids=_str_tuple_from_any(item.get("transition_ids")),
                evidence_clip=_dict_from_any(item.get("evidence_clip")),
                missing_evidence_reason=str(item.get("missing_evidence_reason", "")),
                sample_credit_assignment=_dict_from_any(item.get("sample_credit_assignment")),
                focus_component=str(item.get("focus_component", "")),
                component_totals=_int_dict_from_any(item.get("component_totals")),
                reward_total=int(item.get("reward_total", 0)),
                risk_peak=int(item.get("risk_peak", 0)),
                objective_mean=int(item.get("objective_mean", 0)),
                policy_weight_snapshot=_int_dict_from_any(item.get("policy_weight_snapshot")),
                sample_warning=str(item.get("sample_warning", "")),
                coach_action=str(item.get("coach_action", "")),
                player_feedback=str(item.get("player_feedback", "")),
                next_drill_hook=str(item.get("next_drill_hook", "")),
                replay_annotations=annotations,
            )
        )
    return Week12PolicyFeedback(
        sim_id=str(feedback.get("sim_id", "")),
        selected_plan=str(feedback.get("selected_plan", "")),
        outcome_id=str(feedback.get("outcome_id", "")),
        result_tier=str(feedback.get("result_tier", "")),
        items=tuple(items),
        feedback_summary=tuple(
            str(item) for item in feedback.get("feedback_summary", []) if isinstance(item, str)
        ),
        next_hook=str(feedback.get("next_hook", "")),
    )
