---
name: map-studio-authoring
description: Create, extend, or co-edit ESports Simulator map geometry through the esports-maps MCP server and the same revisioned Studio document used by the visual Map Studio UI. Use for new maps, callouts, floor plates, walls, cover, routes, doors, ropes, teleporters, plant zones, sightlines, or AI-human map collaboration.
---

# Map Studio Authoring

Build against the shared `data/maps/studio/<map_id>.yaml` source through the
`esports-maps` MCP server. Never hand-edit compiled runtime YAML while using
this workflow: Map Studio and the MCP must see the same source and revision.

Read [references/mcp-workflow.md](references/mcp-workflow.md) before authoring.

## Workflow

1. Call `get_map_schema` before constructing elements. Treat its schemas and
   compile limits as authoritative.
2. Call `list_maps`, then either:
   - `create_map` with `template="two-site"` for a valid connected starting
     point or `template="empty"` for a deliberate blank canvas; or
   - `open_map_for_editing` to materialize a legacy map into the Studio source.
   - `fork_map` to make a non-destructive variant of an existing draft or
     legacy map without materializing or modifying the source map.
3. Keep the returned `revision_hash`. Pass it as `if_match_hash` to every
   mutation, and replace it with the hash returned by that mutation.
4. Work in coherent slices: surface, navigational semantic zone, connections,
   then blockers/cover. Use `apply_map_patch` for a complete room group or a
   full generated layout so the slice lands in one revision. Keep individual
   upserts for small interactive corrections. Use stable, descriptive ids.
5. Call `validate_map` after each slice. Invalid intermediate drafts are
   allowed, but do not leave the map incomplete or publish it invalid.
6. Use `probe_map_geometry` at spawns, entries, sites, chokes, and long LOS
   lanes to verify floor resolution, clearance, reachability, and collision.
7. Call `get_map` for a final whole-document review. The user can open
   `/map-studio.html?map=<map_id>` and co-edit the same draft at any time.
8. Call `publish_map` only when the user explicitly asks to replace the runtime
   artifacts. Publishing is not part of ordinary draft authoring.

## Collaboration rule

If any tool reports a stale revision, stop mutating. Call `get_map`, compare the
new document with the work you intended, preserve the human's changes, and
reapply only the still-needed delta using the new hash. Never blind-retry and
never omit `if_match_hash`.

The UI polls for AI saves. It auto-reloads when clean and shows an external
change warning when the human has unsaved work, so both editors retain control.

## Geometry rules

- Author axis-aligned rectangles for walkable surfaces and prop footprints;
  the current runtime compiler rejects arbitrary polygons.
- Map each navigational zone to exactly one walkable surface and each surface
  to exactly one non-plant zone.
- Make plant zones semantic overlays inside the site polygon and reference the
  site's existing surface. Do not create a second plant surface.
- Give every non-plant zone the correct tactical `legacy_zone`.
- Connect navigational surfaces with traversal links. Keep link endpoints and
  every corridor `via` point on walkable floor.
- Use full-height props or walls for LOS blockers and half-height props for
  cover. Keep colliding props strictly supported by their surface.
- Give walls an explicit stable `id`; legacy ID-less walls can be read but new
  MCP walls may not omit it.
- Prefer typed upserts or `apply_map_patch` over untyped document rewrites.
  Batch removals do not cascade, so repair references in the same patch and
  validate immediately.

## Completion

Report the map id, final revision hash, validation result, important probe
findings, whether runtime artifacts were published, and the Map Studio URL. If
published, continue with the full `/maps` gate chain for floor, pacing, balance,
guide/paint alignment, thumbnails, and golden fixtures.
