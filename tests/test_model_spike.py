"""The structured-output adherence spike: corpus, verdict, and CLI.

These prove the spike without a live endpoint by injecting duck-typed clients
(the same trick the vllm tests use):

* the sampled corpus is the *real* adapter contract — built from the production
  ``llm._build_request`` for the real ``_LLMReply`` schema under the real per-kind
  token cap — spanning all three kinds and all five personas, and deterministic;
* a candidate that returns schema-valid JSON on ≥9/10 samples passes and yields a
  chosen model + settings; 8/10 fails; a too-small sample can never pass;
* a sample whose call raises is recorded as non-adhering, not raised; and a client
  that cannot be constructed is a reported top-level error, not a crash;
* the CLI exits 0 only on a passing spike.
"""

import contextlib
import io
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import game_llm, llm  # noqa: E402
from esports_tycoon.model_spike import adherence  # noqa: E402
from esports_tycoon.model_spike.adherence import (  # noqa: E402
    DEFAULT_THRESHOLD,
    MIN_SAMPLES,
    AdherenceReport,
    build_sample_prompts,
    run_adherence_spike,
    write_report,
)


# --------------------------------------------------------------------------- #
# Duck-typed clients.
# --------------------------------------------------------------------------- #
class _GoodLLM:
    """Always returns a schema-valid ``_LLMReply``; records every call."""

    def __init__(self, model="qwen2.5-7b-instruct", temperature=0.2, max_retries=2):
        self.model, self.temperature, self._max_retries = model, temperature, max_retries
        self.calls = []

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.calls.append({"prompt": prompt, "schema": schema, "system": system, "max_tokens": max_tokens})
        return schema.model_validate({"text": "held. won.", "cites": []})


class _PartialLLM(_GoodLLM):
    """Fails (raises, like a parse miss after retries) the first ``fail_first`` calls."""

    def __init__(self, fail_first=1, **kw):
        super().__init__(**kw)
        self.fail_first = fail_first
        self.n = 0

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.n += 1
        if self.n <= self.fail_first:
            raise ValueError("could not parse _LLMReply from the model")
        return super().structured(prompt, schema, system=system, max_tokens=max_tokens)


class _BadShapeLLM(_GoodLLM):
    """Answers, but with a dict, not a validated ``_LLMReply`` — a decode miss."""

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        return {"text": "nope", "cites": []}


class _DownLLM:
    model = "qwen2.5-7b-instruct"

    def structured(self, *a, **k):
        raise ConnectionError("connection refused")


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()


# --------------------------------------------------------------------------- #
# The sampled corpus.
# --------------------------------------------------------------------------- #
class TestCorpus(_Fixture):
    def test_corpus_is_full_size_and_spans_all_kinds(self):
        prompts = build_sample_prompts(self.world)
        self.assertEqual(len(prompts), MIN_SAMPLES)
        kinds = [p.kind for p in prompts]
        self.assertEqual(kinds.count("narration"), 2)
        self.assertEqual(kinds.count("chirper_post"), 5)
        self.assertEqual(kinds.count("halftime_ack"), 3)

    def test_names_are_unique(self):
        names = [p.name for p in build_sample_prompts(self.world)]
        self.assertEqual(len(names), len(set(names)))

    def test_each_prompt_carries_the_real_per_kind_cap(self):
        for p in build_sample_prompts(self.world):
            self.assertEqual(p.max_tokens, llm.MAX_TOKENS[p.kind])

    def test_prompts_are_the_real_contract(self):
        by_name = {p.name: p for p in build_sample_prompts(self.world)}
        # narration: narrator voice + a real cite menu of mem: ids.
        narr = by_name["narration_apex_default"]
        self.assertIn("narrator", narr.system.lower())
        self.assertIn("mem:", narr.user)
        # chirper: the player's handle is in the system (their voice contract).
        self.assertIn("@vexstrike", by_name["chirper_vex_apex"].system)
        # halftime: the second-half stance is in the user prompt.
        self.assertIn("aggressive", by_name["halftime_down_aggressive"].user)

    def test_corpus_is_deterministic(self):
        self.assertEqual(build_sample_prompts(self.world), build_sample_prompts(self.world))


# --------------------------------------------------------------------------- #
# The verdict.
# --------------------------------------------------------------------------- #
class TestVerdict(_Fixture):
    def test_all_valid_passes_and_yields_chosen_model_and_settings(self):
        client = _GoodLLM(model="qwen3-8b", temperature=0.2, max_retries=2)
        report = run_adherence_spike(self.world, client=client)
        self.assertTrue(report.passed)
        self.assertEqual(report.valid, report.total)
        self.assertEqual(report.total, MIN_SAMPLES)
        self.assertIsNone(report.error)
        chosen = report.chosen
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["model"], "qwen3-8b")
        self.assertEqual(chosen["settings"]["temperature"], 0.2)
        self.assertEqual(chosen["settings"]["max_retries"], 2)
        self.assertEqual(chosen["settings"]["decode"], "prompted-json")
        self.assertEqual(chosen["settings"]["token_caps"], llm.MAX_TOKENS)

    def test_each_sample_is_run_under_its_cap_with_the_reply_schema(self):
        client = _GoodLLM()
        run_adherence_spike(self.world, client=client)
        self.assertEqual(len(client.calls), MIN_SAMPLES)
        for call in client.calls:
            self.assertIs(call["schema"], llm._LLMReply)
            self.assertIn(call["max_tokens"], set(llm.MAX_TOKENS.values()))

    def test_valid_samples_report_estimated_output_tokens(self):
        report = run_adherence_spike(self.world, client=_GoodLLM())
        self.assertTrue(all(r.tokens_out > 0 for r in report.results))

    def test_nine_of_ten_passes_at_default_threshold(self):
        report = run_adherence_spike(self.world, client=_PartialLLM(fail_first=1))
        self.assertEqual(report.valid, 9)
        self.assertEqual(report.required, 9)
        self.assertTrue(report.passed)

    def test_eight_of_ten_fails(self):
        report = run_adherence_spike(self.world, client=_PartialLLM(fail_first=2))
        self.assertEqual(report.valid, 8)
        self.assertFalse(report.passed)
        self.assertIsNone(report.chosen)

    def test_failed_sample_is_recorded_not_raised(self):
        report = run_adherence_spike(self.world, client=_PartialLLM(fail_first=1))
        bad = [r for r in report.results if not r.ok]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].tokens_out, 0)
        self.assertIn("could not parse", bad[0].error)

    def test_non_reply_shape_counts_as_non_adhering(self):
        report = run_adherence_spike(self.world, client=_BadShapeLLM())
        self.assertEqual(report.valid, 0)
        self.assertFalse(report.passed)
        self.assertTrue(all("_LLMReply" in (r.error or "") for r in report.results))

    def test_down_endpoint_is_all_failures_not_a_crash(self):
        report = run_adherence_spike(self.world, client=_DownLLM())
        self.assertEqual(report.valid, 0)
        self.assertFalse(report.passed)
        self.assertTrue(all("connection refused" in (r.error or "") for r in report.results))

    def test_client_construction_failure_is_a_reported_top_level_error(self):
        orig = game_llm.get_llm

        def _boom():
            raise ModuleNotFoundError("No module named 'openai'")

        game_llm.get_llm = _boom
        try:
            report = run_adherence_spike(self.world)  # no client → builds the default
        finally:
            game_llm.get_llm = orig
        self.assertIsNotNone(report.error)
        self.assertIn("openai", report.error)
        self.assertEqual(report.results, [])
        self.assertFalse(report.passed)
        # Even on a build failure, the model falls back to the env default name.
        self.assertEqual(report.model, game_llm._DEFAULTS["GAME_LLM_MODEL"])

    def test_threshold_out_of_range_is_rejected(self):
        for bad in (0.0, -0.1, 1.5):
            with self.assertRaises(ValueError):
                run_adherence_spike(self.world, client=_GoodLLM(), threshold=bad)

    def test_too_small_a_sample_can_never_pass(self):
        prompts = build_sample_prompts(self.world)[:3]
        report = run_adherence_spike(self.world, client=_GoodLLM(), samples=prompts)
        self.assertEqual(report.valid, 3)  # all three were valid...
        self.assertFalse(report.passed)  # ...but three is below MIN_SAMPLES


# --------------------------------------------------------------------------- #
# Evidence + writing.
# --------------------------------------------------------------------------- #
class TestEvidence(_Fixture):
    def test_evidence_is_serialisable_and_carries_the_chosen_block(self):
        report = run_adherence_spike(self.world, client=_GoodLLM(model="qwen3-8b"))
        ev = report.evidence()
        round_tripped = json.loads(json.dumps(ev))  # must be JSON-clean
        self.assertEqual(round_tripped["kind"], "model_adherence_spike")
        self.assertTrue(round_tripped["passed"])
        self.assertEqual(round_tripped["chosen"]["model"], "qwen3-8b")
        self.assertEqual(len(round_tripped["samples"]), MIN_SAMPLES)

    def test_failed_evidence_has_null_chosen(self):
        ev = run_adherence_spike(self.world, client=_PartialLLM(fail_first=2)).evidence()
        self.assertIsNone(ev["chosen"])

    def test_write_report_writes_the_evidence_json(self):
        import tempfile

        report = run_adherence_spike(self.world, client=_GoodLLM())
        with tempfile.TemporaryDirectory() as d:
            path = write_report(report, d)
            self.assertTrue(path.exists())
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, report.evidence())


# --------------------------------------------------------------------------- #
# The CLI.
# --------------------------------------------------------------------------- #
class TestCLI(unittest.TestCase):
    def setUp(self):
        self._orig_get_llm = game_llm.get_llm

    def tearDown(self):
        game_llm.get_llm = self._orig_get_llm

    def _main(self, argv, stub):
        from esports_tycoon.model_spike.__main__ import main

        game_llm.get_llm = lambda: stub
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = main([*argv, "--no-write"])
        return code, out.getvalue()

    def test_passing_spike_exits_zero_and_prints_chosen(self):
        code, out = self._main([], _GoodLLM(model="qwen3-8b"))
        self.assertEqual(code, 0)
        self.assertIn("CHOSEN MODEL", out)
        self.assertIn("qwen3-8b", out)

    def test_failing_spike_exits_one(self):
        code, _ = self._main([], _PartialLLM(fail_first=2))
        self.assertEqual(code, 1)

    def test_down_endpoint_exits_one(self):
        code, _ = self._main([], _DownLLM())
        self.assertEqual(code, 1)

    def test_write_lands_in_the_artifacts_dir(self):
        import tempfile

        from esports_tycoon.model_spike.__main__ import main
        from esports_tycoon.model_spike.adherence import REPORT_FILENAME

        game_llm.get_llm = lambda: _GoodLLM()
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["--artifacts-dir", d])
            self.assertEqual(code, 0)
            self.assertTrue((pathlib.Path(d) / REPORT_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
