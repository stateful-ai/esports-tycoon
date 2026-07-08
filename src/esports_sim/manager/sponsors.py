"""Sponsorships — Motorsport-Manager-style.

Five slots (title, jersey, peripheral, stream, apparel — the last two
unlocked by the marketing office facility), each courted by a rotating
MARKET of competing brand offers. Every offer carries three payment
structures — cash up front, steady weekly, or performance-loaded — and
the user picks one at signing. Deals ride achievement objectives ("make
the playoffs", "win the split", "make Masters", "win Champions", "beat a
top-4 team") that pay bonuses when delivered and sour the brand when
missed. Offer money scales with MARKETABILITY (reputation, fans, star
power, results, international appearances) and with the org's history
with that specific brand — sponsors remember.

User team only; AI org finances stay background noise.

Backward compatibility: `GameState.sponsor` / `sponsor_offer` (pre-M4
single deal) and `sponsor_slot_offers` (M4 single-offer-per-slot) are no
longer written, but in-flight deals keep paying and stale offers expire
cleanly, so old saves land softly.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import development, economy
from esports_sim.manager.schedule import regular_season_weeks
from esports_sim.manager.state import (
    GameState,
    SponsorDeal,
    SponsorObjective,
    SponsorOffer,
    SponsorPackage,
)

SLOT_ORDER: tuple[str, ...] = ("title", "jersey", "peripheral", "stream", "apparel")
STRUCTURES: tuple[str, ...] = ("upfront", "steady", "performance")
MARKET_CAP_PER_SLOT = 3
OFFER_SHELF_LIFE = 2  # weeks on the table

# Money component ranges, scaled by slot mult × marketability × relation.
_BASE_UPFRONT_BONUS = (120, 240)  # * scale, * 1000
_BASE_UPFRONT_WEEKLY = (15, 30)  # * scale, * 100
_BASE_STEADY_WEEKLY = (80, 140)  # * scale, * 100
_BASE_PERF_WEEKLY = (35, 60)  # * scale, * 100
_BASE_PERF_PERWIN = (60, 100)  # * scale, * 100

# Objective bonuses scale with the chosen structure: performance deals
# carry the fattest result money.
_STRUCTURE_OBJ_MULT = {"upfront": 0.7, "steady": 1.0, "performance": 1.4}

SLOT_CONFIG: dict[str, dict] = {
    "title": {
        "names": [
            "Quantum Cloudworks", "Ironclad VPN", "Datafall Analytics",
            "Helios Financial", "Aegis Motorworks", "Polar Compute",
        ],
        "offer_prob": 0.16,
        "rep_gate": 55.0,
        "money_mult": 3.0,
        "weeks": (26, 40),
        "unlock": 0,
        # (kind, lo_k, hi_k) — thousands before scaling.
        "objectives": [("win_split", 90, 150), ("make_masters", 120, 200)],
        "big_objective": ("win_champions", 250, 400),  # rep >= 70 only
    },
    "jersey": {
        "names": [
            "Hypercarry Energy", "Streamforge", "Meridian Airlines",
            "Vantage Motors", "Nightshift Cafe", "Baseline Telecom",
        ],
        "offer_prob": 0.30,
        "rep_gate": 0.0,
        "money_mult": 1.0,
        "weeks": (20, 30),
        "unlock": 0,
        "objectives": [("make_playoffs", 40, 70), ("win_split", 60, 100)],
    },
    "peripheral": {
        "names": [
            "NovaTech Peripherals", "Apex Ergonomics", "Redline Chairs",
            "Clutchgear Audio", "Flickshot Optics", "Deadzone Desks",
        ],
        "offer_prob": 0.40,
        "rep_gate": 0.0,
        "money_mult": 0.4,
        "weeks": (12, 20),
        "unlock": 0,
        "objectives": [("beat_top4", 6, 12), ("make_playoffs", 25, 40)],
    },
    "stream": {
        "names": [
            "GlitchTV", "Vodstream", "Clipline", "OrbitCast", "Fanline",
        ],
        "offer_prob": 0.30,
        "rep_gate": 0.0,
        "money_mult": 0.7,
        "weeks": (14, 24),
        "unlock": 1,  # marketing_office level
        "objectives": [("beat_top4", 8, 14), ("make_playoffs", 30, 50)],
    },
    "apparel": {
        "names": [
            "Northpeak Apparel", "GG Threads", "Vanta Wear",
            "Loadout Clothing", "Kitline",
        ],
        "offer_prob": 0.35,
        "rep_gate": 0.0,
        "money_mult": 0.5,
        "weeks": (12, 22),
        "unlock": 2,
        "objectives": [("make_playoffs", 25, 45), ("win_split", 40, 70)],
    },
}

OBJECTIVE_LABELS = {
    "make_playoffs": "make the regional playoffs",
    "win_split": "win the regional split",
    "make_masters": "qualify for Masters",
    "win_champions": "win CHAMPIONS",
    "beat_top4": "beat a world top-4 team (per win)",
}


# ---------------------------------------------------------------------------
# Marketability + brand relations


def marketability(gs: GameState) -> float:
    """How sellable this org is right now: reputation carries, fans and
    star power (streamer/star_player traits) amplify, results and an
    international appearance spike it. ~1.0 for a mid-table org."""
    team = gs.teams[gs.user_team_id]
    rep = team.reputation / 50.0
    fans = min(team.fan_count, 2_000_000) / 1_500_000.0
    stars = sum(
        development.trait_value(p, "fan_mult", 1.0) - 1.0
        for p in gs.roster(team.id)
    )
    rec = gs.standings.get(team.id)
    wr = (
        rec.wins / max(1, rec.wins + rec.losses)
        if rec and (rec.wins + rec.losses) > 0
        else 0.5
    )
    intl = (
        0.25
        if team.id in gs.masters_seeds or team.id in gs.champions_seeds
        else 0.0
    )
    score = rep * 0.55 + fans * 0.25 + stars * 0.35 + (wr - 0.5) * 0.4 + intl
    return max(0.4, score) * economy.facility_marketing_mult(gs)


def relation(gs: GameState, brand: str) -> float:
    return gs.sponsor_relations.get(brand, 50.0)


def _bump_relation(gs: GameState, brand: str, delta: float) -> None:
    gs.sponsor_relations[brand] = round(
        min(100.0, max(0.0, relation(gs, brand) + delta)), 1
    )


def _relation_mult(gs: GameState, brand: str) -> float:
    """0.85 at relation 0 → 1.35 at relation 100."""
    return 0.85 + relation(gs, brand) / 200.0


def _offer_scale(gs: GameState, slot: str, brand: str) -> float:
    return (
        marketability(gs)
        * SLOT_CONFIG[slot]["money_mult"]
        * _relation_mult(gs, brand)
    )


# ---------------------------------------------------------------------------
# Offer generation (the market)


def _slot_unlocked(gs: GameState, slot: str) -> bool:
    need = SLOT_CONFIG[slot]["unlock"]
    return gs.facilities.get("marketing_office", 0) >= need


def _slot_signable(gs: GameState, slot: str) -> bool:
    """A slot can take a new deal when empty or nearly expired."""
    if slot == "jersey" and gs.sponsor is not None and gs.sponsor.weeks_left > 4:
        return False  # legacy pre-M4 deal still doing the jersey job
    deal = gs.sponsor_slots.get(slot)
    return deal is None or deal.weeks_left <= 4


def _roll_objectives(
    rng: np.random.Generator, gs: GameState, slot: str, scale: float
) -> list[SponsorObjective]:
    cfg = SLOT_CONFIG[slot]
    pool = list(cfg["objectives"])
    big = cfg.get("big_objective")
    if big and gs.teams[gs.user_team_id].reputation >= 70 and rng.random() < 0.4:
        pool.append(big)
    n = 1 if len(pool) < 2 or rng.random() < 0.55 else 2
    picks = [pool[int(i)] for i in rng.permutation(len(pool))[:n]]
    return [
        SponsorObjective(
            kind=kind,
            bonus=int(rng.integers(lo, hi + 1) * max(scale, 0.5)) * 1000,
        )
        for kind, lo, hi in picks
    ]


def _generate_offer(
    rng: np.random.Generator, gs: GameState, slot: str
) -> SponsorOffer:
    cfg = SLOT_CONFIG[slot]
    live = {o.brand for o in gs.sponsor_market.get(slot, [])}
    names = [n for n in cfg["names"] if n not in live] or cfg["names"]
    brand = names[int(rng.integers(0, len(names)))]
    scale = _offer_scale(gs, slot, brand)
    weeks = int(rng.integers(*cfg["weeks"]))
    # beat_top4 objectives pay per-win-sized money, not lump sums; roll
    # objectives once — structure choice scales them at signing.
    objectives = _roll_objectives(rng, gs, slot, scale)
    for obj in objectives:
        if obj.kind == "beat_top4":
            obj.bonus = max(2_000, obj.bonus // 4)
    return SponsorOffer(
        brand=brand,
        slot=slot,
        weeks=weeks,
        expires_week=gs.week + OFFER_SHELF_LIFE,
        upfront=SponsorPackage(
            signing_bonus=int(rng.integers(*_BASE_UPFRONT_BONUS) * scale) * 1000,
            weekly=int(rng.integers(*_BASE_UPFRONT_WEEKLY) * scale) * 100,
        ),
        steady=SponsorPackage(
            weekly=int(rng.integers(*_BASE_STEADY_WEEKLY) * scale) * 100,
        ),
        performance=SponsorPackage(
            weekly=int(rng.integers(*_BASE_PERF_WEEKLY) * scale) * 100,
            per_win=int(rng.integers(*_BASE_PERF_PERWIN) * scale) * 100,
        ),
        objectives=objectives,
    )


def maybe_offer(gs: GameState, rng: np.random.Generator) -> None:
    """Roll new market offers for every unlocked slot. Called weekly from
    advance_week (step 3b) — signature stable. Slots are visited in a
    fixed order and only draw from `rng` when actually rolling, keeping
    results deterministic per (seed, season, week)."""
    team = gs.teams[gs.user_team_id]
    for slot in SLOT_ORDER:
        cfg = SLOT_CONFIG[slot]
        if not _slot_unlocked(gs, slot):
            continue
        if cfg["rep_gate"] and team.reputation < cfg["rep_gate"]:
            continue
        live = gs.sponsor_market.get(slot, [])
        if len(live) >= MARKET_CAP_PER_SLOT:
            continue
        # Empty, signable slots attract suitors faster.
        prob = cfg["offer_prob"] * (1.5 if _slot_signable(gs, slot) and not live else 1.0)
        if rng.random() >= min(prob, 0.9):
            continue
        offer = _generate_offer(rng, gs, slot)
        gs.sponsor_market.setdefault(slot, []).append(offer)
        gs.push_news(
            f"{offer.brand} are courting the {slot} slot "
            f"({offer.steady.weekly:,}/wk steady, alternatives available). "
            f"On the table until week {offer.expires_week}."
        )


# ---------------------------------------------------------------------------
# Signing / declining market offers


def sign_market_offer(
    gs: GameState, slot: str, brand: str, structure: str
) -> tuple[bool, str]:
    if slot not in SLOT_ORDER:
        return False, f"unknown slot {slot}"
    if structure not in STRUCTURES:
        return False, f"unknown structure {structure}"
    offer = next(
        (o for o in gs.sponsor_market.get(slot, []) if o.brand == brand), None
    )
    if offer is None:
        return False, "that offer is no longer on the table"
    if not _slot_signable(gs, slot):
        return False, f"the {slot} slot already has an active deal"
    pkg: SponsorPackage = getattr(offer, structure)
    mult = _STRUCTURE_OBJ_MULT[structure]
    deal = SponsorDeal(
        name=brand,
        kind=structure,
        signing_bonus=pkg.signing_bonus,
        weekly=pkg.weekly,
        per_win=pkg.per_win,
        weeks_left=offer.weeks,
        objectives=[
            SponsorObjective(kind=o.kind, bonus=int(o.bonus * mult))
            for o in offer.objectives
        ],
    )
    team = gs.teams[gs.user_team_id]
    team.balance += deal.signing_bonus
    gs.sponsor_slots[slot] = deal
    gs.sponsor_market[slot] = [
        o for o in gs.sponsor_market.get(slot, []) if o.brand != brand
    ]
    _bump_relation(gs, brand, +2.0)
    gs.push_news(
        f"{team.name} sign a {slot} deal with {brand} ({_describe(deal)})."
    )
    return True, f"signed with {brand} ({slot}, {structure})"


def decline_market_offer(gs: GameState, slot: str, brand: str) -> tuple[bool, str]:
    offers = gs.sponsor_market.get(slot, [])
    offer = next((o for o in offers if o.brand == brand), None)
    if offer is None:
        return False, "no such offer"
    gs.sponsor_market[slot] = [o for o in offers if o.brand != brand]
    _bump_relation(gs, brand, -3.0)
    return True, f"declined {brand} ({slot})"


def _describe(deal: SponsorDeal) -> str:
    parts = []
    if deal.signing_bonus:
        parts.append(f"{deal.signing_bonus:,} up front")
    if deal.weekly:
        parts.append(f"{deal.weekly:,}/wk")
    if deal.per_win:
        parts.append(f"{deal.per_win:,} per win")
    if deal.objectives:
        parts.append(
            "objectives: "
            + "; ".join(
                f"{OBJECTIVE_LABELS.get(o.kind, o.kind)} → {o.bonus:,}"
                for o in deal.objectives
            )
        )
    return ", ".join(parts) + f" for {deal.weeks_left} weeks"


# ---------------------------------------------------------------------------
# Objectives: evaluated weekly against real season state


def _season_fixtures(gs: GameState, stage: str) -> list:
    return [
        f
        for f in gs.fixtures
        if f.stage == stage and f.id.startswith(f"s{gs.season}")
    ]


def _eval_objective(gs: GameState, obj: SponsorObjective, brand: str) -> int:
    """Resolve one objective against the current season state. Returns
    the bonus paid this call (0 if nothing resolved)."""
    uid = gs.user_team_id
    if obj.kind == "beat_top4":
        # Recurring rider, handled in the weekly payout loop — not here.
        return 0
    if obj.met is not None:
        return 0

    met: bool | None = None
    semis = _season_fixtures(gs, "semi")
    finals = _season_fixtures(gs, "final")
    if obj.kind == "make_playoffs" and semis:
        met = any(uid in (f.team_a, f.team_b) for f in semis)
    elif obj.kind == "win_split" and finals:
        if any(f.winner_id == uid for f in finals if f.played):
            met = True
        elif all(f.played for f in finals):
            met = False
    elif obj.kind == "make_masters" and gs.masters_seeds:
        met = uid in gs.masters_seeds
    elif obj.kind == "win_champions":
        cf = next(
            (f for f in _season_fixtures(gs, "champ_final") if f.played), None
        )
        if cf is not None:
            met = cf.winner_id == uid
    if met is None:
        return 0

    obj.met = met
    if met:
        gs.teams[uid].balance += obj.bonus
        _bump_relation(gs, brand, +4.0)
        gs.push_news(
            f"Objective met — {brand} pay {obj.bonus:,} cr "
            f"({OBJECTIVE_LABELS.get(obj.kind, obj.kind)})."
        )
        return obj.bonus
    _bump_relation(gs, brand, -6.0)
    gs.push_news(
        f"{brand} note the missed objective "
        f"({OBJECTIVE_LABELS.get(obj.kind, obj.kind)}). Relations cool."
    )
    return 0


# ---------------------------------------------------------------------------
# Legacy single-deal API (pre-M4 saves / tests)


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


def accept_slot_offer(gs: GameState, slot: str) -> tuple[bool, str]:
    """M4-era single-offer path; still honored for old saves."""
    offer = gs.sponsor_slot_offers.get(slot)
    if offer is None:
        return False, "no offer on the table"
    team = gs.teams[gs.user_team_id]
    team.balance += offer.signing_bonus
    gs.sponsor_slots[slot] = offer
    del gs.sponsor_slot_offers[slot]
    gs.push_news(f"{team.name} sign a {slot} deal with {offer.name}.")
    return True, f"signed with {offer.name} ({slot})"


def decline_slot_offer(gs: GameState, slot: str) -> tuple[bool, str]:
    offer = gs.sponsor_slot_offers.get(slot)
    if offer is None:
        return False, "no offer on the table"
    name = offer.name
    del gs.sponsor_slot_offers[slot]
    return True, f"declined {name} ({slot})"


# ---------------------------------------------------------------------------
# Weekly tick


def weekly_tick(gs: GameState, user_won_this_week: bool) -> int:
    """Pay out every active deal, resolve objectives, expire stale market
    offers, and charge facility upkeep. Returns the net delta applied to
    the user's balance (report display). Called weekly from advance_week
    (step 3b) — signature stable.

    Facility upkeep is charged here rather than in apply_weekly_finance's
    per-team loop because this function already runs exactly once a week
    for the user org with the full GameState in hand."""
    total = 0
    team = gs.teams[gs.user_team_id]

    # Legacy single-deal fields (pre-M4 saves): still fully functional.
    if gs.sponsor_offer is not None:
        gs.push_news(f"{gs.sponsor_offer.name}'s offer expired unanswered.")
        gs.sponsor_offer = None
    legacy = gs.sponsor
    if legacy is not None:
        income = legacy.weekly + (legacy.per_win if user_won_this_week else 0)
        team.balance += income
        total += income
        legacy.weeks_left -= 1
        if legacy.weeks_left <= 0:
            gs.push_news(f"The {legacy.name} deal has run its course.")
            gs.sponsor = None

    # M4-era pending single offers expire.
    for slot in list(gs.sponsor_slot_offers):
        gs.push_news(
            f"{gs.sponsor_slot_offers[slot].name}'s {slot} offer expired unanswered."
        )
        del gs.sponsor_slot_offers[slot]

    # Market offers expire on schedule.
    for slot in SLOT_ORDER:
        live = gs.sponsor_market.get(slot, [])
        expired = [o for o in live if o.expires_week <= gs.week]
        for o in expired:
            gs.push_news(f"{o.brand}'s {slot} offer left the table.")
        if expired:
            gs.sponsor_market[slot] = [
                o for o in live if o.expires_week > gs.week
            ]

    # Which opponent did we play this week? (for the beat_top4 rider)
    fixture = gs.team_fixture(gs.user_team_id)
    beat_top4 = False
    if (
        fixture is not None
        and fixture.played
        and fixture.winner_id == gs.user_team_id
    ):
        opp = fixture.team_b if fixture.team_a == gs.user_team_id else fixture.team_a
        opp_rank = gs.teams[opp].world_rank
        beat_top4 = opp_rank is not None and opp_rank <= 4

    # Active slot deals: pay the base, ride the objectives, count down.
    for slot in SLOT_ORDER:
        deal = gs.sponsor_slots.get(slot)
        if deal is None:
            continue
        base = deal.weekly + (deal.per_win if user_won_this_week else 0)
        team.balance += base
        total += base
        for obj in deal.objectives:
            if obj.kind == "beat_top4":
                if beat_top4:
                    team.balance += obj.bonus
                    total += obj.bonus
                    obj.met = True  # triggered at least once this deal
                    gs.push_news(
                        f"{deal.name} pay a {obj.bonus:,} cr top-4 scalp bonus."
                    )
            else:
                # Pays into the balance internally; returns the amount.
                total += _eval_objective(gs, obj, deal.name)
        deal.weeks_left -= 1
        if deal.weeks_left <= 0:
            _bump_relation(gs, deal.name, +8.0)
            gs.push_news(
                f"The {deal.name} {slot} deal has run its course on good terms."
            )
            del gs.sponsor_slots[slot]

    # Facility upkeep.
    upkeep = economy.facility_weekly_upkeep(gs.facilities)
    if upkeep:
        team.balance -= upkeep
        total -= upkeep

    return total
