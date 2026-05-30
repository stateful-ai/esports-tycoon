"""End-to-end wiring for the ``validate-save`` CLI subcommand.

The check authors of hand-edited saves reach for is ``python -m esports_tycoon
validate-save <path>``. The handler in :mod:`esports_tycoon.__main__` is the
one seam this test pins: it must

* exit 0 with ``OK`` on the packaged canonical save,
* exit 1 with a one-line ``<field_path>: <message>`` for every typed
  :class:`loader.SaveError` subclass (YAML parse failure, unknown
  ``schema_version``, typed-schema rejection, *and* — when ``--strict`` is
  set — a dangling cross-entity id reference),
* be strictly shape-only by default: a save that passes the typed schema but
  references an undefined unit must validate clean without ``--strict`` and
  fail only when the flag is on.

The negative-fixture suite (``tests/test_referential_integrity.py``) pins the
loader's typed errors; this suite pins that the CLI surfaces them exactly the
way the docstring of :mod:`esports_tycoon.__main__` promises.
"""

from __future__ import annotations

import io
import pathlib
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.__main__ import main  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "integrity"


def _run(*argv: str):
    """Invoke ``python -m esports_tycoon`` in-process and capture its stdout.

    In-process so the test reads the same code path the entry point does — no
    subprocess shells out to a possibly-different interpreter — and we get the
    actual exit code and the printed line in one round-trip.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


class TestValidateSaveCli(unittest.TestCase):
    """Pin the four user-facing contracts of ``validate-save``."""

    def test_canonical_save_validates_ok(self) -> None:
        # No positional argument -> falls back to ``--save`` / the packaged
        # canned save. That's the smoke test every CI run is implicitly doing,
        # so a regression in the loader's wiring surfaces here first.
        code, out = _run("validate-save")
        self.assertEqual(code, 0, msg=out)
        self.assertEqual(out.strip(), "OK")

    def test_canonical_save_validates_ok_strict(self) -> None:
        # The canned save is integrity-clean (re-asserted in
        # tests/test_referential_integrity.py) so ``--strict`` is no stricter
        # in practice. Pinning this here guards against the strict path
        # silently failing the good case — a regression that would otherwise
        # only show up the next time someone added a hand-authored save.
        code, out = _run("validate-save", "--strict")
        self.assertEqual(code, 0, msg=out)
        self.assertEqual(out.strip(), "OK")

    def test_corrupt_yaml_fixture_exits_nonzero_with_field_path(self) -> None:
        # ``corrupt.yaml`` is the negative fixture for the YAML parse stage —
        # the very first contract the loader enforces. The CLI must surface
        # the typed ``SaveYamlError`` as a single line starting with the
        # ``<yaml>`` field path the negative-fixture suite asserts on.
        code, out = _run("validate-save", str(FIXTURES / "corrupt.yaml"))
        self.assertEqual(code, 1)
        first_line = out.splitlines()[0]
        self.assertTrue(
            first_line.startswith("<yaml>: "),
            msg=f"expected '<yaml>: ...' header, got {first_line!r}",
        )

    def test_dangling_actor_passes_non_strict_fails_strict(self) -> None:
        # The contract that gives ``--strict`` its reason to exist. The
        # dangling-actor fixture is shape-valid (every cite resolves, every
        # field has the right type) but names a unit no entity defines. The
        # default mode must accept it; ``--strict`` must reject it with the
        # path the referential-integrity checker reports.
        path = str(FIXTURES / "dangling_actor.yaml")

        ok_code, ok_out = _run("validate-save", path)
        self.assertEqual(ok_code, 0, msg=ok_out)
        self.assertEqual(ok_out.strip(), "OK")

        bad_code, bad_out = _run("validate-save", "--strict", path)
        self.assertEqual(bad_code, 1)
        first_line = bad_out.splitlines()[0]
        # The fixture's first unresolved reference is the second actor on
        # rook's debut memory; the referential-integrity error's field path
        # names exactly that location.
        self.assertTrue(
            first_line.startswith(
                "players[0=rook].memory_log[0=mem:rook:debut].actors[1]: "
            ),
            msg=f"unexpected strict-mode header line: {first_line!r}",
        )

    def test_missing_path_exits_nonzero_with_clean_one_liner(self) -> None:
        # A typo'd path is the most common authoring mistake. The handler
        # catches ``FileNotFoundError`` so the user sees a one-line ``<path>:
        # ...`` message and exit 1 — the same exit code every other validation
        # failure uses — instead of a Python traceback.
        bogus = pathlib.Path(__file__).resolve().parent / "fixtures" / "_does_not_exist.yaml"
        code, out = _run("validate-save", str(bogus))
        self.assertEqual(code, 1)
        first_line = out.splitlines()[0]
        self.assertTrue(
            first_line.startswith("<path>: "),
            msg=f"expected '<path>: ...' header, got {first_line!r}",
        )


if __name__ == "__main__":
    unittest.main()
