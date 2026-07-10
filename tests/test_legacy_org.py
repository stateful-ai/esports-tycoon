"""Phase 4 of Legacy Mode: coaching tree, philosophy, organizational
knowledge, and the expanded backroom department."""

from __future__ import annotations

import pytest

from esports_sim.manager import career, chronicle, knowledge, staff
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState
from esports_sim.registry import load_all


@pytest.fixture(scope="module")
def game_data():
    return load_all()


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=444)


# -- org knowledge ------------------------------------------------------------


def test_knowledge_accrues_from_play(game_data):
    gs = new_campaign(game_data, seed=21)
    for _ in range(3):
        advance_week(gs, game_data)
    tid = gs.user_team_id
    book = gs.org_knowledge.get(tid, {})
    assert any(k.startswith("playbook:") for k in book)
    assert any(k.startswith("antistrat:") for k in book)
    assert book.get("methodology", 0.0) >= 0.0


def test_knowledge_decays_offseason_and_patch(campaign):
    gs = campaign
    tid = gs.user_team_id
    gs.org_knowledge[tid] = {
        "playbook:haven": 80.0,
        "antistrat:team_x": 60.0,
        "methodology": 50.0,
    }
    knowledge.on_patch(gs)
    assert gs.org_knowledge[tid]["playbook:haven"] == 68.0  # x0.85
    assert gs.org_knowledge[tid]["antistrat:team_x"] == 60.0  # untouched
    knowledge.offseason_decay(gs)
    b = gs.org_knowledge[tid]
    assert b["playbook:haven"] == pytest.approx(68.0 * 0.65, abs=0.1)
    assert b["antistrat:team_x"] == pytest.approx(24.0, abs=0.1)
    assert b["methodology"] == pytest.approx(45.0, abs=0.1)


def test_staff_move_leaks_knowledge(campaign):
    gs = campaign
    a = gs.user_team_id
    b = next(t for t in sorted(gs.teams) if t != a and gs.teams[t].tier == 1)
    gs.org_knowledge[b] = {"methodology": 50.0}
    knowledge.on_staff_move(gs, b, a)
    assert knowledge.get(gs, a, f"antistrat:{b}") == knowledge.LEAK_ANTISTRAT
    assert knowledge.get(gs, a, "methodology") > 0.0


def test_prep_bonus_bounded(campaign):
    gs = campaign
    tid, opp = gs.user_team_id, sorted(gs.teams)[1]
    assert knowledge.prep_bonus(gs, tid, opp, ["haven"]) == 0.0
    gs.org_knowledge[tid] = {
        "playbook:haven": 100.0,
        f"antistrat:{opp}": 100.0,
    }
    bonus = knowledge.prep_bonus(gs, tid, opp, ["haven"])
    assert 0.0 < bonus <= 1.0  # small next to scouting's span


# -- coaching tree ------------------------------------------------------------


def test_igl_retires_into_coaching(campaign):
    gs = campaign
    p = gs.roster(gs.user_team_id)[0]
    p.age = 31
    p.attributes["game_sense"] = 70.0
    member = staff.retire_into_staff(gs, p, ca=62.0, team_name="Team Nexus")
    assert member is not None
    assert member.role == "coach"
    assert member.former_player_id == p.id
    assert any(m.id == member.id for m in gs.staff_pool)
    # A young journeyman does not get a chair.
    q = gs.roster(gs.user_team_id)[1]
    q.age = 24
    assert staff.retire_into_staff(gs, q, ca=50.0, team_name="X") is None


# -- philosophy ---------------------------------------------------------------


def test_philosophy_is_earned(campaign):
    gs = campaign
    seat = gs.manager_for(gs.user_team_id)
    assert career.philosophies(gs, seat.id) == []
    for i in range(4):
        chronicle.record(
            gs, "debut", f"debut {i}", team_id=seat.team_id,
            player_id=f"p{i}", manager_id=seat.id,
        )
    assert "trust_rookies" in career.philosophies(gs, seat.id)
    assert career.philosophy_training_mult(gs, seat.team_id) == 1.0
    for i in range(7):
        chronicle.record(
            gs, "milestone", f"milestone {i}", team_id=seat.team_id,
            player_id=f"p{i}", manager_id=seat.id,
        )
    assert "development_school" in career.philosophies(gs, seat.id)
    assert career.philosophy_training_mult(gs, seat.team_id) == 1.05
    summary = career.career_summary(gs, seat.id)
    assert summary["philosophies"]


# -- expanded department --------------------------------------------------------


def test_new_roles_seed_and_support(game_data):
    gs = new_campaign(game_data, seed=33)
    roles = {m.role for m in gs.staff_pool}
    assert {"psychologist", "performance_coach"} <= roles
    # Support pulls toward 50, never past it.
    psych = next(m for m in gs.staff_pool if m.role == "psychologist")
    gs.set_acting(gs.user_team_id)
    gs.teams[gs.user_team_id].balance = 10_000_000
    ok, _ = staff.hire(gs, psych.id)
    assert ok
    assert staff.confidence_support(gs) > 0.0
    p = gs.roster(gs.user_team_id)[0]
    p.confidence = 49.9
    support = staff.confidence_support(gs)
    assert min(50.0, p.confidence + support) == 50.0


def test_department_briefing_lands_in_inbox(game_data):
    gs = new_campaign(game_data, seed=52)
    gs.set_acting(gs.user_team_id)
    # An elite analyst puts the org at tier >= 2.
    analyst = next(m for m in gs.staff_pool if m.role == "analyst")
    analyst.quality = 90.0
    gs.teams[gs.user_team_id].balance = 10_000_000
    ok, _ = staff.hire(gs, analyst.id)
    assert ok
    for _ in range(4):
        advance_week(gs, game_data)
    gs.set_acting(gs.user_team_id)
    titles = [it.title for it in gs.inbox]
    assert any(t.startswith("Analytics briefing") for t in titles), titles
