"""Player development: potential, traits, and scout assessment.

EHM-style model: every player has a Current Ability (their attributes)
and a hidden Potential Ability ceiling. Development speed depends on the
CA→PA gap, age, traits, and coaching. Scouts don't see truth — they see
bands that tighten with scouting effort, and traits reveal one by one.

Determinism: every derived number comes from blake2 hashes of stable ids
or from the campaign RngTree — never Python's salted hash(), never
wall-clock anything.
"""

from __future__ import annotations

import hashlib

import numpy as np

from esports_sim.schemas import Player

# ---------------------------------------------------------------------------
# Trait catalog. Tags already on players (authored + talk module) keep
# working; this table gives them mechanical teeth. Effects reference
# systems that exist — development, aging, market, chemistry, fandom.

# The catalog itself lives in schemas/traits.py (a leaf module) so the
# match engine can read trait effects too. Re-exported here so all the
# existing manager-layer imports keep working.
from esports_sim.schemas.traits import TRAITS, trait_value  # noqa: F401

# Traits eligible for procedural generation (flavor-only ones included).
GEN_TRAIT_POOL = sorted(TRAITS)


def _h(*parts) -> int:
    b = hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8)
    return int.from_bytes(b.digest(), "big")


def overall(p: Player) -> float:
    """Canonical Current Ability: mean attribute."""
    if not p.attributes:
        return 50.0
    return sum(p.attributes.values()) / len(p.attributes)


def decline_age(p: Player) -> int:
    return int(trait_value(p, "decline_age", 28))


def dev_multiplier(p: Player) -> float:
    """Development speed from the CA→PA gap and traits. A player at
    their ceiling only maintains; a raw prospect with a big gap flies."""
    gap = potential_of(p) - overall(p)
    gap_mult = float(np.clip(gap / 15.0, 0.1, 1.5))
    return gap_mult * trait_value(p, "dev_mult", 1.0)


def potential_of(p: Player) -> float:
    """PA with a deterministic fallback for players authored before the
    field existed: ceiling grows with youth, seeded by player id."""
    if p.potential > 0:
        return p.potential
    ca = overall(p)
    youth = max(0, 25 - p.age)
    bonus = (_h(p.id, "pa") % 1000) / 1000.0  # 0..1, stable per player
    return round(float(min(96.0, ca + youth * (1.2 + 2.0 * bonus))), 1)


def assign_potential(p: Player, rng: np.random.Generator) -> None:
    """Roll PA at generation time (gen.py / rookies). Ceiling-rounded so
    PA >= CA survives the 1-decimal store."""
    ca = overall(p)
    youth = max(0, 25 - p.age)
    raw = min(96.0, max(ca, ca + youth * rng.uniform(1.0, 3.2) + rng.normal(0, 2)))
    p.potential = float(np.ceil(raw * 10.0) / 10.0)


def retirement_prob(p: Player) -> float:
    """Offseason chance a player hangs it up. Nobody retires in their
    prime; past the decline turn it ramps fast, and faster for players
    whose game has already fallen off."""
    turn = decline_age(p)
    if p.age < turn + 2:
        return 0.0
    prob = 0.22 * (p.age - (turn + 1))
    if overall(p) < 48.0:
        prob += 0.18  # the tier-2 grind stops being worth it
    if "veteran" in p.personality_tags:
        prob -= 0.08  # lifers squeeze out one more season
    return float(min(0.95, max(0.0, prob)))


# ---------------------------------------------------------------------------
# Scout assessment


def stars(value: float) -> float:
    """1-99 ability → 0.5-5.0 stars in halves."""
    return max(0.5, min(5.0, round(value / 10.0) / 2.0))


def scout_report(gs, p: Player, progress: float) -> dict:
    """Banded CA/PA view + progressively revealed traits. The band CENTER
    is a stable per-player offset (scouts have priors, not dice), and the
    band tightens as progress rises."""
    ca, pa = overall(p), potential_of(p)
    # A better analyst doesn't just read faster (progress) — they read more
    # ACCURATELY: an elite analyst shrinks the residual floor width and the
    # fixed per-player bias, so their bands hug the truth tighter at the same
    # progress. With no analyst the multiplier is 1.0 and this is exactly the
    # pre-existing report, so default scouting is unchanged.
    from esports_sim.manager import staff

    sm = staff.scout_multiplier(gs)  # 1.0 (none) .. ~1.9 (elite)
    width_ca = 22.0 * (1.0 - progress) + 4.0 / sm
    width_pa = width_ca + 8.0
    # Stable offset in [-0.35, +0.35] of width — truth is always in-band.
    off = ((_h(gs.seed, p.id, "scoutoff") % 1000) / 1000.0 - 0.5) * (0.7 / sm)
    ca_lo = max(1.0, ca + off * width_ca - width_ca / 2.0)
    pa_lo = max(ca_lo, pa + off * width_pa - width_pa / 2.0)
    known_n = int(round(progress * len(p.personality_tags) + 1e-9))
    known = sorted(p.personality_tags)[:known_n]
    strengths = sorted(p.attributes, key=lambda a: -p.attributes[a])[:2]
    weaknesses = sorted(p.attributes, key=lambda a: p.attributes[a])[:2]
    return {
        "player_id": p.id,
        "handle": p.handle,
        "age": p.age,
        "role": str(p.role),
        "playstyle": str(p.playstyle),
        "ca_stars": [stars(ca_lo), stars(ca_lo + width_ca)],
        "pa_stars": [stars(pa_lo), stars(pa_lo + width_pa)],
        "traits": [
            {"id": t, "blurb": TRAITS.get(t, {}).get("blurb", "")} for t in known
        ],
        "traits_hidden": max(0, len(p.personality_tags) - known_n),
        "strengths": strengths if progress >= 0.35 else [],
        "weaknesses": weaknesses if progress >= 0.6 else [],
        "progress": round(progress, 2),
    }
