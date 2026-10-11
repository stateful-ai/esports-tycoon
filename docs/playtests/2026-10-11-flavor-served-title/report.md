# Served flavor title acceptance, 2026-10-11

The Dashboard receipt now preserves the title shown for the clicked flavor
moment. `eventBlock` captures its rendered title, then copies the successful
action response with that title after the existing world/team identity guard.
The action payload, response effects, deterministic fallback title, campaign
mechanics, RNG, and save model are unchanged.

Fresh real Chromium play used this isolated worktree at parent HEAD
`7854dc70899a967738b9f64f7ca54cffa8bcecdd`, with the narrow UI change dirty,
runtime `gpt-6.1-sol` / `medium`, game version recorded by the logger, and the
private world FLV42, seed 2038, S1 W12. The campaign was copied from the
immutable original week-12 fixture (SHA256 in setup-receipt.json).
The serving sidecar supplied `Community clinic: a small group invitation`;
generation was disabled, so no LLM provider was called. This is a controlled
cached-overlay acceptance session, not evidence of live LLM generation.

Four meaningful intents were written before actions and completed in this
session's separate actions.csv. The native Dashboard showed the cached title
and original grounded choices. Clicking `Send a small group` returned the
deterministic title `A community clinic asks for Team Nexus`, but the displayed
receipt kept `Community clinic: a small group invitation`. The receipt showed
the realized community sentiment row 59.1 -> 58.1 (-1) and the original outcome
message. Independent `/api/state` readback showed no pending clinic. Club and
Dashboard navigation preserved that receipt. Save and reload retained the
resolved choice and cleared the temporary receipt. Browser screenshots and
exact public response/DOM/state readbacks are preserved here. No page errors
were recorded. Receipt screenshots were visually inspected.

Saved telemetry retains all 55 pre-existing decisions and exactly one new
`flavor_choice` at index 55, `source=web`, `team_nexus`, S1 W12, event
`8f43d112fb4700ed`, choice `small_group`. Accepted decision coverage is 1/1.
All telemetry snapshots are unchanged. The retained browser stream has 18
events over two page sessions, two complete success-200 attempt/result pairs
(flavor and save), zero unmatched attempts, and zero orphan results. The
three navigation/save intentions are outside the accepted-decision vocabulary;
CSV annotations distinguish those from the accepted choice. Best-effort usage
retention does not prove complete duration funnels or attention.

An initial raw historical baseline comparison was unequal because current
save migration changes schema_version and players. That failed comparison is
reported in baseline-comparison.json. Loading the unchanged historical
resolved baseline through the current GameState loader, without replaying or
resolving any actions, gives a save byte-identical to this browser save:
`cc518817796c95051d132dc19c9cf7ddce59fb1c49c03e462478d3d80448e190`.
This migration-qualified comparison is acceptance reconciliation, not a fresh
determinism gate. The original baseline and source-qualified original evidence
were not overwritten or relabeled as current validation.

All 26 checked historical files, including the canonical shared actions.csv,
original session evidence, and PR370 integration qualification, remain
byte-identical (historical-preservation.json). New raw evidence and source
snapshots use scoped `-text -whitespace` attributes. This session leaves the
primary dirty checkout, user server 8421, and other agents' servers untouched.
cleanup-receipt.json identifies and confirms termination of only the owned
8541 process family; the private browser was closed and 8541 is free.

The flywheel was read before play and now contains two learnings and one
pain-point; before/after receipts are preserved. The important lesson is that
served flavor prose and deterministic action prose may differ while naming
the same event. Visible continuity must be checked at the browser boundary.

The CJS regression source adds cached/native/empty/markup title cases,
response immutability and effect preservation, while retaining world-switch,
team-switch and rejection scenarios. These regression cases are UNRUN.
No local pytest, Node regression tests, or expensive gates were run, per the
user's explicit instruction. Fresh remote CI status must be read at the pushed
head; historical test and native gate records are historical only.
