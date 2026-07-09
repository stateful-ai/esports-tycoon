---
name: tactics
description: Add or extend a coaching tactics dial (or its match-engine reach) the neutral-safe way, so the golden/balance gates stay byte-stable. Use when touching TeamTactics, the dials' engine behaviour, or the per-team roster/chemistry execution modifiers.
---

# Tactics — neutral-safe dial workflow

The coaching dials (`TeamTactics` in `schemas/team.py`) reach deep into
round micro. The whole design rests on ONE rule (ADR-007):

> **Every dial-reach term is an exact no-op at the neutral value 50.**

The golden and balance gates run default (neutral) tactics on the data
teams, so a term that changes behaviour at 50 silently breaks the golden
and forces a re-bless on every tweak. Keep it neutral-safe and a tactics PR
touches neither gate.

## The rule, concretely

A new term must be zero at 50. Two shapes:

- **Two-sided** — scale by the deviation: `x * (dial - 50) / 50`. Zero at
  50, symmetric either way.
- **One-sided** — gate outside the neutral band: `if dial > 55: ...` /
  `max(0.0, dial - 50)`. Use when only one half is a real behaviour (a
  lurker only exists above neutral `map_control`).

Per-team modifiers built from roster/chemistry (`_execution_mod`,
`_system_fit_mult`) follow the same rule — multiply each dial's deviation
from 50, so a neutral team gets exactly `0.0` / `1.0`.

All magnitudes live in `sim/constants.py` as `*_SPAN` constants — never
inline. A balance pass is then a config edit.

## Where the wiring lives (touch all that apply)

| Layer | File | What |
|---|---|---|
| Schema | `schemas/team.py` | `TeamTactics` field (default 50.0, ge/le) + docstring |
| Engine reach | `sim/engine.py` | read via `self._tactics(tid)`; neutral-safe term |
| Tuning | `sim/constants.py` | the `*_SPAN` / band constants |
| API | `web/server.py` | `TacticsBody` field + the `set_tactics` clamp loop + validation |
| UI | `web/static/app.js` | `TACTIC_DIALS` entry (label + hint) |
| AI identity | `manager/campaign.py` | `_assign_ai_tactics` (season identity) + `_adapt_ai_tactics` (in-season drift) |

Not every change touches all six — a new dial does; deepening an existing
dial's engine reach may only touch engine + constants (+ tests).

## Verify (the cheap proof)

1. **Golden = byte-identical** → neutral-safe. Run
   `pytest -q tests/test_golden.py`. If it drifts, a term isn't zero at 50 —
   fix the term, don't re-bless.
2. **Sanity sweep**: `scripts/tactics_report.py` pushes each dial to its
   extremes and asserts a wide degenerate-detector band (attack 30–75%,
   plant rate ≥ 10%). Exit 0 required. Note it prints each dial's `d-atk`
   for eyeballing but does NOT threshold movement — proving a dial actually
   moves its signal is the regression test's job (step 4), not this script's.
3. **Balance still in band**: `scripts/balance_report.py 300` (neutral data
   teams → unchanged, but confirm). Golden byte-identical already implies
   this.
4. Add a regression test in `tests/test_tactics.py`: assert neutral is a
   no-op AND the dial moves its target signal (see the existing
   `test_*_is_wired` / directional tests for the pattern) — this is where
   dial movement is actually enforced.

## Gotchas

- Reviewers (and past bugs) have caught: crediting the wrong side, stale
  orders when a role changes mid-round (lurker grabs the spike), and
  effects leaking onto pistol/gun rounds when gating on the wrong signal.
  Prefer the *actual* game state (loadout, `went`, alive-set) over a proxy.
- The single-match golden is blind to neutral changes that miss its seed;
  the `sweep_neutral` fixture is the safety net — re-bless both together
  when a neutral change IS intended and reviewed.
