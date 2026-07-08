"""Pairwise relationships: affinity drift, chemistry coupling, ripples."""

from __future__ import annotations

import pytest

from esports_sim.manager import market, relationships
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData
from esports_sim.rng.tree import RngTree


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=123)


def test_clash_pairs_sour_and_kindred_bond(campaign: GameState) -> None:
    gs = campaign
    roster = gs.roster(gs.user_team_id)
    a, b = roster[0], roster[1]
    a.personality_tags = ["hot_head"]
    b.personality_tags = ["perfectionist"]
    c, d = roster[2], roster[3]
    c.personality_tags = ["team_player"]
    d.personality_tags = ["team_player"]
    rng = RngTree(5).derive("rel")
    for _ in range(40):
        relationships.weekly_tick(gs, rng, user_won=False)
    assert relationships.get(gs, a.id, b.id) < 45.0
    assert relationships.get(gs, c.id, d.id) > relationships.get(gs, a.id, b.id)


def test_chemistry_chases_pair_graph(campaign: GameState) -> None:
    gs = campaign
    team = gs.teams[gs.user_team_id]
    roster = sorted(team.player_ids)
    for i, a in enumerate(roster):
        for b in roster[i + 1:]:
            gs.relationships[relationships.key(a, b)] = 90.0
    team.chemistry = 50.0
    rng = RngTree(6).derive("rel")
    for _ in range(10):
        relationships.weekly_tick(gs, rng, user_won=False)
    # Chemistry climbed decisively toward the (decaying) 90-pair graph.
    assert team.chemistry > 65.0


def test_departure_ripple_hits_best_friend(campaign: GameState) -> None:
    gs = campaign
    team = gs.teams[gs.user_team_id]
    a, b = sorted(team.player_ids)[:2]
    gs.relationships[relationships.key(a, b)] = 90.0
    morale_before = gs.players[b].morale
    ok, _ = market.release_player(gs, gs.user_team_id, a)
    assert ok
    assert gs.players[b].morale < morale_before


def test_relationships_tick_in_campaign_and_stay_bounded(
    campaign: GameState, game_data: GameData
) -> None:
    gs = campaign
    for _ in range(4):
        advance_week(gs, game_data)
    assert gs.relationships, "weekly tick should populate the graph"
    # Sparse: bounded well under (42 teams × C(5,2)=10) + history.
    assert len(gs.relationships) <= 800
    # Determinism piggybacks on the campaign test; sanity: values in range.
    assert all(0.0 <= v <= 100.0 for v in gs.relationships.values())
