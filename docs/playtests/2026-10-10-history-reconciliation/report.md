# Cumulative playtest evidence review, October 10

The append-only log now contains 665 unique observations across 40 session IDs,
11 tested commits, and game version 0.0.1. The raw 664-row history is an exact
prefix of the current file. These files are working-tree evidence; the reviewed
history PR362 still contains its original 597 rows.

| Observation outcome | Rows |
| --- | ---: |
| Met | 575 |
| Partial | 38 |
| Blocked | 35 |
| Unexpected | 17 |

| Historical capture annotation | Rows |
| --- | ---: |
| Recorded | 397 |
| Not instrumented | 228 |
| Unverified | 34 |
| Missing | 1 |
| Unannotated | 5 |

These are observation counts, not distinct game decisions or a common coverage
denominator. A recorded row may refer to accepted-decision telemetry, browser
usage, or both. Navigation, cancelled controls, diagnostics and offline audits
can legitimately create no accepted decision. Copied world codes are not
independent production players. Model/effort counts describe the recorded test
mix and cannot establish comparative model performance.

The latest real media/sponsor session independently matched all three accepted
decisions against the saved action log and paired all five retained browser
requests with their outcomes. Decision and request coverage remain separate.
Its report is in `../2026-10-10-media-sponsor/report.md`.

This review also recovered original flavor-choice and advance evidence. The
agent prelogged a new offline correction as October10 flavor-hint step6. Root
independently read the retained before/end saves: unchanged 27-action prefix,
exact accepted decisions at indices27/28, and unchanged five-snapshot prefix
followed by one new weekly snapshot. The correction row was appended verbatim;
the old October8 annotations and their timestamps remain unchanged. Original
steps1-5 remain lost, and no old test exit status is inferred. The verification
script initially assumed snapshots were a list and action records included an
index; readback established the actual manager-keyed snapshot dictionary and
list-index convention before any successful receipt or canonical append.

The single historical missing event is the October6 mentor assignment. At
current checkout042d86d, the web handler explicitly records accepted mentor
assignment and clearing before saving. Existing later playtest evidence has
also recorded mentor decisions. This does not retroactively fill the old gap.
The five unannotated rows belong to an interrupted October8 budget session;
that session's existing step7 correction explains that the persisted save
remained at baseline and the lost in-memory release/signing span could not be
reconciled. They remain unclassified instead of claiming durable changes.

Runtime metadata is preserved as supplied: 215 rows explicitly identify the
configured gpt-6.1-sol/medium agents, 163 report unknown/not exposed, and 287
retain an older generic GPT-6 label whose exact runtime ID was unavailable.
No unavailable root model or effort has been guessed.

Evidence in the sibling history-reconciliation folder includes the new single
correction row, agent audit, independent root verification, cumulative audit
and append receipt. No gameplay state, usage stream, old CSV observation or
user career was modified by this offline review.
