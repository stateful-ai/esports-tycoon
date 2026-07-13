# VCT 2021 pack

This is a playable 2021 VCT-era roster pack, intended as the first historical
start date rather than a claim to reproduce every 2021 regional league.

## Scope

- **Snapshot convention:** each selected team uses its latest documented
  shared five from calendar year 2021. It deliberately does not splice a
  player's later 2022 team into an
  earlier lineup just because that later roster is better known.

## Evidence and curation

The compact sheets under `src/` are the canonical inputs. The supplied archive
contains 2021 Champions, Masters Reykjavik/Berlin, NA, EMEA and Korea stats;
those observations anchor quality estimates where coverage exists. Roles,
captains, ages, identities and signature-agent mapping are curated gameplay
data, not direct scrape output. See `docs/historical-roster-data.md` for the
source pipeline and its coverage limits.

The pack intentionally stays within the three regions that had useful 2021
coverage in the supplied archive. China is deliberately deferred: it had no
official VCT circuit in 2021, so adding it needs a separate domestic-scene
research pass rather than filler presented as historical truth.

The world has ten tier-1 and six tier-2 clubs per Americas, EMEA and Pacific.
Every authored club has a corroborated real five; every other player found in
the supplied 2021 event-stat pages is seeded into free agency (after
normalized alias deduplication). Later real prospects stay hidden until age 17
through `src/future_prospects.yaml`.

The supplied 2022-2026 event pages feed separate generated intake sheets:
`src/future_archive_free_agents.yaml` and
`src/future_archive_prospects.yaml`. Recreate them with
`scripts/import_future_archive_players.py <rosters-directory>`. Earlier
observations are signable from 2021; later observations are conservatively
held until their first observed season, with verified under-17 exceptions kept
in the prospect queue.

To update it, edit `src/*.yaml`, then run:

```powershell
.venv-win\Scripts\python.exe scripts\build_roster_pack.py vct-2021
```
