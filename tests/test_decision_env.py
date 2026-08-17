"""Decision observations and the framework-agnostic headless manager env."""

from __future__ import annotations

import json

import numpy as np
import pytest

from esports_sim.manager import career, market, role_fit, sponsors
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import (
    HeadlessManagerEnv,
    InvalidManagerAction,
    manager_observation,
)
from esports_sim.manager.state import TransferOffer


def test_observation_is_json_safe_visible_and_restores_acting_team(game_data):
    gs = new_campaign(game_data, seed=701)
    tid = gs.user_team_id
    gs.set_acting(tid)
    obs = manager_observation(gs, game_data, tid, manager_profile={"risk": 0.25})

    json.dumps(obs, sort_keys=True)
    assert gs.acting_team_id == tid
    # The transfer-market/role kinds arrived ADDITIVELY: new legal_actions
    # keys must not bump the observation version (consumers read known keys
    # only; learned checkpoints carry their own action vocabulary).
    assert obs["observation_version"] == 8
    for kind in ("bid", "buyout", "transfer_offer", "assignment", "igl"):
        assert kind in obs["legal_actions"]
    assert obs["manager_profile"] == {"risk": 0.25}
    assert len(obs["roster"]) == 5
    assert "attributes" in obs["roster"][0]
    assert "assignment_comfort" in obs["roster"][0]
    # Rival/market players expose scouting bands, never their hidden raw book.
    assert obs["free_agents"]
    assert "ca_stars" in obs["free_agents"][0]
    assert "attributes" not in obs["free_agents"][0]
    assert "potential" not in obs["free_agents"][0]


def test_no_change_actions_say_so_instead_of_succeeding_silently(game_data):
    """LLM-playtest finding: a model repeated set_training 14x and
    negotiate_open 7x because identical no-op actions returned success with
    no feedback. The env must name the no-op and, for a live negotiation,
    point at the next step in the chain."""
    gs = new_campaign(game_data, seed=703)
    env = HeadlessManagerEnv(gs, game_data)

    current = gs.training_focus.get(gs.user_team_id)
    focus = "mental" if current != "mental" else "mechanical"
    first = env.step({"kind": "set_training", "params": {"focus": focus}})
    again = env.step({"kind": "set_training", "params": {"focus": focus}})
    assert first.message == f"training focus set to {focus}"
    assert "no change" in again.message

    tac = env.step({"kind": "set_tactics", "params": {"pace": 60.0}})
    tac_again = env.step({"kind": "set_tactics", "params": {"pace": 60.0}})
    assert tac.message == "tactics updated"
    assert "unchanged" in tac_again.message

    negotiable = env.observe()["legal_actions"]["negotiate_open"]["player_ids"]
    if negotiable:
        pid = negotiable[0]
        env.step({"kind": "negotiate_open", "params": {"player_id": pid}})
        reopen = env.step({"kind": "negotiate_open", "params": {"player_id": pid}})
        assert "already open" in reopen.message
        assert "negotiate_offer" in reopen.message

    prep = env.observe()["legal_actions"]["set_preparation"]
    if prep["enabled"]:
        params = {
            "fixture_id": prep["fixture_id"], "partner_id": prep["partner_ids"][0],
            "map_id": prep["map_ids"][0], "objective": prep["objectives"][0],
            "intensity": prep["intensities"][0],
        }
        booked = env.step({"kind": "set_preparation", "params": params})
        rebooked = env.step({"kind": "set_preparation", "params": params})
        # The booking message names what was bought and when it pays off.
        assert booked.message.startswith("preparation booked:")
        assert "when the week advances" in booked.message
        assert "already booked" in rebooked.message


def test_short_roster_advance_reason_names_the_sign_action(game_data):
    gs = new_campaign(game_data, seed=704)
    tid = gs.user_team_id
    team = gs.teams[tid]
    dropped = sorted(team.player_ids)[0]
    team.player_ids.remove(dropped)

    reason = HeadlessManagerEnv(gs, game_data).observe()["legal_actions"]["advance"]["reason"]
    assert "sign 1 more" in reason and "sign action" in reason


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
        "facility_upgrade", "sponsor_respond", "sponsor_demand_respond",
        "set_game_plan", "talk",
        "negotiate_open", "accept_job",
        "bid", "buyout", "transfer_offer", "assignment", "igl",
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


def test_bid_and_buyout_use_shared_market_rules(game_data):
    gs = new_campaign(game_data, seed=709)
    tid = gs.user_team_id
    gs.teams[tid].balance = 5_000_000
    env = HeadlessManagerEnv(gs, game_data)
    legal = env.observe()["legal_actions"]

    assert legal["bid"]["enabled"]
    roster = set(gs.teams[tid].player_ids)
    for option in legal["bid"]["options"]:
        assert option["player_id"] not in roster
        assert option["player_id"] in gs.teams[option["team_id"]].player_ids
        wages = market.asking_salary(gs.players[option["player_id"]]) * 8
        assert gs.teams[tid].balance >= option["ask"] + wages

    option = legal["bid"]["options"][0]
    before = gs.teams[tid].balance
    result = env.step({"kind": "bid", "params": {"player_id": option["player_id"]}})
    assert "joins" in result.message
    assert option["player_id"] in gs.teams[tid].player_ids
    assert gs.teams[tid].balance == before - option["ask"]

    legal = env.observe()["legal_actions"]
    assert legal["buyout"]["enabled"]
    clause = legal["buyout"]["options"][0]
    assert market.buyout_fee(gs, clause["player_id"]) == clause["fee"]
    before = gs.teams[tid].balance
    env.step({"kind": "buyout", "params": {"player_id": clause["player_id"]}})
    assert clause["player_id"] in gs.teams[tid].player_ids
    assert gs.teams[tid].balance == before - clause["fee"]

    with pytest.raises(InvalidManagerAction):  # your own player is not biddable
        env.step({"kind": "bid", "params": {"player_id": sorted(roster)[0]}})
    with pytest.raises(InvalidManagerAction):
        env.step({"kind": "buyout", "params": {"player_id": "nobody"}})
    kinds = [a.kind for a in gs.action_log]
    assert kinds.count("bid") == 1 and kinds.count("buyout") == 1


def test_bid_on_human_seller_parks_on_their_desk(game_data):
    """Agent-to-agent transfers: a bid on another SEAT's player becomes an
    incoming transfer_offer only that seat can answer."""
    gs = new_campaign(game_data, seed=712)
    tid = gs.user_team_id
    rival = next(t for t in sorted(gs.teams) if t != tid and gs.teams[t].tier == 1)
    gs.human_team_ids.append(rival)
    gs.teams[tid].balance = 5_000_000
    env = HeadlessManagerEnv(gs, game_data, tid)

    options = [
        o for o in env.observe()["legal_actions"]["bid"]["options"]
        if o["team_id"] == rival
    ]
    assert options and all(o["seller_human"] for o in options)
    target = options[0]
    result = env.step({"kind": "bid", "params": {"player_id": target["player_id"]}})
    assert "bid sent" in result.message
    assert target["player_id"] not in gs.teams[tid].player_ids

    # The seller seat sees the live offer; the buyer's mask drops the
    # player so the same bid cannot be double-placed.
    seller_env = HeadlessManagerEnv(gs, game_data, rival)
    offers = seller_env.observe()["legal_actions"]["transfer_offer"]["offers"]
    assert [o["player_id"] for o in offers] == [target["player_id"]]
    assert offers[0]["to_team"] == tid
    assert target["player_id"] not in [
        o["player_id"] for o in env.observe()["legal_actions"]["bid"]["options"]
    ]

    seller_before = gs.teams[rival].balance
    seller_env.step({
        "kind": "transfer_offer",
        "params": {"player_id": target["player_id"], "accept": True},
    })
    assert target["player_id"] in gs.teams[tid].player_ids
    assert gs.teams[rival].balance == seller_before + target["ask"]


def test_transfer_offer_answers_are_seller_scoped(game_data):
    gs = new_campaign(game_data, seed=710)
    tid = gs.user_team_id
    rival = next(t for t in sorted(gs.teams) if t != tid and gs.teams[t].tier == 1)
    gs.human_team_ids.append(rival)
    buyer = next(
        t for t in sorted(gs.teams)
        if t not in (tid, rival) and gs.teams[t].tier == 1
    )
    gs.teams[buyer].balance = 5_000_000
    mine = sorted(gs.teams[tid].player_ids)[0]
    gs.transfer_offers.append(TransferOffer(
        player_id=mine, from_team=tid, to_team=buyer,
        fee=150_000, expires_week=gs.week + 2,
    ))

    env = HeadlessManagerEnv(gs, game_data, tid)
    offers = env.observe()["legal_actions"]["transfer_offer"]
    assert offers["enabled"]
    assert offers["offers"][0]["player_id"] == mine
    assert offers["offers"][0]["to_team"] == buyer
    assert offers["offers"][0]["can_accept"]

    # In a shared world a rival seat can never answer a bid on MY desk.
    rival_env = HeadlessManagerEnv(gs, game_data, rival)
    assert not rival_env.observe()["legal_actions"]["transfer_offer"]["enabled"]
    with pytest.raises(InvalidManagerAction):
        rival_env.step({
            "kind": "transfer_offer", "params": {"player_id": mine, "accept": True},
        })
    assert len(gs.transfer_offers) == 1

    before = gs.teams[tid].balance
    env.step({
        "kind": "transfer_offer",
        "params": {"player_id": mine, "accept": True, "to_team": buyer},
    })
    assert mine in gs.teams[buyer].player_ids
    assert mine not in gs.teams[tid].player_ids
    assert gs.teams[tid].balance == before + 150_000
    assert not gs.transfer_offers

    other = sorted(gs.teams[tid].player_ids)[0]
    gs.transfer_offers.append(TransferOffer(
        player_id=other, from_team=tid, to_team=buyer,
        fee=90_000, expires_week=gs.week + 2,
    ))
    declined = env.step({
        "kind": "transfer_offer", "params": {"player_id": other, "accept": False},
    })
    assert "declined" in declined.message
    assert not gs.transfer_offers
    assert other in gs.teams[tid].player_ids


def test_assignment_and_igl_manage_role_fit(game_data):
    gs = new_campaign(game_data, seed=711)
    tid = gs.user_team_id
    env = HeadlessManagerEnv(gs, game_data)
    legal = env.observe()["legal_actions"]

    assert legal["assignment"]["enabled"] and legal["igl"]["enabled"]
    assert set(legal["assignment"]["roles"]) == set(role_fit.ROLE_WEIGHTS)
    assert set(legal["assignment"]["playstyles"]) == set(role_fit.STYLE_WEIGHTS)
    assert legal["igl"]["current_igl"] == gs.teams[tid].captain_id
    assert set(legal["igl"]["experience"]) == set(legal["igl"]["player_ids"])

    pid = legal["assignment"]["player_ids"][0]
    p = gs.players[pid]
    role = "sentinel" if str(p.role) != "sentinel" else "duelist"
    style = "anchor" if str(p.playstyle) != "anchor" else "entry"
    moved = env.step({
        "kind": "assignment",
        "params": {"player_id": pid, "role": role, "playstyle": style},
    })
    assert (str(p.role), str(p.playstyle)) == (role, style)
    assert role_fit.assignment_comfort(p) == role_fit.NEW_ASSIGNMENT_COMFORT
    assert "comfort" in moved.message
    again = env.step({
        "kind": "assignment",
        "params": {"player_id": pid, "role": role, "playstyle": style},
    })
    assert "no change" in again.message
    with pytest.raises(InvalidManagerAction):
        env.step({
            "kind": "assignment",
            "params": {"player_id": pid, "role": "coach", "playstyle": style},
        })

    caller = next(
        c for c in legal["igl"]["player_ids"] if c != legal["igl"]["current_igl"]
    )
    named = env.step({"kind": "igl", "params": {"player_id": caller}})
    assert gs.teams[tid].captain_id == caller
    assert role_fit.igl_experience(gs.teams[tid], caller) == role_fit.NEW_IGL_EXPERIENCE
    assert "calling experience" in named.message
    assert env.observe()["legal_actions"]["igl"]["current_igl"] == caller
    renamed = env.step({"kind": "igl", "params": {"player_id": caller}})
    assert "no change" in renamed.message
    with pytest.raises(InvalidManagerAction):
        env.step({"kind": "igl", "params": {"player_id": "nobody"}})
    kinds = [a.kind for a in gs.action_log]
    assert "set_assignment" in kinds and "set_igl" in kinds


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
    assert traces[0]["observation"]["observation_version"] == 8
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
