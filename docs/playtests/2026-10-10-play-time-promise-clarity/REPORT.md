# Play-time promise clarity: gap22

Tested base `042d86d3161fc5fa3185091031ba546193b2e97e` plus the tested
gap22 changes in an isolated worktree. Browser session `promise-gap22` used
port 8483 and a copy of the immutable W9 media/sponsor save: world `26UHC`,
seed 2038, Team Nexus. Agent configuration was GPT-6.1-sol / medium. The
primary career, primary browser and canonical action CSV were not edited.

The player question was: "What does Echo's target of 60 mean, and does his
next dressed appearance determine whether this promise is kept?"

The old display said `Target: 60 · Dressed 5 weeks`, `1 weeks left`, with a
13% time-remaining bar labeled Progress. Both Locker Room and Echo profile
now display the same server-authored assessment:

- Target: 60% of 8 window weeks, rounded up = 5 dressed weeks.
- Progress: 5/8 window weeks dressed (62.5%). 0 more needed to reach 5.
- Deadline: at the next weekly evaluation.
- Next evaluation: dressed gives 6/5 required weeks and keeps the promise;
  not dressed leaves 5/5 and also keeps it.
- At most one credit per evaluation, earned by dressing for at least one
  played map. Weeks without a played map still use time.

The filled bar measures progress toward the five-credit requirement. It is
distinct from the full-window fraction printed above it. The actual DOM
render assertions for both displays are in [browser-assertions.json](browser-assertions.json).
The profile screenshot was inspected visually: [echo-promise-w9.png](echo-promise-w9.png).

Seven attempts were prelogged in [actions.csv](actions.csv). Two were blocked:
the copied solo world rejected a Join attempt, and Advance required resolving
the pending interview first. The first attempt includes an erroneous click
on another team; it was rejected without joining or changing the world. The
solo-seat recovery used copied session metadata on the separate server.

After choosing the visible team-first interview response, the unchanged
default five advanced W9 to W10. The full report showed Echo **0 maps** and
Hollowlock **1 map**; Nexus won 13-3 against Nordic Frost. Public readback
showed Echo's promise kept with **five**, not six, dressed credits, and no
active promise in his profile. Locker Room retained his kept history. Apex
now showed 6/8 (75%) with the next-evaluation deadline; Vortex showed 4/8
(50%), one more credit needed, four evaluations remaining. No match result
or player-development causal claim is drawn from this short session.

Save was clicked through the browser. Public state was W10 / dirty=false.
Persisted accepted decisions increased 43 to 45 with the original 43 intact:
index43 `flavor_choice` (event `72b29241b2f60658`, `team_first`), then index44
`advance`. Both are Team Nexus / web / S1 W9 and match the CSV order and
parameters: **2/2 accepted decisions, 100% coverage**. The manager's weekly
snapshot list increased 8 to 9.

Retained browser usage had 78 events and **5/5 paired attempts/results**:
Join409, Advance409, flavor-choice200, Advance200 and Save200. The Join pair
belongs to the initial lobby page session with no world binding; the other
four pairs belong to the recovered `26UHC` page session. Failed requests are
not accepted campaign decisions. Navigation and Save are outside that
decision vocabulary. No distinct profile-open view event was retained;
profile acceptance is proved by DOM and public API readback. Visible-time
slices and the bounded best-effort stream do not establish exact attention,
duration or complete funnels. See [reconciliation.json](reconciliation.json).

The source W9 save still matched its copied SHA256 after the session.
Only the verified own server family was stopped and the own browser session
was closed. The independent full-suite process later completed successfully.

Validation completed: 17 new focused tests passed; the existing focused
Locker Room/API tests passed in the first combined run (the new public-view
purity test was corrected to warm existing lazy scouting maps, then all 17
new tests passed). Node syntax checks passed for app.js and profile.js.
Eighty full-GameState comparisons against the old promise evaluator at
042d86d were byte-identical, including legacy targets and window inference:
[evaluator-equivalence.json](evaluator-equivalence.json). Real DOM assertions
passed for both promise renders and the W10 resolution. The full unfiltered
pytest gate passed: **1269 passed in 2470.53s**, native exit0 at
`2026-10-10T19:44:28.828736+00:00`, source_unchanged=true. Independent
post-exit verification matched all 545 frozen source/test/data/config files.
No source changed or rebase occurred under that proof. See [gate-proof.json](gate-proof.json).

Flywheel tools were not exposed. Local findings retained here:

- High confidence: the target refers to the original window, and reaching
  the required dressed-week threshold can precede the resolution deadline.
  Evidence: Echo W9 5/8; W10 zero maps, kept with five credits.
- High confidence: showing actual full-window progress separately from
  requirement progress explains why a bar can be full before the deadline.
  Evidence: both actual W9 DOM renders show 62.5% and a full requirement bar.
- Pain point: copied solo saves need corresponding session metadata to
  resume their occupied seat; Join produces a rejection. Profile opening
  also lacks a distinct retained usage-view event on this build.

Large local evidence lives under
`runs/playtests/2026-10-10-play-time-promise-clarity/`: W9/W10 public readbacks,
Locker Room snapshots/DOM, Echo profile, full report, audit-only save,
decision and usage reports, source freeze and detached gate logs.
