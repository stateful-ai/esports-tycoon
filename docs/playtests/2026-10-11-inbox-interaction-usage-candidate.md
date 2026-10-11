# Inbox interaction telemetry candidate

The root agent reported a genuine browser session on frozen PR #418 build
`da2207febaf8bf577e7c49650449cf54ab9a59cc`, browser port 8560, seed 2039,
fresh world REWKH, season 1 week 1 through week 2. Enter opened an Inbox
disclosure, Space closed it, Enter reopened it, and Open Roster reached Club.
Runtime model and effort for that original played session are
`unknown (not exposed)` here. This document records the supplied observation;
this implementation agent did not perform browser gameplay or read private saves.

The supplied retained usage delta contained 37 events: three request/result
pairs (New, Advance, Save), four views, three Handbook interactions, 23 visible
time slices, and one session start. Inbox disclosure and shortcut activations
could not be counted directly. Existing profile open/close telemetry is present
in actual main; the finding does not imply every navigation surface lacks hooks.
Read-only disclosure/navigation remains outside accepted manager decisions.

Root evidence locations (local artifacts, not copied into this publication):

- `runs/playtests/2026-10-11-pr418-browser-root/collapsed-inert-dom.json`
- `runs/playtests/2026-10-11-pr418-browser-root/enter-expanded-attributes.json`
- `runs/playtests/2026-10-11-pr418-browser-root/space-collapsed-attributes.json`
- `runs/playtests/2026-10-11-pr418-browser-root/expanded-roster-route-dom.txt`
- `runs/playtests/2026-10-11-pr418-browser-support/usage-safe-delta.json`
- `runs/playtests/2026-10-11-pr418-browser-support/safe-finalize-receipt.json`

## Candidate behavior and publication boundaries

This candidate starts from verified remote main
`b9ec161f85d8dcca1152fd3d1b874c1afec77980` in a separate worktree.
It emits `inbox/item_open` or `inbox/item_close` only after shared `setOpen`
changes disclosure state. Repeated digest opens of an already open row emit
nothing. Existing mark-read behavior remains in the same path.

Shortcut receipts use `inbox/shortcut_<canonical tab>` for the nine real tab
destinations. A receipt means the existing enabled tab button's click handler
was dispatched; it does not prove asynchronous screen loading succeeded.
Aliases such as roster become club, and match becomes tactics. Missing or
disabled destination buttons produce no receipt. No message title, body, item
id, subject, category, or subjective intent enters these events.

Browser and server interaction allowlists accept the same closed vocabulary.
The existing sidecar report already groups `interaction:<target>` counts.
There are no new request/result, decision-log, simulation, or duration semantics.
Sidecar retention and best-effort delivery limitations still apply.

Regression coverage is authored for disclosure transitions, repeated digest
opens, mark-read idempotence, real alias routing, missing/disabled destinations,
absent sidecar behavior, browser/server allowlist parity, server report grouping,
and private-field rejection. All tests, syntax validators, simulations, gates,
and analytics-report commands are deliberately UNRUN at the user's explicit
instruction. No new playtest CSV observation is claimed by this child.

PR #418 accessibility changes are not duplicated here. Root should compose the
shared `setOpen` hook with #418, inspect the final source, and perform genuine
browser acceptance before considering the instrumentation runtime verified.
This document and source are staged publication; the root owns review and merge.
