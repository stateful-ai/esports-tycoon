# ESports Simulator

![splash](assets/splash.webp)

A Valorant-flavored esports management sim in the spirit of *Esports Manager
2026*: run an org, build a roster, train players, work the transfer market,
scout rivals, talk to your players, and win Champions — with every match
decided by a deterministic tick-level simulation on real, walkable maps, not
a dice roll.

See **[GDD.md](GDD.md)** for the full game design document (systems,
mechanics, content, and where this is going) and **[ROADMAP.md](ROADMAP.md)**
for sprint-by-sprint status.

## Play

```bash
# Windows: use your venv's python (requires Python 3.12+)
python -m venv .venv-win
.venv-win\Scripts\python -m pip install -e ".[dev,web]"

# Browser (recommended) — campaign hub + isometric match viewer
.venv-win\Scripts\python -m esports_sim --web

# Terminal (rich CLI)
.venv-win\Scripts\python -m esports_sim
```

`New game` → pick a seed and a team → weekly loop: set training, scout a
rival, work the market, talk to a player, advance the week, watch replays.
Autosaves to `saves/campaign.json` every week.

Headless demo (a hands-off season, no UI):

```bash
python -m esports_sim --auto 18 --seed 11 --team team_nexus
```

## What's in the box

- **Match engine** (`sim/engine.py`): tick-level rounds on a callout graph
  with real floor-plan geometry underneath — buy phase with real Valorant
  credit rules, executes/defaults, continuous player movement (real x/y
  positions, speed-scaled travel, tactical slots at cover and doorway
  angles), point-to-point duels (range, elevation, positional cover,
  line-of-sight through props), directional pre-aim/flanks, peeking,
  mid-fight micro-repositioning, coarse agent utility (smokes, flashes,
  recon, post-plant lineups), spike plant/defuse, an asymmetric
  defender-fallback/retake model, halftime swap, overtime. ~50 ms per
  match, and **deterministic**: same seed → byte-identical event log,
  gated by both a determinism test and a golden-file fixture.
- **Management layer** (`manager/`): 8-team league (double round-robin →
  BO3 playoffs with map veto), weekly training with age curves,
  morale/stamina/form, backroom staff (coach/analyst/physio), scouting
  fog on rival attributes, weekly 1:1 player conversations, contract
  pressure, sponsorship offers, finances, free agency, offseason aging,
  multi-season campaigns, season stats + awards, grounded narrative
  recaps with rivalry callbacks. Also fully deterministic.
- **Web UI** (`web/`): FastAPI + a no-build-step frontend on a custom
  design system — dashboard, roster, standings, schedule, market, stats,
  finances — plus an isometric 2D match viewer that replays the event log
  with full playback controls (scrub, speed, round-skip).
- **Data-driven content** (`data/`): 13 agents, 7 weapons, 5 maps (each
  with an authored floor-plan geometry layer — rooms, corridors, props,
  elevation), and starter teams, all YAML — add an agent or a map without
  touching code.
- **Policy interface** (`policy/`): in-match player decisions go through a
  `PlayerPolicy` protocol; the shipped heuristic can be swapped for RL
  agents or LLM playtesters.

## Tuning

Gameplay feel lives in `src/esports_sim/sim/constants.py`. After changing
numbers or map/geometry YAML, check the gates:

```bash
python scripts/balance_report.py 200     # attack-side round rate, 45-65% band
python scripts/pacing_report.py          # attacker rotate ~30s through spawn
python scripts/snowball_report.py        # multi-season blowout/competitiveness check
python scripts/regen_golden.py           # re-bless the golden match log after an
                                          # intentional engine/geometry change
```

## Tests

```bash
python -m pytest -q
```

The north-star invariant: `tests/test_determinism.py` asserts that two runs
of the same match produce byte-identical event logs, and `tests/test_golden.py`
pins one canonical match log's hash so unintentional drift fails CI.
