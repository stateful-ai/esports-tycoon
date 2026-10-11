# Bounded control interaction acceptance

Tested 2026-10-08 on `3ac34df3a476543d9e79dc4dc03bb381c04e397d` with the
usage-control-hooks source changes present (dirty tree), game version captured
in [actions.csv](actions.csv), runtime gpt-6.1-sol / medium. Browser surface:
standalone Playwright Chromium, isolated loopback server port8453 with CWD
`runs/playtests/usage-control-hooks`. Imported package path was verified as
this detached worktree's `src/esports_sim`. No existing career was played.

The player question was whether a manual lobby seed change and explicit
weekly Full report opening leave retained, privacy-safe usage evidence.
Seed2040 produced world M74LG, Baltic Meridian, played S1W1 to S1W2.
The Seed field read2040 after blur; the actual weekly reveal's Full report
button opened the classic results overlay with fixture results. Save returned
HTTP200 and the persisted world reads seed2040 / S1W2.

The additive `interaction` kind uses only `lobby/seed_change` and
`week/full_report_open`. Client and server reject arbitrary targets; the server
also rejects seed/label fields and request, outcome, status, or duration fields
on interactions. The seed hook runs on the user's committed change event, not
the lobby's programmatic random default or every keystroke. The report hook runs
after the explicit button opens the report, not automatic reveal or Continue.
No entered values, report content, URLs, labels, selectors, or settings are sent
by these hooks. Existing batch, queue, body-size, timeout, and four-segment
rotation bounds remain in effect. Schema1 is extended with a new event kind;
existing generic report aggregation already counts it without a new report key.

## Separate evidence streams

- **Player observations:** nine pre-action CSV intentions and nine finalized
  outcomes. Seven rows have positive retained evidence; two blocked clicks have
  unverified capture. The interrupted creation inspection remains `partial`.
- **Deterministic decisions:** [decision-indexed.json](evidence/decision-indexed.json)
  has one action, index0: `advance`, `{}`, team_baltic_meridian,
  mgr_team_baltic_meridian, source `web`, S1W1 regular. It matches row6, the only
  accepted manager decision in this session: **1/1**. One post-tick snapshot is
  retained. Lobby setup, read-only report use, and explicit save do not belong
  to this manager decision vocabulary. The isolated
  [decision report](evidence/decision-report.txt) was run against only this save.
- **Bounded browser usage:** [baseline](evidence/usage-before.json) and
  [end report](evidence/usage-end.json) isolate this server's fresh sidecar.
  [Indexed stream](evidence/usage-indexed.json) retains36 events across four
  hashed page sessions:29 worldM74LG events and7 lobby events. The lobby seed
  event stays in the original pre-world session; the world creation attempt and
  result share that page session and request5 while world linkage transitions
  from null to M74LG. Advance request10 belongs to session
  `3ea72b52d9829f72133f014b47c324a0`, with attempt S1W1 / result S1W2;
  explicit Full report has the same session and worldM74LG. Save has its own
  recovered page session/request pair. **3/3** attempts pair with successful
  results; zero unmatched attempts, orphan results, or malformed lines.
  Both targeted controls have **1/1** retained interaction events. The generic
  `scripts/ui_usage_report.py` CLI produced the saved end report.

The raw client page IDs differ from server stored session IDs, which are hashes
of the actual session cookie plus page ID. Cookies are not published. The
[successful save batches](evidence/batches-saved.json) retain that page's client
ID; earlier driver's in-memory batches were lost on its timeout, so their
linkage is supported by retained hashed page sessions and request IDs rather
than claiming the raw page IDs were exported.

## Friction and recovery

Row3 created the world, but the driver incorrectly waited for `#newgame.hidden`
to be visible. Playwright's timeout explicitly resolved a hidden lobby. The
interrupted inspection was retained and row4 resumed the same world. Row5's
Advance click was intercepted by the automatic first-run Guide and emitted no
request. Row6 dismissed Guide with Escape and advanced successfully. After
Full report, row8 assumed Escape would close results; it remained open and
intercepted Save. Row9 reopened the same world, dismissed Guide with its visible
Close control, and saved successfully. Those two blocked clicks are not HTTP
rejections and have no fabricated request events. The core control hooks were
proven by actual UI use rather than direct event submission.

Retained interaction/open counts describe control use. They do not establish
successful campaign creation, accepted manager decisions, attention, time spent
reading, or complete funnels. Visible milliseconds are a visibility proxy;
best-effort retention can drop or rotate events. A short one-week run does not
establish balance or development causality.

Flywheel pre-read used the direct Agora fallback;
[inherited entries](evidence/flywheel-before.json) were read before play.
[Post-play entries](evidence/flywheel-after.json) contain two learnings and one
pain-point, IDs esports-playtest-0038 through0040.

Focused regression:28 telemetry tests passed, including browser JavaScript
contract checks, allowed counts and rejected interaction shapes. Node syntax
checks passed for app.js and usage.js. Browser target controls and saved-setting
readbacks passed. Full unfiltered `pytest -q -n2` passed **1190 tests** in
4918.78 seconds, exit0, started2026-10-08T17:07:58.228691UTC and
finished2026-10-08T18:29:57.810554UTC. The source/test diff is byte-identical
to the parent's frozen reviewed patch, SHA256
`2de7af6a32b1b61c6481038543515237ae6723d81cede09eff536d79425a6133`;
no source or test changes followed gate startup. The
[freeze manifest](evidence/source-freeze.json),
[completion result](evidence/full-gate-result.json), and
[full stdout](evidence/full-gate-pytest.log) preserve that evidence.
The live helper paths remain under `runs/playtests/usage-control-hooks/full-gate`.
Engine, tuning, map geometry,
campaign economy, and development source are unchanged, so balance, pacing,
floor, and snowball triggers do not apply.
