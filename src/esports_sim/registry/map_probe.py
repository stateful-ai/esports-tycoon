"""Map Probe physics module.
Implements server-side collision raycasting, LOS, clearance, and reachability.
"""

from __future__ import annotations

from collections import deque
from typing import Any
from esports_sim.schemas.studio import MapStudioDocumentV1, WalkableSurface, SemanticZone, Prop
from esports_sim.registry.map_audit import segments_intersect, is_point_in_polygon

def point_to_segment_dist(p: tuple[float, float], s1: tuple[float, float], s2: tuple[float, float]) -> tuple[float, tuple[float, float]]:
    dx = s2[0] - s1[0]
    dy = s2[1] - s1[1]
    if dx == 0 and dy == 0:
        dist = ((p[0]-s1[0])**2 + (p[1]-s1[1])**2)**0.5
        return dist, s1
    
    t = ((p[0]-s1[0])*dx + (p[1]-s1[1])*dy) / (dx*dx + dy*dy)
    t = max(0.0, min(1.0, t))
    proj = (s1[0] + t*dx, s1[1] + t*dy)
    dist = ((p[0]-proj[0])**2 + (p[1]-proj[1])**2)**0.5
    return dist, proj


def probe_map(
    doc: MapStudioDocumentV1,
    from_pos: tuple[float, float],
    to_pos: tuple[float, float] | None = None,
    player_radius: float = 1.0,
) -> dict[str, Any]:
    """Calculate physics queries: resolved position, clearance, LOS, and reachability."""
    px, py = from_pos
    
    # 1. Resolve current surface and semantic zone
    curr_surface_id = None
    curr_zone_id = None
    
    for surf in doc.walkable_surfaces:
        if is_point_in_polygon((px, py), surf.polygon):
            curr_surface_id = surf.id
            break
            
    if curr_surface_id:
        for zone in doc.semantic_zones:
            if zone.kind != "plant" and curr_surface_id in zone.surface_ids:
                curr_zone_id = zone.id
                break

    # 2. Compute clearance to closest wall or prop
    clearance = 999.0
    closest_blocker = None
    
    # Gather all blocking segments on/near the current surface
    blocking_segments: list[tuple[tuple[float, float], tuple[float, float], str, str]] = []
    
    # Add walls
    for idx, wall in enumerate(doc.walls):
        poly = wall.polyline
        for i in range(1, len(poly)):
            blocking_segments.append((poly[i-1], poly[i], wall.id or f"wall_{idx}", "wall"))
            
    # Add props with collision
    for prop in doc.props:
        if prop.collision and prop.surface_id == curr_surface_id:
            foot = prop.footprint
            n = len(foot)
            for i in range(n):
                blocking_segments.append((foot[i], foot[(i+1)%n], prop.id, "prop"))
                
    # Add walkable surface boundaries as virtual boundaries if outside
    if curr_surface_id:
        surf = next(s for s in doc.walkable_surfaces if s.id == curr_surface_id)
        foot = surf.polygon
        n = len(foot)
        for i in range(n):
            blocking_segments.append((foot[i], foot[(i+1)%n], f"surf_bound_{surf.id}", "boundary"))

    # Compute clearance from (px, py)
    for s1, s2, bid, btype in blocking_segments:
        if btype == "boundary":
            # distance to walkable boundary is clearance
            dist, _ = point_to_segment_dist((px, py), s1, s2)
            if dist < clearance:
                clearance = dist
                closest_blocker = {"id": bid, "type": btype}
        else:
            dist, _ = point_to_segment_dist((px, py), s1, s2)
            if dist < clearance:
                clearance = dist
                closest_blocker = {"id": bid, "type": btype}

    # 3. Resolve movement endpoint (if to_pos provided)
    resolved_pos = (px, py)
    blocked_by = None
    
    if to_pos:
        tx, ty = to_pos
        dx = tx - px
        dy = ty - py
        
        # Raycast from (px, py) to (tx, ty)
        first_collision_t = 1.0
        
        for s1, s2, bid, btype in blocking_segments:
            if btype == "boundary":
                continue  # boundaries handled by containment check
                
            # Calculate d0 and d1 as perpendicular distances to the line containing S
            seg_dx = s2[0] - s1[0]
            seg_dy = s2[1] - s1[1]
            seg_len = (seg_dx*seg_dx + seg_dy*seg_dy)**0.5
            if seg_len == 0:
                d_0 = ((px - s1[0])**2 + (py - s1[1])**2)**0.5
                d_1 = ((tx - s1[0])**2 + (ty - s1[1])**2)**0.5
            else:
                d_0 = abs(seg_dy * px - seg_dx * py + s2[0] * s1[1] - s2[1] * s1[0]) / seg_len
                d_1 = abs(seg_dy * tx - seg_dx * ty + s2[0] * s1[1] - s2[1] * s1[0]) / seg_len
                
            t_coll = None
            
            # Check if path intersects the segment S
            if segments_intersect((px, py), (tx, ty), s1, s2):
                denom = (tx-px)*(s2[1]-s1[1]) - (ty-py)*(s2[0]-s1[0])
                if denom != 0:
                    num_t = (s1[0]-px)*(s2[1]-s1[1]) - (s1[1]-py)*(s2[0]-s1[0])
                    t_intersect = num_t / denom
                    if d_0 > 0:
                        t_coll = t_intersect * (d_0 - player_radius) / d_0
                    else:
                        t_coll = 0.0
                    t_coll = max(0.0, min(1.0, t_coll))
            else:
                # Check if minimum distance between the segments is < player_radius
                d_P_S, proj_P_S = point_to_segment_dist((px, py), s1, s2)
                d_T_S, proj_T_S = point_to_segment_dist((tx, ty), s1, s2)
                d_s1_Path, proj_s1_Path = point_to_segment_dist(s1, (px, py), (tx, ty))
                d_s2_Path, proj_s2_Path = point_to_segment_dist(s2, (px, py), (tx, ty))
                
                min_dist = min(d_P_S, d_T_S, d_s1_Path, d_s2_Path)
                if min_dist < player_radius:
                    # Find closest point Q on S to the path
                    if min_dist == d_P_S:
                        Q = proj_P_S
                    elif min_dist == d_T_S:
                        Q = proj_T_S
                    elif min_dist == d_s1_Path:
                        Q = s1
                    else:
                        Q = s2
                        
                    # Check if Q is in the interior of S or an endpoint
                    dist_to_s1 = ((Q[0] - s1[0])**2 + (Q[1] - s1[1])**2)**0.5
                    dist_to_s2 = ((Q[0] - s2[0])**2 + (Q[1] - s2[1])**2)**0.5
                    
                    if dist_to_s1 > 1e-7 and dist_to_s2 > 1e-7:
                        # Q is in the interior of S
                        if abs(d_0 - d_1) > 1e-9:
                            t_coll = (d_0 - player_radius) / (d_0 - d_1)
                            t_coll = max(0.0, min(1.0, t_coll))
                        else:
                            t_coll = 0.0
                    else:
                        # Q is one of the endpoints s1 or s2
                        wx, wy = px - Q[0], py - Q[1]
                        if wx*wx + wy*wy <= player_radius*player_radius:
                            t_coll = 0.0
                        else:
                            a = dx*dx + dy*dy
                            if a > 0:
                                b = 2 * (wx*dx + wy*dy)
                                c = wx*wx + wy*wy - player_radius*player_radius
                                disc = b*b - 4*a*c
                                if disc >= 0:
                                    t_val = (-b - disc**0.5) / (2*a)
                                    if 0 <= t_val <= 1:
                                        t_coll = t_val
                                        
            if t_coll is not None:
                if 0.0 <= t_coll < first_collision_t:
                    first_collision_t = t_coll
                    blocked_by = {"id": bid, "type": btype}

        # Compute resolved point
        resolved_pos = (
            px + dx * first_collision_t,
            py + dy * first_collision_t
        )

    # 4. Check LOS Visibility
    los_result = True
    blocking_sight = None
    if to_pos:
        tx, ty = to_pos
        # Full height props and walls block sight
        sight_blocking_segments = []
        for idx, wall in enumerate(doc.walls):
            poly = wall.polyline
            for i in range(1, len(poly)):
                sight_blocking_segments.append((poly[i-1], poly[i], wall.id or f"wall_{idx}", "wall"))
        for prop in doc.props:
            if prop.collision and prop.height == "full":
                foot = prop.footprint
                n = len(foot)
                for i in range(n):
                    sight_blocking_segments.append((foot[i], foot[(i+1)%n], prop.id, "prop"))
                    
        for s1, s2, bid, btype in sight_blocking_segments:
            if segments_intersect((px, py), (tx, ty), s1, s2):
                los_result = False
                blocking_sight = {"id": bid, "type": btype}
                break

    # 5. Reachability findings
    reachable_zones = []
    if curr_zone_id:
        # Build adjacency graph
        adj: dict[str, set[str]] = {z.id: set() for z in doc.semantic_zones}
        for zone1 in doc.semantic_zones:
            for zone2 in doc.semantic_zones:
                if zone1.id == zone2.id:
                    continue
                shared = set(zone1.surface_ids) & set(zone2.surface_ids)
                if shared:
                    adj[zone1.id].add(zone2.id)
        surf_to_zone: dict[str, str] = {}
        for zone in doc.semantic_zones:
            if zone.kind == "plant":
                continue
            for sid in zone.surface_ids:
                surf_to_zone[sid] = zone.id

        for link in doc.traversal_links:
            from_z = surf_to_zone.get(link.from_pos[2])
            to_z = surf_to_zone.get(link.to_pos[2])
            if from_z and to_z and from_z != to_z:
                adj[from_z].add(to_z)
                adj[to_z].add(from_z)

        # BFS
        visited = {curr_zone_id}
        queue = deque([curr_zone_id])
        while queue:
            curr = queue.popleft()
            for neighbor in adj.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        reachable_zones = list(visited)

    return {
        "resolved_pos": resolved_pos,
        "blocked_by": blocked_by,
        "clearance": round(clearance, 2) if clearance != 999.0 else None,
        "closest_blocker": closest_blocker,
        "los": los_result,
        "blocking_sight": blocking_sight,
        "surface_id": curr_surface_id,
        "zone_id": curr_zone_id,
        "reachable_zones": reachable_zones,
    }
