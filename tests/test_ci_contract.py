"""The ``make test`` + CI contract: clean-clone green, golden-drift fails build.

The acceptance bar for the ``make test`` + CI ticket is two short clauses:

* green from a clean clone with no API key;
* CI fails the build if golden output drifts.

The first clause is *exercised* by every other test in this suite — they all
run under templated mode with no network, so if any of them shells out to a
real endpoint, CI catches it. What that clause leaves implicit is the *plumbing*:
that a ``Makefile`` exposes a ``test`` target and that a CI workflow actually
runs it. The second clause is *enforced* by ``test_golden_determinism.py``, but
only if that file is actually wired into ``make test`` and into CI.

This module locks the plumbing so the two halves can't silently drift apart:
the Makefile has a ``test`` target that runs pytest; the CI workflow runs
``make test``; both refuse to set ``UPDATE_GOLDEN`` (which would silently bless
drifted goldens); and the goldens themselves remain committed. None of these
checks shell out — they read the files in the repo, since the goal is to
catch a config regression in the same place a developer would notice it.
"""

from __future__ import annotations

import pathlib
import re
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MAKEFILE = _REPO_ROOT / "Makefile"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_GOLDEN_DIR = _REPO_ROOT / "tests" / "golden"
_GOLDEN_TEST = _REPO_ROOT / "tests" / "test_golden_determinism.py"


class TestMakefileContract(unittest.TestCase):
    """The Makefile exposes the entrypoints CI and contributors depend on."""

    @classmethod
    def setUpClass(cls):
        cls.text = _MAKEFILE.read_text(encoding="utf-8")

    def test_makefile_exists(self):
        self.assertTrue(_MAKEFILE.exists(), "Makefile is the documented entrypoint")

    def test_test_target_is_defined(self):
        # A line beginning with ``test:`` (with optional dependencies) is what
        # `make test` resolves to. The check tolerates trailing dependencies
        # and ``## help`` comments but requires the bare target to exist.
        self.assertRegex(
            self.text,
            r"(?m)^test:\s",
            "Makefile must define a `test` target — that's what CI runs",
        )

    def test_test_target_invokes_pytest(self):
        # The exact pytest invocation is allowed to vary (args, runner), but
        # `make test` must actually run the test suite — not a stub or a
        # placeholder echo.
        self.assertRegex(
            self.text,
            r"\bpytest\b",
            "the `test` target must run pytest (the suite includes the golden + round-trip tests)",
        )

    def test_test_target_unsets_update_golden(self):
        # An exported UPDATE_GOLDEN=1 in a developer's shell must not survive
        # into the test run, or `make test` would silently rewrite the
        # committed goldens instead of failing on drift.
        self.assertIn(
            "UPDATE_GOLDEN=",
            self.text,
            "`make test` must clear UPDATE_GOLDEN so drifted goldens fail the build",
        )

    def test_golden_update_escape_hatch_exists(self):
        # Intended changes still need a one-command way to re-emit the
        # goldens; without this, every drift forces a hand-edit dance.
        self.assertRegex(
            self.text,
            r"(?m)^golden-update:\s",
            "Makefile must expose a `golden-update` target for intended golden refreshes",
        )


class TestCIWorkflowContract(unittest.TestCase):
    """The CI workflow runs `make test` from a clean clone on every commit."""

    @classmethod
    def setUpClass(cls):
        cls.text = _CI_WORKFLOW.read_text(encoding="utf-8") if _CI_WORKFLOW.exists() else ""

    def test_ci_workflow_exists(self):
        self.assertTrue(
            _CI_WORKFLOW.exists(),
            f"{_CI_WORKFLOW.relative_to(_REPO_ROOT)} must exist — CI is the gate against golden drift",
        )

    def test_ci_triggers_on_push_and_pull_request(self):
        # "On every commit" means both branch pushes and PRs. A workflow that
        # only fired on PRs would let a direct push to main slip through.
        self.assertRegex(self.text, r"(?m)^\s*push:", "CI must trigger on push")
        self.assertRegex(self.text, r"(?m)^\s*pull_request:", "CI must trigger on pull_request")

    def test_ci_runs_make_test(self):
        # The whole point of having a Makefile is that CI and contributors
        # share an entrypoint; if CI drifts to a hand-rolled `pytest ...`
        # incantation, the two stop reflecting each other.
        self.assertRegex(
            self.text,
            r"\bmake test\b",
            "CI must invoke `make test` so contributors and CI share one command",
        )

    def test_ci_does_not_set_update_golden(self):
        # UPDATE_GOLDEN must never be set to a truthy value in CI: that would
        # turn a drift-detection job into a drift-blessing job. An empty
        # assignment (``UPDATE_GOLDEN: ""``) is allowed and is how the
        # workflow strips a possibly-inherited value.
        for match in re.finditer(r"UPDATE_GOLDEN\s*[:=]\s*(\S+)", self.text):
            value = match.group(1).strip().strip('"').strip("'")
            self.assertEqual(
                value,
                "",
                f"CI sets UPDATE_GOLDEN={value!r}; this would bless drifted goldens",
            )

    def test_ci_does_not_inject_api_keys(self):
        # Acceptance bar: "green from a clean clone with no API key". If CI
        # quietly supplies a GAME_LLM_API_KEY or OPENAI_API_KEY, the suite
        # could come to depend on it and the clean-clone bar would silently
        # rot. Block the obvious names.
        forbidden = ("GAME_LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        for name in forbidden:
            self.assertNotRegex(
                self.text,
                rf"{name}\s*[:=]",
                f"CI must not inject {name}; the zero-API path is the gate",
            )


class TestGoldenArtifactsCommitted(unittest.TestCase):
    """The committed goldens must actually be in the tree for drift to fail."""

    def test_golden_directory_exists(self):
        self.assertTrue(_GOLDEN_DIR.is_dir(), "tests/golden/ holds the committed reference bytes")

    def test_each_golden_artifact_is_committed(self):
        # The three artifacts the golden test pins: the resolved record, the
        # canonical save, and the templated render of the week-6 slice. If
        # any of them is missing from the tree, the golden test would either
        # crash on first run or (under UPDATE_GOLDEN) materialize silently —
        # neither is "CI fails the build if golden output drifts."
        for name in ("week6_resolve.json", "week6_canonical.yaml", "week6_content.json"):
            path = _GOLDEN_DIR / name
            self.assertTrue(path.exists(), f"missing committed golden: {path.relative_to(_REPO_ROOT)}")
            self.assertGreater(path.stat().st_size, 0, f"empty golden: {path.relative_to(_REPO_ROOT)}")

    def test_golden_test_module_is_present(self):
        # The Makefile and CI both reference this file by path; if it ever
        # moves, the rename has to happen everywhere at once.
        self.assertTrue(_GOLDEN_TEST.exists(), "tests/test_golden_determinism.py is the drift gate")


if __name__ == "__main__":
    unittest.main()
