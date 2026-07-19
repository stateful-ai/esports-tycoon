"""Doorway openings on region seams: portal placement + audit rules."""

from __future__ import annotations

from esports_sim.registry.loader import load_geometry, load_map
from esports_sim.registry.map_audit import audit_map
from esports_sim.schemas.geometry import MapGeometry, Opening, Region
from esports_sim.schemas.map import Callout, CalloutZone, Map, Site


def _geo(openings: list[Opening]) -> MapGeometry:
    """Two rooms side by side (vertical seam at x=10) and one stacked
    below the left room (horizontal seam at y=10)."""
    return MapGeometry(
        map_id="t",
        regions={
            "left": Region(x=0, y=0, w=10, h=10),
            "right": Region(x=10, y=0, w=10, h=10),
            "below": Region(x=0, y=10, w=10, h=10),
        },
        openings=openings,
    )


def _map() -> Map:
    def co(cid: str, x: float, y: float) -> Callout:
        return Callout(
            id=cid, display_name=cid, site=Site.NONE,
            zone=CalloutZone.MID, x=x, y=y,
        )

    return Map(
        id="t",
        display_name="t",
        sites=[],
        callouts={
            "left": co("left", 5, 5),
            "right": co("right", 15, 5),
            "below": co("below", 5, 15),
        },
        adjacency={
            "left": ["right", "below"],
            "right": ["left"],
            "below": ["left"],
        },
        attacker_spawn="left",
        defender_spawn="right",
    )


def test_portal_defaults_to_seam_midpoint():
    geo = _geo([])
    assert geo.portal("left", "right") == (10.0, 5.0)
    assert geo.portal("left", "below") == (5.0, 10.0)


def test_opening_moves_portal_to_doorway_center():
    geo = _geo([
        Opening(between=("left", "right"), span=(7.0, 9.0)),   # along y
        Opening(between=("below", "left"), span=(1.0, 2.0)),   # along x
    ])
    # Vertical seam: doorway span slides the portal along y.
    assert geo.portal("left", "right") == (10.0, 8.0)
    # Reversed lookup finds the same opening.
    assert geo.portal("right", "left") == (10.0, 8.0)
    # Horizontal seam: span slides along x.
    assert geo.portal("left", "below") == (1.5, 10.0)


def test_paths_route_through_the_doorway():
    geo = _geo([Opening(between=("left", "right"), span=(8.0, 10.0))])
    assert geo.path("left", "right") == [(5.0, 5.0), (10.0, 9.0), (15.0, 5.0)]


def test_audit_accepts_valid_openings():
    geo = _geo([Opening(between=("left", "right"), span=(2.0, 4.0))])
    assert audit_map(_map(), geo) == []


def test_audit_flags_bad_openings():
    geo = _geo([
        Opening(between=("left", "right"), span=(12.0, 14.0)),  # off seam
        Opening(between=("left", "ghost"), span=(1.0, 2.0)),    # no region
        Opening(between=("right", "below"), span=(1.0, 2.0)),   # not adjacent
        Opening(between=("below", "left"), span=(4.0, 3.0)),    # inverted
    ])
    findings = audit_map(_map(), geo)
    assert any("off the shared seam" in f for f in findings)
    assert any("missing region" in f for f in findings)
    assert any("non-adjacent pair" in f for f in findings)
    assert any("span inverted" in f for f in findings)


def test_audit_flags_duplicate_openings():
    geo = _geo([
        Opening(between=("left", "right"), span=(2.0, 4.0)),
        Opening(between=("right", "left"), span=(5.0, 6.0)),
    ])
    assert any("duplicate opening" in f for f in audit_map(_map(), geo))


def test_ascent_gimmick_doors_have_openings():
    """The mechanical doors must sit on declared doorway spans so the
    portal (and later the free-roam wall derivation) matches the door."""
    m = load_map("ascent")
    geo = load_geometry("ascent")
    for gim in m.gimmicks:
        assert geo.opening_for(*gim.between) is not None, gim.id
