# Qualification-aware match-preview stakes

The copied Team Nexus career at Season 1 Week 14 now says its top-four berth is already secured and identifies final league order and playoff seeding as the remaining stakes. The league table and calendar are unchanged.

Build: `64ee15f19f7acf80a2dbb7e5035d8c037128fea6` plus this branch's presentation changes, game 0.0.1. Runtime: gpt-6.1-sol, medium. World: 26UHC, seed 2038. Browser: separate Playwright CLI session `gap30`, loopback port 8436, separate managed worktree and copied saves. Remote main matched this baseline when checked. No primary-checkout changes or original-save writes.

## Player session

Four intentions were written before their actions through `scripts/playtest_log.py`, with a local wrapper selecting this session's CSV directory. All four outcomes met their recorded expectations. [actions.csv](actions.csv) is a new shard; canonical history was untouched.

1. Dashboard: [01-dashboard.yml](proofs/01-dashboard.yml) records the secured-berth clause in the next-match briefing, with Vanguard as the opponent.
2. League: [02-league.yml](proofs/02-league.yml) records Vanguard 12-1, Nexus 11-2, Rust Belt 9-4, Saracen 7-6, and OUT badges for Baltic Meridian, Sahara Compass, Nordic Frost, and Kathmandu Apex.
3. Calendar: [03-fixtures.yml](proofs/03-fixtures.yml) records 13 played weeks and the remaining Week 14 Vanguard-Nexus regular-season fixture.
4. Save: [04-save.yml](proofs/04-save.yml) and [audit.json](proofs/audit.json) confirm the saved career remains byte-identical to the original fixture: SHA256 `4d61cb3de347969f7eea33a9894c929a62b947f19cffbb89709b31ebd2e1186c`.

## Telemetry reconciliation

Accepted decisions: 63 before and 63 after, all identical. Snapshots: one manager stream containing 13 snapshots before and after, all identical. New accepted gameplay decisions: 0. All four CSV rows are correctly `not_instrumented` in the accepted-decision vocabulary: dashboard/league/calendar navigation and explicit saving do not add manager decisions. The career remained S1 W14 regular, with identical standings and fixtures. [telemetry-report.txt](proofs/telemetry-report.txt) is scoped to the copied career's save directory.

Usage was separate and started empty: no original usage directory was copied. The retained endpoint audit contains 32 events overall and 28 tagged to world 26UHC across two page sessions. Three corresponding views identify dashboard, season/league and season/fixtures; a fourth world-tagged view is lobby during reload. The Save attempt and successful HTTP 200 result share request ID 15 and target `/api/actions/save`. Thus the three navigation intents have corresponding view evidence and the save intent has a matching attempt/result pair. [usage.jsonl](proofs/usage.jsonl), [ui-usage-report.json](proofs/ui-usage-report.json), and [audit.json](proofs/audit.json) preserve the exact retained counts. Visible-time events are visibility proxies; these bounded records do not prove total attention or a complete browser funnel.

## Implementation and verification

`manager/qualification.py` computes conservative qualification bounds from public records and the actual unplayed regular league fixtures for the requested region/tier/cut. A team is eliminated only when at least four rivals already strictly exceed its ceiling. A team is secured only when fewer than four rivals can reach or exceed its current wins. Tied ceilings remain contested because round differential can change. Independent bounds can leave a schedule-dependent certainty contested; they never predict an exact seed or title.

The narrative uses these states for secured, contested and eliminated stakes. Tier-2 Challengers has no top-four playoff berth and gets no fictional regional-playoff clause. Played, playoff and international fixtures get no regular-season qualification clause. The web OUT badge reads the same helper. No simulation behavior, RNG, hidden observations, JavaScript formulas or save fields changed.

Meaningful tests cover the final-week record, clinched/contested/eliminated cases, ties despite extreme current round differential, unequal remaining schedules, region/tier/cut isolation, played/nonregular fixtures, deterministic repeated reads and unchanged GameState, and web/narrative agreement. Initial focused run: 115 passed, 4 failed in 182.69s; all failures were older named-ownership assertions expecting the obsolete berth-grip clause for secured teams. The corrected targeted run passed 55 tests in 94.92s. `git diff --check` passed.

The previously launched native unfiltered suite completed with 1289 passed in 6399.11s (1:46:39), terminal exit0 at 2026-10-11T00:24:43.629295+00:00. Root independently verified all626 pre/post/current source/config/test/script/workflow fingerprints, complete saved-state byte equality,63 accepted decisions,13 snapshots and the retained Save request15/result200 pair. Native receipts, terminal output and the original launcher are preserved in proofs/. No new local tests were launched, following the user's instruction. Current-head remote CI remains required before merge.

## Flywheel findings

No flywheel search/recent/record tool was exposed in this agent's available tool inventory. These findings are retained locally for later publication; no remote flywheel write is claimed.

- Learning 1 (high confidence, 26UHC/2038/W14): the public table and actual remaining fixtures can establish a secured berth even while the next fixture remains consequential for the recorded league order. Preview stakes must distinguish qualification from seeding.
- Learning 2 (high confidence, qualification tests): a rival whose ceiling ties current wins prevents a conservative clinch claim even when the team currently leads round differential. Tiebreak ordering today is not a guaranteed final ordering.
- Pain point (high confidence, original browser evidence and this session): position-only playoff wording made a final-week secured berth sound at risk. The same public qualification calculation now grounds both preview stakes and OUT badges; exact future seed changes are deliberately not promised.


Root publication recovery recorded the two learnings and one pain point in the local Agora esports-playtest flywheel, using the existing acceptance evidence. This occurred after the original session; it does not retrospectively establish pre-play inheritance. Original agent tool unavailability remains qualified. Actual entry IDs and recording time are preserved in gap30-qualification-stakes/proofs/late-flywheel-recovery.json.
