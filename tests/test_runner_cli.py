"""End-to-end wiring: one runner invocation exercises load → resolve → recap.

The acceptance bar for ``m0_0_canonical_contract.md`` (Rebind map) is that the
resolver, the slice runner, the recap reader, **and the web app** share **one**
canonical ``WorldState`` — and that both player-visible seams (the headless
runner CLI and the local Flask shell) exercise that contract against the real,
shipped ``week6.yaml``. The wiring landed across PRs #2, #3/#9, #6, #13, #14
and #16/#17; this module pins it as a contract so a future change cannot quietly
re-introduce a parallel/draft typing without a test going red:

* :class:`TestRunnerCliEndToEnd` invokes ``python -m esports_tycoon.runner``'s
  ``main()`` against the packaged canned save, with no fixtures and no
  monkey-patched world. One process load-validates the save (which is what
  reads ``schema_version``), the resolver runs, and the recap reader writes
  the three artifacts (``events.jsonl``, ``recap.md``, ``feed.snapshot.html``).
  Re-running with the same flags lands on the same content-addressed
  ``runs/<slice_id>/`` and the bytes don't drift.
* :class:`TestRunnerCliSchemaVersionGate` proves the load path the CLI uses is
  the *gated* one: an off-version save fed to the same ``main()`` is rejected
  with a typed ``SchemaVersionError``, not silently loaded. This is what makes
  the "in one runner invocation reading ``schema_version``" half of the
  acceptance line real instead of decorative.
* :class:`TestWebAppCanonicalRebind` pins the *other* surface the rebind map
  names: the Flask shell. It drives the app through a Flask test client and
  asserts that the canonical world fields — ``world.save.team.name``,
  ``world.rivals[].name``, ``world.rivals[].archetype``, ``world.save.title``,
  ``world.save.season.{league,division}`` — actually reach the rendered HTML
  on the briefing, match, and recap pages. A draft-typed binding would either
  miss these attributes or render IDs verbatim; asserting them by *value* on
  the same process that the runner CLI uses pins both surfaces to one schema.
* :class:`TestNoDraftFieldReferences` is the structural guard: it scans every
  shipped Python module and HTML template for ``draft_*`` / ``_draft`` field
  references on any object, so the rebind cannot be silently regressed by a
  later change that re-introduces a parallel draft attribute on a surface.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.runner.__main__ import main as runner_main  # noqa: E402
from esports_tycoon.runner.engine import run_slice  # noqa: E402
from esports_tycoon.runner.model import SliceConfig, SliceDecisions  # noqa: E402
from esports_tycoon.runner.recap import (  # noqa: E402
    EVENTS_FILENAME,
    FEED_FILENAME,
    RECAP_FILENAME,
)
from esports_tycoon.schema import CURRENT_SCHEMA_VERSION  # noqa: E402

try:
    import flask  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - exercised only without the extra
    flask = None


class TestRunnerCliEndToEnd(unittest.TestCase):
    """One ``python -m esports_tycoon.runner`` invocation runs all three seams."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.runs_dir = pathlib.Path(self._tmp.name)

    def _invoke(self, *extra: str) -> int:
        # No --save: defaults to ``loader.DEFAULT_SAVE_PATH`` (the packaged,
        # shipped week6.yaml), which is what the acceptance line means by "real
        # week6.yaml". The runs dir is sandboxed so parallel test runs and the
        # repo's ``runs/`` are untouched.
        return runner_main(["--runs-dir", str(self.runs_dir), *extra])

    def test_one_invocation_writes_all_three_artifacts(self):
        # The CLI's job is to thread the canonical world through resolver →
        # slice runner → recap reader in a single process. Success is the three
        # artifact files in one ``runs/<slice_id>/`` folder.
        self.assertEqual(self._invoke(), 0)
        runs = list(self.runs_dir.glob("wk6-*"))
        self.assertEqual(len(runs), 1, "expected exactly one runs/<slice_id>/ folder")
        names = sorted(p.name for p in runs[0].iterdir())
        self.assertEqual(names, sorted([EVENTS_FILENAME, FEED_FILENAME, RECAP_FILENAME]))

    def test_recap_is_authored_against_the_canonical_world(self):
        # The canonical schema is the source of identity in the recap (team
        # name, opponent name resolved via rival id, opponent's archetype). A
        # draft-typed reader would either miss these or render IDs verbatim;
        # asserting them by *value* pins the rebind.
        self.assertEqual(self._invoke(), 0)
        world = loader.load()
        run_dir = next(self.runs_dir.glob("wk6-*"))
        recap = (run_dir / RECAP_FILENAME).read_text(encoding="utf-8")
        opponent = next(r for r in world.rivals if r.id == "apex_foundry")
        self.assertIn(world.save.team.name, recap)
        self.assertIn(opponent.name, recap)
        self.assertIn(opponent.archetype, recap)

    def test_same_flags_replay_byte_identical(self):
        # Determinism is the contract behind "same seed ⇒ identical recap": two
        # invocations land on the same slice_id and produce identical bytes for
        # all three artifacts. The second invocation overwrites the first, so
        # we copy the first set out before re-running.
        self.assertEqual(self._invoke(), 0)
        run_dir = next(self.runs_dir.glob("wk6-*"))
        first = {p.name: p.read_bytes() for p in run_dir.iterdir()}
        self.assertEqual(self._invoke(), 0)
        run_dir2 = next(self.runs_dir.glob("wk6-*"))
        self.assertEqual(run_dir2.name, run_dir.name, "slice_id drifted across runs")
        second = {p.name: p.read_bytes() for p in run_dir2.iterdir()}
        self.assertEqual(first, second)

    def test_decisions_thread_through_to_the_recap(self):
        # The two open-text moments (the captain's pre-match talk and the
        # manager's post-match Chirper line) are the player's only free-text
        # surface, and the recap renders them verbatim. If the decisions don't
        # reach the renderer, the rebind is broken.
        talk = "no heroes. run the default."
        post = "week 6: held the line. on to week 7."
        self.assertEqual(
            self._invoke("--team-talk", talk, "--fallout", post),
            0,
        )
        run_dir = next(self.runs_dir.glob("wk6-*"))
        recap = (run_dir / RECAP_FILENAME).read_text(encoding="utf-8")
        feed = (run_dir / FEED_FILENAME).read_text(encoding="utf-8")
        self.assertIn(talk, recap)
        self.assertIn(post, feed)


class TestRunnerCliSchemaVersionGate(unittest.TestCase):
    """The CLI's load path is the gated one: schema_version is checked, not skipped."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.runs_dir = self.tmp / "runs"

    def _write_save(self, **overrides) -> pathlib.Path:
        # Take the shipped save by value, splice in the override, and write it
        # somewhere the CLI's ``--save`` flag can pick it up. Keeps the gate
        # test honest: we mutate one field on the same bytes the happy path
        # uses, instead of hand-assembling a half-save.
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        raw.update(overrides)
        path = self.tmp / "save.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return path

    def test_future_version_save_is_rejected_by_the_cli(self):
        # A schema_version this build cannot read trips the loader's gate, and
        # the CLI surfaces it as a typed ``SchemaVersionError`` — never as a
        # successful run with silently-degraded data.
        save = self._write_save(schema_version=CURRENT_SCHEMA_VERSION + 1)
        with self.assertRaises(loader.SchemaVersionError):
            runner_main(["--save", str(save), "--runs-dir", str(self.runs_dir)])
        # The gate fires before any artifact is written.
        self.assertFalse(self.runs_dir.exists())

    def test_missing_version_save_is_rejected_by_the_cli(self):
        # A save with no schema_version at all is rejected the same way: the
        # CLI does not fall back to "assume current".
        raw = yaml.safe_load(loader.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
        raw.pop("schema_version")
        path = self.tmp / "save.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with self.assertRaises(loader.SchemaVersionError):
            runner_main(["--save", str(path), "--runs-dir", str(self.runs_dir)])
        self.assertFalse(self.runs_dir.exists())


@unittest.skipIf(flask is None, "Flask not installed (pip install -e '.[web]')")
class TestWebAppCanonicalRebind(unittest.TestCase):
    """The Flask shell renders canonical ``WorldState`` fields on every page.

    Behavioural coverage of the web app lives in ``test_web_app.py``; this class
    only pins the *binding* half of the rebind map. The goal is to catch a
    regression where the shell starts holding a parallel/draft type that happens
    to render but no longer carries the canonical attribute names (``save.team``,
    ``save.season``, ``rivals[].archetype``, etc.).
    """

    def setUp(self):
        from esports_tycoon.web import create_app

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_root = pathlib.Path(self._tmp.name)
        app = create_app(output_root=self.output_root)
        app.testing = True
        self.client = app.test_client()
        # The web app and the runner CLI both default to ``loader.load()``; load
        # one copy here and read canonical fields off it to assert against the
        # rendered HTML, so the test fails if the schema attribute names drift.
        self.world = loader.load()
        self.opponent = next(r for r in self.world.rivals if r.id == "apex_foundry")

    def test_briefing_renders_canonical_team_opponent_and_season(self):
        # The briefing is the one page the player sees before making any
        # decision — if the shell were bound to a draft type, the team name,
        # season metadata, or opponent archetype would not surface here.
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn(self.world.save.team.name, page)
        self.assertIn(self.world.save.title, page)
        self.assertIn(self.world.save.season.league, page)
        self.assertIn(self.world.save.season.division, page)
        self.assertIn(self.opponent.name, page)
        self.assertIn(self.opponent.archetype, page)

    def test_match_page_renders_canonical_team_and_opponent(self):
        self.client.post("/practice", data={"practice_focus": "defaults"})
        self.client.post("/prematch", data={"team_talk": "run the default."})
        page = self.client.get("/match").get_data(as_text=True)
        self.assertIn(self.world.save.team.name, page)
        self.assertIn(self.opponent.name, page)

    def test_recap_page_and_saved_recap_share_canonical_identity(self):
        # Finalizing the week writes ``recap.md`` and renders ``/recap``. Both
        # surfaces must spell the same canonical names — that is the rebind.
        self.client.post("/practice", data={"practice_focus": "defaults"})
        self.client.post("/prematch", data={"team_talk": "run the default."})
        self.client.post("/fallout", data={"fallout_post": "on to week 7."})
        page = self.client.get("/recap").get_data(as_text=True)
        self.assertIn(self.world.save.team.name, page)
        self.assertIn(self.opponent.name, page)
        run_dir = next(self.output_root.glob("wk6-*"))
        recap_md = (run_dir / RECAP_FILENAME).read_text(encoding="utf-8")
        self.assertIn(self.world.save.team.name, recap_md)
        self.assertIn(self.opponent.name, recap_md)
        self.assertIn(self.opponent.archetype, recap_md)


class TestNoDraftFieldReferences(unittest.TestCase):
    """No surface (Python module or HTML template) references a draft-typed field.

    The rebind map calls for *removal* of draft-field references across surfaces,
    not just for the canonical ones to also work. A grep-style guard here is the
    cheapest way to keep that property: if anyone later writes ``world.draft_*``,
    ``save.draft_*``, ``{{ draft_* }}`` or a class named ``Draft*``, this test
    goes red and the rebind cannot be silently regressed.
    """

    # ``draft_<word>`` or ``<word>_draft`` as a Python/HTML attribute access or
    # template variable; deliberately narrow so prose mentioning "draft" in
    # docstrings or comments (the doc files do) is not a false positive.
    _DRAFT_ATTR = re.compile(r"\b(?:draft_[a-z][a-z_]*|[a-z][a-z_]*_draft)\b")
    _DRAFT_CLASS = re.compile(r"\bclass\s+Draft[A-Z][A-Za-z0-9_]*\b")

    def _surfaces(self) -> list[pathlib.Path]:
        repo = pathlib.Path(__file__).resolve().parents[1] / "esports_tycoon"
        return sorted(
            p
            for p in (*repo.rglob("*.py"), *repo.rglob("*.html"))
            if "__pycache__" not in p.parts
        )

    def test_no_draft_attribute_references_on_any_surface(self):
        offenders: list[str] = []
        for path in self._surfaces():
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                # Ignore prose in docstrings/comments — only flag code-shape uses.
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                    continue
                if self._DRAFT_ATTR.search(line) or self._DRAFT_CLASS.search(line):
                    offenders.append(f"{path}:{lineno}: {line.rstrip()}")
        self.assertEqual(offenders, [], "draft-typed references found on shipped surfaces")


class TestMinimumPlayable(unittest.TestCase):
    """The narrowed rebind contract: one default-flags command is the playable slice.

    Pinned against ``docs/m0_1_minimum_playable_rescope.md`` — the re-scope that
    drops "full canonical-schema convergence" from the rebind ticket's
    preconditions and replaces it with: one command, default canned save, plays
    practice → match → fallout, renders Chirper feed + post-match narration, in
    templated (zero-API) mode. The behaviours each test below checks are the
    four bullets of that narrowed acceptance — kept here as a single cohesive
    pin so a future change cannot quietly re-inflate the ticket.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.runs_dir = pathlib.Path(self._tmp.name)

    def _invoke_default(self) -> int:
        # No flags beyond the sandbox: this is the founder's "one command".
        # If the test ever needs to pass a behavioural flag to make this run
        # work, the minimum-playable contract is broken — fix the runner's
        # defaults, not the test.
        return runner_main(["--runs-dir", str(self.runs_dir)])

    def test_default_invocation_writes_recap_and_feed(self):
        # The one command writes the two screenshot-ready artifacts the founder
        # actually opens, in one ``runs/<slice_id>/`` folder.
        self.assertEqual(self._invoke_default(), 0)
        runs = list(self.runs_dir.glob("wk6-*"))
        self.assertEqual(len(runs), 1, "expected exactly one runs/<slice_id>/ folder")
        run_dir = runs[0]
        self.assertTrue((run_dir / RECAP_FILENAME).is_file(), "recap.md missing")
        self.assertTrue((run_dir / FEED_FILENAME).is_file(), "feed.snapshot.html missing")
        # ``events.jsonl`` is the system-of-record the other two artifacts are
        # derived from; if it is gone, "minimum playable" is decoration.
        self.assertTrue((run_dir / EVENTS_FILENAME).is_file(), "events.jsonl missing")

    def test_chirper_feed_snapshot_has_posts(self):
        # The Chirper feed is one of the two named deliverables in the
        # narrowed acceptance. A page with no ``<article class="post">`` is a
        # blank Chirper — not a playable slice.
        self.assertEqual(self._invoke_default(), 0)
        run_dir = next(self.runs_dir.glob("wk6-*"))
        feed = (run_dir / FEED_FILENAME).read_text(encoding="utf-8")
        self.assertIn('<article class="post">', feed)
        # The shape — standalone HTML doc, inline CSS, no external assets —
        # is part of the contract: the screenshot has to work offline from the
        # ``runs/`` folder, not via the running web shell.
        self.assertIn("<!DOCTYPE html>", feed)
        self.assertIn("<style>", feed)

    def test_post_match_narration_is_rendered_in_recap(self):
        # The other named deliverable: the resolver-grounded narration appears
        # verbatim in ``recap.md`` under "## The match". Computed against the
        # engine using the same default inputs the CLI uses, so this test
        # follows the engine's contract rather than hard-coding the prose.
        self.assertEqual(self._invoke_default(), 0)
        run_dir = next(self.runs_dir.glob("wk6-*"))
        recap = (run_dir / RECAP_FILENAME).read_text(encoding="utf-8")

        world = loader.load()
        # Mirror the CLI's defaults (``esports_tycoon.runner.__main__``) so the
        # engine call resolves the same SliceResult the runner produced.
        config = SliceConfig(opponent="apex_foundry", map="Helix", seed=6, tactical_stance="default")
        decisions = SliceDecisions(practice_focus="defaults", team_talk="", fallout_post="")
        expected = run_slice(world, config, decisions)

        self.assertIn("## The match", recap)
        self.assertIn(expected.narration.text, recap)
        self.assertTrue(expected.narration.text.strip(), "narration was empty — not playable")

    def test_default_run_is_in_templated_zero_api_mode(self):
        # "Zero API calls" is the load-bearing property of the narrowed scope.
        # Two checks pin it: the recap header advertises the templated banner,
        # and the run-log records ``content_backend: templated`` on the first
        # event — the projection the recap renderer reads. Anything else would
        # mean the default route silently went through an LLM backend.
        self.assertEqual(self._invoke_default(), 0)
        run_dir = next(self.runs_dir.glob("wk6-*"))
        recap = (run_dir / RECAP_FILENAME).read_text(encoding="utf-8")
        self.assertIn("templated mode (zero-API)", recap)

        events = (run_dir / EVENTS_FILENAME).read_text(encoding="utf-8").splitlines()
        self.assertTrue(events, "events.jsonl was empty")
        first = json.loads(events[0])
        self.assertEqual(first.get("type"), "slice_started")
        self.assertEqual(first.get("content_backend"), "templated")

    def test_templated_default_does_not_route_through_llm_backend(self):
        # The architectural guarantee: ``esports_tycoon.content.adapter`` only
        # imports the LLM backend inside the ``vllm`` branch, so a default run
        # never exercises ``content.llm.generate``. Pin it by trapping that
        # symbol — if the templated default ever silently calls it, the trap
        # fires and the test goes red. Done with a sentinel rather than a
        # ``sys.modules`` membership check because earlier tests in the same
        # process may have legitimately imported the module already.
        import esports_tycoon.content.llm as llm_module

        original = getattr(llm_module, "generate", None)
        sentinel_calls: list[str] = []

        def _trap(*_args, **_kwargs):
            sentinel_calls.append("called")
            raise AssertionError(
                "templated default routed through the vllm backend: "
                "content.llm.generate was invoked during a default run"
            )

        llm_module.generate = _trap  # type: ignore[assignment]
        try:
            self.assertEqual(self._invoke_default(), 0)
        finally:
            if original is None:
                # The module had no ``generate`` before — leave it absent rather
                # than leaking the trap.
                delattr(llm_module, "generate")
            else:
                llm_module.generate = original  # type: ignore[assignment]
        self.assertEqual(sentinel_calls, [], "LLM backend was invoked on the templated default")


if __name__ == "__main__":
    unittest.main()
