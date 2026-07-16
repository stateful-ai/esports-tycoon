"""Map Workbench.
Manages drafts, synthesis, compilation, transactional save, and publication of maps.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml
from pydantic import ValidationError

from esports_sim.registry.loader import DEFAULT_DATA_DIR, GameData
from esports_sim.registry.map_audit import audit_map, audit_continuous
from esports_sim.registry.map_guide_renderer import render_legacy_guide
from esports_sim.schemas.geometry import MapGeometry, Region as GeoRegion, Corridor as GeoCorridor, Prop as GeoProp
from esports_sim.schemas.map import Map, Callout, Site, CalloutZone, SightLine, Gimmick, GimmickType
from esports_sim.schemas.studio import (
    MapStudioDocumentV1,
    WalkableSurface,
    SemanticZone,
    Prop as StudioProp,
    TraversalLink,
    LegacyCompilationConfig,
    EditorState,
)

_INSTALL_LOCK = threading.Lock()
_MAP_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_DOCUMENT_LOCK_TIMEOUT_SECONDS = 10.0
_DOCUMENT_LOCK_STALE_SECONDS = 300.0


def _resolve_paths(data_dir: Path | None = None) -> tuple[Path, Path, Path, Path]:
    # Resolve directories relative to repository root
    data_root = (data_dir or DEFAULT_DATA_DIR).resolve()
    studio_dir = data_root / "maps" / "studio"
    runtime_dir = data_root / "maps"
    geometry_dir = data_root / "maps" / "geometry"
    guide_dir = data_root.parent / "assets" / "maps" / "guides"
    
    studio_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    guide_dir.mkdir(parents=True, exist_ok=True)
    
    return studio_dir, runtime_dir, geometry_dir, guide_dir


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def _document_lock(map_id: str, data_dir: Path | None = None) -> Iterator[None]:
    """Coordinate Studio mutations across the web and MCP processes."""
    if not _MAP_ID_RE.fullmatch(map_id):
        raise ValueError("invalid map id format")
    studio_dir, _, _, _ = _resolve_paths(data_dir)
    lock_dir = studio_dir / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{map_id}.lock"
    deadline = time.monotonic() + _DOCUMENT_LOCK_TIMEOUT_SECONDS

    while True:
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            try:
                os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
            finally:
                os.close(descriptor)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > _DOCUMENT_LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting to edit map '{map_id}'")
            time.sleep(0.05)

    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _write_studio_document(target_path: Path, doc: MapStudioDocumentV1) -> str:
    """Serialize and atomically replace one Studio source document."""
    text = yaml.safe_dump(doc.model_dump(mode="json"), sort_keys=False)
    temp_file = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_file.write_text(text, encoding="utf-8")
        temp_file.replace(target_path)
    finally:
        temp_file.unlink(missing_ok=True)
    return _hash_content(text)


def _current_document_hash(map_id: str, data_dir: Path | None = None) -> str | None:
    studio_dir, runtime_dir, _, _ = _resolve_paths(data_dir)
    target_path = studio_dir / f"{map_id}.yaml"
    if target_path.exists():
        return _hash_content(target_path.read_text(encoding="utf-8"))
    if (runtime_dir / f"{map_id}.yaml").exists():
        doc = synthesize_document(map_id, data_dir)
        text = yaml.safe_dump(doc.model_dump(mode="json"), sort_keys=False)
        return _hash_content(text)
    return None


def _is_rectangle(poly: list[tuple[float, float]]) -> bool:
    if len(poly) != 4:
        return False
    xs = [pt[0] for pt in poly]
    ys = [pt[1] for pt in poly]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    # The set of points must be the 4 corners of the AABB
    corners = {(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)}
    poly_set = {(round(pt[0], 2), round(pt[1], 2)) for pt in poly}
    corners_rounded = {(round(pt[0], 2), round(pt[1], 2)) for pt in corners}
    return poly_set == corners_rounded


def list_documents(data_dir: Path | None = None) -> list[dict[str, Any]]:
    studio_dir, runtime_dir, _, _ = _resolve_paths(data_dir)
    out = []
    
    # 1. Listed studio drafts
    seen = set()
    for path in sorted(studio_dir.glob("*.yaml")):
        map_id = path.stem
        seen.add(map_id)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            out.append({
                "id": map_id,
                "display_name": raw.get("display_name", map_id),
                "status": "draft",
            })
        except Exception:
            out.append({
                "id": map_id,
                "display_name": map_id,
                "status": "corrupt_draft",
            })
            
    # 2. Add legacy maps that have no studio draft
    for path in sorted(runtime_dir.glob("*.yaml")):
        map_id = path.stem
        if map_id in seen:
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            out.append({
                "id": map_id,
                "display_name": raw.get("display_name", map_id),
                "status": "legacy",
            })
        except Exception:
            pass
            
    return out


def synthesize_document(map_id: str, data_dir: Path | None = None) -> MapStudioDocumentV1:
    """Synthesize a continuous studio document from legacy files."""
    _, runtime_dir, geometry_dir, _ = _resolve_paths(data_dir)
    map_path = runtime_dir / f"{map_id}.yaml"
    geo_path = geometry_dir / f"{map_id}.yaml"
    
    if not map_path.exists():
        raise FileNotFoundError(f"map runtime config not found: {map_id}")
        
    map_raw = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    geo_raw = yaml.safe_load(geo_path.read_text(encoding="utf-8")) if geo_path.exists() else {}
    
    surfaces = []
    semantic_zones = []
    props = []
    links = []
    prop_support_exemptions: list[str] = []
    
    # Reconstruct surfaces and zones from geometry regions
    regions = geo_raw.get("regions", {})
    callouts = map_raw.get("callouts", {})
    
    for cid, r in regions.items():
        # Create a walkable surface rectangle
        rx, ry, rw, rh = r["x"], r["y"], r["w"], r["h"]
        z = r.get("z", 0.0)
        surf_id = f"surf_{cid}"
        surfaces.append(WalkableSurface(
            id=surf_id,
            polygon=[(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)],
            elevation=z,
        ))
        
        # Create matching semantic zone
        co = callouts.get(cid, {})
        legacy_zone = co.get("zone", "callout")
        if legacy_zone in ("attacker_spawn", "defender_spawn"):
            zone_kind = "spawn"
        elif legacy_zone == "site":
            zone_kind = "site"
        else:
            zone_kind = "callout"

        semantic_zones.append(SemanticZone(
            id=cid,
            display_name=co.get("display_name"),
            kind=zone_kind,
            polygon=[(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)],
            surface_ids=[surf_id],
            label_position=(co.get("x", rx + rw/2), co.get("y", ry + rh/2)),
            site_id=co.get("site", "none"),
            legacy_zone=(
                legacy_zone
                if legacy_zone in {zone.value for zone in CalloutZone}
                else None
            ),
        ))
        
    # Reconstruct links from corridors
    corridors = geo_raw.get("corridors", [])
    for idx, corr in enumerate(corridors):
        between = corr.get("between", [])
        if len(between) == 2:
            c1, c2 = between[0], between[1]
            via = corr.get("via", [])
            # Center of c1 region to center of c2 region
            r1 = regions.get(c1, {"x":0,"y":0,"w":0,"h":0,"z":0})
            r2 = regions.get(c2, {"x":0,"y":0,"w":0,"h":0,"z":0})
            from_pt = (r1["x"] + r1["w"]/2, r1["y"] + r1["h"]/2, f"surf_{c1}")
            to_pt = (r2["x"] + r2["w"]/2, r2["y"] + r2["h"]/2, f"surf_{c2}")
            
            links.append(TraversalLink(
                id=f"link_{c1}_{c2}_{idx}",
                kind="ramp" if abs(r1.get("z", 0.0) - r2.get("z", 0.0)) > 0.5 else "rope",
                from_pos=from_pt,
                to_pos=to_pt,
                via=via,
                path_mode="corridor",
                include_endpoints_in_path=False,
            ))
            
    # Reconstruct links from gimmicks
    gimmicks = map_raw.get("gimmicks", [])
    for idx, gim in enumerate(gimmicks):
        between = gim.get("between", [])
        if len(between) == 2:
            c1, c2 = between[0], between[1]
            r1 = regions.get(c1, {"x":0,"y":0,"w":0,"h":0,"z":0})
            r2 = regions.get(c2, {"x":0,"y":0,"w":0,"h":0,"z":0})
            from_pt = (r1["x"] + r1["w"]/2, r1["y"] + r1["h"]/2, f"surf_{c1}")
            to_pt = (r2["x"] + r2["w"]/2, r2["y"] + r2["h"]/2, f"surf_{c2}")
            
            kind_by_gimmick = {
                GimmickType.BREAKABLE_DOOR.value: "door",
                GimmickType.ROTATING_DOOR.value: "rotating_door",
                GimmickType.TELEPORTER.value: "teleporter",
            }
            link_kind = kind_by_gimmick.get(gim.get("type"))
            if link_kind is None:
                raise ValueError(f"Unsupported legacy gimmick type: {gim.get('type')}")
            update = {
                "id": gim.get("id") or f"gim_{idx}",
                "kind": link_kind,
                "noise_radius": gim.get("noise_radius", 25.0),
                "start_closed_prob": gim.get("start_closed_prob", 0.7),
            }
            pair = {f"surf_{c1}", f"surf_{c2}"}
            matching_index = next(
                (
                    link_index
                    for link_index, existing in enumerate(links)
                    if {existing.from_pos[2], existing.to_pos[2]} == pair
                ),
                None,
            )
            if matching_index is not None:
                links[matching_index] = links[matching_index].model_copy(update=update)
            else:
                links.append(TraversalLink(
                    **update,
                    from_pos=from_pt,
                    to_pos=to_pt,
                    path_mode="portal",
                    include_endpoints_in_path=False,
                ))

    # Reconstruct props
    for idx, p in enumerate(geo_raw.get("props", [])):
        reg = p.get("region")
        px, py, pw, ph = p["x"], p["y"], p["w"], p["h"]
        prop_id = f"prop_{reg}_{idx}"
        region = regions.get(reg)
        if region is not None and not (
            region["x"] < px
            and region["y"] < py
            and px + pw < region["x"] + region["w"]
            and py + ph < region["y"] + region["h"]
        ):
            prop_support_exemptions.append(prop_id)
        props.append(StudioProp(
            id=prop_id,
            surface_id=f"surf_{reg}",
            footprint=[(px, py), (px + pw, py), (px + pw, py + ph), (px, py + ph)],
            height=p.get("height", "half"),
            collision=True,
            destructible=False,
        ))

    # Build document
    legacy = LegacyCompilationConfig(
        adjacency_overrides=map_raw.get("adjacency", {}),
        sightline_overrides=map_raw.get("sightlines", []),
        prop_support_exemptions=prop_support_exemptions,
    )
    
    return MapStudioDocumentV1(
        id=map_id,
        display_name=map_raw.get("display_name", map_id),
        sites=map_raw.get("sites", []),
        walkable_surfaces=surfaces,
        props=props,
        semantic_zones=semantic_zones,
        traversal_links=links,
        legacy=legacy,
        attacker_spawn=map_raw.get("attacker_spawn", "attacker_spawn"),
        defender_spawn=map_raw.get("defender_spawn", "defender_spawn"),
    )


def load_document(map_id: str, data_dir: Path | None = None) -> tuple[MapStudioDocumentV1, str]:
    studio_dir, _, _, _ = _resolve_paths(data_dir)
    studio_path = studio_dir / f"{map_id}.yaml"
    
    if studio_path.exists():
        text = studio_path.read_text(encoding="utf-8")
        doc = MapStudioDocumentV1(**yaml.safe_load(text))
        return doc, _hash_content(text)
    else:
        # Fallback to synthesizing from legacy files
        doc = synthesize_document(map_id, data_dir)
        text = yaml.safe_dump(doc.model_dump(mode="json"), sort_keys=False)
        return doc, _hash_content(text)


def save_document(
    map_id: str, doc_dict: dict[str, Any], if_match_hash: str | None = None, data_dir: Path | None = None
) -> dict[str, Any]:
    """Validate and save a MapStudioDocumentV1 draft to studio/ folder."""
    if not _MAP_ID_RE.fullmatch(map_id):
        raise ValueError("invalid map id format")
    if doc_dict.get("id") != map_id:
        raise ValueError("URL map id must match document id")
        
    studio_dir, _, _, _ = _resolve_paths(data_dir)
    target_path = studio_dir / f"{map_id}.yaml"
    
    try:
        doc = MapStudioDocumentV1(**doc_dict)
    except ValidationError as exc:
        return {
            "valid": False,
            "errors": [
                {"path": ".".join(map(str, error["loc"])), "message": error["msg"]}
                for error in exc.errors()
            ],
        }

    with _document_lock(map_id, data_dir), _INSTALL_LOCK:
        if if_match_hash is not None:
            current_hash = _current_document_hash(map_id, data_dir)
            if current_hash != if_match_hash:
                raise ValueError("stale revision hash (409 conflict)")
        new_hash = _write_studio_document(target_path, doc)
        return {"valid": True, "id": map_id, "hash": new_hash}


def create_document(
    map_id: str,
    doc_dict: dict[str, Any],
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Create a new Studio document without racing another editor process."""
    if not _MAP_ID_RE.fullmatch(map_id):
        raise ValueError("invalid map id format")
    if doc_dict.get("id") != map_id:
        raise ValueError("map id must match document id")
    try:
        doc = MapStudioDocumentV1(**doc_dict)
    except ValidationError as exc:
        return {
            "valid": False,
            "errors": [
                {"path": ".".join(map(str, error["loc"])), "message": error["msg"]}
                for error in exc.errors()
            ],
        }

    studio_dir, runtime_dir, _, _ = _resolve_paths(data_dir)
    target_path = studio_dir / f"{map_id}.yaml"
    with _document_lock(map_id, data_dir), _INSTALL_LOCK:
        if target_path.exists() or (runtime_dir / f"{map_id}.yaml").exists():
            raise FileExistsError(f"map '{map_id}' already exists")
        new_hash = _write_studio_document(target_path, doc)
        return {"valid": True, "id": map_id, "hash": new_hash}


def delete_document(
    map_id: str,
    *,
    if_match_hash: str,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Permanently delete a Studio map and every published map artifact.

    Deletion uses the same document lock and compare-and-swap revision contract
    as saving and publishing. Existing files are first moved into a temporary
    holding directory so a failed move can be rolled back before anything is
    discarded permanently.
    """
    if not _MAP_ID_RE.fullmatch(map_id):
        raise ValueError("invalid map id format")
    if not if_match_hash:
        raise ValueError("revision hash required for permanent deletion")

    studio_dir, runtime_dir, geometry_dir, guide_dir = _resolve_paths(data_dir)
    map_assets_dir = guide_dir.parent
    targets = {
        "studio_source": studio_dir / f"{map_id}.yaml",
        "runtime_map": runtime_dir / f"{map_id}.yaml",
        "runtime_geometry": geometry_dir / f"{map_id}.yaml",
        "guide": guide_dir / f"{map_id}.png",
        "painted_backdrop": map_assets_dir / "painted" / f"{map_id}.webp",
        "thumbnail": map_assets_dir / f"{map_id}.webp",
    }

    with _document_lock(map_id, data_dir), _INSTALL_LOCK:
        current_hash = _current_document_hash(map_id, data_dir)
        if current_hash is None:
            raise FileNotFoundError(f"unknown map '{map_id}'")
        if current_hash != if_match_hash:
            raise ValueError("stale revision hash (409 conflict)")

        existing = [(kind, path) for kind, path in targets.items() if path.exists()]
        holding_dir = Path(
            tempfile.mkdtemp(prefix=f"map-delete-{map_id}-", dir=runtime_dir.parent)
        )
        moved: list[tuple[Path, Path]] = []
        try:
            for index, (_, target) in enumerate(existing):
                held = holding_dir / f"{index}-{target.name}"
                target.rename(held)
                moved.append((target, held))
        except Exception as exc:
            for target, held in reversed(moved):
                if held.exists() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    held.rename(target)
            raise RuntimeError(f"failed transactional map deletion: {exc}") from exc
        else:
            # The deletion is already committed once every artifact has moved
            # out of its live location.  A Windows handle can keep the
            # temporary directory from being removed briefly; that must not
            # turn a completed deletion into a misleading 500 response.
            try:
                shutil.rmtree(holding_dir, ignore_errors=True)
            except OSError:
                pass
            return {
                "valid": True,
                "status": "deleted",
                "id": map_id,
                "deleted_artifacts": [kind for kind, _ in existing],
            }
        finally:
            try:
                shutil.rmtree(holding_dir, ignore_errors=True)
            except OSError:
                # Cleanup is best-effort after a successful commit or a
                # completed rollback.  Leaving only the private temporary
                # directory is safer than masking the real operation result.
                pass


def compile_document(doc: MapStudioDocumentV1) -> tuple[Map, MapGeometry]:
    """Compile continuous studio geometry to legacy rectangular representations.
    Fails with ValueError if information loss occurs (e.g. non-rectangular elements).
    """
    callouts: dict[str, Callout] = {}
    adjacency: dict[str, list[str]] = {}
    sightlines: list[SightLine] = []
    gimmicks: list[Gimmick] = []
    
    regions: dict[str, GeoRegion] = {}
    corridors: list[GeoCorridor] = []
    props: list[GeoProp] = []
    
    # 1. Compile Walkable Surfaces -> Regions. Plant polygons are semantic
    # overlays on a navigational site surface; they must never overwrite the
    # callout region that player pathing consumes.
    surf_to_zone: dict[str, str] = {}
    for zone in doc.semantic_zones:
        if zone.kind == "plant":
            continue
        for sid in zone.surface_ids:
            previous = surf_to_zone.get(sid)
            if previous is not None and previous != zone.id:
                raise ValueError(
                    f"Walkable surface '{sid}' maps to multiple navigational "
                    f"zones ('{previous}', '{zone.id}')"
                )
            surf_to_zone[sid] = zone.id

    for surf in doc.walkable_surfaces:
        if not _is_rectangle(surf.polygon):
            raise ValueError(f"Walkable surface '{surf.id}' is not an axis-aligned rectangle (incompatible with legacy compile)")
        xs = [pt[0] for pt in surf.polygon]
        ys = [pt[1] for pt in surf.polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Region mapping
        zone_id = surf_to_zone.get(surf.id)
        if not zone_id:
            raise ValueError(f"Walkable surface '{surf.id}' is not mapped to any Semantic Zone")
        if zone_id in regions:
            raise ValueError(
                f"Semantic zone '{zone_id}' maps to multiple walkable surfaces; "
                "the current runtime requires one rectangular surface per callout"
            )
            
        regions[zone_id] = GeoRegion(
            x=min_x,
            y=min_y,
            w=max_x - min_x,
            h=max_y - min_y,
            z=surf.elevation,
        )

    # 2. Compile Semantic Zones -> Callouts
    for zone in doc.semantic_zones:
        if zone.kind == "plant":
            continue
        if zone.id not in regions:
            raise ValueError(
                f"Semantic zone '{zone.id}' is not mapped to a runtime walkable surface"
            )
        if zone.id == doc.attacker_spawn:
            runtime_zone = CalloutZone.ATTACKER_SPAWN
        elif zone.id == doc.defender_spawn:
            runtime_zone = CalloutZone.DEFENDER_SPAWN
        elif zone.legacy_zone is not None:
            runtime_zone = CalloutZone(zone.legacy_zone)
        elif zone.kind == "site":
            runtime_zone = CalloutZone.SITE
        elif zone.site_id == "mid":
            runtime_zone = CalloutZone.MID
        else:
            raise ValueError(
                f"Semantic zone '{zone.id}' needs a tactical runtime zone"
            )
        callouts[zone.id] = Callout(
            id=zone.id,
            display_name=zone.display_name or zone.id.replace("_", " ").title(),
            site=Site(zone.site_id) if zone.site_id in [s.value for s in Site] else Site.NONE,
            zone=runtime_zone,
            x=zone.label_position[0],
            y=zone.label_position[1],
        )

    # 3. Compile Traversal Links -> Gimmicks & Corridors
    for link in doc.traversal_links:
        fx, fy, fsid = link.from_pos
        tx, ty, tsid = link.to_pos
        zone_f = surf_to_zone.get(fsid)
        zone_t = surf_to_zone.get(tsid)
        if not zone_f or not zone_t:
            raise ValueError(
                f"Traversal link '{link.id}' endpoint is not mapped to a "
                "navigational zone"
            )
            
        # Compile as breakable door or teleporter gimmicks
        if link.kind == "door":
            gimmicks.append(Gimmick(
                id=link.id,
                type=GimmickType.BREAKABLE_DOOR,
                between=(zone_f, zone_t),
                noise_radius=link.noise_radius,
                start_closed_prob=link.start_closed_prob,
            ))
        elif link.kind == "rotating_door":
            gimmicks.append(Gimmick(
                id=link.id,
                type=GimmickType.ROTATING_DOOR,
                between=(zone_f, zone_t),
                noise_radius=link.noise_radius,
            ))
        elif link.kind == "teleporter":
            gimmicks.append(Gimmick(
                id=link.id,
                type=GimmickType.TELEPORTER,
                between=(zone_f, zone_t),
                noise_radius=link.noise_radius,
            ))
        if link.path_mode == "corridor":
            # Preserve authored endpoints and bends. These become the exact
            # motor-route polyline between the two semantic callouts.
            via = (
                [(fx, fy), *link.via, (tx, ty)]
                if link.include_endpoints_in_path
                else list(link.via)
            )
            corridors.append(GeoCorridor(
                between=(zone_f, zone_t),
                via=via,
            ))

    # 4. Compile Props
    for prop in doc.props:
        if not prop.collision:
            continue
        zone_id = surf_to_zone.get(prop.surface_id)
        if not zone_id:
            continue
        if not _is_rectangle(prop.footprint):
            raise ValueError(f"Prop '{prop.id}' footprint is not an axis-aligned rectangle (incompatible with legacy compile)")
        xs = [pt[0] for pt in prop.footprint]
        ys = [pt[1] for pt in prop.footprint]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        props.append(GeoProp(
            region=zone_id,
            x=min_x,
            y=min_y,
            w=max_x - min_x,
            h=max_y - min_y,
            height=prop.height,
        ))

    # 5. Compile axis-aligned Studio walls into full-height runtime blockers.
    # MapGeometry already treats full props as wall segments for point LOS;
    # using that representation also keeps the guide/viewer contract intact.
    surface_bounds: dict[str, tuple[float, float, float, float]] = {}
    for surface in doc.walkable_surfaces:
        xs = [point[0] for point in surface.polygon]
        ys = [point[1] for point in surface.polygon]
        surface_bounds[surface.id] = (min(xs), min(ys), max(xs), max(ys))
    for wall_index, wall in enumerate(doc.walls):
        for segment_index, ((x1, y1), (x2, y2)) in enumerate(
            zip(wall.polyline, wall.polyline[1:])
        ):
            if x1 == x2 and y1 == y2:
                continue
            midpoint = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            candidates = sorted(
                sid
                for sid, (min_x, min_y, max_x, max_y) in surface_bounds.items()
                if min_x - 0.01 <= midpoint[0] <= max_x + 0.01
                and min_y - 0.01 <= midpoint[1] <= max_y + 0.01
                and sid in surf_to_zone
            )
            if not candidates:
                raise ValueError(
                    f"Wall {wall_index} segment {segment_index} is not on a "
                    "navigational surface"
                )
            thickness = wall.thickness
            if abs(x1 - x2) <= 1e-6:
                rx, ry = x1 - thickness / 2.0, min(y1, y2)
                rw, rh = thickness, abs(y2 - y1)
            elif abs(y1 - y2) <= 1e-6:
                rx, ry = min(x1, x2), y1 - thickness / 2.0
                rw, rh = abs(x2 - x1), thickness
            else:
                raise ValueError(
                    f"Wall {wall_index} segment {segment_index} is diagonal; "
                    "runtime walls must be axis-aligned"
                )
            props.append(
                GeoProp(
                    region=surf_to_zone[candidates[0]],
                    x=rx,
                    y=ry,
                    w=rw,
                    h=rh,
                    height="full",
                )
            )

    # Apply legacy overrides
    adjacency = doc.legacy.adjacency_overrides.copy()
    
    # Auto-generate adjacency from traversal links
    for link in doc.traversal_links:
        zf = surf_to_zone.get(link.from_pos[2])
        zt = surf_to_zone.get(link.to_pos[2])
        if zf and zt:
            adjacency.setdefault(zf, []).append(zt)
            adjacency.setdefault(zt, []).append(zf)
            
    # Remove duplicates without reordering authored neighbors. Neighbor order
    # is part of deterministic policy tie-breaking, so sorting here changes
    # match outcomes after an otherwise no-op Studio round trip.
    for k in list(adjacency.keys()):
        adjacency[k] = list(dict.fromkeys(adjacency[k]))
        
    for s in doc.legacy.sightline_overrides:
        sightlines.append(SightLine(**s))

    inferred_sites = {
        zone.site_id
        for zone in doc.semantic_zones
        if zone.kind in ("site", "plant")
        and zone.site_id in {site.value for site in Site}
        and zone.site_id not in (Site.NONE.value, Site.MID.value)
    }
    runtime_sites = list(dict.fromkeys([*doc.sites, *sorted(inferred_sites - set(doc.sites))]))
    map_obj = Map(
        id=doc.id,
        display_name=doc.display_name,
        sites=[Site(site) for site in runtime_sites if site in {s.value for s in Site}],
        callouts=callouts,
        adjacency=adjacency,
        sightlines=sightlines,
        attacker_spawn=doc.attacker_spawn,
        defender_spawn=doc.defender_spawn,
        gimmicks=gimmicks,
    )
    
    geo_obj = MapGeometry(
        map_id=doc.id,
        regions=regions,
        corridors=corridors,
        props=props,
    )
    
    return map_obj, geo_obj


def validate_document(
    doc: MapStudioDocumentV1,
) -> tuple[Map | None, MapGeometry | None, list[dict[str, str]]]:
    """Validate both the Studio source and the exact runtime artifacts.

    The dry-run API and transactional publisher share this function so a
    green Validate result means Publish will not uncover a separate geometry
    compatibility failure.
    """
    errors = [
        {"path": "continuous", "message": message}
        for message in audit_continuous(doc)
    ]
    try:
        map_obj, geo_obj = compile_document(doc)
    except ValueError as exc:
        errors.append({"path": "compilation", "message": str(exc)})
        return None, None, errors
    errors.extend(
        {"path": "legacy", "message": message}
        for message in audit_map(map_obj, geo_obj)
    )
    return map_obj, geo_obj, errors


def _publish_document_locked(map_id: str, data_dir: Path | None = None) -> dict[str, Any]:
    """Compiles in-memory structures, validates schemas, runs audits,
    renders guide, and performs a locked transactional promotion of all files.
    """
    studio_dir, runtime_dir, geometry_dir, guide_dir = _resolve_paths(data_dir)
    studio_path = studio_dir / f"{map_id}.yaml"
    
    if not studio_path.exists():
        raise FileNotFoundError(f"studio draft doc not found for: {map_id}")
        
    # Read draft doc
    doc = MapStudioDocumentV1(**yaml.safe_load(studio_path.read_text(encoding="utf-8")))
    
    map_obj, geo_obj, errors = validate_document(doc)
    if errors:
        raise ValueError(f"Publish failed audits: {errors[0]['message']}")
    assert map_obj is not None and geo_obj is not None
        
    # Render guide
    img, info = render_legacy_guide(map_obj, geo_obj)
    
    # Transactional Installation Loop
    with _INSTALL_LOCK:
        # Targets
        map_target = runtime_dir / f"{map_id}.yaml"
        geo_target = geometry_dir / f"{map_id}.yaml"
        guide_target = guide_dir / f"{map_id}.png"
        
        # Temp/Staging Directory
        temp_root = Path(tempfile.mkdtemp(prefix="map-publish-", dir=runtime_dir.parent))
        temp_map = temp_root / "map.yaml"
        temp_geo = temp_root / "geo.yaml"
        temp_guide = temp_root / "guide.png"
        
        # Write staged files
        temp_map.write_text(yaml.safe_dump(map_obj.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
        temp_geo.write_text(yaml.safe_dump(geo_obj.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
        img.save(temp_guide)
        
        # Create Backups
        map_backup = map_target.with_name(f".{map_target.name}.backup-{uuid.uuid4().hex}") if map_target.exists() else None
        geo_backup = geo_target.with_name(f".{geo_target.name}.backup-{uuid.uuid4().hex}") if geo_target.exists() else None
        guide_backup = guide_target.with_name(f".{guide_target.name}.backup-{uuid.uuid4().hex}") if guide_target.exists() else None
        
        try:
            # 1. Rename existing files to backup
            if map_backup:
                map_target.rename(map_backup)
            if geo_backup:
                geo_target.rename(geo_backup)
            if guide_backup:
                guide_target.rename(guide_backup)
                
            # 2. Promote staged files
            shutil.copy2(temp_map, map_target)
            shutil.copy2(temp_geo, geo_target)
            shutil.copy2(temp_guide, guide_target)
            
            # Clean up backups
            if map_backup and map_backup.exists():
                map_backup.unlink()
            if geo_backup and geo_backup.exists():
                geo_backup.unlink()
            if guide_backup and guide_backup.exists():
                guide_backup.unlink()
                
            # Compute hashes
            source_rev = _hash_content(studio_path.read_text(encoding="utf-8"))
            compiled_rev = _hash_content(map_target.read_text(encoding="utf-8") + geo_target.read_text(encoding="utf-8"))
            
            return {
                "valid": True,
                "status": "published",
                "source_revision": source_rev,
                "compiled_revision": compiled_rev,
                "guide_info": info,
            }
            
        except Exception as exc:
            # Rollback
            # 1. Clean up any failed new target files before renaming backups
            for target, backup in [(map_target, map_backup), (geo_target, geo_backup), (guide_target, guide_backup)]:
                if backup is not None:
                    if backup.exists() and target.exists():
                        try: target.unlink()
                        except Exception: pass
                else:
                    if target.exists():
                        try: target.unlink()
                        except Exception: pass
                        
            # 2. Restore backups
            for target, backup in [(map_target, map_backup), (geo_target, geo_backup), (guide_target, guide_backup)]:
                if backup and backup.exists() and not target.exists():
                    try: backup.rename(target)
                    except Exception: pass
                
            raise RuntimeError(f"failed transactional promotion: {exc}") from exc
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


def publish_document(
    map_id: str,
    data_dir: Path | None = None,
    if_match_hash: str | None = None,
) -> dict[str, Any]:
    """Publish the exact revision requested while excluding concurrent edits."""
    with _document_lock(map_id, data_dir):
        current_hash = _current_document_hash(map_id, data_dir)
        if if_match_hash is not None and current_hash != if_match_hash:
            raise ValueError("stale revision hash (409 conflict)")
        return _publish_document_locked(map_id, data_dir)
