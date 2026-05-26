# esports-tycoon — pre-playtest review of the rendered "remembered me" line

**Status.** **Staged for design — awaiting GO.** Drafted 2026-05-26 by the
implementing agent (`task_20260526T012433Z_d0e00d`). This file is the
staged proposal, not the recorded sign-off. The acceptance criterion the
playtest evening depends on is "**design** confirms the bound line reads
personal not coincidental — or files a copy fix"; only a design reviewer
can close that bar. Until the **Design confirmation** block below is
filled in (reviewer name + date + GO/NO-GO), this doc stages the review
but does not greenlight the evening.

## Design confirmation

_To be filled in by the design reviewer before the founder spends an
evening on the playtest. Replace the placeholders verbatim; do not edit
the rest of the doc._

- **Reviewer:** _PENDING_
- **Date:** _PENDING_
- **Verdict:** _PENDING_  <!-- GO or NO-GO -->
- **Notes:** _PENDING_

When recorded, the verdict line should read, on its own line:
`**Design verdict.** **GO.**` (or `**NO-GO.**`). Until that line lands,
the proposal below is the implementing agent's case, not design's call.

## Evidence reviewed

The fixed scannable slot the bound precedent renders into
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

## Personal vs. coincidental — the proposal to design

The acceptance bar for the sign-off is that the bound line reads
**personal** ("the game remembered something about *me*, specifically") and
not **coincidental** ("here is a memory we happened to find that names
someone in the match").

The implementing agent's read is that the rendered line clears the bar on
these four signals — staged here so design can confirm, push back, or
file a copy fix in the **Design confirmation** block above:

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

This is the case for a **GO** verdict. It is not a GO verdict. Design's
call goes in the block above.

## Copy fix #1 — filed regardless of verdict

Independent of whether design returns GO or NO-GO on the line as it
stands, the proposal is to file this copy fix as the next sharpening of
the slot. The signal that says "this rhymes with what just happened" is
left for the reader to infer from the *content* of the summary; the line
itself never names the rhyme. The recall selector already computes that
connective tissue — `esports_tycoon.recall.RecallResult.matched_tag`
(e.g. `choke`) and `relevance_reason` (e.g. `"shared actors: rook;
tag: choke"`) — but the recap projection drops both before it lands in
`events.jsonl`, so the renderer has no way to surface them.

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

If design returns **NO-GO** on the line as it stands, this fix is the
recommended path forward (or design names a different one in the
confirmation block). If design returns **GO**, this fix lands as the
next sharpening after the playtest evening.

## Where this proposal is pinned in the repo

- **This doc** stages the review and will carry design's recorded
  verdict once filled in.
- **`tests/test_remembered_signoff.py`** asserts:
  - this doc exists and is explicitly staged for design (no recorded
    verdict can ship until design fills in the confirmation block);
  - it files Copy fix #1 with the seam it would land on;
  - the rendered shape the proposal was given against
    (`> **Remembered:** {who}, week {N} — {summary} (\`{cite}\`)`)
    still appears in the canonical Week-6 recap, so the proposal cannot
    quietly outlive the line it was given against.

A regression of any of those falsifies the proposal — at which point a
fresh review of the slot is owed *before* the next playtest evening.
