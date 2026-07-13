"""Roster packs — importable real-world (or custom) league worlds.

A pack is a directory under ``data/rosters/<pack_id>/``:

    pack.yaml         # meta + world shape (regions, league sizes)
    teams/*.yaml      # full Team + inline players, SAME schema as data/teams/
    free_agents.yaml  # optional: unrostered real players seeding the FA pool

Team files are the exact ``load_team`` bundle format, so a pack team is
authored/validated identically to a starter team. Packs are static data:
loading one is deterministic by construction, and ``new_campaign`` seeds
the world from the pack's teams instead of the fictional starters, then
generates fill only for any shortfall (a partial pack still plays).

Packs are typically not hand-written — ``scripts/build_roster_pack.py``
expands a compact per-player spec (``src/*.yaml``) into these bundles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from esports_sim.registry.loader import DEFAULT_DATA_DIR
from esports_sim.schemas import FutureProspect, Player, Team
from esports_sim.schemas.common import Region


class PackWorld(BaseModel):
    """World shape a pack requests. Defaults mirror the classic world."""

    model_config = ConfigDict(extra="forbid")

    # 3 or 4 regions only — those are the Masters bracket shapes the season
    # state machine knows (6-side with byes / 8-side full QF).
    league_regions: list[Region] = Field(
        default_factory=lambda: [Region.AMERICAS, Region.EMEA, Region.PACIFIC]
    )
    # >=4 so the regional playoff bracket (top 4) can always be seeded.
    teams_per_region: int = Field(default=8, ge=4, le=16)
    tier2_per_region: int = Field(default=6, ge=0, le=16)


class PackMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    # Real-world calendar year represented by Season 1. Optional so existing
    # custom packs remain valid; required when a pack ships future prospects.
    start_year: int | None = Field(default=None, ge=2021, le=2100)
    world: PackWorld = Field(default_factory=PackWorld)


@dataclass
class RosterPack:
    meta: PackMeta
    teams: dict[str, Team] = field(default_factory=dict)
    players: dict[str, Player] = field(default_factory=dict)
    # Unrostered real players (benched pros, org-less veterans, notable
    # streamers) who seed the campaign's free-agent pool. Kept OUT of
    # `players` so roster maths never counts them.
    free_agents: dict[str, Player] = field(default_factory=dict)
    future_prospects: dict[str, FutureProspect] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.meta.id


def _packs_dir(data_dir: Path | None = None) -> Path:
    return (data_dir or DEFAULT_DATA_DIR) / "rosters"


def list_roster_packs(data_dir: Path | None = None) -> list[PackMeta]:
    """Metas of every pack on disk, sorted by id. Invalid packs raise —
    a broken pack should fail loudly, not vanish from the menu."""
    root = _packs_dir(data_dir)
    if not root.is_dir():
        return []
    metas = []
    for d in sorted(p for p in root.iterdir() if (p / "pack.yaml").is_file()):
        raw = yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8"))
        meta = PackMeta(**raw)
        if meta.id != d.name:
            raise ValueError(
                f"roster pack dir {d.name!r} declares id {meta.id!r} — "
                "the directory name and pack.yaml id must match."
            )
        metas.append(meta)
    return metas


def load_roster_pack(pack_id: str, data_dir: Path | None = None) -> RosterPack:
    d = _packs_dir(data_dir) / pack_id
    if not (d / "pack.yaml").is_file():
        raise FileNotFoundError(f"no roster pack {pack_id!r} under {d.parent}")
    meta = PackMeta(**yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8")))
    if meta.id != pack_id:
        raise ValueError(
            f"roster pack dir {pack_id!r} declares id {meta.id!r} — "
            "the directory name and pack.yaml id must match."
        )
    teams: dict[str, Team] = {}
    players: dict[str, Player] = {}
    for f in sorted((d / "teams").glob("*.yaml")):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        team_players = [Player(**p) for p in raw.pop("players", [])]
        team = Team(**raw, player_ids=[p.id for p in team_players])
        if team.id in teams:
            raise ValueError(f"pack {pack_id!r}: duplicate team id {team.id!r}")
        for p in team_players:
            if p.id in players:
                raise ValueError(
                    f"pack {pack_id!r}: duplicate player id {p.id!r}"
                )
            players[p.id] = p
        teams[team.id] = team

    free_agents: dict[str, Player] = {}
    fa_file = d / "free_agents.yaml"
    if fa_file.is_file():
        raw = yaml.safe_load(fa_file.read_text(encoding="utf-8")) or {}
        for entry in raw.get("free_agents", []):
            p = Player(**entry)
            if p.id in players or p.id in free_agents:
                raise ValueError(
                    f"pack {pack_id!r}: free agent {p.id!r} duplicates a player id"
                )
            free_agents[p.id] = p

    future_prospects: dict[str, FutureProspect] = {}
    prospect_file = d / "future_prospects.yaml"
    if prospect_file.is_file():
        raw = yaml.safe_load(prospect_file.read_text(encoding="utf-8")) or {}
        for entry in raw.get("future_prospects", []):
            prospect = FutureProspect(**entry)
            p = prospect.player
            if p.id in players or p.id in free_agents or p.id in future_prospects:
                raise ValueError(
                    f"pack {pack_id!r}: future prospect {p.id!r} duplicates a player id"
                )
            future_prospects[p.id] = prospect

    pack = RosterPack(
        meta=meta, teams=teams, players=players, free_agents=free_agents,
        future_prospects=future_prospects,
    )
    _validate(pack)
    return pack


def _validate(pack: RosterPack) -> None:
    w = pack.meta.world
    if len(w.league_regions) not in (3, 4):
        raise ValueError(
            f"pack {pack.id!r}: {len(w.league_regions)} league regions — "
            "the season state machine supports exactly 3 or 4."
        )
    if len(set(w.league_regions)) != len(w.league_regions):
        raise ValueError(f"pack {pack.id!r}: duplicate league regions")
    region_set = set(w.league_regions)
    if pack.future_prospects and pack.meta.start_year is None:
        raise ValueError(
            f"pack {pack.id!r}: future prospects require pack.yaml start_year"
        )
    for t in pack.teams.values():
        if t.region not in region_set:
            raise ValueError(
                f"pack {pack.id!r}: team {t.id!r} is in {t.region}, which is "
                f"not one of the pack's league_regions"
            )
        if t.tier == 1 and len(t.player_ids) != 5:
            raise ValueError(
                f"pack {pack.id!r}: tier-1 team {t.id!r} has "
                f"{len(t.player_ids)} players (needs exactly 5)"
            )
        if t.captain_id is not None and t.captain_id not in t.player_ids:
            raise ValueError(
                f"pack {pack.id!r}: team {t.id!r} captain {t.captain_id!r} "
                "is not on its roster"
            )
    for region in w.league_regions:
        n1 = sum(
            1 for t in pack.teams.values() if t.region == region and t.tier == 1
        )
        if n1 > w.teams_per_region:
            raise ValueError(
                f"pack {pack.id!r}: {n1} tier-1 teams in {region} exceeds "
                f"teams_per_region={w.teams_per_region}"
            )
    # Prospects may be imported from an unplayed region (for example China in
    # the 2021 historical pack). They enter the global free-agent market at
    # their debut, so unlike a team they do not require a scheduled league.
    for prospect in pack.future_prospects.values():
        if prospect.player.age >= 17:
            raise ValueError(
                f"pack {pack.id!r}: future prospect {prospect.player.id!r} is already 17"
            )
        if prospect.debut_year <= pack.meta.start_year:
            raise ValueError(
                f"pack {pack.id!r}: future prospect {prospect.player.id!r} must debut after start_year"
            )
