# Architecture (overview)

A 60-second tour. The deeper version lives at docs/architecture.md.

- The codebase splits into a deterministic core and stateless adapters
  around it. The core never depends on the adapters; the adapters import
  the core.
- Tests pin behaviour, not implementation. If a refactor breaks a test
  the test was right.
- Configuration is YAML or env, never code.

Read docs/architecture.md for the per-package detail.
