"""Reward fine-tuning, deterministic exploration, and promotion gates."""

from __future__ import annotations

import copy

import numpy as np
import pytest

import esports_sim.manager.online_manager_learning as online_learning
from esports_sim.manager.learned_manager_policy import LearnedManagerModel
from esports_sim.manager.manager_policy import generate_profile
from esports_sim.manager.online_manager_learning import (
    ExploringLearnedManagerPolicy,
    OnlineLearningConfig,
    evaluate_model,
    fine_tune_online,
    promotion_decision,
)
from esports_sim.manager.rollout import run_rollout


@pytest.fixture(scope="module")
def online_setup(game_data):
    profiles = [
        generate_profile(700, "online-a"),
        generate_profile(701, "online-b"),
    ]
    demonstrations = [
        run_rollout(game_data, seed=seed, weeks=1, profile=profile)
        for profile in profiles
        for seed in (1701, 1702)
    ]
    traces = [trace for run in demonstrations for trace in run.traces]
    return profiles, LearnedManagerModel.train(traces)


def test_exploration_is_legal_bounded_and_reproducible(game_data, online_setup):
    profiles, model = online_setup

    def episode():
        policy = ExploringLearnedManagerPolicy(
            model,
            profiles[0],
            exploration_seed=8123,
            temperature=1.2,
            max_actions_per_week=8,
        )
        run = run_rollout(
            game_data,
            seed=1801,
            weeks=1,
            profile=profiles[0],
            policy=policy,
            max_decisions_per_week=8,
        )
        return run, policy

    left, left_policy = episode()
    right, right_policy = episode()
    assert left.invalid_actions == 0
    assert left.traces == right.traces
    assert left.action_counts["advance"] == 1
    assert len(left_policy.samples) == len(right_policy.samples) <= 8
    assert all(trace["policy_diagnostics"]["sampled"] for trace in left.traces)


def test_exploration_recovers_a_roster_block_before_forcing_advance(
    game_data, online_setup
):
    profiles, model = online_setup
    source = run_rollout(game_data, seed=1802, weeks=1, profile=profiles[0])
    blocked = copy.deepcopy(source.traces[0]["observation"])
    blocked["legal_actions"]["advance"] = {"enabled": False, "reason": "roster"}
    blocked["legal_actions"]["sign"] = {
        "enabled": True,
        "player_ids": [blocked["free_agents"][0]["player_id"]],
    }
    policy = ExploringLearnedManagerPolicy(
        model,
        profiles[0],
        exploration_seed=8124,
        max_actions_per_week=2,
    )
    policy._decision_counts[(int(blocked["season"]), int(blocked["week"]))] = 1
    recovery = policy.choose_action(blocked)
    assert recovery["kind"] == "sign"
    assert policy.last_decision["forced_recovery"]

    ready = copy.deepcopy(blocked)
    ready["legal_actions"]["advance"] = {"enabled": True, "reason": ""}
    advance = policy.choose_action(ready)
    assert advance["kind"] == "advance"
    assert policy.last_decision["forced_advance"]


def test_online_update_is_deterministic_and_does_not_mutate_champion(
    game_data, online_setup
):
    profiles, incumbent = online_setup
    original = incumbent.action_weights.copy()
    config = OnlineLearningConfig(
        iterations=1,
        learning_rate=0.02,
        temperature=1.15,
        max_actions_per_week=8,
    )
    left, left_report = fine_tune_online(
        game_data,
        incumbent,
        seeds=[1901],
        profiles=profiles,
        weeks=1,
        config=config,
    )
    right, right_report = fine_tune_online(
        game_data,
        incumbent,
        seeds=[1901],
        profiles=profiles,
        weeks=1,
        config=config,
    )
    assert np.array_equal(incumbent.action_weights, original)
    assert np.array_equal(left.action_weights, right.action_weights)
    assert left_report == right_report
    assert left_report["iterations"][0]["invalid_actions"] == 0
    assert left.metadata["online_learning"] == left_report


def test_held_out_evaluation_and_promotion_gates(game_data, online_setup):
    profiles, incumbent = online_setup
    metrics = evaluate_model(
        game_data,
        incumbent,
        seeds=[2001],
        profiles=profiles,
        weeks=1,
    )
    accepted = promotion_decision(metrics, metrics)
    assert accepted["promoted"]
    assert all(accepted["checks"].values())

    unsafe = copy.deepcopy(metrics)
    unsafe["invalid_actions"] = 1
    unsafe["mean_reward"] = metrics["mean_reward"] - 1.0
    rejected = promotion_decision(metrics, unsafe)
    assert not rejected["promoted"]
    assert "zero_invalid_actions" in rejected["failed_checks"]
    assert "reward_guard" in rejected["failed_checks"]


def test_online_training_records_failed_exploration_without_promoting(
    game_data, online_setup, monkeypatch
):
    profiles, incumbent = online_setup
    original = online_learning.run_rollout
    calls = 0

    def flaky_rollout(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("exploration policy cannot recover a blocked week")
        return original(*args, **kwargs)

    monkeypatch.setattr(online_learning, "run_rollout", flaky_rollout)
    _, training = fine_tune_online(
        game_data,
        incumbent,
        seeds=[2101],
        profiles=profiles,
        weeks=1,
        config=OnlineLearningConfig(iterations=1, max_actions_per_week=8),
    )
    assert len(training["rollout_failures"]) == 1
    assert training["iterations"][0]["rollout_failures"] == 1

    metrics = evaluate_model(
        game_data, incumbent, seeds=[2102], profiles=profiles, weeks=1
    )
    rejected = promotion_decision(metrics, metrics, training_failures=1)
    assert not rejected["promoted"]
    assert "training_rollouts_complete" in rejected["failed_checks"]
