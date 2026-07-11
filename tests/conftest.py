"""pytest shared fixtures + the `slow` auto-marker.

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
"""

from __future__ import annotations

import pytest

from esports_sim.registry import GameData, load_all

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
    "test_inbox.py::test_non_offer_items_have_no_actions",
    "test_inbox.py::test_save_load_roundtrip",
    "test_inbox.py::test_items_generated_and_well_formed",
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


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Tag SLOW_TESTS with `slow` (so `-m 'not slow'` drops them), and pin
    tests that share a module-scoped season fixture into one xdist group so
    `--dist loadgroup` builds that fixture once instead of per worker."""
    for item in items:
        # item.nodeid looks like "tests/test_inbox.py::test_determinism" or
        # "...::test_x[param]"; strip the dir prefix and param suffix.
        base = item.nodeid.split("[", 1)[0].split("/")[-1]
        if base in SLOW_TESTS:
            item.add_marker(pytest.mark.slow)

        # Co-locate the consumers of test_inbox's shared season fixtures so
        # the whole-season sim behind them runs once per group, not per test.
        fixtures = getattr(item, "fixturenames", ())
        if "det_pair" in fixtures:
            item.add_marker(pytest.mark.xdist_group("inbox_det"))
        elif "season" in fixtures or "season_copy" in fixtures:
            item.add_marker(pytest.mark.xdist_group("inbox_season"))


@pytest.fixture(scope="session")
def game_data() -> GameData:
    return load_all()
