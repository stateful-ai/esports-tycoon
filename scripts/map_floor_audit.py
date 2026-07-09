"""Floor-coverage gate: movement must stay on painted floor plates.

The match backdrops are painted from the floor-region rects in
data/maps/geometry/*.yaml -- anything outside those rects is void
(background art, not walkable floor). Three checks per map:

  1. every callout anchor sits on its own plate (no floating labels),
  2. every adjacency pair's plates touch (shared boundary or slight
     overlap) so the doorway seam has floor under it,
  3. every movement polyline (geo.path, densely sampled) stays on the
     union of plates -- players never walk on the background.

Teleporter edges are exempt from checks 2 and 3: the gimmick beams
players between the pads (the engine collapses the polyline to its two
endpoints and the viewer draws a shaft), so there is intentionally no
floor between them. Walked gimmicks (rotating/breakable doors) get no
exemption.

Exit code 1 when any map has findings. Run after touching
data/maps/**, alongside the balance and pacing gates.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\map_floor_audit.py
"""

from __future__ import annotations

from esports_sim.registry import load_all
from esports_sim.registry.loader import load_geometry
from esports_sim.schemas.map import GimmickType

EPS = 0.75  # world units of forgiveness (sub-door-width)
SAMPLE_STEP = 1.0


def inside(pt: tuple[float, float], rects, eps: float = EPS) -> bool:
    x, y = pt
    return any(
        r.x - eps <= x <= r.x + r.w + eps and r.y - eps <= y <= r.y + r.h + eps
        for r in rects
    )


def rects_touch(a, b, eps: float = EPS) -> bool:
    return not (
        a.x + a.w + eps < b.x or b.x + b.w + eps < a.x
        or a.y + a.h + eps < b.y or b.y + b.h + eps < a.y
    )


def sample(poly: list[tuple[float, float]], step: float = SAMPLE_STEP):
    out: list[tuple[float, float]] = []
    for i in range(1, len(poly)):
        (x0, y0), (x1, y1) = poly[i - 1], poly[i]
        d = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        n = max(2, int(d / step))
        for k in range(n + 1):
            t = k / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def audit_map(m, geo) -> list[str]:
    """All floor-coverage findings for one map (empty = clean)."""
    findings: list[str] = []
    regions = geo.regions
    allrects = list(regions.values())
    teleport_edges = {
        frozenset(g.between)
        for g in m.gimmicks
        if g.type == GimmickType.TELEPORTER
    }

    for cid, c in sorted(m.callouts.items()):
        r = regions.get(cid)
        if r is None:
            findings.append(f"callout {cid}: no region")
        elif not inside((c.x, c.y), [r]):
            findings.append(f"callout {cid}: anchor off own plate")

    seen: set[tuple[str, str]] = set()
    for a, nbrs in sorted(m.adjacency.items()):
        for b in sorted(nbrs):
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            if frozenset((a, b)) in teleport_edges:
                continue  # beamed, not walked; no floor expected
            ra, rb = regions.get(a), regions.get(b)
            if ra and rb and not rects_touch(ra, rb):
                findings.append(f"detached plates: {a} <-> {b}")
            poly = geo.path(a, b)
            pts = sample([(p[0], p[1]) for p in poly])
            off = sum(1 for p in pts if not inside(p, allrects))
            if off:
                findings.append(
                    f"path in void: {a} -> {b} ({off}/{len(pts)} pts off-floor)"
                )
    return findings


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
