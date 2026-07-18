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
from esports_sim.manager.state import (
    DraftDeal,
    DraftPick,
    DraftPrefs,
    FantasyDraftState,
)
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
# The pre-draft interview. Server-owned copy: the client renders whatever
# arrives, so tone lives here in one place. Realistic-ish questions with a
# streak of gamer-culture meme — the ANSWERS have real teeth (they seed
# DraftPrefs and pick the four org offers), the jokes are free.

# identity -> (strategy, style-lane reason shown on fitting recommendations)
_IDENTITY_META = {
    "ring_hunter": ("win_now", "a proven piece for the trophy push"),
    "prodigy_whisperer": ("youth", "raw clay for the prodigy pipeline"),
    "moneyball": ("balanced", "market inefficiency, corrected"),
}
_STYLE_META = {
    # answer -> (preferred playstyles, attribute focus, fit reason)
    "w_key": (
        ["entry", "awper"],
        ["aim_reactivity", "aim_precision"],
        "presses W like you preach",
    ),
    "big_brain": (
        ["igl", "support"],
        ["game_sense", "utility_usage"],
        "plays the 200-IQ default you believe in",
    ),
    "clutch_or_kick": (
        ["lurker", "anchor"],
        ["clutch_factor", "composure"],
        "ice in the veins, like you demand",
    ),
}
_REGION_SUBTITLES = {
    "americas": "Server: Texas. Ping: spicy. Belief: unlimited.",
    "emea": "Tactics, tea, and a 12-man util lineup for A site.",
    "pacific": "Aim gods, 40-bomb culture, scrims at 3am.",
    "china": "Discipline, firepower, and total mystery scrims.",
}


def interview_questions(regions) -> list[dict]:
    """The interview, in order. `regions` is the world's league regions so
    the home-region question matches the pack being started."""
    region_opts = [
        {
            "id": str(r),
            "label": str(r).upper(),
            "blurb": _REGION_SUBTITLES.get(
                str(r), "Home is where the LAN is."
            ),
        }
        for r in regions
    ]
    region_opts.append(
        {
            "id": "anywhere",
            "label": "Wherever wins",
            "blurb": "Passport ready. Loyalty is for fans; I have a job to do.",
        }
    )
    return [
        {
            "id": "identity",
            "prompt": "So. Why do you want this job?",
            "options": [
                {
                    "id": "ring_hunter",
                    "label": "Ring hunting",
                    "blurb": (
                        "I want a trophy before the meta shifts again. "
                        "Vets, firepower, zero rebuild talk."
                    ),
                },
                {
                    "id": "prodigy_whisperer",
                    "label": "The prodigy whisperer",
                    "blurb": (
                        "Give me five cracked teenagers and a bootcamp. "
                        "We lose now so we win forever."
                    ),
                },
                {
                    "id": "moneyball",
                    "label": "Moneyball, but for headshots",
                    "blurb": (
                        "Value picks, no egos, spreadsheets. The market is "
                        "inefficient and I am the correction."
                    ),
                },
            ],
        },
        {
            "id": "style",
            "prompt": "How should the game actually be played?",
            "options": [
                {
                    "id": "w_key",
                    "label": "W-key diplomacy",
                    "blurb": (
                        "First contact wins games. My five hit the site "
                        "before the defenders finish buying."
                    ),
                },
                {
                    "id": "big_brain",
                    "label": "The 200-IQ default",
                    "blurb": (
                        "Structure, mid-round calls, util for everything. "
                        "Aim is a commodity; brains are the edge."
                    ),
                },
                {
                    "id": "clutch_or_kick",
                    "label": "Clutch or kick",
                    "blurb": (
                        "Rounds are won 1v2 at 0:08 on a lurk timing. "
                        "I collect players the enemy fears after the trade."
                    ),
                },
            ],
        },
        {
            "id": "region",
            "prompt": "Where's home?",
            "options": region_opts,
        },
        {
            "id": "comms",
            "prompt": "Comms philosophy?",
            "options": [
                {
                    "id": "one_language",
                    "label": "One language, full sentences",
                    "blurb": (
                        "Five people, one tongue, callouts like poetry. "
                        "No 'he's... somewhere' on my watch."
                    ),
                },
                {
                    "id": "vibes",
                    "label": "Broken English and vibes",
                    "blurb": (
                        "International mercenaries. If the crosshair "
                        "placement is right, 'rush B' is a full sentence."
                    ),
                },
            ],
        },
        {
            "id": "org_life",
            "prompt": "Pick your poison on org life:",
            "options": [
                {
                    "id": "big_org",
                    "label": "Big org, big expectations",
                    "blurb": (
                        "Content team, chef, and an owner who tweets "
                        "through losses. The money is real, so is the heat."
                    ),
                },
                {
                    "id": "basement",
                    "label": "Basement org, full control",
                    "blurb": (
                        "Two sponsors, one of them is an energy drink you've "
                        "never heard of. But every decision is mine."
                    ),
                },
                {
                    "id": "content_house",
                    "label": "The content house",
                    "blurb": (
                        "Fans first, fragging second-ish. We might lose the "
                        "split but we will WIN the clip farm."
                    ),
                },
            ],
        },
    ]


def _answer(answers: dict, qid: str, valid: set[str], default: str) -> str:
    got = str((answers or {}).get(qid, ""))
    return got if got in valid else default


def prefs_from_answers(answers: dict, regions) -> DraftPrefs:
    """Fold the interview into concrete board preferences. Unknown or
    missing answers fall back to neutral, so a hand-rolled API call can't
    crash the lobby."""
    identity = _answer(answers, "identity", set(_IDENTITY_META), "moneyball")
    style = _answer(answers, "style", set(_STYLE_META), "big_brain")
    region = _answer(
        answers, "region", {str(r) for r in regions} | {"anywhere"}, "anywhere"
    )
    comms = _answer(answers, "comms", {"one_language", "vibes"}, "one_language")
    org = _answer(
        answers, "org_life",
        {"big_org", "basement", "content_house"}, "basement",
    )
    styles, attrs, _reason = _STYLE_META[style]
    return DraftPrefs(
        strategy=_IDENTITY_META[identity][0],
        language_focus=comms == "one_language",
        identity=identity,
        preferred_styles=list(styles),
        attr_focus=list(attrs),
        preferred_region="" if region == "anywhere" else region,
        answers={
            "identity": identity, "style": style, "region": region,
            "comms": comms, "org_life": org,
        },
    )


def interview_offers(
    teams: dict, seed: int, answers: dict, taken: set[str], regions
) -> list[dict]:
    """Four contrasting org offers derived from the interview: the best
    answer-fit org, the richest, the lowest-rep rebuild, and a blake2
    wildcard. Pure function of (teams, seed, answers, taken) — no rng
    stream — so the lobby can re-derive and the create call can enforce
    membership, exactly like legacy career offers."""
    prefs = prefs_from_answers(answers, regions)
    avail = {
        tid: t for tid, t in teams.items()
        if t.tier == 1 and tid not in taken
    }
    if not avail:
        return []
    offers: list[dict] = []
    used: set[str] = set()

    def fit_score(tid: str) -> float:
        t = avail[tid]
        s = 0.0
        if prefs.preferred_region and str(t.region) == prefs.preferred_region:
            s += 100.0
        org = prefs.answers.get("org_life", "basement")
        if org == "big_org":
            s += t.balance / 20_000 + t.reputation * 0.5
        elif org == "content_house":
            s += t.fan_count / 20_000
        else:
            s += (100 - t.reputation) * 0.5  # scrappy fits the basement
        s += (_h(seed, "offer-fit", tid) % 100) / 100.0
        return s

    def take(tid: str, deal: DraftDeal) -> None:
        t = avail[tid]
        used.add(tid)
        offers.append(
            {
                "team_id": tid,
                "name": t.name,
                "tag": t.tag,
                "region": str(t.region),
                "reputation": t.reputation,
                "balance": t.balance,
                "archetype": deal.archetype,
                "label": deal.label,
                "goal": deal.goal,
                "blurb": deal.blurb,
                "balance_bonus": deal.balance_bonus,
            }
        )

    def best(key, exclude_used=True):
        pool = [tid for tid in sorted(avail) if tid not in used or not exclude_used]
        return max(pool, key=lambda tid: (key(tid), tid)) if pool else None

    # 1. The Believer — the org that read your interview and loved it.
    believer = best(fit_score)
    if believer is not None:
        take(
            believer,
            DraftDeal(
                archetype="believer",
                label="The Believer",
                goal="Run YOUR blueprint — build the identity you pitched "
                     "and make the playoffs with it.",
                blurb="The owner quoted your interview back at you. "
                      "Slightly concerning. Full buy-in though.",
                balance_bonus=150_000,
            ),
        )
    # 2. The Blank Check — the richest org still listening.
    rich = best(lambda tid: avail[tid].balance)
    if rich is not None:
        take(
            rich,
            DraftDeal(
                archetype="blank_check",
                label="The Blank Check",
                goal="Trophy THIS season, or the owner starts tweeting.",
                blurb="Facilities, chef, content team, a war chest — and "
                      "a fanbase that files a complaint per round loss.",
                balance_bonus=0,
            ),
        )
    # 3. The Project — the lowest-rep rebuild with real patience.
    project = best(lambda tid: -avail[tid].reputation)
    if project is not None:
        take(
            project,
            DraftDeal(
                archetype="project",
                label="The Project",
                goal="Nobody expects anything. Make them regret that "
                     "within two seasons.",
                blurb="The owner sold the office couch to fund your "
                      "signing budget. There is no office. There is a budget.",
                balance_bonus=400_000,
            ),
        )
    # 4. The Wildcard — a blake2 spin, with the owner's personal beef.
    rest = [tid for tid in sorted(avail) if tid not in used]
    if rest:
        wild = rest[_h(seed, "offer-wild", *sorted(answers.items())) % len(rest)]
        rival_pool = [t for t in sorted(teams) if t != wild and teams[t].tier == 1]
        rival = teams[
            rival_pool[_h(seed, "offer-rival", wild) % len(rival_pool)]
        ].name
        take(
            wild,
            DraftDeal(
                archetype="wildcard",
                label="The Wildcard",
                goal=f"Beat {rival} twice this season. The owner lost a "
                     "bet and will not elaborate.",
                blurb="Mid table, mid budget, immaculate vibes. The team "
                      "dog has more followers than the roster.",
                balance_bonus=100_000,
            ),
        )
    return offers


def apply_interview(
    gs: "GameState", team_id: str, answers: dict, taken: set[str] | None = None
) -> None:
    """Land an accepted interview on the world: board prefs for the rec
    panel, the deal's flavor + war-chest bonus on the org. Deterministic
    given (gs, team_id, answers, taken) — the web layer records the
    answers in action_log, so a replay re-applies the same deal. `taken`
    must match what the offers endpoint excluded when the manager chose
    (other humans' orgs), so the accepted card resolves identically."""
    d = gs.fantasy_draft
    if d is None:
        return
    prefs = prefs_from_answers(answers, gs.league_regions)
    d.prefs_by[team_id] = prefs
    offers = interview_offers(
        gs.teams, gs.seed, answers,
        taken=set(taken or ()) - {team_id}, regions=gs.league_regions,
    )
    offer = next((o for o in offers if o["team_id"] == team_id), None)
    if offer is None:
        # The picked org wasn't in this slate (host raced a joiner, or a
        # hand-rolled call). Prefs still apply; no deal, no bonus.
        return
    deal = DraftDeal(
        archetype=offer["archetype"],
        label=offer["label"],
        goal=offer["goal"],
        blurb=offer["blurb"],
        balance_bonus=offer["balance_bonus"],
    )
    d.deals_by[team_id] = deal
    if deal.balance_bonus:
        gs.teams[team_id].balance += deal.balance_bonus
    gs.push_news(
        f"{gs.teams[team_id].name} hand their new manager the keys: "
        f"\"{deal.goal}\""
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

    # Interview-derived style identity. These fields stay empty for AI
    # orgs and pre-interview prefs, so the base function is untouched
    # there — the style lane is a purely human flavor of the same math.
    if prefs.preferred_styles and str(p.playstyle) in prefs.preferred_styles:
        score += 5.0
        style = prefs.answers.get("style", "")
        if style in _STYLE_META:
            reasons.append(_STYLE_META[style][2])
    if prefs.attr_focus:
        edge = (
            sum(p.attr(a) for a in prefs.attr_focus) / len(prefs.attr_focus)
            - q
        )
        score += max(0.0, edge) * 0.4
        if edge >= 6.0:
            reasons.append("elite at exactly what you value")
    if prefs.preferred_region and str(p.region) == prefs.preferred_region:
        score += 2.0
        reasons.append("homegrown for your region")

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


def best_available(gs: "GameState", limit: int = 3) -> list[dict]:
    """The no-opinions board: pure talent (current ability + age-realizable
    upside at balanced weights), ignoring roles, comms, and the manager's
    interview. Shown NEXT TO the style lane so a manager always sees what
    the market thinks, not just what flatters their philosophy."""
    d = gs.fantasy_draft
    if d is None:
        return []
    scored = []
    for pid in d.pool_ids:
        p = gs.players[pid]
        q = market.player_quality(p)
        upside = max(0.0, development.potential_of(p) - q) * _age_upside_factor(p.age)
        scored.append((-(q + upside * 0.9), pid))
    scored.sort()
    return [
        {"player_id": pid, "score": round(-neg, 1)}
        for neg, pid in scored[:limit]
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
