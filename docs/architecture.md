# Architecture

Esports Tycoon is a Python package laid out as:

- 'esports_tycoon/' — the simulation core and content adapter.
- 'scripts/' — operational scripts (CLI entry points, batch jobs).
- 'tests/' — pytest suite covering determinism and content invariants.
- 'saves/' — persisted simulation state used by the runtime.
- 'runs/' — telemetry from past runs (gitignored noise lives here).

The content adapter is the seam between the deterministic simulation
core and the LLM-backed text generation; everything is templated by
default and the LLM backend is opt-in.
