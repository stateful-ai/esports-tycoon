# Replay, recovery and rejected-action browser playtest

Played fictional Sandbox Team Nexus, seed **2038**, world **26UHC**, S1 W1 to
S1 W2, on clean fetched main **3ac34df**. Version and full commit are in the
26 CSV rows under session `2026-10-08-replay-rejection`. Root model and effort
are `unknown (not exposed)`; no configured default was substituted. The frozen
isolated server served `usage-report-overrides` on port 8438 with its own saves
and `SOCIAL_LLM=off`. Playwright handled the native release confirmation.

Player question: can I recover from a roster mistake, understand the resulting
week, and inspect the completed match using replay controls?

## Findings

1. **Release cost is misleading.** Phantom's confirmation promised six weeks
   of salary: 6 × 6,500 = 39,000 credits. The accepted release actually debited
   **78,000**, leaving 409,320 credits and four players. The existing contract
   release fee takes precedence; the interface must show the computed cost.
   Assigned to `release_cost_confirmation`, GPT-6.1-sol / medium.
2. **Development feedback is stale after changing a plan.** Selecting Rest for
   Vortex persisted, but the exhausted warning and tactical attribute list
   remained until navigating away and returning. The fresh screen correctly
   showed Recovery. Step 13 explicitly corrects step 11's overstatement about
   the immediate feedback. Assigned to `training_feedback_refresh`,
   GPT-6.1-sol / medium.
3. **Lineup guidance contradicts known maps.** Match → Game plan showed Lotus
   for the next fixture, while the lineup paragraph claimed the map was unknown
   and agents were committed before map selection. Assigned to
   `lineup_map_guidance`, GPT-6.1-sol / medium.
4. **Two intents have no dedicated usage hook.** Changing the lobby seed and
   opening Full report are absent from the retained coarse event vocabulary.
   Other matched rows sometimes cover navigation only, not all grouped clicks
   or reading. This is an explicit measurement limit, not proof of full funnels.

## Played consequences

Advancing with four players returned **HTTP 409** and a visible instruction to
sign one more. The week did not advance. Market recommended Slyblade, an
English-speaking Duelist Entry. His displayed market ask was 5,700/week; the
negotiation opening terms were 6,300/week for 62 weeks, with a 76,000 release
fee. Accepting those terms restored five players. Readbacks confirmed the new
player and Vortex's Rest plan.

One successful advance produced a **13–2 Lotus win over Sahara Compass**,
S1 W2 and 427,505 credits. Vortex's condition rose **32 → 43**. Development
explained “practice paused, match experience retained,” with +0.02 match OVR
and communications +0.1; displayed overall remained 74.5. One week cannot show
that recovery or signing caused the win, or establish balance.

The completed-match replay rendered the map, team markers, round controls and
score. Pause stopped it; round 13 correctly switched attacking side to Sahara;
16× playback reached the final 13–2 score and stopped. Close returned to the
weekly report; Continue returned to the same saved career. The screenshot was
visually inspected at `runs/playtests/2026-10-08-replay-rejection/replay-lotus.png`.
Ghost → Apex pairing and subsequent clearing both survived navigation. The
final browser Save succeeded, and only the isolated test tab was closed.

## Quantitative reconciliation

Evidence: [indexed decisions and save hash](evidence/2026-10-08-replay-rejection/decisions.json),
[indexed browser events](evidence/2026-10-08-replay-rejection/usage-indexed.json),
[usage report](evidence/2026-10-08-replay-rejection/usage-report.json),
and [single-save decision report](evidence/2026-10-08-replay-rejection/decision-usage-report.txt).

| Stream | Retained evidence |
| --- | --- |
| Accepted decisions | **7/7** matched in order by kind, requested parameters, team, manager, source and game week |
| Weekly telemetry | **1** persisted snapshot after the successful advance |
| Browser requests | **10 attempts / 10 paired results**, 9 success and 1 HTTP 409; 0 unmatched attempts or orphan results |
| Replay controls | **6 events**: open, pause, round, speed_16, play, close |
| Navigation | **17 view events** across lobby, dashboard, squad, development, market, strategy, game plan and replay |
| Entire browser stream | **115 events**, 109 for 26UHC and 6 lobby; 1 page session; 0 malformed lines |
| CSV annotation | **24/26 rows** have at least one matching decision or coarse browser event; 2 explicitly not instrumented |

Decision indices 0–6 match CSV steps 5, 8, 9, 11, 14, 22 and 24. The rejected
advance is browser request 19, event indices 19–20, and has no accepted decision
record. The successful advance is request 34 and decision 4. Mentorship pair
and clear are decisions 5–6 and requests 42/46. Thus the earlier web mentorship
gap is now verified in the played browser, and the previously unverified replay
and rejected-request hooks were exercised successfully on this build.

The first raw sidecar snapshot was taken **mid-session**, after the roster and
training decisions, before replay use. It is not a pre-play baseline. Its
[retained bytes](evidence/2026-10-08-replay-rejection/usage-mid-session-baseline.jsonl)
and [report](evidence/2026-10-08-replay-rejection/usage-mid-session-report.json)
contain 56 events and 7 paired requests; the final snapshot adds 59 events and
3 request pairs. The end stream belongs to this one page session/new world,
so its totals do not mix other careers.

Visible-time slices are browser visibility proxies, not player attention. The
bounded best-effort stream and delayed receipt times do not prove perfect
capture or exact session duration. The CSV's step 2 stale-reference click and
step 12 failed selector were automation recovery, not evidence of game failure.
The historical CSV prefix was preserved byte-for-byte when adding these rows;
there are now **322 unique session/step rows** before other agents' independent
acceptance sessions are incorporated.

## Flywheel

Before play, inherited the six recent `esports-playtest` entries, including the
native-confirmation block, mentorship telemetry evidence and override-report
gap. The Agora Python fallback worked. Post-play records and their IDs are
retained in [flywheel evidence](evidence/2026-10-08-replay-rejection/flywheel.json):
0026 and 0027 are learnings, 0028 is the release-cost pain-point. Confidence is
limited to this one played week. Source defects above are assigned for separate
reviewable PRs; this report describes the tested pre-fix build.

The three agents' independent acceptance sessions were subsequently appended
sequentially: release-cost confirmation (2 rows), development feedback (17 rows,
including retained harness failures), and lineup guidance (1 row). The shared
history now contains **342 unique rows**, preserving the earlier prefix. Those
sessions identify their dirty patched builds and exposed GPT-6.1-sol / medium
runtime separately from this clean pre-fix session.
