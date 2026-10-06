---
name: playtest-log
description: Play the esports simulator as a player, append timestamped intention/action/expectation/outcome CSV observations, and reconcile the session with decision and browser usage telemetry. Use for exploratory playtests and gameplay or UI acceptance testing.
---

# Persistent player-intent playtests

Read `CLAUDE.md` first. Use this method for game playtests; automated unit/gate
runs alone do not constitute playing. The shared history is
`docs/playtests/actions.csv` (tracked, append-only). Session reports live beside
it; large screenshots and disposable saves can live under `runs/playtests/`.

Before play, inherit the `esports-playtest` flywheel findings as described in
`CLAUDE.md`. Prefer the play MCP for campaign play; use the browser for UI
discoverability, visual feedback, or when MCP is unavailable. State the surface
actually used. Create a separate test world unless continuing an identified
test save; do not alter an unrelated existing career. Pick moves from visible
screens/manager observations and legal actions, never hidden state.

Identify the build before play. If the user asks for latest remote main, fetch
and compare HEAD with `origin/main`; preserve local changes and use a clean
checkout if needed. In a worktree without a venv, reuse `.venv-win` with
`PYTHONPATH` pointing to that worktree's `src`, and verify the imported package
path. Capture the tested checkout's commit, not the transport script's checkout.
For a multi-season session, start a fresh world on that build, record rollover
proof and each completed season report, and keep the same test save throughout.

Choose a short player question for the session. Log meaningful navigation,
searches, decisions, rejected attempts, and recovery actions, not merely
successful mutations. Group clicks only when they implement one player intent.
Do not rewrite an expectation after discovering the result.

Read back important settings after mutation. A successful tool response alone
does not prove that every requested parameter was applied. Use the interface's
actual parameter names; inspect public observations to verify persisted values.
Classify outcomes semantically, including no-ops, partial changes, rejected
attempts, and sim-ahead stops. If a later check contradicts an earlier judgment,
append a correction observation and identify it in the report; preserve history.

Use `.venv-win\Scripts\python.exe scripts/playtest_log.py` from the repo root:

```powershell
& '.venv-win\Scripts\python.exe' scripts/playtest_log.py begin --session 'YYYY-MM-DD-topic-unique-id' --step 1 --model 'runtime model ID' --effort 'runtime effort' --surface browser --seed 2026 --world-code ABCDE --game-time 'S1 W1' --intent 'Understand the next fixture' --action 'Open Match' --expected-outcome 'Opponent and preparation controls are visible'
# Perform the action and inspect its result before finishing the row.
& '.venv-win\Scripts\python.exe' scripts/playtest_log.py finish --session 'YYYY-MM-DD-topic-unique-id' --step 1 --actual-outcome 'Describe observed result' --result met --evidence 'session report or screenshot path'
```

`begin` captures UTC start time, HEAD commit, dirty-tree flag and project version
and writes a pending intention under `runs/`. `finish` captures UTC finish time
and appends a CSV row, checking schema and duplicate session/step IDs. Results:
`met`, `partial`, `unexpected`, `blocked`. Complete pending rows even when an
action fails; explain interruptions. Do not backdate or invent boot timestamps.
Supply the actual model and effort from trusted runtime metadata. If unavailable,
write `unknown (not exposed)`; a configured default is not proof of the active
runtime. Record seed, world code, game time, and surface; add the newly assigned
world code at finish or backfill only that factual metadata after creation.
Wall-clock metadata belongs in this sidecar, never deterministic GameState.

At session end, save through the played surface. Inspect only the test world's
persisted `action_log` and `telemetry_snaps` after decisions are complete. Export
the action records with their list indices and compare each decision's kind,
params, team, source, season/week and order. Mark every CSV row with
`analytics_status` (`recorded`, `not_instrumented`, `missing`, `unverified`) and
`analytics_evidence`. Read-only navigation, failed requests, and viewing a
replay may be outside the decision vocabulary; do not infer their capture from
an HTTP access log or a successful UI toast. Preserve evidence supporting both
positive matches and gaps. Use `scripts/telemetry_report.py` on a directory
containing just the session save so other careers do not contaminate counts.

For browser play on a build with UI usage telemetry, also inspect the retained
`saves/usage/usage.*.jsonl` sidecar and run
`scripts/ui_usage_report.py saves/usage` (or the loopback-only
`/api/usage/report`). Preserve a baseline and an end snapshot, and isolate this
test world's events and page sessions; aggregate totals may include other
careers. Reconcile coarse request targets and request IDs for attempts/results,
navigation, replay events, and visible-time slices. Keep decision coverage and
usage coverage separate in the report and name the supporting stream in each
CSV annotation. A successful API result still requires important-setting
readback. MCP and direct HTTP recovery do not emit browser usage events.

Do not equate a blocked browser click or cancelled confirmation with a recorded
HTTP rejection. If no request was observed, retain the blocked intent in the
CSV and mark capture unverified. Visible-page time is a visibility proxy, not
attention or intent duration. The bounded, best-effort sidecar can drop events
or rotate old segments, so retained counts, unmatched attempts, and session
receipt spans do not prove complete funnels or exact session duration. If the
tested build lacks these hooks, report that gap rather than borrowing evidence
from a different build. Save UTF-8 audit output and append a correction when a
fresh audit fails; never substitute an earlier successful read without saying so.

Summarize observed outcomes, friction, exact decision coverage and instrumentation
gaps in a session Markdown report. Distinguish feature-usage counts from funnels,
time spent, failures, or causal effects. A short run cannot establish balance or
prove a preparation action caused a win. Finish the flywheel loop with two
learnings and one pain-point, using honest confidence and world/seed evidence;
if unavailable, retain findings locally and document the limitation.

Never truncate or regenerate past CSV rows. For concurrent runs, stage separate
per-session CSVs with this schema and merge sequentially using unique session/
step IDs; the helper assumes a single writer. Schema changes need an explicit
migration. Update factual analytics annotations only for the current session,
without changing its recorded timestamps, expectations, actions, or outcomes.
