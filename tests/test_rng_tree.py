"""RNG determinism tests — the *invariant* every sim-side test depends on.

If these fail, the sim is not reproducible and the whole project premise
breaks. Treat any failure here as a stop-the-world bug.
"""

from __future__ import annotations

import numpy as np
import pytest

from esports_sim.rng import RngTree


def test_same_seed_same_labels_same_stream() -> None:
    a = RngTree(42).derive("match", 1, "round", 3)
    b = RngTree(42).derive("match", 1, "round", 3)
    assert np.array_equal(a.integers(0, 1_000_000, size=100), b.integers(0, 1_000_000, size=100))


def test_different_seeds_differ() -> None:
    a = RngTree(42).derive("match", 1)
    b = RngTree(43).derive("match", 1)
    assert not np.array_equal(a.integers(0, 1_000_000, size=50), b.integers(0, 1_000_000, size=50))


def test_different_label_paths_differ() -> None:
    root = RngTree(42)
    a = root.derive("match", 1, "round", 3)
    b = root.derive("match", 1, "round", 4)
    assert not np.array_equal(a.integers(0, 1_000_000, size=50), b.integers(0, 1_000_000, size=50))


def test_label_path_prefix_does_not_collide() -> None:
    """(\"ab\", \"c\") must not collide with (\"a\", \"bc\")."""
    root = RngTree(42)
    a = root.derive("ab", "c")
    b = root.derive("a", "bc")
    assert a.integers(0, 1_000_000) != b.integers(0, 1_000_000)


def test_int_and_str_labels_differ() -> None:
    """1 and \"1\" currently map the same (both stringified). Document
    that and assert — if we ever change it, this test forces a decision."""
    root = RngTree(42)
    a = root.derive("x", 1)
    b = root.derive("x", "1")
    assert a.integers(0, 1_000_000) == b.integers(0, 1_000_000)


def test_derive_seed_matches_generator() -> None:
    tree = RngTree(7)
    seed = tree.derive_seed("foo", "bar")
    gen = tree.derive("foo", "bar")
    ref = np.random.Generator(np.random.PCG64(seed))
    assert gen.integers(0, 1_000_000) == ref.integers(0, 1_000_000)


def test_negative_root_seed_rejected() -> None:
    with pytest.raises(ValueError):
        RngTree(-1)
