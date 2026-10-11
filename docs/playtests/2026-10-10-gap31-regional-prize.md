# GAP31: resolved prize income reporting

Build: isolated managed worktree based on main `64ee15f19f7acf80a2dbb7e5035d8c037128fea6`, with the reporting patch. Model: gpt-6.1-sol, medium. Player surface: direct HTTP through separate servers on 8497 (patched) and 8498 (baseline). Both servers were terminated afterward. Root/user servers 8496/8421 were untouched. World 26UHC, seed 2038, copied S1 W14 fixture; original saves were read only.

The actual phase-transition payout code is unchanged. Completed weekly income now includes the exact human-team balance credits awarded during that block, with a named recipient explanation. This covers regional placement, regional playoffs, Masters, Champions, and Challengers. No payout amount, payout order, balance, RNG, or engine behavior changes.

## Observed acceptance

| Value | Baseline main64 | Patched |
|---|---:|---:|
| Bank before | 608,307 | 608,307 |
| Bank after | 741,367 | 741,367 |
| Resolved weekly income | 110,160 | 180,160 |
| Resolved weekly expenses | 47,100 | 47,100 |
| Regional placement prize included | 0 | 70,000 |

Report and Company Finances both expose the corrected income. The completed report says: "Team Nexus received 70,000 cr in tournament prize income this week (included in reported income)." Repeated Report and Finances reads returned identical responses. Bank gain `741,367 - 608,307 = 133,060` exactly equals resolved income minus expenses `180,160 - 47,100 = 133,060`. The original expectation hypothesized an additional 100 facility-upkeep discrepancy, but these copied-world values do not expose one. Correction step 7 preserves the original expectation and records the exact arithmetic. Facility expense paths owned by PR #373 remain untouched.

Both complete saved campaign JSON files are byte-identical, SHA256 `8e8b3f1706501000e8599c0951633f506f7f43d4ea1f0e3b8ef45691f3b03984`. This comparison includes actual payouts and all deterministic campaign state. Reporting changes only the transient report.

The two original isolated transport attempts were blocked by incorrect session restoration before Advance. Both recovered public action sequences then advanced and saved successfully, but their harness processes returned native exit 1 afterward: a post-save assertion expected `/api/report` to return an unwrapped report. The preserved actual response is `{report: {...}}`. Explicit CSV correction step 5 records this failure; independent UTF-8 receipt and complete-state comparison returned native exit 0 without replaying Advance. The failed harness runs are not classified as wholly successful.

## Decision and usage reconciliation

Each W14 copied world retains the original 64 accepted decisions unchanged and adds exactly one accepted `advance` at index 64: S1 W14, regular, manager `mgr_team_nexus`, team `team_nexus`, source `web`, empty params. CSV steps 3 and 4 match these respective decisions. The later W16 copied fixture retains 71 decisions and adds exactly one index71 advance, matched by step8. Across the three independent copied sequences, 3/3 consequential advances are captured. Steps 1 and 2 are blocked pre-advance attempts; steps 5, 6, and 7 are read-only saved-evidence audits, outside accepted-decision instrumentation. Eight scoped rows preserve expectations, outcomes, failures, and corrections.

The original `telemetry_snaps: 1` field in `state-comparison.json` counts manager streams, not snapshots. Correction step 6 and `telemetry-corrected.json` show one `mgr_team_nexus` stream growing from 13 to 14 weekly snapshots, with an exact retained prefix and one new snapshot. Direct HTTP actions do not emit browser usage events; browser navigation/time coverage is unavailable for this scoped session. No claim of browser visual acceptance is made.

## Verification and evidence

Five targeted tests passed in 2.76 seconds. They cover regional placements across all three regions, regional final and semifinal payouts, Masters, Champions, nonrecipients, zero-prize weeks, primary income mirroring, exact actual payout deltas, per-manager resolved income, and repeat-read state/report purity. All payout functions and constants remain unchanged. A separate controlled diagnostic (not a player session and not an added frozen-suite test) verifies all three regional Challengers champions' actual 25,000 credit deltas, reported income increment, and single recipient note; native exit 0.

Evidence under this worktree:

- `runs/playtests/2026-10-10-gap31-regional-prize/acceptance.json` and copied saved campaign: patched public responses and state.
- `runs/gap31/baseline/acceptance.json` and copied saved campaign: baseline main64 public responses and state.
- `runs/gap31/state-comparison.json`: both actual hashes, income/bank fields, new decision, complete-state equality.
- `runs/gap31/telemetry-corrected.json` and `telemetry-report.txt`: exact decision/snapshot reconciliation and campaign-wide usage counts.
- `runs/gap31/challengers-receipt.json`: scoped controlled diagnostic.
- `runs/gap31/receipt.json`, `full-pytest.log`, `freeze-before.json`, `freeze-after.json`: full suite and complete source/config freeze receipts.

Flywheel tools were unavailable in this agent's exposed tool inventory. Local findings retained: (1) prize payouts after finance mirroring must be included in the resolved report; (2) comparing complete saved state isolates report-only fixes; pain point: a legitimate prize award looked like unexplained bank income. Confidence high for the copied W14 case and tested payout branches. Full gate results are reported separately only after actual completion.

## Additional W16 regional-final fixture

Root's real browser session on unchanged main64 produced a regional-final loss0-2 versus Vanguard after fresh Haven/anti_exec/light preparation, Pulse focus, and respect_rival media response. Its baseline income111036 and expenses47100 explain only63936 of the183936 actual bank gain: exactly120000 runner-up award omitted. This is the same GAP31.

Step8 copied root's immutable preadvance fixture and baseline saved campaign into a separate folder and played one Advance through the already-frozen patched code on isolated API port8511. No source/tests changed; independent current freeze receipt confirms the same625 files and hashes. This acceptance used direct HTTP, not browser UI; root's browser DOM remains separate baseline evidence.

The native API harness returned exit0. Both Report and Finances show income231036 and expenses47100; bank805569->989505 gives183936, exactly equal to231036-47100. The named note is "Team Nexus received 120,000 cr in tournament prize income this week (included in reported income)." Repeated public reads were equal. Complete patched and copied baseline saved JSON are byte-identical, both actual SHA256 `32d6564f38d0adff259bd59e53aaf3b45d44df3de8b10470ca301e1b6719bba6`.

Saved accepted decisions71->72 retain the exact prefix and add only index71 advance at S1W16 playoffs, mgr_team_nexus/team_nexus, sourceweb, empty params. The single mgr_team_nexus weekly snapshot stream15->16 also retains its exact prefix. Isolated8511 was terminated in the harness finally block; root/user servers untouched. Durable evidence: `runs/gap31/regional-final/acceptance.json`, source/baseline copies and server identity, `regional-final-terminal.log`, `regional-final-exit.txt` (0), and `regional-final-freeze.json` (625/current matches before). No additional100 residual is claimed.


## Completed native gate and publication recovery

The previously launched full suite completed with 1279 passed in 6275.09s (1:44:35), terminal exit0 at 2026-10-11T00:28:24.462579+00:00. Root independently verified all625 pre/post/current source/config/test/script/workflow fingerprints, both complete baseline/patched saved-state byte equalities, accepted prefixes and snapshot prefixes, and exact income-minus-expense reconciliation for W14 and W16. Durable native and public acceptance receipts are copied to [2026-10-10-gap31-evidence](2026-10-10-gap31-evidence/), alongside a separate root publication review. Raw private session bootstrap and authentication stay untracked. No new local tests were launched, following the user's instruction. Current-head remote CI and root published-head review remain required before merge.


Root publication recovery recorded the two learnings and one pain point in the local Agora esports-playtest flywheel, using the existing acceptance evidence. This occurred after the original session; it does not retrospectively establish pre-play inheritance. Original agent tool unavailability remains qualified. Actual entry IDs and recording time are preserved in 2026-10-10-gap31-evidence/late-flywheel-recovery.json.


Current-head review correction: inline4239895510 correctly identified that the CLI still labeled total report income as sponsor income. The CLI now calls this amount income; named tournament-prize notes continue to identify recipients and amounts. No payout or GameState behavior changed. The earlier1279-test native receipt precedes this one-line CLI correction; its625-file source freeze is historical, and the CLI path now differs. No new local tests were run per direct user instruction. Exact updated-head remote CI remains required.
