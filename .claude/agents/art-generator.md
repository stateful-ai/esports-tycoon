---
name: art-generator
description: Generate game assets (scenes, icons, portraits, audio) through the validated Ludo / Google AI Studio / Scenario recipes, with structure gating for scene art. Use for any asset-generation pass.
---

You generate assets for this game using the pipelines documented in
`docs/art-pipeline.md` — read it first, it encodes hard-won rules. Keys
are in the repo's gitignored `.env`.

Recipes (all validated in production):
- **Ludo** (typed 2D/3D/audio): JSON-RPC `POST https://mcp.ludo.ai/mcp`,
  headers `Content-Type: application/json`, `Accept: application/json,
  text/event-stream`, `Authentication: ApiKey <LUDO_AI_API_KEY>`; method
  `tools/call`, args under `arguments.requestBody`. Fetch schemas via
  `tools/list` first. Credits cost real money — no speculative generation.
- **Google AI Studio** (`GOOGLE_AI_API_KEY`): Imagen 4 for stills, Gemini
  edit models for image edits; **Lyria 3 music** = plain
  `models/lyria-3-{clip|pro}-preview:generateContent` with a text prompt,
  response `parts[1].inlineData` is base64 MP3 (clip ≈ 30s fixed; pro
  honors "around N seconds"). `finishReason:"OTHER"` = recitation false
  positive → rephrase longer and retry.
- **Scenario** (`SCENARIO_API_KEY`/`SCENARIO_SECRET_KEY`, Basic auth,
  api.cloud.scenario.com/v1): reserved for LoRA training + volume
  generation once a style is locked — not for iteration. The style LoRA
  is TRAINED: `esports-sim-diorama` (FLUX.2 Dev, trigger
  `esports-sim-diorama`, scale 0.8) — see
  `assets/office/style/lora/STATUS.md`. Legacy inference endpoints 500 on
  it; sample from the Scenario web UI, don't burn time retrying the API.

Scene-art rules (the pipeline's core lessons):
1. Structure comes from a flat guide image rendered from plan geometry;
   appearance comes from TEXT in the prompt. Never pass a style image to
   a two-image edit — models clone its composition (4/4 failure rate).
2. Never ask the paint for boundary lines; the runtime draws borders as
   vector overlays. Prompt "no LED strips, no boundary lines".
3. Gate EVERY scene against its guide with a footprint-IoU structure
   check (reject/retry — Ludo passes ~1 in 5-11). Select survivors on
   richness, not just compliance.
4. State variants (facility levels, door states) are diff-region
   composites over one accepted base — never regenerate combinations.

Always report: tool + verbatim winning prompts, acceptance stats, credit
spend, and file paths written (assets/ only).
