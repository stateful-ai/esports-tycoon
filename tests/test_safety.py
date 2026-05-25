"""The safety filter: blocks slurs, real-person impersonation, targeted harassment.

Proves the pre/post filter holds against the adversarial seed corpus (including
realistic obfuscation) while letting clean, in-character chatter through — the
false-positive side matters as much as the false-negative side for a dry-comedy
feed that trades in trash talk.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import safety  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402


class TestAdversarialCorpus(unittest.TestCase):
    """Every seeded attack is blocked, and attributed to the right category."""

    def test_every_seed_is_blocked_with_its_category(self):
        for category, seeds in safety.ADVERSARIAL_SEED_CORPUS.items():
            for seed in seeds:
                with self.subTest(category=category, seed=seed):
                    verdict = safety.screen(seed)
                    self.assertFalse(verdict.ok, f"slipped through: {seed!r}")
                    self.assertIn(category, verdict.categories)
                    self.assertTrue(verdict.matches)

    def test_corpus_covers_all_three_categories(self):
        self.assertEqual(set(safety.ADVERSARIAL_SEED_CORPUS), set(safety.CATEGORIES))


class TestObfuscationResistance(unittest.TestCase):
    """The matcher defeats the spellings adversaries actually use."""

    def test_leetspeak_is_folded(self):
        self.assertFalse(safety.is_safe("n1gg3r"))
        self.assertFalse(safety.is_safe("f4gg0t"))

    def test_spacing_and_punctuation_are_rejoined(self):
        self.assertFalse(safety.is_safe("n i g g e r"))
        self.assertFalse(safety.is_safe("k.y.s right now"))

    def test_character_stretching_is_collapsed(self):
        self.assertFalse(safety.is_safe("niiigger"))
        self.assertFalse(safety.is_safe("goooo die"))

    def test_case_and_accents_are_normalised(self):
        self.assertFalse(safety.is_safe("KYS"))
        self.assertFalse(safety.is_safe("KÍLL yourself"))


class TestCategories(unittest.TestCase):
    def test_real_person_impersonation(self):
        self.assertIn("impersonation", safety.screen("this is the real TenZ").categories)
        self.assertIn("impersonation", safety.screen("I played for Riot Games").categories)

    def test_targeted_harassment(self):
        self.assertIn("harassment", safety.screen("kill yourself").categories)
        self.assertIn("harassment", safety.screen("nobody would miss you").categories)

    def test_multiple_categories_in_one_text(self):
        verdict = safety.screen("kys you faggot")
        self.assertFalse(verdict.ok)
        self.assertIn("slur", verdict.categories)
        self.assertIn("harassment", verdict.categories)


class TestCleanContentPasses(unittest.TestCase):
    """In-character chatter — and words that merely contain a substring — pass."""

    CLEAN = [
        "held. won. hungry.",
        "we ran the default. it worked.",
        "esports tycoon",  # contains "coon" — must NOT trip
        "keep it simple, we go again",  # "s1mple" folds to a clean word; not listed
        "don't let it faze you",  # "faze" is a plausible word, deliberately not listed
        "Sable is our sentinel and he holds site",  # role word, not the org "Sentinels"
        "we scrimmed Apex Foundry on Helix",  # in-universe org, not "Apex Legends"
        "the realist take I've seen all split",  # "the real" must need a claim prefix
        "I'm the IGL, back to work",
        "assassin pick on the lurk",  # contains "ass"; not a listed term
    ]

    def test_curated_clean_lines_pass(self):
        for line in self.CLEAN:
            with self.subTest(line=line):
                self.assertTrue(safety.is_safe(line), f"false positive on {line!r}")

    def test_canned_chirper_feed_is_clean(self):
        world = loader.load()
        for post in world.last_week.chirper_feed:
            with self.subTest(post=post.id):
                self.assertTrue(safety.is_safe(post.text), f"feed post flagged: {post.text!r}")

    def test_persona_voice_prompts_are_clean(self):
        world = loader.load()
        for player in world.players:
            with self.subTest(player=player.id):
                self.assertTrue(safety.is_safe(player.persona_voice))


class TestVerdictShape(unittest.TestCase):
    def test_clean_verdict_is_empty(self):
        verdict = safety.screen("good map. back to work.")
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.categories, [])
        self.assertEqual(verdict.matches, [])

    def test_empty_and_whitespace_are_safe(self):
        self.assertTrue(safety.is_safe(""))
        self.assertTrue(safety.is_safe("   \n\t "))

    def test_categories_are_deduped_but_matches_are_not(self):
        # Two harassment phrases -> one category, two matches.
        verdict = safety.screen("go die. you should die.")
        self.assertEqual(verdict.categories, ["harassment"])
        self.assertGreaterEqual(len(verdict.matches), 2)


if __name__ == "__main__":
    unittest.main()
