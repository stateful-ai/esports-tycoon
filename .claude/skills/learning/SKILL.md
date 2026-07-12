---
name: learning
description: Train or extend learned player and manager policies without leaking hidden state, breaking replay determinism, or promoting an unvalidated checkpoint.
---

# Learning - policy training and promotion workflow

Use this skill for learned player policies, learned manager policies, policy
datasets, checkpoint compatibility, or online simulated improvement.

## Pick the boundary first

| Policy | Observation/action contract | Resolver |
|---|---|---|
| In-match player | Typed `PlayerObservation` plus engine-supplied legal `Action` / `CommunicationAction` candidates | Match engine |
| Manager | `decision_env.manager_observation` plus its legal-action mask | `HeadlessManagerEnv` |

Never give either policy raw hidden state. A learned model ranks or samples
only candidates the resolver supplied; it never invents IDs, actions, or
parameters.

## Determinism and data

- Generate demonstrations and rollouts from explicit, recorded seed lists.
  Train, validation, and promotion evaluation seed sets must be disjoint.
- Sort candidate rows before encoding or ranking. Profile conditioning may use
  stable hashes/blake2 buckets, never Python `hash()`.
- A player policy samples with the engine-provided RNG. Offline manager
  exploration may use NumPy only when its seed is a stable hash of run,
  profile, and iteration identifiers; it may never alter campaign state
  outside `HeadlessManagerEnv`.
- Preserve fog-of-war: observations are the contract. Adding a convenient
  hidden field to improve a metric invalidates the policy.

## Checkpoints and promotion

- Pin and validate policy version, observation version, encoder version,
  vocabulary, and profile schema. Reject mismatches on load.
- Store seed lists, profile IDs, training metrics, and held-out evaluation in
  metadata. Keep candidates separate from champions.
- Online manager updates modify only the action-category head; learned
  parameter heads still construct legal player, staff, tactics, and offer
  details.
- Promote only if every held-out rollout completes with zero invalid actions
  and the challenger clears reward, balance, wins, and profile-distinctness
  guards. A blocked advance needs deterministic recovery (accept job/sign),
  not extra random retries.

## Commands and checks

- Player imitation: `scripts/train_player_policy.py <checkpoint>`; inspect
  action accuracy alongside macro/non-hold recall and legal rate.
- Manager imitation: `scripts/train_manager_policy.py`; retain train and
  validation rollout exports.
- Manager online improvement: `scripts/online_train_manager_policy.py
  <checkpoint>`; it always writes a candidate but writes a champion only on
  promotion.
- Run focused policy tests plus resolver tests. For a deployed campaign-policy
  change, run held-out evaluation and the snowball gate if it can shift
  long-run competitive balance.
