# Historical roster data pipeline

Historical packs begin with source observations, not gameplay attributes.
`scripts/extract_historical_stats.py` parses the saved VLR and Liquipedia HTML
pages into deterministic JSON with event provenance, source hashes and a
warning list:

```powershell
python scripts\extract_historical_stats.py C:\Users\aidan\Downloads\rosters data\research\vct-2021\observations.json --season 2021
```

The JSON contains separate `events` and `observations` collections. VLR rows
are season aggregates; Liquipedia rows are per-event observations. Their
player identifiers are source-specific and must only be linked through a
reviewed crosswalk--never by display name alone.

For VCT 2021, the supplied archive yields eight unique Liquipedia stat pages
(411 player-event rows, 241 player pages) and one first-page VLR aggregate
(100 players). It is strong evidence for observed professionals, but it is
not a complete historical roster list: the VLR page is paginated and the
event coverage is concentrated in international, NA, EMEA and Korea events.

The next curation step is a `data/rosters/vct-2021/src/` pack. It must choose
one early-2021 roster snapshot per team, map observed players to a reviewed
identity/role/agent profile, and translate sample-size-adjusted statistics to
the builder's `quality` plus carefully authored `attr_overrides`. Do not put
scraped stats directly into runtime `Player` data; the game only consumes the
curated, deterministic roster sheets.

The current game also treats all maps and agents as available. A true 2021
start requires a later era-availability layer before adding the selectable
start date, otherwise modern agents can leak into a historical campaign.

## Future-player timeline

Historical packs may set `start_year` in `src/pack.yaml` and add a
`src/future_prospects.yaml` sheet. Each future prospect uses the normal compact
player fields plus `birth_year`; they must be under 17 at the pack's start:

```yaml
future_prospects:
  - handle: Example
    birth_year: 2006
    region: americas
    role: duelist
    playstyle: entry
    igl: false
    quality: 54
    agents: [jett, raze]
```

The builder derives the starting age and `debut_year = birth_year + 17`.
Campaign saves keep these players in an off-screen prospect pool, apply normal
offseason aging/development, and release them into free agency only when they
turn 17. They never appear in active rosters, scouting, or the market before
then. The observed 2022-26 pages should be used to curate their eventual
identity, quality, roles and signature agents; birth years must come from a
reviewed biographical source rather than guessed from stat pages.
