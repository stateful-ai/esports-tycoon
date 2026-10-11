"""Transfer boolean demonstrations and legal masking (authored, not run)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from esports_sim.manager.decision_env import OBSERVATION_VERSION
from esports_sim.manager.learned_manager_policy import (
    ACTION_VOCAB,
    LearnedManagerModel,
    conditioned_features,
)
from esports_sim.manager.manager_policy import generate_profile


def _observation(can_accept=True):
    return {
        "observation_version": OBSERVATION_VERSION,
        "season": 1,
        "week": 1,
        "features": {},
        "legal_actions": {
            "advance": {"enabled": True},
            "transfer_offer": {
                "enabled": True,
                "offers": [{
                    "player_id": "seller-player",
                    "to_team": "buyer-team",
                    "can_accept": can_accept,
                }],
            },
        },
    }


def _answer(model, obs):
    return model.make_policy(generate_profile(41, "offer-choice"))._build_action(
        obs, "transfer_offer", conditioned_features(obs)
    )


@pytest.mark.parametrize("accept", [False, True])
def test_demonstrated_transfer_boolean_survives_clone_and_checkpoint(tmp_path, accept):
    obs = _observation()
    params = {"player_id": "seller-player", "to_team": "buyer-team", "accept": accept}
    model = LearnedManagerModel.train([{
        "observation": obs,
        "action": {"kind": "transfer_offer", "params": params},
    }])
    assert model.categorical_labels["transfer_accept"] == ("false", "true")
    path = tmp_path / "manager.json"
    model.save(path)
    for candidate in (model, model.clone(), LearnedManagerModel.load(path)):
        assert _answer(candidate, obs) == {"kind": "transfer_offer", "params": params}
        blocked = _answer(candidate, _observation(can_accept=False))
        assert blocked["params"] == {**params, "accept": False}
        assert _answer(candidate, obs) == _answer(candidate, obs)


@pytest.mark.parametrize("can_accept", [False, True])
def test_checkpoint_without_boolean_head_retains_legal_fallback(tmp_path, can_accept):
    obs = _observation(can_accept)
    model = LearnedManagerModel(
        action_weights=np.zeros((len(ACTION_VOCAB), len(conditioned_features(obs))))
    )
    path = tmp_path / "legacy.json"
    model.save(path)
    loaded = LearnedManagerModel.load(path)
    assert "transfer_accept" not in loaded.categorical_weights
    assert _answer(loaded, obs)["params"]["accept"] is can_accept


@pytest.mark.parametrize("malformation", ["labels", "shape", "nonfinite", "missing_weights"])
def test_checkpoint_rejects_malformed_transfer_boolean_head(tmp_path, malformation):
    obs = _observation()
    width = len(conditioned_features(obs))
    model = LearnedManagerModel(
        action_weights=np.zeros((len(ACTION_VOCAB), width)),
        categorical_weights={"transfer_accept": np.zeros((2, width))},
        categorical_labels={"transfer_accept": ("false", "true")},
    )
    path = tmp_path / "malformed.json"
    model.save(path)
    payload = json.loads(path.read_text())
    if malformation == "labels":
        payload["categorical_labels"]["transfer_accept"] = ["true", "false"]
    elif malformation == "shape":
        payload["categorical_weights"]["transfer_accept"] = [[0.0]]
    elif malformation == "nonfinite":
        payload["categorical_weights"]["transfer_accept"][0][0] = float("nan")
    else:
        del payload["categorical_weights"]["transfer_accept"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="transfer accept head"):
        LearnedManagerModel.load(path)
