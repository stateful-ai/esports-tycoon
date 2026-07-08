"""Finance depth (M4): sponsor slots, facilities, revenue depth."""

from __future__ import annotations

import pytest

from esports_sim.manager import economy, sponsors
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState, SponsorDeal, TeamRecord
from esports_sim.registry import GameData
from esports_sim.rng.tree import RngTree


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=321)


# ---------------------------------------------------------------------------
# Slot exclusivity


def test_slot_signable_gates_on_active_deal(campaign: GameState) -> None:
    assert sponsors._slot_signable(campaign, "jersey")

    campaign.sponsor_slots["jersey"] = SponsorDeal(
        name="Testcorp", kind="steady", weekly=5_000, weeks_left=10,
    )
    assert not sponsors._slot_signable(campaign, "jersey")  # fresh deal

    campaign.sponsor_slots["jersey"].weeks_left = 3
    assert sponsors._slot_signable(campaign, "jersey")  # renewal window


def test_market_respects_per_slot_cap(campaign: GameState) -> None:
    campaign.teams[campaign.user_team_id].reputation = 90.0
    rng = RngTree(1).derive("force-a-roll")
    for _ in range(80):  # hammer the roll so a cap bug shows up quickly
        sponsors.maybe_offer(campaign, rng)
    for slot in sponsors.SLOT_ORDER:
        assert len(campaign.sponsor_market.get(slot, [])) <= sponsors.MARKET_CAP_PER_SLOT


def test_slots_are_independent_and_can_all_be_filled_at_once(campaign: GameState) -> None:
    for slot in sponsors.SLOT_ORDER:
        campaign.sponsor_slot_offers[slot] = SponsorDeal(
            name=f"{slot}-brand", kind="steady", weekly=1_000, weeks_left=20,
        )
    for slot in sponsors.SLOT_ORDER:
        ok, msg = sponsors.accept_slot_offer(campaign, slot)
        assert ok, msg

    assert set(campaign.sponsor_slots) == set(sponsors.SLOT_ORDER)
    for slot in sponsors.SLOT_ORDER:
        assert campaign.sponsor_slots[slot].name == f"{slot}-brand"
    assert campaign.sponsor_slot_offers == {}

    # Declining/accepting one slot must not touch the others.
    campaign.sponsor_slot_offers["jersey"] = SponsorDeal(
        name="Renewal", kind="steady", weekly=2_000, weeks_left=15,
    )
    ok, _ = sponsors.accept_slot_offer(campaign, "jersey")
    assert ok
    assert campaign.sponsor_slots["title"].name == "title-brand"
    assert campaign.sponsor_slots["peripheral"].name == "peripheral-brand"
    assert campaign.sponsor_slots["jersey"].name == "Renewal"


def test_legacy_and_slot_fields_stay_independent(campaign: GameState) -> None:
    """Old-save (pre-M4) single-deal fields and the new slot dicts don't
    clobber each other."""
    team = campaign.teams[campaign.user_team_id]
    campaign.sponsor = SponsorDeal(name="Legacy", kind="steady", weekly=5_000, weeks_left=2)
    campaign.sponsor_slots["jersey"] = SponsorDeal(
        name="Modern", kind="steady", weekly=3_000, weeks_left=10,
    )
    before = team.balance
    got = sponsors.weekly_tick(campaign, user_won_this_week=False)
    assert got == 8_000  # 5000 legacy + 3000 slot
    assert team.balance == before + 8_000
    assert campaign.sponsor is not None  # 1 week left, still active
    assert campaign.sponsor_slots["jersey"].weeks_left == 9


# ---------------------------------------------------------------------------
# Offer generation determinism


def test_generate_offer_is_deterministic(campaign: GameState) -> None:
    rng_a = RngTree(4242).derive("season", 1, "week", 3, "weekly")
    rng_b = RngTree(4242).derive("season", 1, "week", 3, "weekly")
    offer_a = sponsors._generate_offer(rng_a, campaign, "title")
    offer_b = sponsors._generate_offer(rng_b, campaign, "title")
    assert offer_a == offer_b
    # Every offer carries all three structures and at least one objective.
    assert offer_a.upfront.signing_bonus > 0
    assert offer_a.steady.weekly > 0
    assert offer_a.performance.per_win > 0
    assert offer_a.objectives


def test_maybe_offer_end_to_end_is_deterministic(game_data: GameData) -> None:
    a = new_campaign(game_data, seed=777)
    b = new_campaign(game_data, seed=777)
    assert a.model_dump_json() == b.model_dump_json()

    touched = False
    for week in range(1, 16):
        rng_a = RngTree(a.seed).derive("season", a.season, "week", week, "weekly")
        rng_b = RngTree(b.seed).derive("season", b.season, "week", week, "weekly")
        sponsors.maybe_offer(a, rng_a)
        sponsors.maybe_offer(b, rng_b)
        if any(a.sponsor_market.values()):
            touched = True

    assert touched, "no slot rolled an offer in 15 weeks — test seed needs adjusting"
    assert a.sponsor_market == b.sponsor_market


def test_marketability_grows_with_reputation_and_fans(campaign: GameState) -> None:
    team = campaign.teams[campaign.user_team_id]

    team.reputation, team.fan_count = 30.0, 10_000
    low = sponsors.marketability(campaign)
    team.reputation, team.fan_count = 90.0, 2_000_000
    high = sponsors.marketability(campaign)
    assert high > low


def test_title_slot_is_bigger_money_than_peripheral(campaign: GameState) -> None:
    team = campaign.teams[campaign.user_team_id]
    team.reputation, team.fan_count = 70.0, 500_000
    title = sponsors._offer_scale(campaign, "title", "Testbrand")
    jersey = sponsors._offer_scale(campaign, "jersey", "Testbrand")
    peripheral = sponsors._offer_scale(campaign, "peripheral", "Testbrand")
    assert title > jersey > peripheral


def test_relations_scale_offer_money(campaign: GameState) -> None:
    cold = sponsors._offer_scale(campaign, "jersey", "GrudgeCorp")
    campaign.sponsor_relations["GrudgeCorp"] = 95.0
    warm = sponsors._offer_scale(campaign, "jersey", "GrudgeCorp")
    assert warm > cold


def test_objective_payout_and_relation_swing(campaign: GameState) -> None:
    from esports_sim.manager.state import SponsorObjective

    gs = campaign
    team = gs.teams[gs.user_team_id]
    gs.sponsor_slots["jersey"] = SponsorDeal(
        name="Testcorp", kind="performance", weekly=1_000, weeks_left=20,
        objectives=[SponsorObjective(kind="make_masters", bonus=50_000)],
    )
    # Masters drawn WITH the user: objective met, bonus paid, brand warms.
    gs.masters_seeds = [gs.user_team_id]
    before = team.balance
    rel_before = sponsors.relation(gs, "Testcorp")
    total = sponsors.weekly_tick(gs, user_won_this_week=False)
    assert total == 1_000 + 50_000
    assert team.balance == before + 51_000
    assert gs.sponsor_slots["jersey"].objectives[0].met is True
    assert sponsors.relation(gs, "Testcorp") > rel_before
    # Second week: objective doesn't pay twice.
    assert sponsors.weekly_tick(gs, user_won_this_week=False) == 1_000


def test_missed_objective_cools_relations(campaign: GameState) -> None:
    from esports_sim.manager.state import SponsorObjective

    gs = campaign
    gs.sponsor_slots["jersey"] = SponsorDeal(
        name="Sadcorp", kind="steady", weekly=1_000, weeks_left=20,
        objectives=[SponsorObjective(kind="make_masters", bonus=50_000)],
    )
    gs.masters_seeds = ["someone_else"]
    rel_before = sponsors.relation(gs, "Sadcorp")
    total = sponsors.weekly_tick(gs, user_won_this_week=False)
    assert total == 1_000
    assert gs.sponsor_slots["jersey"].objectives[0].met is False
    assert sponsors.relation(gs, "Sadcorp") < rel_before


def test_stream_and_apparel_slots_gated_by_marketing_office(campaign: GameState) -> None:
    gs = campaign
    assert not sponsors._slot_unlocked(gs, "stream")
    assert not sponsors._slot_unlocked(gs, "apparel")
    gs.facilities["marketing_office"] = 1
    assert sponsors._slot_unlocked(gs, "stream")
    assert not sponsors._slot_unlocked(gs, "apparel")
    gs.facilities["marketing_office"] = 2
    assert sponsors._slot_unlocked(gs, "apparel")


def test_sign_market_offer_structure_choice(campaign: GameState) -> None:
    gs = campaign
    rng = RngTree(7).derive("offer")
    offer = sponsors._generate_offer(rng, gs, "jersey")
    gs.sponsor_market["jersey"] = [offer]
    team = gs.teams[gs.user_team_id]
    before = team.balance
    ok, _ = sponsors.sign_market_offer(gs, "jersey", offer.brand, "upfront")
    assert ok
    deal = gs.sponsor_slots["jersey"]
    assert deal.kind == "upfront"
    assert team.balance == before + offer.upfront.signing_bonus
    # Upfront structure discounts the objective bonuses.
    assert deal.objectives[0].bonus == int(offer.objectives[0].bonus * 0.7)
    assert gs.sponsor_market["jersey"] == []


def test_title_slot_gated_by_reputation(campaign: GameState) -> None:
    campaign.teams[campaign.user_team_id].reputation = 10.0
    cfg = sponsors.SLOT_CONFIG["title"]
    assert campaign.teams[campaign.user_team_id].reputation < cfg["rep_gate"]
    rng = RngTree(9).derive("always-roll")
    for _ in range(50):
        sponsors.maybe_offer(campaign, rng)
    assert "title" not in campaign.sponsor_slot_offers


# ---------------------------------------------------------------------------
# Facilities: costs + effects


def test_facility_upgrade_cost_schedule() -> None:
    assert economy.facility_upgrade_cost(0) == 150_000
    assert economy.facility_upgrade_cost(1) == 350_000
    assert economy.facility_upgrade_cost(2) == 700_000
    assert economy.facility_upgrade_cost(3) is None  # maxed


def test_facility_weekly_upkeep_sums_per_level() -> None:
    upkeep = economy.facility_weekly_upkeep(
        {"training_center": 2, "analytics_suite": 1}
    )
    expected = (
        economy.FACILITY_UPKEEP_PER_LEVEL["training_center"] * 2
        + economy.FACILITY_UPKEEP_PER_LEVEL["analytics_suite"] * 1
    )
    assert upkeep == expected
    assert economy.facility_weekly_upkeep({}) == 0


def test_facility_multipliers_scale_with_level(campaign: GameState) -> None:
    assert economy.facility_training_mult(campaign) == 1.0
    assert economy.facility_scout_mult(campaign) == 1.0

    campaign.facilities["training_center"] = 3
    campaign.facilities["analytics_suite"] = 2
    assert economy.facility_training_mult(campaign) == pytest.approx(1.18)
    assert economy.facility_scout_mult(campaign) == pytest.approx(1.16)


def test_facility_upkeep_is_charged_in_weekly_tick(campaign: GameState) -> None:
    campaign.facilities["training_center"] = 1
    campaign.facilities["analytics_suite"] = 1
    team = campaign.teams[campaign.user_team_id]
    before = team.balance
    got = sponsors.weekly_tick(campaign, user_won_this_week=False)
    expected_upkeep = economy.facility_weekly_upkeep(campaign.facilities)
    assert got == -expected_upkeep
    assert team.balance == before - expected_upkeep


# ---------------------------------------------------------------------------
# Old saves must load: every new field needs a default


def test_old_save_without_m4_fields_still_loads(campaign: GameState) -> None:
    raw = campaign.model_dump(mode="json")
    for key in ("sponsor_slots", "sponsor_slot_offers", "facilities"):
        assert key in raw
        del raw[key]
    reloaded = GameState.model_validate(raw)
    assert reloaded.sponsor_slots == {}
    assert reloaded.sponsor_slot_offers == {}
    assert reloaded.facilities == {}


# ---------------------------------------------------------------------------
# Itemized breakdown sums to net


def test_weekly_breakdown_sums_to_net(campaign: GameState) -> None:
    team_id = campaign.user_team_id
    team = campaign.teams[team_id]
    team.fan_count = 300_000
    campaign.standings[team_id] = TeamRecord(wins=6, losses=2)
    campaign.sponsor_slots["title"] = SponsorDeal(
        name="BigCo", kind="performance", weekly=10_000, per_win=5_000, weeks_left=20,
    )
    campaign.sponsor_slots["peripheral"] = SponsorDeal(
        name="GearCo", kind="steady", weekly=2_000, weeks_left=10,
    )
    campaign.facilities["training_center"] = 2

    d = economy.weekly_breakdown(campaign, staff_cost=1_500)

    assert d["income_total"] == d["sponsors_total"] + d["merch"] + d["tickets"]
    assert d["sponsors_total"] == d["sponsors_base"] + sum(d["sponsors_by_slot"].values())
    assert d["expense_total"] == d["salaries"] + d["staff"] + d["facility_upkeep"]
    assert d["net"] == d["income_total"] - d["expense_total"]
    assert d["salaries"] == sum(p.salary for p in campaign.roster(team_id))
    assert d["staff"] == 1_500
    assert d["facility_upkeep"] == economy.facility_weekly_upkeep(campaign.facilities)
    # win_rate 6/8 = 0.75 -> per_win counted at 0.75 in the title slot estimate.
    assert d["sponsors_by_slot"]["title"] == 10_000 + int(5_000 * 0.75)
    assert d["sponsors_by_slot"]["peripheral"] == 2_000
    assert d["sponsors_by_slot"]["jersey"] == 0


def test_cash_projection_matches_breakdown_first_week(campaign: GameState) -> None:
    team_id = campaign.user_team_id
    campaign.standings[team_id] = TeamRecord(wins=3, losses=3)
    campaign.sponsor_slots["jersey"] = SponsorDeal(
        name="MidCo", kind="steady", weekly=4_000, weeks_left=1,
    )
    d = economy.weekly_breakdown(campaign, staff_cost=0)
    rows = economy.cash_projection(campaign, staff_cost=0, weeks=8)
    assert len(rows) == 8
    assert rows[0]["net"] == d["net"]
    # The deal has exactly 1 week left, so it should not contribute from
    # week 2 onward — net should drop.
    assert rows[1]["net"] < rows[0]["net"]
    # Balance accumulates monotonically with the (declining) net stream in
    # this fixture (no expenses exceed income here).
    assert rows[-1]["balance"] >= campaign.teams[team_id].balance


# ---------------------------------------------------------------------------
# apply_weekly_finance stays backward compatible + adds revenue depth


def test_apply_weekly_finance_backward_compatible_signature(campaign: GameState) -> None:
    team_id = campaign.user_team_id
    team = campaign.teams[team_id]
    roster = campaign.roster(team_id)
    before = team.balance
    income, expenses = economy.apply_weekly_finance(team, roster, staff_cost=500)
    assert team.balance == before + income - expenses
    assert income > 0 and expenses > 0


def test_merch_ticket_income_scales_with_win_rate(campaign: GameState) -> None:
    team = campaign.teams[campaign.user_team_id]
    team.fan_count = 500_000
    losing = economy.merch_ticket_income(team, win_rate=0.0)
    neutral = economy.merch_ticket_income(team, win_rate=0.5)
    winning = economy.merch_ticket_income(team, win_rate=1.0)
    assert losing[0] < neutral[0] < winning[0]
    assert losing[1] < neutral[1] < winning[1]
