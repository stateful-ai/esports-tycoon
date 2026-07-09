"""Offline mirror of office.js sprite mode: shell + z-sorted sprites.

Reproduces officeSpriteEntries() placement math exactly (keep the two in
sync when tuning) so placement/scale changes can be judged from a PNG
without a browser — useful because preview screenshot capture is flaky.
Renders with all annexes built at L1.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\render_sprite_office.py [out.png]
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "esports_sim" / "web" / "static"
plan = json.loads((STATIC / "office_plan.json").read_text(encoding="utf-8"))
manifest = json.loads((STATIC / "office_sprites.json").read_text(encoding="utf-8"))
SPRITES = ROOT / "assets" / "office" / "sprites"

SCALE = plan["render"]["scale"]
PAD = plan["render"]["pad"]
WALL_H = plan["render"]["wall_h"]

rooms = plan["rooms"] + plan["annexes"]
pts = []
for r in rooms:
    for x, y in [(r["x"], r["y"]), (r["x"] + r["w"], r["y"]),
                 (r["x"] + r["w"], r["y"] + r["h"]), (r["x"], r["y"] + r["h"])]:
        pts.append((x + y, (x - y) / 2.0))
min_x = min(p[0] for p in pts) - PAD
min_y = min(p[1] for p in pts) - PAD

shell = Image.open(ROOT / "assets" / "office" / "painted" / "shell.webp").convert("RGBA")

entries = []
for r in rooms:
    furn = r.get("furniture")
    if furn is None and "furniture_by_level" in r:
        furn = r["furniture_by_level"]["1"]  # current save: all annexes L1
    for f in furn or []:
        spec = manifest["sprites"].get(f["type"])
        if not spec:
            continue
        auto = "sw" if (f["d"] > f["w"] and "sw" in spec["orientations"]) else spec["orientations"][0]
        o = f["o"] if f.get("o") in spec["orientations"] else auto
        x, y = r["x"] + f["x"], r["y"] + f["y"]
        entries.append({
            "key": f"{f['type']}_{o}",
            "w": (f["w"] + f["d"]) * spec.get("scale", 1) * f.get("s", 1),
            "cx": x + y + (f["w"] + f["d"]) / 2,
            "by": (x + f["w"] - y) / 2,
            "depth": x + f["w"] / 2 - (y + f["d"] / 2),
        })
entries.sort(key=lambda e: e["depth"])

for e in entries:
    sp = Image.open(SPRITES / f"{e['key']}.webp").convert("RGBA")
    w_px = int(e["w"] * SCALE)
    h_px = int(w_px * sp.height / sp.width)
    sp = sp.resize((w_px, h_px), Image.LANCZOS)
    px = int((e["cx"] - e["w"] / 2 - min_x) * SCALE)
    py = int((e["by"] + 0.5 - min_y) * SCALE) - h_px
    shell.alpha_composite(sp, (px, py))

out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "office" / "sprite_preview.png"
shell.convert("RGB").save(out)
print(f"wrote {out} ({shell.width}x{shell.height}, {len(entries)} sprites)")
