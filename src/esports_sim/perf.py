"""In-process performance observability.

A tiny sink for timings and size gauges at the app's hot points: the
weekly tick's phases (campaign.advance_week), save serialization
(web server), and per-endpoint latency (session middleware). Built to
answer ONE question cheaply: "why does advancing get slower the deeper a
save goes?" — the tick history pairs every tick's wall time with the
sizes of the append-only structures that grow with it.

HARD RULE: this module NEVER touches GameState and nothing in the sim
ever reads from it — timings are wall-clock, so a single write into
state (or a branch on a timing) would break determinism (invariant 1).
It is a pure write-only sink with bounded memory, reset on process
restart, exposed read-only via GET /api/perf.
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from typing import Iterator

_MAX_SAMPLES = 256  # per span name
_MAX_TICKS = 200  # tick-history entries (season-and-a-half of weeks)

# span name -> recent durations in ms (append-only ring)
_spans: dict[str, deque[float]] = {}
# one entry per advance_week call: {season, week, total_ms, phases, sizes}
_ticks: deque[dict] = deque(maxlen=_MAX_TICKS)
# gauge name -> latest value (sizes, byte counts)
_gauges: dict[str, float] = {}


def record(name: str, ms: float) -> None:
    _spans.setdefault(name, deque(maxlen=_MAX_SAMPLES)).append(float(ms))


def gauge(name: str, value: float) -> None:
    _gauges[name] = float(value)


def record_tick(entry: dict) -> None:
    """One advance_week's breakdown: phase timings + state-size gauges,
    keyed by (season, week) so slowdown-over-time reads directly."""
    _ticks.append(entry)


@contextmanager
def span(name: str) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        record(name, (time.perf_counter() - t0) * 1000.0)


class Checkpoints:
    """Sequential phase timer for one tick: `mark("phase")` records the
    time since the previous mark. Collects into a dict for record_tick."""

    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self._last = self._t0
        self.phases: dict[str, float] = {}

    def mark(self, phase: str) -> None:
        now = time.perf_counter()
        self.phases[phase] = round((now - self._last) * 1000.0, 2)
        self._last = now

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000.0, 2)


def _agg(samples: deque[float]) -> dict:
    n = len(samples)
    vals = sorted(samples)
    return {
        "count": n,
        "last_ms": round(samples[-1], 2),
        "mean_ms": round(sum(vals) / n, 2),
        "p95_ms": round(vals[min(n - 1, int(n * 0.95))], 2),
        "max_ms": round(vals[-1], 2),
    }


def snapshot() -> dict:
    """The read side for /api/perf: span aggregates, latest gauges, and
    the per-tick history (newest last, ready to plot ms over weeks)."""
    return {
        "spans": {name: _agg(s) for name, s in sorted(_spans.items()) if s},
        "gauges": dict(sorted(_gauges.items())),
        "ticks": list(_ticks),
    }


def reset() -> None:
    """Test hook: wipe the sink."""
    _spans.clear()
    _ticks.clear()
    _gauges.clear()
