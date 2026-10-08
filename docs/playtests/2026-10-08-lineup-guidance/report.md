# Lineup guidance acceptance

Build: dirty `3ac34df3a476543d9e79dc4dc03bb381c04e397d` with the lineup guidance patch. Runtime: gpt-6.1-sol, medium. Browser: isolated localhost port 8442; fictional Sandbox Team Nexus, seed 2038, world WJBF7, S1 W1.

Question: does the agent selection guidance agree with the known fixture maps?

The Match / Game plan screen showed Sahara Compass, league best of 1, Lotus. Beside it, the lineup card said to choose one agent per player for every map they play, use listed fixture maps when available, and choose for comfort otherwise. Its footer said saved agents remain until changed. Auto still showed the best-mastery agents, and the card fit beside the fixture at the browser's default viewport. No console errors were observed. Saving showed `World saved.` Screenshot: `runs/lineup-validation/gameplan.png` in the tested worktree.

One pre-action CSV observation was completed: 1 met, 0 blocked. One navigation click initially used the stale accessible name `Match`; the refreshed screen named it `Match 2`, and that button opened correctly. No agent locks, tactics, game plans, or weeks were changed.

Decision audit of this world's saved `campaign_04bfd43ffa20db57.json`: 0 action_log records, 0 telemetry_snaps. Read-only navigation and saving are outside the decision vocabulary; there were no gameplay decisions to match. The CSV's `recorded` annotation refers only to the browser stream, which captured navigation and saving. This session does not validate lock persistence by advancing a week; persistence was confirmed by tracing the existing model, save endpoint, and agent resolver.

Browser usage evidence was separate: 24 retained world WJBF7 events comprised 3 views (Dashboard, Match / Strategy, Match / Game plan), 18 visible-time slices, 1 attempt and 2 results. Save request 15 had an attempt and successful HTTP 200 result. The other result was world creation through `/api/new`, whose attempt belonged to the lobby. No gameplay mutation requests were made. Audit: `runs/lineup-validation/analytics.json`. Counts are retained-sidecar coverage, not proof of complete input capture or attention.

The pre-play flywheel fallback read the two recent esports-playtest entries and searched `lineup map known` (no matches). Post-play findings record that fixture maps can guide agent choices, agent assignments are distinct from dressed-player map lineups, and the prior map-timing copy contradicted the fixture. This single-week copy acceptance does not establish balance or a competitive effect.

Validation on the frozen source patch: all 1,181 tests passed with no exclusions in 4,563.97 seconds using `pytest -q -n 2` (exit 0, finished 2026-10-08T17:17:22.790833+00:00). Evidence: `runs/lineup-validation/persistent-full/pytest.log` and `result.json`. The earlier interrupted full run is not counted as a gate pass. Existing lineup tests also passed 6/6 in 3.86 seconds; JavaScript syntax and whitespace checks passed. Only this report was updated after the full gate.
