# Resolved preparation player identity

## Public observation supplied by the root playtester

The root agent played current main at commit
`83cd64d1d15b066c17cb392c483f21b870356831` (tree
`4bcc0ca59c7dbc121d3a0feecb0665ebd943af81`) in a separate clean checkout.
The visible world was seed 2040, Phantom Core, Sandbox, season 1 week 1 to
week 2. The root supplied public DOM evidence from its local run:

- `runs/playtests/2026-10-11-match-prep-root/step8-after-continue-dom.txt`
- `runs/playtests/2026-10-11-match-prep-root/step10-prep-note-dom.txt`
- `runs/playtests/2026-10-11-match-prep-root/step10-wraithhawk-profile-dom.txt`

The resolved Match preparation note began `Dev note: Team Phantom Core P3`.
The public roster and opened player profile identified that player as
`Wraithhawk`, age 18. The prefix was the humanized internal identifier rather
than the public player handle. These are root observations, not a child-agent
runtime reproduction. Root runtime model and effort were unknown (not exposed).
The root reported three accepted gameplay actions: a targeted plan, a light
anti-exec scrim, and advancing the week. Its final telemetry audit was pending
when this implementation was authored; this document does not claim reconciled
coverage or create additional gameplay action rows.

## Source finding and change

`preparation.view` returned the persisted report's player ID without a display
handle. The Match renderer fell back to `humanize(player_id)`. The game-plan
latest-artifact payload also exposed the ID without a handle.

The web serializers now enrich both latest-report projections with
`dev_suggestion_handle`, read from the current player registry. IDs and profile
routing remain intact. Current handles also work after renaming or transfer.
If the player no longer exists, the handle is null and the Match label is an
unlinked `Former player`. An empty suggestion ID produces no identity prefix.
The existing `plink` helper escapes the public handle and stable ID.

This identity-only change does not alter stored report text, generated history,
preparation formulas, development values, or saved report models. The separate
development-estimate precision gap is outside this PR's scope.

## Validation status

Authored `tests/test_web_preparation_identity.py` covers both real serializer
paths, current/renamed/transferred/missing identities, empty/no-report behavior,
read-only report projection, real frontend label rendering, escaping, and
stable profile routing. It has **not been run**.

All local tests, validators, simulations, gates, report commands, syntax checks,
and browser acceptance checks were **SKIPPED by explicit user instruction**.
Only source/evidence reads and Git operations were performed. The dirty primary
checkout and the shared gameplay CSV were left untouched. Runtime acceptance
and CI remain pending root review; no passing gate is claimed.
