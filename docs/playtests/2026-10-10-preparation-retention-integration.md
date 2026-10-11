# Preparation retention integration acceptance

PR357 merged at main `042d86d3161fc5fa3185091031ba546193b2e97e`, making
PR360's earlier base conflict. Resolve by hydrating all valid current-fixture
controls before the labeled form and initial cost preview. This report
supersedes the earlier source-inspection-only compatibility claim. The old
1201-test result applies only to the old source, not this integration.

Browser8469 used a separate copy of world26UHC, seed2038, Team Nexus S1W5,
with `gpt-6.1-sol / medium`. No week advanced. Current fixture `s1w5m1am`
already booked Alpine Echo / Bind / Mental Reset / Normal. Step5 retained
all four choices and displayed the server's **4-point** condition cost.
Steps6-7 changed only intensity to Intense, displayed **7.5 points**, booked
the exact four parameters and retained them after rerender.

Steps11-15 retained Intense, changed only intensity back to Normal, booked,
successfully saved through the observed Save control and reloaded. All four
choices and the **4-point** preview matched the public booking after reload.
Step16 intercepted the browser's `/api/club` response to give the existing
booking a synthetic future-fixture id. The form ignored it as a whole,
retaining Adriatic Sirens / Bind / Anti Exec / Light and the **1.5-point**
preview. This is a synthetic response-boundary check, not a naturally reached
future campaign fixture. Step17 removed that response override and restored
the real saved Normal booking and preview. Browser page errors: **0**.

The [17-row append-only session](2026-10-10-preparation-retention-integration-actions.csv)
preserves **15 met, 2 blocked**. Exact accessible names for Match and Save
timed out in steps2 and8 before requests; later steps recover with their
observed rendered ids. No HTTP rejection is inferred. The first audit read
failed under the default Windows encoding; rerunning in UTF-8 produced the
fresh [audit](2026-10-10-preparation-retention-integration-audit.json).
Canonical actions.csv was untouched; earlier session rows remain unchanged.

Saved decision coverage is **2/2**, indices22-23, web `set_preparation`,
Team Nexus S1W5, exact fixture/partner/map/objective/intensity and order.
The baseline22-action prefix and weekly snapshots are unchanged. Read-only
navigation, local choices, Save and synthetic response checks are outside
the accepted decision vocabulary. Separate retained browser usage contains
**54 events**:5 starts,18 views,22 visible-time slices,3 attempts,3 results,
3 ends. Two preparation requests and one Save have successful result pairs;
the crashed browser contexts lack ends, so these totals are retained events,
not a complete visit funnel or attention duration. Scoped decision and usage
reports live under runs/playtests/2026-10-10-preparation-retention-integration/.

Flywheel pre-read and post-record completed, with two learnings and one pain
point (`esports-playtest-0107` through `0109`).

Fresh full unfiltered `pytest -q -n 2` launched against a frozen integrated
checkout at the same main base, with import verification and exact source
hashes. Manifest started `2026-10-10T17:37:52.675540+00:00`, runner12356,
pytest36612. The terminal result is **1253 passed in 7959.26s**, exit **0**,
finished `2026-10-10T19:50:34.688875+00:00`. Publication source and staged Git
content were independently compared with the tested manifest before completing
the paused rebase, then checked again after commit. The tested `042d86d` base
was retained even though remote main advanced during the gate. The previous
head's CI does not validate this source; fresh CI follows the updated head.
Raw manifest, fullgate.log, gate-result.json and both publication-source-check
receipts are in the new run directory. Engine/data tuning did not change; extra balance/pacing/
floor gates are outside this gap's scope.
