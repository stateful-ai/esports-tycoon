"""Map Workbench.
Manages drafts, synthesis, compilation, transactional save, and publication of maps.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import uuid
import re
from pathlib import Path
from typing import Any

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
            kind=zone_kind,
            polygon=[(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)],
            surface_ids=[surf_id],
            label_position=(co.get("x", rx + rw/2), co.get("y", ry + rh/2)),
            site_id=co.get("site", "none"),
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
            
            links.append(TraversalLink(
                id=gim.get("id") or f"gim_{idx}",
                kind="door" if gim["type"] == "breakable_door" else "teleporter",
                from_pos=from_pt,
                to_pos=to_pt,
                noise_radius=gim.get("noise_radius", 25.0),
                start_closed_prob=gim.get("start_closed_prob", 0.7),
            ))

    # Reconstruct props
    for idx, p in enumerate(geo_raw.get("props", [])):
        reg = p.get("region")
        px, py, pw, ph = p["x"], p["y"], p["w"], p["h"]
        props.append(StudioProp(
            id=f"prop_{reg}_{idx}",
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
    )
    
    return MapStudioDocumentV1(
        id=map_id,
        display_name=map_raw.get("display_name", map_id),
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
    
    # Lock for file writing
    with _INSTALL_LOCK:
        # Check If-Match hash
        if if_match_hash is not None and target_path.exists():
            curr_text = target_path.read_text(encoding="utf-8")
            curr_hash = _hash_content(curr_text)
            if curr_hash != if_match_hash:
                raise ValueError("stale revision hash (409 conflict)")
                
        # Validate Pydantic schema
        try:
            doc = MapStudioDocumentV1(**doc_dict)
        except ValidationError as exc:
            return {"valid": False, "errors": [{"path": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]}
            
        # Write YAML atomically
        temp_file = target_path.with_suffix(".tmp")
        try:
            text = yaml.safe_dump(doc.model_dump(mode="json"), sort_keys=False)
            temp_file.write_text(text, encoding="utf-8")
            if target_path.exists():
                target_path.unlink()
            temp_file.rename(target_path)
        finally:
            if temp_file.exists():
                temp_file.unlink()
                
        return {"valid": True, "id": map_id, "hash": _hash_content(text)}


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
    
    # 1. Compile Walkable Surfaces -> Regions
    # Map from surface id to matching semantic zone id
    surf_to_zone: dict[str, str] = {}
    for zone in doc.semantic_zones:
        for sid in zone.surface_ids:
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
            
        regions[zone_id] = GeoRegion(
            x=min_x,
            y=min_y,
            w=max_x - min_x,
            h=max_y - min_y,
            z=surf.elevation,
        )

    # 2. Compile Semantic Zones -> Callouts
    for zone in doc.semantic_zones:
        if zone.kind not in ("callout", "site", "spawn", "plant"):
            continue
        callouts[zone.id] = Callout(
            id=zone.id,
            display_name=zone.id.replace("_", " ").title(),
            site=Site(zone.site_id) if zone.site_id in [s.value for s in Site] else Site.NONE,
            zone=CalloutZone(zone.kind) if zone.kind in [z.value for z in CalloutZone] else CalloutZone.SITE,
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
            continue
            
        # Compile as breakable door or teleporter gimmicks
        if link.kind == "door":
            gimmicks.append(Gimmick(
                id=link.id,
                type=GimmickType.BREAKABLE_DOOR,
                between=(zone_f, zone_t),
                noise_radius=link.noise_radius,
                start_closed_prob=link.start_closed_prob,
            ))
        elif link.kind == "teleporter":
            gimmicks.append(Gimmick(
                id=link.id,
                type=GimmickType.TELEPORTER,
                between=(zone_f, zone_t),
                noise_radius=link.noise_radius,
            ))
        else:
            # Build corridor between them
            corridors.append(GeoCorridor(
                between=(zone_f, zone_t),
                via=[(fx, fy), (tx, ty)],
            ))

    # 4. Compile Props
    for prop in doc.props:
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

    # Apply legacy overrides
    adjacency = doc.legacy.adjacency_overrides.copy()
    
    # Auto-generate adjacency from traversal links
    for link in doc.traversal_links:
        zf = surf_to_zone.get(link.from_pos[2])
        zt = surf_to_zone.get(link.to_pos[2])
        if zf and zt:
            adjacency.setdefault(zf, []).append(zt)
            adjacency.setdefault(zt, []).append(zf)
            
    # Remove duplicates from adjacency
    for k in list(adjacency.keys()):
        adjacency[k] = sorted(list(set(adjacency[k])))
        
    for s in doc.legacy.sightline_overrides:
        sightlines.append(SightLine(**s))

    map_obj = Map(
        id=doc.id,
        display_name=doc.display_name,
        sites=[Site(s) for s in doc.sites if s in [st.value for st in Site]],
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


def publish_document(map_id: str, data_dir: Path | None = None) -> dict[str, Any]:
    """Compiles in-memory structures, validates schemas, runs audits,
    renders guide, and performs a locked transactional promotion of all files.
    """
    studio_dir, runtime_dir, geometry_dir, guide_dir = _resolve_paths(data_dir)
    studio_path = studio_dir / f"{map_id}.yaml"
    
    if not studio_path.exists():
        raise FileNotFoundError(f"studio draft doc not found for: {map_id}")
        
    # Read draft doc
    doc = MapStudioDocumentV1(**yaml.safe_load(studio_path.read_text(encoding="utf-8")))
    
    # Compile
    map_obj, geo_obj = compile_document(doc)
    
    # Audits
    continuous_errors = audit_continuous(doc)
    legacy_errors = audit_map(map_obj, geo_obj)
    all_errors = continuous_errors + legacy_errors
    
    if all_errors:
        raise ValueError(f"Publish failed audits: {all_errors[0]}")
        
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
