---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T08:51:45Z'
summary: Cross-agent consensus
---

### Cross-agent consensus
- **Milestone:** M0 gate — founder plays templated zero-API slice end-to-end and screenshots ≥1 grounded "remembered me" moment within 2 evenings.
- **Architecture invariant:** memory recall is engine logic, not LLM logic. Templated mode binds precedents directly by cite ID; LLM mode is post-gate.
- **Four-wave structure:** W0 closeout + freeze → W1 `recall()` + planted precedent + golden → W2 bind by cite-ID + templated copy → W3 minimum-playable rebind → W4 the gate (founder plays).
- **Critical path:** Wave A/0 keystone (package scaffold + schemas + canned-save loader + `LOCKED_SEED`) → `recall()` selector (highest-risk seam) → bind → rebind → playtest.
- **Determinism floor stays narrow:** golden round-trip + recall purity + recall golden fixture + recap snapshot. 9 hardening tickets stay frozen until the gate fires.
- **3 newly-landed tickets slot cleanly:** fixture-edit safety check (Wave B), copy-pack cite-ID lint (Wave C), grounding-gate negative drop assertion (Wave C). No re-sequencing needed.

### Dissent / tension
- **Engineering_lead + infra_architect both proposed 4 essentially identical new candidate tasks**, framing them as gaps the existing backlog does not cover:
  1. Declared read-set contract for `recall()` (guards against silent coupling to non-canonical WorldState).
  2. Full `recap.md` snapshot golden under `LOCKED_SEED` (current backlog only asserts the verbatim precedent line; this catches drift in layout, marker, dropped-cite footer, fallback).
  3. Zero-outbound-network assertion (the "zero-API" claim is currently untested — only enforced by convention).
  4. Evidence-packet `manifest.json` stamping `commit_sha`, `LOCKED_SEED`, `slice_id`, timestamp, per-file SHA-256 (makes the gate decision reproducible from the artifact alone).
- **Chief_of_staff held the line: zero new tasks.** Their reasoning: the 3 newly-landed tickets already slot cleanly; backlog covers the critical path; resist re-fire churn (now ~10 tickets/re-fire landing).
- **Reconciliation (mine):** the two independent leads converging on the same 4 gaps is signal, not noise. Each closes a "gate would not be reproducible / would not actually enforce zero-API" hole that the CoS hold-the-line note didn't address. Recommend approving all 4 and tagging them into the waves the leads already assigned.

### Out of scope (stay frozen until gate fires)
- 100-run determinism digest, byte-identity contract (beyond the recap snapshot), serializer-pin, CI gate, negative-fixture suite, `TrainingDecision` slice, LLM-mode narration — all post-gate.

### Open risks
- Wave A keystone (package scaffold + schemas + loader) is the single unbuilt blocker for everything downstream; if W0 entry smoke doesn't go green, the freeze doesn't record and W1 can't start.
- The "remembered me" line *shape* needs founder pre-approval before W2 copy authoring — currently active but not done.
