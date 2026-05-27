# Observability

## What we log
- Determinism gate failures (loudly, never silently).
- Recipe load errors with file path + line.

## What we deliberately don't log
- Per-tick state — too noisy; replay the recipe to inspect instead.
- LLM prompts/responses by default — opt in via env if needed.

## Telemetry directory
Each run writes a per-run JSON under `runs/` (in the codebase that has it) or `outputs/` (otherwise). Gitignored.

## Reading a run
Use the rendering helpers in the project's `render_*` modules — they
read the JSON and produce a one-screen summary.
