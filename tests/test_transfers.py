"""Transfer market: values, executed moves, AI window, user offers."""

from __future__ import annotations

import pytest

from esports_sim.manager import market
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState, TransferOffer
from esports_sim.registry import GameData


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=123)


def test_transfer_value_prices_youth_and_expiry(campaign) -> None:
    gs = campaign
    # A young high-PA tier-2 player must cost more than an old journeyman
    # of equal CA; expiring contracts discount.
    young = next(
        gs.players[pid]
        for t in gs.teams.values()
        if t.tier == 2
        for pid in t.player_ids
        if gs.players[pid].age <= 19
    )
    v_now = market.transfer_value(young)
    long_deal = young.contract_weeks_left
    young.contract_weeks_left = 2
    v_expiring = market.transfer_value(young)
    young.contract_weeks_left = long_deal
    assert v_expiring < v_now

    old = young.model_copy(deep=True)
    old.age = 29
    assert market.transfer_value(old) < v_now


def test_execute_transfer_moves_player_and_money(campaign) -> None:
    gs = campaign
    seller = next(
        t for t in gs.teams.values()
        if t.tier == 2 and t.id != gs.user_team_id and t.player_ids
    )
    buyer = next(
        t for t in gs.teams.values()
        if t.tier == 1 and t.id != gs.user_team_id
    )
    pid = seller.player_ids[0]
    buyer.balance = 5_000_000
    fee = market.transfer_ask(gs, pid)
    s_before, b_before = seller.balance, buyer.balance
    n_before = len(buyer.player_ids)
    ok, _ = market.execute_transfer(gs, pid, buyer.id, fee)
    assert ok
    assert pid in buyer.player_ids and pid not in seller.player_ids
    assert seller.balance == s_before + fee
    assert buyer.balance == b_before - fee
    # Full buyer auto-released someone: roster size unchanged.
    assert len(buyer.player_ids) == n_before
    assert gs.players[pid].contract_weeks_left >= market.MIN_CONTRACT_WEEKS


def test_ai_transfers_happen_over_a_season(campaign, game_data: GameData) -> None:
    gs = campaign
    for _ in range(14):
        advance_week(gs, game_data)
    assert any("TRANSFER:" in n for n in gs.news), (
        "a full regular season should see at least one AI-to-AI move"
    )


def test_user_offer_accept_and_decline(campaign) -> None:
    gs = campaign
    pid = gs.teams[gs.user_team_id].player_ids[0]
    buyer = next(
        t for t in gs.teams.values()
        if t.id != gs.user_team_id and t.tier == 1
    )
    buyer.balance = 5_000_000
    gs.transfer_offers.append(
        TransferOffer(
            player_id=pid, from_team=gs.user_team_id,
            to_team=buyer.id, fee=200_000, expires_week=gs.week + 2,
        )
    )
    ok, msg = market.respond_offer(gs, pid, accept=False)
    assert ok and "declined" in msg
    assert not gs.transfer_offers

    gs.transfer_offers.append(
        TransferOffer(
            player_id=pid, from_team=gs.user_team_id,
            to_team=buyer.id, fee=200_000, expires_week=gs.week + 2,
        )
    )
    bal_before = gs.teams[gs.user_team_id].balance
    ok, _ = market.respond_offer(gs, pid, accept=True)
    assert ok
    assert pid in buyer.player_ids
    assert gs.teams[gs.user_team_id].balance == bal_before + 200_000


def test_lifecycle_retirements_and_rookies(campaign, game_data: GameData) -> None:
    """Across multiple seasons the population turns over but stays
    bounded: careers end, rookie classes arrive, rosters stay legal."""
    gs = campaign
    # Age the world so retirements are guaranteed to fire.
    for p in gs.players.values():
        if p.age >= 26:
            p.age = 33
    # Play through to the offseason and roll it.
    guard = 0
    while gs.phase != "offseason" and guard < 40:
        advance_week(gs, game_data)
        guard += 1
    assert gs.phase == "offseason"
    n_before = len(gs.players)
    advance_week(gs, game_data)  # offseason tick → new season
    assert gs.retired, "aged world produced no retirements"
    assert any("rookie class" in n for n in gs.news)
    # Rookies actually landed in free agency with the rookie tag.
    assert any(
        "rookie" in gs.players[pid].personality_tags
        for pid in gs.free_agent_ids
    )
    # Population bounded (turnover, not growth).
    assert len(gs.players) < n_before + 40
    # Retired players are fully unreferenced.
    handles = {r.handle for r in gs.retired}
    for t in gs.teams.values():
        for pid in t.player_ids:
            assert pid in gs.players
    for pid in gs.free_agent_ids:
        assert pid in gs.players
    assert handles  # records kept
