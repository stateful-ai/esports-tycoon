# Accepted web choice telemetry

New web `set_lineup` and `set_game_plan` records keep their legacy coarse
keys and add `choice_encoding=json-v1`. `ActionRecord.params` remains a flat
string map; old rows and saves need no migration. Do not interpret missing
new keys in historical rows as an automatic choice.

For `set_lineup`, `agent_choices` is compact JSON of the validated applied
player-to-agent lock map, with sorted object keys. `{}` explicitly clears all
locks to auto; `null` means that field was not changed. `lineup_ids` and
`player_ids` are compact JSON arrays in applied dressing order, respectively
for default and per-map choices. `null` means unchanged. A default `[]`
explicitly selects automatic completion. Per-map choices require five IDs.
Stale default/per-map IDs are filtered by the existing roster contract before
recording. Lists have at most five entries and agent maps at most roster size;
IDs and agent values come from current validated game state. No free-text,
browser query payloads or hidden opponent statistics are copied into choices.

For `set_game_plan`, `starter_ids` is the applied ordered array; `[]` uses
the standing five. Each of the five dial keys stores the applied clamped float
as a string, or `""` for the standing book. `team_talk` stores the validated
approach or `""` for no talk. Existing `site_focus` and `focus_target` empty
strings mean no override. A plan replaces the previous plan; absent fields
therefore clear overrides rather than preserving them. `clear_game_plan`
continues to identify the separate action that removes the plan entirely.

Repeated accepted no-ops still produce decisions. Rejected requests do not;
mixed lineup requests are completely validated before mutation. The gameplan
and lineup read endpoints remain the public setting readback. Browser usage
retains coarse attempts/results separately and receives no new payload fields.

Manager/CLI/MCP policy actions already record validated `player_ids` or the
applied GamePlan model using their existing scalar codec. These source-specific
encodings remain unchanged: reports must check `source`, `kind`, and
`choice_encoding` before decoding JSON. No action vocabulary, observation,
legal mask, policy encoder, checkpoint version, or simulation formula changes.
