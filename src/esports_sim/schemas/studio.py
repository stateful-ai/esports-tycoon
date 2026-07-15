"""Map Studio document schema.
Defines continuous authoring geometry for Map Studio drafts.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class WalkableSurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    polygon: list[tuple[float, float]]
    elevation: float = 0.0


class SemanticZone(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal["callout", "site", "spawn", "plant"]
    polygon: list[tuple[float, float]]
    surface_ids: list[str] = Field(default_factory=list)
    label_position: tuple[float, float]
    site_id: str = "none"  # "a" | "b" | "c" | "mid" | "none"


class Prop(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    surface_id: str
    footprint: list[tuple[float, float]]
    height: Literal["half", "full"] = "half"
    collision: bool = True
    destructible: bool = False


class TraversalLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal["rope", "door", "teleporter", "drop", "ramp"]
    from_pos: tuple[float, float, str]  # (x, y, surface_id)
    to_pos: tuple[float, float, str]    # (x, y, surface_id)
    via: list[tuple[float, float]] = Field(default_factory=list)
    noise_radius: float = 25.0
    start_closed_prob: float = 0.7  # only breakable_door


class LegacyCompilationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    adjacency_overrides: dict[str, list[str]] = Field(default_factory=dict)
    sightline_overrides: list[dict] = Field(default_factory=list)


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
    walls: list[dict[str, Any]] = Field(default_factory=list)
    props: list[Prop] = Field(default_factory=list)
    semantic_zones: list[SemanticZone] = Field(default_factory=list)
    traversal_links: list[TraversalLink] = Field(default_factory=list)
    legacy: LegacyCompilationConfig = Field(default_factory=LegacyCompilationConfig)
    editor_state: EditorState = Field(default_factory=EditorState)
