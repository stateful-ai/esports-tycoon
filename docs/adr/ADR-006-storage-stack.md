# ADR-006 — Storage stack: Postgres + pgvector + Prefect (supersedes ADR-004)

**Status:** Accepted — supersedes ADR-004
**Date:** 2026-04-23
**Deciders:** Aidan (as PM and as EM)

## Context

ADR-004 committed to a SQLite + DuckDB + parquet + cron stack on a "file-first, single-node, minimum-ops" rationale. The Linear backlog had already committed (via BUF-5, BUF-6, BUF-28, BUF-57) to Postgres + Qdrant + Prefect. When the EM hat went on and the two were compared against the actual data model, workload, and Phase-5 B2B trajectory, ADR-004 was the wrong call on two dimensions (operational data, scheduling), and the PM's Qdrant choice was the wrong call on one (vector store). This ADR replaces ADR-004 with the correct tiered stack.

Load-bearing facts that drive the decision:

- The canonical data model (entity / entity_alias / staging_record / inferred_field / patch_era / relationship_edge) is relational with JSONB payloads, temporal partitioning, FK integrity, and fuzzy-matching on aliases. Postgres is purpose-built for exactly this shape.
- Phase 5 ships a B2B API to paying customers (BUF-61). Arriving at Phase 5 on SQLite with one week to harden for external traffic is a scramble we do not need to take.
- Qdrant's justification is performance at scale. Our scale is ~100 personality summaries and tens of thousands of transcript chunks. There is no performance case.
- The single most useful vector query will be "players similar to X who are currently on an active T1 roster and play Duelist" — that is a JOIN, not a vector DB filter. pgvector collocates the vector with the entity table.
- Research artifacts (RL rollouts, model checkpoints, training logs) are a different workload — write-heavy, append-only, single-writer, large binary blobs. Postgres is wrong for them. The file-first layout from ADR-004 is right for this tier and is retained.

## Decision

A tiered stack, with each tier using the tool that matches its workload:

| Tier | Store | Why |
|---|---|---|
| Canonical operational data | **Postgres 16** | Relational + JSONB + FK + fuzzy matching + Phase-5 B2B ready |
| Vector similarity | **pgvector** extension | One less service, SQL joins with entity, same perf at our scale |
| Scheduling | **Prefect 2 (local)** | Retries, backfills, dashboards — what BUF-57 acceptance requires |
| LLM budget ledger | SQLite (`state/budget.db`) | Single-writer append-only metadata, WAL mode |
| Experiment registry | SQLite (`state/registry.db`, from BUF-69) | Same pattern; cross-cuts runs |
| Research artifacts | `runs/{run_id}/` — parquet, safetensors, JSONL | Append-only, single-writer, binary; not a DB workload |
| Patch-era graph snapshots | `.pt` files referenced from Postgres | PyG serialization; Postgres stores the pointer + metadata |
| Game saves | JSON under user profile | Portable single-player |

ADR-004's narrow-scope contribution — the `runs/{run_id}/` artifact layout and the two SQLite ledgers — is retained. Everything else in ADR-004 is superseded.

## Options considered — operational data

### Option A — Postgres 16 (accepted)

| Dimension | Assessment |
|---|---|
| Complexity | Medium — one more service to run (docker-compose) |
| Cost | Zero marginal — runs local |
| Scalability | Overkill now, right-sized for Phase 5 B2B |
| Team familiarity | High — Aidan has used it before; agents write Postgres fluently |
| Data-model fit | High — JSONB, pg_trgm, CTEs, temporal partitioning all first-class |

Pros: the data model fits the tool; Phase-5 customers expect a real DB; extensions (pgvector, pg_trgm, TimescaleDB if needed) are available without migration; mature migration tooling (Alembic); real FK constraints catch bugs during Phase-0 pipeline churn.

Cons: docker-compose lifecycle; backup/restore is ops work; slightly more friction for quick one-off scripts.

### Option B — SQLite + DuckDB (original ADR-004)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Zero |
| Scalability | Fine at Phase 0–2 volume, awkward by Phase 4, scramble by Phase 5 |
| Team familiarity | High |
| Data-model fit | Medium — JSONB querying works but slower; no pg_trgm; schema migrations crude |

Pros: zero daemon; trivially portable; copy-one-file backups; no WAL contention at one-writer solo scale.

Cons: the JSONB path is measurably slower and lacks GIN indexes; no real FK (SQLite enforces them loosely); fuzzy matching has to live in the app layer only (BUF-7 does this anyway, but losing pg_trgm still stings); schema migration tooling is thin; Phase 5 B2B is a scramble.

## Options considered — vector store

### Option A — Qdrant (PM decision, rejected here)

| Dimension | Assessment |
|---|---|
| Complexity | Medium — another service |
| Cost | Zero marginal |
| Scalability | Engineered for millions of vectors at low latency |
| Team familiarity | Medium |
| Workload fit | Overkill for our volume; cross-entity filter case is weak |

Pros: purpose-built; rich filtering DSL; observability; future-proof if we ever hit millions of vectors.

Cons: duplicates player/entity metadata that already lives in Postgres (sync burden); filter-by-entity-properties means keeping Qdrant payload in sync with the authoritative entity table; another daemon; no SQL JOIN between similarity results and the rest of the graph.

### Option B — pgvector (accepted)

| Dimension | Assessment |
|---|---|
| Complexity | Low — Postgres extension, no extra service |
| Cost | Zero |
| Scalability | HNSW index handles 100k+ 384-dim vectors at sub-10ms |
| Team familiarity | High if you know Postgres |
| Workload fit | Best — enables `SELECT ... JOIN entity ... WHERE role='duelist' ORDER BY embedding <=> $1 LIMIT 10` |

Pros: one less service; SQL joins with the rest of the graph (the whole point of cross-entity similarity); single backup surface; no metadata-sync; well-supported extension shipped in Postgres 16.

Cons: index build time longer than Qdrant at 10M+ vectors (irrelevant at our scale); observability less rich than Qdrant's dashboard.

### Option C — FAISS + flat files

Considered briefly. No metadata filter, no persistence pattern, no incremental updates, no HTTP surface. Dismissed.

## Options considered — scheduler

### Option A — Prefect 2 (local) (accepted)

| Dimension | Assessment |
|---|---|
| Complexity | Medium — another service, but flows are Python |
| Cost | Zero marginal |
| Scalability | More than sufficient |
| Team familiarity | Medium |
| Workload fit | Retries, backfills, failure alerts — directly matches BUF-57 acceptance |

Pros: retries and backfills as a primitive; dashboard; Python-native flows (no DAG YAML); local deployment is a single `prefect server start` + agent.

Cons: one more runtime in docker-compose; learning curve; arguably overkill for 5 schedules.

### Option B — Cron + Python scripts (original ADR-004)

Pros: zero dependencies; trivially debuggable.

Cons: retries, backfills, and failure alerts all have to be rolled by hand; migrating later is the classic "we'll migrate later" trap that I'd rather not take.

## Trade-off analysis

The PM was right that Postgres and Prefect are worth the "one more service each" tax. Both tools solve real problems that I would otherwise rewrite in Python at greater total cost. Both are mature and free.

The PM was wrong on Qdrant in one specific way: the most useful thing we'll do with vectors is join them against the rest of the graph, and a separate vector DB makes that the hardest possible path. pgvector is strictly cheaper and strictly more useful at our scale. The only case Qdrant wins is "we're about to cross 10M vectors with strict latency SLAs", and we're not remotely there.

ADR-004's right-sized contribution — file-first research artifacts, SQLite ledgers — survives because research outputs are a genuinely different workload from operational data. Conflating them was ADR-004's mistake, not the tiering itself.

## Consequences

**Easier:**

- Entity resolution (BUF-7, BUF-12) — pg_trgm available for fuzzy alias matching if rapidfuzz isn't enough.
- Temporal queries (BUF-13) — Postgres views + CTEs clean up the era-scoping pattern.
- Cross-entity similarity — pgvector lets us JOIN embeddings with any entity filter.
- Phase-5 API (BUF-61) — Postgres is what external customers will expect.
- Scheduler reliability — Prefect's retries + alerts come for free.

**Harder:**

- One-off scripts — connecting to Postgres is a few more lines than opening a SQLite file.
- Local dev ergonomics — docker-compose needs to be up before the pipeline runs.
- Backup discipline — Postgres requires an actual `pg_dump` cron vs. `cp file.db`.

**Revisit when:**

- Vector count approaches 10M and pgvector HNSW index build time bites — then Qdrant is back on the table.
- Prefect starts feeling ceremonial because we have five flows and they each run fine — would argue for downgrading to cron + `apprise` for alerts. Unlikely given the direction of travel.
- Phase 5 B2B demand exceeds what a single-node Postgres serves well — then it's time for read replicas, not a different DB.

## Action items

- [ ] Mark ADR-004 as "Superseded by ADR-006". Keep it for history.
- [ ] Update `docs/ARCHITECTURE.md` §7 (storage topology table) and §11 (trade-offs) to reflect this ADR.
- [ ] Update BUF-28 in Linear: swap Qdrant → pgvector. Retain all other acceptance criteria.
- [ ] Update BUF-5 (monorepo bootstrap) in Linear: remove Qdrant from docker-compose; add `pgvector` to the Postgres image.
- [ ] No change to BUF-6 (Postgres schema v1) — ratified.
- [ ] No change to BUF-57 (Prefect scheduler) — ratified.
- [ ] Update the Linear "Architecture" document to reflect that ADR-004 is superseded and the stack is ratified.
