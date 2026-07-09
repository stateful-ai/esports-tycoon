# ADR-007 — Neutral-safe tactics: coaching dials that can't drift the golden

Date: 2026-07-09
Status: Accepted
Deciders: Aidan (solo)
Supersedes: —
Related: ADR-003 (event log canonical)

## Context

The match engine grew a set of EHM-style coaching dials (`TeamTactics`:
aggression, pace, util_discipline, eco_greed, map_control, site_focus) plus
derived per-team modifiers (roster fit, chemistry, execution). These reach
deep into the micro of a round — peek frequency, refrag spacing, execute
timing, defensive setup depth, lurker deployment, retake commitment, and
more.

Two invariants make that dangerous to extend:

1. **The golden gate** (`tests/test_golden.py`, `tests/test_golden.py::
   test_golden_sweep_unchanged`) pins a byte-identical event log for a
   canonical match and an aggregate sweep across the whole map pool. Any
   engine change that alters those logs fails CI until a deliberate
   re-bless.
2. **The balance band** (`scripts/balance_report.py`, a gate) requires every
   map to hold 45–65% attack-round win rate.

Both gates are measured with **default (neutral = 50) tactics** on the data
teams. So a dial that changes behaviour at neutral silently breaks the
golden and forces a re-bless on every tactics tweak — turning what should be
config edits into engine-archaeology, and eroding the golden's value as a
drift detector.

## Decision

**Every new dial-reach term must be an exact no-op at the neutral value
(50).** Concretely, a term either:

- scales by `(dial - 50) / 50` (or `max(0, dial - 50)` for one-sided
  effects), so it is arithmetically zero at 50; or
- gates on a band that leaves `[45, 55]` (or `<= 50`) on the pre-tactics
  code path.

Per-team modifiers built from roster/chemistry (execution fit) follow the
same rule: they multiply each dial's deviation from 50, so a neutral team
gets exactly `0.0`.

All tuning constants live in `sim/constants.py`, never inline, so a balance
pass is a config edit. Genuine neutral-behaviour changes (a real correctness
fix, e.g. the off-site spike-carrier stall) are allowed but are a
**deliberate, separately-reviewed** decision that re-blesses the golden and
re-checks the balance band in the same commit.

## Consequences

**Positive.**

- The golden stays a true drift detector: a neutral-safe tactics change
  keeps it byte-identical, so a golden diff always means an *intended*
  neutral-behaviour change.
- Tactics work ships as small, low-risk PRs that don't touch the balance or
  pacing gates.
- New dials and modifiers compose freely — because each is zero at neutral,
  they never interact at the default.

**Negative.**

- Some effects are naturally one-sided (a lurker only exists above neutral
  `map_control`), so the dial's two halves aren't always symmetric.
- The single-match golden is blind to neutral changes that miss its
  specific seed; the aggregate `sweep_neutral` fixture exists precisely to
  close that blind spot and should be re-blessed alongside the single one.

**Neutral but important.**

- "Neutral-safe" is verified the cheap way: run the golden gate. Byte-
  identical output at default tactics is the proof, so no separate audit is
  needed.
- Campaign-layer features (AI tactic adaptation, development, economy) never
  run inside the match gates, so they're unconstrained by this ADR — the
  rule is specifically for code the deterministic match engine executes.

## Alternatives considered

- **Re-bless the golden on every tactics change.** Rejected: it makes the
  golden diff meaningless (every PR churns it) and invites silent balance
  drift, since a re-bless is easy to rubber-stamp.
- **A separate "tactics off" golden.** Rejected as redundant: the existing
  golden already runs neutral tactics, so neutral-safety and golden-
  stability are the same property.
