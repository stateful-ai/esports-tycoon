---
name: web-screen
description: Add or rework a web UI screen or widget the repo way — thin FastAPI serializer, no sim logic or engine formulas in JS, design-system tokens, profile-link wiring, and the browser-verification workaround. Use when touching web/server.py serializers or web/static/*.
---

# Web screen — frontend/serializer conventions

The stack is FastAPI (`web/server.py`) + no-build vanilla JS
(`web/static/`) on `ui/design-system/tokens.css` (served at
`/ds/tokens.css`). No frameworks, no bundler, no npm.

## The boundary rule (load-bearing)

**The UI holds no sim state and no sim formulas.** It renders GameState
views and event logs the server hands it — nothing else.

- Sim/campaign logic goes in the engine or `manager/`, never in JS.
- Don't MIRROR an engine formula in JS "just for a preview" — no gate
  exercises browser JS, so it silently drifts. Serialize the computed
  values instead. Pattern: `sim/tactics_fit.py` is shared by the engine
  and the serializer; `/api/tactics` returns each dial's impact at both
  poles and the client only lerps (works because the maths is
  piecewise-linear with its knot at neutral 50).
- Server serializers stay THIN: read GameState, shape JSON, no mutation.
  Actions are separate typed POST endpoints that validate against the
  live state (an inbox action derives its buttons from CURRENT offers, so
  a stale message can't fire a dead offer).

## Wiring checklist for a new screen/tab

1. Serializer in `web/server.py` — exact key sets; use nulls, never
   missing keys (frontend agents code against the frozen contract).
2. Tab: `index.html` nav (`data-tab="<name>"`) + the screen function in
   `app.js` (see `async function dashboard(v)` for the shape).
3. Style with tokens (`--es-*` vars; navy dark palette, brand #FF4655,
   teal `--es-color-accent`, amber `--es-color-accent-warm`, Rajdhani via
   `--es-font-display`). Both light/dark blocks live in tokens.css.
4. Any player/team name you render should carry `data-pid`/`data-tid` —
   a document-level capture-phase listener (profile.js) turns them into
   profile-overlay links for free. Don't add per-element handlers.
5. New JS file? Include it in `index.html` and add it to the
   `node --check` pass.

## Verify

- `node --check src\esports_sim\web\static\<file>.js` for every touched
  file (catches syntax before the browser does).
- Preview server: config "web" in `.claude/launch.json` (port 8420).
- **preview_screenshot wedges chronically on this machine** — verify with
  preview_snapshot (structure/text), preview_inspect (CSS values), and
  preview_eval (DOM checks / reload). Never conclude "works" from a
  screenshot attempt that timed out.
- API-contract tests live in `tests/` and import fastapi — guard new test
  modules with `pytest.importorskip("fastapi")` so a `.[dev]`-only
  install still collects (CI installs `.[dev,web]`).

## Parallel-agent etiquette

Partition by FILE: one agent owns a JS file, another owns the serializer.
When both sides are needed, freeze the JSON contract first (exact keys,
null semantics), then let backend/frontend agents run concurrently
against it.
