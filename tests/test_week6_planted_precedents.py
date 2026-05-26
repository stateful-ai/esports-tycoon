"""Acceptance bar for the planted precedent + recall hooks in ``week6.yaml``.

This test locks down the three criteria the canned save must satisfy for the
deterministic recall selector to have something to surface on a week-6 match:

* **≥6 tagged ``MemoryEntry`` candidates across actors.** Recall scores on the
  frozen vocabulary :data:`~esports_tycoon.schema.RECALL_TAGS`; an entry that
  carries no ``recall_tags`` contributes only on actor / rivalry overlap. The
  bar is six tagged entries *distributed* across multiple starters so a beat
  centred on any one of them has a planted precedent to rhyme with.
* **≥1 cross-week precedent pair.** Two recall-tagged entries from different
  weeks that share an authored arc — wired up through ``clash_pairs.seeded_by``
  — so a week-6 beat can be narrated as "same as week 2 …" rather than as a
  one-shot reference to last week. Without a cross-week pair the recap can't
  point at history with any depth; with one, the renderer has something *that
  already happened multiple times* to lean on.
* **``recall(week6 WhyRecord, k=3)`` is non-empty and on-theme under the locked
  seed.** The canonical screenshot fixture is ``(apex_foundry, seed=6)`` (the
  same fixture ``tests/test_recall.py`` calls "the canonical screenshot
  fixture"). For the recap to render "what the room remembered" with any
  signal, recall must return a non-empty top-3 *and* every entry must share
  at least one actor with the match the resolver just produced — anything
  else would be a structurally-on-recall-plane miss.

The criteria are duplicated from this task's acceptance bar verbatim so a
future contributor stripping a ``recall_tags`` list, deleting a planted
precedent, or breaking the clash-pair wiring trips the bar here instead of
flying past it.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.recall import recall  # noqa: E402
from esports_tycoon.schema import Decisions, RECALL_TAGS  # noqa: E402

# The canonical screenshot fixture — the one the recap's "the game remembered
# me" moment is taken against. Held in lockstep with ``tests/test_recall.py``'s
# ``_WEEK6_FIXTURES[0]``; if either moves, both move together.
LOCKED_OPPONENT = "apex_foundry"
LOCKED_SEED = 6
LOCKED_MAP = "Helix"


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()


class TestTaggedCandidates(_Fixture):
    """≥6 tagged ``MemoryEntry`` candidates distributed across actors."""

    def test_at_least_six_recall_tagged_entries(self):
        tagged = [
            entry
            for player in self.world.players
            for entry in player.memory_log
            if entry.recall_tags
        ]
        self.assertGreaterEqual(
            len(tagged),
            6,
            f"expected ≥6 recall-tagged MemoryEntry candidates, found {len(tagged)}: "
            f"{[e.id for e in tagged]}",
        )

    def test_tagged_candidates_span_multiple_actors(self):
        owners = {
            player.id
            for player in self.world.players
            if any(entry.recall_tags for entry in player.memory_log)
        }
        self.assertGreaterEqual(
            len(owners),
            2,
            f"tagged candidates must be distributed across actors (got {owners})",
        )

    def test_every_recall_tag_is_in_the_frozen_vocabulary(self):
        # Belt and braces on the load contract: any ``recall_tags`` entry the
        # author writes must land in the frozen four. Pydantic already rejects
        # off-vocabulary values at load — this asserts the artifact directly
        # so a regression cannot hide behind a permissive type alias.
        for player in self.world.players:
            for entry in player.memory_log:
                for tag in entry.recall_tags:
                    self.assertIn(
                        tag,
                        RECALL_TAGS,
                        f"{entry.id}: recall_tag {tag!r} is off-vocabulary",
                    )


class TestCrossWeekPrecedentPair(_Fixture):
    """≥1 cross-week precedent pair so a "same as week 2 …" beat is reachable."""

    def _resolve(self, cite: str):
        entry = self.world.resolve_cite(cite)
        self.assertIsNotNone(entry, f"unresolvable cite in clash_pair seed: {cite!r}")
        return entry

    def test_some_clash_pair_is_seeded_by_entries_from_different_weeks(self):
        # The strongest authorial form of a cross-week precedent pair is a
        # ``clash_pair`` whose ``seeded_by`` list spans more than one week —
        # the author has explicitly said "this arc has happened before". The
        # bar is a pair that is both (a) cross-week AND (b) reachable through
        # recall (at least one seed entry opts onto the recall plane via
        # ``recall_tags``), so the renderer can actually surface it. A clash
        # pair authored only in canon — no ``recall_tags`` anywhere in its
        # ``seeded_by`` — meets the *narrative* bar but not the *engine* bar
        # this task is closing.
        cross_week_pairs: list[tuple[str, str, set[int]]] = []
        for pair in self.world.clash_pairs:
            weeks = {self._resolve(cite).week for cite in pair.seeded_by}
            if len(weeks) >= 2:
                cross_week_pairs.append((pair.a, pair.b, weeks))
                tagged = any(
                    self._resolve(cite).recall_tags for cite in pair.seeded_by
                )
                if tagged:
                    return
        if not cross_week_pairs:
            self.fail(
                "no clash pair is seeded by entries from multiple weeks; "
                "a 'same as week 2 …' beat has no authored precedent to reach"
            )
        self.fail(
            "every cross-week clash pair is unreachable through recall — at least one "
            "seed entry on a cross-week pair must carry recall_tags so the renderer can "
            f"surface the arc as precedent. Cross-week pairs found: {cross_week_pairs}"
        )

    def test_a_week2_or_earlier_recall_tagged_entry_exists(self):
        # The literal "same as week 2" hook needs at least one tagged entry
        # at or before week 2 — otherwise no week-6 beat could surface a
        # week-2 precedent through the recall plane at any ``k``. (Recall is
        # week-agnostic in its ranking; this is a save-authoring bar.)
        early = [
            entry
            for player in self.world.players
            for entry in player.memory_log
            if entry.recall_tags and entry.week <= 2
        ]
        self.assertTrue(
            early,
            "expected ≥1 recall-tagged entry at or before week 2; "
            "no early precedent means recall can never surface a 'same as week 2' beat",
        )


class TestRecallUnderLockedSeed(_Fixture):
    """``recall(week6 WhyRecord, k=3)`` is non-empty and on-theme under the locked seed."""

    def _why(self):
        return resolver.run(
            self.world,
            Decisions(opponent=LOCKED_OPPONENT, map=LOCKED_MAP),
            LOCKED_SEED,
        )

    def test_top_three_is_non_empty_under_the_locked_seed(self):
        results = recall(self._why(), self.world, k=3)
        self.assertEqual(
            len(results),
            3,
            f"expected exactly 3 recalled precedents at k=3, got {len(results)}: "
            f"{[r.cite_id for r in results]}",
        )

    def test_top_three_is_on_theme(self):
        # "On theme" = each recalled entry shares at least one signal with
        # the match: an actor named in the why-record, an authored tag that
        # rhymes with the resolver's key-moment tag set, or an active-rivalry
        # bonus. By construction, recall only yields entries with ≥1 non-zero
        # signal — but assert it on the loaded artifact directly so a
        # regression that surfaced an inert entry would fail here, not pass
        # silently through the renderer.
        why = self._why()
        why_actors: set[str] = set()
        for moment in why.key_moments:
            why_actors.update(moment.actors)
            if moment.actor_ref is not None:
                why_actors.add(moment.actor_ref)
        if why.mvp:
            why_actors.add(why.mvp)
        why_actors.update(why.who_carried)
        why_actors.update(why.who_tilted)

        why_tags: set[str] = set()
        for moment in why.key_moments:
            if moment.tag is not None:
                why_tags.add(moment.tag)
        if why.who_tilted:
            why_tags.add("tilt")

        for r in recall(why, self.world, k=3):
            entry = self.world.resolve_cite(r.cite_id)
            self.assertIsNotNone(entry, f"recall surfaced unresolvable cite {r.cite_id!r}")
            shares_actor = bool(why_actors & set(entry.actors))
            shares_tag = bool(why_tags & set(entry.recall_tags))
            self.assertTrue(
                shares_actor or shares_tag,
                f"recall surfaced {r.cite_id!r} but it shares neither actor nor "
                f"recall-tag with the match: relevance_reason={r.relevance_reason!r}",
            )

    def test_top_three_is_deterministic_under_the_locked_seed(self):
        # The acceptance bar names a *locked seed*, so the top-3 must be
        # byte-stable across calls — not just non-empty. If a future change
        # accidentally introduced any entropy into recall, this catches it
        # at the screenshot fixture rather than at integration time.
        first = [r.cite_id for r in recall(self._why(), self.world, k=3)]
        for _ in range(5):
            again = [r.cite_id for r in recall(self._why(), self.world, k=3)]
            self.assertEqual(again, first, "recall is non-deterministic under the locked seed")


if __name__ == "__main__":
    unittest.main()
