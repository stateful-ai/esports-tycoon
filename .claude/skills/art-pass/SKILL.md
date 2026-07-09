---
name: art-pass
description: Run a scene-art generation pass through the blockout→beautify pipeline (guides, prompts, structure gates, compositing). Use when generating or regenerating office/map scene art.
---

# Art pass

Full background: `docs/art-pipeline.md`. Condensed runbook (office/scene
first; map-specific deltas at the end):

1. **Guide**: rasterize the plan geometry flat — semantic block colors,
   alternating floor tones for zones, **no outlines or boundary lines**
   (the runtime draws borders as vectors; lines in guides get imitated
   and drift). Office: `scripts\render_office_guide.py`.
2. **Generate**: single-image edit of the guide with the style described
   entirely in TEXT (never a style image in a two-image edit — models
   clone its composition). Include the block legend (cyan = monitors,
   brown = tables, …) and "no LED strips, no boundary lines, no text".
   Iterate on cheap tools (Ludo editImage / Gemini when budget allows);
   Scenario credits are for LoRA training + volume, not iteration.
3. **Gate**: footprint-IoU vs the guide (scratchpad `structcheck.py`
   pattern; office threshold 0.86 now that vectors own edges). Expect
   ~1-in-5 acceptance; among survivors select on RICHNESS by looking at
   them. Keep runners-up in `assets/office/style/candidates/`.
4. **States**: composite variants as diff-region patches over the one
   accepted base (`composite.py` pattern) — never regenerate state
   combinations. For the OFFICE, prefer sprite decomposition instead
   (art-pipeline.md "Stage 2"): one furniture-free shell
   (`render_office_guide.py --shell`) + per-type transparent sprites
   from `office_sprites.json`; placement/z-sort is the runtime's job,
   so furniture cannot drift and no state files exist at all.
5. **Align**: if hover outlines look off, `scripts\align_painted.py`
   estimates/applies a one-time global scale/shift.
6. **Verify in the browser** (hotspot hover on top of painted rooms),
   then ship via the `ship` skill. Save accepted finals + prompt.txt to
   `assets/office/style/`. The style LoRA is TRAINED
   (`esports-sim-diorama`, Scenario/FLUX.2 Dev, trigger word
   `esports-sim-diorama` @ 0.8) — see `assets/office/style/lora/STATUS.md`;
   API inference 500s on legacy endpoints, sample from the web UI.

## Map backdrops (deltas from the office recipe)

Structure guides come from `scripts\render_map_guide.py` (viewer-transform
exact — see the map floor contract in `docs/art-pipeline.md`); briefs +
winning prompts live in `assets/maps/style/`. Lessons that differ from the
office:

- **Full-scene Gemini edits only** — Ludo re-imagines map layouts (0/N
  usable). Scene-framing prompts ("a flat teal stone floor") succeed where
  change-requests ("drain the pool") fail; ONE surgical goal per call.
- **Gate**: footprint IoU ≥ 0.86 + outside-spill ≤ 0.15, then a 50%-blend
  overlay eyeball per seam. After a LOCALIZED geometry fix, IoU alone will
  pass stale paint — the per-seam overlay read is the real detector.
- **Deterministic cleanup**: mask everything outside the footprint back to
  the guide ground color (9,11,17); per-channel mean/std color transfer
  before pasting any crop; strip surgery (a tight band on the offending
  wall) beats whole-courtyard edits for stubborn priors.
- **After accepting**: write to `assets/maps/painted/<map>.webp`, regen
  thumbs via `scripts\render_map_thumbs.py`, and verify in the viewer at
  the pinned backdrop transform.
