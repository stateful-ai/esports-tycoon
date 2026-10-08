# Two seasons on remote main — 2026-10-06

Completed two full seasons as Prairie Signal in a fresh legacy career, seed
2026, world **NEW26**. The calendar advanced **46 weeks**, from S1 W1 to
**S3 W1**. Prairie finished fifth both seasons: **5–9**, then **6–8**. Both
playoff goals were missed. Board patience ended at 8; the manager retained the
job. Froststorm won season-two MVP and Rookie of the Season; Slycore retired
at the second rollover. Final balance: 292,739 credits, five senior players.

The player question was whether a development-led manager could build a
competitive squad while exploring the campaign's coaching, roster, academy,
business and career mechanics. This is one exploratory career, not a balance
experiment or evidence that a particular preparation choice caused a win.

## Build and recording provenance

The initial browser session used `805712bcbf35196ca2c1107eb90dc475daa17c8e`.
Fetching remote main found one newer commit:
`0aabb0d4bfc1366192b23623925ef19ad5784b0d`, “Make player development respond
to practice and match performance (#341).” Both full seasons used that newer
build, project version **0.0.1**, in a clean managed worktree. The primary
checkout was subsequently fast-forwarded to the same commit, preserving local
work. A final fetch confirmed HEAD still equalled origin/main.

The worktree reused the primary Windows venv with `PYTHONPATH` pointing at the
worktree's `src`; the imported package path was verified. Gameplay used the
actual stdio play MCP and its manager-visible observations/legal contracts.
Social LLM was disabled. No engine tuning or gameplay-source changes were made.

Session `2026-10-06-two-seasons-main` contains **262 CSV observations** dated
2026-10-06 19:46:05–20:25:51 UTC. Together with the earlier 25 browser rows,
[actions.csv](actions.csv) now contains **287 observations**. Each row captures
intent and expectation before acting, the observed result, UTC timestamps,
commit, version, surface, seed/world and runtime metadata. Model is recorded
as `GPT-6 (exact runtime model ID unavailable)` and effort as
`unknown (not exposed in session)`; configured defaults were not substituted.

Important logging limits: most MCP rows were initially classified from request
success. `met` therefore often means immediate application/inspection succeeded,
not that the longer-term management objective was achieved. The later readbacks
below document the exceptions without rewriting earlier expectations. Early
multi-action batches sometimes retained their initial game-time label after a
tick. The audit reconstructs exact decision season/week from the preceding
public state and each tick's `played` field. UTC timestamps are unchanged.
The first request failed in the transport's timeout handling, was logged, and
was retried after correcting the driver. Skipped batch steps explain ID gaps.

Full responses, including text omitted from the compact CSV outcome field,
are preserved in [the step evidence](evidence/2026-10-06-two-seasons-steps.jsonl).
Rollover proof is at steps **177** and **267**; archived season reports are at
**178** and **268**. They are also bundled into the analytics evidence.

## Mechanics exercised

| Area | Actual player actions |
| --- | --- |
| Coaching | All five team training focuses; individual mechanical, tactical, team, mental, language and rest plans; light/normal/intense workloads; mentorship pairing, rejection and clearing; training delegation on/off |
| Match preparation | All four scrim objectives; light/normal prep; server-computed tactics fit; dial/site changes; all three team-talk approaches; opponent focus target; default, temporary and per-map lineups; agent lock set/clear; game-plan clearing; tournament registration |
| Roster and contracts | Negotiation open/counter/accept/cancel, free-agent signings, renewal, release, straight transfer bid, release-clause buyout, player-plus-cash package, atomic swap |
| Academy | Academy upgrade, affiliate inspection, promotion and send-down, temporary senior trials, appearance/development readbacks |
| Organisation | All six facilities upgraded to level one; coach/analyst/physio/language coach/psychologist hires; staff release; sponsor upfront/steady/performance structures; marketing-unlocked stream sponsorship; demand acceptance/decline; finances and projections |
| Relationships and career | Captain/council/principle, captain promise and later fulfilment, back/listen talks, four culture-session approaches, streaming restriction, media and flavor choices, board evaluations, awards, aging and retirement |
| Information | Scouting target and standing directives, market/transfer profiles, standings, schedule/results, analyst digest, inbox/read state, player/club/career/chronicle/season reports, save |

The league did not qualify us for playoffs, so controlled BO3 series directives
were unavailable. No incoming transfer offers were observed, so responding to
a buyer was not exercised. Fantasy draft, scenario starts, dismissal/job
acceptance, assignment/IGL editing and every tactical branch remain untested.
The latest-build browser check covered the lobby/join flow, not a second full
browser campaign; the earlier browser play and replay findings remain in
[the initial report](2026-10-06-preparation-gpt6.md).

## Findings worth carrying forward

1. **Successful generic actions can ignore unsupported parameters.** At steps
   32 and 60, `intensity: light` did not change individual workload: the public
   profile still showed normal. Using `training_intensity` at 71/72 and checking
   the profile at 76 confirmed the intended setting. The new skill requires
   readback before concluding an important setting applied.
2. **Simple signing and its telemetry can disagree on requested terms.** Steps
   64/65 supplied `weeks: 52`; the returned contracts were 40 weeks. The simple
   action uses the player ID and default domain terms, whereas its telemetry
   retains the extra requested `weeks: 52`. Negotiation applied explicit terms.
   This is an interface/schema limitation, and a reason to inspect outcomes
   rather than treat raw parameters as proof of persisted contract length.
3. **Academy placement did not deliver intended minutes.** Emberblade's
   send-down was accepted, but he still had zero appearances at the S2 W16
   checkpoint. Steps 249/251 record the delayed readback and partial outcome;
   251 is a retrospective check after 249 exposed the result, not an independent
   blind prediction. Placement and selection are separate outcomes. Zephyrsnap
   did accumulate affiliate appearances.
4. **Sponsor advisories repeatedly interrupt sim-ahead.** Occupied-slot offers
   regenerated with only decline available. Several requests stopped after zero
   or one week. Individual advance remained available once blocking events were
   resolved. This produced real repeated management friction.
5. **Inbox clearing has inconsistent count feedback.** A public inbox read
   showed unread items; mark-all-read then returned `marked_read: 0, unread: 0`
   (157/158; also seen earlier). Clearing apparently happened; the returned
   count did not describe it correctly.
6. **The browser did not expose a direct resume of the MCP-owned seat.** A fresh
   browser against the latest build loaded the Play lobby. Entering NEW26 in
   Join campaign exposed free legacy offers instead of Prairie Signal's occupied
   seat. No new team was claimed and no career action was submitted. This is a
   cross-surface discoverability/ownership limitation, not evidence of a damaged
   save. The final save remains at S3 W1.

Froststorm's improvement and stronger second-season record are observations,
not controlled estimates of the new development commit's effect. Fatigue and
offseason recovery were visible, and temporary match lineups expired as expected.

## Quantitative instrumentation audit

The isolated final save contains **191 decision records across 36 kinds** and
**46 weekly snapshots** for `mgr_team_prairie_signal`. Every expected campaign
record matched in order by kind, supported requested parameters, team, manager
seat, source (`agent`), and reconstructed season/week: **191/191**, with **zero
missing MCP decision records** in this session. This maps to **189 recorded CSV
rows** because one sim-ahead request produced three weekly advance records.
The other **73 rows** are outside this surface's decision capture: reads,
lifecycle/lobby navigation, inbox-read updates, rejected/transport-failed
attempts, or a zero-week sim-ahead request. None remain unverified.

The positive matches and canonical payloads are in
[the indexed analytics audit](evidence/2026-10-06-two-seasons-analytics.json).
Earlier-session CSV rows and all current-session timestamps, intentions,
actions, expectations and outcomes were preserved; only current-session
analytics annotations were updated. The prior session's CSV prefix was checked
byte-for-byte before writing.

| Recorded feature | Count |
| --- | ---: |
| Advance week | 46 |
| Flavor decisions | 28 |
| Individual development plans | 12 |
| Game plans | 10 |
| Team training changes | 8 |
| Sponsor responses | 7 |
| Facility upgrades / preparation / lineup-family actions | 6 each |
| Mentorship / academy moves / culture / staff hires / sponsor demands | 5 each |

`scripts/telemetry_report.py` was run against a directory containing **only**
this save. Its [unaltered usage output](evidence/2026-10-06-two-seasons-usage.txt)
correctly exposes broad action counts, but says **0/10 game plans** carried dial
overrides. Direct inspection finds **4/10** with non-None dial fields. The report
expects `n_dials`, which the MCP canonical payload does not include. Thus record
capture can pass while a downstream usage metric is wrong.

The earlier browser session recorded **6/7 successful gameplay decisions**;
its mentorship action persisted without an action record. On the latest commit,
`web/server.py:5452` still saves both mentor pairing and clearing without calling
`record_action`. The MCP mentorship path does record. This is a confirmed web
instrumentation gap; broad MCP capture does not establish web parity.

Existing telemetry supports quantitative **feature usage and weekly organisation
state**. It does not capture page views, replay usage, navigation paths, dwell
time, failed-attempt funnels, or wall-clock sessions. Those require a separate
UI/session event stream linked to this deterministic decision trace. The CSV
supplies qualitative intent and attempted actions; it is not a substitute for
production usage analytics. No analytics source changes were made during play.

## Validation and retained artifacts

- Latest-main campaign marker: **893 passed** (24:19).
- Logger tests: **3 passed**. Skill validation and `git diff --check` passed.
- No full-suite run or commit was made; no engine/data changes required balance,
  pacing, floor-audit or golden re-blessing.
- Final save: managed worktree
  `C:\Users\aidan\.codex\worktrees\two-season-playtest\ESports Simulator\saves\campaign_45a13c0d218e1007.json`;
  isolated audit copy under `runs/playtests/two-season/telemetry-only/`.
- Flywheel loop completed: two learnings and two pain points, entries
  `esports-playtest-0013` through `0016`, retained in
  [flywheel evidence](evidence/2026-10-06-two-seasons-flywheel.json).
- [AGENTS.md](../../AGENTS.md), [SKILLS.md](../../SKILLS.md) and the
  [playtest-log skill](../../.claude/skills/playtest-log/SKILL.md) now require this
  cumulative method for future gameplay testing.
