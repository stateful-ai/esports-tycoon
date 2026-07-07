# Sprint 2 — "See the game"

> **STATUS: COMPLETE (2026-07-07).** All six workstreams shipped in four
> slices; stretch items and the attack-side round-rate tuning item carry
> to Sprint 3. Bonus work: a league-balance overhaul (blowouts 60-77% →
> ~35%, see `scripts/snowball_report.py`) after multi-season sims showed
> condition snowballing.

**Window:** ~2 weeks from 2026-07-07 · **Prerequisite state:** working terminal
MVP (engine + campaign + CLI, 33 tests green, repo live on GitHub with CI).

**Sprint goal:** turn the terminal MVP into a game you can *see and feel* — a
local web app on the existing design system, an animated 2D match replay, a
narrative layer, season analytics, and the highest-value sim depth. One rule
carries over from the architecture: every pixel renders from the same event
log and GameState the CLI and tests already use. The UI is a pure consumer.

North-star bets served (see ROADMAP.md): #1 "matches feel alive" (viewer +
narrative make aliveness visible), #2 "LLM runs a season" (the web API is the
same state-view/legal-action contract).

---

## Workstream 1 — Web app shell + campaign hub · P0

FastAPI server (`src/esports_sim/web/`) exposing GameState views + campaign
actions as JSON, plus a no-build-step static frontend (vanilla JS + the
`ui/design-system` tokens).

| Item | Notes |
|---|---|
| `GET /state` views: dashboard, roster, standings, schedule, finances, market | Thin serializers over GameState — no new state |
| `POST` actions: training focus, sign/release/renew, advance week | Same campaign functions the CLI calls |
| Screens: Dashboard, Roster (attribute bars, form/stamina/morale), Standings, Schedule, Finances, Market | components.css already has most primitives |
| Launch: `python -m esports_sim --web` opens browser | Keep CLI fully working |

**Acceptance:** a full week loop (set training → advance → read results) is
playable in the browser with zero terminal interaction.

## Workstream 2 — 2D match viewer · P0

The roadmap's Phase 2, unchanged in spirit. The viewer replays an event log —
it holds no independent sim state.

| Item | Notes |
|---|---|
| **Engine: emit movement events** | `MoveEvent(player_id, from, to, tick)` added to schema + engine + EventUnion. Prerequisite for everything below; must keep determinism suite green |
| Map render from YAML (sites, callouts, edges) using authored x/y | The x/y coords were reserved for exactly this |
| Player dots by team/agent, kill markers, spike plant/defuse icons, smoke indicator | Design-token colors |
| Kill feed + scoreline + round timeline bound to events | |
| Playback: 1× / 4× / 16× / instant, pause, scrub, round-skip | |
| Replay any match from the week report + any saved JSONL | |

**Acceptance:** watch a saved match animate end-to-end on all maps; a second
replay of the same log renders identically.

## Workstream 3 — Storylines v0 · P0

The roadmap's Phase 4, upgraded with the salvage material (`docs/salvage/`).

| Item | Notes |
|---|---|
| Deterministic templated recaps from event logs | Seeded-`random.Random`-from-stable-strings pattern; variants per event kind |
| Grounded citations | Recap facts must resolve to real events (players, rounds, callouts) — validator rejects dangling references |
| News ticker on dashboard (3+ items/week: results, streaks, transfers, milestones) | |
| Rivalry seeds: archetype tags on generated orgs (The Dynasty, The Ex-Teammate, …) | From `tone_and_cast_lock.md`; tone bible applies to all copy |
| Precedent recall v0: recaps reference relevant past events ("third straight OT loss on Haven") | Adapt `recall_reference.py` scoring to our log |
| Season awards at season end (MVP, rookie of the season, clutch leader) | Uses analytics aggregates from WS4 |

**Acceptance:** every played week yields ≥3 news items; a spot-check of 20
recap sentences finds zero invented facts.

## Workstream 4 — Analytics · P1

| Item | Notes |
|---|---|
| Season stat aggregation: per-player K/D/A, ACS-like rating, first bloods, clutches, plants/defuses; per-team attack/defense round %, pistol conversion | Aggregated from match box scores into GameState at week end |
| League leaders page + player detail (season trend sparklines) | |
| Team analytics tab: map records, site-hit tendencies, economy efficiency | |

**Acceptance:** stats page numbers match hand-computed values from the event
logs of a seeded season.

## Workstream 5 — Sim depth · P1

| Item | Notes |
|---|---|
| BO3 map veto (ban/ban/pick/pick/remaining over the 5-map pool) | Needs WS6's two new maps; team map mastery drives AI veto choices |
| Scouting fog: non-user-team attributes shown with noise bands; weekly scouting assignment shrinks noise | Uses the reserved `visibility` enum + `scouting_uncertainty` |
| Contract pressure: players with <8 weeks left + good form request renewal; ignoring costs morale | |

**Acceptance:** veto sequence shown pre-match in the UI; opponent roster shows
uncertainty ranges that visibly tighten after two weeks of scouting.

## Workstream 6 — Content & art · P1

| Item | Notes |
|---|---|
| +2 maps as callout graphs: Lotus (3-site), Split (2-site) | Follow haven.yaml conventions; run `scripts/balance_report.py` after |
| +4 agents: Chamber, Skye, Clove, Phoenix | Ability flags only, as with current cast |
| Name-pool expansion in `manager/gen.py` (region-flavored handles) | |
| Ludo-generated art: 8 org logos, user-team player portraits, map thumbnails | Deterministic prompts keyed to entity ids; `assets/`; budget-aware (credits) |

**Acceptance:** balance report keeps all 5 maps in the 45–65% attack-round
band; logos/portraits render in roster + standings screens.

## Stretch (only if P0+P1 land)

- Talk-module-lite: one weekly 1:1 conversation (template choice tree) with
  morale/chemistry consequences
- Chirper-style social feed with tone-bible voice
- Playoff bracket visualization

---

## Sequencing

**Days 1–2:** MoveEvent in engine + schema (unblocks viewer) · web shell +
`/state` endpoints. **Days 3–7:** viewer core + campaign screens; maps/agents
authored in parallel (good subagent tasks). **Days 8–11:** narrative v0 +
analytics aggregation + leaders pages. **Days 12–14:** veto + scouting fog +
art pass + polish + test/balance gates.

## Quality gates (non-negotiable)

1. Determinism suite green throughout — MoveEvents must not disturb replay
   identity; add a golden-file test (canonical bytes + SHA-256) for one full
   match log per the salvage pattern.
2. CI green on every push to main.
3. Balance report re-run after any constants/map change; 45–65% attack band.
4. UI holds no sim state — a hard architecture review item on every PR.

## Out of scope this sprint

RL/gym track, world model, multi-region VCT, injuries, meta patches,
LLM-generated prose (templates only), 3D anything, deployment/hosting.

## Risks

| Risk | Mitigation |
|---|---|
| Viewer reveals the sim looks robotic (synchronized moves, teleporty rotations) | Budget a half-day "juice" pass: stagger move ETAs visually, interpolate dots; sim changes only if legibility demands |
| MoveEvent volume bloats logs (~10 players × ~30 moves/round) | Acceptable (~7k events/match); if not, coalesce into per-tick-chunk snapshots |
| Art generation credit burn | Logos + user-team portraits only; generate once, commit to `assets/` |
| Scope: six workstreams is a lot | P0 (WS1–3) is the sprint; P1 degrades gracefully to Sprint 3 |
