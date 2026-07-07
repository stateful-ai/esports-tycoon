# Scraping Run Guide

How to run the Nexus data pipeline on Windows, macOS, and Linux.

---

## Prerequisites

All three platforms need the same core tools. Install them once per machine.

### 1. Docker Desktop (Postgres)

| Platform | Install |
|----------|---------|
| Windows  | [docs.docker.com/desktop/install/windows](https://docs.docker.com/desktop/install/windows/) — requires WSL 2 |
| macOS    | [docs.docker.com/desktop/install/mac](https://docs.docker.com/desktop/install/mac/) |
| Linux    | `sudo apt install docker.io docker-compose-plugin` (Ubuntu/Debian) |

After installing, make sure the Docker daemon is running before any pipeline commands.

### 2. Python 3.12 + uv

```bash
# All platforms — install uv (replaces pip + venv)
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# Windows: run in PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify: `uv --version`

### 3. Playwright browser binaries (VLR.gg scraper only)

VLR.gg is JS-rendered, so Playwright needs a headless Chromium binary.

```bash
uv run python -m playwright install chromium
```

Note: `uv run playwright ...` won't work — Playwright isn't on your PATH, so always invoke it via `python -m playwright`. On **Linux servers** without a display, also install system deps:

```bash
uv run python -m playwright install-deps chromium   # Linux only
```

### 4. VLR.gg CSV snapshot (seed only)

The bootstrap seed reads a local CSV snapshot of VLR match history. Download or copy the file (`NewVLRDataRaw.csv`, ~129k rows) to a known path on your machine before running the seed step.

---

## Environment Setup

### Clone and install dependencies

```bash
git clone <your-repo-url> nexus
cd nexus
uv sync                  # installs all deps from pyproject.toml into .venv
```

### Create your `.env` file

Copy the example and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Riot Games API — production key from developer.riotgames.com
RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Postgres (matches docker-compose.yml defaults — change if needed)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=nexus
POSTGRES_USER=nexus
POSTGRES_PASSWORD=nexus

# Anthropic (for Phase 1 inference — not needed for scraping)
ANTHROPIC_API_KEY=sk-ant-...
```

**Windows note:** If you're using PowerShell instead of a `.env` file, set variables with:
```powershell
$env:RIOT_API_KEY = "RGAPI-..."
```

---

## Starting the Database

Always start Postgres before running any pipeline commands.

```bash
docker compose up -d postgres
```

Verify it's healthy:
```bash
docker compose ps          # should show postgres as "healthy"
```

First time only — run the migrations (`alembic.ini` lives in `packages/shared/` and must run from there):
```bash
uv run --directory packages/shared alembic upgrade head
```

This applies all six migrations: initial schema, alias dedup, patch_note, patch_era, match/map_result schema, and VLR alias namespace backfill.

---

## Running the Scrapers

All commands are run from the repo root.

### One-time: Seeds (run in order, once per environment)

Seeds use `python -m data_pipeline.seeds`, not the `nexus` CLI. Both require `DATABASE_URL` to be set.

```bash
# Set DATABASE_URL (match your docker-compose defaults)
export DATABASE_URL="postgresql://nexus:nexus@localhost:5432/nexus"   # macOS/Linux
$env:DATABASE_URL = "postgresql://nexus:nexus@localhost:5432/nexus"   # Windows PowerShell

# 1. Patch eras — seed the historical Valorant patch timeline (BUF-13)
#    Run this first so era assignment works on all ingested records.
uv run python -m data_pipeline.seeds patch-eras

# 2. VLR CSV bootstrap — canonical entities + full match/map history (BUF-8 v2)
#    Reads the local CSV snapshot; no network calls, finishes in a few minutes.
#    Replace the path with wherever you saved NewVLRDataRaw.csv.
uv run python -m data_pipeline.seeds vlr /path/to/NewVLRDataRaw.csv
```

**Windows:**
```powershell
uv run python -m data_pipeline.seeds vlr C:\Users\you\Downloads\NewVLRDataRaw.csv
```

The VLR seed lands ~13,000 team entities, ~2,000 tournament entities, and ~129,000 map rows. Expect 5–15 minutes. Watch for the manifest saved to `seeds/`.

---

### Connectors (run after the seeds)

#### VLR.gg (Playwright — daily)

```bash
uv run python -m data_pipeline.connectors.vlr
```

Pulls stats, completed matches, and rankings for the incremental window (records newer than the CSV snapshot). Rate-limited to 20 req/min automatically. Expect ~20–40 minutes for a full backfill.

**Windows-specific:** If Playwright throws a browser launch error, run:
```powershell
uv run python -m playwright install chromium --force
```

#### Riot API (REST — daily, backfill takes hours)

```bash
uv run python -m data_pipeline.connectors.riot
```

The backfill paginates match history for every known pro PUUID back to patch 5.0. Due to Riot's rate limits this will take **several hours** — run it overnight or in a `screen`/`tmux` session so it isn't interrupted.

```bash
# macOS / Linux — run detached so closing the terminal doesn't kill it
screen -S riot-backfill
uv run python -m data_pipeline.connectors.riot
# Ctrl+A, D to detach. Re-attach with: screen -r riot-backfill
```

```powershell
# Windows — run in a background job
Start-Job -ScriptBlock { uv run python -m data_pipeline.connectors.riot }
# Check status: Get-Job | Receive-Job
```

#### Patch Notes (weekly)

```bash
uv run python -m data_pipeline.connectors.playvalorant
```

Fast — a few minutes even for the full backfill.

---

## Validating Data

After scraping, check the pipeline health:

```bash
uv run nexus run ls
```

This runs structural checks, freshness checks, and the `TEMPORAL_BLEED` guard. Look for any `WARN` or `FAIL` lines in the output.

---

## Platform-Specific Notes

### Windows

- Use **PowerShell** (not CMD) for all commands. Git Bash also works.
- Docker requires **WSL 2** to be enabled. If Docker Desktop won't start, run: `wsl --install` in an admin PowerShell, then reboot.
- Long backfill jobs: use `Start-Job` (shown above) or Windows Terminal's persistent sessions. Avoid running backfills in a plain PowerShell window you might close.
- Path separators: all `nexus` CLI commands use forward slashes internally — no changes needed.

### macOS

- If `uv sync` fails on Apple Silicon with a native extension error, make sure you're on Python 3.12 arm64: `uv python install 3.12`.
- Playwright on macOS may prompt for network access permissions — allow them.
- For overnight backfills, prevent sleep: `caffeinate -i uv run python -m data_pipeline.connectors.riot`

### Linux

- If running on a headless server (no display), Playwright needs `--headless` mode (the connector uses it by default) and system deps installed via `playwright install-deps chromium`.
- Run long jobs in `tmux` or `screen` so SSH disconnects don't kill them.
- If using Linux on your local machine (not a server), everything works identically to macOS.

---

## Checking Progress

```bash
# How many records in each table
uv run nexus status

# Tail live ingestion logs
uv run python -m data_pipeline.connectors.riot 2>&1 | tee logs/riot_backfill.log

# Watch staging queue depth
watch -n 5 "uv run nexus status --staging"   # macOS/Linux
# Windows equivalent:
while ($true) { uv run nexus status --staging; Start-Sleep 5; Clear-Host }
```

---

## Order of Operations (first time on a new machine)

1. Set env: `$env:DATABASE_URL = "postgresql://nexus:nexus@localhost:5432/nexus"`
2. Start Docker: `docker compose up -d postgres`
3. Run migrations: `uv run --directory packages/shared alembic upgrade head`
4. Seed patch eras: `uv run python -m data_pipeline.seeds patch-eras`
5. Seed VLR CSV: `uv run python -m data_pipeline.seeds vlr /path/to/NewVLRDataRaw.csv`
6. Run patch notes connector: `uv run python -m data_pipeline.connectors.playvalorant`
7. Run VLR connector (incremental): `uv run python -m data_pipeline.connectors.vlr`
8. Kick off Riot backfill overnight: `uv run python -m data_pipeline.connectors.riot`
