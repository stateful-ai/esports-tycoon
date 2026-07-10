"""CLI wrapper: rebuild a roster pack's `teams/*.yaml` from its `src/` sheets.

Usage: python scripts/build_roster_pack.py vct-2026

The actual expansion logic lives in
`esports_sim.registry.roster_pack_builder` (also used by the web admin-edit
toggle to rebuild a pack after a single player/team correction), so this
script and the in-app editor can never drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from esports_sim.registry.roster_pack_builder import build  # noqa: E402

if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "vct-2026")
