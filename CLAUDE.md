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
| Dynasty gate (title concentration over N seasons) | `... scripts\dynasty_report.py [seasons] [seed]` (exit 1 = fail) |
| RL episode export (save -> transitions/actions/chronicle JSONL) | `... scripts\export_telemetry.py <save-or-dir> [stem]` |
| Match token corpus (world-model data; pinned vocab) | `... scripts\dump_season_tokens.py [n] [seed] [stem]` |
| Play-pattern report (feature usage across saves) | `... scripts\telemetry_report.py [saves-dir]` |
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
  lurker) — all neutral-safe (invariant 7) — plus optional per-match
  `TeamMatchPlan` overrides (game plans: tactics swap, focus target,
  scouting prep edge) supplied by the campaign; the gates pass None, so
  no plan == the pre-plan engine byte-for-byte. In-match `momentum`
  (kills/deaths/clutches, rng-free bookkeeping) only AMPLIFIES a
  player's confidence deviation via `_conf_dev` — exact no-op at 50.
  `sim/tactics_fit.py` is the
  single source of truth for roster-fit maths, shared by the engine's
  `_execution_mod` AND the web tactics serializer, so the UI's impact
  preview can't drift from what the engine applies. `sim/stats.py` derives
  the box score (incl. clutches/multikills/aces/first-deaths) from the
  event log only; never emits events, so it can't drift the golden.
- `src/esports_sim/manager/` — campaign: `campaign.py` (weekly tick, VCT
  phases, in-season AI tactic adaptation, per-map/per-agent stat splits +
  weekly history snapshots), `gen.py` (region-flavoured names),
  `market.py` (transfers + AI poaching; humans may bench up to
  ROSTER_MAX=10 — only the dressed five play a map, resolved by
  `campaign.dressed_for` from per-map overrides -> `Team.lineup_ids` ->
  quality top-up, with agent locks via `sim/lineup.py`; bench players
  scrim at reduced growth), `development.py` (traits/PA, scout
  precision, weekly random dev events on a dedicated rng stream),
  `training.py` (system-fit growth, per-player dev_focus/intensity plans,
  match-XP from box-score lines, bench scrim reps), `economy.py`
  (finances + insolvency), `sponsors.py`, `staff.py` (ONE shared 50+
  free-agent staff pool with rich identities; coach specialty boosts the
  matching focus; `analytics_tier` gates stat-view depth), `social.py`
  (follower counts + deterministic weekly feed; roster reach feeds
  sponsor marketability; per-team community SENTIMENT chases weekly
  outcomes and feeds back into confidence/morale + sponsor pressure),
  `meta.py` (live balance patches twice a season: usage-driven agent
  buffs/nerfs held on GameState, applied by `runtime_gamedata` as a
  fresh agents dict — the bare-engine gates never see them), `talk.py`,
  `relationships.py` (pairwise
  chemistry graph), `narrative.py` (recaps + awards), `inbox.py` (weekly
  digest; item actions derived LIVE from current offers, never stored),
  `state.py` (save; `standings_order` H2H tiebreaker; `schema_version`
  migrations — v3 moved staff candidates into the shared pool; v4 is a
  pass-through for the game-plan/sentiment/patch fields; v5 adds the
  Chronicle + legacy fields, backfilling a skeleton history from
  champions/awards/retired; v6/v7 are pass-throughs for the career-stat/
  mentorship and tenure/language/negotiation fields; v8 is a pass-through
  for the telemetry fields), `telemetry.py` (analytics substrate: `action_log` records
  every HUMAN decision at the web/CLI layer — never AI moves, they
  re-derive from the seed — so seed + action_log fully determines a
  career; `telemetry_snaps` appends a post-tick org feature vector per
  manager seat each week; `state_features`/`reward_components` are the
  single source of truth for RL episodes — `scripts/export_telemetry.py`
  emits (state, actions, reward) JSONL, `scripts/dump_season_tokens.py`
  a match token corpus with a PINNED vocab, `scripts/telemetry_report.py`
  the cross-save feature-usage report). Player
  `confidence` moves on results/ratings/dev events/sentiment, regresses
  weekly, and is read NEUTRAL-SAFE by the engine (exact no-op at 50);
  tilt spirals/heaters roll on the dedicated "tilt" rng stream. Game
  plans live per-manager in `game_plans_by` (one per next fixture,
  consumed at sim time, may carry a one-match lineup).
  **Legacy Mode (GDD section 10)** rides `chronicle.py` — an append-only
  career-event list on GameState (titles/awards/moves/debuts/milestones;
  NEVER pruned) that every legacy system READS, mirroring "the event log
  is the only truth": `career.py` (game_mode sandbox|legacy, ManagerSeat
  ids that follow the person, career offers, contracts + board patience
  + dismissal + job market, reputation/philosophies DERIVED from the
  chronicle), `personality.py` (five axes as a pure function of id+tags;
  consumers scale by (axis-50)/50), `memories.py` (loyalty bias, board
  posture — bounded nudges), `rivalries.py` (pair heat from playoff
  meetings/poaches; offseason cooling), `hof.py` (induction at
  retirement — the one STORED legacy view, retirees are deleted),
  `knowledge.py` (org playbooks/anti-strats/methodology; leaks with
  staff moves; feeds prep edge ONLY through a set game plan; guarded by
  the dynasty gate), coaching tree via `staff.retire_into_staff`
  (deterministic, no rng draw), and strategy diffusion in
  `_adapt_ai_tactics` (strugglers copy the meta identity; season-end
  meta eras chronicled).
- `src/esports_sim/web/` — FastAPI, thin serializers over GameState; static
  vanilla-JS frontend on `ui/design-system` tokens. **UI holds no sim
  state — it renders event logs + GameState only.** Corollary: never
  mirror an engine formula in JS — serialize the computed values (see
  `tactics_fit`: the server returns per-dial impact at both poles, the
  client only lerps). Stat-column depth is gated SERVER-SIDE by
  `staff.analytics_tier` — the client renders whatever fields arrive.
  `web/llm_social.py` ghost-writes social posts with an LLM at SERVE
  time only: the deterministic template text stays in the save (the
  grounded fallback + hover "fact"), rewrites live in a sidecar cache
  (`saves/social_llm_<code>.json`) keyed by post id — so campaign
  determinism is untouched. Providers via .env: `OPENROUTER_API_KEY`
  (OpenRouter) or `SOCIAL_LLM_BASE_URL` (any local OpenAI-compatible
  server, e.g. Ollama); `SOCIAL_LLM=off` disables. The model REPHRASES
  facts we hand it, never invents events (grounded like narrative).
  Screens: app.js (tabs incl. dashboard hub, tactics, market with a
  Players|Staff split, stats hub, social feed), viewer.js
  (painted-backdrop isometric replay), inbox.js, profile.js
  (player/team/staff overlays via `[data-pid]`/`[data-tid]`/`[data-sid]`
  delegation on any name). office.js is PARKED — unloaded from
  index.html, kept on disk.
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
