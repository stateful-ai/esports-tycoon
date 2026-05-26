# esports-tycoon — pre-playtest sign-off on the rendered "remembered me" line

**Verdict.** **GO.** Recorded 2026-05-26.

**Evidence.** The fixed scannable slot the bound precedent renders into
(`esports_tycoon/runner/recap.py`, `REMEMBERED_SLOT_LABEL`) was reviewed
across every Week-6 practice × stance combination at seed 6, plus seeds
1–10 against the default branch, in `templated` mode against the canonical
save. The rendered line is identical across all of them (a single
precedent binds for the canonical fixture):

> **Remembered:** Rook, week 5 — Overcast threw a 9–3 scrim lead the day
> before the Northwind series; Rook blamed comms, not aim.
> (`mem:rook:scrim_w5_choke`)

This is the line the founder will be reading first in the screenshot during
the evening playtest, sitting above `## The fixture` per the contract
locked by `tests/test_run_log.py :: TestRecapSurfacesBoundPrecedent`. The
slice's narration reads "Mariana and Aurelie came apart" / "Mariana came
apart" depending on stance — Mariana is Rook, so the rhyme is *the IGL
choking again on a must-win*.

## Personal vs. coincidental — the design call

The acceptance bar for this sign-off is that the bound line read
**personal** ("the game remembered something about *me*, specifically") and
not **coincidental** ("here is a memory we happened to find that names
someone in the match").

The rendered line clears the bar, on these four signals:

1. **The anchor is a person, not a category.** "Rook, week 5" leads with
   the cast member by alias — the same alias the founder sees in the
   standouts row and the Chirper feed. The slot is owned by a face, not a
   tag.
2. **The summary is character-specific, not generic.** The canned entry
   names Rook *twice* and describes the kind of failure ("threw a 9–3
   scrim lead", "blamed comms, not aim") rather than a neutral event
   ("a scrim happened"). The text would not read interchangeably for any
   other roster member.
3. **The pattern rhymes with what just happened.** Every branch lands
   Rook in the "came apart" row on a must-win loss; the precedent is
   herself, on a thrown lead, the day before another must-win series.
   That is the exact shape of the beat the recap is asking the reader to
   feel.
4. **The cite is stamped verbatim.** `(\`mem:rook:scrim_w5_choke\`)`
   appears in the slot — the same ID that resolves at the bottom of the
   recap and that the run-log carries on `match_resolved`. The grounding
   handle is right there, not behind a click.

The line clears the bar. **Go for the founder's evening playtest.**

## Copy fix #1 — file, do not block

The line clears the bar *softly*. The signal that says "this rhymes with
what just happened" is left for the reader to infer from the *content* of
the summary; the line itself never names the rhyme. The recall selector
already computes that connective tissue —
`esports_tycoon.recall.RecallResult.matched_tag` (e.g. `choke`) and
`relevance_reason` (e.g. `"shared actors: rook; tag: choke"`) — but the
recap projection drops both before it lands in `events.jsonl`, so the
renderer has no way to surface them.

That is the next sharpening of this slot, not a blocker for tonight:

- **Where:** `esports_tycoon/runner/recap.py` (the slot render) and
  `esports_tycoon/runner/events.py` (`MatchResolved` would carry the
  bound precedent's `matched_tag` / `relevance_reason` alongside
  `cites`, so the recap stays a pure projection of the log).
- **What:** Surface the rhyme word inline, so the line reads as
  *causal*, not *adjacent* — e.g.
  `> **Remembered:** Rook, choke — week 5: <summary> (\`<cite>\`)`
  or
  `> **Remembered:** the same choke as week 5, with Rook — <summary>
  (\`<cite>\`)`. The exact wording is design's call; the structural
  ask is that the matched signal lands in the slot.
- **Why it matters:** The line is the screenshot's first beat. For the
  founder (who built the system) the inference is free. For the next
  playtest cohort the inference is not free, and the slot drops back
  toward *adjacent* without the rhyme word.
- **Scope:** Single-seam — a new event field, a one-line render, and the
  matching adapter wiring. Does not touch `RecallResult` (the selector
  already produces what the renderer needs), and does not unfreeze any
  M1-scope ticket.

This fix is logged here so a future playtest sign-off does not need to
re-discover it from scratch, and so a future change to the slot lands
with a deliberate edit to this doc rather than a silent drift.

## Where this decision is pinned in the repo

- **This doc** is the durable record of the GO verdict.
- **`tests/test_remembered_signoff.py`** asserts:
  - this doc exists and records a `GO` verdict;
  - it files Copy fix #1 with the seam it would land on;
  - the rendered shape it signed off on (`> **Remembered:** {who}, week
    {N} — {summary} (\`{cite}\`)`) still appears in the canonical
    Week-6 recap, so the sign-off cannot quietly outlive the line it
    was given against.

A regression of any of those falsifies the sign-off — at which point a
new playtest review of the slot is owed *before* the next playtest
evening.
