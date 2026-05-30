"""``python -m esports_tycoon scenario template`` is the save-scaffolding CLI.

The subcommand emits the bytes of :data:`esports_tycoon.scenario.TEMPLATE` —
a minimal valid save YAML — to stdout (default) or to ``--out FILE``. It is
the author-facing scaffold: an author runs it, edits the placeholders, and
``python -m esports_tycoon validate-save`` confirms the result still loads.
This module pins three contracts:

* the bytes the CLI emits *are* a save the typed loader accepts — so the
  template can never drift away from the schema without this test going red;
* the bytes are byte-stable across calls (the same template every time, no
  env leakage, no timestamping) — so committing the output of a fresh run
  produces no diff against a previous run;
* the placeholder shape names every required top-level section
  (``schema_version``, ``seed``, ``save``, ``players``, ``rivals``,
  ``last_week``) — the structural contract a hand-author relies on the
  template to teach.

Offline-only (no Slack/providers); each test writes to a fresh tmpdir.
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

from esports_tycoon import scenario  # noqa: E402
from esports_tycoon.__main__ import main as cli_main  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402


class TestScenarioTemplateCli(unittest.TestCase):
    """Three contract points for the scaffolding CLI."""

    def setUp(self) -> None:
        # A fresh tmpdir per test so the ``--out`` test can't accidentally
        # read another test's leftover file.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def _run(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(list(argv))
        return rc, buf.getvalue()

    def test_template_emitted_is_a_valid_save(self) -> None:
        # The bytes the CLI writes — via ``--out`` so we exercise the same
        # disk-write path a real author uses — must round-trip through the
        # typed loader without raising. If a future schema bump leaves a
        # required field off the template, this test goes red and points the
        # author at the placeholder they need to add.
        out = self.tmp / "scaffold.yaml"
        rc, stdout = self._run("scenario", "template", "--out", str(out))
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, "", "stdout should be empty when --out is set")
        self.assertTrue(out.is_file(), f"expected scaffold at {out}")
        # The full schema-check path: parse + version gate + typed model +
        # referential integrity. Any failure raises a ``loader.SaveError``.
        world = loader.load(out)
        # The placeholder ids surface as real entities in the loaded world —
        # a sanity check that the wiring through ``--out`` isn't writing an
        # empty / truncated file.
        self.assertEqual(world.save.id, "my_save")
        self.assertGreaterEqual(len(world.players), 1)
        self.assertGreaterEqual(len(world.rivals), 1)

    def test_stdout_bytes_are_byte_stable_across_calls(self) -> None:
        # Two back-to-back runs (no flag, no env tweak) must produce the
        # identical bytes. The template is a frozen literal by design — this
        # test is what keeps a future refactor from sneaking in an
        # f-string'd date or a randomized id and silently breaking
        # "commit the output and diff" workflows for authors.
        rc1, out1 = self._run("scenario", "template")
        rc2, out2 = self._run("scenario", "template")
        self.assertEqual(rc1, 0)
        self.assertEqual(rc2, 0)
        self.assertEqual(out1, out2, "scenario template output must be byte-stable")
        # And the stdout bytes are exactly the module-level constant — no
        # ``print``'s extra newline, no encoding-only differences. This
        # pins the stdout-vs-``--out`` contract: piping the CLI output
        # into a file is byte-equivalent to using ``--out``.
        self.assertEqual(out1, scenario.TEMPLATE)

    def test_template_names_every_required_top_level_section(self) -> None:
        # The template's purpose is to teach the save's required shape. Parse
        # it as YAML and assert each required top-level key the schema demands
        # is named. If the schema grows a new required top-level field, this
        # test goes red until the template (and its placeholder comment) is
        # updated alongside the schema change.
        rc, out = self._run("scenario", "template")
        self.assertEqual(rc, 0)
        data = yaml.safe_load(out)
        self.assertIsInstance(data, dict)
        required_top_level = {
            "schema_version",
            "seed",
            "save",
            "players",
            "rivals",
            "last_week",
        }
        missing = required_top_level - set(data.keys())
        self.assertFalse(
            missing,
            f"template is missing required top-level sections: {sorted(missing)}",
        )
        # ``save`` and ``last_week`` carry nested required structure the
        # author has to fill in; spot-check the named placeholders so a
        # silent shape regression (e.g. ``season`` dropped from the
        # template) trips here, not at the loader.
        self.assertIn("season", data["save"])
        self.assertIn("team", data["save"])
        self.assertIn("standing", data["save"]["team"])
        self.assertIn("scoreline", data["last_week"])
        self.assertIn("maps", data["last_week"]["scoreline"])


if __name__ == "__main__":
    unittest.main()
