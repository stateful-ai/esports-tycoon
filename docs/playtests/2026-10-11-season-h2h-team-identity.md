# Season head-to-head team identity

Observed by the parent browser playtest on frozen PR #415 candidate
`27a2ea2f` (tree prefix `943144e`), fresh sandbox world `REWKH`, seed
2039, S1 W1. This is evidence from that candidate, not acceptance of remote
main or this fix. The parent recorded step 4 intent before acting. Active
runtime model and effort were unknown (not exposed).

The Season standings showed Team Nexus with tag NXS and Team Vanguard with
tag VGD, but both rows and columns of the head-to-head matrix showed TEA.
Columns had full-name titles; row profile links had neither titles nor
accessible full names. The saved DOM captured these visible identities.

Source evidence supplied by the parent:

- `C:/Users/aidan/.codex/worktrees/sponsor-objective-identity/runs/playtests/2026-10-11-pr415-fresh-campaign/season-w1-dom.txt`
- `C:/Users/aidan/.codex/worktrees/sponsor-objective-identity/runs/playtests/2026-10-11-pr415-fresh-campaign/h2h-w1-dom.json`

Observation publication origin remains pending: the fresh session shard has
not yet been appended to the canonical playtest history. This change does
not fabricate a playtest row or alter historical observations.

The renderer uses existing public standings tags by team ID, includes both
tiers, and falls back to the full name when legacy payloads lack a tag.
Row/column headers expose full names and table scopes; row profile links
retain their existing data-tid route and expose full-name titles and labels.
The existing matrix row order, cell order, and series results remain in place.

Regression coverage was authored for duplicate name prefixes, ID-based tag
lookup, both tiers, legacy fallback, matrix order/results, profile identity,
and HTML escaping. All local tests, syntax validators, simulations, gates,
and analytics-report commands were skipped under the user's explicit
instruction. No runtime pass is claimed. Post-fix browser acceptance and
telemetry reconciliation remain for the parent's continued session.
