# Game systems reference — ESports Simulator

What the game actually is, as shipped. `GDD.md` holds the design *intent* and
the reasoning behind it; this file is the *inventory* — the loop, the features,
and every system currently on the weekly tick, with the module that owns each.

Keep this file honest: if a system lands in `src/esports_sim/manager/` and runs
on the tick, it belongs here. Last synced against `campaign.advance_week`,
`web/server.py`, the current manager module set, and the content registries on
2026-07-18.

---

## 1. The gameplay loop

Three nested loops. The manager plays the outer two; the innermost one they
watch.

### Match loop (simulated, ~milliseconds)

Buy → live round (tick = 0.5s) → post-plant → round end, first to 13, side swap
at 12, overtime win-by-2. Every tick, every available player gets a legal-action
decision; a team policy turns five players' attributes plus the standing tactics
into the round plan. The manager's only in-map input is a timeout, and it only
changes the *next* plan — never a hidden combat modifier. Output is a canonical
event log, and the log is the only truth downstream: box score, viewer, season
stats, and recaps are all pure readers of it.

### Weekly loop (the game, ~14–18× per regular season)

```
   ┌── Review ──────────────────────────────────────────────────────┐
   │  Inbox digest, dashboard (next match, form, danger men),        │
   │  standings, finances runway, scouting reports, social feed      │
   │                          ↓                                      │
   │  Decide  (~40 distinct actions available; see §3)               │
   │    · Squad: lineup, IGL, agent/role assignment, bench           │
   │    · Coaching: five tactics dials + site focus, game plan       │
   │    · Development: training focus, per-player dev plans,         │
   │      mentorships, academy promote/send-down                     │
   │    · Prep: scrims/bootcamps, series directives                  │
   │    · People: 1:1 talk, pep talk, shout, culture session,        │
   │      leadership (captain/council), promises                     │
   │    · Business: transfers/bids/buyouts/renewals, staff hiring,   │
   │      sponsors + demands, facility upgrades, delegation policy   │
   │                          ↓                                      │
   │  Advance week  → the tick runs (see §2)                         │
   │                          ↓                                      │
   │  Read  — replay the match, read the grounded recap and match    │
   │  review ("why you won/lost"), watch growth, badges, chronicle   │
   └───────────────────────────── repeat ───────────────────────────┘
```

### Season loop (indefinite)

Regular season (double round-robin) → regional playoffs (BO3 + mastery-driven
map veto) → Masters (cross-region) → Champions → offseason (aging, retirements,
rookie class, awards, FA refresh, AI roster repair, meta era recorded) → next
season. A Challengers circuit runs underneath every region and feeds the
academy. Above all of it, **Legacy Mode** runs a career across decades: manager
seats, board patience, dismissal, and a job market. Sandbox also supports four
deterministic scenario starts and an optional interview-led Fantasy Draft;
these reshape the starting state without changing the weekly contract.

### The attention loop

The campaign is not designed as a checklist of disconnected buttons. Human
decisions are surfaced as **Actionable Items** in the inbox and as matching
Dashboard "Needs you" badges; lower-priority league news stays in a separate
feed. Recent decisions settle later in a grounded decision ledger as paid off,
neutral, or backfired. Match Review attributes the calls that could have
changed the result (lineup, tactics, site focus, talk, and preparation) to the
manager. **Sim Ahead** may resolve up to four weeks under delegation policy,
then stops before a hard decision point. This is the player-facing bridge from
choice to consequence.

---

## 2. What one `advance_week` tick actually does

Ordered, because the order is load-bearing (`manager/campaign.py:496`).

| # | Phase | Owner |
|---|---|---|
| 0 | Heal/backfill save, seed academy affiliates, ensure leadership | `academy`, `culture` |
| 0 | Mid-split **balance patch** (twice a season) — agent buffs/nerfs; dates org playbooks | `meta`, `knowledge` |
| — | Scrims/bootcamps resolve; auto series directives | `preparation`, `series_management` |
| 1 | **Matches sim** (tier 1 captures replays; tier 2 sims fully but isn't broadcast) → stats fold, match XP, debuts | `engine`, `stats`, `chronicle` |
| — | Academy coaching gain reads the tier-2 results; media commitments settle | `academy`, `media_events` |
| — | Role/IGL comfort accrues — *after* matches, so a last-minute switch is never fully comfortable | `role_fit` |
| 2 | **Training** (human focus or delegated; AI uses the same roster-aware picker) × coach fit × facilities × philosophy, with mentorship, scout guidance, language rates | `training`, `staff`, `delegation` |
| 2a | Mentorship **ceiling** growth (raises a protégé's cap on the mentor's best skills) | `development` |
| 2b | Backroom effects — physio/recovery stamina, psychologist/team-house confidence + morale, performance-coach form. All pulls *toward* 50, never boosts past it | `staff`, `economy` |
| 2b′ | Bench week — non-dressed players scrim at reduced reps, keep fresher legs, and start wanting minutes | `campaign`, `transfer_requests` |
| 2b″ | **Dev events** (breakouts, slumps, injuries, viral clips) on a dedicated RNG stream | `development` |
| 2b‴ | **Mental momentum** — tilt spirals and heaters on the "tilt" stream | `development` |
| 2b⁗ | **Badges** rolled from this week's box scores + dev events | `badges` |
| 2c | Relationships drift; team chemistry chases the pair graph; culture tick | `relationships`, `culture` |
| 3 | Finances — payroll, facilities upkeep, merch/tickets riding real win-rate momentum; insolvency bites | `economy` |
| 3b | Sponsors — pay the active deal, settle demands, roll new offers/demands | `sponsors` |
| 4 | Contracts tick, AI transfer window, AI roster fill, AI FA poaching, scouting progress, promises settle | `market`, `academy`, `promises` |
| 4b | Stale game plans expire; world ranks update | `campaign` |
| 5 | Phase transitions — playoffs, Masters, Champions, offseason | `campaign`, `schedule` |

Everything above is campaign-deterministic: same seed → byte-identical
`GameState`. Each subsystem draws from its **own** labelled RNG stream, so
adding a system never shifts another system's draws.

---

## 3. Core features

The systems the game does not exist without.

**Match engine** (`sim/`) — deterministic tick-level tactical shooter. Maps are
a callout graph *plus* a real floor plan on a shared grid: rooms, corridors,
half-height cover, full-height LOS blockers, elevation. Players hold continuous
(x, y) and walk real paths at a speed scaled by their Movement attribute. Duels
resolve on actual range, cover, elevation, line of sight, facing cone (flanks
are punished), weapon, armor, agent and map mastery, all ten attributes, and a
correlated per-match "day form." Micro-combat adds jiggle-peeks, fizzled duels,
post-kill footwork, and individually-attributed, context-selected utility.
Economy follows Valorant's real credit rules. Post-plant, outnumbered defenders
fall back, rally, and mount a grouped retake or save — the asymmetric behavior
that fixed attack/defense balance.

**Players** — ten attributes across mechanical/tactical/mental/team, a role and
an orthogonal playstyle, per-agent and per-map mastery, condition
(morale/stamina/form/confidence), personality tags, languages, and a pairwise
relationship graph that outlives roster moves.

**Development** (`development`, `training`) — age curves, system fit, hidden
career curves (arrival time, volatility, peak duration, decline), potential as a
*forecast* not a cap. Playing time is development: match XP comes off box-score
lines, bench players scrim at a fraction.

**Coaching & tactics** (`sim/tactics_fit`) — five 0–100 dials plus site focus.
Execution quality = roster fit × chemistry, scored per player with
below-baseline misfits *amplified*, so a couple of stars can't average away a
broken roster. **Every dial is an exact no-op at 50** (ADR-007) — this is what
lets tactics reach round micro without destabilising the gates.

**Transfer market & contracts** (`market`) — negotiations, bids, buyouts,
packages, renewals, severance. AI orgs work the same market against you and will
poach a marquee FA out from under you.

**Scouting** (`development`) — rival attributes render behind a noise band that
shrinks over ~3 weeks of dedicated scouting; a better analyst makes the bands
*tighter*, not just faster.

**Staff** (`staff`) — one shared 50+ member pool. Seven attributes, mechanical
traits, career badges, role-weighted overall. Every tier-1 club has a concrete
head coach with a tactical identity; system fit scales only the coach's
contribution, never a raw combat buff — so a compatible lower-overall coach can
be the better hire.

**Finances** (`economy`, `sponsors`) — income vs payroll/upkeep, sponsor deals
with payout structures and achievement demands, insolvency with escalating
penalties and a projected runway.

**Season structure** (`schedule`) — regions, double round-robin, BO3 playoffs
with map veto, Masters, Champions, Challengers, offseason. World shape is data:
a roster pack reshapes it to 3–4 regions of 4–16 teams.

**Analytics & narrative** (`analytics`, `narrative`, `match_review`) — season
stats, an HLTV-flavored rating, clutches/multikills/aces, league leaders, awards,
and grounded recaps where every fact resolves to a real event in the log.

**Presentation** (`web/`) — FastAPI + vanilla JS on a design system. Ten tabs
(dashboard, club, tactics, market, season, stats, social, finances, facilities,
inbox). Isometric replay viewer over AI-painted map backdrops with full playback
control. Player/team/staff profile overlays from any name in the app. A rich CLI
that doubles as the regression harness.

Implementation note (2026-07-18): the compact presentation sentence above is
historical. The current navigation is nine top-level workspaces: Dashboard,
Inbox, Match, Club, Facilities, Season, Market, Stats, and Company. Match owns
tactics, game plans, opponent prep, tournament sixes, and series instructions;
Club owns Squad, Development, Locker Room, and Operations; Market owns
Players, Scouting, and Staff; Company owns Finances and Brand. Social and
Finance deep links route into Company rather than creating duplicate screens.

---

## 4. Additional systems

Everything layered on top. These are the depth, and (see the loop analysis) the
attribution problem.

### Living world / legacy

| System | Module | What it does |
|---|---|---|
| **Chronicle** | `chronicle` | Append-only career-event list (titles, awards, moves, debuts, milestones). Never pruned. *Every* legacy system reads it — mirrors "the event log is the only truth." |
| Career / Legacy Mode | `career` | `sandbox` vs `legacy`. Manager seats that follow the person, career offers, board patience, dismissal, job market, reputation + philosophies **derived** from the chronicle. |
| Personality | `personality` | Five axes as a pure function of id + tags. |
| Memories | `memories` | Player loyalty bias, board posture. Bounded nudges. |
| Rivalries | `rivalries` | Pair heat from playoff meetings and poaches; cools in the offseason. |
| Hall of Fame | `hof` | Induction at retirement — the one *stored* legacy view. |
| Org knowledge | `knowledge` | Playbooks, anti-strats, methodology. Leaks with staff moves, dates on balance patches, feeds prep edge only through a set game plan. Guarded by the dynasty gate. |
| Coaching tree | `staff.retire_into_staff` | Retirees become staff, deterministically. |
| Dynamic meta | `meta` | Usage-driven agent buffs/nerfs twice a season; strategy diffusion (strugglers copy the winning identity); season-end meta eras chronicled. |

### Squad & people

| System | Module | What it does |
|---|---|---|
| Culture | `culture` | Captain/council, team principles, bounded relationship arcs, culture sessions. |
| Locker room | `locker_room` | Locker-room state. |
| Mentorship | `mentorship`, `development` | Manager-set mentor→protégé pairs raise the protégé's *ceiling*. |
| Promises | `promises` | Commitments to players (minutes, signings) that settle and cost trust if broken. |
| Transfer requests | `transfer_requests` | Benched players good enough to start elsewhere ask out. |
| Talk / pep talk / shouts | `talk`, `pep_talk`, `shouts` | Weekly 1:1 (topic read off the player's real state), pre-match team talk, in-series shouts. LLM-ghostwritten at serve time; the deterministic text stays in the save. |
| Role fit | `role_fit` | Assignment comfort and IGL experience accrue with reps. |
| Academy | `academy` | Tier-1 parents over real tier-2 affiliates: intake, promotion/send-down, minutes-based growth. |

### Org & operations

| System | Module | What it does |
|---|---|---|
| Facilities | `facilities`, `economy` | Six upgrade tracks (Training Centre, VOD Room, Media, Recovery Suite, Strategy Lab, Team House). Wellbeing benefits only pull toward neutral 50. |
| Preparation | `preparation` | Scrim/bootcamp plans → grounded reports + org knowledge. |
| Series management | `series_management` | Tournament sixes, conditional between-map responses. |
| Delegation | `delegation` | Hand staff policy control over renewals, scouting, training. The pressure valve on the action surface. |
| Media events | `media_events` | Rare contextual choices with persistent trust/sponsor/sentiment effects. |
| Flavor events | `flavor_events` | LLM-copy campaign events. |
| Social | `social` | Follower counts, deterministic weekly feed, per-team community sentiment that chases results and feeds back into confidence/morale and sponsor pressure. |
| Badges | `badges` | Grounded milestone/feat badges from real box scores. |
| Relationship arcs | `arcs`, `relationships` | Scarce grudge, friction, and mentor-bond arcs derived from real roster history; bounded effects, never a hidden replacement for the relationship graph. |
| Decision ledger | `decision_ledger` | Settles recent human calls against subsequent state and records grounded paid-off, neutral, or backfired outcomes. |
| Match review | `match_review` | Attributes relevant manager calls to a played match and explains the observed result from event-log and campaign facts. |
| Sim Ahead | `sim_ahead` | Advances through delegated weeks until a hard decision point, preserving the same deterministic tick contract. |
| Market history | `market_history` | Transfer record. |
| GM personalities | `gm_personalities` | AI org decision-making flavor. |
| Rival managers | `rival_managers` | Named, persistent AI tier-one managers with region-flavored identities, tenure, board reviews, movement history, and no hidden match modifiers. |
| xDuel | `xduel` | Expected-duel analytics. |
| LLM playtest | `llm_playtest`, `llm_talk`, `flavor_events` | Grounded external-manager playtesting and optional serve-time copy; deterministic facts remain in the save and the model cannot invent events. |

### Substrate (not player-facing)

| System | Module | What it does |
|---|---|---|
| Telemetry | `telemetry` | `action_log` records every **human** decision (AI moves re-derive from the seed), so seed + action log fully determines a career. Weekly per-seat feature vectors. Single source of truth for RL episodes. |
| Decision env | `decision_env` | Shared manager observation + legal-action masks; deterministic headless policy env. |
| Manager policy | `manager_policy`, `learned_manager_policy`, `rollout`, `online_manager_learning` | Heuristic baseline, imitation checkpoints, online fine-tuning behind a promotion gate. |
| Player policy | `policy/` | Engine-facing heuristic and learned rankers over fog-safe observations. |

---

## 5. Player-facing design traceability

This is the compact audit map for keeping the design record attached to the
game rather than to a speculative feature list.

| Design area | What the player can do or observe | Authoritative implementation |
|---|---|---|
| Start a career | Choose a club in Sandbox, choose one of four deterministic scenarios, complete the Fantasy Draft interview and snake draft, or accept a Legacy offer | `manager/scenarios.py`, `manager/fantasy_draft.py`, `manager/career.py`, `web/server.py` |
| Build a roster | Carry up to ten, dress five per map, set IGL and agents, register a tournament six, promote/send down academy players, sign/release/renew/buy out | `manager/market.py`, `manager/academy.py`, `sim/lineup.py`, `manager/series_management.py` |
| Develop people | Set team and player training, intensity, focus, mentorship, rest, scrim reps, language support, and facility investment; read forecasts rather than exact ceilings | `manager/training.py`, `manager/development.py`, `manager/mentorship.py`, `manager/facilities.py` |
| Run the organization | Hire staff, assign or delegate renewals/scouting/training, manage contracts, sponsors, finances, facilities, preparation, and media commitments | `manager/staff.py`, `manager/delegation.py`, `manager/economy.py`, `manager/sponsors.py`, `manager/preparation.py`, `manager/media_events.py` |
| Manage the humans | Talk to players, give pep talks and shouts, set captain/council/principle, honor promises, respond to transfer requests, and navigate bounded relationship arcs | `manager/talk.py`, `manager/pep_talk.py`, `manager/shouts.py`, `manager/culture.py`, `manager/promises.py`, `manager/transfer_requests.py`, `manager/arcs.py` |
| Prepare matches | Set five neutral-safe coaching dials, site focus, game plans, opponent prep, lineup, tournament six, conditional map responses, and timeouts | `src/esports_sim/schemas/team.py`, `src/esports_sim/sim/tactics_fit.py`, `src/esports_sim/manager/preparation.py`, `src/esports_sim/manager/series_management.py`, `src/esports_sim/sim/engine.py` |
| Watch matches | Read the canonical event log as a floor-plan replay with continuous movement, cover, elevation, sightlines, utility, gimmicks, economy, retakes, saves, camera controls, and audio cues | `sim/engine.py`, `schemas/events.py`, `web/static/viewer.js`, `data/maps/geometry/` |
| Live in a world | Follow standings, stats, awards, social feed, sponsors, patches, meta eras, Chronicle, rivalries, Hall of Fame, staff coaching tree, named rival managers, and career history | `manager/analytics.py`, `manager/social.py`, `manager/meta.py`, `manager/chronicle.py`, `manager/rivalries.py`, `manager/hof.py`, `manager/staff.py`, `manager/rival_managers.py` |
| Understand consequences | See inbox priorities, Dashboard needs-you prompts, decision-ledger verdicts, match-review attribution, player/team/staff profiles, and server-computed scouting/privacy gates | `manager/inbox.py`, `manager/decision_ledger.py`, `manager/match_review.py`, `web/server.py`, `web/static/profile.js` |

The following are design constraints, not implementation suggestions: campaign
state and match logs are deterministic for a seed; match-gate tactics are
neutral-safe at 50; the event log is the only match truth; the web client does
not mirror simulation formulas; and public/rival information is filtered by
the server before it reaches the UI.

---

## 6. Invariants any new system must respect

1. **Determinism** — same seed → byte-identical log *and* `GameState`. Labelled
   RNG streams only; never `hash()`, never wall-clock, always sorted iteration.
2. **Golden gate** — engine/data changes that move the canonical log or the
   multi-seed sweep need a deliberate re-bless in the same commit.
3. **Balance band** — 45–65% attack-round rate on every map.
4. **Neutral-safe tactics** — every dial term is an exact no-op at 50.
5. **The event log is the only truth** — the UI holds no sim state and never
   mirrors an engine formula in JS. Serialize computed values instead.
6. **Own RNG stream per system** — so a new system never shifts an old one's
   draws.
