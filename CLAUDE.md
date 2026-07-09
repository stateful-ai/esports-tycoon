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
| Rotation pacing gate (25–35s via spawn) | `... scripts\pacing_report.py` (exit 1 = fail) |
| Multi-season snowball gate (blowout/close band) | `... scripts\snowball_report.py` (exit 1 = fail) |
| Re-bless golden after INTENTIONAL engine change | `... scripts\regen_golden.py` |
| Office guide rasterizer | `... scripts\render_office_guide.py` |
| Sprite-office offline preview (no browser) | `... scripts\render_sprite_office.py [out.png]` |
| Painted-art drift fix | `... scripts\align_painted.py [--apply]` |
| JS sanity | `node --check src\esports_sim\web\static\<file>.js` |

## Architecture (one line each)

- `src/esports_sim/sim/engine.py` — deterministic match engine; ALL tuning
  knobs in `sim/constants.py`, never inline. Reads `TeamTactics` (the
  coaching dials, `schemas/team.py`) for site call, pace, aggression,
  utility discipline, eco greed, and map control (stack vs spread + a
  lurker) — all neutral-safe (invariant 7). `sim/stats.py` derives the box
  score (incl. clutches/multikills/aces/first-deaths) from the event log
  only; never emits events, so it can't drift the golden.
- `src/esports_sim/manager/` — campaign: `campaign.py` (weekly tick, VCT
  phases, in-season AI tactic adaptation), `gen.py` (region-flavoured
  names), `market.py` (transfers + AI free-agent poaching), `development.py`
  (traits/PA, analyst-scaled scout precision), `training.py` (system-fit
  growth), `economy.py` (finances + insolvency), `sponsors.py`, `staff.py`,
  `talk.py`, `relationships.py` (pairwise chemistry graph, spotlight-role
  friction), `narrative.py` (recaps + tactical-identity + team awards),
  `state.py` (save; `standings_order` H2H tiebreaker; `schema_version`
  migration hook).
- `src/esports_sim/web/` — FastAPI, thin serializers over GameState; static
  vanilla-JS frontend on `ui/design-system` tokens. **UI holds no sim
  state — it renders event logs + GameState only.**
- `data/` — YAML registries (agents/weapons/maps/geometry/teams). Strict
  pydantic (`extra="forbid"`): typos fail loudly.
- Docs: `GDD.md` (systems + design), `docs/art-pipeline.md`
  (blockout→beautify), `docs/adr/` (esp. ADR-007 neutral-safe tactics),
  `ROADMAP.md`. Skills: `/ship` (gate stack + push), `/tactics` (neutral-
  safe dial workflow).

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

## Working conventions

- Balance lesson bank: symmetric constant tweaks failed to fix attack-rate
  skew; the working levers were ASYMMETRIC behaviors (defender fallback,
  grouped retakes). Check `git log` + memory before re-treading.
- Parallel subagents: partition by FILE (one agent owns data/maps/geometry,
  another owns web/static/x.js). Shared-file edits = sequence, don't race.
- Commit style: imperative subject + wrapped body explaining the why;
  gates run before every push; CI (GitHub Actions) must stay green.
- Replays are captured at sim time and kept for the latest week only —
  rosters mutate immediately after, so stored seeds don't reproduce logs.
