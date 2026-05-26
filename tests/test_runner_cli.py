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

import ast
import pathlib
import re
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.runner.__main__ import main as runner_main  # noqa: E402
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
    not just for the canonical ones to also work. The check has two halves:

    * Python modules are scanned via :mod:`ast`, not regex, so docstrings and
      comments are excluded by construction (the parser drops them) and a draft
      attribute access cannot hide behind, say, a same-line inline string. We
      look at every ``Attribute`` access, every bare ``Name`` reference, and
      every ``ClassDef``/``FunctionDef`` definition site.
    * Jinja templates are scanned with a regex constrained to ``{{ ... }}`` and
      ``{% ... %}`` expressions, so the same narrowing holds: only template
      *code* is checked, not the surrounding HTML prose.

    If anyone later writes ``world.draft_*``, ``{{ draft_* }}``, or defines a
    class named ``Draft*``, this test goes red and the rebind cannot be silently
    regressed.
    """

    # ``draft_<word>`` or ``<word>_draft`` as a Python identifier or as a Jinja
    # template variable inside an expression block.
    _DRAFT_IDENT = re.compile(r"\b(?:draft_[a-z][a-z_0-9]*|[a-z][a-z_0-9]*_draft)\b")
    _DRAFT_CLASS_NAME = re.compile(r"^Draft[A-Z][A-Za-z0-9_]*$")
    _JINJA_EXPR = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.DOTALL)

    def _python_surfaces(self) -> list[pathlib.Path]:
        repo = pathlib.Path(__file__).resolve().parents[1] / "esports_tycoon"
        return sorted(p for p in repo.rglob("*.py") if "__pycache__" not in p.parts)

    def _template_surfaces(self) -> list[pathlib.Path]:
        repo = pathlib.Path(__file__).resolve().parents[1] / "esports_tycoon"
        return sorted(repo.rglob("*.html"))

    def _python_offenders(self, path: pathlib.Path) -> list[str]:
        # AST walk: attributes, plain name references, class & function defs.
        # Strings (including docstrings) and comments are not ast nodes that
        # carry identifiers, so they're excluded by construction.
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and self._DRAFT_IDENT.fullmatch(node.attr):
                offenders.append(f"{path}:{node.lineno}: attribute .{node.attr}")
            elif isinstance(node, ast.Name) and self._DRAFT_IDENT.fullmatch(node.id):
                offenders.append(f"{path}:{node.lineno}: name {node.id}")
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._DRAFT_CLASS_NAME.match(node.name) or self._DRAFT_IDENT.fullmatch(node.name):
                    offenders.append(f"{path}:{node.lineno}: definition {node.name}")
            elif isinstance(node, ast.arg) and self._DRAFT_IDENT.fullmatch(node.arg):
                offenders.append(f"{path}:{node.lineno}: parameter {node.arg}")
        return offenders

    def _template_offenders(self, path: pathlib.Path) -> list[str]:
        # Only look inside ``{{ ... }}`` and ``{% ... %}`` — the rest is HTML
        # prose that the renderer never evaluates, so it cannot hold a binding.
        text = path.read_text(encoding="utf-8")
        offenders: list[str] = []
        for match in self._JINJA_EXPR.finditer(text):
            expr = match.group(1) or match.group(2) or ""
            if self._DRAFT_IDENT.search(expr):
                lineno = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path}:{lineno}: jinja {expr.strip()}")
        return offenders

    def test_no_draft_references_in_python_modules(self):
        offenders: list[str] = []
        for path in self._python_surfaces():
            offenders.extend(self._python_offenders(path))
        self.assertEqual(offenders, [], "draft-typed references found in Python modules")

    def test_no_draft_references_in_html_templates(self):
        offenders: list[str] = []
        for path in self._template_surfaces():
            offenders.extend(self._template_offenders(path))
        self.assertEqual(offenders, [], "draft-typed references found in HTML templates")


if __name__ == "__main__":
    unittest.main()
