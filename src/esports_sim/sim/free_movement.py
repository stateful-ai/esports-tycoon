"""Deterministic free-roam collision and visibility over authored map geometry.

Callouts remain the tactical language, but they no longer have to be the
movement cell.  This resolver treats the union of authored region floors as
walkable space, props as physical blockers, and declared openings as the only
crossing through an otherwise-walled room seam.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from esports_sim.schemas.geometry import MapGeometry, Opening, Prop, Region
from esports_sim.schemas.map import Map


@dataclass(frozen=True, slots=True)
class MovementResult:
    x: float
    y: float
    callout_id: str


class FreeMovementResolver:
    """Resolve point movement without exposing hidden geometry to policies."""

    def __init__(
        self,
        map_obj: Map,
        geometry: MapGeometry,
        *,
        player_radius: float,
        collision_step: float,
    ) -> None:
        self.map = map_obj
        self.geometry = geometry
        self.player_radius = player_radius
        self.collision_step = collision_step
        self._adjacent = {
            frozenset((source, target))
            for source, targets in map_obj.adjacency.items()
            for target in targets
        }

    @staticmethod
    def _inside_region(region: Region, x: float, y: float) -> bool:
        return region.contains(x, y, pad=1e-7)

    @staticmethod
    def _inside_prop(prop: Prop, x: float, y: float, pad: float) -> bool:
        return (
            prop.x - pad <= x <= prop.x + prop.w + pad
            and prop.y - pad <= y <= prop.y + prop.h + pad
        )

    def _blocked_by_prop(
        self, x: float, y: float, *, visibility: bool
    ) -> bool:
        return any(
            (not visibility or prop.height == "full")
            and self._inside_prop(
                prop,
                x,
                y,
                0.0 if visibility else self.player_radius,
            )
            for prop in self.geometry.props
        )

    def regions_at(
        self, x: float, y: float, *, visibility: bool = False
    ) -> tuple[str, ...]:
        if self._blocked_by_prop(x, y, visibility=visibility):
            return ()
        return tuple(
            region_id
            for region_id, region in sorted(self.geometry.regions.items())
            if self._inside_region(region, x, y)
        )

    def callout_at(
        self,
        x: float,
        y: float,
        current: str | None = None,
        *,
        visibility: bool = False,
    ) -> str | None:
        candidates = self.regions_at(x, y, visibility=visibility)
        if current in candidates:
            return current
        if not candidates:
            return None
        # Overlapping authored rectangles are resolved by the most specific
        # floor plate, then stable id.  This prevents a large spawn band from
        # swallowing a smaller connector at their shared edge.
        return min(
            candidates,
            key=lambda region_id: (
                self.geometry.regions[region_id].w
                * self.geometry.regions[region_id].h,
                region_id,
            ),
        )

    @staticmethod
    def _opening_coordinate(
        opening: Opening,
        first: Region,
        second: Region,
        x: float,
        y: float,
    ) -> float:
        overlap_x = min(first.x + first.w, second.x + second.w) - max(
            first.x, second.x
        )
        overlap_y = min(first.y + first.h, second.y + second.h) - max(
            first.y, second.y
        )
        del opening
        return x if overlap_x >= overlap_y else y

    def _transition_allowed(
        self,
        source: str,
        target: str,
        x: float,
        y: float,
        blocked_edges: frozenset[frozenset[str]],
        *,
        visibility: bool,
    ) -> bool:
        if source == target:
            return True
        edge = frozenset((source, target))
        if edge not in self._adjacent or edge in blocked_edges:
            return False
        opening = self.geometry.opening_for(source, target)
        if opening is None:
            return True
        coordinate = self._opening_coordinate(
            opening,
            self.geometry.regions[source],
            self.geometry.regions[target],
            x,
            y,
        )
        clearance = 0.0 if visibility else self.player_radius
        return (
            opening.span[0] + clearance
            <= coordinate
            <= opening.span[1] - clearance
        )

    def _next_callout(
        self,
        current: str,
        x: float,
        y: float,
        blocked_edges: frozenset[frozenset[str]],
        *,
        visibility: bool,
    ) -> str | None:
        candidates = self.regions_at(x, y, visibility=visibility)
        if current in candidates:
            return current
        allowed = [
            target
            for target in candidates
            if self._transition_allowed(
                current,
                target,
                x,
                y,
                blocked_edges,
                visibility=visibility,
            )
        ]
        if not allowed:
            return None
        return min(
            allowed,
            key=lambda region_id: (
                self.geometry.regions[region_id].w
                * self.geometry.regions[region_id].h,
                region_id,
            ),
        )

    def resolve_step(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        current_callout: str,
        blocked_edges: frozenset[frozenset[str]] = frozenset(),
    ) -> MovementResult:
        """Move with sub-stepping and deterministic wall sliding.

        Sub-steps prevent tunnelling through narrow props.  If the diagonal
        is blocked, the dominant axis is attempted first, producing familiar
        wall sliding without a physics engine or floating-point randomness.
        """
        distance = math.hypot(dx, dy)
        if distance == 0.0:
            return MovementResult(x, y, current_callout)
        steps = max(1, math.ceil(distance / self.collision_step))
        step_x, step_y = dx / steps, dy / steps
        callout = current_callout
        px, py = x, y

        for _ in range(steps):
            attempts = [(step_x, step_y)]
            axes = [(step_x, 0.0), (0.0, step_y)]
            if abs(step_y) > abs(step_x):
                axes.reverse()
            attempts.extend(axes)
            moved = False
            for add_x, add_y in attempts:
                if add_x == 0.0 and add_y == 0.0:
                    continue
                nx, ny = px + add_x, py + add_y
                next_callout = self._next_callout(
                    callout,
                    nx,
                    ny,
                    blocked_edges,
                    visibility=False,
                )
                if next_callout is None:
                    continue
                px, py, callout = nx, ny, next_callout
                moved = True
                break
            if not moved:
                break
        return MovementResult(px, py, callout)

    def has_line_of_sight(
        self,
        x1: float,
        y1: float,
        room1: str,
        x2: float,
        y2: float,
        room2: str,
        blocked_edges: frozenset[frozenset[str]] = frozenset(),
    ) -> bool:
        """Trace visibility through floor, openings, props, and shut doors.

        Region membership can only change where this segment crosses an
        axis-aligned region boundary.  Testing the midpoint of each resulting
        interval is exact for rectangular floors and dramatically cheaper
        than spatial sampling inside every potential duel.
        """
        if self.geometry.los_blocked_at(x1, y1, x2, y2):
            return False
        dx, dy = x2 - x1, y2 - y1
        if dx == 0.0 and dy == 0.0:
            return room1 == room2

        boundaries = {0.0, 1.0}
        for region in self.geometry.regions.values():
            if dx != 0.0:
                for boundary_x in (region.x, region.x + region.w):
                    t = (boundary_x - x1) / dx
                    if 0.0 < t < 1.0:
                        boundaries.add(round(t, 12))
            if dy != 0.0:
                for boundary_y in (region.y, region.y + region.h):
                    t = (boundary_y - y1) / dy
                    if 0.0 < t < 1.0:
                        boundaries.add(round(t, 12))

        ordered = sorted(boundaries)
        callout = room1
        for start, end in zip(ordered, ordered[1:]):
            if end - start <= 1e-12:
                continue
            middle = (start + end) / 2.0
            mx, my = x1 + dx * middle, y1 + dy * middle
            candidates = tuple(
                region_id
                for region_id, region in sorted(self.geometry.regions.items())
                if self._inside_region(region, mx, my)
            )
            if callout in candidates:
                continue
            cross_x, cross_y = x1 + dx * start, y1 + dy * start
            allowed = [
                target
                for target in candidates
                if self._transition_allowed(
                    callout,
                    target,
                    cross_x,
                    cross_y,
                    blocked_edges,
                    visibility=True,
                )
            ]
            if not allowed:
                return False
            callout = min(
                allowed,
                key=lambda region_id: (
                    self.geometry.regions[region_id].w
                    * self.geometry.regions[region_id].h,
                    region_id,
                ),
            )

        endpoint_regions = tuple(
            region_id
            for region_id, region in sorted(self.geometry.regions.items())
            if self._inside_region(region, x2, y2)
        )
        return callout == room2 or room2 in endpoint_regions
