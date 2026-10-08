# Release confirmation acceptance

Tested origin/main `3ac34df` plus this change, on the isolated mentor-telemetry
checkout at port 8441. Runtime: gpt-6.1-sol, medium. The session CSV is separate
from the shared append-only gameplay history. Seed 2038, fictional sandbox,
Team Nexus, world ASQB4, season 1 week 1.

Player question: does the release confirmation tell me what the club will pay?
Phantom earns 6,500 cr/week. The server serialized 78,000 cr, the browser
confirmation said `Release Phantom? Severance = 78,000 cr.`, the successful
release response repeated 78,000 cr, and balance changed from 487,320 to 409,320.
The roster changed from five to four and Phantom disappeared from the roster
readback. Economic behavior is preserved. `evidence.json` retains these reads.

The two CSV intentions were logged before acting. World setup used direct HTTP
in the browser request context; release used the visible Squad button and real
browser confirmation. The save was explicitly flushed through HTTP afterward.
Saved decision telemetry contains exactly one action, index 0: release Phantom,
Team Nexus, source web, season 1 week 1. Decision coverage is 1/1 completed
manager decisions; setup/navigation are not manager decisions. Weekly telemetry
snapshots are 0 because no week was advanced. See `decision-report.txt`.

Browser usage evidence is isolated by world ASQB4: one release attempt and one
successful result share request id 11, with dashboard and club/squad views.
Direct HTTP setup/readbacks/save do not emit browser usage events. Retained
visible time is a visibility proxy, and no claim of full session coverage is
made. See `usage.jsonl` and `usage-report.json`.

An earlier disposable setup world NQWPT was created before this logged session;
its navigation was blocked by the automatic first-week guide. Closing the guide
through its visible Close button resolved this in ASQB4. No release occurred in
the earlier world. Flywheel MCP tools are unavailable in this runtime. After
acceptance, the parent supplied a Python recorder fallback in the Agora checkout;
recent/search then inherited findings 0018/0019 and record saved learnings
0020/0021 plus pain point 0022. The required pre-play read was missed; this
limitation is retained rather than presenting the later read as a pre-read.

Learnings: negotiated severance can differ from six weeks of salary; the roster
serializer and release action should share one pure helper. A numeric browser
confirmation now agrees with the actual debit on the observed seed. Pain point:
automatic first-week help intercepts navigation until explicitly closed.

The fallback case is covered by a regression test with release_fee=0 and salary
6,500: the roster preview and debit both resolve to 39,000 cr. This browser
session only exercises the negotiated 78,000 cr clause.

Release validation: full `pytest -q -n2` passed all 1,183 tests in 4,738.86 seconds.
Targeted release regressions passed 2 tests; logger checks passed 3 tests.
`node --check` passed for app.js. Diff checks passed outside the preserved CSV's
CRLF and captured UI whitespace. No sim/data behavior or economic-rule changes
trigger balance, pacing, floor, or snowball gates.
