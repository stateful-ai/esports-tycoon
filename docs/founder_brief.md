---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T17:11:40Z'
summary: Consensus across all three agents
---

### Consensus across all three agents
- v8 plan, sequencing, and DoD are stable. Critical path: W0 smoke green + freeze → W1 keystone (`recall()` + content + golden — unblocked by M0.0-T1 pinned serialization toolchain and M0.0-T2 deterministic golden-bless script; see [`docs/m0_0_promoted_tickets.md`](m0_0_promoted_tickets.md)) → W2 (bind + copy) → W3 (rebind + recap snapshot + zero-network — unblocked by M0.0-T1 (snapshot bytes stable across machines) and M0.0-T3 shared typed `SaveError` contract (every consumer surfaces load failures the same way)) → W4 (gate w/ manifest-stamped evidence — manifest names the M0.0-T1 toolchain versions, the M0.0-T2 `make regen-golden` step, and the M0.0-T3 negative-fixture acceptance shape).
- DoD = the playtest: founder plays templated zero-API slice in 2 evenings via one-line `play` on a clean checkout; ≥1 grounded "remembered me" screenshot; pre-registered rubric recorded before play.
- Architecture invariant unchanged: memory recall is engine logic, not LLM logic.
- Hardening freeze holds; vLLM is post-gate.

### Tensions / dissent
- **chief_of_staff said "no state change, zero new tasks"** — but engineering_lead and infra_architect each surfaced 4 legitimately new playtest-quality candidates not in the active ticket list. CoS was right about plan/sequencing/DoD; wrong that no new work surfaced. Resolution: accept the new candidates; the *plan* is stable but the *task surface* genuinely grew.
- **Latency budgets at two scales** — eng proposes whole-slice (cold ≤5s, warm ≤2s/beat); infra proposes `recall()` p99 ≤50ms. Not in conflict — keep both, one guards selector perf, the other guards perceived UX.
- **Input handling surfaced twice** — eng's normalization contract (NFC, whitespace, length cap) and infra's ambiguous/empty/over-length fallback spec are complementary, not duplicates. Merge into one task with both halves.
- **Anchoring the founder** — eng wants a CI-enforced line-shape fixture+lint (replacing verbal sign-off); infra wants a README pre-play briefing paragraph. Different surfaces, both keep.

### Out of scope (do not pick up)
- Byte-identity normalization beyond W1 needs, 100-run digest, full bless script, schema-boundary CI gate, `TrainingDecision` slice — all frozen post-gate.
- vLLM bring-up beyond the existing smoke — M0.2.
- Any new architectural seam beyond the three already named (recall selector, precedent→render bind, minimum-playable rebind).

### Harness signal
BUILD phase has now re-fired 8× on this stream with no state change. CoS already has the pre-phase short-circuit guard in the candidate queue — this is the single highest-value harness improvement before the next BUILD fire. Founder Ask below.
