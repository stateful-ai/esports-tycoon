---
name: ship
description: Run the full release gate stack for this repo (tests, golden, balance, pacing) and push with CI watch. Use before any push to main, or when asked to "ship" work.
---

# Ship

The gate stack, in order. A failure stops the ship — fix or explicitly
justify, never skip silently.

1. **Tests**: `.venv-win\Scripts\python.exe -m pytest -q` → all green.
2. **Golden**: if the suite fails ONLY on `tests/test_golden.py` and the
   session intentionally changed engine behavior / map data, re-bless with
   `.venv-win\Scripts\python.exe scripts\regen_golden.py`, then rerun
   pytest. If the change was NOT intentional, that failure is a bug.
3. **Balance** (only if `sim/constants.py`, `sim/engine.py`, or
   `data/maps/**` changed): `scripts\balance_report.py 300` — every map
   45–65% attack.
4. **Pacing** (same trigger set): `scripts\pacing_report.py` → exit 0.
5. **JS** (if web/static changed): `node --check` each changed file, and
   verify the affected screen in the browser preview when one is running.
6. **Commit**: imperative subject; body explains the why and records key
   numbers (balance/pacing/IoU); include
   `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
7. **Push + CI**: push to main, then watch
   `gh run list -R stateful-ai/esports-tycoon --branch main --limit 1`
   in a background poll until `completed success`. Report the result.
