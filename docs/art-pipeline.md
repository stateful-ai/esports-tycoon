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

The winning verbatim prompts (style ref, base repaint, annex variant)
live in the v2 pass report and in `assets/office/style/`; the base
repaint prompt's spine is reusable for any scene:
"Repaint this isometric floor-plan blockout into a finished, richly
detailed stylized 3D render … CRITICAL — preserve the layout exactly …
Interpret the blocks: … Make it RICH: per-room floor materials, LED
boundary strips, plants, cable clutter, glowing light pools … No text,
no logos, no people."

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

## Applying it to maps (next target)

The match maps already have everything the office had: floor-plan
geometry (`data/maps/geometry/*.yaml` — rooms, props, elevation) and an
iso projection shared with the viewer. Plan:

1. Guide renderer variant for maps: rasterize map geometry (floors,
   walls, crates, site tint, elevation shadows) at the viewer's exact
   viewBox transform.
2. Style ref per map theme (haven monastery, bind desert domes, …) —
   one shared "broadcast map diorama" base style + per-map palette.
3. Anchored edit + IoU gate as above. The painted map becomes a backdrop
   `<image>` under the viewer's existing dynamic layers (players,
   utility, spike are already SVG on top).
4. States: maps are static (no variants), so no compositing needed —
   one painted image per map. Doors/teleporters could get small state
   patches later using the office annex technique.

## Word on engines (owner decision log)

No game engine adoption for now. The office/PixiJS trigger: when
characters walk and interact, embed **PixiJS for the office scene only**
— painted scene as background sprite, `office_plan.json` provides walk
floors and `desk_anchors` seats. The web app, sim, and API contract stay
as they are.
