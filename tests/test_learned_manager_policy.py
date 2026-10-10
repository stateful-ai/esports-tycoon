"""Learned manager encoder, imitation heads, checkpoints, and live rollouts."""

from __future__ import annotations

import json

import numpy as np

from esports_sim.manager.learned_manager_policy import (
    ACTION_VOCAB,
    LearnedManagerModel,
    encode_observation,
    imitation_metrics,
)
from esports_sim.manager.manager_policy import generate_profile
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.rollout import play_policy_week, run_rollout


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
