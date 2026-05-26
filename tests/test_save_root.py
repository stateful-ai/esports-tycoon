"""The canonical save root is ``saves/`` — locked, single-rooted, package data.

The on-disk canned save lives at exactly one place — ``saves/week6.yaml`` — and
every loader, CLI, and validator in the codebase resolves it through the same
``importlib.resources`` handle. The acceptance bar for the save-root lock is:

* the loader's :data:`DEFAULT_SAVE_PATH` is the file at ``saves/week6.yaml``;
* the cast-lock gate resolves to the same bytes (no ``canned/`` vs ``saves/``
  split); and
* a fresh ``loader.load()`` against the locked path returns a typed world that
  also clears the load-time referential-integrity gate.

These tests guard those three properties so a future change that introduces a
parallel save location — or quietly points one entry point at a different file
— fails here.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.cast_lock import spec  # noqa: E402
from esports_tycoon.schema import WorldState  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCKED_SAVE_PATH = REPO_ROOT / "saves" / "week6.yaml"


class TestCanonicalSaveRootIsLocked(unittest.TestCase):
    """The canonical save lives at exactly one documented location."""

    def test_locked_save_file_exists(self) -> None:
        # The whole point of locking the path: the file is physically there.
        self.assertTrue(
            LOCKED_SAVE_PATH.is_file(),
            f"canonical save missing: {LOCKED_SAVE_PATH}",
        )

    def test_loader_default_is_the_locked_path(self) -> None:
        # ``DEFAULT_SAVE_PATH`` is an ``importlib.resources`` traversable, not
        # necessarily a ``Path``; compare bytes (the contract callers care
        # about) and the on-disk name, not the object type.
        default_bytes = loader.DEFAULT_SAVE_PATH.read_bytes()
        self.assertEqual(default_bytes, LOCKED_SAVE_PATH.read_bytes())
        self.assertEqual(loader.DEFAULT_SAVE_PATH.name, "week6.yaml")

    def test_cast_lock_resolves_to_the_same_bytes(self) -> None:
        # The cast-lock gate and the loader must agree on which file is the
        # canonical save — otherwise the gate could approve one file while the
        # game runs on another.
        self.assertEqual(
            spec.DEFAULT_SAVE_PATH.read_bytes(),
            loader.DEFAULT_SAVE_PATH.read_bytes(),
        )

    def test_no_legacy_canned_data_directory(self) -> None:
        # ``esports_tycoon/canned/data/`` was the old, parallel save root.
        # Locking ``saves/`` means it must not come back: if it does, every
        # tool that hard-codes a path is one regression away from the split
        # the lock is meant to prevent.
        legacy = REPO_ROOT / "esports_tycoon" / "canned" / "data"
        self.assertFalse(
            legacy.exists(),
            f"legacy save root must not coexist with saves/: {legacy}",
        )


class TestLoaderLoadsFromTheLockedPath(unittest.TestCase):
    """A real load through the locked path produces a clean, typed world."""

    def test_default_load_returns_validated_worldstate(self) -> None:
        # Loads through the default — which IS the locked path. The world
        # validates shape, the referential-integrity gate passes, and the
        # acceptance-bar fingerprints (5 starters, locked tone) survive.
        world = loader.load()
        self.assertIsInstance(world, WorldState)
        self.assertEqual(len(world.players), 5)
        self.assertEqual(world.save.tone, "dry-mockumentary")

    def test_explicit_locked_path_load_matches_default(self) -> None:
        # Passing the locked path explicitly must produce the same world as
        # the default, so anything that records the path verbatim (an
        # approval record, a CI artifact) never diverges from the loader.
        explicit = loader.load(LOCKED_SAVE_PATH)
        default = loader.load()
        self.assertEqual(explicit, default)


if __name__ == "__main__":
    unittest.main()
