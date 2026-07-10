"""Legacy Mode's career frame: offers, contracts, boards, dismissal,
the job market, and manager reputation.

Two game modes exist (GameState.game_mode):
- "sandbox": the classic game. Seats exist (for careers/chronicle
  attribution) but carry no contract and can never be dismissed.
- "legacy": every human seat holds a ManagerContract. The board reviews
  the season goal at the offseason and its patience moves; in-season
  streaks drift it a little. Patience at the floor = dismissal -> the
  seat enters the job market and the world cannot advance until they
  accept an offer (enforced by the UI layers via `blocked_seats`).

Everything here is campaign-deterministic: offer sets derive from
blake2 of (seed, season, seat id); no wall clock, no salted hash().
Reputation is DERIVED from the chronicle on read — never stored.
"""

from __future__ import annotations

import hashlib

import numpy as np

from esports_sim.manager import chronicle
from esports_sim.manager.state import (
    CareerOffer,
    GameState,
    InboxItem,
    ManagerContract,
    ManagerSeat,
)

# Patience mechanics.
PATIENCE_GOAL_MET = +15.0
PATIENCE_GOAL_MISSED = -35.0
PATIENCE_LOSS_STREAK = -3.0  # per week, once the streak is running
PATIENCE_WIN_STREAK = +1.0
LOSS_STREAK_LEN = 4
WIN_STREAK_LEN = 3
MIDSEASON_FLOOR = 5.0  # below this the board doesn't wait for May
RENEWAL_FLOOR = 50.0  # an expiring contract renews at/above this

# Offer archetypes: (contract seasons, board goal, starting patience).
# The org each archetype attaches to is picked by `_archetype_candidates`.
ARCHETYPES: dict[str, tuple[int, str, float]] = {
    "dynasty": (2, "make_masters", 60.0),
    "sleeping_giant": (2, "make_playoffs", 70.0),
    "academy": (3, "make_playoffs", 80.0),
    "rebuilder": (3, "top_half", 90.0),
}

_BLURBS = {
    "dynasty": (
        "A powerhouse with championship expectations. Big budget, short "
        "leash: the board expects international results now."
    ),
    "sleeping_giant": (
        "A historic org with a big fanbase and a trophy drought. Revive "
        "them and the town is yours; stall and the board moves on."
    ),
    "academy": (
        "A development-first org. Modest goals, real patience, and a "
        "board that values the players you grow as much as the wins."
    ),
    "rebuilder": (
        "Bottom of the table, thin budget, but time. The board wants a "
        "trajectory, not a trophy — three seasons to build something."
    ),
}


def _rng_for(seed: int, *parts: object) -> np.random.Generator:
    key = "|".join(str(x) for x in ("career", *parts))
    digest = hashlib.blake2b(
        f"{seed}|{key}".encode("utf-8"), digest_size=8
    ).digest()
    return np.random.default_rng(int.from_bytes(digest, "big"))


def seat_id_for(team_id: str) -> str:
    return f"mgr_{team_id}"


def create_seat(
    gs: GameState,
    team_id: str,
    name: str = "",
    offer: CareerOffer | None = None,
) -> ManagerSeat:
    """Mint a manager seat for a newly joined human. In legacy mode an
    accepted CareerOffer supplies the contract; sandbox seats get none."""
    mid = seat_id_for(team_id)
    # A seat id is minted once per founding org. If a PREVIOUS manager
    # founded here (moved on / was fired), suffix — never overwrite a
    # career that already exists.
    n = 2
    while mid in gs.managers:
        mid = f"{seat_id_for(team_id)}_{n}"
        n += 1
    contract = None
    archetype = ""
    if gs.game_mode == "legacy":
        o = offer
        if o is None:  # joiner picked a team without a formal offer card
            seasons, goal, patience = ARCHETYPES["sleeping_giant"]
            o = CareerOffer(
                team_id=team_id, archetype="sleeping_giant",
                seasons=seasons, goal=goal, patience=patience, blurb="",
            )
        contract = ManagerContract(
            start_season=gs.season, seasons=o.seasons,
            goal=o.goal, patience=o.patience,
        )
        archetype = o.archetype
    seat = ManagerSeat(
        id=mid,
        name=name or f"{gs.teams[team_id].tag} manager",
        team_id=team_id,
        contract=contract,
        archetype=archetype,
    )
    gs.managers[mid] = seat
    chronicle.record(
        gs, "appointment",
        f"{seat.name} takes over at {gs.teams[team_id].name}.",
        team_id=team_id,
        manager_id=mid,
        data={"archetype": archetype} if archetype else {},
    )
    return seat


# -- career offers -----------------------------------------------------------


def _org_strength(gs: GameState, tid: str) -> float:
    """A composite an offer generator can rank orgs by (no history needed
    at new game): roster quality dominates, money and standing shade it."""
    from esports_sim.manager import market

    t = gs.teams[tid]
    roster_q = (
        float(np.mean([market.player_quality(p) for p in gs.roster(tid)]))
        if t.player_ids
        else 40.0
    )
    return roster_q + t.reputation * 0.10 + min(t.balance, 3_000_000) / 300_000.0


def new_game_offers(
    gs: GameState, seat_index: int = 0, taken: set[str] | None = None
) -> list[CareerOffer]:
    """The 3-4 offers a legacy career starts from. Deterministic from
    (seed, seat index); `taken` excludes teams other managers hold. Each
    archetype draws from a different band of the strength table, so the
    offers really are different careers, not different difficulty labels."""
    taken = taken or set()
    tids = [
        tid
        for tid in sorted(gs.teams)
        if gs.teams[tid].tier == 1 and tid not in taken
    ]
    ranked = sorted(tids, key=lambda t: (-_org_strength(gs, t), t))
    n = len(ranked)
    if n < 4:
        bands = {k: ranked for k in ARCHETYPES}
    else:
        bands = {
            "dynasty": ranked[: max(1, n // 6)],
            "sleeping_giant": ranked[n // 6: n // 2],
            "academy": ranked[n // 3: 2 * n // 3],
            "rebuilder": ranked[3 * n // 4:],
        }
    rng = _rng_for(gs.seed, "newgame", seat_index)
    offers: list[CareerOffer] = []
    used: set[str] = set()
    for arch in ("dynasty", "sleeping_giant", "academy", "rebuilder"):
        pool = [t for t in bands[arch] if t not in used]
        if not pool:
            continue
        tid = pool[int(rng.integers(0, len(pool)))]
        used.add(tid)
        seasons, goal, patience = ARCHETYPES[arch]
        offers.append(
            CareerOffer(
                team_id=tid, archetype=arch, seasons=seasons,
                goal=goal, patience=patience, blurb=_BLURBS[arch],
            )
        )
    return offers


def job_market_offers(
    gs: GameState, mid: str, exclude: set[str] | None = None
) -> list[CareerOffer]:
    """Offers for a dismissed manager: AI-run tier-1 orgs, weighted
    toward the struggling (they're the ones hiring), better ones opening
    up as the manager's trophy case grows. `exclude` keeps the org that
    just fired them from calling back the same week."""
    rep = reputation(gs, mid)
    prestige = rep["international_success"] + rep["domestic_success"]
    tids = [
        tid
        for tid in sorted(gs.teams)
        if gs.teams[tid].tier == 1
        and not gs.is_human(tid)
        and tid not in (exclude or set())
    ]
    # Standings position (worse = more likely to be hiring).
    order = {tid: i for i, tid in enumerate(gs.standings_order(tier=1))}
    ranked = sorted(tids, key=lambda t: (-order.get(t, 0), t))  # worst first
    rng = _rng_for(gs.seed, "market", gs.season, mid)
    # A struggling org always calls; with prestige, better projects do too.
    picks: list[str] = []
    strugglers = ranked[: max(3, len(ranked) // 3)]
    if strugglers:
        picks.append(strugglers[int(rng.integers(0, len(strugglers)))])
    mid_pool = [t for t in ranked[len(ranked) // 3: 2 * len(ranked) // 3] if t not in picks]
    if mid_pool:
        picks.append(mid_pool[int(rng.integers(0, len(mid_pool)))])
    if prestige >= 30.0:
        top_pool = [t for t in ranked[2 * len(ranked) // 3:] if t not in picks]
        if top_pool:
            picks.append(top_pool[int(rng.integers(0, len(top_pool)))])
    offers = []
    for tid in picks:
        pos = order.get(tid, 0)
        arch = (
            "rebuilder"
            if pos >= len(order) * 2 // 3
            else ("sleeping_giant" if pos >= len(order) // 3 else "dynasty")
        )
        seasons, goal, patience = ARCHETYPES[arch]
        offers.append(
            CareerOffer(
                team_id=tid, archetype=arch, seasons=seasons,
                goal=goal, patience=patience, blurb=_BLURBS[arch],
            )
        )
    return offers


# -- board review ------------------------------------------------------------


def _goal_met(gs: GameState, tid: str, goal: str) -> bool:
    """Season-end verdict on a board goal (SponsorObjective vocabulary).
    Runs in the offseason tick BEFORE brackets/seeds are cleared."""

    def season_fixtures(stage: str) -> list:
        return [
            f
            for f in gs.fixtures
            if f.id.startswith(f"s{gs.season}") and f.stage == stage
        ]

    region = str(gs.teams[tid].region)
    order = gs.standings_order(region, tier=gs.teams[tid].tier)
    if goal == "make_playoffs":
        return any(
            tid in (f.team_a, f.team_b) for f in season_fixtures("semi")
        )
    if goal == "win_split":
        return any(f.winner_id == tid for f in season_fixtures("final"))
    if goal == "make_masters":
        return tid in gs.masters_seeds
    if goal == "win_champions":
        cf = next(iter(season_fixtures("champ_final")), None)
        return cf is not None and cf.winner_id == tid
    if goal == "top_half":
        return tid in order[: max(1, len(order) // 2)]
    return False


GOAL_LABELS = {
    "make_playoffs": "reach the playoffs",
    "win_split": "win the regional title",
    "make_masters": "qualify for Masters",
    "win_champions": "win Champions",
    "top_half": "finish in the top half",
}


def review_boards(gs: GameState) -> list[str]:
    """The offseason board review for every employed legacy seat. Moves
    patience, decides renewals/dismissals, pushes the news, and PARKS
    dismissals in `career_offers_by` — the seat keeps its team until
    `apply_dismissals` runs (after inboxes generate, so the fired manager
    still receives their own bad news). Returns dismissed seat ids."""
    if gs.game_mode != "legacy":
        return []
    dismissed: list[str] = []
    for mid in sorted(gs.managers):
        seat = gs.managers[mid]
        if not seat.team_id or seat.contract is None:
            continue
        c = seat.contract
        tid = seat.team_id
        team = gs.teams[tid]
        met = _goal_met(gs, tid, c.goal)
        c.patience = float(
            np.clip(
                c.patience
                + (PATIENCE_GOAL_MET if met else PATIENCE_GOAL_MISSED),
                0.0,
                100.0,
            )
        )
        label = GOAL_LABELS.get(c.goal, c.goal)
        if met:
            gs.push_private_news(
                f"Board review: goal met ({label}). The board is pleased "
                f"(patience {c.patience:.0f}).",
                owner=tid,
            )
        else:
            gs.push_private_news(
                f"Board review: goal missed ({label}). The board's patience "
                f"wears thin ({c.patience:.0f}).",
                owner=tid,
            )
        expired = gs.season - c.start_season + 1 >= c.seasons
        if c.patience <= 0.0 or (expired and c.patience < RENEWAL_FLOOR):
            dismissed.append(mid)
            # Derive the offers NOW, while the season's standings are
            # still live — the offseason resets the table before
            # apply_dismissals runs.
            gs.career_offers_by[mid] = job_market_offers(
                gs, mid, exclude={tid}
            )
            gs.push_private_news(
                f"{team.name} part ways with you. New offers await.",
                owner=tid,
            )
            chronicle.record(
                gs, "dismissal",
                f"{seat.name} leaves {team.name} after the board review.",
                team_id=tid,
                manager_id=mid,
            )
        elif expired:
            # The board renews: same goal one notch harder is tempting,
            # but keep phase 1 honest — same terms, patience carried.
            c.start_season = gs.season + 1
            gs.push_private_news(
                f"The board renews your contract for {c.seasons} more "
                f"seasons (goal: {label}).",
                owner=tid,
            )
    return dismissed


def apply_dismissals(gs: GameState, dismissed: list[str]) -> None:
    """Unseat fired managers (run AFTER the offseason inboxes generate).
    The org reverts to AI control; the seat gets its job-market offers.
    The world then can't advance until every seat re-employs (the UI
    layers enforce via `blocked_seats`)."""
    for mid in dismissed:
        seat = gs.managers[mid]
        old_tid = seat.team_id
        if old_tid in gs.human_team_ids:
            gs.human_team_ids.remove(old_tid)
        seat.last_team_id = old_tid
        seat.team_id = ""
        seat.contract = None
        if not gs.career_offers_by.get(mid):
            # Board-review dismissals derived their offers at review time
            # (live standings); the mid-season path derives here.
            gs.career_offers_by[mid] = job_market_offers(
                gs, mid, exclude={old_tid}
            )


def accept_offer(gs: GameState, mid: str, team_id: str) -> tuple[bool, str]:
    """A dismissed manager takes one of their offers: the seat rebinds,
    a fresh contract starts, the org becomes human-run. The caller (web
    lobby / CLI) must rebind its own session team mapping afterwards."""
    offers = gs.career_offers_by.get(mid) or []
    offer = next((o for o in offers if o.team_id == team_id), None)
    if offer is None:
        return False, "that org is not offering you the job"
    if gs.is_human(team_id):
        return False, "another manager already runs that org"
    seat = gs.managers[mid]
    seat.team_id = team_id
    seat.archetype = offer.archetype
    # Org memory: a boardroom you won with starts warmer, one that fired
    # you before starts colder (manager/memories.py).
    from esports_sim.manager import memories

    posture = memories.board_posture(gs, mid, team_id)
    seat.contract = ManagerContract(
        start_season=gs.season, seasons=offer.seasons,
        goal=offer.goal,
        patience=float(np.clip(offer.patience + posture, 10.0, 100.0)),
    )
    gs.human_team_ids.append(team_id)
    del gs.career_offers_by[mid]
    # The primary manager's back-compat pointer follows them.
    if mid == seat_id_for(gs.user_team_id) or gs.user_team_id not in gs.human_team_ids:
        gs.user_team_id = team_id
    team = gs.teams[team_id]
    gs.push_private_news(
        f"You take over at {team.name} ({offer.archetype.replace('_', ' ')}; "
        f"goal: {GOAL_LABELS.get(offer.goal, offer.goal)}).",
        owner=team_id,
    )
    chronicle.record(
        gs, "appointment",
        f"{seat.name} takes over at {team.name}.",
        team_id=team_id,
        manager_id=mid,
        data={"archetype": offer.archetype},
    )
    return True, f"appointed at {team.name}"


def blocked_seats(gs: GameState) -> list[str]:
    """Manager seat ids that must accept a job before the world advances."""
    return sorted(mid for mid, offers in gs.career_offers_by.items() if offers)


def weekly_patience(gs: GameState) -> list[str]:
    """In-season patience drift off result streaks, plus the deep-floor
    mid-season sacking. Returns seat ids dismissed mid-season."""
    if gs.game_mode != "legacy":
        return []
    dismissed: list[str] = []
    for mid in sorted(gs.managers):
        seat = gs.managers[mid]
        if not seat.team_id or seat.contract is None:
            continue
        tid = seat.team_id
        played = sorted(
            (
                f
                for f in gs.fixtures
                if f.played
                and f.stage == "regular"
                and f.id.startswith(f"s{gs.season}")
                and tid in (f.team_a, f.team_b)
            ),
            key=lambda f: (f.week, f.id),
        )
        # Patience only moves on a NEW qualifying result: without this,
        # a split-ending loss streak would be re-penalized every playoff
        # week the team doesn't even play.
        if not played or played[-1].week != gs.week:
            continue
        streak_w = streak_l = 0
        for f in reversed(played):
            if f.winner_id == tid and streak_l == 0:
                streak_w += 1
            elif f.winner_id != tid and streak_w == 0:
                streak_l += 1
            else:
                break
        c = seat.contract
        if streak_l >= LOSS_STREAK_LEN:
            c.patience = float(np.clip(c.patience + PATIENCE_LOSS_STREAK, 0.0, 100.0))
            if c.patience <= MIDSEASON_FLOOR:
                dismissed.append(mid)
                gs.push_private_news(
                    f"{gs.teams[tid].name} sack you mid-season after a "
                    f"{streak_l}-game slide.",
                    owner=tid,
                )
                chronicle.record(
                    gs, "dismissal",
                    f"{seat.name} sacked mid-season by {gs.teams[tid].name}.",
                    team_id=tid,
                    manager_id=mid,
                )
        elif streak_w >= WIN_STREAK_LEN:
            c.patience = float(np.clip(c.patience + PATIENCE_WIN_STREAK, 0.0, 100.0))
    return dismissed


# -- reputation (derived from the chronicle, never stored) --------------------


def reputation(gs: GameState, mid: str) -> dict[str, float]:
    """The GDD reputation axes, 0-100 (50 = an unknown quantity), derived
    from this seat's chronicle with recency weighting (each season back
    counts ~15% less). Historical behavior, not XP.

    Honest bases today: development (milestones/debuts on their watch),
    culture (renewals vs releases), domestic/international success
    (titles), pressure (titles per season in charge). `tactical
    innovation` and `analytics` sit at neutral until later phases give
    them chronicle sources (meta shifts, department work) — documented,
    not hidden."""
    mine = [e for e in gs.chronicle if e.manager_id == mid]

    def w(e) -> float:
        return 0.85 ** max(0, gs.season - e.season)

    def total(kinds: set[str]) -> float:
        return sum(w(e) for e in mine if e.kind in kinds)

    dev = total({"milestone", "debut"})
    renewals = total({"renewal"})
    releases = total({"release"})
    regional = total({"regional_title"})
    intl = total({"masters_title", "champions_title"})
    seasons_managed = max(
        1.0,
        gs.season
        - min((e.season for e in mine if e.kind == "appointment"), default=gs.season)
        + 1.0,
    )

    def scale(x: float, per: float) -> float:
        return float(np.clip(50.0 + x * per, 0.0, 100.0))

    return {
        "player_development": scale(dev, 4.0),
        "tactical_innovation": scale(total({"meta_shift"}), 8.0),
        "team_culture": scale(renewals - releases, 5.0),
        "analytics": 50.0,  # chronicle source arrives with phase 4
        "international_success": scale(intl, 12.0),
        "domestic_success": scale(regional, 8.0),
        "pressure_handling": scale(
            (regional + intl) / seasons_managed * 2.0, 8.0
        ),
    }


# -- philosophy (earned labels, not a menu) -----------------------------------

PHILOSOPHY_DEFS = {
    "trust_rookies": "Trusts Rookies - debuts handed out season after season",
    "development_school": "A Development School - players grow here",
    "loyalty_first": "Loyalty First - re-signs their own before shopping",
    "ruthless": "Ruthless - the roster is a machine, parts get replaced",
    "big_match": "Big-Match Manager - wins the ones that count",
    "heavy_analytics": "Heavy Analytics - a data-first backroom",
}


def philosophies(gs: GameState, mid: str) -> list[str]:
    """A manager's philosophical identity — EARNED from repeated observed
    behavior in the chronicle (the GDD's rule: identities come from what
    you did, not from a picker). Returns PHILOSOPHY_DEFS keys."""
    mine = [e for e in gs.chronicle if e.manager_id == mid]

    def n(kind: str) -> int:
        return sum(1 for e in mine if e.kind == kind)

    out: list[str] = []
    if n("debut") >= 3:
        out.append("trust_rookies")
    if n("milestone") >= 6:
        out.append("development_school")
    renewals, releases = n("renewal"), n("release")
    if renewals >= 6 and renewals > releases * 2:
        out.append("loyalty_first")
    if releases >= renewals + 4:
        out.append("ruthless")
    titles = sum(
        1
        for e in mine
        if e.kind in ("regional_title", "masters_title", "champions_title")
    )
    if titles >= 2:
        out.append("big_match")
    seat = gs.managers.get(mid)
    if seat is not None and seat.team_id:
        # Read the department directly off the per-team maps — never
        # touch the acting pointer from inside a read helper.
        analyst = gs.staff_by.get(seat.team_id, {}).get("analyst")
        score = (analyst.quality if analyst else 0.0) + 15.0 * gs.facilities_by.get(
            seat.team_id, {}
        ).get("analytics_suite", 0)
        if score >= 55.0:
            out.append("heavy_analytics")
    return out


def philosophy_training_mult(gs: GameState, tid: str) -> float:
    """A Development School's roster grows a shade faster — the one
    philosophy with a mechanical effect (small, multiplicative, human
    orgs only since only they have manager seats with history)."""
    seat = gs.manager_for(tid)
    if seat is None:
        return 1.0
    return 1.05 if "development_school" in philosophies(gs, seat.id) else 1.0


def known_for(gs: GameState, mid: str) -> list[str]:
    """Short 'Known For' lines off the strongest reputation axes —
    generated from actual history, silence when there's none yet."""
    rep = reputation(gs, mid)
    lines: list[str] = []
    if rep["international_success"] >= 65:
        lines.append("International success")
    if rep["domestic_success"] >= 65:
        lines.append("A winner at home")
    if rep["player_development"] >= 65:
        lines.append("Developing young talent")
    if rep["team_culture"] >= 62:
        lines.append("Building loyal squads")
    if rep["team_culture"] <= 38:
        lines.append("A ruthless roster hand")
    if rep["pressure_handling"] >= 62:
        lines.append("Big-match temperament")
    return lines[:3]


def career_summary(gs: GameState, mid: str) -> dict:
    """The career-profile payload: counts, reputation, known-for, and a
    landmark timeline — all pure chronicle reads."""
    seat = gs.managers.get(mid)
    mine = [e for e in gs.chronicle if e.manager_id == mid]
    titles = [
        e
        for e in mine
        if e.kind in ("regional_title", "masters_title", "champions_title")
    ]
    return {
        "id": mid,
        "name": seat.name if seat else mid,
        "team_id": seat.team_id if seat else "",
        "archetype": seat.archetype if seat else "",
        "contract": (
            {
                "seasons": seat.contract.seasons,
                "start_season": seat.contract.start_season,
                "goal": GOAL_LABELS.get(seat.contract.goal, seat.contract.goal),
                "patience": round(seat.contract.patience, 1),
            }
            if seat and seat.contract
            else None
        ),
        "titles": [e.data.get("title", e.text) for e in titles],
        "players_developed": sum(1 for e in mine if e.kind == "milestone"),
        "debuts_given": sum(1 for e in mine if e.kind == "debut"),
        "signings": sum(1 for e in mine if e.kind == "signing"),
        "reputation": {k: round(v, 1) for k, v in reputation(gs, mid).items()},
        "known_for": known_for(gs, mid),
        "philosophies": [
            PHILOSOPHY_DEFS[k] for k in philosophies(gs, mid)
        ],
        "timeline": [
            {
                "season": e.season,
                "week": e.week,
                "kind": e.kind,
                "text": e.text,
            }
            for e in mine
            if e.importance >= 40.0
        ][-24:],
    }


def dismissal_inbox_item(gs: GameState, mid: str, season: int, week: int) -> InboxItem:
    """The 'you've been let go' inbox item, delivered to the seat's OLD
    inbox so the story is readable after the rebind."""
    import hashlib as _h

    seat = gs.managers[mid]
    offers = gs.career_offers_by.get(mid) or []
    names = ", ".join(gs.teams[o.team_id].name for o in offers)
    body = (
        "The board has relieved you of your duties.\n"
        f"Offers on the table: {names if names else 'none yet'}.\n"
        "Pick your next project from the dashboard to continue."
    )
    iid = _h.blake2b(
        f"{season}|{week}|dismissal|{mid}".encode(), digest_size=8
    ).hexdigest()
    return InboxItem(
        id=iid, season=season, week=week, category="board",
        title="Dismissed - choose your next club", body=body, tab=None,
    )
