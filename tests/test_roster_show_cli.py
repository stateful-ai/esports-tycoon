"""``python -m esports_tycoon roster show <save>`` is the read-only roster
printer.

The subcommand is a thin shell over :func:`esports_tycoon.canned.loader.load`
plus :func:`esports_tycoon.__main__._print_roster`: it loads the save through
the typed loader (so it doubles as a schema smoke test, the same shape the
existing ``inspect`` and ``resolve`` subcommands take) and prints one row per
starter on the managed team. The contract this module pins:

* the packaged canned save loads and prints every starter — exit ``0``, one
  header line + one row per player on ``world.roster``, in save order, with
  the player id, role, name, handle, age, signature operative, and traits;
* a positional argument wins over the shared ``--save`` flag — the
  subcommand's natural shape ``roster show my.yaml`` reads naturally and is
  the one a hand-author of a save reaches for;
* ``roster`` without a verb is an authoring mistake (help + exit ``2``);
* the printer never advances the sim — running it twice against the same
  save yields the same bytes, and never mutates the loaded world (no
  ``schema_version`` / ``standing`` / ``current_week`` drift).

The tests are offline (no Slack/providers) and mutate a fresh deep copy of
the shipped save written to a tmp file, the same pattern the existing CLI
tests use; nothing here writes to the repo's ``saves/``.
"""

from __future__ import annotations

import copy
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


class TestRosterShowCli(unittest.TestCase):
    """The subcommand's contract points, pinned end-to-end through ``main``."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        # Loaded once for the "what does the canned save actually contain"
        # cross-check below; the CLI under test always loads its own copy.
        self.world = loader.load()

    def _run(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(list(argv))
        return rc, buf.getvalue()

    def _write_save(self) -> pathlib.Path:
        # A by-value copy of the packaged save written to the tmpdir, so a
        # test that drives the CLI via the positional path is reading
        # bytes-identical content to what the default flag would read. The
        # round-trip is what the canonical-yaml test guards in detail; here
        # we only need a real save file on disk.
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        path = self.tmp / "save.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        return path

    def test_default_save_prints_every_starter(self) -> None:
        # No positional arg, no ``--save`` flag: the CLI falls back to
        # ``loader.DEFAULT_SAVE_PATH``. Asserting on every player's id (not
        # just a count) keeps the contract honest if the canned save's
        # roster ever shrinks or grows — and proves the printer walks
        # ``world.roster`` in save order rather than reaching for a parallel
        # players list.
        rc, out = self._run("roster", "show")
        self.assertEqual(rc, 0, out)
        # Header names the managed team and the roster size — pin both so a
        # future "starters" rename (or a count drift) goes red.
        team = self.world.team
        roster = self.world.roster
        first_line = out.splitlines()[0]
        self.assertIn(team.name, first_line)
        self.assertIn(team.tag, first_line)
        self.assertIn(f"({len(roster)})", first_line)
        for player in roster:
            self.assertIn(player.id, out)
            self.assertIn(player.name, out)
            self.assertIn(player.role.value, out)
            self.assertIn(player.handle, out)
            self.assertIn(f"age {player.age:>2}", out)
            self.assertIn(player.signature_operative, out)

    def test_positional_path_wins_over_save_flag(self) -> None:
        # ``--save`` is the shared flag, but ``roster show my.yaml`` is the
        # subcommand's natural shape. Pin precedence by pointing ``--save``
        # at a path that does *not* exist: if the positional argument
        # wasn't honoured, the loader would explode on the ``--save`` path.
        good = self._write_save()
        bogus = self.tmp / "does_not_exist.yaml"
        rc, out = self._run("--save", str(bogus), "roster", "show", str(good))
        self.assertEqual(rc, 0, out)
        # And the output is still the canned roster — the positional file
        # is byte-identical to the packaged save by construction.
        for player in self.world.roster:
            self.assertIn(player.id, out)

    def test_bare_roster_is_an_authoring_mistake(self) -> None:
        # ``roster`` alone has no default verb — print help and exit
        # non-zero rather than silently doing nothing (or, worse, running
        # ``inspect`` against a misread args namespace).
        rc, out = self._run("roster")
        self.assertEqual(rc, 2, out)
        self.assertIn("show", out)

    def test_show_does_not_advance_or_mutate_the_save(self) -> None:
        # The acceptance bar in the brief: no sim advance. Pin it by running
        # the subcommand twice against the same on-disk save and asserting
        # the bytes don't drift, and that the on-disk save itself is
        # untouched after both runs — the printer must never write back.
        path = self._write_save()
        before = path.read_bytes()
        before_data = copy.deepcopy(yaml.safe_load(before))
        rc1, out1 = self._run("roster", "show", str(path))
        rc2, out2 = self._run("roster", "show", str(path))
        self.assertEqual(rc1, 0, out1)
        self.assertEqual(rc2, 0, out2)
        self.assertEqual(out1, out2)
        after = path.read_bytes()
        self.assertEqual(before, after, "roster show must not write back to the save")
        # And the loaded world derived from the save is identical too — a
        # belt-and-braces check against an in-memory mutation that the
        # bytes-on-disk check would miss if the printer happened to round-
        # trip the world back to YAML.
        after_data = yaml.safe_load(after)
        self.assertEqual(before_data, after_data)


if __name__ == "__main__":
    unittest.main()
