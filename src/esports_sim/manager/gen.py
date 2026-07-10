"""Deterministic player / team generation.

Everything derives from the campaign RngTree, so a new game with the same
seed produces the same league, rosters, and free agents.
"""

from __future__ import annotations

import hashlib

import numpy as np

from esports_sim.manager import development
from esports_sim.registry.loader import GameData
from esports_sim.schemas import AgentMastery, LanguageSkill, MapMastery, Player, Team
from esports_sim.schemas.common import Playstyle, Region, Role

# Nationality pools per league region: (country, native language, weight).
# Coarse on purpose — flavour plus the comms-cohesion input, not a census.
_REGION_IDENTITY: dict[Region, list[tuple[str, str, int]]] = {
    Region.AMERICAS: [
        ("US", "en", 28), ("BR", "pt", 26), ("CA", "en", 10), ("AR", "es", 10),
        ("MX", "es", 10), ("CL", "es", 8), ("CO", "es", 8),
    ],
    Region.EMEA: [
        ("FR", "fr", 13), ("UK", "en", 12), ("TR", "tr", 12), ("RU", "ru", 12),
        ("DE", "de", 10), ("ES", "es", 9), ("SE", "sv", 8), ("PL", "pl", 8),
        ("DK", "da", 6), ("FI", "fi", 5), ("NL", "nl", 5),
    ],
    Region.PACIFIC: [
        ("KR", "ko", 28), ("JP", "ja", 14), ("PH", "en", 10), ("ID", "id", 10),
        ("TH", "th", 10), ("IN", "en", 9), ("SG", "en", 8), ("AU", "en", 8),
        ("VN", "vi", 3),
    ],
    Region.CHINA: [("CN", "zh", 100)],
}
# A rare third tongue, per region (neighbours/scene languages).
_THIRD_LANGS: dict[Region, list[str]] = {
    Region.AMERICAS: ["es", "pt"],
    Region.EMEA: ["fr", "de", "ru"],
    Region.PACIFIC: ["ko", "ja", "zh"],
    Region.CHINA: ["ko"],
}


def assign_identity(p: Player) -> None:
    """Give a player a country and up to three spoken languages, derived
    from blake2 hashes of their id (draw-free, idempotent — players who
    already have languages are never touched, so authored/pack data wins).
    English fluency varies: some non-natives are fluent, some can call
    rotations only, CN players skew isolated (the real VCT-CN dynamic)."""
    if p.languages:
        if not p.country:
            p.country = "??"
        return
    pool = _REGION_IDENTITY.get(p.region, _REGION_IDENTITY[Region.AMERICAS])
    total = sum(w for _, _, w in pool)
    pick = _hash01(p.id, "country") * total
    country, native = pool[-1][0], pool[-1][1]
    for c, lang, w in pool:
        if pick < w:
            country, native = c, lang
            break
        pick -= w
    if not p.country:
        p.country = country
    langs: list[LanguageSkill] = [
        LanguageSkill(lang=native, level=round(85.0 + _hash01(p.id, "nat") * 15.0, 1))
    ]
    if native != "en":
        u = _hash01(p.id, "eng")
        # CN players skew low-English (many none at all); elsewhere a real
        # spread with a genuine no-English tail.
        eng = None
        if p.region == Region.CHINA:
            eng = 5.0 + u * 35.0 if u < 0.55 else None
        elif u < 0.25:
            eng = 70.0 + (u / 0.25) * 25.0  # properly fluent
        elif u < 0.70:
            eng = 40.0 + (u - 0.25) / 0.45 * 30.0  # can run comms
        elif u < 0.90:
            eng = 10.0 + (u - 0.70) / 0.20 * 30.0  # callouts only
        # else: no English at all — an interpreter-and-pointing situation
        if eng is not None:
            langs.append(LanguageSkill(lang="en", level=round(eng, 1)))
    if _hash01(p.id, "third") < 0.15 and len(langs) < 3:
        extras = [l for l in _THIRD_LANGS.get(p.region, []) if l != native]
        if extras:
            third = extras[int(_hash01(p.id, "thirdpick") * len(extras)) % len(extras)]
            langs.append(LanguageSkill(
                lang=third, level=round(25.0 + _hash01(p.id, "thirdlvl") * 35.0, 1)
            ))
    p.languages = langs


def _hash01(*parts: str) -> float:
    """Stable uniform in [0, 1) from blake2 of the parts — draw-free, so
    callers never disturb any rng stream."""
    b = hashlib.blake2b("|".join(parts).encode(), digest_size=8)
    return int.from_bytes(b.digest(), "big") / 2**64


def backfill_agent_baselines(p: Player, gd: GameData) -> None:
    """Extend a player's authored 2-3 agent pool to the full cast with the
    same baselines generate_player rolls: same-role agents at least okay,
    off-role playable-but-weak, a rare (~6%) off-role true gap. Values come
    from blake2 hashes of (player id, agent id) — no rng stream is touched,
    so it is deterministic AND idempotent (known agents are never altered).
    The bare-engine gates never call this: registry players stay byte-
    identical inside test fixtures; only campaigns run with full sheets."""
    known = {m.agent_id for m in p.agent_pool}
    missing = [aid for aid in sorted(gd.agents) if aid not in known]
    if not missing:
        return
    q = development.overall(p)
    for aid in missing:
        u = _hash01(p.id, aid, "base")
        if gd.agents[aid].role == p.role:
            mv = _clamp(q - 8 + (u - 0.5) * 12, 35, 80)
        elif _hash01(p.id, aid, "gap") < 0.06:
            mv = u * 8  # never touched the agent
        else:
            mv = _clamp(q - 20 + (u - 0.5) * 14, 12, 60)
        p.agent_pool.append(AgentMastery(agent_id=aid, mastery=round(mv, 1)))

# ---------------------------------------------------------------------------
# Name pools. Modest on purpose — uniqueness comes from combination + suffix.

_HANDLE_PARTS_A = [
    "Night", "Frost", "Iron", "Sly", "Neo", "Volt", "Crim", "Zephyr", "Ash",
    "Blitz", "Hollow", "Rift", "Ember", "Static", "Wraith", "Pyro", "Lunar",
    "Cipher", "Drift", "Falcon", "Grim", "Havoc", "Jinx", "Karma",
]
_HANDLE_PARTS_B = [
    "wolf", "byte", "shot", "fade", "strike", "wing", "storm", "wire",
    "blade", "dash", "mark", "veil", "surge", "hawk", "core", "step",
    "ghost", "flare", "lock", "pulse", "zero", "rush", "snap", "echo",
]
_FIRST_NAMES = [
    "Lucas", "Mateo", "Diego", "Ethan", "Noah", "Liam", "Kai", "Jonas",
    "Felix", "Emil", "Hugo", "Oscar", "Arthur", "Leon", "Nikolai", "Marco",
    "Andre", "Victor", "Dmitri", "Yusuf", "Minho", "Jisoo", "Kenta", "Ren",
    "Arjun", "Ravi", "Tomas", "Erik", "Jan", "Pablo", "Santiago", "Gabriel",
]
_LAST_NAMES = [
    "Silva", "Reyes", "Novak", "Kim", "Tanaka", "Petrov", "Larsson", "Weber",
    "Moreau", "Rossi", "Kowalski", "Nakamura", "Park", "Chen", "Costa",
    "Fischer", "Jensen", "Berg", "Santos", "Vargas", "Ito", "Nguyen",
    "Muller", "Janssen", "Horvat", "Sato", "Lopez", "Andersen", "Popov",
    "Takahashi", "Ferreira", "Lindqvist",
]

# Region-flavoured name pools so an EMEA player doesn't read as "Minho
# Nakamura". Keyed by Region; generate_player picks from the player's own
# region (falling back to the mixed global pool above). The global lists
# stay the neutral default and the staff-name source.
_REGION_FIRST_NAMES: dict[Region, list[str]] = {
    Region.AMERICAS: [
        "Lucas", "Mateo", "Diego", "Santiago", "Gabriel", "Pablo", "Ethan",
        "Noah", "Liam", "Marco", "Victor", "Andre",
    ],
    Region.EMEA: [
        "Jonas", "Felix", "Emil", "Hugo", "Oscar", "Arthur", "Leon", "Erik",
        "Jan", "Tomas", "Nikolai", "Dmitri", "Yusuf",
    ],
    Region.PACIFIC: [
        "Kai", "Minho", "Jisoo", "Kenta", "Ren", "Arjun", "Ravi", "Haru",
        "Wei", "Jin", "Tan", "Aditya",
    ],
    Region.CHINA: [
        "Wei", "Jian", "Hao", "Yuxuan", "Zihan", "Cheng", "Bo", "Rui",
        "Feng", "Kaiwen", "Ming", "Junjie",
    ],
}
_REGION_LAST_NAMES: dict[Region, list[str]] = {
    Region.AMERICAS: [
        "Silva", "Reyes", "Santos", "Vargas", "Costa", "Ferreira", "Lopez",
        "Moreno", "Herrera", "Castro",
    ],
    Region.EMEA: [
        "Novak", "Petrov", "Larsson", "Weber", "Moreau", "Rossi", "Kowalski",
        "Fischer", "Jensen", "Berg", "Muller", "Janssen", "Horvat", "Popov",
        "Lindqvist", "Andersen",
    ],
    Region.PACIFIC: [
        "Kim", "Tanaka", "Nakamura", "Park", "Chen", "Ito", "Nguyen", "Sato",
        "Takahashi", "Wong", "Lee", "Sharma",
    ],
    Region.CHINA: [
        "Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao",
        "Wu", "Zhou", "Xu", "Sun",
    ],
}
_TEAM_NAMES = [
    ("Crimson Order", "CRO"),
    ("Nova Rift", "NVR"),
    ("Apex Syndicate", "APX"),
    ("Iron Pact", "IRP"),
    ("Solar Flare", "SOL"),
    ("Phantom Core", "PHC"),
    ("Obsidian Watch", "OBW"),
    ("Azure Vanta", "AZV"),
    ("Kraken Unit", "KRK"),
    ("Ghostline", "GHL"),
    ("Berlin Wolves", "BWV"),
    ("Meridian Cross", "MRC"),
    ("Volga Reign", "VLG"),
    ("Lisbon Tide", "LTD"),
    ("Nordic Frost", "NFR"),
    ("Saracen Guard", "SRG"),
    ("Alpine Echo", "ALE"),
    ("Gallic Storm", "GST"),
    ("Tokyo Drift Six", "TD6"),
    ("Seoul Dynasty Prime", "SDP"),
    ("Manila Monsoon", "MMS"),
    ("Jakarta Ravens", "JKR"),
    ("Mekong Vipers", "MKV"),
    ("Harbour City Nine", "HC9"),
    ("Outback Sentinels", "OBS"),
    ("Mumbai Meteors", "MUM"),
    # Challengers-flavored orgs (tier 2 draws from the same pool; smaller
    # brands read like smaller brands).
    ("Rust Belt Gaming", "RBG"),
    ("Bayou Kings", "BYK"),
    ("Cascadia Youth", "CSY"),
    ("Prairie Signal", "PRS"),
    ("Yucatan Ceibas", "YCB"),
    ("Patagonia Sur", "PSU"),
    ("Midnight Polders", "MDP"),
    ("Adriatic Sirens", "ADS"),
    ("Baltic Meridian", "BLM"),
    ("Anatolia Forge", "ANF"),
    ("Sahara Compass", "SHC"),
    ("Highlands Nine", "HL9"),
    ("Hokkaido Drift", "HKD"),
    ("Busan Tempest", "BST"),
    ("Chao Phraya Owls", "CPO"),
    ("Taipei Circuit", "TPC"),
    ("Kathmandu Apex", "KTA"),
    ("Coral Sea Drakes", "CSD"),
]

# Playstyle archetypes: which attributes run hot (+) or cold (-) relative
# to the player's base quality.
_ARCHETYPES: dict[Playstyle, dict[str, float]] = {
    Playstyle.IGL: {
        "game_sense": 14, "comms_quality": 14, "utility_usage": 8,
        "composure": 8, "aim_precision": -8, "aim_reactivity": -8,
    },
    Playstyle.ENTRY: {
        "aim_precision": 10, "aim_reactivity": 12, "movement": 10,
        "game_sense": -6, "utility_usage": -8, "tilt_resistance": -4,
    },
    Playstyle.ANCHOR: {
        "positioning": 12, "composure": 8, "tilt_resistance": 8,
        "utility_usage": 6, "movement": -6, "aim_reactivity": -4,
    },
    Playstyle.LURKER: {
        "game_sense": 10, "positioning": 8, "clutch_factor": 8,
        "comms_quality": -8, "utility_usage": -4,
    },
    Playstyle.AWPER: {
        "aim_precision": 14, "aim_reactivity": 8, "positioning": 6,
        "clutch_factor": 6, "utility_usage": -8, "comms_quality": -4,
    },
    Playstyle.SUPPORT: {
        "utility_usage": 12, "comms_quality": 10, "composure": 6,
        "game_sense": 6, "aim_precision": -6, "aim_reactivity": -6,
    },
}

# Standard roster shape: one of each playstyle role slot.
_ROSTER_SLOTS: list[tuple[Playstyle, Role]] = [
    (Playstyle.IGL, Role.CONTROLLER),
    (Playstyle.ENTRY, Role.DUELIST),
    (Playstyle.AWPER, Role.DUELIST),
    (Playstyle.SUPPORT, Role.INITIATOR),
    (Playstyle.ANCHOR, Role.SENTINEL),
]
_FA_SLOTS: list[tuple[Playstyle, Role]] = _ROSTER_SLOTS + [
    (Playstyle.LURKER, Role.INITIATOR),
]

_ATTR_IDS = [
    "aim_precision", "aim_reactivity", "movement", "game_sense",
    "utility_usage", "positioning", "clutch_factor", "tilt_resistance",
    "composure", "comms_quality",
]

_TAG_POOL = [
    "grinder", "streamer", "quiet", "hot_head", "veteran", "rookie",
    "team_player", "perfectionist", "independent", "analytical", "flashy",
    "clutch_gene", "slow_starter", "fan_favorite",
]


def _clamp(v: float, lo: float = 1.0, hi: float = 99.0) -> float:
    return float(min(hi, max(lo, v)))


def generate_player(
    rng: np.random.Generator,
    pid: str,
    playstyle: Playstyle,
    role: Role,
    quality: float,
    gd: GameData,
    region: Region = Region.AMERICAS,
    age_lo: int = 17,
    age_hi: int = 29,
) -> Player:
    """One player around a base `quality` (roughly 40-85), shaped by their
    playstyle archetype."""
    handle = (
        str(rng.choice(_HANDLE_PARTS_A))
        + str(rng.choice(_HANDLE_PARTS_B)).lower()
    )
    firsts = _REGION_FIRST_NAMES.get(region, _FIRST_NAMES)
    lasts = _REGION_LAST_NAMES.get(region, _LAST_NAMES)
    real_name = f"{rng.choice(firsts)} {rng.choice(lasts)}"
    age = int(rng.integers(age_lo, age_hi))
    # Younger players trade current quality for growth headroom.
    q = quality - max(0, 22 - age) * 1.5

    shape = _ARCHETYPES[playstyle]
    attributes = {}
    for attr_id in _ATTR_IDS:
        base = q + shape.get(attr_id, 0.0) + rng.normal(0, 5)
        attributes[attr_id] = round(_clamp(base), 1)

    # Agent pool: 2 signature agents matching role + 1 off-role flex pick run
    # hot, then EVERY other agent gets a baseline so nobody reads as "0" on
    # the rest of the cast: same-role agents are at least okay (an entry
    # duelist can run any duelist), off-role agents are playable-but-weak,
    # and a rare off-role gap (~never played) survives as the exception.
    role_agents = sorted(a.id for a in gd.agents.values() if a.role == role)
    other_agents = sorted(a.id for a in gd.agents.values() if a.role != role)
    picks = list(rng.permutation(role_agents))[:2]
    picks += [str(rng.choice(other_agents))]
    # AWPers main the op-affinity kit of their role (Jett/Chamber): it
    # leads their signature picks and gets a mastery nudge below, so the
    # engine's best-mastery auto-pick fields them on it. Deterministic —
    # the rng draw count is unchanged.
    if playstyle is Playstyle.AWPER:
        aff = [a for a in role_agents if gd.agents[a].op_affinity]
        if aff and not any(a in aff for a in picks[:2]):
            picks[0] = aff[0]
    agent_pool = [
        AgentMastery(
            agent_id=str(a),
            mastery=round(_clamp(
                q + rng.normal(12, 8)
                + (6.0 if playstyle is Playstyle.AWPER and gd.agents[str(a)].op_affinity else 0.0),
                30, 99), 1),
        )
        for a in picks
    ]
    signature = {m.agent_id for m in agent_pool}
    for aid in role_agents:
        if aid in signature:
            continue
        agent_pool.append(AgentMastery(
            agent_id=aid, mastery=round(_clamp(q - 8 + rng.normal(0, 5), 35, 80), 1)
        ))
    for aid in other_agents:
        if aid in signature:
            continue
        if rng.random() < 0.06:  # the rare true gap: never touched the agent
            agent_pool.append(AgentMastery(
                agent_id=aid, mastery=round(float(rng.uniform(0, 8)), 1)
            ))
        else:
            agent_pool.append(AgentMastery(
                agent_id=aid, mastery=round(_clamp(q - 20 + rng.normal(0, 6), 12, 60), 1)
            ))
    map_pool = [
        MapMastery(map_id=mid, mastery=round(_clamp(q + rng.normal(8, 9), 30, 99), 1))
        for mid in sorted(gd.maps)
    ]

    n_tags = int(rng.integers(1, 3))
    tags = [str(t) for t in rng.choice(_TAG_POOL, size=n_tags, replace=False)]

    salary = int(np.round((quality ** 1.6) * 6 / 100) * 100)
    p = Player(
        id=pid,
        handle=handle,
        real_name=real_name,
        region=region,
        age=age,
        role=role,
        playstyle=playstyle,
        attributes=attributes,
        agent_pool=agent_pool,
        map_pool=map_pool,
        salary=max(salary, 1200),
        contract_weeks_left=int(rng.integers(10, 70)),
        morale=round(float(rng.uniform(55, 85)), 1),
        stamina=round(float(rng.uniform(70, 100)), 1),
        form=round(float(rng.uniform(40, 65)), 1),
        personality_tags=tags,
    )
    development.assign_potential(p, rng)
    assign_identity(p)  # hash-based: no rng draw
    return p


def generate_league_teams(
    rng: np.random.Generator,
    gd: GameData,
    n_teams: int = 6,
    region: Region = Region.AMERICAS,
    used_names: set[str] | None = None,
    tier: int = 1,
) -> tuple[list[Team], list[Player]]:
    """Generate `n_teams` orgs with full rosters, spread across a quality
    ladder so the league has a top, a middle, and a bottom. `used_names`
    keeps org names unique across multi-region generation.

    Tier 2 (Challengers) orgs are younger, rawer, and poorer: lower CA
    on a lower ladder, teenage-heavy rosters with big CA→PA gaps — a
    development circuit worth scouting."""
    teams: list[Team] = []
    players: list[Player] = []
    used = used_names if used_names is not None else set()
    available = [i for i, (n, _) in enumerate(_TEAM_NAMES) if n not in used]
    if len(available) < n_teams:
        raise ValueError(
            f"team-name pool exhausted: need {n_teams} unique names, only "
            f"{len(available)} left of {len(_TEAM_NAMES)} (already used "
            f"{len(used)}). Add more entries to _TEAM_NAMES."
        )
    name_order = [
        available[int(k)] for k in rng.permutation(len(available))
    ][:n_teams]
    top_q = 74.0 if tier == 1 else 58.0
    span = 16.0 if tier == 1 else 12.0
    age_lo, age_hi = (17, 29) if tier == 1 else (17, 23)
    for i, name_idx in enumerate(name_order):
        name, tag = _TEAM_NAMES[int(name_idx)]
        used.add(name)
        slug = "team_" + name.lower().replace(" ", "_")
        # Quality ladder kept narrow on purpose: with per-duel edges
        # compounding over rounds, a 20+ point team gap makes the league
        # a foregone conclusion.
        team_q = top_q - i * (span / max(n_teams - 1, 1))
        roster_ids: list[str] = []
        captain_id: str | None = None
        for j, (style, role) in enumerate(_ROSTER_SLOTS):
            pid = f"{slug}_p{j}"
            quality = float(np.clip(team_q + rng.normal(0, 4), 35, 88))
            p = generate_player(
                rng, pid, style, role, quality, gd,
                region=region, age_lo=age_lo, age_hi=age_hi,
            )
            players.append(p)
            roster_ids.append(pid)
            if style == Playstyle.IGL:
                captain_id = pid
        teams.append(
            Team(
                id=slug,
                name=name,
                tag=tag,
                region=region,
                tier=tier,
                player_ids=roster_ids,
                captain_id=captain_id,
                balance=int(rng.integers(300, 900)) * (1000 if tier == 1 else 300),
                reputation=round(_clamp(team_q + rng.normal(0, 6), 20, 95), 1),
                fan_count=int(rng.integers(50, 800)) * (1000 if tier == 1 else 150),
                chemistry=round(float(rng.uniform(55, 85)), 1),
            )
        )
    return teams, players


def generate_free_agents(
    rng: np.random.Generator, gd: GameData, n: int = 18
) -> list[Player]:
    """Signable pool: mostly journeymen, a few gems, a few washed veterans."""
    out: list[Player] = []
    for i in range(n):
        style, role = _FA_SLOTS[i % len(_FA_SLOTS)]
        roll = rng.random()
        if roll < 0.15:
            quality = float(rng.uniform(68, 82))  # gem
        elif roll < 0.35:
            quality = float(rng.uniform(38, 50))  # project / washed
        else:
            quality = float(rng.uniform(50, 66))  # journeyman
        p = generate_player(rng, f"fa_{i}", style, role, quality, gd)
        p.contract_weeks_left = 0
        out.append(p)
    return out
