"""Portable roster-pack documents for humans, agents, and Roster Studio.

The compact source sheets remain the canonical authored representation used by
``roster_pack_builder``. This module presents those sheets as one strict,
portable YAML/JSON document, validates it, and installs it atomically. The CLI
and web UI both call this module so they cannot disagree about a pack.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from esports_sim.registry.loader import DEFAULT_DATA_DIR, GameData, load_all
from esports_sim.registry.roster_pack_builder import build, slugify
from esports_sim.registry.rosters import list_roster_packs, load_roster_pack
from esports_sim.schemas.common import Playstyle, Region, Role

# v2: DraftPlayer grew optional `tags` (canonical personality tags the
# pack builder already consumed from src sheets — vct-2021 uses them).
# v1 documents remain valid; they simply carry no tags.
SCHEMA_VERSION = 2
_INSTALL_LOCK = threading.Lock()
_ATTR_IDS = {
    "aim_precision", "aim_reactivity", "movement", "game_sense",
    "utility_usage", "positioning", "clutch_factor", "tilt_resistance",
    "composure", "comms_quality",
}


def _ascii(value: str, label: str) -> str:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must use ASCII characters") from exc
    return value


class DraftLanguage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lang: str = Field(min_length=2, max_length=12, pattern=r"^[a-zA-Z0-9-]+$")
    level: float = Field(default=80, ge=0, le=100)


class DraftPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handle: str = Field(min_length=1, max_length=40)
    real_name: str = Field(default="", max_length=100)
    age: int = Field(default=20, ge=14, le=45)
    country: str = Field(default="", max_length=8)
    languages: list[DraftLanguage] = Field(default_factory=list, max_length=3)
    role: Role = Role.FLEX
    playstyle: Playstyle = Playstyle.SUPPORT
    igl: bool = False
    quality: float = Field(default=60, ge=1, le=99)
    agents: list[str] = Field(default_factory=list, max_length=3)
    attr_overrides: dict[str, float] = Field(default_factory=dict)
    potential: float | None = Field(default=None, ge=1, le=99)
    career_volatility: float | None = Field(default=None, ge=0, le=100)
    development_archetype: str | None = Field(default=None, pattern=r"^(flash|early|steady|late)$")
    development_peak_age: int | None = Field(default=None, ge=15, le=40)
    development_peak_years: int | None = Field(default=None, ge=1, le=15)
    development_decline_age: int | None = Field(default=None, ge=20, le=45)
    development_realization: float | None = Field(default=None, ge=0.5, le=1.0)
    # Personality tags: optional authored identity ("rookie", "veteran",
    # ...). The pack builder has always consumed these from src sheets;
    # untagged players get deterministic tags rolled at build time. The
    # vocabulary is deliberately OPEN — personality.py no-ops tags it
    # doesn't know — so only the format is validated here.
    tags: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("handle", "real_name", "country")
    @classmethod
    def text_is_ascii(cls, value: str, info) -> str:
        return _ascii(value, info.field_name)

    @field_validator("agents")
    @classmethod
    def agent_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("agent ids must be unique")
        return value

    @field_validator("tags")
    @classmethod
    def tags_are_slugs_and_unique(cls, value: list[str]) -> list[str]:
        for tag in value:
            if not re.fullmatch(r"[a-z0-9_]{2,32}", tag):
                raise ValueError(
                    f"tag '{tag}' must be a lowercase slug (a-z, 0-9, _)"
                )
        if len(set(value)) != len(value):
            raise ValueError("personality tags must be unique")
        return value

    @field_validator("attr_overrides")
    @classmethod
    def overrides_are_known_and_bounded(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        unknown = sorted(set(value) - _ATTR_IDS)
        if unknown:
            raise ValueError(f"unknown attribute ids: {unknown}")
        if any(not 1 <= float(v) <= 99 for v in value.values()):
            raise ValueError("attribute overrides must be between 1 and 99")
        return value


class DraftFreeAgent(DraftPlayer):
    region: Region = Region.AMERICAS


class DraftTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    tag: str = Field(min_length=1, max_length=8)
    region: Region = Region.AMERICAS
    tier: int = Field(default=1, ge=1, le=2)
    prestige: float = Field(default=50, ge=1, le=99)
    partial: bool = False
    players: list[DraftPlayer] = Field(default_factory=list, max_length=5)

    @field_validator("name", "tag")
    @classmethod
    def text_is_ascii(cls, value: str, info) -> str:
        return _ascii(value, info.field_name)

    @model_validator(mode="after")
    def roster_shape(self) -> "DraftTeam":
        if self.tier == 1 and len(self.players) != 5:
            raise ValueError("tier-1 teams need exactly 5 players")
        igls = sum(1 for p in self.players if p.igl)
        if self.tier == 1 and igls != 1:
            raise ValueError("tier-1 teams need exactly one IGL")
        if self.tier == 2 and igls > 1:
            raise ValueError("teams cannot have more than one IGL")
        handles = [slugify(p.handle) for p in self.players]
        if len(set(handles)) != len(handles):
            raise ValueError("player handles must be unique within a team")
        return self


class DraftWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")

    league_regions: list[Region] = Field(min_length=3, max_length=4)
    teams_per_region: int = Field(default=8, ge=4, le=16)
    tier2_per_region: int = Field(default=6, ge=0, le=16)

    @field_validator("league_regions")
    @classmethod
    def regions_are_unique(cls, value: list[Region]) -> list[Region]:
        if len(set(value)) != len(value):
            raise ValueError("league regions must be unique")
        return value


class RosterPackDocument(BaseModel):
    """The stable AI/tool handoff contract. JSON and YAML use the same keys."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
    id: str = Field(
        min_length=2,
        max_length=48,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    world: DraftWorld
    teams: list[DraftTeam] = Field(default_factory=list)
    free_agents: list[DraftFreeAgent] = Field(default_factory=list)

    @field_validator("name", "description")
    @classmethod
    def text_is_ascii(cls, value: str, info) -> str:
        return _ascii(value, info.field_name)

    @model_validator(mode="after")
    def pack_shape(self) -> "RosterPackDocument":
        regions = set(self.world.league_regions)
        bad_regions = sorted(
            {str(t.region) for t in self.teams if t.region not in regions}
            | {str(p.region) for p in self.free_agents if p.region not in regions}
        )
        if bad_regions:
            raise ValueError(
                f"entries use regions outside world.league_regions: {bad_regions}"
            )
        slugs = [slugify(t.name) for t in self.teams]
        if len(set(slugs)) != len(slugs):
            raise ValueError("team names must produce unique ids")
        fa_ids = [slugify(p.handle) for p in self.free_agents]
        if len(set(fa_ids)) != len(fa_ids):
            raise ValueError("free-agent handles must produce unique ids")
        if not any(t.tier == 1 for t in self.teams):
            raise ValueError("a pack needs at least one authored tier-1 team to select")
        for region in self.world.league_regions:
            tier1 = sum(
                1 for t in self.teams if t.region == region and t.tier == 1
            )
            tier2 = sum(
                1 for t in self.teams if t.region == region and t.tier == 2
            )
            if tier1 > self.world.teams_per_region:
                raise ValueError(
                    f"{region} has {tier1} tier-1 teams, above teams_per_region"
                )
            if tier2 > self.world.tier2_per_region:
                raise ValueError(
                    f"{region} has {tier2} tier-2 teams, above tier2_per_region"
                )
        return self


def _errors(exc: ValidationError) -> list[dict[str, str]]:
    out = []
    for error in exc.errors(include_url=False):
        loc = ".".join(str(part) for part in error["loc"])
        out.append({"path": loc or "document", "message": error["msg"]})
    return out


def validate_document(raw: Any, gd: GameData | None = None) -> dict[str, Any]:
    """Validate raw JSON/YAML-compatible data without raising."""
    try:
        document = RosterPackDocument.model_validate(raw)
    except ValidationError as exc:
        return {
            "valid": False,
            "errors": _errors(exc),
            "warnings": [],
            "summary": None,
        }

    gd = gd or load_all()
    errors: list[dict[str, str]] = []
    for ti, team in enumerate(document.teams):
        for pi, player in enumerate(team.players):
            for ai, agent in enumerate(player.agents):
                if agent not in gd.agents:
                    errors.append({
                        "path": f"teams.{ti}.players.{pi}.agents.{ai}",
                        "message": f"unknown agent id '{agent}'",
                    })
    for pi, player in enumerate(document.free_agents):
        for ai, agent in enumerate(player.agents):
            if agent not in gd.agents:
                errors.append({
                    "path": f"free_agents.{pi}.agents.{ai}",
                    "message": f"unknown agent id '{agent}'",
                })

    warnings = []
    for region in document.world.league_regions:
        authored = sum(
            1 for t in document.teams if t.region == region and t.tier == 1
        )
        if authored < document.world.teams_per_region:
            warnings.append(
                f"{region}: {document.world.teams_per_region - authored} tier-1 "
                "teams will be generated when a campaign starts"
            )
    for team in document.teams:
        if team.tier == 2 and len(team.players) < 5:
            warnings.append(
                f"{team.name}: {5 - len(team.players)} academy players will be generated"
            )

    summary = {
        "id": document.id,
        "regions": [str(r) for r in document.world.league_regions],
        "teams": len(document.teams),
        "tier1_teams": sum(1 for t in document.teams if t.tier == 1),
        "tier2_teams": sum(1 for t in document.teams if t.tier == 2),
        "players": sum(len(t.players) for t in document.teams),
        "free_agents": len(document.free_agents),
    }
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
    }


def parse_document(text: str) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML/JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("roster document must be an object")
    return raw


def dump_document(document: RosterPackDocument | dict[str, Any]) -> str:
    doc = (
        document
        if isinstance(document, RosterPackDocument)
        else RosterPackDocument.model_validate(document)
    )
    return yaml.safe_dump(
        doc.model_dump(mode="json"),
        sort_keys=False,
        width=100,
        allow_unicode=False,
    )


def load_document(
    pack_id: str, data_dir: Path | None = None
) -> RosterPackDocument:
    """Reconstruct one portable document from an installed pack's src sheets."""
    root = (data_dir or DEFAULT_DATA_DIR) / "rosters" / pack_id
    pack = load_roster_pack(pack_id, data_dir)
    teams: list[dict[str, Any]] = []
    by_region: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((root / "src").glob("*.yaml")):
        if path.name in {"free_agents.yaml", "pack.yaml"}:
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        by_region.setdefault(str(raw.get("region", "")), []).extend(
            raw.get("teams", [])
        )
    for region in pack.meta.world.league_regions:
        for team in by_region.get(str(region), []):
            teams.append({**team, "region": str(region)})

    fa_path = root / "src" / "free_agents.yaml"
    free_agents = []
    if fa_path.is_file():
        free_agents = (
            yaml.safe_load(fa_path.read_text(encoding="utf-8")) or {}
        ).get("free_agents", [])
    return RosterPackDocument.model_validate({
        "schema_version": SCHEMA_VERSION,
        "id": pack.meta.id,
        "name": pack.meta.name,
        "description": pack.meta.description,
        "world": pack.meta.world.model_dump(mode="json"),
        "teams": teams,
        "free_agents": free_agents,
    })


def _write_sources(pack_dir: Path, document: RosterPackDocument) -> None:
    src = pack_dir / "src"
    src.mkdir(parents=True, exist_ok=True)
    for old in src.glob("*.yaml"):
        old.unlink()
    meta = {
        "schema_version": SCHEMA_VERSION,
        "id": document.id,
        "name": document.name,
        "description": document.description,
        "world": document.world.model_dump(mode="json"),
    }
    (src / "pack.yaml").write_text(
        yaml.safe_dump(meta, sort_keys=False, width=100), encoding="ascii"
    )
    for region in document.world.league_regions:
        teams = []
        for team in document.teams:
            if team.region != region:
                continue
            row = team.model_dump(mode="json")
            row.pop("region")
            teams.append(row)
        (src / f"{region}.yaml").write_text(
            yaml.safe_dump(
                {"region": str(region), "teams": teams},
                sort_keys=False,
                width=100,
            ),
            encoding="ascii",
        )
    (src / "free_agents.yaml").write_text(
        yaml.safe_dump(
            {
                "free_agents": [
                    p.model_dump(mode="json") for p in document.free_agents
                ]
            },
            sort_keys=False,
            width=100,
        ),
        encoding="ascii",
    )


def install_document(
    raw: RosterPackDocument | dict[str, Any], data_dir: Path | None = None
) -> dict[str, Any]:
    """Validate, compile, and atomically install a portable roster document."""
    document = (
        raw
        if isinstance(raw, RosterPackDocument)
        else RosterPackDocument.model_validate(raw)
    )
    result = validate_document(document)
    if not result["valid"]:
        first = result["errors"][0]
        raise ValueError(f"{first['path']}: {first['message']}")

    data_root = data_dir or DEFAULT_DATA_DIR
    roster_root = data_root / "rosters"
    target = roster_root / document.id
    roster_root.mkdir(parents=True, exist_ok=True)
    with _INSTALL_LOCK:
        temp_root = Path(
            tempfile.mkdtemp(prefix="roster-studio-", dir=roster_root.parent)
        )
        staged = temp_root / "rosters" / document.id
        backup: Path | None = None
        try:
            if target.is_dir():
                shutil.copytree(target, staged)
            else:
                staged.mkdir(parents=True)
            _write_sources(staged, document)
            summary_text = build(document.id, data_dir=temp_root)
            compiled = load_roster_pack(document.id, data_dir=temp_root)

            if target.exists():
                backup = target.with_name(
                    f".{target.name}.backup-{uuid.uuid4().hex}"
                )
                target.rename(backup)
            staged.rename(target)
            if backup is not None:
                shutil.rmtree(backup)
            result["compiled"] = {
                "teams": len(compiled.teams),
                "players": len(compiled.players),
                "free_agents": len(compiled.free_agents),
                "summary": summary_text,
            }
            return result
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                backup.rename(target)
            raise
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


def list_documents(data_dir: Path | None = None) -> list[dict[str, Any]]:
    root = (data_dir or DEFAULT_DATA_DIR) / "rosters"
    out = []
    for meta in list_roster_packs(data_dir):
        source = root / meta.id / "src"
        out.append({
            "id": meta.id,
            "name": meta.name,
            "description": meta.description,
            "regions": [str(r) for r in meta.world.league_regions],
            "teams_per_region": meta.world.teams_per_region,
            "editable": source.is_dir(),
        })
    return out


def library_revision(data_dir: Path | None = None) -> tuple[tuple[str, int], ...]:
    """Return a cheap installed-pack fingerprint for cross-process caches.

    Roster Studio runs in the web process, while the MCP server normally runs
    as a separate stdio process. Atomic installation replaces ``pack.yaml``;
    these mtimes let a live Play lobby see either writer's changes.
    """
    root = (data_dir or DEFAULT_DATA_DIR) / "rosters"
    if not root.is_dir():
        return ()
    return tuple(
        (directory.name, (directory / "pack.yaml").stat().st_mtime_ns)
        for directory in sorted(root.iterdir())
        if directory.is_dir() and (directory / "pack.yaml").is_file()
    )


def example_document() -> dict[str, Any]:
    """A small valid document agents can copy and mutate."""
    players = [
        ("caller", "controller", "igl", True, ["omen", "viper"], ["veteran"]),
        ("entry", "duelist", "entry", False, ["jett", "raze"], ["rookie"]),
        ("support", "initiator", "support", False, ["sova", "breach"], []),
        ("anchor", "sentinel", "anchor", False, ["killjoy", "cypher"], []),
        ("flex", "flex", "lurker", False, ["viper", "omen"], []),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "id": "my-roster-pack",
        "name": "My Roster Pack",
        "description": "A custom world built in Roster Studio.",
        "world": {
            "league_regions": ["americas", "emea", "pacific"],
            "teams_per_region": 8,
            "tier2_per_region": 4,
        },
        "teams": [{
            "name": "My Favorite Team",
            "tag": "MFT",
            "region": "americas",
            "tier": 1,
            "prestige": 70,
            "partial": False,
            "players": [
                {
                    "handle": handle,
                    "real_name": "",
                    "age": 21,
                    "country": "US",
                    "languages": [{"lang": "en", "level": 100}],
                    "role": role,
                    "playstyle": style,
                    "igl": igl,
                    "quality": 70,
                    "agents": agents,
                    "attr_overrides": {},
                    "potential": None,
                    "career_volatility": None,
                    "development_archetype": None,
                    "development_peak_age": None,
                    "development_peak_years": None,
                    "development_decline_age": None,
                    "development_realization": None,
                    "tags": tags,
                }
                for handle, role, style, igl, agents, tags in players
            ],
        }],
        "free_agents": [],
    }


def schema_bundle(gd: GameData | None = None) -> dict[str, Any]:
    gd = gd or load_all()
    return {
        "schema_version": SCHEMA_VERSION,
        "schema": RosterPackDocument.model_json_schema(),
        "catalog": {
            "regions": [str(x) for x in Region],
            "roles": [str(x) for x in Role],
            "playstyles": [str(x) for x in Playstyle],
            "agents": [
                {"id": a.id, "name": a.display_name, "role": str(a.role)}
                for a in sorted(gd.agents.values(), key=lambda x: x.id)
            ],
            "attributes": sorted(_ATTR_IDS),
        },
        "example": example_document(),
        "agent_instructions": (
            "Create one RosterPackDocument matching this JSON Schema. Keep ids "
            "and all text ASCII. Tier-1 teams need exactly five players and "
            "one IGL. Use only catalog agent ids. Save as YAML or JSON, run "
            "`python scripts/roster_pack_tool.py validate <file>`, then install "
            "it with `python scripts/roster_pack_tool.py install <file>`."
        ),
    }
