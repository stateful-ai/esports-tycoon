"""The Flask slice app: manager view + Chirper feed in one process.

The web layer is a thin shell over the headless engine (tested in
``test_slice_engine.py``); these tests cover what the shell adds:

* one Flask app serves both the manager view and the Chirper feed;
* the linear flow accepts the MC then the two open-text moments, and an
  over-120-char post is rejected with a form error (not a 500);
* completing the week writes the ``runs/<slice_id>/`` artifact, and the in-app
  ``/feed`` is byte-identical to the saved ``feed.snapshot.html``.

Flask is an opt-in extra, so the whole module skips cleanly when it is absent.
"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    import flask  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - exercised only without the extra
    flask = None

from esports_tycoon.runner.model import OPEN_TEXT_MAX  # noqa: E402


@unittest.skipIf(flask is None, "Flask not installed (pip install -e '.[web]')")
class TestWebApp(unittest.TestCase):
    def setUp(self):
        from esports_tycoon.web import create_app

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_root = pathlib.Path(self._tmp.name)
        app = create_app(output_root=self.output_root)
        app.testing = True
        self.client = app.test_client()

    def _play_through(self, *, team_talk="run the default.", fallout="week 6: on to week 7."):
        self.client.post("/practice", data={"practice_focus": "defaults"})
        self.client.post("/prematch", data={"team_talk": team_talk})
        self.client.post("/fallout", data={"fallout_post": fallout})

    def _play_to_week11_match_result(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})
        self.client.post("/week11/scrim", data={"week11_scrim": "repeat_edge"})
        self.client.post("/week11/match", data={"week11_match_plan": "trust_the_read"})
        self.client.post("/week11/match/result")
        return next(self.output_root.glob("wk6-*"))

    def test_manager_view_and_feed_served_by_one_app(self):
        briefing = self.client.get("/")
        self.assertEqual(briefing.status_code, 200)
        self.assertIn(b"must-win", briefing.data)
        # Feed is reachable from the same process (after the MC is made).
        self.client.post("/practice", data={"practice_focus": "aim"})
        feed = self.client.get("/feed")
        self.assertEqual(feed.status_code, 200)
        self.assertIn(b"Chirper", feed.data)

    def test_week10_ops_room_art_is_served(self):
        resp = self.client.get("/static/art/week10-ops-room.webp")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "image/webp")
        self.assertTrue(resp.data.startswith(b"RIFF"))

        week11_resp = self.client.get("/static/art/week11-prep-room.webp")
        self.assertEqual(week11_resp.status_code, 200)
        self.assertEqual(week11_resp.mimetype, "image/webp")
        self.assertTrue(week11_resp.data.startswith(b"RIFF"))

        week11_scrim_resp = self.client.get("/static/art/week11-scrim-room.webp")
        self.assertEqual(week11_scrim_resp.status_code, 200)
        self.assertEqual(week11_scrim_resp.mimetype, "image/webp")
        self.assertTrue(week11_scrim_resp.data.startswith(b"RIFF"))

        week11_match_resp = self.client.get("/static/art/week11-match-plan-room.webp")
        self.assertEqual(week11_match_resp.status_code, 200)
        self.assertEqual(week11_match_resp.mimetype, "image/webp")
        self.assertTrue(week11_match_resp.data.startswith(b"RIFF"))

        week11_arena_resp = self.client.get("/static/art/week11-match-arena.webp")
        self.assertEqual(week11_arena_resp.status_code, 200)
        self.assertEqual(week11_arena_resp.mimetype, "image/webp")
        self.assertTrue(week11_arena_resp.data.startswith(b"RIFF"))

        week11_broadcast_arena_resp = self.client.get("/static/art/week11-broadcast-arena.webp")
        self.assertEqual(week11_broadcast_arena_resp.status_code, 200)
        self.assertEqual(week11_broadcast_arena_resp.mimetype, "image/webp")
        self.assertTrue(week11_broadcast_arena_resp.data.startswith(b"RIFF"))

        package_config = pathlib.Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("static/art/portraits/*.webp", package_config)
        for portrait in ("rook", "vex", "sable", "pixie", "coyote", "overcast-lineup"):
            with self.subTest(portrait=portrait):
                resp = self.client.get(f"/static/art/portraits/{portrait}.webp")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.mimetype, "image/webp")
                self.assertTrue(resp.data.startswith(b"RIFF"))

    def test_practice_page_offers_focused_training_reps(self):
        resp = self.client.get("/practice")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Focused rep", resp.data)
        self.assertIn(b"Vex: entry mechanics", resp.data)
        self.assertIn(b"Vex/Pixie: flash review", resp.data)
        self.assertIn(b"Analyst read", resp.data)
        self.assertIn(b"High upside, fragile room.", resp.data)
        self.assertIn(b"Lower ceiling, stronger room.", resp.data)

    def test_focused_training_rep_reaches_match_and_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )

        match = self.client.get("/match")
        self.assertEqual(match.status_code, 200)
        self.assertIn(b"Training:", match.data)
        self.assertIn(b"Vex +4 aim (4 TP)", match.data)
        self.assertIn(b"Review-room trust", match.data)
        self.assertIn(b"Late retake crack", match.data)
        self.assertIn(b"Follow-up scrim", match.data)
        self.assertIn(b"Relationship fallout", match.data)
        self.assertIn(b"Vex", match.data)
        self.assertIn(b"Pixie", match.data)

        self.client.post("/prematch", data={"team_talk": "play for the entry."})
        self.client.post("/fallout", data={"fallout_post": "spent the reps where they mattered."})
        recap = self.client.get("/recap")
        self.assertEqual(recap.status_code, 200)
        self.assertIn(b"Vex +4 aim (4 TP)", recap.data)
        self.assertIn(b"Relationship fallout", recap.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        recap_md = (run_dir / "recap.md").read_text(encoding="utf-8")
        self.assertIn("**Training:** Vex +4 aim (4 TP). Spent 4/4 TP.", recap_md)
        self.assertIn("### Relationship fallout", recap_md)
        self.assertIn("### Review-room trust", recap_md)
        self.assertIn("Review room heat", recap_md)
        self.assertIn("**Vex ↔ Pixie** (blame vs. guilt) split the room", recap_md)
        self.assertIn("entry reps helped. still not peeking through our own flash again.", recap_md)
        week7_setup = (run_dir / "week7_setup.json").read_text(encoding="utf-8")
        self.assertIn('"source_branch": "vex_aim"', week7_setup)
        self.assertIn('"delta": -2', week7_setup)
        feed_html = (run_dir / "feed.snapshot.html").read_text(encoding="utf-8")
        self.assertIn('<span class="tag">fallout</span>', feed_html)
        self.assertIn("entry reps helped. still not peeking through our own flash again.", feed_html)

    def test_repair_practice_fork_reaches_match_feed_and_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )

        match = self.client.get("/match")
        self.assertEqual(match.status_code, 200)
        self.assertIn(b"Pixie +4 coordination (4 TP)", match.data)
        self.assertIn(b"Practice consequence", match.data)
        self.assertIn(b"Review-room trust", match.data)
        self.assertIn(b"Clean second contact", match.data)
        self.assertIn(b"Follow-up scrim", match.data)
        self.assertIn(b"No highlight reel, but the entry call and flash finally matched.", match.data)
        self.assertIn(b"Relationship fallout", match.data)
        self.assertIn(b"working review", match.data)
        self.assertIn(b"cooled down", match.data)

        self.client.post("/prematch", data={"team_talk": "fix the flash timing."})
        self.client.post("/fallout", data={"fallout_post": "review work showed up."})
        recap = self.client.get("/recap")
        self.assertEqual(recap.status_code, 200)
        self.assertIn(b"Flash review", recap.data)
        self.assertIn(b"Vex did not get another raw aim bump.", recap.data)
        self.assertIn(b"Stable, not loud", recap.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        recap_md = (run_dir / "recap.md").read_text(encoding="utf-8")
        self.assertIn("### Practice consequence", recap_md)
        self.assertIn("### Review-room trust", recap_md)
        self.assertIn("### Follow-up scrim", recap_md)
        self.assertIn("## Week 7 setup", recap_md)
        self.assertIn("**Flash review:** No highlight reel", recap_md)
        self.assertIn("Stable, not loud", recap_md)
        self.assertIn("**Vex \u2194 Pixie** (working review) cooled down", recap_md)
        self.assertIn("flash review helped. less apology, more timing.", recap_md)
        week7_setup = (run_dir / "week7_setup.json").read_text(encoding="utf-8")
        self.assertIn('"source_branch": "pixie_flash_repair"', week7_setup)
        self.assertIn('"delta": 2', week7_setup)
        self.assertIn('"id": "pixie_stability_low_clip_value"', week7_setup)
        feed_html = (run_dir / "feed.snapshot.html").read_text(encoding="utf-8")
        self.assertIn('<span class="tag">fallout</span>', feed_html)
        self.assertIn("flash review helped. less apology, more timing.", feed_html)

    def test_week7_focus_surface_consumes_setup_and_writes_focus_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})

        page = self.client.get("/week7")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 7 focus lock", page.data)
        self.assertIn(b"Review room heat", page.data)
        self.assertIn(b"contain_fallout", page.data)
        self.assertIn(b"recommended", page.data)

        locked = self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"against the read", locked.data)
        self.assertIn(b"ignored_trust_fire", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        focus_json = (run_dir / "week7_focus.json").read_text(encoding="utf-8")
        self.assertIn('"chosen_focus": "prove_ceiling"', focus_json)
        self.assertIn('"followed_recommendation": false', focus_json)
        self.assertIn('"cost_tag": "ignored_trust_fire"', focus_json)

    def test_week7_focus_recommended_path_omits_ignored_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})

        page = self.client.get("/week7")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Stable, not loud", page.data)
        self.assertIn(b"prove_ceiling", page.data)

        locked = self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"followed the read", locked.data)
        self.assertNotIn(b"Ignored recommendation", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        focus_json = (run_dir / "week7_focus.json").read_text(encoding="utf-8")
        self.assertIn('"chosen_focus": "prove_ceiling"', focus_json)
        self.assertIn('"followed_recommendation": true', focus_json)
        self.assertNotIn('"ignored_recommendation"', focus_json)

    def test_week7_pressure_result_writes_artifact_after_focus_lock(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "contain_fallout"})

        pressure = self.client.post("/week7/result")
        self.assertEqual(pressure.status_code, 200)
        self.assertIn(b"Week 7 pressure result", pressure.data)
        self.assertIn(b"Ugly 2-1, room steadier", pressure.data)
        self.assertIn(b"heat_contained_scrappy_win", pressure.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        pressure_json = (run_dir / "week7_pressure.json").read_text(encoding="utf-8")
        self.assertIn('"source_setup_artifact": "week7_setup.json"', pressure_json)
        self.assertIn('"source_focus_artifact": "week7_focus.json"', pressure_json)
        self.assertIn('"outcome_id": "heat_contained_scrappy_win"', pressure_json)
        self.assertIn('"review_room_trust": 2', pressure_json)

    def test_week7_pressure_result_requires_focus_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})

        page = self.client.get("/week7/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 7 focus required", page.data)
        self.assertIn(b"week7_focus.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week7_pressure.json").exists())

    def test_week8_prep_consumes_pressure_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")

        page = self.client.get("/week8")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 prep", page.data)
        self.assertIn(b"vex_pixie_trust_fracture", page.data)
        self.assertIn(b"Patch the trust fracture", page.data)
        self.assertIn(b"Double down on the Vex ceiling", page.data)

        locked = self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"lower_volatility", locked.data)
        self.assertIn(b"Week 8 opens by patching vex_pixie_trust_fracture.", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        prep_json = (run_dir / "week8_prep.json").read_text(encoding="utf-8")
        self.assertIn('"source_pressure_outcome": "heat_ignored_highlight_loss"', prep_json)
        self.assertIn('"selected_choice": "patch_exposed_break"', prep_json)
        self.assertIn('"week8_modifier": "lower_volatility"', prep_json)

    def test_week8_prep_requires_pressure_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})

        page = self.client.get("/week8")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 7 pressure required", page.data)
        self.assertIn(b"week7_pressure.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week8_prep.json").exists())

    def test_week8_prep_rejects_invalid_choice_without_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")

        page = self.client.post("/week8", data={"week8_prep": "sponsors"})
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Choose a Week 8 prep response.", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week8_prep.json").exists())

    def test_week8_scrim_consumes_prep_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})

        page = self.client.get("/week8/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 scrim setup", page.data)
        self.assertIn(b"trust_buffer", page.data)
        self.assertIn(b"controlled_reset", page.data)
        self.assertIn(b"Run the patched protocol", page.data)

        locked = self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"patch_tested_early", locked.data)
        self.assertIn(b"Week 8 match setup inherits a controlled pressure check.", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        scrim_json = (run_dir / "week8_scrim.json").read_text(encoding="utf-8")
        self.assertIn('"source_pressure_outcome": "heat_ignored_highlight_loss"', scrim_json)
        self.assertIn('"selected_call": "cover_the_crack"', scrim_json)
        self.assertIn('"scrim_modifier": "trust_buffer"', scrim_json)

    def test_week8_scrim_requires_prep_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")

        page = self.client.get("/week8/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 prep required", page.data)
        self.assertIn(b"week8_prep.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week8_scrim.json").exists())

    def test_week8_match_preview_consumes_scrim_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})

        page = self.client.get("/week8/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 match preview", page.data)
        self.assertIn(b"patch_tested_early", page.data)
        self.assertIn(b"retake_blame_pressure", page.data)
        self.assertIn(b"Patch the weakness", page.data)
        self.assertIn(b"Lean into the edge", page.data)

        locked = self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"protected_opener", locked.data)
        self.assertIn(b"managed_but_edge_dulled", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        match_plan_json = (run_dir / "week8_match_plan.json").read_text(encoding="utf-8")
        self.assertIn('"source_pressure_outcome": "heat_ignored_highlight_loss"', match_plan_json)
        self.assertIn('"selected_plan": "patch_weakness"', match_plan_json)
        self.assertIn('"week8_scrim": "week8_scrim.json"', match_plan_json)

    def test_week8_match_preview_requires_scrim_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})

        page = self.client.get("/week8/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 scrim required", page.data)
        self.assertIn(b"week8_scrim.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week8_match_plan.json").exists())

    def test_week8_match_result_consumes_plan_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})

        page = self.client.get("/week8/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 match result", page.data)
        self.assertIn(b"Result ready", page.data)
        self.assertIn(b"patch_weakness", page.data)

        resolved = self.client.post("/week8/match/result")
        self.assertEqual(resolved.status_code, 200)
        self.assertIn(b"messy_win", resolved.data)
        self.assertIn(b"Week 9 opens", resolved.data)
        self.assertIn(b"week8_match_result.json", resolved.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        match_result_json = (run_dir / "week8_match_result.json").read_text(encoding="utf-8")
        self.assertIn('"source_pressure_outcome": "heat_ignored_highlight_loss"', match_result_json)
        self.assertIn('"selected_plan": "patch_weakness"', match_result_json)
        self.assertIn('"week8_match_plan": "week8_match_plan.json"', match_result_json)

    def test_week8_match_result_requires_match_plan_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})

        page = self.client.get("/week8/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 match plan required", page.data)
        self.assertIn(b"week8_match_plan.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week8_match_result.json").exists())

    def test_week9_setup_consumes_result_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")

        page = self.client.get("/week9")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 fallout setup", page.data)
        self.assertIn(b"legitimacy_pressure", page.data)
        self.assertIn(b"Stabilize the roster", page.data)
        self.assertIn(b"Double down on the read", page.data)
        self.assertIn(b"Control the public story", page.data)

        locked = self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"external_pressure", locked.data)
        self.assertIn(b"week9_setup.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        week9_json = (run_dir / "week9_setup.json").read_text(encoding="utf-8")
        self.assertIn('"week8_outcome_id": "messy_win"', week9_json)
        self.assertIn('"selected_response": "control_public_story"', week9_json)
        self.assertIn('"week8_match_result": "week8_match_result.json"', week9_json)

    def test_week9_setup_requires_week8_result_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "lean_into_edge"})

        page = self.client.get("/week9")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 8 match result required", page.data)
        self.assertIn(b"week8_match_result.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week9_setup.json").exists())

    def test_week9_prep_consumes_setup_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})

        page = self.client.get("/week9/prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 prep", page.data)
        self.assertIn(b"external_pressure", page.data)
        self.assertIn(b"Lean into the posture", page.data)
        self.assertIn(b"Balance the risk", page.data)
        self.assertIn(b"Counter the public read", page.data)

        locked = self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"public_read_counter", locked.data)
        self.assertIn(b"week9_prep.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        week9_prep_json = (run_dir / "week9_prep.json").read_text(encoding="utf-8")
        self.assertIn('"selected_prep": "counter_read"', week9_prep_json)
        self.assertIn('"week9_setup": "week9_setup.json"', week9_prep_json)
        self.assertIn('"next_artifact": "week9_scrim.json"', week9_prep_json)

    def test_week9_prep_requires_week9_setup_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "pixie_flash_repair"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "lean_into_edge"})
        self.client.post("/week8/match/result")

        page = self.client.get("/week9/prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 setup required", page.data)
        self.assertIn(b"week9_setup.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week9_prep.json").exists())

    def test_week9_scrim_consumes_prep_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})

        page = self.client.get("/week9/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 scrim", page.data)
        self.assertIn(b"room_read", page.data)
        self.assertIn(b"public_read", page.data)
        self.assertIn(b"tactical_read", page.data)
        self.assertIn(b"public_read_counter", page.data)

        locked = self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week9_scrim.json", locked.data)
        self.assertIn(b"external_pressure", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        week9_scrim_json = (run_dir / "week9_scrim.json").read_text(encoding="utf-8")
        self.assertIn('"selected_scrim_read": "public_read"', week9_scrim_json)
        self.assertIn('"week9_setup": "week9_setup.json"', week9_scrim_json)
        self.assertIn('"week9_prep": "week9_prep.json"', week9_scrim_json)
        self.assertIn('"next_artifact": "week9_match_plan.json"', week9_scrim_json)

    def test_week9_scrim_requires_week9_prep_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})

        page = self.client.get("/week9/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 prep required", page.data)
        self.assertIn(b"week9_prep.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week9_scrim.json").exists())

    def test_week9_match_consumes_scrim_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})

        page = self.client.get("/week9/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 match plan", page.data)
        self.assertIn(b"protect_the_room", page.data)
        self.assertIn(b"play_the_prep", page.data)
        self.assertIn(b"counter_the_read", page.data)

        locked = self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week9_match_plan.json", locked.data)
        self.assertIn(b"commit", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        week9_match_json = (run_dir / "week9_match_plan.json").read_text(encoding="utf-8")
        self.assertIn('"selected_plan": "play_the_prep"', week9_match_json)
        self.assertIn('"week9_scrim": "week9_scrim.json"', week9_match_json)
        self.assertIn('"result_constraints":', week9_match_json)
        self.assertIn('"next_artifact": "week9_match_result.json"', week9_match_json)
        self.assertFalse((run_dir / "week9_match_result.json").exists())

    def test_week9_match_requires_week9_scrim_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})

        page = self.client.get("/week9/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 scrim required", page.data)
        self.assertIn(b"week9_scrim.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week9_match_plan.json").exists())

    def test_week9_match_result_consumes_match_plan_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})

        page = self.client.get("/week9/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 match result", page.data)
        self.assertIn(b"Result ready", page.data)
        self.assertIn(b"play_the_prep", page.data)

        locked = self.client.post("/week9/match/result")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week9_match_result.json", locked.data)
        self.assertIn(b"prep_converted", locked.data)
        self.assertIn(b"week10_fallout.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        week9_result_json = (run_dir / "week9_match_result.json").read_text(encoding="utf-8")
        self.assertIn('"week9_setup": "week9_setup.json"', week9_result_json)
        self.assertIn('"week9_prep": "week9_prep.json"', week9_result_json)
        self.assertIn('"week9_scrim": "week9_scrim.json"', week9_result_json)
        self.assertIn('"week9_match_plan": "week9_match_plan.json"', week9_result_json)
        self.assertIn('"outcome_id": "prep_converted"', week9_result_json)
        self.assertIn('"next_artifact": "week10_fallout.json"', week9_result_json)
        self.assertFalse((run_dir / "week10_fallout.json").exists())

    def test_week9_match_result_requires_match_plan_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})

        page = self.client.get("/week9/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 match plan required", page.data)
        self.assertIn(b"week9_match_plan.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week9_match_result.json").exists())

    def test_week10_fallout_consumes_week9_result_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")

        page = self.client.get("/week10/fallout")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 fallout", page.data)
        self.assertIn(b"steady_room", page.data)
        self.assertIn(b"raise_standards", page.data)
        self.assertIn(b"adapt_system", page.data)

        locked = self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week10_fallout.json", locked.data)
        self.assertIn(b"standards_locked", locked.data)
        self.assertIn(b"week10_prep.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        fallout_json = (run_dir / "week10_fallout.json").read_text(encoding="utf-8")
        self.assertIn('"week9_match_result": "week9_match_result.json"', fallout_json)
        self.assertIn('"selected_choice": "raise_standards"', fallout_json)
        self.assertIn('"outcome_id": "standards_locked"', fallout_json)
        self.assertIn('"next_artifact": "week10_prep.json"', fallout_json)
        self.assertFalse((run_dir / "week10_prep.json").exists())

    def test_week10_fallout_requires_week9_match_result_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})

        page = self.client.get("/week10/fallout")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 9 match result required", page.data)
        self.assertIn(b"week9_match_result.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week10_fallout.json").exists())

    def test_week10_prep_consumes_fallout_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})

        page = self.client.get("/week10/prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 analyst desk", page.data)
        self.assertIn(b"/static/art/week10-ops-room.webp", page.data)
        self.assertIn(b"scout_counter", page.data)
        self.assertIn(b"staff_review", page.data)
        self.assertIn(b"roster_reps", page.data)

        locked = self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week10_prep.json", locked.data)
        self.assertIn(b"reps_translated", locked.data)
        self.assertIn(b"week10_scrim.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        prep_json = (run_dir / "week10_prep.json").read_text(encoding="utf-8")
        self.assertIn('"week10_fallout": "week10_fallout.json"', prep_json)
        self.assertIn('"advisor_packet":', prep_json)
        self.assertIn('"selected_choice": "roster_reps"', prep_json)
        self.assertIn('"outcome_id": "reps_translated"', prep_json)
        self.assertIn('"next_artifact": "week10_scrim.json"', prep_json)
        self.assertFalse((run_dir / "week10_scrim.json").exists())

    def test_week10_prep_requires_fallout_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")

        page = self.client.get("/week10/prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 fallout required", page.data)
        self.assertIn(b"week10_fallout.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week10_prep.json").exists())

    def test_week10_scrim_consumes_prep_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})

        page = self.client.get("/week10/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 scrim lab", page.data)
        self.assertIn(b"/static/art/week10-ops-room.webp", page.data)
        self.assertIn(b"validate_read", page.data)
        self.assertIn(b"stress_execution", page.data)
        self.assertIn(b"stabilize_comms", page.data)

        locked = self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week10_scrim.json", locked.data)
        self.assertIn(b"execution_translated", locked.data)
        self.assertIn(b"week10_match_plan.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        scrim_json = (run_dir / "week10_scrim.json").read_text(encoding="utf-8")
        self.assertIn('"week10_prep": "week10_prep.json"', scrim_json)
        self.assertIn('"selected_scrim": "stress_execution"', scrim_json)
        self.assertIn('"outcome_id": "execution_translated"', scrim_json)
        self.assertIn('"next_artifact": "week10_match_plan.json"', scrim_json)
        self.assertFalse((run_dir / "week10_match_plan.json").exists())

    def test_week10_scrim_requires_prep_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})

        page = self.client.get("/week10/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 prep required", page.data)
        self.assertIn(b"week10_prep.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week10_scrim.json").exists())

    def test_week10_match_consumes_scrim_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})

        page = self.client.get("/week10/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 match plan", page.data)
        self.assertIn(b"/static/art/week10-ops-room.webp", page.data)
        self.assertIn(b"week10_plan_protect_pressure", page.data)
        self.assertIn(b"week10_plan_trade_map", page.data)
        self.assertIn(b"week10_plan_press_advantage", page.data)

        locked = self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week10_match_plan.json", locked.data)
        self.assertIn(b"week10_plan_press_advantage", locked.data)
        self.assertIn(b"week10_match_result.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        plan_json = (run_dir / "week10_match_plan.json").read_text(encoding="utf-8")
        self.assertIn('"week10_scrim": "week10_scrim.json"', plan_json)
        self.assertIn('"selected_plan": "week10_plan_press_advantage"', plan_json)
        self.assertIn('"commitment": "advantage_press"', plan_json)
        self.assertIn('"plan_lock":', plan_json)
        self.assertIn('"result_lock":', plan_json)
        self.assertIn('"next_artifact": "week10_match_result.json"', plan_json)
        self.assertFalse((run_dir / "week10_match_result.json").exists())

    def test_week10_match_result_consumes_plan_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )

        page = self.client.get("/week10/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 result lock", page.data)
        self.assertIn(b"/static/art/week10-ops-room.webp", page.data)
        self.assertIn(b"advantage_press", page.data)

        resolved = self.client.post("/week10/match/result")
        self.assertEqual(resolved.status_code, 200)
        self.assertIn(b"Week 10 match result", resolved.data)
        self.assertIn(b"advantage_converted", resolved.data)
        self.assertIn(b"WIN 2-0", resolved.data)
        self.assertIn(b"week10_match_result.json", resolved.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        result_json = (run_dir / "week10_match_result.json").read_text(encoding="utf-8")
        self.assertIn('"week10_match_plan": "week10_match_plan.json"', result_json)
        self.assertIn('"selected_plan": "week10_plan_press_advantage"', result_json)
        self.assertIn('"outcome_id": "advantage_converted"', result_json)
        self.assertIn('"result_tier": "win"', result_json)
        self.assertIn('"display": "2-0"', result_json)
        self.assertIn('"next_artifact": "week10_post_match_review.json"', result_json)

    def test_week10_post_match_review_consumes_result_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")

        page = self.client.get("/week10/post-match-review")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 post-match review", page.data)
        self.assertIn(b"bank_pattern", page.data)
        self.assertIn(b"repair_break", page.data)
        self.assertIn(b"steady_review", page.data)
        self.assertIn(b"/static/art/week10-ops-room.webp", page.data)

        locked = self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Week 10 review locked", locked.data)
        self.assertIn(b"pattern_banked", locked.data)
        self.assertIn(b"repeatable_edge", locked.data)
        self.assertIn(b"week10_post_match_review.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        review_json = (run_dir / "week10_post_match_review.json").read_text(encoding="utf-8")
        self.assertIn('"week10_match_result": "week10_match_result.json"', review_json)
        self.assertIn('"selected_review": "bank_pattern"', review_json)
        self.assertIn('"review_outcome_id": "pattern_banked"', review_json)
        self.assertIn('"carry_forward_tag": "repeatable_edge"', review_json)
        self.assertIn('"stops_before": "week11_setup"', review_json)
        self.assertIn('"next_artifact": null', review_json)

    def test_week10_post_match_review_requires_match_result_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )

        page = self.client.get("/week10/post-match-review")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 result required", page.data)
        self.assertIn(b"week10_match_result.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week10_post_match_review.json").exists())

    def test_week11_setup_consumes_review_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )

        page = self.client.get("/week11/setup")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 setup", page.data)
        self.assertIn(b"lean_into_carry", page.data)
        self.assertIn(b"stress_test_carry", page.data)
        self.assertIn(b"protect_room", page.data)
        self.assertIn(b"/static/art/week10-ops-room.webp", page.data)

        locked = self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Week 11 setup locked", locked.data)
        self.assertIn(b"edge_activated", locked.data)
        self.assertIn(b"week11_setup.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        setup_json = (run_dir / "week11_setup.json").read_text(encoding="utf-8")
        self.assertIn('"week10_post_match_review": "week10_post_match_review.json"', setup_json)
        self.assertIn('"selected_setup": "lean_into_carry"', setup_json)
        self.assertIn('"setup_outcome_id": "edge_activated"', setup_json)
        self.assertIn('"stops_before": "week11_prep"', setup_json)
        self.assertIn('"next_artifact": "week11_prep.json"', setup_json)

    def test_week11_prep_consumes_setup_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})

        page = self.client.get("/week11/prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 prep", page.data)
        self.assertIn(b"build_edge_lane", page.data)
        self.assertIn(b"scout_countermove", page.data)
        self.assertIn(b"stabilize_room", page.data)
        self.assertIn(b"/static/art/week11-prep-room.webp", page.data)

        locked = self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Week 11 prep locked", locked.data)
        self.assertIn(b"edge_lane_drilled", locked.data)
        self.assertIn(b"week11_prep.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        prep_json = (run_dir / "week11_prep.json").read_text(encoding="utf-8")
        self.assertIn('"week11_setup": "week11_setup.json"', prep_json)
        self.assertIn('"selected_prep": "build_edge_lane"', prep_json)
        self.assertIn('"prep_outcome_id": "edge_lane_drilled"', prep_json)
        self.assertIn('"stops_before": "week11_scrim"', prep_json)
        self.assertIn('"next_artifact": "week11_scrim.json"', prep_json)

    def test_week11_scrim_consumes_prep_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})

        page = self.client.get("/week11/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 scrim", page.data)
        self.assertIn(b"repeat_edge", page.data)
        self.assertIn(b"show_countermove", page.data)
        self.assertIn(b"steady_first_contact", page.data)
        self.assertIn(b"/static/art/week11-scrim-room.webp", page.data)

        locked = self.client.post("/week11/scrim", data={"week11_scrim": "repeat_edge"})
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Week 11 scrim locked", locked.data)
        self.assertIn(b"edge_repeated_under_pressure", locked.data)
        self.assertIn(b"week11_scrim.json", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        scrim_json = (run_dir / "week11_scrim.json").read_text(encoding="utf-8")
        self.assertIn('"week11_prep": "week11_prep.json"', scrim_json)
        self.assertIn('"source_artifact": "week11_prep.json"', scrim_json)
        self.assertIn('"checkpoint": "week11_scrim"', scrim_json)
        self.assertIn('"selected_scrim": "repeat_edge"', scrim_json)
        self.assertIn('"scrim_outcome_id": "edge_repeated_under_pressure"', scrim_json)
        self.assertIn('"scrim_protocol": "repeat_edge_pressure_reps"', scrim_json)
        self.assertIn('"analyst_read_id": "edge_lane_survives_contact"', scrim_json)
        self.assertIn('"recommendation_reason":', scrim_json)
        self.assertIn('"match_plan_seed": "edge_pressure_plan"', scrim_json)
        self.assertIn('"stops_before": "week11_match_plan"', scrim_json)
        self.assertIn('"next_artifact": "week11_match_plan.json"', scrim_json)

    def test_week11_match_plan_consumes_scrim_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})
        self.client.post("/week11/scrim", data={"week11_scrim": "repeat_edge"})

        page = self.client.get("/week11/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 match plan", page.data)
        self.assertIn(b"trust_the_read", page.data)
        self.assertIn(b"attack_the_gap", page.data)
        self.assertIn(b"stabilize_defaults", page.data)
        self.assertIn(b"/static/art/week11-match-plan-room.webp", page.data)
        self.assertIn(b"outcome confirming", page.data)
        self.assertIn(b"signal high_signal", page.data)
        self.assertIn(b"read trust_read", page.data)
        self.assertIn(b"emphasis early_objective", page.data)

        locked = self.client.post(
            "/week11/match",
            data={"week11_match_plan": "trust_the_read"},
        )
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"week11_match_plan.json", locked.data)
        self.assertIn(b"trust_the_read", locked.data)
        self.assertIn(b"read_trust", locked.data)
        self.assertIn(b"emphasis early_objective", locked.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        plan_json = (run_dir / "week11_match_plan.json").read_text(encoding="utf-8")
        self.assertIn('"week11_scrim": "week11_scrim.json"', plan_json)
        self.assertIn('"source_artifact": "week11_scrim.json"', plan_json)
        self.assertIn('"checkpoint": "week11_match_plan"', plan_json)
        self.assertIn('"selected_plan": "trust_the_read"', plan_json)
        self.assertIn('"commitment": "read_trust"', plan_json)
        self.assertIn('"recommendation_inputs":', plan_json)
        self.assertIn('"recommendation_context":', plan_json)
        self.assertIn('"outcome_class": "confirming"', plan_json)
        self.assertIn('"protocol_signal": "high_signal"', plan_json)
        self.assertIn('"analyst_read_class": "trust_read"', plan_json)
        self.assertIn('"scrim_protocol": "repeat_edge_pressure_reps"', plan_json)
        self.assertIn('"analyst_read_id": "edge_lane_survives_contact"', plan_json)
        self.assertIn('"match_plan_seed": "edge_pressure_plan"', plan_json)
        self.assertIn('"plan_lock":', plan_json)
        self.assertIn('"result_lock":', plan_json)
        self.assertIn('"stops_before": "week11_match_result"', plan_json)
        self.assertIn('"next_artifact": "week11_match_result.json"', plan_json)

    def test_week11_match_result_consumes_plan_and_writes_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})
        self.client.post("/week11/scrim", data={"week11_scrim": "repeat_edge"})
        self.client.post("/week11/match", data={"week11_match_plan": "trust_the_read"})

        page = self.client.get("/week11/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 result lock", page.data)
        self.assertIn(b"Resolve Week 11 result", page.data)
        self.assertIn(b"emphasis early_objective", page.data)

        resolved = self.client.post("/week11/match/result")
        self.assertEqual(resolved.status_code, 200)
        self.assertIn(b"Week 11 match result", resolved.data)
        self.assertIn(b"WIN 2-0", resolved.data)
        self.assertIn(b"read_trusted", resolved.data)
        self.assertIn(b"week11_match_result.json", resolved.data)

        run_dir = next(self.output_root.glob("wk6-*"))
        result_json = (run_dir / "week11_match_result.json").read_text(encoding="utf-8")
        self.assertIn('"week11_match_plan": "week11_match_plan.json"', result_json)
        self.assertIn('"source_artifact": "week11_match_plan.json"', result_json)
        self.assertIn('"checkpoint": "week11_match_result"', result_json)
        self.assertIn('"selected_plan": "trust_the_read"', result_json)
        self.assertIn('"outcome_id": "read_trusted"', result_json)
        self.assertIn('"result_tier": "win"', result_json)
        self.assertIn('"scoreline": "2-0"', result_json)
        self.assertIn('"result_basis":', result_json)
        self.assertIn('"causal_chain":', result_json)
        self.assertIn('"stops_before": "week11_match_sim"', result_json)
        self.assertIn('"next_artifact": "week11_match_sim.json"', result_json)

    def test_week11_match_viewer_consumes_result_and_writes_replay(self):
        run_dir = self._play_to_week11_match_result()

        page = self.client.get("/week11/match/viewer")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 tactical sim", page.data)
        self.assertIn(b"/static/art/week11-match-arena.webp", page.data)
        self.assertIn(b"Broadcast overlay", page.data)
        self.assertIn(b"Tactical telemetry", page.data)
        self.assertIn(b"alive-count", page.data)
        self.assertIn(b"telemetry-space-control", page.data)
        self.assertIn(b"/static/art/portraits/overcast-lineup.webp", page.data)
        self.assertIn(b"/static/art/portraits/vex.webp", page.data)
        self.assertIn(b"data-stance", page.data)
        self.assertIn(b"data-intent", page.data)
        self.assertIn(b"current-action", page.data)
        self.assertIn(b"current-reward", page.data)
        self.assertIn(b"metric-comms", page.data)
        self.assertIn(b"top-traits", page.data)
        self.assertIn(b"trail-layer", page.data)
        self.assertIn(b"trail-polyline", page.data)
        self.assertIn(b"renderTrails", page.data)
        self.assertIn(b"map-geometry-layer", page.data)
        self.assertIn(b"map-lane-layer", page.data)
        self.assertIn(b"map-region", page.data)
        self.assertIn(b"cover-block", page.data)
        self.assertIn(b"renderMapGeometry", page.data)
        self.assertIn(b"threat-layer", page.data)
        self.assertIn(b"threat-line", page.data)
        self.assertIn(b"duel-pressure", page.data)
        self.assertIn(b"duel-lanes", page.data)
        self.assertIn(b"renderThreatArcs", page.data)
        self.assertIn(b"combat-layer", page.data)
        self.assertIn(b"combat-pulse", page.data)
        self.assertIn(b"combat-feed", page.data)
        self.assertIn(b"combat-chip", page.data)
        self.assertIn(b"renderCombat", page.data)
        self.assertIn(b"utility-layer", page.data)
        self.assertIn(b"utility-zone", page.data)
        self.assertIn(b"utility-count", page.data)
        self.assertIn(b"utility-stack", page.data)
        self.assertIn(b"renderUtilityZones", page.data)
        self.assertIn(b"event-layer", page.data)
        self.assertIn(b"causality-panel", page.data)
        self.assertIn(b"observation-features", page.data)
        self.assertIn(b"reward-components", page.data)
        self.assertIn(b"action-mask", page.data)
        self.assertIn(b"action-chip", page.data)
        self.assertIn(b"renderActionMask", page.data)
        self.assertIn(b"zone-control", page.data)
        self.assertIn(b"renderEvents", page.data)
        self.assertIn(b"renderCausality", page.data)
        self.assertIn(b"Generate replay artifact", page.data)
        self.assertIn(b"entry_pressure_sprinter", page.data)
        self.assertIn(b"structured_default_caller", page.data)
        self.assertIn(b"skill_epoch_proxy", page.data)
        self.assertIn(b"map_layout", page.data)
        self.assertIn(b"observation_space", page.data)
        self.assertIn(b"R1 attack", page.data)
        self.assertIn(b"Development board", page.data)
        self.assertIn(b"training_signals", page.data)
        self.assertFalse((run_dir / "week11_match_sim.json").exists())

        locked = self.client.post("/week11/match/viewer")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Replay artifact locked", locked.data)
        self.assertIn(b"week11_match_sim.json", locked.data)
        self.assertIn(b"scenario_style_vex_high_tempo_entry", locked.data)

        replay_json = (run_dir / "week11_match_sim.json").read_text(encoding="utf-8")
        self.assertIn('"week11_match_result": "week11_match_result.json"', replay_json)
        self.assertIn('"source_artifact": "week11_match_result.json"', replay_json)
        self.assertIn('"checkpoint": "week11_match_sim"', replay_json)
        self.assertIn('"selected_plan": "trust_the_read"', replay_json)
        self.assertIn('"outcome_id": "read_trusted"', replay_json)
        self.assertIn('"agents":', replay_json)
        self.assertIn('"rounds":', replay_json)
        self.assertIn('"frames":', replay_json)
        self.assertIn('"steps":', replay_json)
        self.assertIn('"telemetry":', replay_json)
        self.assertIn('"telemetry_fields":', replay_json)
        self.assertIn('"observation_features":', replay_json)
        self.assertIn('"action_context":', replay_json)
        self.assertIn('"reward_components":', replay_json)
        self.assertIn('"map_layout":', replay_json)
        self.assertIn('"map_cover_unit": "map_layout.covers[]"', replay_json)
        self.assertIn('"map_lane_unit": "map_layout.lanes[]"', replay_json)
        self.assertIn('"health":', replay_json)
        self.assertIn('"combat_window":', replay_json)
        self.assertIn('"combat_events":', replay_json)
        self.assertIn('"combat_event_unit": "frames[].combat_events[]"', replay_json)
        self.assertIn('"zone_control":', replay_json)
        self.assertIn('"events":', replay_json)
        self.assertIn('"objective_pressure":', replay_json)
        self.assertIn('"training_signals":', replay_json)
        self.assertIn('"rl_contract":', replay_json)
        self.assertIn('"action_space":', replay_json)
        self.assertIn('"reward_fields":', replay_json)
        self.assertIn('"next_policy_id":', replay_json)
        self.assertIn('"skill_epoch_proxy":', replay_json)
        self.assertIn('"portrait_asset": "art/portraits/vex.webp"', replay_json)
        self.assertIn('"round_id": 1', replay_json)
        self.assertIn('"stops_before": "week11_development_plan"', replay_json)
        self.assertIn('"next_artifact": "week11_development_plan.json"', replay_json)

    def test_week11_match_development_consumes_replay_and_writes_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")

        page = self.client.get("/week11/match/development")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 development plan", page.data)
        self.assertIn(b"training_signals", page.data)
        self.assertIn(b"policy_targets", page.data)
        self.assertIn(b"next_policy_id", page.data)
        self.assertIn(b"vex", page.data)
        self.assertIn(b"Lock development plan", page.data)
        self.assertFalse((run_dir / "week11_development_plan.json").exists())

        locked = self.client.post("/week11/match/development")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Development artifact locked", locked.data)
        self.assertIn(b"week11_development_plan.json", locked.data)

        development_json = (run_dir / "week11_development_plan.json").read_text(encoding="utf-8")
        self.assertIn('"source_artifact": "week11_match_sim.json"', development_json)
        self.assertIn('"checkpoint": "week11_development_plan"', development_json)
        self.assertIn('"drills":', development_json)
        self.assertIn('"policy_targets":', development_json)
        self.assertIn('"development_contract":', development_json)
        self.assertIn('"target_policy_id":', development_json)
        self.assertIn('"stops_before": "week11_training_dataset"', development_json)
        self.assertIn('"next_artifact": "week11_training_dataset.json"', development_json)

    def test_week11_training_dataset_consumes_development_plan_and_writes_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")

        page = self.client.get("/week11/match/training-dataset")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 training dataset", page.data)
        self.assertIn(b"offline_rl_transition_v1", page.data)
        self.assertIn(b"policy_targets", page.data)
        self.assertIn(b"Lock training dataset", page.data)
        self.assertIn(b"telemetry", page.data)
        self.assertFalse((run_dir / "week11_training_dataset.json").exists())

        locked = self.client.post("/week11/match/training-dataset")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Training dataset locked", locked.data)
        self.assertIn(b"week11_training_dataset.json", locked.data)
        self.assertIn(b"Open Week 12 model lab", locked.data)

        dataset_json = (run_dir / "week11_training_dataset.json").read_text(encoding="utf-8")
        self.assertIn('"source_artifact": "week11_development_plan.json"', dataset_json)
        self.assertIn('"checkpoint": "week11_training_dataset"', dataset_json)
        self.assertIn('"samples":', dataset_json)
        self.assertIn('"next_observation":', dataset_json)
        self.assertIn('"target_policy_id":', dataset_json)
        self.assertIn('"observation_features":', dataset_json)
        self.assertIn('"reward_components":', dataset_json)
        self.assertIn('"dataset_contract":', dataset_json)
        self.assertIn('"stops_before": "week12_model_prep"', dataset_json)
        self.assertIn('"next_artifact": "week12_model_prep.json"', dataset_json)

    def test_week12_model_prep_consumes_training_dataset_and_writes_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")
        self.client.post("/week11/match/training-dataset")

        page = self.client.get("/week12/model-prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 12 model lab", page.data)
        self.assertIn(b"model_prep_batch_v1", page.data)
        self.assertIn(b"Scenario slots", page.data)
        self.assertIn(b"Lock model prep", page.data)
        self.assertIn(b"scenario://week12/", page.data)
        self.assertFalse((run_dir / "week12_model_prep.json").exists())

        locked = self.client.post("/week12/model-prep")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Model prep locked", locked.data)
        self.assertIn(b"week12_model_prep.json", locked.data)
        self.assertIn(b"Open shadow rollout", locked.data)

        prep_json = (run_dir / "week12_model_prep.json").read_text(encoding="utf-8")
        self.assertIn('"source_artifact": "week11_training_dataset.json"', prep_json)
        self.assertIn('"checkpoint": "week12_model_prep"', prep_json)
        self.assertIn('"model_prep_batch_v1"', prep_json)
        self.assertIn('"scenario_model_slot":', prep_json)
        self.assertIn('"candidate_policy_id":', prep_json)
        self.assertIn('"component_totals":', prep_json)
        self.assertIn('"dominant_failure_mode":', prep_json)
        self.assertIn('"risk_spike_count":', prep_json)
        self.assertIn('"evaluation_gate":', prep_json)
        self.assertIn('"stops_before": "week12_shadow_rollout"', prep_json)
        self.assertIn('"next_artifact": "week12_shadow_rollout.json"', prep_json)

    def test_week12_shadow_rollout_consumes_model_prep_and_writes_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")
        self.client.post("/week11/match/training-dataset")
        self.client.post("/week12/model-prep")

        page = self.client.get("/week12/shadow-rollout")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 12 shadow rollout", page.data)
        self.assertIn(b"shadow_rollout_batch_v1", page.data)
        self.assertIn(b"promotion decisions", page.data)
        self.assertIn(b"Lock shadow rollout", page.data)
        self.assertIn(b"scenario://week12/", page.data)
        self.assertFalse((run_dir / "week12_shadow_rollout.json").exists())

        locked = self.client.post("/week12/shadow-rollout")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Shadow rollout locked", locked.data)
        self.assertIn(b"week12_shadow_rollout.json", locked.data)
        self.assertIn(b"Open training queue", locked.data)

        rollout_json = (run_dir / "week12_shadow_rollout.json").read_text(encoding="utf-8")
        self.assertIn('"source_artifact": "week12_model_prep.json"', rollout_json)
        self.assertIn('"checkpoint": "week12_shadow_rollout"', rollout_json)
        self.assertIn('"shadow_rollout_batch_v1"', rollout_json)
        self.assertIn('"candidate_reward":', rollout_json)
        self.assertIn('"risk_delta":', rollout_json)
        self.assertIn('"decision":', rollout_json)
        self.assertIn('"promotion_blockers":', rollout_json)
        self.assertIn('"stops_before": "week12_training_queue"', rollout_json)
        self.assertIn('"next_artifact": "week12_training_queue.json"', rollout_json)

    def test_week12_training_queue_consumes_shadow_rollout_and_writes_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")
        self.client.post("/week11/match/training-dataset")
        self.client.post("/week12/model-prep")
        self.client.post("/week12/shadow-rollout")

        page = self.client.get("/week12/training-queue")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 12 training ops", page.data)
        self.assertIn(b"training_queue_batch_v1", page.data)
        self.assertIn(b"RL-ready weights", page.data)
        self.assertIn(b"Lock training queue", page.data)
        self.assertIn(b"scenario://week12/", page.data)
        self.assertIn(b"week11-broadcast-arena.webp", page.data)
        self.assertFalse((run_dir / "week12_training_queue.json").exists())

        locked = self.client.post("/week12/training-queue")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Training queue locked", locked.data)
        self.assertIn(b"week12_training_queue.json", locked.data)
        self.assertIn(b"Open policy feedback", locked.data)

        queue_json = (run_dir / "week12_training_queue.json").read_text(encoding="utf-8")
        self.assertIn('"source_artifact": "week12_shadow_rollout.json"', queue_json)
        self.assertIn('"checkpoint": "week12_training_queue"', queue_json)
        self.assertIn('"training_queue_batch_v1"', queue_json)
        self.assertIn('"queue_action":', queue_json)
        self.assertIn('"epoch_budget":', queue_json)
        self.assertIn('"reward_weight_x100":', queue_json)
        self.assertIn('"scenario_asset_slot":', queue_json)
        self.assertIn('"stops_before": "week12_policy_feedback"', queue_json)
        self.assertIn('"next_artifact": "week12_policy_feedback.json"', queue_json)

    def test_week12_policy_feedback_consumes_queue_and_dataset_and_writes_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")
        self.client.post("/week11/match/training-dataset")
        self.client.post("/week12/model-prep")
        self.client.post("/week12/shadow-rollout")
        self.client.post("/week12/training-queue")

        page = self.client.get("/week12/policy-feedback")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 12 policy feedback", page.data)
        self.assertIn(b"policy_feedback_batch_v1", page.data)
        self.assertIn(b"replay-tick coaching", page.data)
        self.assertIn(b"Lock policy feedback", page.data)
        self.assertIn(b"Evidence clip", page.data)
        self.assertIn(b"scenario://week12/", page.data)
        self.assertIn(b"week11-match-arena.webp", page.data)
        self.assertFalse((run_dir / "week12_policy_feedback.json").exists())

        locked = self.client.post("/week12/policy-feedback")
        self.assertEqual(locked.status_code, 200)
        self.assertIn(b"Policy feedback locked", locked.data)
        self.assertIn(b"week12_policy_feedback.json", locked.data)

        feedback_json = (run_dir / "week12_policy_feedback.json").read_text(encoding="utf-8")
        self.assertIn('"source_artifact": "week12_training_queue.json"', feedback_json)
        self.assertIn('"week11_training_dataset": "week11_training_dataset.json"', feedback_json)
        self.assertIn('"checkpoint": "week12_policy_feedback"', feedback_json)
        self.assertIn('"policy_feedback_batch_v1"', feedback_json)
        self.assertIn('"evidence_clip":', feedback_json)
        self.assertIn('"sample_credit_assignment":', feedback_json)
        self.assertIn('"replay_annotations":', feedback_json)
        self.assertIn('"policy_weight_snapshot":', feedback_json)
        self.assertIn('"coach_action":', feedback_json)
        self.assertIn('"player_feedback":', feedback_json)
        self.assertIn('"next_artifact": null', feedback_json)

    def test_week12_policy_feedback_requires_training_queue_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")
        self.client.post("/week11/match/training-dataset")
        self.client.post("/week12/model-prep")
        self.client.post("/week12/shadow-rollout")

        page = self.client.get("/week12/policy-feedback")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 12 policy feedback required", page.data)
        self.assertIn(b"week12_training_queue.json", page.data)
        self.assertFalse((run_dir / "week12_policy_feedback.json").exists())

    def test_week12_training_queue_requires_shadow_rollout_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")
        self.client.post("/week11/match/training-dataset")
        self.client.post("/week12/model-prep")

        page = self.client.get("/week12/training-queue")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 12 shadow rollout required", page.data)
        self.assertIn(b"week12_shadow_rollout.json", page.data)
        self.assertFalse((run_dir / "week12_training_queue.json").exists())

    def test_week12_shadow_rollout_requires_model_prep_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")
        self.client.post("/week11/match/training-dataset")

        page = self.client.get("/week12/shadow-rollout")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 12 model prep required", page.data)
        self.assertIn(b"week12_model_prep.json", page.data)
        self.assertFalse((run_dir / "week12_shadow_rollout.json").exists())

    def test_week12_model_prep_requires_training_dataset_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")
        self.client.post("/week11/match/development")

        page = self.client.get("/week12/model-prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 training dataset required", page.data)
        self.assertIn(b"week11_training_dataset.json", page.data)
        self.assertFalse((run_dir / "week12_model_prep.json").exists())

    def test_week11_training_dataset_requires_development_plan_artifact(self):
        run_dir = self._play_to_week11_match_result()
        self.client.post("/week11/match/viewer")

        page = self.client.get("/week11/match/training-dataset")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 development plan required", page.data)
        self.assertIn(b"week11_development_plan.json", page.data)
        self.assertFalse((run_dir / "week11_training_dataset.json").exists())

    def test_week11_match_development_requires_replay_artifact(self):
        run_dir = self._play_to_week11_match_result()

        page = self.client.get("/week11/match/development")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 match sim required", page.data)
        self.assertIn(b"week11_match_sim.json", page.data)
        self.assertFalse((run_dir / "week11_development_plan.json").exists())

    def test_week11_match_viewer_requires_result_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})
        self.client.post("/week11/scrim", data={"week11_scrim": "repeat_edge"})
        self.client.post("/week11/match", data={"week11_match_plan": "trust_the_read"})

        page = self.client.get("/week11/match/viewer")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 match result required", page.data)
        self.assertIn(b"week11_match_result.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week11_match_sim.json").exists())

    def test_week11_match_result_requires_match_plan_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})
        self.client.post("/week11/scrim", data={"week11_scrim": "repeat_edge"})

        page = self.client.get("/week11/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 match plan required", page.data)
        self.assertIn(b"week11_match_plan.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week11_match_result.json").exists())

    def test_week11_prep_requires_setup_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )

        page = self.client.get("/week11/prep")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 setup required", page.data)
        self.assertIn(b"week11_setup.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week11_prep.json").exists())

    def test_week11_scrim_requires_prep_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})

        page = self.client.get("/week11/scrim")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 prep required", page.data)
        self.assertIn(b"week11_prep.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week11_scrim.json").exists())

    def test_week11_match_plan_requires_scrim_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")
        self.client.post(
            "/week10/post-match-review",
            data={"week10_post_match_review": "bank_pattern"},
        )
        self.client.post("/week11/setup", data={"week11_setup": "lean_into_carry"})
        self.client.post("/week11/prep", data={"week11_prep": "build_edge_lane"})

        page = self.client.get("/week11/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 11 scrim required", page.data)
        self.assertIn(b"week11_scrim.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week11_match_plan.json").exists())

    def test_week11_setup_requires_review_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})
        self.client.post(
            "/week10/match",
            data={"week10_match_plan": "week10_plan_press_advantage"},
        )
        self.client.post("/week10/match/result")

        page = self.client.get("/week11/setup")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 review required", page.data)
        self.assertIn(b"week10_post_match_review.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week11_setup.json").exists())

    def test_week10_match_requires_scrim_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})

        page = self.client.get("/week10/match")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 scrim required", page.data)
        self.assertIn(b"week10_scrim.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week10_match_plan.json").exists())

    def test_week10_match_result_requires_match_plan_artifact(self):
        self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vex_aim"},
        )
        self.client.post("/prematch", data={"team_talk": "trust the review."})
        self.client.post("/fallout", data={"fallout_post": "review receipts logged."})
        self.client.post("/week7", data={"week7_focus": "prove_ceiling"})
        self.client.post("/week7/result")
        self.client.post("/week8", data={"week8_prep": "patch_exposed_break"})
        self.client.post("/week8/scrim", data={"week8_scrim": "cover_the_crack"})
        self.client.post("/week8/match", data={"week8_match_plan": "patch_weakness"})
        self.client.post("/week8/match/result")
        self.client.post("/week9", data={"week9_response": "control_public_story"})
        self.client.post("/week9/prep", data={"week9_prep": "counter_read"})
        self.client.post("/week9/scrim", data={"week9_scrim": "public_read"})
        self.client.post("/week9/match", data={"week9_match_plan": "play_the_prep"})
        self.client.post("/week9/match/result")
        self.client.post("/week10/fallout", data={"week10_fallout": "raise_standards"})
        self.client.post("/week10/prep", data={"week10_prep": "roster_reps"})
        self.client.post("/week10/scrim", data={"week10_scrim": "stress_execution"})

        page = self.client.get("/week10/match/result")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Week 10 match plan required", page.data)
        self.assertIn(b"week10_match_plan.json", page.data)
        run_dir = next(self.output_root.glob("wk6-*"))
        self.assertFalse((run_dir / "week10_match_result.json").exists())

    def test_full_flow_writes_artifact(self):
        fallout = "week 6: held the line."
        self._play_through(fallout=fallout)
        recap = self.client.get("/recap")
        self.assertEqual(recap.status_code, 200)

        runs = list(self.output_root.glob("wk6-*"))
        self.assertEqual(len(runs), 1)
        names = sorted(p.name for p in runs[0].iterdir())
        # Finalizing the week writes the run-log alongside the derived artifacts.
        self.assertEqual(names, ["events.jsonl", "feed.snapshot.html", "recap.md"])
        # The manager's public post made it into the saved feed.
        self.assertIn(fallout, (runs[0] / "feed.snapshot.html").read_text(encoding="utf-8"))

    def test_in_app_feed_matches_saved_snapshot(self):
        self._play_through()
        run_dir = next(self.output_root.glob("wk6-*"))
        served = self.client.get("/feed").get_data()
        saved = (run_dir / "feed.snapshot.html").read_bytes()
        self.assertEqual(served, saved)

    def test_feed_serves_saved_snapshot_not_a_rerun(self):
        # Once the week is finalized, /feed must serve the written artifact, not
        # re-run generation — otherwise a non-deterministic content backend could
        # show a feed that no longer matches feed.snapshot.html for this slice_id.
        # We prove the source by overwriting the saved file and checking /feed
        # returns the override verbatim.
        self._play_through()
        snapshot = next(self.output_root.glob("wk6-*")) / "feed.snapshot.html"
        sentinel = b"<!-- pinned snapshot, not a re-run -->"
        snapshot.write_bytes(sentinel)
        self.assertEqual(self.client.get("/feed").get_data(), sentinel)

    def test_over_120_char_post_is_rejected_not_500(self):
        self.client.post("/practice", data={"practice_focus": "defaults"})
        self.client.post("/prematch", data={"team_talk": "ok"})
        resp = self.client.post("/fallout", data={"fallout_post": "x" * (OPEN_TEXT_MAX + 1)})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"at most", resp.data)
        # Nothing was written for the rejected post.
        self.assertEqual(list(self.output_root.glob("wk6-*")), [])

    def test_steps_require_the_mc_first(self):
        # Jumping ahead without the practice MC bounces back to /practice.
        for path in (
            "/prematch",
            "/match",
            "/fallout",
            "/recap",
            "/week7",
            "/week7/result",
            "/week8",
            "/week8/scrim",
            "/week8/match",
            "/week8/match/result",
            "/week9",
            "/week9/prep",
            "/week9/scrim",
            "/week9/match",
            "/week9/match/result",
            "/week10/fallout",
            "/week10/prep",
            "/week10/scrim",
            "/week10/match",
            "/feed",
        ):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp.headers["Location"].endswith("/practice"))

    def test_invalid_practice_choice_is_rejected(self):
        resp = self.client.post("/practice", data={"practice_focus": "vibes"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Choose one practice focus", resp.data)

    def test_invalid_training_drill_is_rejected(self):
        resp = self.client.post(
            "/practice",
            data={"practice_focus": "defaults", "training_drill": "vibes"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Choose one focused training drill", resp.data)

    def test_reset_clears_the_week(self):
        self.client.post("/practice", data={"practice_focus": "comms"})
        self.assertEqual(self.client.get("/match").status_code, 200)
        self.client.get("/reset")
        # After reset, the match step again requires the MC.
        self.assertEqual(self.client.get("/match").status_code, 302)

    def test_open_text_html_escaped_in_served_feed(self):
        self._play_through(fallout="<b>boom</b>")
        served = self.client.get("/feed").get_data(as_text=True)
        self.assertNotIn("<b>boom</b>", served)
        self.assertIn("&lt;b&gt;boom&lt;/b&gt;", served)


if __name__ == "__main__":
    unittest.main()
