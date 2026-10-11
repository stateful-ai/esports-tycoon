# PR 373 integration review

Original PR head: 5884eeb4f1663630b725deaa43cc98897f35e489.
Integrated actual main: 0401b8a810cdcd75aae7ba6cdd8fe3d22c2fb96b.

This normal forward merge preserves both parent histories. Source changes merged without conflicts. Sixteen add/add conflicts concerned historical evidence; their canonical paths retain main's blobs. Each original PR conflict blob is retained byte-exact in retained-pr373-5884eeb4, with path and blob IDs recorded in manifest.json. Canonical actions.csv is inherited unchanged from main; no new playtest was conducted.

Static review inspected the entire PR source/test delta, the settlement implementation, weekly accounting and primary mirrors, per-seat serializers, CLI and browser renderers, original root review, discussion comment 4239346985, and current-main solvency ordering. The CLI finding is addressed by general income/expense labels, separate primary-seat actual upkeep, and signed income. Actual bank mutations, RNG use, prize awards and final solvency ordering remain unchanged. The weekly_tick compatibility function retains its historical net-return contract. No current-head code finding was identified.

All original test assertions remain unchanged. Coverage is UNRUN on this integration head: three settlement facility configurations, two multi-seat/state-equality/negative-adjustment campaign cases, and three CLI cases. Existing historical 1260-test and 1257-test receipts describe their older frozen sources and do not validate this integrated tree.

Per explicit user waiver, no local tests, syntax validators, simulations, gates, application reports, commit hooks, browser playtests, server actions or save mutations were run. Only source review and Git raw-blob retention checks were performed. New exact-head remote CI and root review govern the subsequent merge decision; this agent does not merge or declare readiness.