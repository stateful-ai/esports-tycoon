"""``python -m esports_tycoon roster export`` is the read-only roster dumper.

The subcommand is a thin shell over :func:`esports_tycoon.canned.loader.load`
plus :func:`esports_tycoon.__main__._format_roster_csv` /
``_format_roster_json``: it loads the save through the typed loader (so it
doubles as a schema smoke test, the same shape ``inspect``/``resolve``/
``validate-save``/``roster show`` take) and emits one record per starter on
the managed team in either CSV (default) or JSON, written to ``--out`` or
stdout. The contract this module pins:

* ``--format csv`` (the default) emits a header row plus one row per starter
  on ``world.roster`` in save order, with the fixed
  :data:`_ROSTER_EXPORT_FIELDS` columns, and the bytes round-trip through
  ``csv.reader`` to recover the same player ids, roles, and traits the typed
  schema yields — proving the export is faithful to the loaded world rather
  than to a hand-shaped string;
* ``--format json`` emits a JSON array whose records carry the same fields
  with native types (``age`` an int, ``traits`` a list), so a downstream tool
  that reads JSON gets the shape the schema names rather than a re-stringified
  CSV;
* ``--out FILE`` writes the same bytes a stdout run would print, so a piped
  ``roster export > file`` and ``roster export --out file`` are
  interchangeable, and the file ends with a single trailing newline;
* the export never advances the sim — two runs against the same save yield
  byte-identical output, and the loaded world's ``schema_version`` /
  ``current_week`` / roster ids are unchanged after the call.

The tests are offline (no Slack/providers) and run against the packaged
canned save through the same ``main()`` entry point a user invokes; nothing
here writes to the repo's ``saves/``.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.__main__ import (  # noqa: E402
    _ROSTER_EXPORT_FIELDS,
    _TRAITS_CSV_DELIM,
    main as cli_main,
)
from esports_tycoon.canned import loader  # noqa: E402


class TestRosterExportCli(unittest.TestCase):
    """The subcommand's contract points, pinned end-to-end through ``main``."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        # Loaded once for the "what does the canned save actually contain"
        # cross-check; the CLI under test always loads its own copy.
        self.world = loader.load()

    def _run(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(list(argv))
        return rc, buf.getvalue()

    def test_csv_default_matches_loaded_roster(self) -> None:
        """``roster export`` (csv by default) round-trips through ``csv.reader``.

        Header is the pinned column tuple; each subsequent row carries one
        starter's projection — ``id`` first, ``traits`` last as a
        ``|``-joined cell. Roles and traits read back to the same enum values
        and list contents the typed schema yields, which is what makes this
        an export *of the loaded world* rather than an export of a string we
        happened to print.
        """
        rc, out = self._run("roster", "export")
        self.assertEqual(rc, 0)
        rows = list(csv.reader(io.StringIO(out)))
        self.assertEqual(rows[0], list(_ROSTER_EXPORT_FIELDS))
        self.assertEqual(len(rows) - 1, len(self.world.roster))
        for row, player in zip(rows[1:], self.world.roster):
            self.assertEqual(row[0], player.id)
            self.assertEqual(row[1], player.name)
            self.assertEqual(row[2], player.handle)
            self.assertEqual(row[3], player.role.value)
            self.assertEqual(row[4], str(player.age))
            self.assertEqual(row[5], player.signature_operative)
            self.assertEqual(
                row[6].split(_TRAITS_CSV_DELIM) if row[6] else [],
                list(player.traits),
            )

    def test_json_records_carry_native_types(self) -> None:
        """``--format json`` emits records with the schema's native shape.

        ``traits`` is a list (not a ``|``-joined string), ``age`` is an int
        (not a stringified one), and the array order matches save order — the
        downstream JSON consumer should get the typed shape, not a
        re-stringified CSV.
        """
        rc, out = self._run("roster", "export", "--format", "json")
        self.assertEqual(rc, 0)
        records = json.loads(out)
        self.assertEqual(len(records), len(self.world.roster))
        for record, player in zip(records, self.world.roster):
            self.assertEqual(record["id"], player.id)
            self.assertEqual(record["name"], player.name)
            self.assertEqual(record["role"], player.role.value)
            self.assertIsInstance(record["age"], int)
            self.assertEqual(record["age"], player.age)
            self.assertIsInstance(record["traits"], list)
            self.assertEqual(record["traits"], list(player.traits))
        # Output ends in a single trailing newline (house convention).
        self.assertTrue(out.endswith("\n"))
        self.assertFalse(out.endswith("\n\n"))

    def test_out_file_matches_stdout_bytes(self) -> None:
        """``--out FILE`` writes the same bytes a stdout run would print.

        Piping is the common case; ``--out`` is the affordance. The two have
        to be interchangeable or one is silently authoring a different
        artefact than the other. Checked for both formats so a future
        format-specific bug (e.g. a Windows ``\\r\\n`` translation) trips
        this rather than landing in a CI tail somewhere.
        """
        for fmt in ("csv", "json"):
            with self.subTest(fmt=fmt):
                _, stdout_bytes = self._run("roster", "export", "--format", fmt)
                out_path = self.tmp / f"roster.{fmt}"
                rc, captured = self._run(
                    "roster", "export", "--format", fmt, "--out", str(out_path)
                )
                self.assertEqual(rc, 0)
                # ``--out`` is silent on stdout — nothing is double-printed.
                self.assertEqual(captured, "")
                self.assertEqual(
                    out_path.read_text(encoding="utf-8"), stdout_bytes
                )

    def test_export_is_pure_and_deterministic(self) -> None:
        """Two runs against the same save yield byte-identical output.

        The export is a read of the loaded world (no sim advance, no
        mutation), so calling ``main()`` twice must produce the same bytes
        and leave a freshly-loaded world's identifying fields unchanged. A
        regression that wired the export through anything that mutated the
        world would trip this without needing to inspect the diff.
        """
        _, first = self._run("roster", "export")
        _, second = self._run("roster", "export")
        self.assertEqual(first, second)
        again = loader.load()
        self.assertEqual(again.schema_version, self.world.schema_version)
        self.assertEqual(
            again.save.season.current_week, self.world.save.season.current_week
        )
        self.assertEqual(
            [p.id for p in again.roster], [p.id for p in self.world.roster]
        )


if __name__ == "__main__":
    unittest.main()
