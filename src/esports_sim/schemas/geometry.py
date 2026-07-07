"""Map geometry — the floor plan under the callout graph.

The sim's *decisions* stay on the callout graph; geometry gives every
callout a physical room (an axis-aligned rect on the same 0-100 grid as
the callout x/y anchors) so that:
  - the viewer can render actual floors, walls, and corridors
    (isometric or top-down) with players moving through space, and
  - the sim can consume real distances (weapon range curves, travel
    detail) without abandoning the graph as its tactical vocabulary.

Movement between adjacent callouts follows center -> portal -> center,
where the portal is the midpoint of the shared boundary between the two
rects. Rects that don't touch declare a `corridor` with explicit
waypoints instead. Geometry is authored per map in
`data/maps/geometry/<map_id>.yaml` and is optional — maps without it
fall back to the plain graph view.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Rects within this gap still derive a portal (small door gaps are fine).
PORTAL_GAP_TOLERANCE = 4.0


class Region(BaseModel):
    """Axis-aligned room for one callout. (x, y) is the min corner."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def contains(self, px: float, py: float, pad: float = 0.0) -> bool:
        return (
            self.x - pad <= px <= self.x + self.w + pad
            and self.y - pad <= py <= self.y + self.h + pad
        )


class Corridor(BaseModel):
    """Explicit waypoint path for an adjacency whose rects don't touch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    between: tuple[str, str]
    via: list[tuple[float, float]] = Field(default_factory=list)


class MapGeometry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    map_id: str
    regions: dict[str, Region]
    corridors: list[Corridor] = Field(default_factory=list)

    # -- portals -------------------------------------------------------------

    def portal(self, a: str, b: str) -> tuple[float, float] | None:
        """Midpoint of the shared boundary between two regions, or None
        if they don't (nearly) touch."""
        ra, rb = self.regions.get(a), self.regions.get(b)
        if ra is None or rb is None:
            return None
        # Overlap interval on each axis (negative = gap).
        ox = min(ra.x + ra.w, rb.x + rb.w) - max(ra.x, rb.x)
        oy = min(ra.y + ra.h, rb.y + rb.h) - max(ra.y, rb.y)
        if ox < -PORTAL_GAP_TOLERANCE or oy < -PORTAL_GAP_TOLERANCE:
            return None
        # Portal sits at the middle of the overlapping span, on the seam.
        px = (max(ra.x, rb.x) + min(ra.x + ra.w, rb.x + rb.w)) / 2.0
        py = (max(ra.y, rb.y) + min(ra.y + ra.h, rb.y + rb.h)) / 2.0
        return (px, py)

    def path(self, a: str, b: str) -> list[tuple[float, float]]:
        """Waypoint polyline for one adjacency hop: center -> (corridor
        waypoints | portal) -> center. Always returns at least the two
        centers, so movement never breaks on missing geometry."""
        ra, rb = self.regions.get(a), self.regions.get(b)
        if ra is None or rb is None:
            return []
        pts: list[tuple[float, float]] = [(ra.cx, ra.cy)]
        corridor = next(
            (c for c in self.corridors if set(c.between) == {a, b}), None
        )
        if corridor is not None:
            via = list(corridor.via)
            # Author corridors in either direction; orient toward b.
            if corridor.between[0] != a:
                via.reverse()
            pts.extend(via)
        else:
            portal = self.portal(a, b)
            if portal is not None:
                pts.append(portal)
        pts.append((rb.cx, rb.cy))
        return pts

    def hop_distance(self, a: str, b: str) -> float:
        """Physical length of the a->b path (grid units)."""
        pts = self.path(a, b)
        return sum(
            ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            for (x1, y1), (x2, y2) in zip(pts, pts[1:])
        )

    def sight_distance(self, a: str, b: str) -> float:
        """Straight-line distance between region centers — the range a
        duel across this sightline is fought at."""
        ra, rb = self.regions.get(a), self.regions.get(b)
        if ra is None or rb is None:
            return 0.0
        return ((ra.cx - rb.cx) ** 2 + (ra.cy - rb.cy) ** 2) ** 0.5
