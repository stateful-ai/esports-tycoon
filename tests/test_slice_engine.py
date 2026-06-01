"""The headless slice engine + auto-recap artifact: the acceptance bar.

The slice-runner ticket's acceptance criteria are exercised here, with no web
dependency (the Flask shell is tested separately):

* It runs **practice → match → fallout** end-to-end against ``week6.yaml`` in
  templated mode, accepting the MC + two open-text decisions.
* The two open-text decisions are **capped at 120 chars** each.
* On completion it writes ``runs/<slice_id>/recap.md`` + ``feed.snapshot.html``.
* The recap (and the feed snapshot) are **byte-identical on re-run with the same
  seed** in templated mode — and a changed decision lands in its own run folder.

Beyond the bar: every cite the feed emits resolves (grounding holds), user open
text is HTML-escaped in the snapshot, and the run touches no network/LLM.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import game_llm  # noqa: E402
from esports_tycoon.runner import (  # noqa: E402
    EVENTS_FILENAME,
    FEED_FILENAME,
    OPEN_TEXT_MAX,
    RECAP_FILENAME,
    WEEK7_SETUP_FILENAME,
    focus_payload_from_json,
    SliceConfig,
    SliceDecisions,
    render_feed_html,
    render_recap_md,
    render_week7_focus_json,
    render_week7_pressure_json,
    run_slice,
    resolve_week7_focus,
    resolve_week7_pressure,
    setup_payload_from_week7_setup,
    slice_events,
    training_decision_for_drill,
    write_artifacts,
)
from esports_tycoon.runner.engine import halftime_scoreline, slice_id  # noqa: E402


def recap_md(result, world):
    """The recap as the artifact path produces it — derived from the run-log."""
    return render_recap_md(slice_events(result, world), world)


def feed_html(result, world):
    """The feed snapshot as the artifact path produces it — derived from the run-log."""
    return render_feed_html(slice_events(result, world), world)


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        cls.config = SliceConfig(opponent="apex_foundry", map="Helix", seed=6)
        cls.decisions = SliceDecisions(
            practice_focus="defaults",
            team_talk="no heroes. run the default.",
            fallout_post="week 6: held the line. on to week 7.",
        )


class TestRunsEndToEnd(_Fixture):
    def test_practice_match_fallout(self):
        result = run_slice(self.world, self.config, self.decisions)
        # The MC drove the resolved match...
        self.assertEqual(len(result.why.morale_deltas), len(self.world.players))
        self.assertEqual(result.why.seed, 6)
        # ...the narration and half-time ack rendered...
        self.assertEqual(result.narration.kind, "narration")
        self.assertTrue(result.narration.text)
        self.assertEqual(result.halftime.kind, "halftime_ack")
        self.assertTrue(result.halftime.text)
        # ...and the fallout produced a feed including the manager's public post.
        self.assertTrue(result.feed)
        self.assertEqual(result.feed[0].text, self.decisions.fallout_post)
        self.assertEqual(result.feed[0].author_handle, self.world.save.team.handle)
        # Every starter reacts in character.
        starter_handles = {p.handle for p in self.world.players}
        feed_handles = {post.author_handle for post in result.feed}
        self.assertTrue(starter_handles <= feed_handles)

    def test_uses_all_three_templated_kinds(self):
        result = run_slice(self.world, self.config, self.decisions)
        self.assertEqual(result.narration.kind, "narration")
        self.assertEqual(result.halftime.kind, "halftime_ack")
        # The five starters' posts are chirper_post (grounded), so cites exist.
        self.assertTrue(any(post.cites for post in result.feed))

    def test_empty_open_text_is_accepted_and_omits_manager_post(self):
        decisions = SliceDecisions(practice_focus="rest")  # both open-text empty
        result = run_slice(self.world, self.config, decisions)
        self.assertNotIn(self.world.save.team.handle, {p.author_handle for p in result.feed})

    def test_halftime_scoreline_matches_round_log(self):
        result = run_slice(self.world, self.config, self.decisions)
        expected = halftime_scoreline(result.why, self.world.save.team.id)
        self.assertEqual(result.halftime_scoreline, expected)
        h_ovc, h_opp = result.halftime_scoreline
        self.assertEqual(h_ovc + h_opp, min(12, len(result.why.round_log)))

    def test_relationship_fallout_surfaces_live_clash_pair(self):
        training_points, effects = training_decision_for_drill("vex_aim")
        result = run_slice(
            self.world,
            self.config,
            SliceDecisions(
                practice_focus="defaults",
                training_points=training_points,
                decision_effects=effects,
            ),
        )

        self.assertEqual(len(result.relationship_fallout), 1)
        fallout = result.relationship_fallout[0]
        self.assertEqual((fallout.a, fallout.b), ("vex", "pixie"))
        self.assertEqual(fallout.axis, "blame vs. guilt")
        self.assertEqual(fallout.kind, "split")
        self.assertIn("mem:pixie:flashed_vex_w5", fallout.cites)
        self.assertIn("mem:vex:flashed_by_pixie_w5", fallout.cites)

    def test_relationship_fallout_adds_grounded_chirper_consequence(self):
        training_points, effects = training_decision_for_drill("vex_aim")
        result = run_slice(
            self.world,
            self.config,
            SliceDecisions(
                practice_focus="defaults",
                training_points=training_points,
                decision_effects=effects,
            ),
        )

        fallout_posts = [post for post in result.feed if post.role == "relationship_fallout"]
        self.assertEqual(len(fallout_posts), 1)
        post = fallout_posts[0]
        self.assertEqual(post.author_player_id, "vex")
        self.assertEqual(post.local_outcome, "carried")
        self.assertIn("entry reps helped", post.text)
        self.assertEqual(
            post.cites,
            ("mem:pixie:flashed_vex_w5", "mem:vex:flashed_by_pixie_w5"),
        )


class TestOpenTextCap(_Fixture):
    def test_rejects_over_120_chars(self):
        with self.assertRaises(ValueError):
            SliceDecisions(practice_focus="aim", team_talk="x" * (OPEN_TEXT_MAX + 1))
        with self.assertRaises(ValueError):
            SliceDecisions(practice_focus="aim", fallout_post="y" * (OPEN_TEXT_MAX + 1))

    def test_accepts_exactly_120_chars(self):
        at_cap = "z" * OPEN_TEXT_MAX
        decisions = SliceDecisions(practice_focus="aim", team_talk=at_cap, fallout_post=at_cap)
        self.assertEqual(len(decisions.team_talk), OPEN_TEXT_MAX)
        self.assertEqual(len(decisions.fallout_post), OPEN_TEXT_MAX)

    def test_normalizes_whitespace_and_newlines_to_one_line(self):
        decisions = SliceDecisions(practice_focus="aim", team_talk="  run\nthe   default  ")
        self.assertEqual(decisions.team_talk, "run the default")

    def test_rejects_unknown_practice_focus(self):
        with self.assertRaises(ValueError):
            SliceDecisions(practice_focus="vibes")  # type: ignore[arg-type]


class TestTrainingDrills(_Fixture):
    def test_training_drill_builds_budgeted_effect(self):
        training_points, effects = training_decision_for_drill("vex_aim")

        self.assertEqual(training_points, 4)
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].player, "vex")
        self.assertEqual(effects[0].skill, "aim")
        self.assertEqual(effects[0].delta, 4)
        self.assertEqual(effects[0].training_points, 4)
        self.assertEqual(effects[0].source, "training")

    def test_repair_drill_builds_budgeted_effect(self):
        training_points, effects = training_decision_for_drill("pixie_flash_repair")

        self.assertEqual(training_points, 4)
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].player, "pixie")
        self.assertEqual(effects[0].skill, "coordination")
        self.assertEqual(effects[0].delta, 4)
        self.assertEqual(effects[0].training_points, 4)
        self.assertEqual(effects[0].source, "pixie_flash_repair")

    def test_training_drill_none_preserves_practice_only_surface(self):
        training_points, effects = training_decision_for_drill("none")

        self.assertEqual(training_points, 0)
        self.assertEqual(effects, ())

    def test_unknown_training_drill_fails_loudly(self):
        with self.assertRaises(ValueError):
            training_decision_for_drill("vibes")

    def test_vex_aim_drill_changes_the_same_seed_visible_outcome(self):
        base = run_slice(self.world, self.config, SliceDecisions(practice_focus="defaults"))
        training_points, effects = training_decision_for_drill("vex_aim")
        trained = run_slice(
            self.world,
            self.config,
            SliceDecisions(
                practice_focus="defaults",
                training_points=training_points,
                decision_effects=effects,
            ),
        )

        self.assertIn("vex", base.why.who_tilted)
        self.assertNotIn("vex", base.why.who_carried)
        self.assertIn("vex", trained.why.who_carried)
        self.assertNotIn("vex", trained.why.who_tilted)
        self.assertGreater(trained.why.morale_deltas["vex"], base.why.morale_deltas["vex"])
        self.assertEqual(base.relationship_fallout, ())
        self.assertEqual(trained.relationship_fallout[0].kind, "split")
        self.assertEqual(trained.training_consequence.kind, "vex_entry_reps")
        self.assertEqual(trained.week7_setup.review_room_trust.delta, -2)
        self.assertEqual(trained.week7_setup.hook_id, "vex_pixie_review_room_heat")

    def test_repair_vs_reps_branches_have_distinct_visible_consequences(self):
        reps_points, reps_effects = training_decision_for_drill("vex_aim")
        repair_points, repair_effects = training_decision_for_drill("pixie_flash_repair")
        reps = run_slice(
            self.world,
            self.config,
            SliceDecisions(
                practice_focus="defaults",
                training_points=reps_points,
                decision_effects=reps_effects,
            ),
        )
        repair = run_slice(
            self.world,
            self.config,
            SliceDecisions(
                practice_focus="defaults",
                training_points=repair_points,
                decision_effects=repair_effects,
            ),
        )

        self.assertEqual(reps.training_consequence.kind, "vex_entry_reps")
        self.assertIn("two calls at once", reps.training_consequence.summary)
        self.assertEqual(reps.relationship_fallout[0].kind, "split")
        self.assertIn("pixie", reps.why.who_tilted)
        self.assertEqual(reps.week7_setup.source_branch, "vex_aim")
        self.assertEqual(reps.week7_setup.review_room_trust.start, 2)
        self.assertEqual(reps.week7_setup.review_room_trust.delta, -2)
        self.assertEqual(reps.week7_setup.review_room_trust.final, 0)
        self.assertIn("late retake stalled", reps.week7_setup.followup_scrim.summary)

        self.assertEqual(repair.training_consequence.kind, "pixie_flash_repair")
        self.assertIn("flash finally matched", repair.training_consequence.summary)
        self.assertEqual(repair.relationship_fallout[0].kind, "repair")
        self.assertEqual(repair.relationship_fallout[0].axis, "working review")
        self.assertNotIn("pixie", repair.why.who_tilted)
        self.assertIn("pixie", repair.why.who_carried)
        self.assertEqual(repair.week7_setup.source_branch, "pixie_flash_repair")
        self.assertEqual(repair.week7_setup.review_room_trust.start, 2)
        self.assertEqual(repair.week7_setup.review_room_trust.delta, 2)
        self.assertEqual(repair.week7_setup.review_room_trust.final, 4)
        self.assertIn("converted the second contact", repair.week7_setup.followup_scrim.summary)

        repair_posts = [post for post in repair.feed if post.role == "relationship_fallout"]
        self.assertEqual(len(repair_posts), 1)
        self.assertEqual(repair_posts[0].author_player_id, "pixie")
        self.assertIn("flash review helped", repair_posts[0].text)

        reps_recap = recap_md(reps, self.world)
        repair_recap = recap_md(repair, self.world)
        self.assertIn("### Practice consequence", reps_recap)
        self.assertIn("### Review-room trust", reps_recap)
        self.assertIn("### Follow-up scrim", reps_recap)
        self.assertIn("## Week 7 setup", reps_recap)
        self.assertIn("**Entry reps:** Vex looked sharper", reps_recap)
        self.assertIn("Review room heat", reps_recap)
        self.assertIn("split the room", reps_recap)
        self.assertIn("**Flash review:** No highlight reel", repair_recap)
        self.assertIn("Stable, not loud", repair_recap)
        self.assertIn("cooled down", repair_recap)
        self.assertIn("Vex did not get another raw aim bump", repair_recap)


class TestArtifacts(_Fixture):
    def test_writes_recap_and_feed_snapshot(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            result = run_slice(self.world, self.config, self.decisions)
            recap_path, feed_path, events_path = write_artifacts(result, self.world, tmp)
            self.assertEqual(recap_path.name, RECAP_FILENAME)
            self.assertEqual(feed_path.name, FEED_FILENAME)
            self.assertEqual(events_path.name, EVENTS_FILENAME)
            self.assertEqual(recap_path.parent.name, result.slice_id)
            self.assertTrue(recap_path.is_file() and feed_path.is_file() and events_path.is_file())
            self.assertIn("# Overcast — Week 6", recap_path.read_text(encoding="utf-8"))
            self.assertIn("<!DOCTYPE html>", feed_path.read_text(encoding="utf-8"))

    def test_writes_week7_setup_export_for_training_fork(self):
        import json
        import tempfile

        training_points, effects = training_decision_for_drill("pixie_flash_repair")
        decisions = SliceDecisions(
            practice_focus="defaults",
            training_points=training_points,
            decision_effects=effects,
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = run_slice(self.world, self.config, decisions)
            recap_path, _, _ = write_artifacts(result, self.world, tmp)
            setup_path = recap_path.parent / WEEK7_SETUP_FILENAME

            self.assertTrue(setup_path.is_file())
            payload = json.loads(setup_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["week7_setup"]["source_branch"], "pixie_flash_repair")
            self.assertEqual(payload["week7_setup"]["review_room_trust"]["delta"], 2)
            self.assertEqual(
                payload["week7_setup"]["next_week_hook"]["id"],
                "pixie_stability_low_clip_value",
            )


class TestWeek7FocusLock(_Fixture):
    def _setup_for(self, drill: str):
        training_points, effects = training_decision_for_drill(drill)
        result = run_slice(
            self.world,
            self.config,
            SliceDecisions(
                practice_focus="defaults",
                training_points=training_points,
                decision_effects=effects,
            ),
        )
        return setup_payload_from_week7_setup(result.week7_setup)

    def test_vex_heat_setup_recommends_containment(self):
        setup = self._setup_for("vex_aim")

        self.assertEqual(setup.hook_id, "vex_pixie_review_room_heat")
        self.assertEqual(setup.recommended_focus, "contain_fallout")
        contained = resolve_week7_focus(setup, "contain_fallout")
        greedy = resolve_week7_focus(setup, "prove_ceiling")

        self.assertTrue(contained.followed_recommendation)
        self.assertEqual(contained.review_room_trust_delta, 1)
        self.assertIsNone(contained.consequence_id)
        self.assertFalse(greedy.followed_recommendation)
        self.assertEqual(greedy.consequence_id, "ignored_trust_fire")
        self.assertIn("hot room", greedy.pressure_note)
        self.assertIn('"chosen_focus": "prove_ceiling"', render_week7_focus_json(greedy))

    def test_pixie_stable_setup_recommends_ceiling(self):
        setup = self._setup_for("pixie_flash_repair")

        self.assertEqual(setup.hook_id, "pixie_stability_low_clip_value")
        self.assertEqual(setup.recommended_focus, "prove_ceiling")
        ceiling = resolve_week7_focus(setup, "prove_ceiling")
        cautious = resolve_week7_focus(setup, "contain_fallout")

        self.assertTrue(ceiling.followed_recommendation)
        self.assertEqual(ceiling.ceiling_signal_delta, 2)
        self.assertIsNone(ceiling.consequence_id)
        self.assertFalse(cautious.followed_recommendation)
        self.assertEqual(cautious.consequence_id, "overcorrected_stability")
        self.assertIn("stable moment", cautious.pressure_note)
        self.assertIn('"ignored_recommendation"', render_week7_focus_json(cautious))


class TestWeek7PressureResult(_Fixture):
    def _pressure_for(self, drill: str, selected_focus: str):
        training_points, effects = training_decision_for_drill(drill)
        result = run_slice(
            self.world,
            self.config,
            SliceDecisions(
                practice_focus="defaults",
                training_points=training_points,
                decision_effects=effects,
            ),
        )
        setup = setup_payload_from_week7_setup(result.week7_setup)
        focus_lock = resolve_week7_focus(setup, selected_focus)
        focus = focus_payload_from_json(render_week7_focus_json(focus_lock))
        return resolve_week7_pressure(setup, focus)

    def test_resolves_all_week7_pressure_outcomes(self):
        cases = (
            (
                "vex_aim",
                "contain_fallout",
                "heat_contained_scrappy_win",
                "win_2_1",
                2,
                -1,
                -2,
                0,
            ),
            (
                "vex_aim",
                "prove_ceiling",
                "heat_ignored_highlight_loss",
                "loss_1_2",
                -2,
                2,
                2,
                1,
            ),
            (
                "pixie_flash_repair",
                "prove_ceiling",
                "stability_unlocked_clean_2_0",
                "win_2_0",
                1,
                3,
                0,
                2,
            ),
            (
                "pixie_flash_repair",
                "contain_fallout",
                "stability_overmanaged_flat_win",
                "win_2_1",
                0,
                -2,
                -1,
                -1,
            ),
        )
        for drill, focus, outcome, scrim, trust, ceiling, heat, fan in cases:
            with self.subTest(drill=drill, focus=focus):
                pressure = self._pressure_for(drill, focus)
                self.assertEqual(pressure.outcome_id, outcome)
                self.assertEqual(pressure.scrim_result, scrim)
                self.assertEqual(pressure.review_room_trust_delta, trust)
                self.assertEqual(pressure.ceiling_signal_delta, ceiling)
                self.assertEqual(pressure.relationship_heat_delta, heat)
                self.assertEqual(pressure.fan_confidence_delta, fan)

    def test_pressure_artifact_names_setup_and_focus_sources(self):
        pressure = self._pressure_for("vex_aim", "prove_ceiling")
        payload = render_week7_pressure_json(pressure)

        self.assertIn('"source_setup_artifact": "week7_setup.json"', payload)
        self.assertIn('"source_focus_artifact": "week7_focus.json"', payload)
        self.assertIn('"outcome_id": "heat_ignored_highlight_loss"', payload)
        self.assertIn('"visible_consequence": "ignored_trust_fire"', payload)

    def test_recap_surfaces_remembered_memories(self):
        result = run_slice(self.world, self.config, self.decisions)
        md = recap_md(result, self.world)
        self.assertIn("What the room remembered", md)
        # Every cited memory id appears with its resolved summary.
        self.assertTrue(result.cited_memories, "the week should cite at least one precedent")
        for cite in result.cited_memories:
            self.assertIn(cite, md)
            entry = self.world.resolve_cite(cite)
            self.assertIsNotNone(entry)
            self.assertIn(entry.summary, md)


class TestDeterminism(_Fixture):
    def test_identical_recap_on_rerun_with_same_seed(self):
        first = recap_md(run_slice(self.world, self.config, self.decisions), self.world)
        for _ in range(5):
            again = recap_md(run_slice(self.world, self.config, self.decisions), self.world)
            self.assertEqual(again, first)

    def test_identical_feed_snapshot_on_rerun(self):
        first = feed_html(run_slice(self.world, self.config, self.decisions), self.world)
        for _ in range(5):
            self.assertEqual(feed_html(run_slice(self.world, self.config, self.decisions), self.world), first)

    def test_written_artifacts_are_byte_identical_across_runs(self):
        import tempfile

        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            r1, f1, e1 = write_artifacts(run_slice(self.world, self.config, self.decisions), self.world, a)
            r2, f2, e2 = write_artifacts(run_slice(self.world, self.config, self.decisions), self.world, b)
            self.assertEqual(r1.read_bytes(), r2.read_bytes())
            self.assertEqual(f1.read_bytes(), f2.read_bytes())
            self.assertEqual(e1.read_bytes(), e2.read_bytes())

    def test_artifacts_byte_identical_across_processes_and_hash_seeds(self):
        """The stronger contract: identical bytes across *separate processes* with
        different ``PYTHONHASHSEED`` values.

        The same-process check above shares one per-process hash seed, so it cannot
        catch set/dict iteration order leaking into the recap or — the classic
        offender — the HTML feed snapshot. Two CLI runs under different
        ``PYTHONHASHSEED`` values close that gap: if any entropy or hash-ordering
        leaked into the output, the bytes would diverge here.
        """
        import os
        import subprocess
        import sys
        import tempfile

        repo_root = pathlib.Path(__file__).resolve().parents[1]
        cli = [
            sys.executable, "-m", "esports_tycoon.runner",
            "--seed", "6", "--practice", "defaults",
            "--team-talk", self.decisions.team_talk,
            "--fallout", self.decisions.fallout_post,
        ]

        def run_under(hashseed: str, runs_dir: str) -> pathlib.Path:
            env = {**os.environ, "PYTHONHASHSEED": hashseed}
            subprocess.run(
                [*cli, "--runs-dir", runs_dir],
                cwd=repo_root, env=env, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            runs = list(pathlib.Path(runs_dir).glob("wk6-*"))
            self.assertEqual(len(runs), 1, "exactly one slice folder should be written")
            return runs[0]

        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            dir_a = run_under("0", a)
            dir_b = run_under("12345", b)
            # Same content-addressed slice id from independent processes.
            self.assertEqual(dir_a.name, dir_b.name)
            for fname in (RECAP_FILENAME, FEED_FILENAME, EVENTS_FILENAME):
                self.assertEqual(
                    (dir_a / fname).read_bytes(), (dir_b / fname).read_bytes(),
                    f"{fname} diverged across processes with different PYTHONHASHSEED",
                )

    def test_slice_id_is_stable_and_input_sensitive(self):
        base = slice_id(self.world, self.config, self.decisions)
        self.assertEqual(base, slice_id(self.world, self.config, self.decisions))
        # A different seed, opponent, or open-text line ⇒ a different run folder.
        other_seed = slice_id(self.world, SliceConfig(opponent="apex_foundry", map="Helix", seed=7), self.decisions)
        self.assertNotEqual(base, other_seed)
        other_text = slice_id(
            self.world,
            self.config,
            SliceDecisions(practice_focus="defaults", team_talk="different", fallout_post=self.decisions.fallout_post),
        )
        self.assertNotEqual(base, other_text)

    def test_different_seeds_can_differ(self):
        recaps = {
            recap_md(run_slice(self.world, SliceConfig(opponent="apex_foundry", seed=s), self.decisions), self.world)
            for s in range(8)
        }
        self.assertGreater(len(recaps), 1, "different seeds should produce visibly different weeks")


class TestGroundingAndSafety(_Fixture):
    def test_every_feed_cite_resolves(self):
        for opp in ("apex_foundry", "sovereign", "goblins", "northwind"):
            for seed in range(4):
                result = run_slice(self.world, SliceConfig(opponent=opp, seed=seed), self.decisions)
                for post in result.feed:
                    for cite in post.cites:
                        self.assertIsNotNone(self.world.resolve_cite(cite), f"dangling cite {cite}")
                # Templated mode grounds everything it tries to cite.
                self.assertEqual(result.grounded_ok, result.grounded_total)
                self.assertEqual(result.grounding_rate, 1.0)

    def test_open_text_is_html_escaped_in_snapshot(self):
        nasty = '<script>alert(1)</script>'
        decisions = SliceDecisions(practice_focus="aim", fallout_post=nasty)
        html = feed_html(run_slice(self.world, self.config, decisions), self.world)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_run_never_constructs_the_llm_client(self):
        # Booby-trap the LLM client: templated slice play must never touch it.
        def explode():
            raise AssertionError("templated slice must not construct an LLM client")

        original = game_llm.get_llm
        game_llm.get_llm = explode
        try:
            result = run_slice(self.world, self.config, self.decisions)
            render_recap_md(slice_events(result, self.world), self.world)
            render_feed_html(slice_events(result, self.world), self.world)
        finally:
            game_llm.get_llm = original


if __name__ == "__main__":
    unittest.main()
