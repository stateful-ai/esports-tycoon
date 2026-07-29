"""MCP server for playing the campaign — the whole game, as an agent plays it.

Every tool routes through ``registry.play_mcp_ops``, which in turn applies
manager decisions through the same headless action contract the web layer,
the learned manager policies, and the LLM playtest harness all use. Playing a
world here is therefore the same game, not a simulation of it: the save it
writes opens in the browser, and the same seed plus the same actions still
reproduces the campaign byte for byte.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from esports_sim.registry import play_mcp_ops as ops

mcp = FastMCP(
    "ESports Manager (Play)",
    instructions=(
        "Play a full esports-manager campaign. First call how_to_play, then "
        "list_playable_teams(seed) and new_game (or load_game for a world you "
        "already started). The turn loop is: get_state to see what needs you, "
        "get_legal_actions for the exact legal parameters, act for each "
        "decision, then advance_week and read the digest it returns. Never "
        "invent ids or action kinds — every id you need appears in the action "
        "contract. Read screens (standings, market, finances, inbox, "
        "chronicle) are free and never change the world."
    ),
    json_response=True,
)


# ---------------------------------------------------------------------------
# Resources — reference an agent can read once and keep
# ---------------------------------------------------------------------------


@mcp.resource("play://guide")
def guide() -> str:
    """How this game works and how to play it well."""
    return json.dumps(ops.how_to_play(), indent=2)


@mcp.resource("play://packs")
def packs() -> str:
    """Roster packs (authored leagues) available to start a world from."""
    return json.dumps(ops.list_packs(), indent=2)


@mcp.resource("play://worlds")
def worlds() -> str:
    """Saved campaign worlds on disk."""
    return json.dumps(ops.list_games(), indent=2)


@mcp.resource("play://state/{code}")
def state(code: str) -> str:
    """One world's dashboard: season, table position, and what needs you."""
    return json.dumps(ops.get_state(code), indent=2)


# ---------------------------------------------------------------------------
# Getting into a game
# ---------------------------------------------------------------------------


@mcp.tool()
def how_to_play() -> dict[str, Any]:
    """Read first: the goal, the weekly loop, the systems, and the gotchas."""
    return ops.how_to_play()


@mcp.tool()
def list_packs() -> dict[str, Any]:
    """List authored roster packs you can build a world from."""
    return ops.list_packs()


@mcp.tool()
def list_playable_teams(
    seed: int = 1, pack_id: str | None = None, tier: int = 1
) -> dict[str, Any]:
    """Preview the clubs this seed's world contains; pass the same seed to new_game."""
    return ops.list_playable_teams(seed, pack_id, tier)


@mcp.tool()
def list_career_offers(seed: int = 1, pack_id: str | None = None) -> dict[str, Any]:
    """The clubs offering you a legacy career on this seed, and their briefs.

    A legacy start is a choice between board offers, not a free pick: the
    archetype sets the contract's goal and patience. Call this before
    new_game(mode="legacy") and pass one of these team ids with the same seed.
    """
    return ops.list_career_offers(seed, pack_id)


@mcp.tool()
def new_game(
    team_id: str,
    seed: int = 1,
    code: str | None = None,
    pack_id: str | None = None,
    mode: str = "sandbox",
    manager_name: str = "",
    scenario: str | None = None,
) -> dict[str, Any]:
    """Start a campaign as one club and return its world code and dashboard."""
    return ops.new_game(team_id, seed, code, pack_id, mode, manager_name, scenario)


@mcp.tool()
def list_games() -> dict[str, Any]:
    """List saved worlds this server can load."""
    return ops.list_games()


@mcp.tool()
def load_game(code: str) -> dict[str, Any]:
    """Resume a saved world by its code."""
    return ops.load_game(code)


@mcp.tool()
def save_game(code: str) -> dict[str, Any]:
    """Force a write. Every decision already saves as it lands, so this is optional."""
    return ops.save_game(code)


# ---------------------------------------------------------------------------
# The turn loop
# ---------------------------------------------------------------------------


@mcp.tool()
def get_state(code: str) -> dict[str, Any]:
    """The dashboard: season, week, record, table place, cash, and what needs you."""
    return ops.get_state(code)


@mcp.tool()
def get_legal_actions(
    code: str, kinds: list[str] | None = None, enabled_only: bool = True
) -> dict[str, Any]:
    """Every legal action and its legal parameter values right now."""
    return ops.get_legal_actions(code, kinds, enabled_only)


@mcp.tool()
def get_observation(
    code: str, sections: list[str] | None = None
) -> dict[str, Any]:
    """The full decision-time observation, or just the sections you name.

    The whole observation is very large; prefer sections such as ["roster"],
    ["opponent"], or ["free_agents"].
    """
    return ops.get_observation(code, sections)


@mcp.tool()
def act(code: str, kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Take one manager decision (tactics, lineup, market, staff, culture, ...).

    ``kind`` and ``params`` must come from get_legal_actions. Illegal actions
    are rejected with the reason rather than silently ignored.
    """
    return ops.act(code, kind, params)


@mcp.tool()
def advance_week(code: str) -> dict[str, Any]:
    """Tick the world one week and return what happened: results, table move, mail."""
    return ops.advance_week(code)


@mcp.tool()
def sim_ahead(code: str, max_weeks: int = 6) -> dict[str, Any]:
    """Fast-forward up to max_weeks, stopping as soon as something needs you."""
    return ops.sim_ahead_weeks(code, max_weeks)


# ---------------------------------------------------------------------------
# Read screens
# ---------------------------------------------------------------------------


@mcp.tool()
def get_inbox(
    code: str, unread_only: bool = False, limit: int = 20
) -> dict[str, Any]:
    """Your weekly feed: results, transfers, board notes, scouting, development."""
    return ops.get_inbox(code, unread_only, limit)


@mcp.tool()
def mark_inbox_read(code: str, item_id: str = "") -> dict[str, Any]:
    """Mark one inbox item read, or the whole feed when no id is given."""
    return ops.mark_inbox_read(code, item_id)


@mcp.tool()
def get_standings(code: str, region: str | None = None) -> dict[str, Any]:
    """League tables for your region first, or one named region."""
    return ops.get_standings(code, region)


@mcp.tool()
def get_schedule(code: str, weeks: int = 4, all_teams: bool = False) -> dict[str, Any]:
    """Your upcoming fixtures (or the whole league's) for the next few weeks."""
    return ops.get_schedule(code, weeks, all_teams)


@mcp.tool()
def get_results(
    code: str, team_id: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Played fixtures, most recent first. Pass team_id="*" for the whole league."""
    return ops.get_results(code, team_id, limit)


@mcp.tool()
def get_match(code: str, fixture_id: str) -> dict[str, Any]:
    """One fixture in full: per-map scores and the player lines behind them."""
    return ops.get_match(code, fixture_id)


@mcp.tool()
def get_analyst_digest(code: str) -> dict[str, Any]:
    """Your coaching staff's read on the last series — why you won or lost."""
    return ops.get_analyst_digest(code)


@mcp.tool()
def get_player(code: str, player_id: str) -> dict[str, Any]:
    """One player. Your own are exact; rivals and free agents are scout-fogged."""
    return ops.get_player(code, player_id)


@mcp.tool()
def get_team(code: str, team_id: str) -> dict[str, Any]:
    """One club: record, roster, tactics (yours only), and honours."""
    return ops.get_team(code, team_id)


@mcp.tool()
def get_market(code: str, limit: int = 25) -> dict[str, Any]:
    """The free-agent pool, the transfer window's status, and your live talks."""
    return ops.get_market(code, limit)


@mcp.tool()
def get_transfer_target(code: str, player_id: str) -> dict[str, Any]:
    """What a contracted rival player costs and whether their club would sell."""
    return ops.get_transfer_target(code, player_id)


@mcp.tool()
def get_tactics(code: str) -> dict[str, Any]:
    """Your dials with their roster fit, plus each starter's agent options.

    Read this before act(kind="set_tactics"): it says what each dial's poles
    reward, how well your five fit each pole, and the exact match impact at
    both ends. Every dial is a no-op at 50.
    """
    return ops.get_tactics(code)


@mcp.tool()
def set_agent_lock(code: str, player_id: str, agent_id: str = "") -> dict[str, Any]:
    """Lock a starter onto one agent, or pass no agent_id to restore auto-pick."""
    return ops.set_agent_lock(code, player_id, agent_id)


@mcp.tool()
def get_scouting(code: str) -> dict[str, Any]:
    """The scout desk: current assignment, progress, and what the intel bought."""
    return ops.get_scouting(code)


@mcp.tool()
def set_scout_directive(
    code: str,
    lane: str,
    directive: str = "",
    role: str = "any",
    caliber: str = "any",
) -> dict[str, Any]:
    """Give the pro or amateur scouting lane a standing directive.

    This replaces re-picking a single scout target every week. See
    get_scouting().directives for the legal directives and calibers.
    """
    return ops.set_scout_directive(code, lane, directive, role, caliber)


@mcp.tool()
def get_finances(code: str) -> dict[str, Any]:
    """Weekly income and expenses plus the cash projection ahead."""
    return ops.get_finances(code)


@mcp.tool()
def get_club(code: str) -> dict[str, Any]:
    """Staff, facilities, academy, culture, and preparation — the org itself."""
    return ops.get_club(code)


@mcp.tool()
def get_league(code: str) -> dict[str, Any]:
    """Power rankings, award races, all-time records, and league parity."""
    return ops.get_league(code)


@mcp.tool()
def get_career(code: str) -> dict[str, Any]:
    """Your manager seat: contract, reputation, job offers, career history."""
    return ops.get_career(code)


@mcp.tool()
def get_chronicle(
    code: str, limit: int = 25, kinds: list[str] | None = None
) -> dict[str, Any]:
    """The append-only history of the world: titles, awards, moves, milestones."""
    return ops.get_chronicle(code, limit, kinds)


@mcp.tool()
def get_season_report(code: str, season: int | None = None) -> dict[str, Any]:
    """Champions, awards, and the headline numbers for one season."""
    return ops.get_season_report(code, season)


@mcp.tool()
def get_playtest_summary(code: str) -> dict[str, Any]:
    """A designer's-eye read of this campaign and how legible its decisions were."""
    return ops.get_playtest_summary(code)


# ---------------------------------------------------------------------------
# Transfer market (actions outside the headless contract)
# ---------------------------------------------------------------------------


@mcp.tool()
def transfer_bid(code: str, player_id: str) -> dict[str, Any]:
    """Bid the asking fee for a contracted player at another club."""
    return ops.transfer_bid(code, player_id)


@mcp.tool()
def transfer_buyout(code: str, player_id: str) -> dict[str, Any]:
    """Pay a release clause: instant, no negotiation, and priced at a premium."""
    return ops.transfer_buyout(code, player_id)


@mcp.tool()
def transfer_respond(
    code: str, player_id: str, accept: bool, to_team: str | None = None
) -> dict[str, Any]:
    """Accept or decline a bid another manager has made for one of your players."""
    return ops.transfer_respond(code, player_id, accept, to_team)


@mcp.tool()
def transfer_package(
    code: str,
    player_id: str,
    offer_player_ids: list[str] | None = None,
    cash_to_seller: int = 0,
    cash_to_buyer: int = 0,
) -> dict[str, Any]:
    """Offer players plus cash for a target instead of a straight fee."""
    return ops.transfer_package(
        code, player_id, offer_player_ids, cash_to_seller, cash_to_buyer
    )


def main() -> None:
    """Run the play MCP over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
