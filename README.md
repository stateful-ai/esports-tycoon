# esports-tycoon

A management sim where the soul of the game is **persistent player
personalities** — their memories of past matches, their relationships, and a
public social feed where they react to everything that happens. You manage the
humans, not the matches.

**M0** is a one-week vertical slice on a hand-authored *Week-6-of-8* canned save,
proving the core taste-reaction: *the game remembered something.* Tone is dry
mockumentary; the game is **Vector Strike**, a fictional Valorant-flavored 5v5.
See `docs/scope-m0.md` (CompanyOS) for the full scope.

## What's here (M0.0 — tone + cast lock)

- **`docs/tone_and_cast_lock.md`** — the 1-pager pinning the voice, the fiction,
  the 5-starter cast with explicit clash pairs, and the 6 rival archetypes.
- **`saves/week6.yaml`** — the canned Week-6-of-8 save: 5 starters, 8 clash
  pairs, 6 rival archetypes, 37 precedent memory entries with stable
  `mem:<player>:<event>` IDs, and last week's scoreline + Chirper feed.
- **`esports_tycoon/cast_lock/`** — the acceptance-bar validator and the founder's
  single batched approve/reject gate.
- **`saves/week6.approval.yaml`** — the recorded founder decision, bound to a
  content digest of the batch.

Later tickets add the typed game schema, the deterministic match resolver, the
LLM content adapter, grounded citation enforcement, and the local web app.

## The cast-lock gate

```bash
python -m esports_tycoon.cast_lock review     # one-screen batch summary
python -m esports_tycoon.cast_lock validate   # acceptance-bar checklist
python -m esports_tycoon.cast_lock status     # decision vs. current content
python -m esports_tycoon.cast_lock approve --approver <you> [--reason ...]
python -m esports_tycoon.cast_lock reject  --approver <you>  --reason ...
```

A batch that fails validation cannot be approved; any edit to either file
invalidates the recorded approval until the gate is re-run.

## Tests

```bash
python -m unittest discover -s tests     # stdlib runner (no extra deps)
# or, with pytest installed:
pytest
```

Requires Python ≥ 3.10 and PyYAML.
