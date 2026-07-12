"""Profile generation, baseline manager policies, rollout traces, and export."""

from __future__ import annotations

import json

from esports_sim.manager.manager_policy import ManagerProfile, generate_profile
from esports_sim.manager.rollout import evaluate_rollouts, export_rollouts, run_rollout


def test_generated_profiles_are_stable_and_bounded():
    a = generate_profile(10, "manager-a")
    b = generate_profile(10, "manager-a")
    c = generate_profile(10, "manager-b")
    assert a == b and a != c
    assert all(0.0 <= value <= 1.0 for value in a.to_dict().values())


def test_rollout_and_traces_are_deterministic(game_data):
    profile = generate_profile(20, "deterministic")
    a = run_rollout(game_data, seed=808, weeks=1, profile=profile)
    b = run_rollout(game_data, seed=808, weeks=1, profile=profile)
    assert a.summary() == b.summary()
    assert a.traces == b.traces
    assert a.invalid_actions == 0
    assert a.action_counts["advance"] == 1
    assert all(t["policy_version"] == "heuristic-manager-v1" for t in a.traces)


def test_profiles_produce_distinct_management_styles(game_data):
    developer = ManagerProfile(
        id="developer", risk=0.2, youth=0.95, loyalty=0.8,
        analytics=0.2, investment=0.2, experimentation=0.1,
    )
    analyst = ManagerProfile(
        id="analyst", risk=0.7, youth=0.1, loyalty=0.2,
        analytics=0.95, investment=0.2, experimentation=0.9,
    )
    a = run_rollout(game_data, seed=809, weeks=1, profile=developer)
    b = run_rollout(game_data, seed=809, weeks=1, profile=analyst)
    focuses = {
        r.profile_id: next(
            t["action"]["params"]["focus"]
            for t in r.traces if t["action"]["kind"] == "set_training"
        )
        for r in (a, b)
    }
    assert focuses == {"developer": "mechanical", "analyst": "tactical"}
    report = evaluate_rollouts([a, b])
    assert report["mean_profile_action_tv"] > 0
    assert all(p["invalid_actions"] == 0 for p in report["profiles"].values())


def test_rollout_export_contract(tmp_path, game_data):
    result = run_rollout(game_data, seed=810, weeks=1)
    paths = export_rollouts([result], tmp_path / "manager")
    traces = [json.loads(line) for line in paths["traces"].read_text().splitlines()]
    runs = [json.loads(line) for line in paths["runs"].read_text().splitlines()]
    evaluation = json.loads(paths["evaluation"].read_text())
    assert traces and traces[-1]["advanced"]
    assert traces[0]["run_id"] == result.run_id
    assert runs[0]["policy_version"] == "heuristic-manager-v1"
    assert evaluation["runs"] == 1
