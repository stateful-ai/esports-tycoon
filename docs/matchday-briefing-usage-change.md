# Pre-match briefing usage candidate

The retained browser playtest opened the Dashboard's Match day briefing and
closed it with Continue. Its frozen sidecar contained 61 events: four HTTP
200 attempt/result pairs (flavor choice, game plan, advance, save), 12 views,
40 visible-time slices, and one session start, with zero interactions. These
counts establish a retained instrumentation gap; they do not establish
telemetry delivery loss or a complete session funnel.

The observed build was `754f525ce5f13636034a951a43e6da7346953df9`, containing
main `6fd38e1d8b413deeec2f3a078d3a80b71a5f0d71` plus PR #358. This candidate
starts from that main commit. The observed run is prior-build evidence, not
acceptance of this candidate. Runtime model and effort for that original run
were `unknown (not exposed)`; the repair request specified GPT-6.1 Sol medium.
Private paths, usage page/session identifiers, raw payloads, and save data
are deliberately excluded from this note.

Source inspection explains the gap: successful read-only `/api/matchday`
requests are suppressed by `Usage.result`, while `openMatchday` and
`closeMatchday` previously emitted no interaction. The overlay does not
change the underlying tab view. Source inspection also found every closing
path converges on `closeMatchday`: Continue, backdrop, Set/Review game plan,
and the no-fixture Close button. The current pre-advance route does not call
`openMatchday`; advancing alone is not briefing usage.

The candidate adds fixed `matchday/briefing_open` and
`matchday/briefing_close` interactions to both allowlists. Completed rendering
marks an inspection; refreshes and repeated closes do not double count.
Fetch failures, missing elements, and incomplete initial renders do not emit
false opening receipts. Existing UI navigation, game-plan persistence,
deterministic state, and sidecar linkage/retention remain as before.
No new cancellation hooks are added. PRs #419 and #420 concern Inbox usage,
so their instrumentation is not duplicated here; shared allowlist/test files
may require integration when those branches land.

Authored regression coverage exercises actual JavaScript handlers with the
real usage queue, every closing path, visible refreshes, failed reads,
missing elements, incomplete rendering, optional instrumentation, target
privacy, server acceptance/count semantics, and payload rejection. Existing
client/server allowlist parity coverage is extended for the two targets.

Validation status: **UNRUN**. The user explicitly requested skipping all
local tests, checks, validators, syntax checks, simulations, gates, report
commands, and hooks. No browser/game session was run for this candidate.
No shared playtest CSV/index was edited and no new-head gameplay acceptance
is claimed. Review and subsequent authorized validation remain outstanding.
