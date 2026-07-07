"""Golden-file gate: the canonical seeded match must produce a
byte-identical event log across code changes.

This is stronger than the run-twice determinism test — it catches
*unintentional* behavior drift between commits, not just nondeterminism
within one. If you changed the engine on purpose, re-bless with
`python scripts/regen_golden.py` and commit the updated fixture; the diff
in event_count/sha256 is the review artifact.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from esports_sim.registry import load_all
from esports_sim.sim import simulate_match

GOLDEN_PATH = Path(__file__).parent / "golden" / "match_haven_42.json"


def test_golden_match_log_unchanged() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    gd = load_all()
    events = simulate_match(
        gd, golden["team_a"], golden["team_b"], golden["map_id"], golden["seed"]
    )
    blob = "\n".join(e.model_dump_json() for e in events).encode("utf-8")
    assert len(events) == golden["event_count"] and (
        hashlib.sha256(blob).hexdigest() == golden["sha256"]
    ), (
        f"Match log drifted from golden fixture "
        f"(events: {len(events)} vs {golden['event_count']}). "
        f"If this change is intentional, re-bless: "
        f"{sys.executable} scripts/regen_golden.py"
    )
