# Preparation condition formatting acceptance

Base: `042d86d3161fc5fa3185091031ba546193b2e97e`. Model: gpt-6.1-sol, medium.
Isolated worktree and server 8477. Copied natural Team Nexus world 26UHC, seed 2038, S1 W8. Source fixture stayed unchanged.

The Match > Prep condition row now reads Apex 76.0, Echo 55.0, Hollowlock 55.9, Slyblade 74.9, Ghost 59.0, Vortex 100.0. [Ordinary-server browser screenshot](evidence/ordinary-server-prep.png) and [visible text](evidence/ordinary-server-prep.txt) verify it. Public club data still contains Hollowlock condition `55.900000000000006`. Light condition cost remains 1.5; coach Normal proposal cost remains 4. Existing labels, controls, and explanatory text remain available.

Only participant-number presentation changes. The source stamina, simulation, preparation costs, and saved players remain identical. Node consumer coverage executes the real row and checks float noise, integers, 0/100, rounding, escaped handles, and unchanged input values. `node --check` passed.

## Session and audit

Four timestamped intent rows are preserved in this session's separate [actions.csv](actions.csv); canonical actions.csv was untouched. Step 1 was blocked at the lobby due to an IAB cookie mismatch. Steps 2/3 were preliminary IAB observations with an isolated transport session alias; those are superseded by step 4 on the ordinary server with a legitimate copied solo SID cookie in standalone Playwright. No transport middleware was published. Step 4 also corrects step 3's premature raw-value audit claim: the first audit failed Windows default UTF-8 decoding, and the subsequent explicit UTF-8 audit passed.

[Saved ledger audit](evidence/audit.json): 40 baseline and 40 final accepted decisions, byte-equivalent action_log, zero new gameplay decisions, one telemetry snapshot before/after, unchanged players, unchanged original/copied fixture hashes. Four of four CSV rows are outside gameplay decision instrumentation (navigation/Save), so there are zero eligible new gameplay decisions and no missing accepted decisions. [Ledger](evidence/decision-ledger.json) and [feature report](evidence/campaign-feature-report.txt) retain the baseline evidence.

Browser usage is separate: 33 retained events across four distinct page-session IDs, with three session-start records, including 9 views, 16 visible-time records, and two Save attempt/result pairs (both request12 within distinct page sessions, success/status200). Both preliminary and ordinary browser Saves have retained usage coverage (2/2). [Per-session audit](evidence/usage-session-audit.json) identifies actual views. Initial lobby navigation emitted usage but no game decision; no HTTP rejection is claimed. Two residual visible-time/session-end records refer to a previous IAB page-session ID inherited through shared browser local storage; no current-run navigation or action coverage is inferred from them. Browser usage is bounded best-effort and visible-time is not attention. Bootstrap/public readbacks do not substitute for browser usage.

Pre-play eight flywheel entries were read; two learnings and one pain-point were recorded afterward, with IDs retained in [flywheel records](evidence/flywheel-records.json).

## Release validation

Full unfiltered `python -m pytest -q`: **1253 passed in 2806.78s**, native exit 0. Detached runner used its own cwd/PYTHONPATH and verified the worktree import. The runner confirmed unchanged source/test/data hashes, and publication rechecked all 545 raw SHA-256 hashes against the freeze. [Native result](evidence/gate-result.json), [terminal output](evidence/pytest.stdout.txt), and [publication verification](evidence/publication-verification.json) retain exact evidence. Engine/balance/pacing gates are not triggered by this presentation-only change.
