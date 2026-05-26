---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T03:53:47Z'
summary: Cross-agent consensus
---

### Cross-agent consensus
- **The milestone is the gate, not the code.** All three agents: M0.1 DoD = founder plays practice→match→fallout in zero-API mode and screenshots ≥1 grounded "remembered me" moment within 2 evenings, against a pre-registered rubric.
- **Critical path is 5 hops, unchanged:** W0 M0.0 closeout → `recall()` selector (pure, deterministic, engine-side) → bind ≥1 precedent into templated render by cite ID → minimum-playable web/recap rebind → playtest.
- **Freeze stands.** The 9 hardening tickets (byte-identity, CI bless script, negative fixtures, toolchain pin, shared `SaveError`, schema-boundary gate, etc.) stay parked until the gate fires. No agent wants to relitigate this.
- **Parallelism opportunities:** Wave 2 copy authoring can start once Wave 1a's planted precedent shape is locked; Wave 3a two-input spec can land in parallel with Wave 1b selector code. Otherwise serial.
- **Four prior candidates are now active tickets** (recall golden fixture, cite-ID grammar, two-input→WorldState spec, pre-registered rubric) — correctly dropped from candidate lists by all three agents.

### Dissent / tensions
- **None substantive.** Engineering Lead and Infra Architect propose different *new* candidates but they're additive, not conflicting. Chief of Staff emits zero new tasks and flags this as a phase-re-fire-without-state-change (seen x6) — worth noting as a recurring signal but not a blocker.
- **Minor framing difference:** Engineering Lead frames the entry-gate as a `make`/`pytest` target gating Wave 1 start; Infra Architect treats W0 closeout as verification only. The smoke script makes the gating mechanical — recommend adopting it.

### New work proposed this round (5 candidates, all gate-adjacent)
1. **Wave 0 entry-gate smoke script** (eng_lead, ops/high) — mechanical gate before Wave 1 starts.
2. **Recap layout convention for the bound precedent line** (eng_lead, design/high) — fixed scannable position + visual marker so the "remembered me" beat lands visually.
3. **One-line founder-facing run command + README quickstart** (eng_lead, docs/medium) — `make play` so the gate doesn't fail on UX friction.
4. **Playtest debrief template tied to R1/R2/R3** (eng_lead, docs/medium) — fills regardless of pass/fail, routes M0.2/M1 vs wedge revisit.
5. **Zero-bind recap fallback spec** (infra_architect, eng/medium) — defines what the recap renders when `recall()` returns zero grounded precedents, prevents fallback from accidentally satisfying the gate.

### Out of scope (do not touch)
- vLLM mode, byte-identity normalization, CI bless script, schema-boundary gate, WhyRecord digest, toolchain pin, shared `SaveError`, golden-render extension, `TrainingDecision` slice — all frozen post-gate.

### Risk watch
- **Recurring phase-re-fire-without-state-change** (Chief of Staff, seen x6 across build/scope/plan). Worth the pre-phase short-circuit guard already in candidate queue, but not blocking.
- **Zero-bind silent pass** — if `recall()` returns nothing and the recap renders a neutral line, the rubric must explicitly treat that as "no remembered-me moment fired" (not pass). Infra Architect's fallback spec closes this.
