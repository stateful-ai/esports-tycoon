"""Draft operations and real stdio protocol coverage for the roster MCP."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from esports_sim.registry import roster_mcp_ops as ops
from esports_sim.registry.roster_workbench import DraftFreeAgent, DraftPlayer


def _player(handle: str, *, igl: bool = False) -> DraftPlayer:
    return DraftPlayer(
        handle=handle,
        age=21,
        country="US",
        languages=[{"lang": "en", "level": 100}],
        role="controller" if igl else "flex",
        playstyle="igl" if igl else "support",
        igl=igl,
        quality=68,
        agents=["omen", "viper"] if igl else ["viper"],
    )


def test_draft_add_edit_remove_player_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESPORTS_ROSTER_DRAFT_DIR", str(tmp_path / "drafts"))
    created = ops.create_draft("tool-pack", "Tool Pack")
    assert created["validation"]["valid"] is False
    assert ops.list_drafts()["draft_ids"] == ["tool-pack"]

    ops.add_team("tool-pack", "Tool Team", "TLS", "americas")
    for index in range(5):
        ops.add_team_player(
            "tool-pack", "Tool Team", _player(f"player-{index}", igl=index == 0)
        )
    assert ops.validate_draft("tool-pack")["validation"]["valid"] is True

    edited = ops.edit_team_player(
        "tool-pack", "Tool Team", "player-4",
        {"handle": "closer", "quality": 74},
    )
    assert edited["changed"]["player"]["handle"] == "closer"
    assert edited["changed"]["player"]["quality"] == 74

    removed = ops.remove_team_player("tool-pack", "Tool Team", "closer")
    assert removed["validation"]["valid"] is False
    assert "exactly 5" in removed["validation"]["errors"][0]["message"]
    ops.add_team_player("tool-pack", "Tool Team", _player("replacement"))

    free_agent = DraftFreeAgent(
        **_player("unsigned").model_dump(mode="json"), region="americas"
    )
    ops.add_free_agent("tool-pack", free_agent)
    updated_fa = ops.edit_free_agent(
        "tool-pack", "unsigned", {"quality": 71, "region": "emea"}
    )
    assert updated_fa["changed"]["free_agent"]["region"] == "emea"
    ops.remove_free_agent("tool-pack", "unsigned")

    complete = ops.get_draft("tool-pack")
    assert complete["validation"]["valid"] is True
    assert len(complete["document"]["teams"][0]["players"]) == 5
    assert complete["document"]["free_agents"] == []


def test_install_is_explicit_and_rejects_invalid_drafts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESPORTS_ROSTER_DRAFT_DIR", str(tmp_path / "drafts"))
    ops.create_draft("install-pack", "Install Pack", template="example")
    seen = {}

    def fake_install(raw):
        seen["id"] = raw["id"]
        return {"valid": True, "compiled": {"teams": 1}}

    monkeypatch.setattr(ops, "install_document", fake_install)
    result = ops.install_draft("install-pack")
    assert result["installed"] is True
    assert seen == {"id": "install-pack"}

    ops.remove_team_player(
        "install-pack", "My Favorite Team", "entry"
    )
    with pytest.raises(ops.RosterMcpError, match="not installable"):
        ops.install_draft("install-pack")


def test_draft_ids_are_sandboxed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESPORTS_ROSTER_DRAFT_DIR", str(tmp_path / "drafts"))
    with pytest.raises(ops.RosterMcpError, match="pack_id"):
        ops.create_draft("../escape", "Escape")


def test_stdio_mcp_lists_schema_tools_and_creates_draft(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    env["ESPORTS_ROSTER_DRAFT_DIR"] = str(tmp_path / "mcp-drafts")

    async def scenario() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "esports_sim.mcp.roster_server"],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                by_name = {tool.name: tool for tool in listed.tools}
                required = {
                    "get_roster_schema", "create_draft", "add_team_player",
                    "edit_team_player", "remove_team_player", "add_free_agent",
                    "edit_free_agent", "remove_free_agent", "install_draft",
                }
                assert required <= set(by_name)
                player_schema = by_name["add_team_player"].inputSchema["properties"]["player"]
                assert "$ref" in player_schema or "properties" in player_schema

                result = await session.call_tool(
                    "create_draft",
                    arguments={
                        "pack_id": "protocol-pack",
                        "name": "Protocol Pack",
                        "template": "example",
                    },
                )
                assert result.isError is not True

                edited = await session.call_tool(
                    "edit_team_player",
                    arguments={
                        "pack_id": "protocol-pack",
                        "team_name": "My Favorite Team",
                        "handle": "entry",
                        "changes": {"quality": 76},
                    },
                )
                assert edited.isError is not True
                removed = await session.call_tool(
                    "remove_team_player",
                    arguments={
                        "pack_id": "protocol-pack",
                        "team_name": "My Favorite Team",
                        "handle": "flex",
                    },
                )
                assert removed.isError is not True
                added = await session.call_tool(
                    "add_team_player",
                    arguments={
                        "pack_id": "protocol-pack",
                        "team_name": "My Favorite Team",
                        "player": _player("protocol-flex").model_dump(mode="json"),
                    },
                )
                assert added.isError is not True

    asyncio.run(scenario())
    assert (tmp_path / "mcp-drafts" / "protocol-pack.roster-pack.yaml").is_file()
