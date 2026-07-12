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


def test_existing_rosters_open_with_realistic_contract_terms(campaign) -> None:
    contracted = [p for tid in sorted(campaign.teams) for p in campaign.roster(tid)]
    assert contracted
    assert all(0.65 <= p.stream_revenue_share <= 0.90 for p in contracted)
    assert all(p.release_fee > 0 for p in contracted)
    assert all(p.buyout_clause >= 15_000 for p in contracted)
    assert all(p.roster_role in ("starter", "bench", "academy") for p in contracted)
    assert not any(p.no_transfer_clause for p in contracted)
    # The defaults are not one cloned template: squad status changes both
    # release protection and the buyout multiple.
    assert len({p.release_fee for p in contracted}) > 1
    assert len({p.buyout_clause for p in contracted}) > 1


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


def test_ai_transfer_window_executes_a_clear_upgrade(
    campaign, game_data: GameData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Market coverage must not depend on one exact sequence of match scores.

    The ability engine legitimately changes season results, so an integration
    assertion that happens to find an AI transfer after 14 weeks is brittle.
    This supplies the transfer window with a rich buyer and an obvious tier-2
    upgrade, then asserts the actual market behavior deterministically.
    """
    gs = campaign
    gs.week = market.TRANSFER_QUIET_WEEKS + 1
    buyer = next(
        t for t in gs.teams.values()
        if t.tier == 1 and not gs.is_human(t.id)
    )
    seller = next(
        t for t in gs.teams.values()
        if t.tier == 2 and not gs.is_human(t.id)
    )
    buyer.balance = 20_000_000
    for team in gs.teams.values():
        if team.tier == 1 and not gs.is_human(team.id) and team.id != buyer.id:
            team.balance = 0
    for pid in buyer.player_ids:
        gs.players[pid].attributes = {
            key: 30.0 for key in gs.players[pid].attributes
        }
    target = seller.player_ids[0]
    gs.players[target].attributes = {
        key: 95.0 for key in gs.players[target].attributes
    }
    # The buying org must be able to justify the tier-2 buyout under its own
    # valuation, not merely afford it.
    gs.players[target].personality_tags = ["star_player", "fan_favorite"]
    gs.players[target].followers = 10_000_000
    gs.players[target].stream_load = 1.0
    # Quote mechanics have their own coverage. Fix the clause here so this
    # test observes the AI selecting and executing the prepared upgrade.
    monkeypatch.setattr(market, "buyout_fee", lambda _gs, _pid: 10_000)

    class EagerBuyer:
        @staticmethod
        def random() -> float:
            return 0.0

    market.ai_transfer_window(gs, game_data, EagerBuyer())

    assert target in buyer.player_ids and target not in seller.player_ids
    assert any("TRANSFER:" in news for news in gs.news)


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


def test_respond_offer_requires_seller_ownership(campaign) -> None:
    """Shared world: only the SELLER (offer.from_team == acting manager) can
    resolve a bid for their player. A rival manager POSTing the same player id
    must be rejected — they cannot accept a bid on someone else's roster."""
    gs = campaign
    seller = gs.user_team_id
    buyer = next(t.id for t in gs.teams.values() if t.id != seller and t.tier == 1)
    gs.human_team_ids = [seller, buyer]  # two live managers
    gs.teams[buyer].balance = 5_000_000
    gs.teams[buyer].player_ids.pop()  # a human buyer needs a free roster slot
    pid = gs.teams[seller].player_ids[0]
    gs.transfer_offers = [
        TransferOffer(player_id=pid, from_team=seller, to_team=buyer,
                      fee=200_000, expires_week=gs.week + 2)
    ]

    # The buyer (not the seller) tries to accept their own incoming bid -> no.
    gs.set_acting(buyer)
    ok, _ = market.respond_offer(gs, pid, accept=True)
    assert not ok
    assert gs.transfer_offers and pid not in gs.teams[buyer].player_ids

    # The seller can.
    gs.set_acting(seller)
    ok, _ = market.respond_offer(gs, pid, accept=True)
    assert ok and pid in gs.teams[buyer].player_ids
    gs.set_acting(None)


def test_respond_offer_disambiguates_between_buyers(campaign) -> None:
    """Two buyers bidding for the same player resolve to the buyer named in the
    payload, not whichever offer happens to sort first."""
    gs = campaign
    seller = gs.user_team_id
    b1, b2 = [t.id for t in gs.teams.values() if t.id != seller and t.tier == 1][:2]
    pid = gs.teams[seller].player_ids[0]
    for b in (b1, b2):
        gs.teams[b].balance = 5_000_000
    gs.transfer_offers = [
        TransferOffer(player_id=pid, from_team=seller, to_team=b1,
                      fee=100_000, expires_week=gs.week + 2),
        TransferOffer(player_id=pid, from_team=seller, to_team=b2,
                      fee=300_000, expires_week=gs.week + 2),
    ]
    bal_before = gs.teams[seller].balance
    gs.set_acting(seller)
    ok, _ = market.respond_offer(gs, pid, accept=True, to_team=b2)
    assert ok
    assert pid in gs.teams[b2].player_ids and pid not in gs.teams[b1].player_ids
    assert gs.teams[seller].balance == bal_before + 300_000  # b2's fee, not b1's
    gs.set_acting(None)


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


def test_swap_signs_and_drops(campaign) -> None:
    gs = campaign
    tid = gs.user_team_id
    gs.set_acting(tid)
    gs.teams[tid].balance = 5_000_000
    drop = gs.teams[tid].player_ids[0]
    fa = gs.free_agent_ids[0]
    ok, _ = market.swap_player(gs, tid, fa, drop)
    gs.set_acting(None)
    assert ok
    assert fa in gs.teams[tid].player_ids
    assert drop not in gs.teams[tid].player_ids and drop in gs.free_agent_ids
    assert len(gs.teams[tid].player_ids) == market.ROSTER_SIZE


def test_roster_ready_gate(campaign) -> None:
    gs = campaign
    tid = gs.user_team_id
    assert market.roster_ready(gs, tid)[0]
    while len(gs.teams[tid].player_ids) > market.ROSTER_MIN - 1:
        market.release_player(gs, tid, gs.teams[tid].player_ids[-1])
    ok, why = market.roster_ready(gs, tid)
    assert not ok and f"{market.ROSTER_MIN} players" in why


def test_package_deal_moves_players_and_cash(campaign) -> None:
    gs = campaign
    buyer = gs.user_team_id
    gs.set_acting(buyer)
    gs.teams[buyer].balance = 10_000_000
    seller = next(
        t for t in gs.teams.values()
        if t.id != buyer and not gs.is_human(t.id) and t.tier == 1
    )
    target = seller.player_ids[0]
    mine = max(
        gs.teams[buyer].player_ids,
        key=lambda pid: market.transfer_value(gs.players[pid]),
    )
    ask = market.transfer_ask(gs, target)
    mine_val = market.transfer_value(gs.players[mine])
    # Sweeten with enough cash that the package clears the asking value.
    cash = max(0, ask - mine_val) + 50_000
    ok, msg = market.propose_package(gs, target, [mine], cash_out=cash, cash_in=0)
    gs.set_acting(None)
    assert ok, msg
    # Target came in, the offered player went out.
    assert target in gs.teams[buyer].player_ids
    assert mine in seller.player_ids
    assert len(gs.teams[buyer].player_ids) == market.ROSTER_SIZE
    assert len(seller.player_ids) == market.ROSTER_SIZE


def test_two_for_one_package_to_ai_seller(campaign) -> None:
    """A 2-for-1 (two of mine for one of theirs) must not bounce off the AI
    seller's roster cap: everyone may carry a bench up to ROSTER_MAX, so the
    AI ending at six players is legal. The buyer needs 7+ players to stay at
    ROSTER_MIN after sending two away."""
    gs = campaign
    buyer = gs.user_team_id
    gs.set_acting(buyer)
    gs.teams[buyer].balance = 20_000_000
    # Deepen the buyer's bench so shipping two out keeps them at five+.
    for fa in list(gs.free_agent_ids[:2]):
        ok, msg = market.sign_player(gs, buyer, fa)
        assert ok, msg
    seller = next(
        t for t in gs.teams.values()
        if t.id != buyer and not gs.is_human(t.id) and t.tier == 1
    )
    target = seller.player_ids[0]
    start = len(seller.player_ids)
    # Offer my two cheapest players + enough cash to clear the ask.
    mine = sorted(
        gs.teams[buyer].player_ids,
        key=lambda pid: market.transfer_value(gs.players[pid]),
    )[:2]
    ask = market.transfer_ask(gs, target)
    got = sum(market.transfer_value(gs.players[p]) for p in mine)
    cash = max(0, ask - got) + 50_000
    ok, msg = market.propose_package(gs, target, mine, cash_out=cash, cash_in=0)
    gs.set_acting(None)
    assert ok, msg
    assert target in gs.teams[buyer].player_ids
    assert all(p in seller.player_ids for p in mine)
    # The AI seller legally carries one more than it started with.
    assert len(seller.player_ids) == start + 1
    assert len(seller.player_ids) <= market.ROSTER_MAX


def test_tier2_buyout_clause(campaign) -> None:
    """A tier-1 org triggers a tier-2 player's buyout clause: the fee is a
    stable per-player multiple of value and the player moves instantly."""
    gs = campaign
    buyer = gs.user_team_id
    gs.set_acting(buyer)
    gs.teams[buyer].balance = 20_000_000
    t2 = next(t for t in gs.teams.values() if t.tier == 2 and t.player_ids)
    pid = t2.player_ids[0]
    fee = market.buyout_fee(gs, pid)
    assert fee is not None and fee > 0
    assert fee == market.buyout_fee(gs, pid)  # stable, "negotiated at signing"
    # Clause sits above plain market value (the tier-2 org's protection).
    assert fee >= market.transfer_value(gs.players[pid])
    ok, msg = market.buy_out_player(gs, buyer, pid)
    assert ok, msg
    assert pid in gs.teams[buyer].player_ids
    assert pid not in t2.player_ids
    # Opening tier-1 contracts now carry negotiated clauses too.
    t1 = next(
        t for t in gs.teams.values()
        if t.tier == 1 and t.id != buyer and t.player_ids
    )
    assert market.buyout_fee(gs, t1.player_ids[0]) is not None


def test_transfer_ask_breakdown_reconciles(campaign) -> None:
    gs = campaign
    seller = next(t for t in gs.teams.values() if t.id != gs.user_team_id)
    pid = seller.player_ids[0]
    parts = market.transfer_ask_breakdown(gs, pid)
    assert sum(part["delta"] for part in parts) == market.transfer_ask(gs, pid)
    assert parts[0]["label"] == "base value"
    gs.set_acting(None)


def test_subjective_valuation_differs_by_viewer(campaign) -> None:
    """Two orgs read the same rival player differently (stable per-viewer
    bias); a club always knows its OWN player exactly."""
    gs = campaign
    seller = next(
        t for t in gs.teams.values()
        if t.id != gs.user_team_id and t.tier == 1 and not gs.is_human(t.id)
    )
    pid = seller.player_ids[0]
    p = gs.players[pid]
    truth = market.player_quality(p)
    # The owner's read is exact.
    assert market.perceived_quality(gs, seller.id, p) == truth
    # Other orgs' reads are stable and (across the league) not all identical.
    viewers = [t.id for t in gs.teams.values() if t.id != seller.id][:8]
    reads = [market.perceived_quality(gs, v, p) for v in viewers]
    assert reads == [market.perceived_quality(gs, v, p) for v in viewers]
    assert len({round(r, 3) for r in reads}) > 1
    # And every read stays within the documented blur.
    assert all(abs(r - truth) <= market.VALUATION_BLUR for r in reads)


def test_staff_valuation_opinions_reconcile_to_package_value(campaign) -> None:
    """The trade-room disagreement is texture around the exact valuation the
    org (and AI package evaluator) actually uses."""
    gs = campaign
    viewer = gs.user_team_id
    rival = next(t for t in gs.teams.values() if t.id != viewer and t.player_ids)
    p = gs.players[rival.player_ids[0]]
    views = market.valuation_opinions(gs, viewer, p)
    assert set(views) == {"coach", "analyst", "consensus"}
    assert views["consensus"] == market.perceived_value(gs, viewer, p)
    assert views["coach"] + views["analyst"] == 2 * views["consensus"]
    assert market.package_value(gs, [p.id], 0, viewer_id=viewer) == views["consensus"]


def test_ai_buyer_protects_new_signings(campaign) -> None:
    """execute_transfer's AI auto-release never flips a fresh arrival: the
    weakest SETTLED player goes instead."""
    gs = campaign
    buyer = next(
        t for t in gs.teams.values()
        if not gs.is_human(t.id) and t.tier == 1 and len(t.player_ids) >= 5
    )
    # Make the roster's weakest player brand-new; everyone else settled.
    ps = [gs.players[q] for q in buyer.player_ids]
    for p in ps:
        p.tenure_weeks = 52
    weakest = min(ps, key=market.player_quality)
    weakest.tenure_weeks = 0  # just arrived
    settled_weakest = min(
        (p for p in ps if p.id != weakest.id), key=market.player_quality
    )
    seller = next(
        t for t in gs.teams.values()
        if t.id != buyer.id and t.tier == 1 and t.player_ids
    )
    target = seller.player_ids[0]
    buyer.balance = 20_000_000
    ok, msg = market.execute_transfer(gs, target, buyer.id, 50_000)
    assert ok, msg
    assert weakest.id in buyer.player_ids  # the new arrival was protected
    assert settled_weakest.id not in buyer.player_ids  # the settled one went


def test_negotiation_haggle_counter_accept(campaign) -> None:
    """The table works: demands open above the current deal, a decent
    offer draws a CONCEDING counter, and meeting the counter signs at the
    NEGOTIATED number (cheaper than the opening ask)."""
    gs = campaign
    tid = gs.user_team_id
    gs.set_acting(tid)
    pid = gs.teams[tid].player_ids[0]
    p = gs.players[pid]
    ok, why, neg = market.open_negotiation(gs, pid)
    assert ok, why
    assert neg.kind == "renew"
    assert neg.demand_salary >= p.salary  # nobody re-signs for less unprompted
    ask0 = neg.demand_salary
    status, msg, neg = market.negotiate_offer(
        gs, pid, int(ask0 * 0.88), neg.demand_weeks
    )
    assert status == "countered"
    assert neg.demand_salary < ask0  # they conceded
    counter = neg.demand_salary
    status, msg, _ = market.negotiate_offer(gs, pid, counter, neg.demand_weeks)
    assert status == "accepted", msg
    assert p.salary == counter < ask0  # the haggle saved real money
    assert pid not in gs.negotiations
    gs.set_acting(None)


def test_negotiation_insult_collapses_with_cooldown(campaign) -> None:
    gs = campaign
    tid = gs.user_team_id
    gs.set_acting(tid)
    pid = gs.teams[tid].player_ids[1]
    p = gs.players[pid]
    morale0 = p.morale
    ok, why, neg = market.open_negotiation(gs, pid)
    assert ok, why
    status, msg, _ = market.negotiate_offer(
        gs, pid, int(neg.demand_salary * 0.5), neg.demand_weeks
    )
    assert status == "collapsed"
    assert p.morale < morale0  # they know you tried to lowball them
    assert gs.talks_cooldown[pid] > gs.week
    ok, why, _ = market.open_negotiation(gs, pid)
    assert not ok and "collapsed" in why  # not taking your calls
    gs.set_acting(None)


def test_negotiation_patience_runs_out(campaign) -> None:
    gs = campaign
    tid = gs.user_team_id
    gs.set_acting(tid)
    pid = gs.teams[tid].player_ids[2]
    ok, why, neg = market.open_negotiation(gs, pid)
    assert ok, why
    lowish = int(neg.demand_salary * 0.78)
    statuses = []
    for _ in range(market.NEGOTIATION_MAX_ROUNDS):
        status, _msg, neg = market.negotiate_offer(gs, pid, lowish, 30)
        statuses.append(status)
    assert statuses[-1] == "collapsed"
    assert all(s == "countered" for s in statuses[:-1])
    gs.set_acting(None)


def test_negotiation_fa_signing_uses_negotiated_terms(campaign) -> None:
    gs = campaign
    tid = gs.user_team_id
    gs.set_acting(tid)
    gs.teams[tid].balance = 10_000_000
    fa = gs.free_agent_ids[0]
    ok, why, neg = market.open_negotiation(gs, fa)
    assert ok, why
    assert neg.kind == "sign"
    status, msg, _ = market.negotiate_offer(
        gs, fa, neg.demand_salary, neg.demand_weeks
    )
    assert status == "accepted", msg
    assert fa in gs.teams[tid].player_ids
    p = gs.players[fa]
    assert p.salary == neg.demand_salary
    assert p.contract_weeks_left == neg.demand_weeks
    assert round(p.stream_revenue_share * 100) == neg.demand_stream_share
    assert p.release_fee == neg.demand_release_fee
    assert p.buyout_clause == neg.demand_buyout
    assert p.no_transfer_clause == neg.demand_no_transfer
    assert p.roster_role == neg.demand_role
    gs.set_acting(None)


def test_role_promise_changes_required_salary(campaign) -> None:
    """A player asking to start rejects starter money paired with a bench
    promise, but a meaningful wage premium can compensate for that downgrade."""
    gs = campaign
    tid = gs.user_team_id
    gs.set_acting(tid)
    pid = gs.teams[tid].player_ids[0]
    ok, why, neg = market.open_negotiation(gs, pid)
    assert ok, why
    neg.demand_role = "starter"
    status, _msg, neg = market.negotiate_offer(
        gs, pid, neg.demand_salary, neg.demand_weeks, role="bench"
    )
    assert status == "countered"
    status, msg, _ = market.negotiate_offer(
        gs, pid, int(neg.demand_salary * 1.15), neg.demand_weeks, role="bench"
    )
    assert status == "accepted", msg
    assert gs.players[pid].roster_role == "bench"
    gs.set_acting(None)


def test_contract_protections_control_release_and_transfer(campaign) -> None:
    gs = campaign
    seller = gs.user_team_id
    pid = gs.teams[seller].player_ids[0]
    p = gs.players[pid]
    p.release_fee = 123_000
    before = gs.teams[seller].balance
    ok, msg = market.release_player(gs, seller, pid)
    assert ok, msg
    assert gs.teams[seller].balance == before - 123_000

    protected = gs.teams[seller].player_ids[0]
    gs.players[protected].no_transfer_clause = True
    buyer = next(t.id for t in gs.teams.values() if t.id != seller)
    ok, msg = market.execute_transfer(gs, protected, buyer, 0)
    assert not ok and "no-transfer" in msg


def test_offer_accept_blocked_in_playoffs(campaign) -> None:
    """Rosters lock in the playoffs: a pre-existing offer can't be ACCEPTED by a
    human seller (it stays live), though declining is still allowed."""
    gs = campaign
    seller = gs.user_team_id
    buyer = next(t.id for t in gs.teams.values() if t.id != seller and t.tier == 1)
    gs.teams[buyer].balance = 5_000_000
    pid = gs.teams[seller].player_ids[0]
    gs.transfer_offers = [
        TransferOffer(
            player_id=pid, from_team=seller, to_team=buyer,
            fee=200_000, expires_week=gs.week + 2,
        )
    ]
    gs.phase = "playoffs"
    gs.set_acting(seller)
    ok, msg = market.respond_offer(gs, pid, accept=True)
    assert not ok and "playoff" in msg.lower()
    # The offer survives and no player moved.
    assert gs.transfer_offers and pid in gs.teams[seller].player_ids
    # Declining is still allowed during the lock.
    ok, _ = market.respond_offer(gs, pid, accept=False)
    gs.set_acting(None)
    assert ok and not gs.transfer_offers


def test_package_offer_revalidates_stale_roster(campaign) -> None:
    """A package offer that was legal when made can go stale on a human's desk.
    execute_package must recheck roster sizes and refuse an illegal settlement
    rather than stranding a roster below the minimum."""
    gs = campaign
    seller = gs.user_team_id
    buyer = next(t.id for t in gs.teams.values() if t.id != seller and t.tier == 1)
    gs.teams[buyer].balance = 5_000_000
    target = gs.teams[seller].player_ids[0]
    # The buyer offers TWO of their players, but their roster is only five — so
    # settling would drop them to four, below ROSTER_MIN. (Represents an offer
    # that was legal when the buyer had six, then released one.)
    out = list(gs.teams[buyer].player_ids[:2])
    gs.transfer_offers = [
        TransferOffer(
            player_id=target, from_team=seller, to_team=buyer,
            fee=0, expires_week=gs.week + 2,
            offer_player_ids=out, cash_to_seller=0, cash_to_buyer=0,
        )
    ]
    gs.set_acting(seller)
    ok, _ = market.respond_offer(gs, target, accept=True)
    gs.set_acting(None)
    assert not ok
    # Nothing moved: the deal was rejected, not half-applied.
    assert target in gs.teams[seller].player_ids
    assert all(p in gs.teams[buyer].player_ids for p in out)
