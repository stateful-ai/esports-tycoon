"""Unit tests for validate_save: each acceptance check fails when it should.

The real save is used as a known-good base; each test mutates a deep copy to
trip exactly one check, proving the gate is not a rubber stamp.
"""

import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.cast_lock import spec  # noqa: E402


def _failed(result):
    return {c.name for c in result.failures}


class TestValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = spec.load_save(spec.DEFAULT_SAVE_PATH)

    def good(self):
        return copy.deepcopy(self.base)

    def test_base_is_valid(self):
        self.assertTrue(spec.validate_save(self.good()).ok)

    def test_too_few_starters(self):
        save = self.good()
        save["players"].pop()
        self.assertIn("five_named_starters", _failed(spec.validate_save(save)))

    def test_duplicate_role(self):
        save = self.good()
        save["players"][1]["role"] = save["players"][0]["role"]
        self.assertIn("one_per_role", _failed(spec.validate_save(save)))

    def test_missing_persona_voice(self):
        save = self.good()
        save["players"][0]["persona_voice"] = "  "
        self.assertIn("starters_have_voice", _failed(spec.validate_save(save)))

    def test_malformed_memory_id(self):
        save = self.good()
        save["players"][0]["memory_log"][0]["id"] = "mem:Rook:BadSlug"  # uppercase
        self.assertIn("memory_ids_well_formed", _failed(spec.validate_save(save)))

    def test_duplicate_memory_id(self):
        save = self.good()
        first = save["players"][0]["memory_log"][0]["id"]
        save["players"][0]["memory_log"][1]["id"] = first
        self.assertIn("memory_ids_unique", _failed(spec.validate_save(save)))

    def test_memory_owner_mismatch(self):
        save = self.good()
        # Move one of rook's memories into vex's log unchanged -> owner mismatch.
        stolen = save["players"][0]["memory_log"].pop()
        save["players"][1]["memory_log"].append(stolen)
        self.assertIn("memory_owner_matches_log", _failed(spec.validate_save(save)))

    def test_too_few_memories(self):
        save = self.good()
        for player in save["players"]:
            player["memory_log"] = player["memory_log"][:1]
        self.assertIn("memory_count", _failed(spec.validate_save(save)))

    def test_invalid_memory_kind(self):
        save = self.good()
        save["players"][0]["memory_log"][0]["kind"] = "gossip"
        self.assertIn("memory_kinds_valid", _failed(spec.validate_save(save)))

    def test_starter_without_clash(self):
        save = self.good()
        orphan = save["players"][2]["id"]
        save["clash_pairs"] = [c for c in save["clash_pairs"] if orphan not in (c["a"], c["b"])]
        result = spec.validate_save(save)
        self.assertIn("every_starter_clashes", _failed(result))

    def test_too_many_rivals(self):
        save = self.good()
        extra = copy.deepcopy(save["rivals"][0])
        extra["id"] = "extra_org"
        extra["name"] = "Extra Org"
        save["rivals"].append(extra)  # 7 -> out of [5, 6]
        self.assertIn("rival_archetype_count", _failed(spec.validate_save(save)))

    def test_missing_scoreline(self):
        save = self.good()
        save["last_week"].pop("scoreline")
        self.assertIn("last_week_scoreline", _failed(spec.validate_save(save)))

    def test_empty_feed(self):
        save = self.good()
        save["last_week"]["chirper_feed"] = []
        self.assertIn("last_week_feed", _failed(spec.validate_save(save)))

    def test_dangling_cite(self):
        save = self.good()
        save["last_week"]["chirper_feed"][0]["cites"] = ["mem:rook:does_not_exist"]
        self.assertIn("cites_resolve", _failed(spec.validate_save(save)))

    def test_tone_not_locked(self):
        save = self.good()
        save["save"]["tone"] = "earnest"
        self.assertIn("tone_locked", _failed(spec.validate_save(save)))

    def test_flavor_not_locked(self):
        save = self.good()
        save["save"]["game"] = "Generic Shooter"
        self.assertIn("flavor_locked", _failed(spec.validate_save(save)))


if __name__ == "__main__":
    unittest.main()
