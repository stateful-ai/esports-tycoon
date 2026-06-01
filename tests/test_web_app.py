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

    def test_manager_view_and_feed_served_by_one_app(self):
        briefing = self.client.get("/")
        self.assertEqual(briefing.status_code, 200)
        self.assertIn(b"must-win", briefing.data)
        # Feed is reachable from the same process (after the MC is made).
        self.client.post("/practice", data={"practice_focus": "aim"})
        feed = self.client.get("/feed")
        self.assertEqual(feed.status_code, 200)
        self.assertIn(b"Chirper", feed.data)

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
        for path in ("/prematch", "/match", "/fallout", "/recap", "/week7", "/week7/result", "/week8", "/feed"):
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
