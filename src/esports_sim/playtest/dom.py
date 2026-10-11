"""Turn a live screen into something an agent can read.

A screenshot alone is a poor control surface: an agent can see that a button
exists but cannot name it precisely enough to click it. So every observation
carries two halves that must agree — the PNG (what a human would see) and a
text digest (what is on the screen, with the exact handles needed to act on
it). The split here keeps the browser out of the digest logic:

``SCREEN_SCRIPT`` runs *in the page* and returns a plain JSON snapshot.
``render_digest`` is a pure function over that snapshot, so the formatting
that agents depend on is unit-testable without launching Chromium.
"""

from __future__ import annotations

from typing import Any

# Text longer than this is elided in the digest; the screenshot carries the
# rest. Long enough for a card body, short enough that a nine-tab sweep fits
# in one agent context.
_MAX_TEXT = 220
_MAX_ROWS = 12


# The in-page collector. Returns a JSON-safe snapshot of the current screen:
# what it says, what can be clicked, and what is currently broken. Kept as a
# string (not a .js file) so the contract travels with the parser that reads
# it — the two are useless apart and drift silently when they live apart.
# The one definition of "the player can see and use this". Every part of the
# harness injects this same function, because the moment two of them disagree
# the harness starts lying: the profile overlay, for instance, is deliberately
# left at `display: flex; opacity: 0; pointer-events: none` when closed so it
# can fade out (see profile.css). A check that only looks at `display` calls
# that closed modal "open", blocks Advance Week on it, and treats it as the
# root for every subsequent click.
VISIBLE_JS = """
  const vis = (node) => {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    if (Number(style.opacity) === 0) return false;
    if (style.pointerEvents === 'none') return false;
    const box = node.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
"""

# Overlays that are visible right now, topmost last. Used to pick the acting
# root, to warn an agent that a modal is covering the page, and to decide
# whether an overlay actually closed.
OPEN_OVERLAYS_SCRIPT = (
    "() => {\n" + VISIBLE_JS + "\n"
    "  return [...document.querySelectorAll('.overlay')].filter(vis)"
    ".map((n) => n.id || 'overlay');\n}"
)


SCREEN_SCRIPT = """
() => {
""" + VISIBLE_JS + """
  const txt = (node) => (node?.innerText || node?.textContent || '')
    .replace(/\\s+/g, ' ').trim();

  const overlayNodes = [...document.querySelectorAll('.overlay')].filter(vis);
  const overlays = overlayNodes.map(
    (node) => ({ id: node.id || '', title: txt(node.querySelector('h1, h2')) }));

  const tabs = [];
  for (const node of document.querySelectorAll('nav#tabs button[data-tab]')) {
    tabs.push({
      tab: node.dataset.tab,
      label: txt(node),
      active: node.classList.contains('active'),
    });
  }

  // The screen root is whichever overlay is on top, else the main view. An
  // agent acting on the page underneath a modal is acting on nothing. Held as
  // the node itself: an overlay without an id would be lost by a lookup.
  const root = overlayNodes.length
    ? overlayNodes[overlayNodes.length - 1]
    : (document.getElementById('view') || document.body);

  const subtabs = [];
  for (const node of root.querySelectorAll('.seg .seg-btn, .seg button')) {
    if (vis(node)) subtabs.push({ label: txt(node), active: node.classList.contains('on') || node.classList.contains('active') });
  }

  const controls = [];
  const seen = new Set();
  for (const node of root.querySelectorAll('button, a[href], input, select, textarea, [role=button]')) {
    if (!vis(node)) continue;
    const label = txt(node) || node.getAttribute('aria-label') || node.getAttribute('placeholder')
      || node.getAttribute('title') || node.value || '';
    const kind = node.tagName.toLowerCase();
    const key = kind + '|' + label + '|' + (node.id || '');
    if (seen.has(key)) continue;
    seen.add(key);
    controls.push({
      kind,
      label: String(label).slice(0, 80),
      id: node.id || '',
      disabled: Boolean(node.disabled) || node.getAttribute('aria-disabled') === 'true',
      type: node.getAttribute('type') || '',
      value: kind === 'input' || kind === 'select' || kind === 'textarea' ? String(node.value ?? '') : '',
    });
  }

  const cards = [];
  for (const node of root.querySelectorAll('.card, .panel-card, section')) {
    if (!vis(node)) continue;
    const heading = txt(node.querySelector('h1, h2, h3, .card-title, .microlabel'));
    const body = txt(node);
    if (!heading && !body) continue;
    cards.push({ heading, body });
  }

  const tables = [];
  for (const node of root.querySelectorAll('table')) {
    if (!vis(node)) continue;
    const headers = [...node.querySelectorAll('thead th, tr:first-child th')].map(txt);
    const rows = [...node.querySelectorAll('tbody tr')].slice(0, 40)
      .map((tr) => [...tr.querySelectorAll('td, th')].map(txt));
    tables.push({ headers, rows, total: node.querySelectorAll('tbody tr').length });
  }

  // Profile overlays open off any name carrying one of these hooks; an agent
  // that cannot see the hooks cannot inspect a player, so surface a sample.
  const links = [];
  for (const node of root.querySelectorAll('[data-pid], [data-tid], [data-sid]')) {
    if (!vis(node) || links.length >= 24) continue;
    const key = node.dataset.pid ? 'player' : node.dataset.tid ? 'team' : 'staff';
    links.push({ kind: key, label: txt(node), ref: node.dataset.pid || node.dataset.tid || node.dataset.sid });
  }

  // Structured extraction only knows the conventions it was taught. Overlays
  // and bespoke panels use their own markup, and a digest that finds no cards
  // and no tables would tell an agent the screen is empty when it is full. The
  // raw text of the root is the floor beneath every convention.
  const bodyText = txt(root).slice(0, 4000);

  // Toasts are the game's primary transient feedback: a refused action says
  // why here and nowhere else, then removes itself after ~4s. Three separate
  // persona reports of "it failed silently" turned out to be this channel
  // being invisible to the digest -- the game HAD answered. Captured every
  // step so a refusal is never mistaken for silence.
  const toasts = [];
  for (const node of document.querySelectorAll('#toast .t')) {
    const text = txt(node);
    if (text) toasts.push(text);
  }

  return {
    toasts,
    url: location.pathname + location.search,
    title: document.title,
    bodyText,
    context: txt(document.getElementById('context')),
    balance: txt(document.getElementById('balance')),
    inGame: !document.getElementById('newgame')?.classList.contains('hidden') ? false : true,
    overlays,
    tabs,
    subtabs,
    screenTitle: txt(root.querySelector('.screen-title')) || txt(root.querySelector('h1')),
    cards,
    tables,
    controls,
    links,
    viewTextLength: (document.getElementById('view')?.innerText || '').length,
  };
}
"""


def _clip(text: str, limit: int = _MAX_TEXT) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _control_line(control: dict[str, Any]) -> str:
    label = _clip(control.get("label", ""), 80) or "(unlabelled)"
    bits = [label]
    if control.get("id"):
        bits.append(f"#{control['id']}")
    if control.get("value"):
        bits.append(f"= {_clip(control['value'], 40)}")
    if control.get("disabled"):
        bits.append("[disabled]")
    return f"  - {control.get('kind', '?')}: " + " ".join(bits)


def render_digest(snapshot: dict[str, Any], *, screenshot: str | None = None) -> str:
    """Render one screen snapshot as the text half of an observation.

    The digest is what the agent reads *alongside* the screenshot, so it says
    what is clickable and what is broken rather than restating the picture.
    """
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")

    out: list[str] = []
    header = snapshot.get("screenTitle") or snapshot.get("title") or "(untitled screen)"
    out.append(f"SCREEN: {_clip(header, 80)}")
    if snapshot.get("context"):
        out.append(f"CONTEXT: {_clip(snapshot['context'], 120)}")
    if snapshot.get("balance"):
        out.append(f"BALANCE: {_clip(snapshot['balance'], 40)}")

    # Directly under the header: a toast is the answer to what you just did,
    # and it is gone in four seconds.
    toasts = [t for t in snapshot.get("toasts", []) if str(t).strip()]
    for message in toasts:
        out.append(f"MESSAGE: {_clip(str(message), 200)}")

    overlays = [o for o in snapshot.get("overlays", []) if o.get("id") or o.get("title")]
    if overlays:
        names = ", ".join(
            f"{o.get('id') or '?'}{' — ' + _clip(o['title'], 50) if o.get('title') else ''}"
            for o in overlays
        )
        out.append(f"OVERLAY OPEN (blocks the page beneath): {names}")

    tabs = snapshot.get("tabs", [])
    if tabs:
        rendered = " ".join(
            f"[{t.get('label', '')}]" if t.get("active") else str(t.get("label", ""))
            for t in tabs
        )
        out.append(f"TABS: {rendered}")

    subtabs = snapshot.get("subtabs", [])
    if subtabs:
        rendered = " ".join(
            f"[{s.get('label', '')}]" if s.get("active") else str(s.get("label", ""))
            for s in subtabs
        )
        out.append(f"SUB-TABS: {rendered}")

    cards = snapshot.get("cards", [])
    tables = snapshot.get("tables", [])
    if not cards and not tables and snapshot.get("bodyText"):
        # No recognised structure: fall back to what the screen literally says,
        # so a bespoke overlay is never reported as an empty screen.
        out.append("")
        out.append("SCREEN TEXT:")
        out.append("  " + _clip(snapshot["bodyText"], 2000))
    if cards:
        out.append("")
        out.append(f"CARDS ({len(cards)}):")
        for card in cards[:_MAX_ROWS]:
            heading = _clip(card.get("heading", ""), 60)
            body = _clip(card.get("body", ""))
            out.append(f"  * {heading or '(no heading)'}: {body}" if heading else f"  * {body}")
        if len(cards) > _MAX_ROWS:
            out.append(f"  ... {len(cards) - _MAX_ROWS} more cards (see the screenshot)")

    for index, table in enumerate(tables):
        headers = [h for h in table.get("headers", []) if h]
        rows = table.get("rows", [])
        total = table.get("total", len(rows))
        out.append("")
        out.append(f"TABLE {index + 1} ({total} rows): {' | '.join(headers) if headers else '(no header)'}")
        for row in rows[:_MAX_ROWS]:
            out.append("  " + " | ".join(_clip(cell, 30) for cell in row))
        if total > _MAX_ROWS:
            out.append(f"  ... {total - _MAX_ROWS} more rows")

    controls = snapshot.get("controls", [])
    if controls:
        out.append("")
        out.append(f"CONTROLS ({len(controls)}):")
        out.extend(_control_line(c) for c in controls[:40])
        if len(controls) > 40:
            out.append(f"  ... {len(controls) - 40} more controls")

    links = snapshot.get("links", [])
    if links:
        out.append("")
        sample = ", ".join(f"{link.get('label', '?')} ({link.get('kind')})" for link in links[:10])
        out.append(f"PROFILE LINKS ({len(links)}): {sample}")

    if screenshot:
        out.append("")
        out.append(f"SCREENSHOT: {screenshot}")
    return "\n".join(out)


def render_console(entries: list[dict[str, Any]] | None) -> str:
    """Render captured console/network errors, newest last. Empty -> ''."""
    entries = entries or []
    if not entries:
        return ""
    lines = [f"CONSOLE/NETWORK ERRORS ({len(entries)}):"]
    for entry in entries[-20:]:
        lines.append(f"  ! [{entry.get('kind', '?')}] {_clip(entry.get('text', ''), 200)}")
    return "\n".join(lines)
