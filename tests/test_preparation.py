"""Scrim/bootcamp preparation: validation, costs, learning, and parity."""

from __future__ import annotations

import pytest

from esports_sim.manager import preparation
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState, TeamMapStats
from esports_sim.rng import RngTree


@pytest.fixture()
def campaign(game_data) -> GameState:
    return new_campaign(game_data, seed=707)


def _booking_parts(gs: GameState, team_id: str | None = None):
    team_id = team_id or gs.user_team_id
    fixture = next(
        f
        for f in sorted(gs.fixtures, key=lambda f: (f.week, f.id))
        if not f.played and team_id in (f.team_a, f.team_b) and f.maps
    )
    opponent = fixture.team_b if fixture.team_a == team_id else fixture.team_a
    partner = next(
        tid
        for tid in sorted(gs.teams)
        if tid not in (team_id, opponent) and gs.teams[tid].player_ids
    )
    return fixture, opponent, partner, fixture.maps[0]


def test_schedule_validates_fixture_partner_map_and_choices(campaign: GameState) -> None:
    gs = campaign
    fixture, opponent, partner, map_id = _booking_parts(gs)
    plan = preparation.schedule(
        gs, gs.user_team_id, fixture.id, partner, map_id, "retakes", "normal"
    )
    assert gs.preparation_plans_by[gs.user_team_id] == plan
    assert plan.opponent_id == opponent
    assert preparation.view(gs, gs.user_team_id)["current"]["id"] == plan.id

    with pytest.raises(ValueError, match="third team"):
        preparation.schedule(
            gs, gs.user_team_id, fixture.id, opponent, map_id, "retakes", "light"
        )
    with pytest.raises(ValueError, match="map pool"):
        preparation.schedule(
            gs, gs.user_team_id, fixture.id, partner, "not-a-map", "retakes", "light"
        )
    with pytest.raises(ValueError, match="objective"):
        preparation.schedule(
            gs, gs.user_team_id, fixture.id, partner, map_id, "wallbangs", "light"
        )
    with pytest.raises(ValueError, match="intensity"):
        preparation.schedule(
            gs, gs.user_team_id, fixture.id, partner, map_id, "retakes", "reckless"
        )


def test_mental_reset_trades_condition_for_morale(campaign: GameState) -> None:
    gs = campaign
    fixture, _opponent, partner, map_id = _booking_parts(gs)
    gs.week = fixture.week
    roster = gs.roster(gs.user_team_id)
    for player in roster:
        player.stamina = 80.0
        player.morale = 50.0
    before_chemistry = gs.teams[gs.user_team_id].chemistry
    preparation.schedule(
        gs,
        gs.user_team_id,
        fixture.id,
        partner,
        map_id,
        "mental_reset",
        "normal",
    )

    reports = preparation.weekly_tick(
        gs, RngTree(gs.seed).derive("preparation", gs.season, gs.week)
    )
    report = next(r for r in reports if r.team_id == gs.user_team_id)

    assert report.status == "completed"
    assert report.stamina_cost == 4.0
    assert report.morale_delta == 3.5
    assert all(player.stamina == 76.0 for player in roster)
    assert all(player.morale == 53.5 for player in roster)
    assert gs.teams[gs.user_team_id].chemistry > before_chemistry
    assert preparation.view(gs, gs.user_team_id)["current"] is None
    assert preparation.view(gs, gs.user_team_id)["last"]["plan_id"] == report.plan_id


def test_anti_exec_uses_public_map_sample_and_grows_bounded_knowledge(
    campaign: GameState,
) -> None:
    gs = campaign
    fixture, opponent, partner, map_id = _booking_parts(gs)
    gs.week = fixture.week
    gs.team_map_stats.setdefault(opponent, {})[map_id] = TeamMapStats(
        maps=4,
        wins=3,
        atk_rounds=40,
        atk_won=24,
        def_rounds=36,
        def_won=18,
    )
    gs.team_map_stats.setdefault(partner, {})[map_id] = TeamMapStats(maps=5, wins=3)
    gs.scout_progress_by.setdefault(gs.user_team_id, {})[opponent] = 0.8
    key = f"antistrat:{opponent}"
    gs.org_knowledge.setdefault(gs.user_team_id, {})[key] = 99.5
    preparation.schedule(
        gs, gs.user_team_id, fixture.id, partner, map_id, "anti_exec", "intense"
    )

    reports = preparation.weekly_tick(gs)
    report = next(r for r in reports if r.team_id == gs.user_team_id)

    assert report.finding_code == "opponent_attack_pressure"
    assert report.evidence.opponent_attack_win_pct == 60.0
    assert report.evidence.scouting_confidence == 0.8
    assert report.knowledge_key == key
    assert report.knowledge_gain == 0.5
    assert gs.org_knowledge[gs.user_team_id][key] == 100.0


def test_determinism_and_ai_playoff_parity(campaign: GameState) -> None:
    raw = campaign.model_dump(mode="json")
    a = GameState.model_validate(raw)
    b = GameState.model_validate(raw)
    for gs in (a, b):
        gs.phase = "playoffs"
        fixture = next(
            f
            for f in sorted(gs.fixtures_for_week(), key=lambda f: f.id)
            if f.maps and not f.played
        )
        # Make this current fixture AI-v-AI while retaining another human org.
        gs.human_team_ids = [gs.user_team_id]
        if gs.user_team_id in (fixture.team_a, fixture.team_b):
            gs.human_team_ids = []

    reports_a = preparation.weekly_tick(
        a, RngTree(a.seed).derive("preparation", a.season, a.week)
    )
    reports_b = preparation.weekly_tick(
        b, RngTree(b.seed).derive("preparation", b.season, b.week)
    )

    assert reports_a
    assert all(r.intensity == "light" for r in reports_a)
    assert [r.model_dump(mode="json") for r in reports_a] == [
        r.model_dump(mode="json") for r in reports_b
    ]
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
