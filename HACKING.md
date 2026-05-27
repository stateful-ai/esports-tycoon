# Hacking on this codebase

## 30-second tour
- `<package>/` is the main code.
- `tests/` is the pytest suite.
- `docs/` is where design notes live.

## First-time setup
1. Clone.
2. `pip install -e .[dev]` (or just `pip install -e .`).
3. `pytest` to confirm the suite passes.

## Making a change
- Keep diffs small and single-concern.
- Add a test for new behaviour.
- Match the surrounding style.

## Where to ask
Open a GitHub Discussion or issue. SECURITY.md covers private reports.
