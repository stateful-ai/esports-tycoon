# ESports Simulator

![splash](assets/splash.webp)

A Valorant-flavored esports management sim in the spirit of *Esports Manager
2026*: run an org, build a roster, train players, work the transfer market,
scout rivals, talk to your players, and win Champions — with every match
decided by a deterministic tick-level simulation on real, walkable maps, not
a dice roll.

See **[GDD.md](GDD.md)** for the full game design document (systems,
mechanics, content, and where this is going) and **[ROADMAP.md](ROADMAP.md)**
for sprint-by-sprint status.

## Play

```bash
# Windows: use your venv's python (requires Python 3.12+)
python -m venv .venv-win
.venv-win\Scripts\python -m pip install -e ".[dev,web]"

# Browser (recommended) — campaign hub + isometric match viewer
.venv-win\Scripts\python -m esports_sim --web

# Terminal (rich CLI)
.venv-win\Scripts\python -m esports_sim
```

### Windows taskbar launcher

Install a local launcher that updates **main**, starts the server in the
background, and opens the game without a PowerShell window:

    powershell -ExecutionPolicy Bypass -File .\scripts\install_taskbar_launcher.ps1

Then open Start, right-click **ESports Simulator**, and choose **Pin to
taskbar**. Each launch runs a safe fast-forward-only pull from **origin/main**.
If the checked-out commit or Python dependencies changed, it restarts its
background server before opening the browser. The taskbar instance binds to
the LAN on the standard playing port, 8420; use 8421 for development tests.
If the launcher was installed before LAN play became the default, run the
install command above once more; subsequent launcher-runtime updates refresh
themselves automatically after the normal pull.

The launcher `.exe` is compiled on your machine, so the installer also
Authenticode-signs it — otherwise SmartScreen / Smart App Control / antivirus
may quarantine it as an unknown-publisher binary and it silently stops
launching. Signing uses a self-signed certificate that is created once and
trusted locally (`scripts\sign_launcher.ps1`); the **first** install shows a
one-time Windows prompt to trust that certificate — choose **Yes**. Re-running
the installer reuses the same certificate and re-signs the rebuilt launcher. To
sign with a real certificate instead, run `sign_launcher.ps1` with
`-Thumbprint`, or `-PfxPath` / `-PfxPassword`.

`New game` → pick a seed, a **world**, and a team → weekly loop: set
training, scout a rival, work the market, talk to a player, advance the
week, watch replays. The terminal CLI autosaves to `saves/campaign.json`;
the web app saves each world separately (see **Play with others** below).

Two worlds ship in the box:

- **Fictional** (default) — a generated 3-region league of original orgs.
- **VCT 2026** (`data/rosters/vct-2026/`) — the real four-region VCT:
  48 partner teams with their real mid-2026 starting fives (plus notable
  Challengers orgs underneath), researched from vlr.gg/Liquipedia and
  expanded into game attributes deterministically. Pick it from the world
  selector on the new-game screen, or headless via `--roster vct-2026`.
  Custom **roster packs** are just a directory of YAML under
  `data/rosters/` — `scripts/build_roster_pack.py` expands a compact
  per-player spec (handle, role, playstyle, quality, signature agents)
  into full rosters. **Roster Studio** on the Play screen adds a visual
  editor plus a portable YAML/JSON, JSON Schema, CLI, and HTTP workflow for
  agent-built packs; see [docs/roster-studio.md](docs/roster-studio.md).

Headless demo (a hands-off season, no UI):

```bash
python -m esports_sim --auto 18 --seed 11 --team team_nexus
python -m esports_sim --auto 30 --seed 11 --team team_sentinels --roster vct-2026
```

## Play with others (LAN)

Run the web server on one PC and share its LAN URL — anyone on the same network
plays in their browser, no install. On load, each player gets a lobby:

- **Solo game** — your own private campaign, isolated from everyone else.
- **Create shared game** — starts a world and gives you a 5-character join code.
- **Join a game** — enter a friend's code and pick a free team.

In a **shared world** you each manage a different team in the same league
(shared standings, schedule, and transfer market — and you can be drawn against
each other). The week only advances once **every** manager has hit *Advance*
(solo advances instantly). Sessions survive a browser refresh or a server
restart.

**AI managers can take seats too**: the `/api/agent/*` HTTP surface (plus an
in-process `AgentWorld`) lets LLM or scripted agents join the same shared
worlds as ordinary seats — same ready-up week barrier, fog-safe observations
with explicit legal-action masks, and a championship-objective scoreboard to
compete on. See [docs/agent-play.md](docs/agent-play.md).

### Boot options (PowerShell)

`scripts\serve.ps1` is a friendly launcher: it finds the project's Python,
prints a short pre-flight summary, and starts the server (which then prints the
exact local + LAN URLs). LAN mode is the default. Run from the **repo root**;
`-ExecutionPolicy Bypass` only affects the single invocation.

```powershell
# LAN multiplayer (default): bind 0.0.0.0, auto-open a browser on this PC.
powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1

# LAN + open the Windows Firewall so peers can reach you (UAC prompt).
powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1 -OpenFirewall

# Local-only (this PC): bind 127.0.0.1, nobody else can connect.
powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1 -Local

# Custom port / no auto-open browser (combine freely).
powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1 -Port 9000 -NoBrowser
```

| Flag | Effect |
|---|---|
| _(none)_ | LAN mode: bind `0.0.0.0`, port 8420, auto-open browser |
| `-Local` (alias `-LocalOnly`) | Bind `127.0.0.1` — this PC only |
| `-Port <1-65535>` | Custom port (default 8420; `$env:PORT` used only when `-Port` is omitted) |
| `-NoBrowser` | Do not auto-open a browser on the host |
| `-OpenFirewall` | Add an inbound TCP allow rule (Private+Domain profiles). Needs admin; self-elevates via UAC or prints the exact elevated command |

The equivalent raw commands (no launcher) are `.venv-win\Scripts\python -m
esports_sim --web [--host 127.0.0.1] [--port N] [--no-browser]`. Press
**Ctrl+C** to stop.

**Firewall:** `-OpenFirewall` scopes the rule to Private/Domain networks (never
Public). If your active network is Public, the launcher warns you; set it to
Private first with `Set-NetConnectionProfile -InterfaceAlias <name>
-NetworkCategory Private` (find `<name>` via `Get-NetConnectionProfile`). To add
the rule by hand once, in an elevated PowerShell:

```powershell
New-NetFirewallRule -DisplayName 'esports-sim web (TCP 8420)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8420 -Profile Private,Domain
```

## What's in the box

- **Match engine** (`sim/engine.py`): tick-level rounds on a callout graph
  with real floor-plan geometry underneath — buy phase with real Valorant
  credit rules, executes/defaults, continuous player movement (real x/y
  positions, speed-scaled travel, tactical slots at cover and doorway
  angles), point-to-point duels (range, elevation, positional cover,
  line-of-sight through props), directional pre-aim/flanks, peeking,
  mid-fight micro-repositioning, coarse agent utility (smokes, flashes,
  recon, post-plant lineups), spike plant/defuse, an asymmetric
  defender-fallback/retake model, halftime swap, overtime. ~50 ms per
  match, and **deterministic**: same seed → byte-identical event log,
  gated by a determinism test and a golden-file fixture (single match +
  a multi-seed sweep).
- **Coaching & tactics**: an EHM-style dial set (`TeamTactics`) the coach
  stamps on a team — aggression, pace, utility discipline, eco greed, site
  focus, and map control (stack-and-hit-as-five vs spread-and-lurk). The
  dials reach into the *micro*: peek/refrag appetite, execute-vs-default
  timing, commit-or-abort discipline, flash-for-swing reserves, forward vs
  anchored defensive setups, post-plant crossfire spread, and a lurker who
  baits then strikes as a second wave. How well a system is *executed* is
  scored per player from the same attributes the engine reads
  (`sim/tactics_fit.py`) — and misfits drag harder than stars lift, so an
  extreme identity is a real trade-off, not a free bonus. Every effect is
  **neutral-safe** (a no-op at each dial's neutral default), so the coach's identity is
  felt without ever destabilising the golden or balance gates (see
  `docs/adr/ADR-007-neutral-safe-tactics.md`).
- **Management layer** (`manager/`): a three-region VCT-style league
  (double round-robin → BO3 playoffs with map veto → Masters/Champions),
  weekly training with age curves and system-fit growth,
  morale/stamina/form, backroom staff (coach/analyst/physio), scouting
  fog whose precision sharpens with a better analyst, weekly 1:1 player
  conversations that move the chemistry graph, contract pressure, a
  transfer market where rival AI orgs poach free agents out from under
  you, sponsorships with results *and* squad-building objectives, finances
  with real insolvency consequences, free agency, offseason aging,
  multi-season campaigns, and AI coaches that adapt their tactical identity
  to how the season is going. Rich per-player season stats (clutches,
  multikills, aces, first-deaths) and team awards feed grounded narrative
  recaps with rivalry callbacks and tactical-identity flavour. Standings
  break ties by head-to-head. Saves carry a `schema_version` migration
  hook. All fully deterministic.
- **Web UI** (`web/`): FastAPI + a no-build-step frontend on a custom
  design system — a dashboard hub, roster, tactics (with live roster-fit
  preview), standings, schedule, scouting, market, stats, finances, a
  weekly **inbox** with inline accept/decline actions, and a painted
  isometric **office** home screen — plus click-through **player and team
  profiles** (charts, weekly form, scouting-fogged attributes) from any
  name in the app, and an isometric match viewer that replays the event
  log over AI-painted map backdrops with full playback controls (scrub,
  speed, round-skip).
- **Data-driven content** (`data/`): 29 agents, 7 weapons, 5 maps (each
  with an authored floor-plan geometry layer — rooms, corridors, props,
  elevation — and its signature gimmick: Bind's teleporter, Lotus's
  rotating door, Ascent's breakable door), and starter teams, all YAML —
  add an agent or a map without touching code.
- **Policy interface** (`policy/`): all ten available players make live-tick
  decisions through `PlayerPolicy`; a `TeamPolicy` forms round plans and a
  `CoachPolicy` may intervene only with a between-round timeout. The shipped
  heuristics can be swapped independently for RL agents or LLM playtesters.

## Tuning

Gameplay feel lives in `src/esports_sim/sim/constants.py` (match) — nothing
inline in the engine. After changing numbers or map/geometry YAML, run the
gates (all exit 1 on failure):

```bash
python scripts/balance_report.py 300     # every map 45-65% attack round rate
python scripts/pacing_report.py          # attacker rotate 25-35s through spawn
python scripts/snowball_report.py        # multi-season blowout/competitiveness band
python scripts/tactics_report.py         # sweep the numeric coaching dials to extremes
python scripts/map_floor_audit.py        # floor plates connect; paths/callouts on the floor
```

`regen_golden.py` is **not** a gate — it's a mutating re-bless tool that
overwrites the golden fixtures (single + sweep). Run it *only* after the
golden test fails on an **intentional** engine/geometry change, to record
the new baseline in the same commit. If the golden drifts unexpectedly,
that's a regression — re-blessing would erase the evidence.

Coaching-dial changes are held to a stricter bar: every term must be a
no-op at the neutral value, so the golden stays byte-identical. Running
`pytest -q tests/test_golden.py` and seeing no change *is* the proof.

## Tests

```bash
python -m pytest -q
```

The north-star invariant: `tests/test_determinism.py` asserts that two runs
of the same match produce byte-identical event logs, and `tests/test_golden.py`
pins one canonical match log's hash so unintentional drift fails CI.
