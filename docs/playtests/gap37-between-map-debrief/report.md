# Gap37: last-match between-map calls

Copied authentic career 26UHC, seed 2038, Team Nexus, S1 W22. Browser acceptance
used isolated port 8526 and named browser gap37, with no new campaign decisions.
The source save is the completed Champions semifinal s1csf0: Nexus lost 1-2 to
Vanguard. The save's engine-authored notes were preserved exactly:

- VGD: targeting Vortex.
- VGD: stabilize response after map 1.
- NXS: stabilize response after map 2.

The Dashboard's existing Your calls card now labels the four dial overrides
(30 aggression, 70 map control, 30 pace, 70 utility discipline, against book 50)
as Initial plan and displays Series notes separately. Both teams' notes appear
verbatim. The explanatory copy describes applied responses without attributing
the result to them. The Dashboard retains seven cards. See
[actual card screenshot](your-calls.png), [Dashboard DOM](01-dashboard.txt), and
[Season fixture DOM](02-played-weeks.txt). Independent public state readback is
in [public-state-readback.txt](public-state-readback.txt).

## Evidence and reconciliation

Three pending-before-action intentions were completed in the isolated
[actions.csv](actions.csv); [actions.raw.csv](actions.raw.csv) preserves the
pre-annotation rows. Only the two analytics fields were changed; all first 19
fields match independently. These rows are ready for the root owner's sequential
append into canonical history. The finding remains pending until that delivery.

No accepted decisions were added. All 90 historical decisions and all 21
team snapshots were preserved, as were the complete save bytes before and after
topbar Save. Both SHA256s are
`9f66e859da37c117077091eeaa4fda946ab04af42bef01c74e7a552d069324c8`.
The session therefore has zero new decisions to reconcile, not 90 newly tested
decisions. Save is outside the accepted decision vocabulary. Decisions and
snapshots were independently compared; the snapshot dictionary has one team key
containing 21 records. An initial ad-hoc count of dictionary keys was corrected
before the final audit.

The usage baseline was empty: copied historical usage was excluded. The retained
[raw usage](usage.raw.jsonl) has 18 events across two page sessions: four bootstrap
events and 14 main-session events. The main session is independently selected by
its Dashboard view and restricted to world 26UHC/team_nexus. All three CSV rows
have coarse usage evidence: Dashboard view, Season/Fixtures views, and Save
attempt/result request ID 12, success 200. Opening Played weeks is not separately
instrumented; the raw DOM proves its observed result. No session-end event for
the main page survived close. Bounded usage retention does not prove complete
funnels or attention duration. [audit.json](audit.json) contains counts, request
mapping, exact save hashes, fixture notes, and preservation results.

## Source contract and validation limits

Browser verification used code commit `a2ca33f` on base
`20273cd7ab885e7d409dec46f511d915d6e08ff4`, verified as fresh remote main before
worktree creation. [source-manifest.json](source-manifest.json) pins 430 tracked
source/data/UI files; every hash was checked unchanged after browser play.
The later receipt commit adds documentation only. This qualifies the current
head's code against that tested freeze; it does not claim earlier test gates.

The serializer resolves notes using review fixture ID, season, week and both
team IDs (either fixture orientation). Missing fixtures, older-season reviews,
different weeks/teams/IDs, empty notes, and legacy fixture defaults yield an
empty list. The client omits that section and permits notes without an initial
call block. Notes are escaped with the existing esc helper. No English parsing,
new RNG, save schema, engine change, JS simulation formula, or analyst gate was
added. The six parametrized edge cases in tests/test_match_review.py were
reviewed in source and added for remote CI; they were NOT run locally. Numerical
between-map effects and synthetic XSS/legacy cases were not browser-tested.

Node syntax, Python AST parsing, git diff whitespace checks and authentic browser
acceptance passed. No local pytest or expensive gates ran, per user instruction.
Remote CI is separate and its current status is reported on the PR. The browser
console after restoration showed zero errors and warnings; an initial bootstrap
load emitted a favicon request error before identity restoration, outside the
accepted player session.

The owner closed only named browser gap37 and stopped only PID 22056 after
verifying its command line targeted esports_sim --web --port 8526. Port 8526
had no remaining listener. Root port 8525 and user port 8421 were untouched.
Copied sessions/auth and complete campaign saves remain untracked under runs.

## Flywheel

Direct Agora recorder fallback read search/recent before play and recorded two
learnings plus one pain point afterward: esports-playtest-0195 through -0197.
Receipts are in flywheel-before.json and flywheel-after.json. The learned lessons
are to distinguish recorded series events from initial plans and compare full
save bytes for read-only acceptance. Team abbreviations remain a small readability
friction; ownership must not be guessed by parsing these strings.
