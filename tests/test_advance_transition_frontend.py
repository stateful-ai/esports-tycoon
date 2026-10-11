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
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for frontend verification")
    source = (Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/app.js").read_text(encoding="utf-8")
    handler = re.search(r'\$\("#advance-btn"\)\.onclick = async \(\) => \{.*?\n\};', source, re.S).group()
    script = """
const button = {disabled: false};
const $ = () => button;
const App = {state: {week: 23}};
const mpPollingRetry = true;
const events = [];
function pollForAdvance(week) {events.push(['poll', week]);}
function updateAdvanceTransition() {events.push(['paint']);}
function showWeekLoading() {throw Error('Retry must not start an advance');}
async function api() {throw Error('Retry must not submit a decision');}
""" + handler + """
button.onclick().then(() => console.log(JSON.stringify({disabled:button.disabled, events})));
"""
    actual = json.loads(subprocess.check_output([node, "-e", script], text=True, encoding="utf-8"))
    assert actual == {"disabled": True, "events": [["poll", 23], ["paint"]]}
