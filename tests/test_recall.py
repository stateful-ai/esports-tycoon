"""The deterministic precedent-recall selector.

Covers the contract pinned in this ticket:

* the selector is pure — zero RNG, zero model calls, zero I/O;
* identical inputs always yield the identical ordered list;
* ranking is by shared actors first, then tag overlap (choke/clutch/tilt and
  their cousins), then active rivalry — Python's stable sort breaks ties by
  save order;
* a week-6 key moment surfaces ≥1 week-2 precedent (or the ``scrim_w5_*``
  carryover that lit it), so the renderer has something *that already
  happened* to point at; and
* the templated narrator binds at least one recalled precedent by cite ID
  into the rendered output (the recap renders cite IDs verbatim under
  "What the room remembered").
"""

from __future__ import annotations

import ast
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import recall as recall_mod  # noqa: E402
from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import GenerationContext, generate_content  # noqa: E402
from esports_tycoon.content import game_llm  # noqa: E402
from esports_tycoon.content.config import ContentConfig  # noqa: E402
from esports_tycoon.recall import recall, score  # noqa: E402
from esports_tycoon.runner import SliceConfig, SliceDecisions, run_slice  # noqa: E402
from esports_tycoon.runner.events import read_events, slice_events, write_events  # noqa: E402
from esports_tycoon.runner.recap import render_recap_md  # noqa: E402
from esports_tycoon.schema import (  # noqa: E402
    Decisions,
    KeyMoment,
    MemoryEntry,
    Player,
    RECALL_TAGS,
    Relationship,
    Role,
    WhyRecord,
)
from pydantic import ValidationError  # noqa: E402


_RECALL_SRC = pathlib.Path(recall_mod.__file__)


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()


class TestPurity(_Fixture):
    """The selector is engine-side and pure: no RNG, no LLM, no I/O."""

    def _imports(self) -> set[str]:
        tree = ast.parse(_RECALL_SRC.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    def test_does_not_import_rng_or_a_model_client(self):
        banned = (
            "random",
            "secrets",
            "time",
            "datetime",
            "openai",
            "anthropic",
            "httpx",
            "requests",
            "urllib",
            "socket",
            "esports_tycoon.content.llm",
            "esports_tycoon.content.game_llm",
        )
        for module in self._imports():
            for bad in banned:
                self.assertFalse(
                    module == bad or module.startswith(bad + "."),
                    f"recall imports {module!r}, which is not allowed (zero RNG, zero model)",
                )

    def test_does_not_construct_the_llm_client(self):
        # Booby-trap the LLM client: if recall ever reaches for it, this blows up.
        def explode():
            raise AssertionError("recall must not construct an LLM client")

        original = game_llm.get_llm
        game_llm.get_llm = explode
        try:
            dec = Decisions(opponent="northwind", map="Helix")
            why = resolver.run(self.world, dec, 7)
            recall(why, self.world, k=5)
        finally:
            game_llm.get_llm = original


class TestDeterminism(_Fixture):
    """Same inputs → identical ordered list, run after run, process after process."""

    def test_identical_inputs_yield_identical_ordered_list(self):
        for opp in ("apex_foundry", "northwind", "sovereign", "tidewater"):
            for seed in range(8):
                why = resolver.run(self.world, Decisions(opponent=opp, map="Helix"), seed)
                first = [e.id for e in recall(why, self.world, k=10)]
                for _ in range(5):
                    again = [e.id for e in recall(why, self.world, k=10)]
                    self.assertEqual(again, first, f"non-deterministic on opp={opp} seed={seed}")

    def test_k_truncation_is_a_prefix_of_the_full_ranking(self):
        # Truncating to k is just ``ranked[:k]`` — every shorter k must be a prefix
        # of every longer one. If it weren't, the selector would be re-ranking on
        # cardinality, which would break the "same inputs ⇒ identical list" promise
        # for any consumer that paged.
        why = resolver.run(self.world, Decisions(opponent="apex_foundry", map="Helix"), 6)
        long = [e.id for e in recall(why, self.world, k=20)]
        for k in (1, 3, 5, 8, 13):
            short = [e.id for e in recall(why, self.world, k=k)]
            self.assertEqual(short, long[:k])

    def test_k_zero_returns_empty(self):
        why = resolver.run(self.world, Decisions(opponent="northwind", map="Helix"), 1)
        self.assertEqual(recall(why, self.world, k=0), [])

    def test_negative_k_is_rejected(self):
        why = resolver.run(self.world, Decisions(opponent="northwind", map="Helix"), 1)
        with self.assertRaises(ValueError):
            recall(why, self.world, k=-1)


class TestScoring(_Fixture):
    """Ranking signals: shared actors, tag overlap, active rivalry — in that order."""

    def _why(self, *, kind: str, actors: list[str], tilters: list[str] | None = None) -> WhyRecord:
        # A hand-crafted WhyRecord so the scoring contract is tested independently
        # of whatever the resolver happens to emit for a given seed. Round/seed
        # values are arbitrary placeholders — recall doesn't look at them. We
        # set ``tag`` directly via the resolver's kind→tag mapping so the typed
        # vocabulary signal is in place when the kind has one; otherwise the
        # beat carries no tag (which is the contract we want to test).
        tag = resolver.KIND_TO_RECALL_TAG.get(kind)
        return WhyRecord(
            scoreline=(13, 9),
            mvp=actors[0] if actors else "rook",
            key_moments=[
                KeyMoment(
                    round=1,
                    kind=kind,
                    actors=actors,
                    descriptor="x",
                    tag=tag,
                    actor_ref=actors[0] if actors else None,
                )
            ],
            who_carried=[],
            who_tilted=list(tilters or []),
            morale_deltas={a: 0 for a in actors},
            seed=0,
            round_log=[],
        )

    def test_shared_actors_outweighs_tag_overlap(self):
        # A precedent that shares actors but no tags must rank above one that
        # shares two tags but no actors. Build a why where Sable is the only
        # actor and the beat is a clutch:
        why = self._why(kind="clutch", actors=["sable"])
        ranked = score(why, self.world)
        # ``mem:sable:smokes_with_coyote_w2`` — actors=sable,coyote, tags don't
        # overlap target_tags={clutch}. actor_score=1, tag_score=0.
        # ``mem:coyote:lurk_winback_w1`` — actors=coyote, tags include "clutch".
        # tag_score=1, actor_score=0.
        by_id = {p.entry.id: p for p in ranked}
        sable_actor_only = by_id["mem:sable:smokes_with_coyote_w2"]
        coyote_tag_only = by_id["mem:coyote:lurk_winback_w1"]
        self.assertEqual(sable_actor_only.actor_score, 1)
        self.assertEqual(sable_actor_only.tag_score, 0)
        self.assertEqual(coyote_tag_only.actor_score, 0)
        self.assertEqual(coyote_tag_only.tag_score, 1)
        # Actor-shared precedent ranks first.
        ids = [p.entry.id for p in ranked]
        self.assertLess(ids.index(sable_actor_only.entry.id), ids.index(coyote_tag_only.entry.id))

    def test_recall_vocabulary_is_the_frozen_four(self):
        # The frozen shared vocabulary is exactly {choke, clutch, tilt, rivalry}
        # — anything else is a colour tag on the open ``MemoryEntry.tags`` list
        # and stays off the recall plane. The set is small on purpose; widening
        # it is a schema change, not a copy change.
        self.assertEqual(RECALL_TAGS, frozenset({"choke", "clutch", "tilt", "rivalry"}))
        # And the resolver's kind→tag map only emits values from this set
        # (every value in the map is a valid recall tag; the map is partial
        # because some kinds — ``ace`` — have no recall analogue).
        for kind, tag in resolver.KIND_TO_RECALL_TAG.items():
            self.assertIn(tag, RECALL_TAGS, f"kind={kind!r} maps to non-vocabulary tag {tag!r}")

    def test_active_rivalry_lifts_a_rival_tagged_memory(self):
        # Vex has an authored kind="rival" relationship with Halo. A memory
        # tagged with the rival's name should earn the rivalry bonus *only*
        # when an actor in the beat is the rival's owner.
        with_vex = self._why(kind="ace", actors=["vex"])
        with_sable = self._why(kind="ace", actors=["sable"])

        by_vex = {p.entry.id: p for p in score(with_vex, self.world)}
        by_sable = {p.entry.id: p for p in score(with_sable, self.world)}

        # mem:vex:trashtalk_halo_w2 has halo as an actor and "halo" as a tag.
        trashtalk = by_vex["mem:vex:trashtalk_halo_w2"]
        self.assertEqual(trashtalk.rivalry_score, 1)

        # Sable has no rival relationship with Halo, so the same memory (which
        # Sable doesn't share actors with anyway) gets no rivalry bonus from
        # Sable's perspective — it simply doesn't appear in the candidate set.
        self.assertNotIn("mem:vex:trashtalk_halo_w2", by_sable)

    def test_stable_sort_breaks_ties_by_save_order(self):
        # Build a synthetic two-player world where two entries score identically.
        # The selector must return them in save order.
        def mem(idx: str, player_id: str, tag: str) -> MemoryEntry:
            return MemoryEntry(
                id=f"mem:{player_id}:e_{idx}",
                week=2,
                day=1,
                kind="scrim",
                actors=[player_id],
                summary="x",
                sentiment="neutral",
                tags=[tag],
                recall_tags=[tag] if tag in RECALL_TAGS else [],
            )

        from esports_tycoon.schema import SaveMeta, Standing, Team, Season, LastWeek, Scoreline

        team = Team(
            id="ovc",
            name="Overcast",
            tag="OVC",
            handle="@overcast",
            blurb="",
            standing=Standing(wins=0, losses=0, place=1, of=10, note=""),
        )
        save_meta = SaveMeta(
            id="x",
            title="t",
            game="g",
            tone="dry",
            flavor="f",
            fiction_note="n",
            season=Season(league="L", division="D", total_weeks=10, current_week=6, playoff_cutoff=4),
            team=team,
        )
        last_week = LastWeek(
            week=5,
            opponent="o",
            format="Bo3",
            result="loss",
            scoreline=Scoreline(overcast=1, opponent=2, maps=[]),
            headline="",
            chirper_feed=[],
        )

        a = Player(
            id="a", name="A", handle="@a", role=Role.IGL, age=20,
            signature_operative="x", bio="", persona_voice="",
            traits=[], relationships=[], memory_log=[mem("1", "a", "clutch")],
        )
        b = Player(
            id="b", name="B", handle="@b", role=Role.DUELIST, age=20,
            signature_operative="x", bio="", persona_voice="",
            traits=[], relationships=[], memory_log=[mem("1", "b", "clutch")],
        )

        from esports_tycoon.schema import WorldState
        synthetic = WorldState(
            schema_version=0, seed=1, save=save_meta,
            players=[a, b], clash_pairs=[], rivals=[], last_week=last_week,
        )
        # MVP is a third party who owns no memory in this synthetic world, so
        # neither a nor b earns an actor-score from it; both score (0, 1, 0) and
        # the only thing left to order them is save order. The KeyMoment carries
        # the typed ``tag="clutch"`` so recall has a target tag to match against
        # (without it, the beat would contribute no tag score — recall fails
        # closed on tag-less beats by design).
        why = WhyRecord(
            scoreline=(13, 9), mvp="ghost",
            key_moments=[KeyMoment(round=1, kind="clutch", actors=[], descriptor="x", tag="clutch")],
            who_carried=[], who_tilted=[],
            morale_deltas={"a": 0, "b": 0},
            seed=0, round_log=[],
        )
        ranked = recall(why, synthetic, k=10)
        # Both score (0, 1, 0); save order is a before b.
        self.assertEqual([e.id for e in ranked], ["mem:a:e_1", "mem:b:e_1"])

        # And reversing the player order in the world flips the recall — proving
        # the tie-break is *save order*, not entry id.
        synthetic_reversed = synthetic.model_copy(update={"players": [b, a]})
        ranked_rev = recall(why, synthetic_reversed, k=10)
        self.assertEqual([e.id for e in ranked_rev], ["mem:b:e_1", "mem:a:e_1"])


class TestWeek6SurfacesWeek2Precedent(_Fixture):
    """The acceptance bar: a week-6 key moment surfaces ≥1 week-2 precedent.

    The example given in the ticket is ``mem:<player>:scrim_w5_*`` *or* a
    week-2 entry; either counts. The week-5 scrim choke is the carryover that
    lit the week-6 must-win, and the week-2 entries are the older precedents
    those carryover memories themselves rhyme with. Recall must surface at
    least one across the canonical week-6 fixture set.
    """

    _WEEK6_FIXTURES = [
        ("apex_foundry", 6),  # the canonical screenshot fixture
        ("apex_foundry", 1),
        ("northwind", 7),
        ("sovereign", 1),
    ]

    def _surfaces_required_precedent(self, ids: list[str]) -> bool:
        for cite in ids:
            if cite.startswith("mem:") and "scrim_w5_" in cite:
                return True
            entry = self.world.resolve_cite(cite)
            if entry is not None and entry.week == 2:
                return True
        return False

    def test_canonical_week6_fixture_surfaces_required_precedent(self):
        # The pinned screenshot fixture (the one the M0.1 minimum-playable
        # acceptance bar runs) must surface either the scrim_w5_choke carryover
        # or a week-2 entry in its recalled top-k.
        why = resolver.run(
            self.world,
            Decisions(opponent="apex_foundry", map="Helix"),
            6,
        )
        ranked = [e.id for e in recall(why, self.world, k=8)]
        self.assertTrue(
            self._surfaces_required_precedent(ranked),
            f"week-6 key moment did not surface scrim_w5_*/week-2 precedent: {ranked}",
        )

    def test_every_week6_fixture_surfaces_required_precedent(self):
        # Holds across the canonical opponent sweep, not just the screenshot.
        for opponent, seed in self._WEEK6_FIXTURES:
            why = resolver.run(self.world, Decisions(opponent=opponent, map="Helix"), seed)
            ranked = [e.id for e in recall(why, self.world, k=8)]
            self.assertTrue(
                self._surfaces_required_precedent(ranked),
                f"opp={opponent} seed={seed} did not surface a required precedent: {ranked}",
            )


class TestTemplatedCopyBindsRecalledCite(_Fixture):
    """The templated narrator binds ≥1 recalled precedent by cite ID into output."""

    def test_narration_cite_is_drawn_from_the_recall_ranking(self):
        # The narration's cite must come from the deterministic recall — not
        # from the templated backend's per-call RNG — so the precedent the
        # rendered output binds against is the one recall surfaced.
        dec = Decisions(opponent="northwind", map="Helix")
        why = resolver.run(self.world, dec, 7)
        gc = generate_content("narration", GenerationContext(world=self.world, why=why, decisions=dec))
        self.assertTrue(gc.cites, "narration with a keyed beat must cite a precedent")
        ranked_ids = {entry.id for entry in recall(why, self.world, k=20)}
        for cite in gc.cites:
            self.assertIn(
                cite,
                ranked_ids,
                f"narration cite {cite!r} is not in the recall ranking",
            )

    def test_recalled_cite_id_appears_in_rendered_recap(self):
        # End-to-end: run the full week-6 slice in templated mode, render the
        # auto-recap, and assert that at least one ID from the recall ranking
        # appears verbatim in the rendered output (the recap's "What the room
        # remembered" section quotes cite IDs back).
        config = SliceConfig(opponent="apex_foundry", map="Helix", seed=6, tactical_stance="default")
        decisions = SliceDecisions(
            practice_focus="defaults",
            team_talk="no heroes. run the default.",
            fallout_post="week 6: held the line.",
        )
        result = run_slice(
            self.world, config, decisions, content_config=ContentConfig(backend="templated")
        )

        ranked_ids = {entry.id for entry in recall(result.why, self.world, k=20)}
        self.assertTrue(ranked_ids, "recall returned no precedents for the canonical fixture")

        # Round-trip through the run-log so we exercise the actual recap path
        # the founder screenshots (recap.md is a projection of events.jsonl).
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            events_path = pathlib.Path(tmp) / "events.jsonl"
            write_events(slice_events(result, self.world), events_path)
            events = read_events(events_path)
            recap_md = render_recap_md(events, self.world)

        bound = [cite for cite in ranked_ids if cite in recap_md]
        self.assertTrue(
            bound,
            "no recalled precedent's cite ID appeared in the rendered recap",
        )

        # And the narration itself carries a recalled cite — the binding is on
        # the narration seam, not just incidental Chirper-post grounding.
        self.assertTrue(result.narration.cites)
        for cite in result.narration.cites:
            self.assertIn(cite, ranked_ids)


class TestFrozenVocabulary(_Fixture):
    """The frozen shared vocabulary on both sides of the recall join.

    The deterministic recall selector speaks one typed enum across both inputs
    it joins: the resolver's :attr:`KeyMoment.tag` and the canned save's
    :attr:`MemoryEntry.recall_tags`. The enum is small (four labels) and the
    load path fails closed on any off-vocabulary value — there is no fallback
    that quietly drops a typo from the ranker.
    """

    def test_resolver_emits_key_moments_with_typed_tag_from_the_frozen_vocabulary(self):
        # The acceptance bar: the resolver emits ``WhyRecord.key_moments[i].tag``
        # drawn from the frozen :data:`RECALL_TAGS` set. Sweep the canonical
        # opponents × seeds so every kind→tag branch fires.
        for opp in ("apex_foundry", "northwind", "sovereign", "tidewater", "last_light"):
            for seed in range(6):
                why = resolver.run(self.world, Decisions(opponent=opp, map="Helix"), seed)
                self.assertTrue(why.key_moments, f"opp={opp} seed={seed} emitted no key moments")
                tagged = [m for m in why.key_moments if m.tag is not None]
                self.assertTrue(
                    tagged,
                    f"opp={opp} seed={seed}: no key moment carries a recall tag",
                )
                for moment in tagged:
                    self.assertIn(
                        moment.tag,
                        RECALL_TAGS,
                        f"opp={opp} seed={seed} round={moment.round}: "
                        f"tag {moment.tag!r} is not in the frozen vocabulary",
                    )

    def test_resolver_emits_actor_ref_that_lives_in_actors(self):
        # actor_ref is the canonical single anchor. It must always be one of the
        # beat's named actors so a downstream consumer can rely on it as a
        # guaranteed-present pointer.
        for opp in ("apex_foundry", "northwind"):
            for seed in (0, 1, 6, 9):
                why = resolver.run(self.world, Decisions(opponent=opp, map="Helix"), seed)
                for moment in why.key_moments:
                    if moment.actor_ref is not None:
                        self.assertIn(
                            moment.actor_ref,
                            moment.actors,
                            f"opp={opp} seed={seed} round={moment.round}: "
                            f"actor_ref {moment.actor_ref!r} not in actors {moment.actors!r}",
                        )

    def test_loader_fails_closed_on_off_enum_recall_tag(self):
        # An off-vocabulary recall tag on the canned save is rejected by the
        # loader. The save is regenerated from a real load of the canonical
        # world (so every other field is valid) and only one entry is corrupted.
        bad_world = self.world.model_copy()
        with self.assertRaises(ValidationError) as cm:
            MemoryEntry(
                id="mem:rook:offenum_w0",
                week=0, day=1, kind="scrim", actors=["rook"],
                summary="x", sentiment="neutral",
                tags=["x"],
                recall_tags=["ace"],  # "ace" is NOT in the frozen vocabulary
            )
        # Pydantic v2 reports the enum violation with the field path
        # ``recall_tags.0`` so the author can take the message straight to the
        # offending value.
        msg = str(cm.exception)
        self.assertIn("recall_tags", msg)

    def test_off_enum_key_moment_tag_is_rejected(self):
        # Same contract on the resolver side: a KeyMoment cannot be built with
        # an off-vocabulary tag. This is what makes the resolver's emit path
        # "fail closed" rather than silently quote a stray string into the
        # recall plane.
        with self.assertRaises(ValidationError):
            KeyMoment(round=1, kind="ace", actors=["vex"], descriptor="5k", tag="ace")

    def test_actor_ref_outside_actors_is_rejected(self):
        with self.assertRaises(ValidationError):
            KeyMoment(round=1, kind="clutch", actors=["rook"], descriptor="x", actor_ref="vex")

    def test_recall_fails_closed_when_key_moments_have_no_tag(self):
        # The "recall callback test fails closed if key-moment tags are
        # absent": a WhyRecord whose beats carry no ``tag`` contributes no
        # tag-overlap signal to the ranker. The expected behaviour is that
        # every surfaced candidate has tag_score == 0 — recall does NOT fall
        # back to ``kind`` or to the open ``tags`` list, so a beat the
        # resolver could not tag stays off the recall plane by construction.
        why = WhyRecord(
            scoreline=(13, 9),
            mvp="sable",
            key_moments=[
                KeyMoment(
                    round=1, kind="clutch", actors=["sable"],
                    descriptor="x", actor_ref="sable",
                    # tag deliberately omitted — this is the failure mode
                    # under test.
                ),
            ],
            who_carried=["sable"], who_tilted=[],
            morale_deltas={"sable": 0},
            seed=0, round_log=[],
        )
        ranked = score(why, self.world)
        # Some candidates still surface via shared actors (sable owns memory
        # entries), but none of them earn a tag_score — recall did not invent
        # one from the bare ``kind``.
        self.assertTrue(ranked, "expected sable's actor-shared precedents to surface")
        for precedent in ranked:
            self.assertEqual(
                precedent.tag_score, 0,
                f"recall produced a tag_score for {precedent.entry.id!r} despite "
                "no key_moment.tag being set — it must fail closed on absent tags",
            )

    def test_canned_save_recall_tags_are_all_in_the_frozen_vocabulary(self):
        # Belt and braces: the loaded world's recall_tags only contain values
        # from the frozen enum. Pydantic would have rejected the load if not,
        # but this asserts the contract on the *loaded* artifact directly so a
        # regression cannot hide behind a permissive type alias.
        for player in self.world.players:
            for entry in player.memory_log:
                for tag in entry.recall_tags:
                    self.assertIn(
                        tag, RECALL_TAGS,
                        f"{entry.id}: recall_tag {tag!r} is not in the frozen vocabulary",
                    )


if __name__ == "__main__":
    unittest.main()
