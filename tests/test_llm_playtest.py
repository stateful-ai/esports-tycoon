"""The LLM harness is tested with scripted replies; no network model is needed."""

from __future__ import annotations

import json

import ssl
from urllib import error

import pytest

from esports_sim.manager import flavor_events, media_events
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import HeadlessManagerEnv
from esports_sim.manager.llm_playtest import (
    LLMPlaytestResult,
    OpenAICompatibleClient,
    _recovery_action,
    _sampled_decisions,
    _season_critique_prompt,
    run_llm_playtest,
    write_artifacts,
)
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
    # The summary artifact carries the decision-legibility section: every
    # env-stepped action lands in action_log, so its census matches the
    # trace counts and the score stays a bounded ratio.
    leg = result.playtest_summary["decision_legibility"]
    assert leg["action_counts"] == result.action_counts
    assert 0.0 <= leg["legibility_score"] <= 1.0
    assert leg["total_decisions"] == leg["settled_with_outcome"] + leg["unsettled"]
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


def test_llm_playtest_gives_one_corrective_retry_before_recovery(game_data):
    result = run_llm_playtest(game_data, InvalidThenAdvanceClient(), seed=902, weeks=1)

    # The rejected first reply counts as invalid, but the model fixed it on
    # the corrective retry — no deterministic recovery needed.
    assert result.invalid_responses == 1
    assert result.recovery_actions == 0
    assert result.traces[0]["corrected"] and not result.traces[0]["recovered"]
    assert result.traces[0]["retry_reply"] is not None
    assert result.traces[0]["action"]["kind"] == "advance"


class AlwaysInvalidClient:
    def complete(self, *, system: str, user: str) -> str:
        if "Review this completed" in user:
            return "Both replies were rejected; deterministic recovery finished the week."
        return "not json ever"


def test_llm_playtest_falls_back_to_recovery_when_retry_also_fails(game_data):
    result = run_llm_playtest(game_data, AlwaysInvalidClient(), seed=902, weeks=1)

    assert result.invalid_responses >= 1
    assert result.recovery_actions >= 1
    assert result.traces[0]["recovered"] and not result.traces[0]["corrected"]
    assert "retry also rejected" in result.traces[0]["error"]


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


class FlakyTransportClient(OpenAICompatibleClient):
    """Fails the wire N times, then succeeds — no real network involved.
    Alternates failure types to prove the catch net covers both raw SSL
    errors (which escape urllib's URLError wrapping mid-read) and URLError."""

    def __init__(self, failures: int, **kwargs):
        self.sleeps: list[float] = []
        super().__init__(
            "http://unit.test/v1", "fake-model", sleeper=self.sleeps.append, **kwargs
        )
        self._failures = failures
        self.attempts = 0

    def _transport(self, payload, headers):
        self.attempts += 1
        if self.attempts <= self._failures:
            if self.attempts % 2 == 1:
                raise ssl.SSLError("bad record mac")
            raise error.URLError("connection dropped")
        return {"choices": [{"message": {"content": "ok"}}]}


def test_openai_client_retries_transient_transport_failures():
    client = FlakyTransportClient(failures=2)

    assert client.complete(system="s", user="u") == "ok"
    assert client.attempts == 3
    # Linear backoff: delay * attempt for each failed attempt.
    assert client.sleeps == [2.0, 4.0]


def test_openai_client_raises_after_exhausting_retries():
    client = FlakyTransportClient(failures=5, retries=2)

    with pytest.raises(RuntimeError, match="after 2 attempts"):
        client.complete(system="s", user="u")
    assert client.attempts == 2


class PaymentRequiredClient(OpenAICompatibleClient):
    def __init__(self):
        self.attempts = 0
        super().__init__("http://unit.test/v1", "fake-model", sleeper=lambda s: None)

    def _transport(self, payload, headers):
        self.attempts += 1
        raise error.HTTPError("http://unit.test", 402, "Payment Required", {}, None)


def test_openai_client_fails_fast_on_non_transient_http_errors():
    """A 402/401 is not transient — retrying just burns wall-clock (a real
    out-of-credits run retried its way through three attempts)."""
    client = PaymentRequiredClient()

    with pytest.raises(RuntimeError, match="HTTP 402"):
        client.complete(system="s", user="u")
    assert client.attempts == 1


def test_llm_playtest_streams_traces_to_sink(game_data):
    streamed: list[dict] = []
    result = run_llm_playtest(
        game_data, ScriptedClient(), seed=906, weeks=1, trace_sink=streamed.append
    )

    assert len(streamed) == result.decisions
    assert streamed == result.traces


def test_sampled_decisions_covers_the_whole_arc():
    traces = [
        {"season": 1, "week": i, "action": {"kind": "advance"}, "message": "", "recovered": False}
        for i in range(200)
    ]
    picked = _sampled_decisions(traces, cap=10)

    assert len(picked) == 10
    assert picked[0]["week"] == 0
    assert picked[-1]["week"] > 150  # tail reached, not just the head
    assert set(picked[0]) == {"season", "week", "action", "message", "recovered"}


def test_season_critique_sections_land_in_artifacts(tmp_path):
    result = LLMPlaytestResult(
        seed=1, initial_team_id="t", team_id="t", weeks=None, seasons_requested=1,
        seasons_completed=1, decisions=1, invalid_responses=0, recovery_actions=0,
        total_reward=0.0, action_counts={}, final_features={}, playtest_summary={},
        season_reports=[], traces=[], critique="Overall fine.", critique_error=None,
        season_critiques=[{"season": 1, "critique": "Season one was legible.", "error": None}],
    )
    paths = write_artifacts(result, tmp_path)

    text = paths["critique"].read_text()
    assert "Overall fine." in text
    assert "## Season 1" in text and "Season one was legible." in text
    prompt = _season_critique_prompt(1, {"champion": "x"}, [])
    assert "Review season 1" in prompt and "season_report" in prompt
