"""A synthetic player's body: a real browser pointed at the real game.

Everything here goes through the shipped UI on purpose. Driving the API
directly would be faster and steadier, but it would test a surface no human
uses and would miss the entire class of bug this harness exists to find — a
button that does not exist, a number that never repaints, a modal that eats
the click. If the synthetic player cannot get there by clicking, neither can
a person.

Two rules hold the harness together:

* **Every action returns an observation.** Act-then-look is one call, so an
  agent physically cannot report on a screen it did not see.
* **Errors are collected continuously, not polled.** Console errors, page
  exceptions, and 4xx/5xx responses accumulate from page load, so a failure
  that happens between two screenshots still gets attributed to the step that
  caused it.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from esports_sim.playtest.dom import (
    OPEN_OVERLAYS_SCRIPT,
    SCREEN_SCRIPT,
    VISIBLE_JS,
    render_console,
    render_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# Playwright ships a version-pinned browser download; sandboxes and CI images
# usually have a Chromium already but not that exact build. Try the pinned one
# first, fall back to whatever is on the box, and say so clearly if neither is.
_CHROMIUM_HINTS: tuple[str, ...] = (
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)

# The painted-map backdrops are probed by the viewer and legitimately 404 when
# a map has not been painted yet — see docs/art-pipeline.md. Counting those as
# findings would bury real errors under known noise.
_BENIGN_404 = ("/assets/maps/painted/",)

TABS: tuple[str, ...] = (
    "dashboard",
    "inbox",
    "tactics",
    "club",
    "facilities",
    "season",
    "market",
    "stats",
    "company",
)


def find_chromium() -> str | None:
    """Return a usable Chromium path, or None to let Playwright pick."""
    override = os.environ.get("PLAYTEST_CHROMIUM")
    if override:
        return override
    for candidate in _CHROMIUM_HINTS:
        if Path(candidate).exists():
            return candidate
    for name in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def free_port() -> int:
    """Ask the OS for a port nobody is using."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class GameServer:
    """The game's own web server, run exactly as a player would run it."""

    def __init__(self, port: int | None = None, *, saves_dir: Path | None = None) -> None:
        self.port = port or free_port()
        self.saves_dir = saves_dir
        self.proc: subprocess.Popen[bytes] | None = None
        self.log_path: Path | None = None
        self._log_handle = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    #: Seconds to wait for the server to answer. Generous on purpose: the
    #: box may be running a full test suite, and a shared CI runner can take
    #: half a minute just to import and bind. Override with
    #: $ESPORTS_SIM_BOOT_TIMEOUT when a machine needs longer still.
    BOOT_TIMEOUT = float(os.environ.get("ESPORTS_SIM_BOOT_TIMEOUT", "180"))

    def start(self, *, timeout: float | None = None, log_path: Path | None = None) -> "GameServer":
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(REPO_ROOT / "src"), env.get("PYTHONPATH", "")])
        )
        if self.saves_dir is not None:
            self.saves_dir.mkdir(parents=True, exist_ok=True)
            env["ESPORTS_SIM_SAVE_DIR"] = str(self.saves_dir)
        # A playtest must never be steered by a live LLM writing social copy:
        # it would make two runs of the same seed disagree for reasons that
        # have nothing to do with the build under test.
        env["SOCIAL_LLM"] = "off"
        # Unbuffered: the server's own stdout is the only diagnosis available
        # when a boot times out, and block-buffered output means the log file
        # is empty at exactly the moment it matters.
        env["PYTHONUNBUFFERED"] = "1"

        timeout = self.BOOT_TIMEOUT if timeout is None else timeout
        self.log_path = log_path
        # Kept on the instance so stop() can close it. A leaked file object is
        # collected non-deterministically, which surfaces as an unraisable
        # ResourceWarning in whichever test happens to be running at the time.
        self._log_handle = log_path.open("wb") if log_path is not None else None
        stdout = self._log_handle if self._log_handle is not None else subprocess.DEVNULL
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable, "-m", "esports_sim", "--web",
                "--port", str(self.port), "--no-browser", "--host", "127.0.0.1",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=stdout,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        # Two phases, because "listening" and "ready" are different states and
        # conflating them is what made this loop livelock.
        #
        # Phase 1 polls a static file: uvicorn binds its socket almost at once,
        # so this only proves the process is up and serving.
        #
        # Phase 2 asks the API exactly once, with a long patience. /api/lobby
        # builds a whole preview world on its first call and can take the best
        # part of a minute on a loaded box. Polling it on a short per-request
        # timeout meant every probe abandoned its own request and started a
        # fresh one, so the server re-did the expensive work continuously and
        # the client never saw an answer -- a boot that finishes in 50s failed
        # a 180s deadline. Ask once and wait.
        while time.monotonic() < deadline:
            self._raise_if_dead(log_path)
            try:
                with urlopen(f"{self.url}/", timeout=5):  # noqa: S310 - localhost
                    break
            except (URLError, OSError, TimeoutError):
                time.sleep(0.4)
        else:
            self.stop()
            raise TimeoutError(f"game server never started serving within {timeout}s")

        self._raise_if_dead(log_path)
        remaining = max(5.0, deadline - time.monotonic())
        try:
            with urlopen(f"{self.url}/api/lobby", timeout=remaining):  # noqa: S310 - localhost
                return self
        except (URLError, OSError, TimeoutError) as exc:
            self._raise_if_dead(log_path)
            self.stop()
            raise TimeoutError(
                f"game server served static files but /api/lobby did not answer "
                f"within {timeout}s ({type(exc).__name__}: {exc})"
            ) from exc

    def _raise_if_dead(self, log_path: Path | None) -> None:
        """Fail with the server's own output rather than a bare timeout."""
        if self.proc is None or self.proc.poll() is None:
            return
        returncode = self.proc.returncode
        tail = ""
        if log_path is not None and log_path.exists():
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        self.stop()
        raise RuntimeError(f"game server exited early (code {returncode})\n{tail}")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
            self.proc = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def __enter__(self) -> "GameServer":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()


@dataclass
class Observation:
    """What one step of play produced: the picture, the text, and the damage."""

    step: int
    action: str
    ok: bool
    message: str
    snapshot: dict[str, Any]
    screenshot: str = ""
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_text(self) -> str:
        parts = [f"STEP {self.step}: {self.action} -> {'ok' if self.ok else 'FAILED'}"]
        if self.message:
            parts.append(self.message)
        parts.append("")
        parts.append(render_digest(self.snapshot, screenshot=self.screenshot or None))
        console = render_console(self.errors)
        if console:
            parts.append("")
            parts.append(console)
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "ok": self.ok,
            "message": self.message,
            "screenshot": self.screenshot,
            "errors": self.errors,
            "snapshot": self.snapshot,
        }


class PlaytestSession:
    """One synthetic player's live browser, bound to one running game."""

    def __init__(
        self,
        *,
        run_dir: Path,
        base_url: str,
        headless: bool = True,
        width: int = 1600,
        height: int = 950,
        chromium: str | None = None,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.shots_dir = self.run_dir / "screens"
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.width = width
        self.height = height
        self.chromium = chromium if chromium is not None else find_chromium()
        self.step = 0
        self._errors: list[dict[str, Any]] = []
        self._playwright = None
        self._browser = None
        self._page = None

    # ── lifecycle ───────────────────────────────────────────────────────

    def start(self) -> "PlaytestSession":
        from playwright.sync_api import sync_playwright

        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        launch: dict[str, Any] = {
            "headless": self.headless,
            # Containers run as root without a user namespace; without this
            # Chromium refuses to start and the failure looks like a hang.
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if self.chromium:
            launch["executable_path"] = self.chromium
        self._browser = self._playwright.chromium.launch(**launch)
        self._page = self._browser.new_page(
            viewport={"width": self.width, "height": self.height}
        )
        page = self._page
        page.on("pageerror", lambda exc: self._note("pageerror", str(exc)))
        page.on(
            "console",
            lambda msg: self._note("console", msg.text) if msg.type == "error" else None,
        )
        page.on(
            "response",
            lambda res: self._note("http", f"{res.status} {res.url}")
            if res.status >= 400 and not any(part in res.url for part in _BENIGN_404)
            else None,
        )
        page.on("requestfailed", lambda req: self._note("netfail", f"{req.url} {req.failure}"))
        page.goto(self.base_url + "/", wait_until="domcontentloaded")
        self._settle()
        return self

    def close(self) -> None:
        # Teardown must never mask the failure that got us here, so both
        # halves are best-effort and independent.
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # noqa: BLE001
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
        self._browser = None
        self._playwright = None
        self._page = None

    def __enter__(self) -> "PlaytestSession":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── internals ───────────────────────────────────────────────────────

    def _note(self, kind: str, text: str) -> None:
        self._errors.append({"kind": kind, "text": text, "step": self.step})

    @property
    def page(self):  # noqa: ANN201 - Playwright type, not imported at module scope
        if self._page is None:
            raise RuntimeError("session is not started; call start() first")
        return self._page

    def _settle(self, ms: int = 700) -> None:
        """Let the app finish its fetch-and-render cycle before we look."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:  # noqa: BLE001 - a busy poll loop never goes idle; not fatal
            pass
        self.page.wait_for_timeout(ms)

    def snapshot(self) -> dict[str, Any]:
        return self.page.evaluate(SCREEN_SCRIPT)

    def _shoot(self, label: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:40]
        path = self.shots_dir / f"{self.step:03d}_{safe}.png"
        self.page.screenshot(path=str(path))
        return str(path)

    def observe(self, action: str, *, ok: bool = True, message: str = "") -> Observation:
        """Look at the screen and package it as one observation.

        Only errors raised *by this step* are attached. Re-attaching the whole
        buffer would make one early error look like it happened on every screen
        afterwards, which is exactly the kind of false report that makes an
        agent's findings worthless.
        """
        self.step += 1
        errors_before = len(self._errors)
        self._settle()
        snapshot = self.snapshot()
        shot = self._shoot(action)
        return Observation(
            step=self.step,
            action=action,
            ok=ok,
            message=message,
            snapshot=snapshot,
            screenshot=shot,
            errors=self._errors[errors_before:],
        )

    def drain_errors(self) -> list[dict[str, Any]]:
        """Return every error seen so far and reset the buffer."""
        errors, self._errors = list(self._errors), []
        return errors

    @property
    def errors(self) -> list[dict[str, Any]]:
        return list(self._errors)

    # ── actions ─────────────────────────────────────────────────────────

    def new_campaign(self, *, seed: int = 2026, team_index: int = 0) -> Observation:
        """Start a fresh solo campaign from the lobby, as a player would.

        Typing a seed makes the lobby refetch its team list, which detaches the
        buttons that were on screen a moment ago — clicking a stale handle is a
        silent no-op. So: set the seed, let the list settle, click by locator,
        and then *confirm the lobby actually closed* before claiming success.
        """
        page = self.page
        in_lobby = page.evaluate(
            "() => !document.getElementById('newgame')?.classList.contains('hidden')"
        )
        if not in_lobby:
            return self.observe("new_campaign", ok=False, message="lobby is not open")
        page.click("#mode-solo")
        page.wait_for_selector("#ng-seed", timeout=10_000)
        page.fill("#ng-seed", str(seed))

        # Editing the seed makes the lobby refetch and rebuild the whole team
        # grid, because a fictional league is *generated* from the seed. Until
        # that lands, the cards on screen belong to the previous seed's league
        # and picking one is meaningless. Wait for the grid to hold still.
        deadline = time.monotonic() + 60
        stable = 0
        last = -1
        while time.monotonic() < deadline and stable < 2:
            state = page.evaluate(
                """() => {
                  const grid = document.getElementById('ng-teams');
                  if (!grid) return { count: -1, loading: true };
                  const text = (grid.innerText || '');
                  return {
                    count: grid.querySelectorAll('button.team-pick:not([disabled])').length,
                    loading: /Preparing league|Loading|Could not load/i.test(text),
                  };
                }"""
            )
            stable = stable + 1 if (state["count"] == last and state["count"] > 0
                                    and not state["loading"]) else 0
            last = state["count"]
            page.wait_for_timeout(400)
        if last <= 0:
            return self.observe(
                "new_campaign", ok=False,
                message="the lobby never produced a selectable team for that seed",
            )

        # Click the live node rather than a screen position: the grid can
        # re-render underneath a mouse click, and a click that lands on a stale
        # card starts a campaign in a league that no longer exists.
        clicked = page.evaluate(
            """(index) => {
              const grid = document.getElementById('ng-teams');
              const picks = [...grid.querySelectorAll('button.team-pick:not([disabled])')];
              if (!picks.length) return '';
              const node = picks[Math.min(index, picks.length - 1)];
              node.click();
              return (node.innerText || '').split('\\n')[0].trim();
            }""",
            team_index,
        )
        if not clicked:
            return self.observe("new_campaign", ok=False, message="no selectable team in the lobby")

        # The lobby closing is the only honest signal the campaign exists.
        deadline = time.monotonic() + 60
        started = False
        while time.monotonic() < deadline:
            started = page.evaluate(
                "() => document.getElementById('newgame')?.classList.contains('hidden') === true"
            )
            if started:
                break
            page.wait_for_timeout(500)
        if not started:
            return self.observe(
                f"new_campaign(seed={seed})", ok=False,
                message=(
                    f"clicked {clicked!r} but the lobby never closed — no campaign was created"
                ),
            )
        page.wait_for_timeout(1200)
        return self.observe(f"new_campaign(seed={seed})", message=f"picked {clicked}")

    def open_tab(self, tab: str) -> Observation:
        if tab not in TABS:
            return self.observe(
                f"tab({tab})", ok=False, message=f"unknown tab; expected one of {', '.join(TABS)}"
            )
        try:
            self.page.click(f'nav#tabs [data-tab="{tab}"]', timeout=8000)
        except Exception as exc:  # noqa: BLE001 - surfaced to the agent, not raised
            return self.observe(f"tab({tab})", ok=False, message=f"could not click tab: {exc}")
        return self.observe(f"tab({tab})")

    def open_subtab(self, label: str) -> Observation:
        """Click a sub-tab (the segmented control) by visible label.

        Searches the same root the digest reports from — the topmost overlay if
        one is open, else the main view — so anything the agent can *see* listed
        as a sub-tab is something it can click.
        """
        script = """
        (want) => {
        """ + VISIBLE_JS + """
          const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const overlays = [...document.querySelectorAll('.overlay')].filter(vis);
          const root = overlays.length
            ? overlays[overlays.length - 1]
            : (document.getElementById('view') || document.body);
          for (const b of root.querySelectorAll('.seg .seg-btn, .seg button')) {
            if (!vis(b)) continue;
            if (norm(b.innerText).includes(norm(want))) { b.click(); return norm(b.innerText); }
          }
          return '';
        }
        """
        hit = self.page.evaluate(script, label)
        if not hit:
            return self.observe(f"subtab({label})", ok=False, message="no sub-tab matched that label")
        return self.observe(f"subtab({label})")

    def click(self, label: str, *, nth: int = 0) -> Observation:
        """Click a visible control by its label, id, or text — as a player would.

        Matching is deliberately forgiving (case-insensitive substring across
        label/aria-label/id) because an agent reading a screenshot types what
        it *saw*, not the exact DOM string.
        """
        script = """
        ([want, nth]) => {
        """ + VISIBLE_JS + """
          const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const target = norm(want);
          const overlays = [...document.querySelectorAll('.overlay')].filter(vis);
          const root = overlays.length ? overlays[overlays.length - 1] : document.body;
          const nodes = [...root.querySelectorAll('button, a[href], [role=button], .seg-btn, .tab')]
            .filter(vis)
            .filter((n) => {
              const text = norm(n.innerText) || norm(n.getAttribute('aria-label'));
              return text.includes(target) || norm(n.id) === target || norm(n.id).includes(target);
            });
          if (!nodes.length) return { ok: false, reason: 'no visible control matched', count: 0 };
          const pick = nodes[Math.min(nth, nodes.length - 1)];
          if (pick.disabled || pick.getAttribute('aria-disabled') === 'true') {
            return { ok: false, reason: 'matched control is disabled', count: nodes.length,
                     label: (pick.innerText || '').trim().slice(0, 60) };
          }
          pick.click();
          return { ok: true, count: nodes.length, label: (pick.innerText || '').trim().slice(0, 60) };
        }
        """
        result = self.page.evaluate(script, [label, nth])
        if not result.get("ok"):
            return self.observe(
                f"click({label})", ok=False,
                message=f"{result.get('reason', 'click failed')} (matches: {result.get('count', 0)})",
            )
        matched = result.get("label") or label
        extra = f"; {result['count']} matched, used #{nth}" if result.get("count", 1) > 1 else ""
        return self.observe(f"click({label})", message=f"clicked {matched!r}{extra}")

    def set_field(self, selector: str, value: str) -> Observation:
        """Set an input/select by CSS selector (ids come from the digest)."""
        try:
            handle = self.page.query_selector(selector)
            if handle is None:
                return self.observe(f"set({selector})", ok=False, message="selector matched nothing")
            tag = handle.evaluate("(n) => n.tagName.toLowerCase()")
            if tag == "select":
                handle.select_option(value)
            else:
                handle.fill(value)
            handle.evaluate("(n) => { n.dispatchEvent(new Event('change', {bubbles: true})); }")
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            return self.observe(f"set({selector})", ok=False, message=str(exc))
        return self.observe(f"set({selector}={value})")

    def open_profile(self, ref: str) -> Observation:
        """Open a player/team/staff profile overlay by its data-* ref."""
        script = """
        (ref) => {
          const node = document.querySelector(
            `[data-pid="${ref}"], [data-tid="${ref}"], [data-sid="${ref}"]`);
          if (!node) return false;
          node.click();
          return true;
        }
        """
        if not self.page.evaluate(script, ref):
            return self.observe(f"profile({ref})", ok=False, message="no element carries that ref")
        return self.observe(f"profile({ref})")

    def _wait_for_overlays_to_clear(self, timeout_ms: int) -> list[str]:
        """Poll until no overlay is visible, or the budget runs out."""
        deadline = time.monotonic() + timeout_ms / 1000
        open_ids: list[str] = self.page.evaluate(OPEN_OVERLAYS_SCRIPT)
        while open_ids and time.monotonic() < deadline:
            self.page.wait_for_timeout(200)
            open_ids = self.page.evaluate(OPEN_OVERLAYS_SCRIPT)
        return open_ids

    def close_overlay(self) -> Observation:
        """Dismiss the topmost overlay — Escape first, then its close control.

        Overlays animate out, so "still visible right now" is not the same as
        "did not close". Both routes are followed by a poll; reporting a
        failure the moment after Escape would make the harness cry wolf on
        every modal in the game.
        """
        self.page.keyboard.press("Escape")
        if not self._wait_for_overlays_to_clear(1500):
            return self.observe("close_overlay")

        # Escape did not take. Fall back to the overlay's own close control,
        # matching its accessible name as well as its label — close buttons are
        # very often a bare glyph with the real name only in aria-label.
        clicked = self.page.evaluate(
            """() => {
            """ + VISIBLE_JS + """
              const open = [...document.querySelectorAll('.overlay')].filter(vis);
              if (!open.length) return 'gone';
              const top = open[open.length - 1];
              const wanted = /close|dismiss|done|cancel|back|[×✕✖⨯]/i;
              const btn = [...top.querySelectorAll('button, [role=button]')].filter(vis).find((b) => {
                const label = (b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')
                  + ' ' + (b.className || '');
                return wanted.test(label);
              });
              if (btn) { btn.click(); return 'clicked'; }
              return '';
            }"""
        )
        if clicked == "gone":
            return self.observe("close_overlay")
        still_open = self._wait_for_overlays_to_clear(2000)
        if not still_open:
            return self.observe("close_overlay")
        return self.observe(
            "close_overlay", ok=False,
            message=(
                f"{still_open} would not close — Escape did nothing and "
                f"{'its close button did not either' if clicked else 'it has no close control'}"
            ),
        )

    def _context(self) -> str:
        return self.page.evaluate(
            "() => (document.getElementById('context')?.innerText || '').trim()"
        )

    def advance_week(self, *, timeout_ms: int = 120_000) -> Observation:
        """Click Advance Week, wait out the reveal, and check the week moved.

        A week that does not advance is one of the most consequential bugs this
        harness can hit — every later observation would be attributed to the
        wrong week — so it is checked rather than assumed.
        """
        page = self.page
        before = self._context()
        open_overlays = page.evaluate(OPEN_OVERLAYS_SCRIPT)
        blocking = open_overlays[-1] if open_overlays else ""
        if blocking:
            return self.observe(
                "advance_week", ok=False,
                message=f"the {blocking!r} overlay is covering the page — close it first",
            )
        try:
            page.click("#advance-btn", timeout=8000)
        except Exception as exc:  # noqa: BLE001 - Playwright's log is a wall; keep the first line
            reason = str(exc).splitlines()[0]
            return self.observe("advance_week", ok=False, message=f"advance button unavailable: {reason}")
        # The reveal overlay is the honest completion signal: it appears while
        # the week simulates and goes away when the new week is renderable.
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            busy = page.evaluate(
                """() => {
                  const vis = (id) => {
                    const n = document.getElementById(id);
                    if (!n) return false;
                    if (n.classList.contains('hidden')) return false;
                    const r = n.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return vis('week-loading') || vis('week-reveal');
                }"""
            )
            if not busy:
                break
            page.wait_for_timeout(500)
        after = self._context()
        if before and after == before:
            return self.observe(
                "advance_week", ok=False,
                message=(
                    f"the week did not move — still {after!r}. Something is blocking the "
                    "advance (an open overlay, or a decision the game is waiting on)."
                ),
            )
        return self.observe("advance_week", message=f"{before or '?'} -> {after or '?'}")

    def read_api(self, path: str) -> dict[str, Any]:
        """Fetch a JSON endpoint through the page's own session.

        Only for *checking* what the UI was given — never for acting. A finding
        is only real if it is reachable by clicking.
        """
        return self.page.evaluate(
            "async (p) => { const r = await fetch(p); "
            "return { status: r.status, body: await r.text() }; }",
            path,
        )
