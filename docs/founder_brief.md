---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T04:28:28Z'
summary: Cross-agent consensus
---

### Cross-agent consensus
- **Milestone framing:** M0.1 = the founder gate. A byte-reproducible save nobody has played proves nothing.
- **Architecture invariant:** `recall(why_record, world_state, k)` is pure engine logic, not LLM logic. Templated copy pack binds by cite ID. vLLM is a post-gate upgrade behind the same adapter.
- **Critical path (5 hops):** verify M0.0 closeout green → `recall()` selector → bind ≥1 precedent via cite ID → minimum-playable web/recap rebind → founder playtest.
- **Wave structure:** W0 entry-gate smoke + freeze → W1 `recall()` + vocab + planted precedent + golden fixture → W2 bind + templated copy + zero-bind fallback → W3 rebind 127.0.0.1 app + recap + run command → W4 sign-off + pre-registered rubric + playtest + debrief.
- **Frozen behind the gate:** byte-identity, 100-run digest, negative fixtures, schema-boundary CI, toolchain pin, bless script, `make test`/CI, templated golden extension, shared `SaveError`, WhyRecord digest. 9 tickets; do not work them until the screenshot lands.
- **DoD = the gate:** founder screenshots ≥1 grounded "remembered me" moment in ≤2 evenings, judged against a pass/fail rubric pre-registered *before* play.

### Tensions / divergence
- **Candidate-task volume.** Engineering Lead proposed 4 new (wave-gate script, status one-pager, founder-time tripwire, clean-checkout dry-run). Infra Architect proposed 2 (dropped-cite logging, deterministic `slice_id`). Chief of Staff (prior pass) proposed 0. No factual conflict — different thresholds for "genuinely new work."
- **Resolution.** The two infra-architect candidates are product diagnostics (without them, a failed playtest has no forensics). The clean-checkout dry-run is the only engineering-lead candidate that's product-bearing — it catches a broken `play` command *before* the founder sits down. The other three (wave-gate enforcement script, status one-pager, time tripwire) are process scaffolding that overlaps with the already-live Wave 0 smoke ticket and debrief template; folding into a one-line "later" note rather than minting tickets.

### Out of scope (explicit)
- Anything that hardens the determinism floor beyond M0.0's existing golden round-trip.
- vLLM bring-up beyond the existing smoke (already completed).
- `TrainingDecision` slice (held to M0.2 by live ticket).
- New product surface — copy pack must be authored against the *specific* recalled-precedent shape, not generalized.

### Risk register (single highest)
**Wave B recall→render seam.** If `recall()` returns a precedent whose cite ID the templated pack can't bind (off-grammar / unresolved), the founder sees the zero-bind fallback and the thesis isn't actually proven by the screenshot. Mitigations already in flight: pin cite-ID grammar *before* copy pack (active ticket), zero-bind recap fallback spec (active ticket), grounding gate drops un-resolvable cites. The new dropped-cite logging task closes the diagnostics gap.

### Later (do not mint as tickets now)
Wave-gate enforcement script · M0.1 wave-status one-pager · founder-time tripwire on the 2-evening window. Revisit only if the gate slips.
