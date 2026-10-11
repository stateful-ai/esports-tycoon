# Preparation advice provenance acceptance

Tested base: `042d86d3161fc5fa3185091031ba546193b2e97e`, dirty isolated branch `fix/preparation-advice-provenance`. Runtime: GPT-6.1-sol, medium. Server: own loopback port 8476, `--no-browser`; Python imports verified from this worktree's `src`. Seed 2038, copied Team Nexus world 26UHC, S1 W8 -> W9. The root's source save and the user's primary career were not changed.

The question was whether a preparation development lead describes its actual evidence. The historical W8 mental-reset report said Echo "pushed the starters on lotus." Preparation selects the bench candidate from map mastery and does not simulate a scrim or measure player performance. That historical string is preserved; changing future report generation must not rewrite old saves.

The new W9 mental-reset/light session with Hokkaido Drift on Ascent produced: "Map mastery projects Echo as a bench option for ascent; no scrim performance was measured. Consider a focused development block before trying that rotation." Public `/api/club` and the Match Prep screenshot independently confirm the report. Its costs and artifact remain methodology +0.67, condition cost 1.5, morale +2.5, chemistry +0.3, prep edge 0. No win is attributed to this wording change.

See [future Match screenshot](evidence/future-match.png), [historical report screenshot](evidence/historical-readback.png), [public final report](evidence/club-after.json), and [before/after mechanical parity](evidence/baseline-parity.json). The parity check loaded the exact base module and compared all four objectives: report numeric fields, candidate IDs, whole GameState mutations, and RNG state were identical; only report text differed. Eighteen targeted preparation tests passed, covering all objectives, no eligible bench, and historical report loading. The full unfiltered `pytest -q -n2` gate completed with **1258 passed in 7688.66s**, native exit 0 at `2026-10-10T20:04:41.4475956Z`; see [terminal log](evidence/full-pytest.log) and [native completion receipt](evidence/full-pytest-result.json). Before publication both raw frozen-source SHA256 hashes were independently checked against the live files, the imported package path was reverified, and all other tracked source, tests, scripts, data, and configuration remained unchanged from the tested base. The branch was not rebased onto later main.

The test kept meaningful blocked attempts:

- The in-app browser join control did not respond. This is an automation blockage with no observed HTTP rejection or accepted decision.
- Standalone Playwright reached the join grid, where the existing human seat was disabled. The isolated copy was reopened through an owned session/history sidecar.
- The first advance returned HTTP 409 for a pending media choice. Choosing the visible "Keep the response inside the room" option resolved it; the next advance succeeded.
- The week-reveal overlay intercepted navigation after the successful advance. A fresh page supplied the final readback and explicit Save.
- Correction to step 3: its first screenshot was taken while Match was rendering and did not itself display the historical note. `historical-readback.txt/png` later visibly confirmed it.
- Correction to the two-surface expectation: Club Development does not render preparation `dev_suggestion` on this build. Match Prep is the visible home of this development advice; no new Development UI was added. The absence is captured in `future-development.txt/png`.

The per-session [CSV](actions.csv) preserves eight rows and their expectations. The independent [audit](evidence/audit.json) confirms the saved action log's original 40-entry prefix is unchanged and all three new accepted decisions appear in order: index 40 `set_preparation`, index 41 `media_choice` (`keep_internal`), index 42 `advance`. Decision coverage is 3/3 (100%). The rejected advance adds no accepted action. Read-only navigation and Save are outside the accepted-decision vocabulary.

Published browser text captures trim trailing whitespace only; screenshots and CSV rows are unchanged, and raw text copies remain in the local validation artifacts.

The retained world usage stream contains 57 events, five attempts and five results, with all five request IDs paired: preparation, rejected advance, media choice, successful advance, and Save. This stream is separate from accepted decisions. Unresponsive IAB clicks and the disabled join choice have no observed request capture; lobby events do not prove such clicks were instrumented. Counts are retained best-effort coverage, not exact session duration or attention. See [world usage](evidence/world-usage.jsonl) and aggregate reports; aggregates include the blocked lobby browser sessions. No other careers were included in the decision report.

The source save's SHA256 remains `ea97d274868fe1e1f21c24ea8f66e9a3b9807cf0aa271b0f8042d279d6e0147a`. Flywheel findings were read before the session via the repository-approved Python fallback and two learnings plus one pain-point were recorded after it. Candidate projection and historical-report preservation are confirmed learnings; copied-career/browser/reveal recovery is the pain-point.

Scope is deterministic report wording only. Balance/pacing/floor gates do not trigger: no engine, constants, maps, or geometry changed. Snowball does not trigger because candidate selection and every campaign numeric effect are preserved.
