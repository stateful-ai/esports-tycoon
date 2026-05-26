---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T03:08:09Z'
summary: Cross-agent consensus
---

### Cross-agent consensus
- **Milestone = the gate.** All three agents (eng_lead, infra_architect, chief_of_staff) treat M0.1's DoD as the founder playtest itself, not infra polish. Pass = screenshot of a grounded "remembered me" moment in zero-API templated mode within 2 evenings.
- **Critical path is 5 hops:** M0.0 floor green → pure `recall(why_record, world_state, k)` → bind ≥1 precedent into templated render by cite ID through the existing grounding gate → minimum-playable 127.0.0.1 rebind (manager view + Chirper feed, 2 open-text inputs ≤120 chars, writes `recap.md` + `feed.snapshot.html`) → playtest.
- **Architectural principle (raised by infra_architect, implicit in others):** memory recall/precedent selection is **engine logic, not LLM logic**. The model (M0.2) only narrates what the engine already chose. This is what makes "remembered me" possible in zero-API mode.
- **Freeze holds.** Byte-identity, 100-run digest, negative fixtures, CI smoke, bless script, toolchain pin, golden-render extension, vLLM wiring, season runner — all parked until the gate fires.
- **`TrainingDecision` stays in M0.2** (it mutates the locked schema).
- **Same 4 new candidates surfaced independently by eng_lead and infra_architect**; chief_of_staff's "pass/fail card" is the same item as the "pre-registered playtest rubric" — merge.

### Tensions / dissent
- **None substantive.** Wave naming differs (eng_lead uses the prior doc's structure, infra_architect uses Waves 0–4, chief_of_staff uses Waves A–D) but the joins are identical: keystone before consumers; `recall()` contract + tag vocab before `week6.yaml` enrichment; `recall()` before recap rebind; pre-playtest sign-off before play; freeze honored throughout.
- **Mild duplication risk:** chief_of_staff proposed a "pass/fail card" as new work; infra_architect already had it as "pre-registered playtest rubric." One ticket, not two.

### What stays out of scope (explicit non-goals)
Byte-identity normalization, 100-run determinism digest, CI gate, bless script, negative fixtures, serializer toolchain pin, golden-render extension, LLM/vLLM mode wiring, season runner, `TrainingDecision` slice. All frozen behind the gate.

### Highest-risk seam
The `recall()` → recap binding (Wave C in CoS framing / Wave 2 in infra). If the cite-ID grammar isn't pinned *before* the templated copy pack is authored, the copy gets rewritten. Lock grammar first.
