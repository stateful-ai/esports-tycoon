"""pytest shared fixtures + the `slow` auto-marker + domain auto-tagging.

The suite's wall time is dominated by a couple dozen whole-season /
multi-seed soak tests (each simulates 25-60 campaign weeks). Rather than
scatter `@pytest.mark.slow` across eight files, we keep the list in one
place here and tag matching tests at collection time. Run the fast lane
with `pytest -m "not slow"`; CI and `/ship` still run the full suite.

To add/remove a slow test: edit SLOW_TESTS below. Entries are matched
against the test's `file::function` id (parametrer suffixes like `[2024]`
are ignored), so they stay precise even when two files share a function
name. Refresh the list from a full run's `pytest --durations=30` output
when new soak tests land.

Domain auto-tagging
-------------------
Every test is automatically tagged with one or more domain markers
(`engine`, `campaign`, `web`, `golden`, `policy`, `mcp`, `registry`)
based on what source packages its module imports. No manual annotation
needed — the hook inspects each test file's AST at collection time.

Use with `-m` to target specific domains:
  pytest -m "golden or engine"   # fast engine-only gate
  pytest -m "campaign"           # manager-layer tests
  pytest -m "not slow"           # skip whole-season soaks
  pytest -m "not campaign"       # skip the heavy manager tests

Combined with pytest-testmon (--testmon), domain markers let you run a
fast targeted subset when iterating, while testmon auto-selects only the
tests affected by your git diff for full pre-push verification.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from esports_sim.registry import GameData, load_all

# ── Slow-test registry ──────────────────────────────────────────────────

# file::function ids of the whole-season / multi-seed soak tests, from
# `pytest --durations` (roughly everything >25s on a 16-core box).
SLOW_TESTS = frozenset({
    "test_legacy_meta.py::test_multiseason_diffusion_stays_bounded",
    "test_legacy_career.py::test_full_legacy_season_ticks_clean",
    "test_manager.py::test_full_season_determinism_multiseed",
    "test_manager.py::test_full_season_lifecycle",
    "test_manager.py::test_campaign_determinism",
    "test_inbox.py::test_actions_are_deterministic_across_seeds",
    "test_inbox.py::test_determinism",
    "test_inbox.py::test_top_calls_deterministic",
    "test_inbox.py::test_non_offer_items_have_no_actions",
    "test_inbox.py::test_save_load_roundtrip",
    "test_inbox.py::test_items_generated_and_well_formed",
    "test_inbox.py::test_hands_off_season_gets_no_decision_ledger_digest",
    "test_inbox.py::test_per_week_and_total_bounds",
    "test_inbox.py::test_read_marking",
    "test_inbox.py::test_sorted_items_newest_first",
    "test_campaign_depth.py::test_ai_tactics_adapt_and_stay_deterministic",
    "test_campaign_depth.py::test_best_defensive_team_award_is_granted",
    "test_legacy_world.py::test_playoffs_build_rivalries",
    "test_legacy_chronicle.py::test_full_season_chronicles_titles_awards_retirements",
    "test_legacy_chronicle.py::test_chronicle_deterministic",
    "test_next_pass.py::test_offseason_patch_is_usage_driven_and_state_resets",
    "test_transfers.py::test_lifecycle_retirements_and_rookies",
    "test_transfers.py::test_ai_transfers_happen_over_a_season",
    "test_tactics.py::test_eco_greed_drives_retake_commitment",
    "test_tactics.py::test_each_micro_dial_is_wired",
    "test_match_review.py::test_review_deterministic",
})

# ── Domain auto-detection ───────────────────────────────────────────────

# Map domain marker → source package prefixes. A test importing from any
# of these prefixes gets that domain's marker. Campaign subsumes engine
# (campaign tests that import sim internals are still campaign tests).
DOMAIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "engine": ("esports_sim.sim", "esports_sim.events", "esports_sim.rng"),
    "campaign": ("esports_sim.manager",),
    "web": ("esports_sim.web", "esports_sim.app"),
    "policy": ("esports_sim.policy",),
    "mcp": ("esports_sim.mcp",),
}

# Files matched by stem for domains that can't be detected via imports
# (MCP tests talk to the server via subprocess stdio, not direct imports).
STEM_DOMAINS: dict[str, frozenset[str]] = {
    "test_golden": frozenset({"golden"}),
    "test_determinism": frozenset({"golden"}),
    "test_map_mcp": frozenset({"mcp"}),
    "test_roster_mcp": frozenset({"mcp"}),
    "test_experiment_mcp": frozenset({"mcp"}),
    "test_play_mcp": frozenset({"mcp"}),
}

# ── Cache ────────────────────────────────────────────────────────────────

_domain_cache: dict[str, frozenset[str]] = {}


def _imported_domains(test_file: Path) -> frozenset[str]:
    """Return the set of domain markers for *test_file* by scanning its AST.

    The result is cached per file path and never changes within a session.
    """
    key = str(test_file)
    if key in _domain_cache:
        return _domain_cache[key]

    domains: set[str] = set()

    # Stem-based domains (golden, mcp via subprocess)
    if test_file.stem in STEM_DOMAINS:
        domains.update(STEM_DOMAINS[test_file.stem])

    # Registry detection: any import from esports_sim.registry / .schemas
    # but only if the test doesn't also import sim/manager (registry-only).
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        _domain_cache[key] = frozenset(domains)
        return _domain_cache[key]

    # Collect all esports_sim imports
    imported_prefixes: set[str] = set()
    has_registry_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("esports_sim."):
                    imported_prefixes.add(alias.name)
                elif alias.name == "esports_sim":
                    imported_prefixes.add("esports_sim")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("esports_sim"):
                imported_prefixes.add(node.module)

    # Match prefixes to domains
    for domain, prefixes in DOMAIN_PREFIXES.items():
        for imp in imported_prefixes:
            for prefix in prefixes:
                if imp == prefix or imp.startswith(prefix + "."):
                    domains.add(domain)
                    break

    # Campaign subsumes engine: if a test imports both sim and manager,
    # it's a campaign test (the sim import is incidental).
    if "engine" in domains and "campaign" in domains:
        domains.discard("engine")

    # Registry: tagged if the test imports registry/schemas but NOT
    # sim/manager/web/policy/mcp (pure data validation tests).
    has_registry = any(
        imp.startswith(("esports_sim.registry", "esports_sim.schemas"))
        for imp in imported_prefixes
    )
    has_behaviour = bool(domains)  # engine/campaign/web/policy/mcp already set
    if has_registry and not has_behaviour:
        domains.add("registry")

    result = frozenset(domains)
    _domain_cache[key] = result
    return result


# ── Collection hook ──────────────────────────────────────────────────────


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Tag SLOW_TESTS with `slow`, auto-tag every test with domain markers,
    and pin inbox tests into xdist groups for fixture sharing."""
    for item in items:
        # --- slow marker ---
        # item.nodeid looks like "tests/test_inbox.py::test_determinism" or
        # "...::test_x[param]"; strip the dir prefix and param suffix.
        base = item.nodeid.split("[", 1)[0].split("/")[-1]
        if base in SLOW_TESTS:
            item.add_marker(pytest.mark.slow)

        # --- domain markers ---
        test_path = Path(item.fspath)
        for domain in _imported_domains(test_path):
            item.add_marker(getattr(pytest.mark, domain))

        # --- xdist groups for inbox fixture sharing ---
        # Co-locate the consumers of test_inbox's shared season fixtures so
        # the whole-season sim behind them runs once per group, not per test.
        fixtures = getattr(item, "fixturenames", ())
        if "det_pair" in fixtures:
            item.add_marker(pytest.mark.xdist_group("inbox_det"))
        elif "season" in fixtures or "season_copy" in fixtures:
            item.add_marker(pytest.mark.xdist_group("inbox_season"))

        # --- browser lane: one worker, one server, one browser ---
        # Every `playtest` test shares a module-scoped game server and a
        # Chromium. Spread across xdist workers they each boot their own
        # pair, and N servers + N browsers competing for a few cores push
        # server startup past its timeout -- the whole lane then fails with
        # "game server did not come up", which reads like an app bug and is
        # not one. Pinning them to one group keeps it to a single pair.
        if item.get_closest_marker("playtest") is not None:
            item.add_marker(pytest.mark.xdist_group("playtest_browser"))


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def game_data() -> GameData:
    return load_all()
