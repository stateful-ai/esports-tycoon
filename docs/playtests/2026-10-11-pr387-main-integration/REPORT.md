# PR 387 integration with current main

The original offseason advance feature at `73acfce15bca918f57395b6aab7246d585e0a285`
is integrated with actual main `ba3f5894af70fc6616e5ceccb71982fcb27d47e1`
by a normal merge. The merge base is `20273cd7ab885e7d409dec46f511d915d6e08ff4`.
Only `.gitattributes` conflicted; both parents' receipt rules were retained.
`server.py` and `app.js` merged automatically. All original added/deleted
feature lines match exactly across the six source and test paths.

`proof.json` records the expected merge parents, source line comparison,
read-only root evidence hashes, and original review/comment references.
`history-inventory.json` records raw checkout SHA256 and Git blob SHA256
separately for 2,004 actual-main playtest paths and 941 original-head
historical paths. Every inventoried Git blob is unchanged. The original
head's canonical CSV and nested attributes are intentionally owned by main
and excluded from the original-head preservation set. No historical dated
proof, receipt, runtime metadata, or artifact was rewritten.

The inventory observes 456 actual-main and 449 original-head checkout files
whose raw bytes differ from Git only by CRLF/LF conversion. These are recorded
honestly rather than claimed byte-identical. All other inventoried raw files
match their Git blob SHA256. The overlapping parent inventories are separate
preservation checks, not a count of unique files.

Actual-main canonical history contains 994 rows with 21 fields and SHA256
`21026ae7ac34bc51cdfc045f754821a46a5b6f8937821d3d2ee3950f57985631`.
The merged canonical CSV has this same raw and Git SHA256. All 32 PR-owned
rows are already published in that main commit, compared using their
original session/step keys and all 21 fields: 6 rollover, 6 shared-ready,
6 status-retry, 6 ready-reload, and 8 readiness-loading rows. None are absent,
duplicated, or field-mismatched. This completes the actual-publication
requirement in comment `4240685536`; it does not replace fresh review or CI.

Original review `5482792375` and the other five addressed inline findings
remain supported by unchanged feature lines and their historical acceptance
qualifications. Earlier browser-tested source, receipts, failed CI, and the
source-only purity repair remain dated evidence at their original heads.

Validation for this integration is static Git, blob, and CSV comparison only.
No local tests, Node, syntax checks, native checks, simulation, gates,
analytics, browser acceptance, or game were launched under the user's
explicit override. Port 8421 and the dirty primary checkout were untouched.
Fresh exact-head remote CI and independent root review are required before
merge; no new runtime acceptance or earlier-head green is claimed.
