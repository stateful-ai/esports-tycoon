"""Derive square map thumbnails from the painted viewer backdrops.

The old thumbnails (assets/maps/<map>.webp) were standalone Ludo art
that clashes with the painted backdrops. This crops each painted map to
its content and squares it, so every thumbnail is literally a view of
the map the player will watch. Content bbox comes from the GUIDE (same
transform as the paint): everything brighter than the ground color.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\render_map_thumbs.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "assets" / "maps" / "guides"
PAINTED = ROOT / "assets" / "maps" / "painted"
OUT = ROOT / "assets" / "maps"

GROUND = (9, 11, 17)  # render_map_guide.py's void color
THUMB = 320
PAD = 24  # px of breathing room around the content


def content_bbox(guide: Image.Image) -> tuple[int, int, int, int]:
    a = np.asarray(guide.convert("RGB"), dtype=np.int16)
    diff = np.abs(a - np.array(GROUND, dtype=np.int16)).sum(axis=2)
    mask = diff > 24
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def main() -> None:
    for gpath in sorted(GUIDES.glob("*.png")):
        name = gpath.stem
        ppath = PAINTED / f"{name}.webp"
        if not ppath.exists():
            print(f"skip {name}: no painted backdrop")
            continue
        guide = Image.open(gpath)
        paint = Image.open(ppath).convert("RGB")
        x0, y0, x1, y1 = content_bbox(guide)
        x0 = max(0, x0 - PAD)
        y0 = max(0, y0 - PAD)
        x1 = min(paint.width, x1 + PAD)
        y1 = min(paint.height, y1 + PAD)
        crop = paint.crop((x0, y0, x1, y1))
        # Square canvas in the void color, content centered.
        side = max(crop.width, crop.height)
        sq = Image.new("RGB", (side, side), GROUND)
        sq.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
        sq = sq.resize((THUMB, THUMB), Image.LANCZOS)
        out = OUT / f"{name}.webp"
        sq.save(out, quality=88)
        print(f"wrote {out} (bbox {x0},{y0}..{x1},{y1})")


if __name__ == "__main__":
    main()
