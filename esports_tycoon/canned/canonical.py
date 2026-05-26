"""Canonical YAML serializer for the canned save.

The output is a deterministic byte form: dump → load → dump is a fixed point on
any save the schema accepts. The contract is what makes the round-trip golden
test (``tests/test_golden_determinism.py``) trip on serializer drift, and it is
what lets a future migration diff two saves with ``diff`` instead of a custom
walker.

The full, human-facing contract — key order, float repr, trailing newline,
unicode, plus the block-style and ``exclude_defaults`` rules — lives in
``saves/SCHEMA.md`` under the **Byte-identity normalization** section
(:data:`CONTRACT_DOC_ANCHOR`). This module is the single seam that emits
those bytes; if a rule changes, update SCHEMA.md and the canonical golden
in the same diff. Two properties keep the bytes stable:

* **Stable key order.** Keys are emitted in the order the input dict iterates
  them. For the canned save that is the Pydantic schema's field declaration
  order (see :mod:`esports_tycoon.schema`) — same order on every dump, on every
  machine, regardless of how PyYAML happens to hash dict keys today.

* **Fixed float formatting.** Floats go through :func:`repr` (Python's shortest
  round-trip form, stable across CPython releases), with NaN / ±Inf forced to
  YAML's canonical ``.nan`` / ``.inf`` / ``-.inf``. PyYAML's default
  representer pads scientific-notation mantissas (``1e-05`` becomes ``1.0e-05``)
  in a way that has shifted between point releases; pinning the format here
  immunises the golden from that drift. There are no floats in week6 today,
  but the contract still has to hold the moment one appears.

Block style is forced (no ``[...]`` / ``{...}``), Unicode is allowed (the save
carries em-dashes and accented names), and the document always ends in a single
trailing newline so the file is POSIX-clean.
"""

from __future__ import annotations

import math
from typing import Any

import yaml

#: Anchor pointing at the human-facing byte-identity contract in
#: ``saves/SCHEMA.md``. Pinned here so a test (and a future reader) can follow
#: the code → docs jump without grepping; if the section heading ever moves,
#: this constant and the golden test that references it are the single seam
#: to update.
CONTRACT_DOC_ANCHOR = "Byte-identity normalization"


class _CanonicalDumper(yaml.SafeDumper):
    """SafeDumper subclass that owns this module's representer conventions.

    Subclassed (rather than mutating ``yaml.SafeDumper``'s global representer
    table) so callers elsewhere that still use plain ``yaml.safe_dump`` are
    unaffected by the canonical float convention.
    """


def _represent_float(dumper: yaml.Dumper, value: float) -> yaml.ScalarNode:
    """Emit a float in its shortest round-trip form, with canonical specials."""
    if math.isnan(value):
        text = ".nan"
    elif math.isinf(value):
        text = "-.inf" if value < 0 else ".inf"
    else:
        # ``repr`` gives the shortest string that ``float()`` parses back to the
        # same bit pattern (PEP 3101 / dtoa); it is the same on every CPython
        # build this project supports.
        text = repr(value)
        # YAML 1.1's implicit float resolver requires a dot in the mantissa
        # (``1e-05`` would otherwise emit with an explicit ``!!float`` tag).
        # ``repr(1e-5) == '1e-05'`` and ``repr(1e20) == '1e+20'`` both miss the
        # dot, so splice ``.0`` into the mantissa.
        if "." not in text:
            for marker in ("e", "E"):
                if marker in text:
                    mantissa, sep, exp = text.partition(marker)
                    text = f"{mantissa}.0{sep}{exp}"
                    break
            else:
                text += ".0"
    return dumper.represent_scalar("tag:yaml.org,2002:float", text)


_CanonicalDumper.add_representer(float, _represent_float)


def dumps(data: Any) -> str:
    """Serialize ``data`` to canonical YAML text.

    See the module docstring for the format contract. The result always ends in
    exactly one ``\\n``, regardless of PyYAML's defaults.
    """
    text = yaml.dump(
        data,
        Dumper=_CanonicalDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    # ``yaml.dump`` already appends ``\n`` on every supported PyYAML, but pin
    # the invariant here so a future PyYAML change cannot silently drop it.
    if not text.endswith("\n"):
        text += "\n"
    return text
