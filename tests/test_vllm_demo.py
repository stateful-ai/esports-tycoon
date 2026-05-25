"""The vLLM-mode demo gate: preflight (safety + latency) + founder sign-off.

The acceptance criteria, exercised without a live endpoint by injecting a canned
client:

* The whole slice runs end-to-end **through the adapter in ``vllm`` mode** — the
  injected client is actually called, and the recap is honestly labelled vLLM
  (never the templated "zero-API" claim).
* **Total slice latency is measured and recorded** (plus the per-model-call
  aggregate), and an optional budget turns it into a pass/fail.
* The **adversarial-seed safety corpus passes** (every seed blocked), the run's
  own output is screened, and a leak in either fails the gate.
* The **founder's written sign-off** is bound to the preflight's output digest:
  a failed gate can't be approved, an approval authorises exactly that output,
  and any re-generation makes it stale.
"""

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import game_llm  # noqa: E402
from esports_tycoon.runner import SliceConfig, SliceDecisions  # noqa: E402
from esports_tycoon.vllm_demo import (  # noqa: E402
    approval,
    preflight,
)
from esports_tycoon.vllm_demo.preflight import (  # noqa: E402
    LatencyReport,
    run_preflight,
    screen_corpus,
    write_preflight,
)


class _StubLLM:
    """A duck-typed ``game_llm.GameLLM``: records every call, returns canned JSON.

    Stands in for a local Qwen so the gate can be exercised with no network. Each
    ``structured`` call returns the same ``{text, cites}`` shape every kind asks
    for; ``model`` is set so the preflight can record which model "ran".
    """

    def __init__(self, text="held the line. back to work.", cites=None):
        self.text, self.cites = text, list(cites or [])
        self.model = "qwen2.5-7b-instruct"
        self.calls = []

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return schema.model_validate({"text": self.text, "cites": self.cites})


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        cls.config = SliceConfig(opponent="apex_foundry", map="Helix", seed=6)
        cls.decisions = SliceDecisions(
            practice_focus="defaults",
            team_talk="no heroes. run the default.",
            fallout_post="week 6: held the line. on to week 7.",
        )

    def preflight(self, **kwargs):
        client = kwargs.pop("client", None) or _StubLLM()
        return run_preflight(self.world, self.config, self.decisions, client=client, **kwargs)


class TestRunsThroughAdapterInVllmMode(_Fixture):
    def test_injected_client_is_actually_called(self):
        client = _StubLLM()
        result = run_preflight(self.world, self.config, self.decisions, client=client)
        # The slice really drove the vllm backend: narration + halftime + 5 starters
        # + caster + opponent star = 9 model calls for this fixture.
        self.assertGreater(len(client.calls), 0)
        self.assertEqual(result.latency.model_calls, len(client.calls))
        # The canned line shows up in the rendered output, so the LLM path produced it.
        self.assertIn("held the line. back to work.", result.feed_html)

    def test_recap_is_labelled_vllm_not_zero_api(self):
        result = self.preflight()
        self.assertIn("vllm mode (local Qwen 7B/8B)", result.recap_md)
        self.assertNotIn("zero-API", result.recap_md)

    def test_records_the_model_that_ran(self):
        result = self.preflight()
        self.assertEqual(result.model, "qwen2.5-7b-instruct")

    def test_model_falls_back_to_env_default_when_client_has_no_model(self):
        class _NoModel(_StubLLM):
            def __init__(self):
                super().__init__()
                del self.model

        result = run_preflight(self.world, self.config, self.decisions, client=_NoModel())
        self.assertEqual(result.model, game_llm._DEFAULTS["GAME_LLM_MODEL"])


class TestLatencyMeasuredAndRecorded(_Fixture):
    def test_total_and_per_call_latency_recorded(self):
        result = self.preflight()
        lat = result.latency
        self.assertGreaterEqual(lat.total_seconds, 0.0)
        self.assertGreater(lat.model_calls, 0)
        # The whole slice wall-clock contains the model time spent inside it.
        self.assertGreaterEqual(lat.total_seconds, lat.model_seconds)
        self.assertGreaterEqual(lat.slowest_call_seconds, lat.mean_call_seconds)

    def test_unset_budget_is_recorded_not_gated(self):
        result = self.preflight()  # no latency_budget_seconds
        self.assertIsNone(result.latency.budget_seconds)
        self.assertTrue(result.latency.within_budget)

    def test_zero_budget_fails_and_blocks_the_gate(self):
        result = self.preflight(latency_budget_seconds=0.0)
        self.assertFalse(result.latency.within_budget)
        self.assertFalse(result.gate_ready)  # safety is fine; latency budget blew it

    def test_generous_budget_passes(self):
        result = self.preflight(latency_budget_seconds=3600.0)
        self.assertTrue(result.latency.within_budget)

    def test_measure_aggregates_durations(self):
        report = LatencyReport.measure(1.0, [0.2, 0.5, 0.3], budget_seconds=2.0)
        self.assertEqual(report.model_calls, 3)
        self.assertAlmostEqual(report.model_seconds, 1.0)
        self.assertAlmostEqual(report.slowest_call_seconds, 0.5)
        self.assertAlmostEqual(report.mean_call_seconds, 1.0 / 3)
        self.assertTrue(report.within_budget)

    def test_measure_with_no_calls_is_zeroed(self):
        report = LatencyReport.measure(0.5, [])
        self.assertEqual(report.model_calls, 0)
        self.assertEqual(report.slowest_call_seconds, 0.0)
        self.assertEqual(report.mean_call_seconds, 0.0)


class TestAdversarialCorpus(unittest.TestCase):
    def test_real_corpus_is_fully_blocked(self):
        result = screen_corpus()
        self.assertTrue(result.passed)
        self.assertEqual(result.leaks, [])
        self.assertEqual(result.blocked, result.total)
        # Every category contributes, attributed to itself.
        from esports_tycoon import safety

        for category, seeds in safety.ADVERSARIAL_SEED_CORPUS.items():
            self.assertEqual(result.by_category[category], len(seeds))

    def test_a_leaking_corpus_is_caught(self):
        doctored = {"slur": ["n1gg3r"], "harassment": ["have a nice day"]}  # 2nd is clean
        result = screen_corpus(doctored)
        self.assertFalse(result.passed)
        self.assertIn("have a nice day", result.leaks)
        self.assertEqual(result.blocked, 1)

    def test_empty_corpus_does_not_vacuously_pass(self):
        self.assertFalse(screen_corpus({}).passed)


class TestOutputScreening(_Fixture):
    def test_clean_generation_has_no_findings(self):
        result = self.preflight()
        self.assertEqual(result.safety.output_findings, [])
        self.assertTrue(result.safety.passed)

    def test_unsafe_generation_is_flagged_per_piece(self):
        result = self.preflight(client=_StubLLM(text="kill yourself, you threw it."))
        findings = result.safety.output_findings
        self.assertTrue(findings)
        for f in findings:
            self.assertIn("harassment", f.categories)
        # Narration + halftime + every generated post is unsafe → many findings.
        self.assertGreater(len(findings), 1)
        self.assertFalse(result.safety.passed)
        self.assertFalse(result.gate_ready)

    def test_screen_output_covers_narration_halftime_and_feed(self):
        # Every generated surface is screened: with a uniformly unsafe client,
        # narration, the half-time ack, and the feed posts all show up as findings.
        unsafe = self.preflight(client=_StubLLM(text="go die already"))
        sources = {f.source for f in unsafe.safety.output_findings}
        self.assertIn("narration", sources)
        self.assertIn("halftime", sources)
        self.assertTrue(any(s.startswith("feed:") for s in sources))


class TestDigestBinding(_Fixture):
    def test_same_output_yields_same_digest(self):
        a = self.preflight(client=_StubLLM(text="same line."))
        b = self.preflight(client=_StubLLM(text="same line."))
        self.assertEqual(a.digest, b.digest)

    def test_different_output_yields_different_digest(self):
        a = self.preflight(client=_StubLLM(text="one line."))
        b = self.preflight(client=_StubLLM(text="another line."))
        self.assertNotEqual(a.digest, b.digest)


class TestWriteAndLoadEvidence(_Fixture):
    def test_writes_bundle_and_reloads_evidence(self):
        result = self.preflight()
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_preflight(result, tmp)
            self.assertTrue(paths["preflight"].is_file())
            self.assertTrue(paths["recap"].is_file())
            self.assertTrue(paths["feed"].is_file())
            # The screenshot surface is the honestly-labelled recap.
            self.assertIn("vllm mode (local Qwen 7B/8B)", paths["recap"].read_text(encoding="utf-8"))
            # The evidence reloads with the same digest the sign-off will bind to.
            evidence = preflight.load_evidence(tmp)
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence["digest"], result.digest)
            self.assertTrue(evidence["gate_ready"])
            self.assertEqual(evidence["safety"]["corpus_blocked"], evidence["safety"]["corpus_total"])

    def test_load_evidence_absent_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(preflight.load_evidence(tmp))

    def test_evidence_is_json_serialisable(self):
        evidence = self.preflight().evidence()
        # Round-trips through JSON with no custom encoder.
        self.assertEqual(json.loads(json.dumps(evidence))["kind"], "vllm_demo_preflight")


class TestFounderSignOff(_Fixture):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.record_path = pathlib.Path(self._tmp.name) / "vllm_demo.approval.yaml"

    def tearDown(self):
        self._tmp.cleanup()

    def test_unreviewed_blocks_screenshots(self):
        evidence = self.preflight().evidence()
        status = approval.gate_status(evidence, None)
        self.assertEqual(status["status"], "unreviewed")
        self.assertFalse(approval.screenshot_allowed(evidence, None))

    def test_no_preflight_status(self):
        status = approval.gate_status(None, None)
        self.assertEqual(status["status"], "no_preflight")
        self.assertFalse(approval.screenshot_allowed(None, None))

    def test_sign_off_authorises_exactly_this_output(self):
        evidence = self.preflight().evidence()
        approval.record_decision(evidence, "approve", approver="founder@x.com", record_path=self.record_path)
        record = approval.load_record(self.record_path)
        self.assertEqual(record["decision"], "approve")
        self.assertEqual(record["digest"], evidence["digest"])
        self.assertEqual(approval.gate_status(evidence, record)["status"], "approved")
        self.assertTrue(approval.screenshot_allowed(evidence, record))

    def test_cannot_sign_off_when_gate_failed(self):
        # An unsafe generation → gate not ready → approval refused.
        bad = self.preflight(client=_StubLLM(text="kys")).evidence()
        self.assertFalse(bad["gate_ready"])
        with self.assertRaises(ValueError):
            approval.record_decision(bad, "approve", approver="founder@x.com", record_path=self.record_path)

    def test_reject_requires_reason_and_blocks_screenshots(self):
        evidence = self.preflight().evidence()
        with self.assertRaises(ValueError):
            approval.record_decision(evidence, "reject", approver="founder@x.com", record_path=self.record_path)
        approval.record_decision(
            evidence, "reject", approver="founder@x.com", reason="tone is off", record_path=self.record_path
        )
        record = approval.load_record(self.record_path)
        self.assertEqual(approval.gate_status(evidence, record)["status"], "rejected")
        self.assertFalse(approval.screenshot_allowed(evidence, record))

    def test_approval_goes_stale_when_output_changes(self):
        approved = self.preflight(client=_StubLLM(text="approved line.")).evidence()
        approval.record_decision(approved, "approve", approver="founder@x.com", record_path=self.record_path)
        record = approval.load_record(self.record_path)

        # A fresh generation produces different prose → a different digest.
        regenerated = self.preflight(client=_StubLLM(text="regenerated line.")).evidence()
        self.assertNotEqual(regenerated["digest"], approved["digest"])
        status = approval.gate_status(regenerated, record)
        self.assertEqual(status["status"], "stale")
        self.assertFalse(approval.screenshot_allowed(regenerated, record))

    def test_invalid_decision_and_missing_approver_rejected(self):
        evidence = self.preflight().evidence()
        with self.assertRaises(ValueError):
            approval.record_decision(evidence, "maybe", approver="x", record_path=self.record_path)
        with self.assertRaises(ValueError):
            approval.record_decision(evidence, "approve", approver="   ", record_path=self.record_path)


class TestCLI(_Fixture):
    """The CLI wired end-to-end, with the live endpoint replaced by the stub."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.artifacts = self._tmp.name
        self.record = str(pathlib.Path(self._tmp.name) / "approval.yaml")
        self._orig_get_llm = game_llm.get_llm
        game_llm.get_llm = lambda: _StubLLM()

    def tearDown(self):
        game_llm.get_llm = self._orig_get_llm
        self._tmp.cleanup()

    def _main(self, argv):
        from esports_tycoon.vllm_demo.__main__ import main

        # Quiet the CLI's prints so the suite stays clean under the verbose runner.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(["--artifacts-dir", self.artifacts, "--record", self.record, *argv])

    def test_preflight_then_signoff_then_status_allows_screenshots(self):
        # preflight: green gate → exit 0, bundle written.
        self.assertEqual(self._main(["preflight", "--seed", "6"]), 0)
        self.assertTrue((pathlib.Path(self.artifacts) / preflight.PREFLIGHT_FILENAME).is_file())

        # status before sign-off: blocked.
        self.assertEqual(self._main(["status"]), 1)

        # sign-off: records the founder's written approval.
        self.assertEqual(self._main(["sign-off", "--approver", "founder@x.com"]), 0)

        # status after sign-off: screenshots allowed.
        self.assertEqual(self._main(["status"]), 0)

    def test_signoff_without_preflight_errors(self):
        self.assertEqual(self._main(["sign-off", "--approver", "founder@x.com"]), 2)

    def test_status_without_preflight_is_blocked(self):
        self.assertEqual(self._main(["status"]), 1)

    def test_reject_requires_reason(self):
        self.assertEqual(self._main(["preflight"]), 0)
        self.assertEqual(self._main(["reject", "--approver", "founder@x.com"]), 1)
        self.assertEqual(self._main(["reject", "--approver", "founder@x.com", "--reason", "off tone"]), 0)
        self.assertEqual(self._main(["status"]), 1)  # rejected → still blocked


if __name__ == "__main__":
    unittest.main()
