"""Geometry invariants: every playable map's floor plan must be usable
by the viewer (rooms for every callout, movement paths for every edge)."""

from __future__ import annotations

import pytest

from esports_sim.registry import GameData
from esports_sim.registry.loader import load_geometry


@pytest.mark.parametrize("map_id", ["haven", "ascent", "bind", "lotus", "split"])
def test_geometry_covers_map(game_data: GameData, map_id: str) -> None:
    geo = load_geometry(map_id)
    assert geo is not None, f"{map_id} has no geometry file"
    m = game_data.maps[map_id]

    # Every callout has a room, and the room holds its anchor point
    # (generously padded — anchors are display hints, not truth).
    for cid, c in m.callouts.items():
        assert cid in geo.regions, f"{map_id}: no region for {cid}"
        assert geo.regions[cid].contains(c.x, c.y, pad=8.0), (
            f"{map_id}: region for {cid} is nowhere near its anchor"
        )

    # No stray regions for callouts that don't exist.
    for rid in geo.regions:
        assert rid in m.callouts, f"{map_id}: region {rid} has no callout"

    # Every adjacency hop yields a movement path with a door: either the
    # rects (nearly) touch or a corridor provides waypoints.
    for a, nbrs in m.adjacency.items():
        for b in nbrs:
            pts = geo.path(a, b)
            assert len(pts) >= 2, f"{map_id}: no path {a}->{b}"
            assert len(pts) >= 3, (
                f"{map_id}: {a}->{b} rects neither touch (within tolerance) "
                f"nor have a corridor — movement would clip through walls"
            )

    # Rooms stay on the board.
    for cid, r in geo.regions.items():
        assert -5 <= r.x and r.x + r.w <= 105, f"{map_id}: {cid} off-grid x"
        assert -5 <= r.y and r.y + r.h <= 105, f"{map_id}: {cid} off-grid y"


def test_hop_and_sight_distances_positive(game_data: GameData) -> None:
    geo = load_geometry("haven")
    assert geo is not None
    m = game_data.maps["haven"]
    for a, nbrs in m.adjacency.items():
        for b in nbrs:
            assert geo.hop_distance(a, b) > 0
    for sl in m.sightlines:
        assert geo.sight_distance(sl.from_callout, sl.to_callout) > 0
