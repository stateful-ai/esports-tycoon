"""Unit tests for the typed game schema.

These exercise the model-level invariants directly (cite-ID format, owner match,
uniqueness, grounding, the runtime resolver/content types) so the schema is
proven to be a real gate, not just a shape.
"""

import pathlib
import sys
import unittest

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import schema  # noqa: E402
from esports_tycoon.cast_lock import spec  # noqa: E402
from esports_tycoon.schema import (  # noqa: E402
    GeneratedContent,
    KeyMoment,
    MemoryEntry,
    Player,
    Relationship,
    WhyRecord,
    WorldState,
)

_SAVE = pathlib.Path(__file__).resolve().parents[1] / "saves" / "week6.yaml"


def _raw():
    return yaml.safe_load(_SAVE.read_text(encoding="utf-8"))


def _memory(**overrides):
    base = {
        "id": "mem:rook:scrim_w5_choke",
        "week": 5,
        "day": 2,
        "kind": "scrim",
        "actors": ["rook"],
        "summary": "x",
        "sentiment": "negative",
        "tags": ["choke"],
    }
    base.update(overrides)
    return base


class TestMemoryEntry(unittest.TestCase):
    def test_valid(self):
        entry = MemoryEntry(**_memory())
        self.assertEqual(entry.id, "mem:rook:scrim_w5_choke")

    def test_rejects_malformed_id(self):
        for bad in ("mem:Rook:BadSlug", "mem:rook:_lead", "rook:choke", "mem:rook:double__us"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                MemoryEntry(**_memory(id=bad))

    def test_rejects_out_of_range_day(self):
        for bad in (0, 8):
            with self.subTest(day=bad), self.assertRaises(ValidationError):
                MemoryEntry(**_memory(day=bad))

    def test_rejects_unknown_kind_and_sentiment(self):
        with self.assertRaises(ValidationError):
            MemoryEntry(**_memory(kind="gossip"))
        with self.assertRaises(ValidationError):
            MemoryEntry(**_memory(sentiment="thrilled"))

    def test_memory_id_regex_matches_cast_lock(self):
        # The schema's cite format must not drift from the cast-lock gate's.
        self.assertEqual(schema.MEMORY_ID_RE.pattern, spec.MEMORY_ID_RE.pattern)


class TestRelationship(unittest.TestCase):
    def test_with_alias_round_trips(self):
        rel = Relationship.model_validate(
            {"with": "vex", "kind": "teammate", "status": "strained", "note": "x"}
        )
        self.assertEqual(rel.with_, "vex")
        self.assertEqual(rel.model_dump(by_alias=True)["with"], "vex")

    def test_extra_field_forbidden(self):
        with self.assertRaises(ValidationError):
            Relationship.model_validate(
                {"with": "vex", "kind": "teammate", "status": "x", "note": "y", "typo": 1}
            )


class TestPlayer(unittest.TestCase):
    def _player(self, **overrides):
        base = {
            "id": "rook",
            "name": "Rook",
            "handle": "@rook",
            "role": "IGL",
            "age": 27,
            "signature_operative": "Atlas",
            "bio": "b",
            "persona_voice": "v",
            "traits": ["veteran"],
            "relationships": [],
            "memory_log": [_memory()],
        }
        base.update(overrides)
        return base

    def test_valid_owner(self):
        player = Player.model_validate(self._player())
        self.assertEqual(player.role.value, "IGL")

    def test_rejects_foreign_memory(self):
        # A vex-owned memory filed in rook's log must fail.
        log = [_memory(id="mem:vex:ace_helix_w1", kind="match", sentiment="positive")]
        with self.assertRaises(ValidationError):
            Player.model_validate(self._player(memory_log=log))

    def test_rejects_unknown_role(self):
        with self.assertRaises(ValidationError):
            Player.model_validate(self._player(role="COACH"))


class TestWorldStateGrounding(unittest.TestCase):
    def test_rejects_duplicate_memory_id(self):
        bad = _raw()
        first = bad["players"][0]["memory_log"][0]["id"]
        bad["players"][0]["memory_log"][1]["id"] = first
        with self.assertRaises(ValidationError):
            WorldState.model_validate(bad)

    def test_rejects_dangling_clash_cite(self):
        bad = _raw()
        bad["clash_pairs"][0]["seeded_by"] = ["mem:rook:does_not_exist"]
        with self.assertRaises(ValidationError):
            WorldState.model_validate(bad)

    def test_rejects_dangling_rival_cite(self):
        bad = _raw()
        bad["rivals"][0]["seeded_by"] = ["mem:vex:does_not_exist"]
        with self.assertRaises(ValidationError):
            WorldState.model_validate(bad)

    def test_rejects_unmodelled_extra_field(self):
        bad = _raw()
        bad["players"][0]["nickname"] = "Cap"
        with self.assertRaises(ValidationError):
            WorldState.model_validate(bad)

    def test_cite_index_is_complete(self):
        world = WorldState.model_validate(_raw())
        index = world.cite_index
        self.assertEqual(len(index), 37)
        self.assertEqual(index["mem:rook:scrim_w5_choke"].day, 2)


class TestRuntimeModels(unittest.TestCase):
    """WhyRecord / GeneratedContent are runtime outputs, not part of the save."""

    def test_why_record(self):
        rec = WhyRecord(
            scoreline=(13, 9),
            mvp="sable",
            key_moments=[KeyMoment(round=24, kind="clutch", actors=["sable"], descriptor="1v3")],
            who_carried=["sable"],
            who_tilted=["vex"],
            morale_deltas={"sable": 2, "vex": -1},
            seed=42,
        )
        self.assertEqual(rec.scoreline, (13, 9))
        self.assertEqual(rec.morale_deltas["vex"], -1)

    def test_generated_content_defaults_to_zero_cost(self):
        gc = GeneratedContent(kind="chirper_post", text="held. won. hungry.", grounding_status="ok")
        self.assertEqual(gc.cost_usd, 0.0)
        self.assertEqual(gc.cites, [])

    def test_generated_content_validates_kind_and_cites(self):
        with self.assertRaises(ValidationError):
            GeneratedContent(kind="tweet", text="x", grounding_status="ok")
        with self.assertRaises(ValidationError):
            GeneratedContent(
                kind="chirper_post", text="x", grounding_status="ok", cites=["not-a-mem-id"]
            )
        with self.assertRaises(ValidationError):
            GeneratedContent(kind="chirper_post", text="x", grounding_status="maybe")


if __name__ == "__main__":
    unittest.main()
