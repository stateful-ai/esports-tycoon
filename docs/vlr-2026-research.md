# VLR 2026 roster research

This research layer extends the existing `vct-2026` pack with real observations,
map outcomes, source identities, and reviewable rating proposals. It does not
write gameplay attributes. The pack represents a **July 9, 2026 snapshot**;
this research was collected on **October 6, 2026**. Season-to-date evidence must
not be presented as information available at the pack's start date.

## Start here

The CSVs live in [`data/research/vct-2026`](../data/research/vct-2026/).

The snapshot contains 3,816 event observations for 1,994 distinct players,
1,567 map outcomes, and 15,157 player-map rows. There are 1,470 complete-lineup
maps available for the outcome model. Counting 52 additional map-only identities
gives 2,046 distinct observed players across both statistics tables.
Of 435 authored pack players, 386 have
corroborated VLR identities and 355 have reviewable statistical quality proposals.
All 88 authored free agents receive an availability review row; this does not
establish that all 88 are professionally available.

| File | Grain / purpose |
| --- | --- |
| `event_manifest.json` | Explicit event selection, regions, competition tiers, and map-collection scope |
| `events.csv` | One row per selected event; aggregate and map coverage counts |
| `player_event_stats.csv` | One player per event, using VLR player IDs |
| `map_outcomes.csv` | One played map, with both scores, winner, timestamp, patch, teams, and source |
| `player_map_stats.csv` | One player per played map; actual agent, team, opponent, and box score |
| `sources.csv` | URL, retrieval timestamp, SHA-256 of downloaded HTML, byte count, parser version |
| `collection_issues.csv` | Failed, unavailable, unfinished, or unsupported source records |
| `player_profiles.csv` | Profile identity and current-team listing evidence; not a contract database |
| `roster_crosswalk.csv` | Existing pack player to VLR identity, with corroboration status and evidence |
| `free_agent_review.csv` | Every authored pack free agent, with availability/status review flags |
| `event_quality_signals.csv` | Role-adjusted, sample-shrunk statistical signals per player/event |
| `quality_recommendations.csv` | Signals joined to corroborated pack identities, existing quality and runtime overall, proposed quality changes |
| `unmapped_player_shortlist.csv` | Observed competitors to research for additions; availability unverified |
| `experimental_lineup_war.csv` | Retrospective lineup-based win association and replacement counterfactual |
| `map_model_eligibility.csv` | Map-by-map eligibility, observed lineup size, and exclusion reason |
| `validation.json` | Key, join, missingness, scoreline, lineup, and event/map reconciliation checks |
| `model_evaluation.json` | Chronological evaluation, baselines, replacement definition, and limitations |
| `manual_audit/` | Independent browser screenshots, manual observations, and field comparisons |
| `research_summary.json` | Collection, identity, browser audit, and model summary |
| `reproduction.json` | Full offline cached-HTML rebuild comparison of nine collected CSVs |
| `verification.json` | Full/focused test results, source checks, browser audit, and balance/pacing receipts |

## Coverage and provenance

The manifest records 50 events discovered from VLR's
[tier-1](https://www.vlr.gg/events/?tier=60) and
[tier-2](https://www.vlr.gg/events/?tier=61) listings. This includes the four
VCT regions' Kickoff, Stage 1, Stage 2, both Masters, and the ongoing Champions
event; selected Challengers circuits cover the Americas, EMEA, Pacific, and
China. This is a bounded research sample, not complete worldwide coverage.
Competition tier describes the selected event, not a player's permanent status.

Full match/map collection is enabled for 16 events: Masters Santiago and London;
the four regional VCT Stage 1 events; all three NA Challengers stages; EMEA
Challengers Stages 1-3; Brazil Challengers Stage 2; Japan Season Finals; Pacific
Last Chance Qualifier; and China National Tournament Split Alpha Pro Division.
Use `events.csv` for actual collection counts and `collection_issues.csv` for
gaps. Stage 2 and Champions have aggregate statistics, not full map coverage in
this first collection. Ongoing Champions totals are provisional.

The China Pro Division may expose map statistics without an event aggregate
table. Its absence is recorded, rather than synthesized into a VLR observation.
Unnamed teams, unplayed maps, and dates outside the cutoff are not silently
converted into losses. Optional stats missing at the source remain empty CSV
cells. Each eligible map has ten player rows and is checked against its outcome.
This snapshot retains 97 China Pro Division map outcomes with incomplete source
lineups. Their available rows remain in the raw CSV, but those maps are excluded
from the lineup model. `map_model_eligibility.csv` records every decision.
Map `rounds` is the sum of the two displayed scores. Event `rounds` is VLR's
reported aggregate denominator. These measures can disagree: ten China Stage 1
players' event totals exceed their collected scoreline sums by one. The source
values and reconciliation warnings are retained without inventing a correction
or a cause. Treat these denominators separately when deriving future rates.

Match pages contain series, attack, defense, and map views. The parser includes
only actual map IDs and the `both` side statistics; series aggregates are never
counted as maps. FK/FD display formatting has changed on VLR: original reported
values are retained, while comparable `fkpr` and `fdpr` use integer totals divided
by rounds. `kast_pct`, `hs_pct`, and clutch percentages are 0-100 percentages.
ACS is average combat score; ADR is average damage per round. Agent identifiers
are the real source agents, without the older pack's agent remapping.

The collector saves gzip-compressed HTML plus hash metadata in the caller's
cache directory. It verifies hashes before reuse, stays on public VLR pages,
avoids the robots-disallowed endpoints, and spaces requests by at least 0.5s.
The repository contains extracted facts and provenance, not full source pages.
Preserve your cache for exact offline reproduction: a later fresh download may
change provisional totals. Retrieval time is observation freshness, not match
time. Source links and hashes alone cannot recover a historical HTML snapshot.

## Independent browser checks

Ten live VLR pages were opened in Chromium and their rendered tables visually
checked against the CSVs. The audit checks 662 manually transcribed fields,
including names, scores, overtime round count, K/D/A, rating, ACS, KAST, ADR,
headshots, opening kills/deaths, event totals, and source blanks. All match.
The sample includes tier 1, tier 2, overtime, missing optional statistics, and
an incomplete China lineup, and the China Stage 1 denominator discrepancy.
Free-agent profile checks verify identity, alias evidence, and the separation
of past-team entries from current-team listings.
This is a purposive spot check, not a statistical
estimate of dataset-wide accuracy or worldwide coverage.

The screenshots and independent observations live in
[`manual_audit`](../data/research/vct-2026/manual_audit/). The comparison script
uses those observations directly and never calls the collection parser:

```bash
python scripts/check_vlr_manual_audit.py
```

Wait for the page's presentation animations to settle before capturing a table;
otherwise digits can appear partly clipped. Differences from the first audit
draft were transcription errors (CHAROD's opening counts and Racoone's handle),
resolved against the screenshots. The collected values did not require changes.

## Identity and free agency

A matching display handle produces a **candidate**, never a sufficient join.
The crosswalk requires either an independently matching profile real name or
matching event team tag plus country. Placeholder real names equal to handles
and `Unknown` do not count as independent evidence. Ambiguous or uncorroborated
rows retain candidate IDs and get no automatic quality proposal. Manually found
profile URLs in `profile_candidates.json` follow the same corroboration rule.

`pack_status` preserves how the existing game categorizes the player. It is not
an assertion about current professional availability. A profile may list an
active team, a bench, a stand-in role, or content creation. No current team
listed does not establish free-agent contract status. Profile news is historical
evidence and must be checked for subsequent returns before declaring retirement.

For example, [FNS's profile](https://www.vlr.gg/player/817/fns) links his retirement,
[Sacy's profile](https://www.vlr.gg/player/659/sacy) links his retirement, and
[Marved's profile](https://www.vlr.gg/player/263/marved) lists stand-in evidence.
Treat these as distinct availability cases. The review CSV retains relevant
news and team evidence, but leaves contract status unverified. Inactive players
without eligible 2026 observations receive no invented current-form statistics.

## Quality proposals

The game's canonical overall is `manager.development.overall(player)`, the mean
of expanded attributes. The compact sheet's `quality` is an authored base;
archetypes, overrides, and deterministic expansion mean it is not identical to
overall. The recommendations expose both existing values and propose **quality**,
not a replacement implementation of overall.

The initial statistical method is an explicit heuristic, not a fitted talent
scale:

1. Assign an event observation's dominant role using its first, most-used real
   agent and the game's current agent-role registry. Unknown agents remain
   unknown. A dominant agent cannot establish IGL responsibility.
2. Compare within the same event and dominant role, using reference players with
   at least 100 rounds. If fewer than five role peers exist, fall back to event
   peers and flag the absence of role control.
3. Combine robust standardized VLR rating (70%), ADR (15%), and KAST (15%).
   Center with the median; use `1.4826 * MAD`, floored at 0.08 rating, 10 ADR,
   and 4 KAST percentage points. Clip each standardized feature to +/-3.
4. Shrink the observation by `rounds / (rounds + 300)`. Translate to a quality
   signal using authored anchors 74 for tier 1 and 64 for tier 2, and 9 points
   per standardized unit; clamp to 45-92.
5. Average a player's event signals by observed rounds, then blend with their
   current pack quality using `total_rounds / (total_rounds + 600)`.

These weights, anchors, and shrinkage constants are modeling choices. They need
calibration against simulation and future results. The tier anchors are a prior,
not proof that an excellent tier-2 player is weaker than every tier-1 player.
No rating cap is imposed solely because somebody is in the game's free-agent
pool. Correlated box-score measures do not provide three independent sources of
evidence. The output uses season-to-date evidence without recency weighting;
it must not be treated as a prediction of form at the July snapshot.

Team losses do not directly reduce this box-score proposal. This protects a
strong performer on a weak team from receiving an automatic losing-team penalty.
Opponent quality, economy, role sacrifices, utility, and team strategy still
affect the underlying statistics. Never infer comms, leadership, discipline,
or every individual mechanical attribute from ACS alone. Review agent pools,
IGL assignments, roster changes, and samples before editing source sheets.

## Experimental WAR

The outcome experiment fits ridge logistic regression to map wins. Each map
has +1 for its five team-1 players and -1 for its five opponents. Teammates and
opponents enter jointly; no same-map box scores enter the predictor. There is
no arbitrary home-side intercept. This is a regularized adjusted-plus-minus
analogue, not an estimate of causal individual skill.

Validation uses chronological UTC-date splits. Entire series and dates stay on
one side. Ridge penalties are selected on an earlier validation period inside
training. The untouched later test period compares lineup predictions against
a separately tuned team-identity model and a 50/50 probability baseline using log loss,
Brier score, and accuracy. The team model also considers smaller penalties to
account for five identical player columns being equivalent to one team column.
Only after evaluation are lineup coefficients refit on all observations.
Classification ties at probability 0.5 predict team 1, so the even-probability
baseline's reported accuracy is the team-1 win frequency; log loss and Brier
score are the relevant probability baselines.

An illustrative replacement baseline is the 25th-percentile lineup coefficient
among same-role, same-connected-component players with at least ten tier-2 maps.
If fewer than eight peers exist, use component-wide tier-2 peers and flag the
role fallback. If that pool is still too small, WAR is blank. This is an
empirical research baseline, not the actual available free-agent market.

For each played map, the experiment replaces one player's coefficient with that
baseline while keeping the other nine fixed. Sum fitted `P(win with player)`
minus fitted `P(win with replacement)` to obtain `experimental_war_proxy`;
the per-100-map column separates rate from accumulated opportunity. Values can
be negative. These are fitted map-win equivalents, not series wins or titles.

**Stable rosters are the central identification problem.** Teammates who always
play together have identical design columns. Ridge divides their shared signal
equally; it cannot learn which one supplied the value. The CSV lists these
inseparable teammates. More subtle collinearity also remains when columns differ.
Disconnected circuits cannot be compared from their coefficients, and changing
rosters can coincide with changing coaches, schedules, patches, or team systems.
There are no calibrated uncertainty intervals or controls for economy, map/side
preferences, coaching, and patch effects. Within-series observations are dependent.
Even beating the team baseline does not resolve these confounders.

In this snapshot, 545 of 680 modeled players are exactly inseparable from at
least one teammate. Held-out lineup log loss is 0.665745, compared with 0.666217
for team identity; accuracy is 58.36% versus 58.03%. The tiny observed advantage
is not convincing evidence that individual WAR is suitable for gameplay ratings.

Consequently every row has `use_for_game_overall = False`. Keep statistical
quality and lineup win association as separate evidence; do not turn team
success into five star ratings. Before using WAR for overalls, broaden map
coverage, require identifiable lineup variation and adequate samples, add
role/patch/economy context where available, use series-block uncertainty, and
validate across later events and actual roster moves. A practical next stage
is a prior-informed hierarchical model, with expert estimates retained for IGL
and utility impact, followed by deterministic simulation calibration.

## Reproduce and extend

Python 3.12+; the repository's Windows environment uses `.venv-win`. Linux CI
and cloud environments can use their existing interpreter. Install the optional
research dependencies:

```sh
python -m pip install -e '.[dev,web,research]'
python scripts/collect_vlr_research.py --cache /path/to/persistent/vlr-cache
python scripts/analyze_vlr_research.py
```

Rebuild from those exact cached pages without network access:

```sh
python scripts/collect_vlr_research.py --cache /path/to/persistent/vlr-cache --offline
python scripts/analyze_vlr_research.py
python -m pytest -q -n0 tests/test_vlr_research.py
```

Use `--profiles-only` to rebuild identity/status CSVs from existing event/map
CSVs. Add events or expand `collect_maps` in the manifest, then rerun. The cache
is immutable by URL; use a **new cache directory and separate output directory**
for a later snapshot. Supply matching `--manifest`, `--profile-candidates`,
`--output`, and `--as-of` arguments when creating a new dataset. The current
collector is for the 2026 season and intentionally is not a general archive
crawler. `--validate-only` reruns data integrity checks without refitting.
The initial snapshot was rebuilt offline into a separate directory; every
record in all nine collected CSVs matched, including provenance and identities.

Research fixtures test map/series/side grain, date cutoffs, unnamed teams,
missing values, identity collisions, current-vs-past team evidence, duplicate
maps, and logistic orientation/locked-teammate behavior. The game suite and
its required gates remain part of the pre-push checks. Applying reviewed
roster changes is a later step through the roster authoring workflow:
edit a draft/compact source, validate, compile deterministically, and run gates.

The dataset's exact final counts, identified gaps, and evaluation results are
summarized in `data/research/vct-2026/research_summary.json` after collection.
