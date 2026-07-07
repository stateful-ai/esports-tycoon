"""Weekly training: attribute growth, stamina management, chemistry.

The manager picks one focus per week per team. Growth is age-gated —
teenagers develop fast, players past 27 mostly fight decline (which is
applied in the offseason, not here).
"""

from __future__ import annotations

import numpy as np

from esports_sim.schemas import Player, Team
from esports_sim.schemas.attributes import AttributeCategory

FOCUS_OPTIONS = ["mechanical", "tactical", "mental", "team", "rest"]

_CATEGORY_ATTRS: dict[str, list[str]] = {
    "mechanical": ["aim_precision", "aim_reactivity", "movement"],
    "tactical": ["game_sense", "utility_usage", "positioning"],
    "mental": ["clutch_factor", "tilt_resistance", "composure"],
    "team": ["comms_quality"],
}


def growth_rate(age: int) -> float:
    """Weekly attribute gain baseline by age."""
    if age <= 19:
        return 0.65
    if age <= 21:
        return 0.5
    if age <= 24:
        return 0.35
    if age <= 27:
        return 0.2
    return 0.08


def apply_training(
    team: Team,
    roster: list[Player],
    focus: str,
    rng: np.random.Generator,
) -> None:
    if focus == "rest":
        for p in roster:
            p.stamina = min(100.0, p.stamina + 18.0)
            p.morale = min(100.0, p.morale + 1.5)
        return

    attrs = _CATEGORY_ATTRS.get(focus, _CATEGORY_ATTRS["tactical"])
    for p in roster:
        rate = growth_rate(p.age)
        # Tired players learn worse; below 35 stamina they barely absorb.
        fatigue_mult = 0.4 if p.stamina < 35 else 1.0
        # Train the weakest attribute in the category hardest.
        by_value = sorted(attrs, key=lambda a: p.attr(a))
        for i, attr_id in enumerate(by_value):
            gain = rate * fatigue_mult * (1.0 if i == 0 else 0.5)
            gain *= float(rng.uniform(0.6, 1.4))
            cur = p.attr(attr_id)
            # Diminishing returns near the ceiling.
            headroom = max(0.0, (95.0 - cur) / 45.0)
            p.attributes[attr_id] = round(min(99.0, cur + gain * headroom), 2)
        p.stamina = max(0.0, p.stamina - 6.0)

    if focus == "team":
        team.chemistry = min(100.0, team.chemistry + 1.2)
        for p in roster:
            p.morale = min(100.0, p.morale + 0.5)


def ai_pick_focus(roster: list[Player], rng: np.random.Generator) -> str:
    """AI coaching: rest when gassed, otherwise train the weakest category."""
    avg_stamina = sum(p.stamina for p in roster) / max(len(roster), 1)
    if avg_stamina < 55:
        return "rest"
    cat_avgs = {
        cat: sum(p.attr(a) for p in roster for a in attrs)
        / max(len(roster) * len(attrs), 1)
        for cat, attrs in _CATEGORY_ATTRS.items()
    }
    weakest = min(sorted(cat_avgs), key=lambda c: cat_avgs[c])
    # A little variety so every AI team doesn't march in lockstep.
    if rng.random() < 0.25:
        return str(rng.choice([c for c in FOCUS_OPTIONS if c != weakest]))
    return weakest


def apply_offseason_aging(p: Player, rng: np.random.Generator) -> None:
    """One year older: young players get a bump, veterans decline."""
    p.age += 1
    if p.age >= 28:
        decline = (p.age - 27) * 0.8
        for attr_id in _CATEGORY_ATTRS["mechanical"]:
            p.attributes[attr_id] = round(
                max(1.0, p.attr(attr_id) - decline * float(rng.uniform(0.7, 1.3))), 2
            )
        # Experience partially compensates.
        for attr_id in ("game_sense", "composure"):
            p.attributes[attr_id] = round(min(99.0, p.attr(attr_id) + 0.4), 2)
    elif p.age <= 22:
        for attr_id in _CATEGORY_ATTRS["mechanical"]:
            p.attributes[attr_id] = round(
                min(99.0, p.attr(attr_id) + float(rng.uniform(0.3, 1.2))), 2
            )
    # Fresh legs for the new season.
    p.stamina = max(p.stamina, 88.0)
    p.form = 50.0
    p.morale = float(np.clip(p.morale, 55.0, 90.0))
