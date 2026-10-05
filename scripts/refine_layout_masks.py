"""Trace solid minimap volumes into revision-safe Studio drafts.

Dry run by default; --apply saves each coherent slice through Map MCP.
Never replaces an existing trace mask or publishes runtime artifacts.
"""
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
from esports_sim.schemas.studio import MapStudioDocumentV1, Prop

ROOT = Path(__file__).resolve().parents[1]


async def refine(apply: bool, maps: list[str]):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), ESPORTS_MAP_DATA_DIR=str(ROOT / "data"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "esports_sim.mcp.map_server"], env=env)
    report = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        await call(session, "get_map_schema", {})
        for name in maps:
            current = await call(session, "get_map", {"map_id": name + "-layout-v2"})
            doc = MapStudioDocumentV1.model_validate(current["document"])
            if any(p.id.startswith("trace_mask_") for p in doc.props):
                print(f"{doc.id}: existing trace masks retained", flush=True)
                continue
            before = map_reference.compare_reference(doc)
            proposals = map_reference.propose_wall_masks(doc)
            revised = doc.model_copy(update={"props": doc.props + [Prop(**p) for p in proposals]})
            _, _, errors = map_workbench.validate_document(revised)
            if errors:
                raise ValueError(errors)
            after = map_reference.compare_reference(revised)
            revision = current["revision_hash"]
            if apply:
                saved = await call(session, "apply_map_patch", {
                    "map_id": doc.id, "if_match_hash": revision, "props": proposals})
                revision = saved["revision_hash"]
                validation = await call(session, "validate_map", {"map_id": doc.id})
                if not validation["validation"]["valid"]:
                    raise ValueError(validation)
            report.append({"map_id": doc.id, "revision_hash": revision, "saved": apply,
                           "mask_count": len(proposals), "before": before, "after": after})
            print(f"{doc.id}: {len(proposals)} masks, floor overlap {before['iou']:.1%} -> {after['iou']:.1%}", flush=True)
    output = ROOT / "runs/layout-review" / ("floor-trace.json" if apply else "floor-trace-proposed.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    if report:
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--maps", nargs="+", default=["ascent", "bind", "haven", "lotus", "split"])
    args = parser.parse_args()
    asyncio.run(refine(args.apply, args.maps))
