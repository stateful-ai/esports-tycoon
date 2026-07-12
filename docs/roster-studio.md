# Roster Studio

Roster Studio turns the game's compact roster source sheets into one portable,
strict YAML/JSON document. A person can edit the document visually, an agent can
edit it as structured data, and both paths call the same validator and
deterministic compiler.

Open the game, choose **Roster Studio** from the Play screen, then either:

1. Open an installed roster pack.
2. Import a `.yaml`, `.yml`, or `.json` document made by an agent.
3. Start from the valid example included in the studio.

**Save & install** validates the complete document, compiles all derived player
attributes/masteries from stable hashes, loads the result through the game's
normal roster-pack loader, and only then swaps it into `data/rosters/<id>/`.
The pack immediately appears as a world in the Play lobby. No server restart is
needed.

## Agent and tool workflow

The portable document is the handoff contract. It contains authored facts and
estimates, not generated attributes. JSON and YAML use exactly the same keys.

```powershell
python scripts\roster_pack_tool.py schema roster-pack-schema.json
python scripts\roster_pack_tool.py new my-pack.roster.yaml
python scripts\roster_pack_tool.py validate my-pack.roster.yaml
python scripts\roster_pack_tool.py install my-pack.roster.yaml
```

Export any installed source-backed pack back to one file:

```powershell
python scripts\roster_pack_tool.py export vct-2026 vct-2026.roster.yaml
```

The studio's **AI handoff** button copies concise format rules plus the current
document. **Download schema bundle** supplies the complete JSON Schema and the
live game catalog of legal regions, roles, playstyles, agent IDs, and attribute
IDs. This works with any agentic tool that can read/write JSON or YAML and run a
validation command.

## HTTP tool contract

When the web server is running, tools can use:

- `GET /api/roster-studio/schema` - JSON Schema, catalogs, example, prompt.
- `GET /api/roster-studio/packs` - installed pack library.
- `GET /api/roster-studio/packs/{id}` - portable source document.
- `POST /api/roster-studio/validate` - field errors, warnings, and counts; an
  incomplete draft returns HTTP 200 with `valid: false`.
- `POST /api/roster-studio/parse` - parse YAML or JSON text into a document.
- `PUT /api/roster-studio/packs/{id}` - validate, compile, and atomically
  install a complete document.
- `GET /api/roster-studio/packs/{id}/export` - portable YAML download.

Tier-1 teams require exactly five authored players and exactly one IGL. Tier-2
teams may be partial; the deterministic builder fills their open academy slots.
A partial world may author only favorite teams: the campaign generator fills
the remaining regional league slots requested by `world.teams_per_region` and
`world.tier2_per_region`.

## MCP server

Install the MCP extra and let the project `.mcp.json` register the
`esports-rosters` stdio server:

```powershell
.venv-win\Scripts\python.exe -m pip install -e ".[dev,web,mcp]"
.venv-win\Scripts\python.exe -m esports_sim.mcp.roster_server
```

The MCP offers schema/catalog inspection, installed-pack and draft listing,
draft creation, pack metadata and team edits, add/edit/remove tools for team
players and free agents, validation, and explicit atomic installation. Drafts
live under `data/rosters/.drafts/` and are ignored by Git; no mutation changes
the playable library until `install_draft` succeeds.
