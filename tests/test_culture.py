"""Deterministic locker-room culture and leadership arcs."""

from __future__ import annotations

import pytest

from esports_sim.manager import culture, relationships
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=8128)


def _set_pair_graph(gs: GameState, team_id: str, value: float) -> None:
    roster = sorted(gs.teams[team_id].player_ids)
    for i, a in enumerate(roster):
        for b in roster[i + 1 :]:
            relationships._set(gs, a, b, value)


def test_leadership_score_reads_player_and_locker_room(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    low_id, high_id = sorted(gs.teams[tid].player_ids)[:2]
    low, high = gs.players[low_id], gs.players[high_id]
    low.attributes["comms_quality"] = low.attributes["game_sense"] = 15.0
    low.tenure_weeks = 0
    low.personality_tags = ["volatile"]
    high.attributes["comms_quality"] = high.attributes["game_sense"] = 95.0
    high.tenure_weeks = 156
    high.personality_tags = ["leader", "reliable", "veteran"]
    for mate_id in gs.teams[tid].player_ids:
        if mate_id not in (low_id, high_id):
            relationships._set(gs, low_id, mate_id, 25.0)
            relationships._set(gs, high_id, mate_id, 85.0)

    assert culture.leadership_score(gs, tid, high_id) > 75.0
    assert culture.leadership_score(gs, tid, high_id) > culture.leadership_score(
        gs, tid, low_id
    ) + 30.0
    assert culture.leadership_score(gs, tid, high_id) == culture.leadership_score(
        gs, tid, high_id
    )


def test_ensure_leadership_repairs_stale_state_for_every_team(
    campaign: GameState,
) -> None:
    gs = campaign
    for tid in sorted(gs.teams):
        roster = sorted(gs.teams[tid].player_ids)
        gs.teams[tid].captain_id = "departed-player"
        gs.leadership_groups[tid] = [roster[0], roster[0], "missing"]
        gs.culture_principles[tid] = "not-a-principle"

    culture.ensure_leadership(gs)

    for tid in sorted(gs.teams):
        roster = set(gs.teams[tid].player_ids)
        captain = gs.teams[tid].captain_id
        council = gs.leadership_groups[tid]
        assert captain in roster
        assert len(council) == min(culture.COUNCIL_MAX, len(roster) - 1)
        assert len(council) == len(set(council))
        assert captain not in council
        assert set(council) <= roster
        assert gs.culture_principles[tid] == "balanced"


def test_set_leadership_validates_and_records_bounded_transition(
    campaign: GameState,
) -> None:
    gs = campaign
    tid = gs.user_team_id
    culture.ensure_leadership(gs)
    roster = sorted(gs.teams[tid].player_ids)
    old_captain = gs.teams[tid].captain_id
    new_captain = next(pid for pid in roster if pid != old_captain)
    council = [pid for pid in roster if pid not in (old_captain, new_captain)][:2]
    old_morale = gs.players[old_captain].morale
    new_morale = gs.players[new_captain].morale
    old_chemistry = gs.teams[tid].chemistry

    ok, why = culture.set_leadership(
        gs, tid, new_captain, [new_captain], "accountability"
    )
    assert not ok and "captain" in why

    ok, _ = culture.set_leadership(
        gs, tid, new_captain, council, "accountability"
    )
    assert ok
    assert gs.teams[tid].captain_id == new_captain
    assert gs.players[new_captain].morale <= new_morale + 4.0
    assert gs.players[new_captain].morale >= new_morale + 2.0
    assert gs.players[old_captain].morale <= old_morale - 1.0
    assert old_chemistry - 2.1 <= gs.teams[tid].chemistry <= old_chemistry
    entry = next(e for e in reversed(gs.chronicle) if e.kind == "leadership")
    assert entry.team_id == tid
    assert entry.player_id == new_captain
    assert entry.data["principle"] == "accountability"


def test_snapshot_exposes_fracture_and_alignment(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    roster = sorted(gs.teams[tid].player_ids)
    _set_pair_graph(gs, tid, 20.0)
    for pid in roster:
        p = gs.players[pid]
        p.tenure_weeks = 0
        p.attributes["comms_quality"] = p.attributes["game_sense"] = 20.0
        p.personality_tags = ["volatile"]
    gs.teams[tid].captain_id = roster[0]
    gs.leadership_groups[tid] = roster[1:3]
    gs.culture_principles[tid] = "accountability"

    low = culture.culture_snapshot(gs, tid)
    assert {"fractured", "leadership_gap", "new_group"} <= set(low["flags"])
    assert low["cohesion"] == 20.0

    _set_pair_graph(gs, tid, 85.0)
    for pid in roster:
        p = gs.players[pid]
        p.tenure_weeks = 156
        p.attributes["comms_quality"] = p.attributes["game_sense"] = 90.0
        p.personality_tags = ["leader", "reliable", "veteran"]
    gs.culture_principles[tid] = "balanced"
    high = culture.culture_snapshot(gs, tid)
    assert {"mentorship_ready", "aligned"} <= set(high["flags"])
    assert high["overall"] > low["overall"] + 40.0


def test_weekly_tick_is_deterministic_and_arcs_are_small(campaign: GameState) -> None:
    gs = campaign
    tid = gs.user_team_id
    roster = sorted(gs.teams[tid].player_ids)
    _set_pair_graph(gs, tid, 82.0)
    for pid in roster:
        p = gs.players[pid]
        p.tenure_weeks = 104
        p.attributes["comms_quality"] = p.attributes["game_sense"] = 88.0
    culture.ensure_leadership(gs)
    a = gs.model_copy(deep=True)
    b = gs.model_copy(deep=True)
    morale_before = {pid: a.players[pid].morale for pid in roster}

    culture.weekly_tick(a)
    culture.weekly_tick(b)

    assert a.model_dump() == b.model_dump()
    assert all(
        abs(a.players[pid].morale - morale_before[pid]) <= 0.6 for pid in roster
    )
    assert any(
        relationships.get(a, x, y) > relationships.get(gs, x, y)
        for i, x in enumerate(roster)
        for y in roster[i + 1 :]
    )

    _set_pair_graph(gs, tid, 20.0)
    before = {
        relationships.key(x, y): relationships.get(gs, x, y)
        for i, x in enumerate(roster)
        for y in roster[i + 1 :]
    }
    culture.weekly_tick(gs)
    after = {key: gs.relationships[key] for key in before}
    assert min(after.values()) == min(before.values()) - 0.3


def test_culture_sessions_have_tradeoffs_and_four_week_cooldown(
    campaign: GameState,
) -> None:
    gs = campaign
    tid = gs.user_team_id
    roster = sorted(gs.teams[tid].player_ids)
    low_pair = roster[0], roster[1]
    high_pair = roster[2], roster[3]
    relationships._set(gs, *low_pair, 20.0)
    relationships._set(gs, *high_pair, 90.0)
    confidence_before = {pid: gs.players[pid].confidence for pid in roster}
    chemistry_before = gs.teams[tid].chemistry

    ok, _message, effects = culture.culture_session(gs, tid, "reset")
    assert ok
    assert effects["morale"] > 0.0
    assert gs.teams[tid].chemistry == chemistry_before - 1.0
    assert relationships.get(gs, *low_pair) > 20.0
    assert relationships.get(gs, *high_pair) < 90.0
    assert all(
        gs.players[pid].confidence == confidence_before[pid] - 1.0 for pid in roster
    )

    ok, why, _ = culture.culture_session(gs, tid, "player_led")
    assert not ok and "more week" in why

    gs.week += culture.SESSION_COOLDOWN_WEEKS
    newcomer = roster[-1]
    gs.players[newcomer].tenure_weeks = 0
    morale_before = gs.players[newcomer].morale
    ok, _message, effects = culture.culture_session(
        gs, tid, "welcome", player_id=newcomer
    )
    assert ok
    assert gs.players[newcomer].morale == min(100.0, morale_before + 3.0)
    assert effects["relationships"] > 0.0
    assert [e for e in gs.chronicle if e.kind == "culture"]
