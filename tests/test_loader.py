"""The canned-save loader returns a typed WorldState and round-trips losslessly."""

import copy
import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.schema import MemoryEntry, WorldState  # noqa: E402


class TestLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        cls.world = loader.load()

    def test_load_returns_worldstate(self):
        self.assertIsInstance(self.world, WorldState)
        self.assertEqual(len(self.world.players), 5)
        self.assertEqual(self.world.save.tone, "dry-mockumentary")

    def test_load_accepts_path_argument(self):
        world = loader.load(loader.DEFAULT_SAVE_PATH)
        self.assertEqual(world, self.world)

    def test_load_rejects_non_mapping(self):
        tmp = pathlib.Path(self.id() + ".yaml")
        try:
            tmp.write_text("- just\n- a\n- list\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                loader.load(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_file_round_trip_is_lossless(self):
        # The typed dump reproduces the parsed YAML exactly: nothing dropped,
        # nothing invented. This is the round-trip the acceptance bar requires.
        self.assertEqual(loader.to_save_dict(self.world), self.raw)

    def test_yaml_round_trip_reloads_equal(self):
        # Dump back to YAML, reload, and the typed world is identical.
        world2 = WorldState.model_validate(yaml.safe_load(loader.dumps(self.world)))
        self.assertEqual(world2, self.world)

    def test_omitted_empty_collection_is_not_reinjected(self):
        # Regression: the save omits empty collections rather than spelling them
        # as `[]`. A naive `exclude_none` dump would load an omitted `tags` to
        # `[]` and re-inject it, breaking the round-trip. `exclude_defaults` must
        # keep an omitted-empty field omitted on the way back out.
        raw = copy.deepcopy(self.raw)
        entry = raw["players"][0]["memory_log"][0]
        entry.pop("tags", None)  # author left an entry with no tags
        self.assertNotIn("tags", entry)

        dumped = loader.to_save_dict(WorldState.model_validate(raw))
        self.assertNotIn("tags", dumped["players"][0]["memory_log"][0])
        self.assertEqual(dumped, raw)

    def test_save_omits_empty_collections(self):
        # Guards the authoring convention the round-trip relies on: the real save
        # never spells an empty collection as `[]` (which `exclude_defaults`
        # would drop, desyncing the dump from the file).
        def empty_lists(node, path="root"):
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(value, list) and not value:
                        yield f"{path}.{key}"
                    else:
                        yield from empty_lists(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    yield from empty_lists(value, f"{path}[{i}]")

        self.assertEqual(list(empty_lists(self.raw)), [])

    def test_stable_cite_ids_resolve(self):
        # Every cite that appears anywhere resolves to a real memory entry, and
        # resolution returns the typed entry (the renderer's grounding hook).
        entry = self.world.resolve_cite("mem:rook:scrim_w5_choke")
        self.assertIsInstance(entry, MemoryEntry)
        self.assertEqual(entry.kind, "scrim")
        self.assertEqual(len(self.world.memory_ids), 37)
        self.assertEqual(set(self.world.cite_index), self.world.memory_ids)

    def test_unknown_cite_resolves_to_none(self):
        self.assertIsNone(self.world.resolve_cite("mem:rook:does_not_exist"))

    def test_every_feed_and_clash_cite_is_grounded(self):
        known = self.world.memory_ids
        for pair in self.world.clash_pairs:
            for cite in pair.seeded_by:
                self.assertIn(cite, known)
        for rival in self.world.rivals:
            for cite in rival.seeded_by:
                self.assertIn(cite, known)
        for post in self.world.last_week.chirper_feed:
            for cite in post.cites:
                self.assertIn(cite, known)

    def test_loader_rejects_dangling_cite(self):
        bad = copy.deepcopy(self.raw)
        bad["last_week"]["chirper_feed"][0]["cites"] = ["mem:rook:nope"]
        with self.assertRaises(ValueError):
            WorldState.model_validate(bad)


if __name__ == "__main__":
    unittest.main()
