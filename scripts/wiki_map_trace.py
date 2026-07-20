"""Wiki-minimap tracing toolkit for geometry rebuilds.

Turns a wiki minimap screenshot into gridded reference images in the
canonical map frame (attackers at low y, defenders at high y, A site
left, B site right), and overlays authored geometry back onto the source
for one-for-one verification. Used by the /trace-map skill.

Subcommands (all paths positional):
  grid <in.png> <out.png> [--rotate ccw|cw|180|flipv|transpose|none]
      Crop to the walkable floor, rotate into the canonical frame, and
      draw a 0-100 unit grid (5u minor / 10u major, labeled). Also
      writes <out>_clean.png (the ungridded canonical crop) plus a
      sidecar <out>.json holding the crop box and units-per-pixel so
      later subcommands stay in register.
  zoom <out.png> <name,x0,y0,x1,y1> [...]
      Cut labeled fine-grid (2u) windows from the clean canonical crop
      for close reading. Coordinates in map units.
  overlay <geometry.yaml> <out.png> <check.png>
      Draw the authored region rects (blue), half props (green) and
      full props (red) over the canonical crop to verify registration.

The long image axis spans 100 units; the short axis keeps the same
scale, so shapes stay true. ASCII-only output (cp1252 consoles).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont


def _font(size: int = 20):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _is_floor(r: int, g: int, b: int) -> bool:
    """Floor pixels are grey/olive; background is near-black, UI is
    saturated red, and gimmick indicators (teleporter paths, door arcs)
    are saturated teal/green lines that can sweep far off the floor."""
    if r > 180 and g < 90 and b < 90:
        return False
    if g > r + 80:  # teal/green overlay lines; grey and olive keep g ~ r
        return False
    return (r + g + b) > 180


def cmd_grid(args: argparse.Namespace) -> None:
    im = Image.open(args.src).convert("RGB")
    px = im.load()
    w, h = im.size
    pts = [
        (x, y)
        for y in range(0, h, 2)
        for x in range(0, w, 2)
        if _is_floor(*px[x, y])
        # Ignore wiki UI chrome hugging the right edge.
        and not (x > w - 90 and (y < 90 or y > h - 220))
    ]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = 12
    x0, y0 = max(0, min(xs) - pad), max(0, min(ys) - pad)
    x1, y1 = min(w - 1, max(xs) + pad), min(h - 1, max(ys) + pad)
    crop = im.crop((x0, y0, x1 + 1, y1 + 1))
    if args.rotate == "ccw":
        crop = crop.rotate(90, expand=True)
    elif args.rotate == "cw":
        crop = crop.rotate(-90, expand=True)
    elif args.rotate == "180":
        crop = crop.rotate(180)
    elif args.rotate == "flipv":
        # Vertical mirror: for sources already in broadcast orientation
        # (attackers at the bottom, A left) — flipping y lands attackers
        # at low y while keeping A on the left. Shapes stay true; the
        # map's chirality mirrors, which the viewer never exposes.
        crop = crop.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    elif args.rotate == "transpose":
        # Main-diagonal reflection (x<->y swap): for sources with the
        # attacker spawn WEST and the A-most site NORTH — lands
        # attackers at low y with that site on the left. Mirrors
        # chirality like flipv.
        crop = crop.transpose(Image.Transpose.TRANSPOSE)
    cw, ch = crop.size
    upp = 100.0 / max(cw, ch)
    out = Path(args.out)
    clean = out.with_name(out.stem + "_clean.png")
    crop.save(clean)
    meta = {
        "crop": [x0, y0, x1, y1],
        "rotate": args.rotate,
        "units_per_pixel": upp,
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))

    scale = 2
    big = crop.resize((cw * scale, ch * scale), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    font = _font(22)
    u = 0
    while u * scale / upp <= max(big.size):
        p = u / upp * scale
        major = u % 10 == 0
        col = (255, 90, 90) if major else (90, 200, 90)
        if p <= big.size[0]:
            d.line([(p, 0), (p, big.size[1])], fill=col, width=2 if major else 1)
            if major:
                d.text((p + 3, 3), str(u), fill=(255, 220, 100), font=font)
        if p <= big.size[1]:
            d.line([(0, p), (big.size[0], p)], fill=col, width=2 if major else 1)
            if major:
                d.text((3, p + 3), str(u), fill=(255, 220, 100), font=font)
        u += 5
    big.save(out)
    print(f"crop box: x {x0}..{x1}, y {y0}..{y1}  size {cw}x{ch}")
    print(f"units per pixel: {upp:.4f}; x spans {cw*upp:.1f}u, y spans {ch*upp:.1f}u")
    print(f"wrote {out} and {clean}")


def _load_meta(gridded: Path) -> float:
    meta = json.loads(gridded.with_suffix(".json").read_text())
    return meta["units_per_pixel"]


def cmd_zoom(args: argparse.Namespace) -> None:
    out = Path(args.gridded)
    upp = _load_meta(out)
    clean = out.with_name(out.stem + "_clean.png")
    im = Image.open(clean)
    z = 4
    font = _font(20)
    for spec in args.windows:
        name, u0, v0, u1, v1 = spec.split(",")
        u0, v0, u1, v1 = float(u0), float(v0), float(u1), float(v1)
        box = (
            int(u0 / upp), int(v0 / upp),
            min(im.size[0], int(u1 / upp)), min(im.size[1], int(v1 / upp)),
        )
        crop = im.crop(box).convert("RGB")
        crop = crop.resize((crop.size[0] * z, crop.size[1] * z), Image.LANCZOS)
        d = ImageDraw.Draw(crop)
        ppu = z / upp
        u = int(u0) - int(u0) % 2
        while u <= u1:
            p = (u - u0) * ppu
            if p >= 0:
                major = u % 10 == 0
                col = (255, 80, 80) if major else (70, 190, 70)
                d.line([(p, 0), (p, crop.size[1])], fill=col, width=2 if major else 1)
                if major:
                    d.text((p + 3, 3), str(u), fill=(255, 220, 100), font=font)
                    d.text(
                        (p + 3, crop.size[1] - 26), str(u),
                        fill=(255, 220, 100), font=font,
                    )
            u += 2
        v = int(v0) - int(v0) % 2
        while v <= v1:
            p = (v - v0) * ppu
            if p >= 0:
                major = v % 10 == 0
                col = (255, 80, 80) if major else (70, 190, 70)
                d.line([(0, p), (crop.size[0], p)], fill=col, width=2 if major else 1)
                if major:
                    d.text((3, p + 3), str(v), fill=(255, 220, 100), font=font)
                    d.text(
                        (crop.size[0] - 40, p + 3), str(v),
                        fill=(255, 220, 100), font=font,
                    )
            v += 2
        dst = out.with_name(out.stem + f"_{name}.png")
        crop.save(dst)
        print(f"wrote {dst}  units ({u0},{v0})..({u1},{v1})")


def cmd_overlay(args: argparse.Namespace) -> None:
    out = Path(args.gridded)
    upp = _load_meta(out)
    clean = out.with_name(out.stem + "_clean.png")
    geo = yaml.safe_load(Path(args.geometry).read_text(encoding="utf-8"))
    im = Image.open(clean).convert("RGB")
    z = 2
    im = im.resize((im.size[0] * z, im.size[1] * z), Image.LANCZOS)
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    ppu = z / upp
    font = _font(20)
    for name, r in geo["regions"].items():
        box = [
            r["x"] * ppu, r["y"] * ppu,
            (r["x"] + r["w"]) * ppu, (r["y"] + r["h"]) * ppu,
        ]
        d.rectangle(box, fill=(60, 160, 255, 45), outline=(80, 200, 255, 220), width=3)
        d.text((box[0] + 5, box[1] + 4), name, fill=(255, 240, 120, 255), font=font)
    for p in geo.get("props", []):
        box = [
            p["x"] * ppu, p["y"] * ppu,
            (p["x"] + p["w"]) * ppu, (p["y"] + p["h"]) * ppu,
        ]
        full = p.get("height", "half") == "full"
        col = (255, 90, 90, 130) if full else (120, 255, 120, 130)
        d.rectangle(box, fill=col, outline=col, width=2)
    Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB").save(args.check)
    print(f"wrote {args.check}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid")
    g.add_argument("src")
    g.add_argument("out")
    g.add_argument(
        "--rotate",
        choices=["ccw", "cw", "180", "flipv", "transpose", "none"],
        default="ccw",
    )
    g.set_defaults(fn=cmd_grid)
    zp = sub.add_parser("zoom")
    zp.add_argument("gridded")
    zp.add_argument("windows", nargs="+")
    zp.set_defaults(fn=cmd_zoom)
    o = sub.add_parser("overlay")
    o.add_argument("geometry")
    o.add_argument("gridded")
    o.add_argument("check")
    o.set_defaults(fn=cmd_overlay)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
