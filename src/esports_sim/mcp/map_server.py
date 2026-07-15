"""Official-SDK MCP server for revision-safe Map Studio co-authoring."""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from esports_sim.registry import map_mcp_ops as ops
from esports_sim.schemas.map import SightLine
from esports_sim.schemas.studio import (
    Prop,
    SemanticZone,
    TraversalLink,
    WalkableSurface,
    Wall,
)

mcp = FastMCP(
    "ESports Map Studio",
    instructions=(
        "Build and co-edit maps in the same Studio source used by the visual UI. "
        "Read the schema, create or open a map, retain revision_hash, and pass it "
        "as if_match_hash on every mutation. On a stale revision, get_map and "
        "reconcile instead of blind-retrying. Validate frequently. Publish only "
        "when the user explicitly asks to replace runtime map artifacts."
    ),
    json_response=True,
)


@mcp.resource("map://schema")
def map_schema() -> str:
    """Authoritative Map Studio schemas and compile/collaboration rules."""
    return json.dumps(ops.get_map_schema(), indent=2)


@mcp.resource("map://library")
def map_library() -> str:
    """Maps currently available to Map Studio."""
    return json.dumps(ops.list_maps(), indent=2)


@mcp.resource("map://document/{map_id}")
def map_document(map_id: str) -> str:
    """Complete shared Studio source and current revision for one map."""
    return json.dumps(ops.get_map(map_id), indent=2)


@mcp.tool()
def get_map_schema() -> dict[str, Any]:
    """Get Studio element schemas, compile limits, and the co-edit protocol."""
    return ops.get_map_schema()


@mcp.tool()
def list_maps() -> dict[str, Any]:
    """List shared Studio drafts and legacy maps that can be opened for editing."""
    return ops.list_maps()


@mcp.tool()
def create_map(
    map_id: str,
    display_name: str,
    template: Literal["empty", "two-site"] = "empty",
) -> dict[str, Any]:
    """Create a shared Studio map; two-site is a valid connected starter."""
    return ops.create_map(map_id, display_name, template)


@mcp.tool()
def open_map_for_editing(map_id: str) -> dict[str, Any]:
    """Open a map and materialize legacy-only data into the shared Studio source."""
    return ops.open_map_for_editing(map_id)


@mcp.tool()
def get_map(map_id: str) -> dict[str, Any]:
    """Get the complete current Studio document, validation, and revision hash."""
    return ops.get_map(map_id)


@mcp.tool()
def validate_map(map_id: str) -> dict[str, Any]:
    """Run continuous geometry, strict compile, and runtime floor audits."""
    return ops.validate_map(map_id)


@mcp.tool()
def update_map_metadata(
    map_id: str,
    changes: dict[str, Any],
    if_match_hash: str,
) -> dict[str, Any]:
    """Patch display name, site ids, or spawn-zone ids at an exact revision."""
    return ops.update_map_metadata(map_id, changes, if_match_hash)


@mcp.tool()
def upsert_walkable_surface(
    map_id: str,
    surface: WalkableSurface,
    if_match_hash: str,
) -> dict[str, Any]:
    """Add or replace one stable-id walkable floor surface."""
    return ops.upsert_walkable_surface(map_id, surface, if_match_hash)


@mcp.tool()
def upsert_semantic_zone(
    map_id: str,
    zone: SemanticZone,
    if_match_hash: str,
) -> dict[str, Any]:
    """Add or replace one callout, site, spawn, or plant semantic zone."""
    return ops.upsert_semantic_zone(map_id, zone, if_match_hash)


@mcp.tool()
def upsert_prop(
    map_id: str,
    prop: Prop,
    if_match_hash: str,
) -> dict[str, Any]:
    """Add or replace one stable-id half/full-height cover prop."""
    return ops.upsert_prop(map_id, prop, if_match_hash)


@mcp.tool()
def upsert_wall(
    map_id: str,
    wall: Wall,
    if_match_hash: str,
) -> dict[str, Any]:
    """Add or replace one stable-id wall; wall.id is required."""
    return ops.upsert_wall(map_id, wall, if_match_hash)


@mcp.tool()
def upsert_traversal_link(
    map_id: str,
    link: TraversalLink,
    if_match_hash: str,
) -> dict[str, Any]:
    """Add or replace a corridor, door, rope, teleporter, drop, or ramp link."""
    return ops.upsert_traversal_link(map_id, link, if_match_hash)


@mcp.tool()
def remove_map_element(
    map_id: str,
    element_type: Literal["surface", "zone", "prop", "wall", "link"],
    element_id: str,
    if_match_hash: str,
) -> dict[str, Any]:
    """Remove one element by stable id; dependent references are not cascaded."""
    return ops.remove_map_element(map_id, element_type, element_id, if_match_hash)


@mcp.tool()
def set_sightlines(
    map_id: str,
    sightlines: list[SightLine],
    if_match_hash: str,
) -> dict[str, Any]:
    """Replace authored runtime sightline hints at an exact revision."""
    return ops.set_sightlines(map_id, sightlines, if_match_hash)


@mcp.tool()
def probe_map_geometry(
    map_id: str,
    from_pos: tuple[float, float],
    to_pos: tuple[float, float] | None = None,
    player_radius: float = 1.0,
) -> dict[str, Any]:
    """Probe floor, zone, clearance, collision, LOS, and reachable zones."""
    return ops.probe_map_geometry(map_id, from_pos, to_pos, player_radius)


@mcp.tool()
def publish_map(map_id: str, if_match_hash: str) -> dict[str, Any]:
    """Explicitly compile and publish the exact validated Studio revision."""
    return ops.publish_map(map_id, if_match_hash)


def main() -> None:
    """Run the Map Studio MCP over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
