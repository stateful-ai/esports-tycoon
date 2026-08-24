"""End-to-end: boot the game, open it in a real browser, play a week.

Every other test in this suite reasons about the game through Python. These
reason about it through Chromium, which is the only way to catch the class of
failure where the server is perfectly healthy and the player still sees
nothing — a module that will not load, a screen that renders empty, a button
that no longer exists. The blank-UI regression that motivated
`tests/test_web_assets.py` passed every API test in the repo.

Marked `playtest` (and `slow`): they need Chromium and a real server boot, so
they sit out the fast lane. Run them with:

    pytest -q -m playtest
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from esports_sim.playtest.dom import render_digest
from esports_sim.playtest.session import GameServer, PlaytestSession, TABS, find_chromium

pytestmark = [pytest.mark.playtest, pytest.mark.slow, pytest.mark.web]


def _require_browser() -> None:
    pytest.importorskip("playwright", reason="playwright is not installed")
    if find_chromium() is None:
        pytest.skip("no Chromium available (set $PLAYTEST_CHROMIUM)")


@pytest.fixture(scope="module")
def game(tmp_path_factory) -> GameServer:
    """The real web app on a real port, with its own saves directory."""
    _require_browser()
    saves = tmp_path_factory.mktemp("playtest-saves")
    server = GameServer(saves_dir=saves)
    server.start(log_path=saves / "server.log")
    yield server
    server.stop()


@pytest.fixture(scope="module")
def session(game: GameServer, tmp_path_factory) -> PlaytestSession:
    """One browser, one campaign, shared across the module.

    Booting Chromium and generating a league costs ~30s; doing it per test
    would make this file too slow to keep. The tests below only read, except
    the advance test which is ordered last by name.
    """
    run_dir = tmp_path_factory.mktemp("playtest-run")
    live = PlaytestSession(run_dir=run_dir, base_url=game.url)
    live.start()
    observation = live.new_campaign(seed=2026)
    assert observation.ok, f"could not start a campaign: {observation.message}"
    live.close_overlay()  # the first-run handbook opens over the dashboard
    yield live
    live.close()


def test_the_server_answers_before_a_browser_is_involved(game: GameServer):
    import urllib.request

    with urllib.request.urlopen(f"{game.url}/api/lobby", timeout=10) as response:  # noqa: S310
        assert response.status == 200
        assert "teams" in json.loads(response.read().decode())


def test_the_app_actually_renders(session: PlaytestSession):
    """The regression guard: chrome painted but an empty #view is the bug."""
    snapshot = session.snapshot()
    assert snapshot["inGame"], "the lobby is still open — no campaign was created"
    assert snapshot["viewTextLength"] > 200, (
        "the app shell rendered but #view is empty — this is what a failed "
        "module load looks like"
    )


def test_the_page_loaded_no_module_from_the_network(session: PlaytestSession):
    urls = session.page.evaluate(
        "() => performance.getEntriesByType('resource')"
        ".map((e) => e.name).filter((u) => !u.startsWith(location.origin))"
    )
    assert not urls, f"the page fetched {urls} from outside its own origin"


@pytest.mark.parametrize("tab", TABS)
def test_every_tab_renders_something(session: PlaytestSession, tab: str):
    observation = session.open_tab(tab)
    assert observation.ok, f"could not open {tab}: {observation.message}"
    snapshot = observation.snapshot
    assert snapshot["viewTextLength"] > 100, f"the {tab} tab rendered an empty view"
    assert any(t["tab"] == tab and t["active"] for t in snapshot["tabs"]), (
        f"clicking {tab} did not make it the active tab"
    )
    # A screen with nothing to click is a dead end; every tab offers something.
    assert snapshot["controls"], f"the {tab} tab has no interactive control"


@pytest.mark.parametrize("tab", TABS)
def test_no_tab_raises_a_javascript_error(session: PlaytestSession, tab: str):
    observation = session.open_tab(tab)
    fatal = [e for e in observation.errors if e["kind"] in ("pageerror", "netfail")]
    assert not fatal, f"the {tab} tab produced {fatal}"


def test_the_digest_describes_the_screen_it_was_taken_from(session: PlaytestSession):
    observation = session.open_tab("club")
    digest = render_digest(observation.snapshot, screenshot=observation.screenshot)
    assert "SCREEN:" in digest
    assert "CONTEXT:" in digest
    assert "[CLUB]" in digest
    assert observation.screenshot in digest


def test_every_step_leaves_a_screenshot_on_disk(session: PlaytestSession):
    observation = session.open_tab("dashboard")
    shot = Path(observation.screenshot)
    assert shot.exists(), "the harness reported a screenshot it did not write"
    assert shot.stat().st_size > 5_000, "the screenshot is too small to be a rendered page"


def test_a_player_profile_opens_off_a_name(session: PlaytestSession):
    squad = session.open_tab("club")
    players = [link for link in squad.snapshot["links"] if link["kind"] == "player"]
    assert players, "no player name on the squad screen carries a profile hook"
    profile = session.open_profile(players[0]["ref"])
    assert profile.ok, profile.message
    assert profile.snapshot["overlays"], "clicking a player opened no profile overlay"
    # Whatever markup the overlay uses, the digest must not report it as empty.
    assert len(render_digest(profile.snapshot)) > 200
    session.close_overlay()


def test_an_open_overlay_blocks_advancing_and_the_harness_says_so(session: PlaytestSession):
    squad = session.open_tab("club")
    players = [link for link in squad.snapshot["links"] if link["kind"] == "player"]
    session.open_profile(players[0]["ref"])
    blocked = session.advance_week()
    assert not blocked.ok
    assert "overlay" in blocked.message
    assert session.close_overlay().ok


def test_unknown_targets_fail_loudly_rather_than_silently(session: PlaytestSession):
    # A harness that shrugs at a bad instruction teaches an agent to trust
    # actions that never happened.
    assert not session.open_tab("nonexistent").ok
    assert not session.click("no such button anywhere").ok
    assert not session.open_profile("player_that_does_not_exist").ok
    assert not session.set_field("#definitely-not-here", "x").ok


def test_zz_advancing_a_week_moves_the_campaign(session: PlaytestSession):
    """Ordered last: it mutates the shared campaign the other tests read."""
    session.open_tab("dashboard")
    before = session.snapshot()["context"]
    observation = session.advance_week()
    assert observation.ok, f"advance failed: {observation.message}"
    assert observation.snapshot["context"] != before, (
        f"the week did not move: still {before!r}"
    )
