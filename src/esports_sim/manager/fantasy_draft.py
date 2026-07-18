"""Fantasy-draft campaign start.

Instead of inheriting authored rosters, every tier-1 org — human and AI —
builds its squad live: all tier-1 pros plus the free-agent pool (topped up
with a generated draft class so every org can make ROUNDS picks and the
last picks still have real choice) enter one shared pool, and orgs pick in
snake order until each holds a ten-man squad (five starters plus
bench/academy depth). Tier-2 Challengers rosters are untouched — they stay
the development circuit the academy layer runs on.

Determinism: the draft class and the pick order come off the campaign gen
rng at creation; from then on AI picks are a pure function of the board
state (value function + blake2 tie-jitter, no rng stream), so the seed
plus the human picks recorded in `action_log` fully determine the final
league. AI parity: AI orgs draft with the SAME value function the human
recommendation panel uses — their strategy lean is blake2-derived per org.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from esports_sim.manager import development, market
from esports_sim.manager.gen import _FA_SLOTS, generate_player
from esports_sim.manager.state import DraftPick, DraftPrefs, FantasyDraftState
from esports_sim.rng.tree import RngTree
from esports_sim.schemas.common import Playstyle

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState
    from esports_sim.registry import GameData

ROUNDS = 10
# Leftover pool depth beyond n_teams * ROUNDS, so round 10 is still a
# choice between prospects rather than a forced take-what's-left.
POOL_SURPLUS = 25

STRATEGIES = ("balanced", "win_now", "youth")
# (current-ability weight, upside weight) per strategy.
_STRATEGY_WEIGHTS = {
    "balanced": (1.0, 0.9),
    "win_now": (1.25, 0.45),
    "youth": (0.8, 1.5),
}


def _h(*parts: object) -> int:
    """Stable 64-bit hash of the joined parts (never builtin hash())."""
    joined = "|".join(str(p) for p in parts)
    return int.from_bytes(
        hashlib.blake2b(joined.encode(), digest_size=8).digest(), "big"
    )


# ---------------------------------------------------------------------------
# Creation (called from campaign.new_campaign)


def draft_class_size(n_teams: int, existing_pool: int) -> int:
    """How many extra prospects to generate on top of the stripped rosters
    and free agents so the pool covers every pick with surplus."""
    return max(0, n_teams * ROUNDS + POOL_SURPLUS - existing_pool)


def generate_draft_class(rng, gd: "GameData", regions, n: int) -> list:
    """Generate the top-up draft class: a few blue-chips, a solid middle,
    and a long tail of teenage projects whose PA outruns their CA. Ids are
    `draftee_{i}` (never collides with fa_/team slugs). Spread round-robin
    across the world's regions so languages and countries vary."""
    out = []
    regions = list(regions)
    for i in range(n):
        style, role = _FA_SLOTS[i % len(_FA_SLOTS)]
        region = regions[i % len(regions)]
        roll = rng.random()
        if roll < 0.12:
            quality = rng.uniform(66, 80)  # blue-chip
            age_lo, age_hi = 18, 26
        elif roll < 0.50:
            quality = rng.uniform(52, 66)  # solid starter material
            age_lo, age_hi = 18, 28
        else:
            quality = rng.uniform(38, 54)  # teenage project
            age_lo, age_hi = 17, 21
        p = generate_player(
            rng, f"draftee_{i}", style, role, float(quality), gd,
            region=region, age_lo=age_lo, age_hi=age_hi,
        )
        p.contract_weeks_left = 0
        out.append(p)
    return out


def setup(gs: "GameState", rng, extra_ids: list[str]) -> None:
    """Strip every tier-1 roster into the shared pool and stage the draft.
    Runs inside new_campaign, right after GameState construction: the
    downstream seeding cascade already no-ops safely on empty rosters
    (contracts, leadership, AI tactics), and `_complete` re-runs those
    passes once the drafted squads exist."""
    pool: set[str] = set(extra_ids)
    tier1 = sorted(tid for tid, t in gs.teams.items() if t.tier == 1)
    for tid in tier1:
        team = gs.teams[tid]
        pool.update(team.player_ids)
        team.player_ids = []
        team.lineup_ids = []
        team.captain_id = None
    pool.update(gs.free_agent_ids)
    gs.free_agent_ids = []
    for pid in sorted(pool):
        p = gs.players[pid]
        p.contract_weeks_left = 0
        p.tenure_weeks = 0
        p.roster_role = "bench"
    order = [tier1[int(i)] for i in rng.permutation(len(tier1))]
    gs.fantasy_draft = FantasyDraftState(
        order=order, pool_ids=sorted(pool), rounds=ROUNDS
    )


def begin(gs: "GameState") -> None:
    """Open the board (host action in shared worlds; automatic for solo)
    and resolve AI picks up to the first human turn."""
    d = gs.fantasy_draft
    if d is None or not d.active or d.started:
        return
    d.started = True
    run_ai(gs)


# ---------------------------------------------------------------------------
# Turn order


def total_picks(d: FantasyDraftState) -> int:
    return d.rounds * len(d.order)


def pick_team(d: FantasyDraftState, overall: int) -> str:
    """Snake order: odd rounds run the order forward, even rounds reverse."""
    n = len(d.order)
    rnd, idx = divmod(overall, n)
    return d.order[idx] if rnd % 2 == 0 else d.order[n - 1 - idx]


def on_clock(d: FantasyDraftState | None) -> str | None:
    """The team whose pick it is, or None (not started / complete)."""
    if d is None or not d.active or not d.started:
        return None
    overall = len(d.picks)
    if overall >= total_picks(d):
        return None
    return pick_team(d, overall)


# ---------------------------------------------------------------------------
# Preferences + the shared value function


def prefs_for(gs: "GameState", team_id: str) -> DraftPrefs:
    """This org's draft preferences. Humans start balanced and may change
    them; AI orgs get a stable blake2-derived lean so every seed rebuilds
    the same league of drafters."""
    d = gs.fantasy_draft
    if d is not None and team_id in d.prefs_by:
        return d.prefs_by[team_id]
    if gs.is_human(team_id):
        return DraftPrefs()
    lean = _h(gs.seed, team_id, "draft-strategy") % 10
    strategy = "win_now" if lean < 3 else ("youth" if lean >= 7 else "balanced")
    return DraftPrefs(
        strategy=strategy,
        language_focus=_h(gs.seed, team_id, "draft-lang") % 4 != 0,
    )


def _age_upside_factor(age: int) -> float:
    """How much of the CA-to-PA gap a drafter can realistically still bank:
    all of it at 19, tapering to a floor for veterans."""
    return max(0.15, min(1.0, (27 - age) / 8.0))


def _shared_language_score(p, squad) -> float:
    """0..1: the best fraction of the picked squad that shares one of this
    player's working languages (fluency >= 40 counts as working)."""
    if not squad:
        return 0.0
    best = 0.0
    for skill in p.languages:
        if skill.level < 40:
            continue
        speakers = sum(
            1
            for q in squad
            if any(s.lang == skill.lang and s.level >= 40 for s in q.languages)
        )
        best = max(best, speakers / len(squad))
    return best


def draft_value(
    gs: "GameState", team_id: str, p, prefs: DraftPrefs,
    picked_ids: list[str],
) -> tuple[float, list[str]]:
    """Score one available player for one org's board state. Returns
    (score, reasons) — the reasons feed the human recommendation panel;
    AI orgs rank by the same score. Pure function of arguments (plus the
    save's stable ids), no rng stream."""
    q = market.player_quality(p)
    pot = development.potential_of(p)
    upside = max(0.0, pot - q) * _age_upside_factor(p.age)
    w_now, w_up = _STRATEGY_WEIGHTS[prefs.strategy]
    score = q * w_now + upside * w_up
    reasons: list[str] = []

    picked = [gs.players[pid] for pid in picked_ids]
    roles = [str(pl.role) for pl in picked]
    if len(picked) < market.ROSTER_SIZE:
        # First five picks are the starting lineup: cover the five roles.
        if str(p.role) not in roles:
            score += 6.0
            reasons.append(f"fills your open {p.role} slot")
        else:
            score -= 4.0
        if p.playstyle == Playstyle.IGL and not any(
            pl.playstyle == Playstyle.IGL for pl in picked
        ):
            score += 5.0
            reasons.append("your five still needs a caller")
    else:
        # Depth picks: back up roles you only hold one of.
        if roles.count(str(p.role)) <= 1:
            score += 2.0
            reasons.append(f"adds depth at {p.role}")

    if picked and prefs.language_focus:
        shared = _shared_language_score(p, picked)
        score += (shared - 0.5) * 8.0
        if shared >= 0.6:
            reasons.append("shares a comms language with your squad")
        elif shared <= 0.1:
            reasons.append("no working language in common yet")

    if upside >= 12:
        reasons.append(f"big ceiling for a {p.age}-year-old")
    elif q >= 70:
        reasons.append("proven top-flight ability")
    return score, reasons


def recommendations(gs: "GameState", team_id: str, limit: int = 5) -> list[dict]:
    """Top available fits for this org right now, by the shared value
    function under the org's current prefs. Deterministic ordering."""
    d = gs.fantasy_draft
    if d is None:
        return []
    prefs = prefs_for(gs, team_id)
    picked = [pk.player_id for pk in d.picks if pk.team_id == team_id]
    scored = []
    for pid in d.pool_ids:
        score, reasons = draft_value(gs, team_id, gs.players[pid], prefs, picked)
        scored.append((-score, pid, reasons))
    scored.sort()
    return [
        {"player_id": pid, "score": round(-neg, 1), "reasons": reasons[:3]}
        for neg, pid, reasons in scored[:limit]
    ]


# ---------------------------------------------------------------------------
# Picking


def make_pick(gs: "GameState", team_id: str, player_id: str) -> DraftPick:
    """Resolve one selection. Raises ValueError on an illegal pick (the web
    layer maps those to 409/422). Completes the draft on the final pick."""
    d = gs.fantasy_draft
    if d is None or not d.active:
        raise ValueError("no draft in progress")
    if not d.started:
        raise ValueError("the draft has not started")
    turn = on_clock(d)
    if turn != team_id:
        raise ValueError("not on the clock")
    if player_id not in d.pool_ids:
        raise ValueError("player not in the draft pool")
    overall = len(d.picks)
    pick = DraftPick(
        overall=overall,
        round=overall // len(d.order) + 1,
        team_id=team_id,
        player_id=player_id,
    )
    d.pool_ids.remove(player_id)
    d.picks.append(pick)
    team = gs.teams[team_id]
    team.player_ids.append(player_id)
    p = gs.players[player_id]
    p.tenure_weeks = 0
    if team.captain_id is None:
        team.captain_id = player_id
    if len(d.picks) >= total_picks(d):
        _complete(gs)
    return pick


def ai_pick(gs: "GameState", team_id: str) -> DraftPick:
    """One AI selection: best score under the org's derived prefs, plus a
    small blake2 jitter keyed on the pick number so two same-archetype orgs
    don't mirror each other board-for-board."""
    d = gs.fantasy_draft
    prefs = prefs_for(gs, team_id)
    picked = [pk.player_id for pk in d.picks if pk.team_id == team_id]
    overall = len(d.picks)
    best_pid, best_score = None, None
    for pid in d.pool_ids:
        score, _ = draft_value(gs, team_id, gs.players[pid], prefs, picked)
        score += (_h(gs.seed, "draft-jitter", team_id, pid, overall) % 1000) / 1000.0 * 3.0
        # Deterministic tie-break: higher score, then lower pid.
        if best_score is None or score > best_score or (
            score == best_score and pid < best_pid
        ):
            best_pid, best_score = pid, score
    return make_pick(gs, team_id, best_pid)


def run_ai(gs: "GameState") -> int:
    """Resolve AI turns until a human is on the clock or the draft ends.
    Returns how many picks resolved."""
    d = gs.fantasy_draft
    n = 0
    while d is not None and d.active:
        turn = on_clock(d)
        if turn is None or gs.is_human(turn):
            break
        ai_pick(gs, turn)
        n += 1
    return n


# ---------------------------------------------------------------------------
# Completion


def _complete(gs: "GameState") -> None:
    """Settle the drafted world: leftovers become free agents, each squad
    gets a lineup/captain/roles/contracts, and the seeding passes that
    no-oped on empty rosters at creation run for real. After this the
    campaign ticks exactly like a classic start."""
    from esports_sim.manager import campaign, culture

    d = gs.fantasy_draft
    d.active = False
    gs.free_agent_ids = sorted(d.pool_ids)
    d.pool_ids = []
    for pid in gs.free_agent_ids:
        gs.players[pid].contract_weeks_left = 0

    for tid in sorted(d.order):
        team = gs.teams[tid]
        ordered = sorted(
            team.player_ids,
            key=lambda q: (-market.player_quality(gs.players[q]), q),
        )
        team.lineup_ids = ordered[: market.ROSTER_SIZE]
        starters = set(team.lineup_ids)
        for pid in team.player_ids:
            p = gs.players[pid]
            role = (
                "starter" if pid in starters
                else "academy" if p.age <= 20
                else "bench"
            )
            p.salary = market.asking_salary(p)
            # Stagger opening contract lengths per player (blake2, no rng)
            # so the whole league doesn't hit free agency the same week.
            p.contract_weeks_left = 30 + _h(pid, "draft-contract") % 50
            market.seed_existing_contract_terms(gs, tid, p, role)

    culture.ensure_leadership(gs)
    rng = RngTree(gs.seed).derive("campaign", "fantasy_draft", "settle")
    campaign._assign_ai_tactics(gs, rng)
    campaign._update_world_ranks(gs)
    campaign._record_dev_snapshots(gs, week=0)
    gs.push_news(
        "Fantasy draft complete — every org built its squad from one shared "
        "pool. Season 1 begins."
    )
