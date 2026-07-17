"""Sandbox scenario starts: opt-in presets that reshape the USER'S org
at `new_campaign` time.

Design rules (all load-bearing):
- Opt-in and no-op when unused: `new_campaign(scenario=None)` never calls
  into this module, so hands-off sims and the gates are byte-identical.
- Deterministic: every per-player variation is a blake2 hash of the
  stable player id — no rng stream is consumed, so applying a scenario
  cannot shift any later campaign draw.
- User-org only: presets mutate the user's team, its rostered players,
  and the user's private slices (facilities, academy level, sentiment).
  Every other club, free agent, and shared pool is untouched.
- Sandbox-only: legacy careers start from board offers, not headaches.
- The choice is chronicled here as a save-start note; the web/CLI layer
  records the human's pick in the action_log ("scenario_start"), like
  every other human decision.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from esports_sim.manager import chronicle, economy, market, staff

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState

# ---------------------------------------------------------------------------
# Tuning data (kept here, not sim/constants.py — campaign layer only)

# Insolvent giant: the club is famous, broke, and burning cash.
GIANT_REPUTATION = 88.0
GIANT_FAN_COUNT = 1_100_000
GIANT_TARGET_BURN = 10_000  # aimed weekly net loss, credits
GIANT_MIN_WAGE_SCALE = 1.6  # wages bloat even if the org somehow earns little
RUNWAY_WEEKS = 20  # weeks of cash left before the insolvency floor

# Youth project: teenagers with upside, a modest budget, strong development.
YOUTH_MAX_BUDGET = 260_000
YOUTH_PA_EDGE = (10.0, 20.0)  # potential raised to quality + this range
YOUTH_FACILITY_LEVEL = 2  # training_center head start (max 3)
YOUTH_ACADEMY_LEVEL = 2  # academy programme head start (max 3)

# Crisis club: a broken locker room under pressure.
CRISIS_CHEMISTRY = 34.0
CRISIS_SENTIMENT = 26.0
CRISIS_REPUTATION = 42.0
CRISIS_MAX_BUDGET = 140_000
CRISIS_MORALE_BASE = (32.0, 42.0)
CRISIS_CONFIDENCE_BASE = (38.0, 46.0)

# Superteam headache: five stars, five egos, one payroll.
SUPER_TARGET_QUALITY = (80.0, 88.0)
SUPER_ATTR_CAP = 96.0
SUPER_WAGE_SCALE = 3.0
SUPER_MIN_WAGE = 9_000
SUPER_CHEMISTRY = 42.0
SUPER_SENTIMENT = 62.0  # the fans are hyped; the locker room isn't
SUPER_CLASH_TAGS = (
    "star_player",
    "hot_head",
    "showman",
    "perfectionist",
    "volatile",
)


def _jit(pid: str, label: str, lo: float, hi: float) -> float:
    """Stable per-player jitter in [lo, hi) — blake2 of the id, never a
    live rng draw, so scenarios consume no stream and stay replayable."""
    digest = hashlib.blake2b(
        f"scenario|{label}|{pid}".encode("utf-8"), digest_size=8
    ).digest()
    frac = (int.from_bytes(digest, "big") % 10_000) / 10_000.0
    return lo + frac * (hi - lo)


def _net_burn(gs: "GameState") -> int:
    """The acting org's weekly net (income - payroll - staff - upkeep)."""
    return economy.weekly_breakdown(gs, staff.weekly_cost(gs))["net"]


# ---------------------------------------------------------------------------
# Presets


def _apply_insolvent_giant(gs: "GameState", tid: str) -> None:
    team = gs.teams[tid]
    roster = gs.roster(tid)
    team.reputation = max(team.reputation, GIANT_REPUTATION)
    team.fan_count = max(team.fan_count, GIANT_FAN_COUNT)
    # Bloat the payroll so the run rate lands near the target burn: solve
    # for the wage bill that leaves net at -GIANT_TARGET_BURN, then apply
    # it with a small per-player spread (some deals age worse than others).
    bd = economy.weekly_breakdown(gs, staff.weekly_cost(gs))
    salaries = max(1, bd["salaries"])
    want = bd["net"] + salaries + GIANT_TARGET_BURN
    scale = max(GIANT_MIN_WAGE_SCALE, want / salaries)
    for p in roster:
        p.salary = int(p.salary * scale * _jit(p.id, "giant-wage", 0.9, 1.1))
    # The jitter can undershoot the solve in a rich world; top the bill up
    # (bounded, deterministic) until the org genuinely burns cash.
    for _ in range(4):
        if _net_burn(gs) <= -(GIANT_TARGET_BURN // 2):
            break
        for p in roster:
            p.salary = int(p.salary * 1.15)
    # Set the cash so the floor is ~RUNWAY_WEEKS away at the actual burn —
    # and always in the red, whatever the world's income looks like.
    burn = max(2_500, -_net_burn(gs))
    team.balance = min(-40_000, economy.INSOLVENCY_FLOOR + RUNWAY_WEEKS * burn)
    gs.push_private_news(
        f"{team.name} are a household name with empty pockets: the wage "
        f"bill dwarfs the income and the reserves are gone.",
        owner=tid,
    )


def _apply_youth_project(gs: "GameState", tid: str) -> None:
    team = gs.teams[tid]
    for pid in list(team.player_ids):
        p = gs.players[pid]
        p.age = min(p.age, 17 + int(_jit(pid, "youth-age", 0.0, 4.0)))
        q = market.player_quality(p)
        lo, hi = YOUTH_PA_EDGE
        p.potential = round(
            min(97.0, max(p.potential, q + _jit(pid, "youth-pa", lo, hi))), 1
        )
        # A project squad was assembled recently, not inherited.
        p.tenure_weeks = min(
            p.tenure_weeks, 12 + int(_jit(pid, "youth-tenure", 0.0, 28.0))
        )
    team.balance = min(team.balance, YOUTH_MAX_BUDGET)
    fac = gs.facilities_by.setdefault(tid, {})
    fac["training_center"] = max(
        fac.get("training_center", 0), YOUTH_FACILITY_LEVEL
    )
    gs.academy_levels[tid] = max(
        gs.academy_levels.get(tid, 0), YOUTH_ACADEMY_LEVEL
    )
    gs.push_private_news(
        f"{team.name} have bet the org on youth: a teenage roster with "
        f"real upside, a development pipeline, and not much cash.",
        owner=tid,
    )


def _apply_crisis_club(gs: "GameState", tid: str) -> None:
    team = gs.teams[tid]
    team.chemistry = min(team.chemistry, CRISIS_CHEMISTRY)
    team.reputation = min(team.reputation, CRISIS_REPUTATION)
    team.balance = min(team.balance, CRISIS_MAX_BUDGET)
    gs.team_sentiment[tid] = CRISIS_SENTIMENT
    for pid in list(team.player_ids):
        p = gs.players[pid]
        m_lo, m_hi = CRISIS_MORALE_BASE
        c_lo, c_hi = CRISIS_CONFIDENCE_BASE
        p.morale = round(min(p.morale, _jit(pid, "crisis-morale", m_lo, m_hi)), 1)
        p.confidence = round(
            min(p.confidence, _jit(pid, "crisis-conf", c_lo, c_hi)), 1
        )
    gs.push_private_news(
        f"The mood at {team.name} is toxic: the room is fractured, the "
        f"fans are furious, and the board demand it fixed fast.",
        owner=tid,
    )


def _apply_superteam_headache(gs: "GameState", tid: str) -> None:
    team = gs.teams[tid]
    q_lo, q_hi = SUPER_TARGET_QUALITY
    for i, pid in enumerate(list(team.player_ids)):
        p = gs.players[pid]
        q = market.player_quality(p)
        target = _jit(pid, "super-q", q_lo, q_hi)
        if 0.0 < q < target:
            factor = target / q
            for k in list(p.attributes):
                v = p.attributes[k]
                p.attributes[k] = round(max(v, min(SUPER_ATTR_CAP, v * factor)), 1)
        p.salary = max(int(p.salary * SUPER_WAGE_SCALE), SUPER_MIN_WAGE)
        tag = SUPER_CLASH_TAGS[i % len(SUPER_CLASH_TAGS)]
        if tag not in p.personality_tags:
            p.personality_tags.append(tag)
    team.chemistry = min(team.chemistry, SUPER_CHEMISTRY)
    gs.team_sentiment[tid] = SUPER_SENTIMENT
    gs.push_private_news(
        f"{team.name} bought five headliners and one locker room: the "
        f"talent is outrageous, the egos more so, and the payroll worst "
        f"of all.",
        owner=tid,
    )


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    blurb: str  # one-line pitch, shown in the lobby / CLI selector
    apply: Callable[["GameState", str], None]


# Declaration order is display order (lobby buttons, CLI list).
SCENARIOS: dict[str, Scenario] = {
    s.id: s
    for s in (
        Scenario(
            id="insolvent_giant",
            name="Insolvent giant",
            blurb=(
                "A famous org with a huge fanbase, a bloated wage bill and "
                "roughly twenty weeks of cash left."
            ),
            apply=_apply_insolvent_giant,
        ),
        Scenario(
            id="youth_project",
            name="Youth project",
            blurb=(
                "A teenage roster with real upside, a strong development "
                "setup and a modest budget."
            ),
            apply=_apply_youth_project,
        ),
        Scenario(
            id="crisis_club",
            name="Crisis club",
            blurb=(
                "Low morale, a fractured locker room and furious fans - "
                "stabilise it before it sinks."
            ),
            apply=_apply_crisis_club,
        ),
        Scenario(
            id="superteam_headache",
            name="Superteam headache",
            blurb=(
                "Five stars, five egos: outrageous talent on big wages "
                "that does not yet fit together."
            ),
            apply=_apply_superteam_headache,
        ),
    )
}


def options() -> list[dict]:
    """Lobby/CLI wire shape: id + name + one-line blurb, display order."""
    return [
        {"id": s.id, "name": s.name, "blurb": s.blurb}
        for s in SCENARIOS.values()
    ]


def apply(gs: "GameState", scenario_id: str) -> None:
    """Apply one preset to the user's org and chronicle the save-start
    note. Called exactly once, by `new_campaign`, before world ranks and
    the season-start snapshots are taken (so both reflect the scenario)."""
    sc = SCENARIOS.get(scenario_id)
    if sc is None:
        raise ValueError(f"unknown scenario '{scenario_id}'")
    tid = gs.user_team_id
    # Bind the acting org for the economy reads (weekly_breakdown/staff
    # cost read the acting slice); restore the default afterwards.
    gs.set_acting(tid)
    try:
        sc.apply(gs, tid)
    finally:
        gs.set_acting(None)
    chronicle.record(
        gs,
        "scenario",
        f"{gs.teams[tid].name} begin the campaign under the "
        f"'{sc.name}' scenario: {sc.blurb}",
        team_id=tid,
        data={"scenario": sc.id},
    )
