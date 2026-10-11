from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
import asyncio
import httpx


class Client:
    def __init__(self, app):
        self.app = app

    def request(self, method, url, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(send())

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def get(self, url):
        return self.request("GET", url)

from esports_sim.web.usage_telemetry import UsageBatch, UsageStore, install_usage_routes

pytestmark = pytest.mark.web
PAGE = "a" * 32


def payload(*events):
    return {"page_id": PAGE, "events": list(events)}


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    @app.post("/api/actions/train")
    def train():
        return {"ok": True}
    def context():
        return {"sid": "secret-cookie", "world": "TEST", "team": "team_test", "season": 1, "week": 2}
    install_usage_routes(app, tmp_path, context, lambda: None)
    return Client(app)


def test_linkage_is_server_owned_and_session_is_not_cookie(client, tmp_path):
    assert client.post("/api/usage/events", json=payload({"kind": "view", "target": "club/development"})).json() == {"accepted": True}
    text = (tmp_path / "usage/usage.0.jsonl").read_text()
    assert "secret-cookie" not in text
    import json
    row = json.loads(text)
    assert (row["world"], row["team"], row["week"]) == ("TEST", "team_test", 2)
    assert row["received_at"] and len(row["session_id"]) == 32
    assert client.post("/api/usage/events", json={**payload({"kind": "session_start"}), "world": "OTHER"}).status_code == 422


@pytest.mark.parametrize("event", [
    {"kind": "view", "target": "secret-text"},
    {"kind": "replay", "target": "fixture-secret"},
    {"kind": "attempt", "target": "/api/actions/train?key=secret", "request_id": 1},
    {"kind": "attempt", "target": "/api/actions/unknown", "request_id": 1},
    {"kind": "attempt", "target": "/api/actions/train"},
    {"kind": "result", "target": "/api/actions/train", "request_id": 1},
    {"kind": "view", "target": "club", "body": "secret"},
    {"kind": "visible_time", "target": "club", "duration_ms": -1},
])
def test_rejects_unbounded_or_unknown_capture(client, event):
    assert client.post("/api/usage/events", json=payload(event)).status_code == 422


def test_bounded_payload(client):
    assert client.post("/api/usage/events", content=b" " * 16385).status_code == 413
    assert client.post("/api/usage/events", json=payload(*[{"kind": "session_start"}] * 33)).status_code == 422


def test_control_interactions_are_counts_only(client):
    events = [{"kind": "interaction", "target": target} for target in
              ("lobby/seed_change", "week/full_report_open", "week/full_report_open")]
    assert client.post("/api/usage/events", json=payload(*events)).json()["accepted"]
    report = client.get("/api/usage/report").json()
    assert report["events"] == {"interaction:lobby/seed_change": 1,
                                "interaction:week/full_report_open": 2}
    assert report["attempts"] == report["paired_results"] == 0
    assert report["visible_ms"] == report["outcomes"] == {}


@pytest.mark.parametrize("event", [
    {"kind": "interaction", "target": "lobby/seed_change/2039"},
    {"kind": "interaction", "target": "week/report_text"},
    {"kind": "interaction", "target": "lobby/seed_change", "seed": 2039},
    {"kind": "interaction", "target": "week/full_report_open", "label": "secret"},
    {"kind": "interaction", "target": "lobby/seed_change", "request_id": 1},
    {"kind": "interaction", "target": "week/full_report_open", "duration_ms": 10},
    {"kind": "interaction", "target": "week/full_report_open", "outcome": "success"},
    {"kind": "interaction", "target": "week/full_report_open", "status": 200},
])
def test_rejects_interaction_values_and_request_semantics(client, event):
    assert client.post("/api/usage/events", json=payload(event)).status_code == 422


def test_reordered_concurrent_funnels_and_visible_time(client):
    rows = [
        {"kind": "result", "target": "/api/actions/train", "request_id": 2, "outcome": "rejected", "status": 200},
        {"kind": "attempt", "target": "/api/actions/train", "request_id": 1},
        {"kind": "attempt", "target": "/api/actions/train", "request_id": 2},
        {"kind": "result", "target": "/api/actions/train", "request_id": 1, "outcome": "http_error", "status": 409},
        {"kind": "visible_time", "target": "club", "duration_ms": 1200},
    ]
    assert client.post("/api/usage/events", json=payload(*rows)).json()["accepted"]
    report = client.get("/api/usage/report").json()
    assert report["attempts"] == report["paired_results"] == 2
    assert report["visible_ms"] == {"club": 1200}
    assert report["outcomes"]["/api/actions/train:rejected"] == 1


def test_write_failure_is_isolated(tmp_path, monkeypatch):
    store = UsageStore(tmp_path)
    def denied(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(Path, "mkdir", denied)
    assert store.append(UsageBatch.model_validate(payload({"kind": "session_start"})), {"sid": "x"}) is False


def test_rotation_and_corrupt_line_report(tmp_path):
    store = UsageStore(tmp_path, max_bytes=500)
    batch = UsageBatch.model_validate(payload({"kind": "session_start"}))
    for _ in range(20):
        assert store.append(batch, {"sid": "x"})
    assert len(list(tmp_path.glob("usage.*.jsonl"))) == 4
    assert all(p.stat().st_size <= 500 for p in store.paths())
    with store.paths()[0].open("a") as stream:
        stream.write("broken\n")
    report = store.report()
    assert report["malformed_lines"] == 1
    assert report["events"]["session_start:"] < 20


def test_report_requires_local_admin(tmp_path):
    app = FastAPI()
    def denied():
        raise HTTPException(403, "local only")
    install_usage_routes(app, tmp_path, lambda: {"sid": "x"}, denied)
    assert Client(app).get("/api/usage/report").status_code == 403


def test_frontend_visible_time_transition_pairing_and_failure_isolation():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend contract verification")
    subprocess.run([node, "tests/usage_frontend_check.cjs"], check=True, capture_output=True)


def test_actual_ui_subtabs_do_not_poison_action_batches(client):
    import re
    source = Path("src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    # All UI tab declarations use this shape, including inline screenHead and React tabs.
    ids = set(re.findall(r'\{ id: "([a-z_]+)", label:', source))
    assert {"playoffs", "races", "meta", "history", "overview"} <= ids
    for subtab in ids:
        response = client.post("/api/usage/events", json=payload(
            {"kind": "view", "target": f"roster/{subtab}"},
            {"kind": "attempt", "target": "/api/actions/train", "request_id": 1},
            {"kind": "result", "target": "/api/actions/train", "request_id": 1, "outcome": "success"},
        ))
        assert response.status_code == 200, subtab
        assert response.json()["accepted"]


def test_real_session_middleware_resolves_transition_linkage(monkeypatch):
    from types import SimpleNamespace
    from esports_sim.web import server
    current = [None, None]
    monkeypatch.setattr(server._LOBBY, "game_for", lambda sid: tuple(current))
    contexts = []
    def append(self, batch, context):
        contexts.append(context)
        return True
    monkeypatch.setattr(UsageStore, "append", append)
    client = Client(server.app)
    headers = {"Cookie": "esports_sid=" + "b"*32}
    assert client.post("/api/usage/events", headers=headers, json=payload(
        {"kind": "attempt", "target": "/api/join", "request_id": 1})).json()["accepted"]
    current[:] = [SimpleNamespace(code="NEXT", gs=SimpleNamespace(season=2, week=3)), "team_next"]
    assert client.post("/api/usage/events", headers=headers, json=payload(
        {"kind": "result", "target": "/api/join", "request_id": 1, "outcome": "success"})).json()["accepted"]
    assert contexts[0]["world"] is None
    assert contexts[1] == {"sid": "b"*32, "world": "NEXT", "team": "team_next", "season": 2, "week": 3}


def test_stalled_disk_append_does_not_block_unrelated_gameplay(monkeypatch, tmp_path):
    import threading
    entered, release = threading.Event(), threading.Event()
    app = FastAPI()
    @app.get("/api/ping")
    async def ping():
        return {"ok": True}
    request_thread = threading.get_ident()
    def context():
        assert threading.get_ident() == request_thread
        return {"sid": "test"}
    install_usage_routes(app, tmp_path, context, lambda: None)
    def stalled(self, batch, resolved):
        assert resolved == {"sid": "test"}
        assert threading.get_ident() != request_thread
        entered.set()
        assert release.wait(3)
        return True
    monkeypatch.setattr(UsageStore, "append", stalled)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            pending = asyncio.create_task(client.post("/api/usage/events", json=payload({"kind": "session_start"})))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                response = await asyncio.wait_for(client.get("/api/ping"), timeout=1)
                assert response.json() == {"ok": True}
            finally:
                release.set()
                assert (await pending).json()["accepted"]
    asyncio.run(scenario())


def test_rotation_respects_exact_byte_boundary_on_windows(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from esports_sim.web import usage_telemetry
    class FixedDatetime:
        @staticmethod
        def now(tz):
            return datetime(2026, 1, 1, microsecond=123000, tzinfo=timezone.utc)
    monkeypatch.setattr(usage_telemetry, "datetime", FixedDatetime)
    store = UsageStore(tmp_path)
    batch = UsageBatch.model_validate(payload({"kind": "session_start"}))
    context = {"sid": "test"}
    assert store.append(batch, context)
    row = store.paths()[0].read_bytes()
    store.max_bytes = 2 * len(row) - 1
    assert store.append(batch, context)
    assert store.paths()[1].exists()
    assert all(path.stat().st_size <= store.max_bytes for path in store.paths() if path.exists())
    assert b"\r\n" not in row


def test_market_search_receipts_are_coarse_counts(client):
    event = {"kind": "interaction", "target": "market/player_search"}
    assert client.post("/api/usage/events", json=payload(event, event)).json()["accepted"]
    report = client.get("/api/usage/report").json()
    assert report["events"] == {"interaction:market/player_search": 2}
    assert report["attempts"] == report["paired_results"] == 0


@pytest.mark.parametrize("event", [
    {"kind": "interaction", "target": "market/player_search/secret"},
    {"kind": "interaction", "target": "market/search"},
    *[{"kind": "interaction", "target": "market/player_search", field: value}
      for field, value in [("query", "secret"), ("handle", "secret"), ("player_id", "secret"),
                           ("selector", "secret"), ("label", "secret"), ("url", "secret"),
                           ("request_id", 1), ("outcome", "success"), ("duration_ms", 1)]],
])
def test_market_search_rejects_values_and_unknown_targets(client, event):
    assert client.post("/api/usage/events", json=payload(event)).status_code == 422


def test_market_search_actual_js_callbacks():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    subprocess.run([node, "tests/market_search_usage_check.cjs"], check=True, capture_output=True)
