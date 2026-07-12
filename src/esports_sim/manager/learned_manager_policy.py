"""Dependency-light learned manager policy.

The policy uses a permutation-invariant set encoder for roster, market, and
staff rows. Manager profile axes condition every head through linear
hypernetwork interactions (equivalent to feature-wise affine/FiLM modulation).
All heads are masked by the legal actions supplied by ``decision_env``.

Training is deterministic full-batch NumPy optimization. Checkpoints are plain
JSON and pin the observation, encoder, action-vocabulary, and policy versions.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from esports_sim.manager.decision_env import OBSERVATION_VERSION, SUPPORTED_ACTIONS
from esports_sim.manager.manager_policy import ManagerProfile
from esports_sim.manager.training import DEV_FOCUS_OPTIONS, FOCUS_OPTIONS

ENCODER_VERSION = 1
POLICY_VERSION = "learned-manager-v1"
PROFILE_KEYS = (
    "risk", "youth", "loyalty", "analytics", "investment", "experimentation"
)
ACTION_VOCAB = tuple(sorted(SUPPORTED_ACTIONS))
TACTIC_DIALS = (
    "aggression", "pace", "util_discipline", "eco_greed", "map_control"
)

_GLOBAL = (
    ("week", 30.0), ("wins", 20.0), ("losses", 20.0),
    ("round_diff", 200.0), ("league_position", 16.0),
    ("balance", 1_000_000.0), ("weekly_payroll", 100_000.0),
    ("reputation", 100.0), ("fan_count", 1_000_000.0),
    ("chemistry", 100.0), ("sentiment", 100.0),
    ("roster_ca", 100.0), ("roster_age", 40.0),
    ("roster_morale", 100.0), ("roster_stamina", 100.0),
    ("roster_form", 100.0), ("roster_confidence", 100.0),
)
_ROSTER_FIELDS = (
    ("ca", 100.0), ("age", 40.0), ("salary", 100_000.0),
    ("contract_weeks", 80.0), ("stamina", 100.0), ("morale", 100.0),
    ("form", 100.0), ("confidence", 100.0),
)
_FA_FIELDS = (
    ("perceived_quality", 100.0), ("age", 40.0),
    ("asking_salary", 100_000.0), ("progress", 1.0),
)
_STAFF_FIELDS = (
    ("quality", 100.0), ("salary", 100_000.0),
    ("age", 70.0), ("seasons_experience", 20.0),
)


def _pool(rows: list[dict[str, Any]], fields: tuple[tuple[str, float], ...]) -> list[float]:
    if not rows:
        return [0.0] * (len(fields) * 2)
    rows = sorted(
        rows,
        key=lambda row: str(
            row.get("id", row.get("player_id", row.get("name", row.get("handle", ""))))
        ),
    )
    matrix = np.asarray(
        [[float(row.get(key, 0.0)) / scale for key, scale in fields] for row in rows],
        dtype=np.float64,
    )
    return [*matrix.mean(axis=0).tolist(), *matrix.max(axis=0).tolist()]


def encode_observation(obs: dict[str, Any]) -> np.ndarray:
    """Encode manager-visible state; row ordering cannot affect the result."""
    features = obs["features"]
    phase = int(features.get("phase", 0.0))
    values = [float(features.get(key, 0.0)) / scale for key, scale in _GLOBAL]
    values.extend(1.0 if phase == i else 0.0 for i in range(3))
    values.extend(_pool(obs.get("roster", []), _ROSTER_FIELDS))
    values.extend(_pool(obs.get("free_agents", []), _FA_FIELDS))
    values.extend(_pool(obs.get("staff_candidates", []), _STAFF_FIELDS))
    values.extend(
        [
            len(obs.get("roster", [])) / 10.0,
            len(obs.get("free_agents", [])) / 100.0,
            len(obs.get("staff_candidates", [])) / 100.0,
            1.0 if obs.get("upcoming_fixture") else 0.0,
            1.0 if obs.get("opponent") else 0.0,
        ]
    )
    return np.asarray(values, dtype=np.float64)


def profile_vector(profile: dict[str, float]) -> np.ndarray:
    return np.asarray([float(profile.get(key, 0.5)) for key in PROFILE_KEYS])


def conditioned_features(obs: dict[str, Any]) -> np.ndarray:
    base = encode_observation(obs)
    profile = profile_vector(obs.get("manager_profile", {}))
    # Effective weights become W(base) + sum(profile_i * W_i(base)): a small
    # linear hypernetwork / FiLM adapter over the shared state encoder.
    interaction = np.outer(profile - 0.5, base).reshape(-1)
    return np.concatenate(([1.0], base, profile, interaction))


def _softmax(logits: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    if mask is not None:
        logits = np.where(mask, logits, -1e9)
    shifted = logits - np.max(logits)
    exps = np.exp(np.clip(shifted, -60.0, 0.0))
    if mask is not None:
        exps *= mask
    total = exps.sum()
    return exps / total if total > 0 else np.ones_like(exps) / len(exps)


def _fit_softmax(
    xs: np.ndarray,
    ys: np.ndarray,
    n_classes: int,
    masks: np.ndarray | None = None,
    *,
    epochs: int = 240,
    learning_rate: float = 0.35,
    l2: float = 1e-4,
) -> np.ndarray:
    weights = np.zeros((n_classes, xs.shape[1]), dtype=np.float64)
    for _ in range(epochs):
        grad = np.zeros_like(weights)
        for i, x in enumerate(xs):
            probs = _softmax(weights @ x, masks[i] if masks is not None else None)
            probs[ys[i]] -= 1.0
            grad += np.outer(probs, x)
        grad = grad / max(len(xs), 1) + l2 * weights
        weights -= learning_rate * grad
    return weights


def _legal_mask(obs: dict[str, Any], vocab: tuple[str, ...]) -> np.ndarray:
    legal = obs["legal_actions"]
    return np.asarray(
        [bool(legal.get(kind, {}).get("enabled", False)) for kind in vocab], dtype=bool
    )


def _sequence_masks(rows: list[dict[str, Any]]) -> np.ndarray:
    used_by: dict[tuple[str, int, int], set[str]] = {}
    masks = []
    for index, row in enumerate(rows):
        obs = row["observation"]
        key = (
            str(row.get("run_id", f"legacy-stream-{index}")),
            int(obs["season"]),
            int(obs["week"]),
        )
        used = used_by.setdefault(key, set())
        mask = _legal_mask(obs, ACTION_VOCAB)
        for i, kind in enumerate(ACTION_VOCAB):
            if kind in used and kind not in ("advance", "sign", "negotiate_offer"):
                mask[i] = False
        masks.append(mask)
        used.add(row["action"]["kind"])
    return np.stack(masks)


def _target_category(target: str) -> str:
    if target == "market":
        return "market"
    if ":" in target:
        return target.split(":", 1)[0]
    return "team"


_CATEGORICAL_SPECS: dict[str, tuple[str, str]] = {
    "training_focus": ("set_training", "focus"),
    "facility": ("facility_upgrade", "facility"),
    "sponsor_structure": ("sponsor_respond", "structure"),
    "dev_focus": ("set_dev_plan", "dev_focus"),
    "team_talk": ("set_game_plan", "team_talk"),
}


@dataclass
class LearnedManagerModel:
    action_weights: np.ndarray
    categorical_weights: dict[str, np.ndarray] = field(default_factory=dict)
    categorical_labels: dict[str, tuple[str, ...]] = field(default_factory=dict)
    tactic_weights: np.ndarray | None = None
    candidate_weights: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def train(cls, traces: Iterable[dict[str, Any]]) -> "LearnedManagerModel":
        rows = [
            trace for trace in traces
            if not trace.get("invalid")
            and trace.get("observation", {}).get("observation_version") == OBSERVATION_VERSION
            and trace.get("action", {}).get("kind") in ACTION_VOCAB
        ]
        if not rows:
            raise ValueError("no compatible decision traces to train on")
        xs = np.stack([conditioned_features(row["observation"]) for row in rows])
        ys = np.asarray([ACTION_VOCAB.index(row["action"]["kind"]) for row in rows])
        masks = _sequence_masks(rows)
        action_weights = _fit_softmax(xs, ys, len(ACTION_VOCAB), masks)

        categorical_weights: dict[str, np.ndarray] = {}
        categorical_labels: dict[str, tuple[str, ...]] = {}
        for head, (kind, field_name) in _CATEGORICAL_SPECS.items():
            examples = [
                (conditioned_features(row["observation"]), str(row["action"]["params"].get(field_name, "")))
                for row in rows
                if row["action"]["kind"] == kind
                and row["action"]["params"].get(field_name)
            ]
            if not examples:
                continue
            labels = tuple(sorted({label for _, label in examples}))
            head_x = np.stack([x for x, _ in examples])
            head_y = np.asarray([labels.index(label) for _, label in examples])
            categorical_weights[head] = _fit_softmax(head_x, head_y, len(labels))
            categorical_labels[head] = labels

        scout_examples = [
            (
                conditioned_features(row["observation"]),
                _target_category(str(row["action"]["params"].get("target", "market"))),
            )
            for row in rows
            if row["action"]["kind"] == "set_scout"
        ]
        if scout_examples:
            labels = tuple(sorted({label for _, label in scout_examples}))
            categorical_weights["scout_mode"] = _fit_softmax(
                np.stack([x for x, _ in scout_examples]),
                np.asarray([labels.index(label) for _, label in scout_examples]),
                len(labels),
            )
            categorical_labels["scout_mode"] = labels

        tactic_examples = [row for row in rows if row["action"]["kind"] == "set_tactics"]
        tactic_weights = None
        if tactic_examples:
            tx = np.stack([conditioned_features(row["observation"]) for row in tactic_examples])
            ty = np.asarray(
                [
                    [float(row["action"]["params"].get(dial, 50.0)) / 100.0 for dial in TACTIC_DIALS]
                    for row in tactic_examples
                ]
            )
            ridge = np.eye(tx.shape[1]) * 1e-3
            ridge[0, 0] = 0.0
            tactic_weights = np.linalg.solve(tx.T @ tx + ridge, tx.T @ ty)

        model = cls(
            action_weights=action_weights,
            categorical_weights=categorical_weights,
            categorical_labels=categorical_labels,
            tactic_weights=tactic_weights,
            metadata={"training_examples": len(rows)},
        )
        model.candidate_weights = model._fit_candidate_heads(rows)
        return model

    def _fit_candidate_heads(self, rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
        heads: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
        for row in rows:
            kind = row["action"]["kind"]
            selected = _selected_candidate(row["action"])
            if selected is None:
                continue
            candidates = _candidate_rows(row["observation"], kind)
            selected_row = next((vec for cid, vec in candidates if cid == selected), None)
            if selected_row is None:
                continue
            for cid, vec in candidates:
                if cid != selected:
                    heads.setdefault(kind, []).append((selected_row, vec))
        out: dict[str, np.ndarray] = {}
        for kind, pairs in heads.items():
            if not pairs:
                continue
            weight = np.zeros(len(pairs[0][0]), dtype=np.float64)
            for _ in range(120):
                grad = np.zeros_like(weight)
                for positive, negative in pairs:
                    diff = positive - negative
                    score = float(np.clip(weight @ diff, -40.0, 40.0))
                    grad += -diff / (1.0 + np.exp(score))
                weight -= 0.2 * (grad / len(pairs) + 1e-4 * weight)
            out[kind] = weight
        return out

    def make_policy(self, profile: ManagerProfile) -> "LearnedManagerPolicy":
        return LearnedManagerPolicy(self, profile)

    def clone(self) -> "LearnedManagerModel":
        """Return an independent in-memory checkpoint copy."""
        return LearnedManagerModel(
            action_weights=self.action_weights.copy(),
            categorical_weights={
                key: value.copy() for key, value in self.categorical_weights.items()
            },
            categorical_labels=dict(self.categorical_labels),
            tactic_weights=(
                self.tactic_weights.copy() if self.tactic_weights is not None else None
            ),
            candidate_weights={
                key: value.copy() for key, value in self.candidate_weights.items()
            },
            metadata=copy.deepcopy(self.metadata),
        )

    def save(self, path: Path, *, metadata: dict[str, Any] | None = None) -> None:
        payload = {
            "policy_version": POLICY_VERSION,
            "observation_version": OBSERVATION_VERSION,
            "encoder_version": ENCODER_VERSION,
            "action_vocab": list(ACTION_VOCAB),
            "profile_keys": list(PROFILE_KEYS),
            "action_weights": self.action_weights.tolist(),
            "categorical_weights": {
                key: value.tolist() for key, value in sorted(self.categorical_weights.items())
            },
            "categorical_labels": {
                key: list(value) for key, value in sorted(self.categorical_labels.items())
            },
            "tactic_weights": self.tactic_weights.tolist() if self.tactic_weights is not None else None,
            "candidate_weights": {
                key: value.tolist() for key, value in sorted(self.candidate_weights.items())
            },
            "metadata": {**self.metadata, **(metadata or {})},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LearnedManagerModel":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("policy_version") != POLICY_VERSION:
            raise ValueError("checkpoint policy version is incompatible")
        if payload["observation_version"] != OBSERVATION_VERSION:
            raise ValueError("checkpoint observation version is incompatible")
        if payload["encoder_version"] != ENCODER_VERSION:
            raise ValueError("checkpoint encoder version is incompatible")
        if tuple(payload["action_vocab"]) != ACTION_VOCAB:
            raise ValueError("checkpoint action vocabulary is incompatible")
        if tuple(payload.get("profile_keys", ())) != PROFILE_KEYS:
            raise ValueError("checkpoint manager-profile schema is incompatible")
        return cls(
            action_weights=np.asarray(payload["action_weights"], dtype=np.float64),
            categorical_weights={
                key: np.asarray(value, dtype=np.float64)
                for key, value in payload.get("categorical_weights", {}).items()
            },
            categorical_labels={
                key: tuple(value) for key, value in payload.get("categorical_labels", {}).items()
            },
            tactic_weights=(
                np.asarray(payload["tactic_weights"], dtype=np.float64)
                if payload.get("tactic_weights") is not None else None
            ),
            candidate_weights={
                key: np.asarray(value, dtype=np.float64)
                for key, value in payload.get("candidate_weights", {}).items()
            },
            metadata=dict(payload.get("metadata", {})),
        )


def _stable_bucket(text: str, buckets: int = 4) -> list[float]:
    digest = hashlib.blake2b(text.encode(), digest_size=4).digest()
    index = int.from_bytes(digest, "big") % buckets
    return [1.0 if i == index else 0.0 for i in range(buckets)]


def _candidate_rows(obs: dict[str, Any], kind: str) -> list[tuple[str, np.ndarray]]:
    legal = obs["legal_actions"].get(kind, {})
    own = {row["id"]: row for row in obs.get("roster", [])}
    free = {row["player_id"]: row for row in obs.get("free_agents", [])}
    staff = {row["id"]: row for row in obs.get("staff_candidates", [])}
    ids: list[str] = []
    if "player_ids" in legal:
        ids = list(legal["player_ids"])
    elif "candidate_ids" in legal:
        ids = list(legal["candidate_ids"])
    rows: list[tuple[str, np.ndarray]] = []
    for cid in ids:
        if cid in own:
            row = own[cid]
            values = [
                row["ca"] / 100.0, row["age"] / 40.0, row["salary"] / 100_000.0,
                row["contract_weeks"] / 80.0, row["stamina"] / 100.0,
                row["morale"] / 100.0, row["form"] / 100.0,
                row["confidence"] / 100.0, 1.0, 0.0,
            ]
        elif cid in free:
            row = free[cid]
            values = [
                row["perceived_quality"] / 100.0, row["age"] / 40.0,
                row["asking_salary"] / 100_000.0, 0.0, 0.5, 0.5, 0.5, 0.5,
                0.0, 1.0,
            ]
        elif cid in staff:
            row = staff[cid]
            values = [
                row["quality"] / 100.0, row["age"] / 70.0,
                row["salary"] / 100_000.0, row["seasons_experience"] / 20.0,
                0.5, 0.5, 0.5, 0.5, 0.0, 0.0,
            ]
        else:
            values = [0.0] * 10
        values.extend(_stable_bucket(cid))
        rows.append((cid, np.asarray(values, dtype=np.float64)))
    return rows


def _selected_candidate(action: dict[str, Any]) -> str | None:
    params = action.get("params", {})
    for key in ("player_id", "candidate_id"):
        if params.get(key):
            return str(params[key])
    return None


class LearnedManagerPolicy:
    version = POLICY_VERSION

    def __init__(self, model: LearnedManagerModel, profile: ManagerProfile) -> None:
        self.model = model
        self.profile = profile
        self._used: dict[tuple[int, int], set[str]] = {}
        self.last_decision: dict[str, Any] = {}

    def _profiled(self, obs: dict[str, Any]) -> dict[str, Any]:
        expected = self.profile.to_dict()
        if obs.get("manager_profile") == expected:
            return obs
        return {**obs, "manager_profile": expected}

    def _predict_head(self, name: str, x: np.ndarray, default: str) -> str:
        weights = self.model.categorical_weights.get(name)
        labels = self.model.categorical_labels.get(name)
        if weights is None or not labels:
            return default
        return labels[int(np.argmax(weights @ x))]

    def _candidate(self, obs: dict[str, Any], kind: str) -> str:
        rows = _candidate_rows(obs, kind)
        if not rows:
            return ""
        weight = self.model.candidate_weights.get(kind)
        if weight is None:
            return max(rows, key=lambda item: (item[1][0], item[0]))[0]
        return max(rows, key=lambda item: (float(weight @ item[1]), item[0]))[0]

    def _action_distribution(
        self, obs: dict[str, Any], *, temperature: float = 1.0
    ) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
        obs = self._profiled(obs)
        x = conditioned_features(obs)
        mask = _legal_mask(obs, ACTION_VOCAB)
        week = (int(obs["season"]), int(obs["week"]))
        used = self._used.get(week, set())
        for i, kind in enumerate(ACTION_VOCAB):
            if kind in used and kind not in ("advance", "sign", "negotiate_offer"):
                mask[i] = False
        logits = self.model.action_weights @ x
        probs = _softmax(logits / max(float(temperature), 1e-6), mask)
        return obs, x, mask, probs

    def action_probabilities(self, obs: dict[str, Any]) -> dict[str, float]:
        _, _, _, probs = self._action_distribution(obs)
        return {kind: round(float(probs[i]), 6) for i, kind in enumerate(ACTION_VOCAB)}

    def choose_action(self, obs: dict[str, Any]) -> dict[str, Any]:
        obs, x, _, probs = self._action_distribution(obs)
        probabilities = {
            kind: round(float(probs[i]), 6) for i, kind in enumerate(ACTION_VOCAB)
        }
        kind = max(ACTION_VOCAB, key=lambda name: (probabilities[name], name))
        week = (int(obs["season"]), int(obs["week"]))
        self._used.setdefault(week, set()).add(kind)
        action = self._build_action(obs, kind, x)
        self.last_decision = {
            "selected": kind,
            "probability": probabilities[kind],
            "legal_action_count": sum(
                1 for value in obs["legal_actions"].values() if value.get("enabled")
            ),
            "profile": self.profile.to_dict(),
            "top_actions": sorted(
                probabilities.items(), key=lambda item: (-item[1], item[0])
            )[:5],
            "action": action,
        }
        return action

    def _build_action(self, obs: dict[str, Any], kind: str, x: np.ndarray) -> dict[str, Any]:
        legal = obs["legal_actions"][kind]
        params: dict[str, Any] = {}
        if kind == "set_training":
            focus = self._predict_head("training_focus", x, "tactical")
            params = {"focus": focus if focus in FOCUS_OPTIONS else "tactical"}
        elif kind == "set_tactics":
            values = (
                x @ self.model.tactic_weights if self.model.tactic_weights is not None
                else np.full(len(TACTIC_DIALS), 0.5)
            )
            params = {
                dial: round(float(np.clip(value, 0.0, 1.0) * 100.0), 1)
                for dial, value in zip(TACTIC_DIALS, values)
            }
        elif kind == "set_scout":
            targets = legal["targets"]
            mode = self._predict_head("scout_mode", x, "market")
            choices = [target for target in targets if _target_category(target) == mode]
            params = {"target": choices[0] if choices else targets[0]}
        elif kind in ("sign", "release", "renew", "rein_streaming", "negotiate_open"):
            params = {"player_id": self._candidate(obs, kind)}
        elif kind == "swap":
            params = dict(legal["pairs"][0])
        elif kind == "set_dev_plan":
            focus = self._predict_head("dev_focus", x, "auto")
            params = {
                "player_id": self._candidate(obs, kind),
                "dev_focus": focus if focus in DEV_FOCUS_OPTIONS else "auto",
                "training_intensity": "normal",
            }
        elif kind == "mentor":
            params = dict(legal["pairs"][0]) if legal["pairs"] else {
                "protege_id": legal["clear_ids"][0], "mentor_id": ""
            }
        elif kind == "hire_staff":
            params = {"candidate_id": self._candidate(obs, kind)}
        elif kind == "release_staff":
            params = {"role": legal["roles"][0]}
        elif kind == "facility_upgrade":
            predicted = self._predict_head("facility", x, legal["options"][0]["facility"])
            option = next(
                (option for option in legal["options"] if option["facility"] == predicted),
                legal["options"][0],
            )
            params = {"facility": option["facility"]}
        elif kind == "sponsor_respond":
            structure = self._predict_head("sponsor_structure", x, "steady")
            accepts = [
                option for option in legal["options"]
                if option["accept"] and option["structure"] == structure
            ]
            params = dict(accepts[0] if accepts else legal["options"][0])
        elif kind == "set_game_plan":
            params = {
                "team_talk": self._predict_head("team_talk", x, "focus"),
                "focus_target": legal["focus_target_ids"][0]
                if legal["focus_target_ids"] else "",
            }
        elif kind == "talk":
            params = dict(legal["options"][0])
        elif kind == "negotiate_offer":
            option = legal["options"][0]
            neg = obs["negotiations"][option["player_id"]]
            params = {
                "player_id": option["player_id"],
                "salary": neg["demand_salary"],
                "weeks": neg["demand_weeks"],
            }
        elif kind == "negotiate_cancel":
            params = {"player_id": legal["player_ids"][0]}
        elif kind == "accept_job":
            params = {"team_id": legal["team_ids"][0]}
        return {"kind": kind, "params": params}


def imitation_metrics(model: LearnedManagerModel, traces: Iterable[dict[str, Any]]) -> dict[str, float]:
    rows = [
        row for row in traces
        if not row.get("invalid") and row.get("action", {}).get("kind") in ACTION_VOCAB
    ]
    if not rows:
        return {"examples": 0.0, "action_accuracy": 0.0, "legal_rate": 0.0}
    correct = 0
    legal = 0
    masks = _sequence_masks(rows)
    for row, mask in zip(rows, masks):
        obs = row["observation"]
        x = conditioned_features(obs)
        prediction = ACTION_VOCAB[int(np.argmax(np.where(mask, model.action_weights @ x, -1e9)))]
        correct += prediction == row["action"]["kind"]
        legal += bool(obs["legal_actions"].get(prediction, {}).get("enabled"))
    return {
        "examples": float(len(rows)),
        "action_accuracy": round(correct / len(rows), 4),
        "legal_rate": round(legal / len(rows), 4),
    }
