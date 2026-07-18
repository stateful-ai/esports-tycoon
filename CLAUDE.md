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
| Tests (full, parallel by default) | `.venv-win\Scripts\python.exe -m pytest -q` |
| Tests (fast pre-merge loop, skips whole-season soak) | `... -m pytest -q -m "not slow"` |
| Tests (serial, for `-x`/`--pdb` on one test) | `... -m pytest -q -n0 <path>::<test>` |
| Balance gate (45–65% attack band) | `... scripts\balance_report.py 300` (exit 1 = fail) |
| Rotation pacing gate (25–35s via spawn, 8–18s spawn→entry) | `... scripts\pacing_report.py` (exit 1 = fail) |
| Multi-season snowball gate (blowout/close band) | `... scripts\snowball_report.py` (exit 1 = fail) |
| Dynasty gate (title concentration over N seasons) | `... scripts\dynasty_report.py [seasons] [seed]` (exit 1 = fail) |
| RL episode export (save -> transitions/actions/chronicle JSONL) | `... scripts\export_telemetry.py <save-or-dir> [stem]` |
| Manager policy rollouts (traces/runs/evaluation) | `... scripts\run_manager_rollouts.py [seeds] [profiles] [weeks] [stem]` |
| Train learned manager policy (seed-split imitation) | `... scripts\train_manager_policy.py [train-seeds] [val-seeds] [profiles] [weeks] [checkpoint]` |
| Generate/train learned player policy (cross-map seed split) | `... scripts\train_player_policy.py <checkpoint> [--map all --seeds N --validation-seeds N --dataset runs\...jsonl]` |
| Improve manager policy (online simulation + promotion gate) | `... scripts\online_train_manager_policy.py <checkpoint> [--train-seeds N --eval-seeds N --profiles N --weeks N]` |
| Autoplay with installed manager AI | `python -m esports_sim --auto N --manager-model telemetry\manager_policy_champion.json` |
| Match token corpus (world-model data; pinned vocab) | `... scripts\dump_season_tokens.py [n] [seed] [stem]` |
| Play-pattern report (feature usage across saves) | `... scripts\telemetry_report.py [saves-dir]` |
| Tactics-dial sweep gate (each numeric dial at its poles) | `... scripts\tactics_report.py` (exit 1 = fail) |
| Map floor gate (plates touch; callouts/paths on-floor) | `... scripts\map_floor_audit.py` (exit 1 = fail) |
| Re-bless golden after INTENTIONAL engine change | `... scripts\regen_golden.py` |
| Rebuild a roster pack from its src/ sheets | `... scripts\build_roster_pack.py <pack-id>` |
| Roster-pack MCP (stdio) | `... -m esports_sim.mcp.roster_server` |
| Map Studio MCP (stdio) | `... -m esports_sim.mcp.map_server` |
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
  scrim at reduced growth), `fantasy_draft.py` (opt-in sandbox start:
  every tier-1 roster + the FA pool + a generated draft class enter one
  shared pool and all orgs snake-draft ten each before week 1; AI picks
  and the human recommendation panel share ONE value function, AI leans
  are blake2-derived, and the web layer gates advancing until the last
  pick — after `_complete` the campaign is indistinguishable from a
  classic start), `development.py` (traits/PA, scout
  precision, weekly random dev events on a dedicated rng stream),
  `training.py` (system-fit growth, per-player dev_focus/intensity plans,
  match-XP from box-score lines, bench scrim reps), `academy.py` (tier-1
  parents over real tier-2 affiliates: intake, promotion/send-down and
  minutes-based growth), `preparation.py` (scrim/bootcamp plans -> grounded
  reports + org knowledge), `series_management.py` (tournament sixes and
  conditional between-map responses), `culture.py` (captain/council,
  principles and bounded relationship arcs), `delegation.py` (human staff
  policies over existing renewal/scouting capacity), `media_events.py` (rare
  contextual choices with persistent trust/sponsor/sentiment effects), `economy.py`
  (finances + insolvency), `sponsors.py`, `staff.py` (ONE shared 50+
  free-agent staff pool with seven attributes, mechanical role traits,
  grounded career badges/stats, and role-weighted overall; every tier-one
  club has a concrete coach whose tactical identity/system fit shapes
  training, preparation, timeout advice and AI adaptation; `analytics_tier`
  gates stat-view depth), `social.py`
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
  mentorship and tenure/language/negotiation fields; migrations now continue
  through v23 for newer campaign, telemetry, complete contracts, club-depth,
  delegation, and durable media state),
  `telemetry.py` (analytics substrate: `action_log` records
  every HUMAN decision at the web/CLI layer — never AI moves, they
  re-derive from the seed — so seed + action_log fully determines a
  career; `telemetry_snaps` appends a post-tick org feature vector per
  manager seat each week; `state_features`/`reward_components` are the
  single source of truth for RL episodes — `scripts/export_telemetry.py`
  emits (state, actions, reward) JSONL, `scripts/dump_season_tokens.py`
  a match token corpus with a PINNED vocab, `scripts/telemetry_report.py`
  the cross-save feature-usage report); `decision_env.py` exposes the shared,
  manager-visible decision observation, legal action masks, and a deterministic
  framework-agnostic headless policy environment; `manager_policy.py` and
  `rollout.py` provide generated manager profiles, a masked heuristic baseline,
  decision traces, batch evaluation, and training-data exports;
  `learned_manager_policy.py` adds the NumPy set encoder, profile-conditioned
  imitation heads, JSON checkpoints, and deterministic learned-policy replay. Player
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
  server, e.g. Ollama); `SOCIAL_LLM=off` disables. When `serve.ps1` or
  the taskbar launcher starts vLLM, it automatically points the social
  writer, 1:1 replies, and campaign flavor-event copy at the local
  OpenAI-compatible endpoint unless those provider settings were explicitly
  configured. The model REPHRASES facts we hand it, never invents events
  (grounded like narrative).
  Screens: app.js (nine tabs: dashboard hub, inbox, Match — the single
  home for all match preparation incl. tactics/game plans, Club with four
  sub-tabs Squad|Development|Locker Room|Operations, facilities, season,
  market with a Players|Scouting|Staff split, stats hub, and Company with a
  Finances|Brand split (Brand absorbed the old Social tab)), viewer.js
  (painted-backdrop isometric replay), inbox.js, profile.js
  (player/team/staff overlays via `[data-pid]`/`[data-tid]`/`[data-sid]`
  delegation on any name). `facilities.js` is the live menu-based upgrade
  screen; `/api/facilities` serializes all six departments, levels, effects,
  staff operators, costs, and next-level previews, so JavaScript owns no
  facility formulas. Recovery, strategy-prep, and wellbeing benefits resolve
  in the campaign layer and remain bounded by stamina/knowledge/neutral caps.
  The office UI (`office.js`/`office.css`) was removed; `office_plan.json`
  and `office_sprites.json` stay for the offline render scripts
  (`render_office_guide.py`, `render_sprite_office.py`).
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
  `/map-studio-authoring`, `/web-screen`, `/campaign`, `/build-roster-packs`.

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
- Dashboard card budget: the Dashboard has a HARD budget of 7 cards. A new
  campaign/web feature lands as an inbox item + a nav "needs you" badge
  (`computeNeedsYou` in app.js) + a section on its OWNING tab — never a new
  Dashboard card without removing one. The Match tab is the single home for
  all match preparation.
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

## Learned policy workflow

- `src/esports_sim/policy/` owns engine-facing player policies. The engine is
  the resolver: policies rank typed, engine-supplied legal actions from a
  fog-safe `PlayerObservation`. `heuristic.py` owns baseline player, IGL, and
  coach behavior; `learned.py` adds version-pinned NumPy action and
  communication rankers. Sampling always receives the engine's per-player RNG.
- Manager policies consume only `decision_env.manager_observation` and its
  legal-action mask. `learned_manager_policy.py` provides deterministic
  imitation checkpoints; `online_manager_learning.py` fine-tunes only the
  action head through simulated exploration and promotes only on disjoint-seed
  completion, legality, reward, balance, wins, and profile-TV gates.
- Learned-policy checkpoints are schema contracts, not loose JSON: pin policy,
  observation, encoder, vocabulary, and profile versions; retain train and
  held-out seed lists in metadata; never overwrite a champion with an
  unpromoted candidate.
- A detached worktree may not have `.venv-win`. When reusing the primary
  checkout's venv, first set `$env:PYTHONPATH=(Resolve-Path 'src').Path`;
  otherwise subprocess CLIs can import the primary checkout instead of the
  worktree under test.

Use `/learning` for player or manager policy work. The command table includes
`scripts/train_player_policy.py`, `scripts/train_manager_policy.py`, and
`scripts/online_train_manager_policy.py`; run focused resolver/policy tests and
held-out evaluation before publishing a checkpoint.
