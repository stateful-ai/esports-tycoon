"""Revision-safe operations for AI and human Map Studio co-authoring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from esports_sim.registry import map_probe, map_workbench
from esports_sim.registry.loader import DEFAULT_DATA_DIR
from esports_sim.schemas.map import SightLine
from esports_sim.schemas.studio import (
    MapStudioDocumentV1,
    EditorState,
    Prop,
    SemanticZone,
    TraversalLink,
    WalkableSurface,
    Wall,
)

ElementType = Literal["surface", "zone", "prop", "wall", "link"]


class MapMcpError(ValueError):
    """A safe, actionable error for a Map Studio MCP caller."""


class MapRemoval(BaseModel):
    """One stable-id element removal inside a transactional map patch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    element_type: ElementType
    element_id: str


def _data_dir() -> Path:
    override = os.environ.get("ESPORTS_MAP_DATA_DIR")
    return (
        Path(override).expanduser().resolve()
        if override
        else DEFAULT_DATA_DIR.resolve()
    )


def _model_error(exc: ValidationError) -> MapMcpError:
    first = exc.errors(include_url=False)[0]
    path = ".".join(str(part) for part in first["loc"])
    return MapMcpError(f"{path or 'element'}: {first['msg']}")


def _parse(model_type: type[BaseModel], value: BaseModel | dict[str, Any]) -> BaseModel:
    if isinstance(value, model_type):
        return value
    try:
        return model_type.model_validate(value)
    except ValidationError as exc:
        raise _model_error(exc) from exc


def _read(map_id: str) -> tuple[MapStudioDocumentV1, str]:
    try:
        return map_workbench.load_document(map_id, _data_dir())
    except FileNotFoundError as exc:
        raise MapMcpError(
            f"no map {map_id!r}; call create_map or open_map_for_editing first"
        ) from exc


def _validation(doc: MapStudioDocumentV1) -> dict[str, Any]:
    _, _, errors = map_workbench.validate_document(doc)
    return {"valid": not errors, "errors": errors}


def _studio_path(map_id: str) -> Path:
    studio_dir, _, _, _ = map_workbench._resolve_paths(_data_dir())
    return studio_dir / f"{map_id}.yaml"


def _view(
    doc: MapStudioDocumentV1,
    revision_hash: str,
    *,
    changed: dict[str, Any] | None = None,
    include_document: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "map_id": doc.id,
        "revision_hash": revision_hash,
        "studio_path": str(_studio_path(doc.id)),
        "ui_path": f"/map-studio.html?map={doc.id}",
        "changed": changed,
        "validation": _validation(doc),
    }
    if include_document:
        result["document"] = doc.model_dump(mode="json")
    return result


def _mutate(
    map_id: str,
    if_match_hash: str,
    change: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    if not if_match_hash:
        raise MapMcpError("if_match_hash is required for every map mutation")
    doc, current_hash = _read(map_id)
    if current_hash != if_match_hash:
        raise MapMcpError(
            "stale revision hash; call get_map, reconcile the human/AI changes, "
            "then retry with the new revision_hash"
        )
    raw = doc.model_dump(mode="json")
    changed = change(raw)
    try:
        result = map_workbench.save_document(
            map_id,
            raw,
            if_match_hash=if_match_hash,
            data_dir=_data_dir(),
        )
    except (TimeoutError, ValueError) as exc:
        if "stale revision" in str(exc):
            raise MapMcpError(
                "stale revision hash; another editor saved first; call get_map "
                "and reconcile before retrying"
            ) from exc
        raise MapMcpError(str(exc)) from exc
    if not result.get("valid"):
        first = result.get("errors", [{"message": "invalid Studio document"}])[0]
        raise MapMcpError(first["message"])
    updated, updated_hash = _read(map_id)
    return _view(updated, updated_hash, changed=changed)


def _upsert(
    raw: dict[str, Any],
    collection: str,
    element: dict[str, Any],
    element_id: str,
) -> dict[str, Any]:
    rows = raw[collection]
    for index, row in enumerate(rows):
        existing_id = row.get("id") or (
            f"wall_{index}" if collection == "walls" else None
        )
        if existing_id == element_id:
            rows[index] = element
            return {"operation": "updated", "type": collection, "id": element_id}
    rows.append(element)
    return {"operation": "added", "type": collection, "id": element_id}


def _remove(raw: dict[str, Any], element_type: ElementType, element_id: str) -> None:
    collections = {
        "surface": "walkable_surfaces",
        "zone": "semantic_zones",
        "prop": "props",
        "wall": "walls",
        "link": "traversal_links",
    }
    collection = collections[element_type]
    rows = raw[collection]
    matches = [
        index for index, row in enumerate(rows)
        if (row.get("id") or (f"wall_{index}" if collection == "walls" else None))
        == element_id
    ]
    if not matches:
        raise MapMcpError(f"{element_type} {element_id!r} does not exist")
    rows.pop(matches[0])


def _unique_ids(label: str, elements: list[BaseModel]) -> None:
    ids = [str(getattr(element, "id", "")) for element in elements]
    duplicates = sorted({element_id for element_id in ids if ids.count(element_id) > 1})
    if duplicates:
        raise MapMcpError(f"duplicate {label} ids in patch: {duplicates}")


def _removal_sort_key(removal: MapRemoval) -> tuple[int, int]:
    """Remove synthetic legacy walls back-to-front so indexes stay stable."""
    if (
        removal.element_type == "wall"
        and removal.element_id.startswith("wall_")
        and removal.element_id[5:].isdigit()
    ):
        return (0, -int(removal.element_id[5:]))
    return (1, 0)


def _empty_document(map_id: str, display_name: str) -> MapStudioDocumentV1:
    return MapStudioDocumentV1(id=map_id, display_name=display_name)


def _two_site_document(map_id: str, display_name: str) -> MapStudioDocumentV1:
    rectangles = {
        "attacker_spawn": (40.0, 0.0, 60.0, 20.0),
        "a_entry": (10.0, 20.0, 50.0, 40.0),
        "b_entry": (50.0, 20.0, 90.0, 40.0),
        "a_site": (10.0, 40.0, 40.0, 65.0),
        "b_site": (60.0, 40.0, 90.0, 65.0),
        "defender_spawn": (30.0, 65.0, 70.0, 85.0),
    }

    def polygon(bounds: tuple[float, float, float, float]) -> list[tuple[float, float]]:
        x1, y1, x2, y2 = bounds
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    surfaces = [
        WalkableSurface(id=f"surf_{zone_id}", polygon=polygon(bounds))
        for zone_id, bounds in rectangles.items()
    ]
    zones = []
    for zone_id, bounds in rectangles.items():
        x1, y1, x2, y2 = bounds
        if zone_id.endswith("_spawn"):
            kind = "spawn"
            legacy_zone = zone_id
        elif zone_id.endswith("_site"):
            kind = "site"
            legacy_zone = "site"
        else:
            kind = "callout"
            legacy_zone = "attacker_side"
        site_id = zone_id[0] if zone_id.startswith(("a_", "b_")) else "none"
        zones.append(SemanticZone(
            id=zone_id,
            display_name=zone_id.replace("_", " ").title(),
            kind=kind,
            polygon=polygon(bounds),
            surface_ids=[f"surf_{zone_id}"],
            label_position=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            site_id=site_id,
            legacy_zone=legacy_zone,
        ))
    zones.extend([
        SemanticZone(
            id="a_plant",
            display_name="A Plant",
            kind="plant",
            polygon=polygon((17.0, 47.0, 33.0, 58.0)),
            surface_ids=["surf_a_site"],
            label_position=(25.0, 52.5),
            site_id="a",
        ),
        SemanticZone(
            id="b_plant",
            display_name="B Plant",
            kind="plant",
            polygon=polygon((67.0, 47.0, 83.0, 58.0)),
            surface_ids=["surf_b_site"],
            label_position=(75.0, 52.5),
            site_id="b",
        ),
    ])
    links = [
        TraversalLink(id="atk_to_a", kind="ramp", from_pos=(45, 19, "surf_attacker_spawn"), to_pos=(45, 21, "surf_a_entry")),
        TraversalLink(id="atk_to_b", kind="ramp", from_pos=(55, 19, "surf_attacker_spawn"), to_pos=(55, 21, "surf_b_entry")),
        TraversalLink(id="a_entry_to_site", kind="ramp", from_pos=(25, 39, "surf_a_entry"), to_pos=(25, 41, "surf_a_site")),
        TraversalLink(id="b_entry_to_site", kind="ramp", from_pos=(75, 39, "surf_b_entry"), to_pos=(75, 41, "surf_b_site")),
        TraversalLink(id="a_site_to_def", kind="ramp", from_pos=(35, 64, "surf_a_site"), to_pos=(35, 66, "surf_defender_spawn")),
        TraversalLink(id="b_site_to_def", kind="ramp", from_pos=(65, 64, "surf_b_site"), to_pos=(65, 66, "surf_defender_spawn")),
    ]
    return MapStudioDocumentV1(
        id=map_id,
        display_name=display_name,
        sites=["a", "b"],
        attacker_spawn="attacker_spawn",
        defender_spawn="defender_spawn",
        walkable_surfaces=surfaces,
        semantic_zones=zones,
        traversal_links=links,
    )


def get_map_schema() -> dict[str, Any]:
    """Return the authoritative Studio schema and co-editing contract."""
    return {
        "document_schema": MapStudioDocumentV1.model_json_schema(),
        "element_schemas": {
            "walkable_surface": WalkableSurface.model_json_schema(),
            "semantic_zone": SemanticZone.model_json_schema(),
            "wall": Wall.model_json_schema(),
            "prop": Prop.model_json_schema(),
            "traversal_link": TraversalLink.model_json_schema(),
            "sightline": SightLine.model_json_schema(),
            "removal": MapRemoval.model_json_schema(),
        },
        "authoring_contract": {
            "source_of_truth": "data/maps/studio/<map_id>.yaml",
            "runtime_artifacts": [
                "data/maps/<map_id>.yaml",
                "data/maps/geometry/<map_id>.yaml",
                "assets/maps/guides/<map_id>.png",
            ],
            "runtime_compile_limits": [
                "walkable surfaces and prop footprints must be axis-aligned rectangles",
                "each navigational semantic zone maps to exactly one surface",
                "plant zones are overlays that share their site's surface",
                "each non-plant zone needs a tactical legacy_zone",
                "traversal endpoints and corridor points must remain on walkable floor",
            ],
            "collaboration": (
                "Pass the latest revision_hash as if_match_hash on every mutation. "
                "On a stale-revision error, call get_map and reconcile; never blind-retry."
            ),
            "recommended_workflow": [
                "fork_map for a non-destructive variant or create_map for a new layout",
                "apply_map_patch for each coherent generated slice",
                "validate_map and probe_map_geometry before human review",
                "publish_map only after explicit approval and runtime gates",
            ],
        },
    }


def list_maps() -> dict[str, Any]:
    return {"maps": map_workbench.list_documents(_data_dir())}


def create_map(
    map_id: str,
    display_name: str,
    template: Literal["empty", "two-site"] = "empty",
) -> dict[str, Any]:
    doc = (
        _two_site_document(map_id, display_name)
        if template == "two-site"
        else _empty_document(map_id, display_name)
    )
    try:
        result = map_workbench.create_document(
            map_id, doc.model_dump(mode="json"), _data_dir()
        )
    except (FileExistsError, TimeoutError, ValueError) as exc:
        raise MapMcpError(str(exc)) from exc
    return _view(doc, result["hash"], include_document=True)


def fork_map(
    source_map_id: str,
    new_map_id: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Create a non-destructive Studio variant from a draft or legacy map."""
    source, _ = _read(source_map_id)
    raw = source.model_dump(mode="json")
    raw["id"] = new_map_id
    raw["display_name"] = display_name or f"{source.display_name} Variant"
    raw["editor_state"] = EditorState().model_dump(mode="json")
    try:
        result = map_workbench.create_document(new_map_id, raw, _data_dir())
    except (FileExistsError, TimeoutError, ValueError) as exc:
        raise MapMcpError(str(exc)) from exc
    doc = MapStudioDocumentV1.model_validate(raw)
    return _view(doc, result["hash"], include_document=True)


def open_map_for_editing(map_id: str) -> dict[str, Any]:
    """Materialize a legacy map as the shared Studio source when necessary."""
    doc, revision_hash = _read(map_id)
    if not _studio_path(map_id).exists():
        try:
            result = map_workbench.save_document(
                map_id,
                doc.model_dump(mode="json"),
                if_match_hash=revision_hash,
                data_dir=_data_dir(),
            )
        except (TimeoutError, ValueError) as exc:
            raise MapMcpError(str(exc)) from exc
        revision_hash = result["hash"]
    doc, revision_hash = _read(map_id)
    return _view(doc, revision_hash, include_document=True)


def get_map(map_id: str) -> dict[str, Any]:
    doc, revision_hash = _read(map_id)
    return _view(doc, revision_hash, include_document=True)


def validate_map(map_id: str) -> dict[str, Any]:
    doc, revision_hash = _read(map_id)
    return _view(doc, revision_hash)


def update_map_metadata(
    map_id: str,
    changes: dict[str, Any],
    if_match_hash: str,
) -> dict[str, Any]:
    allowed = {"display_name", "sites", "attacker_spawn", "defender_spawn"}
    unknown = set(changes) - allowed
    if unknown:
        raise MapMcpError(f"unsupported metadata fields: {sorted(unknown)}")

    def change(raw: dict[str, Any]) -> dict[str, Any]:
        raw.update(changes)
        return {"operation": "metadata", "fields": sorted(changes)}

    return _mutate(map_id, if_match_hash, change)


def apply_map_patch(
    map_id: str,
    if_match_hash: str,
    metadata: dict[str, Any] | None = None,
    walkable_surfaces: list[WalkableSurface | dict[str, Any]] | None = None,
    semantic_zones: list[SemanticZone | dict[str, Any]] | None = None,
    props: list[Prop | dict[str, Any]] | None = None,
    walls: list[Wall | dict[str, Any]] | None = None,
    traversal_links: list[TraversalLink | dict[str, Any]] | None = None,
    sightlines: list[SightLine | dict[str, Any]] | None = None,
    adjacency_overrides: dict[str, list[str]] | None = None,
    prop_support_exemptions: list[str] | None = None,
    removals: list[MapRemoval | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply a coherent typed element batch in one revision-locked save."""
    metadata = metadata or {}
    allowed_metadata = {"display_name", "sites", "attacker_spawn", "defender_spawn"}
    unknown = set(metadata) - allowed_metadata
    if unknown:
        raise MapMcpError(f"unsupported metadata fields: {sorted(unknown)}")

    parsed_surfaces = [
        _parse(WalkableSurface, value) for value in (walkable_surfaces or [])
    ]
    parsed_zones = [_parse(SemanticZone, value) for value in (semantic_zones or [])]
    parsed_props = [_parse(Prop, value) for value in (props or [])]
    parsed_walls = [_parse(Wall, value) for value in (walls or [])]
    parsed_links = [
        _parse(TraversalLink, value) for value in (traversal_links or [])
    ]
    parsed_sightlines = (
        [_parse(SightLine, value) for value in sightlines]
        if sightlines is not None
        else None
    )
    parsed_removals = [_parse(MapRemoval, value) for value in (removals or [])]

    for wall in parsed_walls:
        if not isinstance(wall, Wall) or not wall.id:
            raise MapMcpError("wall.id is required for MCP co-editing")
    _unique_ids("surface", parsed_surfaces)
    _unique_ids("zone", parsed_zones)
    _unique_ids("prop", parsed_props)
    _unique_ids("wall", parsed_walls)
    _unique_ids("link", parsed_links)

    def change(raw: dict[str, Any]) -> dict[str, Any]:
        raw.update(metadata)
        ordered_removals = sorted(parsed_removals, key=_removal_sort_key)
        for removal in ordered_removals:
            assert isinstance(removal, MapRemoval)
            _remove(raw, removal.element_type, removal.element_id)
        batches = [
            ("walkable_surfaces", parsed_surfaces),
            ("semantic_zones", parsed_zones),
            ("props", parsed_props),
            ("walls", parsed_walls),
            ("traversal_links", parsed_links),
        ]
        for collection, elements in batches:
            for element in elements:
                element_id = str(getattr(element, "id"))
                _upsert(raw, collection, element.model_dump(mode="json"), element_id)
        if parsed_sightlines is not None:
            raw["legacy"]["sightline_overrides"] = [
                item.model_dump(mode="json") for item in parsed_sightlines
            ]
        if adjacency_overrides is not None:
            raw["legacy"]["adjacency_overrides"] = adjacency_overrides
        if prop_support_exemptions is not None:
            raw["legacy"]["prop_support_exemptions"] = prop_support_exemptions
        return {
            "operation": "batch_patch",
            "metadata_fields": sorted(metadata),
            "upserted": {
                "surfaces": len(parsed_surfaces),
                "zones": len(parsed_zones),
                "props": len(parsed_props),
                "walls": len(parsed_walls),
                "links": len(parsed_links),
                "sightlines": (
                    len(parsed_sightlines) if parsed_sightlines is not None else None
                ),
                "adjacency_overrides": (
                    len(adjacency_overrides)
                    if adjacency_overrides is not None
                    else None
                ),
                "prop_support_exemptions": (
                    len(prop_support_exemptions)
                    if prop_support_exemptions is not None
                    else None
                ),
            },
            "removed": len(parsed_removals),
        }

    return _mutate(map_id, if_match_hash, change)


def upsert_walkable_surface(
    map_id: str, surface: WalkableSurface | dict[str, Any], if_match_hash: str
) -> dict[str, Any]:
    parsed = _parse(WalkableSurface, surface)
    assert isinstance(parsed, WalkableSurface)
    return _mutate(map_id, if_match_hash, lambda raw: _upsert(
        raw, "walkable_surfaces", parsed.model_dump(mode="json"), parsed.id
    ))


def upsert_semantic_zone(
    map_id: str, zone: SemanticZone | dict[str, Any], if_match_hash: str
) -> dict[str, Any]:
    parsed = _parse(SemanticZone, zone)
    assert isinstance(parsed, SemanticZone)
    return _mutate(map_id, if_match_hash, lambda raw: _upsert(
        raw, "semantic_zones", parsed.model_dump(mode="json"), parsed.id
    ))


def upsert_prop(
    map_id: str, prop: Prop | dict[str, Any], if_match_hash: str
) -> dict[str, Any]:
    parsed = _parse(Prop, prop)
    assert isinstance(parsed, Prop)
    return _mutate(map_id, if_match_hash, lambda raw: _upsert(
        raw, "props", parsed.model_dump(mode="json"), parsed.id
    ))


def upsert_wall(
    map_id: str, wall: Wall | dict[str, Any], if_match_hash: str
) -> dict[str, Any]:
    parsed = _parse(Wall, wall)
    assert isinstance(parsed, Wall)
    if not parsed.id:
        raise MapMcpError("wall.id is required for MCP co-editing")
    return _mutate(map_id, if_match_hash, lambda raw: _upsert(
        raw, "walls", parsed.model_dump(mode="json"), parsed.id or ""
    ))


def upsert_traversal_link(
    map_id: str, link: TraversalLink | dict[str, Any], if_match_hash: str
) -> dict[str, Any]:
    parsed = _parse(TraversalLink, link)
    assert isinstance(parsed, TraversalLink)
    return _mutate(map_id, if_match_hash, lambda raw: _upsert(
        raw, "traversal_links", parsed.model_dump(mode="json"), parsed.id
    ))


def remove_map_element(
    map_id: str,
    element_type: ElementType,
    element_id: str,
    if_match_hash: str,
) -> dict[str, Any]:
    def change(raw: dict[str, Any]) -> dict[str, Any]:
        _remove(raw, element_type, element_id)
        return {"operation": "removed", "type": element_type, "id": element_id}

    return _mutate(map_id, if_match_hash, change)


def set_sightlines(
    map_id: str,
    sightlines: list[SightLine | dict[str, Any]],
    if_match_hash: str,
) -> dict[str, Any]:
    parsed: list[SightLine] = []
    for value in sightlines:
        item = _parse(SightLine, value)
        assert isinstance(item, SightLine)
        parsed.append(item)

    def change(raw: dict[str, Any]) -> dict[str, Any]:
        raw["legacy"]["sightline_overrides"] = [
            item.model_dump(mode="json") for item in parsed
        ]
        return {"operation": "sightlines", "count": len(parsed)}

    return _mutate(map_id, if_match_hash, change)


def probe_map_geometry(
    map_id: str,
    from_pos: tuple[float, float],
    to_pos: tuple[float, float] | None = None,
    player_radius: float = 1.0,
) -> dict[str, Any]:
    doc, revision_hash = _read(map_id)
    return {
        "map_id": map_id,
        "revision_hash": revision_hash,
        "probe": map_probe.probe_map(doc, from_pos, to_pos, player_radius),
    }


def publish_map(map_id: str, if_match_hash: str) -> dict[str, Any]:
    """Compile an explicitly approved Studio revision into runtime artifacts."""
    if not if_match_hash:
        raise MapMcpError("if_match_hash is required to publish")
    try:
        result = map_workbench.publish_document(
            map_id, _data_dir(), if_match_hash=if_match_hash
        )
    except (FileNotFoundError, TimeoutError, ValueError, RuntimeError) as exc:
        raise MapMcpError(str(exc)) from exc
    return {"map_id": map_id, "ui_path": f"/map-studio.html?map={map_id}", **result}
