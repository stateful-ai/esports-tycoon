"""Load the hand-authored canned save into a typed :class:`WorldState`.

The single canonical save ships as package data at
``esports_tycoon/canned/data/week6.yaml`` (the cast-lock gate points at the same
file). ``load`` parses it, checks its ``schema_version`` against the version this
build speaks, and validates it into the typed schema; the resulting world
enforces stable cite IDs and the no-dangling-cites grounding contract.
``to_save_dict`` / ``dumps`` are the inverse, used by the round-trip test to
prove the schema is a lossless description of the save.

The save is self-describing (``m0_0_canonical_contract.md`` §3): it carries a
``schema_version``, and :func:`load` turns an older save into the current version
or refuses it with a clear message. Migration is a *stub* in M0.0 — there is one
supported version and no upgrade steps yet — but :func:`migrate` and
:data:`_MIGRATIONS` are the real seam where future upgrades are registered.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Callable, Union

import yaml

from esports_tycoon.canned.canonical import dumps as _canonical_yaml_dumps
from esports_tycoon.schema import CURRENT_SCHEMA_VERSION, WorldState

#: The one canonical canned save for the M0 slice. Resolved as package data so
#: ``load`` works from an installed wheel, not only a source checkout.
DEFAULT_SAVE_PATH = resources.files(__package__) / "data" / "week6.yaml"


class SchemaVersionError(ValueError):
    """A save's ``schema_version`` cannot be loaded by this build.

    A :class:`ValueError` subclass so callers that already catch ``ValueError``
    on a malformed save keep working, while the distinct type still lets a caller
    tell a version mismatch apart from other load failures.
    """


#: A migration step: it takes a save dict at version ``n`` and returns one at
#: version ``n + 1``. The loader stamps the new ``schema_version`` itself, so a
#: step need only reshape the payload.
Migration = Callable[[dict[str, Any]], dict[str, Any]]

#: Upgrade steps keyed by the version they upgrade *from*: ``_MIGRATIONS[n]``
#: turns a version-``n`` save into a version-``n+1`` one. Empty in M0.0 — there
#: is exactly one supported version and nothing to upgrade yet (the contract's
#: "migration is a stub"). This is the seam: when :data:`CURRENT_SCHEMA_VERSION`
#: is bumped, register the matching step here and old saves migrate on load
#: instead of being rejected.
_MIGRATIONS: dict[int, Migration] = {}


def migrate(data: dict[str, Any], from_version: int) -> dict[str, Any]:
    """Upgrade a save dict from ``from_version`` to :data:`CURRENT_SCHEMA_VERSION`.

    Applies each registered step in turn, stamping the bumped ``schema_version``
    after every step, and returns a new dict ready to validate. Raises
    :class:`SchemaVersionError` at the first version with no registered step —
    which, in M0.0, is every version below current.
    """
    data = dict(data)
    version = from_version
    while version < CURRENT_SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise SchemaVersionError(
                f"cannot upgrade save from schema_version {version} to "
                f"{CURRENT_SCHEMA_VERSION}: no migration registered for version {version}"
            )
        data = step(data)
        version += 1
        data["schema_version"] = version
    return data


def _ensure_loadable_version(data: dict[str, Any], source: object) -> dict[str, Any]:
    """Return ``data`` at the current schema version, migrating it if needed.

    The load-time version gate. A save already at :data:`CURRENT_SCHEMA_VERSION`
    passes through untouched; an older one is migrated forward; a missing,
    non-integer, or future version raises :class:`SchemaVersionError` whose
    message names the source and the offending version.
    """
    if "schema_version" not in data:
        raise SchemaVersionError(
            f"{source}: save has no schema_version (this build speaks "
            f"{CURRENT_SCHEMA_VERSION}); it is too old or not an esports-tycoon save"
        )
    version = data["schema_version"]
    # ``bool`` is an ``int`` subclass; a stray ``true`` is not a version.
    if not isinstance(version, int) or isinstance(version, bool):
        raise SchemaVersionError(
            f"{source}: schema_version must be an integer, got {version!r}"
        )
    if version == CURRENT_SCHEMA_VERSION:
        return data
    if version > CURRENT_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{source}: save schema_version {version} is newer than this build "
            f"supports (current {CURRENT_SCHEMA_VERSION}); upgrade esports-tycoon to load it"
        )
    return migrate(data, version)


def load(path: Union[str, Path] = DEFAULT_SAVE_PATH) -> WorldState:
    """Parse a canned save YAML file into a validated :class:`WorldState`.

    Refuses a save whose ``schema_version`` this build cannot read — migrating an
    older one forward where a step is registered, or raising
    :class:`SchemaVersionError` with a clear message otherwise.
    """
    # The default is an ``importlib.resources`` traversable (which exposes
    # ``read_text`` directly and need not be a real filesystem path under a
    # zipped install); a caller-supplied ``str`` goes through ``Path``.
    text = path.read_text(encoding="utf-8") if hasattr(path, "read_text") else Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    data = _ensure_loadable_version(data, path)
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
    """Serialize a :class:`WorldState` back to a canonical YAML save document.

    Delegates to :func:`esports_tycoon.canned.canonical.dumps` so the bytes are a
    fixed point: ``load(dumps(load(week6.yaml)))`` re-dumps to the identical
    bytes (the round-trip golden in ``tests/test_golden_determinism.py``).
    """
    return _canonical_yaml_dumps(to_save_dict(world))
