"""Measured floor registration against a calibrated local minimap snapshot.

This is an authoring diagnostic for the grey/olive reference images. Image
classification is evidence for tracing, never a substitute for runtime audits.
"""
from __future__ import annotations

from pathlib import Path
from collections import deque
import math

import numpy as np
from PIL import Image

from esports_sim.schemas.studio import MapStudioDocumentV1, WalkableSurface
from esports_sim.registry.map_audit import connected_extension_indices
from esports_sim.registry import map_workbench

ROOT = Path(__file__).resolve().parents[3]
GRID_STEP = 0.5


def rectangle_mask(xs, ys, x, y, w, h):
    return (xs >= x) & (xs < x + w) & (ys >= y) & (ys < y + h)


def grid(doc: MapStudioDocumentV1, grid_step=GRID_STEP):
    if not math.isfinite(grid_step) or grid_step <= 0:
        raise ValueError("Reference grid step must be positive and finite")
    reference = doc.reference
    if reference is None:
        raise ValueError("This map has no calibrated reference image")
    path = (ROOT / reference.image_path.lstrip("/")).resolve()
    if path.parent != (ROOT / "assets/maps/references").resolve():
        raise ValueError("Reference must be a local registered minimap")
    with Image.open(path) as image:
        if image.width * image.height > 4_000_000:
            raise ValueError("Reference image is too large")
        pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    columns = math.ceil(reference.width / grid_step)
    rows = math.ceil(reference.height / grid_step)
    if columns * rows > 500_000:
        raise ValueError("Reference world bounds are too large")
    xs, ys = np.meshgrid(reference.x + (np.arange(columns) + 0.5) * grid_step,
                         reference.y + (np.arange(rows) + 0.5) * grid_step)
    ix = np.minimum(pixels.shape[1] - 1, ((xs - reference.x) / reference.width * pixels.shape[1]).astype(int))
    iy = np.minimum(pixels.shape[0] - 1, ((ys - reference.y) / reference.height * pixels.shape[0]).astype(int))
    colors = pixels[iy, ix]
    red, green, blue = colors[..., 0], colors[..., 1], colors[..., 2]
    # Grey floor and olive plant zones; exclude colored UI/gimmick strokes.
    reference_floor = ((red + green + blue > 180) & (np.abs(red - green) <= 30)
                       & (np.abs(green - blue) <= 80) & (red < reference.floor_color_max))
    _, geometry = map_workbench.compile_document(doc)
    authored_floor = np.zeros(xs.shape, dtype=bool)
    for region in geometry.regions.values():
        authored_floor |= rectangle_mask(xs, ys, region.x, region.y, region.w, region.h)
        for extension in region.floor_extensions:
            authored_floor |= rectangle_mask(xs, ys, extension.x, extension.y, extension.w, extension.h)
    for prop in geometry.props:
        if prop.height == "full":
            authored_floor &= ~rectangle_mask(xs, ys, prop.x, prop.y, prop.w, prop.h)
    return xs, ys, reference_floor, authored_floor, geometry


def merge_cells(mask, origin_x: float, origin_y: float, grid_step=GRID_STEP) -> list[dict[str, float]]:
    """Lossless row-span merge: each rectangle covers only selected cells."""
    rectangles = []
    active = {}
    for row_index, row in enumerate(mask):
        padded = np.pad(row.astype(np.int8), (1, 1))
        changes = np.flatnonzero(np.diff(padded))
        spans = set(zip(changes[::2].tolist(), changes[1::2].tolist()))
        for span in sorted(set(active) - spans):
            first_row = active.pop(span)
            rectangles.append((span[0], first_row, span[1], row_index))
        for span in sorted(spans - set(active)):
            active[span] = row_index
    for span, first_row in sorted(active.items()):
        rectangles.append((span[0], first_row, span[1], mask.shape[0]))
    return [{"x": origin_x + x0 * grid_step, "y": origin_y + y0 * grid_step,
             "w": (x1 - x0) * grid_step, "h": (y1 - y0) * grid_step}
            for x0, y0, x1, y1 in rectangles]


def compare_reference(doc: MapStudioDocumentV1, grid_step=GRID_STEP) -> dict:
    _, _, expected, actual, _ = grid(doc, grid_step)
    intersection = int(np.count_nonzero(expected & actual))
    union = int(np.count_nonzero(expected | actual))
    outside = actual & ~expected
    missing = expected & ~actual
    reference = doc.reference
    return {"map_id": doc.id, "grid_step": grid_step, "iou": intersection / max(1, union),
            "floor_precision": intersection / max(1, int(np.count_nonzero(actual))),
            "floor_recall": intersection / max(1, int(np.count_nonzero(expected))),
            "outside_area": int(np.count_nonzero(outside)) * grid_step ** 2,
            "missing_area": int(np.count_nonzero(missing)) * grid_step ** 2,
            "outside": merge_cells(outside, reference.x, reference.y, grid_step),
            "missing": merge_cells(missing, reference.x, reference.y, grid_step),
            "description": reference.description}


def largest_rectangles(mask, origin_x, origin_y, minimum_area):
    """Pack large solid rectangles first, without bridging a floor cell."""
    remaining = mask.copy()
    rectangles = []
    while True:
        heights = np.zeros(mask.shape[1], dtype=int)
        best_area, best = 0, None
        for row, cells in enumerate(remaining):
            heights = np.where(cells, heights + 1, 0)
            stack = []
            for column in range(len(heights) + 1):
                height = int(heights[column]) if column < len(heights) else 0
                start = column
                while stack and stack[-1][1] > height:
                    left, popped_height = stack.pop()
                    area = (column - left) * popped_height
                    if area > best_area:
                        best_area, best = area, (left, row + 1 - popped_height, column, row + 1)
                    start = left
                if height and (not stack or stack[-1][1] < height):
                    stack.append((start, height))
        if best is None or best_area * GRID_STEP ** 2 < minimum_area:
            return rectangles
        x0, y0, x1, y1 = best
        remaining[y0:y1, x0:x1] = False
        rectangles.append({"x": origin_x + x0 * GRID_STEP, "y": origin_y + y0 * GRID_STEP,
                           "w": (x1 - x0) * GRID_STEP, "h": (y1 - y0) * GRID_STEP})


def propose_floor_extensions(doc):
    """Assign missing reference floor to the nearest room along real floor.

    Each tile inherits a room's elevation and tactical identity. Room cores
    and their navigation centers remain intact. Unseeded islands are omitted.
    """
    xs, ys, expected, _, geometry = grid(doc)
    owners = np.full(xs.shape, -1, dtype=int)
    surfaces = sorted(doc.walkable_surfaces, key=lambda s: (
        geometry.regions[next(z.id for z in doc.semantic_zones if z.kind != "plant" and s.id in z.surface_ids)].w *
        geometry.regions[next(z.id for z in doc.semantic_zones if z.kind != "plant" and s.id in z.surface_ids)].h, s.id))
    regions = []
    base = np.zeros(xs.shape, dtype=bool)
    for index, surface in enumerate(surfaces):
        zone = next(z.id for z in doc.semantic_zones if z.kind != "plant" and surface.id in z.surface_ids)
        region = geometry.regions[zone]
        regions.append(region)
        cells = rectangle_mask(xs, ys, region.x, region.y, region.w, region.h)
        base |= cells
        owners[cells & expected & (owners < 0)] = index
    queue = deque(zip(*np.nonzero(owners >= 0)))
    rows, columns = owners.shape
    while queue:
        row, column = queue.popleft()
        for nr, nc in ((row-1,column),(row,column-1),(row,column+1),(row+1,column)):
            if 0 <= nr < rows and 0 <= nc < columns and expected[nr,nc] and owners[nr,nc] < 0:
                owners[nr,nc] = owners[row,column]
                queue.append((nr,nc))
    proposals = []
    for index, surface in enumerate(surfaces):
        region = regions[index]
        rectangles = largest_rectangles((owners == index) & ~base, doc.reference.x, doc.reference.y, 1.0)
        # Grid centers can leave a <0.25u gap at a non-grid-aligned core
        # boundary. Close that seam with a tiny overlap into the core.
        for rect in rectangles:
            rx, ry, ex, ey = rect['x'], rect['y'], rect['x']+rect['w'], rect['y']+rect['h']
            if min(ey,region.y+region.h) > max(ry,region.y):
                if 0 <= rx-(region.x+region.w) <= .25: rx = region.x+region.w-.01
                if 0 <= region.x-ex <= .25: ex = region.x+.01
            if min(ex,region.x+region.w) > max(rx,region.x):
                if 0 <= ry-(region.y+region.h) <= .25: ry = region.y+region.h-.01
                if 0 <= region.y-ey <= .25: ey = region.y+.01
            rect.update(x=rx,y=ry,w=ex-rx,h=ey-ry)
        if rectangles:
            proposed = WalkableSurface(**{**surface.model_dump(mode="json"), "floor_extensions": rectangles})
            connected = connected_extension_indices(proposed)
            proposals.append({**surface.model_dump(mode="json"), "floor_extensions": [r for i,r in enumerate(rectangles) if i in connected]})
    return proposals


def propose_wall_masks(doc: MapStudioDocumentV1, *, clearance: float = 1.25, minimum_area: float = 2.0) -> list[dict]:
    """Trace solid volumes while reserving anchors, cover and authored routes.

    These are editable full-height rectangular props, using the existing
    source/compile contract. A proposal must pass physical and balance gates.
    """
    xs, ys, expected, actual, geometry = grid(doc)
    protected = np.zeros(xs.shape, dtype=bool)
    points = [zone.label_position for zone in doc.semantic_zones]
    points += [(region.cx, region.cy) for region in geometry.regions.values()]
    segments = []
    for link in doc.traversal_links:
        source = next(z.id for z in doc.semantic_zones if z.kind != "plant" and link.from_pos[2] in z.surface_ids)
        target = next(z.id for z in doc.semantic_zones if z.kind != "plant" and link.to_pos[2] in z.surface_ids)
        route = geometry.path(source, target)
        segments.extend(zip(route, route[1:]))
    for x, y in points:
        protected |= (xs - x) ** 2 + (ys - y) ** 2 <= clearance ** 2
    for (x0, y0), (x1, y1) in segments:
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        if length2 == 0:
            continue
        t = np.clip(((xs - x0) * dx + (ys - y0) * dy) / length2, 0, 1)
        protected |= (xs - x0 - t * dx) ** 2 + (ys - y0 - t * dy) ** 2 <= clearance ** 2
    for prop in geometry.props:
        protected |= rectangle_mask(xs, ys, prop.x - clearance, prop.y - clearance,
                                    prop.w + 2 * clearance, prop.h + 2 * clearance)
    remaining = actual & ~expected & ~protected
    proposals = []
    # Smallest supporting room wins overlaps, avoiding duplicate mask volumes.
    for surface in sorted(doc.walkable_surfaces, key=lambda s: (
            (max(x for x, _ in s.polygon) - min(x for x, _ in s.polygon)) *
            (max(y for _, y in s.polygon) - min(y for _, y in s.polygon)), s.id)):
        x0, y0 = min(x for x, _ in surface.polygon), min(y for _, y in surface.polygon)
        x1, y1 = max(x for x, _ in surface.polygon), max(y for _, y in surface.polygon)
        selected = remaining & rectangle_mask(xs, ys, x0, y0, x1 - x0, y1 - y0)
        for rect in largest_rectangles(selected, doc.reference.x, doc.reference.y, minimum_area):
            # Keep the footprint strictly inside its supporting rectangle.
            # Boundary contact is ambiguous in the polygon support validator.
            rx, ry = max(x0 + 0.01, rect["x"]), max(y0 + 0.01, rect["y"])
            ex, ey = min(x1 - 0.01, rect["x"] + rect["w"]), min(y1 - 0.01, rect["y"] + rect["h"])
            if (ex - rx) * (ey - ry) < minimum_area:
                continue
            proposals.append({"id": f"trace_mask_{surface.id}_{len(proposals):03d}", "surface_id": surface.id,
                              "footprint": [(rx, ry), (ex, ry), (ex, ey), (rx, ey)],
                              "height": "full", "collision": True, "role": "wall"})
            remaining &= ~rectangle_mask(xs, ys, rx, ry, ex - rx, ey - ry)
    return proposals
