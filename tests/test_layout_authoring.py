"""Reference registration, editable doors, and real draft simulation boundaries."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from esports_sim.registry import load_all, map_workbench
from esports_sim.registry import map_mcp_ops as ops
from esports_sim.registry.map_probe import probe_map
from esports_sim.schemas.studio import LayoutReference
from esports_sim.sim import engine
from esports_sim.web.server import map_studio_preview
from esports_sim.web import server


@pytest.fixture(autouse=True)
def local_studio_request():
    token = server._client_host_ctx.set("127.0.0.1")
    yield
    server._client_host_ctx.reset(token)


@pytest.mark.parametrize("name", ["ascent", "bind", "haven", "lotus", "split", "pearl", "fracture", "corrode", "abyss", "breeze", "sunset"])
def test_layout_variants_have_calibrated_references_and_reachable_plants(name):
    doc, _ = map_workbench.load_document(f"{name}-layout-v2")
    _, _, errors = map_workbench.validate_document(doc)
    assert errors == []
    assert doc.reference is not None
    root = Path(__file__).resolve().parents[1]
    with Image.open(root / doc.reference.image_path.lstrip("/")) as image:
        assert doc.reference.width / doc.reference.height == pytest.approx(image.width / image.height)
    plants = [z for z in doc.semantic_zones if z.kind == "plant"]
    assert sorted({z.site_id for z in plants}) == sorted(doc.sites)
    spawn = next(z for z in doc.semantic_zones if z.id == doc.attacker_spawn)
    reachable = probe_map(doc, spawn.label_position)["reachable_zones"]
    assert all(z.id in reachable for z in plants)


def test_reference_survives_revisioned_metadata_save_without_changing_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("ESPORTS_MAP_DATA_DIR", str(tmp_path / "data"))
    created = ops.create_map("registered-layout", "Registered layout", "two-site")
    before, _ = map_workbench.load_document("registered-layout", tmp_path / "data")
    reference = {"image_path": "/assets/maps/references/test.png", "description": "Test snapshot",
                 "source_sha256": "a" * 64, "width": 80, "height": 100}
    updated = ops.update_map_metadata("registered-layout", {"reference": reference}, created["revision_hash"])
    after, _ = map_workbench.load_document("registered-layout", tmp_path / "data")
    assert after.reference.image_path == reference["image_path"]
    assert map_workbench.compile_document(before) == map_workbench.compile_document(after)
    with pytest.raises(ops.MapMcpError, match="stale revision"):
        ops.update_map_metadata("registered-layout", {"reference": reference}, created["revision_hash"])
    assert updated["validation"]["valid"]
    with pytest.raises(ValidationError):
        LayoutReference(**{**reference, "image_path": "/assets/maps/references/../secret.png"})


def test_link_doorway_span_changes_the_physical_portal():
    doc = ops._two_site_document("doors", "Doors")
    links = [l.model_copy(update={"opening_span": (15, 20), "path_mode": "portal"})
             if l.id == "a_entry_to_site" else l for l in doc.traversal_links]
    doc = doc.model_copy(update={"traversal_links": links})
    _, geo, errors = map_workbench.validate_document(doc)
    assert errors == []
    assert geo.portal("a_entry", "a_site") == (17.5, 40)


def test_clearing_an_imported_doorway_does_not_restore_the_hidden_span():
    doc = ops._two_site_document("doors", "Doors")
    legacy = doc.legacy.model_copy(update={"opening_overrides": [
        {"between": ["a_entry", "a_site"], "span": [15, 20]}]})
    doc = doc.model_copy(update={"legacy": legacy})
    _, original_geo = map_workbench.compile_document(doc)
    assert original_geo.portal("a_entry", "a_site") == (17.5, 40)
    links = [l.model_copy(update={"opening_span": None, "override_opening": True})
             if l.id == "a_entry_to_site" else l for l in doc.traversal_links]
    _, changed_geo = map_workbench.compile_document(doc.model_copy(update={"traversal_links": links}))
    assert not changed_geo.openings


def test_visible_imported_routes_control_connectivity_without_changing_neighbor_order():
    doc, _ = map_workbench.load_document("ascent-layout-v2")
    before = doc.model_dump()
    original = map_workbench.compile_document(doc)
    assert doc.model_dump() == before
    authoritative = doc.model_copy(update={"links_define_adjacency": True})
    assert map_workbench.compile_document(authoritative) == original
    links = [l for l in authoritative.traversal_links if
             {l.from_pos[2], l.to_pos[2]} != {"surf_a_lobby", "surf_a_main"}]
    changed, _ = map_workbench.compile_document(authoritative.model_copy(update={"traversal_links": links}))
    assert "a_main" not in changed.adjacency["a_lobby"]
    assert "a_lobby" not in changed.adjacency["a_main"]


def test_explicit_draft_geometry_reaches_the_motor_resolver(monkeypatch):
    doc, _ = map_workbench.load_document("split-layout-v2")
    m, geo = map_workbench.compile_document(doc)
    gd = load_all()
    gd.maps[doc.id] = m
    def fail_disk_load(*args, **kwargs):
        raise AssertionError("draft simulation loaded live geometry")
    monkeypatch.setattr(engine, "load_geometry", fail_disk_load)
    sim = engine._MatchSim(gd, "team_nexus", "team_vanguard", doc.id, 11, geometry=geo)
    assert sim._geo is geo
    assert sim._geo.regions["b_site"].w == 37
    assert sim._free_movement is not None


def test_preview_uses_submitted_draft_and_never_writes_runtime(monkeypatch):
    doc, _ = map_workbench.load_document("ascent-layout-v2")
    map_path = Path(__file__).resolve().parents[1] / "data" / "maps" / "ascent.yaml"
    before = map_path.read_bytes()
    actual = engine.simulate_match_result
    geometry_seen = []
    def capture_geometry(*args, **kwargs):
        geometry_seen.append(kwargs["geometry"])
        return actual(*args, **kwargs)
    monkeypatch.setattr("esports_sim.sim.simulate_match_result", capture_geometry)
    result = map_studio_preview(doc.model_dump(mode="json"))
    assert result["map_id"] == doc.id
    assert result["events"][0]["type"] == "round.start"
    assert result["events"][-1]["type"] == "round.end"
    assert any(e["type"] == "round.control" for e in result["events"])
    assert len(result["players"]) == 10
    assert geometry_seen[0].regions["b_site"].w == 23.5
    assert map_path.read_bytes() == before


def test_preview_rejects_an_incomplete_map():
    with pytest.raises(HTTPException) as error:
        map_studio_preview({"id": "empty", "display_name": "Empty"})
    assert error.value.status_code == 422


@pytest.mark.parametrize('name', ['pearl','fracture','corrode','abyss','breeze','sunset'])
def test_additional_layout_floor_registration_and_transport_contract(name):
    from esports_sim.registry.map_reference import compare_reference
    doc,_=map_workbench.load_document(name+'-layout-v2')
    m,geo=map_workbench.compile_document(doc)
    assert doc.movement_model=='free'
    assert compare_reference(doc,grid_step=.25)['iou']>.90
    assert doc.reference.width==doc.reference.height==100
    for cid,r in geo.regions.items():
        assert all(r.contains(*slot[:2]) for slot in geo.room_slots(cid,.35))
    if name=='fracture':
        link=next(l for l in doc.traversal_links if l.id=='central_zipline')
        assert not link.runtime_enabled
        assert link.kind=='rope'
        assert not any(g.type=='teleporter' for g in m.gimmicks)
        assert not any(set(c.between)=={'attacker_spawn','attacker_side_bridge'} for c in geo.corridors)


def test_recorded_traversal_does_not_create_runtime_adjacency_or_probe_reachability():
    from esports_sim.schemas.studio import TraversalLink
    doc=ops._two_site_document('recorded','Recorded')
    baseline,_=map_workbench.compile_document(doc)
    a,b=doc.walkable_surfaces[:2]
    link=TraversalLink(id='unsupported',kind='rope',from_pos=[*a.polygon[0],a.id],to_pos=[*b.polygon[0],b.id],runtime_enabled=False)
    doc=doc.model_copy(update={'traversal_links':[*doc.traversal_links,link]})
    actual,_=map_workbench.compile_document(doc)
    assert actual==baseline


def test_plant_overlay_can_span_existing_callout_floor_without_duplicating_it():
    doc=ops._two_site_document('multi-floor-plant','Multi-floor plant')
    a=next(z for z in doc.semantic_zones if z.id=='a_site')
    plant=next(z for z in doc.semantic_zones if z.id=='a_plant')
    plant=plant.model_copy(update={'surface_ids':['surf_a_site','surf_a_entry']})
    doc=doc.model_copy(update={'semantic_zones':[plant if z.id==plant.id else z for z in doc.semantic_zones]})
    m,geo,errors=map_workbench.validate_document(doc)
    assert not errors
    assert 'a_plant' not in geo.regions
    assert 'a_plant' not in m.callouts
    reachable=probe_map(doc,a.label_position)['reachable_zones']
    assert 'a_plant' in reachable


def test_floor_comparison_measures_full_blockers_but_keeps_half_cover(tmp_path, monkeypatch):
    from esports_sim.registry import map_reference
    from esports_sim.schemas.studio import Prop
    root = tmp_path / "assets/maps/references"
    root.mkdir(parents=True)
    Image.new("RGB", (100, 100), (118, 118, 118)).save(root / "test.png")
    monkeypatch.setattr(map_reference, "ROOT", tmp_path)
    doc = ops._two_site_document("test", "Test")
    doc = doc.model_copy(update={"reference": LayoutReference(
        image_path="/assets/maps/references/test.png", description="Test",
        source_sha256="a" * 64, width=100, height=100)})
    surf = doc.walkable_surfaces[0]
    x, y = surf.polygon[0]
    footprint = [(x+2,y+2),(x+4,y+2),(x+4,y+4),(x+2,y+4)]
    baseline = map_reference.compare_reference(doc)
    full = Prop(id="mask", surface_id=surf.id, footprint=footprint, height="full")
    blocked = map_reference.compare_reference(doc.model_copy(update={"props": [full]}))
    covered = map_reference.compare_reference(doc.model_copy(update={"props": [full.model_copy(update={"height":"half"})]}))
    assert blocked["missing_area"] == baseline["missing_area"] + 4
    assert covered["missing_area"] == baseline["missing_area"]


def test_rectangle_packing_never_bridges_a_reference_floor_hole():
    import numpy as np
    from esports_sim.registry.map_reference import largest_rectangles, rectangle_mask
    mask = np.ones((12, 12), dtype=bool)
    mask[4:8,4:8] = False
    xs, ys = np.meshgrid((np.arange(12)+0.5)*0.5, (np.arange(12)+0.5)*0.5)
    packed = np.zeros_like(mask)
    for rect in largest_rectangles(mask, 0, 0, 1):
        cells = rectangle_mask(xs, ys, **rect)
        assert not np.any(cells & ~mask)
        assert not np.any(cells & packed)
        packed |= cells
    assert np.array_equal(mask, packed)


def test_comparison_rejects_missing_reference_and_remote_admin():
    doc = ops._two_site_document("no-ref", "No reference")
    with pytest.raises(HTTPException) as error:
        server.map_studio_compare_floor(doc.model_dump(mode="json"))
    assert error.value.status_code == 422
    token = server._client_host_ctx.set("203.0.113.8")
    try:
        with pytest.raises(HTTPException) as error:
            server.map_studio_compare_floor(doc.model_dump(mode="json"))
        assert error.value.status_code == 403
    finally:
        server._client_host_ctx.reset(token)


def test_solid_wall_masks_do_not_create_cover_slots_or_blocked_holding_positions():
    from esports_sim.schemas.studio import Prop
    doc = ops._two_site_document("walls", "Walls")
    surf = doc.walkable_surfaces[0]
    x, y = surf.polygon[0]
    footprint = [(x+1,y+1),(x+8,y+1),(x+8,y+8),(x+1,y+8)]
    prop = Prop(id="solid", surface_id=surf.id, footprint=footprint, height="full", role="wall")
    _, geo = map_workbench.compile_document(doc.model_copy(update={"props":[prop]}))
    region_id = geo.props[0].region
    slots = geo.room_slots(region_id, 0.35)
    assert slots
    assert not any(kind == "cover" for _,_,kind in slots)
    assert not any(x+0.65 <= px <= x+8.35 and y+0.65 <= py <= y+8.35 for px,py,_ in slots)
    assert geo.props[0].role == "wall"


def test_floor_extensions_add_physical_floor_without_moving_routes():
    from esports_sim.schemas.geometry import FloorRect
    from esports_sim.sim.free_movement import FreeMovementResolver
    doc = ops._two_site_document("extensions", "Extensions")
    doc = doc.model_copy(update={"props": []})
    original_map, original_geo = map_workbench.compile_document(doc)
    surf = doc.walkable_surfaces[0]
    region_id = next(z.id for z in doc.semantic_zones if surf.id in z.surface_ids)
    core = original_geo.regions[region_id]
    extension = FloorRect(x=core.x+core.w-.01, y=core.y+2, w=8, h=4)
    modified = surf.model_copy(update={"floor_extensions":[extension]})
    revised = doc.model_copy(update={"walkable_surfaces":[modified, *doc.walkable_surfaces[1:]]})
    m, geo, errors = map_workbench.validate_document(revised)
    assert errors == []
    assert geo.regions[region_id].cx == core.cx
    assert geo.regions[region_id].cy == core.cy
    for a, neighbors in original_map.adjacency.items():
        for b in neighbors:
            assert geo.path(a,b) == original_geo.path(a,b)
    point = (extension.x+5, extension.y+2)
    assert not core.contains(*point)
    assert geo.regions[region_id].contains(*point)
    resolver = FreeMovementResolver(m,geo,player_radius=.35,collision_step=.2)
    assert region_id in resolver.regions_at(*point)
    probe = probe_map(revised, point)
    assert probe["surface_id"] == surf.id
    assert probe["zone_id"] == region_id
    # The seam into the extension is no longer a virtual room boundary.
    probe = probe_map(revised,(core.x+core.w-.2,extension.y+2))
    assert probe['clearance'] >= 1


def test_holding_position_routes_use_clear_room_center_when_wall_blocks_shortcut():
    from esports_sim.schemas.geometry import MapGeometry, Region, Prop as GeoProp, _segment_hits_rect
    geometry = MapGeometry(map_id="corner", regions={"room": Region(x=0,y=0,w=20,h=20)},
        props=[GeoProp(region="room",x=4,y=4,w=4,h=4,height="full",role="wall")])
    start, end = (2.,10.), (10.,2.)
    assert _segment_hits_rect(*start,*end,3.65,3.65,4.7,4.7)
    route = geometry.path_between_points("room","room",start,end,.35)
    assert route == [start,(10.,10.),end]
    assert not any(_segment_hits_rect(*a,*b,3.65,3.65,4.7,4.7) for a,b in zip(route,route[1:]))
    # Existing crate geometry retains its authored legacy route behavior.
    legacy = geometry.model_copy(update={"props":[geometry.props[0].model_copy(update={"role":"cover"})]})
    assert legacy.path_between_points("room","room",start,end,.35) == [start,end]


def test_floor_extension_los_detects_a_gap_between_floor_parts():
    from esports_sim.schemas.geometry import FloorRect, Region, MapGeometry
    from esports_sim.sim.free_movement import FreeMovementResolver
    doc = ops._two_site_document("gap", "Gap")
    m, _ = map_workbench.compile_document(doc)
    rid = doc.attacker_spawn
    geo = MapGeometry(map_id=doc.id,regions={rid:Region(x=0,y=0,w=10,h=10,
        floor_extensions=[FloorRect(x=14,y=0,w=6,h=2)])})
    resolver = FreeMovementResolver(m,geo,player_radius=.35,collision_step=.2)
    assert not resolver.has_line_of_sight(9,1,rid,18,1,rid)


def test_disconnected_floor_extension_is_rejected():
    from esports_sim.schemas.geometry import FloorRect
    doc = ops._two_site_document("island", "Island")
    surf = doc.walkable_surfaces[0]
    revised = doc.model_copy(update={"walkable_surfaces":[
        surf.model_copy(update={"floor_extensions":[FloorRect(x=90,y=90,w=2,h=2)]}),
        *doc.walkable_surfaces[1:]]})
    _,_,errors = map_workbench.validate_document(revised)
    assert any('disconnected floor extensions' in e['message'] for e in errors)


def test_floor_audit_accepts_route_supported_by_connected_extensions():
    from types import SimpleNamespace
    from esports_sim.registry.map_audit import audit_map
    from esports_sim.schemas.geometry import MapGeometry, Region, FloorRect, Corridor
    geometry = MapGeometry(map_id="extension-route", regions={
        "a": Region(x=0,y=0,w=10,h=10,
                    floor_extensions=[FloorRect(x=10,y=0,w=10,h=4)]),
        "b": Region(x=20,y=0,w=10,h=10)},
        corridors=[Corridor(between=("a","b"),via=[(11,2),(19,2)])])
    map_obj = SimpleNamespace(callouts={
        "a": SimpleNamespace(x=5,y=5), "b": SimpleNamespace(x=25,y=5)},
        adjacency={"a":["b"],"b":["a"]},gimmicks=[])
    assert audit_map(map_obj,geometry) == []
    no_extension = geometry.model_copy(update={"regions":{
        **geometry.regions, "a": geometry.regions["a"].model_copy(update={"floor_extensions":[]})}})
    findings = audit_map(map_obj,no_extension)
    assert any("detached plates" in f for f in findings)
    assert any("path in void" in f for f in findings)
