# Gap 34: already-benched last-match advice

Build: base `64ee15f19f7acf80a2dbb7e5035d8c037128fea6`, isolated managed worktree `review-already-benched-advice`, branch `codex/review-already-benched-advice`. Runtime: GPT-6.1-sol, medium. Surface: standalone Playwright CLI, dedicated loopback port 8515. Session: `2026-10-10-gap34-already-benched`.

The copied Team Nexus world `26UHC`, seed 2038, is at S1 W18 after the Masters quarterfinal win against Meridian Cross. Hollowlock's one-match lineup expired; Club shows him on the bench and Apex/Vortex/Ghost/Slyblade/Echo selected for Haven, Ascent and Lotus. The base serializer still advised another bench or agent swap. The corrected Dashboard keeps his historical 0.69 off-colour diagnosis and past one-match appearance, and says he is already out of the next fixture's selected five, with training/agent-fit guidance before his next appearance.

`reproduction.json` compares base and modified serializers on the same copied immutable save and confirms historical breaking-point equality and GameState purity. Browser evidence is in `runs/playtests/2026-10-10-gap34-already-benched/{dashboard-snapshot.txt,club-snapshot.txt,saved-snapshot.txt}`. The source world's verified save SHA is `999038d35e4e45460fa2b495591599dcf4042fc44206fdb4b84d586dca18186f`; the copied save has the same SHA after header Save.

The server reads current map selections through a campaign projection helper. Valid one-fixture lineups use the same eligibility/complete-five validation as match simulation; explicit map lineups retain precedence; stale or invalid fixture plans fall back to authoritative dressed selection. No upcoming fixture uses the default five. Advice acknowledges complete exclusion or partial-map rotation, preserving the development/mentor distinction and existing departed-player guard. JavaScript and simulation tuning are unchanged.

Focused validation: `pytest -q -n0 tests/test_review_selected_lineup.py tests/test_review_current_roster.py`: **56 passed in 12.64s**. The new matrix covers bench, selected player, map rotation, one-match inclusion/exclusion, map-over-plan precedence, stale/incomplete plan, automatic selection, no fixture, developing/veteran guidance and a second acting manager. It also compares projection with the exact override installation used by simulation and checks serializer purity. Existing tests cover departed/missing players and coach absence.

The earlier unfiltered native suite completed with 1314 passed in 5435.67s (1:30:35), actual terminal exit0 at 2026-10-11T01:23:07.682488+00:00. Root independently verified all625 pre/post/current source/config/test/script/workflow fingerprints, complete75-decision/17-snapshot saved-state byte equality, the original18-event audit interval and Save request11/result200 pairing. No new local tests were launched under the user's instruction. Current-head CI remains required before merge.

Reconciliation: 0 new accepted manager decisions were intended or made. All 75 accepted decision records and all 17 snapshots in the single `mgr_team_nexus` stream preserve their baseline prefixes (75/75 and 17/17). Save bytes remain identical. `audit.json` separately counts 18 newly retained world usage records across two page sessions, including Dashboard and Club views, one Save attempt and one Save result. The original usage byte prefix is preserved. Aggregate script reports are retained under the run directory; they include historical baseline events, whereas `audit.json` scopes added events. Usage is bounded and best effort; visible time measures visibility, not attention or complete session duration. There is no mutation coverage from this read-only acceptance.

Four append-only scoped CSV rows preserve the navigation intent, Save, failed cp1252 decoding audit, correction and final fresh audit. Step 3's expectation was mistakenly written after the initial corrected read; step 4 explicitly records that ordering defect and provides a pre-action expectation before closing the browser and rerunning the audit. No canonical CSV was written. Private browser membership/storage files remain only in ignored run storage and are excluded from owned staging.

Flywheel loop: inherited recent findings before browser play; recorded two learnings and one pain-point (`esports-playtest-0164`, `0165`, `0166`) afterward. The learnings cover contextual selection-aware review advice and immutable read-only acceptance; the pain-point covers explicit UTF-8 decoding and audit intention ordering.


Root late publication recovery stopped the still-running task-owned8514/8515 server families after checking their exact CLI identities and parents; zero listeners remained, and user8421 was untouched. Original public snapshots and native evidence are copied into evidence/. The raw18-event interval matches the original dated audit; older baseline events remain separate.

Only the Save row's factual analytics status/evidence was updated to recorded for the retained paired browser usage request, explicitly outside accepted campaign decisions. All19 observation fields, partial/failed outcomes and original intentions remain unchanged. The original scoped CSV and field-protection proof are preserved in evidence/.

Publication clarification: the current adjacent shard SHA256 is
`7999ed3615b406853c06bbcf82aba2e1283216b49902b4ae456079522d708e99`.
Each cited browser snapshot, reproduction and aggregate report has its
same-named durable copy in `evidence/`; `audit.json` is adjacent to this report.
Original ignored run paths above describe acquisition locations. The original
CSV is preserved as `evidence/actions-before-analytics-correction.csv`.
