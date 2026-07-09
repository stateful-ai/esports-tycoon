---
name: maps
description: Change map content end-to-end — callout graph, floor geometry, gimmicks, painted backdrop — through the full gate chain (floor audit, pacing, balance, guides, repaint check, thumbs, golden re-bless). Use for any edit under data/maps/** or assets/maps/**.
---

# Maps — geometry + paint change workflow

A map is FOUR coupled artifacts that must stay in sync:
`data/maps/<id>.yaml` (callout graph + gimmicks) →
`data/maps/geometry/<id>.yaml` (floor plates, corridors, props, elevation) →
`assets/maps/guides/<id>.png` (rasterized structure guide) →
`assets/maps/painted/<id>.webp` (painted backdrop) + `assets/maps/<id>.webp`
(thumb). Editing an early link stales every later one.

## Order of operations

1. **Edit the data.** Delegate pure authoring to the `map-author` agent
   (it owns the YAML conventions and never touches engine code). For the
   graph: adjacency must be symmetric; gimmicks sit on adjacency edges.
   For geometry: rooms within gap 4.0 auto-portal, otherwise author a
   corridor with via-waypoints; props inside their rooms (pad 2).
2. **Floor audit**: `.venv-win\Scripts\python.exe scripts\map_floor_audit.py`
   → exit 0. Plates touch on every adjacency, callout centers on their own
   plate, path polylines on the plate union. Teleporter edges exempt (the
   engine collapses those moves to endpoints — players beam, never walk).
3. **Sim gates**: `scripts\pacing_report.py` (25–35s attacker rotate via
   spawn, 8–18s spawn→entry stage, defender interior strictly faster) and
   `scripts\balance_report.py 300` (45–65% attack, aim 52–60). Geometry is
   gameplay: moving a room changes duel ranges and rotate times.
4. **Regenerate the guide**: `scripts\render_map_guide.py --map <id>`.
   Guides rasterize at the exact viewer transform (the script prints the
   constants + per-map content bounds) — the painted backdrop `<image>` in
   viewer.js is pinned at those same viewBox coords. Never change one side
   of that contract alone.
5. **Repaint or flag stale paint.** If plates moved where paint exists,
   the backdrop is stale EVEN IF footprint-IoU still passes — IoU ≥ 0.99
   has shipped wrong seams. The real detector is a 50%-blend overlay of
   new guide over old paint, read per seam. Repaint via the `/art-pass`
   skill (map section: full-scene Gemini, strip surgery, outside-mask to
   ground color 9,11,17, per-channel color transfer).
6. **Thumbs**: `scripts\render_map_thumbs.py` after any repaint.
7. **Golden**: geometry/graph edits drift the golden fixtures — expected
   for an intentional change. Re-bless BOTH fixtures with
   `scripts\regen_golden.py` in the same commit, after steps 2–3 pass.
8. **Verify in the viewer** (players walk on paint, no void-walking,
   markers legible), then ship via `/ship`.

## Known traps

- The engine paths on the callout graph, not the paint — disconnected
  plates mean players visually walk the void long before any test fails.
  That's why step 2 is a permanent gate.
- Funneling multiple entries into one choke RAISES attack rate; the
  lever that lowers it is defense-advantaged holder→entry sightlines.
- After connecting plates, re-read the map's style brief: flavor props
  that were legal on a void-facing wall become seam-blockers (Lotus's
  B-site mural failure mode).
- Only latest-week fixtures have replays (chips marked with a play
  suffix) — don't click stale map-name chips when verifying.
