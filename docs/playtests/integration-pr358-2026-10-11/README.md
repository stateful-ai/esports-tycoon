# PR 358 integration provenance

This normal merge combines the reviewed PR head
`99e6477aa129c0411dc869c3decfc31792f8dad2` with actual main
`6fd38e1d8b413deeec2f3a078d3a80b71a5f0d71`.

The only product changes relative to main are the existing server-computed
current-fixture scouting readiness, its Dashboard presentation, and a state
refresh after changing a standing scouting directive. The original 108-line
regression file is preserved byte-for-byte. Main's newer roster guidance,
telemetry, serializers, profile behavior and campaign mechanics are preserved.

All 21 conflicts were add/add historical evidence files in the migrated
scouting shard. Each resolution takes current main's published blob. Every
pre-existing main file outside the two feature source files is unchanged;
canonical actions.csv is byte-identical. The qualification JSON lists all
stage 1/2/3 and resolved object IDs. Historical October 8 proof files absent
from current main are not republished over its curated history. Their original
objects remain reachable through the first merge parent. A separate local
archive of both original PR evidence directories was preserved before
resolution, with its SHA-256 recorded in the qualification JSON; it is not
needed to recover the immutable Git objects.

The fully paged live inline review contains the same three findings recorded
in the prior root review: canonical publication, raw-depth readiness, and
migrated pro assignments. The implementation uses raw team depth >= 0.5,
recognizes exact migrated opponent/fixture directives, and preserves current
main's published history. Root's previous review and proof files and a live
inline snapshot were also copied to local runs/playtests/repair-358 before
integration.

No local tests, syntax checks, simulations, gates or report commands were run
for this integration, following the user's current instruction. Historical
1261-test evidence and remote CI on the original head describe that earlier
head only. This merged tree needs fresh root review and remote CI before merge.
No new player session or accepted decision is claimed by this Git-only repair.
The preliminary staff employment report was a closed-overlay DOM false
positive and produced no product change.

## Follow-up display correction

Inline finding 4242676212 on merged head `754f525` identified that raw depth
0.499 was correctly locked but displayed as 50%. The forward correction floors
the displayed team-depth percentage from raw progress in badge, status and
copy. Raw depth >= 0.5 remains the readiness rule; playbook confidence and
assignment handling are unchanged. Authored regressions cover 49.4%, 49.5%,
49.9%, just below 50%, exactly 50%, 99.9% and 100%, both with a standing
assignment and with stored intel alone. These regressions remain unrun.

Root's ordinary browser session on exact `754f525` confirmed standing
assignment/readiness, its next-week opponent rollover and saved persistence.
That session qualifies the earlier merged head's exercised behavior; it does
not establish runtime acceptance of this display correction. The qualification
JSON above records the original integration tree and original regression blob;
the follow-up changes only this README, the readiness serializer and regression
file. Historical native 1261-test and prior remote CI results remain historical.
All local checks and hooks are skipped under the user's current instruction;
fresh remote CI and root review are required for the forward commit.
