---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T05:56:22Z'
summary: Where the three agents agree
---

### Where the three agents agree
- **Milestone framing is locked.** M0.1 = founder plays templated zero-API slice (practice → match → fallout, 2 open-text inputs ≤120 chars) and screenshots ≥1 grounded "remembered me" moment within 2 evenings. Gate path is templated, not vLLM.
- **Critical path is W0 → recall → bind → rebind → playtest.** Same 5-hop chain in all three responses.
- **Three new code seams only:** `recall()` selector, precedent→render binding by cite ID, minimum-playable web/recap rebind. Everything else is reuse.
- **Freeze list holds.** The 9 hardening tickets (byte-identity, serializer polish, CI gate, toolchain pin, bless script, negative fixtures, shared `SaveError`, WhyRecord digest, `make test`) stay frozen until the gate fires.
- **Architecture invariant:** precedent recall is engine logic, not LLM logic. One pure deterministic selector ranks canned memories; templated copy pack binds them by cite ID through the existing grounding gate.
- **Same 4 new candidates** emerged independently from Engineering Lead and Infra Architect — strong signal these are real gaps, not over-emission.

### Tensions / dissent
- **Chief of Staff emitted zero new tasks**; EL + Infra both emitted the same 4. Not a real conflict — CoS was reconciling 3 newly-landed tickets (`slice_id`, dropped-precedent logging, clean-checkout dry-run) into existing waves and treated this as a refresh, not a re-plan. The 4 new candidates from EL+Infra are upstream of authoring (Waves 1–2) and downstream of binding (Waves 2 & 4); they don't conflict with CoS's wave assignments, they fill gaps inside them.
- **Wave numbering:** EL/Infra use Waves 0–4; CoS uses Waves A–D in `m0_gate_build_execution_plan.md` v3. Substantively identical sequence. Pick one naming when committing.

### Out of scope (do not touch this milestone)
- vLLM beyond the demo-gate behind the adapter
- Byte-identity normalization, schema-boundary CI, serializer polish beyond stable dump
- `TrainingDecision` slice (held to M0.2)
- Canonical WhyRecord digest (already rejected)

### Why the 4 new candidates matter
- Without **`recall()` input contract**: Wave 1 planted-precedent author and the selector implementer guess at the same shape independently → drift.
- Without **k>1 surfacing rule**: copy pack author and recap layout author re-decide the same question; recap golden has no stable expectation when `recall()` returns 2 or 3.
- Without **end-to-end recap assertion**: tests stop at "ordered list" instead of "founder sees the line"; bind succeeds but the text silently never lands.
- Without **playtest artifact directory**: gate evidence (recap, feed snapshot, screenshot, rubric card, debrief) scatters; the pass/fail note has nothing concrete to reference.
