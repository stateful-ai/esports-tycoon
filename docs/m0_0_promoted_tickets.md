# esports-tycoon — M0.0 promoted tickets

**Status.** Three M0.0 enablers that originally rode as DoD line items inside
the spine tickets ([`docs/m0_0_founder_brief.md`](m0_0_founder_brief.md)
§*Reconciled position*: "**M0.0 enablers ride as DoD line items inside spine
ticket #1, not as separate Linear tickets. ... Promote only if any single
enabler grows beyond a half-day.**") are **promoted to active M0.0 tickets**.
Recorded 2026-05-27. Each grew past the half-day enabler threshold — each
touches a load-bearing seam (the install graph, the canonical-bytes write
path, the load-time error contract) that more than one W-line in
[`docs/founder_brief.md`](founder_brief.md) reaches for. Folding them inside
one spine ticket would have hidden the cross-W dependency; standalone tickets
make the wiring legible.

The implementations have already landed against these tickets — the doc
exists to **name the acceptance bar** each ticket must hold to *stay* active
(a regression flips the bar before it reaches the broader M1 reproducibility
floor; see [`docs/m0_gate_decision.md`](m0_gate_decision.md) for the rest of
that surface). The W1/W3/W4 lines in [`docs/founder_brief.md`](founder_brief.md)
have been updated to cite each ticket by id below.

## M0.0-T1 — Pin the serialization toolchain

**Unblocks.** **W1** keystone (`recall()` + content + golden): the golden a
W1 reviewer compares against is only a fixed point if the serializer that
emitted it can be reproduced byte-for-byte on a clean clone. **W3** (rebind +
recap snapshot + zero-network): the `runs/<slice_id>/` snapshot artifacts are
also dumped through the same serializer, so the snapshot a playtest captures
is byte-stable across machines. **W4** (gate w/ manifest-stamped evidence):
the manifest names the toolchain versions whose bytes the evidence rests on;
without the pin, the manifest is fiction.

**Why a standalone ticket.** Pinning is a four-seam contract — `pyproject.toml`
range, `constraints.txt` lockfile, `Makefile` / CI install paths, *and* the
running interpreter — and any one of those breaking silently re-shapes the
canonical bytes on a clean checkout. A single DoD checkbox would not have
forced the four-seam discipline; a ticket with the bar below does.

**Acceptance criteria.**

1. `pyproject.toml` carries `requires-python = ">=3.12,<3.13"` (a single-minor
   pin, lower **and** upper bound), and pins `PyYAML` and `pydantic` in
   `[project].dependencies` with `==` — no ranges.
2. `constraints.txt` exists at the repo root and pins, with `==` only, every
   library whose bytes can re-shape canonical YAML / pydantic output:
   `PyYAML`, `pydantic`, `pydantic_core`, `typing_extensions`,
   `annotated-types`. Versions agree with `pyproject.toml` where both name
   the same library.
3. `make install` and the CI workflow (`.github/workflows/ci.yml`) both
   resolve through `constraints.txt` — i.e. `pip install -c constraints.txt …`,
   not `pip install -e .` standalone. CI calls `make install`, not pip
   directly, so the same install path runs locally and in CI.
4. The CI `python-version` matrix is exactly the single minor named in
   `requires-python`. No drift between the pin and the runtime.
5. The running interpreter and the loaded `pydantic` / `PyYAML` versions
   match the lockfile at test time — a stale virtualenv fails this acceptance
   bar before it reaches a confusing golden diff.

**Where it is pinned in-repo.** `pyproject.toml` (`requires-python`,
`[project].dependencies`), `constraints.txt`, `Makefile` (`install` target),
`.github/workflows/ci.yml`, and `tests/test_toolchain_pin.py` (which asserts
all five bars above and is the regression net for this ticket; it stays
parked under `M1 scope:` because the broader byte-identity normalization
work is M1's, but the toolchain-pin bars themselves are met today).

## M0.0-T2 — Deterministic golden-bless script

**Unblocks.** **W1** keystone (`recall()` + content + golden): the W1 golden
is regenerated through one script; a reviewer reads the diff that script
produces, not a hand-edited fixture. **W4** (gate w/ manifest-stamped
evidence): the gate-bundle manifest lists the canonical-bytes regen step by
name (`make regen-golden`) — that step has to be a fixed point, otherwise the
manifest's "regen is a no-op on the bless" claim is unfalsifiable.

**Why a standalone ticket.** The bless script is the *only* supported way to
re-emit the canned save. If it were folded as a DoD line on the canonical
serializer ticket, the script's idempotence — the property that distinguishes
a real fixed point from a one-shot rewrite — would have no acceptance bar of
its own. A standalone ticket names it.

**Acceptance criteria.**

1. `scripts/regen_golden.py` exists and re-emits `saves/week6.yaml` by
   loading it through the full validating loader (shape, cite IDs,
   referential integrity) and dumping the result through the canonical
   serializer.
2. The script is **idempotent on the committed save**: a first run on a
   canonical file rewrites nothing; a second run on the same file also
   rewrites nothing. The committed `saves/week6.yaml` is already at this
   fixed point.
3. The script **converges in one step after any drift**: a hand-edit
   (extra newline, re-folded scalar, re-ordered key) is restored to the
   canonical bytes on the next run, and a second run is then a no-op.
4. A `--check` mode exits zero when the file is canonical, non-zero
   otherwise — suitable for CI / pre-commit.
5. The script never self-heals the committed file from inside a test — the
   regression net (`tests/test_regen_golden.py`) operates on a temp-dir copy
   so a green test cannot quietly rewrite the fixture out from under a
   hand-edit drift.

**Where it is pinned in-repo.** `scripts/regen_golden.py`, the `regen-golden`
target in `Makefile`, and `tests/test_regen_golden.py` (which asserts the
five bars above; parked under `M1 scope:` because the broader byte-identity
contract is M1's, but the idempotence and one-step-convergence bars are met
today).

## M0.0-T3 — Shared typed `SaveError` contract

**Unblocks.** **W3** (rebind + recap snapshot + zero-network): every consumer
of the canonical save — the runner CLI, the web shell, the recap reader —
must surface load failures the same way so a playtest never sees a raw
pydantic traceback or a bare `KeyError`. **W4** (gate w/ manifest-stamped
evidence): the gate bundle includes negative fixtures whose acceptance is
the *typed error subclass and the field path*, not a stringly-typed message
match; without the shared contract, a regression in any one error site would
slip past the manifest.

**Why a standalone ticket.** A "raise the right exception" item folded as a
DoD line on the loader ticket would have produced four ad-hoc exceptions —
one per failure mode — and a caller would have had to learn each one. The
shared base + four siblings, each carrying `field_path` and `source`, is a
real contract; it earns a ticket.

**Acceptance criteria.**

1. `esports_tycoon.canned.loader.SaveError` is a `ValueError` subclass
   carrying `field_path` (the structured save location at fault) and
   `source` (the path or object the save was loaded from). Back-compat:
   callers that catch `ValueError` on a bad save keep working.
2. Four named siblings cover the four failure categories the load path is
   responsible for, each a `SaveError` subclass and each disjoint from the
   others: `SaveYamlError` (YAML parse), `SchemaVersionError` (unsupported
   `schema_version`), `SaveSchemaError` (pydantic shape rejection),
   `SaveReferentialIntegrityError` (cross-entity id reference does not
   resolve).
3. Every `loader.load(...)` failure raises a `SaveError` subclass — not a
   bare `ValidationError`, not a bare `YAMLError`. The original exception is
   preserved on `__cause__` so a caller that needs the parser's
   line/column or pydantic's full per-field list still has it one
   `__cause__` hop away.
4. `field_path` is a non-empty string on every `SaveError` instance.
   `SchemaVersionError`'s default is `"schema_version"`;
   `SaveReferentialIntegrityError`'s is its first issue's path; the
   `SaveSchemaError` field path is derived from the pydantic error and
   promoted off a typed `GroundingError` when the validator raised one, so
   the path always names a concrete spot in the save.
5. Negative fixtures under `tests/fixtures/integrity/` assert on the shared
   `SaveError` base and the `field_path` (not on the ad-hoc subclass message
   text), so a future failure mode added under the contract does not require
   rewriting every fixture's assertion.

**Where it is pinned in-repo.** `esports_tycoon/canned/loader.py` (the
`SaveError` base and its four siblings, plus the `load` flow that lifts every
underlying failure into the contract), the negative fixtures at
`tests/fixtures/integrity/`, and `tests/test_referential_integrity.py`
(which asserts the five bars above; parked under `M1 scope:` because the
broader RI surface is M1's, but the shared-contract bars are met today).

## Where this promotion is pinned in-repo

- **This doc** is the durable record of the three tickets and their
  acceptance criteria.
- **`docs/founder_brief.md`** cites M0.0-T1, M0.0-T2, M0.0-T3 by id on the
  W1, W3, and W4 critical-path lines that each unblocks, so a reader of the
  brief can trace a W-line straight to the ticket whose acceptance bar
  guards it.
- **`tests/test_m0_0_promoted_tickets.py`** asserts: this doc exists with
  the three ticket sections, each carries an `Acceptance criteria` block,
  each is referenced by id from `docs/founder_brief.md`'s W1/W3/W4 lines,
  and the implementation seams each ticket points to (the four toolchain-pin
  files, `scripts/regen_golden.py`, and the `SaveError` shared base + four
  siblings in `loader.py`) are present. A regression to any of those
  surfaces flips this pin.
