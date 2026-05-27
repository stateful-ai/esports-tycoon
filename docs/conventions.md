# Conventions

## Layout
- `esports_tycoon/` is the sim + content adapter.
- `scripts/` holds operational entry points.
- `tests/` is the pytest suite (determinism + content invariants).
- `saves/` is persistent state.
- `runs/` is per-run telemetry (gitignored noise).

## Tests
- One axis per test; parametrize the others.
- Templated prose paths must be byte-identical across runs.

## Commits
- Imperative subject; body explains the *why*.
