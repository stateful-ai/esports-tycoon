"""Viewer static-file contracts.

The replay viewer's spectator camera (zoom/pan/follow) is a pure
presentation transform layered OVER the guide->viewer transform contract:
viewer.js's ISO_VIEWBOX and the pinned painted-backdrop <image> placement
must stay byte-aligned with scripts/render_map_guide.py's rasterizer
(registry/map_guide_renderer.py), or paint and positions shear apart.
These tests pin that contract plus the control ids viewer.js binds to,
so a markup or camera refactor can't silently drift either side.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "esports_sim" / "web" / "static"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_iso_viewbox_matches_guide_renderer() -> None:
    from esports_sim.registry.map_guide_renderer import (
        VIEWBOX_H,
        VIEWBOX_MIN_X,
        VIEWBOX_MIN_Y,
        VIEWBOX_W,
    )

    src = _read("viewer.js")
    m = re.search(r"const ISO_VIEWBOX = \[([^\]]+)\];", src)
    assert m, "viewer.js must declare ISO_VIEWBOX"
    nums = [float(x) for x in m.group(1).split(",")]
    assert nums == [VIEWBOX_MIN_X, VIEWBOX_MIN_Y, VIEWBOX_W, VIEWBOX_H]


def test_backdrop_image_stays_pinned_to_iso_viewbox() -> None:
    src = _read("viewer.js")
    # The painted backdrop <image> is placed at the exact ISO_VIEWBOX coords
    # with preserveAspectRatio none; the spectator camera must transform the
    # whole scene group instead of moving this placement.
    assert "const [vx, vy, vw, vh] = ISO_VIEWBOX;" in src
    assert 'preserveAspectRatio: "none"' in src
    assert "V.camEl.appendChild(bg)" in src, (
        "backdrop must live inside the camera group so zoom/pan cannot "
        "shear paint away from geometry"
    )


def test_spectator_controls_exist_in_markup_and_script() -> None:
    html = _read("index.html")
    js = _read("viewer.js")
    for cid in ("v-sound", "v-evfollow", "v-reframe", "v-map"):
        assert f'id="{cid}"' in html, f"index.html must carry #{cid}"
        assert f'"{cid}"' in js, f"viewer.js must bind #{cid}"


def test_viewer_sound_is_muted_by_default_and_persisted() -> None:
    js = _read("viewer.js")
    assert 'const SFX_KEY = "es-viewer-sfx";' in js
    assert "let sfxOn = false;" in js, "viewer sound must default to muted"
    assert "localStorage.setItem(SFX_KEY" in js, "mute toggle must persist"
    # Synthesized only: no <audio> elements or binary assets in the viewer.
    assert "new Audio(" not in js
