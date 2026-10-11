"""Mentorship programs settle through the real campaign tick, not a UI timer."""

from unittest.mock import patch

import pytest

from esports_sim.manager import campaign, development, mentorship
from esports_sim.manager.state import GameState


@pytest.fixture
def world(game_data):
    gs = campaign.new_campaign(game_data, seed=2038)
    mentor, protege = gs.teams[gs.user_team_id].player_ids[:2]
    for pid, age, ability in [(mentor, 27, 90.0), (protege, 18, 55.0)]:
        player = gs.players[pid]
        player.age = age
        player.personality_tags = []
        player.attributes = {key: ability for key in player.attributes}
    assert mentorship.pair_mentorship(gs, protege, mentor)
    # Exercise a real practice week while retaining the future calendar.
    gs.fixtures = [f for f in gs.fixtures if f.week != gs.week]
    return gs, protege, mentor


def advance(gs, game_data):
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="neutral"):
        return campaign.advance_week(gs, game_data)


def test_weekly_progress_persists_and_continues_after_load(world, game_data, tmp_path):
    gs, protege, mentor = world
    advance(gs, game_data)
    assert gs.mentorships[protege] == mentor
    assert gs.mentorship_progress[protege] == 5.0
    path = tmp_path / "mentorship.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert loaded.mentorship_progress == gs.mentorship_progress
    loaded.fixtures = [f for f in loaded.fixtures if f.week != loaded.week]
    advance(loaded, game_data)
    assert loaded.mentorship_progress[protege] == 10.0


def test_campaign_rewards_are_the_existing_development_effects_once(world, game_data):
    gs, protege, _ = world
    control = gs.model_copy(deep=True)
    with patch.object(mentorship, "tick_mentorship"):
        advance(control, game_data)
    with patch.object(development, "apply_mentorship_growth", wraps=development.apply_mentorship_growth) as growth:
        with patch.object(mentorship, "_apply_legacy_rewards", side_effect=AssertionError("doubled rewards")):
            advance(gs, game_data)
    assert growth.call_count == 1
    assert gs.mentorship_progress[protege] == 5.0
    control.mentorship_progress[protege] = 5.0
    assert gs.model_dump_json() == control.model_dump_json()


def test_completion_receives_final_growth_then_clears_pair(world, game_data, tmp_path):
    gs, protege, mentor = world
    gs.mentorship_progress[protege] = 99.0
    seen = []
    original = development.apply_mentorship_growth

    def growth(state):
        seen.append(state.mentorships.get(protege))
        return original(state)

    with patch.object(development, "apply_mentorship_growth", side_effect=growth):
        advance(gs, game_data)
    assert seen == [mentor]
    assert protege not in gs.mentorships
    assert protege not in gs.mentorship_progress
    path = tmp_path / "completed.json"
    gs.save(path)
    loaded = GameState.load(path)
    assert protege not in loaded.mentorships
    assert protege not in loaded.mentorship_progress


@pytest.mark.parametrize("invalid", ["transfer", "missing", "self"])
def test_campaign_cleans_invalid_pair_and_progress(world, game_data, invalid):
    gs, protege, mentor = world
    gs.mentorship_progress[protege] = 30.0
    if invalid == "self":
        gs.mentorships[protege] = protege
    else:
        gs.teams[gs.user_team_id].player_ids.remove(mentor)
        if invalid == "transfer":
            other = next(tid for tid in sorted(gs.teams) if tid != gs.user_team_id)
            gs.teams[other].player_ids.append(mentor)
        else:
            del gs.players[mentor]
    advance(gs, game_data)
    assert protege not in gs.mentorships
    assert protege not in gs.mentorship_progress


def test_loaded_pair_without_progress_starts_at_zero(world, game_data):
    gs, protege, _ = world
    payload = gs.model_dump()
    payload.pop("mentorship_progress")
    loaded = GameState.model_validate(payload)
    advance(loaded, game_data)
    assert loaded.mentorship_progress[protege] == 5.0


def test_empty_lifecycle_is_an_exact_noop(world):
    gs, _, _ = world
    gs.mentorships.clear()
    gs.mentorship_progress.clear()
    before = gs.model_dump_json()
    mentorship.tick_mentorship(gs, apply_rewards=False)
    assert gs.model_dump_json() == before


def test_lifecycle_preserves_admitted_pair_if_protege_overtakes_mentor(world, game_data):
    gs, protege, mentor = world
    gs.players[protege].attributes = {key: 95.0 for key in gs.players[protege].attributes}
    assert not development.mentorship_valid(gs, protege, mentor)
    advance(gs, game_data)
    assert gs.mentorships[protege] == mentor
    assert gs.mentorship_progress[protege] == 5.0


def test_accepted_lower_ability_mentor_still_accumulates_progress(world, game_data):
    gs, protege, mentor = world
    gs.mentorships.clear()
    gs.mentorship_progress.clear()
    gs.players[mentor].attributes = {key: 40.0 for key in gs.players[mentor].attributes}
    assert mentorship.pair_mentorship(gs, protege, mentor)
    assert not development.mentorship_valid(gs, protege, mentor)
    advance(gs, game_data)
    assert gs.mentorships[protege] == mentor
    assert gs.mentorship_progress[protege] == 5.0


def test_campaign_lifecycle_is_deterministic_across_save_roundtrip(world, game_data, tmp_path):
    gs, _, _ = world
    path = tmp_path / "before.json"
    gs.save(path)
    loaded = GameState.load(path)
    advance(gs, game_data)
    advance(loaded, game_data)
    assert gs.model_dump_json() == loaded.model_dump_json()


def test_progress_settles_on_the_played_week_before_calendar_rollover(world, game_data):
    gs, _, _ = world
    played_clock = (gs.season, gs.week, gs.phase)
    seen = []
    original = mentorship.tick_mentorship

    def settle(state, **kwargs):
        seen.append((state.season, state.week, state.phase))
        return original(state, **kwargs)

    with patch.object(mentorship, "tick_mentorship", side_effect=settle):
        advance(gs, game_data)
    assert seen == [played_clock]
    assert gs.week != played_clock[1]


def test_offseason_rollover_does_not_count_as_a_practice_week(world, game_data):
    gs, protege, _ = world
    gs.phase = "offseason"
    gs.mentorship_progress[protege] = 30.0
    with patch.object(mentorship, "tick_mentorship", wraps=mentorship.tick_mentorship) as lifecycle:
        advance(gs, game_data)
    lifecycle.assert_not_called()
    assert gs.mentorship_progress[protege] == 30.0


def test_lifecycle_visits_pairs_in_stable_id_order(world):
    gs, protege, mentor = world
    second = gs.teams[gs.user_team_id].player_ids[2]
    gs.mentorships = {pid: mentor for pid in sorted([protege, second], reverse=True)}
    seen = []

    def hierarchy(state, pid, tid):
        if pid != mentor:
            seen.append(pid)
        return "neutral"

    with patch("esports_sim.manager.locker_room.get_hierarchy_role", side_effect=hierarchy):
        mentorship.tick_mentorship(gs, apply_rewards=False)
    assert seen == sorted([protege, second])
