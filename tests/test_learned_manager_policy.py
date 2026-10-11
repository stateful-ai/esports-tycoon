"""Learned manager encoder, imitation heads, checkpoints, and live rollouts."""

from __future__ import annotations

import json

import numpy as np
import pytest

from esports_sim.manager.learned_manager_policy import (
    ACTION_VOCAB,
    LearnedManagerModel,
    conditioned_features,
    encode_observation,
    imitation_metrics,
)
from esports_sim.manager.manager_policy import generate_profile
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.rollout import play_policy_week, run_rollout
from esports_sim.manager.decision_env import OBSERVATION_VERSION


def _demonstrations(game_data):
    profiles = [
        generate_profile(100, "learner-a"),
        generate_profile(101, "learner-b"),
    ]
    runs = [
        run_rollout(game_data, seed=seed, weeks=1, profile=profile)
        for profile in profiles
        for seed in (901, 902)
    ]
    return profiles, [trace for run in runs for trace in run.traces]


def test_set_encoder_is_permutation_invariant(game_data):
    profile = generate_profile(90, "encoder")
    run = run_rollout(game_data, seed=900, weeks=1, profile=profile)
    obs = run.traces[0]["observation"]
    shuffled = json.loads(json.dumps(obs))
    shuffled["roster"].reverse()
    shuffled["free_agents"].reverse()
    shuffled["staff_candidates"].reverse()
    assert np.array_equal(encode_observation(obs), encode_observation(shuffled))


@pytest.mark.parametrize("kind,cost_key", [("bid", "ask"), ("buyout", "fee")])
def test_transfer_candidate_head_retains_nonfirst_demonstrated_target(tmp_path, kind, cost_key):
    profile = generate_profile(124, "transfer-target")
    options = [
        {"player_id": "rival-first", "team_id": "seller-a", cost_key: 100_000},
        {"player_id": "rival-selected", "team_id": "seller-b", cost_key: 600_000},
    ]
    obs = {
        "observation_version": OBSERVATION_VERSION,
        "features": {}, "season": 1, "week": 1,
        "manager_profile": profile.to_dict(),
        "legal_actions": {
            kind: {"enabled": True, "options": options},
            "advance": {"enabled": True},
        },
    }
    model = LearnedManagerModel.train([{
        "observation": obs,
        "action": {"kind": kind, "params": {"player_id": "rival-selected"}},
    }])
    assert kind in model.candidate_weights
    path = tmp_path / "transfer.json"
    model.save(path)
    loaded = LearnedManagerModel.load(path)
    for checkpoint in (model, loaded):
        policy = checkpoint.make_policy(profile)
        assert policy.choose_action(obs) == {
            "kind": kind, "params": {"player_id": "rival-selected"},
        }
        reordered = json.loads(json.dumps(obs))
        reordered["legal_actions"][kind]["options"].reverse()
        assert checkpoint.make_policy(profile).choose_action(reordered) == {
            "kind": kind, "params": {"player_id": "rival-selected"},
        }
        # A learned preference cannot emit a target removed from the mask.
        restricted = json.loads(json.dumps(obs))
        restricted["legal_actions"][kind]["options"] = [options[0]]
        assert checkpoint.make_policy(profile).choose_action(restricted)["params"] == {
            "player_id": "rival-first",
        }

    # A checkpoint without the additive head retains its prior fallback.
    legacy = model.clone()
    legacy.candidate_weights.pop(kind)
    assert legacy.make_policy(profile).choose_action(obs)["params"] == {
        "player_id": "rival-first",
    }


def test_training_checkpoint_and_validation_metrics(tmp_path, game_data):
    profiles, traces = _demonstrations(game_data)
    model = LearnedManagerModel.train(traces)
    metrics = imitation_metrics(model, traces)
    assert metrics["examples"] == len(traces)
    assert metrics["legal_rate"] == 1.0
    assert metrics["action_accuracy"] >= 0.5

    path = tmp_path / "manager.json"
    model.save(path, metadata={"train_seeds": [901, 902], "validation_seeds": [999]})
    loaded = LearnedManagerModel.load(path)
    obs = traces[0]["observation"]
    a = model.make_policy(profiles[0]).choose_action(obs)
    b = loaded.make_policy(profiles[0]).choose_action(obs)
    assert a == b
    left = model.make_policy(profiles[0]).action_probabilities(obs)
    right = model.make_policy(profiles[1]).action_probabilities(obs)
    assert left != right
    assert path.read_text().endswith("\n")


def test_learned_policy_runs_legally_and_replays(game_data):
    profile, traces = _demonstrations(game_data)
    model = LearnedManagerModel.train(traces)
    eval_profile = generate_profile(110, "unseen-profile")
    a = run_rollout(
        game_data, seed=999, weeks=1, profile=eval_profile,
        policy=model.make_policy(eval_profile),
    )
    b = run_rollout(
        game_data, seed=999, weeks=1, profile=eval_profile,
        policy=model.make_policy(eval_profile),
    )
    assert a.invalid_actions == 0
    assert a.summary() == b.summary()
    assert a.traces == b.traces
    assert a.action_counts["advance"] == 1
    assert all(t["policy_version"] == "learned-manager-v1" for t in a.traces)
    assert all("policy_diagnostics" in t for t in a.traces)
    assert all(t["policy_diagnostics"]["top_actions"] for t in a.traces)


def test_pre_extension_checkpoint_survives_additive_contract_growth(tmp_path, game_data):
    """The decision contract grows ADDITIVELY (new legal_actions kinds, same
    OBSERVATION_VERSION). A checkpoint saved before an extension must keep
    loading and playing: it carries its own action vocabulary, never emits
    the newer kinds, and save() must not relabel its rows."""
    profile = generate_profile(120, "compat")
    run = run_rollout(game_data, seed=903, weeks=1, profile=profile)
    model = LearnedManagerModel.train(run.traces)
    assert model.action_vocab == ACTION_VOCAB

    # Rebuild the model as if trained before the transfer-market extension.
    newer = {"bid", "buyout", "transfer_offer", "assignment", "igl"}
    old_vocab = tuple(kind for kind in ACTION_VOCAB if kind not in newer)
    keep = [i for i, kind in enumerate(ACTION_VOCAB) if kind not in newer]
    old = LearnedManagerModel(
        action_weights=model.action_weights[keep],
        action_vocab=old_vocab,
        categorical_weights=model.categorical_weights,
        categorical_labels=model.categorical_labels,
        tactic_weights=model.tactic_weights,
        candidate_weights=model.candidate_weights,
    )
    path = tmp_path / "pre_extension.json"
    old.save(path)
    assert json.loads(path.read_text())["action_vocab"] == list(old_vocab)

    loaded = LearnedManagerModel.load(path)
    assert loaded.action_vocab == old_vocab
    obs = run.traces[0]["observation"]
    assert "bid" in obs["legal_actions"]  # the observation IS post-extension
    action = loaded.make_policy(profile).choose_action(obs)
    assert action["kind"] in old_vocab
    assert obs["legal_actions"][action["kind"]]["enabled"]
    metrics = imitation_metrics(loaded, run.traces)
    assert metrics["examples"] > 0 and metrics["legal_rate"] == 1.0

    # A vocabulary the env cannot execute stays rejected.
    bad = LearnedManagerModel(
        action_weights=np.zeros((2, 4)), action_vocab=("advance", "delete_club")
    )
    bad.save(tmp_path / "bad.json")
    try:
        LearnedManagerModel.load(tmp_path / "bad.json")
    except ValueError as exc:
        assert "delete_club" in str(exc)
    else:  # pragma: no cover - the load must refuse
        raise AssertionError("unknown-action checkpoint must not load")


def test_learned_policy_can_autoplay_a_live_campaign_week(game_data):
    profiles, traces = _demonstrations(game_data)
    model = LearnedManagerModel.train(traces)
    profile = generate_profile(111, "autoplay")
    gs = new_campaign(game_data, seed=1000)
    before = (gs.season, gs.week)
    result = play_policy_week(
        gs,
        game_data,
        model.make_policy(profile),
        profile=profile,
    )
    assert result.advanced
    assert (gs.season, gs.week) != before
    assert gs.action_log
    assert all(action.source == "agent" for action in gs.action_log)


def test_assignment_heads_use_demonstrated_legal_parameters(game_data):
    from esports_sim.manager.decision_env import HeadlessManagerEnv

    profile = generate_profile(121, "assignment")
    env = HeadlessManagerEnv(new_campaign(game_data, seed=1001), game_data)
    obs = env.observe()
    legal = obs["legal_actions"]["assignment"]
    pid = legal["player_ids"][0]
    row = next(r for r in obs["roster"] if r["id"] == pid)
    role = next(r for r in legal["roles"] if r != row["role"])
    style = next(s for s in legal["playstyles"] if s != row["playstyle"])
    model = LearnedManagerModel.train([{
        "observation": obs,
        "action": {"kind": "assignment", "params": {
            "player_id": pid, "role": role, "playstyle": style,
        }},
    }])
    assert model.categorical_labels["assignment_role"] == (role,)
    assert model.categorical_labels["assignment_playstyle"] == (style,)
    policy = model.make_policy(profile)
    action = policy._build_action(obs, "assignment", conditioned_features(obs))
    assert action["params"]["role"] == role
    assert action["params"]["playstyle"] == style
    env.step(action)
    selected = env.gs.players[action["params"]["player_id"]]
    assert (str(selected.role), str(selected.playstyle)) == (role, style)


def test_assignment_without_parameter_heads_has_a_legal_change(game_data):
    from esports_sim.manager.decision_env import HeadlessManagerEnv

    obs = HeadlessManagerEnv(new_campaign(game_data, seed=1002), game_data).observe()
    model = LearnedManagerModel(action_weights=np.zeros((len(ACTION_VOCAB), len(conditioned_features(obs)))))
    policy = model.make_policy(generate_profile(122, "old-assignment"))
    action = policy._build_action(obs, "assignment", conditioned_features(obs))
    params = action["params"]
    row = next(r for r in obs["roster"] if r["id"] == params["player_id"])
    assert params["role"] in obs["legal_actions"]["assignment"]["roles"]
    assert params["playstyle"] in obs["legal_actions"]["assignment"]["playstyles"]
    assert (params["role"], params["playstyle"]) != (row["role"], row["playstyle"])


@pytest.mark.parametrize("malformation", [
    "duplicate", "rows", "columns", "rank", "ragged", "nonfinite", "nonstring", "string-vocab",
])
def test_checkpoint_rejects_ambiguous_vocabulary_and_bad_action_shapes(tmp_path, malformation):
    width = len(conditioned_features({"features": {}}))
    path = tmp_path / "malformed.json"
    model = LearnedManagerModel(
        action_weights=np.zeros((2, width)), action_vocab=("set_training", "advance")
    )
    model.save(path)
    payload = json.loads(path.read_text())
    if malformation == "duplicate":
        payload["action_vocab"] = ["advance", "advance"]
    elif malformation == "rows":
        payload["action_weights"].pop()
    elif malformation == "columns":
        payload["action_weights"] = np.zeros((2, width - 1)).tolist()
    elif malformation == "rank":
        payload["action_weights"] = [0.0] * width
    elif malformation == "ragged":
        payload["action_weights"][0].pop()
    elif malformation == "nonfinite":
        payload["action_weights"][0][0] = float("nan")
    elif malformation == "nonstring":
        payload["action_vocab"] = ["advance", {}]
    else:
        payload["action_vocab"] = "advance"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checkpoint action"):
        LearnedManagerModel.load(path)


def test_reordered_legacy_subset_retains_rows_across_load_clone_and_resave(tmp_path, game_data):
    from esports_sim.manager.decision_env import HeadlessManagerEnv

    obs = HeadlessManagerEnv(new_campaign(game_data, seed=1003), game_data).observe()
    width = len(conditioned_features(obs))
    vocab = ("set_training", "advance")
    weights = np.zeros((len(vocab), width))
    weights[0, 0] = 7.0
    model = LearnedManagerModel(action_weights=weights, action_vocab=vocab)
    path = tmp_path / "legacy-subset.json"
    model.save(path)
    loaded = LearnedManagerModel.load(path)
    assert loaded.action_vocab == vocab
    assert np.array_equal(loaded.action_weights, weights)
    policy = loaded.make_policy(generate_profile(123, "subset-order"))
    assert policy.choose_action(obs)["kind"] == "set_training"
    cloned = loaded.clone()
    assert cloned.action_vocab == vocab
    assert np.array_equal(cloned.action_weights, weights)
    # Fine-tuning changes weight rows in place; save must retain their labels.
    cloned.action_weights[1, 0] = 3.0
    cloned.save(path)
    reloaded = LearnedManagerModel.load(path)
    assert reloaded.action_vocab == vocab
    assert np.array_equal(reloaded.action_weights, cloned.action_weights)
    assert json.loads(path.read_text())["action_vocab"] == list(vocab)
