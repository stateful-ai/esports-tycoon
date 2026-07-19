# VCT 2021 pole-specific tactics tuning v5

## Decision summary

The first implementation pass removes the large globally dominant pole effects
from the mirrored-real-roster experiment. Across the same four teams in the
pre-change benchmark, aggression 100 added 31.2 BO3 win-rate points and utility
discipline 100 lost 12.5 points. At v5, the BO3 pole effects range from
-1.7 to +6.7 points,
apart from roster-specific cells. Round-margin effects at the aggregate pole
level range from -0.35 to +1.84 rounds per series.

The result is not a claim that every interaction is fully calibrated. It is a
stronger engine contract: each pole has distinct roster demands and explicit
benefit/cost channels, and multiple real teams now cross over in opposite
directions. Pace 100 remains the clearest follow-up candidate in BO5.

## Experiment

- Roster pack: `vct-2021`
- Teams: FURIA, Team Envy, NUTURN, ZETA DIVISION
- Design: each authored five is mechanically mirrored; control keeps both
  teams at tactics 50; treatment changes one designated-team dial to 0 or 100
- Pairing: identical roster, chemistry, agents, map order, side orientation,
  and per-map seed within each comparison
- Replication: 30 series seeds per team/dial/pole
- Formats: BO3 and BO5 derived from the same five paired maps
- Final simulations: 5,400 maps; 1,920 series rows; 4,800 paired map rows
- Artifacts: `runs/mcp-experiments/20260719-vct2021-poles-final-v5-30series/`

## Aggregate BO3 effects versus neutral

| Dial | Pole | Series win lift | Rounds won added | Round-margin lift |
|---|---:|---:|---:|---:|
| Aggression | 0 | -0.8 pp | +0.20 | +1.84 |
| Aggression | 100 | +6.7 pp | +0.42 | +0.82 |
| Pace | 0 | +3.3 pp | +1.42 | +0.92 |
| Pace | 100 | -0.8 pp | -0.24 | -0.35 |
| Utility discipline | 0 | -1.7 pp | -0.29 | -0.25 |
| Utility discipline | 100 | -1.7 pp | +1.04 | +0.03 |
| Map control | 0 | +1.7 pp | -0.08 | +1.27 |
| Map control | 100 | 0.0 pp | +0.03 | -0.30 |

## Clear roster-dependent cells

- FURIA loses 23.3 BO3 win-rate points and 1.50 rounds won under map control
  100; its high-pole fit edge is -0.543.
- NUTURN gains 13.3 BO3 points and 0.67 rounds under map control 100; its fit
  edge is +0.884.
- NUTURN loses 16.7 BO3 points and 3.43 rounds under pace 100; its fit edge is
  -0.358.
- NUTURN gains 2.30 rounds under utility discipline 100 and loses 0.90 under
  utility discipline 0; its high-pole fit edge is +0.952.
- ZETA loses 3.3 BO3 points and 0.70 rounds under aggression 100, while Team
  Envy gains 23.3 points and 1.47 rounds. This indicates a real composition
  interaction not completely explained by the current displayed fit score.

## Engine changes represented by this run

- Low and high poles use distinct attribute and playstyle requirements.
- Pole fit is relative to the opposite system, so raw overall cannot reward
  both directions automatically.
- Aggression trades initiative/refrags against holder strength and a
  mechanically mitigated overextension cost.
- Pace trades clock/information and abort behavior against pole-specific entry
  setup or surprise.
- Low utility discipline concentrates power in the execute; high discipline
  saves charges and now actually releases them during stalls and retakes.
- High map control converts sense/positioning/comms fit into earlier lurker
  synchronization, while the grouped low side retains local numbers.

## Validation

- Golden neutral gate: passed, byte-identical
- Engine/golden suite: 91 passed
- MCP/API/reporting focused suite: 19 passed
- Tactics extreme sweep: passed; strategy-dial attack rates 47.0%-50.7%
- Neutral balance gate: passed on all five maps (54.0%-59.6% attack)
- Pacing gate: passed (attacker rotations 26.4-29.5s; staging 12.2-16.4s)

## Next calibration question

Run more roster packs and natural opponent contexts before changing the v5
constants again. The highest-priority hypothesis is that pace 100 is too weak
in longer series except for a narrow set of fast-entry compositions. The next
design should cross roster, selected agent composition, map, and opponent
posture rather than search for one universal pace value.
