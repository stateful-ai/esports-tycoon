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
    SliceConfig,
    SliceDecisions,
    read_events,
    render_feed_html,
    render_recap_md,
    run_slice,
    slice_events,
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
