# Nexus — Cross-cutting architecture

Status: Working design, v0.1 — 2026-04-23
Bias: Research-first. The world model is the load-bearing deliverable; other layers are scaffolding for its training signal.

## 1. Thesis

Nexus ships two products off one engine: a B2B "Bloomberg terminal for esports" (the ecosystem simulator) and a consumer tycoon game. The technical bet that makes both possible is a conditioned 2D match world model — a neural simulator whose rollouts vary plausibly by the player the match is being played by. Everything else in the stack exists to produce, condition, or consume this model's output.

That frames every design decision below. If a choice helps the world model train faster, converge better, or condition more sharply, it wins. If it only makes the game prettier or the pipeline neater, it goes to the back of the queue.

## 2. Systems map

```
                    +---------------------------+
                    |   External sources        |
                    |   VLR, Liquipedia,        |
                    |   Riot API, transcripts   |
                    +------------+--------------+
                                 |
                    +------------v--------------+
  LAYER 1 (done     |  Data pipeline (01-10)    |
  on paper,         |  ingest -> staging ->     |
  impl in phase 0)  |  canonical graph          |
                    +------+--------+-----------+
                           |        |
                           v        v
                +----------+--+  +--+----------------+
                |  PPV service|  |  Patch-era graph  |
                |  C2         |  |  snapshots (PyG)  |
                +---+--+--+---+  +--+----------------+
                    |  |  |        |
       +------------+  |  +--------+----+
       |               |               |
       v               v               v
  +----+-------+   +---+--------+  +---+----------+
  | Tick match |   | RL runtime |  | Ecosystem    |
  | engine C3  |<--+ C4         |  | engine C6    |
  +----+-------+   +---+--------+  +---+----------+
       |               |               |
       | event log     | rollouts      | season events
       v               v               |
  +----+---------------+------+        |
  |  Rollout store            |        |
  +----+----------------------+        |
       |                               |
       v                               |
  +----+----------+                    |
  | World model   |                    |
  | C5            |                    |
  +----+----------+                    |
       |                               |
       | conditioned rollouts          |
       v                               v
       +--------------+----------------+
                      |
                      v
              +-------+-------+
              |  Game client  |
              |  C7           |
              +---------------+

  cross-cutting: C8 budget governor, C9 experiment registry,
                 event schema, determinism/seed tree
```

## 3. Components

Each component is a stable contract: name, responsibility, inputs, outputs, owning layer, current status.

### C1 — Data pipeline (Systems 01-10)

Owned layer: data. Status: spec complete (systems_spec.html); impl is Phase 0.
Responsibility: ingest raw sources, reconcile identities, partition by patch era, derive stats, run LLM inference for dark data, build the relationship graph, export PyG HeteroData snapshots.
Inputs: external APIs and scrapers.
Outputs: (a) per-patch-era HeteroData snapshots, (b) canonical event log of matches, (c) confidence-scored inference table.
Downstream: C2, C6.

### C2 — Player Profile Vector (PPV) service

Owned layer: data boundary / shared. Status: to design.
Responsibility: compute a fixed-length, versioned vector describing a player's mechanical, tactical, behavioral, and relational traits for a given patch era. This is the universal conditioning input for RL, the world model, and the game.
Inputs: `(player_id, patch_era_id, as_of=None)`.
Outputs: `PPV_v1` — a dataclass with a stable float tensor view.
Downstream: C3 (as env input), C4 (as policy conditioner), C5 (as world-model conditioner), C7 (as player-card data).

Why it's load-bearing: every layer that needs to know "who this player is" goes through PPV. Versioning PPV is therefore versioning the training regime — see ADR-002.

### C3 — Tick match engine

Owned layer: match. Status: scaffolding exists (src/esports_sim/schemas, rng, events).
Responsibility: deterministic tick-level referee for a single best-of-one match. All available players receive a policy decision each live tick; team policies form round plans and coaches can enter only through timeout directives between rounds. Emits typed events; state is reconstructable from events. Already designed around a seed tree for reproducibility.
Inputs: `MatchConfig` (map, team lineups with PPVs, economy, patch era).
Outputs: event log (JSONL) + terminal `MatchState`.
Used as: (a) RL training environment, (b) ground-truth generator for world-model training, (c) replay source for the game until the world model takes over.

### C4 — RL agent runtime

Owned layer: match. Status: to design; Phase 2.
Responsibility: train PPV-conditioned policies for all five roles via multi-agent PPO or a close relative. Run in two modes: train (policy updates) and rollout (frozen policies, record only).
Inputs: C3 as env, PPVs as conditioning, reward spec from event log.
Outputs: checkpointed policies + compressed rollout records.
Why this matters for research: rollouts are the world model's training corpus. Rollout throughput caps world-model iteration speed. Everything about RL design — vectorized envs, rollout serialization, reward shaping — is downstream of that constraint.

### C5 — Match world model

Owned layer: match. Status: novel work; Phase 3.
Responsibility: a LeWM-scale (~15M params) 2D neural simulator that takes a condensed match state + per-team PPVs and predicts the next-state trajectory as events. Trained on C4 rollouts, FiLM-conditioned on PPVs.
Inputs: initial `MatchState`, per-player PPVs, patch-era embedding.
Outputs: rollout event log — same schema as C3's, so downstream consumers cannot tell the difference.
Validation: rollouts from a player's profile are distinguishable by classifier from rollouts of a different profile (Phase 3 milestone).

### C6 — Ecosystem engine

Owned layer: season. Status: to design; Phase 4.
Responsibility: between-match state transitions — contracts, fatigue, chemistry, sponsor negotiations, scrims, roster moves. Modeled as a heterogeneous GNN over the canonical graph plus LLM-driven agent reasoning for role-taking (GMs, sponsors, players).
Inputs: current season graph, match outcomes (from C3 or C5).
Outputs: season event log (non-match events: signings, interviews, storyline beats), next-match lineups.
Research stance: this is the B2B demo surface. It is not the world-model critical path — treat as secondary consumer.

### C7 — Game client (tycoon frontend)

Owned layer: game. Status: to design; Phase 4-5.
Responsibility: React/Zustand/Pixi single-player app. Player manages a team through a season; match sim is a cinematic replay of either C3 (early) or C5 (later); dialogue handled by LLM against agent personalities.
Inputs: ecosystem events (C6), match rollouts (C3 or C5), LLM API for dialogue.
Outputs: save files (JSON).

### C8 — LLM budget governor

Owned layer: cross-cutting infra. Status: to design; Phase 0.
Responsibility: gate every Claude API call across the whole system. Enforce tier-based cadence (Tier 1 players monthly, Tier 2 quarterly, event-triggered), batch coalescing, confidence-aware re-inference, hard weekly cap (~$40 / 4 budgets), local-model fallback (sentence-transformers for embeddings, Whisper for transcription).
Inputs: named "call site" + payload + confidence_of_last_call + priority tier.
Outputs: LLM response or a deterministic skip with "use prior value" signal.

### C9 — Experiment registry

Owned layer: cross-cutting infra. Status: to design; Phase 0-2.
Responsibility: every training run, scraper sync, PPV computation, world-model pretrain has a deterministic `run_id`. Stores config snapshot, dataset fingerprint, seed, output-artifact paths. Without this, research claims are unreproducible.
Inputs: `run_id`, `config`, `git_sha`, `data_fingerprint`.
Outputs: a SQLite table with run metadata + pointers into a local artifact store.

## 4. The critical loop

The single loop this system is built around:

1. Pipeline (C1) writes a new patch-era graph snapshot.
2. PPV service (C2) can now answer profile queries for that era.
3. RL runtime (C4) trains policies in the tick engine (C3), conditioned on PPVs. Rollouts stream to the rollout store.
4. World model (C5) trains on the rollout store. Checkpoints land in the experiment registry.
5. Ecosystem engine (C6) simulates a season; for each match, either runs C3 live or asks C5 for a conditioned rollout.
6. Game client (C7) renders.

Anywhere this loop is slow, research slows. Optimize throughput: rollout serialization, PPV caching, vectorized envs. Anywhere this loop leaks (mismatched schemas between layers), research breaks silently. Enforce contracts with code, not comments — see §6.

## 5. Data model (working sketch)

### 5.1 PlayerProfileVector (v1)

```python
class PPV_v1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    player_id: str
    patch_era_id: str
    as_of: datetime | None  # None = "full era"

    # Mechanical (from derived stats, C1 system 05)
    mech: MechanicalTraits     # aim_precision, reaction_time, peek_aggression, ...
    # Tactical (from event-derived positional stats)
    tact: TacticalTraits       # map_control_weights, role_fluidity, eco_discipline, ...
    # Behavioral (from LLM inference, system 06)
    behav: BehavioralTraits    # tilt_recovery, leadership, practice_hours_mu, ...
    # Relational (from relationship engine, system 07)
    rel: RelationalTraits      # team_chemistry, coach_trust, rivalries[:3], ...

    # Confidence per block — zero-inflated when data is thin.
    confidence: ConfidenceBlock

    def to_tensor(self) -> Float[Tensor, "D"]:
        """Flat float tensor of fixed size D_v1. D_v1 is frozen at schema
        version — see ADR-002."""
```

The dict-of-structs shape is the human/service view; `to_tensor()` gives the tensor view that RL and world model actually consume. Fixed `D_v1` makes the whole pipeline versioned together.

### 5.2 RolloutRecord

```python
class RolloutRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rollout_id: str
    match_config: MatchConfig
    ppvs: dict[str, PPV_v1]    # keyed by player_id; serialized inline
    seed: int
    source: Literal["tick_engine", "world_model"]
    policy_run_ids: dict[str, str]  # role -> policy run_id in C9
    events: list[EventUnion]   # from schemas/events.py — canonical
```

Rollouts are the frozen currency between C3/C4 (producers) and C5 (consumer). Stored as Zstandard parquet; PPVs inlined so a rollout is self-contained even if the graph is later mutated.

### 5.3 PatchEraSnapshot

Thin wrapper around a PyG `HeteroData` plus metadata: `patch_era_id`, coverage window (`start`, `end`), node counts, edge counts, structural-validation status. One snapshot per patch era, checkpointed to disk.

### 5.4 Event schema (existing)

`src/esports_sim/schemas/events.py` already defines a discriminated union. Contract: **the world model produces events, the tick engine produces events, ecosystem reasoning produces (different) events**. Any new event type is a schema migration — it needs to land in the union plus a consumer update in every downstream layer. See ADR-003.

## 6. Contracts and how they're enforced

The interfaces between components are the failure surface. Enforce them in code:

- **PPV schema**: pydantic `frozen=True`, `extra="forbid"`, plus a `schema_version` literal. Any consumer refuses to accept a different version.
- **Event union**: discriminated on `type`, `extra="forbid"`, written to/read from JSONL — already in repo.
- **Rollout records**: parquet schema pinned; a rollout without its PPV block inline fails validation at read time.
- **Graph snapshot**: a `validate_snapshot()` pass at C1 export time. Downstream refuses to train on a snapshot flagged "dirty".
- **Run registry**: every artifact path is reached via `registry.get(run_id)` rather than hardcoded — makes the blast radius of a rename zero.

Corollary: don't let layers talk via untyped JSON blobs or ad-hoc file globs. If layer B reads from layer A's disk layout directly, one rename breaks both.

## 7. Storage topology

Tiered by workload. Postgres for operational data (the shape of the canonical graph + inferred fields fits relational + JSONB), file-first for research artifacts (append-only binary streams that do not belong in a DB). Single-node throughout. See ADR-006 for the full rationale and options considered; this ADR supersedes the "file-first everywhere" stance of ADR-004.

| Tier | Store | Contents | Why |
|---|---|---|---|
| Raw | JSONL in `data/raw/{source}/{yyyy}/{mm}/*.jsonl.gz` | Scraper output as-is | Grep-able, append-only, cheap |
| Canonical operational | Postgres 16 | Entity, entity_alias, staging_record, inferred_field, patch_era, relationship_edge, api_ledger | Relational + JSONB + FK + pg_trgm + Phase-5-ready |
| Vector similarity | pgvector extension on Postgres | `personality_summaries`, `transcripts_chunks` embeddings | Co-located with entity rows — cross-entity JOINs trivial; no second service |
| Graph snapshots | PyG `.pt` files at `data/graphs/{patch_era}.pt` + pointer rows in Postgres | Per-era training-ready HeteroData | PyG serialization; Postgres holds metadata only |
| Rollouts | Zstd parquet in `runs/{run_id}/rollouts/*.parquet` | Event logs + inlined PPVs | Append-only, single-writer, huge — not a DB workload |
| Models | `runs/{run_id}/ckpt/*.safetensors` | Policy + world-model checkpoints | Versioned per run; binary; safetensors not pickle |
| Budget ledger | SQLite `state/budget.db` | Append-only LLM call log | Single-writer WAL; one-file durability fits the pattern |
| Registry | SQLite `state/registry.db` | `runs` metadata + artifact index | Same pattern as budget; see BUF-69 |
| Scheduler | Prefect 2 local | Flow runs + retries + backfills | Matches BUF-57 acceptance |
| Game saves | JSON under user profile | Single-player saves | Portable |

All paths are resolved through a `paths.py` module. Nothing hardcodes strings. Postgres connection string lives in `.env`; Prefect and Postgres both run via `docker-compose.yml`.

## 8. Runtime topology

There is no server. Nexus is a set of CLI entrypoints and batch jobs:

- `nexus ingest {source}` — run a scraper. Scheduled by cron/Windows Task Scheduler (see System 10).
- `nexus build-graph --patch-era N` — materialize the canonical snapshot.
- `nexus train-rl --config configs/rl/*.yaml` — RL training, writes rollouts + policy.
- `nexus train-wm --config configs/wm/*.yaml` — world-model training.
- `nexus simulate-season --save my-team.sav` — for the game.
- `nexus serve-game` — local FastAPI that the Pixi/React client calls.

The game client runs as a local Electron/Tauri shell against `serve-game`. No cloud. No multi-tenant. If Nexus ever grows to B2B SaaS, the ecosystem layer gets lifted into a container behind a per-tenant key — not today's problem.

## 9. Cross-cutting concerns

### 9.1 Determinism

Seed tree is already implemented (`src/esports_sim/rng/tree.py`). Extend the convention: every component that touches randomness declares a path (`["rl", "train", "env", "buy_phase"]`) rather than grabbing a global RNG. World-model rollouts must be replayable bit-for-bit given seed + checkpoints.

### 9.2 Budget governor (C8)

All Claude API calls flow through one module. It:
- logs the call to `state/budget.db` with tokens_in/out and dollar cost
- checks the weekly ledger; if over cap, returns `BudgetExceededSkip` with a `reason` and a `last_known_value` pointer
- supports `mode: {'fresh', 'cache_ok', 'never_now'}` per call site
- routes `embed/*` and `transcribe/*` calls to local models by default (sentence-transformers, Whisper large-v3)

If a layer wants to bypass it: they file an ADR.

### 9.3 Experiment registry (C9)

Before any `train-*` or `build-graph` command writes to disk, it registers a `run_id = uuid7()`, snapshots its config file verbatim, records the git SHA, and computes a dataset fingerprint (sha256 of sorted source-file list + row counts). Artifacts go under `runs/{run_id}/`. A run is not "done" until its row in `state/registry.db` is finalized.

This is what makes the research reproducible. Without it, a year-in claim like "world model v3 was 12% better than v2" has no meaning.

### 9.4 Observability

One log format (structured JSON via `rich` or `loguru`). Per-run logs go under `runs/{run_id}/logs/`. For anything performance-critical (RL rollout throughput, world-model train step), emit scalars to a TensorBoard event file under the same run dir. No external metrics service.

## 10. Non-functional budget

| Axis | Target | Why |
|---|---|---|
| RL rollout throughput | ≥ 10k matches/day on 5090 | Need ~1M matches for world-model v1 corpus; ~3 months wall-clock acceptable |
| World-model train step | ≥ 20 step/s on 5090 | LeWM-scale, mixed precision; keeps an experiment under 24h |
| LLM spend | ≤ $40/week total | Hard cap, governed by C8 |
| PPV query latency | ≤ 5ms warm, ≤ 100ms cold | Called per env step during RL — has to be cheap |
| Graph snapshot build | ≤ 30 min/era | Once per week; not latency-critical |
| Game client FPS | ≥ 60 | Consumer UX floor |

## 11. Trade-offs taken and what I'd revisit

**Event-log-as-truth everywhere.** Means the world model must produce exactly the event schema the tick engine does. That constrains the model's output head and inflates rollout size vs. a dense-tensor format. Accepted because a mismatched world-model output would create two parallel worldviews in the stack. *Revisit if* rollout storage becomes the bottleneck — could add a compact tensor shadow format cached alongside.

**PPV as one vector.** A single fixed-length conditioning vector is simple and lets FiLM do its thing cleanly. It also forces every new signal to be squeezed into `D_v1`. *Revisit when* a Phase-1 signal (e.g., rivalries) genuinely needs variable-cardinality structure — may need a graph-conditioned world model instead of a vector-conditioned one. That's a bigger redesign, not a tweak.

**One local Postgres for operational data.** Single-node via docker-compose. Carries the canonical graph, inferred fields, relationships, vectors, and the api_ledger. *Revisit when* Phase 5 B2B volume pushes read latency — answer is read replicas, not a different DB.

**pgvector instead of Qdrant.** Collocating vectors with entities makes the joined-filter queries ("similar players among active T1 duelists") trivial and avoids the sync burden of a separate vector DB. See ADR-006. *Revisit when* we cross 10M vectors with strict latency SLAs — we will not.

**Prefect instead of cron.** Retries, backfills, failure alerts are primitives, not something we roll in Python. *Revisit if* we have fewer than five live flows and the dashboard feels ceremonial.

**Single Claude provider.** Budget governor knows one vendor. *Revisit if* a cheaper local model gets close enough on dark-data extraction to replace Tier-2 calls.

**SQLite for budget ledger and experiment registry.** These are single-writer append-only metadata stores and SQLite's sweet spot; keeping them separate from Postgres means they keep working even if the main DB is down for maintenance. *Revisit if* parallel agents start contending on the ledger write path.

## 12. Phase-to-component mapping

| Phase | Weeks | Builds or extends |
|---|---|---|
| 0 | 1-4 | C1 Systems 01-05, C8 v0, C9 v0, PPV stub |
| 1 | 5-12 | C1 Systems 06-10, PPV v1 (C2), relationship data feeding PPV |
| 2 | 13-24 | C3 (extend), C4 (PPO with PPV conditioning), rollout store |
| 3 | 25-36 | C5 world model, FiLM conditioning, classifier eval |
| 4 | 37-48 | C6 ecosystem engine, C7 game MVP consuming C5 rollouts |
| 5 | 49-52 | Polish, scale rollouts, first external customer |

If something in Phase 0 doesn't serve a component on this list, it's yak shaving.

## 13. Open questions

- Exact PPV dimensionality and sub-block composition — defer to ADR-002 follow-up once mechanical stats are derived in Phase 1.
- Reward shaping for multi-agent RL — event-derived sparse vs. dense. Decide at start of Phase 2.
- World model discrete vs. continuous state representation. LeWM uses discrete latents; DIAMOND uses continuous. Defer until Phase 3 exploration week.
- Whether the ecosystem engine's LLM agents need their own "memory" DB or can live off the graph. Phase 4.

## 14. Related docs

- `docs/systems_spec.html` — authoritative Systems 01-10 spec for Layer 1.
- `docs/adr/ADR-001-training-substrate.md` — world-model training data provenance.
- `docs/adr/ADR-002-player-profile-vector.md` — PPV as universal conditioning.
- `docs/adr/ADR-003-event-log-canonical.md` — one event schema across all producers.
- `docs/adr/ADR-004-storage-layout.md` — *superseded by ADR-006*, kept for history.
- `docs/adr/ADR-005-llm-budget-governor.md` — how $40/week gets enforced.
- `docs/adr/ADR-006-storage-stack.md` — Postgres + pgvector + Prefect + file-first research artifacts.
