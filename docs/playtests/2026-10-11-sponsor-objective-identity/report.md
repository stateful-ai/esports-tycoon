# Sponsor objective identity source fix

The root reviewer observed two indistinguishable `make the regional playoffs`
rows in Needs You: both `Sponsor · At Risk · currently 6th of 8`. These can be
separate legitimate obligations; collapsing them would conceal a contract.

Original browser session: `2026-10-11-main401-development`, exact main
`8d6315303205e6ebefa425a9015fc5523ccef701`, game version `0.0.1`, Team Nexus,
world `26UHC`, seed `2038`, S2 W9, runtime `gpt-6.1-sol` / `medium`.
The existing step 12 readback interval is
`2026-10-11T15:03:51.218+00:00` to `2026-10-11T15:04:42.876+00:00`.
This is the original readback interval, not a newly recorded gap-discovery
timestamp. The original session report did not classify this gap; the root's
later independent review did. No prior observation was changed.

Evidence pointers in that session's retained `runs/playtests/` folder:
`weekly-report.png` (dashboard behind the settled report) and
`final-public-readbacks.json`, `/api/state` response body `objectives_hub`.
[Original objective extraction](objectives-before.json) contains only those
public objective fields; no save, authentication, or unrelated state is copied.
Root owns canonical CSV reconciliation and any later browser acceptance.

The source patch adds `sponsor_name` from `SponsorDeal.name` and
`sponsor_slot` from the stored per-team slot key. The frontend escapes the
brand with the goal label and uses the existing Company slot display labels
in the escaped status detail. Goals, status calculations, filtering, order,
and distinct obligations remain unchanged. No GameState schema or migration
is needed. PR #387's pure per-team objective read is retained.

Validation is source-only review. Regression tests were written but not run.
No local tests, syntax checks, simulations, gates, analytics commands, game
server, or new browser acceptance pass ran for this fix, per user instruction.
There is no runtime or acceptance claim for the resulting patch.

This draft is stacked on PR #387's reviewed head
`e95faf7fead10aaf78e68acdd01954ac390831c7`, actual branch
`fix/gap40-offseason-rollover-hint`. PR #387 must actually merge; this PR must
then integrate/retarget to main and receive fresh root review and CI on the
resulting head before merge. An open prerequisite PR is not a completed gate.
