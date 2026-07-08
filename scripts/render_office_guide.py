"""Rasterize the HQ floor plan into img2img GUIDE images for Scenario.

The blockout→beautify pipeline: office_plan.json is the single source of
truth; this script draws it flat (floors, walls, furniture blocks in
semantic colors) and Scenario repaints it with structure preserved — so
the painted art matches the interactive geometry pixel-for-pixel and the
office.js polygon hotspots stay exact.

Outputs (assets/office/guides/):
    base.png                     — shell rooms only, annex slots bare
    <annex>_l1.png / _l3.png     — full scene with that annex furnished

Usage:
    .venv-win\\Scripts\\python.exe scripts\\render_office_guide.py
Requires Pillow (in the [dev] extras).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "src" / "esports_sim" / "web" / "static" / "office_plan.json"
OUT_DIR = ROOT / "assets" / "office" / "guides"

# Semantic guide palette (flat, high-contrast — gives the model clean
# structure to hang detail on). Dark navy world, per-type furniture hues.
GROUND = (13, 15, 24)
FLOOR = (52, 58, 78)
FLOOR_EDGE = (110, 118, 148)
WALL_FACE = (24, 26, 38)
WALL_CROWN = (150, 158, 190)
FURN = {
    "desk": (88, 96, 122),
    "screen": (121, 224, 255),
    "bigscreen": (139, 233, 255),
    "table": (98, 84, 60),
    "chair": (70, 76, 96),
    "couch": (122, 74, 92),
    "shelf": (96, 96, 112),
    "board": (223, 230, 242),
    "bench": (86, 122, 106),
    "cabinet": (100, 112, 130),
    "server": (63, 143, 122),
    "camera": (200, 206, 222),
    "pod": (150, 84, 108),
}
DARKEN = 0.55  # side-face multiplier


def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


class GuideRenderer:
    def __init__(self, plan: dict):
        self.plan = plan
        self.scale = plan["render"]["scale"]
        self.wall_h = plan["render"]["wall_h"]
        rooms = plan["rooms"] + plan["annexes"]
        pts = [
            p
            for r in rooms
            for p in self.corners(r)
        ]
        pad = plan["render"]["pad"]
        self.min_x = min(p[0] for p in pts) - pad
        self.min_y = min(p[1] for p in pts) - pad
        self.w = int((max(p[0] for p in pts) - self.min_x + pad) * self.scale)
        self.h = int(
            (max(p[1] for p in pts) - self.min_y + pad + self.wall_h + 4) * self.scale
        )

    # Same projection as office.js: oiso(x, -y).
    def iso(self, x: float, y: float) -> tuple[float, float]:
        ix, iy = x + y, (x - y) / 2.0
        return ((ix - self.min_x) * self.scale, (iy - self.min_y) * self.scale)

    def corners(self, r: dict) -> list[tuple[float, float]]:
        raw = [
            (r["x"], r["y"]), (r["x"] + r["w"], r["y"]),
            (r["x"] + r["w"], r["y"] + r["h"]), (r["x"], r["y"] + r["h"]),
        ]
        out = []
        for x, y in raw:
            ix, iy = x + y, (x - y) / 2.0
            out.append((ix, iy))
        return out

    def project(self, r: dict) -> list[tuple[float, float]]:
        return [
            ((ix - self.min_x) * self.scale, (iy - self.min_y) * self.scale)
            for ix, iy in self.corners(r)
        ]

    def box(self, d: ImageDraw.ImageDraw, room: dict, f: dict) -> None:
        """Furniture box in room-local coords, three faces like isoBox."""
        x, y = room["x"] + f["x"], room["y"] + f["y"]
        w, dd, h = f["w"], f["d"], f["h"] * self.scale
        cs = [
            self.iso(x, y), self.iso(x + w, y),
            self.iso(x + w, y + dd), self.iso(x, y + dd),
        ]
        color = FURN.get(f["type"], (128, 128, 128))
        dark = tuple(int(c * DARKEN) for c in color)
        mid = tuple(int(c * (DARKEN + 0.2)) for c in color)
        lift = lambda p: (p[0], p[1] - h)  # noqa: E731
        d.polygon([cs[3], cs[0], lift(cs[0]), lift(cs[3])], fill=dark)
        d.polygon([cs[0], cs[1], lift(cs[1]), lift(cs[0])], fill=mid)
        d.polygon([lift(p) for p in cs], fill=color)

    def render(
        self, annex_levels: dict[str, int], furniture: bool = True
    ) -> Image.Image:
        """annex_levels: annex id -> level (0 = absent)."""
        img = Image.new("RGB", (self.w, self.h), GROUND)
        d = ImageDraw.Draw(img)
        rooms = list(self.plan["rooms"]) + [
            a for a in self.plan["annexes"] if annex_levels.get(a["id"], 0) > 0
        ]
        # Back-to-front by max screen y.
        rooms.sort(key=lambda r: max(p[1] for p in self.project(r)))

        # Floors: no outlines (lines teach the model to paint lines);
        # rooms are distinguished by alternating close tones instead, so
        # the model sees zones without inheriting borders.
        floor_tones = [(52, 58, 78), (58, 63, 82), (48, 55, 74)]
        for i, r in enumerate(rooms):
            d.polygon(self.project(r), fill=floor_tones[i % 3])

        # Exterior walls: cheap version for the guide — extrude the two
        # viewer-facing edges (front y=min side, right x=max side) of the
        # building's outline by drawing every room's front/right edge that
        # has no neighbor across it.
        def has_neighbor(r, edge):
            for o in rooms:
                if o is r:
                    continue
                if edge == "front" and o["y"] + o["h"] == r["y"] and o["x"] < r["x"] + r["w"] and o["x"] + o["w"] > r["x"]:
                    return True
                if edge == "right" and o["x"] == r["x"] + r["w"] and o["y"] < r["y"] + r["h"] and o["y"] + o["h"] > r["y"]:
                    return True
            return False

        # NOTE (art-pipeline rule): no interior boundary LINES in guides —
        # the runtime draws authoritative borders as a vector overlay, and
        # lines in the guide teach the model to paint (drifting) lines.
        # Exterior walls keep their solid faces so the plinth reads 3D.
        wall_px = self.wall_h * self.scale
        for r in rooms:
            p = self.project(r)
            if not has_neighbor(r, "front"):
                d.polygon(
                    [p[0], p[1], (p[1][0], p[1][1] + wall_px), (p[0][0], p[0][1] + wall_px)],
                    fill=WALL_FACE,
                )
            if not has_neighbor(r, "right"):
                d.polygon(
                    [p[1], p[2], (p[2][0], p[2][1] + wall_px), (p[1][0], p[1][1] + wall_px)],
                    fill=WALL_FACE,
                )

        # Furniture (skipped for sprite-mode shell guides).
        if furniture:
            for r in rooms:
                furn = r.get("furniture")
                if furn is None and "furniture_by_level" in r:
                    level = annex_levels.get(r["id"], 0)
                    key = "3" if level >= 3 else "1"
                    furn = r["furniture_by_level"].get(key, [])
                for f in furn or []:
                    self.box(d, r, f)
        return img


def main() -> None:
    plan = load_plan()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rend = GuideRenderer(plan)

    if "--shell" in sys.argv:
        # Sprite-mode shell guide: EVERY room + annex floor, NO furniture.
        # The runtime clips unbuilt annex floors away and places furniture
        # as individual sprites, so the shell is one furniture-free image.
        img = rend.render(
            {a["id"]: 1 for a in plan["annexes"]}, furniture=False
        )
        path = OUT_DIR / "shell.png"
        img.save(path)
        print(f"wrote {path} ({rend.w}x{rend.h})")
        return

    rend.render({}).save(OUT_DIR / "base.png")
    print(f"wrote {OUT_DIR / 'base.png'} ({rend.w}x{rend.h})")
    for annex in plan["annexes"]:
        for level, tag in ((1, "l1"), (3, "l3")):
            img = rend.render({annex["id"]: level})
            path = OUT_DIR / f"{annex['id']}_{tag}.png"
            img.save(path)
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
