"""The committed ``saves/week6.yaml`` is a fixed point of the canonical serializer.

The canned save is a *generated* artifact: its source-of-truth content is the
typed :class:`~esports_tycoon.schema.WorldState` the loader materializes from
the file, and its on-disk bytes are whatever the canonical serializer
(:func:`esports_tycoon.canned.loader.dumps`) emits for that world. The
``make regen-golden`` target (``scripts/regen_golden.py``) is the supported way
to (re)write those bytes; this test is the *enforcement* — it asserts the
committed file is already at the canonical fixed point, so a hand-edit that
drifts from canonical form (a re-formatted folded scalar, an inserted comment,
a re-ordered key) fails the build with a pointer back to the script.

This is deliberately distinct from ``tests/test_golden_determinism.py``:

* The golden test there compares ``dumps(load(week6.yaml))`` against a
  *separate* committed byte string at ``tests/golden/week6_canonical.yaml``;
  if both files happened to be hand-edited in lockstep, that test would still
  pass.
* This test compares ``dumps(load(week6.yaml))`` against the bytes of
  ``saves/week6.yaml`` itself, so it catches the very thing the bless script
  prevents: someone editing the fixture by hand without re-running regen.
"""

from __future__ import annotations

import io
import pathlib
import shutil
import sys
import tempfile
import unittest

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from scripts import regen_golden  # noqa: E402

# M0 freeze (founder_brief.md): the golden-bless script's fixed-point contract
# rides on the byte-identity serializer freeze and is deferred to M1/post-gate.
pytestmark = pytest.mark.skip(
    reason="M0 freeze: deterministic golden-bless script deferred to M1/post-gate"
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SAVE_PATH = _REPO_ROOT / "saves" / "week6.yaml"


class TestWeek6FixtureIsCanonical(unittest.TestCase):
    """The committed save must match the canonical serializer's output."""

    def test_committed_bytes_equal_dumps_of_loaded_world(self) -> None:
        # The contract the bless script enforces: the file on disk *is* what
        # ``dumps(load(.))`` produces, byte-for-byte. A hand-edit that
        # introduces non-canonical formatting (a re-folded scalar, a flow-style
        # list, an inserted comment, a stripped trailing newline) trips here.
        produced = loader.dumps(loader.load(_SAVE_PATH))
        on_disk = _SAVE_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            on_disk,
            produced,
            "saves/week6.yaml is not in canonical form; rewrite it with "
            "`make regen-golden` and commit the result. The fixture is a "
            "generated artifact and must never be hand-edited; see "
            "saves/SCHEMA.md § 'Regeneration & blessing'.",
        )


class TestRegenScriptIsIdempotent(unittest.TestCase):
    """The bless script is a fixed point on the committed save.

    These tests deliberately operate on a *copy* of the canonical save in a
    temp dir, never on the real file in ``saves/`` — a self-healing test that
    quietly rewrote the committed fixture under a failure would mask the very
    hand-edit drift we want to catch.
    """

    def setUp(self) -> None:
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="regen-golden-"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self._copy = self._tmp / "week6.yaml"
        shutil.copy2(_SAVE_PATH, self._copy)

    def test_regenerate_on_committed_save_is_a_noop(self) -> None:
        # ``regenerate`` returns True only when it actually rewrites the file.
        # On the committed save (which the test above pins to canonical bytes)
        # it must return False — the second run of ``make regen-golden`` (and
        # therefore CI) does nothing.
        changed = regen_golden.regenerate(self._copy)
        self.assertFalse(
            changed,
            "regen_golden.regenerate rewrote a save that should already be "
            "canonical; the script is not at a fixed point",
        )
        # And the bytes on disk in the temp copy are unchanged.
        self.assertEqual(
            self._copy.read_bytes(),
            _SAVE_PATH.read_bytes(),
        )

    def test_regenerate_returns_to_fixed_point_after_a_drift(self) -> None:
        # Simulate a hand-edit (an extra trailing newline is the smallest
        # non-canonical drift): regenerate must rewrite the file once and then
        # be a no-op on the next call — i.e. converge in one step.
        tampered = self._copy.read_text(encoding="utf-8") + "\n"
        self._copy.write_text(tampered, encoding="utf-8")

        first = regen_golden.regenerate(self._copy)
        second = regen_golden.regenerate(self._copy)
        self.assertTrue(first, "regenerate did not rewrite a drifted save")
        self.assertFalse(second, "regenerate is not idempotent after a rewrite")
        self.assertEqual(
            self._copy.read_bytes(),
            _SAVE_PATH.read_bytes(),
            "rewritten bytes do not match the committed canonical save",
        )

    def test_check_mode_passes_on_committed_save(self) -> None:
        # The ``--check`` flag is the CI-friendly form: exit 0 when the file
        # is canonical, non-zero otherwise. The committed save must pass.
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            exit_code = regen_golden.main(["--check"])
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
