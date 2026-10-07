"""Browser mentorship decisions persist with the shared action-log vocabulary."""

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException

from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState, ManagerSeat
from esports_sim.web import server


@pytest.fixture(params=[False, True], ids=["solo", "second-human"])
def mentor_world(request, game_data, tmp_path):
    gs = new_campaign(game_data, seed=321)
    tid = gs.user_team_id
    if request.param:
        tid = next(t for t in sorted(gs.teams) if t != tid)
        gs.human_team_ids.append(tid)
        gs.managers["mgr_second"] = ManagerSeat(
            id="mgr_second", name="Second manager", team_id=tid
        )
    protege, mentor = gs.teams[tid].player_ids[:2]
    gs.players[protege].age = 18
    gs.players[mentor].age = 27
    game = server._Game(game_data, "MENTR", gs=gs)
    game.save_path = tmp_path / "campaign.json"
    token = server._ctx.set(server._ReqCtx(game, tid))
    try:
        yield gs, game, tid, protege, mentor
    finally:
        server._ctx.reset(token)


def assert_record(gs, tid, protege, mentor):
    record = gs.action_log[-1]
    assert record.kind == "mentor"
    assert record.params == {"protege_id": protege, "mentor_id": mentor}
    assert record.source == "web"
    assert record.team_id == tid
    assert record.manager_id == gs.seat_for_session(tid).id
    assert (record.season, record.week, record.phase) == (
        gs.season, gs.week, gs.phase
    )


def test_pair_and_clear_records_survive_save_load(mentor_world):
    gs, game, tid, protege, mentor = mentor_world
    initial_actions = len(gs.action_log)
    response = server.mentor_action(
        server.MentorBody(protege_id=protege, mentor_id=mentor)
    )
    assert response["ok"] is True
    assert len(gs.action_log) == initial_actions + 1
    assert_record(gs, tid, protege, mentor)
    assert gs.mentorships[protege] == mentor
    assert gs.mentorship_progress[protege] == 0.0
    assert game.dirty
    game.save(force=True)
    loaded = GameState.load(game.save_path)
    assert loaded.action_log == gs.action_log
    assert loaded.mentorships == gs.mentorships
    assert loaded.mentorship_progress == gs.mentorship_progress

    # Continue on the loaded world to verify the persisted pairing can clear.
    game.gs = loaded
    response = server.mentor_action(server.MentorBody(protege_id=protege))
    assert response["ok"] is True
    assert len(loaded.action_log) == initial_actions + 2
    assert_record(loaded, tid, protege, "")
    assert protege not in loaded.mentorships
    assert protege not in loaded.mentorship_progress
    assert game.dirty
    game.save(force=True)
    cleared = GameState.load(game.save_path)
    assert cleared.action_log == loaded.action_log
    assert cleared.mentorships == loaded.mentorships
    assert cleared.mentorship_progress == loaded.mentorship_progress


@pytest.mark.parametrize("rejection", ["age", "existing", "foreign-mentor", "foreign-protege"])
def test_rejected_pair_does_not_mutate_or_record(mentor_world, rejection):
    gs, game, tid, protege, mentor = mentor_world
    other_tid = next(t for t in sorted(gs.teams) if t != tid)
    foreign = gs.teams[other_tid].player_ids[0]
    if rejection == "age":
        gs.players[mentor].age = 24
    elif rejection == "existing":
        gs.mentorships[protege] = mentor
        gs.mentorship_progress[protege] = 42.0
    elif rejection == "foreign-mentor":
        mentor = foreign
    else:
        protege = foreign
    before = gs.model_dump_json()
    with pytest.raises(HTTPException) as error:
        server.mentor_action(server.MentorBody(protege_id=protege, mentor_id=mentor))
    assert error.value.status_code == 409
    assert gs.model_dump_json() == before
    assert not game.dirty


def test_clear_without_pair_remains_successful_and_records(mentor_world):
    gs, game, tid, protege, _ = mentor_world
    initial_actions = len(gs.action_log)
    assert server.mentor_action(server.MentorBody(protege_id=protege))["ok"]
    assert len(gs.action_log) == initial_actions + 1
    assert_record(gs, tid, protege, "")
    assert protege not in gs.mentorships
    assert game.dirty
