"""The real saves/week6.yaml must meet the M0.0 acceptance bar."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.cast_lock import spec  # noqa: E402


class TestWeek6Save(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.save = spec.load_save(spec.DEFAULT_SAVE_PATH)
        cls.result = spec.validate_save(cls.save)

    def test_passes_full_acceptance_bar(self):
        failures = [f"{c.name}: {c.detail}" for c in self.result.failures]
        self.assertTrue(self.result.ok, "acceptance checks failed:\n" + "\n".join(failures))

    def test_five_named_starters_one_per_role(self):
        players = self.save["players"]
        self.assertEqual(len(players), spec.REQUIRED_STARTERS)
        roles = sorted(p["role"] for p in players)
        self.assertEqual(roles, sorted(spec.VALID_ROLES))
        for p in players:
            self.assertTrue(p["name"].strip())
            self.assertTrue(p["persona_voice"].strip())

    def test_six_rival_archetypes(self):
        rivals = self.save["rivals"]
        self.assertEqual(len(rivals), 6)
        for r in rivals:
            self.assertTrue(r["archetype"].strip())

    def test_at_least_thirty_memories(self):
        entries = spec._all_memory_entries(self.save)
        self.assertGreaterEqual(len(entries), spec.MIN_MEMORIES)

    def test_canonical_memory_id_present(self):
        ids = {e["id"] for e in spec._all_memory_entries(self.save)}
        self.assertIn("mem:rook:scrim_w5_choke", ids)

    def test_memory_ids_unique_and_well_formed(self):
        ids = [e["id"] for e in spec._all_memory_entries(self.save)]
        self.assertEqual(len(ids), len(set(ids)), "memory IDs must be unique")
        for mem_id in ids:
            self.assertRegex(mem_id, spec.MEMORY_ID_RE)

    def test_every_starter_appears_in_a_clash_pair(self):
        starter_ids = {p["id"] for p in self.save["players"]}
        clashed = set()
        for pair in self.save["clash_pairs"]:
            clashed.update({pair["a"], pair["b"]} & starter_ids)
        self.assertEqual(clashed, starter_ids)

    def test_last_week_scoreline_and_feed_present(self):
        last_week = self.save["last_week"]
        self.assertIn("scoreline", last_week)
        self.assertGreaterEqual(len(last_week["scoreline"]["maps"]), 1)
        self.assertGreaterEqual(len(last_week["chirper_feed"]), 1)


if __name__ == "__main__":
    unittest.main()
