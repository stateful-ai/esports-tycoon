"""Floor-coverage gate: movement must stay on painted floor plates.

Thin wrapper importing the logic from src/esports_sim/registry/map_audit.py.
"""

from __future__ import annotations

from esports_sim.registry import load_all
from esports_sim.registry.loader import load_geometry
from esports_sim.registry.map_audit import audit_map


def main() -> None:
    gd = load_all()
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
