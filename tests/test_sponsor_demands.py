"""Complex sponsor demands: generation, choices, exact outcomes, and AI parity."""

from __future__ import annotations

import json

import numpy as np
import pytest
from pydantic import ValidationError

from esports_sim.manager import inbox, rivalries, sponsors
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import HeadlessManagerEnv, manager_observation
from esports_sim.manager.manager_policy import HeuristicManagerPolicy, generate_profile
from esports_sim.manager.state import GameState, SCHEMA_VERSION, SponsorDeal, SponsorDemand


def _future_fixture(gs):
    return next(
        fixture for fixture in sorted(gs.fixtures, key=lambda f: (f.week, f.id))
        if not fixture.played
        and fixture.week > gs.week
        and gs.user_team_id in (fixture.team_a, fixture.team_b)
    )


def _opponent(gs, fixture):
    return fixture.team_b if fixture.team_a == gs.user_team_id else fixture.team_a


def _demand(gs, *, kind="field_rookie", player_id=""):
    fixture = _future_fixture(gs)
    return SponsorDemand(
        id=f"test-{kind}",
        brand="Testworks",
        slot="jersey",
        kind=kind,
        fixture_id=fixture.id,
        opponent_id=_opponent(gs, fixture),
        player_id=player_id,
        issued_season=gs.season,
        issued_week=gs.week,
        deadline_week=fixture.week,
        reward=40_000,
        penalty=20_000,
    )


def test_generation_is_deterministic_and_names_exact_rookie(game_data):
    a = new_campaign(game_data, seed=4301)
    b = new_campaign(game_data, seed=4301)
    for gs in (a, b):
        tid = gs.user_team_id
        players = gs.roster(tid)
        for player in players:
            player.age = 25
        players[0].age = 19
        gs.sponsor_slots["jersey"] = SponsorDeal(
            name="Testworks", kind="steady", weekly=12_000, weeks_left=20,
        )
    da = sponsors.maybe_demand(a, np.random.default_rng(3))
    db = sponsors.maybe_demand(b, np.random.default_rng(3))
    assert da is not None and db is not None
    assert da == db
    assert da.kind == "field_rookie"
    assert da.player_id == a.roster(a.user_team_id)[0].id
    assert da.fixture_id == _future_fixture(a).id
    assert a.model_dump_json() == b.model_dump_json()


def test_rivalry_demand_requires_named_rivalry(game_data):
    gs = new_campaign(game_data, seed=4302)
    for player in gs.roster(gs.user_team_id):
        player.age = 25
    fixture = _future_fixture(gs)
    opponent = _opponent(gs, fixture)
    gs.sponsor_slots["jersey"] = SponsorDeal(
        name="Testworks", kind="performance", weekly=10_000,
        per_win=5_000, weeks_left=20,
    )
    assert sponsors.maybe_demand(gs, np.random.default_rng(3)) is None
    gs.rivalries[rivalries.key(gs.user_team_id, opponent)] = rivalries.RIVALRY_BAR
    demand = sponsors.maybe_demand(gs, np.random.default_rng(3))
    assert demand is not None
    assert demand.kind == "win_rivalry"
    assert demand.opponent_id == opponent


def test_accepted_rookie_demand_uses_actual_dressed_lineup(game_data):
    gs = new_campaign(game_data, seed=4303)
    tid = gs.user_team_id
    target = gs.teams[tid].player_ids[0]
    gs.players[target].age = 19
    demand = _demand(gs, player_id=target)
    gs.sponsor_demands.append(demand)
    before = gs.teams[tid].balance
    assert sponsors.respond_demand(gs, demand.id, True)[0]
    fixture = _future_fixture(gs)
    fixture.played = True
    fixture.winner_id = fixture.team_b
    gs.week = fixture.week
    delta = sponsors.settle_demands(gs, {tid: {target}})
    assert delta == demand.reward
    assert demand.status == "met"
    assert gs.teams[tid].balance == before + demand.reward
    assert sponsors.relation(gs, demand.brand) == 55.0


def test_accepted_demand_failure_costs_cash_and_relations(game_data):
    gs = new_campaign(game_data, seed=4304)
    tid = gs.user_team_id
    target = gs.teams[tid].player_ids[0]
    demand = _demand(gs, player_id=target)
    gs.sponsor_demands.append(demand)
    before = gs.teams[tid].balance
    assert sponsors.respond_demand(gs, demand.id, True)[0]
    fixture = _future_fixture(gs)
    fixture.played = True
    fixture.winner_id = fixture.team_a
    gs.week = fixture.week
    delta = sponsors.settle_demands(gs, {tid: set()})
    assert delta == -demand.penalty
    assert demand.status == "missed"
    assert gs.teams[tid].balance == before - demand.penalty
    assert sponsors.relation(gs, demand.brand) == 42.0


def test_unanswered_expires_and_decline_has_smaller_relation_cost(game_data):
    declined = new_campaign(game_data, seed=4305)
    demand = _demand(declined, player_id=declined.teams[declined.user_team_id].player_ids[0])
    declined.sponsor_demands.append(demand)
    assert sponsors.respond_demand(declined, demand.id, False)[0]
    assert demand.status == "declined"
    assert sponsors.relation(declined, demand.brand) == 47.0

    expired = new_campaign(game_data, seed=4305)
    demand = _demand(expired, player_id=expired.teams[expired.user_team_id].player_ids[0])
    expired.sponsor_demands.append(demand)
    fixture = _future_fixture(expired)
    fixture.played = True
    expired.week = fixture.week
    assert sponsors.settle_demands(expired, {}) == 0
    assert demand.status == "expired"
    assert sponsors.relation(expired, demand.brand) == 48.0


def test_demand_view_and_inbox_actions_share_one_contract(game_data):
    gs = new_campaign(game_data, seed=4306)
    target = gs.teams[gs.user_team_id].player_ids[0]
    demand = _demand(gs, player_id=target)
    gs.sponsor_demands.append(demand)
    view = sponsors.demand_views(gs)[0]
    assert set(view) == {
        "id", "brand", "slot", "kind", "fixture_id", "opponent_id",
        "player_id", "issued_season", "issued_week", "deadline_week",
        "reward", "penalty", "status", "resolved_season", "resolved_week",
        "label", "requirement", "detail", "opponent_name", "player_name",
        "relation", "can_respond",
    }
    item = next(
        item for _priority, item in inbox._sponsor_items(gs, gs.season, gs.week)
        if "match demand" in item.title
    )
    actions = inbox.actions_for(gs, item)
    assert [action["id"] for action in actions] == ["accept", "decline"]
    assert all(action["endpoint"] == "/api/actions/sponsor_demand" for action in actions)
    assert sponsors.respond_demand(gs, demand.id, True)[0]
    assert inbox.actions_for(gs, item) == []


def test_headless_and_heuristic_manager_accept_and_field_rookie(game_data):
    gs = new_campaign(game_data, seed=4307)
    tid = gs.user_team_id
    bench = gs.free_agent_ids.pop(0)
    gs.teams[tid].player_ids.append(bench)
    gs.players[bench].age = 19
    demand = _demand(gs, player_id=bench)
    gs.sponsor_demands.append(demand)
    profile = generate_profile(gs.seed, "sponsor-demand-test")
    policy = HeuristicManagerPolicy(profile)
    env = HeadlessManagerEnv(gs, game_data, manager_profile=profile.to_dict())

    obs = env.observe()
    assert obs["observation_version"] == 8
    assert obs["legal_actions"]["sponsor_demand_respond"]["enabled"]
    action = policy.choose_action(obs)
    assert action["kind"] == "sponsor_demand_respond"
    assert action["params"]["accept"] is True
    env.step(action)
    lineup_action = policy.choose_action(env.observe())
    assert lineup_action["kind"] == "set_lineup"
    assert bench in lineup_action["params"]["player_ids"]


def test_v29_migration_and_round_trip(game_data, tmp_path):
    gs = new_campaign(game_data, seed=4308)
    demand = _demand(gs, player_id=gs.teams[gs.user_team_id].player_ids[0])
    gs.sponsor_demands.append(demand)
    path = tmp_path / "current.json"
    gs.save(path)
    assert GameState.load(path).sponsor_demands == [demand]

    old = json.loads(gs.model_dump_json())
    old["schema_version"] = 29
    old.pop("sponsor_demands_by")
    old_path = tmp_path / "v29.json"
    old_path.write_text(json.dumps(old), encoding="utf-8")
    migrated = GameState.load(old_path)
    assert migrated.schema_version == SCHEMA_VERSION == 31
    assert migrated.sponsor_demands == []


def test_demand_schema_rejects_unknown_fields(game_data):
    gs = new_campaign(game_data, seed=4309)
    payload = _demand(
        gs, player_id=gs.teams[gs.user_team_id].player_ids[0]
    ).model_dump()
    payload["untracked_promise"] = True
    with pytest.raises(ValidationError):
        SponsorDemand.model_validate(payload)
