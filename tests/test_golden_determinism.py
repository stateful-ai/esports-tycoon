"""Golden test that locks the whole week6 ``load → resolve → round-trip`` path,
plus the next hop: the content adapter's templated render for the week-6 slice.

This is the single golden the M0.0 canonical-contract milestone calls for
(``docs`` / ``m0_0_canonical_contract.md``: "lock the whole
load→resolve→round-trip path with a single golden test"). It is deliberately
distinct from the other suites:

* ``test_resolver_determinism.py`` proves the resolver is *internally
  consistent* and *byte-identical run-to-run within one process*. It does not
  pin the actual output, so a change to a tuning constant (which moves every
  outcome the same way) sails through it.
* ``test_loader.py`` proves the save round-trips *losslessly against itself*.
  It does not pin the canonical bytes, so a change to the serializer's style
  could pass while silently re-formatting every save.
* ``test_templated_adapter.py`` proves the templated backend is internally
  deterministic and stays in tone. It does not pin the actual rendered bytes,
  so a re-worded template, a re-ordered variant list, or a tweak to the
  seeded variant-selection RNG would sail through it.

A *golden* closes those gaps: it commits the known-good resolve output, the
known-good canonical save bytes, and the known-good templated render of the
week-6 slice, so **any drift** — a resolver retune, a serializer reformat, a
schema field reorder, a re-worded template, or a change to the variant-picking
seed — trips this test with a reviewable diff. The committed goldens are
verified behaviour: the broader suites above assert that behaviour is correct;
this test freezes it.

When a change to the resolver, serializer, or templated backend is *intended*,
regenerate the goldens with ``UPDATE_GOLDEN=1 python -m pytest
tests/test_golden_determinism.py`` and review the resulting diff before
committing it.
"""

import json
import os
import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import game_llm  # noqa: E402
from esports_tycoon.content.config import ContentConfig  # noqa: E402
from esports_tycoon.runner import SliceConfig, SliceDecisions, run_slice  # noqa: E402
from esports_tycoon.runner.model import SliceResult  # noqa: E402
from esports_tycoon.schema import Decisions, WhyRecord, WorldState  # noqa: E402

# The one fixed fixture + seed this golden pins. tidewater/seed 5 is chosen
# because it exercises a broad cross-section of the resolver in a single record:
# a win that swings, with clutch and ace key moments, both carriers and tilters,
# and a full spread of morale deltas. Drift in any of those branches moves the
# bytes and trips the golden.
_FIXTURE = Decisions(
    opponent="tidewater",
    map="Helix",
    practice_focus="defaults",
    tactical_stance="default",
)
_SEED = 5

_GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"
_RESOLVE_GOLDEN = _GOLDEN_DIR / "week6_resolve.json"
_CANONICAL_GOLDEN = _GOLDEN_DIR / "week6_canonical.yaml"
_CONTENT_GOLDEN = _GOLDEN_DIR / "week6_content.json"

# The canonical week-6 slice: the same fixture and decisions the engine suite
# treats as the reference run. Pinning *this* exercise of the slice means the
# golden covers every templated-render seam at once — narration, half-time ack,
# and a chirper_post for each starter plus a caster and the rival's star — and
# any drift in their seeded variant selection moves the bytes.
_SLICE_CONFIG = SliceConfig(opponent="apex_foundry", map="Helix", seed=6, tactical_stance="default")
_SLICE_DECISIONS = SliceDecisions(
    practice_focus="defaults",
    team_talk="no heroes. run the default.",
    fallout_post="week 6: held the line. on to week 7.",
)

# Set UPDATE_GOLDEN=1 to rewrite the committed goldens after an *intended*
# change; review the diff before committing it.
_UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _canonical_record(record: WhyRecord) -> str:
    """Canonical, diff-stable bytes for a resolved :class:`WhyRecord`.

    ``sort_keys`` makes the form independent of incidental dict ordering, so the
    golden trips on a *value* change (the drift that matters) rather than on a
    map's key order. The trailing newline keeps the committed file POSIX-clean.
    """
    return json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _canonical_slice_content(result: SliceResult) -> str:
    """Canonical, diff-stable bytes for everything the templated adapter rendered.

    Captures the narration, the half-time ack, and the full Chirper feed (each
    starter's reaction plus the external voices), since these are the three
    seams the templated backend produces. The manager's fallout post is verbatim
    user text rather than a render, but it lives in the same feed and is included
    so a re-ordering bug would also trip — the test is "the templated render of
    the week-6 slice", and the slice's feed is what the user sees.

    ``sort_keys`` makes the form independent of incidental dict ordering;
    ``ensure_ascii`` (json default) keeps in-character glyphs (Pixie's heart
    hands) committed as escapes so the file is POSIX-clean text.
    """
    payload = {
        "narration": result.narration.model_dump(mode="json"),
        "halftime": result.halftime.model_dump(mode="json"),
        "halftime_scoreline": list(result.halftime_scoreline),
        "feed": [
            {
                "author_handle": post.author_handle,
                "author_name": post.author_name,
                "text": post.text,
                "cites": list(post.cites),
                "grounding_status": post.grounding_status,
            }
            for post in result.feed
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_or_write_golden(path: pathlib.Path, produced: str) -> str:
    """Return the committed golden for ``path``, (re)writing it under UPDATE_GOLDEN.

    Outside update mode a missing golden is a hard failure — a golden that
    silently materializes on first run would never detect drift.
    """
    if _UPDATE:
        _GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(produced, encoding="utf-8")
    if not path.exists():
        raise AssertionError(
            f"missing golden {path}; regenerate with UPDATE_GOLDEN=1 and commit it"
        )
    return path.read_text(encoding="utf-8")


class TestGoldenDeterminism(unittest.TestCase):
    """One golden over load → resolve → round-trip; fails on any drift."""

    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()  # loads week6.yaml

    # --- resolve -------------------------------------------------------------- #
    def test_resolve_is_byte_identical_across_two_runs(self):
        # The same fixture + seed, resolved twice, is byte-for-byte identical.
        first = _canonical_record(resolver.run(self.world, _FIXTURE, _SEED))
        second = _canonical_record(resolver.run(self.world, _FIXTURE, _SEED))
        self.assertEqual(first, second, "resolver output is not byte-identical run-to-run")

    def test_resolve_matches_committed_golden(self):
        # ...and matches the committed known-good bytes, so a retune is caught.
        produced = _canonical_record(resolver.run(self.world, _FIXTURE, _SEED))
        golden = _read_or_write_golden(_RESOLVE_GOLDEN, produced)
        self.assertEqual(
            produced,
            golden,
            "resolve output drifted from the committed golden; if intended, "
            "regenerate with UPDATE_GOLDEN=1 and review the diff",
        )

    # --- round-trip ----------------------------------------------------------- #
    def test_round_trip_is_lossless_against_the_save(self):
        # dump(load(week6.yaml)) reproduces the parsed save exactly: the typed
        # dump drops nothing and invents nothing.
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(loader.to_save_dict(self.world), raw)

    def test_round_trip_normalizes_to_committed_canonical_bytes(self):
        # The canonical serializer's exact output is pinned, so a reformat is
        # caught even when it leaves the parsed data unchanged. This is the
        # byte-identity assertion on ``dump(load(week6.yaml))`` that the
        # ``saves/SCHEMA.md`` **Byte-identity normalization** contract calls
        # for: a reordered key, a re-padded float mantissa, a dropped trailing
        # newline, or an escaped unicode glyph would each flip these bytes.
        canonical = loader.dumps(self.world)
        golden = _read_or_write_golden(_CANONICAL_GOLDEN, canonical)
        self.assertEqual(
            canonical,
            golden,
            "canonical save bytes drifted from the committed golden; if intended, "
            "regenerate with UPDATE_GOLDEN=1 and review the diff",
        )

    def test_round_trip_is_an_idempotent_fixed_point(self):
        # dump(load(x)) normalizes back to x: reloading the canonical bytes and
        # re-dumping yields the identical bytes, and the reloaded world is equal.
        canonical = loader.dumps(self.world)
        world2 = WorldState.model_validate(yaml.safe_load(canonical))
        self.assertEqual(world2, self.world)
        self.assertEqual(loader.dumps(world2), canonical)


class TestGoldenTemplatedRender(unittest.TestCase):
    """One golden over the templated render of the week-6 slice.

    Sibling to the resolve/round-trip suite above: that one freezes the
    load → resolve → round-trip hop; this one freezes the *next* hop, the
    content adapter's templated render. Two same-seed runs of ``run_slice``
    must yield byte-identical content — narration, half-time ack, and every
    Chirper post (each driven by seeded variant selection) — and that content
    must match the committed bytes, so any drift in a template, a variant
    list's order, or the per-call RNG seed trips here with a reviewable diff.

    The slice is played with an explicit ``ContentConfig(backend="templated")``
    so the test stays pinned to the zero-API path regardless of the ambient
    ``ESPORTS_TYCOON_CONTENT_BACKEND`` env var, and the templated render's
    "constructs no LLM client" promise is enforced inline by booby-trapping
    ``game_llm.get_llm`` — a regression that quietly routed through the LLM
    backend would otherwise still pass byte-equality on a cached endpoint.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()  # loads week6.yaml

    def _run(self) -> SliceResult:
        # Templated backend is pinned explicitly; injecting a client would be a
        # vllm-only knob, so it stays at the default ``None`` here.
        return run_slice(
            self.world,
            _SLICE_CONFIG,
            _SLICE_DECISIONS,
            content_config=ContentConfig(backend="templated"),
        )

    def test_templated_render_is_byte_identical_across_two_runs(self):
        # Same world + same slice config + same decisions, played twice in one
        # process, produces byte-for-byte identical templated content.
        first = _canonical_slice_content(self._run())
        second = _canonical_slice_content(self._run())
        self.assertEqual(
            first,
            second,
            "templated render is not byte-identical across two same-seed runs of the week-6 slice",
        )

    def test_templated_render_matches_committed_golden(self):
        # ...and matches the committed known-good bytes, so a re-worded template
        # or a re-tuned variant-selection RNG is caught.
        produced = _canonical_slice_content(self._run())
        golden = _read_or_write_golden(_CONTENT_GOLDEN, produced)
        self.assertEqual(
            produced,
            golden,
            "templated render drifted from the committed golden; if intended, "
            "regenerate with UPDATE_GOLDEN=1 and review the diff",
        )

    def test_templated_render_never_constructs_the_llm_client(self):
        # Byte-equality alone wouldn't catch a templated → vllm misroute if the
        # LLM happened to return the same text; explicitly booby-trap the client
        # so any construction attempt is a hard failure.
        def explode():
            raise AssertionError("templated golden must not construct an LLM client")

        original = game_llm.get_llm
        game_llm.get_llm = explode
        try:
            produced = _canonical_slice_content(self._run())
        finally:
            game_llm.get_llm = original
        # And the bytes still match the committed golden under the trap.
        golden = _read_or_write_golden(_CONTENT_GOLDEN, produced)
        self.assertEqual(produced, golden)


if __name__ == "__main__":
    unittest.main()
