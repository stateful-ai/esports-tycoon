"""The seed-in-save contract: the save owns the RNG seed, and it drives replay.

This is the M0.0 canonical-contract clause "the save carries ... the seed"
(``m0_0_canonical_contract.md`` §2) plus "determinism is anchored in the save"
(§6), made into tests. It is deliberately distinct from the neighbouring suites:

* ``test_resolver_determinism.py`` proves the resolver is reproducible *for a
  seed it is handed*. It never asks where that seed comes from.
* ``test_golden_determinism.py`` pins the canonical bytes and one resolve, but
  with an explicit fixture seed.

This suite proves the missing link: the seed is a required, persisted field of
the world schema, it survives the byte-identical round-trip, and — the headline
acceptance criterion — **loading week6.yaml twice and resolving the same fixture
gives identical results**, because the resolver draws its randomness from the
save's own seed by default.
"""

import pathlib
import sys
import unittest

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.schema import Decisions, WorldState  # noqa: E402

# A representative fixture: a beatable rival on the must-win map. The contract is
# about the seed's provenance, not this particular matchup, so any valid fixture
# would do.
_FIXTURE = Decisions(opponent="northwind", map="Helix")


def _raw() -> dict:
    return yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))


class TestSchemaPersistsSeed(unittest.TestCase):
    """The world schema carries the seed, and the save round-trips it losslessly."""

    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()

    def test_seed_is_loaded_from_the_save(self):
        # week6.yaml authors the seed; the loaded world exposes it as a field.
        self.assertEqual(self.world.seed, 6)
        self.assertEqual(self.world.seed, _raw()["seed"])

    def test_seed_is_required(self):
        # A save with no seed is not a valid save: the field has no default, so the
        # load fails loudly rather than inventing one.
        raw = _raw()
        raw.pop("seed")
        with self.assertRaises(ValidationError):
            WorldState.model_validate(raw)

    def test_seed_must_be_a_non_negative_int(self):
        for bad in (-1, "six", 1.5):
            with self.subTest(seed=bad), self.assertRaises(ValidationError):
                WorldState.model_validate({**_raw(), "seed": bad})

    def test_seed_survives_the_canonical_round_trip(self):
        # Being required (no default), the seed is never excluded from the dump, so
        # it is always in the canonical bytes and reloads to the same value.
        self.assertEqual(loader.to_save_dict(self.world)["seed"], self.world.seed)
        reloaded = WorldState.model_validate(yaml.safe_load(loader.dumps(self.world)))
        self.assertEqual(reloaded.seed, self.world.seed)
        self.assertEqual(reloaded, self.world)


class TestSeedDrivesReplay(unittest.TestCase):
    """Determinism is anchored in the save: the seed in the file drives the match."""

    def test_loading_twice_and_resolving_is_identical(self):
        # The headline acceptance criterion. Two independent loads of week6.yaml,
        # the same fixture, no explicit seed: byte-for-byte the same WhyRecord,
        # because both runs draw from the save's own seed.
        world_a = loader.load()
        world_b = loader.load()
        self.assertIsNot(world_a, world_b)  # genuinely two separate loads
        rec_a = resolver.run(world_a, _FIXTURE)
        rec_b = resolver.run(world_b, _FIXTURE)
        self.assertEqual(rec_a, rec_b)
        # And the seed it replayed from is the save's, not some caller default.
        self.assertEqual(rec_a.seed, world_a.seed)

    def test_resolver_defaults_to_the_save_seed(self):
        # Omitting the seed is identical to passing the save's seed explicitly.
        world = loader.load()
        self.assertEqual(
            resolver.run(world, _FIXTURE),
            resolver.run(world, _FIXTURE, world.seed),
        )

    def test_explicit_seed_overrides_the_save_seed(self):
        # An explicit seed is honoured over the save's: threaded in, echoed back,
        # and (the save seed being one point in the distribution) it changes the
        # outcome.
        world = loader.load()
        default = resolver.run(world, _FIXTURE)
        self.assertEqual(default.seed, world.seed)
        alt = resolver.run(world, _FIXTURE, world.seed + 1)
        self.assertEqual(alt.seed, world.seed + 1)
        self.assertNotEqual(default, alt)

    def test_two_saves_with_different_seeds_replay_differently(self):
        # The seed-in-save is what makes a save bit-reproducible: change only the
        # seed in the file and the same fixture replays to a different week.
        base = _raw()
        world_six = WorldState.model_validate({**base, "seed": 6})
        world_seven = WorldState.model_validate({**base, "seed": 7})
        self.assertNotEqual(
            resolver.run(world_six, _FIXTURE),
            resolver.run(world_seven, _FIXTURE),
        )


if __name__ == "__main__":
    unittest.main()
