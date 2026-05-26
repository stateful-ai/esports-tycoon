# esports-tycoon — `recall()` → render output contract

**Status.** Locked on 2026-05-26. The seam between the deterministic
precedent-recall selector (engine-side) and the copy that renders the
"the room remembered" beat is fixed at the six named fields below.
Changes to these names or types are a breaking change for every templated
and LLM-mode renderer.

## Why this contract exists

[M1's wedge-phase plan][m1] splits the precedent-recall work across two
waves so they can land in parallel without rework:

[m1]: founder_brief_build_m1.md

- **Wave 1 — the selector.** A pure engine-side ranker
  (`esports_tycoon.recall.recall`) that takes a `WhyRecord` + `WorldState`
  and returns the top-K canned precedents that rhyme with the match. Zero
  RNG, zero LLM, zero I/O — identical inputs always yield the identical
  ordered list. The selector earns its taste through the *signal* it scores
  on (shared actors, tag overlap, active rivalry); it doesn't know about
  copy.
- **Wave 2 — the copy.** The templated narrator and Chirper authors
  (`esports_tycoon.content.templated`, plus the LLM-mode adapter when it
  ships) consume the selector's output and render the beat. The copy
  pack earns its taste through the *prose* it puts around the precedent;
  it doesn't know about scoring.

The two waves meet at one struct: `RecallResult`. Locking that struct's
shape means Wave-1 can re-tune scoring without breaking the copy pack, and
Wave-2 can re-author lines without re-shaping the selector — as long as
both waves keep producing / consuming the same six fields by name.

## The locked struct

`esports_tycoon.recall.RecallResult` is a frozen dataclass with exactly
these six fields, in this order, with these types:

| Field              | Type            | What it is                                                                                                                                                       |
| ------------------ | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cite_id`          | `str`           | The stable memory id, `mem:<owner>:<event_slug>`. The grounding handle the renderer stamps into `GeneratedContent.cites`; resolves through `WorldState.resolve_cite`. |
| `actor_ref`        | `str`           | The cast member the precedent attaches to — the owner of the `memory_log` it lives in (parsed from `cite_id`). A single-string anchor copy can bind without a world lookup. |
| `week`             | `int`           | The in-fiction week the original event happened. Lets copy render `"week {week}"` or compare against the current week to phrase "last week" / "five weeks ago". |
| `event_summary`    | `str`           | The canned one-line summary copy can quote verbatim. Stays in the save's tone (no free-form simulation text — the resolver is never inside the recall layer).   |
| `matched_tag`      | `str \| None`   | The authored tag from the entry's own `tags` list that rhymes with this match's target tag vocabulary — preserves the entry's casing. `None` when the entry surfaced on actor or rivalry overlap alone. Picked deterministically by entry-tag order. |
| `relevance_reason` | `str`           | A short, structured explanation of *why* this entry ranked, assembled from the matched signals in priority order (`"shared actors: ...; tag: ...; active rivalry: ..."`). Always non-empty — the selector only yields entries with ≥1 non-zero signal. |

`RecallResult` is frozen — mutating an instance is an error — and the field
order is part of the contract (tests pin it via `dataclasses.fields`). Add a
field only by extending Wave-1 *and* Wave-2 together in the same change.

## How Wave-1 fills the fields

The selector scores every memory entry in the world against the match's
`WhyRecord` on three signals — shared actors, tag overlap, active rivalry —
and stable-sorts by `(-actor_score, -tag_score, -rivalry_score)`. From the
top-K scored `Precedent` objects, it projects each to a `RecallResult`:

- `cite_id` ← `entry.id` (the stable, validated memory id).
- `actor_ref` ← owner segment parsed out of `entry.id` via `MEMORY_ID_RE`.
- `week` ← `entry.week`.
- `event_summary` ← `entry.summary`.
- `matched_tag` ← the first tag in `entry.tags` (authored order) whose
  lowercase form is in the matched tag set; `None` if no tag overlapped.
- `relevance_reason` ← a `"; "`-joined string in score-priority order:
  `"shared actors: <sorted>"`, then `"tag: <matched_tag>"`, then
  `"active rivalry: <sorted>"`. Multi-value clauses are sorted
  alphabetically so the string is byte-identical across runs.

Because the projection is pure and deterministic, the same `WhyRecord` +
`WorldState` always yields the same `list[RecallResult]` — same order,
same fields, same bytes.

## How Wave-2 reads the fields

A copy template binds fields by name and never re-derives the same info
from the world:

```python
# Wave-2 (illustrative — actual lines live in the cast voice pack)
def render_remembered_beat(r: RecallResult) -> str:
    if r.matched_tag is not None:
        return f"the same {r.matched_tag} as week {r.week}: {r.event_summary}"
    return f"week {r.week}, with {r.actor_ref}: {r.event_summary}"
```

For grounding, the renderer stamps `r.cite_id` into
`GeneratedContent.cites`; the recap's "What the room remembered" section
resolves the cite back through the world. The copy never invents a cite,
and the selector never invents a line.

If a copy template needs *more* than the six fields (e.g. the full actor
list for a tighter beat-actor filter), it resolves through the world by
`cite_id` — never by passing extra fields through the seam. This keeps the
contract small enough to reason about and large enough to render against.

## What the doc and tests pin

- `tests/test_recall.py :: TestRecallResultContract` asserts the locked
  fields are exactly these six in this order, that every field is populated
  from the canned save as documented, and that `matched_tag` /
  `relevance_reason` follow the rules above.
- `tests/test_recall.py :: TestDocumentation` asserts this doc exists,
  back-tick-cites every locked field, names both Wave 1 and Wave 2, and
  that `esports_tycoon/recall.py` points at this doc — so the code → docs
  jump cannot silently rot.
- The selector's purity (no RNG, no LLM, no I/O) and the week-6 → week-2
  acceptance bar live in the existing `TestPurity` /
  `TestWeek6SurfacesWeek2Precedent` classes; this doc does not duplicate
  them.

## Out of scope for this contract

- **The scoring weights themselves.** The signal priority (actors → tags →
  rivalry) is Wave-1's; it can re-tune without breaking the seam.
- **Cast voice lines.** The per-character templates that consume
  `RecallResult` are Wave-2's; they can grow without breaking the seam.
- **The LLM-mode adapter.** It binds the same `RecallResult` fields as the
  templated backend; landing it is its own ticket but the seam doesn't
  change.
