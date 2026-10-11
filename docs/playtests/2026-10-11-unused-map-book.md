# Stored map-book debrief wording

Copied career 26UHC, seed 2038, S1 W21, gpt-6.1-sol / medium. Browser acceptance
used owned localhost port 8524. Source base: 20273cd7ab885e7d409dec46f511d915d6e08ff4
with only the three-line Dashboard wording change. No fixture was replayed.

The observed quarterfinal debrief had called historical Lotus knowledge
"prepped Lotus (never played)" although the booked session resolved on Ascent.
The initial candidate Dashboard read **Map book: available on Ascent, Split · unused on
Lotus (not played)**. Independently opening Match > Prep still showed
**ascent retake playbook +2.1**, knowledge **+2.12**, stamina **-4**.

Three before-action intent rows cover Dashboard, Match > Prep and Save. The
fresh browser initially opened the lobby; an owned fixture harness restored its
membership to the copied career. No auth/session values are published.

Saved-career readback remained byte-identical to the copy baseline: SHA256
`c35f370c1525615cc8d5c4d2b1187535e8159d7ff5acad74aec10ddbd78f4051`.
All 85 pre-existing accepted decisions and telemetry snapshots remained intact;
zero new accepted decisions were expected or recorded. Read-only navigation and
Save are outside accepted gameplay decision coverage: all three rows are marked
`recorded` for the separate browser usage stream, with zero missing expected
gameplay decisions. The original annotations conflated these streams; the
published shard corrects only `analytics_status` and `analytics_evidence`.

Usage was isolated by the fresh browser's session-start identifier, excluding
the copied sidecar history. Retained evidence: one lobby view, one Dashboard
view, one strategy view, one Prep view, and one Save attempt/result pair.
Visible-time events are visibility proxies. No gameplay request or fixture
advance was made in this acceptance session. Session CSV and audit JSON are in
the [exact three-row shard](2026-10-11-unused-map-book/actions.csv), supplied to
root for sequential append; the canonical CSV was not edited here. The original
three-row CSV SHA256 is
`79713482c26f1f07fafae038c48ba538722a7dc81fcb1029c9b17140642ffc27`;
the [annotation receipt](2026-10-11-unused-map-book/annotation-receipt.json)
verifies equality of all 19 other fields, including step 2's empty evidence.

Durable original receipts are published alongside the shard:

- [Dashboard DOM](2026-10-11-unused-map-book/dashboard-dom.txt): exact original
  browser tool text, extracted from the retained acceptance transcript.
- [Prep DOM excerpt](2026-10-11-unused-map-book/prep-dom-excerpt.txt) and
  [Save DOM excerpt](2026-10-11-unused-map-book/save-dom-excerpt.txt): exact
  original filtered tool text. These were not full DOM captures.
- [Original audit](2026-10-11-unused-map-book/audit.json) and
  [complete local save comparison hashes](2026-10-11-unused-map-book/save-comparison.json).
  Full saves remain local; only comparison scope and hashes are published.
- [Original own-session usage](2026-10-11-unused-map-book/usage.sanitized.jsonl) and
  [copied baseline usage](2026-10-11-unused-map-book/usage.baseline.sanitized.jsonl):
  session identifier redacted; other raw event fields retained. Seven final
  Prep visible-time slices include four after the original audit's three.
- [Source-to-publication manifest](2026-10-11-unused-map-book/manifest.json):
  source paths, exact original transcript line hashes, timestamps, transformation
  scope, published hashes, and instrumentation limits.

No screenshots were captured during the original acceptance session. No browser
actions were replayed for this publication. The original CSV timestamps,
expectations, outcomes and fields remain unchanged. Historical acceptance used
the dirty base recorded in the CSV; the initial published source head was
`c0b6459e6d27eaf0b8e30a82bc312b8a5b657d61`, whose CI was queued at handoff.
Later review identified two wording errors in that initial candidate. The full
preparation edge includes scouting, institutional knowledge and coaching. Also,
`knowledge.prep_bonus` averages all scheduled fixture maps before the series;
books for unplayed maps can still contribute to the shared preparation edge.
The final wording preserves **Preparation:** and says **stored book on Ascent,
Split (played) · stored book on Lotus (not played)**, making no causal claim
about book use. Static source review confirmed this in `campaign._fixture_plans`,
`preparation.prep_edge_breakdown`, and server `_your_calls`; no formula changed.
The original low-tier fixture hides the numeric edge, so its original acceptance
did not verify higher-tier visible numeric edge wording. The original receipts
and observations are preserved as evidence of the earlier candidate.

Fresh corrected acceptance on source head
`4bbaa16042d8e942cf7782871121402248bd79fc` used an authorized named Playwright
CLI fallback after CUA's browser inventory became empty. Its separately logged
before-action expectations, outcomes and usage annotations are in
[confirmation/actions.csv](2026-10-11-unused-map-book/confirmation/actions.csv).
Dashboard showed the final wording above; Match > Prep independently retained
the Ascent artifact. Save succeeded with HTTP 200. Complete save bytes still
matched the original SHA256 and all 85 decisions and snapshots remained intact.
The fixture still hides the numeric edge; no higher-tier browser acceptance is
claimed. No fixture was replayed.

[Dashboard DOM](2026-10-11-unused-map-book/confirmation/confirmation-dashboard.yml),
[Dashboard screenshot](2026-10-11-unused-map-book/confirmation/confirmation-dashboard.png),
[Prep DOM](2026-10-11-unused-map-book/confirmation/confirmation-prep.yml),
[Prep screenshot](2026-10-11-unused-map-book/confirmation/confirmation-prep.png),
[Save DOM](2026-10-11-unused-map-book/confirmation/confirmation-save.yml), and
[independent audit](2026-10-11-unused-map-book/confirmation/confirmation-audit.json)
are exact original receipts from this fresh session.
[Its manifest](2026-10-11-unused-map-book/confirmation/manifest.json) maps source
bytes to published hashes and separates all retained other-session usage from
the final page session. Two fresh rows have recorded usage evidence; zero new
gameplay decisions were expected. Flywheel records 0189–0191 preserve the
corrected causal interpretation, fresh readback and transport recovery.

Flywheel inheritance used the eight most recent esports-playtest findings.
After play, records 0182/0183 capture stored-book versus session attribution and
unchanged accepted decisions; 0184 preserves the copied-identity recovery pain.

`node --check src/esports_sim/web/static/app.js` and `git diff --check` passed.
Local pytest and expensive gates were not run under the user's explicit
override. This bounded copy change has no simulation, RNG, save-schema, or
server-formula changes; this session does not establish preparation causality
or balance.
