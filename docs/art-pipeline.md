# Art pipeline — blockout → beautify

How this game turns interaction geometry into painted scenes without the
art and the hotspots ever drifting apart. Proven on the office (v3 + v2
style pass); designed to be reused for map scenes next.

## The core problem

AI image generation gives you either **beauty without structure** (txt2img:
gorgeous, but rooms land wherever) or **structure without beauty**
(img2img at high fidelity: preserves your blockout's *sparseness* along
with its layout). Click targets, facility states, and future character
anchors all need the geometry to be authoritative — so beauty has to be
generated *onto* the structure, not instead of it.

## The recipe

```
plan (JSON, single source of truth)
  └─ guide renderer (PIL) → flat semantic blockouts (base + state variants)
       └─ SINGLE-IMAGE EDIT of the guide, style described ENTIRELY IN TEXT
          (Gemini/nano-banana or Ludo editImage), with a block legend:
          "cyan slabs = glowing monitor arrays, brown = wooden tables, …"
            └─ STRUCTURE GATE: footprint-IoU vs guide (accept ≥ 0.90;
               expect a reject/retry loop — structure survival is
               probabilistic on every tool tested)
                 └─ COMPOSITE: state variants pasted as diff-region
                    patches over the accepted base (feathered diff mask)
                    — the shared scene stays pixel-identical across files
                      └─ runtime: painted image + transparent SVG hotspot
                         polygons from the SAME plan/projection
```

Key separations — updated after the v2 style pass (2026-07-08):
- **Structure lives in the guide.** Rooms, walls, furniture *positions*,
  encoded as flat color-coded blocks on a dark background.
- **Appearance lives in TEXT, not in a reference image.** The tested
  two-image approach ("repaint image 1 in the style of image 2")
  **failed 4/4 on Gemini** — the model clones the style image's
  COMPOSITION and throws the layout away, and no prompt strengthening
  fixed it. What works: a single-image edit of the guide with the style
  written out in exhaustive prose (materials per room, lighting, clutter,
  wear) plus the block legend. Style-reference images are still worth
  generating — as taste calibration and as LoRA training seeds — they
  just must never be passed into the edit call.
- **States are composites, not regenerations.** One accepted base; each
  facility/level variant contributes only its own masked region. No
  combinatorial explosion, no cross-file drift. (Shift-alignment before
  compositing can HURT when glow pixels bias the mask — try the plain
  resize first.)
- Cross-tool style continuity works: when Gemini hit its monthly cap
  mid-run, Ludo editImage with `reference_image` = the accepted painted
  base finished the annex variants seamlessly (reference images are safe
  THERE because the diff-mask composite discards everything outside the
  annex region anyway).
- **Never ask the paint for boundary lines.** The footprint gate can't
  hold interior lines in place (they drift even when the silhouette
  passes), and hover hotspots expose every pixel of disagreement. Rule:
  prompt scenes WITHOUT floor/boundary LED strips or wall outlines; the
  runtime draws authoritative borders as a vector overlay from the same
  plan geometry as the hotspots (see office.js painted mode). Paint =
  texture, furniture, mood. Vectors = anything that must align. A small
  global drift can additionally be corrected once with
  `scripts/align_painted.py` (mask-based scale/shift estimate).

The winning verbatim prompts (style ref, base repaint, annex variant)
live in the v2 pass report and in `assets/office/style/`; the base
repaint prompt's spine is reusable for any scene:
"Repaint this isometric floor-plan blockout into a finished, richly
detailed stylized 3D render … CRITICAL — preserve the layout exactly …
Interpret the blocks: … Make it RICH: per-room floor materials, LED
boundary strips, plants, cable clutter, glowing light pools … No text,
no logos, no people."

## Stage 2 — sprite decomposition (office v4, owner-directed 2026-07-08)

Whole-scene repaints hit a ceiling: even gated, beauty-selected bases
put *some* furniture in the wrong room or at loose anchors, because one
generation is being asked to solve layout + placement + style at once.
The fix is to stop asking for placement at all:

- **Shell**: ONE furniture-free repaint of the all-rooms guide
  (`render_office_guide.py --shell` → `guides/shell.png` →
  `painted/shell.webp`). Only the silhouette needs to survive — the
  easiest possible gate — and the whole multi-file state set collapses
  to one image (the runtime's silhouette clip reveals built annexes).
- **Sprites**: each furniture type generated once as an isolated
  isometric object on a transparent background
  (`office_sprites.json` manifest → `assets/office/sprites/
  <type>_<orient>.webp`). Placement is the PLAN's job at runtime:
  bottom-center anchored on the footprint diamond's front vertex,
  width = projected footprint extent × manifest scale, z-sorted by
  screen-y (painter's algorithm). Furniture *cannot* drift.
- **Lighting coherence** across shell + sprites comes from the shared
  `style_lock` phrase: fixed upper-left light, baked soft under-shadow
  on every sprite, cool-ambient/warm-accent grade; the eventual LoRA
  hardens this further.
- **Orientation economy**: generate `se` only; `sw` is a horizontal
  mirror (PIL) — the iso projection makes a mirrored along-x object
  read as along-y. Abstract screen content mirrors safely.
- This layer split is exactly the PixiJS handoff shape: shell =
  background sprite, furniture = display objects characters can pass
  behind/in front of.
- **Validated sprite chain (v4 pass, 2026-07-08)**: Ludo createImage
  insists on painting a diorama tile base under isolated objects
  (prompt negations ignored; creative rembg won't strip it). Working
  chain: Ludo createImage (style) → Gemini flash-image edit "delete
  the base/extra object, plain white background" (surgical) → Ludo
  removeBackground (`creative_edit=false`) → PIL trim + shadow + gates
  (perimeter alpha ≥ 90% clear, coverage 15–92%, short side ≥ 256 px).
  Shell prompt traps: "lamplight" bait-paints literal lanterns and
  "floor markings" bait-paints glyph text — say "light from unseen
  sources above the frame" instead. Reusable scripts from the pass:
  scratchpad `gen_shell.py` / `sprites.py` / `gemini_edit.py`.
- **Characters (v4.2 pass)**: people work in the same chain, and the
  occlusion problem is solved by GENERATION, not layering — a seated
  character is one combined "player at desk" sprite that swaps in for
  the empty-desk sprite (aspect matched desk_se within 0.02, scale
  stays identical). Lessons: (1) append "exactly ONE person with one
  head and two arms" — 6/6 single-subject raws first try; (2) new
  rembg failure mode: it can keep an OPAQUE white background blob that
  alpha gates can't see — deterministic fix is flood-filling the
  debased PNG's near-white background from the borders and zeroing
  those pixels in the rembg alpha (enclosed whites + shadows survive);
  (3) Gemini debase is stochastic (~1/7 leaves the tile slab), so the
  dark-background visual composite check is mandatory, numeric gates
  alone are not enough.
- **Placement tuning loop**: `scripts/render_sprite_office.py` mirrors
  office.js placement math and composes shell+sprites offline — judge
  layout/scale changes from its PNG instead of fighting flaky browser
  screenshots. Lessons from the first pass: z-sort by footprint CENTER
  (front-vertex sorting lets wide tables leapfrog their chairs); tune
  per-type scale against measured sprite aspect (portrait sprites
  explode under width-only scaling); wall pieces go on BACK edges (high
  y, or low x mirrored); don't pair standalone monitor sprites with
  desks whose art already includes monitors.

Facility-state diff compositing (above) remains the fallback path for
whole-scene sets and is still the right tool for map door/teleporter
state patches.

## Agent icon pass — COMPLETE (2026-07-18)

The authored agent registry contains 29 agents and the runtime resolves icons
by the stable path `assets/agents/<agent-id>.webp`. The missing 16 portraits
were generated through the Ludo MCP `generateWithStyle` tool using the
committed Jett portrait as the style reference, with per-agent prompts derived
from `data/agents.yaml`. Each result was downloaded immediately because Ludo
asset URLs expire after seven days. The final local pack contains one square
portrait for every registry id; `tests/test_agent_icons.py` keeps the asset
contract from regressing.

## Scenario LoRA — TRAINED (2026-07-09)

Model `model_5ZuAoQQnRSMSeykEwaHjBKwm` ("esports-sim-diorama",
`flux.2-dev-lora`, trigger `esports-sim-diorama`, concept scale 0.8)
is trained on the full 16-image style corpus (6 office scenes +
5 painted maps + 5 map alts). Use it for future volume generation so
new scenes inherit the locked style by default.

Caveat: API generation against the trained model currently 500s on
both `/models/<id>/inferences` and `/generate/txt2img` (legacy paths
apparently don't serve flux.2 LoRAs on this plan) — generate from the
Scenario web UI, or research the current-generation endpoint before
the next volume pass. Details: `assets/office/style/lora/STATUS.md`.

Validated API recipe (Basic auth `key:secret`, api.cloud.scenario.com):
1. `GET /v1/models?pageSize=100` — duplicate check first.
2. `POST /v1/models?projectId=<proj>` `{"name","type":"flux.2-dev-lora"}`.
3. Per image `POST /v1/models/<id>/training-images?projectId=<proj>`
   `{"name","data":"data:image/png;base64,..."}` (short side >= 1024).
   A `caption` field here is SILENTLY IGNORED.
4. Captions live on the asset: `PUT /v1/assets/<assetId>` with
   `{"description": "<caption>"}`.
5. `PUT /v1/models/<id>/train` with Scenario-default parameters;
   `conceptPrompt` max 20 chars; `GET .../training-images` is 403 for
   API keys, so keep asset ids from the upload responses.
6. Poll `GET /v1/models/<id>` until `trained`.

## Credit strategy (owner-set, 2026-07-08)

1. **Iterate on cheap/abundant tools**: Gemini image edits + Imagen for
   style refs (Google AI Studio key), Ludo for typed assets. Scenario
   credits are NOT for iteration.
2. **Lock the style with a Scenario LoRA** once a scene set is accepted:
   train on `assets/office/style/` + accepted finals. The LoRA then makes
   every future scene stylistically consistent by default.
3. **Volume generation through the LoRA** (maps, loading screens,
   marketing shots), topping up credits only once the style is locked.

## Tool notes (validated)

| Tool | Role | Gotchas |
|---|---|---|
| Gemini `edit_image` (nano-banana) | anchored two-image edits | best structure-instruction following tested; still gate with IoU |
| Imagen 4 / Gemini `generate_image` | style references | unconstrained on purpose |
| Ludo `editImage` | fallback repainter | structure survival ~1/11 — always gate |
| Scenario REST | LoRA training + volume gen | team models only via /models; base models by id (`flux.1-dev`) |
| `scripts/render_office_guide.py` | guide rasterizer | bounds math must match `officeWorldRect()` in office.js exactly |
| scratchpad `structcheck.py` / `composite.py` | gate + composite | promoted here if they harden further |

## Maps (SHIPPED — v1 pass, 2026-07-09)

All five maps are painted and live in the viewer. The working chain:

- `scripts/render_map_guide.py` rasterizes every map at the viewer's
  exact transform (viewBox −110 −12 220 128 at 8 px/unit → 1760×1024;
  constants documented in the script). `viewer.js` probes
  `assets/maps/painted/<map>.webp` and layers it pixel-true as the
  bottom SVG layer; geometry becomes whisper-level glass (floors ~7%,
  props ~16%) so paint shows and the vector borders stay authoritative.
- Style: `assets/maps/style/briefs.md` — shared broadcast-diorama spine
  + per-map paragraphs distilled from real-map references (text only).
  Winning verbatim prompts per map: `assets/maps/style/candidates/
  prompts/`.
- Results: IoU 0.972–0.996, ~2–7 generations per map, all Gemini
  flash-image wins. **Ludo editImage is wrong for map guides** (2/2
  re-imagined the layout as a glyph-covered diorama) — Gemini is the
  map repaint tool; the office-shell Ludo win did not transfer.
- Map-specific prompt rules that earned their place:
  - Tinted plates get literally preserved unless told "Repaint EVERY
    plate, including the colored ones: no plate may remain a flat
    untextured color slab" + one material sentence per zone tint.
  - The seam rule: structures may stand ONLY along plate borders facing
    the dark void — never mid-plate, never on a seam where two plates
    touch; every touching seam is an open walkway (the sim walks
    players through there).
  - Theme priors beat bans (monastery ⇒ courtyard walls 5/5, temple ⇒
    water pools 3/4 despite "never water"): don't re-roll — plan for
    **crop surgery**: crop the flawed region with margin → edit the
    crop → per-channel mean/std color-transfer (Gemini regrades crops)
    → feathered whole-crop paste. Whole-image "remove X" edits destroy
    complex dioramas, and diff-region masks fail (Gemini re-frames
    crops by a few percent).
  - The deterministic outside-mask (carve everything outside the guide
    footprint back to ground navy with PIL) is load-bearing: it fixes
    void spill for free and severs paint bridging separated plates.
  - Gate = IoU ≥ 0.86 **+ void-spill metric ≤ ~0.15 + a 50%-blend
    overlay eyeball** — full-bleed repaints can fake IoU after masking,
    and the overlay catches composition failures the numbers miss.
  - Gemini returns 1344×768 for 1760×1024 input; LANCZOS upscale back
    is fine (post-resize IoUs 0.94–0.996).
- States: maps are static — one painted webp per map. Doors/teleporters
  could get small state patches later using the office annex technique.
- Reusable scripts from the pass (scratchpad): `map_gate.py` (gate +
  spill + overlay + outside-mask), `croppaste.py` (surgical edits).

## Map floor contract (v2 repaint, 2026-07-09)

The paint can only be walked on if the GEOMETRY is walkable art:
`scripts/map_floor_audit.py` is now a permanent gate — every adjacency
pair's plates must touch, every callout center sits on its own plate,
every path polyline stays on the plate union (teleporter edges exempt:
players beam, never walk). When plates CONNECT in a geometry fix,
re-audit the briefs' flavor lines: props that were legal on
void-facing walls become seam-blockers (lotus's B-site mural painted
onto the newly live spawn seam 4/4 until reworded to decorate the
elevation drop instead). Repaint lessons: strip surgery (tight band on
the offending wall, floors as slivers) beats whole-courtyard edits 3/3
vs 0/3 on haven; scene-framing ("a flat teal stone floor") succeeds
where change-requests ("drain the pool") fail; one surgical goal per
Gemini call on dense dioramas; per-channel mean/std color transfer
before every crop paste (scratchpad colorxfer.py).

## Word on engines (owner decision log)

No game engine adoption for now. The office/PixiJS trigger: when
characters walk and interact, embed **PixiJS for the office scene only**
— painted scene as background sprite, `office_plan.json` provides walk
floors and `desk_anchors` seats. The web app, sim, and API contract stay
as they are.
