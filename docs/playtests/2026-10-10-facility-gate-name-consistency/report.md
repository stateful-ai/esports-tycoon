# Facility gate naming acceptance

Tested base 042d86d3161fc5fa3185091031ba546193b2e97e plus the dirty naming fix,
using gpt-6.1-sol / medium and standalone Chromium Playwright on isolated port
8486. World 26UHC, seed 2038, S1 W10. The copied source fixture SHA256 remains
5a89f0fce54c7855224376d7a1370838e526de3dc8649ec3f3f81d5433caf42a.
Original saves, sessions, primary checkout, and shared actions.csv were untouched.

Company Finances at L0 visibly named Media Department for Stream L1 and Apparel
L2. Facilities displayed the matching heading, Content Desk project, 150000 cr
cost, 1500/wk upkeep, and Stream unlock benefit. Building it returned "Media
Department upgraded to level 1". Independent public readback confirmed L1,
exactly 150000 deducted (483406 -> 333406), and upkeep 1500. Stream became open;
Apparel still visibly required Media Department L2. Dashboard News used the same
canonical department name and cost. Media Studio L2 remained unaffordable at
350000: the Upgrade button was disabled, with no rejected request or decision.
L2 unlocked behavior is covered by serializer regression tests, not this cash
limited player session. Screenshots and public readbacks are retained under
runs/playtests/2026-10-10-facility-gate-name-consistency/.

The CSV contains ten immutable intention/outcome rows: seven met, one blocked,
two unexpected harness/audit observations, and the final met audit. Step 7's
Save click actually succeeded; the harness watched /api/save instead of the
observed /api/actions/save and timed out. Step 8 preserves the correction and a
second verified Save. Step 9 preserves an audit type mismatch: telemetry params
are string-valued. Step 10 verifies the actual contract. Before logged acceptance,
a body-text probe failed cp1252 output, then succeeded with escaped JSON; an
acceptance setup read initially lacked UTF-8. Neither failure mutated the world.

## Reconciliation

Persisted action count 46 -> 47. Exactly 1/1 new accepted gameplay decision
matches build row 3 at index 46: facility_upgrade, marketing_office, level "1",
cost "150000", team_nexus, mgr_team_nexus, web, S1 W10 regular. Save/navigation/
disabled controls do not create accepted decisions. No unrelated new decisions.
See audit.json and telemetry-report.txt (the latter includes the fixture's 46
inherited decisions; it is not a session-only feature adoption estimate).

Separate browser coverage: 26 retained world events since the first logged
intention: 2 session_start, 9 view, 9 visible_time, 3 attempt, 3 result. All 3/3
attempts have successful result counterparts: build request 12, original Save
24, recovery Save 10. Request IDs are scoped to their browser pages. No L2
request occurred. Coarse usage targets cannot prove exact intended parameters;
that proof comes from persisted decisions and public readback. Retained sidecars
are bounded and visible time is not attention. usage-evidence.json removes page
session identifiers; usage-report.json therefore intentionally lacks those
session receipt spans. The private SID was neither printed nor committed.

## Mechanical equivalence and validation

17 targeted tests passed. Serializer cases cover L0/L1/L2 with low/high
reputation; upgrades cover all six departments and retain historical news.
equivalence.json compares base economy.upgrade_facility with the edited code
across six departments at L1 and L2: success flags and the entire GameState are
identical except intended newly appended news text. Costs, stable keys, levels,
RNG state, and existing historical narrative remain equal. No engine/data/JS
changes; unrelated tuning gates are not triggered.

The full unfiltered pytest -q -n2 passed: 1264 passed in 7609.70s
(2:06:49), native subprocess exit 0. The detached writer recorded the actual
worktree import, terminal output, and all 545 source/test/data/config fingerprints.
Pre/post manifests are identical, and publication-time verification also found
the current full file set and every raw hash identical. These native proof files
are retained beside this report. The gate ran on base 042d86d plus exactly the
source/test diff published with this evidence; documentation-only evidence updates
after completion do not change the tested source. Own browser closed; own server native
family 36556 / 21968 / 34300 stopped and port 8486 no longer listens.

Flywheel tools are not exposed in this runtime; inherit/record could not be
performed. Local retained learnings: canonical department labels must be reused
by gates and reports; stable facility keys can remain save-compatible while copy
is corrected. Pain point: unrelated obsolete department wording makes the
sponsorship unlock path difficult to discover. Confidence high for this copy
fix and the observed L1 causal unlock; no claim about game balance.
