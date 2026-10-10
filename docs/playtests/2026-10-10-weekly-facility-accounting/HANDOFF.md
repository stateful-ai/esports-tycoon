# Gap 25 durable gate handoff

Worktree: `C:/Users/aidan/.codex/worktrees/weekly-facility-expense-reporting`
Branch: `fix/weekly-facility-expense-reporting`
Base: `042d86d3161fc5fa3185091031ba546193b2e97e`
Source and tests frozen since **2026-10-10 19:37:40 UTC**.
Full gate completed at **2026-10-10 21:41:54 UTC**: **1,257 passed in 7,451.32s**,
actual native pytest exit **0**, all **610** raw paths equal. Production source
and tests remain exactly as tested. Publication follows root's authorized
resumption; do not rebase or edit tested source under this proof.

## Completed detached full gate

- Actual native writer PID **11276** (venv launcher PID 37452).
- Actual pytest subprocess PID **3496**; two xdist workers.
- Command: primary `.venv-win/Scripts/python.exe -m pytest -q -n2`, unfiltered.
- Imported package is the worktree's `src/esports_sim/__init__.py`.
- Durable writer implementation: `runs/gap25/full_gate.py`.
- Terminal log: `runs/gap25/full-gate/pytest.log`.
- Status and native subprocess exit proof: `runs/gap25/full-gate/status.json`.
- Raw 610-file SHA-256 manifests: `source-pre.json`, then `source-post.json` in
  that directory. Status writes `source_freeze_equal` and changed files.
- Writer stdout/stderr: `runs/gap25/writer.out.log`, `writer.err.log`.

Read status first on resumption. If still running, follow this same writer;
never restart a healthy process because a tool yielded. Source equality and
actual **native pytest exit 0** are both required before any commit. The writer
does not commit or publish automatically.

The terminal receipt, full log and raw pre/post manifests are now retained in
this session's `gate/` directory. The original running-state instructions below
preserve how this process was followed without interruption or restart.

## Already complete

Five new targeted accounting tests passed in 104.22 seconds. The previous
31-case run had 30 passes and one corrected synthetic fixture setup failure.
Node syntax and Git whitespace checks passed. Complete actual baseline-source
GameState JSON and event logs equal the changed implementation for the observed
1,500-upkeep fixture; old report 109,232 / 47,100 becomes 110,732 / 48,600,
same bank 333,406 -> 395,538 and net 62,132.

Normal browser acceptance and Save complete. Own browser session `gap25` and
server port8487 (PIDs33540/4784) closed. Parent server and full gate untouched.
Original fixture remains immutable. Session CSV is a separate shard; four
accepted decisions and five browser request/result pairs reconcile exactly.

Scoped production files: `manager/sponsors.py`, `manager/campaign.py`,
`web/server.py`, `web/static/app.js`. New tests:
`tests/test_weekly_facility_accounting.py`. Evidence: only this session folder.

Root independently preliminarily reviewed the four production diffs and test
without findings. Root will independently review the published exact head,
then merge. **Do not merge this agent's own PR.** Main progressed while the gate
ran; preserve the tested branch's baseline and let root manage integration.

## After genuine green

1. Check `status.json` is complete, exit0, freeze true; preserve terminal log,
   raw manifests, imported path, summary/count and exact source proof in this
   session's `gate/` evidence directory. Update `report.md` pending-gate text.
2. Independently check Git diff/status for unexpected files. Stage only the
   four production files, new test and this evidence folder. Do not stage the
   shared `docs/playtests/actions.csv`, `saves`, `.playwright-cli`, or `runs`.
3. Commit, record exact head, push branch, create a non-draft PR to main using
   the body file (prepared at `runs/gap25/pr-body.md`; replace validation
   placeholder with actual terminal proof). Use CLI `gh` if app tools hang.
4. Report PR link, exact head, gate proof and current CI to root; no merge.

No engine, tuning, map, schema, gameplay costs or financial balance changes;
the full unfiltered suite includes campaign/web/golden domains. Separate
balance/pacing/floor gates are not triggered by this reporting-only scope.
