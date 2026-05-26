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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
