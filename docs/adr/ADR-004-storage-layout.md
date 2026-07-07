# ADR-004 — File-first, single-node storage

Date: 2026-04-23
Status: **Superseded by ADR-006 (2026-04-23)**
Deciders: Aidan (solo)
Related: project budget memory, ADR-006 (storage stack)

> **Superseded.** ADR-006 replaces this ADR. The operational-data, vector, and
> scheduler decisions below were wrong calls driven by an over-austere reading
> of the budget constraint. The `runs/{run_id}/` artifact layout and the two
> SQLite ledgers (budget + experiment registry) from this ADR are retained as
> the research-artifact tier in ADR-006; everything else is superseded. Kept
> for history.

## Context

Nexus runs on a single machine (RTX 5090, local disk) with a ~$40/week total operating budget. The pipeline needs to hold:

- Raw scraper output (append-only, long-lived).
- Cleaned, typed staging data for SQL analysis.
- Per-patch-era canonical graph snapshots.
- Rollout event logs at large scale.
- Model checkpoints.
- An LLM budget ledger and an experiment registry, both needing durable, queryable writes.

A managed database is out (cost, ops overhead, overkill). A fleet of microservices is out (solo team). The question is how to lay out files and what lightweight DB, if any, holds the tiny structured-metadata tier.

## Decision

Storage is layered by transformation stage, each layer pinned to a simple file-based store. The whole stack sits under two roots: the repo's `data/` (pipeline outputs) and `runs/` (research artifacts), plus a tiny `state/` for the two SQLite files.

| Tier | Store | Path | Why |
|---|---|---|---|
| Raw | JSONL, gzip | `data/raw/{source}/{yyyy}/{mm}/*.jsonl.gz` | Append-only, grep-able, scraper-local |
| Staging | DuckDB | `data/staging.duckdb` | Analytical SQL, single-file, embedded |
| Canonical graph | PyG `.pt` + DuckDB views on parquet | `data/canonical/graphs/{patch_era_id}.pt` + `data/canonical/*.parquet` | Direct training input; views for ad-hoc SQL |
| Canonical match events | Parquet, zstd | `data/canonical/matches/{patch_era_id}/*.parquet` | Cross-joinable with graph via DuckDB |
| Rollouts | Parquet, zstd, with inlined PPV blob | `runs/{run_id}/rollouts/*.parquet` | Self-describing; streams during training |
| Model checkpoints | safetensors | `runs/{run_id}/ckpt/*.safetensors` | Versioned per run; no pickle |
| Budget ledger | SQLite | `state/budget.db` | Single writer, WAL mode |
| Run registry | SQLite | `state/registry.db` | Queryable metadata over the whole `runs/` tree |
| Game saves | JSON | user profile directory | Portable, single-player |

All paths are resolved through `paths.py`. No hardcoded strings in pipeline or training code.

## Consequences

**Positive.**

- Everything ships with a clone of the repo + a pull of `data/` and `runs/` — no cluster, no migrations, no restore-from-backup ritual.
- DuckDB gives strong analytical SQL over parquet without a server. SQLite is perfect for the two tiny authoritative tables.
- Immutable patch-era graph snapshots enable safe caching all the way through PPV (C2), RL rollouts, and world-model training.
- Every artifact has a home and an owning run_id — nothing floats.

**Negative.**

- Concurrent writes to SQLite are at most one; if the budget ledger is contended by parallel scrapers, we wait. Acceptable at solo scale; WAL mode mitigates.
- No replication. If the disk dies, months of training go with it. Mitigation: nightly rclone to an external drive + occasional offsite for the `runs/` tree that matters.
- DuckDB and SQLite together means two SQL dialects in the head. Mostly identical; occasional friction.
- Parquet rollouts make random access cheap but don't compress quite as hard as a domain-specific binary format would.

## Alternatives considered

**(A) Postgres for structured metadata.** Heavier ops, not worth it at one writer and ~100MB of metadata forever. Revisit if multiple concurrent processes need to write to the registry.

**(B) Everything in DuckDB, no SQLite.** DuckDB is analytical-first; single-writer append-only durability is not its strength. SQLite handles the "append a row and never lose it" case better.

**(C) A proper data lake (Iceberg/Delta) on cloud storage.** Out on cost alone. Revisit only if the project grows a small team and someone else is paying.

**(D) Pickle for checkpoints and rollouts.** Rejected — pickle is a CVE waiting for the day an old checkpoint gets loaded by the game client. safetensors + parquet cover it safely.

## Operational details

- Every directory that Nexus writes to gets created lazily via the `paths.ensure(...)` helper.
- `data/raw/` is in `.gitignore`; tiny fixtures for tests live in `tests/fixtures/`.
- `runs/` is in `.gitignore`; run metadata is in `state/registry.db`.
- Disk watchdog script warns when `runs/` passes 200GB so old experiments can be pruned explicitly (never auto).

## Revisit when

- Training parallelism across multiple local workers starts stepping on SQLite.
- `runs/` outgrows a single SSD (~2TB) — move it to a dedicated drive or prune policy.
- Someone else starts contributing — may want a shared artifact store with read/write roles.
