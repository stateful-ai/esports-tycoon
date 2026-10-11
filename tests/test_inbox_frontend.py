"""Exercise the real Inbox disclosure and shortcut callbacks without a server."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.web


def test_inbox_collapsed_actions_and_keyboard_roster_shortcut():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for frontend verification")
    source = (
        Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/inbox.js"
    ).read_text(encoding="utf-8")
    navigation = re.search(
        r"const INBOX_TAB_ALIAS = \{.*?\n\}\n", source, re.S
    ).group()
    row = source.split("  function inboxRow(it) {", 1)[1].split(
        "  /* -- rail:", 1
    )[0]
    script = """
const assert = require('node:assert/strict');
const App = {tab: 'inbox', clubTab: 'development'};
const clicks = [];
const document = {querySelector(selector) {
  assert.equal(selector, '#tabs [data-tab="club"]');
  return {click() { clicks.push(App.clubTab); App.tab = 'club'; }};
}};
function el(tag, cls, text) {
  const classes = new Set((cls || '').split(' '));
  return {tag, text, children: [], attrs: {},
    classList: {toggle(name, on) { if (on) classes.add(name); else classes.delete(name); },
      contains(name) { return classes.has(name); }},
    setAttribute(key, value) { this.attrs[key] = value; },
    append(...nodes) { this.children.push(...nodes); },
    appendChild(child) { this.children.push(child); }};
}
const INBOX_CAT_LABEL = {board: 'Board'};
const inboxLabel = text => text;
const rowCtl = new Map();
let reads = 0;
async function markItemRead() { reads++; }
""" + navigation + "function inboxRow(it) {" + row + """
const item = inboxRow({id: 'apex-deadline', category: 'board', unread: true,
  week: 1, title: 'Contract deadline', body: 'Renew Apex', tab: 'roster'});
const [header, body] = item.children;
assert.equal(header.attrs.role, 'button');
assert.equal(header.tabIndex, 0);
assert.equal(header.attrs['aria-expanded'], 'false');
assert.equal(body.inert, true);
assert.equal(body.attrs['aria-hidden'], 'true');
assert.equal(reads, 0);
let prevented = 0;
header.onkeydown({key: 'Enter', preventDefault() { prevented++; }});
assert.equal(prevented, 1);
assert.equal(header.attrs['aria-expanded'], 'true');
assert.equal(body.inert, false);
assert.equal(body.attrs['aria-hidden'], 'false');
assert.equal(body.classList.contains('collapsed'), false);
assert.equal(reads, 1);
let stopped = 0;
body.children[1].onclick({stopPropagation() { stopped++; }});
assert.equal(stopped, 1);
assert.equal(App.tab, 'club');
assert.deepEqual(clicks, ['squad']);
header.onkeydown({key: ' ', preventDefault() { prevented++; }});
assert.equal(prevented, 2);
assert.equal(body.inert, true);
assert.equal(body.attrs['aria-hidden'], 'true');
assert.equal(header.attrs['aria-expanded'], 'false');
assert.equal(reads, 1);
rowCtl.get('apex-deadline').openRow();
assert.equal(body.inert, false);
assert.equal(header.attrs['aria-expanded'], 'true');
"""
    subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
