# ADR-005 — One budget governor gates every LLM call

Date: 2026-04-23
Status: Accepted
Deciders: Aidan (solo)
Related: budget memory, ADR-004 (SQLite ledger location)

## Context

The budget is ~$40/week, total, for the whole project. LLM API calls are the number-one cost risk because they appear in at least four places:

1. System 06 dark-data inference over transcripts, patch notes, interviews — offline but high volume.
2. Ecosystem agent reasoning (GMs, sponsors, players) during simulated seasons — per-match cadence.
3. Tycoon dialogue at runtime — per-user-interaction cadence.
4. Ad-hoc one-offs during research — every time I curiously ask "what if we also did X?"

Without a central governor, any of the four can silently burn the weekly cap in a single bad run, and the others simply fail for the rest of the week. We need a single chokepoint that owns "may this LLM call happen, at what cost, and if not, what does the caller do instead".

## Decision

All Claude API calls route through a single module (`llm/governor.py`). Call sites declare:

- `site`: a stable string identifier ("system06.infer_personality", "ecosystem.gm_decision", "game.npc_dialogue", "adhoc.{script_name}").
- `tier`: {critical, high, normal, low}. The governor's weekly budget is split across tiers so a noisy `normal`-tier site cannot starve a `critical` one.
- `mode`: {fresh, cache_ok, never_now}.
    - `fresh` — must hit the API; if cap would exceed, call fails with `BudgetExceededError`.
    - `cache_ok` — prefer a prior result if it exists and satisfies a per-site staleness policy; otherwise call.
    - `never_now` — never hit the API; return the prior result or a `NoPriorValue` sentinel.
- `confidence_of_last_call`: float in [0, 1] if applicable — low-confidence priors are re-inferred sooner.

Every completed call writes a row to `state/budget.db` with timestamp, site, tier, input_tokens, output_tokens, dollar cost, response hash, confidence. That ledger is authoritative for any "how much did we spend this week" question.

Embeddings and transcription do not route through the governor — they route through local defaults (sentence-transformers, Whisper large-v3) with an explicit opt-out for the rare case an API version is needed.

Adding a new call site requires filing (at minimum) a two-line entry in `configs/llm_sites.yaml` with its tier and default cadence. No call site has a default tier — it must be declared.

## Consequences

**Positive.**

- A weekly dollar cap is actually enforceable, not aspirational.
- Rate-limiting, retries, and exponential backoff live in one place, not sprinkled across callers.
- The ledger is queryable: "which site is eating the cap?" is a SQL query, not a grep.
- Confidence-aware re-inference is a first-class concept — a high-confidence personality inference from last month doesn't get re-paid for this month.

**Negative.**

- Every LLM-using code path must go through the governor. Adherence is a discipline problem, not a technical one; it would be plausible to bypass in a hurry.
- The `never_now` mode means some production code paths must handle "we don't have a fresh answer, here's a stale one" gracefully. Consumers that can't handle that get upgraded from normal to high tier.
- Cold-start problem: a new call site has no prior, so its first call is always `fresh`-tier regardless of mode. This is correct but adds a quirk.

**Neutral.**

- The governor does not itself decide pricing; it reads a `pricing.yaml` that must be updated when vendor pricing changes.
- It logs enough to be audit-able but does not try to be a full metrics system — TensorBoard and run logs cover that elsewhere.

## Alternatives considered

**(A) Per-caller rate limiting.** Rejected — no global cap, easy to blow the budget with multiple callers under their individual caps.

**(B) Just alert on spending.** Rejected — alerts don't prevent overrun, they just inform about it. Doesn't match the hard-cap nature of the constraint.

**(C) Move ecosystem agents to a local model only.** Tempting, and in fact the dialogue tier should partially go there, but losing Claude for ecosystem reasoning sacrifices too much behavioral depth. The governor lets both cohabit.

## Enforcement

- A pre-commit hook (optional; cheap) greps for direct `anthropic.` imports outside `llm/governor.py` and flags them.
- CI runs a smoke test that the governor denies a `fresh` call when its mock ledger is over cap.
- Bypasses require an ADR citing this one.

## Revisit when

- A Tier-2 inference task plausibly moves to a local model within 10% of Claude quality.
- The weekly cap doubles or halves — adjust the tier split rather than the per-call logic.
- More than one human is paying attention, at which point per-user or per-environment budgets become a thing.
