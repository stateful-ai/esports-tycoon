# ADR-002 — Player Profile Vector as universal conditioning contract

Date: 2026-04-23
Status: Accepted
Deciders: Aidan (solo)
Related: ADR-001 (training substrate)

## Context

Four Nexus components need to know "who this player is" in a machine-readable way:

1. The RL policy (C4) — to roll differently as Aspas vs. TenZ.
2. The world model (C5) — to condition its rollout distribution.
3. The ecosystem engine (C6) — to decide who fatigues, tilts, gets courted.
4. The game client (C7) — to render the player card the human sees.

If each component derives this from the graph independently, four slightly different "player representations" drift apart and conditioning becomes noise. We need one canonical view.

## Decision

Introduce `PPV_v{N}` — a versioned, frozen, fixed-length player profile type with two surfaces:

- A structured pydantic form (`mech`, `tact`, `behav`, `rel` sub-blocks) for humans, game cards, and any non-tensor consumer.
- A `to_tensor() -> Tensor[D_vN]` view, with `D_vN` a frozen constant per schema version, for RL and world model.

The structured and tensor views are two projections of the same underlying data. Every component that needs conditioning consumes PPV and nothing else. Components never invent their own player features.

PPV is computed by a dedicated service (C2) that reads from the canonical graph (C1 output). Results are cache-able per `(player_id, patch_era_id, as_of)` key because the graph snapshot is immutable within a patch era.

## Consequences

**Positive.**

- One schema, one cache, one place to improve player features.
- Versioning the conditioning is an explicit, auditable event: changing PPV bumps the schema version and all downstream experiments know which regime they trained under via the experiment registry (C9).
- Rollout records inline the PPV used, so even a rollout produced against PPV_v1 remains interpretable after PPV_v2 ships.

**Negative.**

- A fixed-length vector is a poor representation for variable-cardinality signals (rivalries, teammate list, coach identity). These get compressed into fixed-slot summaries, which loses some structure.
- Adding a feature is a schema migration — not a per-run config tweak. This slows iteration on "what if we also conditioned on X?"
- Caching correctness depends on graph snapshots being truly immutable. One stray hotfix-in-place to a snapshot poisons the cache.

**Neutral.**

- The confidence block is first-class (`ConfidenceBlock`) because Phase 1 inference is uneven — some players have thousands of matches, some have six. Downstream consumers are expected to attend to confidence, not just the point estimate.

## Alternatives considered

**(A) Let each component derive its own features from the graph.** Rejected — guarantees drift. Diagnosing "why does my world model's Aspas feel wrong" becomes a four-place investigation instead of one.

**(B) Graph-conditioned instead of vector-conditioned models.** Pass the subgraph around, let each model attend. Rejected for v1 because it's an order of magnitude more engineering and doesn't buy the fixed-length interface that makes the RL/world-model plumbing tractable on one 5090. Explicit revisit point below.

**(C) Unversioned PPV with an evolving shape.** Rejected because it makes experiment reproducibility impossible: a rollout produced under "PPV as of April" cannot be faithfully reloaded after PPV gains a dimension in June.

## Schema versioning policy

- `PPV_v1.schema_version: Literal[1]` is checked at every read boundary. Mismatch is an error, not a warning.
- A new field is a new version. No back-compat reads — rollouts are always re-generated against the active version when the version bumps.
- The experiment registry records the PPV version a run was trained under.

## Revisit when

- Variable-cardinality signals (rivalries, coach transitions mid-era) consistently move the needle on eval metrics.
- The graph-conditioned world model is feasible on a single GPU.
- A Phase-1 finding shows that confidence-weighted conditioning works substantially better than point conditioning — might justify passing the ConfidenceBlock into the model.
