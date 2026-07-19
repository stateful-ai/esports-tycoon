# Match Experiment Lab MCP

`esports-experiments` is the reusable causal-experiment interface for the
deterministic match engine. It replaces one-off sweep scaffolding with a typed,
discoverable workflow: inspect factors, preview cost, launch in the background,
poll progress, validate paired rows, and retrieve an analysis-ready summary.

## Start the server

The repo `.mcp.json` registers the stdio server automatically. It can also run
directly after installing the MCP extra:

```powershell
.venv-win\Scripts\python.exe -m pip install -e ".[dev,web,mcp]"
.venv-win\Scripts\python.exe -m esports_sim.mcp.experiment_server
```

The console entry point is `esports-experiment-mcp`.

## Recommended workflow

1. Call `get_experiment_catalog` to discover suites, factor ids, standard
   levels, maps, and pairing keys.
2. Call `preview_experiment`. A preview is read-only and returns exact version,
   cell, and match counts.
3. Call `start_experiment`. Runs are asynchronous and return a stable `run_id`.
4. Poll `get_experiment(run_id)` while the worker writes its manifest and log.
5. Call `validate_experiment` before interpreting results.
6. Call `summarize_experiment` for level outcomes and paired treatment effects
   expressed as rounds won above baseline. Pass `baselines` only when a run
   intentionally uses a comparator other than the catalog default.

The `core` suite covers overall, individual skills, prep/counter-strat, agent
and map mastery, player state, tactics, chemistry, and coaching. The
`mechanisms` suite covers shared language, role comfort and assignments, IGL
experience, and micro/tactical/mental skill bundles.

For the different question "does this game plan fit this roster?", use the
roster-fit series tools instead:

1. Call `preview_roster_fit_series` to choose roster archetypes, tactics dials,
   treatment poles, and series count.
2. Call `start_roster_fit_series` and poll the ordinary `get_experiment`.
3. Call `validate_roster_fit_series` to verify every control and treatment
   reused the same map and seed.
4. Call `summarize_roster_fit_series` for BO3/BO5 win lift, rounds won above
   the neutral control, and aligned-minus-mismatched fit interactions.

Within each roster-fit cell, both teams have the same player composition and
arithmetic overall. The control leaves every tactics dial at 50; the treatment
changes exactly one dial on the designated team. `fraggers` concentrate quality
in aim, reactions, and movement, while `tacticians` concentrate it in game
sense, utility, and comms. `mixed` fields two fraggers and three tacticians,
and `balanced` holds every attribute at the target quality. This makes the
estimand roster composition x plan, not a search for the globally best pole.

For authored teams rather than synthetic archetypes, use the roster-pack
tactics tools:

1. Call `preview_roster_pack_tactics_series` with a pack id such as
   `vct-2021`, selected team ids (or `all`), dials, poles, and series count.
2. Call `start_roster_pack_tactics_series`; poll it with `get_experiment`.
3. Call `validate_roster_pack_tactics_series` before analysis.
4. Call `summarize_roster_pack_tactics_series` for BO3/BO5 win lift, rounds
   won added, round-margin lift, and the roster features used by the engine.

The runner installs the authored five, including their uneven attributes,
roles, playstyles, agent pools, map mastery, condition, and chemistry, then
creates an exact mechanical mirror with distinct stable ids. The neutral
control and one-dial treatment therefore estimate how that real roster reacts
to the plan without mixing in the strength of a different opponent. Natural
team-versus-team matchups are a separate estimand and should be run only after
this clean composition test.

For an engine symmetry control, use the core factor `symmetry_baseline` with
equal `weak_quality` and `strong_quality`. It mirrors every mechanically
relevant player and team field while preserving stable team/player ids, then
runs without plans, staff bonuses, prep, counter-stratting, or scouting focus.
Keep identity swaps enabled so stable-id and starting-side effects cancel.
Unlike treatment sweeps, the second symmetry orientation uses a disjoint,
deterministically offset seed range; otherwise it would replay the same match
and force the labeled-team win rate to 50% by construction.

## Outcome language and baselines

Every catalog factor advertises its default baseline. Future summaries use the
same map, identity swap, and seed to report:

- `rounds_won_added`: treatment-team score minus baseline-team score;
- `opponent_rounds_denied`: baseline opponent score minus treatment opponent
  score;
- `round_margin_improvement`: the sum of those two components;
- `weak_win_effect_pp`: treatment-minus-baseline win rate in percentage points.

`preview_experiment` returns the selected `baselines`, and `start_experiment`
persists them in `request.json`, so rerunning a summary later does not depend on
whatever the catalog defaults happen to be at that time.

For example, `summarize_experiment(run_id)` treats shared-language fluency 50
as the baseline. To use `no_common` instead, call
`summarize_experiment(run_id, baselines={"shared_language": "no_common"})`.
The response reports a `baseline_issues` entry rather than silently choosing another
level when the requested or default baseline was not included in the run.

## Shared-language experiments

Choose the `mechanisms` suite and factor `shared_language`. Standard levels are
`no_common`, 20, 50, 75, and 100. Numeric levels set every weak-team player to
that fluency in one common language; `no_common` gives every weak-team player a
different language. The exact treatment is also saved in `matches.csv` as
`weak_language_mode`, so future analysis can audit what was applied.

## Equal-player management experiment

Set `weak_quality` and `strong_quality` to the same value and omit direct player
skill factors. For example, a 75-vs-75 `core` run over prep, counter-strat,
tactics, chemistry, coaching, and mastery isolates the management layer. Use
the same qualities and seed blocks in a `mechanisms` run to add language, IGL,
and role-fit treatments. Identity swaps are always included so team ids and
starting sides cannot masquerade as treatment effects.

## Output and reproducibility

Runs default to `runs/mcp-experiments/<run_id>/` and contain:

- `request.json`: exact request, expanded design, command, and expected size;
- `manifest.json`: engine revision, constants, progress, timing, and errors;
- `matches.csv`: one row per deterministic match with treatment inputs and
  outcome mechanisms;
- `run.log`: progress and worker errors;
- `validation.json`: completeness and duplicate-pairing audit.

Roster-fit runs use `series.csv` for one paired control/treatment comparison
per seed and format, `series_maps.csv` for the auditable map arms, and
`summary.json` for effect and interaction estimates.

Roster-pack tactics runs use `series.csv`, paired `maps.csv`, `summary.csv`,
and `team_features.json`. Their manifest records the pack, selected teams,
dials, poles, map-simulation count, engine revision, and exact command.

Override the artifact root with `ESPORTS_EXPERIMENT_RUNS_DIR`. Every stochastic
path remains seed-derived; identical code, data, request, and seeds reproduce
identical match rows.
