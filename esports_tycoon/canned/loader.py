"""Load the hand-authored canned save into a typed :class:`WorldState`.

The single canonical save ships as package data at ``saves/week6.yaml`` — the
one documented save root, with no ``canned/`` vs ``saves/`` split. The cast-lock
gate (:mod:`esports_tycoon.cast_lock.spec`), the runner / web / vLLM-demo CLIs,
and this loader all resolve the file through the same :func:`importlib.resources`
handle, so a source checkout and an installed wheel read the same bytes.
``load`` parses it, checks its ``schema_version`` against the version this build
speaks, and validates it into the typed schema; the resulting world enforces
stable cite IDs and the no-dangling-cites grounding contract. ``to_save_dict`` /
``dumps`` are the inverse, used by the round-trip test to prove the schema is a
lossless description of the save.

The save's on-disk shape — every field, with a one-line description — is
documented in :data:`SCHEMA_DOC_PATH` (``saves/SCHEMA.md``). That page is the
human-facing companion to the typed models in :mod:`esports_tycoon.schema`: if
you are reaching for a field name, types, or default, that's the table to read.

The save is self-describing (``m0_0_canonical_contract.md`` §3): it carries a
``schema_version``, and :func:`load` turns an older save into the current version
or refuses it with a clear message. Migration is a *stub* in M0.0 — there is one
supported version and no upgrade steps yet — but :func:`migrate` and
:data:`_MIGRATIONS` are the real seam where future upgrades are registered.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Union

import yaml

from esports_tycoon.canned.canonical import dumps as _canonical_yaml_dumps
from esports_tycoon.schema import CURRENT_SCHEMA_VERSION, WorldState

#: The one canonical canned save for the M0 slice. Resolved as package data
#: from the ``saves`` package so ``load`` works from an installed wheel, not
#: only a source checkout. This is the single documented save root; every CLI
#: and validator in the codebase reads through this constant rather than
#: rebuilding the path, so the location moves in one place if it ever moves.
DEFAULT_SAVE_PATH = resources.files("saves") / "week6.yaml"

#: The human-facing save-schema reference (``saves/SCHEMA.md``): every field
#: this loader accepts, with a one-line description and the load-time
#: invariants. Pinned here so the loader is the single seam between the typed
#: schema and the documentation about it — if SCHEMA.md ever moves, this
#: pointer is the one place to update, and ``tests/test_schema_doc.py`` follows
#: it. Lives in the repo (not as installed package data); resolved relative to
#: the source file so it works in a source checkout, and is left ``None`` in
#: contexts (e.g. a wheel install with no repo) where the file is absent.
def _resolve_schema_doc_path() -> Path | None:
    candidate = Path(__file__).resolve().parents[2] / "saves" / "SCHEMA.md"
    return candidate if candidate.is_file() else None


SCHEMA_DOC_PATH: Path | None = _resolve_schema_doc_path()


class SchemaVersionError(ValueError):
    """A save's ``schema_version`` cannot be loaded by this build.

    A :class:`ValueError` subclass so callers that already catch ``ValueError``
    on a malformed save keep working, while the distinct type still lets a caller
    tell a version mismatch apart from other load failures.
    """


@dataclass(frozen=True)
class RefIssue:
    """One unresolved id reference: where it lives, what was missing, what was allowed.

    The fields are formatted into :class:`SaveReferentialIntegrityError`'s
    message so the failure is actionable on its own — the author can take the
    path straight to the offending line, see the id that didn't resolve, and the
    categories of id that would have.
    """

    path: str
    missing_id: str
    expected: tuple[str, ...]


class SaveReferentialIntegrityError(ValueError):
    """A save references one or more ids that no entity in the save defines.

    Distinct from :class:`SchemaVersionError` (a version this build can't read)
    and from :class:`pydantic.ValidationError` (a shape this schema doesn't
    accept): this is a save that *parsed and shape-validated* but whose internal
    cross-references — a relationship pointing at no player, a clash citing an
    unknown rival star, a Chirper post whose ``reply_to`` names no other post —
    fail to resolve. A :class:`ValueError` subclass so callers that broadly
    catch ``ValueError`` on a bad save keep working; the distinct type lets a
    caller tell a referential failure apart from the other load failures and
    inspect :attr:`issues` programmatically.
    """

    def __init__(self, source: object, issues: list[RefIssue]) -> None:
        self.source = source
        self.issues = tuple(issues)
        bullets = "\n".join(
            f"  - {issue.path}: id {issue.missing_id!r} is not defined "
            f"(expected one of: {', '.join(issue.expected)})"
            for issue in issues
        )
        super().__init__(
            f"{source}: save references unknown ids "
            f"({len(issues)} unresolved):\n{bullets}"
        )


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


def check_referential_integrity(
    world: WorldState, source: object = "<world>"
) -> None:
    """Raise :class:`SaveReferentialIntegrityError` if any id reference dangles.

    The typed schema enforces *shape* — that fields exist, are the right type,
    and that memory cite IDs (``mem:<player>:<slug>``) all resolve. This pass
    enforces the *cross-entity* contract the schema deliberately leaves open:
    that every reference to a unit (player or rival star), a team or rival
    org, or an in-feed Chirper post resolves to an entity actually defined in
    the same save. Catches the typo a human author is most likely to make —
    ``vexx`` for ``vex``, ``apex`` for ``apex_foundry`` — at load time, with a
    sourced, actionable message, instead of letting it surface later as a
    ``KeyError`` or, worse, silently wrong narration.

    Run after :meth:`WorldState.model_validate`, so the world object is already
    shape-valid. The checker collects *every* unresolved reference and raises
    once, so an author sees the full picture in a single round-trip rather
    than fixing typos one stack-trace at a time.
    """
    players = {p.id for p in world.players}
    rival_orgs = {r.id for r in world.rivals}
    rival_stars = {r.star.id for r in world.rivals}
    team_id = world.save.team.id

    units = players | rival_stars
    entities = units | rival_orgs | {team_id}

    issues: list[RefIssue] = []

    # Id-space hygiene: a player and a rival org sharing an id would make every
    # reference below ambiguous, so catch it before the per-reference checks
    # produce confusing results. Empty in week6.
    id_buckets: list[tuple[str, set[str]]] = [
        ("team", {team_id}),
        ("player", players),
        ("rival_org", rival_orgs),
        ("rival_star", rival_stars),
    ]
    bucket_of: dict[str, list[str]] = {}
    for kind, ids in id_buckets:
        for entity_id in ids:
            bucket_of.setdefault(entity_id, []).append(kind)
    for entity_id, kinds in sorted(bucket_of.items()):
        if len(kinds) > 1:
            issues.append(
                RefIssue(
                    path="<id-collision>",
                    missing_id=entity_id,
                    expected=tuple(
                        [f"unique across {', '.join(sorted(kinds))}"]
                    ),
                )
            )

    unit_kinds = ("player", "rival_star")
    entity_kinds = ("player", "rival_star", "team", "rival_org")

    for pi, player in enumerate(world.players):
        for ri, rel in enumerate(player.relationships):
            if rel.with_ not in units:
                issues.append(
                    RefIssue(
                        path=f"players[{pi}={player.id}].relationships[{ri}].with",
                        missing_id=rel.with_,
                        expected=unit_kinds,
                    )
                )
        for mi, mem in enumerate(player.memory_log):
            for ai, actor in enumerate(mem.actors):
                if actor not in entities:
                    issues.append(
                        RefIssue(
                            path=(
                                f"players[{pi}={player.id}].memory_log[{mi}={mem.id}]"
                                f".actors[{ai}]"
                            ),
                            missing_id=actor,
                            expected=entity_kinds,
                        )
                    )

    for ci, pair in enumerate(world.clash_pairs):
        if pair.a not in units:
            issues.append(
                RefIssue(
                    path=f"clash_pairs[{ci}].a",
                    missing_id=pair.a,
                    expected=unit_kinds,
                )
            )
        if pair.b not in units:
            issues.append(
                RefIssue(
                    path=f"clash_pairs[{ci}].b",
                    missing_id=pair.b,
                    expected=unit_kinds,
                )
            )
        if pair.rival_org is not None and pair.rival_org not in rival_orgs:
            issues.append(
                RefIssue(
                    path=f"clash_pairs[{ci}].rival_org",
                    missing_id=pair.rival_org,
                    expected=("rival_org",),
                )
            )

    if world.last_week.opponent not in rival_orgs:
        issues.append(
            RefIssue(
                path="last_week.opponent",
                missing_id=world.last_week.opponent,
                expected=("rival_org",),
            )
        )

    feed_post_ids = {post.id for post in world.last_week.chirper_feed}
    for fi, post in enumerate(world.last_week.chirper_feed):
        if post.author_id is not None and post.author_id not in entities:
            issues.append(
                RefIssue(
                    path=f"last_week.chirper_feed[{fi}={post.id}].author_id",
                    missing_id=post.author_id,
                    expected=entity_kinds,
                )
            )
        if post.reply_to is not None and post.reply_to not in feed_post_ids:
            issues.append(
                RefIssue(
                    path=f"last_week.chirper_feed[{fi}={post.id}].reply_to",
                    missing_id=post.reply_to,
                    expected=("chirper_feed.id",),
                )
            )

    if issues:
        raise SaveReferentialIntegrityError(source, issues)


def load(path: Union[str, Path] = DEFAULT_SAVE_PATH) -> WorldState:
    """Parse a canned save YAML file into a validated :class:`WorldState`.

    Refuses a save whose ``schema_version`` this build cannot read — migrating an
    older one forward where a step is registered, or raising
    :class:`SchemaVersionError` with a clear message otherwise. After shape
    validation, the loader also runs :func:`check_referential_integrity`, so a
    save that parses and matches the schema but references an unknown unit,
    team, rival, or in-feed post id fails closed with a
    :class:`SaveReferentialIntegrityError` naming each offender.
    """
    # The default is an ``importlib.resources`` traversable (which exposes
    # ``read_text`` directly and need not be a real filesystem path under a
    # zipped install); a caller-supplied ``str`` goes through ``Path``.
    text = path.read_text(encoding="utf-8") if hasattr(path, "read_text") else Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    data = _ensure_loadable_version(data, path)
    world = WorldState.model_validate(data)
    check_referential_integrity(world, source=path)
    return world


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
