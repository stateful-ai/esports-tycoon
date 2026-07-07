# ADR-003 — One event schema across all producers and consumers

Date: 2026-04-23
Status: Accepted
Deciders: Aidan (solo)
Related: ADR-001

## Context

Three components in Nexus produce match trajectories:

1. The tick match engine (C3) — ground-truth 2D simulation.
2. The RL rollout path (C4) — the same engine but recording for training.
3. The world model (C5) — a neural simulator trained to imitate #2.

Three components consume them:

- The reward function (part of C4).
- The world-model training loop (C5).
- The game client (C7).

If producers and consumers negotiate schema pairwise, the stack rots. Especially dangerous: the world model outputting a *slightly different* event format than the tick engine — every downstream consumer then has to branch, and behavioral drift becomes invisible.

## Decision

`src/esports_sim/schemas/events.py` is the single source of truth for match trajectory data. Every producer — tick engine, RL rollout, world model — emits a `list[EventUnion]` of the same discriminated-union types. Every consumer reads the same type.

Adding a new event type requires:

1. A pydantic model in `events.py` with a literal `type` discriminator.
2. Inclusion in `EventUnion`.
3. Handler updates in every consumer that cares (reward, narrative, renderer). Consumers that don't care tolerate unknown-to-them types by default (pydantic discriminated union will parse; consumer-specific dispatch ignores what it doesn't handle).

The world model's output head is constrained to produce valid `EventUnion` members. This is a real constraint — it shapes the model architecture (action/event decoder) and it's intentional.

## Consequences

**Positive.**

- A world-model rollout and a tick-engine rollout are interchangeable by construction. The game client cannot tell them apart; the evaluation classifier for the Phase 3 milestone is the one thing that should.
- Schema validity is enforced at parse time (pydantic `extra="forbid"`), not via downstream assertion churn.
- JSONL on disk remains human-readable and diff-able — crucial for debugging when the world model starts producing nonsense.

**Negative.**

- The world-model architecture is constrained by the event schema shape. We cannot quietly swap to a dense tensor representation for training efficiency without breaking the contract (we'd need to add a shadow format alongside — see ARCHITECTURE §11).
- Schema migrations require coordinated changes across producers and consumers. There is no cheap "just add a field" in the hot path.
- Event log sizes are larger than a packed tensor would be. Zstandard helps; this is budgeted for.

## Alternatives considered

**(A) Different schemas per producer, with translators.** Rejected — translators are the exact place drift hides. "Why does the world model's KillEvent have `is_trade` wrong?" becomes a translator bug instead of a model bug.

**(B) Free-form JSON events.** Rejected — no typing, no parse-time validation, every consumer re-invents validation.

**(C) Protobuf or flatbuffers instead of pydantic.** Defensible at 10x scale but overkill at solo-scale. pydantic gives us Python-native typing, discriminated unions, and JSONL on disk, all of which are easier to debug. Revisit if rollout deserialization becomes a measurable bottleneck.

## Revisit when

- Event log storage exceeds a few hundred GB and zstd is no longer enough.
- The world model wants an internal representation that diverges hard from discrete events (e.g., continuous latent rollouts with intermittent event decoding).
- A second game-type gets added and its event needs disjointly differ — would argue for namespacing (`valorant.round.kill` vs `something.round.kill`).
