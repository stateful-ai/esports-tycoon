r"""Rasterize match-map geometry into img2img GUIDE images for the paint pass.

The map equivalent of ``render_office_guide.py``. Each map's interaction
geometry (``data/maps/geometry/<map>.yaml`` regions/props/elevation, plus
zone/site labels from ``data/maps/<map>.yaml``) is drawn as a FLAT semantic
raster — floors in alternating close tones, per-type prop colours, gentle
site/spawn tints, dark ground outside the footprint. The painter repaints
it (structure preserved) and the result becomes the viewer's backdrop
``<image>`` under the live SVG layers.

Doctrine (see docs/art-pipeline.md):
  * NO outlines / NO boundary lines / NO text anywhere. Lines teach the
    model to paint drifting lines; the runtime draws authoritative borders
    as a vector overlay from the SAME geometry. Paint = texture only.
  * The guide is rendered in the EXACT isometric projection and frame the
    viewer uses, so guide pixels map linearly onto the viewer's viewBox and
    the paint lands pixel-true under the sim's dynamic layers.

============================  TRANSFORM CONTRACT  ============================
Everything below is mirrored from ``viewer.js`` (functions ``P`` /
``regionCorners`` / ``drawStatic``). Keep the two in sync.

  world grid point (gx, gy) with per-room elevation z, y-down 0..100:
      iso_x = gx + gy - 100                      # viewer P(x, 100-y)
      iso_y = (gx - gy + 100) / 2 - z            # z shifts UP on screen

  The guide canvas covers the viewer's iso viewBox EXACTLY:
      VIEWBOX = (min_x, min_y, w, h) = (-110, -12, 220, 128)   # viewer.js
  at a fixed SCALE (px per viewBox unit):
      guide_px  = (iso_x - VIEWBOX_MIN_X) * SCALE = (iso_x + 110) * SCALE
      guide_py  = (iso_y - VIEWBOX_MIN_Y) * SCALE = (iso_y +  12) * SCALE
      image size = (VIEWBOX_W * SCALE, VIEWBOX_H * SCALE)

  Inverse (viewer <image> placement), so the runtime mirrors this:
      place <image> at x=VIEWBOX_MIN_X y=VIEWBOX_MIN_Y
                      width=VIEWBOX_W  height=VIEWBOX_H
                      preserveAspectRatio="none"   (aspect is exact)
  The frame is map-INDEPENDENT — same box for every map — so the paint agent
  always works one consistent 1760x1024 canvas; only the geometry inside
  differs. Per-map content bounds are printed for reference.
=============================================================================

Usage:
    .venv-win\Scripts\python.exe scripts\render_map_guide.py            # all maps
    .venv-win\Scripts\python.exe scripts\render_map_guide.py --map haven
Requires Pillow + PyYAML (in the [dev]/[web] extras).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "data" / "maps" / "geometry"
MAP_DIR = ROOT / "data" / "maps"
OUT_DIR = ROOT / "assets" / "maps" / "guides"

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
# Gentle zone tints, blended over the floor tone.
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
# Per-type prop colours (crate / wall). Match the viewer's prop hues.
PROP_HALF = (150, 110, 66)  # crates — warm tan
PROP_FULL = (108, 115, 131)  # full-height sight blockers — cool grey
PROP_SIDE = 0.6  # side-face brightness multiplier (viewer .prop-side ~.62)
PROP_H = {"half": 1.5, "full": 3.2}  # iso extrusion heights (viewer drawFloor)


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


def region_corners(r: dict, z: float) -> list[tuple[float, float]]:
    """Four projected floor corners (px), elevation applied — matches
    viewer.js regionCorners()."""
    g = [
        (r["x"], r["y"]),
        (r["x"] + r["w"], r["y"]),
        (r["x"] + r["w"], r["y"] + r["h"]),
        (r["x"], r["y"] + r["h"]),
    ]
    out = []
    for gx, gy in g:
        ix, iy = iso(gx, gy)
        out.append(to_px(ix, iy - z))
    return out


def load_map(map_id: str) -> tuple[dict, dict]:
    """Return (geometry dict, callouts dict[id -> {zone, site}])."""
    geo = yaml.safe_load((GEO_DIR / f"{map_id}.yaml").read_text(encoding="utf-8"))
    callouts: dict[str, dict] = {}
    base_path = MAP_DIR / f"{map_id}.yaml"
    if base_path.exists():
        base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
        for cid, c in (base.get("callouts") or {}).items():
            callouts[cid] = {"zone": c.get("zone"), "site": c.get("site")}
    return geo, callouts


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


def draw_prop(d: ImageDraw.ImageDraw, p: dict, zr: float) -> None:
    """Iso box (two near side faces + top face), matching viewer drawFloor
    prop extrusion. No outline."""
    hgt_units = PROP_H.get(p.get("height", "half"), 1.5)
    hgt_px = hgt_units * SCALE
    g = [
        (p["x"], p["y"]),
        (p["x"] + p["w"], p["y"]),
        (p["x"] + p["w"], p["y"] + p["h"]),
        (p["x"], p["y"] + p["h"]),
    ]
    base = []
    for gx, gy in g:
        ix, iy = iso(gx, gy)
        base.append(to_px(ix, iy - zr))
    top = [(x, y - hgt_px) for x, y in base]
    color = PROP_FULL if p.get("height") == "full" else PROP_HALF
    side = darken(color, PROP_SIDE)
    # Two faces adjacent to the nearest (max-y) top corner.
    nearest = max(range(4), key=lambda i: top[i][1])
    for j in ((nearest + 3) % 4, nearest):
        p1, p2 = top[j], top[(j + 1) % 4]
        d.polygon(
            [p1, p2, (p2[0], p2[1] + hgt_px), (p1[0], p1[1] + hgt_px)], fill=side
        )
    d.polygon(top, fill=color)


def render(map_id: str) -> tuple[Image.Image, dict]:
    geo, callouts = load_map(map_id)
    regions: dict[str, dict] = geo["regions"]
    w_px = int(VIEWBOX_W * SCALE)
    h_px = int(VIEWBOX_H * SCALE)
    img = Image.new("RGB", (w_px, h_px), GROUND)
    d = ImageDraw.Draw(img)

    # Painter's algorithm: farthest rooms first (smallest max screen-y),
    # matching viewer drawFloor's sort.
    def maxy(rid: str) -> float:
        r = regions[rid]
        return max(p[1] for p in region_corners(r, r.get("z", 0.0) or 0.0))

    order = sorted(regions, key=maxy)

    content: list[tuple[float, float]] = []
    for idx, rid in enumerate(order):
        r = regions[rid]
        z = r.get("z", 0.0) or 0.0
        corners = region_corners(r, z)
        content.extend(corners)
        # Plinth: two faces adjacent to the nearest corner, dropped by
        # WALL_DROP + z (mirror viewer). No outline, no interior lines.
        drop = (WALL_DROP + z) * SCALE
        nearest = max(range(4), key=lambda i: corners[i][1])
        wall = WALL_FACE_RAISED if z > 0 else WALL_FACE
        for j in ((nearest + 3) % 4, nearest):
            p1, p2 = corners[j], corners[(j + 1) % 4]
            d.polygon(
                [p1, p2, (p2[0], p2[1] + drop), (p1[0], p1[1] + drop)], fill=wall
            )
        co = callouts.get(rid, {})
        d.polygon(corners, fill=floor_fill(idx, co.get("zone"), co.get("site"), z))

    # Props back-to-front by footprint centre (matches viewer prop sort).
    def prop_key(p: dict) -> float:
        ix, iy = iso(p["x"] + p["w"] / 2, p["y"] + p["h"] / 2)
        return iy

    for p in sorted(geo.get("props", []) or [], key=prop_key):
        zr = regions.get(p["region"], {}).get("z", 0.0) or 0.0
        draw_prop(d, p, zr)

    # Content bbox in viewBox units (for the paint agent's reference).
    cxs = [(px / SCALE + VIEWBOX_MIN_X) for px, _ in content]
    cys = [(py / SCALE + VIEWBOX_MIN_Y) for _, py in content]
    info = {
        "w_px": w_px,
        "h_px": h_px,
        "content_vb": (
            round(min(cxs), 1),
            round(min(cys), 1),
            round(max(cxs), 1),
            round(max(cys), 1),
        ),
        "regions": len(regions),
        "props": len(geo.get("props", []) or []),
    }
    return img, info


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    args = sys.argv[1:]
    if "--map" in args:
        map_id = args[args.index("--map") + 1]
        map_ids = [map_id]
    else:
        map_ids = sorted(p.stem for p in GEO_DIR.glob("*.yaml"))

    print(
        "guide->viewer transform: "
        f"viewBox=({VIEWBOX_MIN_X},{VIEWBOX_MIN_Y},{VIEWBOX_W},{VIEWBOX_H}) "
        f"scale={SCALE}px/unit  place <image> x={VIEWBOX_MIN_X} y={VIEWBOX_MIN_Y} "
        f"w={VIEWBOX_W} h={VIEWBOX_H} preserveAspectRatio=none"
    )
    for map_id in map_ids:
        img, info = render(map_id)
        path = OUT_DIR / f"{map_id}.png"
        img.save(path)
        cvb = info["content_vb"]
        print(
            f"wrote {path}  {info['w_px']}x{info['h_px']}px  "
            f"regions={info['regions']} props={info['props']}  "
            f"content_vb=[{cvb[0]},{cvb[1]} .. {cvb[2]},{cvb[3]}]"
        )


if __name__ == "__main__":
    main()
