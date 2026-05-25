"""Load the hand-authored canned save into a typed :class:`WorldState`.

The single canonical save lives at ``saves/week6.yaml`` (the cast-lock gate
points at the same file). ``load`` parses it and validates it into the typed
schema; the resulting world enforces stable cite IDs and the no-dangling-cites
grounding contract. ``to_save_dict`` / ``dumps`` are the inverse, used by the
round-trip test to prove the schema is a lossless description of the save.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

import yaml

from esports_tycoon.schema import WorldState

# esports_tycoon/canned/loader.py -> esports_tycoon/canned -> esports_tycoon -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The one canonical canned save for the M0 slice.
DEFAULT_SAVE_PATH = _REPO_ROOT / "saves" / "week6.yaml"


def load(path: Union[str, Path] = DEFAULT_SAVE_PATH) -> WorldState:
    """Parse a canned save YAML file into a validated :class:`WorldState`."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return WorldState.model_validate(data)


def to_save_dict(world: WorldState) -> dict[str, Any]:
    """Render a :class:`WorldState` back to the plain save-shaped dict.

    Uses the YAML aliases (``with`` not ``with_``) and drops every field still
    at its default, so the result is byte-for-byte comparable to
    ``yaml.safe_load`` of the original file.

    ``exclude_defaults`` (not ``exclude_none``) is deliberate. The canned save is
    hand-authored in the natural style of omitting empty collections and absent
    optionals rather than spelling them as ``[]``/``null``. ``exclude_none`` only
    drops ``None``, so an omitted empty collection (e.g. a memory entry with no
    ``tags``) would load to ``[]`` and then be *re-injected* on dump, silently
    breaking the round-trip. ``exclude_defaults`` keeps the dump aligned with the
    save's convention: a value omitted in the YAML stays omitted on the way out.
    """
    return world.model_dump(mode="json", by_alias=True, exclude_defaults=True)


def dumps(world: WorldState) -> str:
    """Serialize a :class:`WorldState` back to a YAML save document."""
    return yaml.safe_dump(to_save_dict(world), sort_keys=False, allow_unicode=True)
