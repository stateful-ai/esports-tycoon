"""Shared ready-up survives the state refresh before polling starts."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.web


def test_advance_label_tracks_ready_state_and_campaign_transition():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for frontend verification")
    source = (Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    helper = re.search(r"function updateAdvanceTransition\(s\) \{.*?\n\}", source, re.S).group()
    script = """
let mpPolling = false;
let mpPollingRetry = false;
const button = {textContent: '', setAttribute() {}, removeAttribute() {}};
const notice = {textContent: '', classList: {toggle() {}}};
const $ = id => id === '#advance-btn' ? button : notice;
""" + helper + """
const regular = {advance_transition: {label: 'Advance Week', notice: ''}};
const offseason = {advance_transition: {label: 'Start Season 2', notice: 'Rollover'}};
const labels = [];
for (const state of [regular, offseason,
  {...offseason, multiplayer: {you_ready: true}},
  {...regular, multiplayer: {you_ready: true}}, regular]) {
  updateAdvanceTransition(state);
  labels.push(button.textContent);
}
mpPolling = true;
updateAdvanceTransition(offseason);
labels.push(button.textContent);
mpPolling = false;
mpPollingRetry = true;
updateAdvanceTransition({...offseason, multiplayer: {you_ready: true}});
labels.push(button.textContent);
console.log(JSON.stringify(labels));
"""
    assert json.loads(subprocess.check_output([node, "-e", script], text=True, encoding="utf-8")) == [
        "Advance Week ▸", "Start Season 2 ▸", "Waiting… ⏳",
        "Waiting… ⏳", "Advance Week ▸", "Waiting… ⏳", "Retry status ▸",
    ]


def test_retry_status_reconnects_without_resubmitting_advance():
    source = (Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    retry = re.search(r"if \(mpPollingRetry\) \{(.*?)\n  \}", source, re.S).group(1)
    assert "pollForAdvance(prevWeek)" in retry
    assert "return;" in retry
    assert "api(" not in retry
