"""The TrainingDecision M0.2 foundation is landed behind the playtest gate.

This test pins the artifact ``docs/m0_tycoon_decisions_slice.md`` so the three
things it carries cannot quietly drift apart from the test suite:

1. The annotation itself — the slice is the M0.2 post-gate milestone, the
   ninth of the items the founder brief parked behind the playtest gate, and
   its first foundation has landed.
2. The gate condition — the M0.1 playtest pass/fail verdict must stay on disk
   now that ``Player.skills`` / ``training_points`` / ``decision_effects`` have
   landed.
3. The regression bar — the golden round-trip (``test_golden_determinism.py
   :: TestGoldenDeterminism`` resolve half) and the same-seed→same-
   ``WhyRecord`` checks (``test_resolver_determinism.py :: TestDeterminism``
   and ``:: TestResolverEntropyDiscipline``) must stay green and un-skipped
   through the gate.

A regression of any of those halves falsifies the landing record — at which
point a fresh review of the doc is owed before any further work on the slice.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_HOLD_DOC = _REPO_ROOT / "docs" / "m0_tycoon_decisions_slice.md"
_PLAYTEST_DOC = _REPO_ROOT / "docs" / "playtest_m0_1.md"
_GATE_DOC = _REPO_ROOT / "docs" / "m0_gate_decision.md"
_FOUNDER_DOC = _REPO_ROOT / "docs" / "founder_brief.md"
_SCHEMA_SRC = _REPO_ROOT / "esports_tycoon" / "schema.py"
_TESTS_DIR = _REPO_ROOT / "tests"

sys.path.insert(0, str(_REPO_ROOT))

from esports_tycoon import schema  # noqa: E402

# The three field names the slice introduces together. Listed here as the
# single source of truth so the doc, the gate condition, and the landed-shape
# check all reference the same roster.
_SLICE_FIELDS = ("skills", "training_points", "decision_effects")

# The M0.1 playtest verdict line shape. ``docs/playtest_m0_1.md`` records the
# verdict as ``**Verdict: PASS …**`` or ``**Verdict: FAIL …**`` (the
# acceptance criterion is asymmetric, but either half is "recorded"). The
# regex covers both branches so the gate condition is "a verdict was written
# down", not "the verdict was a particular value".
_VERDICT_LINE_RE = re.compile(
    r"\*\*Verdict:\s*(PASS|FAIL)\b[^*]*\*\*",
    re.IGNORECASE,
)


def _playtest_verdict_recorded() -> bool:
    """True iff ``docs/playtest_m0_1.md`` carries a PASS/FAIL verdict line."""
    if not _PLAYTEST_DOC.exists():
        return False
    return bool(_VERDICT_LINE_RE.search(_PLAYTEST_DOC.read_text(encoding="utf-8")))


class TestLandingDocArtifact(unittest.TestCase):
    """The recorded artifact is the durable proof the slice landed intentionally."""

    @classmethod
    def setUpClass(cls):
        cls.text = _HOLD_DOC.read_text(encoding="utf-8")

    def test_landing_doc_exists(self):
        self.assertTrue(
            _HOLD_DOC.exists(),
            "docs/m0_tycoon_decisions_slice.md is the canonical landing artifact "
            "for the TrainingDecision slice",
        )

    def test_annotated_as_post_gate_next_milestone(self):
        # The doc must state, in unambiguous prose, that the slice is the M0.2
        # post-gate next milestone. A reader who only finds this file must be
        # able to answer "where does this slice land?" without external
        # context.
        self.assertRegex(
            self.text,
            r"(?i)post-?gate",
            "the doc must annotate the slice as post-gate",
        )
        self.assertIn(
            "M0.2",
            self.text,
            "the doc must name M0.2 as the milestone the slice lands in",
        )
        self.assertRegex(
            self.text,
            r"\*\*Status\.\*\*\s+\*\*Landed in M0\.2 foundation\.\*\*",
            "the doc must record a **Status.** **Landed in M0.2 foundation.** "
            "line so a future reader can answer the landing question from "
            "the artifact alone",
        )

    def test_cites_the_playtest_gate_and_decision_doc(self):
        # The in-bound condition this landing rests on is the M0.1 playtest gate;
        # the doc must reference both the playtest record and the gate
        # decision so a reader can trace landing → gate → verdict without
        # external context.
        self.assertTrue(_PLAYTEST_DOC.exists(), "playtest record doc is missing")
        self.assertTrue(_GATE_DOC.exists(), "gate decision doc is missing")
        self.assertIn("playtest_m0_1.md", self.text)
        self.assertIn("m0_gate_decision.md", self.text)

    def test_cites_the_founder_brief_freeze_list(self):
        # The slice is named in the founder brief's "Frozen post-gate" roster;
        # the doc must reference that listing so the landing's lineage is
        # traceable from the artifact alone.
        self.assertTrue(_FOUNDER_DOC.exists(), "founder brief is missing")
        self.assertIn("founder_brief.md", self.text)
        self.assertIn(
            "TrainingDecision",
            _FOUNDER_DOC.read_text(encoding="utf-8"),
            "founder_brief.md must still name the TrainingDecision slice in "
            "its freeze list — that is what this landing routed",
        )

    def test_enumerates_the_three_slice_field_names(self):
        # The slice's seam is the three field names landing together; the doc
        # must enumerate each one verbatim so a future PR that introduces them
        # is auditable against the same roster the test pin reads.
        for field in _SLICE_FIELDS:
            with self.subTest(field=field):
                self.assertIn(
                    field,
                    self.text,
                    f"the doc must name the TrainingDecision field {field!r} "
                    "so the slice's seam is enumerated in one place",
                )
        # The composite name ``Player.skills`` is the form the acceptance
        # criterion uses; pin that exact spelling so a rename of the field
        # under the player model lands a deliberate edit to this doc.
        self.assertIn("Player.skills", self.text)

    def test_names_the_regression_bar_pin_modules(self):
        # The doc commits to two regression bars that must stay green through
        # the gate; both pin modules must be named so a future contributor
        # can grep from the doc back to the test that enforces it.
        self.assertIn("test_golden_determinism.py", self.text)
        self.assertIn("test_resolver_determinism.py", self.text)


class TestGateConditionEnforced(unittest.TestCase):
    """No PR adds the three field names until the M0.1 verdict is on disk."""

    def test_playtest_doc_records_a_verdict(self):
        # The current state — the doc records ``Verdict: PASS`` — is what
        # made the slice eligible to land. The pin asserts the verdict line
        # exists at all; stripping it from the playtest doc invalidates the
        # landed fields below.
        self.assertTrue(
            _PLAYTEST_DOC.exists(),
            "docs/playtest_m0_1.md is the playtest record this hold gates on",
        )
        verdict = _VERDICT_LINE_RE.search(_PLAYTEST_DOC.read_text(encoding="utf-8"))
        self.assertIsNotNone(
            verdict,
            "docs/playtest_m0_1.md must carry a recorded **Verdict: PASS** "
            "or **Verdict: FAIL** line — that is the gate condition the "
            "TrainingDecision slice is held behind",
        )

    def test_deferred_fields_absent_when_verdict_is_absent(self):
        # If a regression strips the verdict line, the three field names must
        # not appear on ``Player`` either — the gate is symmetric, and the
        # test fails the schema half loudly so a half-applied regression is
        # caught.
        if _playtest_verdict_recorded():
            # The verdict is on disk; the slice is allowed to stay landed. The
            # absence check lifts. The structural counterpart below pins the
            # landed shape while the verdict remains recorded.
            self.skipTest(
                "playtest verdict is recorded; the absence check lifts. The "
                "structural counterpart runs in "
                "test_training_decision_fields_have_landed_in_the_recorded_shape."
            )
        schema_text = _SCHEMA_SRC.read_text(encoding="utf-8")
        for field in _SLICE_FIELDS:
            with self.subTest(field=field):
                self.assertNotIn(
                    field,
                    schema_text,
                    f"docs/playtest_m0_1.md no longer records a verdict, but "
                    f"{field} has landed in schema.py — the gate contract in "
                    "docs/m0_tycoon_decisions_slice.md is broken",
                )

    def test_training_decision_fields_have_landed_in_the_recorded_shape(self):
        # The gate verdict is on disk, so the first M0.2 foundation is allowed
        # to exist. Pin the exact shape this landing chose: persistent player
        # skills live on Player; weekly budget/effects live on Decisions.
        player_field_names = set(schema.Player.model_fields.keys())
        decision_field_names = set(schema.Decisions.model_fields.keys())

        self.assertIn("skills", player_field_names)
        self.assertIn("training_points", decision_field_names)
        self.assertIn("decision_effects", decision_field_names)
        self.assertTrue(
            {"player", "skill", "delta", "training_points"} <= set(schema.DecisionEffect.model_fields),
            "DecisionEffect must keep the typed player/skill/delta/cost table "
            "that the M0.2 landing record describes",
        )


class TestRegressionBarStaysGreen(unittest.TestCase):
    """The golden round-trip and same-seed→same-WhyRecord pins are present and active."""

    # The hold doc commits to two pin modules. They must exist, must not be
    # parked under ``M1 scope:`` (the M1 reproducibility-floor freeze that
    # docs/m0_gate_decision.md routes), and must contain the specific
    # assertions named in the regression bar.
    _GOLDEN_MODULE = _TESTS_DIR / "test_golden_determinism.py"
    _RESOLVER_MODULE = _TESTS_DIR / "test_resolver_determinism.py"

    def test_golden_resolve_half_is_present_and_active(self):
        # The committed week6 resolve golden is the active half of the
        # golden-determinism module (the round-trip half is M1's scope and
        # is parked under ``M1 scope:``). The slice must not move those
        # bytes without a reviewed regeneration.
        text = self._GOLDEN_MODULE.read_text(encoding="utf-8")
        self.assertIn("class TestGoldenDeterminism", text)
        self.assertIn("test_resolve_is_byte_identical_across_two_runs", text)
        self.assertIn("test_resolve_matches_committed_golden", text)
        # The class itself must not be skip-decorated (the M1-scope skips on
        # individual ``test_round_trip_*`` methods are fine — those are the
        # round-trip half the hold doc explicitly excludes from this bar).
        class_skip = re.search(
            r"@unittest\.skip\([^)]*\)\s*\nclass TestGoldenDeterminism\b",
            text,
        )
        self.assertIsNone(
            class_skip,
            "TestGoldenDeterminism must stay un-skipped: the resolve-half "
            "golden is the active regression bar for the TrainingDecision slice",
        )

    def test_resolver_determinism_seed_pins_are_present_and_active(self):
        # The same-seed → same-WhyRecord half rests on three specific pins:
        # the seed is echoed, the resolver does not mutate inputs, and the
        # entropy-discipline class boobytraps ambient random/time/uuid.
        text = self._RESOLVER_MODULE.read_text(encoding="utf-8")
        self.assertIn("class TestDeterminism", text)
        self.assertIn("def test_seed_is_echoed", text)
        self.assertIn("def test_run_does_not_mutate_inputs", text)
        self.assertIn("class TestResolverEntropyDiscipline", text)
        # The 100-run digest sweep IS parked under ``M1 scope:`` (per the
        # hold doc and the gate decision); only that specific method may
        # carry the skip, and the class itself must not.
        class_skip = re.search(
            r"@unittest\.skip\([^)]*\)\s*\nclass TestDeterminism\b",
            text,
        )
        self.assertIsNone(
            class_skip,
            "TestDeterminism must stay un-skipped at the class level: the "
            "seed-echo and no-mutation pins are the active regression bar "
            "for the TrainingDecision slice",
        )
        entropy_class_skip = re.search(
            r"@unittest\.skip\([^)]*\)\s*\nclass TestResolverEntropyDiscipline\b",
            text,
        )
        self.assertIsNone(
            entropy_class_skip,
            "TestResolverEntropyDiscipline must stay un-skipped: the "
            "same-save → same-match contract is what the slice's new "
            "decision fields must not break",
        )

    def test_regression_bar_modules_run_green(self):
        # Beyond structural presence, the bar must actually pass *now* — the
        # hold doc commits to "stay green through the gate", which means
        # the pin runs the named assertions and trips loudly if any go red.
        # This is a load-bearing assertion: if the resolver's bytes drift or
        # the resolver picks up ambient state, this test fails before the
        # slice is allowed to land further.
        from esports_tycoon import resolver  # noqa: E402
        from esports_tycoon.canned import loader  # noqa: E402
        from esports_tycoon.schema import Decisions  # noqa: E402

        world = loader.load()

        # Same-seed byte-identity, in one process.
        first = resolver.run(world, Decisions(opponent="northwind"), 12345)
        second = resolver.run(world, Decisions(opponent="northwind"), 12345)
        self.assertEqual(
            first,
            second,
            "resolver lost same-seed byte-identity — the regression bar this "
            "hold commits to has tripped; do not land the slice",
        )

        # The committed week6 resolve golden still matches.
        import json

        from esports_tycoon.schema import WhyRecord  # noqa: E402

        golden_path = _TESTS_DIR / "golden" / "week6_resolve.json"
        self.assertTrue(
            golden_path.exists(),
            "tests/golden/week6_resolve.json is the committed resolve "
            "golden the hold doc names as the round-trip regression bar",
        )
        record = resolver.run(
            world,
            Decisions(
                opponent="tidewater",
                map="Helix",
                practice_focus="defaults",
                tactical_stance="default",
            ),
            5,
        )
        produced = (
            json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        )
        self.assertEqual(
            produced,
            golden_path.read_text(encoding="utf-8"),
            "resolve output drifted from tests/golden/week6_resolve.json — "
            "the round-trip regression bar this hold commits to has tripped; "
            "do not land the slice without a reviewed UPDATE_GOLDEN=1 diff",
        )
        # The produced record really is a WhyRecord, not a dict — the
        # same-seed → same-WhyRecord half of the bar names the type by name.
        self.assertIsInstance(record, WhyRecord)


if __name__ == "__main__":
    unittest.main()
