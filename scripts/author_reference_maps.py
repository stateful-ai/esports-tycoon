"""Author image-informed Map Studio variants through the real stdio MCP.

The source minimaps are visual references only. This script encodes their
macro silhouettes as runtime-compatible rectangular rooms, then exercises the
same `esports-maps` tools an AI agent uses: discover, create/fork, batch patch,
validate, probe, and (optionally) publish.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class Room:
    id: str
    display_name: str
    bounds: tuple[float, float, float, float]
    site_id: str = "none"
    legacy_zone: str = "mid"


@dataclass(frozen=True)
class Edge:
    left: str
    right: str
    kind: str = "ramp"
    id: str | None = None
    noise_radius: float = 0.0
    start_closed_prob: float = 0.0


@dataclass(frozen=True)
class MapSpec:
    id: str
    display_name: str
    source_id: str | None
    sites: tuple[str, ...]
    rooms: tuple[Room, ...]
    edges: tuple[Edge, ...]
    props: tuple[dict[str, Any], ...]
    sightlines: tuple[tuple[str, str, str | None], ...]


def room(
    room_id: str,
    display_name: str,
    bounds: tuple[float, float, float, float],
    site_id: str = "none",
    legacy_zone: str = "mid",
) -> Room:
    return Room(room_id, display_name, bounds, site_id, legacy_zone)


def edge(
    left: str,
    right: str,
    *,
    kind: str = "ramp",
    edge_id: str | None = None,
    noise_radius: float = 0.0,
    start_closed_prob: float = 0.0,
) -> Edge:
    return Edge(left, right, kind, edge_id, noise_radius, start_closed_prob)


def prop(
    prop_id: str,
    surface_room: str,
    bounds: tuple[float, float, float, float],
    height: str,
) -> dict[str, Any]:
    x1, y1, x2, y2 = bounds
    return {
        "id": prop_id,
        "surface_id": f"surf_{surface_room}",
        "footprint": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "height": height,
        "collision": True,
        "destructible": False,
    }


def ascent_spec() -> MapSpec:
    rooms = (
        room("attacker_spawn", "Attacker Spawn", (44, 86, 56, 98), legacy_zone="attacker_spawn"),
        room("a_lobby", "A Lobby", (26, 78, 44, 92), "a", "attacker_side"),
        room("mid_bottom", "Mid Bottom", (44, 68, 56, 86), "mid", "mid"),
        room("b_lobby", "B Lobby", (56, 78, 74, 92), "b", "attacker_side"),
        room("a_main", "A Main", (16, 62, 32, 78), "a", "attacker_side"),
        room("catwalk", "Catwalk", (32, 62, 44, 78), "mid", "mid"),
        room("mid_courtyard", "Mid Courtyard", (44, 50, 58, 68), "mid", "mid"),
        room("b_main", "B Main", (68, 60, 84, 78), "b", "attacker_side"),
        room("a_site", "A Site", (12, 44, 30, 62), "a", "site"),
        room("a_garden", "A Garden", (30, 44, 44, 62), "a", "defender_side"),
        room("mid_market", "Market", (58, 44, 72, 60), "mid", "defender_side"),
        room("b_site", "B Site", (72, 42, 90, 60), "b", "site"),
        room("a_heaven", "A Heaven", (12, 30, 30, 44), "a", "defender_side"),
        room("a_rafters", "A Rafters", (30, 30, 40, 44), "a", "defender_side"),
        room("defender_link", "Defender Link", (40, 32, 72, 44), "none", "defender_side"),
        room("b_back", "B Back", (72, 28, 90, 42), "b", "defender_side"),
        room("defender_spawn", "Defender Spawn", (40, 18, 60, 32), legacy_zone="defender_spawn"),
    )
    edges = (
        edge("attacker_spawn", "a_lobby"), edge("attacker_spawn", "mid_bottom"),
        edge("attacker_spawn", "b_lobby"), edge("a_lobby", "a_main"),
        edge("a_lobby", "catwalk"), edge("a_main", "a_site"),
        edge("catwalk", "a_garden"), edge("catwalk", "mid_courtyard"),
        edge("catwalk", "mid_bottom"), edge("mid_bottom", "mid_courtyard"),
        edge("a_site", "a_garden"), edge("a_site", "a_heaven"),
        edge("a_heaven", "a_rafters"),
        edge("a_garden", "a_rafters", kind="door", edge_id="a_garden_door", start_closed_prob=0.7),
        edge("a_rafters", "defender_link"), edge("a_rafters", "defender_spawn"),
        edge("defender_spawn", "defender_link"), edge("defender_link", "mid_market"),
        edge("defender_link", "b_back"), edge("mid_courtyard", "mid_market"),
        edge("mid_market", "b_main"),
        edge("mid_market", "b_site", kind="door", edge_id="b_market_door", start_closed_prob=0.7),
        edge("b_lobby", "b_main"), edge("b_main", "b_site"), edge("b_site", "b_back"),
    )
    return MapSpec(
        "ascent_reference", "Ascent Reference", "ascent", ("a", "b"), rooms, edges,
        (
            prop("a_generator", "a_site", (17, 50, 21, 54), "full"),
            prop("mid_crate", "mid_courtyard", (49, 56, 53, 60), "half"),
            prop("b_boathouse", "b_site", (82, 48, 86, 52), "full"),
        ),
        (
            ("a_heaven", "a_main", "defense"), ("a_garden", "a_site", "defense"),
            ("mid_market", "mid_courtyard", "defense"), ("b_back", "b_main", "defense"),
        ),
    )


def bind_spec() -> MapSpec:
    rooms = (
        room("attacker_spawn", "Attacker Spawn", (42, 86, 58, 98), legacy_zone="attacker_spawn"),
        room("a_lobby", "A Lobby", (24, 72, 42, 92), "a", "attacker_side"),
        room("b_fountain", "B Fountain", (58, 72, 76, 92), "b", "attacker_side"),
        room("a_showers", "Showers", (10, 56, 28, 72), "a", "attacker_side"),
        room("a_short", "A Short", (28, 56, 42, 72), "a", "attacker_side"),
        room("b_window", "Hookah", (58, 56, 72, 72), "b", "attacker_side"),
        room("b_long", "B Long", (72, 56, 90, 72), "b", "attacker_side"),
        room("a_site", "A Site", (14, 38, 34, 56), "a", "site"),
        room("a_lamps", "Lamps", (34, 26, 42, 44), "a", "defender_side"),
        room("a_uhall", "U-Hall", (14, 26, 26, 38), "a", "defender_side"),
        room("b_site", "B Site", (66, 38, 86, 56), "b", "site"),
        room("b_elbow", "B Elbow", (58, 26, 72, 38), "b", "defender_side"),
        room("b_hall", "B Hall", (72, 26, 86, 38), "b", "defender_side"),
        room("defender_spawn", "Defender Spawn", (42, 16, 58, 28), legacy_zone="defender_spawn"),
    )
    edges = (
        edge("attacker_spawn", "a_lobby"), edge("attacker_spawn", "b_fountain"),
        edge("a_lobby", "a_showers"), edge("a_lobby", "a_short"),
        edge("a_showers", "a_site"), edge("a_short", "a_site"),
        edge("a_site", "a_uhall"), edge("a_site", "a_lamps"),
        edge("a_lamps", "defender_spawn"),
        edge("b_fountain", "b_window"), edge("b_fountain", "b_long"),
        edge("b_window", "b_site"), edge("b_long", "b_site"),
        edge("b_site", "b_elbow"), edge("b_site", "b_hall"),
        edge("b_elbow", "b_hall"), edge("b_elbow", "defender_spawn"),
        edge("a_short", "b_window", kind="teleporter", edge_id="tp_short_window", noise_radius=30),
        edge("b_long", "a_uhall", kind="teleporter", edge_id="tp_long_uhall", noise_radius=30),
    )
    return MapSpec(
        "bind_reference", "Bind Reference", "bind", ("a", "b"), rooms, edges,
        (
            prop("a_triple", "a_site", (20, 45, 24, 50), "half"),
            prop("a_lamps_box", "a_lamps", (36, 34, 39, 38), "full"),
            prop("b_tube", "b_site", (76, 45, 80, 50), "full"),
        ),
        (
            ("a_uhall", "a_showers", "defense"), ("a_lamps", "a_short", "defense"),
            ("b_hall", "b_window", "defense"), ("b_elbow", "b_long", "defense"),
        ),
    )


def haven_spec() -> MapSpec:
    rooms = (
        room("attacker_spawn", "Attacker Spawn", (42, 88, 58, 98), legacy_zone="attacker_spawn"),
        room("a_lobby", "A Lobby", (24, 78, 42, 92), "a", "attacker_side"),
        room("b_main", "B Main", (42, 70, 58, 88), "b", "attacker_side"),
        room("c_lobby", "C Lobby", (58, 78, 76, 92), "c", "attacker_side"),
        room("a_long", "A Long", (10, 62, 30, 78), "a", "attacker_side"),
        room("a_short", "A Short", (30, 62, 42, 78), "a", "attacker_side"),
        room("b_garage", "B Garage", (42, 56, 58, 70), "b", "attacker_side"),
        room("mid_window", "Mid Window", (58, 56, 66, 70), "mid", "mid"),
        room("mid_courtyard", "Mid Courtyard", (66, 62, 70, 78), "mid", "mid"),
        room("c_long", "C Long", (70, 62, 90, 78), "c", "attacker_side"),
        room("a_site", "A Site", (14, 44, 34, 62), "a", "site"),
        room("mid_doors", "Mid Doors", (34, 48, 42, 62), "mid", "mid"),
        room("b_site", "B Site", (42, 42, 58, 56), "b", "site"),
        room("c_site", "C Site", (66, 42, 86, 62), "c", "site"),
        room("c_cubby", "C Cubby", (86, 42, 94, 54), "c", "defender_side"),
        room("a_heaven", "A Heaven", (14, 32, 26, 44), "a", "defender_side"),
        room("a_link", "A Link", (26, 28, 34, 44), "a", "defender_side"),
        room("a_sewer", "A Sewer", (34, 32, 42, 48), "a", "defender_side"),
        room("b_back", "B Back", (42, 28, 58, 42), "b", "defender_side"),
        room("c_link", "C Link", (58, 34, 66, 50), "c", "defender_side"),
        room("c_back", "C Back", (58, 28, 74, 34), "c", "defender_side"),
        room("defender_spawn", "Defender Spawn", (32, 16, 66, 28), legacy_zone="defender_spawn"),
    )
    edges = (
        edge("attacker_spawn", "a_lobby"), edge("attacker_spawn", "b_main"),
        edge("attacker_spawn", "c_lobby"), edge("a_lobby", "a_long"),
        edge("a_lobby", "a_short"), edge("a_long", "a_site"),
        edge("a_short", "a_site"), edge("a_short", "mid_doors"),
        edge("a_site", "a_heaven"), edge("a_site", "a_link"),
        edge("a_site", "mid_doors"), edge("a_heaven", "a_link"),
        edge("a_link", "a_sewer"), edge("a_sewer", "mid_doors"),
        edge("a_link", "defender_spawn"), edge("b_main", "b_garage"),
        edge("b_garage", "b_site"), edge("b_garage", "mid_doors"),
        edge("b_garage", "mid_window"), edge("b_site", "b_back"),
        edge("b_back", "defender_spawn"), edge("b_back", "c_link"),
        edge("mid_window", "mid_courtyard"), edge("mid_courtyard", "c_long"),
        edge("mid_courtyard", "c_lobby"), edge("mid_courtyard", "c_site"),
        edge("c_lobby", "c_long"), edge("c_long", "c_site"),
        edge("c_site", "c_cubby"), edge("c_site", "c_link"),
        edge("c_link", "c_back"), edge("c_back", "defender_spawn"),
    )
    return MapSpec(
        "haven_reference", "Haven Reference", "haven", ("a", "b", "c"), rooms, edges,
        (
            prop("a_default", "a_site", (20, 51, 24, 55), "half"),
            prop("b_center_box", "b_site", (48, 47, 52, 51), "full"),
            prop("c_platform", "c_site", (75, 49, 80, 53), "half"),
        ),
        (
            ("a_heaven", "a_long", "defense"), ("a_sewer", "a_short", "defense"),
            ("b_back", "b_main", "defense"), ("c_link", "c_long", "defense"),
            ("mid_window", "mid_doors", None),
        ),
    )


def lotus_spec() -> MapSpec:
    rooms = (
        room("attacker_spawn", "Attacker Spawn", (42, 88, 58, 98), legacy_zone="attacker_spawn"),
        room("a_main", "A Main", (18, 74, 42, 90), "a", "attacker_side"),
        room("b_main", "B Main", (42, 70, 58, 88), "b", "attacker_side"),
        room("b_diamond", "B Diamond", (58, 74, 68, 88), "b", "attacker_side"),
        room("a_link", "A Link", (18, 60, 32, 74), "a", "attacker_side"),
        room("mid_tree", "Mid Tree", (32, 60, 38, 74), "mid", "mid"),
        room("b_site", "B Site", (38, 50, 58, 70), "b", "site"),
        room("alley", "Alley", (58, 60, 72, 74), "mid", "mid"),
        room("c_main", "C Main", (72, 68, 90, 84), "c", "attacker_side"),
        room("a_site", "A Site", (8, 42, 26, 60), "a", "site"),
        room("a_tree", "A Tree", (8, 30, 20, 42), "a", "defender_side"),
        room("a_dock", "A Dock", (26, 30, 38, 48), "a", "defender_side"),
        room("b_link", "B Link", (38, 30, 48, 50), "b", "defender_side"),
        room("b_tower", "B Tower", (48, 30, 60, 50), "b", "defender_side"),
        room("c_alley", "C Alley", (72, 50, 78, 68), "c", "attacker_side"),
        room("c_site", "C Site", (74, 34, 92, 50), "c", "site"),
        room("c_tunnel", "C Tunnel", (62, 28, 74, 42), "c", "defender_side"),
        room("c_dock", "C Dock", (74, 22, 88, 34), "c", "defender_side"),
        room("defender_spawn", "Defender Spawn", (34, 18, 62, 30), legacy_zone="defender_spawn"),
    )
    edges = (
        edge("attacker_spawn", "a_main"), edge("attacker_spawn", "b_main"),
        edge("a_main", "a_link"), edge("a_main", "mid_tree"),
        edge("a_link", "mid_tree"),
        edge("a_link", "a_site", kind="rotating_door", edge_id="lotus_door_a", noise_radius=26),
        edge("a_site", "a_tree"), edge("a_site", "a_dock"),
        edge("a_dock", "b_link"), edge("a_dock", "defender_spawn"),
        edge("mid_tree", "b_site"), edge("b_main", "b_site"),
        edge("b_main", "b_diamond"), edge("b_main", "alley"),
        edge("b_diamond", "alley"), edge("b_site", "b_link"),
        edge("b_site", "b_tower"), edge("b_site", "alley"),
        edge("b_link", "b_tower"), edge("b_link", "defender_spawn"),
        edge("b_tower", "defender_spawn"), edge("alley", "c_main"),
        edge("alley", "c_alley"), edge("c_main", "c_alley"),
        edge("c_alley", "c_site", kind="rotating_door", edge_id="lotus_door_c", noise_radius=26),
        edge("c_site", "c_tunnel"), edge("c_site", "c_dock"),
        edge("c_tunnel", "c_dock"), edge("c_tunnel", "defender_spawn"),
    )
    return MapSpec(
        "lotus_reference", "Lotus Reference", "lotus", ("a", "b", "c"), rooms, edges,
        (
            prop("a_rubble", "a_site", (13, 49, 17, 53), "half"),
            prop("b_pillar", "b_site", (47, 57, 51, 62), "full"),
            prop("c_mound", "c_site", (82, 39, 86, 43), "half"),
        ),
        (
            ("a_tree", "a_main", "defense"), ("b_tower", "b_main", "defense"),
            ("c_tunnel", "c_alley", "defense"), ("mid_tree", "alley", None),
        ),
    )


def breeze_spec() -> MapSpec:
    rooms = (
        room("attacker_spawn", "Attacker Spawn", (42, 88, 58, 98), legacy_zone="attacker_spawn"),
        room("a_lobby", "A Lobby", (20, 78, 42, 92), "a", "attacker_side"),
        room("mid_bottom", "Mid Bottom", (42, 68, 58, 88), "mid", "mid"),
        room("b_lobby", "B Lobby", (58, 78, 80, 92), "b", "attacker_side"),
        room("a_cave", "A Cave", (8, 62, 24, 78), "a", "attacker_side"),
        room("a_hall", "A Hall", (24, 62, 34, 78), "a", "attacker_side"),
        room("mid_pillar", "Mid Pillar", (34, 54, 50, 68), "mid", "mid"),
        room("b_mid", "B Mid", (50, 54, 66, 68), "mid", "mid"),
        room("b_main", "B Main", (66, 62, 82, 78), "b", "attacker_side"),
        room("a_site", "A Site", (10, 42, 34, 62), "a", "site"),
        room("a_bridge", "A Bridge", (34, 42, 44, 54), "a", "defender_side"),
        room("b_tunnel", "B Tunnel", (58, 36, 70, 54), "b", "defender_side"),
        room("b_site", "B Site", (70, 42, 92, 62), "b", "site"),
        room("a_back", "A Back", (18, 28, 34, 42), "a", "defender_side"),
        room("defender_link", "Defender Link", (34, 24, 76, 36), "none", "defender_side"),
        room("b_back", "B Back", (76, 28, 92, 42), "b", "defender_side"),
        room("defender_spawn", "Defender Spawn", (42, 12, 58, 24), legacy_zone="defender_spawn"),
    )
    edges = (
        edge("attacker_spawn", "a_lobby"), edge("attacker_spawn", "mid_bottom"),
        edge("attacker_spawn", "b_lobby"), edge("a_lobby", "a_cave"),
        edge("a_lobby", "a_hall"), edge("a_lobby", "mid_bottom"),
        edge("a_cave", "a_hall"), edge("a_cave", "a_site"),
        edge("a_hall", "a_site"), edge("a_hall", "mid_pillar"),
        edge("a_site", "a_bridge"), edge("a_site", "a_back"),
        edge("a_bridge", "mid_pillar"), edge("a_back", "defender_link"),
        edge("mid_bottom", "mid_pillar"), edge("mid_bottom", "b_mid"),
        edge("mid_pillar", "b_mid"), edge("b_mid", "b_main"),
        edge("b_mid", "b_tunnel"), edge("b_lobby", "mid_bottom"),
        edge("b_lobby", "b_main"), edge("b_main", "b_site"),
        edge("b_tunnel", "b_site"), edge("b_tunnel", "defender_link"),
        edge("b_site", "b_back"), edge("b_back", "defender_link"),
        edge("defender_link", "defender_spawn"),
    )
    return MapSpec(
        "breeze_reference", "Breeze Reference", None, ("a", "b"), rooms, edges,
        (
            prop("a_pyramid_one", "a_site", (16, 48, 20, 55), "full"),
            prop("a_pyramid_two", "a_site", (25, 49, 29, 56), "full"),
            prop("mid_pillar_cover", "mid_pillar", (40, 59, 44, 63), "full"),
            prop("b_wall", "b_site", (82, 48, 87, 52), "full"),
        ),
        (
            ("a_back", "a_cave", "defense"), ("a_bridge", "a_hall", "defense"),
            ("defender_link", "mid_bottom", "defense"), ("b_back", "b_main", "defense"),
        ),
    )


SPECS = {
    spec.id: spec
    for spec in (ascent_spec(), bind_spec(), haven_spec(), lotus_spec(), breeze_spec())
}


def polygon(bounds: tuple[float, float, float, float]) -> list[list[float]]:
    x1, y1, x2, y2 = bounds
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def center(bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bounds
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def portal_points(left: Room, right: Room) -> tuple[list[Any], list[Any], str]:
    ax1, ay1, ax2, ay2 = left.bounds
    bx1, by1, bx2, by2 = right.bounds
    inset = 0.75
    if abs(ax2 - bx1) < 1e-6 and max(ay1, by1) < min(ay2, by2):
        y = (max(ay1, by1) + min(ay2, by2)) / 2
        return [ax2 - inset, y, f"surf_{left.id}"], [bx1 + inset, y, f"surf_{right.id}"], "corridor"
    if abs(bx2 - ax1) < 1e-6 and max(ay1, by1) < min(ay2, by2):
        y = (max(ay1, by1) + min(ay2, by2)) / 2
        return [ax1 + inset, y, f"surf_{left.id}"], [bx2 - inset, y, f"surf_{right.id}"], "corridor"
    if abs(ay2 - by1) < 1e-6 and max(ax1, bx1) < min(ax2, bx2):
        x = (max(ax1, bx1) + min(ax2, bx2)) / 2
        return [x, ay2 - inset, f"surf_{left.id}"], [x, by1 + inset, f"surf_{right.id}"], "corridor"
    if abs(by2 - ay1) < 1e-6 and max(ax1, bx1) < min(ax2, bx2):
        x = (max(ax1, bx1) + min(ax2, bx2)) / 2
        return [x, ay1 + inset, f"surf_{left.id}"], [x, by2 - inset, f"surf_{right.id}"], "corridor"
    raise ValueError(f"non-teleporter rooms do not share an edge: {left.id} <-> {right.id}")


def build_patch(spec: MapSpec) -> dict[str, Any]:
    by_id = {item.id: item for item in spec.rooms}
    surfaces = []
    zones = []
    for item in spec.rooms:
        surfaces.append({
            "id": f"surf_{item.id}",
            "polygon": polygon(item.bounds),
            "elevation": 0.0,
        })
        if item.legacy_zone in {"attacker_spawn", "defender_spawn"}:
            kind = "spawn"
        elif item.legacy_zone == "site":
            kind = "site"
        else:
            kind = "callout"
        zones.append({
            "id": item.id,
            "display_name": item.display_name,
            "kind": kind,
            "polygon": polygon(item.bounds),
            "surface_ids": [f"surf_{item.id}"],
            "label_position": list(center(item.bounds)),
            "site_id": item.site_id,
            "legacy_zone": item.legacy_zone,
        })
        if kind == "site":
            x1, y1, x2, y2 = item.bounds
            dx = (x2 - x1) * 0.25
            dy = (y2 - y1) * 0.25
            zones.append({
                "id": f"{item.site_id}_plant",
                "display_name": f"{item.site_id.upper()} Plant",
                "kind": "plant",
                "polygon": polygon((x1 + dx, y1 + dy, x2 - dx, y2 - dy)),
                "surface_ids": [f"surf_{item.id}"],
                "label_position": list(center(item.bounds)),
                "site_id": item.site_id,
                "legacy_zone": None,
            })

    links = []
    for item in spec.edges:
        left = by_id[item.left]
        right = by_id[item.right]
        if item.kind == "teleporter":
            lx, ly = center(left.bounds)
            rx, ry = center(right.bounds)
            from_pos = [lx, ly, f"surf_{left.id}"]
            to_pos = [rx, ry, f"surf_{right.id}"]
            path_mode = "portal"
        else:
            from_pos, to_pos, path_mode = portal_points(left, right)
        links.append({
            "id": item.id or f"link_{item.left}_{item.right}",
            "kind": item.kind,
            "from_pos": from_pos,
            "to_pos": to_pos,
            "via": [],
            "path_mode": path_mode,
            "include_endpoints_in_path": path_mode == "corridor",
            "noise_radius": item.noise_radius,
            "start_closed_prob": item.start_closed_prob,
        })

    return {
        "metadata": {
            "display_name": spec.display_name,
            "sites": list(spec.sites),
            "attacker_spawn": "attacker_spawn",
            "defender_spawn": "defender_spawn",
        },
        "walkable_surfaces": surfaces,
        "semantic_zones": zones,
        "props": list(spec.props),
        "walls": [],
        "traversal_links": links,
        "sightlines": [
            {
                "from_callout": from_callout,
                "to_callout": to_callout,
                "advantaged_side": advantaged_side,
            }
            for from_callout, to_callout, advantaged_side in spec.sightlines
        ],
        "adjacency_overrides": {},
        "prop_support_exemptions": [],
    }


def removals(document: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    collections = (
        ("surface", "walkable_surfaces"),
        ("zone", "semantic_zones"),
        ("prop", "props"),
        ("link", "traversal_links"),
    )
    for element_type, key in collections:
        rows.extend(
            {"element_type": element_type, "element_id": item["id"]}
            for item in document.get(key, [])
        )
    rows.extend(
        {"element_type": "wall", "element_id": item.get("id") or f"wall_{index}"}
        for index, item in enumerate(document.get("walls", []))
    )
    return rows


def payload(result: Any) -> dict[str, Any]:
    if result.isError:
        message = result.content[0].text if result.content else "unknown MCP error"
        raise RuntimeError(message)
    return json.loads(result.content[0].text)


async def call(session: ClientSession, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return payload(await session.call_tool(name, arguments=arguments or {}))


async def author(selected: list[str], publish: bool) -> list[dict[str, Any]]:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "esports_sim.mcp.map_server"],
        env=env,
    )
    report = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            schema = await call(session, "get_map_schema")
            if schema["document_schema"]["properties"]["schema_version"]["const"] != 1:
                raise RuntimeError("reference author requires MapStudioDocumentV1")
            library = await call(session, "list_maps")
            existing = {item["id"] for item in library["maps"]}

            for map_id in selected:
                spec = SPECS[map_id]
                if map_id in existing:
                    opened = await call(session, "get_map", {"map_id": map_id})
                elif spec.source_id is not None:
                    opened = await call(session, "fork_map", {
                        "source_map_id": spec.source_id,
                        "new_map_id": map_id,
                        "display_name": spec.display_name,
                    })
                else:
                    opened = await call(session, "create_map", {
                        "map_id": map_id,
                        "display_name": spec.display_name,
                        "template": "empty",
                    })

                patch = build_patch(spec)
                patched = await call(session, "apply_map_patch", {
                    "map_id": map_id,
                    "if_match_hash": opened["revision_hash"],
                    "removals": removals(opened["document"]),
                    **patch,
                })
                validated = await call(session, "validate_map", {"map_id": map_id})
                if not validated["validation"]["valid"]:
                    messages = [item["message"] for item in validated["validation"]["errors"]]
                    raise RuntimeError(f"{map_id} failed validation: {messages}")

                probe_rows = []
                probe_ids = ["attacker_spawn", *[f"{site}_site" for site in spec.sites], "defender_spawn"]
                by_id = {item.id: item for item in spec.rooms}
                for probe_id in probe_ids:
                    point = center(by_id[probe_id].bounds)
                    probed = await call(session, "probe_map_geometry", {
                        "map_id": map_id,
                        "from_pos": list(point),
                        "player_radius": 1.0,
                    })
                    probe_rows.append({
                        "requested": probe_id,
                        "resolved_zone": probed["probe"]["zone_id"],
                        "clearance": probed["probe"]["clearance"],
                        "reachable": len(probed["probe"]["reachable_zones"]),
                    })

                published = None
                if publish:
                    published = await call(session, "publish_map", {
                        "map_id": map_id,
                        "if_match_hash": patched["revision_hash"],
                    })
                report.append({
                    "map_id": map_id,
                    "revision_hash": patched["revision_hash"],
                    "rooms": len(spec.rooms),
                    "links": len(spec.edges),
                    "props": len(spec.props),
                    "probes": probe_rows,
                    "published": published,
                    "ui_path": patched["ui_path"],
                })
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maps",
        nargs="*",
        choices=sorted(SPECS),
        default=sorted(SPECS),
        help="Variant ids to author (defaults to all five).",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Compile validated variants into runtime YAML and guide PNG files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(asyncio.run(author(args.maps, args.publish)), indent=2))


if __name__ == "__main__":
    main()
