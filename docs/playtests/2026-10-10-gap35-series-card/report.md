# Gap 35: saved series-card acceptance

Build: `64ee15f19f7acf80a2dbb7e5035d8c037128fea6`, dirty isolated
`fix/gap35-series-card` worktree. Runtime: GPT-6.1-sol, medium. Browser:
owned headed CLI session `gap35-series-card`, loopback port 8517.
World: cloned immutable `26UHC`, seed 2038, season 1 week 18 Masters semifinal
`s1msf0`. The root's live career and browsers were untouched.

The saved `after_loss / stabilize / fa_0 in / ghost out` directive now appears
as After Loss / Stabilize / Hollowlock / Ghost in all four form controls.
The current summary names both players. Clicking Save series card unchanged,
leaving Match, and revisiting Prep preserved every selection. Public API
readback independently confirmed the same directive and default lineup.

A controlled browser response removed the saved players from authoritative
legal options without modifying server state. The form retained both names
as unavailable selected options and disabled Save. Explicitly clearing one
player stayed blocked; clearing both enabled Save. Another controlled response
with a different saved fixture ID rendered Trailing / Steady / No substitution
in both controls and omitted the current summary. These are controlled UI
checks, not claims that the real career lost players or advanced fixtures.
Nine focused tests cover actual serializer read immutability, unchanged-save
roundtrips, absent/played/past/different fixtures, newly starting substitutes,
departed players, and absent player records. Node syntax checking passed.

Accepted decision coverage: exactly one meaningful decision attempt, one
accepted `series_directive` at action index 78. The original 78-decision prefix
is preserved byte-for-byte as parsed records. The final 79-decision save has
identical directive, default lineup, and every other GameState field;
only `action_log` changed. The one team retains all 17 telemetry snapshots.
Header Save persists the save and is outside the accepted decision vocabulary.
The source save SHA256 is
`e8c864a4fb5f6e5894cab49cb4e7e40939a9335286aa1a7f1506036c7a100743`;
final acceptance save SHA256 is
`55879871f9ae8c366c09fcb4b4e495d75c79f6f73adb8fe42d2f6c69c40238f9`.

Retained usage at the final audit: 75 total events, 71 scoped to world26UHC,
including two attempts paired with two successful HTTP200 results:
series directive request12 and header Save request24. Other scoped records:
39 visible-time slices, 20 views, four session starts and four session ends.
This fresh owned sidecar started empty; it contains only this acceptance run.
Counts describe retained bounded telemetry, not complete attention or funnels.
Session/browser identity fields are excluded from committed evidence.
The four blocked bootstrap/argument attempts are preserved as unverified;
no request or accepted-decision capture is inferred for those failures.
Seven rows met their intent, four were blocked. Read-only/editor/audit rows
are outside the accepted decision vocabulary, and row4 is recorded.

Corrections are append-only. Row9 independently asserts partial/both-clear
behavior because row8's console diagnostics were not printed by the CLI;
row11 fixes the first audit's team-key-versus-snapshot count denominator.
The final audit reports one team and 17 snapshots. Expectations and prior
rows remain intact. No match outcome or balance claim is made by this run.

Evidence: [actions.csv](actions.csv), [audit.json](audit.json), and
[browser-evidence.md](browser-evidence.md). Full snapshots, raw own save and
private session bootstrap stay in ignored local paths under `runs/` and
`saves/`; none are staged. Flywheel inherited eight recent esports-playtest
entries before play and recorded two learnings plus one pain-point as
`esports-playtest-0170`, `0171`, `0172`.

The previously launched unfiltered native suite completed with 1283 passed in 1921.53 seconds, terminal exit0 at 2026-10-11T00:42:10.743442+00:00. All634 pre/post/current source, test, data, script, workflow and runtime configuration fingerprints match. The [receipt](evidence/receipt.json), [terminal output](evidence/pytest.log), freeze manifests and original launcher are preserved. Root independently verified the immutable source/save hashes, all78 prior decisions, the sole added series directive, unchanged17 snapshots and both session/request/target usage pairs. Later root readback found78 total usage events,74 world-scoped: the original71 sanitized events are an exact prefix, with three later visible-time events. The original audit and its dated counts above are preserved. See [publication review](evidence/publication-review.json). No new local tests were launched, following the user's instruction. Current-head remote CI remains required before merge.
