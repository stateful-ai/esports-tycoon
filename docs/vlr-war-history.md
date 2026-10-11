# Historical VLR data for WAR research

The research lives in `data/research/war-history/`. It expands the original
[2026 roster research](vlr-2026-research.md) without changing game attributes,
authored quality, canonical overalls, or the installed roster pack.

## Coverage and snapshot

The manifest selects 88 events: all 50 previously selected 2026 events at
full-map detail, all 2024 and 2025 tier-1 Kickoff, Stage 1, Stage 2, Masters
and Champions events, and the four regional Ascension finals in each
historical year. Historical tier-2 regular leagues and every 2026 event are
not comprehensively covered. This is an explicit event sample, not a census
of the entire scene.

Matches must have an identified pair of teams, a date between January 1,
2024 and October 8, 2026 inclusive in UTC, and finished MR12 scores. Unplayed
Champions matches, future fixtures, cancelled matches, partial lineups and
missing stats remain explicit issues or eligibility exclusions.

Cached pages retain their original retrieval time. Some event aggregates
and profiles came from the earlier October 6 snapshot; new match tabs were
retrieved during this expansion. Aggregates are source snapshots, not
reconstructed historical as-of data. The map model uses map outcomes and
lineups, not those event aggregates. Never silently claim that these mixed
retrieval timestamps form a single contemporaneous contract snapshot.

See `research_summary.json`, `validation.json`, `context_validation.json`,
`collection_issues.csv` and `tab_coverage.csv` for actual coverage and gaps.

## Facts and grains

| File | Grain and purpose |
| --- | --- |
| `map_outcomes.csv` | One MR12-complete source map scoreline: teams, winner, date, patch, event, provenance. Administrative scorelines retained for audit; series aggregate excluded. |
| `player_map_stats.csv` | One identified source player/map row: VLR ID, team, opponent, agent, raw box-score markup. Administrative placeholders flagged in model eligibility; side rows and series totals excluded. |
| `player_map_side_stats.csv` | One source player/map/attacking-or-defending side: raw split box-score markup; exposure blank when the round history cannot be reconciled. Kept separate from both-side totals. |
| `player_event_stats.csv` | One player/event aggregate; season is the event's actual year. |
| `map_context.csv` | One map: event stage, raw veto note, picker slot, displayed duration, starting sides and side-specific rounds won. |
| `round_outcomes.csv` | One displayed played round: winner, both sides, cumulative score and win-condition icon name. Empty trailing round placeholders excluded. |
| `round_economy.csv` | One team per displayed round: team loadout value from the cell's tooltip title, rounded bank display, buy-category symbol, side, win. |
| `player_map_performance.csv` | One player/map: displayed 2K–5K counts, 1v1–1v5 clutch wins, ECON, plants, defuses. |
| `tab_coverage.csv` | One map/tab: observed row count and URL/hash/retrieval time; provenance parent for compact round/performance facts. Zero rows means the source did not provide that tab's data. |
| `profile_team_history.csv` | One player/team listing from 441 cached profile candidates: current/past section, role/status badges and date text. |
| `roster_news_index.csv` | One player/profile/roster-news headline: publication date and article link; article body and effective signing date unverified. |
| `team_map_lineups.csv` | One team/map with all five real IDs; incomplete lineups excluded. |
| `observed_lineup_changes.csv` | First map with a different five than that team's previous observed map, including players in/out and the observation gap. |
| `observed_player_team_changes.csv` | A player observed on a different team than their previous observed map. May reflect a transfer, stand-in, affiliate appearance or short substitution. |
| `replacement_pool_review.csv` | Statistical 2026 tier-2 candidates with at least ten eligible maps; availability still requires verification. |
| `agent_role_reference.csv` | 29 agent identities/roles from a pinned public Valorant-API snapshot, including Miks and Veto; gzip JSON and source hash retained under `reference/`. |

The bank string `0.3k` remains a rounded source display; it is not an exact
300-credit balance. Loadout value measures team equipment value, not cash
spent or bank. Blank buy symbols are preserved, including pistol/eco cells;
they do not by themselves indicate missing loadout data. No weapon inventory
is inferred from a buy category.

Blank multikill/clutch cells remain blank. Do not turn them into numeric zero
without a separately verified source contract. Displayed objective zeroes
remain zero. Hover contents containing victim names and round numbers are
excluded from the displayed count. Performance tables lack player-ID links,
so their identities are joined by exact handle plus team tag within that
same map, and ambiguous joins are rejected.
An offline repair pass can recover differing parent/academy tags only when
the performance row's team logo uniquely matches one match-header team and
its local handle and agent also match. `performance_identity_review.csv`
records these joins; unresolved composite names remain excluded. Original
collection issues remain visible beside `performance_issue_resolution.csv`.

Forfeit pages can contain ten named players and zero-valued HTML markup even
when the browser displays blank, unplayed box scores. These are source
placeholders, not observations of zero-kill performances. Administrative
scorelines without recorded play, unknown map names and all-zero combat
placeholders are excluded via `map_model_eligibility.csv`; they remain in
raw tables for audit. A forfeit note alone does not discard played maps with
recorded combat in that series, and a legitimate 13–0 win remains eligible.
The placeholder warning applies to side/performance rows too. Join model
eligibility before treating these raw tables as played-performance samples.
Three negative ECON values on map 269508 were independently confirmed in the
rendered performance table. They remain unchanged in raw facts and are flagged
in `performance_value_review.csv` for source-definition review, with
`use_for_performance_model=False`. Negative discrete counts still fail validation.

Starting side follows the first displayed side in the map's team header;
each played round's side is also preserved from its win-cell class. Overtime
round sides come from the source, not a guessed alternating-side rule.
Round-win totals, sequential scores and scoreline totals are reconciled.
Discrepant or absent histories are retained and excluded from round-model
eligibility, without throwing away an otherwise valid map outcome.
`economy_model_eligibility.csv` separately requires both teams' equipment
values for every played round and winners/sides consistent with a valid
overview history. It excludes source gaps from future economy models; the
raw cells remain available for review.

Profile dates commonly have month precision. Preserve `December 2024` or
`joined in June 2026` verbatim: do not invent a day or a current contract end
date. A past section can contain a `joined in` label or stand-in badge;
section and badge remain separate facts. News dates are publication dates.
Match timestamps come from VLR's UTC match header; maps in the same series
share that timestamp. Observed histories sort by date, match ID and map ID,
not independently verified map start times. They establish appearances and
sampled lineup changes, not the exact time a transfer or substitution began.

## Modeling and evaluation

`analyze_vlr_war_history.py` uses sparse ridge logistic regression and four
models evaluated against exactly the same later maps:

1. Team-year and team-map identities, plus starting side by map.
2. Historical signed player identities, plus starting side by map.
3. The same lineup model trained only on 2026 maps.
4. Historical players combined with the team-year/team-map baseline.

Only identified complete ten-player competitive maps enter these models;
administrative placeholders and unknown-map records are excluded. Neither K/D/A,
ADR, rating, round economy, clutches nor any other same-map outcome enters
that map's prediction. These additional facts support later round/performance
research, not outcome leakage in this experiment.
Combat fields are checked only to flag unplayed placeholders for eligibility,
never used as predictors of the same map's winner.

The fixed chronological boundaries are April 1, 2026 for validation and
July 15, 2026 for the final test. An entire UTC date, and thus every map in a
series, stays on one side of each boundary. Penalties 1/5/20 and equal weights
versus a 365-day half-life are chosen on validation only. Decay age is
measured relative to the corresponding fitting boundary, not a future test
result. Unseen identity columns have zero fitted coefficient under ridge.

`heldout_map_predictions.csv` retains every prediction and label. The report
records hashes of its input files and analysis code, plus NumPy/SciPy
versions, so predictions can be tied to the collected snapshot. It
also separately evaluates maps whose actual lineup differs from their team's
last observed training lineup; this includes transfers/substitutions and
long gaps, and is not a verified roster-move causal experiment.

The lineup-minus-team log-loss difference receives a paired 2,000-resample
series-cluster bootstrap interval with a blake2b seed derived from
`vlr-war-history:series-bootstrap:20261008`. A negative difference
favors the lineup model. The interval preserves dependence between maps in
a series, conditional on the fitted models; it does not express uncertainty
in player coefficients, causality, or the entire selection/tuning process.

After held-out evaluation, a full-history lineup model produces
`experimental_historical_war.csv`. Its replacement coefficient is the 25th
percentile among players in the same connected competition component and
dominant role with at least ten 2026 tier-2 maps. At least eight eligible
peers are required; otherwise the proxy is blank. Availability is unverified.
The candidate review records observed regions and the last observed team;
neither establishes contract availability or regional roster eligibility.
Dominant roles use the published [Valorant-API agent metadata](https://valorant-api.com/v1/agents?isPlayableCharacter=true)
snapshot, with the authored game registry only as fallback. This is a
community-maintained metadata source, not a verified Riot esports feed.
Unknown roles do not form a pooled replacement class.
Dominant role uses 2026 appearances when available; players absent in 2026
use their historical role with that fallback explicitly marked. This does
not infer a player's future role or erase role changes within a season.
The proxy sums fitted win-probability differences over the player's observed
maps after substituting the replacement coefficient.
Separate 2026 totals and rates per 100 observed maps make exposure explicit;
the underlying coefficients still come from the full-history research refit.
These rates are not estimates of a player's causal wins in a future season.

This remains observational WAR research. Transfers improve lineup variation,
but near-collinearity, role changes, coaching, selection and aging remain
confounds. Exactly identical player columns are listed as inseparable;
different columns are not proof of reliable individual estimates.
Each player row also reports the teammate they appeared with most often,
the shared-map fraction, and maps played without that teammate. This makes
near-locked pairings visible without treating a few different appearances
as adequate identification or assigning a confidence interval.
The report also compares exact ties with and without historical appearances
for the same expanded 2026 player cohort, so changed coverage does not inflate
the claimed identification improvement.
Historical coefficients across disconnected circuits are not comparable. Every player
row has `use_for_game_overall=False`.

## Snapshot results

The expansion contains 8,043 source map scorelines: 5,225 from 2026, 1,461
from 2025 and 1,357 from 2024. It has 79,900 raw player/map rows and 2,268
observed player IDs. The competitive lineup models use 7,929 maps and 2,255
players, excluding 105 incomplete lineups, six unknown-map records and three
administrative scorelines without observed play.

The context tables contain 166,527 displayed rounds, 289,764 team/round
economy records and 68,547 player/map performance rows.
The side table has 159,800 source rows; 12,168 contain no reported split stats.
There are 789 observed
five-player lineup changes and 891 observed player/team changes involving
643 players. These are appearance histories, not verified signing counts.
Profile evidence adds 3,065 team-history entries and 392 roster-news index
entries from 441 cached profiles.

On the same 2,041-player 2026 cohort, adding history reduces exact teammate
ties from 1,370 players to 1,083, resolving 287 players' exact ties. More than
half the cohort still has an exactly inseparable teammate, and near-locked
pairings remain beyond that count.

The final holdout has 679 maps across 270 series:

| Model | Log loss (lower is better) | Brier score | Accuracy |
| --- | ---: | ---: | ---: |
| Team-year / team-map | 0.692495 | 0.249542 | 53.02% |
| Historical lineup | 0.695857 | 0.250806 | 54.79% |
| 2026-only lineup | 0.704684 | 0.254522 | 54.64% |
| Historical players + teams | 0.700729 | 0.252800 | 55.23% |

History improves the observed lineup model's log loss relative to its
2026-only ablation, but it does not beat the team baseline. The historical
lineup-minus-team difference is +0.003362, with a series-bootstrap 95%
interval of [-0.008163, +0.015149]. There is no convincing evidence of a
predictive advantage over teams, and the probabilities remain close to a
coin-flip benchmark. The expanded data improves identification and supplies
context for a stronger future model; it does not justify WAR-based overalls.

## Browser checks and reproduction

`manual_audit/observations.json` contains independent browser observations;
screenshots and per-field checks are preserved beside it. The checker uses
CSV lookup and numeric/text comparison, not the collection parser. This is
a purposive sample, not a dataset-wide measured error rate. See the audit
README for reviewed pages and transcription corrections.

The final audit passes 816 fields across ten source URLs and 15 screenshots.
Structural validation has zero errors. Its 2,459 warning entries include 910
event-aggregate reconciliation differences, 1,311 missing-stat entries, 236
incomplete-lineup entries and two opening-duel inconsistencies. These are
warning counts, not unique affected matches or players; they remain visible
in `validation.json`. Context validation separately flags the three negative
ECON values. Nine performance maps remain unresolved rather than receiving
guessed identities. The statistical replacement review lists 1,014 candidates;
their availability and regional eligibility remain unverified.

Install the optional `research` extra. Example on a Python 3.12+ environment:

```sh
python -m pip install -e ".[dev,web,research]"
python scripts/collect_vlr_war_history.py --cache /persistent/vlr-pages
python scripts/collect_vlr_roster_evidence.py --cache /persistent/vlr-pages
python scripts/build_vlr_agent_reference.py
python scripts/repair_vlr_performance_tags.py --cache /persistent/vlr-pages
OPENBLAS_NUM_THREADS=1 python scripts/analyze_vlr_war_history.py
python scripts/enrich_vlr_war_sides.py --cache /persistent/vlr-pages
python scripts/analyze_vlr_war_history.py --validate-only
python scripts/check_vlr_manual_audit.py --data data/research/war-history
```

For exact raw-fact reproduction, retain the immutable gzip HTML cache and
use `--offline --output /temporary/rebuild` on the history collector. The
manifest, cache, parser and dependency versions define the snapshot. Raw
HTML is not committed; URLs can change after collection, so a later network
run is a new snapshot. Requests remain sequential and at least 0.5 seconds
apart. Only public permitted endpoints are used; replay/round-event endpoints
under `/rr/` and automatic search endpoints are not collected.
Use `--resume` after an interrupted collection. It keeps fully checkpointed
events, removes partial next-event rows, and reparses that event from cache.
New checkpoints verify the manifest and snapshot hashes before resuming;
`collection_resumes.json` records any older-format checkpoint recovery.
Incomplete HTTP bodies are never cached and receive up to three attempts.
HTTP client errors such as 403/404 are retained rather than retried. Completed
collections must be rebuilt into a separate output, not resumed after repair.

## Remaining data gaps

Trade timing, utility assists, detailed kill chronology and per-player weapon
inventories need a suitable permitted match-event feed or carefully tagged
VODs. Exact coach tenure and transfer-effective dates need independently
verified announcements. LAN/online context is explicitly unverified rather
than inferred from the event name. A usable free-agent replacement baseline
still needs dated availability, region and role constraints. The headline
index and statistical candidate pool make that work easier but do not finish it.
