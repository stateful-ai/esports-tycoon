"""Replay identities belong to the played map, not today's squad."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import new_campaign
from esports_sim.manager.campaign import runtime_gamedata, _dressed_gamedata
from esports_sim.manager.state import Fixture, MapResult, PlayerLineSnap
from esports_sim.schemas.events import CommsEvent
from esports_sim.sim import simulate_match_result
from esports_sim.sim.stats import compute_match_stats
from esports_sim.web import server


@pytest.fixture(scope="module")
def played_map(game_data):
    gs = new_campaign(game_data, seed=2038, user_team_id="team_nexus")
    a, b = "team_nexus", "team_sahara_compass"
    # A sixth roster member dresses in Vortex's place; the replay must show
    # the actual substitute and omit the rested player even before transfers.
    gs.teams[a].player_ids.append("fa_13")
    gs.free_agent_ids.remove("fa_13")
    dressed = {a: [pid for pid in gs.teams[a].player_ids if pid != "vortex"],
               b: list(gs.teams[b].player_ids)}
    gd = _dressed_gamedata(gs, runtime_gamedata(gs, game_data), dressed)
    result = simulate_match_result(gd, a, b, "lotus", 2038)
    team_of = {pid: tid for tid, pids in dressed.items() for pid in pids}
    stats = compute_match_stats(result.events, team_of)
    fixture = Fixture(
        id="historical", week=1, team_a=a, team_b=b, maps=["lotus"],
        played=True, winner_id=result.winner_id,
        results=[MapResult(
            map_id="lotus", seed=2038, score_a=result.score_a,
            score_b=result.score_b, winner_id=result.winner_id,
            lines=[PlayerLineSnap(player_id=ln.player_id, kills=ln.kills,
                                  deaths=ln.deaths, rating=ln.rating)
                   for ln in stats.lines.values()],
        )],
    )
    gs.fixtures.append(fixture)
    return gs, fixture, result.events, team_of


@pytest.mark.parametrize("change", ["release", "transfer", "agent_lock"])
def test_replay_preserves_played_identity_after_roster_changes(
    played_map, game_data, change
):
    original, old_fixture, events, expected_teams = played_map
    gs = original.model_copy(deep=True)
    fixture = next(f for f in gs.fixtures if f.id == old_fixture.id)
    former = "team_sahara_compass_p1"
    historical_agent = events[0].agents[former]
    if change in {"release", "transfer"}:
        gs.teams[fixture.team_b].player_ids.remove(former)
        gs.teams[fixture.team_b].player_ids.append("fa_7")
        gs.free_agent_ids.remove("fa_7")
        if change == "transfer":
            gs.teams[fixture.team_a].player_ids.append(former)
        else:
            gs.free_agent_ids.append(former)
    else:
        gs.teams[fixture.team_b].lineup.agents[former] = (
            "omen" if historical_agent != "omen" else "jett"
        )
    game = server._Game(game_data, "REPLAY", gs=gs)
    game.event_logs[fixture.id] = [events]
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    before = gs.model_dump_json()
    try:
        response = server.replay(fixture.id, 0)
        assert set(response["players"]) == set(events[0].agents)
        assert "fa_7" not in response["players"]
        assert "vortex" not in response["players"]
        assert "fa_13" in response["players"]
        for pid, identity in response["players"].items():
            assert identity["team_id"] == expected_teams[pid]
            assert identity["agent_id"] == events[0].agents[pid]
            assert identity["agent_icon"] == server._agent_icon_url(events[0].agents[pid])
            assert identity["handle"] == gs.players[pid].handle
        former_line = next(ln for ln in response["box_score"] if ln["player_id"] == former)
        assert former_line["team_id"] == fixture.team_b
        assert former_line["handle"] == gs.players[former].handle
        assert gs.model_dump_json() == before
    finally:
        server._ctx.reset(token)


@pytest.mark.parametrize("placement_mode", ["missing", "partial", "ambiguous"])
def test_replay_does_not_guess_teams_from_incomplete_placements(
    played_map, game_data, placement_mode
):
    gs, fixture, original_events, _ = played_map
    start = original_events[0]
    round_start = next(e for e in original_events if e.type == "round.start")
    placements = [e.model_copy(deep=True) for e in original_events
                  if e.type == "round.move" and e.from_callout is None][:10]
    if placement_mode == "missing":
        placements = []
    elif placement_mode == "partial":
        placements = placements[:9]
    else:
        for event in placements:
            event.to_callout = game_data.maps["lotus"].attacker_spawn
    game = server._Game(game_data, "REPLAY", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    try:
        identities = server._replay_players(gs, fixture, [start, round_start, *placements], fixture.results[0])
        assert all(p["team_id"] is None for p in identities.values())
        # Explicit team evidence remains usable even without placements.
        events = [start, round_start, *placements, CommsEvent(
            team_id=fixture.team_b, player_id="team_sahara_compass_p1", kind="call"
        )]
        identities = server._replay_players(gs, fixture, events, fixture.results[0])
        assert identities["team_sahara_compass_p1"]["team_id"] == fixture.team_b
    finally:
        server._ctx.reset(token)


def test_replay_opening_placements_follow_round_side_switch(played_map, game_data):
    gs, fixture, original_events, expected = played_map
    # Reverse both the round sides and initial placements to model halftime.
    start = original_events[0]
    round_start = next(e for e in original_events if e.type == "round.start").model_copy(deep=True)
    round_start.attacking_team_id, round_start.defending_team_id = (
        round_start.defending_team_id, round_start.attacking_team_id
    )
    m = game_data.maps["lotus"]
    placements = [e.model_copy(deep=True) for e in original_events
                  if e.type == "round.move" and e.from_callout is None][:10]
    for event in placements:
        event.to_callout = (m.attacker_spawn
                            if expected[event.player_id] == round_start.attacking_team_id
                            else m.defender_spawn)
    game = server._Game(game_data, "REPLAY", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, gs.user_team_id))
    try:
        identities = server._replay_players(gs, fixture, [start, round_start, *placements], fixture.results[0])
        assert {pid: p["team_id"] for pid, p in identities.items()} == expected
    finally:
        server._ctx.reset(token)
