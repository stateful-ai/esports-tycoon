# ADR-001 — Training substrate: RL rollouts feed the world model

Date: 2026-04-23
Status: Accepted
Deciders: Aidan (solo)
Supersedes: —
Related: ADR-002 (PPV), ADR-003 (event log)

## Context

The world model (C5) is Nexus's novel bet. It needs a training corpus of gameplay trajectories conditioned on player identity. Three plausible sources of that corpus exist:

1. **Scraped real matches.** Authoritative but thin — Riot and VLR give you outcomes and summary stats, not tick-level positional data. You cannot train a 2D trajectory model on "SEN won 13-9".
2. **Scripted bots in the tick engine.** Cheap and infinite but data is flat — every match looks the same because behavior does not vary by player. World model learns a blurry average of one playstyle.
3. **RL agents conditioned on player profile vectors, running in the tick engine.** Expensive in compute but the rollouts inherently vary by player because the policies do. This is the only path where conditioning actually has something to condition on.

## Decision

Option 3. RL agents (C4) are the world model's (C5) training data source. The tick match engine (C3) is their training environment. Every RL rollout is a `RolloutRecord` with the PPVs used to condition the policy inlined, so rollouts are self-describing artifacts even if the underlying graph later changes.

## Consequences

**Positive.**

- The world model sees trajectory distributions that actually depend on player identity — the whole point of conditioning.
- Training data volume is bounded only by 5090 hours, not by scraper throughput.
- A frozen rollout dataset is a reproducible artifact: given seed + policy checkpoints + PPVs, you regenerate bit-for-bit.

**Negative.**

- Phase 3 blocks on Phase 2 being done well enough that its rollouts are worth training on. If RL policies are garbage, the world model learns garbage-distinguishing-by-player.
- RL throughput becomes the critical-path resource. Every minute of RL-env speed saved is a world-model iteration unlocked.
- The world model can only learn behaviors the RL policies exhibit. If RL never learns to fake-defuse, the world model cannot roll that out.

**Neutral but important.**

- Real-match data is still useful but in a different role: it trains the PPV derivation (C2) and validates that RL rollouts land in a plausible basin (e.g., kill rates, round win rates match league distributions). It is not directly world-model training data.

## Alternatives considered

**(A) Pretrain the world model on scripted bot rollouts, fine-tune on RL.** Rejected — pretraining gives you a prior about "a match looks like this" but the conditioning signal only exists in the RL data, so pretraining adds wall-clock without adding the thing we care about. Revisit if RL rollout cost is prohibitive.

**(B) Distill from an LLM describing matches.** Rejected on budget grounds (C8) and because tick-level positional trajectories are not what LLMs produce well. Possible future: LLM-generated match *summaries* as aux objective.

**(C) Skip the world model entirely; use RL policies live at game time.** Rejected because RL policy inference is expensive enough that a game simulating a 20-match season means 2000+ rounds, each needing multi-agent inference. World-model rollouts amortize that cost to a single forward pass per rollout.

## Revisit when

- RL wall-clock to reach "basin-plausible" policies exceeds two months.
- A real tick-level VCT data source appears (Riot public demos with positional data).
- Open-weight world-model foundation models for 2D competitive gameplay exist — pretraining shifts the math.
