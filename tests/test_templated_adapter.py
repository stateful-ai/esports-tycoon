"""The templated content backend: deterministic, zero-API, grounded, in-tone.

The acceptance bar for this backend has four parts, each tested directly:

* It renders the three M0 kinds — ``chirper_post``, ``narration``,
  ``halftime_ack`` — from a real :class:`WorldState` + :class:`WhyRecord`.
* It makes **zero API calls**: asserted statically (the module imports no client,
  no network) and dynamically (rendering succeeds with the LLM client booby-
  trapped to explode if touched).
* It is **deterministic**: identical context always yields identical content,
  while different matches/authors still read differently.
* Every cite it emits **resolves** against the canned log (grounding "ok"), and
  the narrator honours the dry-mockumentary tone (no emoji, no hype).
"""

import ast
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import GenerationContext, generate_content  # noqa: E402
from esports_tycoon.content import game_llm, templated  # noqa: E402
from esports_tycoon.schema import Decisions, GeneratedContent  # noqa: E402

_TEMPLATED_SRC = pathlib.Path(templated.__file__)
_HEART_HANDS = "\U0001faf6"


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        cls.starters = [p.id for p in cls.world.players]


class TestRendersThreeKinds(_Fixture):
    def test_narration(self):
        dec = Decisions(opponent="northwind", map="Helix")
        why = resolver.run(self.world, dec, 7)
        gc = generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec))
        self.assertIsInstance(gc, GeneratedContent)
        self.assertEqual(gc.kind, "narration")
        self.assertIsNone(gc.author)
        self.assertIn("Overcast", gc.text)
        self.assertTrue(gc.text)

    def test_chirper_post_for_each_starter(self):
        dec = Decisions(opponent="northwind")
        why = resolver.run(self.world, dec, 7)
        for pid in self.starters:
            gc = generate_content("chirper_post", GenerationContext(world=self.world, why=why, author=pid))
            self.assertEqual(gc.kind, "chirper_post")
            player = next(p for p in self.world.players if p.id == pid)
            self.assertEqual(gc.author, player.handle)
            self.assertTrue(gc.text)

    def test_halftime_ack_reads_the_scoreline(self):
        up = generate_content(
            "halftime_ack",
            GenerationContext(world=self.world, halftime_scoreline=(8, 3), second_half_stance="disciplined"),
        )
        down = generate_content(
            "halftime_ack",
            GenerationContext(world=self.world, halftime_scoreline=(3, 8), second_half_stance="aggressive"),
        )
        self.assertEqual(up.kind, "halftime_ack")
        self.assertIn("Up 5", up.text)
        self.assertIn("Down 5", down.text)
        # Defaults to the fielded IGL (Rook) when no author is named.
        igl = next(p for p in self.world.players if p.role.value == "IGL")
        self.assertEqual(up.author, igl.handle)

    def test_chirper_for_external_voice_has_no_persona_or_cite(self):
        dec = Decisions(opponent="sovereign")
        why = resolver.run(self.world, dec, 1)
        gc = generate_content("chirper_post", GenerationContext(world=self.world, why=why, author="@gridcast"))
        self.assertEqual(gc.author, "@gridcast")
        self.assertEqual(gc.cites, [])


class TestZeroApi(_Fixture):
    """Templated mode never reaches for the network — statically and at runtime."""

    def _imports(self) -> set[str]:
        tree = ast.parse(_TEMPLATED_SRC.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    def test_imports_no_client_or_network(self):
        banned = ("openai", "anthropic", "socket", "http", "urllib", "requests", "httpx")
        banned += ("esports_tycoon.content.game_llm", "esports_tycoon.content.llm")
        for module in self._imports():
            for bad in banned:
                self.assertFalse(
                    module == bad or module.startswith(bad + "."),
                    f"templated backend imports {module!r}, which is not zero-API",
                )

    def test_rendering_never_constructs_the_llm_client(self):
        # Booby-trap the LLM client: if the templated path touches it, this blows up.
        def explode():
            raise AssertionError("templated backend must not construct an LLM client")

        original = game_llm.get_llm
        game_llm.get_llm = explode
        try:
            dec = Decisions(opponent="northwind")
            why = resolver.run(self.world, dec, 3)
            generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec))
            generate_content("chirper_post", GenerationContext(world=self.world, why=why, author="vex"))
            generate_content(
                "halftime_ack",
                GenerationContext(world=self.world, halftime_scoreline=(6, 6), second_half_stance="default"),
            )
        finally:
            game_llm.get_llm = original

    def test_outputs_report_zero_cost(self):
        dec = Decisions(opponent="northwind")
        why = resolver.run(self.world, dec, 3)
        gc = generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec))
        self.assertEqual((gc.tokens_in, gc.tokens_out, gc.cost_usd), (0, 0, 0.0))
        self.assertIsNone(gc.raw_llm_output)


class TestDeterminism(_Fixture):
    def test_identical_context_yields_identical_content(self):
        for seed in (0, 1, 7, 42, 99):
            dec = Decisions(opponent="northwind", map="Helix")
            why = resolver.run(self.world, dec, seed)
            for kind, ctx in (
                ("narration", GenerationContext(world=self.world, why=why, decisions=dec)),
                ("chirper_post", GenerationContext(world=self.world, why=why, author="vex")),
                (
                    "halftime_ack",
                    GenerationContext(world=self.world, halftime_scoreline=(why.scoreline), second_half_stance="aggressive"),
                ),
            ):
                first = generate_content(kind, ctx)
                for _ in range(20):
                    self.assertEqual(generate_content(kind, ctx), first)

    def test_content_varies_across_matches(self):
        narrations = set()
        for seed in range(12):
            dec = Decisions(opponent="sovereign", map="Helix")
            why = resolver.run(self.world, dec, seed)
            narrations.add(generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec)).text)
        self.assertGreater(len(narrations), 1, "narration should vary across different matches")

    def test_chirper_varies_across_authors(self):
        dec = Decisions(opponent="northwind")
        why = resolver.run(self.world, dec, 7)
        posts = {
            pid: generate_content("chirper_post", GenerationContext(world=self.world, why=why, author=pid)).text
            for pid in self.starters
        }
        self.assertEqual(len(set(posts.values())), len(posts), f"every starter sounds different: {posts}")


class TestGrounding(_Fixture):
    def test_every_cite_resolves(self):
        for opp in ("northwind", "sovereign", "goblins", "tidewater"):
            for seed in range(8):
                dec = Decisions(opponent=opp, map="Helix")
                why = resolver.run(self.world, dec, seed)
                outputs = [generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec))]
                outputs += [
                    generate_content("chirper_post", GenerationContext(world=self.world, why=why, author=pid))
                    for pid in self.starters
                ]
                for gc in outputs:
                    self.assertEqual(gc.grounding_status, "ok")
                    for cite in gc.cites:
                        self.assertIsNotNone(self.world.resolve_cite(cite), f"dangling cite {cite}")

    def test_chirper_cites_the_authors_own_memory(self):
        dec = Decisions(opponent="northwind")
        why = resolver.run(self.world, dec, 7)
        for pid in self.starters:
            gc = generate_content("chirper_post", GenerationContext(world=self.world, why=why, author=pid))
            for cite in gc.cites:
                self.assertTrue(cite.startswith(f"mem:{pid}:"), f"{pid} cited someone else's memory: {cite}")

    def test_narration_cites_a_precedent_for_a_keyed_beat(self):
        # Seed 7 vs Northwind yields an ace; narration should ground it in a real
        # ace/clutch precedent from a fielded player.
        dec = Decisions(opponent="northwind", map="Helix")
        why = resolver.run(self.world, dec, 7)
        self.assertTrue(any(m.kind in ("ace", "choke", "clutch") for m in why.key_moments))
        gc = generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec))
        self.assertTrue(gc.cites, "a narration with a keyed beat should cite a precedent")


class TestTone(_Fixture):
    """Narrator stays dry; characters keep their authored register."""

    def test_narrator_never_uses_emoji_or_hype(self):
        for opp in ("northwind", "sovereign", "goblins"):
            for seed in range(8):
                dec = Decisions(opponent=opp, map="Terminus")
                why = resolver.run(self.world, dec, seed)
                text = generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec)).text
                self.assertNotIn("!", text)
                self.assertNotIn(_HEART_HANDS, text)

    def test_halftime_is_flat(self):
        for stance in ("disciplined", "aggressive", "default"):
            for score in ((9, 3), (3, 9), (6, 6)):
                text = generate_content(
                    "halftime_ack",
                    GenerationContext(world=self.world, halftime_scoreline=score, second_half_stance=stance),
                ).text
                self.assertNotIn("!", text)
                self.assertNotIn(_HEART_HANDS, text)

    def test_sable_is_terse_and_pixie_is_sincere(self):
        dec = Decisions(opponent="northwind")
        why = resolver.run(self.world, dec, 7)
        sable = generate_content("chirper_post", GenerationContext(world=self.world, why=why, author="sable")).text
        # The sentinel answers in a word or two; never a paragraph.
        self.assertLessEqual(len(sable.split()), 4)
        # Pixie is allowed emoji in-character; over a few matches she uses it.
        pixie_posts = {
            generate_content(
                "chirper_post",
                GenerationContext(world=self.world, why=resolver.run(self.world, dec, s), author="pixie"),
            ).text
            for s in range(6)
        }
        self.assertTrue(any(_HEART_HANDS in post for post in pixie_posts))


class TestContextRequirements(_Fixture):
    def test_narration_requires_why_and_decisions(self):
        dec = Decisions(opponent="northwind")
        why = resolver.run(self.world, dec, 1)
        with self.assertRaises(ValueError):
            generate_content("narration", GenerationContext(world=self.world, decisions=dec))
        with self.assertRaises(ValueError):
            generate_content("narration", GenerationContext(world=self.world, why=why))

    def test_chirper_requires_author(self):
        why = resolver.run(self.world, Decisions(opponent="northwind"), 1)
        with self.assertRaises(ValueError):
            generate_content("chirper_post", GenerationContext(world=self.world, why=why))

    def test_halftime_requires_scoreline_and_stance(self):
        with self.assertRaises(ValueError):
            generate_content("halftime_ack", GenerationContext(world=self.world, second_half_stance="default"))
        with self.assertRaises(ValueError):
            generate_content("halftime_ack", GenerationContext(world=self.world, halftime_scoreline=(5, 5)))

    def test_unsupported_kind_is_rejected(self):
        why = resolver.run(self.world, Decisions(opponent="northwind"), 1)
        with self.assertRaises(ValueError) as cm:
            generate_content("interview", GenerationContext(world=self.world, why=why, author="rook"))
        self.assertIn("interview", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
