"""YAML -> Pydantic loaders.

Anything Valorant-specific (agents, weapons, maps, teams) is authored in
`data/` as YAML and loaded here. Schemas are strict (`extra="forbid"`)
so a typo in a data file fails loudly at load time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from esports_sim.schemas import (
    Agent,
    AttributeDefinition,
    AttributeRegistry,
    Map,
    Player,
    Team,
    Weapon,
)


# Resolve `data/` relative to the repo root (two parents up from this file
# would land us in src/; three up lands us at repo root).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = _REPO_ROOT / "data"


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Individual loaders


def load_attributes(data_dir: Path | None = None) -> AttributeRegistry:
    data_dir = data_dir or DEFAULT_DATA_DIR
    raw = _load_yaml(data_dir / "attributes.yaml")
    defs = [AttributeDefinition(**d) for d in raw["attributes"]]
    return AttributeRegistry.from_list(defs)


def load_agents(data_dir: Path | None = None) -> dict[str, Agent]:
    data_dir = data_dir or DEFAULT_DATA_DIR
    raw = _load_yaml(data_dir / "agents.yaml")
    agents = [Agent(**a) for a in raw["agents"]]
    return {a.id: a for a in agents}


def load_weapons(data_dir: Path | None = None) -> dict[str, Weapon]:
    data_dir = data_dir or DEFAULT_DATA_DIR
    raw = _load_yaml(data_dir / "weapons.yaml")
    weapons = [Weapon(**w) for w in raw["weapons"]]
    return {w.id: w for w in weapons}


def load_map(map_id: str, data_dir: Path | None = None) -> Map:
    data_dir = data_dir or DEFAULT_DATA_DIR
    raw = _load_yaml(data_dir / "maps" / f"{map_id}.yaml")
    return Map(**raw)


def load_team(team_id: str, data_dir: Path | None = None) -> tuple[Team, list[Player]]:
    """Load a team plus its players. Teams bundle player data inline for MVP."""
    data_dir = data_dir or DEFAULT_DATA_DIR
    raw = _load_yaml(data_dir / "teams" / f"{team_id}.yaml")
    players = [Player(**p) for p in raw.pop("players", [])]
    team = Team(**raw, player_ids=[p.id for p in players])
    return team, players


# ---------------------------------------------------------------------------
# Bundle


class GameData(BaseModel):
    """A resolved bundle of all registries + starter teams. Convenient for
    tests and for the CLI entry point."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    attributes: AttributeRegistry
    agents: dict[str, Agent]
    weapons: dict[str, Weapon]
    maps: dict[str, Map]
    teams: dict[str, Team]
    players: dict[str, Player]


def load_all(
    map_ids: list[str] | None = None,
    team_ids: list[str] | None = None,
    data_dir: Path | None = None,
) -> GameData:
    data_dir = data_dir or DEFAULT_DATA_DIR
    map_ids = map_ids or ["haven", "ascent", "bind", "lotus", "split"]
    team_ids = team_ids or ["team_nexus", "team_vanguard"]

    attributes = load_attributes(data_dir)
    agents = load_agents(data_dir)
    weapons = load_weapons(data_dir)

    maps: dict[str, Map] = {}
    for mid in map_ids:
        m = load_map(mid, data_dir)
        maps[m.id] = m

    teams: dict[str, Team] = {}
    players: dict[str, Player] = {}
    for tid in team_ids:
        team, team_players = load_team(tid, data_dir)
        teams[team.id] = team
        for p in team_players:
            players[p.id] = p

    return GameData(
        attributes=attributes,
        agents=agents,
        weapons=weapons,
        maps=maps,
        teams=teams,
        players=players,
    )
