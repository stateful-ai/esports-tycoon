"""Dependency-light learned in-match player policy.

This mirrors the learned-manager approach: deterministic full-batch NumPy
imitation training, legal-action masking, profile-conditioned linear
hypernetwork interactions, and version-pinned JSON checkpoints.  The match
engine remains the resolver; this model only ranks candidates supplied by it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from esports_sim.policy.base import Action, ActionType, PlayerPolicy
from esports_sim.rng.tree import RngTree
from esports_sim.schemas import CommunicationAction, PlayerObservation
from esports_sim.schemas.communication import ClaimKind, ClaimValue


POLICY_VERSION = "learned-player-v1"
ENCODER_VERSION = 1
OBSERVATION_VERSION = 1
ACTION_VOCAB = tuple(sorted(ActionType, key=str))
CLAIM_KIND_VOCAB = tuple(sorted(ClaimKind, key=str))
CLAIM_VALUE_VOCAB = tuple(sorted(ClaimValue, key=str))


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


def _stable_bucket(text: str | None, buckets: int) -> np.ndarray:
    out = np.zeros(buckets, dtype=np.float64)
    if not text:
        return out
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=4).digest()
    out[int.from_bytes(digest, "big") % buckets] = 1.0
    return out


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return float(sum(rows) / len(rows)) if rows else 0.0


def encode_observation(obs: PlayerObservation) -> np.ndarray:
    """Fixed-size actor-visible state encoder; contains no hidden truth."""
    self_state = obs.self_state
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
    ]
    return np.concatenate(
        (
            np.asarray(values, dtype=np.float64),
            _stable_bucket(obs.igl_call, 6),
            _stable_bucket(self_state.callout_id, 6),
            _stable_bucket(self_state.agent_id, 4),
            _stable_bucket(self_state.weapon_id, 4),
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
            _stable_bucket(str(condition.role), 3),
            _stable_bucket(str(condition.playstyle), 3),
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
            _stable_bucket(action.weapon_id, 4),
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


class LearnedPlayerModel(BaseModel):
    """Serializable shared action and communication candidate rankers."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    action_weights: np.ndarray
    communication_weights: np.ndarray
    training_examples: int = Field(ge=1)
    communication_examples: int = Field(ge=0)

    @classmethod
    def train(
        cls,
        traces: Iterable[PlayerDecisionTraceV1],
        communication_traces: Iterable[CommunicationDecisionTraceV1] = (),
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

        state_dim = len(action_rows[0][0])
        action_dim = len(action_rows[0][1][0])
        action_weights = _fit_ranker(action_rows, action_dim, state_dim)
        comm_dim = len(_communication_features(CommunicationAction()))
        communication_weights = (
            _fit_ranker(comm_rows, comm_dim, state_dim)
            if comm_rows
            else np.zeros((comm_dim, state_dim), dtype=np.float64)
        )
        return cls(
            action_weights=action_weights,
            communication_weights=communication_weights,
            training_examples=len(action_rows),
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
            "claim_kind_vocab": [str(kind) for kind in CLAIM_KIND_VOCAB],
            "claim_value_vocab": [str(value) for value in CLAIM_VALUE_VOCAB],
            "action_weights": self.action_weights.tolist(),
            "communication_weights": self.communication_weights.tolist(),
            "training_examples": self.training_examples,
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
            communication_weights=np.asarray(
                payload["communication_weights"], dtype=np.float64
            ),
            training_examples=int(payload["training_examples"]),
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
        del rng  # deterministic argmax, matching learned-manager inference
        ranked = self.action_probabilities(obs, legal)
        return max(ranked, key=lambda item: (item[1], item[0].model_dump_json()))[0]

    def communicate(
        self,
        obs: PlayerObservation,
        legal: list[CommunicationAction],
        rng: np.random.Generator,
    ) -> CommunicationAction:
        del rng
        ordered = _sorted_comms(legal)
        state = conditioned_features(obs)
        matrix = np.stack([_communication_features(action) for action in ordered])
        scores = matrix @ self.model.communication_weights @ state
        index = max(range(len(ordered)), key=lambda i: (float(scores[i]), ordered[i].model_dump_json()))
        return ordered[index]


class RecordingPlayerPolicy:
    """Typed demonstration recorder around any acting player policy."""

    def __init__(self, delegate: PlayerPolicy):
        self.delegate = delegate
        self.traces: list[PlayerDecisionTraceV1] = []
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
) -> dict[str, float]:
    policy = model.make_policy()
    rows = list(traces)
    if not rows:
        return {"examples": 0.0, "action_accuracy": 0.0, "legal_rate": 0.0}
    correct = 0
    legal_count = 0
    eval_rng = RngTree(0).derive("learned-player", "imitation-metrics")
    for trace in rows:
        selected = policy.decide(
            trace.observation,
            list(trace.legal_actions),
            eval_rng,
        )
        correct += selected == trace.selected_action
        legal_count += selected in trace.legal_actions
    return {
        "examples": float(len(rows)),
        "action_accuracy": round(correct / len(rows), 4),
        "legal_rate": round(legal_count / len(rows), 4),
    }
