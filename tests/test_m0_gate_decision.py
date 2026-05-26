"""The M0 gate decision is recorded in-repo and routes the frozen infra to M1.

This test pins the gate-decision artifact ``docs/m0_gate_decision.md`` so the
two things it carries cannot quietly drift apart from the test suite:

1. The decision itself — a verdict (``PASS``) bound to the playtest evidence
   that produced it.
2. The routing consequence — the M0-freeze skip labels that the parking PR
   (#32) wrote across the test suite have been re-scoped to M1, so a future
   contributor can grep one consistent string (``M1 scope:``) to find the
   M1 wedge-phase acceptance surface.

Both halves live in the same module because re-scoping the labels without
recording the decision would leave the M1 work surface unanchored, and
recording the decision without re-scoping the labels would let the parking
language outlive the gate it was waiting on. A regression of either half
should fail this test.
"""

from __future__ import annotations

import pathlib
import unittest


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DECISION_DOC = _REPO_ROOT / "docs" / "m0_gate_decision.md"
_PLAYTEST_DOC = _REPO_ROOT / "docs" / "playtest_m0_1.md"
_RESCOPE_DOC = _REPO_ROOT / "docs" / "m0_1_minimum_playable_rescope.md"
_TESTS_DIR = _REPO_ROOT / "tests"

# The set of test modules that PR #32 parked under "M0 freeze". The gate has
# now fired (PASS), so each module's skip reason must read "M1 scope: …" —
# the routing label this decision installs. Listed explicitly (rather than
# discovered) so a future un-skip lands a deliberate edit to this roster, not
# a silent removal that the test would no longer notice.
_M1_SCOPE_MODULES = (
    "test_canonical.py",
    "test_ci_contract.py",
    "test_golden_determinism.py",
    "test_loader.py",
    "test_referential_integrity.py",
    "test_regen_golden.py",
    "test_resolver_determinism.py",
    "test_schema_boundary.py",
    "test_schema_version.py",
    "test_toolchain_pin.py",
)


class TestGateDecisionArtifact(unittest.TestCase):
    """The recorded decision is the durable proof the gate closed."""

    @classmethod
    def setUpClass(cls):
        cls.text = _DECISION_DOC.read_text(encoding="utf-8")

    def test_decision_doc_exists(self):
        self.assertTrue(
            _DECISION_DOC.exists(),
            "docs/m0_gate_decision.md is the canonical M0 gate decision artifact",
        )

    def test_records_a_pass_verdict(self):
        # The acceptance criterion is asymmetric: pass greenlights M1, fail
        # opens a wedge-revisit. The decision doc must state which branch was
        # taken, in unambiguous prose, so a reader can answer the question
        # "did M0 close?" from this file alone.
        self.assertRegex(
            self.text,
            r"\*\*Verdict\.\*\*\s+\*\*PASS\.\*\*",
            "the decision doc must record a **Verdict.** **PASS.** line",
        )

    def test_cites_the_playtest_evidence(self):
        # The playtest doc is the evidence the verdict rests on. If this link
        # ever breaks (rename, deletion), the decision is no longer reproducible
        # from the artifact alone — the same hole PR #32's gate-decision
        # manifest concern flagged for the screenshot bundle.
        self.assertTrue(_PLAYTEST_DOC.exists(), "playtest evidence doc is missing")
        self.assertIn("playtest_m0_1.md", self.text)

    def test_cites_the_acceptance_bar(self):
        # The narrowed acceptance bar (one command, practice → match → fallout,
        # Chirper + recap, templated zero-API) is what the gate measured against;
        # the decision doc must reference it so a reader can trace verdict →
        # bar → in-repo pin (TestMinimumPlayable) without external context.
        self.assertTrue(_RESCOPE_DOC.exists(), "minimum-playable rescope doc is missing")
        self.assertIn("m0_1_minimum_playable_rescope.md", self.text)

    def test_routes_the_two_consequences(self):
        # Both branches of the acceptance criterion are named so this doc is
        # self-contained for a future reader who only finds this file: the
        # pass branch (M1 greenlit + frozen infra re-scoped) and the fail
        # branch (wedge-revisit), even though only the former was taken.
        self.assertIn("M1 is greenlit", self.text)
        self.assertIn("re-scoped to M1", self.text)
        self.assertIn("wedge-revisit", self.text)


class TestFrozenInfraReScopedToM1(unittest.TestCase):
    """Every parked test module now skips under the M1-scope label, not M0-freeze."""

    # The skip-reason patterns the parking PR installed. The decision doc
    # promises these are gone from the test surface — that promise is what
    # makes the M1 wedge-phase grep-discoverable under one consistent string.
    _FORBIDDEN_PATTERNS = (
        "M0 freeze",
        "deferred to M1/post-gate",
    )

    def _read(self, name: str) -> str:
        path = _TESTS_DIR / name
        self.assertTrue(path.exists(), f"missing M1-scope module: {name}")
        return path.read_text(encoding="utf-8")

    def test_each_parked_module_carries_the_m1_scope_label(self):
        # Every module in the roster must surface ``M1 scope:`` in its skip
        # reason text. The exact wording after the colon is module-specific
        # (it names the contract that module pins), so the check is a
        # prefix-presence test, not a full-string equality test.
        for name in _M1_SCOPE_MODULES:
            with self.subTest(module=name):
                text = self._read(name)
                self.assertRegex(
                    text,
                    r'(reason=|@unittest\.skip\()\s*\n?\s*"?M1 scope:',
                    f"{name} no longer carries an M1-scope skip label — "
                    "did a frozen test land without updating the decision roster?",
                )

    def test_no_parked_test_still_uses_the_pre_gate_language(self):
        # The pre-gate parking language (``M0 freeze:`` / ``deferred to
        # M1/post-gate``) must be gone from every test module. A lingering
        # match means the re-scope is half-applied: the decision doc would
        # claim the routing is complete while the suite still carried the
        # old hold.
        # This module itself names the forbidden labels (to grep for them);
        # exclude it from the scan so the check doesn't shadow-match its own
        # source.
        self_name = pathlib.Path(__file__).name
        for py_file in sorted(_TESTS_DIR.glob("*.py")):
            if py_file.name == self_name:
                continue
            with self.subTest(module=py_file.name):
                text = py_file.read_text(encoding="utf-8")
                for pattern in self._FORBIDDEN_PATTERNS:
                    self.assertNotIn(
                        pattern,
                        text,
                        f"{py_file.name} still carries pre-gate parking language "
                        f"{pattern!r}; re-scope to 'M1 scope: …' or drop the skip",
                    )

    def test_decision_doc_lists_every_parked_module(self):
        # The decision doc enumerates the frozen-now-M1 surface; if a module
        # joins or leaves the roster, the doc must move with it. (A test that
        # un-skips out from under the freeze should remove the corresponding
        # line in the decision doc in the same change.)
        text = _DECISION_DOC.read_text(encoding="utf-8")
        for name in _M1_SCOPE_MODULES:
            with self.subTest(module=name):
                self.assertIn(
                    f"tests/{name}",
                    text,
                    f"docs/m0_gate_decision.md must list tests/{name} in its "
                    "'Frozen items now owned by M1' roster",
                )


if __name__ == "__main__":
    unittest.main()
