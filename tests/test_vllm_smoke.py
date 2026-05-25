"""The OpenAI-endpoint smoke test: up + structured + warm under budget.

The bring-up acceptance check, exercised without a live endpoint by injecting a
duck-typed client (the same trick the rest of the vllm tests use):

* a structured round-trip through the game's own client path resolves to ``ok``
  only when the reply parses **and** the warm call lands within the budget;
* a down endpoint (the client raises) is reported, not raised — ``ok=False`` with
  a populated ``error``, so a caller/CLI can branch on it;
* the *measured* call is the warm one (after the untimed warm-up), and the budget
  defaults to the 5s the acceptance criterion names;
* the CLI exits 0 only on a fully green smoke.
"""

import contextlib
import io
import pathlib
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.content import game_llm  # noqa: E402
from esports_tycoon.vllm_demo import smoke  # noqa: E402
from esports_tycoon.vllm_demo.smoke import (  # noqa: E402
    DEFAULT_BUDGET_SECONDS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROMPT,
    SmokeResult,
    run_smoke,
)


class _StubLLM:
    """A duck-typed ``game_llm.GameLLM``: records calls, returns canned JSON."""

    def __init__(self, ready=True, note="ok", model="qwen2.5-7b-instruct"):
        self.ready, self.note, self.model = ready, note, model
        self.calls = []

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.calls.append({"prompt": prompt, "schema": schema, "system": system, "max_tokens": max_tokens})
        return schema.model_validate({"ready": self.ready, "note": self.note})


class _CountingStub:
    """Returns a distinct note per call, so the test can tell which call was timed."""

    def __init__(self):
        self.n = 0
        self.model = "qwen2.5-7b-instruct"

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.n += 1
        return schema.model_validate({"ready": True, "note": f"call{self.n}"})


class _DownStub:
    """A server that isn't there: every call raises, like a refused connection."""

    model = "qwen2.5-7b-instruct"

    def structured(self, *args, **kwargs):
        raise ConnectionError("connection refused")


class _BadShapeStub:
    """Answers, but not with the asked-for model — a structured-decode miss."""

    model = "qwen2.5-7b-instruct"

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        return {"ready": True}  # a dict, not a validated _SmokePing


def _raise_no_openai():
    raise ModuleNotFoundError("No module named 'openai'")


class TestHappyPath(unittest.TestCase):
    def test_green_smoke_is_ok(self):
        result = run_smoke(client=_StubLLM(note="up"), budget_seconds=5.0)
        self.assertTrue(result.ok)
        self.assertTrue(result.reachable)
        self.assertTrue(result.structured_ok)
        self.assertTrue(result.within_budget)
        self.assertIsNone(result.error)
        self.assertEqual(result.reply, {"ready": True, "note": "up"})

    def test_default_budget_is_the_acceptance_5s(self):
        self.assertEqual(DEFAULT_BUDGET_SECONDS, 5.0)
        result = run_smoke(client=_StubLLM())  # no explicit budget
        self.assertEqual(result.budget_seconds, 5.0)

    def test_records_the_model_that_answered(self):
        result = run_smoke(client=_StubLLM(model="qwen3-8b"), budget_seconds=5.0)
        self.assertEqual(result.model, "qwen3-8b")

    def test_model_falls_back_to_env_default_when_client_has_no_model(self):
        class _NoModel(_StubLLM):
            def __init__(self):
                super().__init__()
                del self.model

        result = run_smoke(client=_NoModel(), budget_seconds=5.0)
        self.assertEqual(result.model, game_llm._DEFAULTS["GAME_LLM_MODEL"])


class TestPromptContract(unittest.TestCase):
    def test_asks_for_the_smoke_schema_with_system_and_token_cap(self):
        client = _StubLLM()
        run_smoke(client=client, budget_seconds=5.0)
        call = client.calls[-1]
        self.assertEqual(call["schema"].__name__, "_SmokePing")
        self.assertEqual(call["system"], smoke._SYSTEM)
        self.assertEqual(call["max_tokens"], DEFAULT_MAX_TOKENS)
        self.assertEqual(call["prompt"], DEFAULT_PROMPT)

    def test_custom_prompt_is_forwarded(self):
        client = _StubLLM()
        run_smoke(client=client, prompt="ping?", budget_seconds=5.0)
        self.assertEqual(client.calls[-1]["prompt"], "ping?")


class TestWarmup(unittest.TestCase):
    def test_warmup_makes_two_calls_and_times_the_second(self):
        client = _CountingStub()
        result = run_smoke(client=client, budget_seconds=5.0)
        self.assertEqual(client.n, 2)  # one warm-up + one measured
        self.assertIsNotNone(result.warmup_seconds)
        # The reported reply is the warm (second) call, not the warm-up.
        self.assertEqual(result.reply, {"ready": True, "note": "call2"})

    def test_no_warmup_makes_one_call_and_records_no_warmup(self):
        client = _CountingStub()
        result = run_smoke(client=client, warmup=False, budget_seconds=5.0)
        self.assertEqual(client.n, 1)
        self.assertIsNone(result.warmup_seconds)
        self.assertEqual(result.reply, {"ready": True, "note": "call1"})


class TestBudget(unittest.TestCase):
    def test_over_budget_fails_but_is_still_reachable_and_structured(self):
        # A zero budget can never be met (a completed call always took > 0s), so
        # this isolates the latency verdict without a sleep or a real endpoint.
        result = run_smoke(client=_StubLLM(), budget_seconds=0.0)
        self.assertTrue(result.reachable)
        self.assertTrue(result.structured_ok)
        self.assertFalse(result.within_budget)
        self.assertFalse(result.ok)
        self.assertIsNone(result.error)

    def test_a_real_delay_over_budget_fails(self):
        class _SlowStub(_StubLLM):
            def structured(self, prompt, schema, *, system=None, max_tokens=None):
                time.sleep(0.02)
                return super().structured(prompt, schema, system=system, max_tokens=max_tokens)

        result = run_smoke(client=_SlowStub(), warmup=False, budget_seconds=0.005)
        self.assertGreaterEqual(result.latency_seconds, 0.02)
        self.assertFalse(result.ok)


class TestFailures(unittest.TestCase):
    def test_down_endpoint_is_reported_not_raised(self):
        result = run_smoke(client=_DownStub(), budget_seconds=5.0)
        self.assertFalse(result.ok)
        self.assertFalse(result.reachable)
        self.assertFalse(result.structured_ok)
        self.assertIsNone(result.reply)
        self.assertIn("connection refused", result.error)
        self.assertEqual(result.latency_seconds, 0.0)

    def test_unparseable_reply_is_not_ok(self):
        result = run_smoke(client=_BadShapeStub(), budget_seconds=5.0)
        self.assertTrue(result.reachable)  # the call returned
        self.assertFalse(result.structured_ok)  # ...but not the asked-for shape
        self.assertFalse(result.ok)
        self.assertIsNone(result.reply)

    def test_client_construction_failure_is_reported_not_raised(self):
        # No client passed → run_smoke builds the default via game_llm.get_llm(),
        # which imports openai lazily; a missing `vllm` extra raises there. The
        # smoke must catch it and fall back to the env-default model name.
        orig = game_llm.get_llm
        game_llm.get_llm = _raise_no_openai
        try:
            result = run_smoke(budget_seconds=5.0)
        finally:
            game_llm.get_llm = orig
        self.assertFalse(result.ok)
        self.assertFalse(result.reachable)
        self.assertEqual(result.model, game_llm._DEFAULTS["GAME_LLM_MODEL"])
        self.assertIn("openai", result.error)


class TestWithinBudgetProperty(unittest.TestCase):
    def test_within_budget_requires_structured_ok(self):
        # A call that never returned has no honest latency; within_budget must not
        # read the zeroed latency as "fast".
        unreachable = SmokeResult(
            ok=False, model="m", reachable=False, structured_ok=False,
            latency_seconds=0.0, budget_seconds=5.0, warmup_seconds=None,
            reply=None, error="boom",
        )
        self.assertFalse(unreachable.within_budget)

    def test_within_budget_is_inclusive_of_the_budget(self):
        on_budget = SmokeResult(
            ok=True, model="m", reachable=True, structured_ok=True,
            latency_seconds=5.0, budget_seconds=5.0, warmup_seconds=None,
            reply={"ready": True, "note": ""}, error=None,
        )
        self.assertTrue(on_budget.within_budget)


class TestCLI(unittest.TestCase):
    """The `smoke` subcommand, with the live endpoint replaced by a stub."""

    def setUp(self):
        self._orig_get_llm = game_llm.get_llm

    def tearDown(self):
        game_llm.get_llm = self._orig_get_llm

    def _main(self, argv, stub):
        from esports_tycoon.vllm_demo.__main__ import main

        game_llm.get_llm = lambda: stub
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(["smoke", *argv])

    def test_green_smoke_exits_zero(self):
        self.assertEqual(self._main(["--budget", "5"], _StubLLM()), 0)

    def test_over_budget_exits_one(self):
        self.assertEqual(self._main(["--budget", "0"], _StubLLM()), 1)

    def test_down_endpoint_exits_one(self):
        self.assertEqual(self._main([], _DownStub()), 1)

    def test_no_warmup_flag_is_accepted(self):
        self.assertEqual(self._main(["--no-warmup", "--budget", "5"], _StubLLM()), 0)


if __name__ == "__main__":
    unittest.main()
