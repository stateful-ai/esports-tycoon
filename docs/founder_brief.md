---
type: stream_doc
title: founder_brief
stream: esports-tycoon
updated: '2026-05-28T05:25:39Z'
summary: Where we are
---

### Where we are
- 9th BUILD re-fire on esports-tycoon. Ticket state (32 tickets, 14 done / 18 active) is identical to v8. No new founder decision, no build signal since v8.
- v8 remains canonical. engineering_lead's v9 is a re-issue under required headings + 4 enforcement-gap candidates; infra_architect reconciles to the same plan + 2 small gate-quality candidates; chief_of_staff held the line and minted no v-bump.

### Cross-agent consensus
- **Critical path:** Wave A foundation → Wave B-1a contracts-only PR (cut-line, founder-signed) → Wave B-1b selector against frozen contracts → Wave C bind/copy in parallel → Wave D founder playtest. Unanimous across all three agents.
- **Architecture invariant:** recall is engine logic; templated mode binds precedents directly; M0.2 LLM mode only narrates what the engine already chose. Unanimous.
- **DoD:** under `LOCKED_SEED`, golden + round-trip + recall + recap snapshot + zero-egress all green; ≥1 grounded "remembered me" screenshot at the fixed recap marker; self-describing evidence packet; founder plays in 2 evenings via one-line `play`; gate decision logged.
- **Two-evening budget + kill switch + daily heartbeat note** stay as the forcing function.

### Tensions / dissent
- **None substantive.** engineering_lead and infra_architect both re-issue under the same critical path. chief_of_staff dissents only on *whether re-issuing is worth doing* — they argue v8 is canonical and v-bumping is itself bloat. That dissent is a process call, not a plan disagreement, and is best resolved by the pre-phase short-circuit harness fix (already logged as a recurring improvement signal, seen x9).
- The 6 new candidates this round are non-overlapping enforcement seams, not duplicates — worth accepting all 6.

### Out of scope for M0.1
Multi-slice library, hosted-LLM swap, M1 memory-compounding scaffolding, vLLM safety re-validation, observability beyond the run-log, `TrainingDecision` (held to M0.2).

### What unblocks the next motion
1. Wave-A foundation drop lands as a single PR.
2. Wave-B-1a contracts-only PR merged + tagged `wave-b-contracts-frozen` + founder sign-off.
3. Then Wave-B-1b selector + Wave-C copy authoring can run in parallel.
4. Wave-D dry-run on clean checkout before the founder playtest.
