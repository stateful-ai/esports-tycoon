"""Play-loop operations and real stdio protocol coverage for the play MCP."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from esports_sim.registry import play_mcp_ops as ops


def clear_blockers(code: str) -> None:
    """Answer whatever is gating the tick, the same way every run.

    Narrative events and sponsor demands block the advance, so any test that
    needs to reach a later week has to resolve them first — deterministically,
    so the world stays reproducible.
    """
    for kind in ("resolve_flavor", "resolve_media"):
        contract = ops.get_legal_actions(code, [kind])["actions"][kind]
        if contract["enabled"]:
            ops.act(code, kind, {
                "event_id": contract["event_id"],
                "choice_id": contract["choice_ids"][0],
            })
    demands = ops.get_legal_actions(code, ["sponsor_demand_respond"])
    contract = demands["actions"]["sponsor_demand_respond"]
    if contract["enabled"]:
        option = contract["options"][0]
        ops.act(code, "sponsor_demand_respond", option)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A fresh campaign in an isolated save directory."""
    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    ops.new_game(team_id="team_nexus", seed=11, code="TESTA")
    return "TESTA"


def test_new_game_opens_a_playable_dashboard(world: str) -> None:
    state = ops.get_state(world)
    assert state["season"] == 1 and state["week"] == 1
    assert state["team"]["id"] == "team_nexus"
    assert state["team"]["tier"] == 1
    assert state["can_advance"] is True
    # The dashboard must name the actions that are actually available, so an
    # agent never has to guess at the contract.
    assert "advance" in state["enabled_actions"]
    assert "set_tactics" in state["enabled_actions"]


def test_playable_team_preview_follows_the_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    listed = ops.list_playable_teams(seed=11)
    assert listed["seed"] == 11
    assert listed["teams"] and all(t["tier"] == 1 for t in listed["teams"])
    ops.new_game(team_id=listed["teams"][0]["team_id"], seed=11, code="SEEDA")
    assert ops.get_state("SEEDA")["team"]["tier"] == 1


def test_legal_actions_are_the_only_contract_needed(world: str) -> None:
    legal = ops.get_legal_actions(world)["actions"]
    assert legal["set_training"]["enabled"] is True
    focus = legal["set_training"]["options"][0]
    result = ops.act(world, "set_training", {"focus": focus})
    assert result["ok"] is True
    # Every enabled kind carries its own parameter vocabulary.
    assert set(legal["set_tactics"]["dials"]) >= {"aggression", "pace"}


def test_illegal_actions_are_rejected_with_a_reason(world: str) -> None:
    with pytest.raises(ops.PlayError, match="illegal action"):
        ops.act(world, "set_training", {"focus": "not-a-focus"})
    with pytest.raises(ops.PlayError, match="unsupported manager action"):
        ops.act(world, "teleport", {})
    with pytest.raises(ops.PlayError, match="unknown observation section"):
        ops.get_observation(world, ["nope"])


def test_observation_sections_narrow_a_very_large_payload(world: str) -> None:
    full = ops.get_observation(world)
    narrow = ops.get_observation(world, ["roster"])
    assert "free_agents" in full and "free_agents" not in narrow
    assert narrow["roster"] and narrow["season"] == 1
    assert len(str(narrow)) * 4 < len(str(full))


def test_advance_returns_what_actually_happened(world: str) -> None:
    digest = ops.advance_week(world)
    assert digest["advanced"] is True
    assert digest["played"] == {"season": 1, "week": 1}
    assert digest["your_matches"], "the digest must show the match you just played"
    played = digest["your_matches"][0]
    assert played["result"] in ("win", "loss", "draw")
    assert played["map_score"]
    assert digest["state"]["week"] == 2
    assert "cash_change" in digest
    # A second tick never re-reports the same fixture.
    again = ops.advance_week(world)
    assert {f["fixture_id"] for f in again["your_matches"]}.isdisjoint(
        {f["fixture_id"] for f in digest["your_matches"]}
    )


def test_advance_through_act_is_the_same_tick_as_advance_week(world: str) -> None:
    """"advance" is in the action contract, so act() must not be a lesser path.

    Without the pre-tick snapshot the digest loses the cash swing and the table
    move, calls every inbox item new, and mislabels the week after a rollover.
    """
    ops.advance_week(world)
    ops.mark_inbox_read(world)
    digest = ops.act(world, "advance", {})
    assert digest["advanced"] is True
    assert digest["played"] == {"season": 1, "week": 2}
    assert "cash_change" in digest
    stale = {item["id"] for item in ops.get_inbox(world)["items"]}
    assert {item["id"] for item in digest["inbox"]} < stale or not stale, (
        "the digest must report only the mail this tick generated"
    )
    assert digest["state"]["week"] == 3


def test_week_digest_carries_the_mail_the_tick_generated(world: str) -> None:
    digest = ops.advance_week(world)
    assert digest["inbox"], "advancing must surface the week's inbox"
    assert ops.get_inbox(world)["unread"] >= len(digest["inbox"])
    ops.mark_inbox_read(world)
    assert ops.get_inbox(world)["unread"] == 0


def test_read_screens_never_move_the_world(world: str) -> None:
    ops.advance_week(world)
    before = ops.get_state(world)
    for read in (
        ops.get_standings, ops.get_schedule, ops.get_results, ops.get_market,
        ops.get_scouting, ops.get_finances, ops.get_club, ops.get_league,
        ops.get_career, ops.get_chronicle, ops.get_playtest_summary,
        ops.get_analyst_digest, ops.get_season_report,
    ):
        assert read(world) is not None
    assert ops.get_state(world) == before


def test_standings_and_results_agree_after_a_week(world: str) -> None:
    digest = ops.advance_week(world)
    won = digest["your_matches"][0]["result"] == "win"
    record = ops.get_state(world)["record"]
    assert record["wins"] == (1 if won else 0)
    table = ops.get_standings(world)["regions"][0]
    you = next(row for row in table["tier1"] if row["is_you"])
    assert you["wins"] == record["wins"] and you["losses"] == record["losses"]
    results = ops.get_results(world)["results"]
    assert results[0]["fixture_id"] == digest["your_matches"][0]["fixture_id"]
    detail = ops.get_match(world, results[0]["fixture_id"])
    assert detail["maps_detail"] and detail["maps_detail"][0]["lines"]


def test_fog_holds_for_rivals_and_lifts_for_your_own(world: str) -> None:
    mine = ops.get_observation(world, ["roster"])["roster"][0]["id"]
    own = ops.get_player(world, mine)
    assert own["is_yours"] is True
    assert own["attributes"], "your own players are exact"
    session = ops._session(world)
    rival_team = next(
        tid for tid in sorted(session.gs.teams)
        if tid != "team_nexus" and session.gs.teams[tid].player_ids
    )
    rival_pid = sorted(session.gs.teams[rival_team].player_ids)[0]
    rival = ops.get_player(world, rival_pid)
    assert rival["is_yours"] is False
    # A rival read is the scouting report, not the raw attribute block.
    assert "perceived_quality" in rival
    view = ops.get_team(world, rival_team)
    assert view["balance"] is None and view["tactics"] is None


def test_sim_ahead_stops_when_something_needs_you(world: str) -> None:
    run = ops.sim_ahead_weeks(world, max_weeks=4)
    assert 1 <= run["weeks_advanced"] <= 4
    assert run["state"]["week"] == 1 + run["weeks_advanced"]
    if run["weeks_advanced"] < 4:
        assert run["state"]["needs_you"] or not run["state"]["can_advance"]


def test_dashboard_answers_a_blind_decision(world: str) -> None:
    """Every gate a manager can hit must be visible on one screen.

    Playing found three ways to be asked for a decision with nothing to
    decide on: an event with choice ids but no copy, a sponsor demand with no
    terms, and a transfer plan silently dead because the window is shut.
    """
    state = ops.get_state(world)
    assert set(state["market_window"]) >= {"open", "label"}
    ops.advance_week(world)
    for _ in range(6):
        pending = ops.get_state(world)["pending_events"]
        if pending:
            break
        if not ops.get_state(world)["can_advance"]:
            break
        ops.advance_week(world)
    for item in pending:
        event = item["event"]
        if item["action"] == "sponsor_demand_respond":
            # A demand you cannot price is a coin flip.
            assert event["reward"] and "penalty" in event
            assert event["label"]
        else:
            assert event["title"] and event["prompt"]
            # Choice ids alone are unplayable — each needs its label.
            assert all(c["id"] and c["label"] for c in event["choices"])


def test_tactics_view_prices_every_dial_against_the_roster(world: str) -> None:
    view = ops.get_tactics(world)
    assert view["tactics"]["aggression"] == 50.0
    dials = {d["dial"]: d for d in view["dials"]}
    assert "aggression" in dials and "util_discipline" in dials
    for dial in dials.values():
        assert dial["low_means"] and dial["high_means"]
        assert dial["impact_at_0"] != dial["impact_at_100"]
        assert dial["best_at_low"] and dial["best_at_high"]
    starter = view["lineup"][0]
    assert starter["resolved_agent"] == starter["auto_agent"]
    assert starter["top_agents"][0]["mastery"] >= starter["top_agents"][-1]["mastery"]


def test_agent_lock_overrides_and_clears(world: str) -> None:
    starter = ops.get_tactics(world)["lineup"][0]
    other = next(
        option["agent_id"] for option in starter["top_agents"]
        if option["agent_id"] != starter["auto_agent"]
    )
    ops.set_agent_lock(world, starter["player_id"], other)
    locked = ops.get_tactics(world)["lineup"][0]
    assert locked["locked_agent"] == other and locked["resolved_agent"] == other
    ops.set_agent_lock(world, starter["player_id"])
    assert ops.get_tactics(world)["lineup"][0]["locked_agent"] is None
    with pytest.raises(ops.PlayError, match="unknown agent"):
        ops.set_agent_lock(world, starter["player_id"], "not-an-agent")


def test_standing_scout_directive_replaces_the_weekly_slot(world: str) -> None:
    menu = ops.get_scouting(world)["directives"]
    assert "fill_gap" in menu["pro"] and "track_academy" in menu["amateur"]
    result = ops.set_scout_directive(
        world, "pro", "fill_gap", role="duelist", caliber="tier1"
    )
    assert result["message"].endswith("fill_gap:duelist:tier1")
    assert ops.get_scouting(world)["pro"]["directive"] == "fill_gap:duelist:tier1"
    ops.set_scout_directive(world, "pro", "")
    assert ops.get_scouting(world)["pro"]["directive"] is None
    with pytest.raises(ops.PlayError, match="lane must be"):
        ops.set_scout_directive(world, "sideline", "fill_gap")
    with pytest.raises(ops.PlayError, match="unknown pro directive"):
        ops.set_scout_directive(world, "pro", "read_minds")


def test_fill_gap_without_a_role_actually_sweeps_the_market(world: str) -> None:
    """The default must be a wildcard, not a role no player has.

    scouting._build_shortlist matches a non-empty role EXACTLY, so storing the
    literal "any" would return an empty shortlist forever while reporting
    success — the worst kind of failure, a silent one.
    """
    ops.set_scout_directive(world, "pro", "fill_gap")
    assert ops.get_scouting(world)["pro"]["directive"] == "fill_gap::any"
    for _ in range(2):
        clear_blockers(world)
        ops.advance_week(world)
    assert ops.get_scouting(world)["pro"]["shortlist"], "wildcard swept nobody"

    ops.set_scout_directive(world, "pro", "fill_gap", role="duelist")
    assert ops.get_scouting(world)["pro"]["directive"] == "fill_gap:duelist:any"
    clear_blockers(world)
    ops.advance_week(world)
    listed = ops.get_scouting(world)["pro"]["shortlist"]
    assert listed and all(row["role"] == "duelist" for row in listed)


def test_every_decision_survives_a_dropped_client(world: str) -> None:
    """No mutation may live only in memory.

    An MCP client is its own process and can vanish after any single call, so
    a decision the caller was told had landed must already be on disk.
    """
    ops.act(world, "set_tactics", {"util_discipline": 77.0})
    ops.set_scout_directive(world, "amateur", "track_academy")
    starter = ops.get_tactics(world)["lineup"][0]
    ops.set_agent_lock(world, starter["player_id"], starter["top_agents"][1]["agent_id"])
    ops._SESSIONS.clear()  # the client went away without calling save_game
    assert ops.get_observation(world, ["tactics"])["tactics"]["util_discipline"] == 77.0
    assert ops.get_scouting(world)["amateur"]["directive"] == "track_academy"
    assert ops.get_tactics(world)["lineup"][0]["locked_agent"] is not None


def test_market_actions_log_under_the_canonical_action_kinds(world: str) -> None:
    """The action log is the replay record; an unknown kind raises on write."""
    from esports_sim.manager import telemetry

    for kind in ("bid", "buyout", "respond_offer", "propose_package",
                 "set_assignment", "set_scout_directive"):
        assert kind in telemetry.ACTION_KINDS
    session = ops._session(world)
    starter = ops.get_tactics(world)["lineup"][0]
    ops.set_agent_lock(world, starter["player_id"], starter["top_agents"][1]["agent_id"])
    assert session.gs.action_log[-1].kind == "set_assignment"


def test_save_and_reload_preserves_the_world(world: str) -> None:
    ops.advance_week(world)
    ops.act(world, "set_tactics", {"aggression": 62.0})
    ops.save_game(world)
    before = ops.get_state(world)
    ops._SESSIONS.clear()
    reloaded = ops.load_game(world)["state"]
    assert reloaded == before
    assert (
        ops.get_observation(world, ["tactics"])["tactics"]["aggression"] == 62.0
    )
    assert any(w["code"] == world for w in ops.list_games()["worlds"])


def test_replaying_the_same_actions_reproduces_the_campaign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Determinism: seed + action sequence still fixes the whole world."""
    def play(code: str) -> str:
        ops.new_game(team_id="team_nexus", seed=5, code=code)
        ops.act(code, "set_tactics", {"aggression": 58.0, "pace": 44.0})
        ops.act(code, "set_scout", {"target": "market"})
        for _ in range(3):
            clear_blockers(code)
            ops.advance_week(code)
        return ops._session(code).gs.model_dump_json()

    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    first = play("RUNAA")
    second = play("RUNBB")
    # Only the world code differs between the two saves, and that is not
    # campaign state — the serialized GameState must match exactly.
    assert first == second


def test_transfer_target_prices_a_rival_player(world: str) -> None:
    session = ops._session(world)
    rival_team = next(
        tid for tid in sorted(session.gs.teams)
        if tid != "team_nexus" and session.gs.teams[tid].player_ids
    )
    pid = sorted(session.gs.teams[rival_team].player_ids)[0]
    quote = ops.get_transfer_target(world, pid)
    assert quote["transfer_ask"] > 0
    assert quote["owner"]["team_id"] == rival_team
    assert quote["ask_breakdown"]
    with pytest.raises(ops.PlayError, match="your own player"):
        own = ops.get_observation(world, ["roster"])["roster"][0]["id"]
        ops.get_transfer_target(world, own)


def test_unknown_world_is_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    with pytest.raises(ops.PlayError, match="no world"):
        ops.get_state("NOPEE")
    with pytest.raises(ops.PlayError, match="invalid world code"):
        ops.get_state("not a code")


def test_world_codes_match_the_browser_join_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A world the browser cannot join defeats sharing the save convention."""
    from esports_sim.web import server as web

    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    for bad in ("ABC", "ABCD", "ABCDEF", "ABCDEFGH"):
        with pytest.raises(ops.PlayError, match="invalid world code"):
            ops.new_game(team_id="team_nexus", seed=3, code=bad)
    created = ops.new_game(team_id="team_nexus", seed=3)
    code = created["code"]
    assert web._CODE_RE.match(code), "generated codes must pass the lobby regex"
    # Same save path on both sides, so the browser opens the same world.
    monkeypatch.setattr(web, "SAVE_DIR", tmp_path / "saves")
    assert web._save_path_for(code) == ops.save_path_for(code)
    assert ops.save_path_for(code).exists()


def test_generated_codes_come_from_stable_hashed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No process-local RNG: the same seed names the same world every time."""
    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    first = ops._new_code(77)
    assert ops._new_code(77) == first
    assert ops._new_code(78) != first
    assert set(first) <= set(ops.CODE_ALPHABET)
    # A taken code advances the attempt index rather than a draw count.
    ops.new_game(team_id="team_nexus", seed=77, code=first)
    assert ops._new_code(77) != first


def test_stdio_mcp_plays_a_week_end_to_end(tmp_path: Path) -> None:
    """The real protocol path: list tools, start a world, act, advance."""
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")

    async def scenario() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "esports_sim.mcp.play_server"],
            env=env,
            cwd=str(tmp_path),  # saves land in the tmp world, not the repo
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                assert {
                    "how_to_play", "list_playable_teams", "new_game",
                    "get_state", "get_legal_actions", "act", "advance_week",
                    "get_standings", "get_inbox", "get_match", "load_game",
                } <= names

                created = await session.call_tool(
                    "new_game",
                    arguments={
                        "team_id": "team_nexus", "seed": 4, "code": "PROTO",
                    },
                )
                assert not created.isError
                assert created.structuredContent["state"]["week"] == 1

                acted = await session.call_tool(
                    "act",
                    arguments={
                        "code": "PROTO", "kind": "set_tactics",
                        "params": {"aggression": 65.0},
                    },
                )
                assert not acted.isError
                assert acted.structuredContent["ok"] is True

                ticked = await session.call_tool(
                    "advance_week", arguments={"code": "PROTO"}
                )
                assert not ticked.isError
                digest = ticked.structuredContent
                assert digest["advanced"] is True
                assert digest["state"]["week"] == 2

                rejected = await session.call_tool(
                    "act",
                    arguments={
                        "code": "PROTO", "kind": "sign",
                        "params": {"player_id": "nobody"},
                    },
                )
                assert rejected.isError

    asyncio.run(scenario())
