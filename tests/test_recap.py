"""The recap: per-slice grounding-rate + drop-rate (and safety/cost) into recap.md.

Proves the aggregation math, the rendered markdown carries the rates the
acceptance requires, the >20% drop-rate smell is flagged, and ``write_recap``
actually writes a ``recap.md`` containing them.
"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import recap  # noqa: E402
from esports_tycoon.cost import CostMeter, CostModel  # noqa: E402
from esports_tycoon.gate import GateResult  # noqa: E402
from esports_tycoon.grounding import GroundingOutcome  # noqa: E402
from esports_tycoon.cost import CallCost  # noqa: E402
from esports_tycoon.safety import SafetyVerdict  # noqa: E402
from esports_tycoon.schema import GeneratedContent  # noqa: E402


def result(*, status, offered, resolved, dropped, blocked=False, categories=None):
    gc = GeneratedContent(kind="chirper_post", text="x", grounding_status=status)
    return GateResult(
        content=gc,
        grounding=GroundingOutcome(
            status=status, attempts=1, offered=offered, resolved=resolved, dropped=dropped
        ),
        safety=SafetyVerdict(ok=not blocked, categories=list(categories or []), matches=[]),
        cost=CallCost(tokens_in=0, tokens_out=0, cost_usd=0.0),
        blocked=blocked,
        attempts=1,
    )


class TestSliceReportMath(unittest.TestCase):
    def test_aggregates_counts_and_rates(self):
        report = recap.SliceReport()
        report.add(result(status="ok", offered=2, resolved=2, dropped=0))
        report.add(result(status="dropped", offered=2, resolved=1, dropped=1))
        self.assertEqual(report.pieces, 2)
        self.assertEqual(report.cites_offered, 4)
        self.assertEqual(report.cites_resolved, 3)
        self.assertEqual(report.cites_dropped, 1)
        self.assertEqual(report.grounding_rate, 0.75)
        self.assertEqual(report.drop_rate, 0.25)
        self.assertEqual(report.status_counts["ok"], 1)
        self.assertEqual(report.status_counts["dropped"], 1)

    def test_no_offered_cites_is_vacuously_grounded(self):
        report = recap.SliceReport()
        report.add(result(status="ok", offered=0, resolved=0, dropped=0))
        self.assertEqual(report.grounding_rate, 1.0)
        self.assertEqual(report.drop_rate, 0.0)

    def test_safety_blocks_are_tallied(self):
        report = recap.SliceReport()
        report.add(result(status="ok", offered=0, resolved=0, dropped=0,
                          blocked=True, categories=["harassment"]))
        self.assertEqual(report.blocked, 1)
        self.assertEqual(report.safety_categories["harassment"], 1)


class TestRenderMarkdown(unittest.TestCase):
    def test_contains_grounding_and_drop_rate(self):
        report = recap.SliceReport()
        report.add(result(status="regen", offered=4, resolved=3, dropped=1))
        md = recap.render_markdown(report)
        self.assertIn("grounding-rate: 75.0%", md)
        self.assertIn("drop-rate: 25.0%", md)
        self.assertIn("regen 1", md)

    def test_drop_rate_smell_flagged_above_threshold(self):
        report = recap.SliceReport()
        report.add(result(status="dropped", offered=10, resolved=7, dropped=3))  # 30%
        md = recap.render_markdown(report)
        self.assertIn("⚠", md)
        self.assertIn("smell", md)

    def test_drop_rate_not_flagged_below_threshold(self):
        report = recap.SliceReport()
        report.add(result(status="ok", offered=100, resolved=90, dropped=10))  # 10%
        md = recap.render_markdown(report)
        self.assertNotIn("smell", md)

    def test_cost_section_present_with_meter(self):
        report = recap.SliceReport()
        report.add(result(status="ok", offered=1, resolved=1, dropped=0))
        meter = CostMeter(ceiling_usd=0.50, model=CostModel(1.0, 1.0))
        meter.record(100, 100)
        md = recap.render_markdown(report, meter=meter)
        self.assertIn("## Cost", md)
        self.assertIn("ceiling $0.5000", md)
        self.assertIn("200", md)  # tokens line (100 in + 100 out)

    def test_halted_flag_renders(self):
        report = recap.SliceReport()
        meter = CostMeter(ceiling_usd=0.01, model=CostModel(1.0, 1.0))
        md = recap.render_markdown(report, meter=meter, halted=True)
        self.assertIn("HALTED", md)

    def test_cost_section_absent_without_meter(self):
        report = recap.SliceReport()
        md = recap.render_markdown(report)
        self.assertNotIn("## Cost", md)


class TestWriteRecap(unittest.TestCase):
    def test_writes_file_with_rates(self):
        report = recap.SliceReport()
        report.add(result(status="ok", offered=2, resolved=2, dropped=0))
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "runs" / "slice1" / "recap.md"
            written = recap.write_recap(path, report)
            self.assertTrue(written.exists())
            body = written.read_text(encoding="utf-8")
            self.assertIn("# Slice recap", body)
            self.assertIn("grounding-rate: 100.0%", body)
            self.assertIn("drop-rate: 0.0%", body)


if __name__ == "__main__":
    unittest.main()
