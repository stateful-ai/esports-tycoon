# Locked fixture map advice acceptance

Build: main `64ee15f19f7acf80a2dbb7e5035d8c037128fea6`, dirty owned worktree,
game 0.0.1 (the CSV captures the build version), runtime gpt-6.1-sol/medium.
Surface: actual standalone Playwright browser session `gap33-map-advice`,
isolated loopback port 8514. Copied world 26UHC, seed 2038, S1 W17,
Team Nexus versus Meridian Cross, fixture s1mqf1 Masters QF BO3.

The historical comparison independently reproduces Haven as the relative
weakness (Nexus 50%, Meridian 100%) and Bind as the relative strength
(Nexus 100%, Meridian 57%). The old shared board exposed these as Ban/Pick
despite the stored series already banning Haven and Bind. The fixed board
keeps all own-team historical records and replaces actionable historical
advice with the stored veto and records for the actual scheduled maps.

| Scheduled map | Nexus season record | Meridian season record |
| --- | --- | --- |
| Ascent | 3/5 (60%) | 2/4 (50%) |
| Lotus | 4/7 (57%) | 1/2 (50%) |
| Split | 1/1 (100%) | 5/5 (100%) |

Dashboard and Match day briefing both display “Series maps — veto locked”,
the stored `MRC ban haven · NXS ban bind · MRC pick ascent · NXS pick lotus ·
decider split`, and the exact records above. Neither offers Pick Bind as
an action. Game plan lists ascent/lotus/split; Prep offers exactly Ascent,
Lotus and Split. Historical own-team Bind and Haven records remain visible.
These are descriptive season records with sample sizes, not forecasts.

Evidence under `runs/playtests/2026-10-10-gap33-fixture-map-advice/`:
`05-dashboard-confirmed.yml`, `06-matchday.yml`, `03-gameplan.yml`,
`04-prep.yml`, `08-saved.yml`, and `reconciliation.json`.
Four attempts are logged in the adjacent append-only `actions.csv` shard.
Step 2 explicitly corrects step 1: its initial reload file was incomplete
and its numeric records were wrong. Do not use that initial observation
as numeric evidence. The completed snapshots and independent audit agree.
The audit initially failed on Windows cp1252 decoding and then an incorrect
attribute substitution; the corrected UTF-8 audit succeeded. No source files
were changed during these audit repairs.

Browser Save left the campaign byte-identical to the identified immutable
source: SHA256 `32d6564f38d0adff259bd59e53aaf3b45d44df3de8b10470ca301e1b6719bba6`.
All 72 pre-existing accepted action records and all telemetry snapshots remain
unchanged. There were zero new accepted gameplay decisions and zero changed
GameState fields. All four read-only/persistence attempts are outside the
accepted decision vocabulary, so decision coverage is 0/0 new decisions,
with four `not_instrumented` annotations. This does not imply missing decisions.

The separate retained browser stream contains 27 events, 25 attached to 26UHC,
across two page sessions (one initial lobby session). It records seven views,
one Save attempt and one paired successful result, no unmatched attempts,
and no orphan results. Dashboard, Strategy, Game plan and Prep navigation
have retained view records. Opening the Match day overlay has no separate
view event, and read-only GETs are outside request attempt/result telemetry.
Visible-time events are visibility proxies; no attention, complete funnel,
or duration claims are made. The isolated usage directory started empty.
Reports: `decision-report.txt` and `usage-report.json` beside the snapshots.

Focused regression tests: 9 passed (shape, team ownership in both orientations,
single-map fixture, locked series with/without historical records, no fixture).
JS syntax and diff whitespace checks passed previously. The earlier unfiltered native suite completed with 1278 passed in 5656.29s (1:34:16), actual terminal exit0 at 2026-10-11T01:18:18.142772+00:00. Root independently verified all624 pre/post/current source/config/test/script/workflow fingerprints, complete72-decision/16-snapshot saved-state byte equality and Save request21/result200 pairing. No new local tests were launched under the user's instruction. Current-head CI remains required before merge.

Flywheel inherited four recent findings before play; follow-up entries
esports-playtest-0158, -0159 and -0160 record two learnings and one pain point.
Canonical primary CSV and user careers were untouched; root reconciles this
session shard sequentially.

Raw shard SHA256:
`bbaef9c6897db17a388655928d2b8e45612376825b98992410d51ad0310592ff`.


Root late cleanup/readback found the dedicated browser still open, generating idle visibility records. The browser was closed through its named CLI session and both task-owned server families were stopped, with ports8514/8515 no longer listening; user8421 was untouched. The original dated aggregate27/25 counts above remain historical snapshots. Current raw retained readback contains507 events, all currently tagged26UHC, including495 visibility slices, seven views, two starts, one end and the same single Save pair. These later visibility records are idle surface exposure, not player attention. The original27-event audit categories and newer raw filtering are separate observations; no absent final session-end beacon is reconstructed after server shutdown. Durable evidence now lives in evidence/.

Only the Save row's factual analytics status/evidence was updated to recorded for the retained paired browser usage request, explicitly outside accepted campaign decisions. All19 observation fields, partial/failed outcomes and original intentions remain unchanged. The original scoped CSV and field-protection proof are preserved in evidence/.
