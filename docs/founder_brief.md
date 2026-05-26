---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T06:54:36Z'
summary: Cross-agent consensus
---

### Cross-agent consensus
- **Plan is canonical** in `m0_1_build_execution_plan.md` / `m0_gate_build_execution_plan_v4.md`. All three agents reuse it verbatim — no re-planning needed.
- **Critical path (5 hops):** W0 entry-gate smoke green → `recall()` selector → bind ≥1 precedent into templated render by cite ID → minimum-playable web/recap rebind → founder playtest (the gate).
- **Architecture invariant unchanged:** memory recall is engine logic, not LLM logic. One pure deterministic `recall()` selector; templated copy binds by cite ID; vLLM is a post-gate upgrade behind the same adapter.
- **Determinism floor is narrow:** golden round-trip + same-seed→same-WhyRecord + `recall()` purity + `recall()` golden fixture. The 9 hardening tickets stay **frozen until the gate fires**.
- **DoD is the screenshot:** founder plays practice → match → fallout (2 open-text inputs ≤120 chars) in zero-API mode within 2 evenings and screenshots ≥1 grounded "remembered me" moment, judged against a pre-registered rubric.

### Tensions / dissent
- **Candidate volume.** Engineering proposed 4, infra proposed 6, CoS proposed 0. I read CoS as correct in spirit (don't bloat the queue) but too strict — several of these (LOCKED_SEED, run-log schema, line-shape pre-approval) materially de-risk the gate. Consolidated to 7 total under cap.
- **Rubric outcomes.** Engineering's plan calls for pass/fail. Infra wants pass/fail/**ambiguous** with a pre-registered follow-up for the ambiguous case. I'm folding "ambiguous" into the existing pre-registered pass/fail card ticket as an amendment, not a new task.
- **Schedule discipline.** Engineering added a Wave time-tripwire (W1+W2+W3 ≤ 1 evening → ship-templated-baseline kill switch). Infra didn't mention this. I'm keeping it — single-founder execution risk is real and the tripwire is cheap.
- **Pre- vs post-render sign-off.** Infra distinguished founder pre-approval of line *shape* (before Wave 2 authoring) from post-render design sign-off (already a ticket). Engineering only had the post-render one. Keep both — they catch different failure modes.

### Folded (not new tasks)
- Chirper feed content → fold into existing templated copy pack ticket.
- Git SHA + dep versions in evidence → fold into the existing designated evidence-packet directory ticket (amend acceptance).
- Ambiguous rubric outcome → fold into the existing pre-registered pass/fail card ticket.

### Out of scope (frozen until gate fires)
Byte-identity normalization, 100-run determinism digest, schema-boundary CI gate, toolchain pin, deterministic bless script, `make test` + CI smoke, golden render extension, shared typed `SaveError`, canonical WhyRecord digest, negative fixtures. All recorded. None move the screenshot.
