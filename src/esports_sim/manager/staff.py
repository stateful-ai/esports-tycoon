"""Backroom staff: coach, analyst, physio.

Each hired member scales one weekly system — coach boosts training
growth, analyst speeds scouting, physio restores stamina. Candidates are
generated deterministically per season; hiring is instant, releasing is
free (staff contracts are at-will in this economy). User team only.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.gen import _FIRST_NAMES, _LAST_NAMES
from esports_sim.manager.state import GameState, StaffMember
from esports_sim.rng.tree import RngTree

ROLES = ["coach", "analyst", "physio"]
CANDIDATES_PER_ROLE = 3

ROLE_BLURB = {
    "coach": "training growth",
    "analyst": "scouting speed",
    "physio": "weekly stamina recovery",
}


def refresh_candidates(gs: GameState) -> None:
    """(Re)generate the candidate market. Called at campaign start and
    every offseason. Deterministic from (seed, season)."""
    rng = RngTree(gs.seed).derive("staff", gs.season)
    market: dict[str, list[StaffMember]] = {}
    for role in ROLES:
        pool: list[StaffMember] = []
        for i in range(CANDIDATES_PER_ROLE):
            quality = float(np.round(rng.uniform(45, 88), 1))
            name = f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
            salary = max(1_500, int(np.round((quality ** 1.5) * 8 / 100) * 100))
            pool.append(
                StaffMember(
                    id=f"staff_s{gs.season}_{role}_{i}",
                    name=name,
                    role=role,
                    quality=quality,
                    salary=salary,
                )
            )
        market[role] = pool
    gs.staff_candidates = market


def hire(gs: GameState, candidate_id: str) -> tuple[bool, str]:
    for role, pool in gs.staff_candidates.items():
        for cand in pool:
            if cand.id != candidate_id:
                continue
            team = gs.teams[gs.acting_team_id]
            if team.balance < cand.salary * 8:
                return False, f"need {cand.salary * 8:,} cr banked for the hire"
            old = gs.staff.get(role)
            gs.staff[role] = cand
            pool.remove(cand)
            if old is not None:
                pool.append(old)  # the outgoing member re-enters the market
            gs.push_news(
                f"{team.name} bring in {cand.name} ({role}, {cand.salary:,}/wk)."
            )
            return True, f"hired {cand.name} as {role}"
    return False, "unknown candidate"


def release(gs: GameState, role: str) -> tuple[bool, str]:
    member = gs.staff.pop(role, None)
    if member is None:
        return False, f"no {role} on staff"
    gs.staff_candidates.setdefault(role, []).append(member)
    gs.push_news(f"{member.name} leaves the {role} role.")
    return True, f"released {member.name}"


# -- weekly effect hooks -------------------------------------------------------


def weekly_cost(gs: GameState) -> int:
    return sum(m.salary for m in gs.staff.values())


def coach_multiplier(gs: GameState) -> float:
    """Training growth multiplier: 1.0 bare, up to ~1.45 with an elite coach."""
    coach = gs.staff.get("coach")
    return 1.0 + (coach.quality / 200.0) if coach else 1.0


def scout_multiplier(gs: GameState) -> float:
    """Scouting speed multiplier: up to ~1.9 with an elite analyst."""
    analyst = gs.staff.get("analyst")
    return 1.0 + (analyst.quality / 100.0) if analyst else 1.0


def physio_recovery(gs: GameState) -> float:
    """Extra stamina per player per week."""
    physio = gs.staff.get("physio")
    return physio.quality / 18.0 if physio else 0.0  # up to ~5.4/wk
