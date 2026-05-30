# Glossary v3 — patterns

Beyond single-word terms, these are *patterns* the codebase uses
repeatedly. Naming them so contributors can recognize them.

## Seam
An explicit dependency injection point — a function parameter (often
default-None) that takes a replacement implementation. Tests inject
fakes here; production gets the real one. Every external call in the
hot path goes through one.

## Pure reducer over an event log
The Mirror's architecture: events are the source of truth; state is
always recomputed. No authoritative mutable state.

## Templated default, LLM opt-in
Whenever we generate text, the templated path is the default and the
LLM backend is opt-in. Tests pin the templated path; the LLM is
validated separately.

## Idempotent per-day
A daily writer that re-running on the same day is a no-op or a
byte-identical overwrite.
