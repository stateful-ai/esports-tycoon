# Weekly facility expense accounting acceptance

Tested baseline `042d86d3161fc5fa3185091031ba546193b2e97e` plus the scoped
uncommitted accounting fix, branch `fix/weekly-facility-expense-reporting`.
Normal Chromium browser, own server port 8487, copied world 26UHC / seed 2038.
Runtime model and effort were not exposed, so the CSV retains unknown values.
The original test world and shared CSV were untouched.

The player question was whether building Media Department level 1 makes its
ongoing cost visible when the week settles, while preserving the bank movement.
Intent and expectations were recorded before each action in this session's
[CSV shard](actions.csv), using the existing helper with a separate log directory.

## Observed result

The browser showed Media Department build cost 150,000 and weekly upkeep 1,500.
Building reduced the bank from 483,406 to 333,406. The measured rival-quote choice
resolved the pending event. The visible Polar Compute steady offer was accepted:
41,300 per week for 37 weeks, no upfront payment. This reproduces the financial
scenario from the original playtest, although the three decisions were made in
a different order. One advance settled W10 and moved the world to W11.

The Full report displayed **income 110,732, expenses 48,600**, followed by
**Facility upkeep 1,500 (included in expenses)**. The bank became 395,538,
exactly the 62,132 report net above the pre-tick bank of 333,406. Company historical
income and expenses, the actual advance response, and `/api/report` all agreed.
The live run rate is a current-state projection and remains distinct from this
settled report. [Public readbacks](public-accounting.json),
[browser screenshot](full-report.png).

## Deterministic and accounting checks

Five new targeted tests passed, covering zero facilities, varying department
levels, legacy plus current sponsorships, multi-human seat accounting, actual
charged costs, actual negative accepted-demand penalties, primary compatibility
fields, and report/finance serializers. The first targeted run had 30 passes
(26 existing finance cases plus four new cases). Its new negative-demand case initially failed because
the test used a missing fixture; the corrected case names a real played fixture.
The corrected five-test run passed in 104.22 seconds. JavaScript syntax and Git
whitespace checks passed.

The baseline comparison loads the actual campaign and sponsors source from Git
at `042d86d`, then advances the same observed pre-tick state with baseline and
changed implementations. Both **complete GameState JSON and match event logs
are identical**. Baseline report 109,232 / 47,100 becomes 110,732 / 48,600, with
the same 62,132 net and 395,538 ending bank. [Comparison](baseline-comparison.json).
The pre-tick state was reconstructed through the real endpoint functions using
exactly the three observed accepted browser decisions; its full action prefix
matches the end save before advance. No production save was mutated by this
offline reconstruction. An earlier comparison input was stale because it had
been copied before the browser explicitly saved; it compared the original
zero-facility state and was not evidence for the facility scenario. That result
was replaced by the correctly reconstructed fixture.

An initial baseline helper error decoded UTF-8 Git source with Windows' default
encoding, producing mojibake in one private-news line. This caused a false state
mismatch; the helper now reads UTF-8 explicitly. The diagnostic failures remain
under `runs/gap25/`, and no source edits were needed.

The full **unfiltered** `python -m pytest -q -n2` gate finished with **1,257
passed in 7,451.32 seconds**, native subprocess exit **0**, at 21:41:54 UTC.
All **610** raw pre/post source, test, data, script and configuration file hashes
match, with no changed files. The imported package was this worktree's `src`.
[Terminal log](gate/pytest.log), [native receipt](gate/status.json), and raw
[before](gate/source-pre.json) / [after](gate/source-post.json) manifests retain
the proof. No tested source was changed or rebased after this gate.

## Telemetry reconciliation and limitations

[Audit](audit.json) and [indexed decisions](decisions.json): the original 46
accepted-action records remain an exact prefix of the 50 end records. All four
new decisions match CSV steps 2-5 in kind, parameters, team, web source, season,
week and order: facility upgrade, flavor choice, sponsor acceptance, advance.
Coverage is **4/4 accepted decisions**, with zero unmatched decisions.
The original nine per-manager weekly snapshots remain a prefix of ten.

[Owned usage events](usage-events.json) exclude all lines inherited from the
original copied world. Five browser attempts pair with five successful results
by request ID: the four decisions plus explicit Save. Navigation and Full report
opening appear separately. Save and read-only navigation are outside the
accepted-decision vocabulary. The initial stale Company reference was rejected
by the browser tool locally; it emitted no HTTP rejection and is retained in
CSV step 1. The only console error was the existing missing favicon request.
Usage is a bounded retained sidecar; these counts do not establish exhaustive
funnels or attention duration.

The browser was closed and its own server PIDs 33540 / 4784 stopped after Save.
The detached full gate was left running. The original save SHA-256 remains
`5a89f0fce54c7855224376d7a1370838e526de3dc8649ec3f3f81d5433caf42a`.

## Local flywheel findings

The esports-playtest flywheel tool was unavailable in this agent's tool catalog.
Pre-play context came from the original root playtest evidence, canonical guide,
playtest skill and the relevant memory registry; no remote flywheel search or
record is claimed. These post-play findings preserve the local loop:

- High confidence: a cost charged correctly can still be misleading if it is
  netted into a revenue line. Weekly settlements should return actual income
  and charged costs separately for reporting consumers.
- High confidence: retaining the net-return compatibility wrapper permits
  direct callers to keep their contract while per-manager reports use gross
  accounting; exact saved-state and event-log equality verifies the boundary.
- Pain point: the old report concealed facility costs even though the live
  finance screen exposed them, making an otherwise correct bank movement
  difficult to reconcile. The explicit included-in-expenses line resolves that
  observed friction for this one-week scenario; it does not establish balance.
