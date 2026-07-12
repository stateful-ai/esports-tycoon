---
name: build-roster-packs
description: Build, research, validate, and edit esports-sim roster packs with the portable YAML/JSON schema and the esports-rosters MCP server. Use when an agent needs to create a custom league, import favorite teams, inspect or correct an installed pack, add/edit/remove rostered players or free agents, validate roster data, or install a finished pack into the game.
---

# Build roster packs

Use the `esports-rosters` MCP tools when available. They edit portable drafts
through the same schema and deterministic compiler as Roster Studio.

## Workflow

1. Call `get_roster_schema` before authoring unfamiliar fields or ids.
2. Start with `create_draft`, or call `open_installed_pack` to correct a pack.
3. Add teams, then use the team-player/free-agent add, edit, and remove tools.
4. Call `validate_draft` after each logical batch. Treat errors as blockers and
   warnings about generated regional fill as informational.
5. Review the complete document with `get_draft`.
6. Call `install_draft` only when `validation.valid` is true and the user asked
   to make the pack playable. Installation atomically replaces that pack id.
7. Run `tests/test_roster_workbench.py` and `tests/test_rosters.py` after code
   or compiler changes. Pure content edits need at least draft validation.

Draft tools write `data/rosters/.drafts/<pack-id>.roster-pack.yaml`; they do not
change installed game data. `install_draft` is the sole MCP install boundary.

## Authoring rules

- Never edit derived `data/rosters/<id>/teams/*.yaml` files directly.
- Keep ids and authored text ASCII. Pack ids use lowercase hyphen-case.
- Use only catalog region, role, playstyle, agent, and attribute ids.
- Give each tier-1 team exactly five players and exactly one `igl: true`.
- Give a tier-2 team zero to five players and at most one IGL; missing academy
  players are generated deterministically.
- Keep handles unique within a team and in the free-agent pool.
- Treat `quality` as an authored estimate, not a scraped statistical rating.
- Sanity-check duplicate or mismatched source links before entering real names.
- Preserve source notes separately; the portable document contains data, not
  research citations.

Read [references/roster-schema.md](references/roster-schema.md) for field
shapes, MCP setup, tool selection, and a player example.

## Fallback without MCP

Use the shared CLI rather than hand-writing generated bundles:

```powershell
python scripts\roster_pack_tool.py schema roster-pack-schema.json
python scripts\roster_pack_tool.py validate my-pack.roster.yaml
python scripts\roster_pack_tool.py install my-pack.roster.yaml
```

The web UI at `/roster-studio.html` can observe and edit the same document.
