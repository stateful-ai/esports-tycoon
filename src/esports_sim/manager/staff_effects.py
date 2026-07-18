"""Shared staff ratings, identities, and effect resolution.

The staff market, weekly campaign tick, manager policy, and web serializers all
read this module.  The browser never re-derives these formulas.  ``quality`` is
retained on ``StaffMember`` as a save/API compatibility value, while the
attribute profile is the source of truth for every new effect.
"""

from __future__ import annotations

from esports_sim.labels import humanize_identifier

from typing import Any

import numpy as np


ATTRIBUTE_LABELS = {
    "expertise": "Expertise",
    "tactical_knowledge": "Tactical Knowledge",
    "analysis": "Analysis",
    "teaching": "Teaching",
    "people_management": "People Management",
    "motivation": "Motivation",
    "adaptability": "Adaptability",
}

ATTRIBUTE_DESCRIPTIONS = {
    "expertise": "Professional command of this staff member's discipline.",
    "tactical_knowledge": "Understanding of systems, game plans, and the live meta.",
    "analysis": "Ability to diagnose opponents, players, and performance evidence.",
    "teaching": "Ability to turn knowledge into repeatable player improvement.",
    "people_management": "Trust, relationships, and individual handling.",
    "motivation": "Ability to set intensity and restore belief under pressure.",
    "adaptability": "Effectiveness outside a preferred method and during change.",
}

ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "coach": {
        "tactical_knowledge": 0.25, "teaching": 0.22,
        "people_management": 0.17, "motivation": 0.14,
        "adaptability": 0.12, "analysis": 0.06, "expertise": 0.04,
    },
    "analyst": {
        "analysis": 0.35, "tactical_knowledge": 0.25,
        "expertise": 0.20, "adaptability": 0.12, "teaching": 0.08,
    },
    "physio": {
        "expertise": 0.45, "analysis": 0.22, "teaching": 0.13,
        "people_management": 0.10, "adaptability": 0.10,
    },
    "psychologist": {
        "expertise": 0.30, "people_management": 0.28,
        "motivation": 0.22, "analysis": 0.10, "adaptability": 0.10,
    },
    "performance_coach": {
        "expertise": 0.27, "analysis": 0.20, "teaching": 0.18,
        "motivation": 0.18, "adaptability": 0.10,
        "people_management": 0.07,
    },
    "language_coach": {
        "expertise": 0.36, "teaching": 0.30,
        "people_management": 0.18, "adaptability": 0.10,
        "motivation": 0.06,
    },
}

STYLE_ARCHETYPES: dict[str, dict[str, float]] = {
    "fast_pressure": {
        "aggression": 76.0, "pace": 78.0, "util_discipline": 42.0,
        "eco_greed": 62.0, "map_control": 35.0,
    },
    "structured_control": {
        "aggression": 38.0, "pace": 34.0, "util_discipline": 72.0,
        "eco_greed": 42.0, "map_control": 68.0,
    },
    "utility_first": {
        "aggression": 48.0, "pace": 44.0, "util_discipline": 82.0,
        "eco_greed": 36.0, "map_control": 62.0,
    },
    "map_control": {
        "aggression": 52.0, "pace": 38.0, "util_discipline": 66.0,
        "eco_greed": 45.0, "map_control": 82.0,
    },
    "pragmatic": {
        "aggression": 52.0, "pace": 50.0, "util_discipline": 55.0,
        "eco_greed": 50.0, "map_control": 54.0,
    },
}

STYLE_LABELS = {
    "fast_pressure": "Fast pressure",
    "structured_control": "Structured control",
    "utility_first": "Utility first",
    "map_control": "Map control",
    "pragmatic": "Pragmatic",
}

TRAITS: dict[str, dict[str, Any]] = {
    "developer": {"label": "Developer", "desc": "Adds 8% to coached development for players aged 22 or younger."},
    "players_coach": {"label": "Players' Coach", "desc": "Adds 5% development when a player is low on morale and favors stabilizing timeout advice."},
    "disciplinarian": {"label": "Disciplinarian", "desc": "Intense plans gain 6% development; light plans lose 3%."},
    "innovator": {"label": "Innovator", "desc": "Game-plan preparation gains 12% when working outside a near-perfect system fit."},
    "system_builder": {"label": "System Builder", "desc": "Strong system fit adds 5% development; a severe mismatch loses 5%."},
    "pragmatist": {"label": "Pragmatist", "desc": "System mismatch is softened, but perfect-fit upside is capped."},
    "opponent_specialist": {"label": "Opponent Specialist", "desc": "Team and player opposition scouting progresses 8% faster."},
    "talent_spotter": {"label": "Talent Spotter", "desc": "Market scouting progresses 8% faster."},
    "data_purist": {"label": "Data Purist", "desc": "Adds five points to analytics-department tier scoring."},
    "recovery_specialist": {"label": "Recovery Specialist", "desc": "Restores 8% more weekly stamina."},
    "preventive": {"label": "Preventive", "desc": "Restores 5% more weekly stamina through load management."},
    "confidence_builder": {"label": "Confidence Builder", "desc": "Restores 8% more confidence to shaken players."},
    "pressure_specialist": {"label": "Pressure Specialist", "desc": "Restores 6% more confidence under pressure."},
    "consistency": {"label": "Consistency", "desc": "Restores 8% more form to slumping players."},
    "routines": {"label": "Routines", "desc": "Restores 5% more form through repeatable weekly habits."},
    "callout_specialist": {"label": "Callout Specialist", "desc": "Adds 8% more fluency per language session."},
    "immersion": {"label": "Immersion", "desc": "Adds 6% more fluency per language session."},
}

BADGES: dict[str, dict[str, str]] = {
    "champion": {"label": "Champion", "desc": "Won a major title while employed."},
    "dynasty_architect": {"label": "Dynasty Architect", "desc": "Collected three major titles while employed."},
    "veteran_operator": {"label": "Veteran Operator", "desc": "Completed 100 weeks in professional staff roles."},
    "talent_developer": {"label": "Talent Developer", "desc": "Recorded 25 points of player development while employed."},
    "master_strategist": {"label": "Master Strategist", "desc": "Coached 50 maps with at least a 60% series win rate."},
    "opposition_expert": {"label": "Opposition Expert", "desc": "Added ten full reports' worth of scouting progress."},
    "iron_squad": {"label": "Iron Squad", "desc": "Restored 500 stamina points to players."},
    "stabilizer": {"label": "Stabilizer", "desc": "Restored 100 confidence points to shaken players."},
    "consistency_architect": {"label": "Consistency Architect", "desc": "Restored 100 form points to slumping players."},
    "polyglot_program": {"label": "Polyglot Program", "desc": "Taught 50 fluency points through language sessions."},
}


def attr(member: Any, key: str) -> float:
    values = getattr(member, "attributes", {}) or {}
    return float(values.get(key, getattr(member, "quality", 50.0)))


def overall(member: Any) -> float:
    weights = ROLE_WEIGHTS.get(getattr(member, "role", ""), {"expertise": 1.0})
    return round(sum(attr(member, key) * weight for key, weight in weights.items()), 1)


def style_identity(member: Any) -> str:
    style = getattr(member, "style_identity", "")
    return style if style in STYLE_ARCHETYPES else "pragmatic"


def style_preferences(member: Any) -> dict[str, float]:
    stored = getattr(member, "style_preferences", {}) or {}
    base = STYLE_ARCHETYPES[style_identity(member)]
    return {dial: float(stored.get(dial, value)) for dial, value in base.items()}


def system_fit(member: Any, tactics: Any) -> float:
    """0-100 coach-to-system fit; adaptability softens preference distance."""
    if getattr(member, "role", "") != "coach":
        return 100.0
    prefs = style_preferences(member)
    distance = float(np.mean([
        abs(float(getattr(tactics, dial)) - preferred)
        for dial, preferred in sorted(prefs.items())
    ]))
    adaptability = attr(member, "adaptability")
    fit = 100.0 - distance * (1.0 - 0.45 * adaptability / 100.0)
    if "pragmatist" in (getattr(member, "traits", []) or []):
        fit = min(95.0, max(65.0, fit))
    return round(float(np.clip(fit, 0.0, 100.0)), 1)


def fit_multiplier(member: Any, tactics: Any) -> float:
    return 0.85 + 0.30 * system_fit(member, tactics) / 100.0


def coach_training_multiplier(member: Any, tactics: Any, focus: str | None) -> float:
    coaching = (
        attr(member, "teaching") * 0.42
        + attr(member, "tactical_knowledge") * 0.22
        + attr(member, "expertise") * 0.16
        + attr(member, "people_management") * 0.12
        + attr(member, "motivation") * 0.08
    )
    contribution = coaching / 200.0 * fit_multiplier(member, tactics)
    if focus is not None and focus == getattr(member, "specialty", ""):
        contribution += 0.15
    return round(1.0 + contribution, 4)


def coach_player_multiplier(member: Any, player: Any, tactics: Any) -> float:
    mult = 1.0
    traits = set(getattr(member, "traits", []) or [])
    if "developer" in traits and int(getattr(player, "age", 99)) <= 22:
        mult += 0.08
    if "players_coach" in traits and float(getattr(player, "morale", 100.0)) < 55.0:
        mult += 0.05
    intensity = str(getattr(player, "training_intensity", "normal"))
    if "disciplinarian" in traits:
        mult += 0.06 if intensity == "intense" else -0.03 if intensity == "light" else 0.0
    fit = system_fit(member, tactics)
    if "system_builder" in traits:
        mult += 0.05 if fit >= 75.0 else -0.05 if fit < 55.0 else 0.0
    return round(max(0.85, mult), 4)


def coach_prep_bonus(member: Any, tactics: Any) -> float:
    base = (
        attr(member, "tactical_knowledge") * 0.0010
        + attr(member, "analysis") * 0.0007
        + attr(member, "adaptability") * 0.0003
    ) * fit_multiplier(member, tactics)
    if "innovator" in (getattr(member, "traits", []) or []) and system_fit(member, tactics) < 90.0:
        base *= 1.12
    return round(float(np.clip(base, 0.0, 0.18)), 4)


def role_effect_score(member: Any) -> float:
    role = getattr(member, "role", "")
    weights = {
        "analyst": {"analysis": 0.45, "tactical_knowledge": 0.30, "expertise": 0.25},
        "physio": {"expertise": 0.55, "analysis": 0.30, "teaching": 0.15},
        "psychologist": {"expertise": 0.35, "people_management": 0.35, "motivation": 0.30},
        "performance_coach": {"expertise": 0.35, "analysis": 0.30, "motivation": 0.20, "teaching": 0.15},
        "language_coach": {"expertise": 0.40, "teaching": 0.38, "people_management": 0.22},
    }.get(role, ROLE_WEIGHTS.get(role, {"expertise": 1.0}))
    score = sum(attr(member, key) * weight for key, weight in weights.items())
    traits = set(getattr(member, "traits", []) or [])
    trait_mult = 1.0
    for trait, amount in {
        "recovery_specialist": 0.08, "preventive": 0.05,
        "confidence_builder": 0.08, "pressure_specialist": 0.06,
        "consistency": 0.08, "routines": 0.05,
        "callout_specialist": 0.08, "immersion": 0.06,
    }.items():
        if trait in traits:
            trait_mult += amount
    return round(float(np.clip(score * trait_mult, 1.0, 99.0)), 1)


def trait_views(member: Any) -> list[dict[str, str]]:
    return [
        {"id": trait, **TRAITS.get(trait, {"label": humanize_identifier(trait), "desc": ""})}
        for trait in sorted(getattr(member, "traits", []) or [])
    ]


def badge_views(member: Any) -> list[dict[str, str]]:
    return [
        {"id": badge, **BADGES.get(badge, {"label": humanize_identifier(badge), "desc": ""})}
        for badge in sorted(getattr(member, "badges", []) or [])
    ]
