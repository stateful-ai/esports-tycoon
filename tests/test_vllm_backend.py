"""The vllm backend: the gaming-pack client wired behind the adapter seam.

These prove the wiring without a live endpoint, by passing a duck-typed client:

* The vendored ``game_llm`` is the pack client and imports **lazily** — importing
  the backend needs no ``openai`` install and makes no connection.
* Each kind sends the persona/tone as the system prompt, asks for the structured
  ``{text, cites}`` shape, and respects the per-kind token budget.
* Cites are grounded on the way back: real ones are kept, invented ones dropped,
  and ``grounding_status`` reflects which happened — so the output never carries a
  cite that doesn't resolve.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import GenerationContext  # noqa: E402
from esports_tycoon.content import game_llm, llm  # noqa: E402
from esports_tycoon.schema import Decisions  # noqa: E402


class _RecordingLLM:
    """A duck-typed ``game_llm.GameLLM``: records the call, returns canned JSON."""

    def __init__(self, text="canned line.", cites=None):
        self.text, self.cites = text, list(cites or [])
        self.calls = []

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.calls.append({"prompt": prompt, "schema": schema, "system": system, "max_tokens": max_tokens})
        return schema.model_validate({"text": self.text, "cites": self.cites})


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        cls.decisions = Decisions(opponent="northwind", map="Helix")
        cls.why = resolver.run(cls.world, cls.decisions, 7)


class TestPackClientWiring(_Fixture):
    def test_game_llm_imports_without_openai_installed(self):
        # The pack client imports openai lazily (inside __init__), so importing the
        # backend never requires the dep or a network — only constructing a real
        # client would. We exercise the import path and the module surface.
        self.assertTrue(hasattr(game_llm, "GameLLM"))
        self.assertTrue(hasattr(game_llm, "get_llm"))
        self.assertTrue(callable(game_llm.extract_json))

    def test_pack_env_defaults_are_intact(self):
        # The backend relies on the pack's OpenAI-compatible, env-configured
        # defaults being unchanged (the file is vendored verbatim).
        self.assertEqual(game_llm._DEFAULTS["GAME_LLM_BASE_URL"], "http://localhost:8000/v1")
        self.assertEqual(game_llm._DEFAULTS["GAME_LLM_MODEL"], "qwen2.5-7b-instruct")
        self.assertEqual(game_llm._DEFAULTS["GAME_LLM_API_KEY"], "local")

    def test_token_budgets_match_the_plan(self):
        self.assertEqual(llm.MAX_TOKENS, {"chirper_post": 80, "narration": 320, "halftime_ack": 200})


class TestExtractJson(unittest.TestCase):
    """``extract_json`` returns the first complete object, ignoring trailing junk."""

    def test_plain_object(self):
        self.assertEqual(game_llm.extract_json('{"text": "hi", "cites": []}'), {"text": "hi", "cites": []})

    def test_object_then_prose_is_not_glued_into_an_invalid_blob(self):
        raw = '{"text": "hi", "cites": []}\n\nHope that helps!'
        self.assertEqual(game_llm.extract_json(raw), {"text": "hi", "cites": []})

    def test_trailing_second_object_is_ignored(self):
        raw = '{"text": "first"}\n{"text": "second"}'
        self.assertEqual(game_llm.extract_json(raw), {"text": "first"})

    def test_code_fence_and_leading_prose(self):
        raw = 'Sure:\n```json\n{"text": "hi"}\n```'
        self.assertEqual(game_llm.extract_json(raw), {"text": "hi"})

    def test_nested_object_is_kept_whole(self):
        raw = 'noise {"a": {"b": 1}} more {"c": 2}'
        self.assertEqual(game_llm.extract_json(raw), {"a": {"b": 1}})

    def test_skips_a_broken_object_to_reach_a_valid_one(self):
        raw = "{not json} then {\"text\": \"ok\"}"
        self.assertEqual(game_llm.extract_json(raw), {"text": "ok"})

    def test_no_object_returns_none(self):
        self.assertIsNone(game_llm.extract_json("just prose, no json here"))
        self.assertIsNone(game_llm.extract_json(""))

    def test_non_dict_json_is_skipped(self):
        self.assertIsNone(game_llm.extract_json("[1, 2, 3]"))


class TestPromptConstruction(_Fixture):
    def test_chirper_sends_persona_and_budget_and_schema(self):
        client = _RecordingLLM()
        rook = next(p for p in self.world.players if p.id == "rook")
        gc = llm.generate(
            "chirper_post",
            GenerationContext(world=self.world, why=self.why, author="rook", decisions=self.decisions),
            client=client,
        )
        call = client.calls[0]
        self.assertEqual(call["max_tokens"], 80)
        self.assertEqual(call["schema"].__name__, "_LLMReply")
        self.assertIn(rook.persona_voice.strip()[:20], call["system"])  # the player's voice contract
        self.assertIn("@rooktanaka", call["system"])
        self.assertIn("Your local match outcome: carried.", call["prompt"])
        self.assertEqual(gc.author, rook.handle)

    def test_narration_uses_narrator_voice_and_offers_a_cite_menu(self):
        client = _RecordingLLM()
        gc = llm.generate(
            "narration",
            GenerationContext(world=self.world, why=self.why, decisions=self.decisions),
            client=client,
        )
        call = client.calls[0]
        self.assertEqual(call["max_tokens"], 320)
        self.assertIn("narrator", call["system"].lower())
        # The cite menu lists real, resolvable memory IDs from fielded players.
        self.assertIn("mem:", call["prompt"])
        self.assertIsNone(gc.author)

    def test_halftime_uses_igl_voice_and_stance(self):
        client = _RecordingLLM()
        igl = next(p for p in self.world.players if p.role.value == "IGL")
        gc = llm.generate(
            "halftime_ack",
            GenerationContext(world=self.world, halftime_scoreline=(4, 8), second_half_stance="aggressive"),
            client=client,
        )
        call = client.calls[0]
        self.assertEqual(call["max_tokens"], 200)
        self.assertIn("aggressive", call["prompt"])
        self.assertEqual(gc.author, igl.handle)


class TestGroundingOnReturn(_Fixture):
    def test_real_cites_are_kept_status_ok(self):
        client = _RecordingLLM(text="we'll review the tape.", cites=["mem:rook:scrim_w5_choke"])
        gc = llm.generate(
            "chirper_post",
            GenerationContext(world=self.world, why=self.why, author="rook"),
            client=client,
        )
        self.assertEqual(gc.cites, ["mem:rook:scrim_w5_choke"])
        self.assertEqual(gc.grounding_status, "ok")

    def test_invented_cites_are_dropped_status_dropped(self):
        client = _RecordingLLM(
            text="remember the playoffs?", cites=["mem:rook:scrim_w5_choke", "mem:rook:invented_event"]
        )
        gc = llm.generate(
            "chirper_post",
            GenerationContext(world=self.world, why=self.why, author="rook"),
            client=client,
        )
        self.assertEqual(gc.cites, ["mem:rook:scrim_w5_choke"])  # only the real one survives
        self.assertEqual(gc.grounding_status, "dropped")
        for cite in gc.cites:
            self.assertIsNotNone(self.world.resolve_cite(cite))

    def test_duplicate_cites_are_collapsed(self):
        client = _RecordingLLM(text="x", cites=["mem:rook:scrim_w5_choke", "mem:rook:scrim_w5_choke"])
        gc = llm.generate(
            "chirper_post",
            GenerationContext(world=self.world, why=self.why, author="rook"),
            client=client,
        )
        self.assertEqual(gc.cites, ["mem:rook:scrim_w5_choke"])

    def test_raw_output_is_retained_for_audit(self):
        client = _RecordingLLM(text="held. won.", cites=[])
        gc = llm.generate(
            "chirper_post",
            GenerationContext(world=self.world, why=self.why, author="sable"),
            client=client,
        )
        self.assertIsNotNone(gc.raw_llm_output)
        self.assertIn("held. won.", gc.raw_llm_output)

    def test_tokens_out_priced_off_completion_not_json_envelope(self):
        # tokens_out must estimate the model's completion (its prose + cites it
        # offered), not the serialized {text, cites} envelope. Pricing the
        # envelope's JSON scaffolding would overstate output tokens and the cost
        # the recap reports. The full envelope is still kept for the audit.
        from esports_tycoon.cost import estimate_tokens

        client = _RecordingLLM(text="we'll review the tape.", cites=["mem:rook:scrim_w5_choke"])
        gc = llm.generate(
            "chirper_post",
            GenerationContext(world=self.world, why=self.why, author="rook"),
            client=client,
        )
        completion = "we'll review the tape. mem:rook:scrim_w5_choke"
        self.assertEqual(gc.tokens_out, estimate_tokens(completion))
        # The envelope (with "text"/"cites" keys, quotes, brackets) is strictly
        # larger, so estimating off it would have over-counted.
        self.assertLess(gc.tokens_out, estimate_tokens(gc.raw_llm_output))

    def test_unsupported_kind_is_rejected(self):
        client = _RecordingLLM()
        with self.assertRaises(ValueError):
            llm.generate("interview", GenerationContext(world=self.world, why=self.why, author="rook"), client=client)


if __name__ == "__main__":
    unittest.main()
