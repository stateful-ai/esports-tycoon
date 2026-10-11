# All sponsor slots in Company run rate

Authentic copied world 26UHC, seed 2038, Team Nexus, S2 W1. Source build
`20273cd7ab885e7d409dec46f511d915d6e08ff4`; acceptance tested that build with the
three-file gap39 patch dirty. Runtime model and effort were not exposed and are
recorded as unknown. Original root-session receipts remain attributed to the
root session; this session only owns its new observations.

Root's original Stream signing receipt reports OrbitCast steady 9,400 cr/week,
22 weeks, no signing bonus. Original S2 W1 finances had live net 66,490 while
the first cash projection already showed 75,890. Own browser Company view now
shows Stream sponsor 9,400, Apparel sponsor 0, player Streaming 8,968, income
124,490, expenses 48,600 and net 75,890. The first projected net is 75,890;
the projection path was not changed. See `company-dom.yml`, `company.png` and
the independent GET-only `finances-after.json` readback.

The first IAB attempt was blocked by the copied world's taken human seat.
Clearing only the copied session registry did not enable the browser Join UI.
Direct HTTP recovery first hit a UTF-8 transport decoding error before any
request and then a 409 Join response. Both blocked intents were retained.
The original copied session registry was restored; an isolated named CLI
browser received that copied test identity, with secret-bearing CLI output
discarded. That browser opened Company and saved through the UI. No original
save, root session, user server or user browser was modified.

Saved-state audit: 104 accepted actions and 23 snapshots before and after,
identical action_log, telemetry_snaps and every top-level state field. Original
and post-browser-save bytes both hash to SHA256
`68d1cb1ff58813416eb23c92caf94d1c8046e7286e111fa4682155ad7e778663`.
There were zero new gameplay decisions, so decision capture is 0/0 (not
applicable). Three 21-column rows live in the per-session `actions.csv` shard;
the canonical actions.csv was not edited. Two rows are blocked and one met.

Retained browser usage records Company Finances view and the browser Save
attempt/result pair, request 11, HTTP 200. Save pairing is 1/1 with zero
unmatched attempts or orphan results. Read-only finances GET and blocked lobby
Join clicks do not have corresponding retained request events: do not infer
those from HTTP responses or views. Direct HTTP recovery emits no browser
usage. `ui-usage-report.txt` covers this isolated server only, including lobby
bootstrap sessions, and `telemetry-report.txt` covers this copied save only.
Usage is bounded best-effort evidence, not proof of exact attention duration.

`original-evidence-hashes.json` records SHA256 over original raw receipt bytes,
without decoding or line-ending normalization. The original receipts contain
Windows CRLF; copies and hashes must preserve those bytes. Durable original
root evidence is `docs/playtests/2026-10-11-offseason-rebuild` in root's history;
absolute raw paths are included in the manifest.

Regression tests were added for all five slot estimates, per-win terms,
projection expiry, empty/expired slots and unchanged serialized state. They
are **UNRUN locally** under the user's override. No local pytest or expensive
gate process ran. Node syntax and git whitespace checks completed successfully.
Exact-head remote CI is the merge gate; this report does not claim tests pass.
Apparel with an active contract is regression-test coverage, not an observed
browser contract in this save (the slot is locked and empty).

Learnings: (1) the existing projection provided an independent public check
for an omitted active deal; (2) explicit separate Stream sponsor and player
Streaming rows make both revenue sources understandable. Pain point: the
lobby Join UI labels an existing human seat taken even after copied session
ownership is cleared, so fixture identity restoration was necessary.
Flywheel tools were unavailable in the exposed tool inventory; these findings
are retained here for later ingestion instead of claiming a remote recording.
