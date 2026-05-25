"""The adapter seam: one ``generate_content`` interface, a flag-selected backend.

Covers the routing contract, the config flag (env-driven, ``templated`` default),
and the architectural invariant that the resolver never imports the adapter.
"""

import ast
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import (  # noqa: E402
    BACKEND_ENV_VAR,
    ContentConfig,
    GenerationContext,
    config_from_env,
    generate_content,
)
from esports_tycoon.content import adapter, llm  # noqa: E402
from esports_tycoon.schema import Decisions, GeneratedContent  # noqa: E402


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        cls.decisions = Decisions(opponent="northwind", map="Helix")
        cls.why = resolver.run(cls.world, cls.decisions, 7)

    def ctx(self):
        return GenerationContext(world=self.world, why=self.why, decisions=self.decisions, author="vex")


class _FakeLLM:
    """A stand-in for the gaming-pack client: records calls, returns canned JSON."""

    def __init__(self, text="canned.", cites=None):
        self.text, self.cites = text, list(cites or [])
        self.calls = []

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return schema.model_validate({"text": self.text, "cites": self.cites})


class TestConfigFlag(unittest.TestCase):
    def test_default_is_templated_zero_api(self):
        self.assertEqual(config_from_env({}).backend, "templated")

    def test_flag_selects_backend(self):
        self.assertEqual(config_from_env({BACKEND_ENV_VAR: "vllm"}).backend, "vllm")
        self.assertEqual(config_from_env({BACKEND_ENV_VAR: "templated"}).backend, "templated")

    def test_flag_is_normalised(self):
        self.assertEqual(config_from_env({BACKEND_ENV_VAR: "  VLLM  "}).backend, "vllm")

    def test_unknown_backend_fails_loudly(self):
        with self.assertRaises(ValueError):
            config_from_env({BACKEND_ENV_VAR: "anthropic"})
        with self.assertRaises(ValueError):
            ContentConfig(backend="gpt")


class TestRouting(_Fixture):
    def test_single_interface_returns_generated_content(self):
        gc = generate_content("narration", GenerationContext(world=self.world, why=self.why, decisions=self.decisions))
        self.assertIsInstance(gc, GeneratedContent)

    def test_default_config_routes_to_templated(self):
        # No config, no client, and the LLM is booby-trapped: a render that
        # succeeds proves the default never left the templated path.
        original = llm.game_llm.get_llm
        llm.game_llm.get_llm = lambda: (_ for _ in ()).throw(AssertionError("default must be zero-API"))
        try:
            gc = generate_content("chirper_post", self.ctx())
        finally:
            llm.game_llm.get_llm = original
        self.assertEqual(gc.grounding_status, "ok")

    def test_vllm_backend_routes_through_the_client(self):
        fake = _FakeLLM(text="held. won.", cites=[])
        gc = generate_content("chirper_post", self.ctx(), config=ContentConfig(backend="vllm"), client=fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(gc.text, "held. won.")

    def test_vllm_without_client_uses_the_env_default_client(self):
        fake = _FakeLLM(text="from default client.")
        original = llm.game_llm.get_llm
        llm.game_llm.get_llm = lambda: fake
        try:
            gc = generate_content("narration", GenerationContext(world=self.world, why=self.why, decisions=self.decisions), config=ContentConfig(backend="vllm"))
        finally:
            llm.game_llm.get_llm = original
        self.assertEqual(gc.text, "from default client.")
        self.assertEqual(len(fake.calls), 1)

    def test_backends_agree_on_kind_and_author(self):
        fake = _FakeLLM(text="x")
        for kind, ctx in (
            ("narration", GenerationContext(world=self.world, why=self.why, decisions=self.decisions)),
            ("chirper_post", self.ctx()),
            (
                "halftime_ack",
                GenerationContext(world=self.world, halftime_scoreline=(7, 5), second_half_stance="aggressive"),
            ),
        ):
            templated_out = generate_content(kind, ctx)
            vllm_out = generate_content(kind, ctx, config=ContentConfig(backend="vllm"), client=fake)
            self.assertEqual(templated_out.kind, vllm_out.kind)
            self.assertEqual(templated_out.author, vllm_out.author)


class TestResolverNeverImportsAdapter(unittest.TestCase):
    """Rule #1 of the architecture: generation can't leak into the deterministic sim."""

    def _imports(self, module_path: pathlib.Path) -> set[str]:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    def test_resolver_does_not_import_the_content_package(self):
        imports = self._imports(pathlib.Path(resolver.__file__))
        offenders = {m for m in imports if m == "esports_tycoon.content" or m.startswith("esports_tycoon.content.")}
        self.assertEqual(offenders, set(), f"resolver must not import the adapter: {offenders}")

    def test_adapter_depends_on_the_resolver_output_only_through_the_schema(self):
        # The adapter sees WhyRecord (via the context) but not resolver.run — the
        # dependency is on the data contract, not the sim.
        imports = self._imports(pathlib.Path(adapter.__file__))
        self.assertNotIn("esports_tycoon.resolver", imports)


if __name__ == "__main__":
    unittest.main()
