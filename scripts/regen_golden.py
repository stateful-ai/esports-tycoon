"""Re-emit ``saves/week6.yaml`` in canonical byte form.

The canned save is a *generated* artifact: its source-of-truth content is the
typed :class:`~esports_tycoon.schema.WorldState` that
:func:`~esports_tycoon.canned.loader.load` materializes from the file, and its
on-disk bytes are whatever :func:`~esports_tycoon.canned.loader.dumps` (i.e.
the canonical serializer in :mod:`esports_tycoon.canned.canonical`) emits for
that world. This script is the one supported way to (re)write those bytes —
the "bless" path that ties the fixture to the canonical serializer rather than
to a human's formatting choices.

Workflow:

* read ``saves/week6.yaml`` and validate it into a ``WorldState``, applying
  the shape, cite-id, and referential-integrity checks the loader runs;
* serialize the validated world via the canonical serializer; and
* overwrite ``saves/week6.yaml`` with the result *only when the bytes
  differ*, so a clean re-bless is observable (the file's mtime moves only
  on an actual change).

The operation is idempotent: ``dumps(load(canonical_bytes)) == canonical_bytes``
is a fixed point of the canonical serializer (see ``saves/SCHEMA.md`` §
**Byte-identity normalization** and ``tests/test_golden_determinism.py``), so
``make regen-golden`` run twice in a row writes nothing the second time. CI
guards the inverse — ``tests/test_regen_golden.py`` asserts that the committed
file is already at the fixed point, so a hand-edit that drifts from the
canonical form fails the build with a pointer back to this script.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

# Run-as-script support: when invoked via ``python scripts/regen_golden.py``,
# the repo root is not on ``sys.path``. Add it before importing the package.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from esports_tycoon.canned import loader  # noqa: E402

#: Filesystem path to the canonical save in the source tree. The loader's
#: ``DEFAULT_SAVE_PATH`` is an ``importlib.resources`` traversable that need
#: not be a writable filesystem path under a zipped install; this script is a
#: developer-tree tool, so resolve the target relative to the repo root.
SAVE_PATH: pathlib.Path = _REPO_ROOT / "saves" / "week6.yaml"


def regenerate(save_path: pathlib.Path = SAVE_PATH) -> bool:
    """Rewrite ``save_path`` with canonical bytes, returning ``True`` on change.

    Reads the file, loads it through the full validating loader (shape, cite
    ids, referential integrity), and writes the canonical serializer's output
    back to the same path. The file is touched only when the canonical bytes
    differ from what's already on disk, so a no-op regen leaves the file —
    and its mtime — untouched.
    """
    world = loader.load(save_path)
    canonical = loader.dumps(world)
    if save_path.read_text(encoding="utf-8") == canonical:
        return False
    save_path.write_text(canonical, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not write; exit non-zero if the file is not already in "
            "canonical form. Intended for use in CI / pre-commit."
        ),
    )
    args = parser.parse_args(argv)

    world = loader.load(SAVE_PATH)
    canonical = loader.dumps(world)
    on_disk = SAVE_PATH.read_text(encoding="utf-8")

    if on_disk == canonical:
        print(f"{SAVE_PATH}: already canonical (no-op)")
        return 0

    if args.check:
        print(
            f"{SAVE_PATH}: not in canonical form; run `make regen-golden` to "
            "rewrite it.",
            file=sys.stderr,
        )
        return 1

    SAVE_PATH.write_text(canonical, encoding="utf-8")
    print(f"{SAVE_PATH}: rewrote {len(canonical)} bytes from the canonical serializer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
