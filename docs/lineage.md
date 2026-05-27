# Lineage

Where this project's ideas come from. Track them so contributors can
see what we're building on, not just what we're building.

## Direct inheritors
- The deterministic core's design lineage traces back to the rule
  that 'replay is the source of truth' — every event log we accept
  must reduce byte-identically.

## Adjacent inspirations
- The architecture of small Lisp-machine programs: many small,
  inspectable parts.
- Tom Sawyer-style 'pretend it was hard so others want to try' — we
  expose seams aggressively so contribution is welcome.

## What we don't borrow
- Heavyweight ECS frameworks.
- 'Engine-first' tooling that requires a build dance to test a unit.
