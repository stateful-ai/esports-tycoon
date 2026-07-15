"""Unit tests for Map Studio backend, compiler, audits, and transform parity.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import pytest

from esports_sim.registry import load_all, map_workbench
from esports_sim.registry.map_audit import audit_continuous, audit_map
from esports_sim.registry.loader import load_geometry, load_map
from esports_sim.registry.map_guide_renderer import iso
from esports_sim.schemas.map import CalloutZone, Site
from esports_sim.schemas.studio import MapStudioDocumentV1
from esports_sim.sim import engine
from esports_sim.web.server import app, map_studio_create, map_studio_validate


def test_map_studio_mutation_routes_inject_the_http_request():
    """FastAPI must not mistake the Request object for a query parameter."""
    schema = app.openapi()
    for path, method in (
        ("/api/map-studio/maps/{map_id}", "put"),
        ("/api/map-studio/maps/{map_id}/publish", "post"),
    ):
        parameters = schema["paths"][path][method].get("parameters", [])
        assert "request" not in {item["name"] for item in parameters}


@pytest.mark.parametrize(
    "map_id",
    [
        "ascent_reference",
        "bind_reference",
        "breeze_reference",
        "haven_reference",
        "lotus_reference",
    ],
)
def test_reference_map_drafts_remain_compilable(map_id: str):
    doc, revision_hash = map_workbench.load_document(map_id)
    map_obj, geometry, errors = map_workbench.validate_document(doc)

    assert revision_hash
    assert errors == []
    assert map_obj is not None
    assert geometry is not None


def test_transform_parity_with_node():
    """Verify that MapTransform.projectGridToIso matches Python's iso() function.
    Executes the actual JavaScript file in a Node process.
    """
    js_path = Path(__file__).resolve().parents[1] / "src" / "esports_sim" / "web" / "static" / "map-transform.js"
    assert js_path.is_file()

    # Known points to sweep: (0,0), (100,0), (0,100), (100,100), (50,50)
    # with elevations 0, 5.0
    test_points = [
        (0.0, 0.0, 0.0),
        (100.0, 0.0, 0.0),
        (0.0, 100.0, 0.0),
        (100.0, 100.0, 0.0),
        (50.0, 50.0, 0.0),
        (25.0, 75.0, 5.0),
    ]

    for gx, gy, z in test_points:
        # Python projection
        py_ix, py_iy = iso(gx, gy)
        py_iy_elevated = py_iy - z

        # Node projection
        node_code = (
            f"const T = require('{js_path.as_posix()}'); "
            f"console.log(JSON.stringify(T.projectGridToIso({gx}, {gy}, {z})));"
        )
        res = subprocess.run(["node", "-e", node_code], capture_output=True, text=True)
        assert res.returncode == 0, f"Node script failed: {res.stderr}"
        
        js_x, js_y = json.loads(res.stdout.strip())

        assert py_ix == pytest.approx(js_x), f"Mismatch X at {gx},{gy}: py={py_ix} js={js_x}"
        assert py_iy_elevated == pytest.approx(js_y), f"Mismatch Y at {gx},{gy},{z}: py={py_iy_elevated} js={js_y}"


def test_malicious_map_ids():
    # Check invalid map id format raises ValueError from pydantic or workbench validation
    with pytest.raises(Exception):
        map_studio_create({"id": "../escape", "display_name": "Test"})
    
    with pytest.raises(Exception):
        map_studio_create({"id": "sub/dir", "display_name": "Test"})


@pytest.mark.parametrize("map_id", ["ascent", "bind", "haven", "lotus", "split"])
def test_workbench_synthesis_is_exact_runtime_roundtrip(map_id):
    """Opening and publishing an existing map must not change match behavior."""
    doc = map_workbench.synthesize_document(map_id)
    map_obj, geo_obj = map_workbench.compile_document(doc)

    assert map_obj == load_map(map_id)
    assert geo_obj == load_geometry(map_id)
    assert audit_continuous(doc) == []
    assert audit_map(map_obj, geo_obj) == []
    assert map_studio_validate(doc.model_dump(mode="json")) == {
        "valid": True,
        "errors": [],
    }


def test_studio_map_compiles_into_player_motor_route(monkeypatch):
    """Studio endpoints/via points feed the per-tick movement contract."""
    doc = MapStudioDocumentV1(
        id="studio-motor",
        display_name="Studio Motor",
        sites=[],  # inferred from the site and plant overlays
        attacker_spawn="attacker_spawn",
        defender_spawn="defender_spawn",
        walkable_surfaces=[
            {"id": "surf_atk", "polygon": [(0, 0), (20, 0), (20, 10), (0, 10)]},
            {"id": "surf_site", "polygon": [(20, 0), (50, 0), (50, 10), (20, 10)]},
            {"id": "surf_def", "polygon": [(40, 10), (50, 10), (50, 20), (40, 20)]},
        ],
        semantic_zones=[
            {
                "id": "attacker_spawn", "display_name": "Attack Spawn", "kind": "spawn",
                "polygon": [(0, 0), (20, 0), (20, 10), (0, 10)],
                "surface_ids": ["surf_atk"], "label_position": (10, 5),
            },
            {
                "id": "a_site", "display_name": "A Site", "kind": "site",
                "polygon": [(20, 0), (50, 0), (50, 10), (20, 10)],
                "surface_ids": ["surf_site"], "label_position": (35, 5), "site_id": "a",
            },
            {
                "id": "a_plant", "kind": "plant",
                "polygon": [(42, 2), (48, 2), (48, 8), (42, 8)],
                "surface_ids": ["surf_site"], "label_position": (45, 5), "site_id": "a",
            },
            {
                "id": "defender_spawn", "display_name": "Defense Spawn", "kind": "spawn",
                "polygon": [(40, 10), (50, 10), (50, 20), (40, 20)],
                "surface_ids": ["surf_def"], "label_position": (45, 15),
            },
        ],
        traversal_links=[
            {
                "id": "atk_to_a", "kind": "ramp",
                "from_pos": (19, 5, "surf_atk"), "to_pos": (21, 5, "surf_site"),
                "via": [(19, 8), (30, 8)], "noise_radius": 0,
            },
            {
                "id": "def_to_a", "kind": "ramp",
                "from_pos": (45, 11, "surf_def"), "to_pos": (45, 9, "surf_site"),
                "noise_radius": 0,
            },
        ],
        walls=[{"polyline": [(48, 2), (48, 8)], "thickness": 1.0}],
        props=[
            {
                "id": "visual_only", "surface_id": "surf_site",
                "footprint": [(42, 2), (43, 2), (43, 3), (42, 3)],
                "collision": False,
            },
        ],
    )

    map_obj, geo_obj = map_workbench.compile_document(doc)
    assert map_obj.sites == [Site.A]
    assert "a_plant" not in map_obj.callouts
    assert map_obj.callouts["attacker_spawn"].zone == CalloutZone.ATTACKER_SPAWN
    assert map_obj.callouts["a_site"].zone == CalloutZone.SITE
    assert geo_obj.corridors[0].via == [(19, 5), (19, 8), (30, 8), (21, 5)]
    assert len(geo_obj.props) == 1
    assert geo_obj.props[0].height == "full"
    assert audit_continuous(doc) == []
    assert audit_map(map_obj, geo_obj) == []

    game_data = load_all()
    game_data.maps[map_obj.id] = map_obj
    monkeypatch.setattr(engine, "load_geometry", lambda _map_id: geo_obj)
    sim = engine._MatchSim(
        game_data, "team_nexus", "team_vanguard", map_obj.id, seed=91
    )
    player = sim.p[sorted(sim.p)[0]]
    player.callout = "attacker_spawn"
    player.x, player.y = 5.0, 5.0
    sim._begin_move(player, "a_site", 1, ("test",), "spread")

    assert (19.0, 5.0) in player.path
    assert (19.0, 8.0) in player.path
    assert (30.0, 8.0) in player.path
    legal = sim._motor_legal_controls(player)
    advance = next(
        control
        for control in legal
        if control.movement.value == "advance"
        and control.pace.value == "run"
        and control.turn_degrees == 0.0
    )
    sim._apply_motor_control(player, advance, legal, 2, ("test", "motor"))
    assert player.x > 5.0


def test_compiler_rejects_lossy_surface_mappings():
    base = {
        "id": "lossy-map",
        "display_name": "Lossy Map",
        "attacker_spawn": "zone",
        "defender_spawn": "zone",
        "walkable_surfaces": [
            {"id": "one", "polygon": [(0, 0), (10, 0), (10, 10), (0, 10)]},
            {"id": "two", "polygon": [(20, 0), (30, 0), (30, 10), (20, 10)]},
        ],
    }
    duplicate_zone = MapStudioDocumentV1(
        **base,
        semantic_zones=[{
            "id": "zone", "kind": "spawn",
            "polygon": [(0, 0), (30, 0), (30, 10), (0, 10)],
            "surface_ids": ["one", "two"], "label_position": (5, 5),
        }],
    )
    with pytest.raises(ValueError, match="multiple walkable surfaces"):
        map_workbench.compile_document(duplicate_zone)

    duplicate_surface = MapStudioDocumentV1(
        **base,
        semantic_zones=[
            {
                "id": "zone", "kind": "spawn",
                "polygon": [(0, 0), (10, 0), (10, 10), (0, 10)],
                "surface_ids": ["one"], "label_position": (5, 5),
            },
            {
                "id": "other", "kind": "callout", "legacy_zone": "mid",
                "polygon": [(0, 0), (10, 0), (10, 10), (0, 10)],
                "surface_ids": ["one"], "label_position": (5, 5),
            },
        ],
    )
    with pytest.raises(ValueError, match="multiple navigational zones"):
        map_workbench.compile_document(duplicate_surface)


def test_transactional_install_rollback(tmp_path):
    # Set up directories inside tmp_path
    studio_dir = tmp_path / "maps" / "studio"
    runtime_dir = tmp_path / "maps"
    geometry_dir = tmp_path / "maps" / "geometry"
    guide_dir = tmp_path / "assets" / "maps" / "guides"

    studio_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    guide_dir.mkdir(parents=True, exist_ok=True)

    # Put a mock draft
    map_id = "test-rollback"
    doc_dict = {
        "schema_version": 1,
        "id": map_id,
        "display_name": "Test Rollback",
        "walkable_surfaces": [
            {"id": "surf_1", "polygon": [[10,10],[20,10],[20,20],[10,20]], "elevation": 0.0}
        ],
        "semantic_zones": [
            {"id": "zone_1", "kind": "site", "polygon": [[10,10],[20,10],[20,20],[10,20]], "surface_ids": ["surf_1"], "label_position": [15, 15], "site_id": "a"}
        ],
        "attacker_spawn": "zone_1",
        "defender_spawn": "zone_1"
    }

    # Save draft
    res_save = map_workbench.save_document(map_id, doc_dict, data_dir=tmp_path)
    assert res_save["valid"]

    # Trigger a publish but inject a failure (e.g. make destination guide directory read-only or similar,
    # or compile to something invalid that fails validation during audit)
    doc_corrupt = doc_dict.copy()
    # Zone has no path to defender spawn (none defined in callouts) -> fails audit
    doc_corrupt["defender_spawn"] = "missing_zone"
    map_workbench.save_document(map_id, doc_corrupt, data_dir=tmp_path, if_match_hash=res_save["hash"])

    # Attempt to publish -> should raise ValueError due to audit fail, leaving no legacy configs on disk
    with pytest.raises(ValueError):
        map_workbench.publish_document(map_id, data_dir=tmp_path)

    assert not (runtime_dir / f"{map_id}.yaml").exists()
    assert not (geometry_dir / f"{map_id}.yaml").exists()
    assert not (guide_dir / f"{map_id}.png").exists()


def test_map_id_underscores_and_uppercase(tmp_path):
    map_id = "My_New_Map"
    doc_dict = {
        "schema_version": 1,
        "id": map_id,
        "display_name": "My New Map",
        "walkable_surfaces": [],
        "semantic_zones": [],
        "attacker_spawn": "zone_1",
        "defender_spawn": "zone_1"
    }
    # Test server _map_studio_id helper directly or via mock
    from esports_sim.web.server import _map_studio_id
    # Validates ok
    assert _map_studio_id(map_id) == map_id

    # Test workbench save/load
    res = map_workbench.save_document(map_id, doc_dict, data_dir=tmp_path)
    assert res["valid"]

    doc_loaded, _ = map_workbench.load_document(map_id, data_dir=tmp_path)
    assert doc_loaded.id == map_id


def test_overlapping_surfaces_crossing():
    from esports_sim.registry.map_audit import audit_continuous
    doc = MapStudioDocumentV1(
        id="test-overlap",
        display_name="Test Overlap",
        walkable_surfaces=[
            {"id": "surf_1", "polygon": [(0.0, 5.0), (10.0, 5.0), (10.0, 6.0), (0.0, 6.0)], "elevation": 0.0},
            {"id": "surf_2", "polygon": [(5.0, 0.0), (6.0, 0.0), (6.0, 10.0), (5.0, 10.0)], "elevation": 1.0}
        ],
        semantic_zones=[],
        attacker_spawn="none",
        defender_spawn="none"
    )
    errors = audit_continuous(doc)
    # Check if the error about overlap is reported
    overlap_errors = [err for err in errors if "overlap in 2D" in err]
    assert len(overlap_errors) > 0
    assert "surf_1" in overlap_errors[0]
    assert "surf_2" in overlap_errors[0]


def test_rollback_restores_backups_on_failed_copy(tmp_path, monkeypatch):
    # Set up directories inside tmp_path
    studio_dir, runtime_dir, geometry_dir, guide_dir = map_workbench._resolve_paths(tmp_path)
    
    map_id = "test-rollback-restore"
    
    # 1. Create original files on disk
    original_map_content = "original_map_data"
    original_geo_content = "original_geo_data"
    original_guide_content = b"original_guide_data"
    
    map_target = runtime_dir / f"{map_id}.yaml"
    geo_target = geometry_dir / f"{map_id}.yaml"
    guide_target = guide_dir / f"{map_id}.png"
    
    map_target.write_text(original_map_content, encoding="utf-8")
    geo_target.write_text(original_geo_content, encoding="utf-8")
    guide_target.write_bytes(original_guide_content)
    
    # 2. Put a mock valid draft to promote
    doc_dict = {
        "schema_version": 1,
        "id": map_id,
        "display_name": "Test Rollback Restore",
        "walkable_surfaces": [
            {"id": "surf_1", "polygon": [(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)], "elevation": 0.0},
            {"id": "surf_2", "polygon": [(30.0, 10.0), (40.0, 10.0), (40.0, 20.0), (30.0, 20.0)], "elevation": 0.0}
        ],
        "semantic_zones": [
            {"id": "zone_1", "kind": "spawn", "polygon": [(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)], "surface_ids": ["surf_1"], "label_position": [15, 15], "site_id": "none"},
            {"id": "zone_2", "kind": "site", "polygon": [(30.0, 10.0), (40.0, 10.0), (40.0, 20.0), (30.0, 20.0)], "surface_ids": ["surf_2"], "label_position": [35, 15], "site_id": "a"}
        ],
        "traversal_links": [
            {"id": "link_1", "kind": "teleporter", "from_pos": [15.0, 15.0, "surf_1"], "to_pos": [35.0, 15.0, "surf_2"]}
        ],
        "attacker_spawn": "zone_1",
        "defender_spawn": "zone_1"
    }
    map_workbench.save_document(map_id, doc_dict, data_dir=tmp_path)
    
    # 3. Mock shutil.copy2 to raise an exception on the second copy (geo target copy)
    import shutil
    orig_copy2 = shutil.copy2
    
    call_count = 0
    def mock_copy2(src, dst):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise IOError("Mocked copy failure")
        return orig_copy2(src, dst)
        
    monkeypatch.setattr(shutil, "copy2", mock_copy2)
    
    # 4. Attempt to publish -> should raise RuntimeError
    with pytest.raises(RuntimeError) as excinfo:
        map_workbench.publish_document(map_id, data_dir=tmp_path)
        
    assert "Mocked copy failure" in str(excinfo.value)
    
    # 5. Verify the files are restored to their original content
    assert map_target.read_text(encoding="utf-8") == original_map_content
    assert geo_target.read_text(encoding="utf-8") == original_geo_content
    assert guide_target.read_bytes() == original_guide_content


def test_symmetric_and_segment_overlap_checks():
    from esports_sim.registry.map_audit import audit_continuous
    # 1. Test symmetric vertex containment
    doc_contained = MapStudioDocumentV1(
        id="test-contained",
        display_name="Test Contained",
        walkable_surfaces=[
            {"id": "surf_1", "polygon": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], "elevation": 0.0}
        ],
        semantic_zones=[
            {"id": "zone_1", "kind": "spawn", "polygon": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], "surface_ids": ["surf_1"], "label_position": [5.0, 5.0]},
            {"id": "zone_2", "kind": "plant", "polygon": [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)], "surface_ids": ["surf_1"], "label_position": [5.0, 5.0], "site_id": "a"}
        ],
        attacker_spawn="zone_1",
        defender_spawn="zone_1"
    )
    errors = audit_continuous(doc_contained)
    assert any("Ambiguous overlap" in err for err in errors)

    # 2. Test segment intersection (crossing zones) without vertex containment
    doc_crossing = MapStudioDocumentV1(
        id="test-crossing",
        display_name="Test Crossing",
        walkable_surfaces=[
            {"id": "surf_1", "polygon": [(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)], "elevation": 0.0}
        ],
        semantic_zones=[
            {"id": "zone_1", "kind": "spawn", "polygon": [(-5.0, -0.5), (5.0, -0.5), (5.0, 0.5), (-5.0, 0.5)], "surface_ids": ["surf_1"], "label_position": [0.0, 0.0]},
            {"id": "zone_2", "kind": "plant", "polygon": [(-0.5, -5.0), (0.5, -5.0), (0.5, 5.0), (-0.5, 5.0)], "surface_ids": ["surf_1"], "label_position": [0.0, 0.0], "site_id": "a"}
        ],
        attacker_spawn="zone_1",
        defender_spawn="zone_1"
    )
    errors = audit_continuous(doc_crossing)
    assert any("Ambiguous overlap" in err for err in errors)


def test_reachability_surf_to_zone():
    from esports_sim.registry.map_probe import probe_map
    doc = MapStudioDocumentV1(
        id="test-reach",
        display_name="Test Reach",
        walkable_surfaces=[
            {"id": "surf_1", "polygon": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], "elevation": 0.0},
            {"id": "surf_2", "polygon": [(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 10.0)], "elevation": 0.0}
        ],
        semantic_zones=[
            {"id": "zone_1", "kind": "spawn", "polygon": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], "surface_ids": ["surf_1"], "label_position": [5.0, 5.0]},
            {"id": "zone_2", "kind": "site", "polygon": [(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 10.0)], "surface_ids": ["surf_2"], "label_position": [25.0, 5.0], "site_id": "a"}
        ],
        traversal_links=[
            {"id": "link_1", "kind": "rope", "from_pos": [5.0, 5.0, "surf_1"], "to_pos": [25.0, 5.0, "surf_2"]}
        ],
        attacker_spawn="zone_1",
        defender_spawn="zone_1"
    )
    res = probe_map(doc, from_pos=(3.0, 3.0))
    assert "zone_1" in res["reachable_zones"]
    assert "zone_2" in res["reachable_zones"]


def test_movement_sweep_collision():
    from esports_sim.registry.map_probe import probe_map
    doc = MapStudioDocumentV1(
        id="test-coll",
        display_name="Test Coll",
        walkable_surfaces=[
            {"id": "surf_1", "polygon": [(0.0, -10.0), (20.0, -10.0), (20.0, 20.0), (0.0, 20.0)], "elevation": 0.0}
        ],
        walls=[
            {"polyline": [(10.0, 0.0), (10.0, 10.0)]}
        ],
        semantic_zones=[
            {"id": "zone_1", "kind": "spawn", "polygon": [(0.0, -10.0), (20.0, -10.0), (20.0, 20.0), (0.0, 20.0)], "surface_ids": ["surf_1"], "label_position": [5.0, 5.0]}
        ],
        attacker_spawn="zone_1",
        defender_spawn="zone_1"
    )

    # 1. Straight path intersecting the wall segment
    res1 = probe_map(doc, from_pos=(5.0, 5.0), to_pos=(15.0, 5.0), player_radius=1.0)
    assert res1["resolved_pos"] == pytest.approx((9.0, 5.0))
    assert res1["blocked_by"] is not None
    assert res1["blocked_by"]["id"] == "wall_0"

    # 2. Path not intersecting, but closest point is in interior of S (minimum distance < player_radius)
    res2 = probe_map(doc, from_pos=(8.0, 2.0), to_pos=(9.5, 8.0), player_radius=1.0)
    assert res2["resolved_pos"] == pytest.approx((9.0, 6.0))

    # Path parallel to wall, starts outside collision radius of endpoint but collides with endpoint
    res2_endpoint = probe_map(doc, from_pos=(8.5, -2.0), to_pos=(8.5, 12.0), player_radius=2.0)
    assert res2_endpoint["resolved_pos"] == pytest.approx((8.5, -1.3228756555322954))

    res3 = probe_map(doc, from_pos=(9.5, -5.0), to_pos=(8.5, 15.0), player_radius=1.0)
    assert res3["resolved_pos"] == pytest.approx((9.284953863245441, -0.6990772649088077))

    # Path starting in collision with endpoint
    res3_start_collision = probe_map(doc, from_pos=(9.8, -0.5), to_pos=(8.5, 15.0), player_radius=1.0)
    assert res3_start_collision["resolved_pos"] == pytest.approx((9.8, -0.5))

    res4 = probe_map(doc, from_pos=(12.0, 5.0), to_pos=(10.5, 8.0), player_radius=1.0)
    assert res4["resolved_pos"] == pytest.approx((11.0, 7.0))

    # 3. Path not intersecting, but closest point is an endpoint (s1 or s2)
    res5 = probe_map(doc, from_pos=(12.0, 12.0), to_pos=(8.0, 12.0), player_radius=2.5)
    assert res5["resolved_pos"] == pytest.approx((11.5, 12.0))
