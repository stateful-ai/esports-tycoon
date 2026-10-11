# GAP29 preparation development player label

On base `64ee15f19f7acf80a2dbb7e5035d8c037128fea6` with the scoped serializer change, the copied Team Nexus world 26UHC (seed 2038, S1 W14, game 0.0.1) displays Hollowlock in the completed development note. Clicking that note's `data-pid="fa_0"` opens the actual Hollowlock profile, showing Team Nexus, age 26, bench and the signed-player career timeline. The completed note reads:

> Dev note: Hollowlock — Hollowlock pushed the starters on lotus; a focused development block could make that rotation real.

Model/effort: gpt-6.1-sol / medium. Browser surface: CUA in-app browser, local port 8439. The expected outcome was recorded before browser actions in the scoped actions.csv using scripts/playtest_log.py. Primary actions.csv and earlier shards were untouched.

The copied solo seat initially appeared taken in Join. An acceptance-only route in the ignored runtime script recovered that copied seat with a fresh opaque browser session. It did not alter the product, reuse source cookies, or change GameState. A server-launch quoting error and early connection refusal were corrected before acceptance. The browser showed Save's "World saved." response after the report/profile readback. The temporary server and accepted tab were closed afterward.

The fix supplies `dev_suggestion_handle` in the Match preparation serializer and the compact artifact serializer. It resolves the exact report player ID against current public player identity, keeps the stable profile target, and returns an empty handle for missing players so the existing frontend fallback remains available. No engine formulas, player attributes or hidden development information were added.

Validation: five focused native tests passed (known fa_0 to Hollowlock; unknown, removed and empty IDs; acting-team/player isolation; repeated read purity). Full native unfiltered pytest completed: 1279 passed in 2176.78 seconds, actual native exit 0, frozen_equal true across 613 files. Published native-receipt.json, native-full-suite.log and native-frozen-files.json preserve the completed proof. The implementation tested is the unchanged source/tests fileset in that manifest; the receipt records the pre-commit base HEAD because validation occurred before the publication commit. The fileset covers src, tests, data, scripts, config, .github and root test configuration. The completed receipt records writer PID 44464, pytest PID 5496, the native command and owned cwd; a fresh post-gate comparison also found no implementation changes.

The live source fixture and saved browser copy both hash to `4d61cb3de347969f7eea33a9894c929a62b947f19cffbb89709b31ebd2e1186c`. save-audit.json verifies byte equality and complete parsed GameState equality: 63 accepted decisions, one manager telemetry stream containing 13 snapshots, zero changed top-level fields. This read-only session added no accepted decisions. Its original browser CSV row is correctly marked not_instrumented for decision telemetry. Correction row 2 and save-audit-correction.json explicitly clarify that the preserved original save-audit.json field snaps=1 counted manager streams, not snapshots. The source and copy each retain 13 snapshots in mgr_team_nexus.

Usage is separate: usage-audit.json retains 17 events (2 page starts, 5 views, 8 visible-time slices, 1 attempt, 1 result), including lobby recovery and the bound world. Match Prep has a retained view; Save request 13 has an attempt/success pair (HTTP 200). Profile opening has no dedicated retained event. There were no API rejections observed; the disabled lobby seat is a UI block, not an HTTP rejection. Visible time is only a visibility proxy. The bounded stream does not prove complete session capture. Authentication identifiers are omitted from the published audit.

Flywheel tools were absent from this runtime's tool catalog, so findings stay local:

- Learning (high confidence, world 26UHC): existing UI handle support requires the serializer to supply the name; otherwise a valid stable ID becomes an incorrect visible label.
- Learning (high confidence, world 26UHC): the corrected display name can retain the original profile target while report/profile/save readbacks leave all 63 decisions and the full saved state unchanged.
- Pain point (high confidence, world 26UHC): copied solo worlds cannot claim their old seat via the visible Join flow even without source session mappings, requiring explicit isolated seat recovery for acceptance.
