"""Decision observations and the framework-agnostic headless manager env."""

from __future__ import annotations

import json

import pytest

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
    assert obs["observation_version"] == 1
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
    assert legal["set_lineup"]["player_ids"] == sorted(gs.teams[gs.user_team_id].player_ids)
    assert set(legal["sign"]["player_ids"]).issubset(gs.free_agent_ids)
    for pair in legal["swap"]["pairs"]:
        assert pair["sign_id"] in gs.free_agent_ids
        assert pair["drop_id"] in gs.teams[gs.user_team_id].player_ids


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
