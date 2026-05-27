# Runbook

## Local dev loop
- Install: `pip install -e .[dev]`.
- Tests: `pytest`.

## Save/load
- State lives under `saves/` (gitignored).
- Schema-version mismatch on load triggers a friendly error; see
  docs/troubleshooting.md for the migration path.

## Content adapter
- Templated default is on. LLM backend is opt-in via env (see
  `esports_tycoon.content.config`).
