# Stored map-book debrief wording

Copied career 26UHC, seed 2038, S1 W21, gpt-6.1-sol / medium. Browser acceptance
used owned localhost port 8524. Source base: 20273cd7ab885e7d409dec46f511d915d6e08ff4
with only the three-line Dashboard wording change. No fixture was replayed.

The observed quarterfinal debrief had called historical Lotus knowledge
"prepped Lotus (never played)" although the booked session resolved on Ascent.
The corrected Dashboard reads **Map book: available on Ascent, Split · unused on
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
`not_instrumented` for that stream, with zero missing expected decisions.

Usage was isolated by the fresh browser's session-start identifier, excluding
the copied sidecar history. Retained evidence: one lobby view, one Dashboard
view, one strategy view, one Prep view, and one Save attempt/result pair.
Visible-time events are visibility proxies. No gameplay request or fixture
advance was made in this acceptance session. Session CSV and audit JSON are in
`runs/playtests/2026-10-11-unused-map-book/`, supplied to root for sequential
append; the canonical CSV was not edited here.

Flywheel inheritance used the eight most recent esports-playtest findings.
After play, records 0182/0183 capture stored-book versus session attribution and
unchanged accepted decisions; 0184 preserves the copied-identity recovery pain.

`node --check src/esports_sim/web/static/app.js` and `git diff --check` passed.
Local pytest and expensive gates were not run under the user's explicit
override. This bounded copy change has no simulation, RNG, save-schema, or
server-formula changes; this session does not establish preparation causality
or balance.
