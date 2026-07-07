# ESports Simulator

![splash](assets/splash.webp)

A Valorant-flavored esports management sim in the spirit of *Esports Manager
2026*: run an org, build a roster, train players, work the transfer market,
and win Champions — with every match decided by a deterministic tick-level
simulation on real callout-graph maps, not a dice roll.

## Play

```bash
# Windows: use your venv's python (requires Python 3.12+)
python -m venv .venv-win
.venv-win\Scripts\python -m pip install -e ".[dev]"
.venv-win\Scripts\python -m esports_sim
```

`New game` → pick a seed and a team → weekly loop: set training, work the
market, play the week. Autosaves to `saves/campaign.json` every week.

Headless demo (a hands-off season):

```bash
python -m esports_sim --auto 18 --seed 11 --team team_nexus
```

## What's in the box

- **Match engine** (`sim/engine.py`): tick-level rounds on a callout graph —
  buy phase with real Valorant credit rules, executes/defaults, sightline
  duels driven by ten player attributes, coarse agent utility (smokes,
  flashes, recon, post-plant lineups), spike plant/defuse, retake-or-save
  decisions, halftime swap, overtime. ~50 ms per match, and **deterministic**:
  same seed → byte-identical event log.
- **Management layer** (`manager/`): 8-team league (double round-robin →
  BO3 playoffs), weekly training with age curves, morale/stamina/form,
  finances (salaries, sponsors, prize money), free agency + contracts,
  offseason aging, multi-season campaigns. Also fully deterministic given
  the same seed and player decisions.
- **Data-driven content** (`data/`): agents, weapons, maps, and teams are
  YAML — add an agent or a map without touching code.
- **Policy interface** (`policy/`): in-match player decisions go through a
  `PlayerPolicy` protocol; the shipped heuristic can be swapped for RL
  agents or LLM playtesters.

## Tuning

Gameplay feel lives in `src/esports_sim/sim/constants.py`. After changing
numbers (or map YAML), check the balance:

```bash
python scripts/balance_report.py 40
```

## Tests

```bash
python -m pytest -q
```

The north-star invariant: `tests/test_determinism.py` asserts that two runs
of the same match produce byte-identical event logs.
