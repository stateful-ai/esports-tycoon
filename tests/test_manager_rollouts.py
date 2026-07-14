"""Profile generation, baseline manager policies, rollout traces, and export."""

from __future__ import annotations

import json

from esports_sim.manager import delegation, series_management
from esports_sim.manager.decision_env import HeadlessManagerEnv
from esports_sim.manager.manager_policy import (
    HeuristicManagerPolicy,
    ManagerProfile,
    generate_profile,
)
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
    assert all(t["policy_version"] == "heuristic-manager-v3" for t in a.traces)


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
    assert runs[0]["policy_version"] == "heuristic-manager-v3"
    assert evaluation["runs"] == 1


def test_analytical_baseline_books_visible_preparation(game_data):
    """A configured manager turns public fixture information into a legal plan."""
    from esports_sim.manager.campaign import new_campaign

    gs = new_campaign(game_data, seed=811)
    tid = gs.user_team_id
    delegation.configure(gs, tid, {
        "auto_renew_core": True,
        "renewal_salary_min": 800,
        "renewal_salary_max": 8_000,
        "renewal_trigger_weeks": 8,
        "auto_scout": True,
        "scout_region": "pacific",
        "scout_roles": ["initiator"],
        "scout_max_age": 21,
        "alert_level": "tier1_ready",
    })
    series_management.register_roster(gs, tid, list(gs.teams[tid].player_ids))
    # Isolate the fixture-planning decision from optional transfer-market work.
    gs.free_agent_ids = []
    profile = ManagerProfile(
        id="analytical-prep", risk=0.4, youth=0.2, loyalty=0.4,
        analytics=0.95, investment=0.4, experimentation=0.3,
    )
    env = HeadlessManagerEnv(gs, game_data)
    action = HeuristicManagerPolicy(profile).choose_action(env.observe())

    assert action["kind"] == "set_preparation"
    assert action["params"]["objective"] == "anti_exec"
    env.step(action)
    assert gs.preparation_plans_by[tid].objective == "anti_exec"


def test_baseline_prioritizes_recovery_facility_for_a_tired_roster(game_data):
    from esports_sim.manager.campaign import new_campaign

    gs = new_campaign(game_data, seed=813)
    for player in gs.roster(gs.user_team_id):
        player.stamina = 45.0
    obs = HeadlessManagerEnv(gs, game_data).observe()
    for kind, contract in obs["legal_actions"].items():
        if kind != "facility_upgrade" and "enabled" in contract:
            contract["enabled"] = False
    profile = ManagerProfile(
        id="recovery-investor",
        risk=0.4,
        youth=0.4,
        loyalty=0.4,
        analytics=0.4,
        investment=0.95,
        experimentation=0.4,
    )

    action = HeuristicManagerPolicy(profile)._initiative(obs)

    assert action == {
        "kind": "facility_upgrade",
        "params": {"facility": "recovery_suite"},
    }


def test_stale_learned_checkpoint_falls_back_to_the_default_manager(
    tmp_path, game_data, monkeypatch,
):
    """Autoplay remains usable while an older learned checkpoint is retrained."""
    from esports_sim.app import cli

    stale = tmp_path / "stale-manager.json"
    stale.write_text('{"policy_version": "learned-manager-v0"}', encoding="utf-8")
    monkeypatch.setattr(cli, "save", lambda _gs: None)

    gs = cli.auto_play(
        game_data,
        weeks=1,
        seed=812,
        team="team_nexus",
        manager_model=stale,
    )
    assert gs.week != 1 or gs.phase != "regular"
