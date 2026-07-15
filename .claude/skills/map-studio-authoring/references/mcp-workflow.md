# ESports Map Studio MCP workflow

## Source and registration

The project registers the stdio server as `esports-maps` in `.mcp.json` and
also exposes `esports-map-mcp`. Its shared source is:

`data/maps/studio/<map_id>.yaml`

Map Studio reads and writes that file. Publishing compiles it transactionally
to the runtime graph, geometry YAML, and guide PNG.

If the MCP extra is missing, install the project with `pip install -e ".[mcp]"`
using the repository's Windows virtual environment, then restart the MCP host.

## Tool sequence

| Stage | Tools | Notes |
|---|---|---|
| Discover | `get_map_schema`, `list_maps` | Read schemas before making elements. |
| Begin | `create_map`, `open_map_for_editing` | Both return the full document and revision hash. |
| Inspect | `get_map`, `validate_map` | `get_map` is the conflict-reconciliation source. |
| Structure | `update_map_metadata`, `upsert_walkable_surface`, `upsert_semantic_zone` | Pass and advance `if_match_hash` after every call. |
| Gameplay | `upsert_traversal_link`, `upsert_prop`, `upsert_wall`, `set_sightlines` | Use stable ids and validate coherent batches. |
| Repair | `remove_map_element` | No cascade; fix references yourself. |
| Test | `probe_map_geometry` | Check floor, collision, LOS, clearance, and reachability. |
| Promote | `publish_map` | Explicit user approval only; exact revision is locked. |

## Revision protocol

Every mutation is compare-and-swap:

1. Read revision `H1`.
2. Mutate with `if_match_hash=H1`.
3. Continue with returned revision `H2`.
4. If stale, fetch the new document and revision, reconcile both editors'
   intent, then submit a fresh typed mutation.

Do not cache hashes across tasks and do not guess whether another editor has
saved. A mutation result deliberately omits the full document to reduce token
use; call `get_map` whenever whole-document context is needed.

## Authoring model

- A `WalkableSurface` is physical floor.
- A non-plant `SemanticZone` is the runtime callout attached to that floor.
- A plant `SemanticZone` is an overlay inside a site and shares its surface.
- A `TraversalLink` creates runtime adjacency and optionally a motor-route
  corridor or an environment gimmick.
- A colliding `Prop` creates cover or a full-height blocker.
- A `Wall` creates stable-id wall segments and full-height runtime blockers.
- Sightlines are runtime strategic hints between callouts, not substitutes for
  physical LOS probes.

The `two-site` template is meant as a structurally valid scaffold, not a
finished competitive layout. Reshape it deliberately, then use the `/maps`
skill's pacing and balance gates before shipping.
