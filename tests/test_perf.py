"""Performance observability sink: write-only, bounded, sim-inert."""

from __future__ import annotations

from esports_sim import perf
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.registry import GameData


def test_sink_records_spans_and_ticks() -> None:
    perf.reset()
    with perf.span("unit.test"):
        pass
    perf.record("unit.test", 5.0)
    perf.gauge("unit.gauge", 42)
    perf.record_tick({"season": 1, "week": 1, "total_ms": 9.0,
                      "phases": {"a": 9.0}, "sizes": {"players": 5}})
    snap = perf.snapshot()
    agg = snap["spans"]["unit.test"]
    assert agg["count"] == 2 and agg["max_ms"] >= 5.0
    assert snap["gauges"]["unit.gauge"] == 42
    assert snap["ticks"][-1]["week"] == 1
    perf.reset()
    assert perf.snapshot() == {"spans": {}, "gauges": {}, "ticks": []}


def test_advance_week_records_a_tick_breakdown(game_data: GameData) -> None:
    """Every advance_week leaves one tick entry: phase timings that sum
    close to the total, plus the state-size gauges. The sink is write-only
    — the same seed still produces the same GameState (nothing in the sim
    reads a timing)."""
    perf.reset()
    gs = new_campaign(game_data, seed=31)
    advance_week(gs, game_data)
    snap = perf.snapshot()
    assert len(snap["ticks"]) == 1
    t = snap["ticks"][0]
    assert t["season"] == 1 and t["week"] == 1
    assert t["total_ms"] > 0
    assert "matches" in t["phases"] and "inbox" in t["phases"]
    # Phases account for (almost) all of the total — nothing big untimed.
    assert sum(t["phases"].values()) >= t["total_ms"] * 0.95
    assert t["sizes"]["players"] == len(gs.players)
    assert t["sizes"]["fixtures"] == len(gs.fixtures)
    assert snap["spans"]["tick.total"]["count"] == 1
    perf.reset()
