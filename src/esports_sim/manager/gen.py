"""Deterministic player / team generation.

Everything derives from the campaign RngTree, so a new game with the same
seed produces the same league, rosters, and free agents.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager import development
from esports_sim.registry.loader import GameData
from esports_sim.schemas import AgentMastery, MapMastery, Player, Team
from esports_sim.schemas.common import Playstyle, Region, Role

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
) -> Player:
    """One player around a base `quality` (roughly 40-85), shaped by their
    playstyle archetype."""
    handle = (
        str(rng.choice(_HANDLE_PARTS_A))
        + str(rng.choice(_HANDLE_PARTS_B)).lower()
    )
    real_name = f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
    age = int(rng.integers(17, 29))
    # Younger players trade current quality for growth headroom.
    q = quality - max(0, 22 - age) * 1.5

    shape = _ARCHETYPES[playstyle]
    attributes = {}
    for attr_id in _ATTR_IDS:
        base = q + shape.get(attr_id, 0.0) + rng.normal(0, 5)
        attributes[attr_id] = round(_clamp(base), 1)

    # Agent pool: 2 agents matching role + 1 off-role flex pick.
    role_agents = sorted(a.id for a in gd.agents.values() if a.role == role)
    other_agents = sorted(a.id for a in gd.agents.values() if a.role != role)
    picks = list(rng.permutation(role_agents))[:2]
    picks += [str(rng.choice(other_agents))]
    agent_pool = [
        AgentMastery(agent_id=str(a), mastery=round(_clamp(q + rng.normal(12, 8), 30, 99), 1))
        for a in picks
    ]
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
    return p


def generate_league_teams(
    rng: np.random.Generator, gd: GameData, n_teams: int = 6
) -> tuple[list[Team], list[Player]]:
    """Generate `n_teams` orgs with full rosters, spread across a quality
    ladder so the league has a top, a middle, and a bottom."""
    teams: list[Team] = []
    players: list[Player] = []
    name_order = list(rng.permutation(len(_TEAM_NAMES)))[:n_teams]
    for i, name_idx in enumerate(name_order):
        name, tag = _TEAM_NAMES[int(name_idx)]
        slug = "team_" + name.lower().replace(" ", "_")
        # Quality ladder from ~74 down to ~58. Kept narrow on purpose:
        # with per-duel edges compounding over rounds, a 20+ point team
        # gap makes the league a foregone conclusion.
        team_q = 74.0 - i * (16.0 / max(n_teams - 1, 1))
        roster_ids: list[str] = []
        captain_id: str | None = None
        for j, (style, role) in enumerate(_ROSTER_SLOTS):
            pid = f"{slug}_p{j}"
            quality = float(np.clip(team_q + rng.normal(0, 4), 40, 88))
            p = generate_player(rng, pid, style, role, quality, gd)
            players.append(p)
            roster_ids.append(pid)
            if style == Playstyle.IGL:
                captain_id = pid
        teams.append(
            Team(
                id=slug,
                name=name,
                tag=tag,
                region=Region.AMERICAS,
                player_ids=roster_ids,
                captain_id=captain_id,
                balance=int(rng.integers(300, 900)) * 1000,
                reputation=round(_clamp(team_q + rng.normal(0, 6), 20, 95), 1),
                fan_count=int(rng.integers(50, 800)) * 1000,
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
