# Free-movement match engine

The destination is a match resolver that plays the same kind of game the
viewer depicts: ten bodies move through physical space, see only through real
angles, make per-tick motor and combat decisions, and create the event log from
those interactions. Callouts remain tactical vocabulary; they are no longer
the movement cells.

## Milestone 1: Ascent physical resolver

Ascent declares `movement_model: free` because its traced geometry includes
the doorway spans needed to derive walls. The engine now offers policies these
heading-relative controls:

- forward and backward;
- strafe left and right;
- walk or run;
- the existing bounded turn increments.

The resolver sub-steps movement against the authored floor union, treats every
prop as body collision, permits room transitions only across graph-adjacent
seams and their doorway span, and treats a shut mechanical door as a wall.
Player callouts are derived from physical position after a crossing.

Visibility uses exact segment intersections with rectangular floor regions,
full-height props, doorway spans, and closed doors. It does not spatially
sample every few pixels, which keeps large deterministic experiment batches
practical. The viewer receives authoritative per-tick positions for freely
steered movement; it does not reproduce collision or speed formulas.

`advance` remains a compatibility autopilot along an engine-authored route.
The shipped heuristic therefore behaves as before until we deliberately teach
it physical steering, while external and learned policies can use the new
controls immediately. The learned-player checkpoint contract is bumped to v4
because the pinned motor vocabulary changed; old checkpoints fail closed.

## Next milestones

1. Move the heuristic from route autopilot to waypoint-seeking physical
   steering, including stopping distance, shoulder peeks, counter-strafing,
   teammate separation, and path recovery.
2. Make shoot, aim, reload, and equip explicit per-tick actions. Replace
   one-roll duels with damage, fire cadence, recoil, movement inaccuracy,
   armor, and tradeable time-to-kill.
3. Give utility physical origins, trajectories, volumes, durations, and
   destructible or suppressible interactions rather than callout-only effects.
4. Put the spike at a physical coordinate and make plant and defuse channels
   depend on range, facing, interruption, and partial defuse progress.
5. Trace doorway openings for the remaining maps, validate each map's floor,
   pacing, balance, and paint alignment, then switch it from `routed` to `free`.
6. Version the observation again when policies receive safe local geometry
   probes, teammate body positions, weapon state, and objective coordinates.

## Acceptance gates

- Same seed and policies produce a byte-identical event log.
- Policies rank only engine-supplied legal controls and never receive hidden
  enemy truth.
- The viewer consumes emitted positions; it owns no physics.
- Floor audit, 25–35 second attacker rotation, faster defender rotation, and
  45–65% attack-round balance remain green per migrated map.
- The full 300-match gate after milestone 1 produced 52.5% attacker rounds on
  Ascent, 228/300 favorite wins, and eliminations, defuses, and detonations.
