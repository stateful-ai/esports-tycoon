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


def test_roster_pack_worlds_can_be_previewed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pack replaces the fictional starters, so "team_nexus" is not there.

    Building the preview on that default raised KeyError, which broke the
    documented first step for every authored league.
    """
    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    pack_id = ops.list_packs()["packs"][0]["pack_id"]
    listed = ops.list_playable_teams(seed=3, pack_id=pack_id)
    assert listed["teams"], "an authored pack listed no playable clubs"
    assert all(t["tier"] == 1 for t in listed["teams"])
    assert not any(t["team_id"] == "team_nexus" for t in listed["teams"])
    # And the previewed club actually starts.
    ops.new_game(
        team_id=listed["teams"][0]["team_id"], seed=3,
        code="PACKW", pack_id=pack_id,
    )
    assert ops.get_state("PACKW")["team"]["id"] == listed["teams"][0]["team_id"]


def test_free_agent_profiles_keep_their_signing_numbers(world: str) -> None:
    """The two pools key their id differently — matching one loses the pool."""
    free_agents = ops.get_observation(world, ["free_agents"])["free_agents"]
    assert free_agents and "player_id" in free_agents[0]
    view = ops.get_player(world, free_agents[0]["player_id"])
    assert view["is_yours"] is False
    # Exactly the fields a signing decision turns on.
    assert view["asking_salary"] > 0
    assert "stats" in view and "perceived_quality" in view


def test_buyouts_are_not_advertised_to_clubs_that_cannot_make_them(
    world: str
) -> None:
    """Only a tier-1 org may trigger a clause, and it must cover the wages."""
    session = ops._session(world)
    tier1 = ops.get_legal_actions(world)["extra_actions"]["transfer_buyout"]
    assert tier1["reason"] == ""
    assert all(
        target["fee"] > 0 and target["wage_reserve"] > 0
        for target in tier1["sample_targets"]
    )
    balance = session.gs.teams["team_nexus"].balance
    assert all(
        target["fee"] + target["wage_reserve"] <= balance
        for target in tier1["sample_targets"]
    ), "advertised a clause the club cannot actually cover"

    session.gs.teams["team_nexus"].tier = 2
    tier2 = ops.get_legal_actions(world)["extra_actions"]["transfer_buyout"]
    assert tier2["enabled"] is False
    assert "tier-1" in tier2["reason"]
    assert tier2["sample_targets"] == []


def test_package_offers_show_what_is_being_offered(world: str) -> None:
    """transfer_respond is irreversible, so the consideration must be visible."""
    from esports_sim.manager.state import TransferOffer

    session = ops._session(world)
    buyer = next(
        tid for tid in sorted(session.gs.teams)
        if tid != "team_nexus" and len(session.gs.teams[tid].player_ids) >= 2
    )
    wanted = sorted(session.gs.teams["team_nexus"].player_ids)[0]
    offered = sorted(session.gs.teams[buyer].player_ids)[:2]
    session.gs.transfer_offers.append(
        TransferOffer(
            player_id=wanted, from_team="team_nexus", to_team=buyer,
            fee=50_000, expires_week=session.gs.week + 2,
            offer_player_ids=offered, cash_to_seller=50_000,
            cash_to_buyer=10_000,
        )
    )
    view = ops.get_legal_actions(world)["extra_actions"]["transfer_respond"]
    assert view["enabled"] is True
    deal = view["offers"][0]
    assert deal["kind"] == "package"
    assert [p["player_id"] for p in deal["offered_players"]] == offered
    assert all(p["perceived_quality"] > 0 for p in deal["offered_players"])
    assert deal["cash_to_seller"] == 50_000 and deal["cash_to_buyer"] == 10_000
    # The same view backs the market screen.
    assert ops.get_market(world)["incoming_offers"][0]["kind"] == "package"


#: Every mutating op that does NOT go through act(). Kept as a literal so a
#: new one has to be added here consciously — the contract test below then
#: forces it to be published, which is how three separate "shipped surface
#: nobody can discover" defects got in.
DIRECT_MUTATION_OPS = frozenset({
    "transfer_bid", "transfer_buyout", "transfer_respond", "transfer_package",
    "set_agent_lock", "set_map_lineup", "set_scout_directive",
})


def test_every_direct_mutation_tool_appears_in_the_contract(world: str) -> None:
    """how_to_play promises the mask names every action; a tool it omits can
    only be reached by guessing.

    Enumerated from the ops module, not the server: play_server is a 1:1 thin
    wrapper, and importing it would drag in the optional `mcp` package that
    only the protocol test needs — the rest of this file must run without it.
    """
    contract = ops.get_legal_actions(world)["extra_actions"]
    # The roster is the source of truth for what exists...
    live = {
        name for name in dir(ops)
        if callable(getattr(ops, name))
        and (name.startswith("transfer_") or name.startswith("set_"))
        and not name.startswith("_")
    }
    assert DIRECT_MUTATION_OPS <= live, (
        f"the roster names ops that no longer exist: "
        f"{DIRECT_MUTATION_OPS - live}"
    )
    # ...and every one of them has to be discoverable.
    missing = DIRECT_MUTATION_OPS - set(contract)
    assert not missing, f"undeclared tools: {sorted(missing)}"
    # Each entry must carry a real parameter vocabulary, not just a flag.
    for name in sorted(DIRECT_MUTATION_OPS):
        entry = contract[name]
        assert "enabled" in entry, name
        assert len(entry) > 1, f"{name} publishes no parameters"

    package = contract["transfer_package"]
    assert package["enabled"] is True
    assert set(package["offerable_player_ids"]) == set(
        ops._session(world).gs.teams["team_nexus"].player_ids
    )
    assert "cash_to_seller" in package["note"]
    lock = contract["set_agent_lock"]
    assert set(lock["player_ids"]) == set(package["offerable_player_ids"])
    per_map = contract["set_map_lineup"]
    assert per_map["enabled"] is True and per_map["count"] == 5
    assert all(
        slot["fixture_id"] and slot["map_id"] for slot in per_map["slots"]
    )


def test_direct_tools_can_be_asked_for_by_name(world: str) -> None:
    """Filtering by kind spans both halves of the contract.

    The direct tools live in extras, so validating names against the headless
    contract alone rejected every one of them as unknown.
    """
    picked = ops.get_legal_actions(
        world, kinds=["set_scout_directive", "advance"]
    )
    assert set(picked["actions"]) == {"advance"}
    assert set(picked["extra_actions"]) == {"set_scout_directive"}
    directive = picked["extra_actions"]["set_scout_directive"]
    assert "fill_gap" in directive["pro_directives"]
    assert "duelist" in directive["roles"]
    with pytest.raises(ops.PlayError, match="unknown action kind"):
        ops.get_legal_actions(world, kinds=["set_telepathy"])


def test_scenario_ids_are_published_and_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An accepted parameter with no published vocabulary is a guessing game."""
    from esports_sim.manager import scenarios

    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    listed = ops.list_scenarios()["scenarios"]
    assert {s["id"] for s in listed} == set(scenarios.SCENARIOS)
    assert all(s["name"] and s["blurb"] for s in listed)

    with pytest.raises(ops.PlayError, match="unknown scenario"):
        ops.new_game(
            team_id="team_nexus", seed=8, code="BADSC", scenario="get_rich"
        )
    ops.new_game(
        team_id="team_nexus", seed=8, code="GOODS",
        scenario=listed[0]["id"],
    )
    assert ops.get_state("GOODS")["season"] == 1


def test_a_refused_market_action_still_persists_its_history(world: str) -> None:
    """A refusal is not a no-op: helpers write real state before returning False.

    Left unwritten it lived only in memory — saved later by an unrelated
    action, or lost entirely if the process exited first.
    """
    from esports_sim.manager import market_history
    from esports_sim.manager.state import GameState

    session = ops._session(world)
    icon = sorted(session.gs.teams["team_vanguard"].player_ids)[0]

    def refuse_after_recording(gs):
        """Stands in for market.user_bid's not-for-sale path, which appends to
        market_decisions and only then returns False."""
        market_history.record(
            gs, "bid", "rejected", icon, actor_team_id="team_vanguard",
            counterparty_team_id="team_nexus", context="sell",
            reason="cash bid refused for an organisational icon",
        )
        return False, "they see them as a pillar of the organisation"

    before = len(session.gs.market_decisions)
    with pytest.raises(ops.PlayError, match="illegal action"):
        ops._market_action(world, "bid", {"player_id": icon}, refuse_after_recording)
    assert len(session.gs.market_decisions) == before + 1

    # And it is on disk, not just in this process.
    on_disk = GameState.load(ops.save_path_for(world))
    assert len(on_disk.market_decisions) == before + 1
    assert on_disk.market_decisions[-1].outcome == "rejected"

    # Persisting the side effect while logging nothing would leave a save the
    # action log cannot rebuild, so the refused call is recorded too.
    logged = on_disk.action_log[-1]
    assert logged.kind == "bid"
    assert logged.params["outcome"] == "rejected"
    assert logged.params["player_id"] == icon


def test_a_cash_back_offer_is_not_shown_as_a_plain_cash_bid(
    world: str
) -> None:
    """No players but cash owed to the BUYER is still a package.

    market.respond_offer treats cash_to_buyer alone as one. Classifying it on
    the player list showed fee 0 and no cash fields, so a seller could accept,
    lose the player AND pay, having been shown nothing.
    """
    from esports_sim.manager.state import TransferOffer

    session = ops._session(world)
    buyer = next(
        tid for tid in sorted(session.gs.teams)
        if tid != "team_nexus" and session.gs.teams[tid].player_ids
    )
    session.gs.transfer_offers.append(
        TransferOffer(
            player_id=sorted(session.gs.teams["team_nexus"].player_ids)[0],
            from_team="team_nexus", to_team=buyer, fee=0,
            expires_week=session.gs.week + 2,
            offer_player_ids=[], cash_to_seller=0, cash_to_buyer=75_000,
        )
    )
    deal = ops.get_market(world)["incoming_offers"][0]
    assert deal["kind"] == "package", "a cash-back offer read as a cash bid"
    assert deal["offered_players"] == []
    assert deal["cash_to_buyer"] == 75_000
    assert deal["cash_to_seller"] == 0


def test_each_bid_names_the_buyer_under_the_answer_parameter(
    world: str
) -> None:
    """Two clubs can bid for one player; the wrong one must not be answerable.

    market.respond_offer falls back to the lexicographically first bidder
    when the buyer is unnamed, so publishing the buyer under any key other
    than transfer_respond's own parameter invites answering a deal the
    manager never read.
    """
    from esports_sim.manager.state import TransferOffer

    session = ops._session(world)
    wanted = sorted(session.gs.teams["team_nexus"].player_ids)[0]
    rivals = [
        tid for tid in sorted(session.gs.teams)
        if tid != "team_nexus" and session.gs.teams[tid].player_ids
    ][:2]
    for index, buyer in enumerate(rivals):
        session.gs.transfer_offers.append(
            TransferOffer(
                player_id=wanted, from_team="team_nexus", to_team=buyer,
                fee=100_000 * (index + 1),
                expires_week=session.gs.week + 2,
            )
        )
    contract = ops.get_legal_actions(world)["extra_actions"]["transfer_respond"]
    assert "to_team" in contract["note"]
    offers = {o["to_team"]: o for o in contract["offers"]}
    assert set(offers) == set(rivals)
    assert all(o["buyer_name"] for o in offers.values())

    # Answering the SECOND bid must resolve that one, not the first by sort.
    richer = rivals[1]
    ops.transfer_respond(world, wanted, accept=False, to_team=richer)
    left = {
        o.to_team for o in ops._session(world).gs.transfer_offers
        if o.player_id == wanted
    }
    assert left == {rivals[0]}


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
    assert 0 <= run["weeks_advanced"] <= 4
    assert run["state"]["week"] == 1 + run["weeks_advanced"]
    assert run["stopped_because"]
    if run["weeks_advanced"] < 4:
        assert run["state"]["deadlines"] or not run["state"]["can_advance"]


def test_a_dismissed_manager_cannot_keep_running_the_old_club(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Being fired hands the club to the AI; the env stays bound to it anyway.

    career.apply_dismissals clears the seat's team and drops the club from
    human_team_ids, but nothing rebinds the environment, so an unguarded
    layer keeps setting tactics and spending money at a club that is no
    longer yours.
    """
    from esports_sim.manager import career

    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    slate = ops.list_career_offers(seed=21)["offers"]
    ops.new_game(
        team_id=slate[0]["team_id"], seed=21, code="FIRED", mode="legacy"
    )
    session = ops._session("FIRED")
    seat = session.gs.seat_for_session(session.env.team_id)
    career.apply_dismissals(session.gs, [seat.id])

    state = ops.get_state("FIRED")
    assert state["dismissed"] is True
    assert any("job offer" in call for call in state["needs_you"])
    # The contract must not advertise running a club the AI now owns —
    # including the market tools, which bypass act() entirely.
    contract = ops.get_legal_actions("FIRED")
    assert set(contract["actions"]) == {"accept_job"}
    assert not [
        name for name, entry in contract["extra_actions"].items()
        if isinstance(entry, dict) and entry.get("enabled")
    ]
    for kind, params in (
        ("set_tactics", {"aggression": 90.0}),
        ("hire_staff", {"candidate_id": "whoever"}),
        ("release", {"player_id": "whoever"}),
    ):
        with pytest.raises(ops.PlayError, match="dismissed"):
            ops.act("FIRED", kind, params)
    # Every direct mutation route, not just the ones that go through act().
    for label, call in (
        ("transfer_bid", lambda: ops.transfer_bid("FIRED", "whoever")),
        ("transfer_buyout", lambda: ops.transfer_buyout("FIRED", "whoever")),
        ("transfer_respond",
         lambda: ops.transfer_respond("FIRED", "whoever", True)),
        ("transfer_package",
         lambda: ops.transfer_package("FIRED", "whoever", [])),
        ("set_agent_lock",
         lambda: ops.set_agent_lock("FIRED", "whoever", "omen")),
        ("set_scout_directive",
         lambda: ops.set_scout_directive("FIRED", "amateur", "track_academy")),
        ("set_map_lineup",
         lambda: ops.set_map_lineup("FIRED", "f", "m", [])),
        ("mark_inbox_read", lambda: ops.mark_inbox_read("FIRED")),
        ("sim_ahead", lambda: ops.sim_ahead_weeks("FIRED", 2)),
        ("save_game", lambda: ops.save_game("FIRED")),
        ("advance_week", lambda: ops.advance_week("FIRED")),
    ):
        with pytest.raises(ops.PlayError, match="dismissed"):
            call()
    # Reads stay open — you can still study the job market.
    assert ops.get_standings("FIRED")["regions"]

    # Taking a new job puts the manager back to work.
    offers = ops.get_career("FIRED")["offers"]
    assert offers, "a dismissed seat must be given a job market"
    ops.act("FIRED", "accept_job", {"team_id": offers[0]["team_id"]})
    assert ops.get_state("FIRED")["dismissed"] is False
    assert ops.act("FIRED", "set_tactics", {"aggression": 55.0})["ok"] is True


def test_per_map_lineups_are_settable_not_just_visible(world: str) -> None:
    """An override outranks the default five, so it has to be reachable.

    campaign.dressed_for reads gs.map_lineups first; with no way to change
    one, a browser-left override silently beats every set_lineup made here.
    """
    session = ops._session(world)
    fixture = session.gs.team_fixture("team_nexus")
    map_id = fixture.maps[0]
    roster = sorted(session.gs.teams["team_nexus"].player_ids)

    signable = ops.get_legal_actions(world, ["sign"])["actions"]["sign"]
    ops.act(world, "sign", {"player_id": signable["player_ids"][0]})
    benched = signable["player_ids"][0]
    ops.act(world, "set_lineup", {"player_ids": roster})

    # A stale override wins over the default five until it is cleared.
    ops.set_map_lineup(
        world, fixture.id, map_id, roster[:-1] + [benched]
    )
    view = ops.get_tactics(world)
    assert view["measured_over"]["map_overrides"][map_id][-1] == benched
    assert benched in view["measured_over"]["player_ids"]

    ops.set_map_lineup(world, fixture.id, map_id)
    cleared = ops.get_tactics(world)
    assert cleared["measured_over"]["map_overrides"] == {}
    assert benched not in cleared["measured_over"]["player_ids"]

    # Every per-map decision has to be distinguishable in the replay record:
    # the dressed five changes results, so "set these five" and "clear" must
    # not log identically.
    log = [row for row in session.gs.action_log if row.kind == "set_lineup"]
    per_map = [row for row in log if row.params.get("per_map") == "True"]
    assert len(per_map) == 2
    assert per_map[0].params["player_ids"] != per_map[1].params["player_ids"]
    assert benched in per_map[0].params["player_ids"]
    assert per_map[1].params["player_ids"] == "[]", "a clear must record as one"
    assert all(row.params["map_id"] == map_id for row in per_map)

    with pytest.raises(ops.PlayError, match="exactly 5"):
        ops.set_map_lineup(world, fixture.id, map_id, roster[:3])
    with pytest.raises(ops.PlayError, match="not on your roster"):
        ops.set_map_lineup(world, fixture.id, map_id, roster[:4] + ["nobody"])
    with pytest.raises(ops.PlayError, match="not on that fixture"):
        ops.set_map_lineup(world, fixture.id, "not-a-map", roster)
    with pytest.raises(ops.PlayError, match="no fixture"):
        ops.set_map_lineup(world, "not-a-fixture", map_id, roster)


def test_an_unfinished_fantasy_draft_blocks_the_season(world: str) -> None:
    """The headless env cannot see the draft, so this layer has to.

    Five picks in, a squad is ROSTER_SIZE and reads as ready — advancing
    would start the season half-drafted and forfeit every club's remaining
    picks. The browser refuses the same state.
    """
    from esports_sim.manager.state import FantasyDraftState

    session = ops._session(world)
    session.gs.fantasy_draft = FantasyDraftState(active=True, started=True)

    state = ops.get_state(world)
    assert state["can_advance"] is False
    assert "fantasy draft" in state["advance_blocked_by"]
    assert any("fantasy draft" in call for call in state["deadlines"])
    with pytest.raises(ops.PlayError, match="fantasy draft"):
        ops.advance_week(world)
    with pytest.raises(ops.PlayError, match="fantasy draft"):
        ops.act(world, "advance", {})
    assert ops.sim_ahead_weeks(world, max_weeks=3)["weeks_advanced"] == 0

    # Draft over: the season starts normally again.
    session.gs.fantasy_draft.active = False
    assert ops.get_state(world)["can_advance"] is True
    assert ops.advance_week(world)["advanced"] is True


def test_standing_advisories_do_not_halt_a_fast_forward(world: str) -> None:
    """A deadline stops the tick; a nudge that is true for weeks must not.

    "A contract expires within six weeks" holds for six consecutive weeks, so
    halting on it would make sim_ahead a permanent no-op — a worse failure
    than the burnt week it was meant to prevent.
    """
    state = ops.get_state(world)
    advisory = [call for call in state["needs_you"] if call not in state["deadlines"]]
    assert advisory and "within 6 weeks" in advisory[0]
    assert state["deadlines"] == []
    run = ops.sim_ahead_weeks(world, max_weeks=3)
    assert run["weeks_advanced"] >= 1, "an advisory froze the fast-forward"


def test_a_contract_in_its_last_week_is_a_deadline(world: str) -> None:
    session = ops._session(world)
    doomed = sorted(session.gs.teams["team_nexus"].player_ids)[0]
    session.gs.players[doomed].contract_weeks_left = ops.URGENT_CONTRACT_WEEKS
    state = ops.get_state(world)
    expiring = [call for call in state["deadlines"] if "expire this week" in call]
    assert expiring and session.gs.players[doomed].handle in expiring[0]
    assert ops.sim_ahead_weeks(world, max_weeks=3)["weeks_advanced"] == 0


def test_sim_ahead_will_not_burn_the_week_it_should_stop_for(
    world: str
) -> None:
    """Entry check, not just the post-tick one.

    A pending bid or a contract in its last week sets needs_you without
    blocking the advance, so checking only can_advance would consume the week
    the caller was promised a stop for — and expire the thing it stopped for.
    """
    session = ops._session(world)
    seller = next(
        tid for tid in sorted(session.gs.teams)
        if tid != "team_nexus" and session.gs.teams[tid].player_ids
    )
    from esports_sim.manager.state import TransferOffer

    session.gs.transfer_offers.append(
        TransferOffer(
            player_id=sorted(session.gs.teams["team_nexus"].player_ids)[0],
            from_team="team_nexus", to_team=seller,
            fee=100_000, expires_week=session.gs.week + 1,
        )
    )
    state = ops.get_state(world)
    assert state["can_advance"], "the bid must not block the tick by itself"
    assert any("bid" in call for call in state["needs_you"])

    run = ops.sim_ahead_weeks(world, max_weeks=4)
    assert run["weeks_advanced"] == 0, "fast-forward burned the pending bid"
    assert "needs you" in run["stopped_because"]
    assert ops.get_state(world)["week"] == state["week"]


def test_scenario_starts_are_in_the_replay_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """seed + action_log is meant to determine a career; a pick left out breaks that."""
    from esports_sim.manager import scenarios

    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    chosen = sorted(scenarios.SCENARIOS)[0]
    ops.new_game(
        team_id="team_nexus", seed=6, code="SCENA", scenario=chosen
    )
    log = ops._session("SCENA").gs.action_log
    assert [row.kind for row in log] == ["scenario_start"]
    assert log[0].params == {"scenario": chosen}
    assert log[0].team_id == "team_nexus"

    ops.new_game(team_id="team_nexus", seed=6, code="PLAIN")
    assert ops._session("PLAIN").gs.action_log == []


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
    assert starter["agents"][0]["mastery"] >= starter["agents"][-1]["mastery"]
    # Every agent is a legal lock, so every agent has to be named — an option
    # the contract omits can only be reached by guessing an id.
    assert {a["agent_id"] for a in starter["agents"]} == set(ops._gamedata().agents)
    assert len(view["measured_over"]["player_ids"]) == 5
    assert view["measured_over"]["benched"] == []


def test_tactics_fit_measures_the_dressed_five_not_the_bench(world: str) -> None:
    """Past five players the engine only ever sees campaign.dressed_for's five.

    A bench-inclusive average would describe a team that never takes the
    server, so signing a sixth player must not move the fit numbers until that
    player is actually dressed.
    """
    from esports_sim.manager import market

    session = ops._session(world)
    signable = ops.get_legal_actions(world, ["sign"])["actions"]["sign"]
    assert signable["enabled"], "need a free agent to bench"
    before = ops.get_tactics(world)
    five = list(session.gs.teams["team_nexus"].player_ids)

    ops.act(world, "sign", {"player_id": signable["player_ids"][0]})
    assert len(session.gs.teams["team_nexus"].player_ids) == 6
    ops.act(world, "set_lineup", {"player_ids": five})

    benched = ops.get_tactics(world)
    assert set(benched["measured_over"]["player_ids"]) == set(five)
    assert len(benched["measured_over"]["benched"]) == 1
    assert benched["dials"] == before["dials"], (
        "a benched player must not move the fit the engine will apply"
    )
    # The signing is still offered an agent menu — it just is not dressing.
    assert len(benched["lineup"]) == 6
    assert sum(1 for row in benched["lineup"] if row["dressing"]) == market.ROSTER_SIZE

    swapped = five[:-1] + [signable["player_ids"][0]]
    ops.act(world, "set_lineup", {"player_ids": swapped})
    after = ops.get_tactics(world)
    assert set(after["measured_over"]["player_ids"]) == set(swapped)
    assert after["dials"] != before["dials"], (
        "dressing a different five must move the fit"
    )


def test_agent_lock_overrides_and_clears(world: str) -> None:
    starter = ops.get_tactics(world)["lineup"][0]
    # Deliberately the WORST pick, not the runner-up: a low-mastery agent is
    # still a legal lock, and it is the one a truncated menu would have hidden.
    other = next(
        option["agent_id"] for option in reversed(starter["agents"])
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


def test_a_world_moved_by_another_process_is_reloaded(world: str) -> None:
    """Worlds are browser-joinable now, so this process is not the only writer.

    Serving a cached GameState that disk has moved past is the case that
    destroys work: the next write here would stamp a stale world over the
    other process's decisions.
    """
    from esports_sim.manager.state import GameState

    path = ops.save_path_for(world)
    assert ops.get_state(world)["team"]["balance"] > 0
    # Another process (the browser) opens, changes and saves the same world.
    theirs = GameState.load(path)
    theirs.teams["team_nexus"].tactics.aggression = 33.0
    theirs.save(path)

    reloaded = ops.get_observation(world, ["tactics"])["tactics"]
    assert reloaded["aggression"] == 33.0, "MCP served a stale world"
    # And our next decision builds on theirs instead of overwriting it.
    ops.act(world, "set_tactics", {"pace": 44.0})
    disk = GameState.load(path)
    assert disk.teams["team_nexus"].tactics.aggression == 33.0
    assert disk.teams["team_nexus"].tactics.pace == 44.0


def test_fill_gap_rejects_a_role_the_sweep_could_never_match(world: str) -> None:
    """Same silent-empty failure as "any" — reject or normalise, never pass through."""
    desk = ops.get_scouting(world)["directives"]
    assert set(desk["roles"]) == {
        "duelist", "controller", "initiator", "sentinel", "flex"
    }
    assert desk["role_wildcard"] == "any"
    for bad in ("Duelist ", "DUELIST"):  # canonical roles are lower-case
        ops.set_scout_directive(world, "pro", "fill_gap", role=bad)
        assert ops.get_scouting(world)["pro"]["directive"] == "fill_gap:duelist:any"
    for bad in ("awper", "igl", "striker"):
        with pytest.raises(ops.PlayError, match="unknown role"):
            ops.set_scout_directive(world, "pro", "fill_gap", role=bad)


def test_series_preview_does_not_pass_map_one_off_as_the_series(
    world: str
) -> None:
    """A BO3 resolves its dressed five per map, so one preview can be a lie."""
    session = ops._session(world)
    signable = ops.get_legal_actions(world, ["sign"])["actions"]["sign"]
    ops.act(world, "sign", {"player_id": signable["player_ids"][0]})
    five = [
        pid for pid in session.gs.teams["team_nexus"].player_ids
        if pid != signable["player_ids"][0]
    ]
    ops.act(world, "set_lineup", {"player_ids": five})

    fixture = session.gs.team_fixture("team_nexus")
    assert fixture is not None
    single = ops.get_tactics(world)
    assert single["per_map"] is None, "one map cannot disagree with itself"

    # Give the series a second map and dress a different five on it.
    fixture.maps = list(fixture.maps) + ["ascent"]
    fixture.best_of = 3
    session.gs.map_lineups[f"team_nexus|{fixture.id}|ascent"] = (
        five[:-1] + [signable["player_ids"][0]]
    )
    view = ops.get_tactics(world)
    assert view["per_map"] is not None, "diverging maps must be surfaced"
    assert [m["map_id"] for m in view["per_map"]] == list(fixture.maps)
    assert view["per_map"][0]["dials"] == view["dials"]
    assert view["per_map"][1]["dials"] != view["dials"]
    assert fixture.maps[0] in view["measured_over"]["source"]


def test_every_decision_survives_a_dropped_client(world: str) -> None:
    """No mutation may live only in memory.

    An MCP client is its own process and can vanish after any single call, so
    a decision the caller was told had landed must already be on disk.
    """
    ops.act(world, "set_tactics", {"util_discipline": 77.0})
    ops.set_scout_directive(world, "amateur", "track_academy")
    starter = ops.get_tactics(world)["lineup"][0]
    ops.set_agent_lock(world, starter["player_id"], starter["agents"][1]["agent_id"])
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
    ops.set_agent_lock(world, starter["player_id"], starter["agents"][1]["agent_id"])
    # An agent lock is a lineup change, not a role/playstyle reassignment —
    # "set_assignment" is the web's kind for the latter, and recording it here
    # would hand replay an action whose params do not belong to it.
    logged = session.gs.action_log[-1]
    assert logged.kind == "set_lineup"
    assert logged.params["agents"] == "True"
    assert logged.params["agent_id"] == starter["agents"][1]["agent_id"]


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


def test_browser_can_actually_open_an_mcp_world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive the real lobby, because the compat claim is otherwise untested.

    A "solo" world is reachable only through the per-browser history in
    sessions.json, which an MCP-created world can never be in, so marking it
    solo made the claim false. Shared worlds are reachable by code, and the
    lobby releases a human seat whenever no browser is attached to it.
    """
    from esports_sim.web import server as web

    saves = tmp_path / "saves"
    monkeypatch.setattr(ops, "SAVE_DIR", saves)
    monkeypatch.setattr(ops, "_SESSIONS", {})
    monkeypatch.setattr(web, "SAVE_DIR", saves)
    monkeypatch.setattr(web, "_SESSIONS_PATH", saves / "sessions.json")
    lobby = web.Lobby()
    monkeypatch.setattr(lobby, "gd", ops._gamedata(), raising=False)

    created = ops.new_game(team_id="team_nexus", seed=9)
    code = created["code"]
    ops.act(code, "set_tactics", {"aggression": 61.0})

    game, error = lobby.join_game("0" * 32, code, "team_nexus")
    assert error is None, f"browser could not open the MCP world: {error}"
    assert game is not None and game.gs is not None
    # Same world, not a fresh one: the decision made over MCP is there.
    assert game.gs.teams["team_nexus"].tactics.aggression == 61.0
    assert "team_nexus" in game.gs.human_team_ids


def test_legacy_careers_start_from_the_board_slate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The offer IS the brief: archetype sets the contract goal and patience.

    Without it career.create_seat fabricates a sleeping_giant contract, so an
    offered dynasty or rebuilder club silently gets the wrong goal — and any
    club at all can be picked, which the browser refuses.
    """
    monkeypatch.setattr(ops, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(ops, "_SESSIONS", {})
    slate = ops.list_career_offers(seed=21)["offers"]
    assert slate and {o["archetype"] for o in slate} > {"sleeping_giant"}
    assert all(o["team_name"] for o in slate)

    offered = next(o for o in slate if o["archetype"] != "sleeping_giant")
    ops.new_game(
        team_id=offered["team_id"], seed=21, code="LEGCY", mode="legacy"
    )
    seat = ops.get_career("LEGCY")["seat"]
    assert seat["archetype"] == offered["archetype"]
    assert seat["contract"]["goal"] == offered["goal"]
    assert seat["contract"]["patience"] == offered["patience"]

    unoffered = next(
        tid for tid in sorted(ops._session("LEGCY").gs.teams)
        if tid not in {o["team_id"] for o in slate}
    )
    with pytest.raises(ops.PlayError, match="not offering you a job"):
        ops.new_game(
            team_id=unoffered, seed=21, code="NOJOB", mode="legacy"
        )
    # Sandbox is still a free pick: a seat, but no contract to be fired from.
    ops.new_game(team_id=unoffered, seed=21, code="SANDB")
    sandbox_seat = ops.get_career("SANDB")["seat"]
    assert sandbox_seat["team_id"] == unoffered
    assert sandbox_seat["contract"] is None


def test_a_browser_taking_the_seat_stops_mcp_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk stamp cannot see a browser that has not saved yet.

    The web layer defers its writes, so a browser can be several decisions
    ahead with the save file untouched. Once it has claimed the seat, this
    module must stop writing rather than race it.
    """
    from esports_sim.web import server as web

    saves = tmp_path / "saves"
    monkeypatch.setattr(ops, "SAVE_DIR", saves)
    monkeypatch.setattr(ops, "_SESSIONS", {})
    monkeypatch.setattr(web, "SAVE_DIR", saves)
    monkeypatch.setattr(web, "_SESSIONS_PATH", saves / "sessions.json")
    lobby = web.Lobby()
    monkeypatch.setattr(lobby, "gd", ops._gamedata(), raising=False)

    code = ops.new_game(team_id="team_nexus", seed=9)["code"]
    ops.act(code, "set_tactics", {"aggression": 61.0})

    game, error = lobby.join_game("0" * 32, code, "team_nexus")
    assert error is None and game is not None

    # Reads keep working — the browser is playing, not deleting.
    assert ops.get_state(code)["team"]["id"] == "team_nexus"
    assert ops.get_standings(code)["regions"]
    for mutate in (
        lambda: ops.act(code, "set_tactics", {"aggression": 20.0}),
        lambda: ops.advance_week(code),
        lambda: ops.set_scout_directive(code, "amateur", "track_academy"),
        lambda: ops.save_game(code),
    ):
        with pytest.raises(ops.PlayError, match="other human managers"):
            mutate()
    # Leaving our own seat hands it back — that club is still ours.
    lobby.leave("0" * 32)
    assert ops.act(code, "set_tactics", {"aggression": 20.0})["ok"] is True


def test_a_second_human_club_keeps_the_world_read_only_for_good(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leaving detaches the session but never gives the club back to the AI.

    Lobby.leave pops sessions.json; gs.human_team_ids keeps the club forever.
    Advancing from here would then tick a human club's week with no manager
    at all — the browser is gone and the AI skips human teams — so the
    durable signal has to be the save, not the sidecar.
    """
    from esports_sim.web import server as web

    saves = tmp_path / "saves"
    monkeypatch.setattr(ops, "SAVE_DIR", saves)
    monkeypatch.setattr(ops, "_SESSIONS", {})
    monkeypatch.setattr(web, "SAVE_DIR", saves)
    monkeypatch.setattr(web, "_SESSIONS_PATH", saves / "sessions.json")
    lobby = web.Lobby()
    monkeypatch.setattr(lobby, "gd", ops._gamedata(), raising=False)

    code = ops.new_game(team_id="team_nexus", seed=9)["code"]
    assert ops.advance_week(code)["advanced"] is True

    rival = next(
        tid for tid in sorted(ops._session(code).gs.teams)
        if tid != "team_nexus" and ops._session(code).gs.teams[tid].tier == 1
    )
    game, error = lobby.join_game("1" * 32, code, rival)
    assert error is None and game is not None
    with pytest.raises(ops.PlayError, match="other human managers"):
        ops.advance_week(code)

    lobby.leave("1" * 32)
    assert not ops._attached_browsers(code), "the sidecar entry is gone"
    assert rival in ops._session(code).gs.human_team_ids, "but the club is not"
    with pytest.raises(ops.PlayError, match="other human managers"):
        ops.advance_week(code)
    assert ops.get_standings(code)["regions"], "reads must still work"


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
