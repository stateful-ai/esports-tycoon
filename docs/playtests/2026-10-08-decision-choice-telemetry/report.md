# Decision choice telemetry acceptance

Tested build: base `26b9281357e74de1bdc7beffe5d5660fe05e47b4` plus the dirty gap17
server/test changes, GPT-6.1-sol / medium, standalone Chromium on isolated port
8470. Copied world 26UHC, seed 2038, Team Nexus, S1 W6; source fixture was copied,
never played in place. No week was advanced. Source fixture and final save hashes
are in evidence/audit-summary.json; disposable full saves remain in runs/.

Exact accepted choices now survive the deterministic saved ledger. Browser
readbacks and the screenshot agree: Vortex, Ghost, Slyblade, Echo and Hollowlock
were dressed while Apex rested; Hollowlock was locked to Harbor. The plan carried
Aggression 72, Pace 31, that same five and Reassure. This session verifies the
setting and telemetry seam, not a performance or preparation-effect claim.

The session CSV records intentions/expectations before each interaction and
keeps failures/corrections. The first fresh browser could not resume the cloned
world because its new cookie had no world history. Step 2 recovered using the
copied authorized sessions cookie. Step 11 retained an interrupted audit recovery
caused by Windows cp1252 decoding; step 12 independently read UTF8 and checked
nested snapshots. The original counter error counted dictionary seats rather
than snapshots; evidence/audit-correction.json preserves both audit failures.
There are 12 observations: 10 met and 2 unexpected. The canonical shared CSV was not
changed; this session has its own append-only CSV for sequential integration.

| Step | Player intent and observed result | Decision evidence |
| --- | --- | --- |
| 1 | Fresh-cookie resume selector timed out; no request observed | Unverified failed intent; initial lobby usage retained |
| 2 | Copied-session recovery and public six-player roster read | Navigation, no accepted decision |
| 3 | Clear default lineup to auto; public default IDs empty | action_log27 `lineup_ids=[]`, omitted agents/per-map=`null` |
| 4 | Save non-Apex five; public ordered IDs agree | action_log28 exact five |
| 5 | Save first-map five | action_log29 exact five, fixture s1w6m0am, map bind |
| 6 | Set Hollowlock to Harbor; public assigned lock agrees | action_log30 `agent_choices={"fa_0":"harbor"}` |
| 7 | Set Aggression 72/Pace 31/five/Reassure; public plan agrees | action_log31 exact applied values |
| 8 | Accept unchanged game plan again | action_log32 identical params, distinct accepted decision |
| 9 | Direct HTTP mixed valid agent/invalid map request returns 422 | Public agent book unchanged; zero accepted record; no browser pair |
| 10 | Explicit Save and public plan/tactics readback | Save 200 pair, persisted independent ledger audit |
| 11 | Audit recovery used cp1252 and stopped before assertions | Failed local audit, no game mutation |
| 12 | UTF8 recovery verifies old prefix and nested snapshot counts | Independent saved-data audit |

Saved decision coverage: 6 of 6 accepted session choices (100%) matched by kind,
params, team, source, S1 W6 and order. The ledger grew 27 to 33 rows; the 27 old rows
are exactly equal. Snapshots remained 5 to 5. The new ledger alone quantifies:
1 default-auto clear,1 explicit default five,1 per-map five,1 Harbor lock;2 plans
with Aggression 72/Pace 31, that exact starter five and Reassure;1 repeat no-op.
Historical coarse rows remain intact and cannot quantify their omitted choices.
See evidence/decision-indexed.json and evidence/audit-summary.json.

Browser usage is separate: 29 retained events total, 25 for the copied world,
7 attempt/result pairs (all 200),0 unmatched attempts,0 orphan results. Six pairs
correspond to accepted decisions and one to Save. The direct HTTP 422 has no
browser attempt/result. The failed initial resume has lobby-only events and no
observed resume request. These retained bounded sidecars are not complete
attention/session-duration funnels. See evidence/usage-retained.jsonl and the
scoped usage-report.json. The scoped telemetry-report.txt includes this world's
full 33 row history; exact new-choice counts above use only rows 27 through 32.

Focused validation: 40 passed in 66.19 seconds (nine choice-telemetry tests,
manager decision environment and telemetry-report compatibility). A first
focused invocation named a nonexistent manager-test file and ran no tests;
corrected invocation is the 40-test result. Tests cover stale-ID filtering,
JSON ordering, explicit clear versus absent fields, per-map/alternate-human
boundaries, gameplan clamp/inherit/clear semantics, rejected choices and save
roundtrip. Learned observations/actions/encoders/checkpoints are unchanged.

The pre-play local flywheel recent read and post-play two learnings/one pain
point are retained in evidence/flywheel-before.json and flywheel-after.json.
The post write occurred once after the saved-choice audit. Browser closed and
only the owned 8470 server processes were stopped. No pending prelogged rows remain.

Publication gate: full unfiltered `python -m pytest -q -n2` completed with
**1209 passed in 5381.25s (1:29:41)**, exit code 0. The terminal result
confirms unchanged server/test source; publication-time SHA256 verification
matched both recorded source hashes. The primary Windows venv imported this
worktree's `src` through its explicit `PYTHONPATH`. Two workers bounded concurrent
machine load; there were no domain/slow filters or test exclusions. The start
manifest, terminal result and full log are retained in evidence/full-gate-*.json
and evidence/full-pytest.log. No source changed after the full run. No engine/data
tuning was made, so balance/pacing/floor/snowball triggers do not apply.
