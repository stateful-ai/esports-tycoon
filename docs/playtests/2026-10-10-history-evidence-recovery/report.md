# Published playtest history evidence reconciliation

This offline audit addresses both PR362 review comments (4238542612 and
4238542617) against remote main `64ee15f19f7acf80a2dbb7e5035d8c037128fea6`.
It creates no gameplay decisions, browser requests, or replacement receipts.
The current observation was prelogged before the audit and finished afterward;
the missing screenshot and old receipts remain explicit limitations.

## Retained roster recovery evidence

The PR362 review snapshot lacked `2026-10-08-roster-hint` artifacts. Current main
already contains 13 original files from PR351 (`4b04824`), including the report,
rejection, ledger, usage baseline/end/stream/report, and historical test results.
All 13 match the primary checkout byte for byte; the audit records their hashes.
These are recovered references to retained original evidence, not a new playtest
or a fresh verification of the historical test build.

Independent recount of `../2026-10-08-roster-hint/decision-evidence.json` verifies
five indexed exported decisions: release, two negotiation opens, accepted offer,
and advance, all web/team_nexus/S1W1. The export reports one weekly snapshot.
The 58 retained usage events contain 47 world95WTN events and 11 lobby events.
Pairing by page-session plus request ID gives eight attempts and eight results,
seven HTTP200 and one HTTP409, with no unmatched attempts or orphan results.
The rejected advance has no accepted-decision record. Decision and usage
denominators remain separate. The export retains the accepted offer parameters,
but no original save was recovered for a fresh roster/contract setting readback.

`market.png`, referenced by historical roster step4, was not found in the
named session folders across registered worktrees or the related runs inspected
in `recovery-audit.json`. The historical claim that this screenshot was captured
remains **unverified**. Retained `market/players` usage supports navigation only;
it cannot prove what was visually displayed. Historical step4 keeps its original
outcome and annotation; this append-only correction narrows the supported claim.
The rejection JSON supports the historical409 response/unchanged week and bank,
and the exported ledger supports accepted decisions; neither fills the screenshot
gap. No screenshot or request was invented.

## Interrupted budget session

The five blank analytics annotations belong to
`2026-10-08-mid-split-budget`, steps1-5. Their **effective status is unverified**.
The per-row mapping is in `recovery-audit.json`. The existing session report and
step7 correction already explain that receipts were never exported, the retained
save had the36-action baseline, and observed in-memory release/signing changes
could not be reconciled as durable decisions. This audit does not duplicate that
gameplay correction or rewrite the old observations, expectations, timestamps,
or blank historical annotations. Analytical consumers must apply the explicit
effective mapping instead of treating blank annotations as verified coverage.

The separate flavor correction, October10 flavor-hint step6, already proves two
original accepted decisions at indices27/28; its root verification remains in
`../2026-10-10-history-reconciliation/`. It does not provide budget receipts.

## Append-only publication snapshot

The frozen root-owned snapshot contains684 unique session/step keys, SHA256
`8bd8fa790427a14beeed479f805483e9e77002966a28b035872adbb500333556`.
Current main's597-row CSV is an exact byte prefix. This PR preserves all684 raw
rows byte for byte and appends one current offline correction, giving685 rows.
It copies132 existing root-owned files from the five October10 session folders
missing on main; each source/destination hash is retained in the audit. No
unrelated career, save, session credential, source, or game file is imported.
This snapshot deliberately excludes later concurrent root appends.

Validation: the fresh unfiltered full suite is running on this checkout's
unchanged source, using the primary Windows venv with PYTHONPATH/import verification
pointing to this worktree. The native writer will retain its exit code, log,
source freeze, and result before commit. Historical test logs are archival evidence
and are not this PR's gate. Documentation-only scope does not trigger balance,
pacing, snowball, or floor gates.

Two learnings: merged evidence can resolve an older review snapshot without
reconstructing events; request pairing needs both session and request ID.
Pain point: screenshot references and blank historical annotations require
explicit append-only qualification when raw receipts are unavailable. These
forensic findings are local; no new gameplay flywheel observation is claimed.

## Final publication and completed validation

The full unfiltered native gate completed at2026-10-10T21:56:41.938594Z:
**1274 passed in7246.32s (2:00:46), exit0**. `full-result.json` verifies all612
raw frozen source/test/scripts/data/config files unchanged; the imported package
was this worktree's `src/esports_sim`, and the tested parent remains64ee15f.
The log's terminal summary was independently read before any publication update.

Root's sole writer appended this audit's exact correction after its698 existing
rows, then appended the clinic and promise sessions. The final approved immutable
publication snapshot has **724 unique rows**, SHA256
`0597857c221b2f60818472dfd1c07eca7435d081759d6e00b6ac659393604697`.
It preserves exact597,684,698,699 and706 byte prefixes. The correction is row699,
with its original timestamps and all21 fields intact. The initial685-row snapshot
is archived byte-identically as `snapshot-685.csv`, and `recovery-audit.json`
remains unchanged; its685 final count describes the original forensic snapshot.
The earlier699 handoff is retained as `snapshot-699.csv`. These archives explain
the publication ordering without changing historical observations.

After the native gate passed, this documentation-only publication imported the
immutable724 snapshot and71 additional byte-identical evidence files from the
approved sponsor, rookie-clinic, promise-original and promise-renewal folders.
The39 rows in those four shards match the canonical rows in all21 columns;
the original132 copied files still match their frozen hashes. The separate
`publication-audit.json` records these checks, prefix hashes, root append receipts,
and a fresh comparison with the same612-file runtime source manifest.
No later root session or source change is included. The full-suite proof covers
the unchanged64ee15f runtime; publication ordering and documentation bytes are
verified separately by the publication audit.
