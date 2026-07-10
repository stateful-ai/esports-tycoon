"""Phase 2 of Legacy Mode: personality axes (the continuous layer under
the tags) and persistent memories (chronicle selectors with small,
bounded campaign effects)."""

from __future__ import annotations

import pytest

from esports_sim.manager import (
    career,
    chronicle,
    market,
    memories,
    personality,
    relationships,
)
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import load_all


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=555)


# -- personality axes ---------------------------------------------------------


def test_axes_deterministic_and_bounded(campaign):
    p = campaign.roster(campaign.user_team_id)[0]
    a1, a2 = personality.axes(p), personality.axes(p)
    assert a1 == a2
    assert set(a1) == set(personality.AXES)
    assert all(5.0 <= v <= 95.0 for v in a1.values())


def test_tags_shade_axes(campaign):
    p = campaign.roster(campaign.user_team_id)[0]
    p.personality_tags = []
    base = personality.axes(p)
    p.personality_tags = ["hot_head"]
    hot = personality.axes(p)
    assert hot["resilience"] < base["resilience"]
    assert hot["ego"] > base["ego"]


def test_affinity_reads_axes(campaign):
    r = campaign.roster(campaign.user_team_id)
    a, b = r[0], r[1]
    a.personality_tags, b.personality_tags = ["team_player"], ["team_player"]
    social = relationships.affinity_target(a, b)
    a.personality_tags, b.personality_tags = ["quiet"], ["quiet"]
    withdrawn = relationships.affinity_target(a, b)
    assert social > withdrawn


# -- memories -----------------------------------------------------------------


def _plant(gs, kind, pid="", tid="", data=None):
    return chronicle.record(
        gs, kind, f"{kind} test entry {pid}|{tid}",
        team_id=tid, player_id=pid, data=data or {},
    )


def test_loyalty_bias_signs_and_cap(campaign):
    gs = campaign
    tid = gs.user_team_id
    p = gs.roster(tid)[0]
    assert memories.loyalty_bias(gs, p.id, tid) == 0.0  # blank slate
    _plant(gs, "debut", pid=p.id, tid=tid)
    assert memories.loyalty_bias(gs, p.id, tid) > 0.0
    _plant(gs, "release", pid=p.id, tid=tid)
    biased = memories.loyalty_bias(gs, p.id, tid)
    assert biased < memories.loyalty_bias(gs, p.id, "someone_else")
    for i in range(8):  # pile on: the cap must hold
        chronicle.record(
            gs, "milestone", f"milestone {i}", team_id=tid, player_id=p.id
        )
    assert abs(memories.loyalty_bias(gs, p.id, tid)) <= memories.BIAS_CAP


def test_renewal_reads_loyalty(game_data):
    a = new_campaign(game_data, seed=91)
    b = new_campaign(game_data, seed=91)
    tid = a.user_team_id
    pid = a.teams[tid].player_ids[0]
    # Same world twice; plant a made-here history in one.
    _plant(a, "debut", pid=pid, tid=tid)
    for i in range(3):
        chronicle.record(a, "milestone", f"m{i}", team_id=tid, player_id=pid)
    ok_a, _ = market.renew_contract(a, tid, pid)
    ok_b, _ = market.renew_contract(b, tid, pid)
    assert ok_a and ok_b
    # The loyal player re-signs a shade under the blank-slate ask.
    assert a.players[pid].salary < b.players[pid].salary


def test_memory_lines_capped_and_ranked(campaign):
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    for i in range(15):
        chronicle.record(
            gs, "milestone", f"milestone {i}",
            team_id=gs.user_team_id, player_id=p.id,
        )
    _plant(gs, "award", pid=p.id, tid=gs.user_team_id)
    lines = memories.memory_lines(gs, p.id)
    assert len(lines) == memories.MEMORY_CAP
    assert "award" in lines[0]  # highest importance leads


def test_board_posture_on_return(game_data):
    offers = career.new_game_offers(new_campaign(game_data, seed=77), 0)
    gs = new_campaign(
        game_data, seed=77, user_team_id=offers[0].team_id,
        mode="legacy", career_offer=offers[0],
    )
    seat = gs.manager_for(gs.user_team_id)
    old_tid = seat.team_id
    chronicle.record(
        gs, "champions_title", "won it all",
        team_id=old_tid, manager_id=seat.id,
    )
    chronicle.record(
        gs, "masters_title", "won that too",
        team_id=old_tid, manager_id=seat.id,
    )
    # Fire them, then have the OLD org (title memories) vs a stranger org
    # court them: the reunion board starts warmer.
    seat.contract.goal = "win_champions"
    seat.contract.patience = 1.0
    career.apply_dismissals(gs, career.review_boards(gs))
    stranger = gs.career_offers_by[seat.id][0]
    reunion = stranger.model_copy(update={"team_id": old_tid})
    gs.career_offers_by[seat.id].append(reunion)
    ok, _ = career.accept_offer(gs, seat.id, old_tid)
    assert ok
    warm = seat.contract.patience
    assert warm > stranger.patience  # posture bonus applied


def test_profile_serves_memories(game_data):
    pytest.importorskip("fastapi")
    import esports_sim.web.server as server_mod

    gs = new_campaign(game_data, seed=13)
    p = gs.roster(gs.user_team_id)[0]
    chronicle.record(
        gs, "debut", f"{p.handle} makes their professional debut.",
        team_id=gs.user_team_id, player_id=p.id,
    )
    game = server_mod._Game(game_data, "TESTM", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, gs.user_team_id))
    prof = server_mod.player_profile(p.id)
    assert prof["memories"] and "debut" in prof["memories"][0]
