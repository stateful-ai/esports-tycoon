"""Latest prep reports use public handles while retaining stable profile IDs."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.preparation import PrepReport
from esports_sim.web import server

pytestmark = pytest.mark.web


@pytest.mark.parametrize("identity", ["current", "renamed", "transferred", "removed", "empty"])
def test_latest_prep_serializers_resolve_public_identity_without_changing_report(game_data, identity):
    gs = new_campaign(game_data, seed=2040)
    tid = gs.user_team_id
    player = gs.roster(tid)[0]
    pid = player.id
    expected_handle = player.handle
    if identity == "renamed":
        player.handle = expected_handle = 'Wraith & "Hawk"'
    elif identity == "transferred":
        gs.teams[tid].player_ids.remove(pid)
        other = next(t for t in sorted(gs.teams) if t != tid)
        gs.teams[other].player_ids.append(pid)
    elif identity == "removed":
        pid = "team_phantom_core_p3_removed"
        expected_handle = None
    elif identity == "empty":
        pid = ""
        expected_handle = None
    fixture = gs.team_fixture(tid)
    assert fixture is not None
    report = PrepReport(
        plan_id="identity-report", team_id=tid, fixture_id=fixture.id,
        opponent_id=fixture.team_b if fixture.team_a == tid else fixture.team_a,
        partner_id=next(t for t in sorted(gs.teams) if t != tid),
        map_id=fixture.maps[0], objective="anti_exec", intensity="light",
        season=gs.season, week=gs.week, artifact_label="Anti-exec book",
        dev_suggestion_player_id=pid, dev_suggestion="Archived development observation.",
        dev_suggestion_basis="age",
    )
    gs.preparation_reports_by[tid] = report
    saved_report = report.model_dump_json()
    # The club view initializes unrelated defaults on its first read.
    server._club_view(gs)
    before = gs.model_dump_json()
    club = server._club_view(gs)["preparation"]["last"]
    artifact = server._last_prep_artifact(gs, tid)
    for view in (club, artifact):
        assert view["dev_suggestion_player_id"] == pid
        assert view["dev_suggestion_handle"] == expected_handle
        assert view["dev_suggestion"] == report.dev_suggestion
    assert report.model_dump_json() == saved_report
    assert gs.model_dump_json() == before


def test_legacy_hidden_target_projects_public_identity_before_resolving_handle(game_data):
    gs = new_campaign(game_data, seed=2040)
    tid = gs.user_team_id
    pids = sorted(gs.teams[tid].player_ids)
    public_pid, private_pid = pids[0], pids[-1]
    for pid in pids:
        gs.players[pid].age = 25
    gs.players[public_pid].age = 19
    gs.players[public_pid].handle = "Public youth"
    gs.players[private_pid].handle = "Hidden selected target"
    report = PrepReport(
        plan_id="legacy-identity-report", team_id=tid, fixture_id="fixture",
        opponent_id=tid, partner_id=tid, map_id="bind", objective="anti_exec",
        intensity="light", season=gs.season, week=gs.week,
        participant_ids=pids, artifact_label="Bind prep book",
        dev_suggestion_player_id=private_pid,
        dev_suggestion="Hidden selected target has ~21 points of untapped ceiling.",
    )
    gs.preparation_reports_by[tid] = report
    saved_report = report.model_dump_json()
    server._club_view(gs)
    before = gs.model_dump_json()
    club = server._club_view(gs)["preparation"]["last"]
    artifact = server._last_prep_artifact(gs, tid)
    for view in (club, artifact):
        assert view["dev_suggestion_player_id"] == public_pid
        assert view["dev_suggestion_handle"] == "Public youth"
        assert "Hidden selected target" not in view["dev_suggestion"]
        assert "~21" not in view["dev_suggestion"]
        assert "age-based" in view["dev_suggestion"]
    assert gs.model_dump_json() == before
    for pid in pids:
        gs.players[pid].potential = 1 if pid == public_pid else 99
    counterfactual_before = gs.model_dump_json()
    assert server._club_view(gs)["preparation"]["last"] == club
    assert server._last_prep_artifact(gs, tid) == artifact
    assert report.model_dump_json() == saved_report
    assert gs.model_dump_json() == counterfactual_before


def test_prep_identity_handles_no_report_and_does_not_mutate_projection(game_data):
    gs = new_campaign(game_data, seed=2040)
    assert server._prep_report_identity(gs, None) is None
    player = gs.roster(gs.user_team_id)[0]
    projection = {"dev_suggestion_player_id": player.id}
    assert server._prep_report_identity(gs, projection)["dev_suggestion_handle"] == player.handle
    assert "dev_suggestion_handle" not in projection
    gs.players.pop(player.id)
    assert server._prep_report_identity(gs, projection)["dev_suggestion_handle"] is None


def test_prep_dev_label_preserves_profile_routing_and_escapes_public_handle():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for frontend verification")
    source = (Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    parts = [
        re.search(r"const esc = .*?;\n", source, re.S).group(),
        re.search(r"const plink = .*?;\n", source, re.S).group(),
        re.search(r"function preparationDevPlayerLabel\(report\) \{.*?\n\}", source, re.S).group(),
    ]
    script = "\n".join(parts) + """
console.log(JSON.stringify([
  preparationDevPlayerLabel({dev_suggestion_player_id: 'team_phantom_core_p3', dev_suggestion_handle: 'Wraithhawk'}),
  preparationDevPlayerLabel({dev_suggestion_player_id: 'p"<&', dev_suggestion_handle: 'Wraith & "Hawk" <x>'}),
  preparationDevPlayerLabel({dev_suggestion_player_id: 'removed_internal_id', dev_suggestion_handle: null}),
  preparationDevPlayerLabel({dev_suggestion_player_id: '', dev_suggestion_handle: null})
]));
"""
    labels = json.loads(subprocess.check_output([node, "-e", script], text=True))
    assert labels[0] == '<button type="button" class="plink " data-pid="team_phantom_core_p3">Wraithhawk</button> — '
    assert labels[1] == '<button type="button" class="plink " data-pid="p&quot;&lt;&amp;">Wraith &amp; &quot;Hawk&quot; &lt;x&gt;</button> — '
    assert labels[2:] == ["Former player — ", ""]
    assert "${preparationDevPlayerLabel(pr.last)}${esc(pr.last.dev_suggestion)}" in source
