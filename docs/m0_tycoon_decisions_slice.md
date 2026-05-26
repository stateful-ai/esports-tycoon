# esports-tycoon — Hold: TrainingDecision slice → M0.2 (post-gate)

**Status.** **Held to M0.2.** Recorded 2026-05-26. The `TrainingDecision` slice
named under "Frozen post-gate" in [`docs/founder_brief.md`](founder_brief.md)
(the ninth of the nine hardening/feature tickets the brief parked behind the
playtest gate) is annotated here as the **post-gate next milestone (M0.2)** for
the player-development loop, distinct from M1's wedge-phase reproducibility
floor ([`docs/m0_gate_decision.md`](m0_gate_decision.md) §*Frozen items now
owned by M1*). M1 ships the reproducibility floor under the canonical schema;
M0.2 is where the *feature* surface this doc names lands.

The M0.1 playtest gate has fired
([`docs/playtest_m0_1.md`](playtest_m0_1.md): **PASS**, recorded 2026-05-26;
re-affirmed in [`docs/m0_gate_decision.md`](m0_gate_decision.md)). The
in-bound condition for opening this slice is therefore satisfied — but the
slice is not built. This doc is the durable record of *why* it was held, *what*
it will introduce, and *what regression bar* it must stay under as it lands.

## The slice

The `TrainingDecision` slice extends the manager's decision surface from the
single-week "practice focus + tactical stance" pair (which the M0.1 slice
already exercises end-to-end against the canonical save) into a recurring
training loop with per-player attribution. Three named field names land
together — they are the slice's seam, and a partial landing would split the
loop in half:

- **`Player.skills`** — a per-player vector of named skill ratings (the
  granularity the resolver currently approximates from `traits` + recent
  `memory_log` sentiment via `esports_tycoon.resolver._form` and
  `esports_tycoon.resolver._skill_for`). Making these first-class means the
  resolver no longer has to infer "form" from the memory log alone, and a
  training week can move a single skill rather than tilting the whole player.
- **`training_points`** — the budget the manager spends each week on training
  choices. Earned per week (and bonus-earned on outcomes the slice will
  define), spent on the decisions the next field enumerates. The points
  *replace* the current open-ended `practice_focus` string with a typed,
  budgeted choice: the M0.1 string is the input the M0.2 slice generalises.
- **`decision_effects`** — the typed table mapping each training decision to
  the `skills` delta it applies (plus its `training_points` cost). The
  resolver reads decision_effects → skills → match outcome; the renderer
  reads decision_effects → `WhyRecord.key_moments` to attribute *which*
  training week's decision rhymed with the play that just happened.

Together these three are the smallest seam that makes a player-development
loop legible to both the resolver and the renderer without re-shaping the
canonical save's invariants (cite IDs, memory ownership, grounding).

## Why this was held

The M0.1 minimum-playable rescope
([`docs/m0_1_minimum_playable_rescope.md`](m0_1_minimum_playable_rescope.md))
narrowed the gate to a single-week screenshot of the "remembered me" beat.
Adding three new player fields, a new currency, and a new decision table to
that surface would have:

1. **Re-shaped the canonical save** — any field added to `Player`/`Decisions`
   flows through `WorldState`, the loader, the resolver, the templated render,
   and the run-log. That is exactly the convergence work
   [`docs/m0_1_minimum_playable_rescope.md`](m0_1_minimum_playable_rescope.md)
   removed as a precondition.
2. **Moved the playtest target** — the gate is the screenshot of the
   precedent-recall beat. A second decision surface in the same slice would
   give a failing playtest two plausible suspects (recall, or training), and
   the gate would not have routed cleanly. Per the wedge-phase principle in
   [`docs/founder_brief.md`](founder_brief.md), this is the kind of work
   that is "out of scope until the gate fires."
3. **Broken the regression bars** — see the next section. Both bars are
   things the slice's new fields can plausibly disturb, and disturbing either
   one inside the playtest window would have shipped a failing pin.

The pass/fail verdict has now been recorded ([`docs/playtest_m0_1.md`](playtest_m0_1.md)),
which releases the hold. The slice is **eligible to land** in M0.2 — but the
release is conditional on the regression bar below staying green, and the
test pin enforces both halves.

## The gate condition (enforced)

> **No PR adds `Player.skills`, `training_points`, or `decision_effects`
> until the M0.1 playtest pass/fail is recorded.**

The pin reads the verdict line from `docs/playtest_m0_1.md` at test time:

- If the verdict line is **absent** (regression that strips the record), the
  three field names must be **absent** from `esports_tycoon/schema.py`. A PR
  that removes the playtest record while introducing the fields fails this
  pin.
- If the verdict line is **present** (current state — `PASS`), the fields
  *may* land. The field-absence assertion lifts; the regression bar below
  still applies.

Either branch keeps the gate condition self-falsifying: a future contributor
cannot land the new surface without the verdict being on disk, and cannot
quietly delete the verdict from under landed work.

## The regression bar (must stay green through the gate)

Two pins guard the contract this slice is most likely to disturb. Both must
stay green as M0.2 work lands; either going red is a stop-the-slice signal:

1. **Golden round-trip on the active M0 surface** —
   `tests/test_golden_determinism.py :: TestGoldenDeterminism` (the
   `test_resolve_*` half that is not parked under `M1 scope:`). The
   committed `tests/golden/week6_resolve.json` pins the resolver's bytes
   against the canonical Week-6 fixture. Adding skills/points/effects without
   wiring them through the resolver-determinism contract would move those
   bytes; the golden trips with a reviewable diff.
2. **Same-seed → same-`WhyRecord`** —
   `tests/test_resolver_determinism.py :: TestDeterminism.test_seed_is_echoed`,
   `:: TestDeterminism.test_run_does_not_mutate_inputs`, and the
   `:: TestResolverEntropyDiscipline` class. The resolver's "same save ⇒ same
   match" contract is the lever the recall selector and the run-log both
   rest on; a new field that reaches for ambient state (e.g. realtime training
   timestamps) would fail this bar before it reached the golden.

The 100-run digest sweep is M1's reproducibility-floor work (gated under
`M1 scope:` per [`docs/m0_gate_decision.md`](m0_gate_decision.md)) and is
*not* part of this slice's bar. The same-process, same-seed byte-identity
half above is what M0.2 must hold.

## Out of scope for this slice

The following are explicitly *not* part of the `TrainingDecision` slice and
must not ride in on the same PR — each lands on its own merits:

- The `M1 scope:` roster in [`docs/m0_gate_decision.md`](m0_gate_decision.md)
  (byte-identity normalization, the 100-run digest, schema-boundary CI gate,
  deterministic bless script, schema-version migration, etc.). M1 owns that
  work; M0.2 must not unfreeze any of those skips.
- The vLLM demo gate ([`esports_tycoon/vllm_demo/`](../esports_tycoon/vllm_demo)).
  That is the other M0.2 surface and ships under its own approval doc bound
  to a content digest. This slice does not depend on vLLM mode and must
  remain templated-mode-green at every step.
- The recap copy fix for the `Remembered:` slot
  ([`docs/playtest_signoff_remembered_line.md`](playtest_signoff_remembered_line.md)
  §*Copy fix #1*). That seam (`matched_tag`/`relevance_reason` plumbing into
  `MatchResolved`) is the next sharpening of the M0.1 surface; it is not
  blocked on training decisions and they are not blocked on it.
- The per-player local-outcome fix logged in
  [`docs/playtest_m0_1.md`](playtest_m0_1.md) §*Fix #1*. Same routing: lands
  on its own ticket, on the same templated-mode surface, independent of this
  slice.

## Where this is pinned in the repo

- **This doc** is the durable record that the slice was held to M0.2 and the
  conditions under which it is eligible to land.
- **`tests/test_tycoon_decisions_slice.py`** asserts:
  - this doc exists and is annotated as the M0.2 post-gate next milestone;
  - it cites the playtest record and the gate decision by path;
  - it enumerates the three deferred field names (`Player.skills`,
    `training_points`, `decision_effects`) verbatim;
  - the playtest verdict is recorded — and if it is *not*, the three field
    names are absent from `esports_tycoon/schema.py`;
  - the golden round-trip and same-seed→same-`WhyRecord` regression tests
    above are present, unskipped (i.e. not parked under `M1 scope:`), and
    green at the moment of the pin.

A regression of any of those falsifies the hold — at which point a fresh
review of this doc is owed *before* any further work on the slice.
