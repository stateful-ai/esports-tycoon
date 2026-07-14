"""The LLM harness is tested with scripted replies; no network model is needed."""

from __future__ import annotations

import json

from esports_sim.manager import flavor_events, media_events
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import HeadlessManagerEnv
from esports_sim.manager.llm_playtest import _recovery_action, run_llm_playtest, write_artifacts
from esports_sim.rng.tree import RngTree


class ScriptedClient:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if "Review this completed" in user:
            return "The action contract was readable. Add a clearer deadline summary."
        observation = json.loads(user.split("\n", 1)[1])
        legal = observation["legal_actions"]
        if legal["advance"]["enabled"]:
            return json.dumps({"kind": "advance", "params": {}})
        return json.dumps({"kind": "set_training", "params": {"focus": "tactical"}})


def test_llm_playtest_captures_contract_trace_and_artifacts(tmp_path, game_data):
    client = ScriptedClient()
    result = run_llm_playtest(game_data, client, seed=901, weeks=1)

    assert result.invalid_responses == 0
    assert result.action_counts["advance"] == 1
    assert result.traces[-1]["advanced"]
    assert result.critique.startswith("The action contract")
    paths = write_artifacts(result, tmp_path)
    assert paths["summary"].exists() and paths["critique"].read_text().startswith("The action")
    assert len(paths["traces"].read_text().splitlines()) == result.decisions


class InvalidThenAdvanceClient:
    def __init__(self):
        self.decisions = 0

    def complete(self, *, system: str, user: str) -> str:
        if "Review this completed" in user:
            return "The malformed reply was recovered and should be investigated."
        self.decisions += 1
        return "not json" if self.decisions == 1 else '{"kind":"advance","params":{}}'


def test_llm_playtest_records_invalid_reply_and_legal_recovery(game_data):
    result = run_llm_playtest(game_data, InvalidThenAdvanceClient(), seed=902, weeks=1)

    assert result.invalid_responses == result.recovery_actions == 1
    assert result.traces[0]["recovered"]
    assert result.traces[0]["action"]["kind"] == "advance"


def test_recovery_resolves_a_required_media_decision(game_data):
    gs = new_campaign(game_data, seed=903)
    tid = gs.user_team_id
    event = media_events._build_event(gs, tid, RngTree(gs.seed).derive("test", "media"))
    assert event is not None
    gs.media_events_by[tid] = event

    action = _recovery_action(HeadlessManagerEnv(gs, game_data).observe())

    assert action == {
        "kind": "resolve_media",
        "params": {"event_id": event.id, "choice_id": event.choices[0].id},
    }


def test_recovery_resolves_a_required_flavor_event(game_data):
    gs = new_campaign(game_data, seed=905)
    tid = gs.user_team_id
    event = flavor_events._build_event(gs, tid, RngTree(gs.seed).derive("test", "flavor"))
    gs.flavor_events_by[tid] = event

    action = _recovery_action(HeadlessManagerEnv(gs, game_data).observe())

    assert action == {
        "kind": "resolve_flavor",
        "params": {"event_id": event.id, "choice_id": event.choices[0].id},
    }


class RepeatsValidActionClient:
    def complete(self, *, system: str, user: str) -> str:
        if "Review this completed" in user:
            raise RuntimeError("critic unavailable")
        return '{"kind":"set_training","params":{"focus":"tactical"}}'


def test_llm_playtest_forces_weekly_progress_and_preserves_critique_failure(game_data):
    result = run_llm_playtest(
        game_data, RepeatsValidActionClient(), seed=904, weeks=1, max_decisions_per_week=2
    )

    assert result.traces[-1]["budget_forced"]
    assert result.traces[-1]["action"]["kind"] == "advance"
    assert result.critique_error == "critic unavailable"
    assert "failed" in result.critique.lower()
