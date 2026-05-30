# esports-tycoon — M0 gate decision

**Verdict.** **PASS.** Recorded 2026-05-26.

**Evidence.** [`docs/playtest_m0_1.md`](playtest_m0_1.md) — fresh-clone Week-6
playtest of the zero-API slice. All four bullets of the narrowed acceptance bar
in [`docs/m0_1_minimum_playable_rescope.md`](m0_1_minimum_playable_rescope.md)
were exercised end-to-end (one default-flags command; practice → match →
fallout; Chirper feed + post-match narration rendered to `runs/<slice_id>/`;
templated mode, zero outbound network), and the "remembered me" beat landed
with **6 / 6 grounding** (every cited memory resolved back to the canned log).
The acceptance bar is also pinned in-repo by
`tests/test_runner_cli.py :: TestMinimumPlayable`, which runs on every commit.
One fix is logged against the slice (Chirper posts not conditioned on the
*player's* local match outcome) — it is a content tuning fix, not a gate
condition, and rides its own ticket.

## What this decision routes

Two consequences, named so this artifact is self-contained:

1. **M1 is greenlit.** The wedge-phase milestone (`docs/founder_brief_build_m1.md`)
   is unblocked. Subsequent build tickets land against M1.
2. **The M0 reproducibility freeze is lifted, and the frozen infra is
   re-scoped to M1.** Up to this commit, ten test modules carried
   `M0 freeze: … deferred to M1/post-gate` skip labels — the parking marker
   PR #32 set when this gate was still ahead. The gate has now fired; those
   modules are re-labelled `M1 scope: …` so the routing reflects ownership
   (M1's wedge-phase acceptance bar), not a paused-pending-gate hold. The
   underlying tests stay skipped — the work behind them is M1's to land — but
   the *reason* they skip is no longer "the gate hasn't fired yet."

### The fail branch (recorded for completeness)

The other half of the acceptance criterion was: on a **fail** verdict, open a
wedge-revisit before any further build. That branch is **not exercised** —
the playtest was a clear pass — and this doc is the proof. If a future
playtest of this same screenshot surface lands a fail, the wedge-revisit lives
at `docs/m0_wedge_revisit.md` (created on demand) and is a precondition for
re-firing any M1 ticket.

## Frozen items now owned by M1

The "Out of scope (stay frozen until gate fires)" list in `docs/founder_brief.md`
is the authoritative roster. The same items are surfaced inline in the test
suite via the (now renamed) `M1 scope: …` skip labels on:

- `tests/test_canonical.py` — byte-identity serializer + canonical YAML/float
  formatting.
- `tests/test_ci_contract.py` — `make test` / CI golden-drift plumbing contract.
- `tests/test_golden_determinism.py` — canonical-byte round-trip + fixed-point;
  golden-render extension to the templated adapter.
- `tests/test_loader.py` — load → dump → load → dump byte-identical fixed point.
- `tests/test_referential_integrity.py` — RI validator + negative fixtures +
  typed `SaveError` contract.
- `tests/test_regen_golden.py` — deterministic golden-bless script fixed-point.
- `tests/test_schema_boundary.py` — schema-boundary CI gate.
- `tests/test_schema_version.py` — migration stub + `schema_version` gate.
- `tests/test_toolchain_pin.py` — pinned-toolchain enforcement.

These are the M1 acceptance surface for the reproducibility floor; ordering
and ticket-shaping live in `docs/founder_brief_build_m1.md`. A future change
that un-skips one of these tests **lands its M1 ticket**, not this one.

## Where this decision is pinned in the repo

- **This doc** is the durable record; future readers find it by path.
- **`tests/test_m0_gate_decision.py`** asserts:
  - this doc exists and records a `PASS` verdict;
  - it cites the playtest evidence;
  - no `tests/*.py` file still carries the old `M0 freeze` / "until the gate
    fires" tense — i.e. the re-scope is complete in one direction;
  - every still-skipped frozen test now skips under an `M1 scope: …` label
    (so a future contributor can grep one consistent string to find the M1
    work surface).
