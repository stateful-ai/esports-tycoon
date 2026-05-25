"""The load-time schema_version gate and its migration stub.

This is the M0.0 canonical-contract clause "the save is self-describing ... the
loader refuses an unknown major version (migration is a stub)"
(``m0_0_canonical_contract.md`` §3), made into tests, plus the contract's
fail-closed requirement that a wrong version must be rejected, not silently
loaded (Risks → "negative fixtures ... wrong version that must fail closed").

Two halves:

* The **gate** rejects a save this build cannot read — missing, non-integer, or
  newer-than-current ``schema_version`` — with a clear, sourced message.
* The **migration seam** is real, not decoration: with an upgrade step
  registered, an older save migrates forward on load and lands at the current
  version. M0.0 ships no steps, so today an older save fails closed; this proves
  the machinery the moment a step exists.
"""

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.schema import CURRENT_SCHEMA_VERSION  # noqa: E402


def _raw() -> dict:
    """A fresh parse of the canonical save (a valid, current-version save)."""
    return yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))


class _SaveFileTest(unittest.TestCase):
    """Base: write save dicts to a real temp file and load through ``load``."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def _write(self, raw: dict) -> pathlib.Path:
        path = pathlib.Path(self._dir.name) / "save.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return path


class TestCurrentVersionLoads(_SaveFileTest):
    """The happy path: a save at the current version loads unchanged."""

    def test_canonical_save_is_at_current_version(self):
        # The shipped save is authored at exactly the version this build speaks,
        # so the gate is a no-op on the common path.
        self.assertEqual(_raw()["schema_version"], CURRENT_SCHEMA_VERSION)

    def test_current_version_passes_the_gate_untouched(self):
        # A current-version save dict comes back out of the gate as the very same
        # object — no copy, no migration on the hot path.
        data = _raw()
        self.assertIs(loader._ensure_loadable_version(data, "<test>"), data)

    def test_load_succeeds_on_current_version(self):
        world = loader.load(self._write(_raw()))
        self.assertEqual(world.schema_version, CURRENT_SCHEMA_VERSION)


class TestGateRejects(_SaveFileTest):
    """The gate refuses a version this build cannot read, with a clear message."""

    def test_future_version_is_rejected(self):
        raw = {**_raw(), "schema_version": CURRENT_SCHEMA_VERSION + 1}
        with self.assertRaises(loader.SchemaVersionError) as cm:
            loader.load(self._write(raw))
        msg = str(cm.exception)
        self.assertIn(str(CURRENT_SCHEMA_VERSION + 1), msg)
        self.assertIn("newer", msg)
        self.assertIn("schema_version", msg)

    def test_missing_version_is_rejected(self):
        raw = _raw()
        raw.pop("schema_version")
        with self.assertRaises(loader.SchemaVersionError) as cm:
            loader.load(self._write(raw))
        self.assertIn("schema_version", str(cm.exception))

    def test_non_integer_version_is_rejected(self):
        for bad in ("0", 1.0, None, [0]):
            with self.subTest(version=bad):
                raw = {**_raw(), "schema_version": bad}
                with self.assertRaises(loader.SchemaVersionError) as cm:
                    loader.load(self._write(raw))
                self.assertIn("integer", str(cm.exception))

    def test_boolean_version_is_rejected(self):
        # ``bool`` is an ``int`` subclass; a stray ``true`` must not slip through
        # as "version 1".
        with self.assertRaises(loader.SchemaVersionError) as cm:
            loader._ensure_loadable_version({"schema_version": True}, "<test>")
        self.assertIn("integer", str(cm.exception))

    def test_error_is_a_valueerror(self):
        # Back-compat: callers that catch ValueError on a bad save keep working.
        self.assertTrue(issubclass(loader.SchemaVersionError, ValueError))

    def test_message_names_the_source(self):
        path = self._write({**_raw(), "schema_version": CURRENT_SCHEMA_VERSION + 1})
        with self.assertRaises(loader.SchemaVersionError) as cm:
            loader.load(path)
        self.assertIn(str(path), str(cm.exception))


class TestOlderVersionFailsClosedWithoutAMigration(_SaveFileTest):
    """Absent a registered step, an older save is rejected — never silent-loaded."""

    def test_old_version_with_no_migration_is_rejected(self):
        # Simulate a future build (current = 1) that forgot to register the 0->1
        # step: the version-0 save must fail closed, not load as if current.
        with mock.patch.object(loader, "CURRENT_SCHEMA_VERSION", 1), mock.patch.dict(
            loader._MIGRATIONS, {}, clear=True
        ):
            with self.assertRaises(loader.SchemaVersionError) as cm:
                loader.load(self._write({**_raw(), "schema_version": 0}))
        msg = str(cm.exception)
        self.assertIn("no migration", msg)
        self.assertIn("0", msg)

    def test_migrate_raises_on_a_gap_in_the_chain(self):
        # A chain missing an intermediate step stops at the gap rather than
        # skipping it.
        with mock.patch.object(loader, "CURRENT_SCHEMA_VERSION", 2), mock.patch.dict(
            loader._MIGRATIONS, {0: lambda d: d}, clear=True
        ):
            with self.assertRaises(loader.SchemaVersionError) as cm:
                loader.migrate({"schema_version": 0}, 0)
            self.assertIn("version 1", str(cm.exception))


class TestMigrationSeamUpgradesOnLoad(_SaveFileTest):
    """With steps registered, an older save migrates forward and lands current."""

    def test_load_migrates_an_old_save_through_the_chain(self):
        # Patch in a two-step chain (current = 2) and load the version-0 canonical
        # save: both steps must run in order, the version is stamped each step,
        # and the world lands at the new current.
        calls: list[int] = []

        def step0(data: dict) -> dict:
            calls.append(0)
            return {**data, "seed": data["seed"] + 1}

        def step1(data: dict) -> dict:
            calls.append(1)
            return {**data, "seed": data["seed"] + 10}

        base_seed = _raw()["seed"]
        with mock.patch.object(loader, "CURRENT_SCHEMA_VERSION", 2), mock.patch.dict(
            loader._MIGRATIONS, {0: step0, 1: step1}, clear=True
        ):
            world = loader.load(self._write({**_raw(), "schema_version": 0}))

        self.assertEqual(calls, [0, 1])  # ran in order, no step skipped
        self.assertEqual(world.schema_version, 2)  # stamped to the new current
        self.assertEqual(world.seed, base_seed + 11)  # both steps' effects applied

    def test_migrate_stamps_the_version_after_each_step(self):
        # ``migrate`` owns the version stamp; a step that ignores schema_version
        # still produces a dict at the target version.
        with mock.patch.object(loader, "CURRENT_SCHEMA_VERSION", 1), mock.patch.dict(
            loader._MIGRATIONS, {0: lambda d: dict(d)}, clear=True
        ):
            out = loader.migrate({"schema_version": 0, "k": "v"}, 0)
        self.assertEqual(out["schema_version"], 1)
        self.assertEqual(out["k"], "v")

    def test_migrate_does_not_mutate_its_input(self):
        with mock.patch.object(loader, "CURRENT_SCHEMA_VERSION", 1), mock.patch.dict(
            loader._MIGRATIONS, {0: lambda d: {**d, "seed": 99}}, clear=True
        ):
            original = {"schema_version": 0, "seed": 1}
            loader.migrate(original, 0)
            self.assertEqual(original, {"schema_version": 0, "seed": 1})


if __name__ == "__main__":
    unittest.main()
