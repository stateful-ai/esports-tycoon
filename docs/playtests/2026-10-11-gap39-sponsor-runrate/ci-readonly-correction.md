# Remote CI read-only correction

Remote run `38121115590` on pre-correction head
`78d9658800e9c595e4f1ca207a6cce5724d95590` failed the Python 3.13
`test_all_sponsor_slots_run_rate_matches_projection_without_mutating_save`
regression: 1 failed, 1289 passed, 4 skipped in 5462.76 seconds. The Python
3.12 matrix job was cancelled. The failed log's serialized save diff is
`facilities_by: {}` becoming `facilities_by: {"team_nexus": {}}`.

Source reading identifies the cause: both finance calculations read
`GameState.facilities`, whose getter uses `setdefault`. The correction reads
the acting team's facilities and sponsor slots through their backing maps
with `get`; a missing entry therefore stays missing. The finance endpoint's
facility rows and sponsor unlock checks also use non-mutating facility reads.
The convenience property and actual upgrade/write paths retain their existing
semantics. Sponsor estimates, expiry, RNG, tuning and simulation are unchanged.

The original all-five-slot regression is preserved unchanged. Additional
regressions exercise each finance reader independently with missing sponsor
slots, absent or nonzero acting-team facilities, and facilities owned by
another team; a separate unlock read regression checks absent facilities.
These new tests are **UNRUN locally**, under the user's explicit prohibition
on local tests/native checks/simulation gates. Git whitespace checking passed.
Fresh exact-head remote CI is required; this source diagnosis is not a passing
test claim.

No new browser session was performed for this correction, and no new CSV shard
was created. The prior report, four-row session CSV, 17 retained raw receipts,
source qualifications and byte proofs remain unchanged. The prior 104 accepted
actions / 23 snapshots and byte-identical copied-save observation are historical
evidence on the earlier source, not acceptance evidence for this correction or
proof that fresh absent-team maps had been tested. Browser/setup property
materialization can pre-create an empty team entry and mask this defect.
Other materializing convenience properties used by finance serialization were
not subjected to a fresh whole-endpoint purity claim here.

The root coordinator owns the failed remote log publication and independent
exact-head CI review. No primary user files, canonical playtest history, shared
fetch state, existing user server or existing career was altered by this repair.
