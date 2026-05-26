---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T07:29:16Z'
summary: Consensus across all three agents
---

### Consensus across all three agents
- **Milestone = the gate.** M0.1 ships when the founder plays practice → match → fallout in zero-API mode in ≤2 evenings and screenshots ≥1 grounded "remembered me" moment against a pre-registered rubric.
- **Critical path is 5 hops.** Verify W0 (M0.0 closeout) → pure `recall()` selector → bind ≥1 precedent into templated render by cite ID → minimum-playable web/recap rebind → founder plays.
- **Architecture invariant.** `recall()` is engine-side, pure, deterministic — *not* LLM logic. Zero-API templated is the gate path; vLLM is a post-gate upgrade behind the same adapter.
- **Freeze holds.** Byte-identity, CI/bless, negative fixtures, toolchain pin, schema-boundary gate, typed `SaveError`, WhyRecord digest — all frozen until the gate fires.
- **Wave shape.** W0 closeout → W1 contracts + selector + planted precedent → W2 bind + copy → W3 rebind + `play` one-liner → W4 gate. Engineering_lead and chief_of_staff use 4-wave numbering; infra_architect splits W1 into 1a (contracts) / 1b (selector + content) — same DAG, finer label.

### Where they diverge
- **New tasks vs. zero new tasks.** Chief_of_staff held the line: 7 newly-landed tickets already slot into existing waves; mint nothing. Engineering_lead and infra_architect each surfaced 4 candidates (8 total) — each removes a specific guess from the playtest the current backlog does not cover. My read: chief_of_staff's discipline is correct in spirit, but two of these candidates (Chirper content, reproducible answers fixture) are gate-blockers in disguise.
- **Founder-visible bind indicator.** Engineering_lead wants a "N cited memory" chip in the live manager view in addition to the recap. The recap already places the bound-precedent line in a fixed scannable position with a marker — the chip is duplication. Drop.
- **A/A baseline sanity.** Engineering_lead alone proposed this — running the same slice with `recall()` stubbed empty to prove the bind is visible work. Worth doing; cheap; protects against a false-positive gate.

### What stays out of scope
- All 9 hardening tickets (byte-identity, CI, bless script, etc.) — frozen.
- vLLM mode beyond what's already gated — post-gate.
- `TrainingDecision` slice — held to M0.2.
- Any new infra not tied to the gate decision.

### Risk posture
- Highest-risk seam: `recall()` → render binding. Wave-time tripwire + ship-templated-baseline kill switch guarantees a gate decision even if W2/W3 overrun.
- Sanity floor: A/A baseline replay before founder plays, so the bound-precedent line is provably doing visible work.
