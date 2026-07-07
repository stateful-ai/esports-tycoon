"""North-star determinism test.

The single invariant the whole project hangs on: run the same match with
the same seed, twice — the event logs are byte-identical.
"""

from __future__ import annotations

from esports_sim.registry import load_all
from esports_sim.sim import simulate_match


def test_match_determinism_identical_seed_identical_events() -> None:
    gd_a = load_all()
    gd_b = load_all()  # fresh load: no shared mutable state between runs
    events_a = simulate_match(
        gd_a, team_a="team_nexus", team_b="team_vanguard", map_id="haven", seed=42
    )
    events_b = simulate_match(
        gd_b, team_a="team_nexus", team_b="team_vanguard", map_id="haven", seed=42
    )
    assert [e.model_dump_json() for e in events_a] == [
        e.model_dump_json() for e in events_b
    ]


def test_different_seeds_differ() -> None:
    gd = load_all()
    events_a = simulate_match(
        gd, team_a="team_nexus", team_b="team_vanguard", map_id="haven", seed=1
    )
    events_b = simulate_match(
        gd, team_a="team_nexus", team_b="team_vanguard", map_id="haven", seed=2
    )
    assert [e.model_dump_json() for e in events_a] != [
        e.model_dump_json() for e in events_b
    ]
