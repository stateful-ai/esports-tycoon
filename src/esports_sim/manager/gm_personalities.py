"""Stable, public identities for off-screen AI general managers.

Archetypes are pure functions of campaign seed + team id. Consumers use only
information that manager code already treats as visible (age, followers,
perceived quality, results, budget), and every consequential action remains in
the existing market/tactics resolvers.
"""

from __future__ import annotations

import hashlib

import numpy as np

from esports_sim.manager.state import GameState


ARCHETYPES = (
    "spender",
    "scapegoater",
    "developer",
    "loyalist",
    "analyst",
)

_COPY = {
    "spender": (
        "The Spender",
        "Pays premiums for marquee talent and enters bidding races early.",
        "Aggressive market bids",
    ),
    "scapegoater": (
        "The Scapegoater",
        "Treats short losing streaks as a coaching failure and changes direction fast.",
        "Frequent coaching changes",
    ),
    "developer": (
        "The Developer",
        "Prefers younger upgrades and is willing to wait for them to mature.",
        "Targets young players",
    ),
    "loyalist": (
        "The Loyalist",
        "Avoids churn and moves only for an unmistakable roster upgrade.",
        "Low roster turnover",
    ),
    "analyst": (
        "The Analyst",
        "Prices every move tightly and follows proven league trends.",
        "Value-led decisions",
    ),
}


def archetype_for(seed: int, team_id: str) -> str:
    raw = hashlib.blake2b(
        f"ai-gm|{seed}|{team_id}".encode("utf-8"), digest_size=8
    ).digest()
    return ARCHETYPES[int.from_bytes(raw, "big") % len(ARCHETYPES)]


def profile(gs: GameState, team_id: str) -> dict:
    archetype = archetype_for(gs.seed, team_id)
    label, description, behavior = _COPY[archetype]
    return {
        "id": archetype,
        "label": label,
        "description": description,
        "behavior": behavior,
        "coach_changes": gs.ai_gm_coach_changes_by.get(team_id, 0),
    }


def transfer_appetite(archetype: str, *, quiet: bool) -> float:
    base = {
        "spender": 0.25,
        "scapegoater": 0.14,
        "developer": 0.16,
        "loyalist": 0.055,
        "analyst": 0.11,
    }[archetype]
    return base * (0.35 if quiet else 1.0)


def upgrade_threshold(archetype: str) -> float:
    return {
        "spender": 3.0,
        "scapegoater": 4.5,
        "developer": 4.0,
        "loyalist": 8.5,
        "analyst": 6.0,
    }[archetype]


def target_bonus(archetype: str, *, age: int, followers: int) -> float:
    if archetype == "developer":
        return max(0.0, 23 - age) * 0.9
    if archetype == "spender":
        return min(4.0, followers / 250_000.0)
    return 0.0


def bid_multiplier(archetype: str) -> float:
    return 1.18 if archetype == "spender" else 1.0


def free_agent_salary_multiplier(archetype: str) -> float:
    return 1.20 if archetype == "spender" else 1.0


def poach_priority(archetype: str) -> int:
    return {
        "spender": 5,
        "developer": 4,
        "scapegoater": 3,
        "analyst": 2,
        "loyalist": 1,
    }[archetype]


def _loss_streak(gs: GameState, team_id: str) -> int:
    fixtures = sorted(
        (
            f for f in gs.fixtures
            if f.played and team_id in (f.team_a, f.team_b)
        ),
        key=lambda f: (f.week, f.id),
        reverse=True,
    )
    streak = 0
    for fixture in fixtures:
        if fixture.winner_id == team_id:
            break
        streak += 1
    return streak


def weekly_tick(gs: GameState, rng: np.random.Generator) -> None:
    """Apply rare, visible front-office consequences after the week's games."""
    now = (gs.season - 1) * 100 + gs.week
    dials = ("aggression", "pace", "util_discipline", "eco_greed", "map_control")
    for team_id in sorted(gs.teams):
        team = gs.teams[team_id]
        if team.tier != 1 or gs.is_human(team_id):
            continue
        if archetype_for(gs.seed, team_id) != "scapegoater":
            continue
        if _loss_streak(gs, team_id) < 2:
            continue
        last = gs.ai_gm_last_action_week_by.get(team_id, -999)
        if now - last < 4:
            continue
        # A new coaching direction is a reset, not a hidden performance buff.
        # Every dial stays bounded and the public news makes the churn legible.
        for dial in dials:
            setattr(team.tactics, dial, round(float(np.clip(50 + rng.normal(0, 9), 25, 75)), 1))
        gs.ai_gm_last_action_week_by[team_id] = now
        gs.ai_gm_coach_changes_by[team_id] = (
            gs.ai_gm_coach_changes_by.get(team_id, 0) + 1
        )
        gs.push_news(
            f"{team.name} part with their coach after a {_loss_streak(gs, team_id)}-match losing streak."
        )
