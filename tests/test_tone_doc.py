"""The tone + cast 1-pager pins the locked voice, flavor, cast, and rivals."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.cast_lock import spec  # noqa: E402


class TestToneDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = spec.DEFAULT_DOC_PATH.read_text(encoding="utf-8")
        cls.lower = cls.text.lower()
        cls.save = spec.load_save(spec.DEFAULT_SAVE_PATH)

    def test_exists(self):
        self.assertTrue(spec.DEFAULT_DOC_PATH.exists())

    def test_pins_voice_and_flavor(self):
        self.assertIn("dry mockumentary", self.lower)
        self.assertIn("vector strike", self.lower)
        self.assertIn("valorant", self.lower)

    def test_lists_every_starter(self):
        # The 1-pager references each starter by canonical id (e.g. `rook`) and
        # by surname; both are stable across nickname formatting in the save.
        for player in self.save["players"]:
            self.assertIn(f"`{player['id']}`", self.text, f"starter id missing from 1-pager: {player['id']}")
            surname = player["name"].rstrip('"').split()[-1]
            self.assertIn(surname, self.text, f"starter surname missing from 1-pager: {surname}")

    def test_lists_every_rival_archetype(self):
        for rival in self.save["rivals"]:
            self.assertIn(rival["name"], self.text, f"rival missing from 1-pager: {rival['name']}")
            self.assertIn(rival["archetype"], self.text)

    def test_documents_clash_pairs_section(self):
        self.assertIn("clash pair", self.lower)

    def test_documents_grounding_id_format(self):
        self.assertIn("mem:<player_id>:<event_slug>", self.text)
        self.assertIn("mem:rook:scrim_w5_choke", self.text)

    def test_documents_single_approval_pass(self):
        self.assertIn("batched", self.lower)
        self.assertIn("approve/reject", self.lower)


if __name__ == "__main__":
    unittest.main()
