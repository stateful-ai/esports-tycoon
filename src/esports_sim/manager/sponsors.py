"""Sponsorship offers — the finances screen's actual decisions.

Three concurrent slots — title (big money, reputation-gated), jersey
(the original mid-tier mechanics), peripheral (smaller, fan-driven) — each
holding at most one active deal plus one pending offer. An offer appears
occasionally per open slot (more often when that slot is empty), scaled by
reputation + fan_count, in one of three shapes: cash up front, steady
weekly, or performance-loaded. Offers sit on the table for one week. User
team only; AI org finances stay background noise.

Backward compatibility: `GameState.sponsor` / `sponsor_offer` are the
pre-M4 single-deal fields. New offers are never written there any more
(everything goes through the slot dicts below), but `accept_offer` /
`decline_offer` / the legacy half of `weekly_tick` still operate on them
unchanged, so old saves that already had a deal in flight keep paying out
exactly as before until it runs its course.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import economy
from esports_sim.manager.state import GameState, SponsorDeal
from esports_sim.schemas import Team

SLOT_ORDER: tuple[str, ...] = ("title", "jersey", "peripheral")

# Pre-scale money ranges, shared shape across slots (kind -> component).
_BASE_UPFRONT_BONUS = (120, 240)  # * scale, * 1000
_BASE_UPFRONT_WEEKLY = (15, 30)  # * scale, * 100
_BASE_STEADY_WEEKLY = (80, 140)  # * scale, * 100
_BASE_PERF_WEEKLY = (35, 60)  # * scale, * 100
_BASE_PERF_PERWIN = (60, 100)  # * scale, * 100

SLOT_CONFIG: dict[str, dict] = {
    "title": {
        "names": [
            "Quantum Cloudworks", "Ironclad VPN", "Datafall Analytics", "Helios Financial",
        ],
        "offer_prob": 0.12,  # prestige brands don't call often
        "rep_gate": 55.0,  # need a real reputation before the big money shows up
        "money_mult": 3.0,
        "fan_weight": 0.08,  # mostly reputation-driven
        "weeks": (26, 40),
    },
    "jersey": {
        "names": [
            "Hypercarry Energy", "Streamforge", "Meridian Airlines", "Vantage Motors",
        ],
        "offer_prob": 0.30,  # unchanged from the original single-deal cadence
        "rep_gate": 0.0,
        "money_mult": 1.0,
        "fan_weight": 0.04,
        "weeks": (20, 30),
    },
    "peripheral": {
        "names": [
            "NovaTech Peripherals", "Apex Ergonomics", "Redline Chairs", "Clutchgear Audio",
        ],
        "offer_prob": 0.40,  # smaller commitment, offered more freely
        "rep_gate": 0.0,
        "money_mult": 0.4,
        "fan_weight": 0.35,  # gear brands chase eyeballs, not trophies
        "weeks": (12, 20),
    },
}


def _offer_scale(team: Team, cfg: dict) -> float:
    """Blend of reputation and fan_count, weighted per-slot, then scaled by
    the slot's money multiplier. Deterministic, no randomness here."""
    rep = max(0.4, team.reputation / 50.0)  # rep 50 = baseline
    fan_norm = min(team.fan_count, 3_000_000) / 1_000_000.0  # 0..3
    fw = cfg["fan_weight"]
    blended = rep * (1.0 - fw) + fan_norm * fw
    return blended * cfg["money_mult"]


def _slot_open(gs: GameState, slot: str) -> bool:
    if gs.sponsor_slot_offers.get(slot) is not None:
        return False
    if slot == "jersey" and gs.sponsor is not None and gs.sponsor.weeks_left > 4:
        # A legacy (pre-M4) deal is still doing the jersey slot's job.
        return False
    deal = gs.sponsor_slots.get(slot)
    return deal is None or deal.weeks_left <= 4


def _generate_deal(rng: np.random.Generator, team: Team, cfg: dict) -> SponsorDeal:
    scale = _offer_scale(team, cfg)
    name = cfg["names"][int(rng.integers(0, len(cfg["names"])))]
    kind = ["upfront", "steady", "performance"][int(rng.integers(0, 3))]
    weeks_lo, weeks_hi = cfg["weeks"]
    weeks_left = int(rng.integers(weeks_lo, weeks_hi + 1))
    if kind == "upfront":
        return SponsorDeal(
            name=name, kind=kind,
            signing_bonus=int(rng.integers(*_BASE_UPFRONT_BONUS) * scale) * 1000,
            weekly=int(rng.integers(*_BASE_UPFRONT_WEEKLY) * scale) * 100,
            weeks_left=weeks_left,
        )
    if kind == "steady":
        return SponsorDeal(
            name=name, kind=kind,
            weekly=int(rng.integers(*_BASE_STEADY_WEEKLY) * scale) * 100,
            weeks_left=weeks_left,
        )
    return SponsorDeal(
        name=name, kind=kind,
        weekly=int(rng.integers(*_BASE_PERF_WEEKLY) * scale) * 100,
        per_win=int(rng.integers(*_BASE_PERF_PERWIN) * scale) * 100,
        weeks_left=weeks_left,
    )


def maybe_offer(gs: GameState, rng: np.random.Generator) -> None:
    """Roll for a new offer in each open slot. Called weekly from
    advance_week (step 3b) — signature kept stable so campaign.py needs no
    edits. Slots are always visited in a fixed order and only draw from
    `rng` when actually rolling, so results stay deterministic for a given
    (seed, season, week)."""
    team = gs.teams[gs.user_team_id]
    for slot in SLOT_ORDER:
        cfg = SLOT_CONFIG[slot]
        if not _slot_open(gs, slot):
            continue
        if cfg["rep_gate"] and team.reputation < cfg["rep_gate"]:
            continue
        if rng.random() >= cfg["offer_prob"]:
            continue
        deal = _generate_deal(rng, team, cfg)
        gs.sponsor_slot_offers[slot] = deal
        gs.push_news(
            f"{slot.title()} sponsorship offer from {deal.name}: "
            f"{_describe(deal)}. On the table for one week."
        )


def _describe(deal: SponsorDeal) -> str:
    parts = []
    if deal.signing_bonus:
        parts.append(f"{deal.signing_bonus:,} up front")
    if deal.weekly:
        parts.append(f"{deal.weekly:,}/wk")
    if deal.per_win:
        parts.append(f"{deal.per_win:,} per win")
    return ", ".join(parts) + f" for {deal.weeks_left} weeks"


# -- legacy single-deal API (pre-M4 saves / tests) ----------------------------


def accept_offer(gs: GameState) -> tuple[bool, str]:
    offer = gs.sponsor_offer
    if offer is None:
        return False, "no offer on the table"
    team = gs.teams[gs.user_team_id]
    team.balance += offer.signing_bonus
    gs.sponsor = offer
    gs.sponsor_offer = None
    gs.push_news(f"{team.name} sign with {offer.name} ({_describe(offer)}).")
    return True, f"signed with {offer.name}"


def decline_offer(gs: GameState) -> tuple[bool, str]:
    if gs.sponsor_offer is None:
        return False, "no offer on the table"
    name = gs.sponsor_offer.name
    gs.sponsor_offer = None
    return True, f"declined {name}"


# -- slot API (M4) -------------------------------------------------------------


def accept_slot_offer(gs: GameState, slot: str) -> tuple[bool, str]:
    if slot not in SLOT_ORDER:
        return False, f"unknown slot {slot}"
    offer = gs.sponsor_slot_offers.get(slot)
    if offer is None:
        return False, "no offer on the table"
    team = gs.teams[gs.user_team_id]
    team.balance += offer.signing_bonus
    gs.sponsor_slots[slot] = offer
    del gs.sponsor_slot_offers[slot]
    gs.push_news(f"{team.name} sign a {slot} deal with {offer.name} ({_describe(offer)}).")
    return True, f"signed with {offer.name} ({slot})"


def decline_slot_offer(gs: GameState, slot: str) -> tuple[bool, str]:
    if slot not in SLOT_ORDER:
        return False, f"unknown slot {slot}"
    offer = gs.sponsor_slot_offers.get(slot)
    if offer is None:
        return False, "no offer on the table"
    name = offer.name
    del gs.sponsor_slot_offers[slot]
    return True, f"declined {name} ({slot})"


def weekly_tick(gs: GameState, user_won_this_week: bool) -> int:
    """Pay out every active deal (legacy + all three slots), expire stale
    offers, and charge facility upkeep. Returns the net delta applied to
    the user's balance this call (report display). Called weekly from
    advance_week (step 3b) — signature kept stable so campaign.py needs no
    edits.

    Facility upkeep is charged from here (rather than from
    apply_weekly_finance's per-team loop in campaign.py) because that loop
    calls apply_weekly_finance identically for every team and has no way
    to know which one is the user org without an edit to campaign.py.
    This function already gets the full GameState and already runs once a
    week for the user team only, so it is the natural place to apply an
    org-specific weekly cost without touching campaign.py."""
    total = 0

    # Legacy single-deal fields (pre-M4 saves): still fully functional.
    if gs.sponsor_offer is not None:
        gs.push_news(f"{gs.sponsor_offer.name}'s offer expired unanswered.")
        gs.sponsor_offer = None
    legacy = gs.sponsor
    if legacy is not None:
        income = legacy.weekly + (legacy.per_win if user_won_this_week else 0)
        gs.teams[gs.user_team_id].balance += income
        total += income
        legacy.weeks_left -= 1
        if legacy.weeks_left <= 0:
            gs.push_news(f"The {legacy.name} deal has run its course.")
            gs.sponsor = None

    # Slot offers expire after a week on the table.
    for slot in SLOT_ORDER:
        offer = gs.sponsor_slot_offers.get(slot)
        if offer is not None:
            gs.push_news(f"{offer.name}'s {slot} offer expired unanswered.")
            del gs.sponsor_slot_offers[slot]

    # Active slot deals pay out and count down.
    team = gs.teams[gs.user_team_id]
    for slot in SLOT_ORDER:
        deal = gs.sponsor_slots.get(slot)
        if deal is None:
            continue
        income = deal.weekly + (deal.per_win if user_won_this_week else 0)
        team.balance += income
        total += income
        deal.weeks_left -= 1
        if deal.weeks_left <= 0:
            gs.push_news(f"The {deal.name} {slot} deal has run its course.")
            del gs.sponsor_slots[slot]

    # Facility upkeep.
    upkeep = economy.facility_weekly_upkeep(gs.facilities)
    if upkeep:
        team.balance -= upkeep
        total -= upkeep

    return total
