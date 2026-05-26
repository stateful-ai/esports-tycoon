"""The pre-playtest review proposal for the rendered "remembered me" line is durable.

This test pins the proposal artifact ``docs/playtest_signoff_remembered_line.md``
so the three things it carries cannot quietly drift apart from the test suite:

1. The staged framing itself — the doc is explicitly an implementing-agent
   proposal *awaiting* design's recorded GO, not a recorded GO. The
   acceptance criterion the playtest evening hangs on is that **design**
   confirms the line reads personal-not-coincidental, and only a design
   reviewer can close that bar. The pin fails closed if the doc ever
   self-issues a GO before that confirmation lands.
2. The copy fix that was filed alongside the proposal (so it does not get
   lost as the next sharpening of the slot — and so it remains the
   recommended path if design returns NO-GO).
3. The rendered shape the proposal was given against — if the slot's
   render format changes, the proposal must be re-staged. The pin asserts
   the slot still renders as ``> **Remembered:** {who}, week {N} —
   {summary} (`{cite}`)`` against the canonical save, so a silent format
   change to the line invalidates this test (and the doc that depends on
   it).

Together those three halves make the proposal self-falsifying: a regression
on the staged framing, the filed fix, or the rendered line each fails this
test, which is the contract the doc itself promises in its "Where this
proposal is pinned" section.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SIGNOFF_DOC = _REPO_ROOT / "docs" / "playtest_signoff_remembered_line.md"

sys.path.insert(0, str(_REPO_ROOT))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.runner import (  # noqa: E402
    SliceConfig,
    SliceDecisions,
    render_recap_md,
    run_slice,
    slice_events,
)
from esports_tycoon.runner.recap import REMEMBERED_SLOT_LABEL  # noqa: E402


class TestSignoffDoc(unittest.TestCase):
    """The staged proposal is the durable record of what design is being asked."""

    @classmethod
    def setUpClass(cls):
        cls.text = _SIGNOFF_DOC.read_text(encoding="utf-8")

    def test_signoff_doc_exists(self):
        self.assertTrue(
            _SIGNOFF_DOC.exists(),
            "docs/playtest_signoff_remembered_line.md is the canonical "
            "pre-playtest review artifact for the bound precedent slot",
        )

    def test_is_staged_for_design_not_self_issued(self):
        # The acceptance criterion is that **design** confirms the line, and
        # the implementing agent cannot stand in for that. The doc must mark
        # itself as staged, carry an explicit confirmation block keyed for
        # design to fill in, and must NOT have already filled it in. If the
        # confirmation block ever loses its PENDING placeholders without a
        # named reviewer + date taking their place, this test fails closed.
        self.assertRegex(
            self.text,
            r"\*\*Status\.\*\*\s+\*\*Staged for design\s*—\s*awaiting GO\.\*\*",
            "the doc must mark itself **Staged for design — awaiting GO.** so "
            "no reader mistakes it for a recorded sign-off",
        )
        self.assertIn(
            "## Design confirmation",
            self.text,
            "the doc must carry a Design confirmation block for the reviewer "
            "to record their verdict in",
        )
        # The PENDING placeholders are the unfilled state of the block. If a
        # design reviewer fills the block in, they replace these verbatim; if
        # they are missing AND no `**Design verdict.** **GO.**` / **NO-GO.**
        # line has been recorded, the doc is in a broken halfway state and
        # the test must fail.
        has_pending = "_PENDING_" in self.text
        has_recorded_verdict = bool(
            re.search(
                r"\*\*Design verdict\.\*\*\s+\*\*(GO|NO-GO)\.\*\*",
                self.text,
            )
        )
        self.assertTrue(
            has_pending or has_recorded_verdict,
            "the Design confirmation block must either still carry its "
            "_PENDING_ placeholders (staged, awaiting design) or carry a "
            "recorded `**Design verdict.** **GO.**` / **NO-GO.** line — "
            "never neither",
        )

    def test_does_not_self_issue_a_verdict(self):
        # Guard against regressing to the prior framing where the
        # implementing agent recorded a `**Verdict.** **GO.**` line itself.
        # Only `**Design verdict.** **GO.**` / **NO-GO.** is permitted, and
        # only the design reviewer writes it.
        self.assertNotRegex(
            self.text,
            r"(?<!Design )\*\*Verdict\.\*\*\s+\*\*GO\.\*\*",
            "the doc must not carry a bare **Verdict.** **GO.** line — only "
            "design records the verdict, under the **Design verdict.** label",
        )

    def test_names_the_slot_label_it_signed_off_on(self):
        # The slot is identified by REMEMBERED_SLOT_LABEL ("Remembered"). The
        # doc must reference the same label so a future reader can grep from
        # the slot to the sign-off and back without external context.
        self.assertIn(f"**{REMEMBERED_SLOT_LABEL}:**", self.text)
        self.assertIn("REMEMBERED_SLOT_LABEL", self.text)

    def test_quotes_the_canonical_bound_cite(self):
        # The line reviewed bound `mem:rook:scrim_w5_choke` on the canonical
        # Week-6 fixture; the doc quotes that cite so the verdict is bound to
        # the specific bytes the founder will see, not a hypothetical line.
        self.assertIn("mem:rook:scrim_w5_choke", self.text)

    def test_files_the_followup_copy_fix(self):
        # The "personal but soft" framing must come with a filed copy fix so
        # the next sharpening of the slot is not re-discovered from scratch
        # by the next playtest reviewer. The fix names its seam (the recap
        # render and the run-log event it would extend) so it lands on the
        # same surface this doc reviewed.
        self.assertIn("Copy fix #1", self.text)
        self.assertIn("matched_tag", self.text)
        self.assertIn("esports_tycoon/runner/recap.py", self.text)
        self.assertIn("esports_tycoon/runner/events.py", self.text)


class TestSignedOffLineShapeStillRenders(unittest.TestCase):
    """The rendered shape the verdict was given against still lands in recap.md.

    A silent change to the slot's render format would leave a GO verdict
    standing for a line that no longer exists. Pinning the shape here means
    a future render edit either updates this test (and re-runs the playtest
    sign-off) or fails loudly.
    """

    @classmethod
    def setUpClass(cls):
        world = loader.load()
        config = SliceConfig(opponent="apex_foundry", map="Helix", seed=6)
        decisions = SliceDecisions(
            practice_focus="defaults",
            team_talk="no heroes. run the default.",
            fallout_post="week 6: held the line. on to week 7.",
        )
        result = run_slice(world, config, decisions)
        cls.world = world
        cls.result = result
        cls.recap = render_recap_md(slice_events(result, world), world)

    def test_canonical_fixture_binds_the_signed_off_cite(self):
        # The verdict in the doc was given against `mem:rook:scrim_w5_choke`
        # binding on the canonical Week-6 fixture. If the selector ever
        # rebinds a different precedent here, the verdict no longer covers
        # the rendered line and a fresh sign-off is owed.
        self.assertTrue(
            self.result.narration.cites,
            "the canonical Week-6 fixture should bind at least one precedent",
        )
        self.assertEqual(
            self.result.narration.cites[0],
            "mem:rook:scrim_w5_choke",
            "the canonical Week-6 fixture must still bind "
            "mem:rook:scrim_w5_choke as the lead precedent — that is the "
            "cite the sign-off verdict covers",
        )

    def test_recap_renders_the_signed_off_line_shape(self):
        # The shape the doc signed off on is:
        #   > **Remembered:** {who}, week {N} — {summary} (`{cite}`)
        # Pin it by regex (literal label + cast alias + numeric week + cite
        # backtick form), against the same recap render the recap.md write
        # path would produce.
        pattern = (
            rf"> \*\*{re.escape(REMEMBERED_SLOT_LABEL)}:\*\* "
            r"Rook, week \d+ — .+ \(`mem:rook:scrim_w5_choke`\)"
        )
        self.assertRegex(
            self.recap,
            pattern,
            "the Remembered slot no longer renders in the shape the "
            "sign-off was given against; re-review the slot before the "
            "next playtest evening",
        )


if __name__ == "__main__":
    unittest.main()
