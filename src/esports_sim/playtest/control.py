"""The control plane: one live browser, many short commands.

An agent cannot hold a browser open between tool calls — each shell command is
its own process. So the session lives in a daemon and the agent talks to it
over localhost HTTP, one command per call. Sessions survive between commands;
the agent does not have to.

The server is deliberately single-threaded (``HTTPServer``, not the threading
variant). Playwright's sync API belongs to the thread that created it, and
serialising commands is correct anyway: there is one browser, so two
overlapping clicks would be a race, not concurrency.

Responses are plain text — the digest an agent reads — with the structured
form available at ``/state`` for anything that wants JSON.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from esports_sim.playtest.findings import Finding, append_finding, load_findings, render_report
from esports_sim.playtest.session import GameServer, Observation, PlaytestSession

# name -> (handler, help text). Registered below so `/help` and the CLI's
# usage text cannot drift from what the daemon actually accepts.
Command = Callable[["ControlState", dict[str, Any]], str]


class ControlState:
    """Everything one daemon owns: the game, the browser, and the ledger."""

    def __init__(
        self,
        session: PlaytestSession,
        *,
        run_dir: Path,
        persona: str = "unknown",
        game: GameServer | None = None,
    ) -> None:
        self.session = session
        self.run_dir = Path(run_dir)
        self.persona = persona
        self.game = game
        self.journal_path = self.run_dir / "journal.jsonl"
        self.findings_path = self.run_dir / "findings.jsonl"
        self.last: Observation | None = None
        self.should_stop = threading.Event()

    def record(self, observation: Observation) -> str:
        self.last = observation
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(observation.to_dict(), sort_keys=True, default=str) + "\n")
        return observation.as_text()

    @property
    def week(self) -> int:
        """Best-effort in-game week, for stamping findings."""
        context = (self.last.snapshot.get("context") if self.last else "") or ""
        for token in context.replace("·", " ").split():
            if token.lower().startswith("w") and token[1:].isdigit():
                return int(token[1:])
        return 0


def _cmd_look(state: ControlState, _: dict[str, Any]) -> str:
    return state.record(state.session.observe("look"))


def _cmd_new(state: ControlState, params: dict[str, Any]) -> str:
    return state.record(
        state.session.new_campaign(
            seed=int(params.get("seed", 2026)), team_index=int(params.get("team_index", 0))
        )
    )


def _cmd_tab(state: ControlState, params: dict[str, Any]) -> str:
    return state.record(state.session.open_tab(str(params.get("tab", ""))))


def _cmd_subtab(state: ControlState, params: dict[str, Any]) -> str:
    return state.record(state.session.open_subtab(str(params.get("label", ""))))


def _cmd_click(state: ControlState, params: dict[str, Any]) -> str:
    return state.record(
        state.session.click(str(params.get("label", "")), nth=int(params.get("nth", 0)))
    )


def _cmd_set(state: ControlState, params: dict[str, Any]) -> str:
    return state.record(
        state.session.set_field(str(params.get("selector", "")), str(params.get("value", "")))
    )


def _cmd_profile(state: ControlState, params: dict[str, Any]) -> str:
    return state.record(state.session.open_profile(str(params.get("ref", ""))))


def _cmd_close(state: ControlState, _: dict[str, Any]) -> str:
    return state.record(state.session.close_overlay())


def _cmd_advance(state: ControlState, params: dict[str, Any]) -> str:
    weeks = max(1, int(params.get("weeks", 1)))
    out: list[str] = []
    for _ in range(weeks):
        out.append(state.record(state.session.advance_week()))
    return "\n\n".join(out)


def _cmd_api(state: ControlState, params: dict[str, Any]) -> str:
    result = state.session.read_api(str(params.get("path", "/api/state")))
    body = str(result.get("body", ""))
    limit = int(params.get("limit", 4000))
    if len(body) > limit:
        body = body[:limit] + f"\n… (+{len(body) - limit} bytes)"
    return f"HTTP {result.get('status')}\n{body}"


def _cmd_note(state: ControlState, params: dict[str, Any]) -> str:
    """File a finding. This is the output of a playtest, so it validates hard."""
    finding = Finding(
        severity=str(params.get("severity", "")),
        area=str(params.get("area", "")),
        title=str(params.get("title", "")),
        detail=str(params.get("detail", "")),
        persona=str(params.get("persona") or state.persona),
        screen=str(params.get("screen") or (state.last.action if state.last else "")),
        screenshot=str(params.get("screenshot") or (state.last.screenshot if state.last else "")),
        repro=str(params.get("repro", "")),
        week=int(params.get("week", state.week)),
        tags=tuple(params.get("tags") or ()),
    )
    append_finding(state.findings_path, finding)
    total = len(load_findings(state.findings_path))
    return f"recorded [{finding.severity}/{finding.area}] {finding.title} ({total} findings so far)"


def _cmd_findings(state: ControlState, _: dict[str, Any]) -> str:
    findings = load_findings(state.findings_path)
    if not findings:
        return "no findings recorded yet"
    return render_report(findings, title=f"Findings so far — {state.persona}")


def _cmd_errors(state: ControlState, _: dict[str, Any]) -> str:
    errors = state.session.errors
    if not errors:
        return "no console/network errors captured"
    return "\n".join(f"[{e['kind']}] step {e.get('step')}: {e['text']}" for e in errors)


def _cmd_stop(state: ControlState, _: dict[str, Any]) -> str:
    state.should_stop.set()
    return "stopping"


COMMANDS: dict[str, tuple[Command, str]] = {
    "look": (_cmd_look, "re-observe the current screen"),
    "new": (_cmd_new, "start a new campaign (seed, team_index)"),
    "tab": (_cmd_tab, "open a top-level tab (tab=dashboard|inbox|tactics|club|…)"),
    "subtab": (_cmd_subtab, "open a sub-tab by visible label (label=…)"),
    "click": (_cmd_click, "click a control by label/id (label=…, nth=0)"),
    "set": (_cmd_set, "set an input/select (selector=#id, value=…)"),
    "profile": (_cmd_profile, "open a player/team/staff profile (ref=…)"),
    "close": (_cmd_close, "dismiss the topmost overlay"),
    "advance": (_cmd_advance, "advance the week (weeks=1)"),
    "api": (_cmd_api, "read a JSON endpoint for cross-checking (path=/api/state)"),
    "note": (_cmd_note, "file a finding (severity, area, title, detail, repro?)"),
    "findings": (_cmd_findings, "show the findings filed so far"),
    "errors": (_cmd_errors, "show every console/network error captured this run"),
    "stop": (_cmd_stop, "shut the session down"),
}


def _help_text() -> str:
    width = max(len(name) for name in COMMANDS)
    lines = ["commands:"]
    lines.extend(f"  {name.ljust(width)}  {help_}" for name, (_, help_) in sorted(COMMANDS.items()))
    return "\n".join(lines)


class _Handler(BaseHTTPRequestHandler):
    state: ControlState  # injected by serve()

    # BaseHTTPRequestHandler logs every request to stderr; the daemon's stderr
    # is the run log, and one line per click drowns the real output.
    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def _reply(self, body: str, status: int = 200) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = urlparse(self.path).path
        if path in ("/", "/help"):
            self._reply(_help_text())
        elif path == "/ping":
            self._reply("ok")
        elif path == "/state":
            last = self.state.last
            self._reply(json.dumps(last.to_dict() if last else {}, default=str, indent=1))
        else:
            self._reply(f"unknown path {path}", status=404)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            params = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            self._reply(f"bad JSON body: {exc}", status=400)
            return
        name = urlparse(self.path).path.strip("/")
        entry = COMMANDS.get(name)
        if entry is None:
            self._reply(f"unknown command {name!r}\n\n{_help_text()}", status=404)
            return
        try:
            self._reply(entry[0](self.state, params))
        except Exception as exc:  # noqa: BLE001 - a bad command must not kill the daemon
            self._reply(f"command {name!r} failed: {type(exc).__name__}: {exc}", status=500)


def serve(state: ControlState, port: int) -> None:
    """Run the control plane until a `stop` command arrives."""
    handler = type("_BoundHandler", (_Handler,), {"state": state})
    server = HTTPServer(("127.0.0.1", port), handler)
    server.timeout = 1.0
    while not state.should_stop.is_set():
        server.handle_request()
    server.server_close()
