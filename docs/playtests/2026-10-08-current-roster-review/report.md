# Current-squad match-review advice

Question: after a player leaves, does the historical match finding remain useful without suggesting an unavailable roster action?

Build: base `38f4e9c48dbe4cbb344e525f5bf74f075042e273` plus the localized server patch and regression test, frozen during the full gate. Runtime: GPT-6.1-sol / medium. Independent browser server: loopback 8460, world JEB4V, seed 2038, Team Nexus, S1 W1–W2. The primary checkout and root's test world were not used for mutations.

## Observed player result

The real W1 match produced Echo's 0.55 average-rating finding. Before release, the review offered a lineup action. The browser released Echo for 66,000 credits and returned to Dashboard. The historical finding remained, with the explanation: "Historical match finding — this player is no longer in your squad, so roster changes for them are unavailable." No Echo lever remained. A fresh Club readback and the saved squad confirmed Apex, Phantom, Vortex and Ghost, with Echo absent. `departed-player.png` was visually inspected; `pre-release-dom.txt`, `departed-player-dom.txt`, `review-readback.json`, and `club-after-dom.txt` preserve text evidence. This main-based match differs from the integrated root test's 0.72 rating; no historical numbers were changed by the fix.

Five CSV rows retain intent and expectations written before actions. The first Advance attempt was blocked by the automatic handbook; no request was sent. Recovery closed the guide and advanced. The recovery driver's wait for a literal `S1 W2` label timed out because the header displays `Season 1 · Week 2`; a fresh browser session and persisted action log confirmed the accepted advance before the pending observation was finalized. No duplicate Advance was issued. World creation used browser HTTP setup; Advance, Release, navigation and Save used visible controls.

## Decision telemetry

Both accepted decisions matched the persisted log (2/2, 100%): `saved-decisions.json` index 0 is `advance`, source web, Team Nexus, S1 W1; index 1 is `release`, player_id echo, source web, Team Nexus, S1 W2. `saved-squad.json` preserves final roster and telemetry snapshot count. The blocked attempt is unverified/outside the decision log. Setup creation, read-only navigation and explicit Save are outside its decision vocabulary. `telemetry-report.txt` comes from a directory containing only this session's save. Coverage is specific to these two decisions; no broader gameplay or balance claim follows.

## Browser usage

The retained bounded sidecar contains 38 events across four page sessions for JEB4V, all preserved with indices in `usage-indexed.json`. It contains one attempt/result pair each for Advance, Release and Save (3/3 paired, zero unmatched attempts or orphan results). Retained coarse views: Dashboard 4, Club Squad 2, Lobby 4. `usage-report.json` preserves the independent aggregate. UI advice-control clicks are not individually instrumented. The blocked handbook attempt is not a recorded HTTP rejection. Visible-time slices and receipt spans are proxies; page closures, best-effort delivery and bounded retention prevent exact duration/funnel conclusions. Setup HTTP did not use application request hooks.

## Validation and flywheel

Sixteen focused parameter cases cover current/departed/missing/missing-record players, young/veteran advice, and primary/second acting human manager. They confirm preserved historical diagnostics, current teammate advice after a skipped departed finding, unrelated tactic levers, coach gating, and no changes to initialized GameState. No JavaScript or simulation code changed. The full unfiltered `pytest -q -n2` passed 1,199 tests in 5,413.55 seconds, with exit code 0, before commit. `full-gate.stdout.txt` preserves its output; `full-gate.json` confirms unchanged before/after SHA-256 hashes for the server and regression test. Raw DOM evidence intentionally preserves table whitespace; source, test and report whitespace checks passed.

The flywheel MCP was unavailable. Initial guidance came from the root task's reproduction and repository skill; the local recorder fallback was provided during the browser recovery, so this session's flywheel read happened after initial creation/Advance attempts and before Release acceptance. `flywheel-inherited.json` preserves eight prior findings including root's 0062–64. `flywheel-recorded.json` retains two learnings and one pain-point through the authorized project recorder. Learnings: derive current player actions from the acting squad; filter unavailable advice before lever deduplication. Pain-point: the automatic guide can intercept an Advance click and must be explicitly closed. Confidence is high for this reproduction, with seed/world evidence above.
