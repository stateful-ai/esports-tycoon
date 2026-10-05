# Real-layout Studio drafts

Eleven editable map sources are available in `data/maps/studio/`. The six added
on 2026-10-04 are Pearl, Fracture, Corrode, Abyss, Breeze, and Sunset. Open
`http://127.0.0.1:8421/map-studio.html?map=pearl-layout-v2` and select a draft in
the library. The existing Ascent, Bind, Haven, Lotus, and Split sources were
restored without changing their prior revision hashes.

These are structural drafts. They have valid connected geometry, measured floor
footprints, source callouts, navigation routes, and plant overlays. They are not
promoted runtime maps, and the new six still need cover, vertical mechanics, and
gameplay tuning. No live map artifacts or golden fixtures were replaced.

## Six new sources

| Map | Studio source | Rooms | Active links | Recorded links | Floor extensions | Plant overlays | Floor IoU |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pearl | [pearl-layout-v2.yaml](../data/maps/studio/pearl-layout-v2.yaml) | 25 | 37 | 0 | 554 | 2 | 95.32% |
| Fracture | [fracture-layout-v2.yaml](../data/maps/studio/fracture-layout-v2.yaml) | 22 | 33 | 2 | 531 | 2 | 94.22% |
| Corrode | [corrode-layout-v2.yaml](../data/maps/studio/corrode-layout-v2.yaml) | 21 | 32 | 0 | 399 | 2 | 94.71% |
| Abyss | [abyss-layout-v2.yaml](../data/maps/studio/abyss-layout-v2.yaml) | 23 | 33 | 0 | 481 | 2 | 93.96% |
| Breeze | [breeze-layout-v2.yaml](../data/maps/studio/breeze-layout-v2.yaml) | 23 | 36 | 0 | 616 | 3 | 95.47% |
| Sunset | [sunset-layout-v2.yaml](../data/maps/studio/sunset-layout-v2.yaml) | 17 | 27 | 0 | 419 | 3 | 94.29% |

IoU compares the physical floor union with a classified source image on a
0.25-map-unit grid. Authoring uses a separate 0.5-unit grid. This measures the
approximate minimap floor footprint, not overall map accuracy, collision
meshes, crates, or vertical layers.

Prior sources: [Ascent](../data/maps/studio/ascent-layout-v2.yaml),
[Bind](../data/maps/studio/bind-layout-v2.yaml),
[Haven](../data/maps/studio/haven-layout-v2.yaml),
[Lotus](../data/maps/studio/lotus-layout-v2.yaml), and
[Split](../data/maps/studio/split-layout-v2.yaml).

## Provenance and coordinate frame

The six traces use the unannotated minimap images and world-space callout
coordinates from the [Valorant API map snapshot](https://valorant-api.com/v1/maps)
retrieved on 2026-10-04. This community API exposes extracted game assets; it is
not Riot's public developer API. Riot's [map page](https://playvalorant.com/en-us/maps/)
was also checked for the map identities and Corrode overview.

`assets/maps/references/<map>-source.png` preserves each original image.
`<map>-source.json` retains its SHA-256, asset URL, complete original callouts,
world-to-image transform, orientation, merged callouts, and omitted disconnected
floor areas. `<map>.png` is the canonically oriented source image used by Studio.

API world coordinates are in centimetres. Source image coordinates are
`u = location.y * xMultiplier + xScalarToAdd` and
`v = location.x * yMultiplier + yScalarToAdd`. Pearl, Fracture, Breeze, and Sunset
rotate 180 degrees; Corrode and Abyss rotate counterclockwise. The resulting
image coordinates are multiplied by 100. Attackers appear at the bottom,
defenders at the top, A on the left, and B on the right. Map units are normalized
to the image; one map unit is not necessarily one metre.

Gray and olive floor pixels are classified, white wall markings are excluded,
and the main connected component is traced. Small isolated fragments are
excluded with their areas recorded in the source manifest. Floor ownership is
partitioned by distance along the walkable mask from source callouts. Each
room has a core rectangle centered on its callout plus rectangular extensions
for the remainder of its physical floor. Navigation routes stay within the two
adjacent floor owners; diagonal shortcuts check every crossed grid cell.

Plant shapes are semantic overlays over existing floor pieces. A plant overlay
may reference several neighboring surfaces when its source contour spans a
site, bridge, or dugout. It does not add walkable floor or change room ownership.

## Editor workflow

1. Select a `Layout v2` draft. Its URL now follows library selection, so reload
   reopens the selected map.
2. Use **Focus Canvas**, **Outlines**, and **Reference** to compare source floor
   boundaries. **Routes** reveals navigational links; **Compare Floor** marks
   missing floor green and extra floor red, with a 0.25-unit comparison.
3. Use **Room Rectangle** to create a room and callout together. Select a room
   and use **Floor Extension** for bends and concave sections. Union outlines
   remove internal rectangle seams while retaining holes and external edges.
4. Use **Wall** for solid blockers and **Prop** for surveyed cover. Plant zones
   remain overlays rather than duplicate rooms. Select a traversal to give it a
   description or mark it **Recorded only** when its mechanic is unsupported.
5. **Validate** checks geometry, containment, and reachability. **Probe** checks
   floor membership, collision, and sightlines. **Test Round** runs a disposable
   match on the current draft and plays its first round; seed 1167 was verified
   in the Pearl UI.
6. **Save Draft** persists source revisions. Concurrent clean drafts reload;
   unsaved edits show an external-change warning. MCP mutations require the
   current revision hash and must reconcile a conflict before retrying.

## Reproducible authoring and verification

Run from the repository root with `src` on `PYTHONPATH` and the project Python
environment. Required Python dependencies are declared in `pyproject.toml`.

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
python scripts/build_additional_layouts.py
python scripts/check_layout_drafts.py --matches 300 --maps pearl fracture corrode abyss breeze sunset --output-dir runs/layout-review/additional-maps
python -m pytest -q -m 'golden or engine'
python -m pytest -q -m 'web or registry'
python -m pytest -q -n0 tests/test_layout_authoring.py tests/test_map_studio.py tests/test_map_mcp.py
node --test tests/stress_test_map_studio_frontend.js
node --test tests/test_map_authoring_frontend.js
```

The generator uses the stdio `esports-maps` MCP schema, typed patches, and
compare-and-swap revisions. It preserves existing drafts by default. Explicit
`--maps <name> --refine-generated` is allowed only when a draft still matches its
last generated revision. Original assets are reused offline and their pinned
SHA-256 is checked; modified images are not silently accepted as the source.

The gate script compiles to a disposable data directory, checks spawn/site/plant
probes and all adjacent holding-slot routes, then runs the actual floor, pacing,
and balance scripts. Its report records the tested source revisions, compiled
fingerprints, and simulation-code fingerprint. A concurrent gameplay edit
invalidates the run. Publishing requires a separate explicit request.

The fixed-geometry movement resolver indexes floor pieces and caches repeated
visibility checks per match, including door state in each cache key. Engine and
golden tests passed (141), as did authoring/MCP tests (61), the nine frontend
stress cases, floor-outline union tests, and web/registry tests (327). These
selections overlap; their counts are not a combined unique test total.
A seed-1167 Pearl test also verified
that cached and uncached complete event logs match.

## Current limitations

- The six new maps have no surveyed crate/cover prop set. Minimap outlines do
  not establish precise crate height or collision behavior.
- Callout elevations are coarse flat layers derived from API z coordinates.
  Ramps and vertical overlap are not reconstructed. Pearl's co-located Mid Shops
  and B Club are merged into one physical room, with both source labels retained.
- Fracture's two central zipline cables have measured docking positions and
  descriptions, but are recorded only. They do not become a walkable bridge or
  teleport route. Other scripted doors and motion mechanics are not replicated.
- Abyss void is excluded from the floor. Death drops, jumps across gaps, and
  isolated danger ledges are not implemented by the runtime.
- The runtime uses site callouts for planting; the detailed plant overlay is
  retained for authoring and does not enforce exact plant legality during a match.
- API callout labels are not surveyed player spawn positions. Labels snapped to
  the nearest physical floor can sit close to a floor edge. Probes resolve all
  spawn/site/plant anchors to floor, but minimum own-surface clearance is 0.25
  units on Pearl, Abyss, and Sunset. Revisit actor clearance and spawn volumes
  before promotion; floor membership alone does not establish a safe body fit.
- Pacing uses graph routes at the simulator's existing normalized movement
  speed. Targets are attacker spawn-to-entry 8â€“18 seconds and attacker rotate
  through spawn 25â€“35 seconds. Several faithful source traces miss those
  targets. Footprints were not stretched to make this benchmark green.

## Validation results

The [review JSON](additional-map-layout-review.json) records source revisions,
compiled SHA-256 values, simulation-code SHA-256, probe findings, counts, and the
complete gate output. Each map was simulated for 300 matches (seeds 0â€“299), with
Team Nexus against Team Vanguard. All maps produced elimination, detonation,
and defuse round endings, but none met the 45â€“65% attacker-round win band.

| Map | Floor | Holding routes checked | A entry | B entry | Attacker rotate | Defender rotate | Pacing | Attacker wins | Balance |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| Pearl | Pass | 1,412 | 20.4s | 13.1s | 33.5s | 25.4s | Fail: A entry | 42.7% | Fail |
| Fracture | Pass | 1,442 | 8.8s | 7.5s | 16.3s | 15.6s | Fail: B entry, rotate | 32.6% | Fail |
| Corrode | Pass | 1,602 | 13.8s | 8.7s | 22.5s | 20.8s | Fail: rotate | 40.1% | Fail |
| Abyss | Pass | 1,342 | 7.7s | 17.2s | 24.9s | 24.4s | Fail: A entry, rotate | 33.3% | Fail |
| Breeze | Pass | 1,366 | 13.4s | 15.0s | 28.4s | 22.5s | Pass | 33.1% | Fail |
| Sunset | Pass | 968 | 13.6s | 7.4s | 21.0s | 21.2s | Fail: B entry, rotate | 23.8% | Fail |

All 8,132 holding-slot routes stayed on their two adjacent physical floor
owners, with no solid-wall hits. All 38 spawn/site/plant probes resolve to floor
and the plant overlays are reachable. Pacing values are the report's graph
measurements; defender times are reported for comparison, without a separate
defender-time gate. Percentages and times above are rounded report values.

The geometry is ready for continued authoring, while runtime promotion remains
blocked by the gameplay gates. Add source-backed cover, review spawn/entry
roles and player clearance, implement unsupported traversal, and tune the
simulator's handling of these layouts before running the sweep again. Do not
change the reference footprint solely to satisfy a pacing or balance metric.

Before committing this authoring work, the full suite passed: **1,022 tests**.
The five live maps also passed floor, pacing, and 300-match balance gates:
Ascent 55.6%, Bind 49.5%, Haven 51.9%, Lotus 56.0%, and Split 50.1% attacker
round wins. The six new maps retain the draft tuning results above.

## Keep the PC awake

`scripts/map_keep_awake.ps1` runs separately from the game and requests Windows
display, system, and execution activity. It renews a heartbeat every 30 seconds
in `runs/layout-review/codex-map-awake.status.json`. The helper was verified active
after the new map work. To stop it without changing persistent power settings,
create `runs/layout-review/codex-map-awake.stop`. Remove or rename that marker
before launching the helper again.
