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

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "tests" / "golden"
GOLDEN_PATH = GOLDEN_DIR / "match_haven_42.json"
# A broad sweep (every map x many seeds) with default tactics. The single
# match above pins one canonical log in fine detail; this pins the AGGREGATE
# behaviour across the whole map pool, so a neutral-behaviour change that
# happens to miss haven/42 (e.g. the off-site carrier stall fix) still trips
# a gate instead of slipping through the single-match blind spot.
SWEEP_PATH = GOLDEN_DIR / "sweep_neutral.json"

TEAM_A = "team_nexus"
TEAM_B = "team_vanguard"
MAP_ID = "haven"
SEED = 42
SWEEP_SEEDS = 10  # seeds 0..9 per map


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


def compute_sweep() -> dict:
    gd = load_all()
    h = hashlib.sha256()
    total_events = 0
    maps = sorted(gd.maps)
    for map_id in maps:
        for seed in range(SWEEP_SEEDS):
            events = simulate_match(gd, TEAM_A, TEAM_B, map_id, seed)
            total_events += len(events)
            h.update(canonical_log_bytes(events))
            h.update(b"\x00")  # match separator
    return {
        "team_a": TEAM_A,
        "team_b": TEAM_B,
        "maps": maps,
        "seeds": SWEEP_SEEDS,
        "n_matches": len(maps) * SWEEP_SEEDS,
        "event_count_total": total_events,
        "sha256": h.hexdigest(),
    }


if __name__ == "__main__":
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    golden = compute()
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2) + "\n", encoding="utf-8")
    print(f"blessed {GOLDEN_PATH}")
    print(json.dumps(golden, indent=2))
    sweep = compute_sweep()
    SWEEP_PATH.write_text(json.dumps(sweep, indent=2) + "\n", encoding="utf-8")
    print(f"blessed {SWEEP_PATH}")
    print(json.dumps(sweep, indent=2))
