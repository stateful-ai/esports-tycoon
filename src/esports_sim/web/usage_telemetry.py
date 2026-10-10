"""Best-effort local UI usage sidecar. Never reads or writes deterministic state."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import threading
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool


class UsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["session_start", "session_end", "view", "visible_time", "attempt", "result", "replay", "interaction"]
    target: str = Field(default="", max_length=100, pattern=r"^[a-z0-9_/.-]*$")
    request_id: int | None = Field(default=None, ge=1, le=2**31-1)
    outcome: Literal["success", "http_error", "transport_error", "rejected"] | None = None
    status: int | None = Field(default=None, ge=100, le=599)
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class UsageBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    page_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    events: list[UsageEvent] = Field(min_length=1, max_length=32)


VIEWS = {"replay", "lobby", "draft", "dashboard", "inbox", "club", "roster", "tactics",
         "facilities", "season", "market", "stats", "company"}
SUBTABS = {"overview", "squad", "development", "locker_room", "operations", "strategy", "prep",
           "gameplan", "league", "fixtures", "playoffs", "records", "players", "scouting", "staff",
           "leaders", "races", "meta", "history", "teams", "agents", "maps", "finances", "brand"}
REPLAY = {"open", "close", "play", "pause", "seek", "round", "speed_1", "speed_4", "speed_16", "speed_inst"}
# Coarse control use only: never values, labels, selectors, or report contents.
# Overlay inspections count successful visible content, not attempted fetches.
PROFILE_INTERACTIONS = {f"profile/{kind}_{action}"
                        for kind in ("player", "team", "staff", "manager")
                        for action in ("open", "close")}
HANDBOOK_INTERACTIONS = {"handbook/open", "handbook/close", "handbook/section_first_week",
                         "handbook/section_screens", "handbook/section_glossary"}
INTERACTIONS = {"lobby/seed_change", "week/full_report_open"} | PROFILE_INTERACTIONS | HANDBOOK_INTERACTIONS


def validate_events(batch: UsageBatch, endpoints: set[str]) -> None:
    for event in batch.events:
        if event.kind in {"view", "visible_time"}:
            parts = event.target.split("/")
            valid = parts[0] in VIEWS and len(parts) <= 2 and (len(parts) == 1 or parts[1] in SUBTABS)
        elif event.kind == "replay":
            valid = event.target in REPLAY
        elif event.kind == "interaction":
            valid = event.target in INTERACTIONS
        elif event.kind in {"attempt", "result"}:
            valid = event.target in endpoints and event.request_id is not None
        else:
            valid = event.target == ""
        if not valid or (event.kind == "result" and event.outcome is None):
            raise HTTPException(422, "invalid usage event")
        if event.kind != "result" and (event.outcome is not None or event.status is not None):
            raise HTTPException(422, "invalid usage fields")
        if event.kind not in {"attempt", "result"} and event.request_id is not None:
            raise HTTPException(422, "invalid usage fields")
        if event.kind not in {"visible_time", "result"} and event.duration_ms is not None:
            raise HTTPException(422, "invalid usage fields")
        if event.kind == "visible_time" and (event.duration_ms is None or event.duration_ms > 60_000):
            raise HTTPException(422, "invalid visible-time slice")


class UsageStore:
    """Four bounded JSONL segments; process-local lock serializes writes/rotation."""
    def __init__(self, directory: Path, max_bytes: int = 2 * 1024 * 1024):
        self.directory = directory
        self.max_bytes = max_bytes
        self.lock = threading.Lock()

    def paths(self):
        return [self.directory / f"usage.{n}.jsonl" for n in range(4)]

    def append(self, batch: UsageBatch, context: dict) -> bool:
        try:
            # The cookie is hashed and never emitted; page ids grant no authority.
            session_id = sha256((context["sid"] + ":" + batch.page_id).encode()).hexdigest()[:32]
            linkage = {k: context.get(k) for k in ("world", "team", "season", "week")}
            now = datetime.now(timezone.utc).isoformat()
            rows = [{"schema_version": 1, "session_id": session_id, "received_at": now,
                     **linkage, **e.model_dump(exclude_none=True)} for e in batch.events]
            payload = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
            if len(payload.encode()) > self.max_bytes:
                return False
            with self.lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                paths = self.paths()
                if paths[0].exists() and paths[0].stat().st_size + len(payload.encode()) > self.max_bytes:
                    paths[-1].unlink(missing_ok=True)
                    for n in range(2, -1, -1):
                        if paths[n].exists():
                            paths[n].replace(paths[n+1])
                with paths[0].open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(payload)
            return True
        except (OSError, ValueError, KeyError):
            return False

    def report(self) -> dict:
        counts, visible, outcomes, worlds = Counter(), Counter(), Counter(), Counter()
        attempts, results, sessions = set(), set(), set()
        spans = {}
        malformed = 0
        with self.lock:
            for path in reversed(self.paths()):
                if not path.exists():
                    continue
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            row = json.loads(line)
                            sid, kind, target = row["session_id"], row["kind"], row["target"]
                            received = datetime.fromisoformat(row["received_at"])
                            first, last = spans.get(sid, (received, received))
                            spans[sid] = (min(first, received), max(last, received))
                            sessions.add(sid)
                            worlds[row.get("world") or "lobby"] += 1
                            counts[f"{kind}:{target}"] += 1
                            if kind == "visible_time":
                                visible[target] += row.get("duration_ms", 0)
                            if kind in {"attempt", "result"}:
                                key = (sid, row["request_id"], target)
                                (attempts if kind == "attempt" else results).add(key)
                            if kind == "result":
                                outcomes[f"{target}:{row['outcome']}"] += 1
                        except (ValueError, KeyError, TypeError):
                            malformed += 1
        return {"sessions": len(sessions), "events": dict(sorted(counts.items())),
                "visible_ms": dict(sorted(visible.items())), "outcomes": dict(sorted(outcomes.items())),
                "attempts": len(attempts), "paired_results": len(attempts & results),
                "unmatched_attempts": len(attempts-results), "orphan_results": len(results-attempts),
                "world_events": dict(sorted(worlds.items())),
                "observed_session_span_ms": {sid: round((last-first).total_seconds()*1000)
                                             for sid, (first, last) in sorted(spans.items())},
                "malformed_lines": malformed, "retention_bytes": 4*self.max_bytes}


def install_usage_routes(app, directory: Path, context, require_local_admin) -> None:
    """Register before the static mount; context resolves the actual request seat."""
    store = UsageStore(directory / "usage")

    def endpoints():
        # Same buckets as the browser: actions keep their verb; dynamic ids never leave it.
        return {"/".join(r.path.split("/")[:4 if r.path.startswith("/api/actions/") else 3])
                for r in app.routes if hasattr(r, "path") and r.path.startswith("/api/")
                and not r.path.startswith("/api/usage")}

    @app.post("/api/usage/events")
    async def ingest(request: Request):
        size, chunks = 0, []
        async for chunk in request.stream():
            size += len(chunk)
            if size > 16_384:
                raise HTTPException(413, "usage payload too large")
            chunks.append(chunk)
        try:
            batch = UsageBatch.model_validate_json(b"".join(chunks))
        except ValidationError:
            raise HTTPException(422, "invalid usage payload") from None
        validate_events(batch, endpoints())
        resolved_context = context()
        accepted = await run_in_threadpool(store.append, batch, resolved_context)
        return {"accepted": accepted}

    @app.get("/api/usage/report")
    def report():
        require_local_admin()
        try:
            return store.report()
        except OSError:
            return {"available": False}
