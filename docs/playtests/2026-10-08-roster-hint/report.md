# Browser roster recovery acceptance — 2026-10-08

Build: `3ac34df3a476543d9e79dc4dc03bb381c04e397d` with the roster recovery copy/test patch dirty; game version recorded in actions.csv; trusted runtime GPT-6.1-sol / medium. Isolated server 8455, world 95WTN, actual saved seed 830794, Team Nexus Sandbox, S1W1→W2. No primary/user career was modified.

Player question: can a browser player recover from a four-player Advance Week rejection using its visible guidance?

The real rejection returned HTTP 409 and displayed: “you need 5 players to advance — open Market → Players and sign 1 more free agent, then try Advance Week again”. Week 1 and409,320 cr remained unchanged. Market Players displayed free agents and Negotiate controls. Grimwire signed at 6,600 cr/week for 55 weeks, 71% player streaming,79,000 cr release fee,518,000 cr buyout, starter role. Club readback showed five players. Retry returned 200 and advanced to W2. Browser Save returned 200 and the save retained recovery decisions.

The shared manager roster check retains its CLI sign-action hint. The web error is surface-specific; minimum-five rule and campaign/economy logic are unchanged. The multiplayer final revalidation text also directs affected managers to Market and re-ready, but this brief player session exercises only the solo path.

## Intent and evidence reconciliation

Eight meaningful attempts are in the separate 21-column actions.csv; expectations precede actions. `decision-evidence.json` captures all five saved decisions, in order: index 0 release phantom; index 1 negotiate_open fa_2; index 2 reopen fa_2 after reload; index 3 accepted negotiate_offer with the terms above; index 4 advance. All are team_nexus / mgr_team_nexus / web / S1W1 regular. Five of five accepted decision records are matched to four CSV rows (2,5,6,7); one weekly telemetry snapshot persisted. No rejected advance record exists, as intended. Creation, navigation, rejected requests and Save are outside this decision vocabulary and retain that gap.

Bounded browser usage is separate: 58 retained events, 47 associated with 95WTN and 11 with lobby. Eight attempt/result pairs: creation 1, release 1, negotiation 3, advance 2 (one 409/one 200), Save 1. No unmatched attempts or orphan results. Retained Market Players and Club Squad views support recovery navigation; receipt spans/visible slices are proxies, not attention or complete funnels. `usage-baseline.json` and `usage-end.json` retain endpoint snapshots; `usage-evidence.json` and `usage-report.json` retain end stream/audit. Setup browser reloads add page sessions; totals do not represent one uninterrupted page visit.

## Interruptions and limitations

In-app browser initialization timed out. Standalone Playwright initially failed when printing Unicode to cp1252; UTF8 output fixed it. Initial seed 2038 lobby creation attempts did not produce an observed new request; Club click was intercepted by lobby. Later default lobby creation succeeded with actual seed 830794. Row1 preserves the requested2038 expectation and partial result; only factual seed/world metadata was corrected from the save. No2038 acceptance is claimed.

Reloading the browser closed negotiation overlay, requiring reopen and creating a second negotiate_open decision. Save driver awaited wrong `/api/save` URL and timed out, although actual `/api/actions/save` returned 200 and persisted data. Row8 retains the partial driver outcome; saved state and matched browser result verify successful Save.

Pre-play recent flywheel findings were inherited. Post-play two learnings and one pain-point were recorded via Agora flywheel recorder as esports-playtest-0046/0047/0048; local `flywheel.json` preserves entries. No telemetry gap is inferred away from HTTP access logs.

## Validation

Focused regression tests: 2 passed, preserving HTTP 409, byte-identical GameState, no ready/dirty mutation, count-sensitive recovery wording and unchanged CLI hint. Node syntax check of app.js passed (no JS source changed). Full unfiltered `pytest -q -n2` launched with durable helper; final result will be appended before commit. Copy-only scope does not trigger balance/pacing/floor/snowball gates.

Seed setup evidence clarification: attempt 1 used fill 2038, manual change dispatch, 500 ms wait, Team Nexus click and Club click. Attempt 2 used mode-solo, fill 2038/manual change, awaited preview?seed 2038,500ms wait, Team Nexus click, then 15 s response timeout. Final successful debug run reloaded lobby and clicked Team Nexus without any seed fill/change. The fresh lobby randomizes seed; saved campaign seed is830794. Contemporaneous displayed Seed and raw creation request body were not captured. This is insufficient to establish a product defect; automation rerender targeting remains a possible explanation. No seed UI fix was made.


Final full-suite result: unfiltered `pytest -q -n2` completed successfully with exit 0: **1183 passed in 6221.24s (1:43:41)**. The durable helper set `PYTHONPATH` to this worktree's `src` while using the primary Windows venv. Completed output is retained in `full-pytest.log` and `full-result.json`. The source/test patch matches the independently reviewed frozen patch after CRLF normalization; no source or test changes followed this full gate. Earlier pending wording above records the state when originally written. All eight CSV rows and every earlier evidence artifact are preserved byte-for-byte; only this final result was appended to the report.
