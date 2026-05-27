# Known quirks

Harmless oddities that aren't bugs but might surprise a contributor.

## Reproducible by design
Adaptive behaviour is gated by determinism, so the same seed produces
the same run. If you change your local random module seed you'll get
*exactly* the same output as before — that's not a bug, it's the
guarantee in action.

## No analytics
No usage counters, no metrics, no telemetry. If you go looking for
retention dashboards you won't find any; we deliberately don't build
for them.

## Templates first
Most prose looks oddly mechanical until you read closely. That's
because the templated path is the default; the LLM backend is opt-in.
