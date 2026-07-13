"""Decision observations and the framework-agnostic headless manager env."""

from __future__ import annotations

import json

import numpy as np
import pytest

from esports_sim.manager import career, sponsors
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import (
    HeadlessManagerEnv,
    InvalidManagerAction,
    manager_observation,
)


def test_observation_is_json_safe_visible_and_restores_acting_team(game_data):
    gs = new_campaign(game_data, seed=701)
    tid = gs.user_team_id
    gs.set_acting(tid)
    obs = manager_observation(gs, game_data, tid, manager_profile={"risk": 0.25})

    json.dumps(obs, sort_keys=True)
    assert gs.acting_team_id == tid
    assert obs["observation_version"] == 4
    assert obs["manager_profile"] == {"risk": 0.25}
    assert len(obs["roster"]) == 5
    assert "attributes" in obs["roster"][0]
    # Rival/market players expose scouting bands, never their hidden raw book.
    assert obs["free_agents"]
    assert "ca_stars" in obs["free_agents"][0]
    assert "attributes" not in obs["free_agents"][0]
    assert "potential" not in obs["free_agents"][0]


def test_legal_masks_match_domain_rules(game_data):
    gs = new_campaign(game_data, seed=702)
    env = HeadlessManagerEnv(gs, game_data)
    legal = env.observe()["legal_actions"]

    assert legal["advance"]["enabled"]
    assert legal["set_training"]["options"] == [
        "mechanical", "tactical", "mental", "team", "rest"
    ]
    assert "rest" in legal["set_dev_plan"]["focus_options"]
    assert legal["set_lineup"]["player_ids"] == sorted(gs.teams[gs.user_team_id].player_ids)
    assert set(legal["sign"]["player_ids"]).issubset(gs.free_agent_ids)
    for pair in legal["swap"]["pairs"]:
        assert pair["sign_id"] in gs.free_agent_ids
        assert pair["drop_id"] in gs.teams[gs.user_team_id].player_ids
    for kind in (
        "set_dev_plan", "mentor", "hire_staff", "release_staff",
        "facility_upgrade", "sponsor_respond", "set_game_plan", "talk",
        "negotiate_open", "accept_job",
    ):
        assert kind in legal


def test_extended_manager_actions_use_shared_domain_rules(game_data):
    gs = new_campaign(game_data, seed=706)
    tid = gs.user_team_id
    gs.teams[tid].balance = 2_000_000
    env = HeadlessManagerEnv(gs, game_data)
    pid = sorted(gs.teams[tid].player_ids)[0]

    env.step({
        "kind": "set_dev_plan",
        "params": {
            "player_id": pid,
            "dev_focus": "mechanical",
            "training_intensity": "light",
        },
    })
    assert gs.players[pid].dev_focus == "mechanical"
    assert gs.players[pid].training_intensity == "light"

    env.step({
        "kind": "set_dev_plan",
        "params": {"player_id": pid, "dev_focus": "rest"},
    })
    assert gs.players[pid].dev_focus == "rest"

    candidate = env.observe()["legal_actions"]["hire_staff"]["candidate_ids"][0]
    role = next(m.role for m in gs.staff_pool if m.id == candidate)
    env.step({"kind": "hire_staff", "params": {"candidate_id": candidate}})
    assert gs.staff_by[tid][role].id == candidate

    before = gs.teams[tid].balance
    env.step({"kind": "facility_upgrade", "params": {"facility": "analytics_suite"}})
    assert gs.facilities_by[tid]["analytics_suite"] == 1
    assert gs.teams[tid].balance < before

    target = env.observe()["legal_actions"]["negotiate_open"]["player_ids"][0]
    env.step({"kind": "negotiate_open", "params": {"player_id": target}})
    neg = gs.negotiations_by[tid][target]
    env.step({
        "kind": "negotiate_offer",
        "params": {
            "player_id": target,
            "salary": neg.demand_salary,
            "weeks": neg.demand_weeks,
        },
    })
    assert target not in gs.negotiations_by[tid]


def test_game_plan_talk_and_trace_capture(game_data):
    gs = new_campaign(game_data, seed=707)
    traces = []
    env = HeadlessManagerEnv(
        gs, game_data, trace_sink=traces.append, policy_version="test-policy-v1"
    )
    obs = env.observe()
    target = obs["legal_actions"]["set_game_plan"]["focus_target_ids"][0]
    env.step({
        "kind": "set_game_plan",
        "params": {"pace": 63.0, "focus_target": target, "team_talk": "focus"},
    })
    assert gs.game_plans_by[gs.user_team_id].pace == 63.0

    option = env.observe()["legal_actions"]["talk"]["options"][0]
    env.step({"kind": "talk", "params": option})
    assert len(traces) == 2
    assert traces[0]["policy_version"] == "test-policy-v1"
    assert traces[0]["observation"]["observation_version"] == 4
    assert traces[0]["action"]["kind"] == "set_game_plan"


def test_sponsor_and_career_offer_adapters(game_data):
    gs = new_campaign(game_data, seed=708, mode="legacy", manager_name="Agent")
    tid = gs.user_team_id
    gs.set_acting(tid)
    for seed in range(30):
        sponsors.maybe_offer(gs, np.random.default_rng(seed))
        if any(gs.sponsor_market_by[tid].values()):
            break
    env = HeadlessManagerEnv(gs, game_data)
    option = next(
        o for o in env.observe()["legal_actions"]["sponsor_respond"]["options"]
        if o["accept"]
    )
    env.step({"kind": "sponsor_respond", "params": option})
    assert option["slot"] in gs.sponsor_slots_by[tid]

    seat = gs.manager_for(tid)
    assert seat is not None
    career.apply_dismissals(gs, [seat.id])
    offers = env.observe()["legal_actions"]["accept_job"]["team_ids"]
    assert offers
    env.step({"kind": "accept_job", "params": {"team_id": offers[0]}})
    assert env.team_id == offers[0]
    assert gs.managers[seat.id].team_id == offers[0]


def test_headless_actions_and_week_reward(game_data):
    gs = new_campaign(game_data, seed=703)
    env = HeadlessManagerEnv(gs, game_data, manager_profile={"youth": 0.8})

    result = env.step({"kind": "set_training", "params": {"focus": "mental"}})
    assert not result.advanced and result.reward == 0.0
    assert result.observation["training_focus"] == "mental"
    assert gs.action_log[-1].source == "agent"

    result = env.step({"kind": "set_tactics", "params": {"pace": 67.0}})
    assert result.observation["tactics"]["pace"] == 67.0

    week = gs.week
    result = env.step({"kind": "advance", "params": {}})
    assert result.advanced
    assert gs.week != week or gs.phase != "regular"
    assert isinstance(result.reward, float)
    assert "wins_delta" in result.reward_components


def test_headless_env_rejects_invalid_actions(game_data):
    gs = new_campaign(game_data, seed=704)
    env = HeadlessManagerEnv(gs, game_data)
    with pytest.raises(InvalidManagerAction):
        env.step({"kind": "set_training", "params": {"focus": "vibes"}})
    with pytest.raises(InvalidManagerAction):
        env.step({"kind": "set_tactics", "params": {"pace": 101}})
    with pytest.raises(InvalidManagerAction):
        env.step({"kind": "delete_club", "params": {}})


def test_headless_rollout_is_deterministic(game_data):
    a = HeadlessManagerEnv(new_campaign(game_data, seed=705), game_data)
    b = HeadlessManagerEnv(new_campaign(game_data, seed=705), game_data)
    actions = [
        {"kind": "set_training", "params": {"focus": "team"}},
        {"kind": "set_tactics", "params": {"map_control": 62.0}},
        {"kind": "advance", "params": {}},
    ]
    for action in actions:
        ra = a.step(action)
        rb = b.step(action)
        assert ra.observation == rb.observation
        assert ra.reward == rb.reward
    assert a.gs.model_dump() == b.gs.model_dump()
