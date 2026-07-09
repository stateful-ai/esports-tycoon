# Agent instructions

This repo's canonical AI-agent guide lives in [CLAUDE.md](CLAUDE.md) —
environment, commands, architecture, and the non-negotiable invariants
(determinism, golden gate, balance band, pacing rule, ASCII CLI, art/hotspot
alignment). Read it before changing anything.

Quick orientation for any agent:

- Windows repo. Python via `.venv-win\Scripts\python.exe` (NOT `.venv/`).
- Test: `.venv-win\Scripts\python.exe -m pytest -q` — must be green before
  any commit. Engine/data changes additionally require the balance +
  pacing gates; map geometry changes also the floor-audit gate
  (`scripts\map_floor_audit.py`); and (if the match log changed on
  purpose) a golden re-bless. All commands are tabulated in CLAUDE.md.
- Every stochastic thing derives from seeds/stable hashes. If you add
  randomness, thread it through `RngTree` or blake2 of stable ids. This
  holds for the CAMPAIGN too: same seed → byte-identical `GameState`.
- Gameplay tuning lives in `src/esports_sim/sim/constants.py` and
  `data/*.yaml` — not inline in the engine.
- **Coaching tactics are neutral-safe**: the `TeamTactics` dials reach into
  round micro, but every term is an exact no-op at 50 so the golden gate
  stays byte-identical. Extending a dial? Use the `/tactics` skill and see
  `docs/adr/ADR-007-neutral-safe-tactics.md`.
- The web UI is a pure consumer of GameState + event logs. Don't put sim
  logic in JavaScript — and don't MIRROR engine formulas in JS either:
  serialize the computed values (pattern: `sim/tactics_fit.py`, shared by
  engine and serializer; the client only interpolates server-sent poles).
- Design overview: `GDD.md`. Asset generation (Ludo / Scenario / Google AI
  Studio): recipes, the blockout→beautify pipeline, and the map floor
  contract are in `docs/art-pipeline.md`; API keys are in the gitignored
  `.env`.
- Skill/agent index: `SKILLS.md` (repo skills `/ship`, `/tactics`,
  `/art-pass`, `/maps`, `/web-screen`, `/campaign`; custom agents
  map-author, sim-tuner, art-generator).
