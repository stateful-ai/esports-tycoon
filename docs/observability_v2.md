# Observability (v2)

Companion to docs/observability.md. Where the short version lists
what we log, this one captures the per-run telemetry shape so
contributors don't accidentally diverge it.

## Per-run JSON envelope
Every run writes a JSON envelope with at minimum:

- `run_id` — short stable id.
- `started_at_utc` / `ended_at_utc` — ISO 8601 strings.
- `seed` — the random seed actually used.
- `ticks` or `turns` — count of steps advanced.
- `exit_code` — 0 = clean.

## Where it goes
Local: `runs/` or `outputs/` (whichever the project already uses).
No cloud telemetry. No phone-home.

## When you read it
Use existing render helpers. Don't write a parser script — extend the
existing renderer if it doesn't cover your use.
