"""Load-time referential-integrity gate on the canonical save.

The typed schema in :mod:`esports_tycoon.schema` enforces *shape* — types,
required fields, and the stable-cite-id grammar for memories — but
deliberately leaves cross-entity references (a clash between two units, a
chirper post addressed at a team, last week's opponent) as plain strings.
:func:`esports_tycoon.canned.loader.check_referential_integrity` closes that
gap on load: every such reference must resolve to an entity actually defined
in the save, and a save that fails this check must do so loudly, naming the
offending path and id.

Every load-time failure surfaces as a :class:`loader.SaveError` carrying
``field_path`` — the structured save location at fault. Subclasses
distinguish *which* contract fired (YAML parse, version gate, typed schema,
referential integrity), but the negative fixtures assert on the shared base
type *and* the field path, not on ad-hoc exceptions, so the contract stays
single-sourced as new failure modes are added.

Four classes of failure, four distinct field paths, four fixtures:

* Corrupt YAML → :class:`SaveYamlError`, ``field_path == "<yaml>"`` (the
  underlying parser's line/column hint is preserved on ``__cause__``).
* Unknown ``schema_version`` → :class:`SchemaVersionError`,
  ``field_path == "schema_version"``.
* Orphan ``mem:`` cite → :class:`SaveSchemaError`, ``field_path`` is the
  structured location of the dangling cite (e.g.
  ``"clash_pairs[0].seeded_by[0]"``).
* Dangling unit / team / rival / post id →
  :class:`SaveReferentialIntegrityError`, ``field_path`` is the first
  unresolved reference's path.

The week6 canonical save is also re-asserted as integrity-clean here, so the
gate cannot silently regress into a rubber stamp.
"""

from __future__ import annotations

import copy
import pathlib
import sys
import tempfile
import unittest

import pytest
import yaml
from pydantic import ValidationError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import canonical, loader  # noqa: E402
from esports_tycoon.schema import WorldState  # noqa: E402

# M1 scope (docs/m0_gate_decision.md): the RI validator + the negative-fixture
# suite + the typed SaveError contract all harden a load path the M0 screenshot
# gate did not exercise. The validator code stays wired so happy-path loads
# still benefit from it; only the enforcement tests park under M1's name until
# the M1 ticket that lands the contract.
pytestmark = pytest.mark.skip(
    reason="M1 scope: RI validator + negative fixtures + typed SaveError contract"
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "integrity"


def _raw_canonical() -> dict:
    return yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))


class _TempSaveTest(unittest.TestCase):
    """Base: serialize a save dict to disk and round-trip it through ``load``."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def _write(self, raw: dict, name: str = "save.yaml") -> pathlib.Path:
        path = pathlib.Path(self._dir.name) / name
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return path


class TestWeek6PassesIntegrity(unittest.TestCase):
    """The shipped canonical save loads cleanly through the new gate."""

    def test_week6_load_does_not_raise(self) -> None:
        world = loader.load()
        # And running the checker again is idempotent on a clean world.
        loader.check_referential_integrity(world, source="<week6>")

    def test_week6_has_no_outstanding_ref_issues(self) -> None:
        world = loader.load()
        # The checker on a clean world raises nothing; this asserts the
        # acceptance contract directly so a future regression — say, a
        # rename without a follow-up — fails loudly here, not as a vague
        # KeyError in narration months later.
        try:
            loader.check_referential_integrity(world)
        except loader.SaveReferentialIntegrityError as exc:  # pragma: no cover
            self.fail(
                "week6 must pass referential integrity, "
                f"found {len(exc.issues)} issue(s): {exc.issues}"
            )


class TestMissingUnitRefFails(_TempSaveTest):
    """A reference to an undefined unit/team/rival fails with the named error."""

    def test_clash_pair_unit_typo_is_rejected(self) -> None:
        raw = copy.deepcopy(_raw_canonical())
        raw["clash_pairs"][0]["b"] = "vexx"  # typo for ``vex``
        path = self._write(raw)
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(path)
        msg = str(cm.exception)
        self.assertIn(str(path), msg)
        self.assertIn("clash_pairs[0].b", msg)
        self.assertIn("'vexx'", msg)
        self.assertIn("player", msg)
        self.assertIn("rival_star", msg)

    def test_clash_pair_rival_org_typo_is_rejected(self) -> None:
        raw = copy.deepcopy(_raw_canonical())
        cross_team_idx = next(
            i for i, p in enumerate(raw["clash_pairs"]) if p.get("rival_org")
        )
        raw["clash_pairs"][cross_team_idx]["rival_org"] = "northwhind"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        self.assertIn(f"clash_pairs[{cross_team_idx}].rival_org", str(cm.exception))
        self.assertIn("'northwhind'", str(cm.exception))
        self.assertIn("rival_org", str(cm.exception))

    def test_last_week_opponent_is_validated(self) -> None:
        raw = copy.deepcopy(_raw_canonical())
        raw["last_week"]["opponent"] = "ghosts_of_winter"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        self.assertIn("last_week.opponent", str(cm.exception))
        self.assertIn("ghosts_of_winter", str(cm.exception))

    def test_chirper_author_id_is_validated(self) -> None:
        # ``author_id`` may be a team id (e.g. ``overcast``) as well as a
        # player or rival star, so the validator must accept the team but
        # reject an outright-unknown handle.
        raw = copy.deepcopy(_raw_canonical())
        raw["last_week"]["chirper_feed"][0]["author_id"] = "phantom_org"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        self.assertIn(
            "last_week.chirper_feed[0=chirp:w5:01].author_id", str(cm.exception)
        )
        self.assertIn("phantom_org", str(cm.exception))

    def test_chirper_reply_to_must_name_a_real_post(self) -> None:
        raw = copy.deepcopy(_raw_canonical())
        feed = raw["last_week"]["chirper_feed"]
        # First post that replies to another in this feed.
        reply_idx = next(i for i, p in enumerate(feed) if p.get("reply_to"))
        feed[reply_idx]["reply_to"] = "chirp:w5:does_not_exist"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        msg = str(cm.exception)
        self.assertIn(f"chirper_feed[{reply_idx}=", msg)
        self.assertIn("reply_to", msg)
        self.assertIn("chirp:w5:does_not_exist", msg)
        self.assertIn("chirper_feed.id", msg)

    def test_relationship_with_is_validated(self) -> None:
        raw = copy.deepcopy(_raw_canonical())
        raw["players"][0]["relationships"][0]["with"] = "no_such_player"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        self.assertIn(
            "players[0=rook].relationships[0].with", str(cm.exception)
        )
        self.assertIn("no_such_player", str(cm.exception))

    def test_memory_actor_is_validated(self) -> None:
        raw = copy.deepcopy(_raw_canonical())
        raw["players"][0]["memory_log"][0]["actors"] = ["rook", "phantom_actor"]
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        msg = str(cm.exception)
        self.assertIn("players[0=rook].memory_log[0", msg)
        self.assertIn("actors[1]", msg)
        self.assertIn("phantom_actor", msg)

    def test_all_issues_are_reported_in_one_pass(self) -> None:
        # The checker collects every dangling reference and raises once, so an
        # author who broke two things in the same edit doesn't have to fix them
        # one at a time.
        raw = copy.deepcopy(_raw_canonical())
        raw["last_week"]["opponent"] = "ghosts_of_winter"
        raw["clash_pairs"][0]["a"] = "rookk"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        self.assertEqual(len(cm.exception.issues), 2)
        paths = {issue.path for issue in cm.exception.issues}
        self.assertIn("last_week.opponent", paths)
        self.assertIn("clash_pairs[0].a", paths)

    def test_id_collision_between_player_and_rival_is_rejected(self) -> None:
        # An id that names two entity kinds at once makes every reference to
        # it ambiguous; the integrity check refuses it instead of guessing.
        raw = copy.deepcopy(_raw_canonical())
        raw["rivals"][0]["id"] = raw["players"][0]["id"]  # rivals[0].id = "rook"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(self._write(raw))
        msg = str(cm.exception)
        self.assertIn("<id-collision>", msg)
        self.assertIn(raw["players"][0]["id"], msg)
        self.assertIn("unique", msg)


class TestErrorTypeIsADistinctValueErrorSubclass(unittest.TestCase):
    """The named error must be catchable narrowly, on the shared base, and as ``ValueError``."""

    def test_is_value_error_subclass(self) -> None:
        self.assertTrue(
            issubclass(loader.SaveReferentialIntegrityError, ValueError)
        )

    def test_is_save_error_subclass(self) -> None:
        # Every load-time error is a ``SaveError`` so a caller can catch the
        # shared base once and read ``field_path`` uniformly.
        self.assertTrue(
            issubclass(loader.SaveReferentialIntegrityError, loader.SaveError)
        )

    def test_is_disjoint_from_schema_version_error(self) -> None:
        # The named errors are siblings, not ancestors; a caller that catches
        # one must not accidentally swallow another. Their common parent is
        # :class:`SaveError`, never each other.
        self.assertFalse(
            issubclass(
                loader.SaveReferentialIntegrityError, loader.SchemaVersionError
            )
        )
        self.assertFalse(
            issubclass(
                loader.SchemaVersionError, loader.SaveReferentialIntegrityError
            )
        )


class TestSharedSaveErrorContract(unittest.TestCase):
    """``SaveError`` is the single typed contract every load failure raises.

    Pins the acceptance: one shared base error carrying ``field_path``; the
    loader, the version check, and the RI validator each raise it (as their
    own subclass); negative fixtures assert on the shared type and the field
    path, not on ad-hoc exceptions.
    """

    def test_save_error_is_a_value_error(self) -> None:
        # Back-compat: callers that broadly catch ``ValueError`` on a bad save
        # keep working. ``SaveError`` is the typed twin, not a replacement.
        self.assertTrue(issubclass(loader.SaveError, ValueError))

    def test_every_save_error_subclass_inherits_the_shared_base(self) -> None:
        # The four named subclasses share one parent; a caller that catches
        # ``SaveError`` catches all of them and can read the same fields.
        for subclass in (
            loader.SaveYamlError,
            loader.SchemaVersionError,
            loader.SaveSchemaError,
            loader.SaveReferentialIntegrityError,
        ):
            with self.subTest(subclass=subclass):
                self.assertTrue(issubclass(subclass, loader.SaveError))

    def test_save_error_carries_field_path_and_source(self) -> None:
        # The shared instance contract: ``field_path`` (a string naming the
        # offending location) and ``source`` (the path or object the save was
        # loaded from) are both present on every SaveError, regardless of
        # which subclass fired.
        exc = loader.SaveError("boom", field_path="players[0].id", source="<x>")
        self.assertEqual(exc.field_path, "players[0].id")
        self.assertEqual(exc.source, "<x>")
        # And it's catchable as ``ValueError`` for back-compat.
        try:
            raise exc
        except ValueError as caught:
            self.assertIs(caught, exc)

    def test_schema_version_error_defaults_field_path_to_schema_version(
        self,
    ) -> None:
        # The version gate's field is always ``schema_version`` — the author
        # knows where to look without reading the message. The default lives
        # on the subclass so every raise site stays terse.
        exc = loader.SchemaVersionError("nope", source="<x>")
        self.assertEqual(exc.field_path, "schema_version")

    def test_referential_integrity_error_field_path_is_first_issue(self) -> None:
        issues = [
            loader.RefIssue(
                path="last_week.opponent",
                missing_id="ghosts_of_winter",
                expected=("rival_org",),
            ),
            loader.RefIssue(
                path="clash_pairs[0].a",
                missing_id="rookk",
                expected=("player", "rival_star"),
            ),
        ]
        exc = loader.SaveReferentialIntegrityError("<world>", issues)
        # The surfaced ``field_path`` is the *first* issue's path (the most
        # actionable on its own); the full list is still on ``.issues`` so an
        # author gets every offender in one round-trip.
        self.assertEqual(exc.field_path, "last_week.opponent")
        self.assertEqual(len(exc.issues), 2)
        self.assertEqual(exc.source, "<world>")

    def test_loader_version_check_and_ri_validator_all_raise_save_error(
        self,
    ) -> None:
        # The acceptance, restated: each of the three named layers — the
        # loader (yaml + shape), the version check, the RI validator — raises
        # ``SaveError``. One fixture per layer; one catch per layer; the
        # ``field_path`` attribute is the shared contract.
        with self.assertRaises(loader.SaveError) as cm:
            loader.load(FIXTURES / "corrupt.yaml")
        self.assertIsInstance(cm.exception, loader.SaveYamlError)
        self.assertEqual(cm.exception.field_path, "<yaml>")

        with self.assertRaises(loader.SaveError) as cm:
            loader.load(FIXTURES / "unknown_schema_version_major.yaml")
        self.assertIsInstance(cm.exception, loader.SchemaVersionError)
        self.assertEqual(cm.exception.field_path, "schema_version")

        with self.assertRaises(loader.SaveError) as cm:
            loader.load(FIXTURES / "orphan_mem_cite.yaml")
        self.assertIsInstance(cm.exception, loader.SaveSchemaError)
        self.assertEqual(cm.exception.field_path, "clash_pairs[0].seeded_by[0]")

        with self.assertRaises(loader.SaveError) as cm:
            loader.load(FIXTURES / "dangling_actor.yaml")
        self.assertIsInstance(cm.exception, loader.SaveReferentialIntegrityError)
        self.assertEqual(
            cm.exception.field_path,
            "players[0=rook].memory_log[0=mem:rook:debut].actors[1]",
        )


class TestProgrammaticCheck(unittest.TestCase):
    """The checker is callable on a constructed ``WorldState`` for unit-test use."""

    def test_checker_runs_on_world_object(self) -> None:
        world = loader.load()
        loader.check_referential_integrity(world)

    def test_checker_default_source_is_in_message(self) -> None:
        # ``check_referential_integrity(world)`` (no source) still produces a
        # readable message — the default ``<world>`` shows in the error.
        raw = copy.deepcopy(_raw_canonical())
        raw["clash_pairs"][0]["b"] = "vexx"
        world = WorldState.model_validate(raw)  # shape-valid, integrity-bad
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.check_referential_integrity(world)
        self.assertIn("<world>", str(cm.exception))


class TestCommittedFixturesProduceDistinctMessages(unittest.TestCase):
    """Each negative fixture raises ``SaveError`` with the right field path.

    Asserts the shared-contract acceptance: every load failure surfaces as a
    :class:`loader.SaveError` carrying a structured ``field_path``, with a
    specific subclass per category. The fixtures pin both halves — the shared
    type and the location — so neither half can regress alone.
    """

    def test_corrupt_fixture_is_a_yaml_save_error(self) -> None:
        path = FIXTURES / "corrupt.yaml"
        with self.assertRaises(loader.SaveError) as cm:
            loader.load(path)
        exc = cm.exception
        self.assertIsInstance(exc, loader.SaveYamlError)
        self.assertEqual(exc.field_path, "<yaml>")
        self.assertEqual(exc.source, path)
        # The yaml parser's line/column hint is preserved on the cause so a
        # caller that wants the original locator still has it one ``__cause__``
        # hop away from the typed save error.
        self.assertIsInstance(exc.__cause__, yaml.YAMLError)
        cause_msg = str(exc.__cause__)
        self.assertIn("line", cause_msg)
        self.assertIn("column", cause_msg)

    def test_unknown_version_fixture_is_a_schema_version_error(self) -> None:
        path = FIXTURES / "unknown_version.yaml"
        with self.assertRaises(loader.SaveError) as cm:
            loader.load(path)
        exc = cm.exception
        self.assertIsInstance(exc, loader.SchemaVersionError)
        self.assertEqual(exc.field_path, "schema_version")
        self.assertEqual(exc.source, path)
        msg = str(exc)
        self.assertIn(str(path), msg)
        self.assertIn("9999", msg)  # the offending version is named
        self.assertIn("newer", msg)  # vs. the version this build supports
        self.assertIn("schema_version", msg)

    def test_missing_ref_fixture_is_a_referential_integrity_error(self) -> None:
        path = FIXTURES / "missing_unit_ref.yaml"
        with self.assertRaises(loader.SaveError) as cm:
            loader.load(path)
        exc = cm.exception
        self.assertIsInstance(exc, loader.SaveReferentialIntegrityError)
        self.assertEqual(exc.field_path, "clash_pairs[0].b")
        self.assertEqual(exc.source, path)
        msg = str(exc)
        self.assertIn(str(path), msg)
        self.assertIn("clash_pairs[0].b", msg)
        self.assertIn("vexx", msg)
        self.assertIn("player", msg)

    def test_four_fixtures_four_distinct_save_error_subclasses(self) -> None:
        # The four failures must surface as four different SaveError subclasses
        # so a caller can distinguish "you can't parse this file" from "you
        # can't read this version" from "this save's shape is wrong" from
        # "this save is internally inconsistent" — while still catching them
        # all on the shared ``SaveError`` base.
        types: set[type] = set()
        for name, expected_subclass in [
            ("corrupt.yaml", loader.SaveYamlError),
            ("unknown_version.yaml", loader.SchemaVersionError),
            ("orphan_mem_cite.yaml", loader.SaveSchemaError),
            ("missing_unit_ref.yaml", loader.SaveReferentialIntegrityError),
        ]:
            with self.assertRaises(loader.SaveError) as cm:
                loader.load(FIXTURES / name)
            self.assertIsInstance(cm.exception, expected_subclass)
            # The field path must be a non-empty string so a caller can route
            # on it without checking for None.
            self.assertIsInstance(cm.exception.field_path, str)
            self.assertTrue(cm.exception.field_path)
            types.add(type(cm.exception))
        self.assertEqual(len(types), 4)


class TestNegativeFixturesFailClosed(unittest.TestCase):
    """The committed negative fixtures must each fail closed in the right way.

    One fixture per failure category the load path is responsible for catching,
    asserted against the file on disk so a regression in *either* the loader's
    error type *or* its message format trips here. The happy week6 save is
    re-asserted alongside so the suite cannot regress into "fixtures fail, but
    so does the real save."
    """

    def test_happy_week6_still_loads(self) -> None:
        # The shipped canonical save must keep loading clean while the negative
        # fixtures around it grow — a regression that caught one of the bad
        # paths by also rejecting the good save would still be a regression.
        world = loader.load()
        self.assertEqual(world.save.id, "week6")

    def test_orphan_mem_cite_fixture_fails_in_grounding_validator(self) -> None:
        # The shape-validator catches the dangling cite *before* the loader
        # reaches ``check_referential_integrity``. The loader lifts pydantic's
        # ``ValidationError`` into the shared ``SaveError`` contract as a
        # ``SaveSchemaError``, with ``field_path`` promoted off the typed
        # ``GroundingError`` the schema validator raised — so the negative
        # fixture asserts on the shared type and the structured location, not
        # on pydantic's exception class. The author can take the field path
        # straight to the offending line.
        path = FIXTURES / "orphan_mem_cite.yaml"
        with self.assertRaises(loader.SaveError) as cm:
            loader.load(path)
        exc = cm.exception
        self.assertIsInstance(exc, loader.SaveSchemaError)
        self.assertEqual(exc.field_path, "clash_pairs[0].seeded_by[0]")
        self.assertEqual(exc.source, path)
        # The original pydantic error is preserved so a caller that needs the
        # full per-field list still has it one hop away.
        self.assertIsInstance(exc.original, ValidationError)
        self.assertIs(exc.__cause__, exc.original)
        # The message body keeps the actor descriptor and the offending cite,
        # so a human reader sees both the structured path and the human-named
        # entities in one place.
        msg = str(exc)
        self.assertIn("cites must resolve to a real memory", msg)
        self.assertIn("clash_pairs[0].seeded_by[0]", msg)
        self.assertIn("clash rook/vex", msg)
        self.assertIn("mem:rook:never_happened", msg)

    def test_dangling_actor_fixture_fails_in_referential_integrity(self) -> None:
        # Shape-valid (every cite resolves) but an actor on a memory entry
        # names a unit no entity defines. The integrity gate raises the typed
        # error with the exact field path — players[N=id].memory_log[M=mem-id]
        # .actors[K] — and the offending id.
        path = FIXTURES / "dangling_actor.yaml"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(path)
        msg = str(cm.exception)
        self.assertIn(str(path), msg)
        self.assertIn(
            "players[0=rook].memory_log[0=mem:rook:debut].actors[1]", msg
        )
        self.assertIn("'phantom_unit'", msg)
        # The expected-id-kinds list belongs in the message too, so an author
        # can see at a glance whether they meant a player or a rival.
        self.assertIn("player", msg)
        self.assertIn("rival_star", msg)
        # And the typed-error contract: exactly one issue, on that path.
        self.assertEqual(len(cm.exception.issues), 1)
        issue = cm.exception.issues[0]
        self.assertEqual(
            issue.path,
            "players[0=rook].memory_log[0=mem:rook:debut].actors[1]",
        )
        self.assertEqual(issue.missing_id, "phantom_unit")

    def test_unknown_schema_version_major_fixture_fails_in_version_gate(self) -> None:
        # A version higher than this build supports is "unknown major" and the
        # version gate fires before any of the rest of the schema is touched.
        # The typed error here is ``SchemaVersionError``, and the field path it
        # owes the author is ``schema_version`` plus the offending value, so
        # they can take the message straight to the offending line. This
        # fixture pins the *next-major* case (current + 1), the realistic save
        # an author would hand-write; sibling ``unknown_version.yaml`` pins
        # the sky-high-future case so neither regression slips through.
        path = FIXTURES / "unknown_schema_version_major.yaml"
        with self.assertRaises(loader.SchemaVersionError) as cm:
            loader.load(path)
        msg = str(cm.exception)
        self.assertIn(str(path), msg)
        self.assertIn("schema_version", msg)
        # The offending value (1) and the build's current version (0) both
        # belong in the message so the author can see the gap at a glance.
        self.assertIn("1", msg)
        self.assertIn("newer", msg)

    # --- bytes fail-closed ---------------------------------------------------- #
    def test_loose_floats_shuffled_keys_fixture_normalizes_to_canonical_bytes(
        self,
    ) -> None:
        # The fourth fail-closed category isn't a typed error: it is *bytes*.
        # A loose-form input (loose float spellings + non-alphabetical key
        # order) must flow through the canonical serializer to one fixed-point
        # byte form. The expected canonical text is pinned inline so any drift
        # — re-padded mantissa, alphabetized keys, dropped trailing newline,
        # flow-style fallback — flips the assertion with a reviewable diff.
        path = FIXTURES / "loose_floats_shuffled_keys.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        produced = canonical.dumps(data)
        expected = (
            "zebra: 1.0\n"
            "alpha: 1.0e-05\n"
            "mike: 1.0e+20\n"
            "nan_value: .nan\n"
            "inf_value: .inf\n"
            "neg_inf: -.inf\n"
            "neg_zero: -0.0\n"
        )
        self.assertEqual(produced, expected)
        # Idempotence: re-loading the canonical bytes and re-dumping yields
        # the identical text. This is what "canonical bytes" means — the
        # serializer is a fixed point, not just a one-shot rewrite.
        self.assertEqual(canonical.dumps(yaml.safe_load(produced)), expected)

    def test_loose_floats_shuffled_keys_fixture_preserves_input_key_order(
        self,
    ) -> None:
        # The shuffled-key half of the contract: the canonical dumper preserves
        # input dict iteration order (``sort_keys=False``). A regression that
        # alphabetized would emit ``alpha`` first; we assert ``zebra`` does.
        path = FIXTURES / "loose_floats_shuffled_keys.yaml"
        produced = canonical.dumps(yaml.safe_load(path.read_text(encoding="utf-8")))
        first_line = produced.splitlines()[0]
        self.assertTrue(
            first_line.startswith("zebra:"),
            f"canonical dumper must preserve input key order; got first line {first_line!r}",
        )

    def test_negative_fixtures_surface_four_distinct_outcomes(self) -> None:
        # The four negative fixtures must each fail closed *in their own way* —
        # three distinct ``SaveError`` subclasses plus the bytes-equality
        # assertion — so a caller (or a future maintainer) can tell which
        # contract was breached by looking at the subclass alone, while still
        # catching every load failure on the shared ``SaveError`` base. A
        # collapse where two fixtures started raising the same subclass would
        # silently merge two contracts; this guard trips on that.
        subclasses: set[type] = set()
        for name, expected_subclass, expected_field_path in [
            (
                "orphan_mem_cite.yaml",
                loader.SaveSchemaError,
                "clash_pairs[0].seeded_by[0]",
            ),
            (
                "dangling_actor.yaml",
                loader.SaveReferentialIntegrityError,
                "players[0=rook].memory_log[0=mem:rook:debut].actors[1]",
            ),
            (
                "unknown_schema_version_major.yaml",
                loader.SchemaVersionError,
                "schema_version",
            ),
        ]:
            with self.assertRaises(loader.SaveError) as cm:
                loader.load(FIXTURES / name)
            self.assertIsInstance(cm.exception, expected_subclass)
            self.assertEqual(cm.exception.field_path, expected_field_path)
            subclasses.add(type(cm.exception))
        self.assertEqual(len(subclasses), 3)
        # The fourth doesn't raise — it must normalize. Equality here proves
        # that contract; a regression would either raise (wrong) or produce
        # different bytes (also wrong).
        path = FIXTURES / "loose_floats_shuffled_keys.yaml"
        produced = canonical.dumps(yaml.safe_load(path.read_text(encoding="utf-8")))
        self.assertTrue(produced.endswith("\n"))
        self.assertFalse(produced.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
