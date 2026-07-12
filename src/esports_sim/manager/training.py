"""Weekly training: attribute growth, stamina management, chemistry.

The manager picks one focus per week per team — and, per player, an
individual development plan: a pinned focus category (`Player.dev_focus`,
"auto" = follow the team week) and a training intensity that trades
growth for stamina. Growth follows a hidden player-specific curve rather
than one universal age ladder. Matches are the other half of development:
`apply_match_experience`
turns what a player actually DID on the server into reps, so playing time
(and how they play) shapes who they become. AI players stay on the
defaults ("auto"/"normal"), so the plans are a purely human lever.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import development
from esports_sim.schemas import LanguageSkill, Player, Team
from esports_sim.schemas.attributes import AttributeCategory

FOCUS_OPTIONS = ["mechanical", "tactical", "mental", "team", "rest"]

# Per-player plan knobs (Player.dev_focus / Player.training_intensity).
DEV_FOCUS_OPTIONS = ["auto", "mechanical", "tactical", "mental", "team", "language"]
INTENSITY_OPTIONS = ["light", "normal", "intense"]
LANGUAGE_OPTIONS = ["ar", "de", "en", "es", "fr", "id", "ja", "ko", "ms", "pt", "ru", "th", "tl", "tr", "vi", "zh"]
_INTENSITY_GROWTH = {"light": 0.6, "normal": 1.0, "intense": 1.4}
_INTENSITY_DRAIN = {"light": 3.0, "normal": 6.0, "intense": 10.0}

_CATEGORY_ATTRS: dict[str, list[str]] = {
    "mechanical": ["aim_precision", "aim_reactivity", "movement"],
    "tactical": ["game_sense", "utility_usage", "positioning"],
    "mental": ["clutch_factor", "tilt_resistance", "composure"],
    "team": ["comms_quality"],
}

# System fit: a player whose playstyle suits the coach's system gets more
# meaningful reps and develops faster; a mismatch develops slower. Each
# playstyle keys off the tactic dials it lives on. Neutral tactics (every
# dial 50) yield exactly 1.0, so default teams — and the development tests —
# are unchanged.
_FIT_DIALS: dict[str, list[str]] = {
    "entry": ["aggression", "pace"],
    "awper": ["aggression"],
    "lurker": ["map_control"],
    "igl": ["util_discipline", "map_control"],
    "support": ["util_discipline"],
    "anchor": ["util_discipline"],
}
_FIT_SPAN = 0.15  # per fully-cranked matching dial


def _system_fit_mult(team: Team, p: Player) -> float:
    dials = _FIT_DIALS.get(str(p.playstyle), [])
    bonus = sum(
        (getattr(team.tactics, d) - 50.0) / 50.0 for d in dials
    ) * _FIT_SPAN
    return float(np.clip(1.0 + bonus, 0.7, 1.3))


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


def _player_rate(p: Player, support_bonus: float = 0.0) -> float:
    """Broad age rate x hidden curve x reachable headroom and traits."""
    base = growth_rate(p.age)
    floor = development.trait_value(p, "growth_floor", 0.0)
    if floor > 0 and p.age <= development.decline_age(p) - 1:
        base = max(base, floor)
    return (
        base
        * development.curve_growth_multiplier(p)
        * development.dev_multiplier(p, support_bonus)
    )


# Streaming eats practice time: a player pouring their week into the camera
# (Player.stream_load, follower-driven — see social.py) develops slower. It's
# a pure read of stream_load, so a synthetic player (load 0, no followers) is
# unchanged and the golden/balance gates — which never run campaign training —
# stay byte-identical. A manager reins a player in via a 1:1 (talk.py) to buy
# back some of this growth, trading away streaming revenue and morale.
STREAM_GROWTH_PENALTY_SPAN = 0.35  # a full-load streamer develops 35% slower


def stream_practice_mult(p: Player) -> float:
    """Growth multiplier from streaming load: 1.0 at load 0, falling to
    1 - STREAM_GROWTH_PENALTY_SPAN at load 100."""
    return 1.0 - (p.stream_load / 100.0) * STREAM_GROWTH_PENALTY_SPAN


# A protege under a veteran's wing develops this much faster. Bounded and
# opt-in: only a manager-set mentorship (empty in hands-off sims) supplies a
# multiplier here, so the balance gates see rate * 1.0 == rate, unchanged.
MENTOR_GROWTH_MULT = 1.15


def apply_training(
    team: Team,
    roster: list[Player],
    focus: str,
    rng: np.random.Generator,
    growth_mult: float = 1.0,  # coaching staff boost (user team)
    mentor_mults: dict[str, float] | None = None,
    support_bonuses: dict[str, float] | None = None,
    language_rate: float = 0.0,
) -> None:
    # Weekly regression to the mean: streaks fade unless re-earned.
    # Without this, form/morale lock at 100 for winners and the league
    # snowballs into 13-0 blowouts by season 3. Confidence regresses the
    # same way — belief needs re-earning too (and the clamp keeps the
    # engine's neutral-safe term from compounding, see snowball gate).
    for p in roster:
        p.form = round(p.form + (52.0 - p.form) * 0.06, 1)
        p.morale = round(p.morale + (60.0 - p.morale) * 0.04, 1)
        p.confidence = round(p.confidence + (50.0 - p.confidence) * 0.05, 1)

    if focus == "rest":
        for p in roster:
            p.stamina = min(100.0, p.stamina + 18.0)
            p.morale = min(100.0, p.morale + 1.5)
        return

    for p in roster:
        # Individual plan: a pinned focus overrides the team's category
        # (a team "rest" week still rests everyone, handled above).
        p_focus = p.dev_focus if p.dev_focus in _CATEGORY_ATTRS else focus
        if p.dev_focus == "language":
            # Language practice always replaces game-skill reps. A plan left
            # behind after the coach is released simply pauses until a new
            # language coach is hired.
            if p.learning_language and language_rate > 0:
                intensity = _INTENSITY_GROWTH.get(p.training_intensity, 1.0)
                gain = language_rate * intensity * stream_practice_mult(p)
                index = next(
                    (i for i, skill in enumerate(p.languages) if skill.lang == p.learning_language),
                    None,
                )
                current = p.languages[index].level if index is not None else 0.0
                learned = LanguageSkill(
                    lang=p.learning_language,
                    level=round(min(100.0, current + gain), 1),
                )
                if index is None:
                    p.languages.append(learned)
                    p.languages.sort(key=lambda skill: skill.lang)
                else:
                    p.languages[index] = learned
                p.stamina = max(0.0, p.stamina - _INTENSITY_DRAIN.get(p.training_intensity, 6.0))
            continue
        attrs = _CATEGORY_ATTRS.get(p_focus, _CATEGORY_ATTRS["tactical"])
        intensity = _INTENSITY_GROWTH.get(p.training_intensity, 1.0)
        # Mentorship boost — exactly 1.0 (a no-op) unless the manager set one.
        mentor = mentor_mults.get(p.id, 1.0) if mentor_mults else 1.0
        support = support_bonuses.get(p.id, 0.0) if support_bonuses else 0.0
        rate = (
            _player_rate(p, support) * _system_fit_mult(team, p) * intensity * mentor
            * stream_practice_mult(p)
        )
        # Tired players learn worse; below 35 stamina they barely absorb.
        fatigue_mult = 0.4 if p.stamina < 35 else 1.0
        # Train the weakest attribute in the category hardest.
        by_value = sorted(attrs, key=lambda a: p.attr(a))
        for i, attr_id in enumerate(by_value):
            gain = rate * fatigue_mult * growth_mult * (1.0 if i == 0 else 0.5)
            gain *= float(rng.uniform(0.6, 1.4))
            cur = p.attr(attr_id)
            ceil = development.development_ceiling(p, attr_id, support)
            # Diminishing returns near the currently reachable outcome. The
            # outcome may sit below headline potential for an unrealised
            # prospect or above it when the player's environment is exceptional.
            headroom = max(0.0, (max(95.0, ceil) - cur) / 45.0)
            p.attributes[attr_id] = round(
                min(cur + gain * headroom, max(cur, ceil)), 2
            )
        p.stamina = max(
            0.0, p.stamina - _INTENSITY_DRAIN.get(p.training_intensity, 6.0)
        )

    if focus == "team":
        team.chemistry = min(100.0, team.chemistry + 1.2)
        for p in roster:
            p.morale = min(100.0, p.morale + 0.5)

    # Locker-room gravity: leaders pull chemistry up a little every week.
    chem_regen = sum(
        development.trait_value(p, "chem_regen", 0.0) for p in roster
    )
    if chem_regen > 0:
        team.chemistry = round(min(100.0, team.chemistry + chem_regen), 1)


# ---------------------------------------------------------------------------
# Match experience: playing time is the other half of development.

# Per-attribute gain cap per map — a monster map is still one map.
_MATCH_XP_CAP = 0.25
_MATCH_XP_PER_REP = 0.02


def apply_match_experience(
    p: Player, line, n_rounds: int, support_bonus: float | None = None
) -> None:
    """Turn one map's box-score line into attribute reps: what a player
    actually DID on the server is what improves. Deterministic — derived
    from the line only, no rng — and scaled by the same age/PA-gap rate
    as training, so a prospect grows from minutes and a veteran at their
    ceiling mostly just logs them. Bench players get none of this (see
    apply_scrim_reps): playing time is a real development decision."""
    if support_bonus is None:
        support_bonus = development.contextual_ceiling_bonus(p)
    rate = _player_rate(p, support_bonus) * stream_practice_mult(p)
    clutch_n = line.clutch_1v1 + line.clutch_1v2 + line.clutch_1v3
    reps = {
        "aim_precision": line.kills * 0.5 + line.headshots * 0.5,
        "aim_reactivity": line.first_kills + line.trade_kills * 0.5 + line.kills * 0.25,
        "game_sense": n_rounds * 0.05 + line.assists * 0.5,
        "utility_usage": line.assists * 0.7 + (line.plants + line.defuses) * 0.5,
        "clutch_factor": clutch_n * 2.0,
        "composure": line.survived * 0.08 + clutch_n,
        "positioning": line.first_deaths * 0.4,  # dying first teaches spacing
    }
    for attr_id in sorted(reps):
        r = reps[attr_id]
        if r <= 0:
            continue
        cur = p.attr(attr_id)
        ceil = development.development_ceiling(p, attr_id, support_bonus)
        headroom = max(0.0, (max(95.0, ceil) - cur) / 45.0)
        gain = min(_MATCH_XP_CAP, _MATCH_XP_PER_REP * r) * rate * headroom
        if gain > 0:
            p.attributes[attr_id] = round(min(cur + gain, max(cur, ceil)), 2)


def apply_scrim_reps(p: Player, support_bonus: float = 0.0) -> None:
    """A benched player's week: scrims and VOD, a fraction of real minutes.
    Keeps prospects on the bench from flat-lining without making the bench
    a substitute for playing."""
    rate = _player_rate(p, support_bonus) * 0.25
    for attr_id in sorted(("game_sense", "positioning")):
        cur = p.attr(attr_id)
        ceil = development.development_ceiling(p, attr_id, support_bonus)
        headroom = max(0.0, (max(95.0, ceil) - cur) / 45.0)
        p.attributes[attr_id] = round(
            min(cur + 0.05 * rate * headroom, max(cur, ceil)), 2
        )


def ai_pick_focus(
    roster: list[Player],
    rng: np.random.Generator,
    team: Team | None = None,
) -> str:
    """AI coaching: rest when gassed, otherwise train toward the roster's
    needs — the weakest category by default, but a young roster spends some
    weeks building mechanics on its prospects, and a team with a strong
    tactical identity trains the attributes that identity leans on."""
    avg_stamina = sum(p.stamina for p in roster) / max(len(roster), 1)
    if avg_stamina < 55:
        return "rest"
    cat_avgs = {
        cat: sum(p.attr(a) for p in roster for a in attrs)
        / max(len(roster) * len(attrs), 1)
        for cat, attrs in _CATEGORY_ATTRS.items()
    }
    weakest = min(sorted(cat_avgs), key=lambda c: cat_avgs[c])
    # Youth development: a young core spends reps on raw mechanics.
    avg_age = sum(p.age for p in roster) / max(len(roster), 1)
    if avg_age <= 21.0 and rng.random() < 0.35:
        return "mechanical"
    # Identity training: sharp systems drill the attributes they run on.
    if team is not None:
        tac = team.tactics
        if max(tac.util_discipline, tac.map_control) >= 68.0 and rng.random() < 0.30:
            return "tactical"
        if max(tac.aggression, tac.pace) >= 68.0 and rng.random() < 0.30:
            return "mechanical"
    # A little variety so every AI team doesn't march in lockstep.
    if rng.random() < 0.25:
        return str(rng.choice([c for c in FOCUS_OPTIONS if c != weakest]))
    return weakest


def apply_offseason_aging(p: Player, rng: np.random.Generator) -> None:
    """One year older along the player's hidden peak and decline curve."""
    p.age += 1
    curve = development.development_curve(p)
    turn = curve.decline_age
    if p.age >= turn:
        # Short peaks fall away more sharply; long-peak players erode slowly.
        decline = (
            (p.age - (turn - 1))
            * 0.8
            * development.curve_decline_multiplier(p)
        )
        for attr_id in _CATEGORY_ATTRS["mechanical"]:
            p.attributes[attr_id] = round(
                max(1.0, p.attr(attr_id) - decline * float(rng.uniform(0.7, 1.3))), 2
            )
        # Experience partially compensates.
        for attr_id in ("game_sense", "composure"):
            p.attributes[attr_id] = round(min(99.0, p.attr(attr_id) + 0.4), 2)
    elif p.age <= 22:
        for attr_id in _CATEGORY_ATTRS["mechanical"]:
            cap = development.development_ceiling(p, attr_id)
            p.attributes[attr_id] = round(
                min(99.0, cap, p.attr(attr_id) + float(rng.uniform(0.3, 1.2))), 2
            )
    # Fresh legs for the new season.
    p.stamina = max(p.stamina, 88.0)
    p.form = 50.0
    p.morale = float(np.clip(p.morale, 55.0, 90.0))
