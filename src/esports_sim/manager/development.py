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
    """Roll PA at generation time (gen.py / rookies). Ceiling-rounded so
    PA >= CA survives the 1-decimal store; soft-capped so few reach the top."""
    ca = overall(p)
    youth = max(0, 25 - p.age)
    raw = ca + youth * rng.uniform(1.0, 3.2) + rng.normal(0, 2)
    p.potential = float(np.ceil(max(ca, _soft_cap_potential(raw)) * 10.0) / 10.0)


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
    headroom = max(0.0, (95.0 - cur) / 45.0)
    p.attributes[attr_id] = round(min(99.0, cur + amount * headroom), 2)


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
    to the table — the risk that pays for the extra growth."""
    roll = rng.random()
    if p.training_intensity == "intense" and roll < 0.22:
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


def scout_report(gs, p: Player, progress: float) -> dict:
    """Banded CA/PA view + progressively revealed traits. The band CENTER
    is a stable per-player offset (scouts have priors, not dice), and the
    band tightens as progress rises."""
    ca, pa = overall(p), potential_of(p)
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
    width_pa = width_ca + 8.0
    # Stable offset in [-0.35, +0.35] of width — truth is always in-band, and
    # analyst-independent so a tighter band only shrinks, never shifts.
    off = ((_h(gs.seed, p.id, "scoutoff") % 1000) / 1000.0 - 0.5) * 0.7
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
        "verdict": _scout_verdict(p, ca, pa) if progress >= 0.95 else "",
        "progress": round(progress, 2),
    }


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


def _scout_verdict(p: Player, ca: float, pa: float) -> str:
    """The full book's bottom line (95%+): a near-exact read."""
    gap = pa - ca
    if gap >= 12 and p.age <= 21:
        shape = "a genuine prospect — the ceiling is real"
    elif gap >= 6:
        shape = "still has another level"
    elif ca >= 75:
        shape = "the finished article, and it's good"
    elif p.age >= 27:
        shape = "what you see is what you get"
    else:
        shape = "close to their ceiling"
    return f"CA ~{ca:.0f}, ceiling ~{pa:.0f} — {shape}."
