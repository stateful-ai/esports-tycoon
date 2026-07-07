"""Sponsorship offers — the finances screen's actual decisions.

An offer appears occasionally (more often when the org has no active
deal), scaled by reputation, in one of three shapes: cash up front,
steady weekly, or performance-loaded. Offers sit on the table for one
week. User team only; AI org finances stay background noise.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.state import GameState, SponsorDeal

SPONSOR_NAMES = [
    "Hypercarry Energy",
    "NovaTech Peripherals",
    "Quantum Cloudworks",
    "Ironclad VPN",
    "Streamforge",
    "Apex Ergonomics",
    "Datafall Analytics",
    "Redline Chairs",
]

OFFER_PROB = 0.30  # per week, when the slot logic allows one


def _slot_open(gs: GameState) -> bool:
    if gs.sponsor_offer is not None:
        return False
    return gs.sponsor is None or gs.sponsor.weeks_left <= 4


def maybe_offer(gs: GameState, rng: np.random.Generator) -> None:
    """Roll for a new offer. Called weekly from advance_week."""
    if not _slot_open(gs):
        return
    if rng.random() >= OFFER_PROB:
        return
    team = gs.teams[gs.user_team_id]
    scale = max(0.4, team.reputation / 50.0)  # rep 50 = baseline money
    name = SPONSOR_NAMES[int(rng.integers(0, len(SPONSOR_NAMES)))]
    kind = ["upfront", "steady", "performance"][int(rng.integers(0, 3))]
    if kind == "upfront":
        deal = SponsorDeal(
            name=name, kind=kind,
            signing_bonus=int(rng.integers(120, 240) * scale) * 1000,
            weekly=int(rng.integers(15, 30)) * 100,
            weeks_left=20,
        )
    elif kind == "steady":
        deal = SponsorDeal(
            name=name, kind=kind,
            weekly=int(rng.integers(80, 140) * scale) * 100,
            weeks_left=30,
        )
    else:
        deal = SponsorDeal(
            name=name, kind=kind,
            weekly=int(rng.integers(35, 60) * scale) * 100,
            per_win=int(rng.integers(60, 100) * scale) * 100,
            weeks_left=25,
        )
    gs.sponsor_offer = deal
    gs.push_news(
        f"Sponsorship offer from {deal.name}: "
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


def weekly_tick(gs: GameState, user_won_this_week: bool) -> int:
    """Pay out the active deal, expire stale offers/deals. Returns the
    deal income added this week (report display)."""
    # Offers expire after sitting a week (maybe_offer never double-books).
    if gs.sponsor_offer is not None:
        gs.push_news(f"{gs.sponsor_offer.name}'s offer expired unanswered.")
        gs.sponsor_offer = None

    deal = gs.sponsor
    if deal is None:
        return 0
    income = deal.weekly + (deal.per_win if user_won_this_week else 0)
    gs.teams[gs.user_team_id].balance += income
    deal.weeks_left -= 1
    if deal.weeks_left <= 0:
        gs.push_news(f"The {deal.name} deal has run its course.")
        gs.sponsor = None
    return income
