"""Settlement receipts must observe exact engine results, including culture."""
import pytest

from esports_sim.manager import culture, flavor_events, new_campaign, telemetry
from esports_sim.manager.state import FlavorChoice, FlavorEvent, FlavorOutcome
from esports_sim.web import flavor_feedback
import esports_sim.web.server as server


@pytest.mark.parametrize("committed", [False, True])
def test_web_receipt_preserves_entire_resolution_state(game_data, monkeypatch, committed):
    gs = new_campaign(game_data, seed=123)
    tid = gs.user_team_id
    pid = gs.teams[tid].player_ids[0]
    gs.teams[tid].balance = 2
    gs.teams[tid].reputation = 100.0
    gs.players[pid].confidence = 99.9
    gs.players[pid].morale = 0.0
    for i, roster_id in enumerate(gs.teams[tid].player_ids):
        gs.players[roster_id].stamina = 100.0 if i == 0 else 99.5
    if committed:
        culture.commit_principle(gs, tid, "development")
    event = FlavorEvent(id="receipt", season=gs.season, week=gs.week, team_id=tid,
        player_id=pid, type_id="community_clinic", title="A clinic", prompt="Choose",
        choices=[FlavorChoice(id="decline", label="Decline", outcomes=[FlavorOutcome(text="Settled", effects={
            "team_balance": -10, "team_reputation": 5, "team_sentiment": 1,
            "player_confidence": 5, "player_morale": -2, "team_stamina": 2,
            "player_followers": 10})])])
    gs.flavor_events_by[tid] = event
    baseline = gs.model_copy(deep=True)
    _, _, nominal = flavor_events.resolve(baseline, tid, "decline")
    telemetry.record_action(baseline, "flavor_choice", {"event_id": "receipt", "choice_id": "decline"})
    game = server._Game(game_data, "AUDIT", gs=gs)
    token = server._ctx.set(server._ReqCtx(game, tid))
    monkeypatch.setattr(game, "save", lambda: None)
    try:
        result = server.resolve_flavor_event(server.FlavorEventChoiceBody(event_id="receipt", choice_id="decline"))
    finally:
        server._ctx.reset(token)
    assert gs.model_dump_json() == baseline.model_dump_json()
    assert result["message"] == "Settled"
    rows = {(row["metric"], row["subject_id"]): row for row in result["realized_effects"]}
    assert rows[("team_balance", tid)]["delta"] == -2
    assert rows[("team_reputation", tid)]["delta"] == 0
    assert rows[("player_confidence", pid)]["delta"] == 0.1
    assert rows[("player_morale", pid)]["delta"] == 0
    assert "no net change" in rows[("player_morale", pid)]["text"]
    assert rows[("player_stamina", pid)]["delta"] == 0
    assert len([row for row in rows.values() if row["metric"] == "player_stamina"]) == len(gs.teams[tid].player_ids)
    assert all(row["after"] - row["before"] == pytest.approx(row["delta"]) for row in rows.values())
    assert "effects" not in flavor_events.to_api(event)["choices"][0]


def test_receipt_reports_actual_culture_consequences(game_data):
    gs = new_campaign(game_data, seed=123)
    tid = gs.user_team_id
    pid = gs.teams[tid].player_ids[0]
    culture.commit_principle(gs, tid, "development")
    event = FlavorEvent(id="culture-receipt", season=gs.season, week=gs.week, team_id=tid,
        player_id=pid, type_id="community_clinic", title="Clinic", prompt="Choose", choices=[
            FlavorChoice(id="decline", label="Decline", outcomes=[FlavorOutcome(text="Settled", effects={})])])
    gs.flavor_events_by[tid] = event
    before = flavor_feedback.snapshot(gs, event)
    ok, _, nominal = flavor_events.resolve(gs, tid, "decline")
    assert ok
    rows = flavor_feedback.settlement(gs, event, nominal, before)
    metrics = {row["metric"] for row in rows}
    assert {"culture_conviction", "team_chemistry", "player_morale", "player_trust", "relationship"} <= metrics
    assert all(row["delta"] < 0 for row in rows)


def test_empty_effect_receipt_is_honest_and_read_only(game_data):
    gs = new_campaign(game_data, seed=123)
    event = FlavorEvent(id="empty", season=gs.season, week=gs.week, team_id=gs.user_team_id,
        title="Moment", prompt="Choose", type_id="unknown", choices=[])
    frozen = gs.model_dump_json()
    before = flavor_feedback.snapshot(gs, event)
    assert flavor_feedback.settlement(gs, event, {}, before) == []
    assert gs.model_dump_json() == frozen



def test_opposing_culture_and_nominal_morale_can_cancel(game_data):
    gs = new_campaign(game_data, seed=123)
    tid = gs.user_team_id
    pid = gs.teams[tid].player_ids[0]
    culture.commit_principle(gs, tid, "development")
    # Obtain the real culture consequence without duplicating its formula.
    culture_only = gs.model_copy(deep=True)
    culture_only.players[pid].morale = 100.0
    culture.register_choice(culture_only, tid, "flavor", "behind_the_scenes", "let_loose", pid)
    settled_morale = culture_only.players[pid].morale
    assert 98.0 < settled_morale < 100.0
    gs.players[pid].morale = settled_morale
    event = FlavorEvent(id="cancellation", season=gs.season, week=gs.week, team_id=tid,
        player_id=pid, type_id="behind_the_scenes", title="Video", prompt="Choose", choices=[
            FlavorChoice(id="let_loose", label="Make it playful", outcomes=[FlavorOutcome(
                text="A loose moment catches on and brightens the squad.",
                effects={"player_followers": 1700, "player_morale": 2})])])
    gs.flavor_events_by[tid] = event
    before = flavor_feedback.snapshot(gs, event)
    # The authored morale boost changes the intermediate value; culture cancels it.
    intermediate = gs.model_copy(deep=True)
    flavor_events._apply_effects(intermediate, event, {"player_morale": 2})
    assert intermediate.players[pid].morale == 100.0
    ok, _, nominal = flavor_events.resolve(gs, tid, "let_loose")
    assert ok and gs.players[pid].morale == settled_morale
    row = next(row for row in flavor_feedback.settlement(gs, event, nominal, before)
        if row["metric"] == "player_morale" and row["subject_id"] == pid)
    assert row["delta"] == 0
    assert row["text"].endswith("; no net change.")


def test_actual_flavor_handler_does_not_leak_receipt_across_world_switch():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    subprocess.run([node, "tests/flavor_feedback_check.cjs"], check=True, capture_output=True, text=True)
