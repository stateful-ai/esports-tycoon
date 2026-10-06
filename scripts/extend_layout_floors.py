"""Restore missing reference floor as shared room extensions through Map MCP."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from build_layout_drafts import call
from esports_sim.registry import map_reference, map_workbench
from esports_sim.schemas.studio import MapStudioDocumentV1, WalkableSurface

ROOT = Path(__file__).resolve().parents[1]


async def extend(apply):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), ESPORTS_MAP_DATA_DIR=str(ROOT / "data"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "esports_sim.mcp.map_server"], env=env)
    reports = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        await call(session, "get_map_schema", {})
        for name in ["ascent","bind","haven","lotus","split"]:
            current = await call(session, "get_map", {"map_id":name+"-layout-v2"})
            doc = MapStudioDocumentV1.model_validate(current["document"])
            if any(s.floor_extensions for s in doc.walkable_surfaces):
                print(f"{doc.id}: preserving existing extensions", flush=True)
                continue
            before = map_reference.compare_reference(doc)
            proposals = map_reference.propose_floor_extensions(doc)
            updated = {p["id"]: WalkableSurface(**p) for p in proposals}
            revised = doc.model_copy(update={"walkable_surfaces":[updated.get(s.id,s) for s in doc.walkable_surfaces]})
            _, _, errors = map_workbench.validate_document(revised)
            if errors: raise ValueError(errors)
            after = map_reference.compare_reference(revised)
            revision = current["revision_hash"]
            if apply:
                saved = await call(session, "apply_map_patch", {"map_id":doc.id,
                    "if_match_hash":revision,"walkable_surfaces":proposals})
                revision = saved["revision_hash"]
                if not saved["validation"]["valid"]: raise ValueError(saved)
            reports.append({"map_id":doc.id,"revision_hash":revision,"saved":apply,
                "extension_count":sum(len(p['floor_extensions']) for p in proposals),"before":before,"after":after})
            print(f"{doc.id}: floor overlap {before['iou']:.1%} -> {after['iou']:.1%}",flush=True)
    if reports:
        folder = ROOT / "runs/layout-review"
        folder.mkdir(parents=True,exist_ok=True)
        (folder / ("floor-extensions.json" if apply else "floor-extensions-proposed.json")).write_text(json.dumps(reports,indent=2),encoding="utf-8")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    asyncio.run(extend(parser.parse_args().apply))
