"""Map guide renderer.
Implements guide image rendering for both legacy compiled maps and continuous studio documents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from esports_sim.schemas.map import Map
from esports_sim.schemas.geometry import MapGeometry
from esports_sim.schemas.studio import MapStudioDocumentV1

# -- transform constants (mirror viewer.js drawStatic() iso branch) ----------
VIEWBOX_MIN_X = -110.0
VIEWBOX_MIN_Y = -12.0
VIEWBOX_W = 220.0
VIEWBOX_H = 128.0
SCALE = 8  # px per viewBox unit -> 1760 x 1024 guide
WALL_DROP = 3.2  # viewer.js WALL_DROP: iso plinth extrusion depth

# -- semantic palette (flat, high-contrast; navy-broadcast diorama base) -----
GROUND = (9, 11, 17)  # dark ground outside the playable footprint
# Alternating close floor tones so adjacent rooms read apart WITHOUT borders.
FLOOR_TONES = [(54, 60, 76), (61, 67, 84), (47, 53, 70)]
WALL_FACE = (17, 19, 28)  # plinth face under a floor
WALL_FACE_RAISED = (26, 29, 41)  # taller plinth under an elevated room
SPAWN_TINT = {
    "attacker_spawn": (206, 96, 74),  # warm — attacker side
    "defender_spawn": (78, 138, 208),  # cool — defender side
}
SITE_TINT = {
    "a": (178, 132, 72),  # amber
    "b": (84, 158, 128),  # teal
    "c": (150, 108, 172),  # violet
    "mid": (120, 124, 140),  # neutral
}
RAISED_FLOOR_LIFT = 0.16  # brighten elevated floors toward white
PROP_HALF = (150, 110, 66)  # crates — warm tan
PROP_FULL = (108, 115, 131)  # full-height sight blockers — cool grey
PROP_SIDE = 0.6  # side-face brightness multiplier
PROP_H = {"half": 1.5, "full": 3.2}  # iso extrusion heights


def blend(base: tuple, over: tuple, a: float) -> tuple[int, int, int]:
    return tuple(int(base[i] * (1 - a) + over[i] * a) for i in range(3))


def brighten(c: tuple, a: float) -> tuple[int, int, int]:
    return blend(c, (255, 255, 255), a)


def darken(c: tuple, m: float) -> tuple[int, int, int]:
    return tuple(int(v * m) for v in c)


def iso(gx: float, gy: float) -> tuple[float, float]:
    """World grid -> viewBox-space iso point. Mirrors viewer P(x, 100-y)."""
    return (gx + gy - 100.0, (gx - gy + 100.0) / 2.0)


def to_px(ix: float, iy: float) -> tuple[float, float]:
    return ((ix - VIEWBOX_MIN_X) * SCALE, (iy - VIEWBOX_MIN_Y) * SCALE)


def region_corners(r: Any, z: float) -> list[tuple[float, float]]:
    """Four projected floor corners (px), elevation applied."""
    x = getattr(r, "x", 0.0)
    y = getattr(r, "y", 0.0)
    w = getattr(r, "w", 0.0)
    h = getattr(r, "h", 0.0)
    g = [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h),
    ]
    out = []
    for gx, gy in g:
        ix, iy = iso(gx, gy)
        out.append(to_px(ix, iy - z))
    return out


def floor_fill(idx: int, zone: str | None, site: str | None, z: float) -> tuple:
    """Base tone (alternating) + gentle zone tint + elevation lift."""
    tone = FLOOR_TONES[idx % len(FLOOR_TONES)]
    if zone in SPAWN_TINT:
        tone = blend(tone, SPAWN_TINT[zone], 0.28)
    elif zone == "site" and site in SITE_TINT:
        tone = blend(tone, SITE_TINT[site], 0.24)
    elif zone == "mid":
        tone = blend(tone, SITE_TINT["mid"], 0.10)
    if z > 0:
        tone = brighten(tone, RAISED_FLOOR_LIFT)
    return tone


def draw_prop(d: ImageDraw.ImageDraw, p: Any, zr: float) -> None:
    """Iso box (two near side faces + top face), matching viewer drawFloor prop extrusion."""
    px = getattr(p, "x", 0.0)
    py = getattr(p, "y", 0.0)
    pw = getattr(p, "w", 0.0)
    ph = getattr(p, "h", 0.0)
    pheight = getattr(p, "height", "half")

    hgt_units = PROP_H.get(pheight, 1.5)
    hgt_px = hgt_units * SCALE
    g = [
        (px, py),
        (px + pw, py),
        (px + pw, py + ph),
        (px, py + ph),
    ]
    base = []
    for gx, gy in g:
        ix, iy = iso(gx, gy)
        base.append(to_px(ix, iy - zr))
    top = [(x, y - hgt_px) for x, y in base]
    color = PROP_FULL if pheight == "full" else PROP_HALF
    side = darken(color, PROP_SIDE)
    # Two faces adjacent to the nearest (max-y) top corner.
    nearest = max(range(4), key=lambda i: top[i][1])
    for j in ((nearest + 3) % 4, nearest):
        p1, p2 = top[j], top[(j + 1) % 4]
        d.polygon(
            [p1, p2, (p2[0], p2[1] + hgt_px), (p1[0], p1[1] + hgt_px)], fill=side
        )
    d.polygon(top, fill=color)


# ---------------------------------------------------------------------------
# Core Renderers

def render_legacy_guide(m: Map, geo: MapGeometry) -> tuple[Image.Image, dict[str, Any]]:
    """Render legacy guide image from compiled Map + MapGeometry objects."""
    regions = geo.regions
    w_px = int(VIEWBOX_W * SCALE)
    h_px = int(VIEWBOX_H * SCALE)
    img = Image.new("RGB", (w_px, h_px), GROUND)
    d = ImageDraw.Draw(img)

    # Painter's algorithm: farthest rooms first (smallest max screen-y)
    def maxy(rid: str) -> float:
        r = regions[rid]
        return max(p[1] for p in region_corners(r, r.z))

    order = sorted(regions, key=maxy)

    content: list[tuple[float, float]] = []
    for idx, rid in enumerate(order):
        r = regions[rid]
        z = r.z
        corners = region_corners(r, z)
        content.extend(corners)
        # Plinth
        drop = (WALL_DROP + z) * SCALE
        nearest = max(range(4), key=lambda i: corners[i][1])
        wall = WALL_FACE_RAISED if z > 0 else WALL_FACE
        for j in ((nearest + 3) % 4, nearest):
            p1, p2 = corners[j], corners[(j + 1) % 4]
            d.polygon(
                [p1, p2, (p2[0], p2[1] + drop), (p1[0], p1[1] + drop)], fill=wall
            )
        co = m.callouts.get(rid)
        zone = co.zone if co else None
        site = co.site if co else None
        d.polygon(corners, fill=floor_fill(idx, zone, site, z))

    # Props back-to-front
    def prop_key(p: Any) -> float:
        ix, iy = iso(p.x + p.w / 2, p.y + p.h / 2)
        return iy

    for p in sorted(geo.props, key=prop_key):
        zr = regions.get(prop.region).z if (prop := p) and prop.region in regions else 0.0
        draw_prop(d, p, zr)

    cxs = [(px / SCALE + VIEWBOX_MIN_X) for px, _ in content]
    cys = [(py / SCALE + VIEWBOX_MIN_Y) for _, py in content]
    info = {
        "w_px": w_px,
        "h_px": h_px,
        "content_vb": (
            round(min(cxs), 1) if cxs else VIEWBOX_MIN_X,
            round(min(cys), 1) if cys else VIEWBOX_MIN_Y,
            round(max(cxs), 1) if cxs else VIEWBOX_MIN_X + VIEWBOX_W,
            round(max(cys), 1) if cys else VIEWBOX_MIN_Y + VIEWBOX_H,
        ),
        "regions": len(regions),
        "props": len(geo.props),
    }
    return img, info


def render_continuous_preview(doc: MapStudioDocumentV1) -> tuple[Image.Image, dict[str, Any]]:
    """Render a preview guide of the continuous source geometry for the editor."""
    w_px = int(VIEWBOX_W * SCALE)
    h_px = int(VIEWBOX_H * SCALE)
    img = Image.new("RGB", (w_px, h_px), GROUND)
    d = ImageDraw.Draw(img)

    # Convert walkable surfaces polygons to projected corners
    # Farthest surfaces first
    def maxy_surf(surf: Any) -> float:
        corners = []
        for gx, gy in surf.polygon:
            ix, iy = iso(gx, gy)
            corners.append(to_px(ix, iy - surf.elevation))
        return max(p[1] for p in corners) if corners else 0.0

    sorted_surfs = sorted(doc.walkable_surfaces, key=maxy_surf)

    content: list[tuple[float, float]] = []
    for idx, surf in enumerate(sorted_surfs):
        corners = []
        for gx, gy in surf.polygon:
            ix, iy = iso(gx, gy)
            corners.append(to_px(ix, iy - surf.elevation))
        
        if not corners:
            continue
        content.extend(corners)

        # Plinth
        drop = (WALL_DROP + surf.elevation) * SCALE
        nearest = max(range(len(corners)), key=lambda i: corners[i][1])
        wall = WALL_FACE_RAISED if surf.elevation > 0 else WALL_FACE
        # Draw plinth faces
        n_pts = len(corners)
        for j in ((nearest - 1) % n_pts, nearest):
            p1, p2 = corners[j], corners[(j + 1) % n_pts]
            d.polygon(
                [p1, p2, (p2[0], p2[1] + drop), (p1[0], p1[1] + drop)], fill=wall
            )

        # Find matching semantic zone
        zone_kind = None
        site_id = None
        for zone in doc.semantic_zones:
            if surf.id in zone.surface_ids:
                zone_kind = zone.kind
                site_id = zone.site_id
                break
        
        d.polygon(corners, fill=floor_fill(idx, zone_kind, site_id, surf.elevation))

    # Draw continuous props
    def prop_key_cont(p: Any) -> float:
        # compute center of footprint
        if not p.footprint:
            return 0.0
        xs = [pt[0] for pt in p.footprint]
        ys = [pt[1] for pt in p.footprint]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        ix, iy = iso(cx, cy)
        return iy

    for p in sorted(doc.props, key=prop_key_cont):
        # find elevation of surface
        elevation = 0.0
        for surf in doc.walkable_surfaces:
            if surf.id == p.surface_id:
                elevation = surf.elevation
                break
        
        # Extrude prop
        hgt_units = PROP_H.get(p.height, 1.5)
        hgt_px = hgt_units * SCALE
        base_pts = []
        for gx, gy in p.footprint:
            ix, iy = iso(gx, gy)
            base_pts.append(to_px(ix, iy - elevation))
        
        if not base_pts:
            continue
        top = [(x, y - hgt_px) for x, y in base_pts]
        color = PROP_FULL if p.height == "full" else PROP_HALF
        side = darken(color, PROP_SIDE)
        
        # Extrude sides
        n_pts = len(top)
        nearest = max(range(n_pts), key=lambda i: top[i][1])
        for j in ((nearest - 1) % n_pts, nearest):
            p1, p2 = top[j], top[(j + 1) % n_pts]
            d.polygon(
                [p1, p2, (p2[0], p2[1] + hgt_px), (p1[0], p1[1] + hgt_px)], fill=side
            )
        d.polygon(top, fill=color)

    # Render walls as thin elevated line segments (optional, or just for visual guide)
    for wall in doc.walls:
        polyline = wall.polyline
        thickness = wall.thickness
        # draw a simple line in iso projection
        for i in range(1, len(polyline)):
            p1 = polyline[i-1]
            p2 = polyline[i]
            ix1, iy1 = iso(p1[0], p1[1])
            ix2, iy2 = iso(p2[0], p2[1])
            d.line([to_px(ix1, iy1), to_px(ix2, iy2)], fill=(20, 20, 30), width=int(thickness * SCALE))

    cxs = [(px / SCALE + VIEWBOX_MIN_X) for px, _ in content]
    cys = [(py / SCALE + VIEWBOX_MIN_Y) for _, py in content]
    info = {
        "w_px": w_px,
        "h_px": h_px,
        "content_vb": (
            round(min(cxs), 1) if cxs else VIEWBOX_MIN_X,
            round(min(cys), 1) if cys else VIEWBOX_MIN_Y,
            round(max(cxs), 1) if cxs else VIEWBOX_MIN_X + VIEWBOX_W,
            round(max(cys), 1) if cys else VIEWBOX_MIN_Y + VIEWBOX_H,
        ),
        "regions": len(doc.walkable_surfaces),
        "props": len(doc.props),
    }
    return img, info
