"""Preparation report names resolve at read time without changing saved reports."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.preparation import PrepReport
from esports_sim.web.server import _club_view, _last_prep_artifact


def report(gs, tid, pid):
    return PrepReport(
        plan_id="label-test", team_id=tid, fixture_id="fixture", opponent_id="opponent",
        partner_id="partner", map_id="lotus", objective="retakes", intensity="normal",
        season=gs.season, week=gs.week, artifact_label="Lotus retake book",
        dev_suggestion_player_id=pid, dev_suggestion="Hollowlock pushed the starters.",
    )


@pytest.mark.parametrize("availability", ["known", "unknown", "removed", "empty"])
def test_prep_player_label_keeps_profile_id_and_saved_state(game_data, availability):
    gs = new_campaign(game_data, seed=2038)
    tid = gs.acting_team_id
    pid = "fa_0"
    assert pid in gs.players
    gs.players[pid].handle = "Hollowlock"
    if availability == "unknown":
        pid = "unknown_player"
    elif availability == "removed":
        del gs.players[pid]
        gs.free_agent_ids.remove(pid)
    elif availability == "empty":
        pid = ""
    gs.preparation_reports_by[tid] = report(gs, tid, pid)
    # Club view initializes unrelated defaults on first read.
    _club_view(gs)
    before = gs.model_dump_json()
    for _ in range(2):
        full = _club_view(gs)["preparation"]["last"]
        artifact = _last_prep_artifact(gs, tid)
        for view in (full, artifact):
            assert view["dev_suggestion_player_id"] == pid
            assert view["dev_suggestion_handle"] == ("Hollowlock" if availability == "known" else "")
        assert gs.model_dump_json() == before


def test_prep_label_follows_acting_team_and_exact_report_player(game_data):
    gs = new_campaign(game_data, seed=2038)
    original = gs.user_team_id
    other = next(t for t in sorted(gs.teams) if t != original and gs.teams[t].player_ids)
    own_pid = gs.teams[original].player_ids[0]
    other_pid = gs.teams[other].player_ids[0]
    gs.players[own_pid].handle = "Own player"
    gs.players[other_pid].handle = "Other player"
    gs.preparation_reports_by[original] = report(gs, original, own_pid)
    gs.preparation_reports_by[other] = report(gs, other, other_pid)
    gs.human_team_ids.append(other)
    gs.set_acting(other)
    _club_view(gs)
    before = gs.model_dump_json()
    view = _club_view(gs)["preparation"]["last"]
    assert view["team_id"] == other
    assert view["dev_suggestion_player_id"] == other_pid
    assert view["dev_suggestion_handle"] == "Other player"
    assert _last_prep_artifact(gs, original)["dev_suggestion_handle"] == "Own player"
    assert gs.model_dump_json() == before
