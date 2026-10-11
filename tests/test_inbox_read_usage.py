"""Inbox read usage contracts; authored without execution for this change."""
import shutil
import subprocess

import pytest
from fastapi import FastAPI

from esports_sim.web.usage_telemetry import install_usage_routes
from tests.test_usage_telemetry import Client, payload

pytestmark = pytest.mark.web


def test_silent_inbox_read_frontend_receipts():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend contract verification")
    subprocess.run([node, "tests/inbox_read_usage_check.cjs"], check=True, capture_output=True)


def test_fixed_inbox_read_bucket_retains_report_compatibility_and_privacy(tmp_path):
    app = FastAPI()

    @app.post("/api/inbox/read")
    def read():
        return {"unread": 0}

    install_usage_routes(app, tmp_path, lambda: {"sid": "private-cookie"}, lambda: None)
    client = Client(app)
    events = []
    for i, (target, outcome) in enumerate([
        ("/api/inbox", "success"),
        ("/api/inbox/read", "success"),
        ("/api/inbox/read", "http_error"),
        ("/api/inbox/read", "transport_error"),
    ], 1):
        events.extend([
            {"kind": "attempt", "target": target, "request_id": i},
            {"kind": "result", "target": target, "request_id": i, "outcome": outcome},
        ])
    assert client.post("/api/usage/events", json=payload(*events)).json() == {"accepted": True}
    report = client.get("/api/usage/report").json()
    assert report["attempts"] == report["paired_results"] == 4
    assert report["unmatched_attempts"] == report["orphan_results"] == 0
    assert report["events"]["attempt:/api/inbox"] == 1
    assert report["events"]["attempt:/api/inbox/read"] == 3
    assert report["outcomes"]["/api/inbox/read:transport_error"] == 1
    for target in ("/api/inbox/read/private-id", "/api/inbox/read?secret=private", "/api/inbox/private-id"):
        assert client.post("/api/usage/events", json=payload(
            {"kind": "attempt", "target": target, "request_id": 5},
        )).status_code == 422
    for field in ("id", "all", "title", "body"):
        assert client.post("/api/usage/events", json=payload(
            {"kind": "attempt", "target": "/api/inbox/read", "request_id": 5, field: "private"},
        )).status_code == 422
    assert "private" not in (tmp_path / "usage/usage.0.jsonl").read_text()
