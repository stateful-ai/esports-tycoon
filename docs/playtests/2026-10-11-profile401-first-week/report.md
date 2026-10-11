# PR401 corrected-profile browser acceptance — 2026-10-11

Played unchanged clean head `806eb37881ff9a49f7cfdf71785c99e5e5d5c7ca`, base `e7dceefc306649982bc15b9fe9c0f723246c1ce7`, using gpt-6.1-sol / medium. Read-only copied world 26UHC, seed2038, S2 W5. Own CLI browser `profile401-first-week` and listener8535. CUA browsers are unavailable per parent's verified inventory; Playwright CLI fallback was authorized. No tests, Node checks, native acceptance helpers, gates or analytics report commands ran. No PR/code/ref edits, advance, fixture simulation, flavor choice, mentor reassignment, badge fabrication or canonical save access occurred.

Before play, inherited flywheel0240–0245 and0238–0239. The package imported from this exact worktree. `source-before.json` and `source-after.json` freeze all425 tracked paths under src/ and data/ with raw SHA256 and Git blob IDs; the manifests and head remain identical. The full tracked worktree remains clean.

## Actual visible outcomes

- Nightsurge was selected through the Squad identity `team_kraken_unit_p0`, separate from map-lineup buttons. The screenshot shows **First observation · S2 W4 · CA52.2 — no earlier dated comparison ·1 recorded observation** and **First skill observation · S2 W4 — no earlier skill comparison**. The public owned profile returns `comparison_available=false`, `status=first_observation`, `overall_delta=null`, `elapsed_weeks=null` and one raw observation.
- Season analytics shows3 matches; latest recorded week S2W4 shows0 senior maps. These are separately labelled scopes.
- All five latest-week source chips are visible: practice+0.31OVR, senior matches0.00, bench scrims+0.01, career events0.00 and badges0.00. Expanding the breakdown visibly shows practice Game Sense+0.67 / Positioning+0.85 / Utility Usage+1.56 and bench Game Sense+0.03 / Positioning+0.03. Server-authored factors remain visible. Public profile GET200 independently confirms these values, `badge_tracking=true`, `badge_events=[]`, and no badge skill gain. The visible text says **No badge changes this week**.
- Hollowlock `fa_0` has cumulative CA63.0→62.8 from S1W5→S2W4 across23 recorded observations; this is regression, not overall flat growth. The separate Season2 skill panel has S2W0→S2W4 endpoints and **No measurable attribute movement between these observations**. Public profile GET200 confirms5 season observations, elapsed4 weeks, available comparison with steady status and all10 skill deltas zero. Screenshots were visually inspected.

## Preserved partial attempt and correction

Step5 expected Hollowlock to be overall steady. Actual cumulative history contradicted that expectation. A scroll locator targeting absent overall-flat wording timed out30s once; it was not repeated. This is a harness assumption failure, not a game HTTP rejection. Its raw output remains `05-scroll.txt`; `hollowlock-measured-flat.png` retains the original expectation-derived filename and does not establish overall flatness. Step5 is partial; step6 explicitly corrects the scope and uses observed season skill wording. Seven21-column official logger rows were staged before actions:6 met,1 partial, including the correction row.

## Save and telemetry evidence

One explicit header Save POST `/api/actions/save` returned200 `World saved.`. Wire observer was installed before the first world load; `wire-events.json` preserves254 URL/method/status events without headers/cookies. It contains exactly one save request. Independent roster/profile reads used public GETs in this own authenticated browser context; their full synthetic owned responses are retained separately in `public-readbacks.json`.

The raw whole save remains byte-identical before/after: SHA256 `699c475c39b34cfc49748d0fe774f0ea8e753ac675cd36fc3ea5d82d27e8996f`. All120 accepted decisions and27 telemetry snapshots remain identical, at S2W5. No new accepted decision exists to reconcile; read-only navigation and explicit save are `not_instrumented` in decision telemetry, with evidence annotations on each CSV row.

Usage baseline is empty in this new isolated save directory. Raw retained end stream has27 rows:1 session_start,3 views,21 visible_time,1 attempt,1 result. Save request13 has one paired successful attempt/result200, with0 unmatched attempts and0 unmatched results. This is usage capture, not an accepted gameplay decision. No dedicated profile-view/skill-expansion hook exists on this played base; navigation intent coverage cannot be inferred from coarse views. No session_end event was retained on close. Retained sidecar counts do not prove complete funnels or attention duration. The only browser console error is favicon404 (`07-console.txt`), separate from the one harness locator timeout.

## Limits and cleanup

Positive/negative badge event rendering, legacy unavailable-attribution rendering, a naturally occurring zero-history profile, new skill growth, runtime rival privacy, and first→second observation transition remain UNVERIFIED. No claim about runtime integration with other feature PRs, automated tests, current main, CI, balance, or full acceptance is made. This is dated narrow acceptance on the exact played PR401 head only.

Own browser closed through its named CLI. Listener child38340 was confirmed to have parent32432 and the8535 command, then both were stopped; cleanup confirms both absent. Other listeners/browser contexts were untouched. Flywheel recorded two learnings0246/0247 and one pain-point0248 with exact session/head/world/seed evidence.

`evidence-allowlist.json` defines publishable artifacts. Sessions/auth/bootstrap/cookies/private helper scripts/server logs are excluded. Parent independently audits and publishes this staged CSV later; canonical history was not modified.
