# PR #376 forward integration

Source commit 8f3ee9b5864bbc7a878440ce3517035d3b7aa777 normally merges original PR head ad2316b95794289a8681391641660ed9a55641d5 with actual main 0401b8a810cdcd75aae7ba6cdd8fe3d22c2fb96b.

All twelve historical evidence add/add conflicts were line-ending only. Main blobs are retained byte-exact. Canonical history is unchanged from main; all eight MEDIA observations match the scoped CSV in all 21 fields. No new play observations or gameplay actions were made.

The preservation receipt inventories all parent and integrated tracked file OIDs, plus actual raw SHA256 and normalized Git OIDs for source, test, data, script, workflow and root paths. Changes against main are limited to the existing six MEDIA implementation and regression paths; MEDIA/state/test blobs remain identical to the reviewed PR source.

No local tests, CJS, syntax checks, validators, simulations, gates, application reports, hooks, browser/server actions or save mutations were run. Authored coverage remains UNRUN locally. Earlier receipts qualify earlier source only; exact published-head remote CI and independent root review are required.
