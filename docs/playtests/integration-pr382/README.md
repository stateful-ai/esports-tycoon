# PR 382 forward integration

The original PR head is 9a0f17a216fcd75060333b88922158e52ccc5401.
It is integrated with main 0401b8a810cdcd75aae7ba6cdd8fe3d22c2fb96b
by a normal two-parent merge. Both source files merged without conflicts.

Sixteen add/add conflicts were historical gap34 evidence. Main's published
canonical versions are retained. The entire original PR directory is preserved
byte-for-byte by Git archive in original-pr-gap34-9a0f17a2.tar.gz. The adjacent
qualification JSON records both original and canonical Git blob inventories.
The canonical actions.csv is identical to main; no historical rows were rewritten.

Static review covered eligible roster resolution, complete-five validation,
explicit-map precedence, shallow non-mutating projection, acting-manager and
departed-player guards, and developing/veteran advice. Existing regression
sources are retained. No new regressions were needed from this review.

No local tests, syntax checks, simulations, gates, hooks, application reports,
servers, save actions, or playtesting were run under the user's explicit waiver.
Old validation receipts are historical only and do not validate this composed
tree. Exact integration-head remote CI and root review remain separate checks.

## Challengers review follow-up

Current inline discussion 4243011405 correctly identified that the tier-one
filter bypassed the fixture lineup for a human-managed Challengers club. The
next-fixture lookup now follows acting-team membership across both tiers,
retaining deterministic week/id order, unplayed status and current-or-future
week constraints. GameState.fixtures contains the current season schedule and
is replaced at rollover; Fixture has no separate season field.

Six focused regression cases were authored for a real tier-two acting club:
per-map exclusion/inclusion, one-match exclusion/inclusion, existing bench
status and partial-map rotation. Unsorted played, past, later and unrelated
primary-manager fixtures exercise the lookup; historical diagnosis and
serializer purity are asserted. These added regressions are UNRUN locally.
No local tests, syntax validators, hooks, simulation, reports or play actions
were performed. Current repair-head remote CI remains separate evidence.
