"""Build reviewable real-layout variants through the revision-safe Map MCP.

Usage: python scripts/build_layout_drafts.py <folder-of-minimap-pngs>
Sources are the owner's July 2026 screenshots, not an asserted current patch.
Existing variants are never overwritten; continue them in Map Studio.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ROTATIONS = {"ascent": "ccw", "bind": "flipv", "haven": "ccw", "lotus": "180", "split": "ccw"}

# Plant silhouettes read from the canonical reference grid (map units).
# Room corrections retain the existing topology and lane doglegs.
PLANTS = {
    "ascent": {"a": [(4.25, 65.25), (18.75, 65.25), (18.75, 74.25), (4.25, 74.25)],
               "b": [(73.0, 67.0), (85.5, 67.0), (85.5, 80.25), (73.0, 80.25)]},
    "bind": {"a": [(14.25, 67.25), (22.5, 67.25), (22.5, 74.0), (14.25, 74.0)],
             "b": [(57.25, 60.75), (66.75, 60.75), (66.75, 70.25), (57.25, 70.25)]},
    "haven": {"a": [(5.0, 58.25), (16.5, 58.25), (16.5, 68.0), (5.0, 68.0)],
              "b": [(42.0, 56.5), (52.5, 56.5), (52.5, 66.25), (42.0, 66.25)],
              "c": [(75.25, 59.0), (90.5, 59.0), (90.5, 69.75), (75.25, 69.75)]},
    "lotus": {"a": [(4.0, 58.25), (8.0, 58.25), (8.0, 61.5), (14.0, 61.5), (14.0, 70.5), (4.0, 70.5)],
              "b": [(44.25, 50.0), (57.75, 50.0), (57.75, 57.75), (44.25, 57.75)],
              "c": [(85.5, 45.0), (96.5, 45.0), (96.5, 55.0), (85.5, 55.0)]},
    "split": {"a": [(3.5, 52.0), (6.5, 55.0), (14.5, 55.0), (14.5, 70.5), (3.5, 70.5)],
              "b": [(75.0, 58.25), (88.5, 58.25), (88.5, 66.0), (75.0, 66.0)]},
}
ROOM_BOUNDS = {
    "ascent": {"a_site": (4.0, 55.0, 21.0, 79.5), "b_site": (62.5, 53.0, 86.0, 80.5)},
    "bind": {"a_site": (10.0, 60.0, 30.0, 74.5)},
    "haven": {"c_site": (70.0, 50.0, 90.75, 70.0)},
    "lotus": {"c_site": (75.0, 40.0, 97.0, 58.0)},
    "split": {"b_site": (52.0, 50.0, 89.0, 70.0)},
}


async def call(session: ClientSession, name: str, args: dict) -> dict:
    result = await session.call_tool(name, args)
    if result.isError:
        raise RuntimeError(f"{name}: {result.content}")
    if result.structuredContent:
        return result.structuredContent
    return json.loads(next(c.text for c in result.content if c.type == "text"))


async def build(sources: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), ESPORTS_MAP_DATA_DIR=str(ROOT / "data"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "esports_sim.mcp.map_server"], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        await call(session, "get_map_schema", {})
        library = await call(session, "list_maps", {})
        existing = {row["id"] for row in library["maps"]}
        for map_id, rotation in ROTATIONS.items():
            draft_id = f"{map_id}-layout-v2"
            if draft_id in existing:
                print(f"{draft_id}: already exists; preserving all edits")
                continue
            source = sources / f"{map_id}.png"
            ref_dir = ROOT / "assets" / "maps" / "references"
            scratch = ROOT / "runs" / "layout-trace"
            scratch.mkdir(parents=True, exist_ok=True)
            ref_dir.mkdir(parents=True, exist_ok=True)
            grid = scratch / f"{map_id}-grid.png"
            subprocess.run([sys.executable, str(ROOT / "scripts" / "wiki_map_trace.py"), "grid",
                            str(source), str(grid), "--rotate", rotation], check=True, capture_output=True)
            clean = grid.with_name(grid.stem + "_clean.png")
            target = ref_dir / f"{map_id}.png"
            if target.exists() and target.read_bytes() != clean.read_bytes():
                raise RuntimeError(f"Reference changed: {target}; calibrate a new reference rather than overwrite")
            target.write_bytes(clean.read_bytes())
            meta = json.loads(grid.with_suffix(".json").read_text())
            with Image.open(clean) as image:
                width, height = image.size
            reference = {
                "image_path": f"/assets/maps/references/{map_id}.png",
                "description": f"{map_id.title()} minimap - owner's July 2026 snapshot; {rotation} orientation",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "rotation": rotation, "x": 0, "y": 0,
                "width": width * meta["units_per_pixel"], "height": height * meta["units_per_pixel"],
            }
            current = await call(session, "fork_map", {"source_map_id": map_id, "new_map_id": draft_id,
                                                      "display_name": f"{map_id.title()} - Layout v2"})
            doc = current["document"]
            surfaces = {s["id"]: s for s in doc["walkable_surfaces"]}
            zones = {z["id"]: z for z in doc["semantic_zones"]}
            changed_surfaces, changed_zones = [], []
            for zone_id, (x0, y0, x1, y1) in ROOM_BOUNDS[map_id].items():
                zone = zones[zone_id]
                polygon = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
                surf = surfaces[zone["surface_ids"][0]]
                surf["polygon"] = polygon
                zone["polygon"] = polygon
                changed_surfaces.append(surf)
                changed_zones.append(zone)
            for site_id, polygon in PLANTS[map_id].items():
                zone = zones[f"{site_id}_site"]
                # Semantic label anchor; clearance is recorded by the probes.
                center = [sum(p[0] for p in polygon) / len(polygon), sum(p[1] for p in polygon) / len(polygon)]
                changed_zones.append({"id": f"{site_id}_plant", "display_name": f"{site_id.upper()} Plant",
                                      "kind": "plant", "polygon": polygon, "surface_ids": zone["surface_ids"],
                                      "label_position": center, "site_id": site_id})
            if map_id == "haven":
                # The old spawn callout covered the CT route and part of B's
                # plant area. Keep its navigational plate, bound the semantic
                # spawn to the actual southern CT area.
                spawn = zones[doc["defender_spawn"]]
                spawn["polygon"] = [[33.5, 70], [44.5, 70], [44.5, 89], [33.5, 89]]
                changed_zones.append(spawn)
            links = doc["traversal_links"]
            pairs = {frozenset((l["from_pos"][2], l["to_pos"][2])) for l in links}
            # Make every route visible/editable instead of leaving portal edges hidden in legacy overrides.
            for a, neighbors in doc["legacy"]["adjacency_overrides"].items():
                for b in neighbors:
                    pair = frozenset((f"surf_{a}", f"surf_{b}"))
                    if pair in pairs:
                        continue
                    pairs.add(pair)
                    links.append({"id": f"route_{a}_{b}", "kind": "ramp",
                                  "from_pos": [*zones[a]["label_position"], f"surf_{a}"],
                                  "to_pos": [*zones[b]["label_position"], f"surf_{b}"],
                                  "via": [], "path_mode": "portal", "include_endpoints_in_path": False,
                                  "noise_radius": 0, "start_closed_prob": 0})
            for link in links:
                pair = {link["from_pos"][2].removeprefix("surf_"), link["to_pos"][2].removeprefix("surf_")}
                opening = next((o for o in doc["legacy"]["opening_overrides"] if set(o["between"]) == pair), None)
                if opening:
                    link["opening_span"] = opening["span"]
            result = await call(session, "apply_map_patch", {
                "map_id": draft_id, "if_match_hash": current["revision_hash"],
                "metadata": {"reference": reference, "links_define_adjacency": True}, "walkable_surfaces": changed_surfaces,
                "semantic_zones": changed_zones, "traversal_links": links,
            })
            if not result["validation"]["valid"]:
                raise RuntimeError(f"{draft_id}: {result['validation']['errors']}")
            checks = []
            for zid in [doc["attacker_spawn"], doc["defender_spawn"], *[f"{s}_site" for s in PLANTS[map_id]]]:
                point = zones[zid]["label_position"]
                probe = await call(session, "probe_map_geometry", {"map_id": draft_id, "from_pos": point})
                checks.append({"zone": zid, "point": point, **probe["probe"]})
            final = await call(session, "get_map", {"map_id": draft_id})
            report = {"map_id": draft_id, "revision_hash": final["revision_hash"],
                      "validation": final["validation"], "probes": checks, "published": False}
            (scratch / f"{draft_id}-review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"{draft_id}: valid, {len(surfaces)} rooms, {len(links)} routes, {len(PLANTS[map_id])} plants; "
                  f"revision {final['revision_hash'][:12]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path)
    asyncio.run(build(parser.parse_args().sources))
