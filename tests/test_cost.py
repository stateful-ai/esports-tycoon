"""The per-slice cost meter: accounting plus a fail-closed ceiling.

Proves token estimation, pricing, accumulation, and — the acceptance criterion —
that a per-slice ceiling breach raises and so halts the run, while the default
(free local-vLLM) model never trips it.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.cost import (  # noqa: E402
    DEFAULT_CEILING_USD,
    CallCost,
    CostCeilingExceeded,
    CostMeter,
    CostModel,
    estimate_tokens,
)


class TestEstimateTokens(unittest.TestCase):
    def test_empty_and_whitespace_are_zero(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("   \n "), 0)

    def test_scales_with_length(self):
        self.assertEqual(estimate_tokens("abcd"), 1)  # 4 chars / 4
        self.assertEqual(estimate_tokens("a" * 41), 11)  # ceil(41/4)
        self.assertGreater(estimate_tokens("a" * 100), estimate_tokens("a" * 10))


class TestCostModel(unittest.TestCase):
    def test_default_is_free_local_vllm(self):
        self.assertEqual(CostModel().price(1000, 1000), 0.0)

    def test_prices_per_thousand_tokens(self):
        model = CostModel(usd_per_1k_input=2.0, usd_per_1k_output=4.0)
        self.assertAlmostEqual(model.price(1000, 500), 2.0 + 2.0)

    def test_negative_prices_rejected(self):
        with self.assertRaises(ValueError):
            CostModel(usd_per_1k_input=-1.0)


class TestCostMeter(unittest.TestCase):
    def test_accumulates_tokens_and_spend(self):
        meter = CostMeter(ceiling_usd=None, model=CostModel(1.0, 1.0))
        meter.record(100, 200)
        meter.record(50, 50)
        self.assertEqual(meter.tokens_in, 150)
        self.assertEqual(meter.tokens_out, 250)
        self.assertEqual(meter.calls, 2)
        self.assertAlmostEqual(meter.spent_usd, (150 + 250) / 1000.0)

    def test_record_returns_call_cost(self):
        meter = CostMeter(ceiling_usd=None, model=CostModel(1.0, 1.0))
        call = meter.record(100, 100)
        self.assertIsInstance(call, CallCost)
        self.assertAlmostEqual(call.cost_usd, 0.2)

    def test_ceiling_breach_halts_with_figures(self):
        meter = CostMeter(ceiling_usd=0.10, model=CostModel(1.0, 1.0))
        meter.record(40, 40)  # $0.08, under
        with self.assertRaises(CostCeilingExceeded) as caught:
            meter.record(20, 20)  # tips to $0.12, over
        err = caught.exception
        self.assertGreater(err.spent_usd, err.ceiling_usd)
        self.assertEqual(err.ceiling_usd, 0.10)
        self.assertEqual(err.calls, 2)

    def test_breaching_call_is_still_counted(self):
        # The run halts, but the spend reflects everything generated, including
        # the call that tipped it over.
        meter = CostMeter(ceiling_usd=0.10, model=CostModel(1.0, 1.0))
        with self.assertRaises(CostCeilingExceeded):
            meter.record(200, 0)  # $0.20 in one shot
        self.assertEqual(meter.tokens_in, 200)
        self.assertAlmostEqual(meter.spent_usd, 0.20)

    def test_exactly_at_ceiling_does_not_breach(self):
        meter = CostMeter(ceiling_usd=0.10, model=CostModel(1.0, 1.0))
        meter.record(50, 50)  # exactly $0.10
        self.assertAlmostEqual(meter.spent_usd, 0.10)  # no raise

    def test_none_ceiling_never_halts(self):
        meter = CostMeter(ceiling_usd=None, model=CostModel(1000.0, 1000.0))
        for _ in range(5):
            meter.record(1000, 1000)
        self.assertGreater(meter.spent_usd, 1.0)  # no raise

    def test_default_free_model_stays_at_zero_under_default_ceiling(self):
        # The M0 reality: local vLLM is free, so a slice spends $0 well under the
        # default ceiling no matter how much it generates.
        meter = CostMeter()  # default ceiling + free model
        self.assertEqual(meter.ceiling_usd, DEFAULT_CEILING_USD)
        for _ in range(1000):
            meter.record(500, 500)
        self.assertEqual(meter.spent_usd, 0.0)

    def test_negative_token_counts_rejected(self):
        meter = CostMeter()
        with self.assertRaises(ValueError):
            meter.record(-1, 0)

    def test_negative_ceiling_rejected(self):
        with self.assertRaises(ValueError):
            CostMeter(ceiling_usd=-0.5)


if __name__ == "__main__":
    unittest.main()
