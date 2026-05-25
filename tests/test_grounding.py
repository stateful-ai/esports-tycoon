"""The grounding resolver: parse cites, resolve, regen up to N, then drop.

Covers the cite parser, the resolve split, and the regen loop's three terminal
states (ok / regen / dropped) plus its hooks — the ``accept`` predicate (used by
the gate for safety) and the per-attempt ``on_attempt`` hook (used by the gate for
cost), including that an exception raised there propagates out and halts the loop.
"""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import grounding  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.schema import GeneratedContent  # noqa: E402

REAL = "mem:rook:scrim_w5_choke"
REAL_2 = "mem:vex:ace_helix_w1"
FAKE = "mem:rook:not_a_real_event"
MALFORMED = "mem:rook"  # not a valid cite token at all


def content(text="x", *, cites=None, raw_cites=None, tin=10, tout=10):
    """Build a GeneratedContent; ``raw_cites`` simulates an LLM's offered cites."""
    raw = None
    if raw_cites is not None:
        raw = json.dumps({"text": text, "cites": raw_cites})
    return GeneratedContent(
        kind="chirper_post",
        text=text,
        grounding_status="ok",
        cites=list(cites or []),
        raw_llm_output=raw,
        tokens_in=tin,
        tokens_out=tout,
    )


def scripted(*items):
    """A zero-arg generate() that yields each item in turn, then repeats the last."""
    seq = list(items)

    def gen():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return gen


class TestParseCites(unittest.TestCase):
    def test_finds_inline_tokens_in_order_deduped(self):
        text = f"like {REAL}, and again {REAL}, plus {REAL_2}."
        self.assertEqual(grounding.parse_cites(text), [REAL, REAL_2])

    def test_ignores_malformed_tokens(self):
        self.assertEqual(grounding.parse_cites("see mem:rook and memory_5"), [])

    def test_empty_text(self):
        self.assertEqual(grounding.parse_cites(""), [])


class TestOfferedCites(unittest.TestCase):
    def test_from_raw_llm_output_including_malformed(self):
        gc = content(raw_cites=[REAL, FAKE, MALFORMED])
        self.assertEqual(grounding.offered_cites(gc), [REAL, FAKE, MALFORMED])

    def test_merges_inline_and_kept_cites_deduped(self):
        gc = content(text=f"echoing {REAL_2}", cites=[REAL], raw_cites=[REAL])
        self.assertEqual(grounding.offered_cites(gc), [REAL, REAL_2])

    def test_templated_content_without_raw_uses_kept_cites(self):
        gc = content(cites=[REAL])  # no raw_llm_output
        self.assertEqual(grounding.offered_cites(gc), [REAL])

    def test_corrupt_raw_json_is_ignored(self):
        gc = content(cites=[REAL])
        gc = gc.model_copy(update={"raw_llm_output": "not json {"})
        self.assertEqual(grounding.offered_cites(gc), [REAL])


class TestResolveCites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()

    def test_splits_resolved_and_unresolved(self):
        resolved, unresolved = grounding.resolve_cites(self.world, [REAL, FAKE, MALFORMED])
        self.assertEqual(resolved, [REAL])
        self.assertEqual(unresolved, [FAKE, MALFORMED])


class TestGroundLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()

    def test_ok_on_first_try(self):
        gc = content(cites=[REAL], raw_cites=[REAL])
        final, outcome = grounding.ground(scripted(gc), self.world)
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.attempts, 1)
        self.assertEqual(outcome.offered, 1)
        self.assertEqual(outcome.resolved, 1)
        self.assertEqual(outcome.dropped, 0)
        self.assertEqual(final.grounding_status, "ok")
        self.assertEqual(final.cites, [REAL])

    def test_regen_then_clean(self):
        bad = content("a", raw_cites=[REAL, FAKE])
        good = content("b", cites=[REAL], raw_cites=[REAL])
        final, outcome = grounding.ground(scripted(bad, good), self.world, max_regen=2)
        self.assertEqual(outcome.status, "regen")
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(final.text, "b")
        self.assertEqual(final.cites, [REAL])

    def test_dropped_after_exhausting_regens(self):
        bad = content("a", raw_cites=[REAL, FAKE])
        final, outcome = grounding.ground(scripted(bad), self.world, max_regen=2)
        self.assertEqual(outcome.status, "dropped")
        self.assertEqual(outcome.attempts, 3)  # 1 initial + 2 regens
        self.assertEqual(outcome.offered, 2)
        self.assertEqual(outcome.resolved, 1)
        self.assertEqual(outcome.dropped, 1)
        self.assertEqual(final.cites, [REAL])  # only the resolvable one survives
        self.assertEqual(final.grounding_status, "dropped")

    def test_max_regen_zero_drops_immediately(self):
        bad = content("a", raw_cites=[FAKE])
        final, outcome = grounding.ground(scripted(bad), self.world, max_regen=0)
        self.assertEqual(outcome.attempts, 1)
        self.assertEqual(outcome.status, "dropped")
        self.assertEqual(final.cites, [])

    def test_no_cites_is_ok(self):
        gc = content("held. won.", raw_cites=[])
        final, outcome = grounding.ground(scripted(gc), self.world)
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.offered, 0)

    def test_accept_predicate_forces_regen_without_touching_cite_status(self):
        # Cites always resolve, but `accept` rejects the first attempt: the loop
        # regenerates, yet the cite-based status stays "ok" (no cite ever failed).
        first = content("reject me", cites=[REAL], raw_cites=[REAL])
        second = content("accept me", cites=[REAL], raw_cites=[REAL])
        accept = lambda c, r, u: c.text == "accept me"  # noqa: E731
        final, outcome = grounding.ground(
            scripted(first, second), self.world, max_regen=2, accept=accept
        )
        self.assertEqual(final.text, "accept me")
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.attempts, 2)

    def test_on_attempt_fires_once_per_attempt(self):
        bad = content("a", raw_cites=[FAKE])
        calls = []
        grounding.ground(
            scripted(bad), self.world, max_regen=2, on_attempt=lambda c: calls.append(c)
        )
        self.assertEqual(len(calls), 3)

    def test_on_attempt_exception_propagates_and_halts(self):
        gc = content("a", raw_cites=[FAKE])

        class Boom(RuntimeError):
            pass

        def explode(_c):
            raise Boom()

        with self.assertRaises(Boom):
            grounding.ground(scripted(gc), self.world, on_attempt=explode)

    def test_negative_max_regen_rejected(self):
        with self.assertRaises(ValueError):
            grounding.ground(scripted(content()), self.world, max_regen=-1)


if __name__ == "__main__":
    unittest.main()
