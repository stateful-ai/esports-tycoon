# AI skills & agents in this repo

Index of the repo's AI-assist configuration. `CLAUDE.md` is the entry
point (environment, commands, invariants); `AGENTS.md` is the cross-tool
mirror of it.

## Skills (`.claude/skills/`)

| Skill | Use it to |
|---|---|
| `ship` | Run the full gate stack (tests → golden → balance → pacing → floor audit → JS) and push with CI watch |
| `tactics` | Add or extend a coaching dial the neutral-safe way (ADR-007), incl. the shared `tactics_fit` layer |
| `art-pass` | Run a scene-art generation pass through the blockout→beautify pipeline (office + maps) |
| `maps` | Change map geometry/graphs end-to-end: audit → pacing/balance → guides → repaint check → thumbs → re-bless |
| `web-screen` | Add or rework a web UI screen the repo way (thin serializer, no sim logic in JS, tokens, profile links) |
| `campaign` | Add a campaign-layer (manager/) feature: determinism rules, save migration, snowball gate, inbox surfacing |
| `skills/esports-sim-guardrails` (repo-root, legacy location) | Engineering guardrails: determinism, typed boundaries, data-driven design |

## Learning policy work

Use `.claude/skills/learning/SKILL.md` for learned player or manager policies:
fog-safe observations, resolver-provided legal actions, deterministic seed
splits, version-pinned checkpoints, and champion/challenger promotion. The
repo-root guardrails retain their strict simulation rules while documenting the
narrow stable-hash RNG exception for offline training.

## Custom agents (`.claude/agents/`)

| Agent | Scope |
|---|---|
| `map-author` | Map content only (graphs, geometry, props, gimmicks) with balance + pacing gates baked in |
| `art-generator` | Asset generation via the validated Ludo / Google AI Studio / Scenario recipes, with structure gating |
| `sim-tuner` | Engine balance/pacing tuning with the measurement stack and the do-not-retread lesson bank |

## Other AI-relevant fixtures

- `.claude/settings.json` — shared permission allowlist (tests, gate
  scripts, git/gh read ops) so sessions prompt less.
- `.claude/launch.json` — "web" preview config (`python -m esports_sim
  --web --no-browser`, port 8420).
- `docs/art-pipeline.md` — the full blockout→beautify doctrine.
- `.env` (gitignored) — generation API keys; never commit.
