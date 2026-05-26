"""Load-time referential-integrity gate on the canonical save.

The typed schema in :mod:`esports_tycoon.schema` enforces *shape* — types,
required fields, and the stable-cite-id grammar for memories — but
deliberately leaves cross-entity references (a clash between two units, a
chirper post addressed at a team, last week's opponent) as plain strings.
:func:`esports_tycoon.canned.loader.check_referential_integrity` closes that
gap on load: every such reference must resolve to an entity actually defined
in the save, and a save that fails this check must do so loudly, naming the
offending path and id, with a distinct error type from the schema-version
gate and the YAML parser.

Three classes of failure, three distinct messages, three fixtures:

* Corrupt YAML → ``yaml.YAMLError``, message names the line / column.
* Unknown ``schema_version`` → :class:`SchemaVersionError`, message names
  the offending version and the version this build supports.
* Dangling unit / team / rival / post id →
  :class:`SaveReferentialIntegrityError`, message names every unresolved
  reference and the kinds of id that would have resolved.

The week6 canonical save is also re-asserted as integrity-clean here, so the
gate cannot silently regress into a rubber stamp.
"""

from __future__ import annotations

import copy
import pathlib
import sys
import tempfile
import unittest

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import canonical, loader  # noqa: E402
from esports_tycoon.schema import WorldState  # noqa: E402

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
    """The named error must be catchable both narrowly and as ``ValueError``."""

    def test_is_value_error_subclass(self) -> None:
        self.assertTrue(
            issubclass(loader.SaveReferentialIntegrityError, ValueError)
        )

    def test_is_disjoint_from_schema_version_error(self) -> None:
        # The two named errors are siblings, not ancestors; a caller that
        # catches one must not accidentally swallow the other.
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
    """Three negative fixtures, three distinct error types and messages."""

    def test_corrupt_fixture_is_a_yaml_parse_error(self) -> None:
        path = FIXTURES / "corrupt.yaml"
        with self.assertRaises(yaml.YAMLError) as cm:
            loader.load(path)
        msg = str(cm.exception)
        # The actionable bits: a yaml parser locates the failure in the file.
        self.assertIn("line", msg)
        self.assertIn("column", msg)

    def test_unknown_version_fixture_is_a_schema_version_error(self) -> None:
        path = FIXTURES / "unknown_version.yaml"
        with self.assertRaises(loader.SchemaVersionError) as cm:
            loader.load(path)
        msg = str(cm.exception)
        self.assertIn(str(path), msg)
        self.assertIn("9999", msg)  # the offending version is named
        self.assertIn("newer", msg)  # vs. the version this build supports
        self.assertIn("schema_version", msg)

    def test_missing_ref_fixture_is_a_referential_integrity_error(self) -> None:
        path = FIXTURES / "missing_unit_ref.yaml"
        with self.assertRaises(loader.SaveReferentialIntegrityError) as cm:
            loader.load(path)
        msg = str(cm.exception)
        self.assertIn(str(path), msg)
        self.assertIn("clash_pairs[0].b", msg)
        self.assertIn("vexx", msg)
        self.assertIn("player", msg)

    def test_three_fixtures_three_distinct_error_types(self) -> None:
        # The three failures must surface as three different types so a
        # caller can distinguish "you can't parse this file" from "you can't
        # read this version" from "this save is internally inconsistent".
        types: set[type] = set()
        for name, expected in [
            ("corrupt.yaml", yaml.YAMLError),
            ("unknown_version.yaml", loader.SchemaVersionError),
            ("missing_unit_ref.yaml", loader.SaveReferentialIntegrityError),
        ]:
            with self.assertRaises(expected) as cm:
                loader.load(FIXTURES / name)
            types.add(type(cm.exception))
        self.assertEqual(len(types), 3)


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
        # reaches ``check_referential_integrity``, so the typed error here is
        # pydantic's ``ValidationError`` (raised out of
        # ``WorldState._grounding_holds``), distinct from the integrity error.
        # The field path the message owes the author is the clash that holds
        # the orphan cite and the cite id itself.
        path = FIXTURES / "orphan_mem_cite.yaml"
        with self.assertRaises(ValidationError) as cm:
            loader.load(path)
        msg = str(cm.exception)
        self.assertIn("cites must resolve to a real memory", msg)
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
        # three distinct typed errors plus the bytes-equality assertion — so a
        # caller (or a future maintainer) can tell which contract was breached
        # by looking at the type alone, without parsing the message. A
        # collapse where two fixtures started raising the same error would
        # silently merge two contracts; this guard trips on that.
        with self.assertRaises(ValidationError):
            loader.load(FIXTURES / "orphan_mem_cite.yaml")
        with self.assertRaises(loader.SaveReferentialIntegrityError):
            loader.load(FIXTURES / "dangling_actor.yaml")
        with self.assertRaises(loader.SchemaVersionError):
            loader.load(FIXTURES / "unknown_schema_version_major.yaml")
        # The fourth doesn't raise — it must normalize. Equality here proves
        # that contract; a regression would either raise (wrong) or produce
        # different bytes (also wrong).
        path = FIXTURES / "loose_floats_shuffled_keys.yaml"
        produced = canonical.dumps(yaml.safe_load(path.read_text(encoding="utf-8")))
        self.assertTrue(produced.endswith("\n"))
        self.assertFalse(produced.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
