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

    def test_full_flow_writes_artifact(self):
        fallout = "week 6: held the line."
        self._play_through(fallout=fallout)
        recap = self.client.get("/recap")
        self.assertEqual(recap.status_code, 200)

        runs = list(self.output_root.glob("wk6-*"))
        self.assertEqual(len(runs), 1)
        names = sorted(p.name for p in runs[0].iterdir())
        self.assertEqual(names, ["feed.snapshot.html", "recap.md"])
        # The manager's public post made it into the saved feed.
        self.assertIn(fallout, (runs[0] / "feed.snapshot.html").read_text(encoding="utf-8"))

    def test_in_app_feed_matches_saved_snapshot(self):
        self._play_through()
        run_dir = next(self.output_root.glob("wk6-*"))
        served = self.client.get("/feed").get_data()
        saved = (run_dir / "feed.snapshot.html").read_bytes()
        self.assertEqual(served, saved)

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
        for path in ("/prematch", "/match", "/fallout", "/recap", "/feed"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp.headers["Location"].endswith("/practice"))

    def test_invalid_practice_choice_is_rejected(self):
        resp = self.client.post("/practice", data={"practice_focus": "vibes"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Choose one practice focus", resp.data)

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
