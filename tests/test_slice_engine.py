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
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import game_llm  # noqa: E402
from esports_tycoon.runner import (  # noqa: E402
    EVENTS_FILENAME,
    FEED_FILENAME,
    OPEN_TEXT_MAX,
    RECAP_FILENAME,
    WEEK7_SETUP_FILENAME,
    pressure_payload_from_json,
    focus_payload_from_json,
    SliceConfig,
    SliceDecisions,
    render_feed_html,
    render_recap_md,
    render_week7_focus_json,
    render_week7_pressure_json,
    render_week8_match_plan_json,
    render_week8_match_result_json,
    render_week8_prep_json,
    render_week8_scrim_json,
    render_week9_match_plan_json,
    render_week9_match_result_json,
    render_week9_prep_json,
    render_week9_scrim_json,
    render_week9_setup_json,
    render_week10_fallout_json,
    render_week10_match_plan_json,
    render_week10_match_result_json,
    render_week10_post_match_review_json,
    render_week10_prep_json,
    render_week10_scrim_json,
    render_week11_setup_json,
    run_slice,
    resolve_week7_focus,
    resolve_week7_pressure,
    resolve_week8_match_plan,
    resolve_week8_match_result,
    resolve_week8_prep,
    resolve_week8_scrim,
    resolve_week9_match_plan,
    resolve_week9_match_result,
    resolve_week9_prep,
    resolve_week9_scrim,
    resolve_week9_setup,
    resolve_week10_fallout,
    resolve_week10_match_plan,
    resolve_week10_match_result,
    resolve_week10_post_match_review,
    resolve_week10_prep,
    resolve_week10_scrim,
    resolve_week11_setup,
    setup_payload_from_week7_setup,
    slice_events,
    training_decision_for_drill,
    week8_match_preview,
    week8_prep_plan,
    week8_scrim_plan,
    week9_match_plan_preview,
    week9_prep_plan,
    week9_scrim_plan,
    week9_setup_plan,
    week10_fallout_plan,
    week10_match_plan_from_json,
    week10_match_plan_preview,
    week10_match_result_from_json,
    week10_post_match_review_from_json,
    week10_post_match_review_plan,
    week10_prep_from_json,
    week10_prep_plan,
    week10_scrim_from_json,
    week10_scrim_plan,
    week11_setup_from_json,
    week11_setup_plan,
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


class TestWeek8PrepFork(_Fixture):
    def _receipts_for(self, drill: str, selected_focus: str):
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
        pressure = resolve_week7_pressure(setup, focus)
        pressure_payload = pressure_payload_from_json(render_week7_pressure_json(pressure))
        return setup, focus, pressure_payload

    def _plan_for(self, drill: str, selected_focus: str):
        return week8_prep_plan(*self._receipts_for(drill, selected_focus))

    def test_maps_all_pressure_outcomes_to_week8_problems(self):
        cases = (
            ("vex_aim", "contain_fallout", "heat_contained_scrappy_win", "low_ceiling_after_reset"),
            ("vex_aim", "prove_ceiling", "heat_ignored_highlight_loss", "vex_pixie_trust_fracture"),
            (
                "pixie_flash_repair",
                "prove_ceiling",
                "stability_unlocked_clean_2_0",
                "identity_needs_second_layer",
            ),
            (
                "pixie_flash_repair",
                "contain_fallout",
                "stability_overmanaged_flat_win",
                "overmanaged_low_threat",
            ),
        )
        for drill, focus, outcome, exposed in cases:
            with self.subTest(drill=drill, focus=focus):
                plan = self._plan_for(drill, focus)
                self.assertEqual(plan.source_pressure_outcome, outcome)
                self.assertEqual(plan.exposed_problem, exposed)
                self.assertEqual(
                    [option.value for option in plan.options],
                    ["patch_exposed_break", "double_down_identity"],
                )

    def test_week8_prep_choices_create_different_tradeoffs(self):
        plan = self._plan_for("vex_aim", "prove_ceiling")

        patched = resolve_week8_prep(plan, "patch_exposed_break")
        doubled = resolve_week8_prep(plan, "double_down_identity")

        self.assertEqual(patched.week8_modifier, "lower_volatility")
        self.assertEqual(patched.review_room_trust_delta, 1)
        self.assertEqual(patched.competitive_edge_delta, -1)
        self.assertEqual(doubled.week8_modifier, "higher_ceiling_higher_tilt")
        self.assertEqual(doubled.review_room_trust_delta, -1)
        self.assertEqual(doubled.competitive_edge_delta, 1)
        self.assertEqual(patched.exposed_problem, "vex_pixie_trust_fracture")
        self.assertIn("vex_pixie_trust_fracture", render_week8_prep_json(doubled))

    def test_week8_prep_artifact_names_sources(self):
        plan = self._plan_for("pixie_flash_repair", "prove_ceiling")
        lock = resolve_week8_prep(plan, "double_down_identity")
        payload = render_week8_prep_json(lock)

        self.assertIn('"week7_pressure": "week7_pressure.json"', payload)
        self.assertIn('"source_pressure_outcome": "stability_unlocked_clean_2_0"', payload)
        self.assertIn('"selected_choice": "double_down_identity"', payload)
        self.assertIn('"week8_modifier": "higher_ceiling_higher_tilt"', payload)


class TestWeek8ScrimSetup(_Fixture):
    def _scrim_plan_for(self, drill: str, selected_focus: str, prep_choice: str):
        setup, focus, pressure = TestWeek8PrepFork._receipts_for(self, drill, selected_focus)
        prep_plan = week8_prep_plan(setup, focus, pressure)
        prep = resolve_week8_prep(prep_plan, prep_choice)
        return week8_scrim_plan(setup, focus, pressure, prep)

    def test_week8_scrim_setup_changes_by_prep_branch(self):
        patched = self._scrim_plan_for("vex_aim", "prove_ceiling", "patch_exposed_break")
        doubled = self._scrim_plan_for("vex_aim", "prove_ceiling", "double_down_identity")

        self.assertEqual(patched.scrim_modifier, "trust_buffer")
        self.assertEqual(patched.scrim_opening_state, "controlled_reset")
        self.assertEqual(doubled.scrim_modifier, "tempo_spike")
        self.assertEqual(doubled.scrim_opening_state, "volatile_opener")
        self.assertIn("vex_pixie_trust_fracture", patched.setup_body)
        self.assertEqual(doubled.options[0].label, "Force the identity")

    def test_week8_scrim_calls_create_different_setup_locks(self):
        plan = self._scrim_plan_for("pixie_flash_repair", "prove_ceiling", "patch_exposed_break")

        play = resolve_week8_scrim(plan, "play_to_prep")
        cover = resolve_week8_scrim(plan, "cover_the_crack")

        self.assertEqual(play.visible_consequence, "patched_protocol_held")
        self.assertEqual(play.readiness_delta, 2)
        self.assertEqual(play.tempo_delta, -1)
        self.assertEqual(cover.visible_consequence, "patch_tested_early")
        self.assertEqual(cover.tempo_delta, 1)
        self.assertEqual(cover.tilt_risk_delta, -1)

    def test_week8_scrim_artifact_names_sources(self):
        plan = self._scrim_plan_for("pixie_flash_repair", "contain_fallout", "double_down_identity")
        lock = resolve_week8_scrim(plan, "cover_the_crack")
        payload = render_week8_scrim_json(lock)

        self.assertIn('"week8_prep": "week8_prep.json"', payload)
        self.assertIn('"scrim_modifier": "tempo_spike"', payload)
        self.assertIn('"selected_call": "cover_the_crack"', payload)
        self.assertIn('"visible_consequence": "identity_split_reps"', payload)

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


class TestWeek8MatchPreview(_Fixture):
    def _preview_for(
        self,
        drill: str,
        selected_focus: str,
        prep_choice: str,
        scrim_call: str,
    ):
        setup, focus, pressure = TestWeek8PrepFork._receipts_for(self, drill, selected_focus)
        prep_plan = week8_prep_plan(setup, focus, pressure)
        prep = resolve_week8_prep(prep_plan, prep_choice)
        scrim_plan = week8_scrim_plan(setup, focus, pressure, prep)
        scrim = resolve_week8_scrim(scrim_plan, scrim_call)
        return week8_match_preview(setup, focus, pressure, prep, scrim)

    def test_week8_match_preview_changes_by_scrim_signal(self):
        protected = self._preview_for(
            "pixie_flash_repair",
            "prove_ceiling",
            "patch_exposed_break",
            "play_to_prep",
        )
        forced = self._preview_for(
            "vex_aim",
            "prove_ceiling",
            "double_down_identity",
            "play_to_prep",
        )

        self.assertEqual(protected.scrim_signal, "patched_protocol_held")
        self.assertEqual(protected.match_risk, "low")
        self.assertEqual(protected.team_edge, "cleaner_first_contact")
        self.assertEqual(protected.recommended_plan, "lean_into_edge")
        self.assertEqual(forced.scrim_signal, "identity_forced")
        self.assertEqual(forced.match_risk, "high")
        self.assertEqual(forced.team_edge, "explosive_opening_tempo")
        self.assertEqual(forced.recommended_plan, "patch_weakness")

    def test_week8_match_plan_choices_create_different_locks(self):
        preview = self._preview_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
        )

        patched = resolve_week8_match_plan(preview, "patch_weakness")
        edge = resolve_week8_match_plan(preview, "lean_into_edge")

        self.assertEqual(patched.match_pressure, "protected_opener")
        self.assertEqual(patched.readiness_delta, 1)
        self.assertEqual(patched.edge_delta, -1)
        self.assertEqual(patched.risk_delta, -1)
        self.assertEqual(edge.match_pressure, "edge_first_opener")
        self.assertEqual(edge.edge_delta, 1)
        self.assertEqual(edge.risk_delta, 1)
        self.assertIn("carried_into_match", edge.next_problem)

    def test_week8_match_plan_artifact_names_sources(self):
        preview = self._preview_for(
            "pixie_flash_repair",
            "contain_fallout",
            "double_down_identity",
            "cover_the_crack",
        )
        lock = resolve_week8_match_plan(preview, "lean_into_edge")
        payload = render_week8_match_plan_json(lock)

        self.assertIn('"week8_scrim": "week8_scrim.json"', payload)
        self.assertIn('"artifact_type": "week8_match_plan"', payload)
        self.assertIn('"selected_plan": "lean_into_edge"', payload)
        self.assertIn('"scrim_signal": "identity_split_reps"', payload)


class TestWeek8MatchResult(_Fixture):
    def _match_plan_for(
        self,
        drill: str,
        selected_focus: str,
        prep_choice: str,
        scrim_call: str,
        match_plan_choice: str,
    ):
        preview = TestWeek8MatchPreview._preview_for(
            self,
            drill,
            selected_focus,
            prep_choice,
            scrim_call,
        )
        return resolve_week8_match_plan(preview, match_plan_choice)

    def test_recommended_low_risk_plan_resolves_clean_win(self):
        plan = self._match_plan_for(
            "pixie_flash_repair",
            "prove_ceiling",
            "patch_exposed_break",
            "play_to_prep",
            "lean_into_edge",
        )

        result = resolve_week8_match_result(plan)

        self.assertEqual(result.outcome_id, "clean_win")
        self.assertEqual(result.match_result, "win")
        self.assertEqual(result.scoreline, "2-0")
        self.assertTrue(result.matched_recommendation)
        self.assertEqual(result.consequence_axis, "confidence")

    def test_ignored_high_risk_recommendation_resolves_loss(self):
        plan = self._match_plan_for(
            "vex_aim",
            "prove_ceiling",
            "double_down_identity",
            "play_to_prep",
            "lean_into_edge",
        )

        result = resolve_week8_match_result(plan)

        self.assertEqual(result.outcome_id, "loss_with_signal")
        self.assertEqual(result.match_result, "loss")
        self.assertEqual(result.scoreline, "0-2")
        self.assertFalse(result.matched_recommendation)
        self.assertIn("retake_blame_pressure", result.plan_effect)

    def test_week8_match_result_artifact_names_source_plan(self):
        plan = self._match_plan_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
        )
        result = resolve_week8_match_result(plan)
        payload = render_week8_match_result_json(result)

        self.assertIn('"week8_match_plan": "week8_match_plan.json"', payload)
        self.assertIn('"artifact_type": "week8_match_result"', payload)
        self.assertIn('"outcome_id": "messy_win"', payload)
        self.assertIn('"week9_hook":', payload)


class TestWeek9FalloutSetup(_Fixture):
    def _week9_plan_for(
        self,
        drill: str,
        selected_focus: str,
        prep_choice: str,
        scrim_call: str,
        match_plan_choice: str,
    ):
        match_plan = TestWeek8MatchResult._match_plan_for(
            self,
            drill,
            selected_focus,
            prep_choice,
            scrim_call,
            match_plan_choice,
        )
        match_result = resolve_week8_match_result(match_plan)
        return week9_setup_plan(match_result)

    def test_week9_setup_changes_by_week8_outcome(self):
        clean = self._week9_plan_for(
            "pixie_flash_repair",
            "prove_ceiling",
            "patch_exposed_break",
            "play_to_prep",
            "lean_into_edge",
        )
        messy = self._week9_plan_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
        )
        loss = self._week9_plan_for(
            "vex_aim",
            "prove_ceiling",
            "double_down_identity",
            "play_to_prep",
            "lean_into_edge",
        )

        self.assertEqual(clean.week9_problem_id, "expectations_spike")
        self.assertEqual(clean.recommended_response, "double_down_read")
        self.assertEqual(messy.week9_problem_id, "legitimacy_pressure")
        self.assertEqual(messy.recommended_response, "control_public_story")
        self.assertEqual(loss.week9_problem_id, "proof_of_learning")
        self.assertEqual(loss.recommended_response, "stabilize_roster")

    def test_week9_responses_create_different_setup_locks(self):
        plan = self._week9_plan_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
        )

        stabilize = resolve_week9_setup(plan, "stabilize_roster")
        double = resolve_week9_setup(plan, "double_down_read")
        story = resolve_week9_setup(plan, "control_public_story")

        self.assertEqual(stabilize.prep_bias, "room_stability")
        self.assertEqual(stabilize.risk_delta, -1)
        self.assertEqual(double.prep_bias, "strategic_conviction")
        self.assertEqual(double.risk_delta, 1)
        self.assertEqual(story.prep_bias, "external_pressure")
        self.assertTrue(story.followed_recommendation)

    def test_week9_setup_artifact_names_source_result(self):
        plan = self._week9_plan_for(
            "pixie_flash_repair",
            "prove_ceiling",
            "patch_exposed_break",
            "play_to_prep",
            "lean_into_edge",
        )
        lock = resolve_week9_setup(plan, "double_down_read")
        payload = render_week9_setup_json(lock)

        self.assertIn('"week8_match_result": "week8_match_result.json"', payload)
        self.assertIn('"artifact_type": "week9_setup"', payload)
        self.assertIn('"selected_response": "double_down_read"', payload)
        self.assertIn('"next_artifact": "week9_prep.json"', payload)


class TestWeek9PrepChoice(_Fixture):
    def _prep_plan_for(
        self,
        drill: str,
        selected_focus: str,
        prep_choice: str,
        scrim_call: str,
        match_plan_choice: str,
        response_choice: str,
    ):
        setup_plan = TestWeek9FalloutSetup._week9_plan_for(
            self,
            drill,
            selected_focus,
            prep_choice,
            scrim_call,
            match_plan_choice,
        )
        setup = resolve_week9_setup(setup_plan, response_choice)
        return week9_prep_plan(setup)

    def test_week9_prep_recommendation_changes_by_response_posture(self):
        stabilize = self._prep_plan_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
            "stabilize_roster",
        )
        double = self._prep_plan_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
            "double_down_read",
        )
        story = self._prep_plan_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
            "control_public_story",
        )

        self.assertEqual(stabilize.recommended_prep, "balance_risk")
        self.assertEqual(double.recommended_prep, "lean_into_bias")
        self.assertEqual(story.recommended_prep, "counter_read")

    def test_week9_prep_choices_create_different_locks(self):
        plan = self._prep_plan_for(
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
            "control_public_story",
        )

        lean = resolve_week9_prep(plan, "lean_into_bias")
        balance = resolve_week9_prep(plan, "balance_risk")
        counter = resolve_week9_prep(plan, "counter_read")

        self.assertEqual(lean.selected_prep_bias, "external_pressure")
        self.assertEqual(lean.match_read_alignment, "follow_bias")
        self.assertEqual(balance.selected_prep_bias, "fundamentals")
        self.assertEqual(balance.combined_risk_delta, -2)
        self.assertEqual(counter.selected_prep_bias, "public_read_counter")
        self.assertEqual(counter.combined_external_pressure_delta, 0)

    def test_week9_prep_artifact_names_source_setup(self):
        plan = self._prep_plan_for(
            "pixie_flash_repair",
            "prove_ceiling",
            "patch_exposed_break",
            "play_to_prep",
            "lean_into_edge",
            "double_down_read",
        )
        lock = resolve_week9_prep(plan, "lean_into_bias")
        payload = render_week9_prep_json(lock)

        self.assertIn('"week9_setup": "week9_setup.json"', payload)
        self.assertIn('"artifact_type": "week9_prep"', payload)
        self.assertIn('"selected_prep": "lean_into_bias"', payload)
        self.assertIn('"next_artifact": "week9_scrim.json"', payload)


class TestWeek9ScrimChoice(_Fixture):
    def _scrim_plan_for(
        self,
        response_choice: str,
        prep_choice: str,
    ):
        prep_plan = TestWeek9PrepChoice._prep_plan_for(
            self,
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
            response_choice,
        )
        setup_plan = TestWeek9FalloutSetup._week9_plan_for(
            self,
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
        )
        setup = resolve_week9_setup(setup_plan, response_choice)
        prep = resolve_week9_prep(prep_plan, prep_choice)
        return week9_scrim_plan(setup, prep)

    def test_week9_scrim_reads_are_fixed_and_recommended_from_setup_and_prep(self):
        public = self._scrim_plan_for("control_public_story", "counter_read")
        room = self._scrim_plan_for("stabilize_roster", "lean_into_bias")
        tactical = self._scrim_plan_for("double_down_read", "balance_risk")

        self.assertEqual(tuple(read.value for read in public.reads), ("room_read", "public_read", "tactical_read"))
        self.assertEqual(public.recommended_scrim_read, "public_read")
        self.assertEqual(room.recommended_scrim_read, "room_read")
        self.assertEqual(tactical.recommended_scrim_read, "tactical_read")

    def test_week9_scrim_output_changes_when_prep_lane_changes(self):
        setup_aligned = self._scrim_plan_for("control_public_story", "counter_read")
        setup_conflicted = self._scrim_plan_for("control_public_story", "balance_risk")

        self.assertEqual(setup_aligned.setup_read_id, "public_read")
        self.assertEqual(setup_aligned.prep_read_id, "public_read")
        self.assertEqual(setup_conflicted.setup_read_id, "public_read")
        self.assertEqual(setup_conflicted.prep_read_id, "tactical_read")
        self.assertNotEqual(
            setup_aligned.recommendation_reason,
            setup_conflicted.recommendation_reason,
        )

    def test_week9_scrim_artifact_names_source_prep_and_stops_before_match_plan(self):
        plan = self._scrim_plan_for("control_public_story", "counter_read")
        lock = resolve_week9_scrim(plan, "public_read")
        payload = render_week9_scrim_json(lock)

        self.assertIn('"week9_setup": "week9_setup.json"', payload)
        self.assertIn('"week9_prep": "week9_prep.json"', payload)
        self.assertIn('"artifact_type": "week9_scrim"', payload)
        self.assertIn('"selected_scrim_read": "public_read"', payload)
        self.assertIn('"next_artifact": "week9_match_plan.json"', payload)
        self.assertNotIn('"selected_match_plan"', payload)
        self.assertNotIn('"match_result"', payload)


class TestWeek9MatchPlanChoice(_Fixture):
    def _match_preview_for(
        self,
        response_choice: str,
        prep_choice: str,
        scrim_read: str,
    ):
        prep_plan = TestWeek9PrepChoice._prep_plan_for(
            self,
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
            response_choice,
        )
        setup_plan = TestWeek9FalloutSetup._week9_plan_for(
            self,
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
        )
        setup = resolve_week9_setup(setup_plan, response_choice)
        prep = resolve_week9_prep(prep_plan, prep_choice)
        scrim_plan = week9_scrim_plan(setup, prep)
        scrim = resolve_week9_scrim(scrim_plan, scrim_read)
        return week9_match_plan_preview(setup, prep, scrim)

    def test_week9_match_plan_options_are_fixed(self):
        preview = self._match_preview_for("control_public_story", "counter_read", "public_read")

        self.assertEqual(
            tuple(option.value for option in preview.options),
            ("protect_the_room", "play_the_prep", "counter_the_read"),
        )

    def test_week9_match_plan_recommendation_uses_room_alignment_and_counter_reads(self):
        room = self._match_preview_for("stabilize_roster", "lean_into_bias", "room_read")
        aligned = self._match_preview_for("control_public_story", "counter_read", "public_read")
        counter = self._match_preview_for("control_public_story", "counter_read", "tactical_read")

        self.assertEqual(room.recommended_plan, "protect_the_room")
        self.assertEqual(aligned.recommended_plan, "play_the_prep")
        self.assertEqual(counter.recommended_plan, "counter_the_read")

    def test_week9_match_plan_artifact_sources_scrim_and_stops_before_result(self):
        preview = self._match_preview_for("control_public_story", "counter_read", "public_read")
        lock = resolve_week9_match_plan(preview, "play_the_prep")
        payload = render_week9_match_plan_json(lock)

        self.assertIn('"week9_setup": "week9_setup.json"', payload)
        self.assertIn('"week9_prep": "week9_prep.json"', payload)
        self.assertIn('"week9_scrim": "week9_scrim.json"', payload)
        self.assertIn('"artifact_type": "week9_match_plan"', payload)
        self.assertIn('"selected_plan": "play_the_prep"', payload)
        self.assertIn('"result_constraints":', payload)
        self.assertIn('"stops_before": "match_result"', payload)
        self.assertIn('"next_artifact": "week9_match_result.json"', payload)
        self.assertNotIn('"week9_match_result"', payload)
        self.assertNotIn('"winner"', payload)


class TestWeek9MatchResult(_Fixture):
    def _match_result_for(
        self,
        response_choice: str,
        prep_choice: str,
        scrim_read: str,
        selected_plan: str,
    ):
        setup_plan = TestWeek9FalloutSetup._week9_plan_for(
            self,
            "vex_aim",
            "prove_ceiling",
            "patch_exposed_break",
            "cover_the_crack",
            "patch_weakness",
        )
        setup = resolve_week9_setup(setup_plan, response_choice)
        prep = resolve_week9_prep(week9_prep_plan(setup), prep_choice)
        scrim = resolve_week9_scrim(week9_scrim_plan(setup, prep), scrim_read)
        preview = week9_match_plan_preview(setup, prep, scrim)
        plan = resolve_week9_match_plan(preview, selected_plan)
        return setup, prep, scrim, plan, resolve_week9_match_result(setup, prep, scrim, plan)

    def test_week9_match_result_outcomes_cover_plan_success_and_failure(self):
        cases = (
            ("stabilize_roster", "lean_into_bias", "room_read", "protect_the_room", "room_held"),
            ("control_public_story", "counter_read", "public_read", "protect_the_room", "room_cracked"),
            ("control_public_story", "counter_read", "public_read", "play_the_prep", "prep_converted"),
            ("control_public_story", "counter_read", "tactical_read", "play_the_prep", "prep_stalled"),
            ("control_public_story", "counter_read", "tactical_read", "counter_the_read", "read_punished"),
            (
                "stabilize_roster",
                "lean_into_bias",
                "room_read",
                "counter_the_read",
                "counter_overreached",
            ),
        )

        for response, prep, scrim, plan, expected in cases:
            with self.subTest(plan=plan, expected=expected):
                *_, result = self._match_result_for(response, prep, scrim, plan)
                self.assertEqual(result.outcome_id, expected)

    def test_week9_match_result_artifact_sources_all_inputs_and_stops_before_week10(self):
        *_, result = self._match_result_for(
            "control_public_story",
            "counter_read",
            "public_read",
            "play_the_prep",
        )
        payload = render_week9_match_result_json(result)

        self.assertIn('"week9_setup": "week9_setup.json"', payload)
        self.assertIn('"week9_prep": "week9_prep.json"', payload)
        self.assertIn('"week9_scrim": "week9_scrim.json"', payload)
        self.assertIn('"week9_match_plan": "week9_match_plan.json"', payload)
        self.assertIn('"artifact_type": "week9_match_result"', payload)
        self.assertIn('"outcome_id": "prep_converted"', payload)
        self.assertIn('"next_artifact": "week10_fallout.json"', payload)
        self.assertIn('"stops_before": "week10_fallout"', payload)
        self.assertNotIn('"week10_fallout"', payload.split('"next_artifact"')[0])
        self.assertNotIn('"winner"', payload)

    def test_week9_match_result_rejects_mismatched_plan_artifact(self):
        setup, prep, scrim, plan, _ = self._match_result_for(
            "control_public_story",
            "counter_read",
            "public_read",
            "play_the_prep",
        )
        mismatched = replace(plan, selected_scrim_read="room_read")

        with self.assertRaisesRegex(ValueError, "scrim read"):
            resolve_week9_match_result(setup, prep, scrim, mismatched)


class TestWeek10Fallout(_Fixture):
    def _week9_results_by_outcome(self):
        cases = (
            ("stabilize_roster", "lean_into_bias", "room_read", "protect_the_room"),
            ("control_public_story", "counter_read", "public_read", "protect_the_room"),
            ("control_public_story", "counter_read", "public_read", "play_the_prep"),
            ("control_public_story", "counter_read", "tactical_read", "play_the_prep"),
            ("control_public_story", "counter_read", "tactical_read", "counter_the_read"),
            ("stabilize_roster", "lean_into_bias", "room_read", "counter_the_read"),
        )
        results = {}
        for response, prep, scrim, plan in cases:
            *_, result = TestWeek9MatchResult._match_result_for(self, response, prep, scrim, plan)
            results[result.outcome_id] = result
        return results

    def test_week10_fallout_choice_matrix_is_stable(self):
        expected = {
            ("room_held", "steady_room"): "room_recentered",
            ("room_held", "raise_standards"): "standards_locked",
            ("room_held", "adapt_system"): "system_blurred",
            ("room_cracked", "steady_room"): "room_recentered",
            ("room_cracked", "raise_standards"): "standards_overfit",
            ("room_cracked", "adapt_system"): "system_blurred",
            ("prep_converted", "steady_room"): "room_overmanaged",
            ("prep_converted", "raise_standards"): "standards_locked",
            ("prep_converted", "adapt_system"): "system_adjusted",
            ("prep_stalled", "steady_room"): "room_recentered",
            ("prep_stalled", "raise_standards"): "standards_overfit",
            ("prep_stalled", "adapt_system"): "system_adjusted",
            ("read_punished", "steady_room"): "room_overmanaged",
            ("read_punished", "raise_standards"): "standards_locked",
            ("read_punished", "adapt_system"): "system_adjusted",
            ("counter_overreached", "steady_room"): "room_recentered",
            ("counter_overreached", "raise_standards"): "standards_overfit",
            ("counter_overreached", "adapt_system"): "system_adjusted",
        }
        results = self._week9_results_by_outcome()

        for (week9_outcome, choice), fallout_outcome in expected.items():
            with self.subTest(week9_outcome=week9_outcome, choice=choice):
                result = results[week9_outcome]
                plan = week10_fallout_plan(result)
                lock = resolve_week10_fallout(result, plan, choice)
                self.assertEqual(lock.outcome_id, fallout_outcome)

    def test_week10_fallout_artifact_sources_result_and_stops_before_prep(self):
        result = self._week9_results_by_outcome()["prep_converted"]
        plan = week10_fallout_plan(result)
        lock = resolve_week10_fallout(result, plan, "raise_standards")
        payload = render_week10_fallout_json(lock)

        self.assertIn('"week9_match_result": "week9_match_result.json"', payload)
        self.assertIn('"artifact_type": "week10_fallout"', payload)
        self.assertIn('"selected_choice": "raise_standards"', payload)
        self.assertIn('"outcome_id": "standards_locked"', payload)
        self.assertIn('"stops_before": "week10_prep"', payload)
        self.assertIn('"next_artifact": "week10_prep.json"', payload)
        self.assertNotIn('"week10_prep"', payload.split('"next_artifact"')[0])

    def test_week10_fallout_rejects_invalid_choice(self):
        result = self._week9_results_by_outcome()["prep_converted"]
        plan = week10_fallout_plan(result)

        with self.assertRaisesRegex(ValueError, "selected_choice"):
            resolve_week10_fallout(result, plan, "sponsor_panic")


class TestWeek10Prep(_Fixture):
    def _prep_fallout_for(self, choice="raise_standards"):
        result = TestWeek10Fallout._week9_results_by_outcome(self)["prep_converted"]
        plan = week10_fallout_plan(result)
        return resolve_week10_fallout(result, plan, choice)

    def test_week10_prep_recommendation_uses_fallout_state(self):
        cases = {
            "system_adjusted": "scout_counter",
            "room_overmanaged": "staff_review",
            "standards_overfit": "staff_review",
            "system_blurred": "staff_review",
            "standards_locked": "roster_reps",
            "room_recentered": "roster_reps",
        }
        result = TestWeek10Fallout._week9_results_by_outcome(self)["prep_converted"]
        for fallout_choice in ("steady_room", "raise_standards", "adapt_system"):
            with self.subTest(fallout_choice=fallout_choice):
                fallout = resolve_week10_fallout(result, week10_fallout_plan(result), fallout_choice)
                plan = week10_prep_plan(fallout)
                self.assertEqual(plan.advisor_packet.recommended_prep, cases[fallout.outcome_id])

    def test_week10_prep_choice_matrix_is_stable(self):
        outcomes = {
            ("room_recentered", "scout_counter"): "counter_read_overfit",
            ("room_recentered", "staff_review"): "review_loop_locked",
            ("room_recentered", "roster_reps"): "reps_translated",
            ("room_overmanaged", "scout_counter"): "counter_read_overfit",
            ("room_overmanaged", "staff_review"): "review_loop_locked",
            ("room_overmanaged", "roster_reps"): "reps_burned",
            ("standards_locked", "scout_counter"): "counter_read_overfit",
            ("standards_locked", "staff_review"): "review_loop_drift",
            ("standards_locked", "roster_reps"): "reps_translated",
            ("standards_overfit", "scout_counter"): "counter_read_overfit",
            ("standards_overfit", "staff_review"): "review_loop_locked",
            ("standards_overfit", "roster_reps"): "reps_burned",
            ("system_adjusted", "scout_counter"): "counter_read_ready",
            ("system_adjusted", "staff_review"): "review_loop_drift",
            ("system_adjusted", "roster_reps"): "reps_burned",
            ("system_blurred", "scout_counter"): "counter_read_overfit",
            ("system_blurred", "staff_review"): "review_loop_locked",
            ("system_blurred", "roster_reps"): "reps_burned",
        }
        fallout_by_outcome = {}
        for result in TestWeek10Fallout._week9_results_by_outcome(self).values():
            for fallout_choice in ("steady_room", "raise_standards", "adapt_system"):
                fallout = resolve_week10_fallout(result, week10_fallout_plan(result), fallout_choice)
                fallout_by_outcome.setdefault(fallout.outcome_id, fallout)

        for (fallout_outcome, prep_choice), expected in outcomes.items():
            with self.subTest(fallout_outcome=fallout_outcome, prep_choice=prep_choice):
                fallout = fallout_by_outcome[fallout_outcome]
                plan = week10_prep_plan(fallout)
                lock = resolve_week10_prep(fallout, plan, prep_choice)
                self.assertEqual(lock.outcome_id, expected)

    def test_week10_prep_artifact_sources_fallout_and_stops_before_scrim(self):
        fallout = self._prep_fallout_for("raise_standards")
        plan = week10_prep_plan(fallout)
        lock = resolve_week10_prep(fallout, plan, "roster_reps")
        payload = render_week10_prep_json(lock)

        self.assertIn('"week10_fallout": "week10_fallout.json"', payload)
        self.assertIn('"artifact_type": "week10_prep"', payload)
        self.assertIn('"advisor_packet":', payload)
        self.assertIn('"selected_choice": "roster_reps"', payload)
        self.assertIn('"outcome_id": "reps_translated"', payload)
        self.assertIn('"prep_effect":', payload)
        self.assertIn('"stops_before": "week10_scrim"', payload)
        self.assertIn('"next_artifact": "week10_scrim.json"', payload)
        self.assertNotIn('"week10_scrim"', payload.split('"next_artifact"')[0])

    def test_week10_prep_render_parse_round_trip_is_stable(self):
        fallout = self._prep_fallout_for("raise_standards")
        plan = week10_prep_plan(fallout)
        lock = resolve_week10_prep(fallout, plan, "roster_reps")
        payload = render_week10_prep_json(lock)
        parsed = week10_prep_from_json(payload)

        self.assertEqual(parsed, lock)
        self.assertEqual(render_week10_prep_json(parsed), payload)

    def test_week10_prep_rejects_invalid_choice(self):
        fallout = self._prep_fallout_for("raise_standards")
        plan = week10_prep_plan(fallout)

        with self.assertRaisesRegex(ValueError, "selected_choice"):
            resolve_week10_prep(fallout, plan, "hire_psychologist")


class TestWeek10Scrim(_Fixture):
    def _preps_by_outcome(self):
        preps = {}
        for result in TestWeek10Fallout._week9_results_by_outcome(self).values():
            fallout_plan = week10_fallout_plan(result)
            for fallout_choice in ("steady_room", "raise_standards", "adapt_system"):
                fallout = resolve_week10_fallout(result, fallout_plan, fallout_choice)
                prep_plan = week10_prep_plan(fallout)
                for prep_choice in ("scout_counter", "staff_review", "roster_reps"):
                    prep = resolve_week10_prep(fallout, prep_plan, prep_choice)
                    preps.setdefault(prep.outcome_id, prep)
        return preps

    def test_week10_scrim_recommendation_uses_prep_effects(self):
        cases = {
            "counter_read_ready": "validate_read",
            "counter_read_overfit": "stabilize_comms",
            "review_loop_locked": "stabilize_comms",
            "review_loop_drift": "stabilize_comms",
            "reps_translated": "stress_execution",
            "reps_burned": "stabilize_comms",
        }

        for prep_outcome, expected in cases.items():
            with self.subTest(prep_outcome=prep_outcome):
                plan = week10_scrim_plan(self._preps_by_outcome()[prep_outcome])
                self.assertEqual(plan.recommended_scrim, expected)

    def test_week10_scrim_choice_matrix_is_stable(self):
        outcomes = {
            ("counter_read_ready", "validate_read"): "read_validated",
            ("counter_read_ready", "stress_execution"): "execution_frayed",
            ("counter_read_ready", "stabilize_comms"): "comms_turtled",
            ("counter_read_overfit", "validate_read"): "read_exposed",
            ("counter_read_overfit", "stress_execution"): "execution_frayed",
            ("counter_read_overfit", "stabilize_comms"): "comms_stabilized",
            ("review_loop_locked", "validate_read"): "read_validated",
            ("review_loop_locked", "stress_execution"): "execution_frayed",
            ("review_loop_locked", "stabilize_comms"): "comms_stabilized",
            ("review_loop_drift", "validate_read"): "read_exposed",
            ("review_loop_drift", "stress_execution"): "execution_frayed",
            ("review_loop_drift", "stabilize_comms"): "comms_stabilized",
            ("reps_translated", "validate_read"): "read_exposed",
            ("reps_translated", "stress_execution"): "execution_translated",
            ("reps_translated", "stabilize_comms"): "comms_stabilized",
            ("reps_burned", "validate_read"): "read_exposed",
            ("reps_burned", "stress_execution"): "execution_frayed",
            ("reps_burned", "stabilize_comms"): "comms_stabilized",
        }
        preps = self._preps_by_outcome()

        for (prep_outcome, scrim_choice), expected in outcomes.items():
            with self.subTest(prep_outcome=prep_outcome, scrim_choice=scrim_choice):
                prep = preps[prep_outcome]
                lock = resolve_week10_scrim(prep, week10_scrim_plan(prep), scrim_choice)
                self.assertEqual(lock.outcome_id, expected)

    def test_week10_scrim_artifact_sources_prep_and_stops_before_match_plan(self):
        prep = self._preps_by_outcome()["reps_translated"]
        plan = week10_scrim_plan(prep)
        lock = resolve_week10_scrim(prep, plan, "stress_execution")
        payload = render_week10_scrim_json(lock)

        self.assertIn('"week10_prep": "week10_prep.json"', payload)
        self.assertIn('"artifact_type": "week10_scrim"', payload)
        self.assertIn('"selected_scrim": "stress_execution"', payload)
        self.assertIn('"outcome_id": "execution_translated"', payload)
        self.assertIn('"scrim_effect":', payload)
        self.assertIn('"lane_states":', payload)
        self.assertIn('"stops_before": "week10_match_plan"', payload)
        self.assertIn('"next_artifact": "week10_match_plan.json"', payload)

    def test_week10_scrim_render_parse_round_trip_is_stable(self):
        prep = self._preps_by_outcome()["reps_translated"]
        plan = week10_scrim_plan(prep)
        lock = resolve_week10_scrim(prep, plan, "stress_execution")
        payload = render_week10_scrim_json(lock)
        parsed = week10_scrim_from_json(payload)

        self.assertEqual(parsed, lock)
        self.assertEqual(render_week10_scrim_json(parsed), payload)

    def test_week10_scrim_rejects_invalid_choice(self):
        prep = self._preps_by_outcome()["reps_translated"]
        plan = week10_scrim_plan(prep)

        with self.assertRaisesRegex(ValueError, "selected_scrim"):
            resolve_week10_scrim(prep, plan, "skip_scrims")


class TestWeek10MatchPlan(_Fixture):
    def _scrims_by_outcome(self):
        scrims = {}
        for prep in TestWeek10Scrim._preps_by_outcome(self).values():
            scrim_plan = week10_scrim_plan(prep)
            for scrim_choice in ("validate_read", "stress_execution", "stabilize_comms"):
                scrim = resolve_week10_scrim(prep, scrim_plan, scrim_choice)
                scrims.setdefault(scrim.outcome_id, scrim)
        return scrims

    def test_week10_match_plan_recommendation_uses_scrim_pressure(self):
        cases = {
            "read_validated": "week10_plan_press_advantage",
            "read_exposed": "week10_plan_protect_pressure",
            "execution_translated": "week10_plan_press_advantage",
            "execution_frayed": "week10_plan_protect_pressure",
            "comms_stabilized": "week10_plan_protect_pressure",
            "comms_turtled": "week10_plan_trade_map",
        }

        for scrim_outcome, expected in cases.items():
            with self.subTest(scrim_outcome=scrim_outcome):
                preview = week10_match_plan_preview(self._scrims_by_outcome()[scrim_outcome])
                self.assertEqual(preview.recommended_plan, expected)

    def test_week10_match_plan_lock_fields_are_stable(self):
        cases = {
            "week10_plan_protect_pressure": (
                "Protect pressure",
                "pressure_protection",
                "protected_pressure_must_not_collapse",
            ),
            "week10_plan_trade_map": ("Trade map", "map_trade", "map_trade_must_create_cross_pressure"),
            "week10_plan_press_advantage": (
                "Press advantage",
                "advantage_press",
                "pressed_advantage_must_land_before_punish",
            ),
        }
        scrim = self._scrims_by_outcome()["execution_translated"]
        preview = week10_match_plan_preview(scrim)

        for selected_plan, (label, commitment, constraint) in cases.items():
            with self.subTest(selected_plan=selected_plan):
                lock = resolve_week10_match_plan(preview, selected_plan)
                self.assertEqual(lock.plan_label, label)
                self.assertEqual(lock.commitment, commitment)
                self.assertIn(constraint, lock.result_constraints)

    def test_week10_match_plan_artifact_sources_scrim_and_stops_before_result(self):
        scrim = self._scrims_by_outcome()["execution_translated"]
        preview = week10_match_plan_preview(scrim)
        lock = resolve_week10_match_plan(preview, "week10_plan_press_advantage")
        payload = render_week10_match_plan_json(lock)

        self.assertIn('"week10_scrim": "week10_scrim.json"', payload)
        self.assertIn('"artifact_type": "week10_match_plan"', payload)
        self.assertIn('"selected_plan": "week10_plan_press_advantage"', payload)
        self.assertIn('"plan_lock":', payload)
        self.assertIn('"result_lock":', payload)
        self.assertIn('"scrim_effect":', payload)
        self.assertIn('"result_constraints":', payload)
        self.assertIn('"stops_before": "week10_match_result"', payload)
        self.assertIn('"next_artifact": "week10_match_result.json"', payload)

    def test_week10_match_plan_render_parse_round_trip_is_stable(self):
        scrim = self._scrims_by_outcome()["execution_translated"]
        preview = week10_match_plan_preview(scrim)
        lock = resolve_week10_match_plan(preview, "week10_plan_press_advantage")
        payload = render_week10_match_plan_json(lock)
        parsed = week10_match_plan_from_json(payload)

        self.assertEqual(parsed, lock)
        self.assertEqual(render_week10_match_plan_json(parsed), payload)

    def test_week10_match_plan_rejects_invalid_choice(self):
        scrim = self._scrims_by_outcome()["execution_translated"]
        preview = week10_match_plan_preview(scrim)

        with self.assertRaisesRegex(ValueError, "selected_plan"):
            resolve_week10_match_plan(preview, "coinflip")


class TestWeek10MatchResult(_Fixture):
    def _plans_by_selection(self):
        scrim = TestWeek10MatchPlan._scrims_by_outcome(self)["execution_translated"]
        preview = week10_match_plan_preview(scrim)
        return {
            selected: resolve_week10_match_plan(preview, selected)
            for selected in (
                "week10_plan_protect_pressure",
                "week10_plan_trade_map",
                "week10_plan_press_advantage",
            )
        }

    def _plan_for_path(
        self,
        week9_outcome,
        fallout_choice,
        prep_choice,
        scrim_choice,
        selected_plan,
    ):
        week9_result = TestWeek10Fallout._week9_results_by_outcome(self)[week9_outcome]
        fallout = resolve_week10_fallout(
            week9_result,
            week10_fallout_plan(week9_result),
            fallout_choice,
        )
        prep = resolve_week10_prep(fallout, week10_prep_plan(fallout), prep_choice)
        scrim = resolve_week10_scrim(prep, week10_scrim_plan(prep), scrim_choice)
        return resolve_week10_match_plan(week10_match_plan_preview(scrim), selected_plan)

    def test_week10_match_result_resolves_from_committed_plan(self):
        plan = self._plans_by_selection()["week10_plan_press_advantage"]
        result = resolve_week10_match_result(plan)

        self.assertEqual(result.outcome_id, "advantage_converted")
        self.assertEqual(result.result_tier, "win")
        self.assertEqual(result.scoreline, "2-0")
        self.assertEqual(result.selected_plan, "week10_plan_press_advantage")
        self.assertEqual(result.commitment, "advantage_press")
        self.assertIn("Match commitment: advantage press.", result.causal_chain)
        self.assertIn("score:10", result.result_basis)

    def test_week10_match_result_outcomes_follow_plan_family(self):
        cases = {
            "week10_plan_protect_pressure": "pressure_held",
            "week10_plan_trade_map": "map_trade_paid",
            "week10_plan_press_advantage": "advantage_converted",
        }
        for selected_plan, expected in cases.items():
            with self.subTest(selected_plan=selected_plan):
                result = resolve_week10_match_result(self._plans_by_selection()[selected_plan])
                self.assertEqual(result.outcome_id, expected)

    def test_week10_match_result_locks_all_six_outcomes_to_reachable_paths(self):
        cases = {
            "pressure_held": (
                "room_held",
                "steady_room",
                "scout_counter",
                "stabilize_comms",
                "week10_plan_protect_pressure",
                "win",
            ),
            "pressure_broke": (
                "room_held",
                "steady_room",
                "scout_counter",
                "validate_read",
                "week10_plan_protect_pressure",
                "loss",
            ),
            "map_trade_paid": (
                "room_held",
                "steady_room",
                "roster_reps",
                "stress_execution",
                "week10_plan_trade_map",
                "win",
            ),
            "map_trade_late": (
                "room_held",
                "steady_room",
                "scout_counter",
                "validate_read",
                "week10_plan_trade_map",
                "loss",
            ),
            "advantage_converted": (
                "room_held",
                "steady_room",
                "staff_review",
                "validate_read",
                "week10_plan_press_advantage",
                "win",
            ),
            "advantage_punished": (
                "room_held",
                "steady_room",
                "scout_counter",
                "validate_read",
                "week10_plan_press_advantage",
                "loss",
            ),
        }
        for outcome_id, path in cases.items():
            with self.subTest(outcome_id=outcome_id):
                *plan_path, result_tier = path
                result = resolve_week10_match_result(self._plan_for_path(*plan_path))

                self.assertEqual(result.outcome_id, outcome_id)
                self.assertEqual(result.result_tier, result_tier)

    def test_week10_match_result_artifact_sources_plan_and_ends_slice(self):
        plan = self._plans_by_selection()["week10_plan_press_advantage"]
        result = resolve_week10_match_result(plan)
        payload = render_week10_match_result_json(result)

        self.assertIn('"week10_match_plan": "week10_match_plan.json"', payload)
        self.assertIn('"artifact_type": "week10_match_result"', payload)
        self.assertIn('"selected_plan": "week10_plan_press_advantage"', payload)
        self.assertIn('"outcome_id": "advantage_converted"', payload)
        self.assertIn('"visible_effects":', payload)
        self.assertIn('"causal_chain":', payload)
        self.assertIn('"stops_before": "week10_post_match_review"', payload)
        self.assertIn('"next_artifact": "week10_post_match_review.json"', payload)

    def test_week10_match_result_render_parse_round_trip_is_stable(self):
        plan = self._plans_by_selection()["week10_plan_press_advantage"]
        result = resolve_week10_match_result(plan)
        payload = render_week10_match_result_json(result)
        parsed = week10_match_result_from_json(payload)

        self.assertEqual(parsed, result)
        self.assertEqual(render_week10_match_result_json(parsed), payload)


class TestWeek10PostMatchReview(_Fixture):
    def _result_for_path(
        self,
        week9_outcome,
        fallout_choice,
        prep_choice,
        scrim_choice,
        selected_plan,
    ):
        plan = TestWeek10MatchResult._plan_for_path(
            self,
            week9_outcome,
            fallout_choice,
            prep_choice,
            scrim_choice,
            selected_plan,
        )
        return resolve_week10_match_result(plan)

    def _clean_win_review_plan(self):
        return week10_post_match_review_plan(
            self._result_for_path(
                "room_held",
                "steady_room",
                "staff_review",
                "validate_read",
                "week10_plan_press_advantage",
            )
        )

    def _punished_loss_review_plan(self):
        return week10_post_match_review_plan(
            self._result_for_path(
                "room_held",
                "steady_room",
                "scout_counter",
                "validate_read",
                "week10_plan_protect_pressure",
            )
        )

    def test_week10_post_match_review_recommends_from_result_quality(self):
        self.assertEqual(self._clean_win_review_plan().recommended_review, "bank_pattern")
        self.assertEqual(self._punished_loss_review_plan().recommended_review, "repair_break")

    def test_week10_post_match_review_locks_all_six_review_outcomes(self):
        cases = {
            "pattern_banked": (self._clean_win_review_plan(), "bank_pattern", "advantage"),
            "pattern_overfit": (self._punished_loss_review_plan(), "bank_pattern", "watch"),
            "break_repaired": (self._punished_loss_review_plan(), "repair_break", "constraint"),
            "repair_overcorrected": (self._clean_win_review_plan(), "repair_break", "watch"),
            "standard_reset": (self._clean_win_review_plan(), "steady_review", "advantage"),
            "standard_blurred": (self._punished_loss_review_plan(), "steady_review", "constraint"),
        }
        for outcome_id, (plan, selected_review, carry_type) in cases.items():
            with self.subTest(outcome_id=outcome_id):
                lock = resolve_week10_post_match_review(plan, selected_review)

                self.assertEqual(lock.review_outcome_id, outcome_id)
                self.assertEqual(lock.carry_forward_type, carry_type)

    def test_week10_post_match_review_artifact_sources_result_and_stops_before_week11(self):
        lock = resolve_week10_post_match_review(self._clean_win_review_plan(), "bank_pattern")
        payload = render_week10_post_match_review_json(lock)

        self.assertIn('"week10_match_result": "week10_match_result.json"', payload)
        self.assertIn('"artifact_type": "week10_post_match_review"', payload)
        self.assertIn('"selected_review": "bank_pattern"', payload)
        self.assertIn('"review_outcome_id": "pattern_banked"', payload)
        self.assertIn('"carry_forward_tag": "repeatable_edge"', payload)
        self.assertIn('"reviewed_causal_chain":', payload)
        self.assertIn('"stops_before": "week11_setup"', payload)
        self.assertIn('"next_artifact": null', payload)

    def test_week10_post_match_review_render_parse_round_trip_is_stable(self):
        lock = resolve_week10_post_match_review(self._clean_win_review_plan(), "bank_pattern")
        payload = render_week10_post_match_review_json(lock)
        parsed = week10_post_match_review_from_json(payload)

        self.assertEqual(parsed, lock)
        self.assertEqual(render_week10_post_match_review_json(parsed), payload)

    def test_week10_post_match_review_rejects_invalid_choice(self):
        with self.assertRaisesRegex(ValueError, "selected_review"):
            resolve_week10_post_match_review(self._clean_win_review_plan(), "skip_review")


class TestWeek11Setup(_Fixture):
    def _result_for_path(
        self,
        week9_outcome,
        fallout_choice,
        prep_choice,
        scrim_choice,
        selected_plan,
    ):
        return TestWeek10PostMatchReview._result_for_path(
            self,
            week9_outcome,
            fallout_choice,
            prep_choice,
            scrim_choice,
            selected_plan,
        )

    def _advantage_review(self):
        return resolve_week10_post_match_review(
            TestWeek10PostMatchReview._clean_win_review_plan(self),
            "bank_pattern",
        )

    def _watch_review(self):
        return resolve_week10_post_match_review(
            TestWeek10PostMatchReview._punished_loss_review_plan(self),
            "bank_pattern",
        )

    def _constraint_review(self):
        return resolve_week10_post_match_review(
            TestWeek10PostMatchReview._punished_loss_review_plan(self),
            "repair_break",
        )

    def test_week11_setup_recommendation_uses_carry_forward_type(self):
        self.assertEqual(week11_setup_plan(self._advantage_review()).recommended_setup, "lean_into_carry")
        self.assertEqual(week11_setup_plan(self._watch_review()).recommended_setup, "stress_test_carry")
        self.assertEqual(week11_setup_plan(self._constraint_review()).recommended_setup, "protect_room")

    def test_week11_setup_locks_all_six_outcomes(self):
        cases = {
            "edge_activated": (self._advantage_review(), "lean_into_carry", "edge_lane"),
            "edge_overcalled": (self._watch_review(), "lean_into_carry", "overcalled_edge"),
            "test_defined": (self._watch_review(), "stress_test_carry", "validation_lane"),
            "test_scattered": (self._advantage_review(), "stress_test_carry", "scattered_validation"),
            "room_stabilized": (self._constraint_review(), "protect_room", "stable_room"),
            "room_passive": (self._advantage_review(), "protect_room", "passive_room"),
        }
        for outcome_id, (review, selected_setup, pressure) in cases.items():
            with self.subTest(outcome_id=outcome_id):
                lock = resolve_week11_setup(week11_setup_plan(review), selected_setup)

                self.assertEqual(lock.setup_outcome_id, outcome_id)
                self.assertEqual(lock.week11_pressure, pressure)

    def test_week11_setup_artifact_sources_review_and_stops_before_prep(self):
        lock = resolve_week11_setup(week11_setup_plan(self._advantage_review()), "lean_into_carry")
        payload = render_week11_setup_json(lock)

        self.assertIn('"week10_post_match_review": "week10_post_match_review.json"', payload)
        self.assertIn('"artifact_type": "week11_setup"', payload)
        self.assertIn('"selected_setup": "lean_into_carry"', payload)
        self.assertIn('"setup_outcome_id": "edge_activated"', payload)
        self.assertIn('"week11_pressure": "edge_lane"', payload)
        self.assertIn('"stops_before": "week11_prep"', payload)
        self.assertIn('"next_artifact": null', payload)

    def test_week11_setup_render_parse_round_trip_is_stable(self):
        lock = resolve_week11_setup(week11_setup_plan(self._advantage_review()), "lean_into_carry")
        payload = render_week11_setup_json(lock)
        parsed = week11_setup_from_json(payload)

        self.assertEqual(parsed, lock)
        self.assertEqual(render_week11_setup_json(parsed), payload)

    def test_week11_setup_rejects_invalid_choice(self):
        with self.assertRaisesRegex(ValueError, "selected_setup"):
            resolve_week11_setup(week11_setup_plan(self._advantage_review()), "skip_setup")


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
