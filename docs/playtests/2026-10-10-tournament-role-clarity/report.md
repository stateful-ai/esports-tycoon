# Tournament six role clarity

Tested origin/main `042d86d3161fc5fa3185091031ba546193b2e97e` plus this change,
Python 3.13.14, GPT-6.1-sol / medium, hidden Chromium browser and isolated
server `127.0.0.1:8475`. Seed 2038, world 26UHC, Team Nexus, S1 W7.
The immutable 36-decision source world was copied with its metadata, sessions
and match review into this worktree's ignored run directory. Primary saves,
the user's server and canonical actions CSV were untouched.

The player question was whether Tournament six described eligibility,
contractual expectations, or the current selected five. Its rows now explicitly
say **Promised squad role**. The card explains the eligibility checkboxes and
directs the player to Club and fixture game plans, including map overrides,
for actual selection. No server, campaign, registration or simulation rules
changed.

## Player observations

Four timestamped pre-action expectations and outcomes are in `actions.csv`.
The copied source fixture initially still selected Echo, unlike the parent's
later rotation. This unexpected observation was retained. In the isolated
browser, the player benched exhausted Echo and selected Ghost using Club's
star controls and Save lineup. Independent public roster readback confirmed
Hollowlock (`fa_0`) and Ghost selected, Echo excluded. Returning to Match / Prep
showed Echo **Promised squad role: Starter** and Hollowlock **Promised squad
role: Bench**, with the explicit explanation above. Eligible registration
membership and promised roles stayed unchanged; automatic registration order
followed the new default five. The screenshot was visually inspected at
1600x1000 and the explanatory copy wrapped within the card without overlap.

The initial direct read used `/api/roster` instead of
`/api/roster/team_nexus` and returned 404. That readback failure was recorded
and corrected before accepting the result. An overstrict equality assertion
also stopped after the successful rotation because automatic registration
ordering changed. The continuation read the already-applied selection; it
did not repeat the mutation or change the original expectation.

## Independent telemetry reconciliation

`accepted-before.json`, `accepted-after.json` and `telemetry-audit.json`
preserve the saved decision evidence. All 36 baseline records match the saved
prefix exactly, by index, kind, parameters, team, source and S1 W7 ordering.
There is exactly one new accepted decision: index 36, `set_lineup`, source
`web`, team `team_nexus`, manager `mgr_team_nexus`. One meaningful decision
attempt matched one accepted record (100%). Its coarse flags omit selected
IDs; exact membership is proven by the independent public roster in
`browser.json`. Save and navigation add no accepted decisions.

`usage-events.jsonl` preserves 27 retained events across two browser page
sessions: 2 session starts, 11 views, 10 visibility slices, 2 request attempts
and 2 results. Lineup request 13 and save request 15 each pair with HTTP 200
success in their respective sessions. `usage-report.json` is the independent
usage aggregate; `decision-report.txt` reports only this copied world's save.
Successful public reads do not emit request events. The direct HTTP 404 was
outside the application API wrapper and is not represented as a browser
rejection. Early short browser contexts closed before periodic flush, so
retained usage does not establish complete navigation coverage or attention.

## Validation and learning loop

Four focused integration tests passed, covering saved and automatic defaults,
the primary and a second human club, opposing contract promises, a per-map
override, and repeated read purity. `node --check` passed. The full unfiltered
Python 3.13.14 `pytest -q -n2` gate passed: **1256 passed in 7611.99s**
(2:06:51), terminal exit 0. `gate-result.json`, `pytest.log` and
`source-before.json` retain the receipt, final summary and all 544 source
hashes. At publication every raw src/tests/data hash matched the manifest;
the package imported from this worktree. No rebase or source edit intervened. This wording-only change does not trigger
balance, pacing, floor or snowball gates.

Pre-play inheritance used the repository guide and prior playtest evidence:
record expectations before acting, read back consequential state independently,
and separate accepted decisions from usage. No flywheel MCP tools were exposed
in this runtime, so the required findings are retained here for later ingestion.

- Learning (high confidence): promised squad role can intentionally differ
  from current lineup; explicit row labels resolve the ambiguity without
  rewriting career promises or sim selection rules. Evidence: browser card and
  roster, world 26UHC / seed 2038 / W7.
- Learning (high confidence): a source fixture and a later test world may
  share world code/time but have different selections. Verify the actual
  public lineup before claiming a reproduction; retain unexpected results.
- Pain point (high confidence): coarse lineup decision parameters cannot
  establish exact dressed IDs alone. Independent public roster readback is
  necessary, and brief browser sessions may close before usage flush.
