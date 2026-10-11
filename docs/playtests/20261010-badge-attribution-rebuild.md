# Badge development attribution rebuild

Build: `063452905f69edd85ea866d0278ce609494308a9` plus the scoped dirty source recorded in [source-freeze.json](evidence/20261010-badge-attribution/source-freeze.json). Manifest SHA256: `fdf066ef0800e614258c38809a09fbf56fbb22f47ed1b333225e5c929c344296`. The worktree is badge-attribution-rebuild. The primary checkout and user server 8421 were untouched. Python import verification points to this worktree's src.

## Recovery and implementation

The previous badge-development-attribution checkout was absent; its task attachment did not provide an archived source snapshot. Its earlier uncommitted source and 1197-test result were not recovered or credited. Reconstructed from freshly fetched origin/main including weekly Full report dependency PR #352.

Badges record their measured post-clamp skill deltas in a distinct weekly source plus earn/loss provenance. Overall attribution is computed in Python from actual applied skill changes. The profile tooltip uses stored applied CA and PA, rather than catalogue maxima. A new weekly tracking flag distinguishes an observed no-badge week from legacy missing evidence. Schema 37 preserves old-save defaults; no historical badge evidence is fabricated. Dedicated RNG streams and badge effects are unchanged; both AI and human rosters use the same evidence hook.

## Player session and controlled rendering

Runtime: gpt-6.1-sol, medium. Browser acceptance server: 8464, social LLM off. Intents/expectations precede actions under session `20261010-badge-attribution-rebuild`. The four original session rows are preserved verbatim in [session actions.csv](evidence/20261010-badge-attribution/actions.csv), isolated for sequential integration into the canonical history by the parent task. The canonical CSV in this PR equals the base version. Each meaningful action, recovery, and blocked attempt is retained.

Natural world **247PG**, seed **2026**: created Team Nexus at S1 W1, advanced one week, opened Full report, then saved via the browser. Public report: 13-1 versus Tokyo Drift Six. Phantom's Practice +0.50 OVR appears separately from Matches +0.03 OVR. All five say "No badge changes this week". This is a counterexample to attributing the +0.50 growth to a badge.

The original CUA Campaigns click stalled on a JavaScript confirmation. A fresh tab allowed observation and seed changes, but organisation clicks emitted no retained requests. Direct HTTP leave recovered the isolated lobby; standalone Playwright was then used for a clearly marked rendering fixture. This blocked/recovered result is a partial CSV row; it is not a successful simulated week.

[Controlled Full report screenshot](evidence/20261010-badge-attribution/controlled-full-report.png) uses the real report rendering and server-computed fixture payload:

- Apex: Clutch Master +0.07 OVR, from actual Clutch Factor +0.50 and Composure +0.20 at the upper bound.
- Phantom: Choker -0.15 OVR, from actual Clutch Factor -1.00 and Composure -0.50 at the lower bound.
- Three other players: no badge changes. The fixture exposes no weekly OVR comparison because no adjacent snapshots were simulated.

The fixture is disposable, outside shipped source, and did not simulate or save a career. Playwright captured zero page errors. It verifies rendering, not naturally earned badge probability or gameplay outcomes.

## Decision and usage reconciliation

Independent saved-state readback: [decision-audit.json](evidence/20261010-badge-attribution/decision-audit.json) contains exactly one accepted decision, action_log index 0: `advance`, empty params, team_nexus, source web, S1 W1 regular. The one consequential CSV decision matches **1/1 (100%)**; one weekly telemetry snapshot exists. Creation, read-only report navigation, saving, and the fixture are outside the accepted decision vocabulary.

Natural-session usage evidence is isolated by session id and readback cutoff. The pre-intent baseline was reconstructed from retained receipt timestamps after play, rather than captured live before the first action; the baseline and retained raw events are preserved; retained report has **3 attempts, 3 paired success results, zero unmatched attempts, zero orphan results**, for new/advance/save. Full-report opening has one `week/full_report_open` interaction. These are **3/3 retained request pairs**, not proof of an exhaustive funnel. CUA blocked clicks emitted no observed request, and direct HTTP recovery emits no browser usage. Visible-time slices are a visibility proxy and the bounded sidecar can drop events. The isolated telemetry report reads only world 247PG.

## Validation

Focused: 4 new badge attribution tests passed, covering bounded positive/negative gains, refresh no-op, measured decay reversal, legacy schema 36 load/schema 37 roundtrip, no-badge and read-only report provenance. Existing badge + weekly development tests: 15 passed. `node --check app.js` passed. The staged whitespace check reports one extra blank line at the new test file EOF; it is preserved so the committed source matches the frozen test bytes.

Durable hidden gate runners started 2026-10-10 17:17 UTC. Status JSON preserves cwd, command, baseline head, runner/child PID, start/end and terminal exit. Each completed gate asserts source_unchanged against the same manifest.

- Snowball seed 777, 3 seasons: exit 0; blowout 15.1/17.8/17.1%, close 43.4/36.4/41.5%.
- Snowball seed 2026, 3 seasons: exit 0; blowout 14.0/16.7/16.3%, close 42.2/37.2/33.3%.
- Snowball seed 31337, 3 seasons: exit 0; blowout 16.7/19.4/13.6%, close 39.9/39.9/44.2%.
- Full unfiltered pytest: exit 0; `1249 passed in 2644.72s (0:44:04)`. Frozen source unchanged.
- Dynasty seed 4242, 10 seasons: exit 0; frozen source unchanged. Terminal report:

```text
dynasty report: 10 seasons, seed 4242
champions: 10 titles, 5 distinct orgs
   3  Team Vanguard
   3  Gallic Storm
   2  Jakarta Ravens
   1  Ghostline
   1  Nova Rift
top share: 30% (Team Vanguard)
PASS
```

No engine, constants, map data or policy contract changes; balance, pacing and floor gates are outside this change's trigger set. Golden is included in full pytest.

## Flywheel findings

Flywheel tools were unavailable in this session, so findings remain local.

Learning 1 (high confidence, 247PG/2026): a visible +0.50 OVR can be practice rather than badges; explicit per-source evidence prevents false causal attribution.

Learning 2 (high confidence, controlled fixture): catalogue badge amounts overstate actual gains at bounds; measured per-skill deltas and provenance make small positive and negative changes auditable.

Pain point (observed CUA/8464): a stalled campaign-lobby confirmation can leave new-tab clicks without requests; standalone browser fallback preserved the acceptance result, while the original blocked attempt remained logged.
