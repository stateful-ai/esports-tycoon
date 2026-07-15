"""Shared-draft operations and real stdio coverage for the Map Studio MCP."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from esports_sim.registry import map_mcp_ops as ops
from esports_sim.registry import map_workbench
from esports_sim.registry.loader import DEFAULT_DATA_DIR


def test_two_site_workflow_is_valid_revisioned_and_publishable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ESPORTS_MAP_DATA_DIR", str(data_dir))

    created = ops.create_map("coedit-map", "Coedit Map", template="two-site")
    assert created["validation"] == {"valid": True, "errors": []}
    assert created["document"]["sites"] == ["a", "b"]
    first_hash = created["revision_hash"]
    assert created["ui_path"] == "/map-studio.html?map=coedit-map"

    changed = ops.upsert_wall(
        "coedit-map",
        {
            "id": "wall_a_heaven",
            "polyline": [(18, 45), (18, 57)],
            "thickness": 1.0,
            "height": 3.2,
            "penetrability": 0.5,
        },
        first_hash,
    )
    second_hash = changed["revision_hash"]
    assert second_hash != first_hash
    assert changed["changed"]["id"] == "wall_a_heaven"

    with pytest.raises(ops.MapMcpError, match="stale revision"):
        ops.update_map_metadata(
            "coedit-map", {"display_name": "Stale Name"}, first_hash
        )
    with pytest.raises(ops.MapMcpError, match="stale revision"):
        ops.publish_map("coedit-map", first_hash)

    current = ops.get_map("coedit-map")
    assert current["revision_hash"] == second_hash
    assert current["document"]["walls"][0]["id"] == "wall_a_heaven"
    assert ops.probe_map_geometry("coedit-map", (25, 50))["probe"]["zone_id"] == "a_site"

    published = ops.publish_map("coedit-map", second_hash)
    assert published["status"] == "published"
    assert (data_dir / "maps" / "coedit-map.yaml").is_file()
    assert (data_dir / "maps" / "geometry" / "coedit-map.yaml").is_file()
    assert (tmp_path / "assets" / "maps" / "guides" / "coedit-map.png").is_file()


def test_human_save_forces_ai_to_reconcile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ESPORTS_MAP_DATA_DIR", str(data_dir))
    created = ops.create_map("shared-map", "Shared Map")

    doc, revision_hash = map_workbench.load_document("shared-map", data_dir)
    raw = doc.model_dump(mode="json")
    raw["display_name"] = "Human Saved Name"
    human_save = map_workbench.save_document(
        "shared-map", raw, if_match_hash=revision_hash, data_dir=data_dir
    )

    with pytest.raises(ops.MapMcpError, match="reconcile"):
        ops.update_map_metadata(
            "shared-map",
            {"display_name": "AI Blind Overwrite"},
            created["revision_hash"],
        )
    latest = ops.get_map("shared-map")
    assert latest["revision_hash"] == human_save["hash"]
    assert latest["document"]["display_name"] == "Human Saved Name"


def test_fork_and_batch_patch_keep_variant_work_coherent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ESPORTS_MAP_DATA_DIR", str(data_dir))
    source = ops.create_map("source-map", "Source Map", template="two-site")

    forked = ops.fork_map("source-map", "variant-map", "Variant Map")
    assert forked["validation"]["valid"] is True
    assert forked["document"]["id"] == "variant-map"
    assert forked["document"]["editor_state"]["test_players"] == []

    patched = ops.apply_map_patch(
        "variant-map",
        forked["revision_hash"],
        metadata={"display_name": "Reference Variant"},
        walkable_surfaces=[{
            "id": "surf_a_entry",
            "polygon": [(8, 20), (50, 20), (50, 40), (8, 40)],
            "elevation": 0,
        }],
        semantic_zones=[{
            "id": "a_entry",
            "display_name": "A Entry",
            "kind": "callout",
            "polygon": [(8, 20), (50, 20), (50, 40), (8, 40)],
            "surface_ids": ["surf_a_entry"],
            "label_position": (29, 30),
            "site_id": "a",
            "legacy_zone": "attacker_side",
        }],
        props=[{
            "id": "a_entry_box",
            "surface_id": "surf_a_entry",
            "footprint": [(12, 26), (16, 26), (16, 30), (12, 30)],
            "height": "half",
        }],
    )
    assert patched["changed"]["operation"] == "batch_patch"
    assert patched["changed"]["upserted"] == {
        "surfaces": 1,
        "zones": 1,
        "props": 1,
        "walls": 0,
        "links": 0,
        "sightlines": None,
        "adjacency_overrides": None,
        "prop_support_exemptions": None,
    }
    assert patched["validation"]["valid"] is True
    assert ops.get_map("source-map")["document"]["props"] == []
    assert ops.get_map("variant-map")["document"]["props"][0]["id"] == "a_entry_box"

    with pytest.raises(ops.MapMcpError, match="stale revision"):
        ops.apply_map_patch("variant-map", forked["revision_hash"], metadata={})
    with pytest.raises(ops.MapMcpError, match="duplicate prop ids"):
        ops.apply_map_patch(
            "variant-map",
            patched["revision_hash"],
            props=[
                {"id": "dup", "surface_id": "surf_a_site", "footprint": [(20, 45), (22, 45), (22, 47), (20, 47)]},
                {"id": "dup", "surface_id": "surf_a_site", "footprint": [(24, 45), (26, 45), (26, 47), (24, 47)]},
            ],
        )


def test_legacy_materialization_checks_synthetic_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    runtime_dir = data_dir / "maps"
    geometry_dir = runtime_dir / "geometry"
    runtime_dir.mkdir(parents=True)
    geometry_dir.mkdir(parents=True)
    shutil.copy2(DEFAULT_DATA_DIR / "maps" / "ascent.yaml", runtime_dir / "ascent.yaml")
    shutil.copy2(
        DEFAULT_DATA_DIR / "maps" / "geometry" / "ascent.yaml",
        geometry_dir / "ascent.yaml",
    )
    monkeypatch.setenv("ESPORTS_MAP_DATA_DIR", str(data_dir))

    _, old_hash = map_workbench.load_document("ascent", data_dir)
    runtime_path = runtime_dir / "ascent.yaml"
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    runtime["display_name"] = "Human Changed Legacy"
    runtime_path.write_text(yaml.safe_dump(runtime, sort_keys=False), encoding="utf-8")

    stale_doc = map_workbench.synthesize_document("ascent", data_dir)
    with pytest.raises(ValueError, match="stale revision"):
        map_workbench.save_document(
            "ascent",
            stale_doc.model_dump(mode="json"),
            if_match_hash=old_hash,
            data_dir=data_dir,
        )

    opened = ops.open_map_for_editing("ascent")
    assert opened["document"]["display_name"] == "Human Changed Legacy"
    assert (data_dir / "maps" / "studio" / "ascent.yaml").is_file()


def test_stdio_mcp_exposes_typed_map_tools_and_creates_shared_draft(
    tmp_path: Path,
) -> None:
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    env["ESPORTS_MAP_DATA_DIR"] = str(tmp_path / "data")

    async def scenario() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "esports_sim.mcp.map_server"],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                by_name = {tool.name: tool for tool in listed.tools}
                required = {
                    "get_map_schema",
                    "create_map",
                    "fork_map",
                    "apply_map_patch",
                    "open_map_for_editing",
                    "get_map",
                    "upsert_walkable_surface",
                    "upsert_semantic_zone",
                    "upsert_wall",
                    "upsert_prop",
                    "upsert_traversal_link",
                    "remove_map_element",
                    "probe_map_geometry",
                    "publish_map",
                }
                assert required <= set(by_name)
                wall_schema = by_name["upsert_wall"].inputSchema["properties"]["wall"]
                assert "$ref" in wall_schema or "properties" in wall_schema

                result = await session.call_tool(
                    "create_map",
                    arguments={
                        "map_id": "protocol-map",
                        "display_name": "Protocol Map",
                        "template": "two-site",
                    },
                )
                assert result.isError is not True
                created = json.loads(result.content[0].text)
                patched = await session.call_tool(
                    "apply_map_patch",
                    arguments={
                        "map_id": "protocol-map",
                        "if_match_hash": created["revision_hash"],
                        "props": [{
                            "id": "protocol-box",
                            "surface_id": "surf_a_site",
                            "footprint": [[20, 48], [23, 48], [23, 51], [20, 51]],
                            "height": "half",
                        }],
                    },
                )
                assert patched.isError is not True
                forked = await session.call_tool(
                    "fork_map",
                    arguments={
                        "source_map_id": "protocol-map",
                        "new_map_id": "protocol-fork",
                    },
                )
                assert forked.isError is not True

    asyncio.run(scenario())
    assert (
        tmp_path / "data" / "maps" / "studio" / "protocol-map.yaml"
    ).is_file()
    assert (
        tmp_path / "data" / "maps" / "studio" / "protocol-fork.yaml"
    ).is_file()
