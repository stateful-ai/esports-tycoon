# Decisions

Append-only log of founder/team decisions encoded in the codebase.

## 2026-05 — Templated content first, LLM second
The content adapter ships a templated default and an opt-in LLM backend.
Templates are cheap, deterministic, and good enough for the core loop;
the LLM backend is reserved for moments where templated prose feels flat.

## 2026-05 — Tycoon loop is the M0 anchor
Everything else (Chirper, halftime narration, save/load polish) lands
*after* a player can complete one full Now-Next-Later cycle end-to-end.
