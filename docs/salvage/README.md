# Salvage from `esports-tycoon` (the previous prototype)

The repo this project replaced on GitHub (`stateful-ai/esports-tycoon`, June
2026) was a narrative-first vertical slice — no real match engine, but a few
pieces were worth keeping. Files here are reference material, not live code.

## Files

- **`recall_reference.py`** — deterministic "precedent recall" ranker from the
  prototype. Scores memory-log entries against a resolved match by shared
  actors, tag overlap, and active rivalries; stable-sorted, zero RNG/IO.
  Blueprint for the narrative engine (roadmap Phase 4): surfacing grounded
  "the team remembers when…" callbacks from our JSONL event log. It reads the
  old schema — adapt, don't import.
- **`tone_and_cast_lock.md`** — the prototype's voice + cast design doc.
  Dry-mockumentary tone rules with calibration lines, clash-pair casting
  discipline (every character exists to clash with someone), and six named
  rival-org archetypes (The Dynasty, The Ex-Teammate, The Fallen Star, …).
  Seed material for flavoring league teams and generated rosters.

## Patterns worth reusing (no file to copy)

- **Deterministic templated text**: seed `random.Random` from stable string
  parts (`"|".join(seed, scoreline, kind, author)`) to pick template variants
  — varied phrasing, reproducible output.
- **Grounded citations**: generated text may only reference stable opaque ids
  (`mem:<owner>:<slug>`); a validator rejects dangling cites. No hallucinated
  history in narrative output.
- **Golden-file determinism gate**: canonical serialization + SHA-256 digest
  committed as a fixture, CI fails on drift, `scripts/regen_golden.py` as the
  reviewed "bless" path. Stronger than run-twice determinism tests; consider
  for match-engine event logs and campaign saves.
- **Prose schema companions**: a human-facing `SCHEMA.md` kept in lockstep
  with the typed schema — worth doing for `data/*.yaml` formats.
