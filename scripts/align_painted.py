"""Align the painted office scenes to the guide geometry.

Generated art drifts a few percent in scale/position from the guide it
was painted over (the structure gate tolerates it; hover outlines do
not). The plan/guide is the source of truth, so this script warps the
ART: estimate a uniform-scale + translation transform from the building
masks of (guide base, painted base), then apply that ONE transform to
all painted files — they share the base's coordinate frame because annex
regions were composited onto the accepted base.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\align_painted.py           # dry run
    .venv-win\\Scripts\\python.exe scripts\\align_painted.py --apply   # overwrite
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "assets" / "office" / "guides"
PAINTED = ROOT / "assets" / "office" / "painted"

FILES = [
    "base",
    "analytics_suite_l1", "analytics_suite_l3",
    "marketing_office_l1", "marketing_office_l3",
    "training_center_l1", "training_center_l3",
]

MASK_THR = 34  # luminance above the near-black background
DOWN = 6  # estimate on a downscaled grid for speed


def building_mask(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    g = img.convert("L").resize(size, Image.BILINEAR)
    return np.asarray(g, dtype=np.uint8) > MASK_THR


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return inter / union if union else 0.0


def warp_mask(mask: np.ndarray, s: float, dx: float, dy: float) -> np.ndarray:
    """Scale around center + translate, on a small boolean grid."""
    h, w = mask.shape
    img = Image.fromarray((mask * 255).astype(np.uint8))
    sw, sh = max(1, round(w * s)), max(1, round(h * s))
    scaled = img.resize((sw, sh), Image.BILINEAR)
    canvas = Image.new("L", (w, h), 0)
    ox = round((w - sw) / 2 + dx)
    oy = round((h - sh) / 2 + dy)
    canvas.paste(scaled, (ox, oy))
    return np.asarray(canvas) > 127


def estimate(guide: Image.Image, painted: Image.Image) -> tuple[float, float, float, float, float]:
    w, h = guide.size
    size = (w // DOWN, h // DOWN)
    gm = building_mask(guide, size)
    pm = building_mask(painted, size)
    base_iou = iou(gm, pm)

    best = (1.0, 0.0, 0.0, base_iou)
    # Coarse → fine search over (scale, dx, dy) applied to the PAINTED mask.
    grids = [
        (np.arange(0.94, 1.061, 0.01), range(-8, 9, 2), range(-8, 9, 2)),
        (None, None, None),  # refined below from the coarse winner
    ]
    s0, dx0, dy0, _ = best
    for gi, (ss, xs, ys) in enumerate(grids):
        if gi == 1:
            s0, dx0, dy0, _ = best
            ss = np.arange(s0 - 0.008, s0 + 0.0081, 0.002)
            xs = range(int(dx0) - 2, int(dx0) + 3)
            ys = range(int(dy0) - 2, int(dy0) + 3)
        for s in ss:
            for dx in xs:
                for dy in ys:
                    v = iou(gm, warp_mask(pm, float(s), dx, dy))
                    if v > best[3]:
                        best = (float(s), float(dx), float(dy), v)
    s, dx, dy, refined_iou = best
    return s, dx * DOWN, dy * DOWN, base_iou, refined_iou


def apply_transform(path: Path, s: float, dx: float, dy: float) -> None:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    sw, sh = round(w * s), round(h * s)
    scaled = img.resize((sw, sh), Image.LANCZOS)
    # Sample the background color from a corner so exposed borders blend.
    bg = img.getpixel((4, 4))
    canvas = Image.new("RGB", (w, h), bg)
    canvas.paste(scaled, (round((w - sw) / 2 + dx), round((h - sh) / 2 + dy)))
    canvas.save(path, quality=85)


def main() -> None:
    apply = "--apply" in sys.argv
    guide = Image.open(GUIDES / "base.png")
    painted = Image.open(PAINTED / "base.webp")
    if guide.size != painted.size:
        painted = painted.resize(guide.size, Image.LANCZOS)
    s, dx, dy, before, after = estimate(guide, painted)
    print(f"estimated: scale={s:.3f} dx={dx:+.0f}px dy={dy:+.0f}px")
    print(f"building-mask IoU: {before:.3f} -> {after:.3f}")
    if after <= before + 0.005:
        print("no meaningful improvement available — leaving files untouched")
        return
    if not apply:
        print("dry run (pass --apply to overwrite the painted set)")
        return
    for name in FILES:
        p = PAINTED / f"{name}.webp"
        apply_transform(p, s, dx, dy)
        print(f"aligned {p.name}")


if __name__ == "__main__":
    main()
