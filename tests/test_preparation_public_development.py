"""Development leads must not reveal hidden PA, including legacy reports."""

import pytest

from esports_sim.manager import preparation, inbox
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import manager_observation


def _report(gs):
    tid = gs.user_team_id
    pids = sorted(gs.teams[tid].player_ids)
    for pid in pids:
        gs.players[pid].age = 22
    gs.players[pids[0]].age = 19
    return preparation.PrepReport(
        plan_id="public-development-test", team_id=tid, fixture_id="fixture",
        opponent_id=tid, partner_id=tid, map_id="bind", objective="anti_exec",
        intensity="light", season=gs.season, week=gs.week,
        participant_ids=pids, artifact_label="Bind prep book",
    )


def test_new_lead_counterfactual_hidden_potential_does_not_choose_target(game_data):
    gs = new_campaign(game_data, seed=707)
    report = _report(gs)
    plan = preparation.PrepPlan(
        id=report.plan_id, team_id=report.team_id, fixture_id=report.fixture_id,
        opponent_id=report.opponent_id, partner_id=report.partner_id,
        map_id=report.map_id, objective=report.objective,
        intensity=report.intensity, created_season=gs.season, created_week=gs.week,
    )
    before = preparation._dev_suggestion(gs, plan, report.evidence)
    for index, pid in enumerate(report.participant_ids):
        gs.players[pid].potential = 99 if index else 1
    after = preparation._dev_suggestion(gs, plan, report.evidence)
    assert before == after
    assert before[0] == report.participant_ids[0]
    assert "age-based" in before[1]
    assert "did not measure" in before[1]
    assert "untapped ceiling" not in before[1]


def test_legacy_projection_replaces_hidden_ranked_id_without_mutating_save(game_data):
    gs = new_campaign(game_data, seed=707)
    report = _report(gs)
    report.dev_suggestion_player_id = report.participant_ids[-1]
    report.dev_suggestion = "Old target has ~21 points of untapped ceiling."
    gs.preparation_reports_by[report.team_id] = report
    saved = report.model_dump(mode="json")
    public = preparation.view(gs, report.team_id)["last"]
    assert public["dev_suggestion_player_id"] == report.participant_ids[0]
    assert "~21" not in public["dev_suggestion"]
    assert report.model_dump(mode="json") == saved
    expected_policy = {k: v for k, v in public.items() if k != "dev_suggestion_basis"}
    assert manager_observation(gs, game_data, report.team_id)["club"]["preparation"]["last"] == expected_policy
    for pid in report.participant_ids:
        gs.players[pid].potential = 99
    assert preparation.view(gs, report.team_id)["last"] == public


def test_legacy_inbox_projection_withholds_private_target_and_preserves_history(game_data):
    gs = new_campaign(game_data, seed=707)
    item = inbox._make(
        gs.season, gs.week, "development", "prep_report|old",
        "Prep report: Bind prep book",
        "Scrim block resolved.\nNote on Old target: Old target has ~21 points of untapped ceiling.",
        "tactics",
    )
    original = item.body
    public = inbox.to_api(item, gs)
    assert "Old target" not in public["body"]
    assert "~21" not in public["body"]
    assert "Scrim block resolved." in public["body"]
    assert item.body == original


def test_aged_legacy_report_labels_current_reconstruction_not_historical_read(game_data):
    gs = new_campaign(game_data, seed=707)
    report = _report(gs)
    report.dev_suggestion_player_id = report.participant_ids[-1]
    report.dev_suggestion = "Old target has ~21 points of untapped ceiling."
    saved = report.model_dump(mode="json")
    gs.season = report.season + 1
    gs.week = 2
    for pid in report.participant_ids:
        gs.players[pid].age = 25
    current_youth = report.participant_ids[1]
    gs.players[current_youth].age = 23

    public = preparation.public_report(gs, report)
    assert public["season"] == saved["season"]
    assert public["week"] == saved["week"]
    assert public["dev_suggestion_player_id"] == current_youth
    assert "Reconstructed legacy lead using current public ages" in public["dev_suggestion"]
    assert "not the session's original recommendation" in public["dev_suggestion"]
    assert "At current age 23" in public["dev_suggestion"]
    assert report.model_dump(mode="json") == saved

    gs.players[current_youth].age = 24
    public = preparation.public_report(gs, report)
    assert public["dev_suggestion_player_id"] == ""
    assert public["dev_suggestion"] == ""
    assert report.model_dump(mode="json") == saved


def test_public_reports_keep_recorded_lead_and_map_mastery_legacy(game_data):
    gs = new_campaign(game_data, seed=707)
    report = _report(gs)
    report.dev_suggestion_basis = "age"
    report.dev_suggestion_player_id = report.participant_ids[0]
    report.dev_suggestion = "At age 19, this participant is a youth development option."
    gs.players[report.participant_ids[0]].age = 30
    assert preparation.public_dev_suggestion(gs, report) == (
        report.dev_suggestion_player_id, report.dev_suggestion,
    )
    report.dev_suggestion_basis = ""
    report.dev_suggestion = "Map mastery projects Young player as a bench option for bind."
    assert preparation.public_dev_suggestion(gs, report) == (
        report.dev_suggestion_player_id, report.dev_suggestion,
    )


@pytest.mark.parametrize("basis", ["", "age", "map_mastery"])
def test_version_8_prep_observation_omits_save_provenance_without_mutation(game_data, basis):
    gs = new_campaign(game_data, seed=707)
    report = _report(gs)
    report.dev_suggestion_basis = basis
    report.dev_suggestion_player_id = report.participant_ids[-1]
    report.dev_suggestion = (
        "Old target has ~21 points of untapped ceiling." if not basis
        else "Recorded public development lead."
    )
    gs.preparation_reports_by[report.team_id] = report
    saved = gs.model_dump_json()
    public = preparation.view(gs, report.team_id)["last"]
    obs = manager_observation(gs, game_data, report.team_id)
    last = obs["club"]["preparation"]["last"]

    assert obs["observation_version"] == 8
    # Explicit pre-provenance report contract: adding another field must not
    # silently widen the versioned observation again.
    assert set(last) == {
        "plan_id", "team_id", "fixture_id", "opponent_id", "partner_id",
        "map_id", "objective", "intensity", "season", "week", "status",
        "finding_code", "finding", "evidence", "participant_ids",
        "knowledge_key", "knowledge_gain", "stamina_cost", "morale_delta",
        "chemistry_delta", "artifact_label", "prep_edge_contribution",
        "dev_suggestion_player_id", "dev_suggestion",
    }
    assert last == {k: v for k, v in public.items() if k != "dev_suggestion_basis"}
    assert public["dev_suggestion_basis"] == basis
    assert report.model_dump(mode="json")["dev_suggestion_basis"] == basis
    if not basis:
        assert last["dev_suggestion_player_id"] == report.participant_ids[0]
        assert "~21" not in last["dev_suggestion"]
        assert "untapped ceiling" not in last["dev_suggestion"]
        assert "age-based" in last["dev_suggestion"]
    else:
        assert last["dev_suggestion_player_id"] == report.dev_suggestion_player_id
        assert last["dev_suggestion"] == report.dev_suggestion
    assert preparation.view(gs, report.team_id)["last"] == public
    assert gs.model_dump_json() == saved
