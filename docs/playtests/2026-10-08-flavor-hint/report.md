# Flavor-event advance recovery, 2026-10-08

Recovery note, 2026-10-10: this original report records the completed October 8 session. The original uncommitted checkout subsequently lost Git metadata and tracked files during its full test run. The retained terminal run failed (95 failed, 1038 passed, 73 errors), followed by a missing-file freeze error; it is preserved as `interrupted-full-result.json` and `interrupted-full-pytest.log`, and is not a release gate. An isolated registered checkout was restored at the original base, with all frozen source hashes matching exactly. Only original CSV rows 6–8 could be recovered with their exact timestamps from the session transcript (`recovered-actions.csv`); rows 1–5 and several browser/flywheel artifacts were lost. No timestamps or observations were fabricated. `decision-evidence.json` was regenerated directly from the retained before/end saves. The complete fresh acceptance session and its five prelogged rows are in `../2026-10-10-flavor-hint/`. References below to missing original artifacts describe original observations, not currently retained evidence. The replacement full gate uses the unchanged original source manifest.

Gap18: the pending flavor-event 409 sent the player to removed **Action required**. Both browser advance guards now direct the player to **Dashboard → Needs you → Team moment**, choosing a response, then retrying the appropriate control (Advance Week or Sim Ahead).

Tested checkout: `codex/advance-flavor-recovery-hint`, base `121e55ed36e5538eeee80a2c17c656a8021ccf22` (fetched origin/main), with the two guard-copy edits and focused regression test dirty. Runtime: GPT-6.1-sol / medium. Used standalone headless Chromium/Playwright on isolated port8472; user8421 and root8471 were untouched. Imported this worktree's `src` using the primary `.venv-win` and explicit PYTHONPATH.

Continued an isolated copy of the immutable bench-rotation world26UHC, seed2038, S1W6: 27 accepted actions, five snapshots, Ghost behind-the-scenes event. `decision-evidence.json` contains source fixture SHA256s, checked unchanged after the session. Disposable campaign saves remain under `runs/playtests/2026-10-08-flavor-hint/saves`.

## Player observations

- Baseline: Dashboard displayed Needs you, Team moment, Ghost prompt and three existing choices. Clicking Advance Week returned409 with the obsolete section label. Before/after `/api/state` values were identical.
- Changed build: identical409 gate, now naming the visible Dashboard route and retry. The existing Dashboard navigation button was used; no new navigation affordance was needed.
- Chose **Make it playful** (`let_loose`): HTTP200, “The joke misses its audience and draws a few groans.” The pending prompt disappeared, with week still6. No outcome previews or event rules were added.
- Retried Advance Week: HTTP200 and week7. Explicit save through browser fetch returned200. Sim Ahead's pending guard is covered by the focused unchanged-state test; the browser flow exercised Advance Week.

## Evidence reconciliation

Eight append-only session rows in this session's `actions.csv`; canonical shared history was untouched. Exact decision coverage: **2/2 accepted decisions**, indices27 (`flavor_choice`, event39e83f39373aa3ea, choicelet_loose) and28 (`advance`), both sourceweb/team_nexus/S1W6, in order. Existing27-action prefix unchanged; telemetry snapshots5→6 with old prefixes unchanged. Rejected409s added zero accepted decisions.

Browser usage: two retained page sessions, 19 events, **4/4 attempts paired** by session/request-ID/target: baseline advance409, fixed advance409, choice200, retryadvance200. No unmatched attempts or orphan results. Dashboard navigation and visibility are retained independently from deterministic decisions. Browser-visible time is a visibility proxy. The initial failed harness page was not retained by usage; direct save fetch bypassed the Usage wrapper. Neither gap is represented as captured activity. Source prefix and request pairs are retained in `decision-evidence.json` and `usage-evidence.json`; isolated aggregate reports are also included.

Corrections: the first harness attempt failed its case-sensitive `Team moment` assertion because rendered text was uppercase; row1 remains blocked/unverified, and row2 records the corrected check. No decision preceded that failure. The handoff save read initially used Windows cp1252, failed, then succeeded with explicit UTF-8. Both baseline/fixed page-error captures contain only the expected thrown409 message from the existing generic API handler. No pending intents remain. Own browser closed and own server stopped after saving.

Flywheel: inherited domain recent/search before playing (`flywheel-before.json`), then recorded two learnings and one pain-point once (`flywheel-after.json`). This one-world UI session establishes recovery/discoverability and telemetry consistency, not gameplay balance.

## Validation

Focused suite: **7 passed in2.47s**, covering both unchanged-state pending guards and the existing flavor contract tests. The final detached unfiltered release gate passed **1206 tests in 3939.13s**, with native pytest exit 0 and runner exit 0, finishing 2026-10-10T19:10:00.313118Z. `release-full-result.json`, `release-pytest-exit.json`, and `release-full-pytest.log` retain the terminal proof; all 606 frozen source files were identical before and after the run and independently rechecked before publication. The superseded `full-pytest.log` has green test text but no recoverable native exit receipt; `receipt-audit.json` preserves that limitation separately. No engine, data, tuning, legal-action, RNG or event-effect changes, so balance/pacing/floor/snowball extra gates are outside the trigger set.
