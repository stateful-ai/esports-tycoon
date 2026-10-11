# Silent inbox read request receipts

Candidate source: branch `codex/inbox-read-request-usage`, isolated worktree
`C:/Users/aidan/.codex/worktrees/inbox-read-request-usage`, based on verified
remote main `b9ec161f85d8dcca1152fd3d1b874c1afec77980` on 2026-10-11.
The primary checkout's dirty files, index, and HEAD were not changed.

The motivating observation was the root browser session on PR #418 candidate
`da2207fe`, fresh world REWKH, seed 2039, week 1 to week 2: opening an unread
reminder with Enter changed the unread count from 2 to 1, but retained usage
events contained no inbox read request pair. That observation is supplied by
the root agent; it is not validation of this candidate. Private page/auth/save
and raw usage evidence remains in the root's local run directory and is not
included in this change.

This candidate instruments only the actual silent POST transport. Both single
read and read-all requests share the fixed `/api/inbox/read` target and existing
request IDs, durations, outcome and HTTP status fields. Payloads, item IDs,
titles and bodies are never passed to telemetry. The server retains the older
`/api/inbox` target for report compatibility and accepts the fixed target only
when the corresponding route exists. HTTP errors return null without parsing
response bodies; network/JSON errors return null; application rejection keeps
the existing returned response. Missing or failing telemetry hooks cannot
interrupt the transport. Mock reads produce no real-request receipts.

No accepted manager decision vocabulary or deterministic GameState is changed.
Disclosure and shortcut usage is a separate candidate owned by another agent.

Regression coverage is authored in `tests/inbox_read_usage_check.cjs` and
`tests/test_inbox_read_usage.py`: success, read all, HTTP failure, network failure,
JSON failure, application rejection, missing/failing hooks, payload privacy,
fixed and legacy endpoint reports, and rejection of unknown fields/targets.
All tests, validators, simulations, analytics commands and browser acceptance
are **UNRUN**, per explicit user instruction to skip all local tests. Root
review and future genuine browser acceptance remain required; this document
does not claim runtime verification or completed gates.
