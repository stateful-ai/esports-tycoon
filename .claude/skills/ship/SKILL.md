---
name: ship
description: Run the full release gate stack for this repo (tests, golden, balance, pacing) and push with CI watch. Use before any push to main, or when asked to "ship" work.
---

# Ship

The gate stack, in order. A failure stops the ship — fix or explicitly
justify, never skip silently.

1. **Tests**: `.venv-win\Scripts\python.exe -m pytest -q` → all green.
   Runs parallel by default (`-n auto`, see pyproject). Ship runs the FULL
   suite — the `-m "not slow"` fast lane is for the tight edit loop only and
   skips the whole-season determinism soak tests, so never ship on it alone.
2. **Golden** (two fixtures — the single canonical match AND the
   `sweep_neutral` multi-seed aggregate): if the suite fails ONLY on
   `tests/test_golden.py` and the session intentionally changed engine
   behavior / map data, re-bless BOTH with
   `.venv-win\Scripts\python.exe scripts\regen_golden.py`, then rerun
   pytest. If the change was NOT intentional, that failure is a bug — and
   for a tactics change it almost always means a term isn't neutral-safe
   (see the `/tactics` skill / ADR-007), not something to re-bless.
3. **Balance** (only if `sim/constants.py`, `sim/engine.py`, or
   `data/maps/**` changed): `scripts\balance_report.py 300` → exit 0
   (every map 45–65% attack, three core round-end reasons present).
4. **Pacing** (same trigger set): `scripts\pacing_report.py` → exit 0
   (attacker via-spawn rotate 25–35s, spawn→entry stage 8–18s).
5. **Snowball** (if the change could affect multi-season competitiveness —
   balance, development, economy, market): `scripts\snowball_report.py` →
   exit 0 (blowout/close band across 3 seasons).
6. **Floor audit** (if `data/maps/geometry/**` changed):
   `scripts\map_floor_audit.py` → exit 0 (plates touch, callouts on-plate,
   paths on the plate union; teleporter edges exempt). If geometry moved
   where paint exists, also eyeball the seams — IoU won't catch stale
   paint (see the `/maps` skill).
7. **JS** (if web/static changed): `node --check` each changed file, and
   verify the affected screen in the browser preview when one is running
   (prefer preview_snapshot/preview_eval — screenshots wedge on this box).
8. **Commit**: imperative subject; body explains the why and records key
   numbers (balance/pacing/snowball). Use the repo's co-author line.
9. **Push + CI**: push to main — parallel sessions land PRs here, so a
   non-fast-forward reject is normal: `git pull --rebase origin main`,
   rerun the gates that the incoming commits could affect, push again.
   Then watch
   `gh run list -R stateful-ai/esports-tycoon --branch main --limit 1`
   in a background poll until `completed success`. Report the result.

Note: `balance_report.py` and `snowball_report.py` are now real exit-1
gates (they were print-only diagnostics earlier). `tactics_report.py`
(sweep each dial to its extremes) is also a gate — run it after any change
to the tactics dials or their engine reach.
