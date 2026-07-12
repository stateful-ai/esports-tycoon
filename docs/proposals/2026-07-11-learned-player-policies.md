# Learned player policies in the match engine

Date: 2026-07-11
Status: Phase 1 and dependency-light learned baseline implemented
Owners: Match simulation / research

## Implementation status

Implemented in the first vertical slice:

- injectable per-match `PlayerPolicy` and optional policy-owned comms;
- versioned compositional `PlayerConditionV1` with no player-id shortcut;
- private sight observations with decaying memory and no buy-phase leak;
- structured communication claims and a receiver-specific shared whiteboard;
- deterministic dropout, latency, topology-plausible corruption, confidence
  decay and misremembering, all on match/claim/sender/receiver RNG paths;
- a parallel heuristic comms head plus a byte-identical compatibility mode;
- typed action/comms demonstration traces;
- a NumPy learned player model matching the learned-manager architecture:
  legal candidate ranking, profile-conditioned hypernetwork/FiLM interaction,
  deterministic full-batch imitation training and version-pinned JSON
  checkpoints;
- `scripts/train_player_policy.py` for producing a baseline artifact.

Still intentionally deferred to later phases: moving shoot/utility/peek and
team macro ownership fully out of `engine.py`, vectorised self-play, recurrent
memory, PPO/MAPPO, population training, and promotion of a trained artifact as
the default game policy.

## Outcome

Replace hand-authored player decision rules with a shared learned policy that
makes legal in-match choices and is conditioned on each player's role,
playstyle, personality, traits, skills, agent mastery, current mental state,
and team instructions.

The intended result is not ten unrelated neural networks. It is one capable
base policy with lightweight player conditioning. Two equally skilled players
should remain competitive while making recognisably different choices: an
aggressive entry takes space earlier, a patient anchor preserves utility, and
a volatile star becomes less predictable under pressure. Player development
must alter both execution quality and decision quality without turning every
high-rated player into the same optimal archetype.

This is a policy replacement, not a neural match simulator. The deterministic
engine remains authoritative for legal actions, movement, combat, economy,
utility effects, objectives, and canonical events.

## Why the existing seam is promising but not yet sufficient

The repository already has the correct high-level boundary:

- `PlayerPolicy.decide(observation, legal_actions, rng) -> Action`
- `HeuristicPolicy` is replaceable without changing event consumers.
- The engine validates and resolves actions.
- `PlayerObservation` prevents policies from reading the full match state.

However, the current learned-policy surface is not training-ready:

- The engine creates one shared `HeuristicPolicy`, rather than resolving a
  policy/runtime per player or per match configuration.
- Policy calls mostly occur when an engine-authored order becomes dirty. The
  engine still owns site choice, executes/defaults, defensive assignments,
  rotations, fallback, retakes, saves, utility timing, peeking, and shooting.
- `PlayerObservation.enemies` is currently always empty and there is no
  explicit memory, sound, visible-event, objective-timer, score, economy, or
  teammate-intent representation.
- The legal action vocabulary exists, but the current application path only
  meaningfully applies movement, plant, defuse, hold, and wait. Combat and
  much utility decision-making bypass the policy.
- The policy must look up the `Player` in `GameData`; identity and mutable
  campaign state are not an explicit, versioned conditioning contract.
- A single round RNG generator is passed to all decisions. That is
  deterministic today, but batching or changing inference order could change
  later draws.

Training a model before addressing these gaps would reproduce the scripted
engine with extra latency and weaker debuggability.

## Product boundaries

### In scope

- Player-controlled tactical decisions inside a round: movement intent,
  hold/peek, target selection, utility use, plant/defuse, save/retake, and buy
  preference where the player legitimately owns the choice.
- A shared learned backbone conditioned by a versioned player profile.
- Role/playstyle adapters and player-specific conditioning generated from
  profile features; no manually stored checkpoint per generated player.
- Offline training and evaluation, frozen inference artifacts, deterministic
  match-time inference, heuristic fallback, and shadow/A-B rollout modes.
- Telemetry that explains which observation, legal-action mask, profile
  version, model version, logits, and selected action produced an event.
- Gradual transfer of decision ownership from engine rules to policies.

### Out of scope for the first release

- Replacing physics/combat/event resolution with a world model.
- Live LLM calls during matches.
- End-to-end learning from pixels or viewer frames.
- Online learning inside a campaign save.
- A unique full model or permanently mutable embedding for every generated
  player.
- Letting models emit arbitrary coordinates, prose, or events.
- Removing the heuristic policy; it remains the compatibility and safety
  baseline.

## Proposed architecture

### 1. Keep a hard engine-policy boundary

Introduce a policy runtime selected through `MatchConfig`, not constructed
inside `MatchEngine`:

```text
MatchEngine
  -> ObservationBuilder (versioned, fog-of-war safe)
  -> LegalActionBuilder (typed candidates + mask)
  -> PlayerPolicyRuntime
       - heuristic
       - learned
       - shadow (heuristic acts, learned policy logs)
  -> ActionValidator
  -> deterministic engine resolution
  -> canonical EventUnion log
```

The runtime receives a batch of decision requests in stable player-id order.
The engine owns invalid-action recovery: mask before inference, validate after
inference, then choose a deterministic safe action if the artifact is corrupt.

### 2. Version the decision contract

Add immutable, tensor-friendly contracts alongside the human-readable
Pydantic schemas:

- `ObservationV1`: self state, teammates, private perceptions, the player's
  current read of the shared team whiteboard, visible/recent events,
  map-local topology, clock/objective, score/economy context, team call, and
  short recurrent state key.
- `ActionCandidateV1`: action type plus enumerated target/callout/ability.
  Candidate ordering is canonical and the model produces a masked categorical
  choice over candidates.
- `PlayerConditionV1`: the only player-personality input used by policies.
- `DecisionRecordV1`: observation/action/profile/model versions, legal mask,
  selected action, behaviour-policy probability, and optional logits/value.

Every version and feature order is frozen. A shape or semantic change creates
V2 and a new model run; it never silently changes V1.

### 3. Make team knowledge a fallible shared whiteboard

Fog of war needs an explicit information lifecycle. The team must not receive
perfect enemy state merely because one player saw or inferred it. Model four
separate layers:

1. **World truth** is private to the engine and never enters an actor
   observation.
2. **Private perception** is what a player saw, heard, or inferred. It may
   already be incomplete or wrong based on line of sight, sound ambiguity,
   attention, game sense, stress, flashes, and recency.
3. **Communication** is a policy decision to publish a structured claim. A
   player may communicate promptly, late, vaguely, not at all, or incorrectly.
4. **Team belief** is the shared whiteboard assembled from those claims. Each
   receiving player reads an individually reconstructed, decaying version of
   it and may misremember or misinterpret it.

The whiteboard contains beliefs, never authoritative enemy records. Suggested
typed claims include:

```text
EnemyLocation(enemy_or_unknown, callout, confidence, observed_tick)
EnemyIntent(site_or_route, intent, confidence, observed_tick)
EnemyStatus(enemy_or_unknown, weapon/class, hp_band, utility_hint, confidence)
AreaStatus(callout, clear|contested|unknown, confidence, observed_tick)
ObjectiveInfo(spike_seen|spike_dropped|planting, callout, confidence)
TeamIntent(callout, hold|rotate|retake|save|trade, urgency)
Correction(prior_claim_id, replacement_claim)
```

Claims use enumerated map and intent vocabulary; policies never generate free
text. The engine attaches stable ids and source/timing metadata, applies
deterministic delivery delay, and maintains the append-only round comms
ledger. `ObservationV1` receives a bounded materialised whiteboard view rather
than the whole ledger.

`comms_quality` should influence several distinct failure modes rather than a
single accuracy multiplier:

- probability that a useful private perception is communicated at all;
- latency before the claim reaches teammates;
- specificity (named enemy and exact callout versus "one near A");
- transmission corruption, such as adjacent callout, wrong count, wrong
  enemy, stale intent, or overconfident wording;
- probability and speed of correcting an earlier bad call;
- signal-to-noise: repeated or low-value claims can crowd the bounded
  whiteboard and teammates' attention.

The learned policy still owns whether and what to communicate. Skill defines
the noisy channel and available fidelity, not a rule that forces every
high-comms player to report every fact. Personality, role, pressure, team
tactics and information value can therefore produce quiet stars, vocal IGLs,
panicked spam, deliberate silence, or confident wrong calls.

Belief decay should depend on claim type and game state. A sighting becomes
stale quickly once the enemy could traverse an edge; a dropped-spike claim
persists until contradicted or recovered; an area-clear claim expires once an
unseen route could repopulate it. Old location claims should collapse into a
probability over reachable callouts instead of remaining permanent pins.

Misremembering happens when a player materialises the shared ledger into an
individual observation. Its probability and severity can depend on the
receiver's `game_sense`, `comms_quality`, composure/tilt, language overlap,
relationship cohesion, simultaneous message load, and elapsed time.
Corruption stays plausible: locations move to adjacent/reachable callouts,
counts drift slightly, identity becomes unknown, and intent becomes less
certain. Impossible information becomes unknown rather than random nonsense.

All channel and memory errors draw from stable `RngTree` paths containing the
claim id, sender, receiver and error stage. The same communication remains
identically wrong on replay, independent of policy batching order.

Crucially, an actor must not receive `was_wrong`, hidden ground-truth
confidence, pristine source perception, or metadata that reveals which comms
are corrupted. Source identity, age and expressed confidence may be visible;
truth is learned only when later perception or contradiction supplies evidence.

### 4. Use one shared policy with compositional conditioning

Recommended v1 model:

- A small shared encoder for symbolic observations and candidate actions.
- A recurrent core (GRU initially) for within-round memory. A small
  Transformer is only justified if the event/history sequence proves useful.
- A role/playstyle adapter selected from a small learned bank.
- FiLM-style modulation of hidden layers from `PlayerConditionV1`.
- Optional low-rank adapter deltas generated by a small hypernetwork from the
  condition vector.
- Masked policy head over legal candidates and a value head for training.

Start with FiLM plus a role adapter. Add hypernetwork-generated LoRA only if
ablation shows it improves identity fidelity without destabilising gameplay.
This gives generated rookies coherent behaviour immediately and avoids an
unbounded model-artifact problem.

The condition vector should separate capabilities from preferences:

- **Capability:** mechanical, tactical, communication and mental attributes;
  agent/map mastery; stamina/form. These should affect what the policy can
  recognise or execute well, not simply multiply every preferred action.
- **Identity:** role, playstyle, stable personality axes derived from tags,
  and mechanically meaningful traits.
- **Situation:** confidence, momentum/tilt, side, assigned agent, current team
  tactics, chemistry, and IGL instruction.

Stable identity must not include player id in v1. Otherwise the model can
memorise roster-pack players and cannot generalise identity to generated
players. If later evidence supports individual residuals, use a bounded,
regularised residual embedding with a zero/default path for unseen players.

### 5. Preserve determinism explicitly

Model inference must be reproducible, not merely usually stable:

- Frozen `safetensors` artifact, model config, feature schema, normalization
  statistics, code revision, and content hash recorded under a run id.
- Evaluation mode only; no dropout, mutable batch-norm, online updates, or
  ambient randomness.
- CPU inference is the canonical golden-test runtime initially. GPU inference
  may be used for training and corpus generation after cross-device drift is
  characterised.
- Stochastic action sampling uses a per-decision `RngTree` path such as
  `(match, round, tick, player, decision_index, policy_run_id)`. Batching and
  iteration order cannot alter another player's draw.
- Logits are converted to probabilities in one pinned implementation. For
  maximum replay longevity, quantise logits or use a pinned deterministic
  categorical sampler rather than depending on backend sampling kernels.
- A save records the policy artifact id needed to replay it. Missing artifacts
  fail clearly or use an explicitly marked compatibility mode; they do not
  silently change policy.

Determinism tests should run the same match across repeated processes, batch
sizes, and supported devices. Byte-identical event logs remain the contract.

## Training strategy

### Bootstrap rather than cold-start self-play

1. Instrument the current heuristic/engine decisions as `DecisionRecordV1`.
   Record private perceptions, communication decisions, delivered claims,
   per-receiver belief views, contradictions and corrections. Hidden truth is
   retained only for critic/evaluation data and is structurally absent from
   actor observations.
2. Extract currently embedded rule decisions behind policy-owned expert
   actions, preserving behaviour while broadening the action contract.
3. Train behavioural cloning on that expert corpus so the learned runtime can
   complete matches legally and reproduce baseline pacing/economy.
4. Fine-tune with multi-agent self-play using parameter sharing and centralised
   training/decentralised execution.
5. Train against a population: frozen heuristic, prior checkpoints, and
   diverse conditioned policies. This reduces cyclic exploits and collapse.

### Rewards

Use an event-derived hierarchy, with coefficients in versioned training
config rather than match-engine constants:

- Primary: round and match outcome.
- Team credit: plant/defuse, trades, useful survival/save, space gained, and
  successful retake/hold.
- Role-sensitive auxiliary credit: entry/trade timing, information converted,
  utility value, anchoring delay, lurk pressure, and economy discipline.
- Penalties: illegal/fallback action, friendly obstruction if modelled,
  purposeless oscillation, utility waste, baiting that does not convert, and
  timeout/idling.

Role rewards should speed learning, not dictate personality. Identity comes
from conditioning and diversity objectives; otherwise every duelist becomes
the same reward-shaped caricature.

### Making conditioning matter

Self-play can learn to ignore profile inputs. Require explicit anti-collapse
objectives and evaluation:

- Randomly pair the same observation with different player conditions.
- Contrast trajectory embeddings: same condition should be more similar than
  shuffled conditions after controlling for skill and role.
- Predict condition attributes from trajectories with an auxiliary probe.
- Regularise policy divergence into a target band: enough behavioural
  separation to be recognisable, not enough to make a trait irrational.
- Use counterfactual swaps: identical seed/team/state, change only one
  conditioning block and measure the expected behavioural delta.

## Delivery plan

### Phase 0 - Baselines and design decisions (about 1 week)

- Inventory every rule in `engine.py` as engine resolution, team/IGL decision,
  or player decision.
- Record current match, balance, pacing, action-frequency, role and style
  distributions as the comparison baseline.
- Write ADRs for decision-contract versioning, inference determinism, artifact
  retention, and player-conditioning ownership.
- Decide whether the existing historical Nexus PPV documents represent the
  active game architecture or need a game-native `PlayerConditionV1` adapter.

Exit: an agreed ownership table and frozen V1 schemas.

### Phase 1 - Training-ready policy seam (2-3 weeks)

- Inject policy runtime through match configuration.
- Build complete fog-of-war observations and stable legal candidate lists.
- Add the engine-owned round comms ledger, structured claim vocabulary,
  deterministic noisy delivery, belief decay, and per-receiver misremembering.
- Add a parallel communication decision channel so players can send,
  withhold, repeat, qualify, or correct claims without using free text.
- Move player-owned shoot/peek/utility/objective/buy choices behind policy;
  keep macro IGL calls scripted initially.
- Allocate per-decision RNG paths and decision indices.
- Add invalid-action fallback and decision telemetry.
- Expand `HeuristicPolicy` to cover the new contract with no intended gameplay
  change, then deliberately re-bless only if action ownership changes logs.

Exit: heuristic matches run entirely through the V1 player-decision contract,
with deterministic logs and all existing gates green.

### Phase 2 - Offline model baseline (2-3 weeks)

- Add an optional research dependency group (PyTorch, safetensors, training
  tools); keep the shipped core install model-free unless learned inference is
  enabled.
- Export expert decision datasets with feature and artifact fingerprints.
- Train a small masked behavioural-cloning model.
- Add `LearnedPolicyRuntime`, artifact loader, batching, and shadow mode.
- Compare legality, outcome, pacing, economy and throughput against heuristic.

Exit: the learned policy completes 10,000 shadow/offline matches with zero
uncaught illegal actions and meets a defined performance budget.

### Phase 3 - Conditioned multi-agent self-play (4-8 weeks)

- Add FiLM player conditioning and role/playstyle adapter bank.
- Implement vectorised match environments and recurrent-state lifecycle.
- Train parameter-shared PPO/MAPPO-style policies against a checkpoint
  population.
- Add conditioning anti-collapse objectives and counterfactual eval suites.
- Ablate base-only, concatenation, FiLM, adapters, and hypernetwork LoRA.

Exit: learned policies meet gameplay gates and conditioning changes behaviour
in expected directions without unacceptable win-rate distortion.

### Phase 4 - Controlled game rollout (2 weeks plus soak)

- Ship learned policy as opt-in or experimental, with heuristic fallback.
- Run large fixed-seed regression and multi-season campaign soaks.
- Add model/artifact diagnostics to developer tools and replay metadata.
- Promote to default only after balance, pacing, identity, determinism,
  performance and save-compatibility gates pass.

Exit: the learned policy can be selected for normal campaigns and old saves
retain an explicit, reproducible policy mode.

## Evaluation gates

### Correctness and safety

- 100% selected actions legal after masking; any fallback is counted and must
  remain below an agreed near-zero artifact-error threshold.
- No policy can emit an event or mutate match state directly.
- Same seed, conditions and artifact produce byte-identical event logs across
  repeated processes and supported batching configurations.
- Observation tests prove no hidden enemy state leaks through features,
  candidate ordering, masks, or recurrent-state handling.
- Communication leak tests prove corrupted claims carry no hidden correctness
  marker and actor tensors cannot recover pristine perceptions or world truth
  through ids, padding, ordering, or confidence fields.

### Gameplay

- Existing golden, attack/defence balance, pacing and tactics gates pass under
  the declared learned-policy baseline. Learned policies need their own pinned
  golden artifact rather than replacing the heuristic golden.
- Economy, round duration, plant rate, retake/save rate, trade rate, utility
  usage and role participation stay in plausible bands.
- Exploit suite covers oscillation, spawn camping, refusal to plant/defuse,
  degenerate saving, utility dumping, and teammate bait loops.

### Identity fidelity

Counterfactual fixed-seed tests should measure monotonic, bounded tendencies:

- Entry/aggression increases early contact and first-engagement share.
- Anchor/patience increases site dwell and delays rotation without ignoring
  confirmed commits.
- Support/team-player increases trade proximity and utility-before-contact.
- AWPer changes weapon preference, sightline choice and reposition cadence.
- High game sense improves information response and risk selection.
- Calm/ice-cold reduces decision entropy change under pressure; volatile or
  hot-headed traits increase it within a safe band.
- High comms quality improves useful delivery, correction speed and
  calibration, but does not guarantee that every sighting is called.
- High game sense improves retention and interpretation of stale or conflicting
  claims; stress, poor cohesion and message overload increase plausible
  misremembering.
- Higher skill improves outcomes without erasing style separation.

Use distributions over thousands of paired rollouts, not assertions about one
seed. A blinded trajectory classifier should identify archetype above chance,
while a player-id classifier should not succeed for unseen/generated players.

### Performance

- Establish budgets in Phase 0 from current throughput. Initial targets:
  model inference adds less than 25% to single-match wall time when batched,
  and corpus generation remains fast enough for the planned rollout volume.
- Report decisions/second, matches/hour, peak memory, batch utilisation, and
  CPU/GPU parity for every candidate artifact.

## Likely code and artifact surface

```text
src/esports_sim/policy/
  base.py                  # versioned runtime/batch protocol
  heuristic.py             # complete V1 expert and fallback
  observation.py           # feature builder; no model dependency
  conditioning.py          # Player -> PlayerConditionV1
  learned.py               # artifact-backed inference runtime
  sampling.py              # pinned deterministic masked sampler

src/esports_sim/sim/
  comms.py                 # truth-free claim ledger, delivery and decay
  beliefs.py               # per-receiver whiteboard materialisation
  engine.py                # inject runtime, resolve actions only
  match_config.py          # policy/artifact selection

src/esports_sim/schemas/
  observation.py           # richer fog-of-war contract
  decision.py              # candidates and decision records
  policy_artifact.py       # manifest metadata

src/esports_sim/research/player_policy/
  dataset.py, env.py, model.py, train_bc.py, train_selfplay.py, evaluate.py

configs/player_policy/
  bc_v1.yaml, selfplay_v1.yaml, eval_v1.yaml

runs/{run_id}/
  manifest.json, ckpt/*.safetensors, metrics/, decisions/, rollouts/
```

Model binaries and large datasets remain outside Git. Tiny deterministic test
fixtures and artifact manifests may be committed. Production promotion should
pin a content-addressed artifact location plus checksum.

## Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Model merely imitates IGL scripts | Move genuine player choices behind the policy before training; progressively relax macro calls. |
| Conditioning is ignored | Counterfactual training pairs, auxiliary probes, divergence-band regularisation, and mandatory ablations. |
| Personality overwhelms skill | Separate capability and preference inputs; bound adapter output; gate on paired win-rate and style metrics. |
| Reward hacking produces ugly play | Population opponents, event-derived exploit metrics, heuristic opponents, and replay review of metric outliers. |
| Neural nondeterminism breaks replay | Canonical CPU path, pinned artifacts/runtime, per-decision RNG, quantised/pinned sampler, cross-process tests. |
| Inference makes seasons too slow | Batch the ten players, infer only at meaningful decision points, profile feature building, distil/quantise after quality. |
| Generated players lack learned identity | Condition on compositional traits rather than player id; always support a zero/default residual. |
| Save depends on missing model file | Persist artifact id/hash, retain promoted artifacts, and make fallback explicit and visible. |
| Policy learns hidden information | Centralised critic only during training; actor gets exactly `ObservationV1`; fog-of-war leak tests. |
| Wrong comms feel arbitrary or unfair | Restrict corruption to plausible topology/status transforms, expose source/age/expressed confidence, and make later evidence visibly correct beliefs. |
| Shared whiteboard becomes perfect team telepathy | Require explicit communication and noisy delivery; private perception never writes directly to team belief. |
| Models spam comms to maximise information | Bound attention/whiteboard capacity, rate-limit speech, track duplication, and reward information that changes a useful teammate decision. |
| Learned policy destabilises balance | Separate learned-policy gates and staged opt-in; never overwrite the heuristic baseline. |

## Open decisions

1. Does the learned player control macro intent (site call, rotate/save/retake)
   in v1, or only execution under an IGL order? Recommendation: execution plus
   individual rotate/save/retake in V1; team site strategy remains an explicit
   IGL policy and becomes learned separately.
2. Is the older documented PPV pipeline active and authoritative for this
   game's current player schema? Recommendation: define a game-native,
   versioned `PlayerConditionV1`, with a future adapter from PPV rather than
   blocking on the external data pipeline.
3. Should normal game distribution require PyTorch? Recommendation: no for the
   first experiment. Keep training optional and evaluate ONNX Runtime or a
   small pinned inference runtime only after a policy proves valuable.
4. What is the canonical inference platform for long-term replay?
   Recommendation: deterministic CPU first, then explicitly certify faster
   backends per artifact/runtime version.
5. How much autonomy should a player have to disobey an IGL call?
   Recommendation: model this as a legal deviation with bounded cost and
   condition it on comms, game sense, confidence and personality; do not hide
   disobedience in stochastic engine rules.
6. Are comms simultaneous with physical actions or do they consume a decision
   opportunity? Recommendation: use a small parallel communication head with
   rate limits and an attention cost. Speaking should not replace movement for
   a whole tick, but unlimited zero-cost broadcasting will become optimal and
   erase personality.

## Recommended first milestone

Do not begin with PPO or a hypernetwork. Deliver Phase 0 and Phase 1 as one
vertical milestone: a versioned, fog-of-war-safe decision dataset in which the
expanded heuristic policy owns all individual player choices and the engine
only resolves them. That artifact will reveal the true action frequency,
observation gaps, throughput ceiling, and class imbalance. Those measurements
are the evidence needed to choose the smallest useful learned architecture.
