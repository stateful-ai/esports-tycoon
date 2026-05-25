"""The one render-time gate: safety + grounding + cost in a single pass.

Covers the pre-filter (unsafe input never reaches the model), the unified regen
loop (regen on an un-resolvable cite *or* an unsafe completion), withholding of
output that can't be made safe, per-attempt cost metering across regens, and the
ceiling breach that halts the run. A final integration test drives the real vLLM
backend (via a fake client) through the gate to prove it composes end to end.
"""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import gate, resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import GenerationContext, llm  # noqa: E402
from esports_tycoon.cost import CostCeilingExceeded, CostMeter, CostModel  # noqa: E402
from esports_tycoon.schema import Decisions, GeneratedContent  # noqa: E402

REAL = "mem:rook:scrim_w5_choke"
FAKE = "mem:rook:not_a_real_event"


def content(text="held. won.", *, cites=None, raw_cites=None, tin=10, tout=10):
    raw = json.dumps({"text": text, "cites": raw_cites}) if raw_cites is not None else None
    return GeneratedContent(
        kind="chirper_post",
        text=text,
        grounding_status="ok",
        cites=list(cites or []),
        raw_llm_output=raw,
        tokens_in=tin,
        tokens_out=tout,
    )


def scripted(*items):
    seq = list(items)

    def gen():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return gen


class TestPreFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()

    def test_unsafe_input_rejected_before_any_generation(self):
        called = {"n": 0}

        def gen():
            called["n"] += 1
            return content()

        meter = CostMeter(ceiling_usd=None)
        with self.assertRaises(gate.UnsafeInputError) as caught:
            gate.render(gen, world=self.world, meter=meter, inputs=["kys"])
        self.assertEqual(called["n"], 0)  # model never invoked
        self.assertEqual(meter.calls, 0)  # nothing metered
        self.assertIn("harassment", caught.exception.verdict.categories)

    def test_safe_inputs_pass_through(self):
        meter = CostMeter(ceiling_usd=None)
        result = gate.render(
            scripted(content(cites=[REAL], raw_cites=[REAL])),
            world=self.world, meter=meter, inputs=["push aggressive this half"],
        )
        self.assertFalse(result.blocked)


class TestGateComposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()

    def test_happy_path_grounded_safe_and_priced(self):
        meter = CostMeter(ceiling_usd=None, model=CostModel(1.0, 1.0))
        result = gate.render(
            scripted(content("held. won.", cites=[REAL], raw_cites=[REAL])),
            world=self.world, meter=meter,
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.content.grounding_status, "ok")
        self.assertEqual(result.content.cites, [REAL])
        self.assertTrue(result.safety.ok)
        self.assertAlmostEqual(result.cost.cost_usd, 0.02)  # (10+10)/1000 * 1.0
        self.assertAlmostEqual(result.content.cost_usd, 0.02)  # stamped back on

    def test_unresolvable_cite_dropped(self):
        meter = CostMeter(ceiling_usd=None)
        result = gate.render(
            scripted(content("x", raw_cites=[REAL, FAKE])),
            world=self.world, meter=meter, max_regen=2,
        )
        self.assertEqual(result.content.grounding_status, "dropped")
        self.assertEqual(result.content.cites, [REAL])
        self.assertEqual(result.attempts, 3)

    def test_unsafe_output_regenerated_then_withheld(self):
        meter = CostMeter(ceiling_usd=None)
        result = gate.render(
            scripted(content("kys loser", raw_cites=[])),
            world=self.world, meter=meter, max_regen=2,
        )
        self.assertTrue(result.blocked)
        self.assertEqual(result.content.text, gate.WITHHELD_TEXT)
        self.assertEqual(result.content.cites, [])
        self.assertEqual(result.attempts, 3)  # tried to regen the slur away
        self.assertIn("harassment", result.safety.categories)

    def test_unsafe_then_safe_is_not_blocked(self):
        bad = content("kys", raw_cites=[])
        good = content("held. won.", raw_cites=[])
        meter = CostMeter(ceiling_usd=None)
        result = gate.render(
            scripted(bad, good), world=self.world, meter=meter, max_regen=2
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.content.text, "held. won.")

    def test_cost_is_summed_across_regens(self):
        bad = content("x", raw_cites=[FAKE], tin=10, tout=10)
        meter = CostMeter(ceiling_usd=None, model=CostModel(1.0, 1.0))
        result = gate.render(
            scripted(bad), world=self.world, meter=meter, max_regen=2
        )
        # 3 attempts * (10+10) tokens * $1/1k = $0.06
        self.assertEqual(meter.calls, 3)
        self.assertAlmostEqual(result.cost.cost_usd, 0.06)

    def test_meter_accumulates_across_renders_for_the_slice(self):
        meter = CostMeter(ceiling_usd=None, model=CostModel(1.0, 1.0))
        for _ in range(3):
            gate.render(
                scripted(content(cites=[REAL], raw_cites=[REAL])),
                world=self.world, meter=meter,
            )
        self.assertEqual(meter.calls, 3)
        self.assertAlmostEqual(meter.spent_usd, 0.06)

    def test_cost_ceiling_breach_halts_the_run(self):
        # A priced model with a tiny ceiling: the gate must let the breach raise.
        meter = CostMeter(ceiling_usd=0.01, model=CostModel(1.0, 1.0))
        with self.assertRaises(CostCeilingExceeded):
            gate.render(
                scripted(content(tin=100, tout=100, cites=[REAL], raw_cites=[REAL])),
                world=self.world, meter=meter,
            )


class TestGateWithRealBackend(unittest.TestCase):
    """The real vLLM backend (via a fake client) composes through the gate."""

    class _FakeLLM:
        def __init__(self, *replies):
            self.replies = list(replies)
            self.calls = 0

        def structured(self, prompt, schema, *, system=None, max_tokens=None):
            reply = self.replies[min(self.calls, len(self.replies) - 1)]
            self.calls += 1
            return schema.model_validate(reply)

    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        cls.decisions = Decisions(opponent="northwind", map="Helix")
        cls.why = resolver.run(cls.world, cls.decisions, 7)

    def _ctx(self):
        return GenerationContext(world=self.world, why=self.why, author="rook", decisions=self.decisions)

    def test_invented_cite_is_regenerated_then_resolved(self):
        client = self._FakeLLM(
            {"text": "remember the playoffs?", "cites": [FAKE]},          # invented -> regen
            {"text": "we'll review the tape.", "cites": [REAL]},          # clean
        )
        meter = CostMeter(ceiling_usd=None, model=CostModel(1.0, 1.0))
        generate = lambda: llm.generate("chirper_post", self._ctx(), client=client)  # noqa: E731
        result = gate.render(generate, world=self.world, meter=meter, max_regen=2)
        self.assertEqual(client.calls, 2)
        self.assertEqual(result.content.grounding_status, "regen")
        self.assertEqual(result.content.cites, [REAL])
        self.assertGreater(meter.tokens_in, 0)  # real backend stamped usage
        self.assertGreater(meter.spent_usd, 0.0)

    def test_unsafe_completion_is_withheld(self):
        client = self._FakeLLM({"text": "kill yourself", "cites": []})
        meter = CostMeter(ceiling_usd=None)
        generate = lambda: llm.generate("chirper_post", self._ctx(), client=client)  # noqa: E731
        result = gate.render(generate, world=self.world, meter=meter, max_regen=1)
        self.assertTrue(result.blocked)
        self.assertEqual(result.content.text, gate.WITHHELD_TEXT)


if __name__ == "__main__":
    unittest.main()
