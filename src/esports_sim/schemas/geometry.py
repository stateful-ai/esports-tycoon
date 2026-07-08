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
    """Axis-aligned room for one callout. (x, y) is the min corner.
    `z` is the floor elevation — heaven boxes sit above the site they
    overlook, and the sim pays a high-ground bonus across the gap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float
    y: float
    w: float
    h: float
    z: float = 0.0

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


class Prop(BaseModel):
    """A box/crate/wall segment inside a room.

    half-height: cover — a stationary holder shoots over it and is harder
    to hit from other rooms. full-height: blocks sight — a cross-room
    sightline whose line crosses it is broken (engagements become rare
    repositioning skirmishes and nobody holds an angle through a box).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    region: str
    x: float
    y: float
    w: float
    h: float
    height: str = "half"  # half | full


class MapGeometry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    map_id: str
    regions: dict[str, Region]
    corridors: list[Corridor] = Field(default_factory=list)
    props: list[Prop] = Field(default_factory=list)

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

    # -- detail: cover, elevation, line of sight -----------------------------

    def cover_count(self, region_id: str) -> int:
        """Half-height props in a room — each one is somewhere for a
        holder to anchor behind."""
        return sum(
            1 for p in self.props if p.region == region_id and p.height == "half"
        )

    def height_delta(self, a: str, b: str) -> float:
        """Floor elevation of `a` minus `b` (positive = a stands higher)."""
        ra, rb = self.regions.get(a), self.regions.get(b)
        if ra is None or rb is None:
            return 0.0
        return ra.z - rb.z

    def sight_blocked(self, a: str, b: str) -> bool:
        """True when a full-height prop crosses the center-to-center line
        between two rooms — the angle can't actually be held."""
        ra, rb = self.regions.get(a), self.regions.get(b)
        if ra is None or rb is None:
            return False
        for p in self.props:
            if p.height != "full":
                continue
            if _segment_hits_rect(
                ra.cx, ra.cy, rb.cx, rb.cy, p.x, p.y, p.w, p.h
            ):
                return True
        return False

    # -- continuous positions: slots, point LOS, point paths -----------------

    def los_blocked_at(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> bool:
        """True when a full-height prop crosses the line between two
        actual positions. Point-level upgrade of `sight_blocked` — where
        you stand decides whether the box is in the way."""
        for p in self.props:
            if p.height != "full":
                continue
            if _segment_hits_rect(x1, y1, x2, y2, p.x, p.y, p.w, p.h):
                return True
        return False

    def cover_near(
        self, x: float, y: float, ex: float, ey: float,
        radius: float = 5.0,
    ) -> bool:
        """Is there a half-height prop close to (x, y) that sits roughly
        between it and the enemy at (ex, ey)? Positional cover: hugging a
        crate only helps against fire from the far side of it."""
        for p in self.props:
            if p.height != "half":
                continue
            pcx, pcy = p.x + p.w / 2.0, p.y + p.h / 2.0
            dpx, dpy = pcx - x, pcy - y
            dist = (dpx * dpx + dpy * dpy) ** 0.5
            if dist > radius or dist == 0.0:
                continue
            dex, dey = ex - x, ey - y
            elen = (dex * dex + dey * dey) ** 0.5
            if elen == 0.0:
                continue
            # Prop within a ~60° cone toward the enemy counts as cover.
            if (dpx * dex + dpy * dey) / (dist * elen) > 0.5:
                return True
        return False

    def room_slots(self, region_id: str) -> list[tuple[float, float, str]]:
        """Deterministic tactical spots inside a room: one behind each
        prop ("cover"), one just inside each doorway ("portal"), and four
        interior spread points ("spread"). Players stand at slots instead
        of stacking on the room center."""
        r = self.regions.get(region_id)
        if r is None:
            return []
        margin = 1.5
        lo_x, hi_x = r.x + margin, r.x + r.w - margin
        lo_y, hi_y = r.y + margin, r.y + r.h - margin

        def clamp(px: float, py: float) -> tuple[float, float]:
            return (min(max(px, lo_x), hi_x), min(max(py, lo_y), hi_y))

        slots: list[tuple[float, float, str]] = []
        # Cover slots: on the room-center side of each prop in the room.
        for p in sorted(
            (p for p in self.props if p.region == region_id),
            key=lambda p: (p.x, p.y),
        ):
            pcx, pcy = p.x + p.w / 2.0, p.y + p.h / 2.0
            dx, dy = r.cx - pcx, r.cy - pcy
            norm = (dx * dx + dy * dy) ** 0.5 or 1.0
            off = max(p.w, p.h) / 2.0 + 1.2
            cx, cy = clamp(pcx + dx / norm * off, pcy + dy / norm * off)
            slots.append((cx, cy, "cover"))
        # Portal slots: just inside each doorway.
        for other in sorted(self.regions):
            if other == region_id:
                continue
            portal = self.portal(region_id, other)
            if portal is None:
                continue
            px, py = portal
            dx, dy = r.cx - px, r.cy - py
            norm = (dx * dx + dy * dy) ** 0.5 or 1.0
            sx, sy = clamp(px + dx / norm * 3.0, py + dy / norm * 3.0)
            slots.append((sx, sy, "portal"))
        # Spread slots: quarter points of the room interior.
        for fx, fy in ((0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)):
            slots.append(
                (round(r.x + r.w * fx, 2), round(r.y + r.h * fy, 2), "spread")
            )
        return slots

    def path_between_points(
        self,
        from_room: str,
        to_room: str,
        from_pt: tuple[float, float],
        to_pt: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Waypoint polyline from an actual position in one room to an
        actual position in an adjacent room: through the corridor/portal,
        never through walls. Same room → straight line."""
        if from_room == to_room:
            return [from_pt, to_pt]
        mid = self.path(from_room, to_room)
        # Replace the room-center endpoints with the real positions.
        core = mid[1:-1] if len(mid) > 2 else []
        return [from_pt, *core, to_pt]


def _segment_hits_rect(
    x1: float, y1: float, x2: float, y2: float,
    rx: float, ry: float, rw: float, rh: float,
) -> bool:
    """Liang-Barsky segment/AABB intersection (pure, deterministic)."""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, x1 - rx),
        (dx, rx + rw - x1),
        (-dy, y1 - ry),
        (dy, ry + rh - y1),
    ):
        if p == 0:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1
