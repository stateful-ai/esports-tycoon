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
SWEEP_PATH = Path(__file__).parent / "golden" / "sweep_neutral.json"


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


def test_golden_sweep_unchanged() -> None:
    """Aggregate drift gate over the whole map pool x many neutral seeds.

    The single-match golden pins one log in detail but is blind to changes
    that miss that specific seed (the off-site carrier stall fix was one
    such neutral-behaviour change). This pins the combined SHA of every
    map x seeds 0..N with default tactics, so broad neutral drift trips a
    gate even when haven/42 is unaffected."""
    sweep = json.loads(SWEEP_PATH.read_text(encoding="utf-8"))
    gd = load_all()
    # The fixture must cover the whole current map pool — otherwise a newly
    # added map would silently escape the drift gate until re-blessed.
    assert sweep["maps"] == sorted(gd.maps), (
        f"sweep fixture covers {sweep['maps']} but the registry has "
        f"{sorted(gd.maps)}. Re-bless: {sys.executable} scripts/regen_golden.py"
    )
    h = hashlib.sha256()
    total = 0
    for map_id in sweep["maps"]:
        for seed in range(sweep["seeds"]):
            events = simulate_match(
                gd, sweep["team_a"], sweep["team_b"], map_id, seed
            )
            total += len(events)
            h.update("\n".join(e.model_dump_json() for e in events).encode("utf-8"))
            h.update(b"\x00")
    assert total == sweep["event_count_total"] and (
        h.hexdigest() == sweep["sha256"]
    ), (
        f"Neutral sweep drifted (events: {total} vs "
        f"{sweep['event_count_total']}). If intentional, re-bless: "
        f"{sys.executable} scripts/regen_golden.py"
    )
