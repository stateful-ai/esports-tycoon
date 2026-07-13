# VCT 2021 pack

This is a playable early-VCT-era snapshot, intended as the first historical
start date rather than a claim to reproduce every 2021 regional league.

## Scope

- **Start year:** 2021.
- **World:** ten curated tier-1 teams plus six performance-weighted tier-2
  organizations each from Americas, EMEA and Pacific.
- **Snapshot convention:** core lineups reflect the 2021 VCT season, using
  roster combinations that were active for a meaningful part of the year.
  It deliberately does not splice a player's later 2021/2022 team into an
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

Tier-2 rosters are explicitly marked `partial` where historical five-player
evidence is too thin in the supplied archive. The deterministic builder tops
those teams up with regional prospects; this preserves a real organization and
relative performance tier without inventing a precise historical roster.

To update it, edit `src/*.yaml`, then run:

```powershell
.venv-win\Scripts\python.exe scripts\build_roster_pack.py vct-2021
```
