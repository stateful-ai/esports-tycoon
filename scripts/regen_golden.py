"""Regenerate the golden match-log fixture.

The golden test (tests/test_golden.py) pins the SHA-256 of a canonical,
seeded match's event log. Any engine change that alters the log — even one
event field — fails CI until the fixture is re-blessed by running this
script and committing the diff. That makes every sim-behavior change an
explicit, reviewable decision instead of silent drift.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\regen_golden.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from esports_sim.registry import load_all
from esports_sim.sim import simulate_match

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "tests" / "golden" / "match_haven_42.json"

TEAM_A = "team_nexus"
TEAM_B = "team_vanguard"
MAP_ID = "haven"
SEED = 42


def canonical_log_bytes(events) -> bytes:
    return "\n".join(e.model_dump_json() for e in events).encode("utf-8")


def compute() -> dict:
    gd = load_all()
    events = simulate_match(gd, TEAM_A, TEAM_B, MAP_ID, SEED)
    blob = canonical_log_bytes(events)
    return {
        "team_a": TEAM_A,
        "team_b": TEAM_B,
        "map_id": MAP_ID,
        "seed": SEED,
        "event_count": len(events),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


if __name__ == "__main__":
    golden = compute()
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2) + "\n", encoding="utf-8")
    print(f"blessed {GOLDEN_PATH}")
    print(json.dumps(golden, indent=2))
