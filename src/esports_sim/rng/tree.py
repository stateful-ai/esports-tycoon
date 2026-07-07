"""Deterministic hierarchical RNG.

Every stochastic decision in the sim should `derive` an RNG from a labelled
path. Two matches with the same root seed and the same label path produce
byte-identical random streams — which is what makes the event log
reproducible.

Usage:

    root = RngTree(root_seed=42)
    match_rng = root.derive("match", "nexus_vs_vanguard")
    round_rng = root.derive("match", "nexus_vs_vanguard", "round", 3)
    shot_rng = root.derive(
        "match", "nexus_vs_vanguard", "round", 3, "player", "phantom", "shot", 17,
    )

Labels may be str or int. Ordering and content both matter.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np


def _labels_to_seed(root_seed: int, labels: tuple[Any, ...]) -> int:
    """Derive a 64-bit seed from (root_seed, labels) via blake2b.

    Using a cryptographic hash gives us near-uniform distribution and a
    low-collision probability across arbitrary label paths.
    """

    h = hashlib.blake2b(digest_size=8)
    h.update(root_seed.to_bytes(8, "big", signed=False))
    for label in labels:
        h.update(b"\x00")  # null-byte separator so ("a", "bc") != ("ab", "c")
        h.update(str(label).encode("utf-8"))
    return int.from_bytes(h.digest(), "big", signed=False)


class RngTree:
    """Entry point for deterministic RNG derivation.

    Immutable. Does not hold state — every `derive` call computes a fresh
    seed and returns a fresh `numpy.random.Generator`. Callers keep a
    handle to the generator they want to draw from.
    """

    __slots__ = ("_root_seed",)

    def __init__(self, root_seed: int):
        if root_seed < 0:
            raise ValueError("root_seed must be non-negative")
        self._root_seed = root_seed & ((1 << 64) - 1)

    @property
    def root_seed(self) -> int:
        return self._root_seed

    def derive(self, *labels: Any) -> np.random.Generator:
        """Return a numpy Generator seeded deterministically from `labels`.

        Calling `.derive()` with no labels returns the root RNG — useful for
        a top-level stream, but most callers should pass labels.
        """
        seed = _labels_to_seed(self._root_seed, tuple(labels))
        # PCG64 is the numpy default and is deterministic across versions.
        return np.random.Generator(np.random.PCG64(seed))

    def derive_seed(self, *labels: Any) -> int:
        """Return just the 64-bit integer seed — useful for logging /
        reconstructing external RNGs."""
        return _labels_to_seed(self._root_seed, tuple(labels))

    def __repr__(self) -> str:
        return f"RngTree(root_seed={self._root_seed})"
