from __future__ import annotations

import pytest

from esports_sim.manager import culture, locker_room, promises, market, development
from esports_sim.manager import campaign as campaign_mod
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState, SCHEMA_VERSION
from esports_sim.registry import GameData
from esports_sim.schemas.promise import ManagerPromise
from esports_sim.schemas import Player


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=8128)


def _add_sixth_player(gs: GameState, team_id: str) -> str:
    new_pid = "dummy_six"
    first_pid = gs.teams[team_id].player_ids[0]
    p = gs.players[first_pid].model_copy(update={"id": new_pid, "handle": "DummySix"})
    gs.players[new_pid] = p
    gs.teams[team_id].player_ids.append(new_pid)
    return new_pid


def test_hierarchy_roles(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    team = gs.teams[tid]
    
    # 1. Test Designated Captain is automatically "leader"
    captain_id = team.captain_id
    assert locker_room.get_hierarchy_role(gs, captain_id, tid) == "incumbent_leader"
    
    # 2. Test Rookie age <= 20
    rookie_id = sorted(team.player_ids)[0]
    rookie = gs.players[rookie_id]
    rookie.age = 19
    rookie.followers = 0
    # Clear attributes to ensure quality < 76
    rookie.attributes = {k: 50.0 for k in rookie.attributes}
    if rookie_id == captain_id:
        # Swap captaincy to someone else so rookie_id isn't captain
        other_id = sorted(team.player_ids)[1]
        team.captain_id = other_id
    assert locker_room.get_hierarchy_role(gs, rookie_id, tid) == "rookie"
    
    # 3. Test High Score is "leader"
    p_id = sorted(team.player_ids)[2]
    if p_id == team.captain_id:
        p_id = sorted(team.player_ids)[3]
    p = gs.players[p_id]
    p.age = 28
    p.tenure_weeks = 80
    p.personality_tags = ["leader", "veteran"]
    # Force high leadership score
    p.attributes["comms_quality"] = p.attributes["game_sense"] = 90.0
    role = locker_room.get_hierarchy_role(gs, p_id, tid)
    assert role == "council_member"
    
    # 4. Test "star_player" is "influential"
    p_star_id = sorted(team.player_ids)[4]
    if p_star_id in (team.captain_id, p_id):
        p_star_id = sorted(team.player_ids)[1]
    p_star = gs.players[p_star_id]
    p_star.age = 22
    p_star.tenure_weeks = 10
    p_star.personality_tags = ["star_player"]
    role_star = locker_room.get_hierarchy_role(gs, p_star_id, tid)
    assert role_star == "core"


def test_benching_cascades(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    team = gs.teams[tid]
    
    # Add a 6th player so benching applies
    _add_sixth_player(gs, tid)
    
    # Get players
    pids = sorted(team.player_ids)
    p_leader = gs.players[pids[0]]
    p_influential = gs.players[pids[1]]
    p_rookie = gs.players[pids[2]]
    
    # Configure roles
    team.captain_id = p_leader.id
    
    p_influential.age = 23
    p_influential.tenure_weeks = 20
    p_influential.personality_tags = ["star_player"]
    
    p_rookie.age = 19
    p_rookie.followers = 0
    p_rookie.personality_tags = ["rookie"]
    p_rookie.attributes = {k: 50.0 for k in p_rookie.attributes}
    
    # Verify their roles
    assert locker_room.get_hierarchy_role(gs, p_leader.id, tid) == "incumbent_leader"
    assert locker_room.get_hierarchy_role(gs, p_influential.id, tid) == "core"
    assert locker_room.get_hierarchy_role(gs, p_rookie.id, tid) == "rookie"
    
    # Mock benching week:
    # 1. Leader benched:
    # Teammates morale drops by -4.0, team chemistry drops by -3.0, own morale drops by -5.0.
    team.chemistry = 70.0
    for p in gs.roster(tid):
        p.morale = 75.0
        
    week_dressed = {tid: {p_influential.id, p_rookie.id}} # leader and core benched
    # Let's add other team players to played set so they are dressed
    for pid in pids[3:]:
        week_dressed[tid].add(pid)
        
    campaign_mod._apply_bench_week(gs, week_dressed)
    
    # Teammates (p_influential, p_rookie) morale drops by -4.0
    assert p_influential.morale == 71.0
    # p_leader was benched: own morale drops by -5.0 (75.0 - 5.0 = 70.0)
    assert p_leader.morale == 70.0
    # team chemistry drops by -3.0 (70.0 - 3.0 = 67.0)
    assert team.chemistry == 67.0


def test_releasing_cascades(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    team = gs.teams[tid]
    
    # Get players
    pids = sorted(team.player_ids)
    p_leader = gs.players[pids[0]]
    p_influential = gs.players[pids[1]]
    p_rookie = gs.players[pids[2]]
    
    # Configure roles
    team.captain_id = p_leader.id
    
    p_influential.age = 23
    p_influential.tenure_weeks = 20
    p_influential.personality_tags = ["star_player"]
    
    p_rookie.age = 19
    p_rookie.followers = 0
    p_rookie.personality_tags = ["rookie"]
    p_rookie.attributes = {k: 50.0 for k in p_rookie.attributes}
    
    # Reset morale, chemistry, sentiment
    for p in gs.roster(tid):
        p.morale = 75.0
    team.chemistry = 70.0
    gs.team_sentiment[tid] = 50.0
    
    # Release leader
    market._departure_consequences(gs, tid, p_leader.id)
    # Remaining teammates (influential, rookie) morale drops by -8.0
    assert p_influential.morale == 67.0
    assert p_rookie.morale == 67.0
    assert team.chemistry == 65.0
    assert gs.sentiment(tid) == 44.0
    
    # Reset and release rookie
    for p in gs.roster(tid):
        p.morale = 75.0
    team.chemistry = 70.0
    gs.team_sentiment[tid] = 50.0
    
    market._departure_consequences(gs, tid, p_rookie.id)
    # Remaining teammates morale drops by -0.5, chemistry 0.0, sentiment -1.0
    assert p_influential.morale == 74.5
    assert team.chemistry == 70.0
    assert gs.sentiment(tid) == 49.0


def test_promises_lifecycle(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    team = gs.teams[tid]
    
    # 1. Play time promise
    pids = sorted(team.player_ids)
    pid = pids[0]
    p = gs.players[pid]
    p.morale = 70.0
    p.confidence = 50.0
    team.chemistry = 70.0
    
    # Create promise
    promise = ManagerPromise(
        id="promise_1",
        team_id=tid,
        player_id=pid,
        promise_type="play_time",
        weeks_left=3,
        created_week=gs.week,
        created_season=gs.season,
        status="active"
    )
    gs.promises.append(promise)
    
    # First week: dressed
    week_dressed = {tid: {pid}}
    promises.weekly_tick(gs, week_dressed)
    assert promise.status == "active"
    assert promise.weeks_left == 2
    
    # Second week: benched -> broken
    # Make sure team plays but player doesn't dress
    week_dressed_2 = {tid: {"some_other_player"}}
    promises.weekly_tick(gs, week_dressed_2)
    assert promise.status == "broken"
    assert promise.weeks_left == 4  # reset to 4 for housekeeping
    
    # Morale should drop: personality-scaled drop, chemistry: -8.0, confidence: -15.0
    assert p.morale == 50.5
    assert p.confidence == 35.0
    assert team.chemistry == 62.0
    
    # 2. Contract renewal promise
    promise_renew = ManagerPromise(
        id="promise_2",
        team_id=tid,
        player_id=pid,
        promise_type="renew_contract",
        weeks_left=2,
        created_week=gs.week,
        created_season=gs.season,
        status="active"
    )
    gs.promises.append(promise_renew)
    p.morale = 70.0
    team.chemistry = 70.0
    
    # Renew contract -> kept
    market.renew_contract(gs, tid, pid)
    assert promise_renew.status == "kept"
    assert promise_renew.weeks_left == 4
    # Kept: player morale +10, chemistry +5 (plus contract renewal defaults)
    assert p.morale > 75.0
    assert team.chemistry > 70.0
    
    # 3. Make captain promise
    # Ensure player is not currently captain
    team.captain_id = pids[1]
    
    promise_captain = ManagerPromise(
        id="promise_3",
        team_id=tid,
        player_id=pid,
        promise_type="make_captain",
        weeks_left=1,
        created_week=gs.week,
        created_season=gs.season,
        status="active"
    )
    gs.promises.append(promise_captain)
    
    # Tick week without naming captain -> broken
    promises.weekly_tick(gs, {tid: {pid}})
    assert promise_captain.status == "broken"
    assert promise_captain.weeks_left == 4
    
    # Naming captain should resolve active promise
    team.captain_id = pids[1]
    promise_captain_2 = ManagerPromise(
        id="promise_4",
        team_id=tid,
        player_id=pid,
        promise_type="make_captain",
        weeks_left=2,
        created_week=gs.week,
        created_season=gs.season,
        status="active"
    )
    gs.promises.append(promise_captain_2)
    culture.set_leadership(gs, tid, pid, [], "balanced")
    assert promise_captain_2.status == "kept"
    assert promise_captain_2.weeks_left == 4


def test_practice_week_mentorship(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    team = gs.teams[tid]
    pids = sorted(team.player_ids)
    
    mentor = gs.players[pids[0]]
    protege = gs.players[pids[1]]
    
    # Make mentor a Veteran and protege a Rookie
    mentor.age = 28
    mentor.personality_tags = ["reliable"]
    protege.age = 18
    protege.personality_tags = ["student"]
    
    # Set mentorship on state
    gs.mentorships[protege.id] = mentor.id
    
    # Clear this week's fixtures to make it a practice week
    gs.fixtures = []
    
    old_potential = protege.potential
    development.apply_mentorship_growth(gs)
    
    # Protege should have either increased potential or acquired "reliable" tag
    has_tag = "reliable" in protege.personality_tags
    potential_increased = protege.potential > old_potential
    assert has_tag or potential_increased


def test_save_migration() -> None:
    # Mock data at v23
    data = {
        "schema_version": 23,
        "seed": 12345,
        "user_team_id": "team_1",
        "human_team_ids": ["team_1"],
        "teams": {},
        "players": {},
        "fixtures": [],
    }
    from esports_sim.manager.state import _migrate_v23_to_v24
    migrated = _migrate_v23_to_v24(data)
    assert migrated["promises"] == []


def test_promise_resolution_released_player(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    team = gs.teams[tid]
    
    # 1. Play time promise
    pids = sorted(team.player_ids)
    pid = pids[0]
    p = gs.players[pid]
    p.morale = 70.0
    p.confidence = 50.0
    team.chemistry = 70.0
    
    # Force the player to be a leader to exercise that code path
    team.captain_id = pid
    assert locker_room.get_hierarchy_role(gs, pid, tid) == "incumbent_leader"
    
    # Create promise
    promise = ManagerPromise(
        id="promise_release_test",
        team_id=tid,
        player_id=pid,
        promise_type="play_time",
        weeks_left=2,
        created_week=gs.week,
        created_season=gs.season,
        status="active"
    )
    gs.promises.append(promise)
    
    # Initialize all teammate morale to 80.0
    for mate_id in team.player_ids:
        if mate_id != pid:
            gs.players[mate_id].morale = 80.0
            
    # Now release the player: remove from team roster
    team.player_ids.remove(pid)
    if team.captain_id == pid:
        team.captain_id = team.player_ids[0] if team.player_ids else None
    
    # Run weekly tick to trigger promise resolution (since player is released, they won't dress)
    week_dressed = {tid: {team.player_ids[0]}}
    promises.weekly_tick(gs, week_dressed)
    
    # Assert promise is broken
    assert promise.status == "broken"
    # Chemistry should drop: 70.0 - 8.0 = 62.0
    assert team.chemistry == 62.0
    # Teammate morale should NOT drop because the released player's role logic was skipped
    for mate_id in team.player_ids:
        assert gs.players[mate_id].morale == 80.0


def test_promise_resolution_retired_player(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    team = gs.teams[tid]
    
    # 1. Play time promise
    pids = sorted(team.player_ids)
    pid = pids[0]
    p = gs.players[pid]
    p.morale = 70.0
    p.confidence = 50.0
    team.chemistry = 70.0
    
    # Force the player to be a leader to exercise that code path
    team.captain_id = pid
    assert locker_room.get_hierarchy_role(gs, pid, tid) == "incumbent_leader"
    
    # Create promise
    promise = ManagerPromise(
        id="promise_retire_test",
        team_id=tid,
        player_id=pid,
        promise_type="play_time",
        weeks_left=2,
        created_week=gs.week,
        created_season=gs.season,
        status="active"
    )
    gs.promises.append(promise)
    
    # Now retire the player: remove from gs.players and team roster
    team.player_ids.remove(pid)
    if team.captain_id == pid:
        team.captain_id = team.player_ids[0] if team.player_ids else None
    del gs.players[pid]
    
    # Run weekly tick to trigger promise resolution. It must not crash.
    week_dressed = {tid: {team.player_ids[0]}}
    promises.weekly_tick(gs, week_dressed)
    
    # Assert promise is broken
    assert promise.status == "broken"
    # Chemistry should drop: 70.0 - 8.0 = 62.0
    assert team.chemistry == 62.0

