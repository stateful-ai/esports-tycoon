# esports-tycoon — TrainingDecision foundation → M0.2 (post-gate)

**Status.** **Landed in M0.2 foundation.** First playable rep exposed. Recorded
2026-06-01. The
`TrainingDecision` slice named under "Frozen post-gate" in
[`docs/founder_brief.md`](founder_brief.md) (the ninth of the nine
hardening/feature tickets the brief parked behind the playtest gate) is the
**post-gate next milestone (M0.2)** for the player-development loop, distinct
from M1's wedge-phase reproducibility floor
([`docs/m0_gate_decision.md`](m0_gate_decision.md) §*Frozen items now owned by
M1*). M1 ships the reproducibility floor under the canonical schema; M0.2 is
where the *feature* surface this doc names lands.

The M0.1 playtest gate has fired
([`docs/playtest_m0_1.md`](playtest_m0_1.md): **PASS**, recorded 2026-05-26;
re-affirmed in [`docs/m0_gate_decision.md`](m0_gate_decision.md)). The
in-bound condition for opening this slice is therefore satisfied — but the
first foundation is now built. This doc is the durable record of *why* it was
held, *what* landed, and *what regression bar* it must stay under as it deepens.

## The slice

The `TrainingDecision` foundation extends the manager's decision surface from the
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
  choices. In the foundation this lives on `Decisions` and defaults to zero so
  the existing M0 web path and canonical Week-6 fixture stay stable. Future UI
  work can decide how points are earned across weeks.
- **`decision_effects`** — the typed table mapping each training decision to
  the `skills` delta it applies (plus its `training_points` cost). The
  resolver reads decision_effects → skills → match outcome; the renderer
  reads decision_effects → `WhyRecord.key_moments` to attribute *which*
  training week's decision rhymed with the play that just happened.

Together these three are the smallest seam that makes a player-development
loop legible to both the resolver and the renderer without re-shaping the
canonical save's invariants (cite IDs, memory ownership, grounding).

Foundation scope landed:

- `Player.skills` is a default-empty persistent rating vector accepted by the
  save schema and omitted from canonical dumps while empty.
- `Decisions.training_points` and `Decisions.decision_effects` are default-empty
  structured resolver inputs; budget overspend fails validation.
- The resolver layers persistent skills plus same-week decision effects into
  role-weighted skill and tilt calculations.
- The run-log records the budget/effects on `PracticeChosen`, and `recap.md`
  renders a compact training attribution line when effects are present.
- The web `/practice` flow now exposes the first player-facing rep choice:
  spend 4 TP on a named starter drill, with the chosen effect surfaced on
  `/match`, `/recap`, and the saved recap artifact. The pinned Week-6
  `vex_aim` drill moves Vex from `came_apart` to `carried` on the same seed,
  so training is tested as a visible outcome shift rather than a receipt only.
- The same `vex_aim` path now projects a deterministic training-to-clash
  fallout receipt: the focused rep reopens the seeded Vex ↔ Pixie
  "blame vs. guilt" pair as a visible match/recap/artifact line, grounded in
  the flash memories that authored the clash. No focused rep means no
  relationship-fallout event, keeping the slice a consequence of training
  rather than generic relationship simulation.
- The fallout receipt now compounds into Chirper: the `vex_aim` path appends
  one grounded Vex post tagged as `fallout` in `feed.snapshot.html`, citing the
  same Vex/Pixie seeded memories. This keeps the next social consequence on the
  existing deterministic feed surface instead of introducing persistence or a
  wider relationship system.
- The first repair-vs-reps fork has landed on that same surface. The canonical
  save unlocks `pixie_flash_repair` beside `vex_aim`: `vex_aim` shows the
  benefit/cost of sharper entry reps while the Vex/Pixie split stays public;
  `pixie_flash_repair` spends the block on coordination, steadies Pixie, cools
  the fallout to a `working review`, and emits a distinct Pixie Chirper receipt.
  The fork remains authored, deterministic, and database-free.
- The fork now sets one run-local future constraint: `review_room_trust`.
  `vex_aim` exports `2 -> 0 (-2)` plus the `Review room heat` Week-7 hook;
  `pixie_flash_repair` exports `2 -> 4 (+2)` plus the `Stable, not loud`
  Week-7 hook. Match/recap show the trust delta and a follow-up scrim receipt,
  while `week7_setup.json` carries the branch, fallout state, trust delta, hook,
  and recommended next focus for the next slice.
- The next slice now consumes that hook: `/week7` presents `contain_fallout`
  and `prove_ceiling`, marks the exported `recommended_focus`, and writes
  `week7_focus.json` after the player locks a focus. Choosing against the read
  emits a deterministic ignored-recommendation consequence (`ignored_trust_fire`
  or `overcorrected_stability`) without introducing persistence or a generalized
  season planner.
- The focus receipt now pays off on `/week7/result`: the route consumes
  `week7_setup.json` plus `week7_focus.json`, resolves one of four deterministic
  Tuesday pressure outcomes, and writes `week7_pressure.json` with the scrim
  result, review-room beat, public signal, and deltas. This proves the locked
  Week-7 focus changes gameplay before adding any new choice or season layer.
- That pressure receipt now becomes the next manager problem on `/week8`: the
  route consumes the three Week-7 artifacts, maps each pressure outcome to an
  exposed problem, and writes `week8_prep.json` when the player chooses either
  `patch_exposed_break` or `double_down_identity`. The slice stops at the prep
  fork rather than resolving a full Week-8 match.
- The prep response now changes the next visible setup on `/week8/scrim`: it
  consumes `week8_prep.json`, maps the response to a scrim modifier/opening
  state, and writes `week8_scrim.json` after the player locks either
  `play_to_prep` or `cover_the_crack`. This keeps compounding visible while
  still deferring a full Week-8 match resolver.
- The scrim setup now compounds into `/week8/match`: it consumes
  `week8_scrim.json`, previews the opponent's first attack, the team's current
  edge, and the match risk, then writes `week8_match_plan.json` after the player
  locks either `patch_weakness` or `lean_into_edge`. This adds the match-week
  planning decision without simulating the match result yet.
- The match plan now pays off on `/week8/match/result`: it consumes
  `week8_match_plan.json`, resolves the plan into an outcome/scoreline/public
  read/pressure beat, and writes `week8_match_result.json` with a Week 9 hook.
  The slice deliberately keeps media, sponsor, roster, and Week 9 systems out of
  scope until the single-result consequence is proven.
- The Week 8 result now becomes the next playable manager problem on `/week9`:
  it consumes `week8_match_result.json`, maps the outcome and consequence axis
  into a Week 9 problem/recommendation, and writes `week9_setup.json` after the
  player locks one of three response postures. This proves result-to-next-choice
  causality without adding a Week 9 match, standings, sponsor, or roster system.

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
which released the hold. The foundation has landed in M0.2; further
TrainingDecision depth remains conditional on the regression bar below staying
green, and the test pin enforces both halves.

## The gate condition (enforced)

> **No PR adds `Player.skills`, `training_points`, or `decision_effects`
> until the M0.1 playtest pass/fail is recorded.**

The pin reads the verdict line from `docs/playtest_m0_1.md` at test time:

- If the verdict line is **absent** (regression that strips the record), the
  three field names must be **absent** from `esports_tycoon/schema.py`. A PR
  that removes the playtest record while introducing the fields fails this
  pin.
- If the verdict line is **present** (current state — `PASS`), the fields may
  land. They have now landed in the foundation shape recorded above; the
  regression bar below still applies.

Either branch keeps the gate condition self-falsifying: a future contributor
could not land the new surface without the verdict being on disk, and cannot
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

- **This doc** is the durable record that the slice was held to M0.2, that the
  first foundation has landed, and the conditions under which it can deepen.
- **`tests/test_tycoon_decisions_slice.py`** asserts:
  - this doc exists and is annotated as the M0.2 post-gate next milestone;
  - it cites the playtest record and the gate decision by path;
  - it enumerates the three landed field names (`Player.skills`,
    `training_points`, `decision_effects`) verbatim;
  - the playtest verdict is recorded — and if it is *not*, the three landed
    field names cannot remain in `esports_tycoon/schema.py`;
  - the landed shape is `Player.skills` plus `Decisions.training_points` and
    `Decisions.decision_effects`;
  - the golden round-trip and same-seed→same-`WhyRecord` regression tests
    above are present, unskipped (i.e. not parked under `M1 scope:`), and
    green at the moment of the pin.

A regression of any of those falsifies the landing record — at which point a
fresh review of this doc is owed *before* any further work on the slice.
