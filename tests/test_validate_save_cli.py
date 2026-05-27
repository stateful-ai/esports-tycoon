"""``python -m esports_tycoon validate-save`` is the read-only schema-check CLI.

The subcommand is a thin shell over :func:`esports_tycoon.canned.loader.load`:
exit ``0`` and print ``OK`` for a save that loads, exit ``1`` and print one
``<field_path>: <message>`` line for the first :class:`loader.SaveError` it
raises (and the same shape for a missing file). The contract this module pins:

* the packaged canned save validates — proves the wiring through ``--save``'s
  default plus the loader is healthy, and that the happy-path bytes don't drift
  underneath the CLI;
* a positional argument wins over the shared ``--save`` flag — the subcommand's
  natural shape ``validate-save my.yaml`` reads naturally and is the one a
  hand-author of a save reaches for;
* an off-version save trips :class:`loader.SchemaVersionError` and the CLI
  surfaces it as ``schema_version: …`` with exit code ``1`` — the
  ``field_path`` half of the contract;
* a missing path returns exit code ``1`` and a one-line ``<path>: …`` — the
  same exit code as a validation failure, since to the caller "I broke it"
  and "I typo'd the path" are the same outcome.

The tests are offline (no Slack/providers) and mutate a fresh deep copy of the
shipped save written to a tmp file, the same pattern the existing runner CLI
tests use; nothing here writes to the repo's ``saves/``.
"""

from __future__ import annotations

import io
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.__main__ import main as cli_main  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.schema import CURRENT_SCHEMA_VERSION  # noqa: E402


class TestValidateSaveCli(unittest.TestCase):
    """The subcommand's four contract points, pinned end-to-end through ``main``."""

    def setUp(self) -> None:
        # A tmpdir per test so a positional-vs-flag run can't accidentally read
        # another test's leftover file.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def _run(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(list(argv))
        return rc, buf.getvalue()

    def _write_save(self, **overrides) -> pathlib.Path:
        # Take the packaged save by value, splice in the overrides, and write
        # it to the tmpdir. Same shape the runner CLI test uses, so the trip
        # point is exactly one field, not a hand-assembled half-save.
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        raw.update(overrides)
        path = self.tmp / "save.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return path

    def test_default_save_validates_OK(self) -> None:
        # No positional arg, no ``--save`` flag: the CLI falls back to
        # ``loader.DEFAULT_SAVE_PATH`` (the packaged canned save). If the
        # shipped bytes ever drift out of sync with the typed schema, this
        # test goes red — which is exactly the smoke check the subcommand
        # gives a hand-author of a save.
        rc, out = self._run("validate-save")
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "OK")

    def test_positional_path_wins_over_save_flag(self) -> None:
        # ``--save`` is the shared flag, but ``validate-save my.yaml`` is the
        # subcommand's natural shape — and the only one discoverable from
        # ``--help``. Pin both the precedence (positional wins) and the
        # output: the loader's ``schema_version`` gate fires on the positional
        # file, not on whatever ``--save`` points at.
        bad = self._write_save(schema_version=CURRENT_SCHEMA_VERSION + 1)
        rc, out = self._run("--save", str(loader.DEFAULT_SAVE_PATH), "validate-save", str(bad))
        self.assertEqual(rc, 1)
        # ``SchemaVersionError.field_path`` is always ``schema_version`` — the
        # contract the loader docstring promises — and that's the one-line
        # shape the CLI surfaces.
        self.assertTrue(out.startswith("schema_version: "), out)
        self.assertIn(str(bad), out)
        self.assertIn(str(CURRENT_SCHEMA_VERSION + 1), out)

    def test_schema_error_prints_field_path_one_liner(self) -> None:
        # A typed-schema failure (here: ``schema_version`` removed entirely)
        # also surfaces as ``<field_path>: <message>``. The exact field is the
        # loader's promise, not ours — but exit ``1`` and a one-line shape is
        # the CLI's contract, and that's what we pin.
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        raw.pop("schema_version")
        path = self.tmp / "noversion.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        rc, out = self._run("validate-save", str(path))
        self.assertEqual(rc, 1)
        # One terminal line, ``field_path:`` prefix, no Python traceback.
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, f"expected exactly one error line, got {out!r}")
        self.assertIn(": ", lines[0])
        self.assertNotIn("Traceback", out)

    def test_missing_file_exits_nonzero_with_one_line(self) -> None:
        # The loader doesn't catch ``FileNotFoundError`` — the file is read
        # before YAML parsing — so the CLI does, and it surfaces the same
        # one-line shape as a validation failure with the same exit code. From
        # the hand-author's seat, "I broke it" and "I typo'd the path" are the
        # same outcome: ``$? != 0`` and a single readable line.
        missing = self.tmp / "does_not_exist.yaml"
        rc, out = self._run("validate-save", str(missing))
        self.assertEqual(rc, 1)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, f"expected exactly one error line, got {out!r}")
        self.assertTrue(lines[0].startswith("<path>: "), lines[0])
        self.assertIn(str(missing), lines[0])


if __name__ == "__main__":
    unittest.main()
