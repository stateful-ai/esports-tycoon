# Completed full gate: gap22 publication handoff

Own worktree:
`C:\Users\aidan\.codex\worktrees\play-time-promise-clarity\ESports Simulator`
Branch: `fix/play-time-promise-clarity`.
Tested base: `042d86d3161fc5fa3185091031ba546193b2e97e`.
Do not merge; root independently reviews the eventual PR.

Implementation, focused tests and separate copied-W9 browser acceptance are
complete. No source/test/data files changed after the full gate began.
The full unfiltered gate was genuinely detached with a native Python runner,
then a subprocess running `.venv-win\Scripts\python.exe -m pytest -q`.
It started `2026-10-10T19:03:17.119129+00:00`:

- Wrapper launcher PID28192; native runner PID38144; pytest PID35736.
- Python: primary `.venv-win\Scripts\python.exe` with PYTHONPATH pointing
  to this worktree's src; imported-package path is recorded in running JSON.
- Directory: `runs/playtests/2026-10-10-play-time-promise-clarity/`.
- Proof: `gate-running.json`, `gate-freeze.json`, `pytest.stdout`,
  `pytest.stderr`; completion writer produces `gate-result.json` only after
  the actual subprocess exits, including exit code and source_unchanged.
- Freeze covers 545 source/test/data/config files. Independent end-of-play
  hash comparison matched all 545 files. The suite completed at `2026-10-10T19:44:28.828736+00:00`: native
  exit0, source_unchanged=true, **1269 passed in 2470.53s**. Independent
  post-exit verification matched all 545 hashes; receipt is gate-proof.json.
  Do not restart the unchanged green gate.

`gate-result.json` reports exit_code0 and source_unchanged=true. Never
borrow proof from another PR or confuse this runner with port8483's family.

Source scope:

- manager/promises.py extracts the existing duration reconstruction,
  required dressed-week threshold and result rule into pure helpers. Both
  weekly_tick and public assessment share them. No RNG/schema/state fields.
- web/server.py routes roster/player promise serialization through the
  assessment; the bench-promise response names exact target/window/deadline.
- web/static/app.js and profile.js consume those labels and server progress;
  they contain no promise threshold/window formulas. Other promise types and
  kept/broken history keep their existing behavior.
- tests/test_play_time_assessment.py adds 17 cases for actual next-tick
  outcomes, legacy targets/windows, bye/one-credit counting, read purity,
  preserved history/unknown types and shared public serializer output.

Completed checks: 17 new focused tests, existing focused Locker Room/API
tests, Node syntax, 80 byte-identical full-GameState old-evaluator comparisons,
both actual DOM renders, and real W9->W10 deadline resolution with Echo zero
maps/kept/five credits. No sim/constants/maps or tuning changes; separate
balance/pacing/snowball gates have no trigger. The full suite includes golden.

Evidence under this directory is ready for a scoped commit: seven-row session
CSV shard, REPORT.md, reconciliation.json, evaluator-equivalence.json,
browser-assertions.json and inspected profile screenshot. Canonical action
CSV in this worktree is byte-identical to HEAD. Root merges shards later;
do not modify the primary CSV. `.playwright-cli/` is disposable/untracked
and must not be staged. Large runs and copied saves are ignored.

Browser `promise-gap22` is closed. Own8483 server family
38084(parent)/38156(listener)/28712(conhost) was verified and stopped;
family evidence is in server-family.json. Initial family6240/2044/17152 was
also verified/stopped during copied-session recovery. Do not stop unrelated
server, browser or test processes.

Authorized publication steps after verified gate success:

1. Recheck source hashes against gate-freeze.json and record terminal proof
   in REPORT.md. Copy a sanitized gate result/summary into this report folder.
2. `git diff --check` (source and session shard should be clean); inspect diff.
3. Scoped commit only four implementation files, the new test and this session
   report directory. Use `Co-authored-by: Codex <noreply@openai.com>`.
4. Push branch; create PR via `gh pr create --body-file <exact-text-file>`.
   Suggested title: "Clarify play-time promise progress and deadlines".
5. Attach PR to root with exact head SHA, terminal exit/test counts,
   source-freeze proof, browser/CSV/audit coverage and limitations. Do not
   merge. CI pending must be stated honestly.

Limitations: flywheel tools unavailable (local findings in REPORT.md);
profile-open lacks distinct usage-view events; retained usage is bounded.
The shared bench acceptance toast is now explicit, but the Inbox action
button still uses its existing "Promise minutes" caption before selection.
No future action availability is promised: next-evaluation scenarios are
conditional on actual dressed participation, not predicted fixtures.
