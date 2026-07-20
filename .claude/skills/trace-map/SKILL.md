---
name: trace-map
description: Trace a real-map wiki minimap into esports-sim geometry one-for-one (grid overlay, canonical rotation, rect-per-callout trace, gate chain). Use when rebuilding a map's geometry from a reference minimap image.
---

# Trace a wiki minimap into map geometry

Rebuild `data/maps/geometry/<id>.yaml` (and the callout anchors in
`data/maps/<id>.yaml`) so the plates copy a real minimap screenshot
one-for-one. Proven on all five live maps (ascent/bind/haven/lotus/
split — see those files' comments for the house style). Source images
live wherever the user dropped them (e.g. `~/Downloads/maps/<id>.png`).

Rotations that worked: ascent/haven/split `ccw` (game compass:
attackers east, A north), bind `flipv` (already broadcast-oriented),
lotus `180` (attackers south, A east). `transpose` exists for
attackers-west sources but hasn't been needed yet.

## Workflow

1. **Grid the source.**
   `.venv-win\Scripts\python.exe scripts\wiki_map_trace.py grid <src.png> <scratch>\<id>_grid.png --rotate ccw`
   Wiki minimaps are in raw game orientation; our canonical frame is
   attackers at low y, defenders at high y, A site left, B site right.
   Find the plant zones first (olive rectangles with pin markers) and
   the spawn masses, then pick the rotation that lands attackers on
   top. Ascent needed `ccw`; check per map, don't assume.
2. **Read the layout.** View the gridded image, then cut labeled
   close-ups with `... wiki_map_trace.py zoom <id>_grid.png
   "aside,0,40,45,90" "mid,25,25,65,95" ...` (name,x0,y0,x1,y1 in map
   units). Identify every existing callout's floor mass and note exact
   unit coordinates for room edges, plant zones, necks, and signature
   props. Keep the existing callout SET, but expect to rewire several
   adjacency edges per map: every adjacency pair's plates must
   physically touch (corridors don't exempt), so an edge whose real
   walk crosses a third room's floor gets rerouted through that room
   (haven: spawn's Long edges via the lobbies, garage->site via mid
   doors; lotus: Diamond off the Tree lane; split: the west street off
   Mid Top). When an edge dies, kill or reassign its sightlines too.
3. **Author the geometry.** One axis-aligned rect per callout tracing
   its floor mass, on these rules (all enforced by gates or the
   engine):
   - Every adjacency pair's rects must touch: gap <= 0.75u
     (`map_audit.rects_touch`); corridors do NOT exempt an edge.
   - Every corridor waypoint AND the sampled center->portal->center
     polylines must stay on the union of region rects (eps 0.75).
   - Callout anchors (`data/maps/<id>.yaml` x/y) must sit on their own
     plate — update them to the new rect interiors.
   - L-shaped rooms: cover the bounding span with the rect and stand a
     full-height "mask" prop on the solid building volume inside it.
     Masks are sight blockers: check every declared sightline's
     center-to-center segment against every mask (and keep portal
     paths from walking through them). Drop a mask rather than kill a
     declared sightline.
   - Keep the half-prop cover count per region close to the previous
     file (cover density feeds the balance gate); reposition them onto
     the real map's crates/boxes. Keep the map's signature full-height
     sight blockers (e.g. Ascent's mid box) crossing the same
     center-lines as before.
   - Elevated rooms keep their `z` (heaven-style perches).
   - **Record doorways while tracing** (`openings:` in the geometry
     YAML): for every seam that is wall-with-a-doorway on the minimap
     (door arcs, necks, gates), declare
     `- { between: [a, b], span: [lo, hi] }` with the doorway's real
     extent along the seam's long axis. The portal moves to the
     doorway's center; undeclared seams stay fully open (plaza edges).
     The audit enforces: span inside the shared seam interval, regions
     exist, pair adjacent, no duplicates. Every mechanical-door gimmick
     edge MUST have an opening (`tests/test_map_openings.py` pins this
     for traced maps). These spans are also the source for the future
     free-roam wall derivation, so capture them even on corridor edges'
     seams where they don't move the portal.
4. **Verify registration.**
   `... wiki_map_trace.py overlay data\maps\geometry\<id>.yaml <scratch>\<id>_grid.png <scratch>\<id>_check.png`
   View it: blue rects on floor, red masks on void, green cover on real
   crates. Iterate until it reads one-for-one.
5. **Gates, in order** (all from repo root; worktrees need
   `$env:PYTHONPATH=(Resolve-Path 'src').Path` and the primary
   checkout's `.venv-win`):
   - `scripts\map_floor_audit.py` -> exit 0.
   - `scripts\pacing_report.py`: a faithful trace usually walks TOO
     FAST because rect-center paths shortcut the real doglegged lanes.
     Fix by adding corridors whose `via` waypoints trace the real
     walking lanes (spawn-plaza traverses, hall runs, necks) until the
     attacker rotate is 25-35s with stages 8-18s — never by inflating
     rects off the floor. Defender rotate must stay strictly faster.
     Note the BFS in the report picks fewest-hops routes in adjacency
     order: check WHICH route carries each stage before lengthening.
   - Flip `movement_model: free` in `data/maps/<id>.yaml` before the
     balance run — a traced map with openings qualifies for the
     free-movement resolver (docs/free-movement-engine.md), and the
     balance number must be measured under the flag that ships.
   - `scripts\balance_report.py 300 --maps <id>` (45-65% attack, aim
     52-60). Traced maps land defense-leaning (~45-53%) until the
     weapon-range retune lands — real-scale rooms compress duel
     ranges. Working levers, in order tried: kill physically-false
     defense-advantaged sightlines; deepen the defender-spawn rect so
     retakes muster further back (bind's vase); soften heaven `z` to
     ~4-5 (z 6 made split's retake angles oppressive); widen site-door
     openings to their real spans. Don't distort plate positions.
   - `scripts\regen_golden.py` — intentional drift, re-bless both
     fixtures in the same commit.
   - `scripts\render_map_guide.py --map <id>`, then
     `pytest -q -m "golden or engine"`.
6. **Flag the paint.** The painted backdrop
   (`assets/maps/painted/<id>.webp`) is fully stale after a trace —
   repaint via `/art-pass` (then `render_map_thumbs.py`), or say so in
   the handoff if the repaint is batched for later.

## Traps hit across the five traces

- The rotation is about where the SITES and spawn masses are, not
  compass labels; verify with the plant-zone pins before tracing.
- `mid_market`-style connector rooms often need their rect stretched
  along the connecting lane so the corridor to spawn stays on plates.
- Editing the compiled YAML directly is fine here (Studio synthesizes
  its documents from compiled files), but never hand-edit while a Map
  Studio UI session is open on the same map.
- Do NOT edit these YAMLs with PowerShell string tools (mojibake +
  BOM); use the Edit tool. (`[System.IO.File]::ReadAllText/WriteAllText`
  with regex anchor rewrites is the one proven exception.)
- ALWAYS set `$env:PYTHONPATH=(Resolve-Path 'src').Path` in EVERY
  shell call when working from a worktree: without it the primary
  checkout's editable install silently supplies BOTH code and data
  (`DEFAULT_DATA_DIR` is package-relative), and every gate runs
  against the wrong tree. This poisoned a whole gate cycle + golden
  bless once — pytest (worktree-rooted) disagreeing with the scripts
  is the tell.
- Region centers land inside masks on big L-rooms (bind's spawn,
  split's a_main). Sight_distance and hop paths use centers, so
  notch the masks around any declared sightline's center-to-center
  segment instead of accepting a dead read; leaving small void
  slivers unmasked is fine (paint hides them).
- The pacing gate's entry per site is the FIRST SORTED attacker/mid
  neighbor of the site room, and defenders may legally route through
  teleporters (bind's def rotate rides the Hookah TP). Check which
  rooms actually carry each measured number before tuning.
- A stray bright pixel can hijack the crop box — the grid command
  uses percentile bounds now; if a crop looks half-void, that fix
  regressed.
