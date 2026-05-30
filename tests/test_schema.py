"""Unit tests for the typed game schema.

These exercise the model-level invariants directly (cite-ID format, owner match,
uniqueness, grounding, the runtime resolver/content types) so the schema is
proven to be a real gate, not just a shape.
"""

import json
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
    RoundResult,
    WhyRecord,
    WorldState,
    canonical_why_record_bytes,
    why_record_digest,
)

_SAVE = spec.DEFAULT_SAVE_PATH


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


def _why_record(**overrides) -> WhyRecord:
    """A small WhyRecord with every shape the canonical digest cares about."""
    base = dict(
        scoreline=(13, 9),
        mvp="sable",
        key_moments=[
            KeyMoment(round=24, kind="clutch", actors=["sable", "vex"], descriptor="1v3"),
        ],
        who_carried=["sable"],
        who_tilted=["vex"],
        morale_deltas={"sable": 2, "vex": -1, "rook": 0},
        seed=42,
        round_log=[RoundResult(round=1, winner="overcast", summary="1-0")],
    )
    base.update(overrides)
    return WhyRecord(**base)


class TestCanonicalWhyRecord(unittest.TestCase):
    """The canonical bytes and digest implement the byte-identity contract.

    These checks pin the properties the 100-run determinism sweep leans on:
    dict iteration order can't leak through (``PYTHONHASHSEED`` immunity),
    perturbing any field flips the digest, and the bytes are real UTF-8 JSON
    so a diff is reviewable.
    """

    def test_digest_is_stable_under_dict_insertion_order(self):
        # Same morale_deltas content, different insertion order. Pydantic
        # preserves insertion order on dump, so without the sort step in
        # _canonicalize_for_digest the bytes (and digest) would diverge.
        forward = _why_record(morale_deltas={"sable": 2, "vex": -1, "rook": 0})
        reversed_ = _why_record(morale_deltas={"rook": 0, "vex": -1, "sable": 2})
        self.assertEqual(why_record_digest(forward), why_record_digest(reversed_))
        self.assertEqual(
            canonical_why_record_bytes(forward),
            canonical_why_record_bytes(reversed_),
        )

    def test_digest_changes_when_any_field_changes(self):
        # Every WhyRecord field that the resolver feeds the narrator must
        # contribute to the digest — otherwise a regression in that field
        # would sail past the determinism check.
        base = _why_record()
        base_digest = why_record_digest(base)
        for tweak in (
            _why_record(scoreline=(13, 10)),
            _why_record(mvp="rook"),
            _why_record(who_carried=["rook"]),
            _why_record(who_tilted=["rook"]),
            _why_record(morale_deltas={"sable": 3, "vex": -1, "rook": 0}),
            _why_record(seed=43),
            _why_record(
                key_moments=[
                    KeyMoment(round=24, kind="clutch", actors=["sable"], descriptor="1v3"),
                ],
            ),
            _why_record(
                round_log=[RoundResult(round=1, winner="overcast", summary="1-0")]
                + [RoundResult(round=2, winner="overcast", summary="2-0")],
            ),
        ):
            with self.subTest(tweak=tweak.model_dump()):
                self.assertNotEqual(why_record_digest(tweak), base_digest)

    def test_canonical_bytes_are_compact_sorted_utf8_json(self):
        # The byte form must be parseable JSON whose top-level keys are sorted
        # — that is the actual ``PYTHONHASHSEED``-immunity guarantee, stated
        # in a way that fails if json.dumps's ``sort_keys`` is ever dropped.
        record = _why_record()
        text = canonical_why_record_bytes(record).decode("utf-8")
        parsed = json.loads(text)
        self.assertEqual(parsed["mvp"], "sable")
        top_keys = [
            line.lstrip().split('"', 2)[1]
            for line in text.replace("{", "{\n").replace(",", ",\n").splitlines()
            if line.lstrip().startswith('"')
        ]
        # The first occurrence of each top-level key, in the order they appear
        # in the compact bytes, must be sorted. Nested keys (e.g. inside
        # ``key_moments``) sort independently, so we only check first-seen
        # order at the document root.
        seen: list[str] = []
        depth = 0
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
            elif ch == '"' and depth == 1:
                end = text.index('"', i + 1)
                key = text[i + 1 : end]
                # A key is followed by ':'; a value-string by ',' or '}'.
                if text[end + 1] == ":":
                    if key not in seen:
                        seen.append(key)
                i = end
            i += 1
        self.assertEqual(seen, sorted(seen), f"top-level keys are not sorted: {seen}")
        # Separators must be the compact form, with no incidental whitespace.
        self.assertNotIn(", ", text)
        self.assertNotIn(": ", text)

    def test_perturbation_proves_the_digest_can_fail(self):
        # Mirror of the resolver-side perturbation case: a deliberately
        # tweaked record yields a different digest, so the equality assertion
        # the 100-run sweep relies on is not vacuous.
        base = _why_record()
        perturbed = _why_record(seed=base.seed + 1)
        self.assertNotEqual(why_record_digest(base), why_record_digest(perturbed))

    def test_digest_is_64_hex_chars(self):
        digest = why_record_digest(_why_record())
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # no ValueError ⇒ it is hex


if __name__ == "__main__":
    unittest.main()
