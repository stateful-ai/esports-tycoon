"""Player development: potential, career curves, traits, and scouting.

Potential is an upside forecast, not a hard cap.  Every player has a hidden,
stable career curve which controls when growth arrives, how long their peak
lasts, how volatile the path is, and how much of the forecast they naturally
realise.  Context (mentors, close duos, morale, confidence, and the wider
locker room) can unlock more of that upside and can even carry Current Ability
past the original forecast.

Scouts never see the hidden curve or a final maximum.  They see outcome bands
which remain uncertain even with a complete book.

Determinism: every derived number comes from blake2 hashes of stable ids
or from the campaign RngTree — never Python's salted hash(), never
wall-clock anything.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

from esports_sim.schemas import Player, DevelopmentCurveModel
from esports_sim.manager import role_fit

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


@dataclass(frozen=True)
class DevelopmentCurve:
    """Hidden shape of one career, derived from stable player identity.

    ``growth_peak_age`` is when training is absorbed fastest. ``decline_age``
    is the end of the player's competitive peak, not their maximum possible
    rating. ``realization`` is how much of the headline potential tends to be
    reached without an unusually good environment.
    """

    archetype: str
    growth_peak_age: int
    growth_width: float
    peak_years: int
    decline_age: int
    realization: float
    volatility: float


def _unit(*parts) -> float:
    return (_h(*parts) % 10_000) / 10_000.0


def development_curve(p: Player) -> DevelopmentCurve:
    """Return a deterministic, hidden career curve for ``p``.

    IDs, rather than generation order, own the curve. Old saves therefore gain
    the system without a schema migration and the same player keeps the same
    career shape through transfers and save/load cycles.
    """
    if p.development_curve is not None:
        dc = p.development_curve
        return DevelopmentCurve(
            archetype=dc.archetype,
            growth_peak_age=dc.growth_peak_age,
            growth_width=dc.growth_width,
            peak_years=dc.peak_years,
            decline_age=dc.decline_age,
            realization=dc.realization,
            volatility=dc.volatility,
        )

    shape = _unit(p.id, "devcurve", "shape")
    timing = _unit(p.id, "devcurve", "timing")
    length = _unit(p.id, "devcurve", "length")
    if shape < 0.22:
        archetype, peak, width = "flash", 18 + round(2 * timing), 1.5 + timing
        peak_years = 1 + round(2 * length)
    elif shape < 0.48:
        archetype, peak, width = "early", 20 + round(2 * timing), 2.2 + timing
        peak_years = 2 + round(2 * length)
    elif shape < 0.78:
        archetype, peak, width = "steady", 22 + round(2 * timing), 3.0 + 1.2 * timing
        peak_years = 4 + round(2 * length)
    else:
        archetype, peak, width = "late", 24 + round(2 * timing), 3.8 + 1.2 * timing
        peak_years = 3 + round(3 * length)

    # Traits are visible clues, not the whole answer. They pin the broad turn
    # while the hidden width, realization, volatility, and peak duration still
    # distinguish two prodigies or two late bloomers.
    tagged_turn = trait_value(p, "decline_age", 0)
    if "prodigy" in p.personality_tags:
        archetype, peak, peak_years = "flash", min(peak, 20), min(peak_years, 2)
    elif "late_bloomer" in p.personality_tags:
        archetype, peak, peak_years = "late", max(peak, 24), max(peak_years, 4)
    decline = int(tagged_turn) if tagged_turn else max(24, peak + 4 + peak_years)

    # Skew toward plausible success while leaving a meaningful population of
    # high-upside players who never realise the headline number.
    realization_roll = _unit(p.id, "devcurve", "realization")
    realization = 0.62 + 0.38 * math.sqrt(realization_roll)
    volatility = 0.78 + 0.48 * _unit(p.id, "devcurve", "volatility")
    return DevelopmentCurve(
        archetype=archetype,
        growth_peak_age=int(peak),
        growth_width=round(width, 2),
        peak_years=int(peak_years),
        decline_age=decline,
        realization=round(realization, 3),
        volatility=round(volatility, 3),
    )


def initialize_player_seed_variance(p: Player, campaign_seed: int) -> None:
    """Initialize deterministic potential variance and hidden curve based on campaign seed."""
    base_pa = p.potential if p.potential > 0.0 else potential_of(p)

    if p.age <= 21 or "prodigy" in p.personality_tags or "rookie" in p.personality_tags:
        max_swing = 6.0
    elif p.age >= 26 or "veteran" in p.personality_tags:
        max_swing = 0.0
    else:
        max_swing = 6.0 * (26.0 - p.age) / (26.0 - 21.0)

    swing = 0.0
    if max_swing > 0.0:
        pot_seed = _h(campaign_seed, p.id, "potential_swing")
        rng_pot = np.random.default_rng(pot_seed)
        swing = rng_pot.uniform(-max_swing, max_swing)

    p.potential = float(max(overall(p), np.round(np.clip(base_pa + swing, overall(p), 99.0), 1)))

    is_veteran = p.age >= 26 or "veteran" in p.personality_tags
    if is_veteran:
        player_curve_seed = _h(p.id, "curve")
    else:
        player_curve_seed = _h(campaign_seed, p.id, "curve")

    p.dev_seed = player_curve_seed

    rng_curve = np.random.default_rng(player_curve_seed)
    shape = rng_curve.uniform(0.0, 1.0)
    timing = rng_curve.uniform(0.0, 1.0)
    length = rng_curve.uniform(0.0, 1.0)
    decline_roll = rng_curve.uniform(0.0, 1.0)
    realization_roll = rng_curve.uniform(0.0, 1.0)
    volatility_roll = rng_curve.uniform(0.0, 1.0)

    if shape < 0.22:
        archetype, peak, width = "flash", 18 + round(2 * timing), 1.5 + timing
        peak_years = 1 + round(2 * length)
    elif shape < 0.48:
        archetype, peak, width = "early", 20 + round(2 * timing), 2.2 + timing
        peak_years = 2 + round(2 * length)
    elif shape < 0.78:
        archetype, peak, width = "steady", 22 + round(2 * timing), 3.0 + 1.2 * timing
        peak_years = 4 + round(2 * length)
    else:
        archetype, peak, width = "late", 24 + round(2 * timing), 3.8 + 1.2 * timing
        peak_years = 3 + round(3 * length)

    tagged_turn = trait_value(p, "decline_age", 0)
    if "prodigy" in p.personality_tags:
        archetype, peak, peak_years = "flash", min(peak, 20), min(peak_years, 2)
    elif "late_bloomer" in p.personality_tags:
        archetype, peak, peak_years = "late", max(peak, 24), max(peak_years, 4)
    decline = int(tagged_turn) if tagged_turn else max(24, peak + 4 + peak_years)

    realization = 0.62 + 0.38 * math.sqrt(realization_roll)
    volatility = 0.78 + 0.48 * volatility_roll

    p.development_curve = DevelopmentCurveModel(
        archetype=archetype,
        growth_peak_age=int(peak),
        growth_width=round(width, 2),
        peak_years=int(peak_years),
        decline_age=decline,
        realization=round(realization, 3),
        volatility=round(volatility, 3),
    )


def assign_development_curve(p: Player, rng: np.random.Generator) -> None:
    """Generate and assign the development curve using the passed rng."""
    shape = float(rng.uniform(0.0, 1.0))
    timing = float(rng.uniform(0.0, 1.0))
    length = float(rng.uniform(0.0, 1.0))
    decline_roll = float(rng.uniform(0.0, 1.0))
    realization_roll = float(rng.uniform(0.0, 1.0))
    volatility_roll = float(rng.uniform(0.0, 1.0))

    if shape < 0.22:
        archetype, peak, width = "flash", 18 + round(2 * timing), 1.5 + timing
        peak_years = 1 + round(2 * length)
    elif shape < 0.48:
        archetype, peak, width = "early", 20 + round(2 * timing), 2.2 + timing
        peak_years = 2 + round(2 * length)
    elif shape < 0.78:
        archetype, peak, width = "steady", 22 + round(2 * timing), 3.0 + 1.2 * timing
        peak_years = 4 + round(2 * length)
    else:
        archetype, peak, width = "late", 24 + round(2 * timing), 3.8 + 1.2 * timing
        peak_years = 3 + round(3 * length)

    tagged_turn = trait_value(p, "decline_age", 0)
    if "prodigy" in p.personality_tags:
        archetype, peak, peak_years = "flash", min(peak, 20), min(peak_years, 2)
    elif "late_bloomer" in p.personality_tags:
        archetype, peak, peak_years = "late", max(peak, 24), max(peak_years, 4)
    decline = int(tagged_turn) if tagged_turn else max(24, peak + 4 + peak_years)

    realization = 0.62 + 0.38 * math.sqrt(realization_roll)
    volatility = 0.78 + 0.48 * volatility_roll

    p.development_curve = DevelopmentCurveModel(
        archetype=archetype,
        growth_peak_age=int(peak),
        growth_width=round(width, 2),
        peak_years=int(peak_years),
        decline_age=decline,
        realization=round(realization, 3),
        volatility=round(volatility, 3),
    )


def decline_age(p: Player) -> int:
    return development_curve(p).decline_age


def curve_growth_multiplier(p: Player) -> float:
    """How strongly this player absorbs development at their current age.

    The broad bell gives early surges, steady builders, and late arrivals
    genuinely different paths. A stable age-specific pulse makes progress
    lumpy without consuming RNG or changing when other campaign draws happen.
    """
    curve = development_curve(p)
    distance = abs(p.age - curve.growth_peak_age)
    bell = math.exp(-0.5 * (distance / curve.growth_width) ** 2)
    if p.age <= curve.growth_peak_age:
        shape = 0.45 + 0.95 * bell
    elif p.age < curve.decline_age:
        shape = 0.22 + 0.78 * bell
    else:
        shape = 0.08
    pulse = 0.78 + 0.44 * _unit(p.id, "devcurve", "year", p.age)
    return round(float(np.clip(shape * pulse * curve.volatility, 0.08, 1.65)), 3)


def curve_decline_multiplier(p: Player) -> float:
    """Decline severity: short peaks fade faster, long peaks erode slowly."""
    curve = development_curve(p)
    longevity = float(np.clip(1.35 - curve.peak_years * 0.10, 0.65, 1.25))
    year_pulse = 0.85 + 0.30 * _unit(p.id, "decline", p.age)
    return round(longevity * year_pulse, 3)


_REALIZATION_FLOOR = 45.0


def natural_potential(p: Player) -> float:
    """Likely peak in an ordinary environment, deliberately hidden from UI."""
    pa = potential_of(p)
    realised = (
        _REALIZATION_FLOOR
        + (pa - _REALIZATION_FLOOR) * development_curve(p).realization
    )
    return round(float(max(overall(p), min(99.0, realised))), 2)


def contextual_ceiling_bonus(
    p: Player,
    *,
    mentor_strength: float = 0.0,
    duo_affinity: float = 50.0,
    team_chemistry: float = 70.0,
) -> float:
    """Extra development headroom supplied by a player's environment.

    This is intentionally capable of carrying ability past headline potential:
    potential is what scouts thought the player might become, while a great
    mentor, trusted duo, and thriving player can produce an outlier career.
    """
    morale = max(0.0, (p.morale - 70.0) / 30.0) * 3.0
    belief = max(0.0, (p.confidence - 55.0) / 40.0) * 1.5
    form = max(0.0, (p.form - 55.0) / 45.0) * 0.8
    mentor = float(np.clip(mentor_strength, 0.0, 1.0)) * 2.5
    duo = max(0.0, (duo_affinity - 75.0) / 25.0) * 2.7
    room = max(0.0, (team_chemistry - 72.0) / 28.0) * 1.2
    total = morale + belief + form + mentor + duo + room
    return round(float(np.clip(total, 0.0, 10.0)), 2)


def development_ceiling(p: Player, attr_id: str, support_bonus: float = 0.0) -> float:
    """Reachable skill level now: hidden realization plus contextual upside."""
    cur = p.attr(attr_id)
    full = raw_skill_potential(p, attr_id)
    realised = (
        _REALIZATION_FLOOR
        + (full - _REALIZATION_FLOOR) * development_curve(p).realization
    )
    return round(float(min(99.0, max(cur, realised + max(0.0, support_bonus)))), 2)


def dev_multiplier(p: Player, support_bonus: float = 0.0) -> float:
    """Development speed from reachable headroom, curve, and traits."""
    targets = [development_ceiling(p, a, support_bonus) for a in p.attributes]
    target = sum(targets) / len(targets) if targets else natural_potential(p)
    gap = target - overall(p)
    gap_mult = float(np.clip(gap / 15.0, 0.08, 1.5))
    return gap_mult * trait_value(p, "dev_mult", 1.0)


# Ceilings COMPRESS toward the top instead of clipping at a hard cap, so a
# realistic few players are generational (5-star) rather than a pile-up at
# the cap. The knee/slope only reshape the growth HEADROOM above the knee;
# current ability is never touched, and the squash is applied AFTER the rng
# draws, so the draw sequence — and every other subsystem's determinism —
# is untouched. Only ceiling VALUES move.
_PA_KNEE = 82.0
_PA_SLOPE = 0.55
_PA_CAP = 95.0


def _soft_cap_potential(raw: float) -> float:
    """Smoothly compress a raw ceiling above the knee toward an asymptotic
    cap, so top-end talent spreads out rather than clipping at one value."""
    if raw <= _PA_KNEE:
        return raw
    return min(_PA_CAP, _PA_KNEE + (raw - _PA_KNEE) * _PA_SLOPE)


def potential_of(p: Player) -> float:
    """PA with a deterministic fallback for players authored before the
    field existed: ceiling grows with youth, seeded by player id."""
    if p.potential > 0:
        return p.potential
    ca = overall(p)
    youth = max(0, 25 - p.age)
    bonus = (_h(p.id, "pa") % 1000) / 1000.0  # 0..1, stable per player
    raw = ca + youth * (1.2 + 2.0 * bonus)
    return round(float(max(ca, _soft_cap_potential(raw))), 1)


def assign_potential(p: Player, rng: np.random.Generator) -> None:
    """Roll generous upside at generation time.

    More young players can plausibly become stars than will actually do so;
    their hidden realization and career environment decide which forecasts
    become careers.
    """
    ca = overall(p)
    youth = max(0, 25 - p.age)
    raw = ca + youth * rng.uniform(1.1, 3.7) + rng.normal(0, 2.8)
    # Dream-upside texture is ID-derived so potential assignment consumes the
    # exact same two RNG draws as before; contract/personality generation later
    # on the shared stream must not shift when this distribution changes.
    if p.age <= 21 and _unit(p.id, "dream_upside") < 0.32:
        raw += 3.0 + 6.0 * _unit(p.id, "dream_upside", "size")
    p.potential = float(np.ceil(max(ca, _soft_cap_potential(raw)) * 10.0) / 10.0)


# ---------------------------------------------------------------------------
# Per-skill ceilings (per-attribute Potential Ability). The scalar `potential`
# is the OVERALL ceiling; each attribute has its OWN ceiling that varies around
# it (some players cap higher on aim than utility, and vice-versa). An absent
# skill_potential entry derives a stable per-skill ceiling from the scalar PA
# plus a blake2 spread, so a save with an empty map behaves as before EXCEPT
# that an attribute now plateaus at its own ceiling instead of drifting toward
# the old flat 95 — which is exactly what makes PA a real ceiling. Mentorship
# and monumental moments WRITE entries to raise specific skills.

_SKILL_SPREAD = 13.0  # peak-to-peak spread of the derived per-skill ceilings


def raw_skill_potential(p: Player, attr_id: str) -> float:
    """Unfloored possibility for one skill (hidden forecast input)."""
    stored = p.skill_potential.get(attr_id)
    if stored is not None:
        return float(min(99.0, max(0.0, stored)))
    pa = potential_of(p)
    spread = ((_h(p.id, "skillpa", attr_id) % 1000) / 1000.0 - 0.5) * _SKILL_SPREAD
    return float(min(99.0, max(0.0, pa + spread)))


def skill_ceiling(p: Player, attr_id: str) -> float:
    """Headline skill potential, floored at demonstrated current ability.

    Kept as the public compatibility entry point. Growth uses
    :func:`development_ceiling`, which applies hidden realization and support.
    """
    return float(max(p.attr(attr_id), raw_skill_potential(p, attr_id)))


def skill_potential_projection(p: Player, attr_id: str) -> tuple[float, float]:
    """Uncertain outcome band for one skill, including supported upside."""
    cur = p.attr(attr_id)
    raw = raw_skill_potential(p, attr_id)
    curve = development_curve(p)
    realised = _REALIZATION_FLOOR + (raw - _REALIZATION_FLOOR) * curve.realization
    uncertainty = (
        3.0
        + (1.0 - curve.realization) * 8.0
        + abs(curve.volatility - 1.0) * 4.0
    )
    lo = max(cur, realised - uncertainty)
    hi = min(99.0, max(cur, raw + uncertainty * 0.5 + 3.0))
    return round(lo, 1), round(hi, 1)


def _raise_toward(value: float, delta: float, cap: float, softness: float) -> float:
    """Monotonic raise of `value` by up to `delta`, diminishing as it nears
    `cap`. Never drops below `value`, never exceeds `cap` — so re-applying it
    can only ever inch a ceiling up, which keeps PA moves order-independent."""
    if delta <= 0.0:
        return value
    room = max(0.0, cap - value)
    return round(min(cap, value + delta * (room / (room + softness))), 2)


def adjust_potential(p: Player, delta: float, attrs=None) -> float:
    """The SECOND writer of potential (assign_potential is the first). Raise the
    scalar forecast by `delta` (already scaled by the caller), diminishing near
    the cap without ratcheting it up to current ability, and optionally lift it into
    specific skill ceilings. Returns the applied scalar delta. Deterministic —
    no rng; the magnitude is the caller's responsibility."""
    if delta <= 0.0:
        return 0.0
    old = potential_of(p)
    new = round(min(99.0, _raise_toward(old, delta, _PA_CAP, 6.0)), 1)
    p.potential = new
    if attrs:
        for a in sorted(set(attrs)):
            base = skill_ceiling(p, a)
            p.skill_potential[a] = round(
                min(99.0, max(p.attr(a), _raise_toward(base, delta, 99.0, 8.0))), 1
            )
    return round(new - old, 2)


def _moment_scale(p: Player) -> float:
    """How plastic a player's ceiling is to a career moment: young players with
    room revise up hard; players at or past their peak barely move."""
    return float(np.clip((27 - p.age) / 9.0, 0.0, 1.0))  # 18 -> 1.0, 27+ -> 0


def moment_potential_bump(p: Player, base: float, *, skills: int = 2) -> float:
    """Apply a monumental-moment ceiling revision: `base` points scaled down by
    age, raising the scalar ceiling and the player's top current strengths (the
    skills they just proved). Returns the applied scalar delta (0 if capped/old
    enough that it rounds away)."""
    delta = base * _moment_scale(p)
    if delta < 0.05:
        return 0.0
    top = sorted(p.attributes, key=lambda a: (-p.attributes[a], a))[:skills]
    return adjust_potential(p, delta, attrs=top)


# ---------------------------------------------------------------------------
# Potential as a projection band. Even a full scout book / your own academy
# never resolves the ceiling to an exact number — the future is a projection.
# The band narrows as a player ages toward their ceiling (a settled veteran is
# nearly known, a teenager a wide range) and, for a scouted rival, as scouting
# progress rises. A stable per-player anchor makes some reads symmetrical and
# others put the hidden ceiling at either edge. Repeated looks stay consistent
# without implying that uncertainty is always evenly distributed.

_PROJ_FLOOR = 3.0  # irreducible outcome uncertainty, even for a full book
_PERFORMANCE_COACH_MAX_TIGHTEN = 0.45


def potential_projection(
    p: Player,
    progress: float = 1.0,
    own: bool = False,
    performance_coach_quality: float | None = None,
) -> tuple[float, float]:
    """A peak-outcome estimate which never collapses to a known maximum.

    A strong performance coach tightens only an own-roster read. The coach
    does not move hidden potential; they reduce the uncertainty around it.
    """
    pa = potential_of(p)
    ca = overall(p)
    curve = development_curve(p)
    youth = float(np.clip((26 - p.age) / 8.0, 0.0, 1.0))
    gap = max(0.0, pa - ca)
    curve_uncertainty = (
        (1.0 - curve.realization) * 9.0
        + abs(curve.volatility - 1.0) * 5.0
    )
    half = _PROJ_FLOOR + youth * 7.0 + min(gap, 18.0) * 0.20 + curve_uncertainty
    if not own:
        half += (1.0 - float(np.clip(progress, 0.0, 1.0))) * 10.0
    elif performance_coach_quality is not None:
        # Quality below 40 supplies no extra insight. From 40 to 100 the read
        # tightens smoothly, reaching 45% narrower at the very top end.
        precision = float(np.clip(
            (performance_coach_quality - 40.0) / 60.0, 0.0, 1.0
        ))
        half *= 1.0 - _PERFORMANCE_COACH_MAX_TIGHTEN * precision

    # Stable player identity owns the shape: centered, true value at the
    # upper edge, or true value at the lower edge. This is random-looking but
    # remains byte-identical across save/load and repeated reads.
    anchor = _h(p.id, "pa-window-anchor") % 3
    if anchor == 0:
        lo, hi = pa - half, pa + half
    elif anchor == 1:
        lo, hi = pa - 2.0 * half, pa
    else:
        lo, hi = pa, pa + 2.0 * half
    lo = max(1.0, lo)
    hi = min(99.0, hi)
    return round(lo, 1), round(hi, 1)


def curve_read(p: Player) -> str:
    """Qualitative scouting clue without exposing exact hidden curve values."""
    curve = development_curve(p)
    reads = {
        "flash": "development may arrive in an early burst; the peak could be brief",
        "early": "looks likely to mature early, but sustaining the peak is uncertain",
        "steady": "projects as a gradual builder with a potentially durable peak",
        "late": "may need a long runway; the best years could arrive late",
    }
    return reads[curve.archetype]


# ---------------------------------------------------------------------------
# Mentorship: a manager pairs a young player with a stronger, older teammate.
# Validity + the flat growth-rate boost live with training/campaign; the
# CEILING-raising effect and the hidden mentor_skill that gates it live here.
# gs.mentorships is empty in hands-off sims, so every mentorship function is a
# no-op there and the balance gates never see it.

MENTOR_MIN_SKILL = 30.0     # below this a veteran teaches too little to matter
MENTOR_CEILING_STEP = 0.18  # weekly ceiling nudge (before skill/youth scaling)


def mentorship_valid(gs, protege_id: str, mentor_id: str) -> bool:
    """A mentorship holds when both share a roster and the mentor is the older,
    higher-ability of the pair (a senior guiding a junior)."""
    if protege_id == mentor_id:
        return False
    pro, men = gs.players.get(protege_id), gs.players.get(mentor_id)
    if pro is None or men is None:
        return False
    same_team = any(
        {protege_id, mentor_id} <= set(t.player_ids) for t in gs.teams.values()
    )
    return same_team and men.age > pro.age and overall(men) > overall(pro)


def mentor_skill(p: Player, seasons: int = 0) -> float:
    """Hidden teaching ability (0-99). Grows with AGE and EXPERIENCE, so young
    players floor low; a small stable blake2 latent leaves room for the rare
    young natural teacher, game-IQ/comms help, and locker-room traits shade it
    up. Pure function of the player + a seasons-played count — no rng."""
    latent = 6.0 + (_h(p.id, "mentor") % 1000) / 1000.0 * 16.0        # ~6..22
    age_term = float(np.clip((p.age - 22) / 8.0, 0.0, 1.0)) * 44.0    # 0..44
    exp_term = float(np.clip(seasons / 6.0, 0.0, 1.0)) * 24.0         # 0..24
    iq = (p.attr("game_sense") + p.attr("comms_quality")) / 2.0
    iq_term = float(np.clip((iq - 50.0) / 45.0, 0.0, 1.0)) * 12.0     # 0..12
    tag_term = sum(
        TRAITS[t].get("mentor_bonus", 0.0)
        for t in p.personality_tags if t in TRAITS
    )
    return round(
        float(np.clip(latent + age_term + exp_term + iq_term + tag_term, 0.0, 99.0)),
        1,
    )


def _team_of(gs, pid: str) -> str:
    return next((t for t in sorted(gs.teams) if pid in gs.teams[t].player_ids), "")


def apply_mentorship_growth(gs) -> list[dict]:
    """Weekly: each valid, manager-set mentorship slowly raises the protege's
    ceiling on the MENTOR's best skills, toward (never past) the mentor's own
    level, gated by the mentor's hidden mentor_skill and the protege's youth.
    A great aimer lifts a young player's aim ceiling specifically. Also nudges
    the scalar ceiling so the headline projection tracks the skill lift.
    Deterministic (no rng); no-op when gs.mentorships is empty."""
    if not gs.mentorships:
        return []
    out: list[dict] = []
    for pid in sorted(gs.mentorships):
        mentor_id = gs.mentorships[pid]
        if not mentorship_valid(gs, pid, mentor_id):
            continue
        pro, men = gs.players[pid], gs.players[mentor_id]
        
        # Check practice week veteran-rookie mentorship breakthrough
        if men.age >= 25 and pro.age <= 20:
            from esports_sim.rng.tree import RngTree
            rng = RngTree(gs.seed).derive("season", gs.season, "week", gs.week, "mentorship", pid)
            team_id = _team_of(gs, pid)
            week_fixtures = gs.fixtures_for_week()
            is_practice_week = not any(f.team_a == team_id or f.team_b == team_id for f in week_fixtures)
            
            breakthrough_chance = 0.30 if is_practice_week else 0.05
            if rng.random() < breakthrough_chance:
                roll = rng.random()
                if roll < 0.5:
                    bump = float(rng.uniform(1.0, 2.0))
                    adjust_potential(pro, bump)
                else:
                    pos_tags = ["workhorse", "student", "calm", "reliable", "team_player", "patient", "analytical", "grinder"]
                    candidate_tags = [t for t in pos_tags if t in men.personality_tags and t not in pro.personality_tags]
                    if candidate_tags:
                        candidate_tags.sort()
                        chosen_tag = rng.choice(candidate_tags)
                        pro.personality_tags.append(chosen_tag)
                        pro.personality_tags.sort()
                        
                        if chosen_tag == "calm" and "hot_head" in pro.personality_tags:
                            pro.personality_tags.remove("hot_head")
                        if chosen_tag == "reliable" and "volatile" in pro.personality_tags:
                            pro.personality_tags.remove("volatile")
                    else:
                        bump = float(rng.uniform(1.0, 2.0))
                        adjust_potential(pro, bump)

        cs = gs.career_stats.get(mentor_id)
        msk = mentor_skill(men, cs.seasons if cs else 0)
        if msk < MENTOR_MIN_SKILL:
            continue
        youth = float(np.clip((25 - pro.age) / 7.0, 0.1, 1.0))
        best = sorted(men.attributes, key=lambda a: (-men.attributes[a], a))[:2]
        total_step, lifted = 0.0, []
        for a in best:
            mentor_level = men.attr(a)
            cap = mentor_level - max(0.0, (99.0 - msk) * 0.15)  # skill gates reach
            cur_ceil = skill_ceiling(pro, a)
            if cap <= cur_ceil:
                continue
            step = MENTOR_CEILING_STEP * (msk / 99.0) * youth
            new_ceil = round(min(cap, cur_ceil + step), 2)
            pro.skill_potential[a] = new_ceil
            total_step += new_ceil - cur_ceil
            lifted.append(a)
        if lifted:
            adjust_potential(pro, total_step * 0.4)  # headline tracks the lift
            out.append(
                {
                    "team_id": _team_of(gs, pid),
                    "player_id": pid,
                    "mentor_id": mentor_id,
                    "skills": lifted,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Earned traits: unlocked once from settled, deterministic career state at the
# offseason (rng-free, sorted iteration). Guarded by tag membership so each
# fires once. Applied to EVERY org (AI parity, like dev events); the news line
# goes only to the owning human. Some unlocks carry a ceiling revision.

_LATE_BLOOM_GAIN = 2.5   # CA gained this season to earn the late-bloomer streak
_CLUTCH_GENE_BAR = 22    # career clutch rounds to earn the clutch gene


def _add_tag(p: Player, tag: str) -> None:
    p.personality_tags = sorted({*p.personality_tags, tag})


def offseason_trait_unlocks(gs) -> list[dict]:
    """Unlock earned traits. Call at the offseason BEFORE aging (so age is the
    just-played age and season_start_ca still holds this season's baseline)."""
    out: list[dict] = []
    for tid in sorted(gs.teams):
        for p in sorted(gs.roster(tid), key=lambda q: q.id):
            tags = p.personality_tags
            unlocked: list[tuple[str, str]] = []
            # veteran: a long career earns the badge (and feeds mentor_skill).
            if p.age >= 30 and "veteran" not in tags and "rookie" not in tags:
                _add_tag(p, "veteran")
                unlocked.append(("veteran", "a veteran's presence"))
            # late_bloomer: still climbing in their mid-to-late twenties.
            if (
                24 <= p.age <= 29
                and "late_bloomer" not in p.personality_tags
                and "prodigy" not in p.personality_tags
                and p.id in gs.season_start_ca
                and overall(p) - gs.season_start_ca[p.id] >= _LATE_BLOOM_GAIN
            ):
                _add_tag(p, "late_bloomer")
                adjust_potential(p, 2.0)  # a later, higher peak
                unlocked.append(("late_bloomer", "a late-bloomer streak"))
            # clutch_gene: a career of stepping up a man down.
            cs = gs.career_stats.get(p.id)
            if cs and cs.clutches >= _CLUTCH_GENE_BAR and "clutch_gene" not in p.personality_tags:
                _add_tag(p, "clutch_gene")
                adjust_potential(p, 1.0, attrs=["clutch_factor"])
                unlocked.append(("clutch_gene", "the clutch gene"))
            for trait, phrase in unlocked:
                out.append(
                    {"team_id": tid, "player_id": p.id, "kind": "trait_unlock", "trait": trait}
                )
                if gs.is_human(tid):
                    gs.push_private_news(
                        f"{p.handle} unlocks a new trait: {phrase}.", owner=tid
                    )
    return out


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
# Weekly development events: the random texture of a career. Applied to
# EVERY org's roster (AI parity — rivals' prospects break out and slump
# too); only human-owned teams get the news line. Drawn from a dedicated
# rng stream (campaign label "devevents") so adding/removing events never
# shifts any other subsystem's draws.

DEV_EVENT_PROB = 0.05  # per player per week

# Substrings that identify a dev-event news line (the inbox's detector —
# keep in sync with the headlines in _fire_event below AND the mental
# events in weekly_mental_events).
DEV_EVENT_MARKERS = [
    "breakthrough week",
    "is in a slump",
    "tweaks a wrist",
    "running on fumes",
    "does numbers online",
    "gets into it with fans",
    "under their wing",
    "grinding.",
    "is spiralling",
    "is on a heater",
    "unlocks a new trait",
    "badge.",
]

_CATEGORY_ATTRS = {
    "mechanical": ["aim_precision", "aim_reactivity", "movement"],
    "tactical": ["game_sense", "utility_usage", "positioning"],
    "mental": ["clutch_factor", "tilt_resistance", "composure"],
}


def _clamp_stat(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(min(hi, max(lo, v)), 1)


def _bump_attr(p: Player, attr_id: str, amount: float) -> None:
    cur = p.attr(attr_id)
    support = contextual_ceiling_bonus(p)
    ceil = development_ceiling(p, attr_id, support)
    headroom = max(0.0, (max(95.0, ceil) - cur) / 45.0)
    p.attributes[attr_id] = round(min(cur + amount * headroom, max(cur, ceil)), 2)


def _weakest_category(p: Player) -> str:
    return min(
        sorted(_CATEGORY_ATTRS),
        key=lambda c: sum(p.attr(a) for a in _CATEGORY_ATTRS[c]),
    )


def weekly_dev_events(gs, rng) -> list[dict]:
    """Roll development events for every rostered player. Returns the
    events that fired ({team_id, player_id, kind, headline}) so the inbox
    and the social layer can surface them; effects are applied here."""
    out: list[dict] = []
    for tid in sorted(gs.teams):
        for p in sorted(gs.roster(tid), key=lambda q: q.id):
            if rng.random() >= DEV_EVENT_PROB:
                continue
            kind, headline = _fire_event(gs, tid, p, rng)
            out.append(
                {"team_id": tid, "player_id": p.id, "kind": kind, "headline": headline}
            )
            if gs.is_human(tid):
                gs.push_private_news(headline, owner=tid)
    return out


def _fire_event(gs, tid: str, p: Player, rng) -> tuple[str, str]:
    """Pick and apply one event. An 'intense' training plan adds burnout
    to the table — the risk that pays for extra growth — unless the player
    has opted out to rest that week."""
    roll = rng.random()
    if p.dev_focus != "rest" and p.training_intensity == "intense" and roll < 0.22:
        p.stamina = _clamp_stat(p.stamina - 30.0)
        p.morale = _clamp_stat(p.morale - 8.0)
        p.confidence = _clamp_stat(p.confidence - 6.0, 5.0, 95.0)
        p.form = _clamp_stat(p.form - 6.0)
        return "burnout", (
            f"{p.handle} is running on fumes — the intense schedule bites."
        )
    if roll < 0.18:
        mult = dev_multiplier(p)
        for a in _CATEGORY_ATTRS[_weakest_category(p)]:
            _bump_attr(p, a, float(rng.uniform(0.8, 1.4)) * mult)
        p.confidence = _clamp_stat(p.confidence + 6.0, 5.0, 95.0)
        return "breakthrough", (
            f"{p.handle} has a breakthrough week — something clicked in practice."
        )
    if roll < 0.33:
        p.form = _clamp_stat(p.form - 8.0)
        p.confidence = _clamp_stat(p.confidence - 7.0, 5.0, 95.0)
        return "slump", f"{p.handle} is in a slump — coaches see hesitation."
    if roll < 0.45:
        p.stamina = _clamp_stat(p.stamina - 35.0)
        p.form = _clamp_stat(p.form - 4.0)
        return "minor_injury", (
            f"{p.handle} tweaks a wrist in practice — the physio is monitoring."
        )
    if roll < 0.60:
        p.confidence = _clamp_stat(p.confidence + 5.0, 5.0, 95.0)
        p.morale = _clamp_stat(p.morale + 3.0)
        return "viral_clip", f"A clip of {p.handle} does numbers online."
    if roll < 0.70:
        p.morale = _clamp_stat(p.morale - 6.0)
        p.confidence = _clamp_stat(p.confidence - 4.0, 5.0, 95.0)
        team = gs.teams[tid]
        team.chemistry = _clamp_stat(team.chemistry - 2.0)
        return "drama", f"{p.handle} gets into it with fans online."
    # Mentorship: a veteran takes a young player under their wing; falls
    # back to a solo grind week when the roster has no such pairing.
    vets = [
        q
        for q in gs.roster(tid)
        if q.id != p.id and (q.age >= 27 or "veteran" in q.personality_tags)
    ]
    if p.age <= 22 and vets:
        vet = min(vets, key=lambda q: q.id)
        _bump_attr(p, "game_sense", float(rng.uniform(0.6, 1.0)))
        _bump_attr(p, "composure", float(rng.uniform(0.4, 0.8)))
        p.morale = _clamp_stat(p.morale + 3.0)
        return "mentorship", (
            f"{vet.handle} takes {p.handle} under their wing this week."
        )
    focus = p.dev_focus if p.dev_focus in _CATEGORY_ATTRS else _weakest_category(p)
    _bump_attr(
        p,
        min(_CATEGORY_ATTRS[focus], key=lambda a: p.attr(a)),
        float(rng.uniform(0.5, 0.9)),
    )
    p.stamina = _clamp_stat(p.stamina - 8.0)
    p.morale = _clamp_stat(p.morale + 2.0)
    return "grind", f"{p.handle} stays late every night this week, grinding."


# ---------------------------------------------------------------------------
# Mental momentum across weeks: tilt spirals and heaters. The per-map
# confidence movement (campaign._apply_map_effects) is the smooth signal;
# these are the THRESHOLD events — a player whose belief has already
# cratered keeps unravelling, one riding high keeps hitting. Applied to
# every org (AI parity, like dev events); news lines only to the owning
# human manager. Drawn from a dedicated rng stream (campaign label
# "tilt") so no other subsystem's draws ever shift. The weekly 5%
# confidence regression in training.apply_training is the counterweight
# that keeps spirals from running away (see the snowball gate).

TILT_SPIRAL_PROB = 0.30  # per week, for a player under both thresholds
HEATER_PROB = 0.25  # per week, for a player over both thresholds
_TILT_CONF, _TILT_FORM = 30.0, 45.0
_HEAT_CONF, _HEAT_FORM = 72.0, 58.0


def weekly_mental_events(gs, rng) -> list[dict]:
    """Roll spiral/heater events for every rostered player. Exactly one
    rng draw per player (fixed effect sizes — no extra draws on fire), so
    the stream stays stable as rosters churn. Returns the same
    {team_id, player_id, kind, headline} shape as weekly_dev_events so
    the inbox and social layer consume both alike."""
    out: list[dict] = []
    for tid in sorted(gs.teams):
        for p in sorted(gs.roster(tid), key=lambda q: q.id):
            roll = rng.random()
            kind: str | None = None
            headline = ""
            if p.confidence <= _TILT_CONF and p.form <= _TILT_FORM:
                # Fragile players spiral harder; ice-cold ones catch it.
                fragility = (100.0 - p.attr("tilt_resistance")) / 100.0
                if roll < TILT_SPIRAL_PROB * (0.4 + 0.6 * fragility):
                    p.confidence = _clamp_stat(p.confidence - 5.0, 5.0, 95.0)
                    p.form = _clamp_stat(p.form - 3.0)
                    p.morale = _clamp_stat(p.morale - 3.0)
                    kind = "tilt_spiral"
                    headline = (
                        f"{p.handle} is spiralling — the belief is gone "
                        f"and everyone can see it."
                    )
            elif p.confidence >= _HEAT_CONF and p.form >= _HEAT_FORM:
                if roll < HEATER_PROB:
                    p.confidence = _clamp_stat(p.confidence + 3.0, 5.0, 95.0)
                    p.morale = _clamp_stat(p.morale + 2.0)
                    kind = "heater"
                    headline = (
                        f"{p.handle} is on a heater — everything is "
                        f"hitting right now."
                    )
            if kind is None:
                continue
            out.append(
                {"team_id": tid, "player_id": p.id, "kind": kind, "headline": headline}
            )
            if gs.is_human(tid):
                gs.push_private_news(headline, owner=tid)
    return out


# ---------------------------------------------------------------------------
# Scout assessment


# Star tiers are a COARSE quick-glance only — the overall number is the
# source of truth in profiles and the engine. This ladder is anchored to the
# real rating spread (top league CA ~58-90, ceilings ~68-95) so the tiers
# actually differentiate and 5 stars stays a rare, generational badge rather
# than a label half the league carries. A linear value/20 curve clustered
# most pros at "4 stars"; these thresholds spread them 1-5.
_STAR_LADDER = [
    (90.0, 5.0),  # generational (a rare top ceiling; current ability tops ~4.5)
    (87.0, 4.5),  # elite
    (82.0, 4.0),  # star
    (77.0, 3.5),  # high-end starter
    (71.0, 3.0),  # solid pro
    (64.0, 2.5),  # rotation / tier-1 fringe
    (57.0, 2.0),  # tier-2 starter
    (50.0, 1.5),  # project
    (43.0, 1.0),  # raw / depth
]


def stars(value: float) -> float:
    """1-99 ability → 0.5-5.0 stars, as a coarse tier (see _STAR_LADDER)."""
    for lo, s in _STAR_LADDER:
        if value >= lo:
            return s
    return 0.5


def current_ability_projection(p: Player, progress: float = 1.0) -> tuple[float, float]:
    """A scouted range for hidden role/style current ability.

    Unlike raw overall, this is never exposed as an exact number: even a full
    book leaves a small uncertainty margin around role execution and comfort.
    """
    value = role_fit.current_ability(p)
    progress = float(np.clip(progress, 0.0, 1.0))
    width = 14.0 * (1.0 - progress) + 3.0
    off = ((_h(p.id, "role-ca-scout") % 1000) / 1000.0 - 0.5) * 0.35
    lo = max(1.0, value + off * width - width / 2.0)
    hi = min(99.0, lo + width)
    return round(lo, 1), round(hi, 1)


def scout_report(gs, p: Player, progress: float, *, own_player: bool = False) -> dict:
    """Banded CA/PA view + progressively revealed traits. The band CENTER
    is a stable per-player offset (scouts have priors, not dice), and the
    band tightens as progress rises."""
    # Keep the legacy CA star band anchored to public raw overall. The new
    # assignment-aware number is separately hidden behind its own projection.
    ca = overall(p)
    # A better analyst doesn't just read faster (progress) — they read more
    # ACCURATELY: an elite analyst shrinks the residual floor WIDTH, so their
    # bands hug the truth tighter at the same progress. The per-player bias is
    # analyst-independent (see below), which keeps a tighter band strictly
    # NESTED inside a weaker one — the accuracy gain never shifts the band out
    # across a star tier. With no analyst the multiplier is 1.0 and this is
    # exactly the pre-existing report, so default scouting is unchanged.
    from esports_sim.manager import staff

    sm = staff.scout_multiplier(gs)  # 1.0 (none) .. ~1.9 (elite)
    width_ca = 22.0 * (1.0 - progress) + 4.0 / sm
    # Stable offset in [-0.35, +0.35] of width — truth is always in-band, and
    # analyst-independent so a tighter band only shrinks, never shifts.
    off = ((_h(gs.seed, p.id, "scoutoff") % 1000) / 1000.0 - 0.5) * 0.7
    ca_lo = max(1.0, ca + off * width_ca - width_ca / 2.0)
    proj_lo, proj_hi = potential_projection(p, progress, own=False)
    known_n = int(round(progress * len(p.personality_tags) + 1e-9))
    known = sorted(p.personality_tags)[:known_n]
    strengths = sorted(p.attributes, key=lambda a: -p.attributes[a])[:2]
    weaknesses = sorted(p.attributes, key=lambda a: p.attributes[a])[:2]
    # Own-player work interprets a path the manager already observes every day,
    # so guidance unlocks earlier than it does for an external recruitment read.
    # Local import avoids an import-time cycle (training imports development).
    from esports_sim.manager import training

    hint_at = training.SCOUT_GUIDANCE_UNLOCK if own_player else 0.75
    training_hint = training.scouting_guidance(p) if progress >= hint_at else None
    return {
        "player_id": p.id,
        "own_player": own_player,
        "handle": p.handle,
        "age": p.age,
        "role": str(p.role),
        "playstyle": str(p.playstyle),
        "ca_stars": [stars(ca_lo), stars(ca_lo + width_ca)],
        "current_ability_projection": list(current_ability_projection(p, progress)),
        "comfort": round(role_fit.assignment_comfort(p)),
        "pa_stars": [stars(proj_lo), stars(proj_hi)],
        # A numeric ceiling PROJECTION band. Always a range, never a point —
        # the future can't be read exactly — and it never closes below an
        # irreducible floor even at a full book (see potential_projection).
        "pa_projection": [proj_lo, proj_hi],
        "traits": [
            {"id": t, "blurb": TRAITS.get(t, {}).get("blurb", "")} for t in known
        ],
        "traits_hidden": max(0, len(p.personality_tags) - known_n),
        "strengths": strengths if progress >= 0.35 else [],
        "weaknesses": weaknesses if progress >= 0.6 else [],
        # Per-skill ceiling reads (which skills have headroom, which are near
        # their cap) — the deep-book payoff of a per-attribute potential model.
        "ceiling_reads": (
            _ceiling_reads(p, strengths + weaknesses) if progress >= 0.6 else []
        ),
        # Progressive "how they play" intel — each tier unlocks a deeper
        # read (the whole point of deep-diving one player):
        "agent_comfort": (
            [
                {"agent_id": m.agent_id, "mastery": round(m.mastery)}
                for m in sorted(p.agent_pool, key=lambda m: (-m.mastery, m.agent_id))[:3]
            ]
            if progress >= 0.25 else []
        ),
        "style_read": _style_read(p) if progress >= 0.5 else "",
        "mental_read": _mental_read(p) if progress >= 0.75 else "",
        "curve_read": curve_read(p) if progress >= 0.75 else "",
        "training_hint": training_hint,
        "verdict": _scout_verdict(p, ca, progress) if progress >= 0.95 else "",
        "progress": round(progress, 2),
    }


def _ceiling_tier(headroom: float) -> str:
    """Qualitative read of how much room a skill has left to its ceiling."""
    if headroom >= 12.0:
        return "big ceiling"
    if headroom >= 6.0:
        return "room to grow"
    if headroom >= 2.5:
        return "some headroom"
    return "near their cap"


def _ceiling_reads(p: Player, attrs: list[str]) -> list[dict]:
    """For a handful of the player's notable skills, how much ceiling is left
    (deduped, stable order). Reads the per-skill ceiling, so a great-aimer
    prospect shows aim headroom even once their current aim is already good."""
    out, seen = [], set()
    for a in attrs:
        if a in seen:
            continue
        seen.add(a)
        lo, hi = skill_potential_projection(p, a)
        out.append(
            {"attr": a, "read": _ceiling_tier((lo + hi) / 2.0 - p.attr(a))}
        )
    return out


def _style_read(p: Player) -> str:
    """One-line read of HOW a player plays, derived from their true
    attributes (unlocked at 50% book depth — tendencies show before exact
    numbers do)."""
    aggr = (p.attr("aim_reactivity") + p.attr("movement")) / 2.0
    disc = (p.attr("positioning") + p.attr("game_sense")) / 2.0
    if aggr - disc >= 8.0:
        pace = "plays fast and takes space aggressively"
    elif disc - aggr >= 8.0:
        pace = "plays a slow, positional game"
    else:
        pace = "balances aggression with discipline"
    util = p.attr("utility_usage")
    if util >= 68:
        pace += "; excellent utility"
    elif util <= 42:
        pace += "; wastes utility"
    return pace


def _mental_read(p: Player) -> str:
    """The psychological book (75% depth): nerve and tilt under pressure."""
    clutch = p.attr("clutch_factor")
    tilt = p.attr("tilt_resistance")
    nerve = (
        "ice-cold in clutches" if clutch >= 68
        else "shaky when it matters" if clutch <= 45
        else "steady enough late"
    )
    temper = (
        "hard to tilt" if tilt >= 68
        else "tilts off one bad round" if tilt <= 45
        else "average composure"
    )
    return f"{nerve}; {temper}"


def _scout_verdict(p: Player, ca: float, progress: float) -> str:
    """The full book's bottom line (95%+): a precise read of CURRENT ability
    and a PROJECTED ceiling BAND — never a single exact number, because a
    ceiling is a forecast, not a measurement (and it keeps moving)."""
    lo, hi = potential_projection(p, progress, own=False)
    gap = (lo + hi) / 2.0 - ca
    if gap >= 10 and p.age <= 21:
        shape = "a genuine prospect — the ceiling looks real"
    elif gap >= 5:
        shape = "still has another level in them"
    elif ca >= 75:
        shape = "the finished article, and it's good"
    elif p.age >= 27:
        shape = "what you see is what you get"
    else:
        shape = "close to their ceiling"
    return f"reads around {ca:.0f} now; ceiling projects to ~{lo:.0f}-{hi:.0f} — {shape}."
