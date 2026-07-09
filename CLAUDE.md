# esports-sim — Claude Code project guide

Valorant-inspired esports manager: deterministic tick-level match engine,
multi-region VCT campaign layer, FastAPI web UI, AI-generated art/audio.
Published at github.com/stateful-ai/esports-tycoon.

## Environment (Windows)

- **Python venv: `.venv-win\Scripts\python.exe`** — never `.venv/`
  (that's a WSL venv, unusable on Windows). Python ≥3.12.
- Install: `.venv-win\Scripts\python.exe -m pip install -e ".[dev,web]"`
- Run web app: `python -m esports_sim --web` (port 8420; `.claude/launch.json`
  has the preview config "web"). Headless: `--auto N --seed S --team T`.
- Generation keys live in `.env` (gitignored): `LUDO_AI_API_KEY`,
  `SCENARIO_API_KEY` + `SCENARIO_SECRET_KEY` (Basic auth), `GOOGLE_AI_API_KEY`
  (Imagen/Lyria/Veo via generativelanguage.googleapis.com). Never commit it.

## Commands

| What | Command |
|---|---|
| Tests | `.venv-win\Scripts\python.exe -m pytest -q` |
| Balance gate (45–65% attack band) | `... scripts\balance_report.py 300` (exit 1 = fail) |
| Rotation pacing gate (25–35s via spawn, 8–18s spawn→entry) | `... scripts\pacing_report.py` (exit 1 = fail) |
| Multi-season snowball gate (blowout/close band) | `... scripts\snowball_report.py` (exit 1 = fail) |
| Tactics-dial sweep gate (each numeric dial at its poles) | `... scripts\tactics_report.py` (exit 1 = fail) |
| Map floor gate (plates touch; callouts/paths on-floor) | `... scripts\map_floor_audit.py` (exit 1 = fail) |
| Re-bless golden after INTENTIONAL engine change | `... scripts\regen_golden.py` |
| Rebuild a roster pack from its src/ sheets | `... scripts\build_roster_pack.py <pack-id>` |
| Map guide rasterizer (viewer-transform-exact) | `... scripts\render_map_guide.py [--map <id>]` |
| Painted map thumbnails (crop from backdrops) | `... scripts\render_map_thumbs.py` |
| Office guide rasterizer | `... scripts\render_office_guide.py` |
| Sprite-office offline preview (no browser) | `... scripts\render_sprite_office.py [out.png]` |
| Painted-art drift fix | `... scripts\align_painted.py [--apply]` |
| JS sanity | `node --check src\esports_sim\web\static\<file>.js` |

## Architecture (one line each)

- `src/esports_sim/sim/engine.py` — deterministic match engine; ALL tuning
  knobs in `sim/constants.py`, never inline. Reads `TeamTactics` (the
  coaching dials, `schemas/team.py`) for site call, pace, aggression,
  utility discipline, eco greed, and map control (stack vs spread + a
  lurker) — all neutral-safe (invariant 7). `sim/tactics_fit.py` is the
  single source of truth for roster-fit maths, shared by the engine's
  `_execution_mod` AND the web tactics serializer, so the UI's impact
  preview can't drift from what the engine applies. `sim/stats.py` derives
  the box score (incl. clutches/multikills/aces/first-deaths) from the
  event log only; never emits events, so it can't drift the golden.
- `src/esports_sim/manager/` — campaign: `campaign.py` (weekly tick, VCT
  phases, in-season AI tactic adaptation), `gen.py` (region-flavoured
  names), `market.py` (transfers + AI free-agent poaching), `development.py`
  (traits/PA, analyst-scaled scout precision), `training.py` (system-fit
  growth), `economy.py` (finances + insolvency), `sponsors.py`, `staff.py`,
  `talk.py`, `relationships.py` (pairwise chemistry graph, spotlight-role
  friction), `narrative.py` (recaps + tactical-identity + team awards),
  `inbox.py` (weekly digest; item actions derived LIVE from current
  offers, never stored), `state.py` (save; `standings_order` H2H
  tiebreaker; `schema_version` migration hook).
- `src/esports_sim/web/` — FastAPI, thin serializers over GameState; static
  vanilla-JS frontend on `ui/design-system` tokens. **UI holds no sim
  state — it renders event logs + GameState only.** Corollary: never
  mirror an engine formula in JS — serialize the computed values (see
  `tactics_fit`: the server returns per-dial impact at both poles, the
  client only lerps). Screens: app.js (tabs incl. dashboard hub +
  tactics), viewer.js (painted-backdrop isometric replay), office.js
  (sprite-composited home), inbox.js, profile.js (player/team overlays,
  opened via `[data-pid]`/`[data-tid]` delegation on any name).
- `data/` — YAML registries (agents/weapons/maps/geometry/teams). Strict
  pydantic (`extra="forbid"`): typos fail loudly. `data/rosters/<id>/` =
  roster packs (importable worlds, e.g. the real VCT 2026): `pack.yaml`
  (world shape: 3-4 regions, teams/region) + team bundles built from
  compact `src/` sheets by `scripts/build_roster_pack.py`
  (blake2-deterministic expansion; loader `registry/rosters.py`;
  `new_campaign(pack=...)` seeds from it and generates only shortfall).
  World shape lives on GameState (`league_regions`/`teams_per_region`),
  NOT the module constants — those are just the defaults.
- Docs: `GDD.md` (systems + design), `docs/art-pipeline.md`
  (blockout→beautify + map floor contract + LoRA status), `docs/adr/`
  (esp. ADR-007 neutral-safe tactics), `ROADMAP.md`, `SKILLS.md` (index
  of skills/agents). Skills: `/ship`, `/tactics`, `/art-pass`, `/maps`,
  `/web-screen`, `/campaign`.

## Non-negotiable invariants

1. **Determinism**: same seed → byte-identical event log. Every random draw
   comes from `RngTree` labels or blake2 hashes of stable ids. NEVER
   `hash()` (salted per process), never wall-clock, always sorted iteration.
2. **Golden gate**: `tests/test_golden.py` pins a canonical match log AND a
   multi-seed `sweep_neutral` fixture (every map × seeds 0-9). Engine/data
   changes that alter either require a deliberate re-bless
   (`scripts/regen_golden.py`, which blesses both) in the same commit.
3. **Balance band**: every map 45–65% attack-round rate after any change to
   `sim/constants.py` or `data/maps/**`.
4. **Pacing rule**: attacker site-to-site rotate through own spawn ≈ 30s
   (25–35 gate); defender interior rotates strictly faster.
5. **CLI output is ASCII-only** (legacy Windows consoles are cp1252).
6. Art/hotspot alignment: the plan owns silhouette + borders (vector
   overlay); paint supplies texture only. See `docs/art-pipeline.md`.
7. **Neutral-safe tactics** (see `docs/adr/ADR-007-neutral-safe-tactics.md`):
   the coaching dials (`TeamTactics`) and the per-team roster/chemistry
   modifiers reach deep into round micro, but EVERY term must be an exact
   no-op at the neutral value 50 (scale by `(dial-50)/50`, or gate outside
   `[45,55]`). The golden/balance gates run neutral tactics, so neutrality
   is what keeps them stable. Verify a tactics change by running the golden
   gate: byte-identical output = neutral-safe. Campaign-layer features
   (AI adaptation, economy, development) never run inside the match gates,
   so they're unconstrained by this rule — but must stay campaign-
   deterministic (same seed → byte-identical `GameState`).
8. **Map floor contract** (`scripts/map_floor_audit.py`, exit 1 = fail):
   every adjacency pair's floor plates touch, every callout center sits on
   its own plate, every path polyline stays on the plate union. Teleporter
   edges are exempt (the engine collapses those moves to endpoints —
   players beam, never walk). Run it after ANY `data/maps/geometry/**`
   edit; a geometry fix that passes it may still leave the PAINT stale —
   IoU won't catch that, only a per-seam 50%-blend overlay read does.

## Working conventions

- Balance lesson bank: symmetric constant tweaks failed to fix attack-rate
  skew; the working levers were ASYMMETRIC behaviors (defender fallback,
  grouped retakes). Check `git log` + memory before re-treading.
- Parallel subagents: partition by FILE (one agent owns data/maps/geometry,
  another owns web/static/x.js). Shared-file edits = sequence, don't race.
- Commit style: imperative subject + wrapped body explaining the why;
  gates run before every push; CI (GitHub Actions) must stay green.
  Parallel sessions push to this repo — expect non-fast-forward rejects;
  `git pull --rebase origin main`, rerun the gates, then push.
- Replays are captured at sim time and kept for the latest week only —
  rosters mutate immediately after, so stored seeds don't reproduce logs.
- Browser screenshots via the preview tools wedge chronically on this
  machine — verify UI with `preview_snapshot`/`preview_eval`/
  `preview_inspect`, and use the offline compositors
  (`render_sprite_office.py`, `render_map_guide.py`) for pixel checks.
- Viewer/guide transform contract: guides rasterize geometry at the exact
  transform the viewer uses (`render_map_guide.py` prints it), and the
  painted backdrop `<image>` is pinned at those same viewBox coords —
  change one side and the other must follow or paint/positions shear.
