"""The batched approve/reject pass behaves as one atomic, content-bound decision."""

import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.cast_lock import approval, spec  # noqa: E402


class TestApproval(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save = self.tmp / "week6.yaml"
        self.doc = self.tmp / "tone.md"
        shutil.copy(spec.DEFAULT_SAVE_PATH, self.save)
        shutil.copy(spec.DEFAULT_DOC_PATH, self.doc)
        self.record = self.tmp / "approval.yaml"

    def build(self):
        return approval.build_batch(save_path=self.save, doc_path=self.doc)

    def test_real_batch_is_approvable(self):
        self.assertTrue(self.build().approvable)

    def test_missing_doc_raises(self):
        self.doc.unlink()
        with self.assertRaises(FileNotFoundError):
            self.build()

    def test_approve_writes_bound_record(self):
        batch = self.build()
        rec = approval.record_decision(
            batch, "approve", approver="founder@example.com", record_path=self.record
        )
        self.assertEqual(rec["decision"], "approve")
        self.assertEqual(rec["batch_digest"], batch.digest)
        loaded = approval.load_record(self.record)
        status = approval.approval_status(batch, loaded)
        self.assertEqual(status["status"], "approved")
        self.assertTrue(status["approved"])

    def test_one_decision_field_over_whole_batch(self):
        # Atomicity: a single decision + digest covering both files, no per-item keys.
        batch = self.build()
        rec = approval.record_decision(
            batch, "approve", approver="founder@example.com", record_path=self.record
        )
        self.assertIn("decision", rec)
        self.assertEqual(set(rec["files"]), {"doc", "save"})
        # acceptance is a flat pass/fail snapshot, not an approvable list of items
        self.assertTrue(all(isinstance(v, bool) for v in rec["acceptance"].values()))

    def test_reject_requires_reason(self):
        batch = self.build()
        with self.assertRaises(ValueError):
            approval.record_decision(batch, "reject", approver="f", record_path=self.record)
        rec = approval.record_decision(
            batch, "reject", approver="f", reason="cast too pleasant", record_path=self.record
        )
        status = approval.approval_status(batch, approval.load_record(self.record))
        self.assertEqual(status["status"], "rejected")
        self.assertFalse(status["approved"])

    def test_cannot_approve_invalid_batch(self):
        # Break the save so validation fails, then attempt to approve.
        text = self.save.read_text(encoding="utf-8")
        self.save.write_text(text.replace("tone: dry-mockumentary", "tone: earnest"), encoding="utf-8")
        batch = self.build()
        self.assertFalse(batch.approvable)
        with self.assertRaises(ValueError):
            approval.record_decision(
                batch, "approve", approver="founder", record_path=self.record
            )

    def test_invalid_decision_value(self):
        batch = self.build()
        with self.assertRaises(ValueError):
            approval.record_decision(batch, "maybe", approver="f", record_path=self.record)

    def test_empty_approver(self):
        batch = self.build()
        with self.assertRaises(ValueError):
            approval.record_decision(batch, "approve", approver="   ", record_path=self.record)

    def test_edit_after_approval_goes_stale(self):
        batch = self.build()
        approval.record_decision(
            batch, "approve", approver="founder", record_path=self.record
        )
        # Edit either file -> the recorded approval no longer binds.
        self.save.write_text(self.save.read_text(encoding="utf-8") + "\n# tweak\n", encoding="utf-8")
        new_batch = self.build()
        status = approval.approval_status(new_batch, approval.load_record(self.record))
        self.assertEqual(status["status"], "stale")
        self.assertFalse(status["approved"])

    def test_unreviewed_when_no_record(self):
        status = approval.approval_status(self.build(), approval.load_record(self.record))
        self.assertEqual(status["status"], "unreviewed")

    def test_digest_changes_with_either_file(self):
        d0 = approval.batch_digest(self.save, self.doc)
        self.doc.write_text(self.doc.read_text(encoding="utf-8") + "\nedit\n", encoding="utf-8")
        d1 = approval.batch_digest(self.save, self.doc)
        self.assertNotEqual(d0, d1)


if __name__ == "__main__":
    unittest.main()
