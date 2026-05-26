---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-26T08:05:05Z'
summary: Consensus across all three agents
---

### Consensus across all three agents
- **Single milestone, single gate.** Founder plays the templated zero-API slice (practice → match → fallout, 2 open-text inputs ≤120 chars) and screenshots ≥1 grounded "remembered me" moment within 2 evenings. The gate *is* the DoD.
- **Architecture invariant.** Precedent recall is engine logic, not LLM logic. A pure deterministic `recall(why_record, world_state, k=3)` + templated copy pack bound by cite ID through the existing grounding gate. vLLM is post-gate.
- **Critical path (5 hops).** Wave 0 smoke green → `recall()` selector → bind ≥1 precedent by cite ID → minimum-playable web/recap rebind → founder playtest. Wave 2 copy can parallelize with W1 once the planted-precedent shape is locked.
- **Determinism floor is narrow.** Golden round-trip + same-seed → same-WhyRecord + `recall()` purity + `recall()` golden fixture under `LOCKED_SEED`. The 9 hardening tickets (byte-identity, 100-run digest, CI/bless/negative fixtures, toolchain pin) **stay frozen behind the screenshot**.
- **Kill switch.** Wave time-tripwire ships a templated-baseline (single hard-coded precedent) if W1/W2 overrun — debrief must flag baseline mode.

### Dissent / tension to resolve
- **Engineering & infra: 8 new candidates.** Engineering wants gate-adjacent safety nets — fixture-edit safety (does adding the planted precedent shift the WhyRecord digest?), templated copy-pack cite-ID lint at load time, a single frozen `recap.md.j2` owning layout + zero-bind + dropped-cite footer, and an explicit negative-drop assertion for un-resolvable cites. Infra wants reproducibility/audit/quality — git-SHA + Python + deps-hash embedded in every run-log, a Chirper feed content pack tied to the planted precedent, ambiguous-input routing fallback for the 2 open-text inputs, and an evidence-packet `manifest.yaml` + wall-clock budget.
- **Chief of Staff: zero new tasks.** Argues v5 is canonical, nothing has changed since the last fire, the backlog already covers every implied ticket, and the right move is to *ship Wave A*, not write more reconciliation.
- **My read.** CoS is right that the backlog is dense and Wave A is the bottleneck. But three of the 8 candidates are genuinely gate-protective and should land *before* the playtest: **fixture-edit safety** (silent WhyRecord drift would invalidate the golden), **copy-pack cite-ID lint** (silent unresolved cites would corrupt the screenshot), and **grounding-gate negative drop assertion** (proves the gate behaves as advertised). The other 5 are nice-to-have post-gate or already implicit in active tickets (e.g., evidence-manifest overlaps `gate.md` summary; git-SHA can be a one-liner inside the existing run-log schema ticket; Chirper content is design work, not a gate prerequisite).

### Out of scope (explicitly frozen until the screenshot lands)
Byte-identity normalization, negative fixtures, schema-boundary CI gate, toolchain pin, deterministic bless script, `make test` CI, golden-render extension to templated, WhyRecord canonical digest, M0.2 LLM-mode wiring + structured-output spike.

### Approved-memory check
No conflict with prior approved decisions. The "engine-side recall, templated default, vLLM post-gate" invariant is consistent with the seed-stage product principle that channels + persistent agents + approved memory must prove out before integrations.
