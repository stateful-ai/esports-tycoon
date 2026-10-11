"""Scrim/bootcamp preparation: validation, costs, learning, and parity."""

from __future__ import annotations

import pytest

from esports_sim.manager import preparation
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState, TeamMapStats
from esports_sim.rng import RngTree
from esports_sim.schemas.player import MapMastery


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


def test_strategy_lab_improves_prep_learning_and_reduces_condition_cost(
    campaign: GameState,
) -> None:
    raw = campaign.model_dump(mode="json")
    baseline = GameState.model_validate(raw)
    upgraded = GameState.model_validate(raw)
    upgraded.facilities_by.setdefault(upgraded.user_team_id, {})["strategy_lab"] = 3

    reports = []
    for gs in (baseline, upgraded):
        fixture, _opponent, partner, map_id = _booking_parts(gs)
        gs.week = fixture.week
        for player in gs.roster(gs.user_team_id):
            player.stamina = 80.0
        preparation.schedule(
            gs, gs.user_team_id, fixture.id, partner, map_id, "retakes", "normal"
        )
        reports.append(next(
            report for report in preparation.weekly_tick(gs)
            if report.team_id == gs.user_team_id
        ))

    standard, lab = reports
    assert lab.knowledge_gain == round(standard.knowledge_gain * 1.3, 2)
    assert lab.stamina_cost == standard.stamina_cost - 1.5


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


@pytest.mark.parametrize("intensity,base_cost", [("light", 1.5), ("normal", 4.0), ("intense", 7.5)])
@pytest.mark.parametrize("lab_level", [0, 3])
def test_condition_preview_matches_resolved_whole_squad_cost(
    campaign: GameState, intensity: str, base_cost: float, lab_level: int
) -> None:
    gs = campaign
    tid = gs.user_team_id
    gs.facilities_by.setdefault(tid, {})["strategy_lab"] = lab_level
    roster = gs.roster(tid)
    for player in roster:
        player.stamina = 80.0
    roster[0].stamina = 0.5  # floor means this player pays less than the displayed maximum
    fixture, _, partner, map_id = _booking_parts(gs)
    gs.week = fixture.week
    expected_cost = max(0.0, base_cost - 0.5 * lab_level)
    prep = preparation.view(gs, tid)
    assert prep["condition_costs"][intensity] == expected_cost
    assert {p["id"] for p in prep["participants"]} == set(gs.teams[tid].player_ids)
    preparation.schedule(gs, tid, fixture.id, partner, map_id, "mental_reset", intensity)
    current = preparation.view(gs, tid)
    assert current["proposal"] is None
    assert current["current"]["partner_name"] == gs.teams[partner].name
    assert current["current"]["condition_cost"] == expected_cost
    before = {p.id: p.stamina for p in roster}
    preparation.weekly_tick(gs)
    for player in roster:
        assert player.stamina == round(max(0.0, before[player.id] - expected_cost), 1)


def test_proposal_preview_is_read_only_and_uses_acting_human_club(campaign: GameState) -> None:
    from esports_sim.web.server import _club_view

    gs = campaign
    other = next(t for t in sorted(gs.teams) if t != gs.user_team_id and gs.teams[t].player_ids)
    gs.human_team_ids.append(other)
    gs.set_acting(other)
    gs.facilities_by.setdefault(other, {})["strategy_lab"] = 3
    for player in gs.roster(other):
        player.stamina = 40.0
    # Initialize unrelated club-view defaults, then verify repeated reads are inert.
    _club_view(gs)
    before = gs.model_dump_json()
    prep = _club_view(gs)["preparation"]
    assert gs.model_dump_json() == before
    assert prep == _club_view(gs)["preparation"]
    assert prep["condition_costs"] == {"light": 0.0, "normal": 2.5, "intense": 6.0}
    assert {p["id"] for p in prep["participants"]} == set(gs.teams[other].player_ids)
    proposal = prep["proposal"]
    assert proposal["team_id"] == other
    assert proposal["objective"] == "mental_reset"
    assert proposal["intensity"] == "light"
    assert proposal["partner_name"] == gs.teams[proposal["partner_id"]].name
    assert proposal["condition_cost"] == 0.0
    assert "expected_edge" not in proposal
    assert gs.model_dump_json() == before


@pytest.mark.parametrize("objective", preparation.OBJECTIVES)
def test_rotation_advice_is_a_map_mastery_projection_without_scrim_results(
    campaign: GameState, objective: str
) -> None:
    gs = campaign
    tid = gs.user_team_id
    fixture, _, partner, map_id = _booking_parts(gs)
    gs.week = fixture.week
    gs.teams[tid].player_ids.extend(sorted(gs.free_agent_ids)[:2])
    roster = sorted(gs.teams[tid].player_ids)
    gs.teams[tid].lineup_ids = roster[:5]
    bench = roster[5:]
    assert bench
    candidate = bench[-1]
    for pid in bench:
        gs.players[pid].map_pool = [MapMastery(map_id=map_id, mastery=10.0)]
    gs.players[candidate].map_pool = [MapMastery(map_id=map_id, mastery=90.0)]
    before_stats = gs.model_dump(mode="json")["player_stats"]
    plan = preparation.schedule(gs, tid, fixture.id, partner, map_id, objective, "light")
    report = preparation._resolve(gs, plan, None)

    assert report.evidence.rotation_candidate_id == candidate
    assert report.dev_suggestion_player_id == candidate
    assert "Map mastery projects" in report.dev_suggestion
    assert gs.players[candidate].handle in report.dev_suggestion
    assert "no scrim performance was measured" in report.dev_suggestion
    assert "pushed the starters" not in report.dev_suggestion
    assert gs.model_dump(mode="json")["player_stats"] == before_stats
    if objective == "lineup_test":
        assert report.finding_code == "rotation_candidate"
        assert "Map mastery projects" in report.finding
        assert "no scrim performance was measured" in report.finding
    else:
        assert "bench option" not in report.finding


def test_lineup_review_without_bench_does_not_claim_a_measured_confirmation(
    campaign: GameState,
) -> None:
    gs = campaign
    tid = gs.user_team_id
    gs.teams[tid].player_ids = gs.teams[tid].player_ids[:5]
    gs.teams[tid].lineup_ids = list(gs.teams[tid].player_ids)
    fixture, _, partner, map_id = _booking_parts(gs)
    plan = preparation.schedule(gs, tid, fixture.id, partner, map_id, "lineup_test", "light")
    report = preparation._resolve(gs, plan, None)
    assert report.evidence.rotation_candidate_id == ""
    assert report.finding_code == "lineup_confirmed"  # preserve saved code compatibility
    assert "No eligible bench alternative was available" in report.finding
    assert "no scrim performance was measured" in report.finding
    assert "lineup review" in report.artifact_label


def test_loading_historical_preparation_preserves_its_original_advice() -> None:
    report = preparation.PrepReport(
        plan_id="old", team_id="team", fixture_id="fixture", opponent_id="opponent",
        partner_id="partner", map_id="lotus", objective="mental_reset", intensity="light",
        season=1, week=7, dev_suggestion_player_id="echo",
        dev_suggestion="Echo pushed the starters on lotus; a focused development block could make that rotation real.",
    )
    assert preparation.PrepReport.model_validate_json(report.model_dump_json()) == report
