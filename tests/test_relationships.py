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


def test_language_overlap_shapes_affinity(campaign: GameState) -> None:
    """Pairs sharing a fluent tongue settle warmer than pairs with no
    common language; players without language data read neutral."""
    from esports_sim.schemas import LanguageSkill

    gs = campaign
    roster = gs.roster(gs.user_team_id)
    a, b, c = roster[0], roster[1], roster[2]
    # Same personality slate so ONLY languages differ.
    for p in (a, b, c):
        p.personality_tags = []
    a.languages = [LanguageSkill(lang="ko", level=95.0)]
    b.languages = [LanguageSkill(lang="ko", level=92.0)]
    c.languages = [LanguageSkill(lang="fr", level=95.0)]
    shared = relationships.affinity_target(a, b)
    none = relationships.affinity_target(a, c)
    assert shared > none, "a shared fluent tongue must settle warmer"
    assert relationships.language_overlap(a, b) > 0.9
    assert relationships.language_overlap(a, c) == 0.0
    # No language data (pre-heal save) reads neutral, not hostile.
    c.languages = []
    assert relationships.language_overlap(a, c) == 0.6


def test_team_comms_cohesion_reads_roster(campaign: GameState) -> None:
    from esports_sim.schemas import LanguageSkill

    gs = campaign
    tid = gs.user_team_id
    for p in gs.roster(tid):
        p.languages = [LanguageSkill(lang="en", level=90.0)]
    assert relationships.team_comms_cohesion(gs, tid) >= 80.0
    # One player with no shared tongue drags the roster read down.
    gs.roster(tid)[0].languages = [LanguageSkill(lang="zh", level=95.0)]
    assert relationships.team_comms_cohesion(gs, tid) < 70.0


def test_departure_ripple_hits_best_friend(campaign: GameState) -> None:
    gs = campaign
    team = gs.teams[gs.user_team_id]
    a, b = sorted(team.player_ids)[:2]
    gs.relationships[relationships.key(a, b)] = 90.0
    morale_before = gs.players[b].morale
    ok, _ = market.release_player(gs, gs.user_team_id, a)
    assert ok
    assert gs.players[b].morale < morale_before


def test_feuds_block_voluntary_signings_and_renewals(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    teammate = gs.teams[tid].player_ids[0]
    free_agent = gs.free_agent_ids[0]
    gs.relationships[relationships.key(teammate, free_agent)] = 20.0

    ok, why = market.can_sign(gs, tid, free_agent)
    assert not ok
    assert "refuses to share" in why

    incumbent = gs.teams[tid].player_ids[1]
    gs.relationships[relationships.key(teammate, incumbent)] = 20.0
    gs.players[incumbent].morale = 35.0
    ok, why = market.renew_contract(gs, tid, incumbent)
    assert not ok
    assert "will not renew" in why


def test_transfer_into_feud_has_a_morale_cost(campaign: GameState) -> None:
    gs = campaign
    seller_id = next(tid for tid in gs.teams if tid != gs.user_team_id)
    pid = gs.teams[seller_id].player_ids[0]
    teammate = gs.teams[gs.user_team_id].player_ids[0]
    gs.relationships[relationships.key(pid, teammate)] = 20.0
    gs.teams[gs.user_team_id].balance = 10_000_000
    before = gs.players[pid].morale

    ok, _ = market.execute_transfer(gs, pid, gs.user_team_id, fee=10_000)
    assert ok
    assert gs.players[pid].morale < before


def test_transfer_between_rival_clubs_has_a_morale_cost(campaign: GameState) -> None:
    from esports_sim.manager import rivalries

    gs = campaign
    buyer_id = gs.user_team_id
    seller_id = next(tid for tid in gs.teams if tid != buyer_id)
    pid = gs.teams[seller_id].player_ids[0]
    gs.rivalries[rivalries.key(seller_id, buyer_id)] = 100.0
    gs.teams[buyer_id].balance = 10_000_000
    before = gs.players[pid].morale

    ok, _ = market.execute_transfer(gs, pid, buyer_id, fee=10_000)
    assert ok
    assert gs.players[pid].morale < before


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
