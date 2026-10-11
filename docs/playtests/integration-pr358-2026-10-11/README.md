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
