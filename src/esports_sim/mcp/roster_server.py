"""Official-SDK MCP server for creating and editing roster-pack drafts."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from esports_sim.registry import roster_mcp_ops as ops
from esports_sim.registry.roster_workbench import DraftFreeAgent, DraftPlayer

mcp = FastMCP(
    "ESports Roster Packs",
    instructions=(
        "Build roster packs through draft-first tools. Read the schema, create "
        "or open a draft, add/edit/remove teams and players, validate, then call "
        "install_draft only when valid. Draft mutations do not change game data."
    ),
    json_response=True,
)


@mcp.resource("roster://schema")
def roster_schema() -> str:
    """Portable roster document JSON Schema and legal game catalog ids."""
    return json.dumps(ops.get_schema(), indent=2)


@mcp.resource("roster://installed")
def installed_rosters() -> str:
    """Roster packs currently installed in the game's Play lobby."""
    return json.dumps(ops.list_installed_packs(), indent=2)


@mcp.resource("roster://draft/{pack_id}")
def roster_draft(pack_id: str) -> str:
    """Complete portable roster draft for one pack id."""
    return json.dumps(ops.get_draft(pack_id), indent=2)


@mcp.tool()
def get_roster_schema() -> dict:
    """Get the portable document schema and legal region/role/agent ids."""
    return ops.get_schema()


@mcp.tool()
def list_roster_packs() -> dict:
    """List packs installed in the game and available from the Play lobby."""
    return ops.list_installed_packs()


@mcp.tool()
def list_roster_drafts() -> dict:
    """List draft ids available for MCP editing."""
    return ops.list_drafts()


@mcp.tool()
def create_draft(
    pack_id: str,
    name: str,
    description: str = "",
    league_regions: list[str] | None = None,
    teams_per_region: int = 8,
    tier2_per_region: int = 4,
    template: str = "empty",
    overwrite: bool = False,
) -> dict:
    """Create an empty/example roster draft; this does not install a pack."""
    return ops.create_draft(
        pack_id, name, description, league_regions, teams_per_region,
        tier2_per_region, template, overwrite,
    )


@mcp.tool()
def open_installed_pack(pack_id: str, overwrite: bool = False) -> dict:
    """Copy an installed source-backed pack into an editable draft."""
    return ops.open_installed_pack(pack_id, overwrite)


@mcp.tool()
def get_draft(pack_id: str) -> dict:
    """Get a complete draft and its current validation result."""
    return ops.get_draft(pack_id)


@mcp.tool()
def validate_draft(pack_id: str) -> dict:
    """Validate a draft without installing or changing game data."""
    return ops.validate_draft(pack_id)


@mcp.tool()
def update_pack_metadata(pack_id: str, changes: dict[str, Any]) -> dict:
    """Patch name, description, regions, or league-size settings."""
    return ops.update_pack_metadata(pack_id, changes)


@mcp.tool()
def add_team(
    pack_id: str,
    name: str,
    tag: str,
    region: str,
    tier: int = 1,
    prestige: float = 50,
    partial: bool = False,
) -> dict:
    """Add an empty team; use add_team_player to fill its roster."""
    return ops.add_team(pack_id, name, tag, region, tier, prestige, partial)


@mcp.tool()
def edit_team(pack_id: str, team_name: str, changes: dict[str, Any]) -> dict:
    """Patch a draft team's name, tag, region, tier, prestige, or partial flag."""
    return ops.edit_team(pack_id, team_name, changes)


@mcp.tool()
def remove_team(pack_id: str, team_name: str) -> dict:
    """Remove a team and all of its players from a draft."""
    return ops.remove_team(pack_id, team_name)


@mcp.tool()
def add_team_player(pack_id: str, team_name: str, player: DraftPlayer) -> dict:
    """Add one schema-validated player to a draft team."""
    return ops.add_team_player(pack_id, team_name, player)


@mcp.tool()
def edit_team_player(
    pack_id: str, team_name: str, handle: str, changes: dict[str, Any]
) -> dict:
    """Patch one team player by handle and validate the resulting player."""
    return ops.edit_team_player(pack_id, team_name, handle, changes)


@mcp.tool()
def remove_team_player(pack_id: str, team_name: str, handle: str) -> dict:
    """Remove one team player by handle from a draft."""
    return ops.remove_team_player(pack_id, team_name, handle)


@mcp.tool()
def add_free_agent(pack_id: str, player: DraftFreeAgent) -> dict:
    """Add one schema-validated free agent to a draft."""
    return ops.add_free_agent(pack_id, player)


@mcp.tool()
def edit_free_agent(
    pack_id: str, handle: str, changes: dict[str, Any]
) -> dict:
    """Patch one free agent by handle and validate the resulting player."""
    return ops.edit_free_agent(pack_id, handle, changes)


@mcp.tool()
def remove_free_agent(pack_id: str, handle: str) -> dict:
    """Remove one free agent by handle from a draft."""
    return ops.remove_free_agent(pack_id, handle)


@mcp.tool()
def install_draft(pack_id: str) -> dict:
    """Compile and atomically install a valid draft into the Play lobby."""
    return ops.install_draft(pack_id)


def main() -> None:
    """Run the roster MCP over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
