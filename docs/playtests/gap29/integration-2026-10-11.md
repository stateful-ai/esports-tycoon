# PR375 forward integration, 2026-10-11

Source head before integration: `3f13ccd09256e288e08329d94259a19a1eefc841` (tree `f5e488f6e7b1b2b759944ab7bd4c568e042f2173`). Integrated actual main: `0401b8a810cdcd75aae7ba6cdd8fe3d22c2fb96b` by a normal two-parent merge.

The two serializer changes and all five original test cases are retained unchanged: known current handle, unknown/removed/empty target fallback, acting-team and exact-player isolation, and repeated-read saved-state purity. The stable profile target remains unchanged. No manager, engine, randomness, browser, save or running-server operation was performed.

Seven add/add evidence conflicts (actions.csv, native-frozen-files.json, native-full-suite.log, native-receipt.json, save-audit-correction.json, save-audit.json, usage-audit.json) differed only by line endings: Git diff with ignore-space-at-eol returned no differences across the full gap29 folder. Resolve using main's already published raw artifact bytes, retaining historical source blobs in the first parent. The report and original observations are unchanged. Canonical actions.csv is inherited from main.

Compatibility follow-up: pending PR422 uses a public report projection that intentionally replaces legacy hidden-potential targets; pending PR423 resolves the handle after that projection and returns null for unavailable players. When those changes land, retain their public projection and shared identity helper. Update this PR's five fixtures to explicitly authored public age evidence and align the absent-handle expectation with null, retaining every behavioral assertion. Do not restore a legacy private selected target or invent a handle for missing players. The original empty-string fallback is a transport detail superseded by PR423's public missing-player behavior.

All local tests, syntax validators, simulations, gates, application reports and hooks were skipped under the user's explicit waiver. Existing native and browser evidence describes the old implementation only and is not acceptance of the new integrated head. Tests are retained but UNRUN on this integration. Prior published-head CI: 3.12 and 3.13 succeeded on 3f13ccd; new-head CI requires independent inspection.

## Public-policy integration follow-up

PR422 exact head `e495bf7dfe2836324cce740846637d680611758c` was integrated by normal merge `5caa2a6f84e17c2f470529a28ac0b5fdf56aefed` (tree `2046610dc37405a0811666ce5d99f5596b539d49`, parents `f18c31487424e019f20926293fe640a85aa84dcf` and `e495bf7dfe2836324cce740846637d680611758c`). Its only conflict was compact-artifact development fields in server.py: retain public-report text and ID and temporarily resolve that public ID's handle.

PR423 exact head `411051a08e50fee1c06da98eb27af69ed5552b91` was then integrated by another normal merge. Its two server.py conflict regions were the club report identity and compact artifact identity. Both resolve to PR423's shared `_prep_report_identity` after PR422's public projection. Final server.py is exactly PR423's blob; no duplicated identity formula remains. Its frontend behavior, public development projection, regression files, source, and evidence are retained unchanged.

All five original PR375 cases remain: known handle and stable profile ID, unknown/removed/empty public targets, team/exact-player isolation, and repeated-read purity. Their shared fixture now declares `dev_suggestion_basis="age"`, ensuring the explicit public authored report retains its target; unavailable handles expect null consistent with PR423. Unknown public stable IDs are retained as report attribution but rendered as Former player by the shared frontend. Legacy private target IDs/text are withheld by the public projection, covered by PR423's retained counterfactual test. No original observation or report history was rewritten. All tests remain UNRUN locally, and old acceptance remains limited to its old implementation.

## Current frontend assertion repair integration

Normally merge PR423 repaired exact head `e7bd0e1aefbc35c95cbe4f0463a80fc622cdccbe` (tree `ec900aff5cec1607f4ce153f488af1d9d21ec458`) into PR375 previous head `216deffe83aebe05ba42b21ab0ae3874a005d5d7`. The repaired branch includes actual main `a7d2c6d3d6d0fc583850b34bc07855ad1e1384f2` through normal merge `6b3dd910540432694e03d2e8c5798d874f879716`. This final merge has no conflicts.

Inline finding 4243047913 correctly identified obsolete span expectations. PR423's two assertions now expect native `button type="button"` markup matching current `plink`; escaping and stable-profile routing assertions remain. All five PR375 label cases, public age fixture basis, null unavailable handles, shared identity helper, public/private projection counterfactuals and historical evidence are retained. No source change or executable validation was introduced by this repair integration. All tests remain UNRUN locally and old acceptance is not evidence for this new integrated head.
