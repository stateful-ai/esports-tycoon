"""Map Studio document schema.
Defines continuous authoring geometry for Map Studio drafts.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class WalkableSurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    polygon: list[tuple[float, float]] = Field(min_length=3)
    elevation: float = 0.0


class SemanticZone(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    display_name: str | None = None
    kind: Literal["callout", "site", "spawn", "plant"]
    polygon: list[tuple[float, float]] = Field(min_length=3)
    surface_ids: list[str] = Field(default_factory=list)
    label_position: tuple[float, float]
    site_id: str = "none"  # "a" | "b" | "c" | "mid" | "none"
    # Runtime tactical classification consumed by team/player policies.
    # Plant zones are semantic overlays and may leave this unset.
    legacy_zone: Literal[
        "attacker_spawn",
        "defender_spawn",
        "attacker_side",
        "defender_side",
        "mid",
        "site",
    ] | None = None


class Wall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Optional for backward compatibility with drafts created before walls
    # became independently addressable by Studio/MCP co-editors.
    id: str | None = None
    polyline: list[tuple[float, float]] = Field(min_length=2)
    thickness: float = Field(default=1.0, gt=0.0)
    height: float = Field(default=3.2, gt=0.0)
    penetrability: float = Field(default=1.0, ge=0.0)


class Prop(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    surface_id: str
    footprint: list[tuple[float, float]] = Field(min_length=3)
    height: Literal["half", "full"] = "half"
    collision: bool = True
    destructible: bool = False


class TraversalLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal["rope", "door", "rotating_door", "teleporter", "drop", "ramp"]
    from_pos: tuple[float, float, str]  # (x, y, surface_id)
    to_pos: tuple[float, float, str]    # (x, y, surface_id)
    via: list[tuple[float, float]] = Field(default_factory=list)
    # Studio-authored links use their endpoint positions as the first and last
    # corridor points. Synthesized legacy corridors leave them out so an
    # open-edit-publish round trip remains byte-for-byte route-equivalent.
    path_mode: Literal["corridor", "portal"] = "corridor"
    include_endpoints_in_path: bool = True
    noise_radius: float = Field(default=25.0, ge=0.0)
    start_closed_prob: float = Field(default=0.7, ge=0.0, le=1.0)  # breakable door only


class LegacyCompilationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    adjacency_overrides: dict[str, list[str]] = Field(default_factory=dict)
    sightline_overrides: list[dict] = Field(default_factory=list)
    # Synthesized legacy maps may contain deliberately overhanging blockers.
    # New Studio props remain subject to strict surface containment.
    prop_support_exemptions: list[str] = Field(default_factory=list)


class EditorState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    test_players: list[dict[str, Any]] = Field(default_factory=list)
    viewport: dict[str, Any] = Field(default_factory=dict)
    selected_tool: str = ""


class MapStudioDocumentV1(BaseModel):
    """Source authoring document format for Map Studio."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    id: str
    display_name: str
    sites: list[str] = Field(default_factory=list)
    attacker_spawn: str = "attacker_spawn"
    defender_spawn: str = "defender_spawn"
    walkable_surfaces: list[WalkableSurface] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    props: list[Prop] = Field(default_factory=list)
    semantic_zones: list[SemanticZone] = Field(default_factory=list)
    traversal_links: list[TraversalLink] = Field(default_factory=list)
    legacy: LegacyCompilationConfig = Field(default_factory=LegacyCompilationConfig)
    editor_state: EditorState = Field(default_factory=EditorState)
