# Roster schema and MCP reference

## Setup

Install the project with the MCP extra:

```powershell
.venv-win\Scripts\python.exe -m pip install -e ".[dev,web,mcp]"
```

The project `.mcp.json` registers the stdio server as `esports-rosters` using:

```text
.venv-win\Scripts\python.exe -m esports_sim.mcp.roster_server
```

Set `ESPORTS_ROSTER_DRAFT_DIR` to redirect draft files, such as in tests or an
external agent workspace. Installed packs always use the game's configured
`data/rosters/` library.

## Tool selection

| Goal | Tool |
|---|---|
| Inspect legal fields and game ids | `get_roster_schema` |
| List playable installed packs | `list_roster_packs` |
| List editable drafts | `list_roster_drafts` |
| Start from scratch or a valid example | `create_draft` |
| Correct an existing source-backed pack | `open_installed_pack` |
| Read the complete portable document | `get_draft` |
| Check errors without changing game data | `validate_draft` |
| Change pack/world settings | `update_pack_metadata` |
| Create/edit/remove an org | `add_team`, `edit_team`, `remove_team` |
| Create/edit/remove a rostered player | `add_team_player`, `edit_team_player`, `remove_team_player` |
| Create/edit/remove an unsigned player | `add_free_agent`, `edit_free_agent`, `remove_free_agent` |
| Make a valid draft playable | `install_draft` |

## Portable document

Top-level fields:

- `schema_version`: currently `1`.
- `id`: lowercase hyphen-case pack id and install directory.
- `name`, `description`: ASCII display metadata.
- `world.league_regions`: three or four unique region ids.
- `world.teams_per_region`: tier-1 target, 4-16.
- `world.tier2_per_region`: tier-2 target, 0-16.
- `teams`: authored team sheets.
- `free_agents`: unrostered players available in the opening market.

Team fields:

- `name`, `tag`, `region`, `tier`, `prestige`, `partial`, `players`.
- Tier 1 requires five authored players and one IGL.
- Tier 2 may be partial and receives deterministic generated fill to five.

Player fields:

- Required identity/shape: `handle`, `role`, `playstyle`, `quality`.
- Common authored fields: `real_name`, `age`, `country`, `languages`, `igl`,
  `agents`, and `attr_overrides`.
- Optional hidden career fields: `potential`, `career_volatility` (0-100),
  `development_archetype`, `development_peak_age`, `development_peak_years`,
  `development_decline_age`, and `development_realization`. These center
  future development and do not change opening `quality` or attributes.
- Free agents additionally require `region`.
- `languages` is at most three `{lang, level}` objects.
- `agents` is at most three unique signature agent ids.
- `quality`, language levels, and attribute overrides use bounded scales as
  declared by `get_roster_schema`.

Example team-player payload:

```json
{
  "handle": "caller",
  "real_name": "",
  "age": 22,
  "country": "US",
  "languages": [{"lang": "en", "level": 100}],
  "role": "controller",
  "playstyle": "igl",
  "igl": true,
  "quality": 72,
  "agents": ["omen", "viper"],
  "attr_overrides": {}
}
```

Mutation tools return the changed entity plus current validation. An invalid
result is expected while an empty tier-1 team is being assembled; continue to
five players and one IGL before installation.
