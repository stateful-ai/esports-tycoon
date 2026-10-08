# Development feedback acceptance

Tested dirty 3ac34df with the development feedback patch, gpt-6.1-sol medium.
A separate server on 127.0.0.1:8451 used saves under runs/playtests/development-refresh.
Final world NHVUT, fictional Sandbox Team Nexus, seed 2038, S1 W1.

In the real Chromium browser, Vortex initially showed the exhaustion warning and
Game Sense, Utility Usage, Positioning. Selecting Rest immediately changed that
same row to Recovery and removed the warning. The focus dropdown remained the
active element. Selecting Light intensity retained Recovery; live roster readback
confirmed rest/light. No browser page errors occurred. The screenshot and complete
browser readback are retained in runs/playtests/development-refresh.

The final four logged observations (29-32) cover creation, Development navigation,
Rest, and Light. Both accepted decisions match the final save's action_log indices
0 and 1 in order, source web, mgr_team_nexus, team_nexus, S1 W1. Weekly snapshots
are zero because this acceptance run did not advance the week. Decision coverage
is 2/2. Browser usage separately retained 14 world events, including both dev_plan
attempt/result pairs (request IDs 16 and 18, success 200). See evidence.json.

Earlier harness attempts are preserved in the per-session actions.csv. Seed-input
blur replaced the pick button before its click; the automatic handbook intercepted
navigation; console Unicode and case-sensitive assertions interrupted readback.
The earlier WZVWL acceptance passed visible Rest and Light checks but used the wrong
explicit-save endpoint, so its decision persistence remains unverified. The final
NHVUT run used /api/actions/save and reconciled both records. No blocked click is
claimed to have produced a campaign action.

Language changes and rejection/readback failures are covered by the actual-JS Node
regression check. Browser language acceptance is unverified because this world has
no language coach. This short UI test does not establish gameplay balance.

Flywheel: read the two recent esports-playtest findings before playing; recorded
two learnings and one pain-point after the run. Main shared history is untouched;
this directory contains an isolated session CSV for sequential reconciliation.

17 isolated observations are retained: 5 blocked harness attempts, 12 met outcomes.
Only the final NHVUT decisions are confirmed in the saved decision stream; earlier
WZVWL readbacks remain explicitly unverified for persistence.

The standard read-only telemetry report confirms one saved world and two web
set_dev_plan actions. Its per-advanced-week display uses a denominator floor,
so the printed 2.00/wk is not evidence of a simulated week. The standard usage
report reads the 18 retained final-session events (14 belong to NHVUT; the rest
are lobby boundary events). Both dev_plan requests pair successfully. The first
isolated usage audit used a nonstandard segment filename and returned zero;
renaming the copied segment to usage.0.jsonl corrected the audit. Raw source
sidecars were preserved.

Release validation: full pytest suite passed 1,182 tests with two workers in
4,770.67 seconds. JS syntax and the actual-JS focused check passed. No engine,
data, or campaign mechanics changed, so balance/pacing/snowball gates do not apply.
