"""End-to-end wiring: one runner invocation exercises load → resolve → recap.

The acceptance bar for ``m0_0_canonical_contract.md`` (Rebind map) is that the
resolver, the slice runner, and the recap reader share **one** canonical
``WorldState`` — and that the runner CLI is the single seam where that contract
is exercised against the real, shipped ``week6.yaml``. This module pins that
seam:

* :class:`TestRunnerCliEndToEnd` invokes ``python -m esports_tycoon.runner``'s
  ``main()`` against the packaged canned save, with no fixtures and no
  monkey-patched world. One process load-validates the save (which is what
  reads ``schema_version``), the resolver runs, and the recap reader writes
  the three artifacts (``events.jsonl``, ``recap.md``, ``feed.snapshot.html``).
  Re-running with the same flags lands on the same content-addressed
  ``runs/<slice_id>/`` and the bytes don't drift.
* :class:`TestRunnerCliSchemaVersionGate` proves the load path the CLI uses is
  the *gated* one: an off-version save fed to the same ``main()`` is rejected
  with a typed ``SchemaVersionError``, not silently loaded. This is what makes
  the "in one runner invocation reading ``schema_version``" half of the
  acceptance line real instead of decorative.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.runner.__main__ import main as runner_main  # noqa: E402
from esports_tycoon.runner.recap import (  # noqa: E402
    EVENTS_FILENAME,
    FEED_FILENAME,
    RECAP_FILENAME,
)
from esports_tycoon.schema import CURRENT_SCHEMA_VERSION  # noqa: E402


class TestRunnerCliEndToEnd(unittest.TestCase):
    """One ``python -m esports_tycoon.runner`` invocation runs all three seams."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.runs_dir = pathlib.Path(self._tmp.name)

    def _invoke(self, *extra: str) -> int:
        # No --save: defaults to ``loader.DEFAULT_SAVE_PATH`` (the packaged,
        # shipped week6.yaml), which is what the acceptance line means by "real
        # week6.yaml". The runs dir is sandboxed so parallel test runs and the
        # repo's ``runs/`` are untouched.
        return runner_main(["--runs-dir", str(self.runs_dir), *extra])

    def test_one_invocation_writes_all_three_artifacts(self):
        # The CLI's job is to thread the canonical world through resolver →
        # slice runner → recap reader in a single process. Success is the three
        # artifact files in one ``runs/<slice_id>/`` folder.
        self.assertEqual(self._invoke(), 0)
        runs = list(self.runs_dir.glob("wk6-*"))
        self.assertEqual(len(runs), 1, "expected exactly one runs/<slice_id>/ folder")
        names = sorted(p.name for p in runs[0].iterdir())
        self.assertEqual(names, sorted([EVENTS_FILENAME, FEED_FILENAME, RECAP_FILENAME]))

    def test_recap_is_authored_against_the_canonical_world(self):
        # The canonical schema is the source of identity in the recap (team
        # name, opponent name resolved via rival id, opponent's archetype). A
        # draft-typed reader would either miss these or render IDs verbatim;
        # asserting them by *value* pins the rebind.
        self.assertEqual(self._invoke(), 0)
        world = loader.load()
        run_dir = next(self.runs_dir.glob("wk6-*"))
        recap = (run_dir / RECAP_FILENAME).read_text(encoding="utf-8")
        opponent = next(r for r in world.rivals if r.id == "apex_foundry")
        self.assertIn(world.save.team.name, recap)
        self.assertIn(opponent.name, recap)
        self.assertIn(opponent.archetype, recap)

    def test_same_flags_replay_byte_identical(self):
        # Determinism is the contract behind "same seed ⇒ identical recap": two
        # invocations land on the same slice_id and produce identical bytes for
        # all three artifacts. The second invocation overwrites the first, so
        # we copy the first set out before re-running.
        self.assertEqual(self._invoke(), 0)
        run_dir = next(self.runs_dir.glob("wk6-*"))
        first = {p.name: p.read_bytes() for p in run_dir.iterdir()}
        self.assertEqual(self._invoke(), 0)
        run_dir2 = next(self.runs_dir.glob("wk6-*"))
        self.assertEqual(run_dir2.name, run_dir.name, "slice_id drifted across runs")
        second = {p.name: p.read_bytes() for p in run_dir2.iterdir()}
        self.assertEqual(first, second)

    def test_decisions_thread_through_to_the_recap(self):
        # The two open-text moments (the captain's pre-match talk and the
        # manager's post-match Chirper line) are the player's only free-text
        # surface, and the recap renders them verbatim. If the decisions don't
        # reach the renderer, the rebind is broken.
        talk = "no heroes. run the default."
        post = "week 6: held the line. on to week 7."
        self.assertEqual(
            self._invoke("--team-talk", talk, "--fallout", post),
            0,
        )
        run_dir = next(self.runs_dir.glob("wk6-*"))
        recap = (run_dir / RECAP_FILENAME).read_text(encoding="utf-8")
        feed = (run_dir / FEED_FILENAME).read_text(encoding="utf-8")
        self.assertIn(talk, recap)
        self.assertIn(post, feed)


class TestRunnerCliSchemaVersionGate(unittest.TestCase):
    """The CLI's load path is the gated one: schema_version is checked, not skipped."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.runs_dir = self.tmp / "runs"

    def _write_save(self, **overrides) -> pathlib.Path:
        # Take the shipped save by value, splice in the override, and write it
        # somewhere the CLI's ``--save`` flag can pick it up. Keeps the gate
        # test honest: we mutate one field on the same bytes the happy path
        # uses, instead of hand-assembling a half-save.
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        raw.update(overrides)
        path = self.tmp / "save.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return path

    def test_future_version_save_is_rejected_by_the_cli(self):
        # A schema_version this build cannot read trips the loader's gate, and
        # the CLI surfaces it as a typed ``SchemaVersionError`` — never as a
        # successful run with silently-degraded data.
        save = self._write_save(schema_version=CURRENT_SCHEMA_VERSION + 1)
        with self.assertRaises(loader.SchemaVersionError):
            runner_main(["--save", str(save), "--runs-dir", str(self.runs_dir)])
        # The gate fires before any artifact is written.
        self.assertFalse(self.runs_dir.exists())

    def test_missing_version_save_is_rejected_by_the_cli(self):
        # A save with no schema_version at all is rejected the same way: the
        # CLI does not fall back to "assume current".
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        raw.pop("schema_version")
        path = self.tmp / "save.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with self.assertRaises(loader.SchemaVersionError):
            runner_main(["--save", str(path), "--runs-dir", str(self.runs_dir)])
        self.assertFalse(self.runs_dir.exists())


if __name__ == "__main__":
    unittest.main()
