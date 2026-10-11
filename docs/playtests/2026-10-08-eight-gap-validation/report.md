# Combined eight-fix player acceptance

Tested a fresh fictional Sandbox Team Nexus career on seed2038, world26UHC,
Season1 Week1 through Week2. The deterministic world code matches an earlier
controlled run, but this server has a separate save and usage directory under
`runs/playtests/2026-10-08-eight-gap-validation`; no earlier career was reused.
Browser: standalone Playwright MCP on isolated loopback8458. Game version0.0.1,
checkout commit3ac34df3a476543d9e79dc4dc03bb381c04e397d with dirty integrated source
tree833ae36edda98357c6f88b012a6fdfbba94104e0. Root runtime model and effort are
`unknown (not exposed)`; dispatched child settings are not proof of root runtime.
The worktree imports its own source through the primary Windows venv/PYTHONPATH.

Question: do the eight reviewed fixes work together, including report ownership
after a real post-match roster change? Intent and expectation were written before
each attempt using `scripts/playtest_log.py` with a separate session LOG_DIR.
Nineteen finalized observations remain: seventeen met, one partial, one unexpected.
Only factual world metadata and current-session analytics annotations were added
afterward. Original actions, expectations, outcomes, and timestamps are retained.

## Observed outcomes

The public creation request carried seed2038 and Team Nexus, and the new campaign
started at487320 credits. Phantom's native confirmation quoted78000 severance;
release charged exactly that amount, leaving409320 credits and four players.
Advance returned a real409 with actionable guidance: Market -> Players, sign one
more free agent, then try Advance Week again. Week and balance were unchanged.

Market search for Slyblade returned three different people with that handle.
Andre Costa was the free agent, age28, approximately72 OVR and5700 asking salary.
Negotiation quoted6300/week,62weeks,71% streaming share,76000 release fee,180000
buyout, no-transfer clause and starter role. The unchanged offer was accepted;
public roster readback verified five players, salary6300,62weeks and release76000.
The saved accepted decision independently verifies every remaining contract term.
The search produced one dedicated coarse receipt without transmitting its query.

Vortex began at condition32. Choosing Rest/normal immediately removed the exhausted
warning and showed Recovery and server-authored rest advice. The original focus
node remained connected and enabled, and public readback verified the selection.
Match Game plan showed the known Lotus fixture and corrected guidance to use known
fixture maps; agent locks explicitly stay in place until changed. No lineup or
tactical plan was changed during this session.

Advance reached Week2 at427505 credits, resolving Lotus13-2 against Sahara Compass.
The real Full report button opened a readable five-player development section.
Vortex retained Rest/normal, one map, Matches+0.02 OVR, practice-paused/match-learning
explanation and displayed74.5 ->74.5. Slyblade's missing adjacent history was
honestly labeled "Weekly OVR comparison unavailable" while small source gains
remained visible. Screenshot `evidence/development.png` was visually inspected.
This short run does not establish balance or that Rest caused the victory.

After the match, a real Echo release quoted66000 and left the current roster at
four players and361505 credits. A new `/api/report` read was exactly equal to the
prior development snapshot, including Echo among the five resolved participants.
Public before/after payloads are preserved in `evidence/public-report-usage.json`.
The copied report stays separate from the mutable current roster and save schema.

Replay access required recovery from Match to Season -> Fixtures -> Played weeks.
The historical Lotus replay retained both released Echo and Grimveil/Jett11K12D.
The current Sahara roster instead contains Frostecho, as corroborated by the
visible transaction news and public roster. Pause changed the control to Play,
and participant panels and named combat feed stayed correct. The replay screenshot
was visually inspected. A final pending Market query followed immediately by
Dashboard navigation initiated zero search requests over a600ms request observer;
the retained player-search receipt count stayed one.

## New defect retained

Club correctly says4/10 and need five players/sign one more. The refreshed
Dashboard Staff briefing nevertheless says "Squad ready", marks Assistant Coach
"Stable", and recommends keeping the match five settled. Reopening Club and
Dashboard reproduces the contradiction. CSV row15 remains unexpected, supported
by `evidence/dashboard-short-roster.png` and current roster readback. A dedicated
GPT-6.1-sol/medium `dashboard_roster_readiness` agent owns its isolated fix and PR.

## Separate quantitative evidence

Save returned200. The one saved test world contains six accepted decisions, all
matched by exact kind, params, team, manager, source, season/week and order:

- CSV5 -> action_log[0]: release Phantom, S1W1.
- CSV8 -> action_log[1]: open negotiation forfa_13, S1W1.
- CSV9 -> action_log[2]: accepted full Slyblade contract, S1W1.
- CSV10 -> action_log[3]: Vortex Rest/normal/empty learning_language, S1W1.
- CSV12 -> action_log[4]: advance, S1W1.
- CSV13 -> action_log[5]: release Echo, S1W2.

One post-tick manager snapshot is saved. Navigation, control use, rejected
Advance, replay and Save are outside the accepted deterministic decision ledger.
The isolated `decision-report.txt` consumes only this session save; detailed
matches and save SHA256 are in `decision-indexed.json`.

The played browser page retained110 usage records and nine complete request pairs:
creation1, releases2, rejected Advance1, negotiation2, development plan1,
successful Advance1 and Save1. One pair is an actual409; the other eight succeeded.
There are zero unmatched attempts and orphan results. Dedicated interactions are
one each for seed change, player search and explicit Full report. Replay has one
open, pause and close receipt. Interactions contain only the existing coarse
envelope, kind and closed target; no query, name or raw control value is emitted.

The test server was launched with the CLI's default auto-browser behavior, which
also opened an unused lobby page. The audit excludes its45 lobby-only records and
uses the single page session carrying this test world's events, including its
pre-creation lobby records. Aggregate all-page output is preserved separately.
Future isolated CLI launches must use `--no-browser`. No complete funnel, exact
session duration, attention measure, or rejected deterministic decision is inferred
from bounded best-effort receipts. A recorded navigation does not encode the
readiness contradiction; DOM and public state supply that evidence.

## Driver recovery and validation

A guessed `#lobby` snapshot selector matched no element and was recovered by a
full snapshot. A stale Advance reference after a partial snapshot made no request;
fresh header references recovered it before the real409. A five-second wait for
Full report expired while the live campaign processing screen was still resolving;
the same request completed normally without another Advance action. CSV14 retains
the unsuccessful attempt to find the replay in Match, followed by successful
Season fixture recovery in CSV16. These observations do not fabricate API failures
or substitute successful later actions for earlier friction.

Before play, the latest eight esports-playtest flywheel entries were inherited.
After reconciliation, two learnings and one pain-point were recorded as0056-0058;
pre/post evidence is retained. Original350 canonical CSV rows remain untouched;
this session is staged separately for sequential append-only integration.

The fifteen changed source/test blobs were checked against the frozen combined
tree before the full unfiltered `pytest -q -n2` run started at18:04:47UTC. The
durable gate's running.json/result.json and raw file hashes establish the actual
source and completion. Full gate remains pending; syntax and browser acceptance
are not substitutes for it. Neither this report nor source tests claim final-main
CI success or that all eight PRs have merged.


## Completed combined-eight full gate

The frozen fifteen-path integrated source completed the full unfiltered `pytest -q -n2` run: **1225 passed in 6240.22s (1:44:00)**, exit0. Started 2026-10-08T18:04:47.872264+00:00; finished 2026-10-08T19:48:48.675153+00:00. The result confirms source_unchanged=true, and every raw file hash still matches the pre-run manifest. Startup, complete stdout and result are copied under evidence/full-gate. The pending wording above preserves the earlier state. This validates the reviewed eight-source combination, not later dashboard/current-roster fixes or final actual-main CI. The nineteen player observations and their annotations are unchanged.

Artifact verification correction: the first preservation helper compared raw Windows hashes to Git-filtered blob hashes and exited1 before writing. The corrected helper verifies each representation separately; the actual pytest gate was already exit0/source_unchanged=true. The failed assumption is retained in evidence/full-gate/verification-correction.txt and the separate 2026-10-08-eight-gate-verification observation. No source or test was changed.
