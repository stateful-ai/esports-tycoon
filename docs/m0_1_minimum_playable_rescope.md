# esports-tycoon — Re-scope: "End-to-end wiring + rebind web app/recap reader" → Minimum Playable

**Status.** Scope change to the existing rebind ticket. Recorded on 2026-05-26.
Supersedes the broader "rebind every consumer to the canonical schema" framing
that the ticket carried in `m0_0_canonical_contract.md` § *Rebind map* and in
`m0_1_build_execution_plan.md` § *Wave 3 — Minimum-playable rebind*. Reuses
`scope-m0.md` (the M0 slice) and the founder brief (`docs/founder_brief.md`)
verbatim for the locked acceptance bar and the wedge-phase product principle.

## What changed and why

The original ticket entangled two pieces of work that have different costs and
different consumers:

1. **Minimum playable.** One command loads the canned Week-6 save, plays
   practice → match → fallout, and renders the Chirper feed and post-match
   narration in templated (zero-API) mode. The founder can sit down, hit one
   command, and screenshot the "remembered me" moment within an evening.
2. **Full canonical-schema convergence.** Every consumer of the world state —
   the resolver, the loader, the web shell, the recap reader, the content
   adapter, the run-log writer — imports the *same* typed `WorldState`, the
   save is byte-stable on round-trip, every `mem:` cite has a referential-
   integrity check, and the schema carries a load-gated `schema_version`.

These were entangled because the rebind work happened to *land* most of the
convergence as a by-product. But the M1 wedge-phase principle (company memory
`mem_20260526T003406Z_f3e92d`) is to **build only the minimum infra needed to
gather the taste evidence; defer reproducibility rigor to the milestone that
actually needs it.** Full convergence is reproducibility rigor — it pays off
in M1's `baseline ≡ adaptive` diff, not in the M0.1 screenshot.

So the ticket is narrowed to (1) and **(2) is explicitly removed as a
precondition**.

## Narrowed acceptance

- **One command.** `python -m esports_tycoon.runner` against the packaged
  canned save (no `--save`, no env), with defaults that mirror the Week-6
  fixture (opponent `apex_foundry`, map `Helix`, seed `6`).
- **Practice → match → fallout.** The single invocation runs the MC practice
  choice, the seeded resolver, the templated half-time ack, and the Chirper
  feed end-to-end — the same loop the local web shell drives, just headless.
- **Renders the Chirper feed.** `runs/<slice_id>/feed.snapshot.html` is
  written; the file is a standalone, self-contained Chirper page (inline
  CSS, no external assets) with one `<article class="post">` per fielded
  starter plus the caster and the opponent's star.
- **Renders the post-match narration.** `runs/<slice_id>/recap.md` contains
  the resolver-grounded prose narration of the match under `## The match`;
  the bytes go through the templated content adapter, not the LLM seam.
- **Templated mode, zero API calls.** The default backend is `templated`;
  the recap header reads "templated mode (zero-API)". The vLLM backend
  module (`esports_tycoon.content.llm`) is imported lazily — *only* when
  the flag selects it — so the zero-API guarantee holds by construction,
  not by trusting the network to be unreachable.

## Explicitly NOT a precondition

The following work is **out of scope for this ticket**. None of it is a
blocker for the minimum-playable acceptance bar above; each line stays
tracked under its own ticket and lands on its own merits.

- A single canonical `WorldState` type imported by *every* consumer
  (`m0_0_canonical_contract.md` § *The contract*, item 1).
- Byte-identical save round-trip on `week6.yaml` (item 4).
- Referential-integrity validation on load (item 5).
- A load-gated `schema_version` field (item 3).
- Determinism-anchored RNG plumbing (item 6).
- Removal of every draft-typed binding from every shipped surface (the
  `TestNoDraftFieldReferences` structural guard in `tests/test_runner_cli.py`).
- The byte-identity + 100-run digest + CI/bless/negative-fixture suite, which
  the founder brief lists under "Out of scope (explicitly frozen until the
  screenshot lands)".

These may all be true *as a side-effect* of work that has already merged on
the way to the rebind — but they are not what the rebind ticket is being held
to. A future change that regresses any of them lands a different ticket.

## Where the acceptance is pinned in the repo

- **One-command runner** — `esports_tycoon/runner/__main__.py` (`python -m
  esports_tycoon.runner`).
- **Practice → match → fallout** — `esports_tycoon/runner/engine.py` ::
  `run_slice`.
- **Chirper feed + post-match narration** — `esports_tycoon/runner/recap.py`
  :: `render_feed_html`, `render_recap_md`.
- **Templated default + lazy vLLM import** — `esports_tycoon/content/config.py`
  (`templated` default) and `esports_tycoon/content/adapter.py` (the `vllm`
  branch imports `esports_tycoon.content.llm` inside the `if`).
- **Test contract** — `tests/test_runner_cli.py` :: `TestMinimumPlayable`
  asserts the four bullets above by running the CLI once with default flags
  and inspecting the artifacts plus `sys.modules`.

## Out-of-scope sanity check

If a reviewer notices the ticket touching draft-field removal, version-gate
plumbing, byte-identity normalization, or any consumer beyond the runner
CLI's recap+feed surface, the ticket has re-inflated — bounce it back to
the minimum-playable carve-out above and route the extra work to its own
ticket.
