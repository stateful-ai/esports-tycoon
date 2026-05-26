---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T16:37:59Z'
summary: Consensus across all three agents
---

### Consensus across all three agents
- **Milestone:** M0.1 — The Thesis Test. Exit = founder gate (playtest screenshot).
- **Keystone:** precedent recall is engine logic (pure deterministic `recall(why_record, world_state, k=3)`) bound into templated render by cite ID. Zero-API path is the gate; vLLM is a post-gate upgrade behind the same adapter.
- **Sequencing:** Wave 0 (smoke + freeze) → 1a (contracts-only PR, no selector code) → 1b (selector + planted precedent + golden) → 2 (bind + copy pack + verbatim recap E2E) → 3 (web/recap rebind + `play` one-liner + snapshot + zero-network) → 4 (pre-registered rubric + playtest + evidence packet).
- **Frozen post-gate:** byte-identity normalization, canonical YAML serializer pinning, CI/`make test`, 100-run digest, schema-boundary gate, deterministic bless script, typed SaveError, RI validator polish, TrainingDecision slice. All nine hardening tickets stay frozen until the gate fires.
- **DoD floor:** `recall()` purity + golden, planted-precedent text verbatim in `recap.md` under LOCKED_SEED, zero-bind fallback exercised, snapshot golden green, zero-outbound-network assertion green, evidence packet self-sufficient.

### Tension: new candidates this pass
- **engineering_lead** proposes 4 new candidates.
- **infra_architect** and **chief_of_staff** explicitly hold the line at zero new tasks (active backlog is already dense; adding to it is planning bloat against a 2-evening budget).

**My adjudication.** Two of the four are genuinely new risk surfaces not covered by existing tickets and cheap to land:
1. **In-process determinism guard** — same-process repeated invocation produces byte-identical output. Catches module-level state, lru_cache, import-order leakage that the load-once round-trip test won't. Real failure mode, cheap test.
2. **Recall-side input snapshot fixture** — checks in `(why_record, world_state)` for the locked seed so recall-golden re-runs against a frozen fixture, not a live load. Cleanly separates upstream WorldState/WhyRecord drift from recall ordering drift when something breaks.

The other two I'm dropping as polish:
- **W0 entry-gate sentinel checklist** — duplicates the existing Wave 0 entry-gate smoke ticket; fold the assertion strings into that ticket's acceptance, don't mint a sibling.
- **Single-source gate clock** — real but tiny; can land inside the `manifest.json` generator ticket. No need for its own row.

### Out of scope until the gate fires
Anything that doesn't move W0→W1a→W1b→W2→W3→W4. If a new idea isn't on the critical path, log it for M0.2.

### Conflicts with approved decisions / memory
None observed. Plan respects the freeze and the zero-API templated path as the gate.
