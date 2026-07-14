"""Backroom staff: coach, analyst, physio.

Each hired member scales one weekly system — coach boosts training growth
(more when the week's focus matches their specialty), analyst speeds
scouting AND unlocks deeper stat views (see analytics_tier), physio
restores stamina.

Hiring happens against ONE shared, world-level free-agent pool
(gs.staff_pool) — in a shared world managers compete for the same staff.
The pool is seeded 50+ deep at campaign start and churned every offseason
so the ecosystem stays healthy. Hiring is instant, releasing is free
(staff contracts are at-will in this economy). Every tier-one club carries a
concrete head coach. AI support departments remain abstract, which is the
documented economy boundary for this pass.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.gen import _FIRST_NAMES, _LAST_NAMES, _TEAM_NAMES
from esports_sim.manager import staff_effects
from esports_sim.manager.state import GameState, StaffMember
from esports_sim.rng.tree import RngTree

ROLES = ["coach", "analyst", "physio", "psychologist", "performance_coach", "language_coach"]

# A healthy market: at least this many free agents at all times. The two
# department roles (psychologist / performance coach) are rarer — a full
# competitive-intelligence department is a late-game build.
POOL_MIN = 54
_POOL_ROLE_CYCLE = [
    "coach", "analyst", "physio", "psychologist",
    "performance_coach", "language_coach",
]

ROLE_BLURB = {
    "coach": "training growth (extra on their specialty focus)",
    "analyst": "scouting speed + stat depth",
    "physio": "weekly stamina recovery",
    "psychologist": "confidence stability (shaken players recover faster)",
    "performance_coach": "form upkeep between matches",
    "language_coach": "weekly language fluency training",
}

SPECIALTIES: dict[str, list[str]] = {
    "coach": ["mechanical", "tactical", "mental", "team"],
    "analyst": ["opponents", "market", "data"],
    "physio": ["recovery", "longevity", "prevention"],
    "psychologist": ["pressure", "confidence", "cohesion"],
    "performance_coach": ["routines", "consistency", "peaking"],
    "language_coach": ["conversation", "callouts", "immersion"],
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
    "pressure": "big-stage composure work",
    "confidence": "rebuilding shaken players",
    "cohesion": "keeping five heads in one game",
    "routines": "week-in, week-out preparation",
    "consistency": "flattening the form rollercoaster",
    "peaking": "arriving at playoffs in top gear",
    "conversation": "everyday conversation and team-room confidence",
    "callouts": "fast, clear in-game callouts",
    "immersion": "practical immersion and vocabulary building",
}

_ROLE_TRAITS: dict[str, list[str]] = {
    "coach": [
        "developer", "players_coach", "disciplinarian", "innovator",
        "system_builder", "pragmatist",
    ],
    "analyst": ["opponent_specialist", "talent_spotter", "data_purist"],
    "physio": ["recovery_specialist", "preventive"],
    "psychologist": ["confidence_builder", "pressure_specialist"],
    "performance_coach": ["consistency", "routines"],
    "language_coach": ["callout_specialist", "immersion"],
}

_AGE_RANGE = {
    "coach": (30, 56),
    "analyst": (23, 46),
    "physio": (26, 52),
    "psychologist": (30, 58),
    "performance_coach": (27, 50),
    "language_coach": (25, 60),
}
_REGIONS = ["americas", "emea", "pacific"]

# Curated VCT market identities. The first four fields are stable game ids,
# display handles, the closest supported role, and the region; the final field
# is provenance displayed in the staff profile. Current staff are sourced from
# VLR team/transaction pages (2026-07-12); the explicit Free agent entries are
# recent, publicly announced departures. Game ratings/traits are deterministic
# balance values, not real-world assessments.
_REAL_VCT_STAFF: tuple[tuple[str, str, str, str, str], ...] = (
    # Americas
    ("vct_nbs", "nbs", "coach", "americas", "Head coach, 100 Thieves (VCT 2026)"),
    ("vct_d00mbr0s", "d00mbr0s", "coach", "americas", "Assistant coach, 100 Thieves (VCT 2026)"),
    ("vct_immi", "Immi", "coach", "americas", "Head coach, Cloud9 (VCT 2026)"),
    ("vct_veer", "Veer", "coach", "americas", "Assistant coach, Cloud9 (VCT 2026)"),
    ("vct_potter", "potter", "coach", "americas", "Head coach, Evil Geniuses (VCT 2026)"),
    ("vct_faded", "Faded", "coach", "americas", "Assistant coach, Evil Geniuses (VCT 2026)"),
    ("vct_stunner", "stunner", "coach", "americas", "Head coach, ENVY (VCT 2026)"),
    ("vct_wkn", "wkn", "coach", "americas", "Coach, ENVY (VCT 2026)"),
    ("vct_shaw", "shaw", "coach", "americas", "Head coach, FURIA (VCT 2026)"),
    ("vct_kamino", "kamino", "coach", "americas", "Assistant coach, FURIA (VCT 2026)"),
    ("vct_joshrt", "JoshRT", "coach", "americas", "Head coach, G2 Esports (VCT 2026)"),
    ("vct_shhhack", "shhhack", "coach", "americas", "Assistant coach, G2 Esports (VCT 2026)"),
    ("vct_robert_yip", "Robert", "performance_coach", "americas", "Performance coach, G2 Esports (VCT 2026)"),
    ("vct_zonyk", "zonyk", "coach", "americas", "Head coach, KRÜ Esports (VCT 2026)"),
    ("vct_fadeout", "Fadeout", "analyst", "americas", "Analyst, KRÜ Esports (VCT 2026)"),
    ("vct_onur", "Onur", "coach", "americas", "Head coach, LEVIATÁN (VCT 2026)"),
    ("vct_jhein", "Jhein", "coach", "americas", "Assistant coach, LEVIATÁN (VCT 2026)"),
    ("vct_romanilly", "Romanilly", "coach", "americas", "Head coach, LOUD (VCT 2026)"),
    ("vct_bati", "Bati", "coach", "americas", "Assistant coach, LOUD (VCT 2026)"),
    ("vct_bajerski", "Bajerski", "performance_coach", "americas", "Performance coach, LOUD (VCT 2026)"),
    ("vct_frod", "fRoD", "coach", "americas", "Head coach, MIBR (VCT 2026)"),
    ("vct_happy", "Happy", "coach", "americas", "Assistant coach, MIBR (VCT 2026)"),
    ("vct_bonkar", "bonkar", "coach", "americas", "Head coach, NRG (VCT 2026)"),
    ("vct_mitch", "mitch", "coach", "americas", "Assistant coach, NRG (VCT 2026)"),
    ("vct_ewok", "Ewok", "coach", "americas", "Head coach, Sentinels (VCT 2026)"),
    ("vct_gunter", "Gunter", "coach", "americas", "Assistant coach, Sentinels (VCT 2026)"),
    # EMEA
    ("vct_key", "KEY", "coach", "emea", "Head coach, BBL Esports (VCT 2026)"),
    ("vct_viento", "Viento", "coach", "emea", "Assistant coach, BBL Esports (VCT 2026)"),
    ("vct_vlad", "Vlad", "coach", "emea", "Head coach, FUT Esports (VCT 2026)"),
    ("vct_bambino", "Bambino", "coach", "emea", "Assistant coach, FUT Esports (VCT 2026)"),
    ("vct_engr", "ENGH", "coach", "emea", "Head coach, FNATIC (VCT 2026)"),
    ("vct_desmo", "Desmo", "coach", "emea", "Assistant coach, FNATIC (VCT 2026)"),
    ("vct_szed", "Szed", "performance_coach", "emea", "Performance coach, FNATIC (VCT 2026)"),
    ("vct_pipson", "pipsoN", "coach", "emea", "Head coach, GIANTX (VCT 2026)"),
    ("vct_waylander", "wayLander", "coach", "emea", "Assistant coach, GIANTX (VCT 2026)"),
    ("vct_mew", "Mew", "performance_coach", "emea", "Performance coach, GIANTX (VCT 2026)"),
    ("vct_kundikundi", "KUNDIKUNDI", "coach", "emea", "Head coach, Gentle Mates (VCT 2026)"),
    ("vct_mavera", "Mavera", "coach", "emea", "Assistant coach, Gentle Mates (VCT 2026)"),
    ("vct_ze1sh", "ZE1SH", "coach", "emea", "Head coach, Karmine Corp (VCT 2026)"),
    ("vct_lohan", "LohaN", "coach", "emea", "Head coach, Team Liquid (VCT 2026)"),
    ("vct_yaotzin", "yaotziN", "coach", "emea", "Assistant coach, Team Liquid (VCT 2026)"),
    ("vct_bacon9", "Bacon9", "analyst", "emea", "Analyst, Team Liquid (VCT 2026)"),
    ("vct_ange1", "ANGE1", "coach", "emea", "Head coach, NAVI (VCT 2026)"),
    ("vct_salah", "salah", "coach", "emea", "Assistant coach, NAVI (VCT 2026)"),
    ("vct_flynn", "Flynn", "analyst", "emea", "Analyst, NAVI (VCT 2026)"),
    ("vct_zuzanna", "Zuzanna", "performance_coach", "emea", "Performance coach, NAVI (VCT 2026)"),
    ("vct_xirreth", "Xirreth", "performance_coach", "emea", "Performance coach, NAVI (VCT 2026)"),
    ("vct_neilzinho", "neilzinho", "coach", "emea", "Head coach, Team Heretics (VCT 2026)"),
    ("vct_weber", "weber", "coach", "emea", "Assistant coach, Team Heretics (VCT 2026)"),
    ("vct_rob", "Rob", "performance_coach", "emea", "Performance coach, Team Heretics (VCT 2026)"),
    ("vct_beni", "Beni", "analyst", "emea", "Analyst, Team Heretics (VCT 2026)"),
    ("vct_pal", "PAL", "coach", "emea", "Coach, Team Vitality (VCT 2026)"),
    ("vct_scuttt", "Scuttt", "coach", "emea", "Coach, Team Vitality (VCT 2026)"),
    ("vct_slk", "slk", "analyst", "emea", "Analyst, Team Vitality (VCT 2026)"),
    ("vct_thinkii", "thinkii", "coach", "emea", "Head coach, PCIFIC Esport (VCT 2026)"),
    ("vct_zaes", "ZaeS", "coach", "emea", "Assistant coach, PCIFIC Esport (VCT 2026)"),
    ("vct_koyo", "Koyo", "analyst", "emea", "Analyst, PCIFIC Esport (VCT 2026)"),
    ("vct_afronfire", "afr0nfire", "coach", "emea", "Head coach, Eternal Fire (VCT 2026)"),
    ("vct_l7", "L7", "coach", "emea", "Assistant coach, Eternal Fire (VCT 2026)"),
    ("vct_castell0", "casteLL0", "coach", "emea", "Assistant coach, Eternal Fire (VCT 2026)"),
    # Pacific
    ("vct_alecks", "alecks", "coach", "pacific", "Head coach, Paper Rex (VCT 2026)"),
    ("vct_wendler", "Wendler", "coach", "pacific", "Assistant coach, Paper Rex (VCT 2026)"),
    ("vct_panda", "Panda", "performance_coach", "pacific", "Performance coach, Paper Rex (VCT 2026)"),
    ("vct_solo", "solo", "coach", "pacific", "Head coach, Gen.G (VCT 2026)"),
    ("vct_hsk", "HSK", "coach", "pacific", "Coach, Gen.G (VCT 2026)"),
    ("vct_peri", "peri", "coach", "pacific", "Coach, Gen.G (VCT 2026)"),
    ("vct_termi", "termi", "coach", "pacific", "Head coach, KIWOOM DRX (VCT 2026)"),
    ("vct_glow", "glow", "coach", "pacific", "Coach, KIWOOM DRX (VCT 2026)"),
    ("vct_argency", "Argency", "coach", "pacific", "Coach, KIWOOM DRX (VCT 2026)"),
    ("vct_jovi", "Jovi", "coach", "pacific", "Head coach, Rex Regum Qeon (VCT 2026)"),
    ("vct_warbirds", "Warbirds", "coach", "pacific", "Assistant coach, Rex Regum Qeon (VCT 2026)"),
    ("vct_rebecca", "Rebecca", "performance_coach", "pacific", "Performance coach, Rex Regum Qeon (VCT 2026)"),
    ("vct_kdg", "KDG", "coach", "pacific", "Head coach, T1 (VCT 2026)"),
    ("vct_cheonggak", "CheongGak", "coach", "pacific", "Coach, T1 (VCT 2026)"),
    ("vct_frost", "Frost", "coach", "pacific", "Head coach, FULL SENSE (VCT 2026)"),
    ("vct_theelovefamily", "theeLoveFamily", "coach", "pacific", "Coach, FULL SENSE (VCT 2026)"),
    ("vct_sushiboys", "Sushiboys", "coach", "pacific", "Assistant coach, FULL SENSE (VCT 2026)"),
    ("vct_platoon", "Platoon", "coach", "pacific", "Head coach, Global Esports (VCT 2026)"),
    ("vct_vladk0r", "vladk0r", "coach", "pacific", "Assistant coach, Global Esports (VCT 2026)"),
    ("vct_skye", "Skye", "analyst", "pacific", "Analyst, Team Secret (VCT 2026)"),
    ("vct_ryota", "ryota-", "coach", "pacific", "Head coach, ZETA DIVISION (VCT 2026)"),
    ("vct_xqq", "XQQ", "coach", "pacific", "Assistant coach, ZETA DIVISION (VCT 2026)"),
    ("vct_gya9", "gya9", "analyst", "pacific", "Analyst, ZETA DIVISION (VCT 2026)"),
    ("vct_mini", "mini", "coach", "pacific", "Staff coach, ZETA DIVISION (VCT 2026)"),
    ("vct_vorz", "Vorz", "coach", "pacific", "Head coach, DetonatioN FocusMe (VCT 2026)"),
    ("vct_melofovia", "Melofovia", "coach", "pacific", "Coach, DetonatioN FocusMe (VCT 2026)"),
    ("vct_northernlights", "NorthernLights", "coach", "pacific", "Coach, DetonatioN FocusMe (VCT 2026)"),
    ("vct_silkanon", "SilkAn0n", "coach", "pacific", "Head coach, Nongshim RedForce (VCT 2026)"),
    ("vct_yoman", "Yoman", "coach", "pacific", "Coach, Nongshim RedForce (VCT 2026)"),
    ("vct_sungmin", "Sungmin", "coach", "pacific", "Coach, Nongshim RedForce (VCT 2026)"),
    ("vct_tk9", "TK9", "coach", "pacific", "Head coach, VARREL (VCT 2026)"),
    ("vct_r3thme", "r3thme", "analyst", "pacific", "Analyst, VARREL (VCT 2026)"),
    # China (current roster records where available; history avoids a claim
    # that a fast-moving staff assignment remains current after the source date).
    ("vct_ed101", "ED101", "coach", "china", "Head coach, All Gamers (VCT 2026)"),
    ("vct_septem7", "Septem7", "coach", "china", "Assistant coach, All Gamers (VCT 2026)"),
    ("vct_muggle", "Muggle", "coach", "china", "Head coach, Bilibili Gaming (VCT 2026)"),
    ("vct_jexen", "Jexen", "coach", "china", "Coach, Bilibili Gaming (VCT 2026)"),
    ("vct_nathand", "NaThanD", "coach", "china", "Head coach, Dragon Ranger Gaming (VCT 2026)"),
    ("vct_lt", "Lt", "coach", "china", "Assistant coach, Dragon Ranger Gaming (VCT 2026)"),
    ("vct_autumn", "Autumn", "coach", "china", "Head coach, EDward Gaming (VCT 2026)"),
    ("vct_indigo", "indigo", "coach", "china", "Assistant coach, EDward Gaming (VCT 2026)"),
    ("vct_legija", "LEGIJA", "coach", "china", "Head coach, FunPlus Phoenix (VCT 2026)"),
    ("vct_york", "York", "coach", "china", "Assistant coach, FunPlus Phoenix (VCT 2026)"),
    ("vct_bail", "Bail", "coach", "china", "Head coach, JD Gaming (VCT 2026)"),
    ("vct_desire", "Desire", "coach", "china", "Assistant coach, JD Gaming (VCT 2026)"),
    ("vct_24k", "24K", "coach", "china", "Head coach, Nova Esports (VCT 2026)"),
    ("vct_destroyer", "destroyer", "coach", "china", "Head coach, Trace Esports (VCT 2026)"),
    ("vct_yiyee", "Yiyee", "coach", "china", "Coach, Trace Esports (VCT 2026)"),
    ("vct_after", "AFTER", "coach", "china", "Head coach, Titan Esports Club (VCT 2026)"),
    ("vct_3water", "3water", "coach", "china", "Assistant coach, Titan Esports Club (VCT 2026)"),
    ("vct_hypnotizing", "hypnotizing", "coach", "china", "Head coach, TYLOO (VCT 2026)"),
    ("vct_billyo", "billyo", "coach", "china", "Assistant coach, TYLOO (VCT 2026)"),
    ("vct_sword9", "sword9", "coach", "china", "Coach, TYLOO (VCT 2026)"),
    ("vct_alexrr", "alexRr", "coach", "china", "Head coach, Wolves Esports (VCT 2026)"),
    ("vct_hvoya", "hVoya", "coach", "china", "Head coach, Xi Lai Gaming (VCT 2026)"),
    # Recent, explicitly announced departures: free-agent market candidates.
    ("vct_strong", "Strong", "coach", "emea", "Free agent — assistant coach, NRG (departed 2026)"),
    ("vct_anderzz", "Anderzz", "coach", "americas", "Free agent — assistant coach, G2 Esports (departed 2025)"),
    ("vct_chippy", "chippy", "coach", "emea", "Free agent — assistant coach, NAVI (departed 2026)"),
    ("vct_milan", "Milan", "coach", "emea", "Free agent — head coach, FNATIC (departed 2026)"),
    ("vct_fayde", "Fayde", "coach", "china", "Free agent — head coach, Wolves Esports (departed 2026)"),
    ("vct_r1cklee", "R1ckLee", "coach", "china", "Free agent — coach, Wolves Esports (departed 2026)"),
)

# Extra ticks a coach's specialty adds when the week's focus matches it.
SPECIALTY_GROWTH_BONUS = 0.15


def _attribute_profile(rng, quality: float, role: str) -> dict[str, float]:
    """Create a distinct but quality-anchored seven-attribute profile."""
    weights = staff_effects.ROLE_WEIGHTS[role]
    values: dict[str, float] = {}
    for key in staff_effects.ATTRIBUTE_LABELS:
        role_lift = 5.0 if key in weights and weights[key] >= 0.18 else 0.0
        value = quality + role_lift + float(rng.normal(0.0, 7.0))
        values[key] = round(float(np.clip(value, 1.0, 99.0)), 1)
    return values


def _style_profile(rng, role: str) -> tuple[str, dict[str, float]]:
    if role != "coach":
        return "", {}
    identity = str(rng.choice(sorted(staff_effects.STYLE_ARCHETYPES)))
    preferences = {
        dial: round(float(np.clip(value + rng.normal(0.0, 3.0), 10.0, 90.0)), 1)
        for dial, value in sorted(staff_effects.STYLE_ARCHETYPES[identity].items())
    }
    return identity, preferences


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
    n_traits = min(len(_ROLE_TRAITS[role]), int(rng.integers(1, 3)))
    traits = sorted(
        str(t) for t in rng.choice(_ROLE_TRAITS[role], size=n_traits, replace=False)
    )
    attributes = _attribute_profile(rng, quality, role)
    style_identity, style_preferences = _style_profile(rng, role)
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
        attributes=attributes,
        style_identity=style_identity,
        style_preferences=style_preferences,
    )


def needs_real_vct_staff(gs: GameState) -> bool:
    """Whether this save has not yet received the curated real VCT cohort."""
    # The curated cohort is a start-of-save import, not an immortal source of
    # staff. Once a campaign reaches a second season, departures and
    # retirements must remain permanent.
    if gs.season > 1:
        return False
    present = {m.id for m in gs.staff_pool}
    for team_staff in gs.staff_by.values():
        present.update(m.id for m in team_staff.values())
    return any(spec[0] not in present for spec in _REAL_VCT_STAFF)


def _make_real_vct_member(spec: tuple[str, str, str, str, str]) -> StaffMember:
    """Build a stable, balance-tuned market member from a real identity."""
    staff_id, name, role, region, history = spec
    rng = RngTree(2026).derive("real-vct-staff", staff_id)
    lo, hi = _AGE_RANGE[role]
    quality_floor = {"coach": 65.0, "analyst": 58.0, "performance_coach": 60.0}[role]
    quality = float(np.round(rng.uniform(quality_floor, 90.0), 1))
    salary = max(1_500, int(np.round((quality ** 1.5) * 8 / 100) * 100))
    traits = sorted(str(t) for t in rng.choice(_ROLE_TRAITS[role], size=2, replace=False))
    attributes = _attribute_profile(rng, quality, role)
    style_identity, style_preferences = _style_profile(rng, role)
    return StaffMember(
        id=staff_id,
        name=name,
        role=role,
        quality=quality,
        salary=salary,
        age=int(rng.integers(lo, hi)),
        region=region,
        specialty=str(rng.choice(SPECIALTIES[role])),
        traits=traits,
        history=[history],
        seasons_experience=int(rng.integers(2, 10)),
        attributes=attributes,
        style_identity=style_identity,
        style_preferences=style_preferences,
    )


def _seed_real_vct_staff(gs: GameState, taken: set[str]) -> None:
    player_names = _player_identity_keys(gs)
    for spec in _REAL_VCT_STAFF:
        if spec[0] in taken or _identity_key(spec[1]) in player_names:
            continue
        gs.staff_pool.append(_make_real_vct_member(spec))
        taken.add(spec[0])


def pool_role_targets(team_count: int) -> dict[str, int]:
    """Minimum market depth by role for a league of ``team_count`` clubs.

    Coaches have a rich real-world pool, while support disciplines are often
    omitted from public team pages.  These targets deliberately give managers
    viable alternatives in every department instead of merely one token hire.
    """
    teams = max(1, team_count)
    return {
        "coach": max(12, (teams + 2) // 3),
        "analyst": max(12, (teams + 1) // 2),
        "physio": max(8, (teams + 2) // 3),
        "psychologist": max(6, (teams + 3) // 4),
        "performance_coach": max(10, (teams + 2) // 3),
        "language_coach": max(6, (teams + 3) // 4),
    }


def seed_pool(gs: GameState, *, include_real: bool = True) -> None:
    """Fill the shared staff market up to POOL_MIN. Deterministic — each
    member is a pure function of (campaign seed, member id) — and every id
    ever employed stays taken, so a hire can never be 'replaced' by a
    doppelganger holding the same id. Called at campaign start, at every
    offseason after churn, and lazily when the market runs thin."""
    taken = {m.id for m in gs.staff_pool}
    staff_names = {_identity_key(m.name) for m in gs.staff_pool}
    for staff in gs.staff_by.values():
        taken.update(m.id for m in staff.values())
        staff_names.update(_identity_key(m.name) for m in staff.values())
    if include_real:
        _seed_real_vct_staff(gs, taken)
    staff_names.update(_identity_key(m.name) for m in gs.staff_pool)
    i = 0
    player_names = _player_identity_keys(gs)
    # A historical expanded world needs more choice than the original small
    # default league. Keep a 24-person cushion above one candidate per team.
    pool_target = max(POOL_MIN, len(gs.teams) + 24)
    role_targets = pool_role_targets(len(gs.teams))
    while (
        len(gs.staff_pool) < pool_target
        or any(
            sum(m.role == role for m in gs.staff_pool) < minimum
            for role, minimum in role_targets.items()
        )
    ):
        sid = f"staff_s{gs.season}_{i}"
        role = _POOL_ROLE_CYCLE[i % len(_POOL_ROLE_CYCLE)]
        i += 1
        if sid in taken:
            continue
        taken.add(sid)
        member = _make_member(gs.seed, sid, role)
        identity = _identity_key(member.name)
        if identity in player_names or identity in staff_names:
            # Stable id still advances, so the replacement name is just as
            # deterministic and no player can also appear as market staff.
            continue
        gs.staff_pool.append(member)
        staff_names.add(identity)
    gs.staff_pool.sort(key=lambda m: m.id)


def seed_team_coaches(gs: GameState) -> None:
    """Give every tier-one club a concrete, deterministic head coach.

    Roster packs may already assign historical coaches. Generated incumbents
    never enter the free-agent pool until replaced, and their identities are
    checked against every player and staff name in the world.
    """
    used = {_identity_key(m.name) for m in gs.staff_pool}
    for team_staff in gs.staff_by.values():
        used.update(_identity_key(m.name) for m in team_staff.values())
    used.update(_player_identity_keys(gs))
    for team_id in sorted(gs.teams):
        if gs.teams[team_id].tier != 1:
            continue
        team_staff = gs.staff_by.setdefault(team_id, {})
        if "coach" in team_staff:
            continue
        for attempt in range(100):
            sid = f"staff_incumbent_{team_id}" + (f"_{attempt}" if attempt else "")
            member = _make_member(gs.seed, sid, "coach")
            identity = _identity_key(member.name)
            if identity in used:
                continue
            member.region = str(gs.teams[team_id].region)
            member.history = [f"S{gs.season}: head coach, {gs.teams[team_id].name}"]
            team_staff["coach"] = member
            used.add(identity)
            break
        else:
            raise RuntimeError(f"could not generate distinct coach for {team_id}")


_VCT_2021_COACHES = (
    ("team_100_thieves", "frost"), ("team_cloud9_blue", "autumn"),
    ("team_version1", "immi"), ("team_tsm", "tailored"),
    ("team_faze_clan", "trippy"), ("team_xset", "syykont"),
    ("team_kru_esports", "onur"), ("team_furia_esports", "carlao"),
    ("team_fnatic", "mini"), ("team_team_liquid", "sliggy"),
    ("team_acend", "nbs"), ("team_gambit_esports", "engh"),
    ("team_funplus_phoenix", "d00mbr0s"), ("team_guild_esports", "barbarr"),
    ("team_team_heretics", "johnta"), ("team_supermassive_blaze", "9999"),
    ("team_team_bds", "wallax"), ("team_vision_strikers", "termi"),
    ("team_nuturn_gaming", "jaemin"), ("team_x10_esports", "0bi"),
    ("team_crazy_raccoon", "mun"), ("team_paper_rex", "alecks"),
    ("team_bren_esports", "gibo"),
    ("team_f4q", "locomotive"), ("team_zeta_division", "xqq"),
    ("team_northeption", "vorz"),
    # Later-2021 team records used where the first pass had no named coach.
    ("team_team_envy", "chet"), ("team_gen_g_esports", "doolb"),
    ("team_immortals", "jamezirl"), ("team_rise", "ohai"),
    ("team_luminosity_gaming", "piggye"), ("team_t1", "david denis"),
    ("team_ninjas_in_pyjamas", "emil"), ("team_giants_gaming", "pipson"),
    ("team_futbolist", "paura"), ("team_wave_esports", "mrsnooze"),
    ("team_alliance", "prycyy"), ("team_team_finest", "physiq"),
    ("team_damwon_gaming", "j1n"), ("team_tnl_esports", "sunday"),
    ("team_prince", "soma"), ("team_boom_esports", "mushi"),
    ("team_fennel", "hnt"),
)


def _identity_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _player_identity_keys(gs: GameState) -> set[str]:
    """All real-player identities, including hidden future arrivals."""
    names = {_identity_key(p.handle) for p in gs.players.values()}
    names.update(
        _identity_key(prospect.player.handle)
        for prospect in gs.future_prospects.values()
    )
    return names


def seed_vct_2021_staff(gs: GameState) -> None:
    """Seed every historical team with a distinct, non-player head coach."""
    player_names = _player_identity_keys(gs)
    researched = dict(_VCT_2021_COACHES)
    for team_id in sorted(gs.teams):
        handle = researched.get(team_id)
        if handle is not None and _identity_key(handle) in player_names:
            # A real coach who is also a rostered competitor cannot wear both
            # hats in this pack; give the team a deterministic staff record.
            handle = None
        if handle is not None:
            # Prefer the era-specific assignment over a duplicate of the same
            # real person in the generic/current staff market.
            key = _identity_key(handle)
            gs.staff_pool = [m for m in gs.staff_pool if _identity_key(m.name) != key]
        staff_id = (
            f"vct2021_{_identity_key(handle)}"
            if handle is not None else f"vct2021_generated_{team_id}"
        )
        if any(m.id == staff_id for m in gs.staff_pool):
            continue
        member = _make_member(2021, staff_id, "coach")
        if handle is not None:
            member.name = handle
        existing_staff_names = {
            _identity_key(m.name) for m in gs.staff_pool
        }
        for staff in gs.staff_by.values():
            existing_staff_names.update(_identity_key(m.name) for m in staff.values())
        if (
            _identity_key(member.name) in player_names
            or _identity_key(member.name) in existing_staff_names
        ):
            continue
        member.region = str(gs.teams[team_id].region)
        provenance = "2021 coach" if handle is not None else "generated 2021 staff record"
        member.history = [f"{provenance}, {gs.teams[team_id].name}"]
        member.last_org = team_id
        gs.staff_by.setdefault(team_id, {})["coach"] = member


def _retirement_chance(member: StaffMember) -> float:
    """Retirement likelihood after the member ages at an offseason."""
    return 1.0 if member.age >= 62 else max(0.0, (member.age - 55) * 0.12)


def _replacement_member(
    gs: GameState, team_id: str, role: str, used_names: set[str],
) -> StaffMember:
    """Create a deterministic new hire when an assigned staffer retires."""
    player_names = _player_identity_keys(gs)
    base = f"staff_s{gs.season}_replacement_{team_id}_{role}"
    for attempt in range(100):
        staff_id = base if attempt == 0 else f"{base}_{attempt}"
        member = _make_member(gs.seed, staff_id, role)
        identity = _identity_key(member.name)
        if identity not in player_names and identity not in used_names:
            member.region = str(gs.teams[team_id].region)
            member.history = [f"S{gs.season}: new {role}, {gs.teams[team_id].name}"]
            member.last_org = team_id
            used_names.add(identity)
            return member
    raise RuntimeError("could not generate a distinct staff replacement")


def offseason_churn(gs: GameState) -> None:
    """Age and retire staff, then produce a fresh market class each season."""
    rng = RngTree(gs.seed).derive("staffpool", gs.season, "churn")
    for m in sorted(gs.staff_pool, key=lambda member: member.id):
        m.age += 1
    keep: list[StaffMember] = []
    for m in sorted(gs.staff_pool, key=lambda member: member.id):
        if rng.random() >= _retirement_chance(m):
            keep.append(m)
    gs.staff_pool = sorted(keep, key=lambda member: member.id)

    used_names = {_identity_key(m.name) for m in gs.staff_pool}
    retired_human_staff: list[tuple[str, str]] = []
    for team_id in sorted(gs.staff_by):
        team_staff = gs.staff_by[team_id]
        retiring_roles: list[str] = []
        for role, member in sorted(team_staff.items()):
            member.age += 1
            member.seasons_experience += 1
            if rng.random() < _retirement_chance(member):
                retiring_roles.append(role)
                if team_id in gs.human_team_ids:
                    retired_human_staff.append((member.name, role))
            else:
                _develop_employed_member(member)
                used_names.add(_identity_key(member.name))
        for role in retiring_roles:
            del team_staff[role]
            team_staff[role] = _replacement_member(gs, team_id, role, used_names)

    # This is deliberately a new-season class; don't resurrect retired real
    # staff from the initial curated cohort.
    seed_pool(gs, include_real=False)
    for name, role in retired_human_staff:
        gs.push_news(f"{name} retired from the {role} role; a replacement has joined.")


def ai_offseason_coach_hiring(gs: GameState) -> None:
    """Struggling AI clubs use the shared market to seek a better-fit coach."""
    for team_id in sorted(gs.teams):
        if gs.is_human(team_id) or gs.teams[team_id].tier != 1:
            continue
        coach = gs.staff_by.get(team_id, {}).get("coach")
        if coach is None:
            continue
        order = gs.standings_order(str(gs.teams[team_id].region), tier=1)
        position = order.index(team_id) + 1 if team_id in order else len(order)
        fit = staff_effects.system_fit(coach, gs.teams[team_id].tactics)
        if position <= max(1, len(order) // 2) and fit >= 60.0:
            continue
        replace_ai_coach(gs, team_id, min_improvement=8.0)


def _coach_market_score(gs: GameState, team_id: str, member: StaffMember) -> float:
    tactics = gs.teams[team_id].tactics
    return (
        staff_effects.overall(member)
        + staff_effects.system_fit(member, tactics) * 0.25
        - member.salary / 5_000.0
    )


def replace_ai_coach(
    gs: GameState,
    team_id: str,
    *,
    min_improvement: float | None = None,
) -> tuple[StaffMember, StaffMember] | None:
    """Swap an AI club's coach through the same shared staff market.

    Both incumbent and candidates use the same quality, fit, and salary score.
    ``min_improvement=None`` models an impatient in-season firing; offseason
    hiring requires a real upgrade before creating churn.
    """
    from esports_sim.manager import knowledge

    incumbent = gs.staff_by.get(team_id, {}).get("coach")
    candidates = [member for member in gs.staff_pool if member.role == "coach"]
    if incumbent is None or not candidates:
        return None
    candidate = max(
        candidates,
        key=lambda member: (_coach_market_score(gs, team_id, member), member.id),
    )
    if (
        min_improvement is not None
        and _coach_market_score(gs, team_id, candidate)
        < _coach_market_score(gs, team_id, incumbent) + min_improvement
    ):
        return None

    gs.staff_pool.remove(candidate)
    incumbent.last_org = team_id
    gs.staff_pool.append(incumbent)
    gs.staff_pool.sort(key=lambda member: member.id)
    if candidate.last_org:
        knowledge.on_staff_move(gs, candidate.last_org, team_id)
    candidate.history.append(f"S{gs.season}: head coach, {gs.teams[team_id].name}")
    candidate.last_org = ""
    gs.staff_by[team_id]["coach"] = candidate
    return incumbent, candidate


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
    # An ex-staffer of another org carries part of the old book with them
    # (knowledge leak — see manager/knowledge.py).
    if cand.last_org and cand.role in ("coach", "analyst"):
        from esports_sim.manager import knowledge

        knowledge.on_staff_move(gs, cand.last_org, gs.acting_team_id)
    cand.last_org = ""
    if old is not None:
        old.last_org = gs.acting_team_id
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
    member.last_org = gs.acting_team_id  # they leave knowing your book
    gs.staff_pool.append(member)
    gs.staff_pool.sort(key=lambda m: m.id)
    gs.push_news(f"{member.name} leaves the {role} role.")
    return True, f"released {member.name}"


def record_title(gs: GameState, team_id: str, title: str) -> None:
    """Silverware sticks to the staff who were in the building for it."""
    for m in gs.staff_by.get(team_id, {}).values():
        m.titles.append(title)
        _evaluate_badges(m)


def _career_add(member: StaffMember, key: str, amount: float) -> None:
    member.career_stats[key] = round(member.career_stats.get(key, 0.0) + amount, 3)
    _evaluate_badges(member)


def _evaluate_badges(member: StaffMember) -> None:
    stats = member.career_stats
    earned = set(member.badges)
    if member.titles:
        earned.add("champion")
    if len(member.titles) >= 3:
        earned.add("dynasty_architect")
    if stats.get("weeks", 0.0) >= 100:
        earned.add("veteran_operator")
    if stats.get("training_gain", 0.0) >= 25:
        earned.add("talent_developer")
    if (
        stats.get("maps", 0.0) >= 50
        and stats.get("series_wins", 0.0) / max(stats.get("series", 0.0), 1.0) >= 0.60
    ):
        earned.add("master_strategist")
    if stats.get("scouting_progress", 0.0) >= 10:
        earned.add("opposition_expert")
    if stats.get("stamina_restored", 0.0) >= 500:
        earned.add("iron_squad")
    if stats.get("confidence_restored", 0.0) >= 100:
        earned.add("stabilizer")
    if stats.get("form_restored", 0.0) >= 100:
        earned.add("consistency_architect")
    if stats.get("fluency_taught", 0.0) >= 50:
        earned.add("polyglot_program")
    member.badges = sorted(earned)


def add_contribution(
    gs: GameState, team_id: str, role: str, key: str, amount: float,
) -> None:
    if amount <= 0:
        return
    member = gs.staff_by.get(team_id, {}).get(role)
    if member is not None:
        _career_add(member, key, amount)


def record_week(gs: GameState, report) -> None:
    """Ground staff career totals in the fixtures actually played this week."""
    for team_id in sorted(gs.staff_by):
        team_staff = gs.staff_by[team_id]
        for member in team_staff.values():
            _career_add(member, "weeks", 1.0)
        coach = team_staff.get("coach")
        if coach is None:
            continue
        fixtures = [
            f for f in report.fixtures
            if team_id in (f.team_a, f.team_b) and f.id in report.match_stats
        ]
        maps = sum(len(report.match_stats.get(f.id, [])) for f in fixtures)
        _career_add(coach, "maps", float(maps))
        _career_add(coach, "series", float(len(fixtures)))
        _career_add(coach, "series_wins", float(sum(f.winner_id == team_id for f in fixtures)))


def _develop_employed_member(member: StaffMember) -> None:
    """Small deterministic experience growth; staff knowledge does not age like aim."""
    if member.career_stats.get("weeks", 0.0) < 20 or member.age >= 52:
        return
    for key in ("teaching", "people_management", "tactical_knowledge"):
        if key in member.attributes:
            member.attributes[key] = round(min(99.0, member.attributes[key] + 0.2), 1)
    member.quality = staff_effects.overall(member)


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
    return staff_effects.coach_training_multiplier(
        coach, gs.teams[gs.acting_team_id].tactics, focus
    )


def coach_player_multipliers(gs: GameState) -> dict[str, float]:
    coach = gs.staff.get("coach")
    if coach is None:
        return {}
    tactics = gs.teams[gs.acting_team_id].tactics
    return {
        player.id: staff_effects.coach_player_multiplier(coach, player, tactics)
        for player in gs.roster(gs.acting_team_id)
    }


def coach_prep_bonus(gs: GameState, team_id: str, tactics=None) -> float:
    coach = gs.staff_by.get(team_id, {}).get("coach")
    if coach is None:
        return 0.0
    resolved = tactics or gs.teams[team_id].tactics
    return staff_effects.coach_prep_bonus(coach, resolved)


def scout_multiplier(gs: GameState) -> float:
    """Scouting speed multiplier: up to ~1.9 with an elite analyst."""
    analyst = gs.staff.get("analyst")
    if analyst is None:
        return 1.0
    score = staff_effects.role_effect_score(analyst)
    traits = set(analyst.traits)
    target = gs.scout_target
    if target == "market" and "talent_spotter" in traits:
        score *= 1.08
    elif target not in (None, "market") and "opponent_specialist" in traits:
        score *= 1.08
    return 1.0 + score / 100.0


def physio_recovery(gs: GameState) -> float:
    """Extra stamina per player per week."""
    physio = gs.staff.get("physio")
    return staff_effects.role_effect_score(physio) / 18.0 if physio else 0.0


def confidence_support(gs: GameState) -> float:
    """Psychologist: weekly pull applied to sub-50 confidence — shaken
    players recover toward neutral faster. Zero without one, and never
    inflates confidence past 50 (support, not a hype machine)."""
    psych = gs.staff.get("psychologist")
    return staff_effects.role_effect_score(psych) / 60.0 if psych else 0.0


def form_upkeep(gs: GameState) -> float:
    """Performance coach: weekly form floor maintenance for sub-50 form.
    Same shape as confidence_support — a pull toward neutral, not a buff."""
    pc = gs.staff.get("performance_coach")
    return staff_effects.role_effect_score(pc) / 70.0 if pc else 0.0


def language_learning_rate_for_quality(quality: float) -> float:
    """Fluency points a language coach delivers in one normal weekly session."""
    return 0.35 + quality / 90.0


def language_learning_rate(gs: GameState) -> float:
    """Weekly fluency points from the dedicated language coach (zero without one)."""
    coach = gs.staff.get("language_coach")
    return language_learning_rate_for_quality(staff_effects.role_effect_score(coach)) if coach else 0.0


# -- coaching tree --------------------------------------------------------------

# What makes a retiring player staff material, and which chair suits them.
TREE_MIN_AGE = 28
TREE_MIN_CA = 52.0


def retire_into_staff(gs: GameState, p, ca: float, team_name: str) -> "StaffMember | None":
    """The coaching tree: an eligible retiree joins the shared staff pool
    as a candidate — IGLs and high-game-sense players become coaches,
    utility/positioning brains become analysts. Deterministic (no rng, so
    the offseason stream never shifts); their playing identity carries
    into the chair (name, region, a career line, their titles)."""
    if p.age < TREE_MIN_AGE or ca < TREE_MIN_CA:
        return None
    attrs = p.attributes
    game_sense = attrs.get("game_sense", 0.0)
    comms = attrs.get("comms_quality", 0.0)
    utility = attrs.get("utility_usage", 0.0)
    positioning = attrs.get("positioning", 0.0)
    is_igl = str(p.playstyle) == "igl"
    if is_igl or game_sense >= 62.0 or comms >= 66.0:
        role = "coach"
        specialty = "tactical" if game_sense >= comms else "team"
    elif utility >= 62.0 or positioning >= 64.0:
        role = "analyst"
        specialty = "opponents"
    else:
        return None
    quality = float(np.round(min(88.0, 30.0 + ca * 0.55 + (8.0 if is_igl else 0.0)), 1))
    seed_rng = RngTree(gs.seed).derive("retired-staff", p.id)
    attributes = _attribute_profile(seed_rng, quality, role)
    # Playing careers carry forward into the most legible staff attributes.
    attributes["tactical_knowledge"] = round(min(99.0, max(
        attributes["tactical_knowledge"], game_sense,
    )), 1)
    attributes["people_management"] = round(min(99.0, max(
        attributes["people_management"], comms,
    )), 1)
    style_identity, style_preferences = _style_profile(seed_rng, role)
    member = StaffMember(
        id=f"staff_ex_{p.id}",
        name=p.real_name or p.handle,
        role=role,
        quality=quality,
        salary=max(1_500, int(np.round((quality ** 1.5) * 8 / 100) * 100)),
        age=p.age,
        region=str(getattr(p, "region", "") or ""),
        specialty=specialty,
        traits=["developer"] if role == "coach" else ["grinder"],
        history=[f"pro career as {p.handle}" + (f", last of {team_name}" if team_name else "")],
        seasons_experience=0,
        former_player_id=p.id,
        attributes=attributes,
        style_identity=style_identity,
        style_preferences=style_preferences,
    )
    if any(m.id == member.id for m in gs.staff_pool):
        return None  # already in the pool (can't happen twice, but cheap)
    gs.staff_pool.append(member)
    gs.staff_pool.sort(key=lambda m: m.id)
    gs.push_news(
        f"{p.handle} moves into the backroom - available as a {role.replace('_', ' ')}."
    )
    return member


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


def analytics_tier_for(analyst: StaffMember | None, facility_level: int) -> int:
    """Resolve analytics access for a staff/facility combination.

    Keeping the hypothetical-level calculation here lets serializers preview
    an upgrade without copying this campaign formula into the browser.
    """
    score = (staff_effects.role_effect_score(analyst) if analyst else 0.0)
    if analyst is not None and "data_purist" in analyst.traits:
        score += 5.0
    score += 15.0 * max(0, facility_level)
    if score >= 95.0:
        return 3
    if score >= 55.0:
        return 2
    if score >= 1.0:
        return 1
    return 0


def analytics_tier(gs: GameState) -> int:
    """0-3, from the analyst's quality plus the analytics suite facility.
    Score = analyst quality + 15/level; tiers at 1 / 55 / 95 — an average
    analyst alone reaches tier 1-2, elite-plus-suite reaches 3."""
    return analytics_tier_for(
        gs.staff.get("analyst"), gs.facilities.get("analytics_suite", 0)
    )
