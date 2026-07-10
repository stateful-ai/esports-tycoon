"""Personality axes — the continuous layer under the personality tags.

The GDD's Track A asks for personality "beyond the current tag-based
model". Tags stay (they're the display language and the save format);
underneath, every player gets five numeric axes (0-100, 50 = neutral)
DERIVED deterministically from their id and tags — a pure function, so
there is nothing to store, nothing to migrate, and every consumer reads
the same values forever.

Axes:
- ego           — appetite for the spotlight; friction in shared roles
- resilience    — how well criticism/pressure lands (talk challenges)
- sociability   — how fast bonds form (relationship affinity)
- professionalism — routine, prep, veteran steadiness
- ambition      — drive; responds to goals and big stages

Consumers scale by (axis - 50) / 50 so a neutral player is an exact
no-op — the same discipline the coaching dials follow (ADR-007), applied
at the campaign layer.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from esports_sim.schemas import Player

AXES = ("ego", "resilience", "sociability", "professionalism", "ambition")

# How tags shade the axes: tag -> {axis: delta}. Derived FROM the tags so
# existing players keep their established character.
_TAG_SHIFTS: dict[str, dict[str, float]] = {
    "hot_head": {"ego": +12.0, "resilience": -15.0},
    "volatile": {"resilience": -12.0, "professionalism": -6.0},
    "perfectionist": {"professionalism": +10.0, "resilience": -8.0},
    "calm": {"resilience": +12.0},
    "veteran": {"professionalism": +12.0, "ego": -4.0},
    "reliable": {"professionalism": +8.0, "resilience": +5.0},
    "team_player": {"sociability": +12.0, "ego": -8.0},
    "star_player": {"ego": +14.0, "ambition": +8.0},
    "rookie": {"ambition": +8.0, "professionalism": -5.0},
    "underrated": {"ambition": +6.0, "ego": -5.0},
    "grinder": {"professionalism": +8.0, "ambition": +6.0},
    "showman": {"ego": +10.0, "sociability": +8.0},
    "quiet": {"sociability": -12.0},
    "leader": {"sociability": +6.0, "professionalism": +6.0},
}


@lru_cache(maxsize=4096)
def _axes_cached(pid: str, tags: tuple[str, ...]) -> dict[str, float]:
    out: dict[str, float] = {}
    for axis in AXES:
        digest = hashlib.blake2b(
            f"personality|{pid}|{axis}".encode("utf-8"), digest_size=4
        ).digest()
        # Base jitter in [35, 65] — character without caricature.
        base = 35.0 + (int.from_bytes(digest, "big") % 3001) / 100.0
        out[axis] = base
    for tag in tags:
        for axis, delta in _TAG_SHIFTS.get(tag, {}).items():
            out[axis] += delta
    return {a: round(min(95.0, max(5.0, v)), 1) for a, v in out.items()}


def axes(p: Player) -> dict[str, float]:
    """A player's personality axes — pure and deterministic."""
    return dict(_axes_cached(p.id, tuple(sorted(p.personality_tags))))


def dev(p: Player, axis: str) -> float:
    """Signed deviation from neutral in [-1, 1] (exact 0.0 at 50)."""
    return (axes(p)[axis] - 50.0) / 50.0
