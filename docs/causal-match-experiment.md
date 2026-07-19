# Causal match experiment

## Question

How often should an approximately 65-overall roster beat an 85-overall
roster, and which management or match-engine levers are responsible when it
does?

This experiment measures the engine before changing its tuning. It uses a
normalized synthetic matchup so player quality, condition, mastery, chemistry,
and tactics do not arrive as a correlated bundle. The favorite is held at 85
overall and the underdog starts at 65 overall. Each experiment changes one
declared factor while preserving every other input.

## Identification design

- Each version is simulated 30 times per map, roster-identity assignment, and
  seed block.
- The same exact seeds are reused across control and treatment versions. This
  permits paired estimates rather than comparing unrelated match samples.
- The underdog is alternated between Nexus and Vanguard. This separates a
  quality effect from player ids, authored roles, captain identity, and the
  order in which teams enter the engine.
- Five maps test whether a lever is general or geometry-specific.
- Seed blocks begin at 0, 10,000, and 20,000. The later analysis should fit on
  two blocks and validate direction/rank on the held-out block, then rotate the
  holdout.
- Neutral inputs are intentionally duplicated across factor families. They are
  deterministic negative controls: identical map/identity/seed rows should
  have identical results even when reached through a different no-op version.

The design is one-factor-at-a-time. It estimates total causal effects cleanly,
but does not identify arbitrary interactions. The one deliberate conditional
experiment varies chemistry while a complex map-control/utility system is held
fixed, because chemistry is neutral-safe and therefore has no mechanical reach
under neutral tactics.

## Interventions

The primary tier covers:

- the underdog quality curve from 45 through 85 overall;
- scouting/preparation edge and signed counter-strategy edge;
- each of the ten player attributes independently;
- agent mastery and map mastery;
- form, morale, stamina, and confidence.

The second tier covers:

- each coaching tactic dial from 0 through 100;
- chemistry at neutral and in a coordination-heavy system;
- focus targeting;
- automatic, comfort-locked, and unfamiliar same-role agent selection;
- balanced versus star-heavy rosters at the same 65 team mean;
- coach quality, halftime talks, and touchline shouts.

## Outcomes recorded per match

The analysis table stores the treatment, context, map, roster identity, seed
block, seed index, and raw seed alongside:

- underdog win, score, round margin, close-match flag, and overtime flag;
- underdog attack/defense rounds and wins;
- kills and trade kills by side;
- utility uses and failed utility by side;
- plants and defuses by side;
- coach timeout, halftime-talk, and shout activations;
- round-end reason counts and final event tick.

The manifest pins the git SHA and the relevant engine constants. The cell
summary is only a convenience view; `matches.csv` remains the source of truth.

## Planned analysis

Start with the baseline 65-vs-85 upset rate and an exact binomial interval.
For each factor, estimate paired average treatment effects on underdog win and
round margin within `(map, identity_swap, seed)`. Report both absolute
percentage-point movement and movement relative to the 20-point talent gap.

Then fit a conditional logistic or fixed-effect win model with map, identity,
and seed-block controls. Rank levers by held-out seed-block effect size, not by
in-sample p-value. Check sign consistency across maps and seed blocks, and flag
levers whose average hides a large map interaction.

Finally, use the negative controls to verify deterministic equivalence and use
the same-mean roster-shape experiment to distinguish team-average quality from
star concentration. Engine tuning should begin only after these checks; likely
targets are levers with a large reproducible effect relative to raw talent or a
65-vs-85 baseline upset rate above the intended design band.

## Running and resuming

```powershell
.venv-win\Scripts\python.exe scripts\causal_match_experiment.py `
  --minutes 40 --workers 14
```

Pass the same `--out runs\causal-match-...` directory to resume. Completed
30-match cells are skipped, the match CSV is appended, and the manifest and
cell summary are refreshed at the end.

Validate a completed artifact without performing substantive analysis:

```powershell
.venv-win\Scripts\python.exe scripts\validate_causal_match_dataset.py `
  runs\causal-match-20260718-main-e1d9db2
```
