# UI usage acceptance - 2026-10-06

Fresh sandbox Team Nexus world **63BFF**, seed **2037**, S1 W1, on dirty
`0aabb0d` plus the usage patch. A separate worktree server ran at loopback8437;
the existing8421 game was untouched. Runtime gpt-6.1-sol/medium came from the
assignment. Social LLM was off. Used the repo playtest-log skill/helper with
ROOT set to this checkout and a distinct per-session CSV.

Verified browser behavior: created the campaign, inspected Club Squad and
Development, changed training to Mechanical, and read back the active button
and mechanical attribute descriptions. Creation attempt request3 was stamped
with lobby membership; the paired result was stamped63BFF/team_nexus. Training
request14 had a success result and matched saved action_log[0]: set_training,
focus mechanical, delegate_to_coach False, source web, S1W1, mgr_team_nexus.

A Release Phantom attempt from the five-player roster hit a browser-control
confirmation timeout. It produced no observed HTTP usage attempt. A new tab
restored the dashboard, but later Season clicks did not change the screen.
The blocked rows were preserved; rejection, omitted subtabs and replay controls
are **not browser-proven**. Source-derived subtab and Node frontend contracts
cover them structurally, while endpoint tests cover rejection/failure isolation.
The dashboard screenshot is docs/playtests/evidence/2026-10-06-ui-usage-dashboard.png.

Saved63BFF through separately logged local HTTP API after browser input stalled.
The saved decision log has exactly **one** gameplay record (the training change)
and **zero** weekly snapshots. No release decision exists. No week was advanced.
Gameplay decision coverage is **1/1** for accepted management decisions;
creation, navigation, browser-control failures and save are not gameplay records.

Audit snapshot: **34** retained sidecar events across **two page sessions**,
**two attempts/two paired success results**, no unmatched/orphan pairs. Four of
nine CSV rows have usage evidence; four are outside browser capture and one
blocked release outcome remains unverified. Visible-time totals at snapshot:
lobby19452ms, dashboard213740ms, Club Squad3401ms, Development18410ms. These are
page visibility proxies, including observation/control recovery time, not
attention or exact intent duration. Later heartbeat events may increase totals.

Evidence: docs/playtests/actions.csv (nine append-only
observations), docs/playtests/evidence/2026-10-06-ui-usage-analytics.json (indexed decision + raw
usage audit), screenshot above, docs/playtests/evidence/2026-10-06-ui-usage-flywheel.json. Flywheel
pre-read inherited telemetry findings; post-loop wrote two learnings and one
pain point (esports-playtest-0017 through0019). The parent appended these nine rows to the primary history, preserving all
earlier rows byte-for-byte (296 rows total).

Audit provenance correction: step8 default-encoding read failed; its outcome
repeated the prior valid audit. Step9 preserves that failure and confirms the
same decision evidence with an explicit UTF8 read. No earlier outcome was
rewritten to hide this failure.
