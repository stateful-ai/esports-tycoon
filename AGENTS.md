# Agent instructions

This repo's canonical AI-agent guide lives in [CLAUDE.md](CLAUDE.md) —
environment, commands, architecture, and the non-negotiable invariants
(determinism, golden gate, balance band, pacing rule, ASCII CLI, art/hotspot
alignment). Read it before changing anything.

Quick orientation for any agent:

- Windows repo. Python via `.venv-win\Scripts\python.exe` (NOT `.venv/`).
- Test: `.venv-win\Scripts\python.exe -m pytest -q` — must be green before
  any commit. Engine/data changes additionally require the balance +
  pacing gates and (if the match log changed on purpose) a golden re-bless.
  All commands are tabulated in CLAUDE.md.
- Every stochastic thing derives from seeds/stable hashes. If you add
  randomness, thread it through `RngTree` or blake2 of stable ids.
- Gameplay tuning lives in `src/esports_sim/sim/constants.py` and
  `data/*.yaml` — not inline in the engine.
- The web UI is a pure consumer of GameState + event logs. Don't put sim
  logic in JavaScript.
- Asset generation (Ludo / Scenario / Google AI Studio): recipes and the
  blockout→beautify pipeline are in `docs/art-pipeline.md`; API keys are in
  the gitignored `.env`.
