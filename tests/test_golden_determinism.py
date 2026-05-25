"""Golden test that locks the whole week6 ``load → resolve → round-trip`` path.

This is the single golden the M0.0 canonical-contract milestone calls for
(``docs`` / ``m0_0_canonical_contract.md``: "lock the whole
load→resolve→round-trip path with a single golden test"). It is deliberately
distinct from the other suites:

* ``test_resolver_determinism.py`` proves the resolver is *internally
  consistent* and *byte-identical run-to-run within one process*. It does not
  pin the actual output, so a change to a tuning constant (which moves every
  outcome the same way) sails through it.
* ``test_loader.py`` proves the save round-trips *losslessly against itself*.
  It does not pin the canonical bytes, so a change to the serializer's style
  could pass while silently re-formatting every save.

A *golden* closes both gaps: it commits the known-good resolve output and the
known-good canonical save bytes, so **any drift** — a resolver retune, a
serializer reformat, a schema field reorder — trips this test with a reviewable
diff. The committed goldens are verified behaviour: the broader suites above
assert that behaviour is correct; this test freezes it.

When a change to the resolver or serializer is *intended*, regenerate the
goldens with ``UPDATE_GOLDEN=1 python -m pytest tests/test_golden_determinism.py``
and review the resulting diff before committing it.
"""

import json
import os
import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.schema import Decisions, WhyRecord, WorldState  # noqa: E402

# The one fixed fixture + seed this golden pins. tidewater/seed 5 is chosen
# because it exercises a broad cross-section of the resolver in a single record:
# a win that swings, with clutch and ace key moments, both carriers and tilters,
# and a full spread of morale deltas. Drift in any of those branches moves the
# bytes and trips the golden.
_FIXTURE = Decisions(
    opponent="tidewater",
    map="Helix",
    practice_focus="defaults",
    tactical_stance="default",
)
_SEED = 5

_GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"
_RESOLVE_GOLDEN = _GOLDEN_DIR / "week6_resolve.json"
_CANONICAL_GOLDEN = _GOLDEN_DIR / "week6_canonical.yaml"

# Set UPDATE_GOLDEN=1 to rewrite the committed goldens after an *intended*
# change; review the diff before committing it.
_UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _canonical_record(record: WhyRecord) -> str:
    """Canonical, diff-stable bytes for a resolved :class:`WhyRecord`.

    ``sort_keys`` makes the form independent of incidental dict ordering, so the
    golden trips on a *value* change (the drift that matters) rather than on a
    map's key order. The trailing newline keeps the committed file POSIX-clean.
    """
    return json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _read_or_write_golden(path: pathlib.Path, produced: str) -> str:
    """Return the committed golden for ``path``, (re)writing it under UPDATE_GOLDEN.

    Outside update mode a missing golden is a hard failure — a golden that
    silently materializes on first run would never detect drift.
    """
    if _UPDATE:
        _GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(produced, encoding="utf-8")
    if not path.exists():
        raise AssertionError(
            f"missing golden {path}; regenerate with UPDATE_GOLDEN=1 and commit it"
        )
    return path.read_text(encoding="utf-8")


class TestGoldenDeterminism(unittest.TestCase):
    """One golden over load → resolve → round-trip; fails on any drift."""

    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()  # loads week6.yaml

    # --- resolve -------------------------------------------------------------- #
    def test_resolve_is_byte_identical_across_two_runs(self):
        # The same fixture + seed, resolved twice, is byte-for-byte identical.
        first = _canonical_record(resolver.run(self.world, _FIXTURE, _SEED))
        second = _canonical_record(resolver.run(self.world, _FIXTURE, _SEED))
        self.assertEqual(first, second, "resolver output is not byte-identical run-to-run")

    def test_resolve_matches_committed_golden(self):
        # ...and matches the committed known-good bytes, so a retune is caught.
        produced = _canonical_record(resolver.run(self.world, _FIXTURE, _SEED))
        golden = _read_or_write_golden(_RESOLVE_GOLDEN, produced)
        self.assertEqual(
            produced,
            golden,
            "resolve output drifted from the committed golden; if intended, "
            "regenerate with UPDATE_GOLDEN=1 and review the diff",
        )

    # --- round-trip ----------------------------------------------------------- #
    def test_round_trip_is_lossless_against_the_save(self):
        # dump(load(week6.yaml)) reproduces the parsed save exactly: the typed
        # dump drops nothing and invents nothing.
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(loader.to_save_dict(self.world), raw)

    def test_round_trip_normalizes_to_committed_canonical_bytes(self):
        # The canonical serializer's exact output is pinned, so a reformat is
        # caught even when it leaves the parsed data unchanged.
        canonical = loader.dumps(self.world)
        golden = _read_or_write_golden(_CANONICAL_GOLDEN, canonical)
        self.assertEqual(
            canonical,
            golden,
            "canonical save bytes drifted from the committed golden; if intended, "
            "regenerate with UPDATE_GOLDEN=1 and review the diff",
        )

    def test_round_trip_is_an_idempotent_fixed_point(self):
        # dump(load(x)) normalizes back to x: reloading the canonical bytes and
        # re-dumping yields the identical bytes, and the reloaded world is equal.
        canonical = loader.dumps(self.world)
        world2 = WorldState.model_validate(yaml.safe_load(canonical))
        self.assertEqual(world2, self.world)
        self.assertEqual(loader.dumps(world2), canonical)


if __name__ == "__main__":
    unittest.main()
