"""The week-advance controls must refuse a week without crashing the page.

A synthetic player found both halves of this. Advancing with a decision still
pending is a *normal* answer -- the server returns 409 and the UI toasts why --
but the two handlers wrapped their `await api(...)` in `try/finally` with no
`catch`. `api()` toasts the detail and then rethrows, so the rejection escaped
an async click handler and surfaced as an uncaught pageerror. To a player,
"you have one thing left to do" looked like the game had crashed.

The same finding caught the message those 409s carry. They sent players to a
screen called "Action required", which `app.js` deleted -- its own comment says
so ("The old ws-12 'Action required' band is gone"). The prompts live in
"Needs You" on the Dashboard now.

These are file reads, so they run in every CI lane rather than only where a
browser exists. The browser lane proves the click path; this proves the two
shapes that made it fail cannot come back unnoticed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src/esports_sim/web/static/app.js"
SERVER = ROOT / "src/esports_sim/web/server.py"
SIM_AHEAD = ROOT / "src/esports_sim/manager/sim_ahead.py"

# The two controls that can be refused mid-flight by a 409.
HANDLERS = ("#advance-btn", "#simahead-btn")


def _handler_body(source: str, selector: str) -> str:
    """The onclick body for *selector*, from its `$("<sel>").onclick` to the
    `};` that closes it."""
    start = source.index(f'$("{selector}").onclick')
    end = source.index("\n};", start)
    return source[start:end]


@pytest.mark.web
@pytest.mark.parametrize("selector", HANDLERS)
def test_the_advance_controls_catch_a_refusal(selector: str) -> None:
    body = _handler_body(APP_JS.read_text(encoding="utf-8"), selector)
    assert "await api(" in body, f"{selector} no longer calls api() — retarget this test"
    assert re.search(r"\}\s*catch\s*(\{|\()", body), (
        f"{selector} awaits api() with no catch. api() rethrows after toasting, "
        "so a 409 (a decision still pending) becomes an unhandled rejection and "
        "a pageerror — the browser lane fails on exactly that signal."
    )


@pytest.mark.web
def test_no_advance_guard_points_at_a_screen_that_was_deleted() -> None:
    """'Action required' was removed from the UI; nothing may still name it."""
    for path in (SERVER, SIM_AHEAD):
        text = path.read_text(encoding="utf-8")
        assert "Action required" not in text, (
            f"{path.name} sends players to 'Action required', which app.js no "
            "longer renders. These prompts live in 'Needs You' on the Dashboard."
        )


@pytest.mark.web
def test_the_advance_guards_name_a_screen_the_player_can_find() -> None:
    """Every 'before advancing' refusal must route somewhere real."""
    text = SERVER.read_text(encoding="utf-8")
    guards = [line.strip() for line in text.splitlines() if "before advancing" in line]
    assert guards, "the advance guards moved — retarget this test"
    for guard in guards:
        assert "Needs You" in guard, f"advance guard names no reachable screen: {guard}"


@pytest.mark.web
def test_the_guards_avoid_developer_vocabulary() -> None:
    """'flavor event' is an internal name for what a player sees as a decision."""
    text = SERVER.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "before advancing" in line:
            assert "flavor" not in line.lower(), (
                f"player-facing guard uses the internal term 'flavor': {line.strip()}"
            )
