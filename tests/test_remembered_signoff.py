"""The pre-playtest sign-off on the rendered "remembered me" line is durable.

This test pins the sign-off artifact ``docs/playtest_signoff_remembered_line.md``
so the three things it carries cannot quietly drift apart from the test suite:

1. The verdict itself — a ``GO`` decision recorded on the canonical Week-6
   fixture's rendered ``Remembered:`` slot.
2. The copy fix that was filed alongside the GO (so it does not get lost as
   the next sharpening of the slot).
3. The rendered shape the verdict was given against — if the slot's render
   format changes, the sign-off must be re-given. The pin asserts the
   slot still renders as ``> **Remembered:** {who}, week {N} — {summary}
   (`{cite}`)`` against the canonical save, so a silent format change to
   the line invalidates this test (and the doc that depends on it).

Together those three halves make the sign-off self-falsifying: a regression
on the verdict text, the filed fix, or the rendered line each fails this
test, which is the contract the doc itself promises in its "Where this
decision is pinned" section.
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
    """The recorded sign-off is the durable proof the design review happened."""

    @classmethod
    def setUpClass(cls):
        cls.text = _SIGNOFF_DOC.read_text(encoding="utf-8")

    def test_signoff_doc_exists(self):
        self.assertTrue(
            _SIGNOFF_DOC.exists(),
            "docs/playtest_signoff_remembered_line.md is the canonical "
            "pre-playtest sign-off artifact for the bound precedent slot",
        )

    def test_records_a_go_verdict(self):
        # The acceptance criterion is asymmetric: GO greenlights the playtest
        # evening, no-go opens a re-review. The doc must state which branch
        # was taken, in unambiguous prose, so a reader can answer the question
        # "was the slot signed off?" from this file alone.
        self.assertRegex(
            self.text,
            r"\*\*Verdict\.\*\*\s+\*\*GO\.\*\*",
            "the sign-off doc must record a **Verdict.** **GO.** line",
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
