"""Floor-coverage gate: movement must stay on painted floor plates.

Thin wrapper importing the logic from src/esports_sim/registry/map_audit.py.
"""

from __future__ import annotations

import argparse

from esports_sim.registry import load_all
from esports_sim.registry.loader import load_geometry
from esports_sim.registry.map_audit import audit_map


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maps",
        nargs="+",
        metavar="MAP_ID",
        help="audit specific published map ids instead of the live rotation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gd = load_all(map_ids=args.maps)
    total = 0
    for mid in sorted(gd.maps):
        m = gd.maps[mid]
        geo = load_geometry(mid)
        if geo is None:
            print(f"{mid:8s} no geometry -- skipped")
            continue
        findings = audit_map(m, geo)
        total += len(findings)
        status = "clean" if not findings else f"{len(findings)} finding(s)"
        print(f"{mid:8s} {status}")
        for f in findings:
            print(f"         {f}")
    print()
    if total:
        print(f"FAIL: {total} floor-coverage finding(s)")
        raise SystemExit(1)
    print("OK: all movement stays on painted floor")


if __name__ == "__main__":
    main()
