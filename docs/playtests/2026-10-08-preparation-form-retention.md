# Preparation form retention acceptance

Isolated browser server 8469; copied world **26UHC**, seed **2038**, Team Nexus,
S1 W5. Runtime **gpt-6.1-sol / medium**. Base `26b9281357e74de1bdc7beffe5d5660fe05e47b4`
with the form patch dirty. Source hashes are in the accompanying audit.
Original source career and other browsers were untouched. No week advanced.

The manual form now hydrates the server-returned booking only when its fixture
matches the displayed fixture and every booked option remains available. It
uses server choices; no simulation formulas or browser persistence were added.

Browser steps5-6 selected and booked **Alpine Echo / Bind / Mental Reset / Intense**.
The booking rerender retained all four choices. Steps7-8 changed only intensity
to **Normal**: partner, map and objective stayed selected and were applied exactly.
Steps13-16 saved, reloaded, reopened Match / Prep, and confirmed the same final
booking in controls and public `/api/club` readback. Browser page errors: **0**.
The single-map W5 fixture exposes only Bind; alternate-map retention is covered
by the frontend regression along with stale fixture, no booking, no fixture and
unavailable partner/map/objective/intensity boundaries.

The [16-row session CSV](2026-10-08-preparation-form-retention-actions.csv) has
**14 met, 2 blocked**. Steps3 and9 used incorrect navigation/save selectors;
timeouts are preserved, and steps4 and13 recover using observed controls.
They are not inferred HTTP rejections. Their snapshot paths were nominated
before capture but were not emitted on timeout; the actual errors are in the CSV.
The pre-action intent for each row was written with `scripts/playtest_log.py`
using a separate session journal. Canonical `actions.csv` remains unchanged.

The [audit](2026-10-08-preparation-form-retention-audit.json) reconciles saved
accepted decisions: **2/2 (100%)**, ledger indices20-21, `set_preparation`,
`team_nexus`, web source, S1 W5, fixture `s1w5m1am`, all four parameters and order.
The 20-entry baseline prefix is unchanged, as are all **4 weekly snapshots**.
Navigation/local selects/Save are outside the decision vocabulary.

Separate retained browser usage: **35 events**, **2 retained page sessions**,
8 views, 17 visible-time slices, 3 attempts and 3 results, 2 session starts/ends.
The stream pairs both preparation requests and the successful Save request
with status200/success, by page ordinal and request ID. It does not record
individual select intentions or prove complete visit count or attention.
Scoped `telemetry_report.py` and `ui_usage_report.py` ran only on this test
world's directory; raw snapshots/reports remain under
`runs/playtests/2026-10-08-preparation-form-retention/`.

Flywheel pre-read inherited preparation/recent findings through the authorized
local recorder fallback. Two learnings and one pain point were recorded after
play as `esports-playtest-0089`, `0090`, `0091`: retain valid current-fixture
choices before previews; guard fixture/option boundaries; preserve failed
attempts and distinguish in-memory reload readback from successful durable Save.

Validation: frontend regression and JS syntax passed. The full unfiltered
frozen-source gate (`python -m pytest -q -n 2`) completed with **1201 passed in
5919.17s**, exit **0**, at `2026-10-08T23:15:27.911229+00:00` (pytest PID32772).
Before publication on October10, all **540** manifest files matched this
worktree byte-for-byte. The added test's LF/CRLF-only difference was resolved
by copying the tested bytes; its Git diff was unchanged. The gate manifest,
result, log and publication-source-check.json remain in the session run directory.
Remote main at publication was `4b048242ab366ce96a96b6460289457859e5a10e`;
the isolated patch remains based on the tested `26b9281`. Preparation clarity
PR357 (`5dc13c67`) was still open: its labels and cost preview run after this
hydration insertion, so both changes are compatible by source inspection.
Their integrated runtime remains a separate merge validation step.
Engine/data/simulation
math did not change, so balance/pacing/snowball/floor gates are outside scope.
