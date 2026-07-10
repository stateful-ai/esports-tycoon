"""Backroom staff: coach, analyst, physio.

Each hired member scales one weekly system — coach boosts training growth
(more when the week's focus matches their specialty), analyst speeds
scouting AND unlocks deeper stat views (see analytics_tier), physio
restores stamina.

Hiring happens against ONE shared, world-level free-agent pool
(gs.staff_pool) — in a shared world managers compete for the same staff.
The pool is seeded 50+ deep at campaign start and churned every offseason
so the ecosystem stays healthy. Hiring is instant, releasing is free
(staff contracts are at-will in this economy). Human orgs only: AI teams'
staff stay abstract — their training/scouting multipliers assume a
league-average bench, which is the documented difficulty lever.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.gen import _FIRST_NAMES, _LAST_NAMES, _TEAM_NAMES
from esports_sim.manager.state import GameState, StaffMember
from esports_sim.rng.tree import RngTree

ROLES = ["coach", "analyst", "physio"]

# A healthy market: at least this many free agents at all times, roughly
# 40% coaches / 30% analysts / 30% physios.
POOL_MIN = 54
_POOL_ROLE_CYCLE = [
    "coach", "analyst", "physio", "coach", "analyst",
    "physio", "coach", "coach", "analyst", "physio",
]

ROLE_BLURB = {
    "coach": "training growth (extra on their specialty focus)",
    "analyst": "scouting speed + stat depth",
    "physio": "weekly stamina recovery",
}

SPECIALTIES: dict[str, list[str]] = {
    "coach": ["mechanical", "tactical", "mental", "team"],
    "analyst": ["opponents", "market", "data"],
    "physio": ["recovery", "longevity", "prevention"],
}

SPECIALTY_BLURB = {
    "mechanical": "aim-lab drills; extra growth on mechanical weeks",
    "tactical": "VOD-room general; extra growth on tactical weeks",
    "mental": "sports psychologist; extra growth on mental weeks",
    "team": "culture builder; extra growth on team weeks",
    "opponents": "opponent breakdowns",
    "market": "talent identification",
    "data": "deep statistical modelling",
    "recovery": "post-match recovery protocols",
    "longevity": "career-extension programs",
    "prevention": "wrist/posture injury prevention",
}

_TRAIT_POOL = [
    "players_coach", "disciplinarian", "innovator", "old_school",
    "networker", "quiet", "demanding", "developer", "grinder",
]

_AGE_RANGE = {"coach": (30, 56), "analyst": (23, 46), "physio": (26, 52)}
_REGIONS = ["americas", "emea", "pacific"]

# Extra ticks a coach's specialty adds when the week's focus matches it.
SPECIALTY_GROWTH_BONUS = 0.15


def _make_member(seed: int, sid: str, role: str) -> StaffMember:
    # Identity is a pure function of (campaign seed, member id): top-ups at
    # different times can never mint clones or shift each other's draws.
    rng = RngTree(seed).derive("staffgen", sid)
    quality = float(np.round(rng.uniform(42, 90), 1))
    name = f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
    salary = max(1_500, int(np.round((quality ** 1.5) * 8 / 100) * 100))
    lo, hi = _AGE_RANGE[role]
    age = int(rng.integers(lo, hi))
    specialty = str(rng.choice(SPECIALTIES[role]))
    n_traits = int(rng.integers(1, 3))
    traits = sorted(
        str(t) for t in rng.choice(_TRAIT_POOL, size=n_traits, replace=False)
    )
    # A paper trail proportional to age: journeymen arrive with history.
    seasons = max(0, int((age - lo) * 0.6 + rng.integers(0, 3)))
    history: list[str] = []
    n_stops = min(3, max(0, seasons // 3))
    for k in range(n_stops):
        org, _tag = _TEAM_NAMES[int(rng.integers(0, len(_TEAM_NAMES)))]
        years = int(rng.integers(1, 4))
        history.append(f"{years} season{'s' if years > 1 else ''} with {org}")
    return StaffMember(
        id=sid,
        name=name,
        role=role,
        quality=quality,
        salary=salary,
        age=age,
        region=str(rng.choice(_REGIONS)),
        specialty=specialty,
        traits=traits,
        history=history,
        seasons_experience=seasons,
    )


def seed_pool(gs: GameState) -> None:
    """Fill the shared staff market up to POOL_MIN. Deterministic — each
    member is a pure function of (campaign seed, member id) — and every id
    ever employed stays taken, so a hire can never be 'replaced' by a
    doppelganger holding the same id. Called at campaign start, at every
    offseason after churn, and lazily when the market runs thin."""
    taken = {m.id for m in gs.staff_pool}
    for staff in gs.staff_by.values():
        taken.update(m.id for m in staff.values())
    i = 0
    while len(gs.staff_pool) < POOL_MIN:
        sid = f"staff_s{gs.season}_{i}"
        role = _POOL_ROLE_CYCLE[i % len(_POOL_ROLE_CYCLE)]
        i += 1
        if sid in taken:
            continue
        taken.add(sid)
        gs.staff_pool.append(_make_member(gs.seed, sid, role))
    gs.staff_pool.sort(key=lambda m: m.id)


def offseason_churn(gs: GameState) -> None:
    """Careers move on over the break: everyone ages a year, the oldest
    pool members retire, hired staff bank a season of experience, then the
    pool refills to POOL_MIN with the new season's class."""
    rng = RngTree(gs.seed).derive("staffpool", gs.season, "churn")
    for m in gs.staff_pool:
        m.age += 1
    # Retirement: hard at 62+, increasingly likely from the late 50s.
    keep: list[StaffMember] = []
    for m in gs.staff_pool:
        p_retire = 1.0 if m.age >= 62 else max(0.0, (m.age - 55) * 0.12)
        if rng.random() >= p_retire:
            keep.append(m)
    gs.staff_pool = keep
    for staff in gs.staff_by.values():
        for m in staff.values():
            m.age += 1
            m.seasons_experience += 1
    seed_pool(gs)


def find_member(gs: GameState, staff_id: str) -> tuple[StaffMember | None, str | None]:
    """Locate a member anywhere: (member, employer_team_id | None). Pool
    members employ nobody; hired members name their org."""
    for m in gs.staff_pool:
        if m.id == staff_id:
            return m, None
    for tid in sorted(gs.staff_by):
        for m in gs.staff_by[tid].values():
            if m.id == staff_id:
                return m, tid
    return None, None


def hire(gs: GameState, staff_id: str) -> tuple[bool, str]:
    """The acting manager hires from the shared pool. The outgoing member
    in that role (if any) re-enters the market."""
    cand = next((m for m in gs.staff_pool if m.id == staff_id), None)
    if cand is None:
        return False, "that candidate is no longer on the market"
    team = gs.teams[gs.acting_team_id]
    if team.balance < cand.salary * 8:
        return False, f"need {cand.salary * 8:,} cr banked for the hire"
    old = gs.staff.get(cand.role)
    gs.staff[cand.role] = cand
    gs.staff_pool.remove(cand)
    cand.history.append(f"S{gs.season}: {cand.role}, {team.name}")
    if old is not None:
        gs.staff_pool.append(old)
        gs.staff_pool.sort(key=lambda m: m.id)
    gs.push_news(
        f"{team.name} bring in {cand.name} ({cand.role}, {cand.salary:,}/wk)."
    )
    return True, f"hired {cand.name} as {cand.role}"


def release(gs: GameState, role: str) -> tuple[bool, str]:
    member = gs.staff.pop(role, None)
    if member is None:
        return False, f"no {role} on staff"
    gs.staff_pool.append(member)
    gs.staff_pool.sort(key=lambda m: m.id)
    gs.push_news(f"{member.name} leaves the {role} role.")
    return True, f"released {member.name}"


def record_title(gs: GameState, team_id: str, title: str) -> None:
    """Silverware sticks to the staff who were in the building for it."""
    for m in gs.staff_by.get(team_id, {}).values():
        m.titles.append(title)


# -- weekly effect hooks -------------------------------------------------------


def weekly_cost(gs: GameState) -> int:
    return sum(m.salary for m in gs.staff.values())


def coach_multiplier(gs: GameState, focus: str | None = None) -> float:
    """Training growth multiplier: 1.0 bare, up to ~1.45 with an elite
    coach — plus a specialty premium when the week's focus is the
    category they drill best."""
    coach = gs.staff.get("coach")
    if coach is None:
        return 1.0
    mult = 1.0 + coach.quality / 200.0
    if focus is not None and focus == coach.specialty:
        mult += SPECIALTY_GROWTH_BONUS
    return mult


def scout_multiplier(gs: GameState) -> float:
    """Scouting speed multiplier: up to ~1.9 with an elite analyst."""
    analyst = gs.staff.get("analyst")
    return 1.0 + (analyst.quality / 100.0) if analyst else 1.0


def physio_recovery(gs: GameState) -> float:
    """Extra stamina per player per week."""
    physio = gs.staff.get("physio")
    return physio.quality / 18.0 if physio else 0.0  # up to ~5.4/wk


# -- analytics department ------------------------------------------------------

# What each tier of the analytics department can compile. The web stats
# serializers gate their columns on this — a bare org reads box scores, an
# elite department reads everything.
ANALYTICS_TIER_LABEL = {
    0: "box scores only",
    1: "duel detail (FK/FD, HS%, ACS, clutches)",
    2: "round context (KAST, trades, weapons, eco/save splits)",
    3: "full splits (per-map, per-agent, trend charts)",
}


def analytics_tier(gs: GameState) -> int:
    """0-3, from the analyst's quality plus the analytics suite facility.
    Score = analyst quality + 15/level; tiers at 1 / 55 / 95 — an average
    analyst alone reaches tier 1-2, elite-plus-suite reaches 3."""
    analyst = gs.staff.get("analyst")
    score = (analyst.quality if analyst else 0.0) + 15.0 * gs.facilities.get(
        "analytics_suite", 0
    )
    if score >= 95.0:
        return 3
    if score >= 55.0:
        return 2
    if score >= 1.0:
        return 1
    return 0
