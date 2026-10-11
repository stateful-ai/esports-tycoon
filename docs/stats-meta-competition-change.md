# Stats Meta competition selection

The root browser session `2026-10-11-early-samples-stats-usage-root`, step 6,
opened Stats, selected Challengers, opened Meta, then selected Top flight.
Both views showed Jett 10.5%, Lotus 24 team maps, aggression 45.2 and pace 49.7;
the Challengers selection also showed Top flight clubs Chao Phraya Owls and
Berlin Wolves under Team tendencies. The observed candidate was
`cde009e5221b5cd4f90af8d49d9395004a6c7e3d`, tree
`addcdcebba03621eb11d95dda25187fb56eb25d8`, combining PRs 427/428/430/431
above main `0194b426f9c141591959443f44e092ed873e5df4`.
This is prior-build evidence, not acceptance of this change.

Safe public DOM origin files (in the root acceptance worktree, not published):
`runs/playtests/2026-10-11-early-samples-stats-usage-root/step06-challengers-meta.dom.txt`
and `step06-topflight-meta.dom.txt`. Only the public observations above are
retained here. No raw save, authentication material, usage payload or private
page identifier is included. The root session shard is not claimed published.

Source cause: `stats()` sends `league_tier` to `/api/stats` but previously sent
an unqualified `/api/meta`. `meta_view()` read global `meta_report()` totals;
`stats_view()` also iterated default Top flight standings for its team rows.

The Stats frontend now sends its competition to both endpoints. Team rows use
that tier's standings; public agent picks and map tactics are aggregated by
the played fixture's tier at map completion, including both sides. The same
aggregation helper maintains the existing global public map totals. No RNG,
engine tuning or outcome calculation changes. GET endpoints remain pure and
consume captured public aggregate facts, never current private scouting plans.
Default `/api/meta` means Top flight; invalid integer tiers follow the existing
Stats fallback to Top flight. Nonnumeric HTTP inputs retain FastAPI validation.
Non-Stats callers of `meta_report()` retain its global default and original shape.
Global balance-patch selection still consumes the original global player-agent
usage; patch notes and buff/nerf truth apply to both competitions and are labeled
global in the UI.

Schema 38 adds `map_meta_stats_by_tier`. Migration starts it empty: old global
tactic sums have no tier identity, and stored fixture player lines have no
agent IDs. Reconstructing historical picks from today's affiliations or agent
preferences would fabricate evidence after transfers. Completed fixture map
counts can be read safely, so older maps remain visible while their agent and
tactic samples are explicitly unavailable. Responses expose completed,
recorded and legacy team-map counts, plus each map's recorded sample. Percentages
and tactic averages use only that recorded competition sample. New campaigns
record from their first map; migrated campaigns accumulate samples going forward.
Both public global and competition aggregates reset at season rollover.

Created from actual main `0194b426f9c141591959443f44e092ed873e5df4`, then
rebased normally onto actual main `fd0df90d5aa691464e67c70e28480451e005d017`
after the root merged finite playtest history PR 414. Its existing history
is retained. No new source-head runtime acceptance is claimed.

Reviewed all 39 open PRs returned by the 100-result query on 2026-10-11. No
existing PR addresses this Meta data gap. PR 431 independently adds coarse
competition selection usage and is not a dependency; this change preserves its
handler when later composed. Existing playtest histories remain untouched.

Authored regressions cover competition isolation, both sides, multiple maps,
public-read purity, independence from current roster/tactics, global patch
invariance, old aggregate compatibility, schema migration, honest legacy
counts, future sample accumulation, deterministic recording, save round-trip,
empty/default/invalid-tier contracts, team rows, and actual frontend queries,
selection handlers and sample rendering.

All local tests, CJS execution, syntax checks, validators, simulations, gates,
application analytics reports and hooks were intentionally skipped under the
explicit user waiver. Tests are **UNRUN**, CI is **UNQUALIFIED**, and no new-head
runtime acceptance is claimed. Only source reading and Git/file bookkeeping
were performed. This draft is prepared for root review before merge.
