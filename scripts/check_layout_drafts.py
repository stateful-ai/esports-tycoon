"""Compile Studio variants to disposable data and run the real map gates.

No runtime publishing or golden re-blessing. Review JSON retains source hashes.
Usage: python scripts/check_layout_drafts.py [--matches 300]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from esports_sim.registry import map_workbench
from esports_sim.registry.map_probe import probe_map
from esports_sim.registry.map_reference import compare_reference
from esports_sim.schemas.geometry import _segment_hits_rect
from esports_sim.registry.map_audit import inside, sample

ROOT = Path(__file__).resolve().parents[1]
MAPS = ["ascent", "bind", "haven", "lotus", "split"]


def compiled_fingerprint(map_obj, geometry) -> str:
    payload = [map_obj.model_dump(mode="json"), geometry.model_dump(mode="json")]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def simulation_code_fingerprint():
    paths = sorted((ROOT / "src/esports_sim/sim").rglob("*.py"))
    paths.append(ROOT / "src/esports_sim/schemas/geometry.py")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def physical_route_audit(map_obj, geometry):
    walls = [p for p in geometry.props if p.role == "wall"]
    count, blocked, off_floor = 0, [], []
    for a, neighbors in map_obj.adjacency.items():
        for b in neighbors:
            for start in geometry.room_slots(a, .35):
                for end in geometry.room_slots(b, .35):
                    route = geometry.path_between_points(a,b,start[:2],end[:2],.35)
                    count += 1
                    if any(_segment_hits_rect(*u,*v,p.x-.35,p.y-.35,p.w+.7,p.h+.7)
                           for u,v in zip(route,route[1:]) for p in walls):
                        blocked.append({"from":a,"to":b,"start":start,"end":end})
                    if any(not inside(p, [geometry.regions[a],geometry.regions[b]], eps=1e-7)
                           for p in sample(route, step=.25)):
                        off_floor.append({"from":a,"to":b,"start":start,"end":end})
    return {"holding_routes_checked":count,"blocked_routes":blocked,"off_floor_routes":off_floor}


def main(matches: int, maps=None, output_dir=None) -> None:
    maps = maps or MAPS
    review = output_dir or ROOT / "runs" / "layout-review"
    review.mkdir(parents=True, exist_ok=True)
    reports = []
    code_fingerprint = simulation_code_fingerprint()
    with tempfile.TemporaryDirectory(prefix="compiled-", dir=review) as tmp:
        data_dir = Path(tmp) / "data"
        shutil.copytree(ROOT / "data", data_dir)
        for name in maps:
            doc, revision = map_workbench.load_document(f"{name}-layout-v2")
            map_obj, geo, errors = map_workbench.validate_document(doc)
            if errors:
                raise ValueError(f"{doc.id}: {errors}")
            assert map_obj is not None and geo is not None
            route_audit = physical_route_audit(map_obj,geo)
            if route_audit["blocked_routes"]:
                raise ValueError(f"{doc.id}: holding routes cross solid wall volumes")
            if name not in MAPS and route_audit['off_floor_routes']:
                raise ValueError(f"{doc.id}: holding routes leave adjacent physical floors")
            (data_dir / "maps" / f"{name}.yaml").write_text(yaml.safe_dump(
                map_obj.model_copy(update={"id": name}).model_dump(mode="json"), sort_keys=False), encoding="utf-8")
            (data_dir / "maps" / "geometry" / f"{name}.yaml").write_text(yaml.safe_dump(
                geo.model_copy(update={"map_id": name}).model_dump(mode="json"), sort_keys=False), encoding="utf-8")
            probes = []
            for zone in doc.semantic_zones:
                if zone.kind in ("spawn", "site", "plant") and zone.site_id != "mid":
                    result = probe_map(doc, zone.label_position)
                    result["reachable_zones"] = sorted(result["reachable_zones"])
                    probes.append({"zone": zone.id, "point": zone.label_position, **result})
            reports.append({"map_id": doc.id, "revision_hash": revision, "geometry_valid": True,
                            "compiled_sha256": compiled_fingerprint(map_obj, geo),
                            "floor_comparison": compare_reference(doc, grid_step=.25 if name not in MAPS else .5),
                            "physical_route_audit": route_audit,
                            "reference": doc.reference.model_dump() if doc.reference else None, "probes": probes})
        failed = False
        for script, args in [("map_floor_audit.py", []), ("pacing_report.py", []), ("balance_report.py", [str(matches)])]:
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args,
                                     "--data-dir", str(data_dir), "--maps", *maps],
                                    cwd=ROOT, capture_output=True, text=True)
            (review / f"{Path(script).stem}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
            print(result.stdout, end="", flush=True)
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            failed |= result.returncode != 0
        # Keep a concurrent authoring edit only when it produces exactly the
        # artifacts that were simulated. Never attach a green gate to changed
        # gameplay merely because the map id is the same.
        if simulation_code_fingerprint() != code_fingerprint:
            failed = True
            print("Simulation code changed during gates; run again", flush=True)
        for report in reports:
            current, revision = map_workbench.load_document(report["map_id"])
            current_map, current_geo, errors = map_workbench.validate_document(current)
            if errors or compiled_fingerprint(current_map, current_geo) != report["compiled_sha256"]:
                failed = True
                report["current_revision_hash"] = revision
                report["changed_during_gates"] = True
                print(f"{current.id}: gameplay changed during gates; run again", flush=True)
            elif revision != report["revision_hash"]:
                report["tested_revision_hash"] = report["revision_hash"]
                report["revision_hash"] = revision
                report["runtime_equivalent_revision"] = True
        (review / "review.json").write_text(json.dumps({"matches_per_map": matches, "gates_passed": not failed,
                                                        "simulation_code_sha256": code_fingerprint,
                                                        "published": False, "maps": reports}, indent=2), encoding="utf-8")
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=300)
    parser.add_argument("--maps", nargs='+')
    parser.add_argument("--output-dir", type=Path)
    args=parser.parse_args()
    main(args.matches,args.maps,args.output_dir)
