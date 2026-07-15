"""Map auditing package for legacy and continuous geometry.
"""

from __future__ import annotations

from collections import deque
from typing import Any
from esports_sim.schemas.map import GimmickType
from esports_sim.schemas.studio import MapStudioDocumentV1, WalkableSurface, SemanticZone, Prop, TraversalLink

EPS = 0.75  # world units of forgiveness (sub-door-width)
SAMPLE_STEP = 1.0


# ---------------------------------------------------------------------------
# Legacy Floor Audit (Refactored from scripts/map_floor_audit.py)

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


def audit_map(m: Any, geo: Any) -> list[str]:
    """All floor-coverage findings for one compiled map (empty = clean)."""
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


# ---------------------------------------------------------------------------
# Continuous Geometry Audits

def ccw(A: tuple[float, float], B: tuple[float, float], C: tuple[float, float]) -> bool:
    return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])


def segments_intersect(p1: tuple[float, float], p2: tuple[float, float], q1: tuple[float, float], q2: tuple[float, float]) -> bool:
    # Liang-Barsky or orientation-based check
    return ccw(p1, q1, q2) != ccw(p2, q1, q2) and ccw(p1, p2, q1) != ccw(p1, p2, q2)


def point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0.0 and dy == 0.0:
        return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
    t = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / (dx * dx + dy * dy),
        ),
    )
    px, py = start[0] + t * dx, start[1] + t * dy
    return ((point[0] - px) ** 2 + (point[1] - py) ** 2) ** 0.5


def segment_distance(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> float:
    if segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        point_segment_distance(a1, b1, b2),
        point_segment_distance(a2, b1, b2),
        point_segment_distance(b1, a1, a2),
        point_segment_distance(b2, a1, a2),
    )


def is_point_in_polygon(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    # Ray-casting algorithm
    x, y = pt
    inside_poly = False
    n = len(poly)
    if n == 0:
        return False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside_poly = not inside_poly
        p1x, p1y = p2x, p2y
    return inside_poly


def check_polygon_valid(poly: list[tuple[float, float]]) -> list[str]:
    findings = []
    if len(poly) < 3:
        findings.append(f"Polygon has too few vertices: {len(poly)}")
        return findings
    n = len(poly)
    # Check self-intersection
    for i in range(n):
        p1, p2 = poly[i], poly[(i + 1) % n]
        for j in range(i + 2, n):
            if (j + 1) % n == i:
                continue
            q1, q2 = poly[j], poly[(j + 1) % n]
            if segments_intersect(p1, p2, q1, q2):
                findings.append(f"Polygon self-intersects between edge {p1}->{p2} and edge {q1}->{q2}")
    return findings


def polygon_contains_polygon(outer: list[tuple[float, float]], inner: list[tuple[float, float]]) -> bool:
    # Every point of inner must be inside outer, and no edges may intersect
    for pt in inner:
        if not is_point_in_polygon(pt, outer):
            return False
    n_out = len(outer)
    n_in = len(inner)
    for i in range(n_out):
        o1, o2 = outer[i], outer[(i + 1) % n_out]
        for j in range(n_in):
            i1, i2 = inner[j], inner[(j + 1) % n_in]
            if segments_intersect(o1, o2, i1, i2):
                return False
    return True


def audit_continuous(doc: MapStudioDocumentV1) -> list[str]:
    """Continuous geometry audits for the MapStudioDocumentV1."""
    findings: list[str] = []

    # 1. Walkable surfaces: polygon validity
    surfaces_by_id: dict[str, WalkableSurface] = {}
    for surf in doc.walkable_surfaces:
        if surf.id in surfaces_by_id:
            findings.append(f"Duplicate walkable surface id '{surf.id}'")
            continue
        surfaces_by_id[surf.id] = surf
        errors = check_polygon_valid(surf.polygon)
        for err in errors:
            findings.append(f"Walkable surface '{surf.id}': {err}")

    # 2. Semantic zones: polygon validity & containment
    zones_by_id: dict[str, SemanticZone] = {}
    for zone in doc.semantic_zones:
        if zone.id in zones_by_id:
            findings.append(f"Duplicate semantic zone id '{zone.id}'")
            continue
        zones_by_id[zone.id] = zone
        errors = check_polygon_valid(zone.polygon)
        for err in errors:
            findings.append(f"Semantic zone '{zone.id}': {err}")

        # Check surface mappings
        for sid in zone.surface_ids:
            if sid not in surfaces_by_id:
                findings.append(f"Semantic zone '{zone.id}' references missing surface '{sid}'")
            else:
                surf = surfaces_by_id[sid]
                if not is_point_in_polygon(zone.label_position, surf.polygon):
                    findings.append(
                        f"Semantic zone '{zone.id}' label position is outside "
                        f"walkable surface '{sid}'"
                    )

    for side, spawn_id in (
        ("attacker", doc.attacker_spawn),
        ("defender", doc.defender_spawn),
    ):
        spawn = zones_by_id.get(spawn_id)
        if spawn is None:
            findings.append(f"{side.title()} spawn references missing zone '{spawn_id}'")
        elif spawn.kind != "spawn":
            findings.append(f"{side.title()} spawn zone '{spawn_id}' must have kind 'spawn'")

    # 3. Traversal links: endpoints supported & reachable
    link_ids: set[str] = set()
    for link in doc.traversal_links:
        if link.id in link_ids:
            findings.append(f"Duplicate traversal link id '{link.id}'")
            continue
        link_ids.add(link.id)
        # from pos
        fx, fy, fsid = link.from_pos
        if fsid not in surfaces_by_id:
            findings.append(f"Traversal link '{link.id}' from_pos references missing surface '{fsid}'")
        else:
            surf = surfaces_by_id[fsid]
            if not is_point_in_polygon((fx, fy), surf.polygon):
                findings.append(f"Traversal link '{link.id}' from_pos ({fx}, {fy}) is outside walkable surface '{fsid}'")
        # to pos
        tx, ty, tsid = link.to_pos
        if tsid not in surfaces_by_id:
            findings.append(f"Traversal link '{link.id}' to_pos references missing surface '{tsid}'")
        else:
            surf = surfaces_by_id[tsid]
            if not is_point_in_polygon((tx, ty), surf.polygon):
                findings.append(f"Traversal link '{link.id}' to_pos ({tx}, {ty}) is outside walkable surface '{tsid}'")

        # A Studio-authored corridor is the motor controller's exact route
        # core. Reject it if a player-sized capsule would clip authored walls
        # or colliding props; the current match sim deliberately trusts this
        # validated path rather than running a second pathfinder every tick.
        if link.path_mode == "corridor" and link.include_endpoints_in_path:
            route = [link.from_pos[:2], *link.via, link.to_pos[:2]]
            blockers: list[
                tuple[str, tuple[float, float], tuple[float, float], float]
            ] = []
            for wall_index, wall in enumerate(doc.walls):
                for point_index in range(1, len(wall.polyline)):
                    blockers.append((
                        f"wall_{wall_index}",
                        wall.polyline[point_index - 1],
                        wall.polyline[point_index],
                        1.0 + wall.thickness / 2.0,
                    ))
            for prop in doc.props:
                if not prop.collision:
                    continue
                for point_index in range(len(prop.footprint)):
                    blockers.append((
                        prop.id,
                        prop.footprint[point_index],
                        prop.footprint[(point_index + 1) % len(prop.footprint)],
                        1.0,
                    ))
            collision = next(
                (
                    blocker_id
                    for route_start, route_end in zip(route, route[1:])
                    for blocker_id, block_start, block_end, clearance in blockers
                    if segment_distance(route_start, route_end, block_start, block_end)
                    < clearance
                ),
                None,
            )
            if collision is not None:
                findings.append(
                    f"Traversal link '{link.id}' lacks player clearance at '{collision}'"
                )

    # 4. Object support (props)
    prop_ids: set[str] = set()
    for prop in doc.props:
        if prop.id in prop_ids:
            findings.append(f"Duplicate prop id '{prop.id}'")
            continue
        prop_ids.add(prop.id)
        if prop.surface_id not in surfaces_by_id:
            findings.append(f"Prop '{prop.id}' references missing surface '{prop.surface_id}'")
        else:
            surf = surfaces_by_id[prop.surface_id]
            if (
                prop.id not in doc.legacy.prop_support_exemptions
                and not polygon_contains_polygon(surf.polygon, prop.footprint)
            ):
                findings.append(f"Prop '{prop.id}' footprint is not fully supported by surface '{prop.surface_id}'")

    # 5. Overlapping surfaces / elevation audit
    for i, surf1 in enumerate(doc.walkable_surfaces):
        for j, surf2 in enumerate(doc.walkable_surfaces[i+1:]):
            # Check overlap in 2D
            overlaps = False
            for pt in surf1.polygon:
                if is_point_in_polygon(pt, surf2.polygon):
                    overlaps = True
                    break
            if not overlaps:
                for pt in surf2.polygon:
                    if is_point_in_polygon(pt, surf1.polygon):
                        overlaps = True
                        break
            if not overlaps:
                # Check if any line segments of surf1 intersect with surf2's line segments
                n1 = len(surf1.polygon)
                n2 = len(surf2.polygon)
                for k1 in range(n1):
                    p1 = surf1.polygon[k1]
                    p2 = surf1.polygon[(k1 + 1) % n1]
                    for k2 in range(n2):
                        q1 = surf2.polygon[k2]
                        q2 = surf2.polygon[(k2 + 1) % n2]
                        if segments_intersect(p1, p2, q1, q2):
                            overlaps = True
                            break
                    if overlaps:
                        break
            if overlaps:
                z_diff = abs(surf1.elevation - surf2.elevation)
                if z_diff > 0 and z_diff < 2.5:
                    findings.append(
                        f"Walkable surfaces '{surf1.id}' and '{surf2.id}' overlap in 2D "
                        f"but have incompatible elevations (z diff = {z_diff:.2f} < 2.5)"
                    )

    # 6. Reachability checks: spawn zones to every site and plant zone
    # Build reachability graph:
    # Nodes: semantic zone IDs
    # Edges: zones that touch/overlap walkable surfaces, or connected via traversal links
    adj: dict[str, set[str]] = {z.id: set() for z in doc.semantic_zones}
    
    # Connect zones if they share a surface
    for zone1 in doc.semantic_zones:
        for zone2 in doc.semantic_zones:
            if zone1.id == zone2.id:
                continue
            shared_surfaces = set(zone1.surface_ids) & set(zone2.surface_ids)
            if shared_surfaces:
                adj[zone1.id].add(zone2.id)
                adj[zone2.id].add(zone1.id)

    # Synthesized legacy documents retain the complete runtime graph here.
    # It is just as traversable as an explicitly drawn Studio link.
    for from_zone, neighbors in doc.legacy.adjacency_overrides.items():
        if from_zone not in adj:
            continue
        for to_zone in neighbors:
            if to_zone in adj:
                adj[from_zone].add(to_zone)

    # Connect zones via traversal links
    surf_to_zone: dict[str, str] = {}
    for zone in doc.semantic_zones:
        if zone.kind == "plant":
            continue
        for sid in zone.surface_ids:
            surf_to_zone[sid] = zone.id

    for link in doc.traversal_links:
        from_surf_id = link.from_pos[2]
        to_surf_id = link.to_pos[2]
        from_zone = surf_to_zone.get(from_surf_id)
        to_zone = surf_to_zone.get(to_surf_id)
        if from_zone and to_zone and from_zone != to_zone:
            adj[from_zone].add(to_zone)
            adj[to_zone].add(from_zone)

    # Find spawn zones and targets (sites/plant zones)
    spawns = [z.id for z in doc.semantic_zones if z.kind == "spawn"]
    targets = [z.id for z in doc.semantic_zones if z.kind in ("site", "plant")]

    if not spawns:
        findings.append("No spawn zones defined in map")
    if not targets:
        findings.append("No site/plant targets defined in map")

    for spawn in spawns:
        # Check reachability to all targets using BFS
        visited = {spawn}
        queue = deque([spawn])
        while queue:
            curr = queue.popleft()
            for neighbor in adj.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        
        unreachable = [t for t in targets if t not in visited]
        if unreachable:
            findings.append(f"Spawn zone '{spawn}' cannot reach targets: {unreachable}")

    # 7. Zone containment: plant zones strictly contained inside parent site zones
    for zone in doc.semantic_zones:
        if zone.kind == "plant":
            # Must find a site zone that contains it and matches its site_id
            site_found = False
            for other in doc.semantic_zones:
                if other.kind == "site" and other.site_id == zone.site_id:
                    if polygon_contains_polygon(other.polygon, zone.polygon):
                        site_found = True
                        break
            if not site_found:
                findings.append(f"Plant zone '{zone.id}' (site '{zone.site_id}') is not contained in matching site zone")

    # 8. Ambiguous overlaps: semantic zones must not ambiguously overlap
    # If two site/spawn/plant zones overlap heavily, report it
    for i, zone1 in enumerate(doc.semantic_zones):
        for j, zone2 in enumerate(doc.semantic_zones[i+1:]):
            if zone1.kind in ("spawn", "plant") and zone2.kind in ("spawn", "plant"):
                # If they overlap, it's ambiguous
                overlaps = False
                for pt in zone1.polygon:
                    if is_point_in_polygon(pt, zone2.polygon):
                        overlaps = True
                        break
                if not overlaps:
                    for pt in zone2.polygon:
                        if is_point_in_polygon(pt, zone1.polygon):
                            overlaps = True
                            break
                if not overlaps:
                    n1 = len(zone1.polygon)
                    n2 = len(zone2.polygon)
                    for k in range(n1):
                        e1_1 = zone1.polygon[k]
                        e1_2 = zone1.polygon[(k + 1) % n1]
                        for m in range(n2):
                            e2_1 = zone2.polygon[m]
                            e2_2 = zone2.polygon[(m + 1) % n2]
                            if segments_intersect(e1_1, e1_2, e2_1, e2_2):
                                overlaps = True
                                break
                        if overlaps:
                            break
                if overlaps:
                    findings.append(f"Ambiguous overlap between semantic zones '{zone1.id}' and '{zone2.id}'")

    return findings
