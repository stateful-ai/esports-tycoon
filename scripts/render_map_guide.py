"""Rasterize match-map geometry into img2img GUIDE images for the paint pass.

Thin wrapper importing the logic from src/esports_sim/registry/map_guide_renderer.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import yaml

from esports_sim.schemas.map import Map
from esports_sim.schemas.geometry import MapGeometry
from esports_sim.registry.map_guide_renderer import (
    render_legacy_guide,
    VIEWBOX_MIN_X,
    VIEWBOX_MIN_Y,
    VIEWBOX_W,
    VIEWBOX_H,
    SCALE,
)

ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "data" / "maps" / "geometry"
MAP_DIR = ROOT / "data" / "maps"
OUT_DIR = ROOT / "assets" / "maps" / "guides"


def load_map_legacy(map_id: str) -> tuple[Map, MapGeometry]:
    geo_raw = yaml.safe_load((GEO_DIR / f"{map_id}.yaml").read_text(encoding="utf-8"))
    map_raw = yaml.safe_load((MAP_DIR / f"{map_id}.yaml").read_text(encoding="utf-8"))
    return Map(**map_raw), MapGeometry(**geo_raw)


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
        try:
            m, geo = load_map_legacy(map_id)
        except FileNotFoundError:
            print(f"{map_id:8s} legacy files missing -- skipped")
            continue
        img, info = render_legacy_guide(m, geo)
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
