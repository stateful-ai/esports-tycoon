# PR 369 source and history qualification

Merged authoritative main `300462da2ae10a55c6106918c9de209638f85406` into original reviewed head `5b583f60980690d64c4eaa0c816291b94ab9ed1f`. The overlay feature added/deleted source lines are unchanged. All published main playtest Git blobs and the canonical 765 rows remain exact.

Eighteen conflicts were newline-equivalent. Main's README omits exactly the final historical native-test paragraph present in the original branch. Root reviewed that reverse-prefix difference before resolution: the authoritative main README is retained byte-for-byte, and `historical-original/README.md` archives the original full README from its Git object.

The historical **1285 passed in 5155.67s**, exit 0, and **616 frozen source paths** apply only to original head `5b583f60980690d64c4eaa0c816291b94ab9ed1f` and the preserved historical manifests. The earlier 1262 native gate and all browser receipts also apply only to their original source. Original artifact references remain preserved. `historical-changed-source.zip` contains exact old-head Git bytes for changed source references; its members and hashes are recorded in the JSON proof.

No local tests, expensive gates, or fresh browser acceptance were launched for this integration. Old-head CI does not validate the new integrated source. Fresh remote CI is required and remains pending at publication. `source-and-history-qualification.json` records conflict hashes, exact source-feature deltas, complete current src/tests/data/scripts raw and Git manifests, canonical hash, published artifact blobs, and historical archives.
