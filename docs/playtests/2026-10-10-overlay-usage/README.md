# Overlay inspection telemetry acceptance

Tested base `042d86d3161fc5fa3185091031ba546193b2e97e` plus this branch's uncommitted overlay change, configured GPT-6.1-sol / medium. Browser: isolated Playwright CLI session `overlay-usage`; server `127.0.0.1:8484`; copied immutable natural W9 world `26UHC`, seed 2038, Team Nexus. Source save came from the `current-main-recovery-playtest` media-sponsor run. The original world, primary checkout, canonical CSV and user browser were untouched.

## Contract

Usage `interaction` targets are fixed and count-only:

- `profile/{player,team,staff,manager}_{open,close}`: successful visible content begins an inspection. Switching identity closes the previous successful inspection and opens the next. Returning with Back counts another inspection; refreshing the same identity does not. Loading, failed, cancelled or stale responses never open an inspection. Repeated close does not duplicate. A failed replacement closes the former successful inspection when unavailable content replaces it.
- `handbook/open`, `handbook/close`: visible overlay lifecycle, including automatic first-week opening. Duplicate open/close calls while already in that state do not duplicate.
- `handbook/section_first_week`, `handbook/section_screens`, `handbook/section_glossary`: one initial section per opening plus actual section changes. Reselecting the same section does not duplicate; closing resets the section. Hidden rendering does not count.

Player, team, staff and manager use the actual shared profile overlay plumbing. Browser acceptance covers player/team/manager; staff, cancelled/stale responses and automatic handbook opening are verified by executing the real handlers in the Node contract test. This change does not add profile subsection/dwell measurement. Underlying screen visible-time remains a page-visibility proxy and is not overlay attention time.

The client and backend allowlists are tested for exact equality. The existing report `events` map counts these targets. No private profile identity, handle, query text, handbook prose, selector, or payload is included. Existing server-owned world/team linkage remains. Navigation never adds accepted campaign decisions; usage/timestamps remain in the bounded sidecar.

## Observed session and reconciliation

Five intention/outcome rows were written with `scripts/playtest_log.py` redirected to this session's `actions.csv`. Step 2 preserves an accidental different-player refresh and the corrected Echo retry; it is marked partial rather than rewriting the expectation. Echo's visible profile, team Back navigation, manager profile and handbook Key terms are preserved in snapshots. The failure test injected a browser response, not a real rejected HTTP request.

The retained snapshot contains 66 world events across two page receipts plus three lobby events. Overlay interactions: six player opens and six closes (including the incidental player transition and repeated inspections), one team open/close, one manager open/close, two handbook opens/closes, two initial First week sections, one Screen guide and one Key terms section. All 24 observed successful overlay/section interactions are retained; repeated Screen guide, same-player refresh and duplicate closes add none. The injected failed load adds no successful inspection event. This is bounded retained-event evidence, not a guarantee of complete funnels across arbitrary browser sessions.

Save emitted one attempt and one successful paired result, with zero unmatched/orphan requests. No other campaign mutation was performed. The save remains byte-identical: SHA256 `89637d44d2c73cf60a7c027d3b7d9cdf3634d02e88439f9427aa1ddb2a26cb11` before/after, 43 unchanged accepted decisions and eight unchanged telemetry snapshot entries in one manager group (`mgr_team_nexus`: 8 before/after). Seed/time and all serialized campaign data remain identical. There are no serialized RNG fields to compare separately; the complete-save comparison includes all deterministic seed inputs. No usage/timestamp field was added to GameState. Evidence: `audit.json`, `usage-events.jsonl`, `usage-report.json`, `baseline.json`.

## Validation

Focused backend/frontend suite: 38 passed before final extra out-of-order/failure-replacement handler cases; the complete Node handler check passes with those final cases. JavaScript syntax and `git diff --check` pass. The same full unfiltered `pytest -q -n2` gate completed: **1262 passed in 6596.45s (1:49:56)**, native exit **0**, with source-freeze equality **true**. Before publication, this agent independently reread the terminal receipt/log and verified every frozen file still matches both pre/post manifests. No source/test edits or rebase occurred during or after the gate. Evidence: `terminal-gate-proof.json`, `full-pytest-summary.txt`; complete original log, receipt and manifests remain in `runs/overlay-usage/`.

## Flywheel findings

No callable flywheel search/recent/record tools were exposed in this agent's tool inventory. The following findings are retained locally for later ingestion:

1. Learning: underlying Club/dashboard views cannot answer whether profiles were inspected. Fixed overlay type events now distinguish that interaction without retaining a player's identity (high confidence; browser + sidecar evidence).
2. Learning: an initial handbook section is meaningful inspection coverage, but it should count once per opening. Duplicate section selections and profile refreshes inflate counts unless state is tracked (high confidence; real handler tests + repeated browser clicks).
3. Pain point: coarse events cannot identify which player a tester accidentally selected; preserve the player-intent CSV and visible readback alongside privacy-bounded aggregate counts. Profile raw fetch failures still lack request usage hooks and are explicitly outside this fix (high confidence; corrected step 2 and injected failure).

Cleanup completed after acceptance: Playwright CLI `overlay-usage` closed; subsequent CLI list reported no browsers for this task workspace. Verified port 8484 was owned by Python server family PID24924 -> PID34604 with the exact owned command. Sent Ctrl-C only to server exec session55359; it terminated (exit1). Fresh process and socket inspection proves both server PIDs gone and no listener on8484. Full-gate writer12516 and launcher30704 remain alive; frozen source/test hashes remain unchanged and gate receipt is still pending. Evidence: `cleanup-server-before.json`, `cleanup.json`. The retained telemetry audit is the earlier bounded acceptance snapshot; browser closure occurs after that snapshot.

Snapshot-count correction: the original audit counted `len(telemetry_snaps)` as one snapshot, which is the number of manager groups. `audit-original.json` preserves that original evidence; `audit.json` now reports group counts 1/1, total entry counts 8/8 and per-manager counts. `snapshot-count-correction.json` records the independent readback and original/corrected audit hashes. `baseline.json` is preserved unchanged; its `snap_count: 1` also denotes a manager group. No CSV outcome claimed one snapshot, so its original five rows are unchanged.

Durable step-two evidence: the original CSV reference `runs/overlay-usage/echo-dedup-corrected.txt` now maps to the byte-identical tracked copy `docs/playtests/2026-10-10-overlay-usage/echo-dedup-corrected.txt`. This preserves the successful corrected Echo/refresh/double-close readback (`hidden: true`) without changing any original CSV bytes, timestamps, expectations or outcomes. This is preservation of the original acceptance artifact, not a new runtime test.

Integration follow-up: PR369 had no CI because exact28cb conflicted with newly merged main64ee15f (Market-search allowlists/tests). The authorized uncommitted integration and fresh three-row browser acceptance are documented in `integration/README.md`; its NEW full gate is running. The 1262-test proof above belongs to the original published source and is preserved as historical evidence; it does not validate the new integrated source. Original five-row CSV bytes and readbacks are unchanged.

Integrated-source terminal validation: the necessary main64 merge now has its own successful native full gate, **1285passed5155.67s**, exit0 and complete616-file frozen-source equality/current readback. Raw integrated proofs and the separate three-row browser acceptance are preserved in `integration/`; all original five observation rows and original1262 proof remain unchanged.
