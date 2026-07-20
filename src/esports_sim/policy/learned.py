"""Dependency-light learned in-match player policy.

This mirrors the learned-manager approach: deterministic full-batch NumPy
imitation training, legal-action masking, profile-conditioned linear
hypernetwork interactions, and version-pinned JSON checkpoints.  The match
engine remains the resolver; this model only ranks candidates supplied by it.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from esports_sim.policy.base import (
    Action,
    ActionType,
    MotorControl,
    MotorMovement,
    MovementPace,
    PlayerPolicy,
)
from esports_sim.schemas import CommunicationAction, PlayerObservation
from esports_sim.schemas.communication import ClaimKind, ClaimValue


POLICY_VERSION = "learned-player-v4"
ENCODER_VERSION = 3
OBSERVATION_VERSION = 2
ACTION_VOCAB = tuple(sorted(ActionType, key=str))
MOTOR_MOVEMENT_VOCAB = tuple(sorted(MotorMovement, key=str))
MOVEMENT_PACE_VOCAB = tuple(sorted(MovementPace, key=str))
CLAIM_KIND_VOCAB = tuple(sorted(ClaimKind, key=str))
CLAIM_VALUE_VOCAB = tuple(sorted(ClaimValue, key=str))
ORDER_VERB_VOCAB = ("buy", "defuse", "goto", "hold", "plant", "wait")
TACTICAL_ROLE_VOCAB = (
    "anchor",
    "carrier",
    "entry",
    "flex",
    "holder",
    "lurker",
    "support",
)
TARGET_SITE_VOCAB = ("a", "b", "c")
TIMEOUT_VOCAB = ("pressure", "retake", "stabilize")
PLAYER_ROLE_VOCAB = ("controller", "duelist", "flex", "initiator", "sentinel")
PLAYSTYLE_VOCAB = ("anchor", "awper", "entry", "igl", "lurker", "support")
WEAPON_VOCAB = (
    "classic",
    "ghost",
    "operator",
    "phantom",
    "sheriff",
    "spectre",
    "vandal",
)


class PlayerDecisionTraceV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    observation: PlayerObservation
    legal_actions: tuple[Action, ...]
    selected_action: Action


class CommunicationDecisionTraceV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    observation: PlayerObservation
    legal_actions: tuple[CommunicationAction, ...]
    selected_action: CommunicationAction


class MotorDecisionTraceV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    observation: PlayerObservation
    legal_controls: tuple[MotorControl, ...]
    selected_control: MotorControl


def _stable_bucket(text: str | None, buckets: int) -> np.ndarray:
    out = np.zeros(buckets, dtype=np.float64)
    if not text:
        return out
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=4).digest()
    out[int.from_bytes(digest, "big") % buckets] = 1.0
    return out


def _one_hot(text: str | None, vocabulary: tuple[str, ...]) -> np.ndarray:
    """Collision-free categorical encoding with an explicit unknown slot."""
    out = np.zeros(len(vocabulary) + 1, dtype=np.float64)
    try:
        index = vocabulary.index(text) if text is not None else len(vocabulary)
    except ValueError:
        index = len(vocabulary)
    out[index] = 1.0
    return out


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return float(sum(rows) / len(rows)) if rows else 0.0


def encode_observation(obs: PlayerObservation) -> np.ndarray:
    """Fixed-size actor-visible state encoder; contains no hidden truth."""
    self_state = obs.self_state
    order_verb, _, order_target = (obs.igl_call or "hold").partition(":")
    teammates_here = sum(
        teammate.callout_id == self_state.callout_id
        for teammate in obs.teammates
        if self_state.callout_id is not None
    )
    fresh_enemy_reads = [
        enemy
        for enemy in obs.enemies
        if enemy.last_seen_tick is not None and obs.tick - enemy.last_seen_tick <= 12
    ]
    values = [
        self_state.hp / 100.0,
        self_state.armor / 50.0,
        self_state.credits / 9_000.0,
        self_state.ult_points / 8.0,
        len(self_state.ability_charges) / 4.0,
        obs.round_num / 30.0,
        obs.tick / 200.0,
        float(obs.spike_planted),
        float(obs.is_attacking),
        len(obs.teammates) / 4.0,
        len(obs.enemies) / 5.0,
        _mean(enemy.confidence for enemy in obs.enemies),
        len(obs.team_whiteboard) / 12.0,
        _mean(belief.confidence for belief in obs.team_whiteboard),
        len(obs.adjacent_callouts) / 6.0,
        obs.tactical_aggression / 100.0,
        teammates_here / 4.0,
        len(fresh_enemy_reads) / 5.0,
        _mean(enemy.confidence for enemy in fresh_enemy_reads),
        self_state.x / 100.0,
        self_state.y / 100.0,
        np.sin(np.deg2rad(self_state.heading_degrees)),
        np.cos(np.deg2rad(self_state.heading_degrees)),
        float(self_state.is_moving),
        float(self_state.has_active_route),
        float(self_state.movement_pace == "walk"),
        (
            np.sin(np.deg2rad(obs.navigation_heading_degrees))
            if obs.navigation_heading_degrees is not None else 0.0
        ),
        (
            np.cos(np.deg2rad(obs.navigation_heading_degrees))
            if obs.navigation_heading_degrees is not None else 0.0
        ),
    ]
    return np.concatenate(
        (
            np.asarray(values, dtype=np.float64),
            _stable_bucket(obs.igl_call, 6),
            _one_hot(order_verb, ORDER_VERB_VOCAB),
            _stable_bucket(order_target, 6),
            _stable_bucket(self_state.callout_id, 6),
            _stable_bucket(self_state.agent_id, 4),
            _one_hot(self_state.weapon_id, WEAPON_VOCAB),
            _one_hot(obs.role, TACTICAL_ROLE_VOCAB),
            _one_hot(obs.team_target, TARGET_SITE_VOCAB),
            _one_hot(obs.timeout_directive, TIMEOUT_VOCAB),
        )
    )


def encode_condition(obs: PlayerObservation) -> np.ndarray:
    condition = obs.player_condition
    if condition is None:
        return np.full(24, 0.5, dtype=np.float64)
    numeric = np.asarray(
        [
            condition.aim_precision,
            condition.aim_reactivity,
            condition.movement,
            condition.game_sense,
            condition.utility_usage,
            condition.positioning,
            condition.clutch_factor,
            condition.tilt_resistance,
            condition.composure,
            condition.comms_quality,
            condition.agent_mastery,
            condition.map_mastery,
            condition.confidence,
            condition.form,
            condition.stamina,
        ],
        dtype=np.float64,
    ) / 100.0
    trait_buckets = np.zeros(3, dtype=np.float64)
    for tag in condition.personality_tags:
        trait_buckets += _stable_bucket(tag, 3)
    if condition.personality_tags:
        trait_buckets /= len(condition.personality_tags)
    return np.concatenate(
        (
            numeric,
            _one_hot(str(condition.role), PLAYER_ROLE_VOCAB),
            _one_hot(str(condition.playstyle), PLAYSTYLE_VOCAB),
            trait_buckets,
        )
    )


def conditioned_features(obs: PlayerObservation) -> np.ndarray:
    state = encode_observation(obs)
    condition = encode_condition(obs)
    # Effective candidate weights vary with profile axes: a small linear
    # hypernetwork / FiLM adapter over the shared symbolic state encoder.
    interaction = np.outer(condition - 0.5, state).reshape(-1)
    return np.concatenate(([1.0], state, condition, interaction))


def _action_features(action: Action) -> np.ndarray:
    return np.concatenate(
        (
            np.asarray([float(action.type == kind) for kind in ACTION_VOCAB]),
            _stable_bucket(action.callout_id, 6),
            _stable_bucket(action.target_player_id, 4),
            _one_hot(action.weapon_id, WEAPON_VOCAB),
            _stable_bucket(action.ability_id, 4),
            np.asarray([action.armor / 50.0, len(action.abilities) / 4.0]),
        )
    )


def _communication_features(action: CommunicationAction) -> np.ndarray:
    return np.concatenate(
        (
            np.asarray([float(action.speak)]),
            np.asarray(
                [float(action.kind == kind) for kind in CLAIM_KIND_VOCAB]
            ),
            np.asarray(
                [float(action.value == value) for value in CLAIM_VALUE_VOCAB]
            ),
            _stable_bucket(action.callout_id, 6),
            _stable_bucket(action.enemy_id, 4),
            np.asarray(
                [
                    action.expressed_confidence,
                    float(action.corrects_claim_id is not None),
                ]
            ),
        )
    )


def _motor_features(control: MotorControl) -> np.ndarray:
    return np.concatenate(
        (
            np.asarray(
                [float(control.movement == movement) for movement in MOTOR_MOVEMENT_VOCAB]
            ),
            np.asarray(
                [float(control.pace == pace) for pace in MOVEMENT_PACE_VOCAB]
            ),
            np.asarray([control.turn_degrees / 45.0]),
        )
    )


def _softmax(scores: np.ndarray) -> np.ndarray:
    shifted = scores - np.max(scores)
    exps = np.exp(np.clip(shifted, -60.0, 0.0))
    return exps / exps.sum()


def _fit_ranker(
    rows: list[tuple[np.ndarray, list[np.ndarray], int]],
    candidate_dim: int,
    state_dim: int,
    *,
    epochs: int = 80,
    learning_rate: float = 0.18,
) -> np.ndarray:
    weights = np.zeros((candidate_dim, state_dim), dtype=np.float64)
    for _ in range(epochs):
        grad = np.zeros_like(weights)
        for state, candidates, target in rows:
            matrix = np.stack(candidates)
            probs = _softmax(matrix @ weights @ state)
            probs[target] -= 1.0
            grad += np.outer(probs @ matrix, state)
        grad = grad / max(len(rows), 1) + 1e-4 * weights
        weights -= learning_rate * grad
    return weights


def _sorted_actions(actions: Iterable[Action]) -> list[Action]:
    return sorted(actions, key=lambda action: action.model_dump_json())


def _sorted_comms(actions: Iterable[CommunicationAction]) -> list[CommunicationAction]:
    return sorted(actions, key=lambda action: action.model_dump_json())


def _sorted_controls(controls: Iterable[MotorControl]) -> list[MotorControl]:
    return sorted(controls, key=lambda control: control.model_dump_json())


class LearnedPlayerModel(BaseModel):
    """Serializable shared tactical, motor, and communication rankers."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    action_weights: np.ndarray
    motor_weights: np.ndarray
    communication_weights: np.ndarray
    training_examples: int = Field(ge=1)
    motor_examples: int = Field(ge=0)
    communication_examples: int = Field(ge=0)

    @classmethod
    def train(
        cls,
        traces: Iterable[PlayerDecisionTraceV1],
        communication_traces: Iterable[CommunicationDecisionTraceV1] = (),
        motor_traces: Iterable[MotorDecisionTraceV1] = (),
    ) -> "LearnedPlayerModel":
        action_rows = []
        for trace in traces:
            legal = _sorted_actions(trace.legal_actions)
            if trace.selected_action not in legal:
                continue
            state = conditioned_features(trace.observation)
            candidates = [_action_features(action) for action in legal]
            action_rows.append((state, candidates, legal.index(trace.selected_action)))
        if not action_rows:
            raise ValueError("no compatible player decision traces to train on")

        comm_rows = []
        for trace in communication_traces:
            legal = _sorted_comms(trace.legal_actions)
            if trace.selected_action not in legal:
                continue
            state = conditioned_features(trace.observation)
            candidates = [_communication_features(action) for action in legal]
            comm_rows.append((state, candidates, legal.index(trace.selected_action)))

        motor_rows = []
        for trace in motor_traces:
            legal = _sorted_controls(trace.legal_controls)
            if trace.selected_control not in legal:
                continue
            state = conditioned_features(trace.observation)
            candidates = [_motor_features(control) for control in legal]
            motor_rows.append((state, candidates, legal.index(trace.selected_control)))

        state_dim = len(action_rows[0][0])
        action_dim = len(action_rows[0][1][0])
        action_weights = _fit_ranker(action_rows, action_dim, state_dim)
        motor_dim = len(_motor_features(MotorControl()))
        motor_weights = (
            _fit_ranker(motor_rows, motor_dim, state_dim)
            if motor_rows
            else np.zeros((motor_dim, state_dim), dtype=np.float64)
        )
        comm_dim = len(_communication_features(CommunicationAction()))
        communication_weights = (
            _fit_ranker(comm_rows, comm_dim, state_dim)
            if comm_rows
            else np.zeros((comm_dim, state_dim), dtype=np.float64)
        )
        return cls(
            action_weights=action_weights,
            motor_weights=motor_weights,
            communication_weights=communication_weights,
            training_examples=len(action_rows),
            motor_examples=len(motor_rows),
            communication_examples=len(comm_rows),
        )

    def make_policy(self) -> "LearnedPlayerPolicy":
        return LearnedPlayerPolicy(self)

    def save(self, path: Path) -> None:
        payload = {
            "policy_version": POLICY_VERSION,
            "observation_version": OBSERVATION_VERSION,
            "encoder_version": ENCODER_VERSION,
            "action_vocab": [str(kind) for kind in ACTION_VOCAB],
            "motor_movement_vocab": [str(kind) for kind in MOTOR_MOVEMENT_VOCAB],
            "movement_pace_vocab": [str(kind) for kind in MOVEMENT_PACE_VOCAB],
            "claim_kind_vocab": [str(kind) for kind in CLAIM_KIND_VOCAB],
            "claim_value_vocab": [str(value) for value in CLAIM_VALUE_VOCAB],
            "action_weights": self.action_weights.tolist(),
            "motor_weights": self.motor_weights.tolist(),
            "communication_weights": self.communication_weights.tolist(),
            "training_examples": self.training_examples,
            "motor_examples": self.motor_examples,
            "communication_examples": self.communication_examples,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "LearnedPlayerModel":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("policy_version") != POLICY_VERSION:
            raise ValueError("checkpoint policy version is incompatible")
        if payload.get("observation_version") != OBSERVATION_VERSION:
            raise ValueError("checkpoint observation version is incompatible")
        if payload.get("encoder_version") != ENCODER_VERSION:
            raise ValueError("checkpoint encoder version is incompatible")
        if tuple(payload.get("action_vocab", ())) != tuple(
            str(kind) for kind in ACTION_VOCAB
        ):
            raise ValueError("checkpoint action vocabulary is incompatible")
        if tuple(payload.get("motor_movement_vocab", ())) != tuple(
            str(kind) for kind in MOTOR_MOVEMENT_VOCAB
        ):
            raise ValueError("checkpoint motor-movement vocabulary is incompatible")
        if tuple(payload.get("movement_pace_vocab", ())) != tuple(
            str(kind) for kind in MOVEMENT_PACE_VOCAB
        ):
            raise ValueError("checkpoint movement-pace vocabulary is incompatible")
        if tuple(payload.get("claim_kind_vocab", ())) != tuple(
            str(kind) for kind in CLAIM_KIND_VOCAB
        ):
            raise ValueError("checkpoint communication vocabulary is incompatible")
        if tuple(payload.get("claim_value_vocab", ())) != tuple(
            str(value) for value in CLAIM_VALUE_VOCAB
        ):
            raise ValueError("checkpoint claim-value vocabulary is incompatible")
        return cls(
            action_weights=np.asarray(payload["action_weights"], dtype=np.float64),
            motor_weights=np.asarray(payload["motor_weights"], dtype=np.float64),
            communication_weights=np.asarray(
                payload["communication_weights"], dtype=np.float64
            ),
            training_examples=int(payload["training_examples"]),
            motor_examples=int(payload["motor_examples"]),
            communication_examples=int(payload["communication_examples"]),
        )


class LearnedPlayerPolicy:
    version = POLICY_VERSION

    def __init__(self, model: LearnedPlayerModel):
        self.model = model

    def action_probabilities(
        self, obs: PlayerObservation, legal: list[Action]
    ) -> list[tuple[Action, float]]:
        ordered = _sorted_actions(legal)
        state = conditioned_features(obs)
        matrix = np.stack([_action_features(action) for action in ordered])
        probs = _softmax(matrix @ self.model.action_weights @ state)
        return list(zip(ordered, (float(value) for value in probs)))

    def decide(
        self,
        obs: PlayerObservation,
        legal: list[Action],
        rng: np.random.Generator,
    ) -> Action:
        ranked = self.action_probabilities(obs, legal)
        probabilities = np.asarray([probability for _, probability in ranked])
        # Sampling preserves the stochastic expert's tactical variety.  The
        # injected per-player RNG keeps the choice byte-identical on replay.
        return ranked[int(rng.choice(len(ranked), p=probabilities))][0]

    def control_probabilities(
        self, obs: PlayerObservation, legal: list[MotorControl]
    ) -> list[tuple[MotorControl, float]]:
        ordered = _sorted_controls(legal)
        state = conditioned_features(obs)
        matrix = np.stack([_motor_features(control) for control in ordered])
        probabilities = _softmax(matrix @ self.model.motor_weights @ state)
        return list(zip(ordered, (float(value) for value in probabilities)))

    def control(
        self,
        obs: PlayerObservation,
        legal: list[MotorControl],
        rng: np.random.Generator,
    ) -> MotorControl:
        del rng  # low-level steering should not twitch between tied frames
        if self.model.motor_examples == 0:
            desired_movement = (
                MotorMovement.ADVANCE
                if obs.self_state.has_active_route else MotorMovement.HOLD
            )
            compatible = [
                control for control in legal
                if control.movement == desired_movement
                and control.pace == MovementPace.RUN
            ]
            return min(
                compatible or legal,
                key=lambda control: (
                    abs(control.turn_degrees), control.model_dump_json()
                ),
            )
        ranked = self.control_probabilities(obs, legal)
        return max(
            ranked, key=lambda item: (item[1], item[0].model_dump_json())
        )[0]

    def communicate(
        self,
        obs: PlayerObservation,
        legal: list[CommunicationAction],
        rng: np.random.Generator,
    ) -> CommunicationAction:
        ordered = _sorted_comms(legal)
        state = conditioned_features(obs)
        matrix = np.stack([_communication_features(action) for action in ordered])
        scores = matrix @ self.model.communication_weights @ state
        probabilities = _softmax(scores)
        return ordered[int(rng.choice(len(ordered), p=probabilities))]


class RecordingPlayerPolicy:
    """Typed demonstration recorder around any acting player policy."""

    def __init__(self, delegate: PlayerPolicy):
        self.delegate = delegate
        self.traces: list[PlayerDecisionTraceV1] = []
        self.motor_traces: list[MotorDecisionTraceV1] = []
        self.communication_traces: list[CommunicationDecisionTraceV1] = []

    def decide(
        self,
        obs: PlayerObservation,
        legal: list[Action],
        rng: np.random.Generator,
    ) -> Action:
        selected = self.delegate.decide(obs, legal, rng)
        self.traces.append(
            PlayerDecisionTraceV1(
                observation=obs,
                legal_actions=tuple(legal),
                selected_action=selected,
            )
        )
        return selected

    def control(
        self,
        obs: PlayerObservation,
        legal: list[MotorControl],
        rng: np.random.Generator,
    ) -> MotorControl:
        choose = getattr(self.delegate, "control", None)
        selected = choose(obs, legal, rng) if callable(choose) else legal[0]
        self.motor_traces.append(
            MotorDecisionTraceV1(
                observation=obs,
                legal_controls=tuple(legal),
                selected_control=selected,
            )
        )
        return selected

    def communicate(
        self,
        obs: PlayerObservation,
        legal: list[CommunicationAction],
        rng: np.random.Generator,
    ) -> CommunicationAction:
        decide = getattr(self.delegate, "communicate", None)
        selected = decide(obs, legal, rng) if callable(decide) else legal[0]
        self.communication_traces.append(
            CommunicationDecisionTraceV1(
                observation=obs,
                legal_actions=tuple(legal),
                selected_action=selected,
            )
        )
        return selected


def imitation_metrics(
    model: LearnedPlayerModel,
    traces: Iterable[PlayerDecisionTraceV1],
) -> dict[str, float | dict[str, int] | dict[str, float]]:
    policy = model.make_policy()
    rows = list(traces)
    if not rows:
        return {
            "examples": 0.0,
            "action_accuracy": 0.0,
            "legal_rate": 0.0,
            "majority_baseline": 0.0,
            "macro_action_recall": 0.0,
            "non_hold_accuracy": 0.0,
            "mean_selected_probability": 0.0,
            "expected_non_hold_rate": 0.0,
            "action_counts": {},
            "predicted_action_counts": {},
            "expected_action_counts": {},
            "per_action_recall": {},
        }
    correct = 0
    legal_count = 0
    selected_counts: dict[str, int] = {}
    predicted_counts: dict[str, int] = {}
    correct_by_action: dict[str, int] = {}
    expected_counts: Counter[str] = Counter()
    selected_probability = 0.0
    for trace in rows:
        ranked = policy.action_probabilities(
            trace.observation, list(trace.legal_actions)
        )
        for candidate, probability in ranked:
            expected_counts[str(candidate.type)] += probability
            if candidate == trace.selected_action:
                selected_probability += probability
        selected = max(
            ranked, key=lambda item: (item[1], item[0].model_dump_json())
        )[0]
        correct += selected == trace.selected_action
        legal_count += selected in trace.legal_actions
        target = str(trace.selected_action.type)
        predicted = str(selected.type)
        selected_counts[target] = selected_counts.get(target, 0) + 1
        predicted_counts[predicted] = predicted_counts.get(predicted, 0) + 1
        correct_by_action[target] = correct_by_action.get(target, 0) + int(
            selected == trace.selected_action
        )
    per_action_recall = {
        action: round(correct_by_action.get(action, 0) / count, 4)
        for action, count in sorted(selected_counts.items())
    }
    non_hold_total = sum(
        count for action, count in selected_counts.items() if action != str(ActionType.HOLD)
    )
    non_hold_correct = sum(
        correct_by_action.get(action, 0)
        for action in selected_counts
        if action != str(ActionType.HOLD)
    )
    return {
        "examples": float(len(rows)),
        "action_accuracy": round(correct / len(rows), 4),
        "legal_rate": round(legal_count / len(rows), 4),
        "majority_baseline": round(max(selected_counts.values()) / len(rows), 4),
        "macro_action_recall": round(
            sum(per_action_recall.values()) / len(per_action_recall), 4
        ),
        "non_hold_accuracy": round(
            non_hold_correct / non_hold_total if non_hold_total else 0.0, 4
        ),
        "mean_selected_probability": round(selected_probability / len(rows), 4),
        "expected_non_hold_rate": round(
            sum(
                count
                for action, count in expected_counts.items()
                if action != str(ActionType.HOLD)
            )
            / len(rows),
            4,
        ),
        "action_counts": dict(sorted(selected_counts.items())),
        "predicted_action_counts": dict(sorted(predicted_counts.items())),
        "expected_action_counts": {
            action: round(count, 2)
            for action, count in sorted(expected_counts.items())
        },
        "per_action_recall": per_action_recall,
    }


def communication_imitation_metrics(
    model: LearnedPlayerModel,
    traces: Iterable[CommunicationDecisionTraceV1],
) -> dict[str, float | dict[str, int]]:
    """Held-out diagnostics for the separate speak/withhold policy head."""
    rows = list(traces)
    if not rows:
        return {
            "examples": 0.0,
            "accuracy": 0.0,
            "macro_speak_recall": 0.0,
            "selected_counts": {},
            "predicted_counts": {},
        }
    selected_counts: Counter[str] = Counter()
    predicted_counts: Counter[str] = Counter()
    correct_counts: Counter[str] = Counter()
    correct = 0
    for trace in rows:
        ordered = _sorted_comms(trace.legal_actions)
        state = conditioned_features(trace.observation)
        matrix = np.stack([_communication_features(action) for action in ordered])
        scores = matrix @ model.communication_weights @ state
        selected = ordered[
            max(
                range(len(ordered)),
                key=lambda index: (
                    float(scores[index]),
                    ordered[index].model_dump_json(),
                ),
            )
        ]
        target = "speak" if trace.selected_action.speak else "silent"
        predicted = "speak" if selected.speak else "silent"
        selected_counts[target] += 1
        predicted_counts[predicted] += 1
        correct += selected == trace.selected_action
        correct_counts[target] += int(selected == trace.selected_action)
    recalls = [
        correct_counts[label] / count for label, count in sorted(selected_counts.items())
    ]
    return {
        "examples": float(len(rows)),
        "accuracy": round(correct / len(rows), 4),
        "macro_speak_recall": round(sum(recalls) / len(recalls), 4),
        "selected_counts": dict(sorted(selected_counts.items())),
        "predicted_counts": dict(sorted(predicted_counts.items())),
    }


def motor_imitation_metrics(
    model: LearnedPlayerModel,
    traces: Iterable[MotorDecisionTraceV1],
) -> dict[str, float | dict[str, int]]:
    """Held-out legality and exact-command accuracy for the motor head."""
    rows = list(traces)
    if not rows:
        return {
            "examples": 0.0,
            "accuracy": 0.0,
            "legal_rate": 0.0,
            "selected_counts": {},
            "predicted_counts": {},
        }
    policy = model.make_policy()
    selected_counts: Counter[str] = Counter()
    predicted_counts: Counter[str] = Counter()
    correct = 0
    legal_count = 0
    for trace in rows:
        ranked = policy.control_probabilities(
            trace.observation, list(trace.legal_controls)
        )
        selected = max(
            ranked, key=lambda item: (item[1], item[0].model_dump_json())
        )[0]
        target = f"{trace.selected_control.movement}:{trace.selected_control.pace}"
        predicted = f"{selected.movement}:{selected.pace}"
        selected_counts[target] += 1
        predicted_counts[predicted] += 1
        correct += selected == trace.selected_control
        legal_count += selected in trace.legal_controls
    return {
        "examples": float(len(rows)),
        "accuracy": round(correct / len(rows), 4),
        "legal_rate": round(legal_count / len(rows), 4),
        "selected_counts": dict(sorted(selected_counts.items())),
        "predicted_counts": dict(sorted(predicted_counts.items())),
    }
