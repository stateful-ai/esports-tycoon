# Roadmap

**Project:** esports-sim — Valorant-inspired tycoon + RL substrate + world-model research target
**Format:** Now / Next / Later. Avoids false precision for a solo long-horizon project.
**Last updated:** 2026-07-09

---

## North-star bets

Three outcomes the whole project is aiming at. Everything on the roadmap should serve at least one. If an initiative doesn't ladder up to one of these, it goes on the parking lot, not on the roadmap.

1. **Matches feel alive.** Two replays of the same teams with different seeds produce visibly different, legible stories. Mechanical skill doesn't overwhelm intangibles; chemistry, tilt, and clutch moments show up on screen.
2. **An LLM can run a full season competently through the headless API.** Proves the state-view + legal-actions contract is legible enough for external players — which is the same contract RL agents and human UIs will use.
3. **A world model trained on agent gameplay can sample a plausible season.** The research capstone. Success = unconditional + conditional season generation that reads as "yeah, that could have happened."

---

## Now (active, 0-2 weeks)

**→ Headless LLM-playtest harness (north-star bet #2).** The state-view +
action API already drives the CLI, web UI, and `--auto` runs; the missing
piece is a harness that hands an LLM the state + legal actions each week
and collects a season-long narrative critique. This is the next
committed item — everything below it in "Next" shipped.

Also open, smaller: Scenario-API sampling of the trained `esports-sim-diorama`
LoRA (works from the Scenario web UI; the legacy inference endpoints 500 —
see `assets/office/style/lora/STATUS.md`), development-milestone inbox
items, viewer camera follow/zoom, animated office characters.

Previously in Now — all done: Sprint 0 (schemas/RNG/events/tests), design
system v0, engineering guardrails skill, heuristic policy v0, and
**Sprint 2 — "See the game"** (web UI, match viewer, narrative v0,
analytics, veto + scouting fog, maps/agents/art) — see
[docs/sprints/sprint-02.md](docs/sprints/sprint-02.md).

---

## Next (MVP game loop — target ~3 months) — ✅ SHIPPED

All five phases below are done (see the 2026-07-07/09 changelog entries);
the tables are kept as the acceptance record. The only remnant is the LLM
half of Phase 5, promoted to "Now" above.

### Phase 1 — Match engine (3-5 weeks) · *primary risk*

| Item | Acceptance |
|---|---|
| Round lifecycle — BUY → ROUND → POST_PLANT → END | Phase-transition events in the log |
| Sightline resolver over callout graph + utility | Smoke breaks a sightline for N ticks; test verifies |
| Duel resolver (weapon + attributes + movement → p(hit)) | KillEvent emitted with killer / victim / weapon / callout |
| Economy system | BuyEvent per player per round; force/eco/full all reachable |
| Full match to first-to-13 + side swap + OT | Match completes with valid MatchEndEvent |
| **Acceptance gate**: un-xfail `test_match_determinism_identical_seed_identical_events` and it passes strict | |
| **"Feels alive" gate**: 20 matches with same teams + different seeds produce visibly different event streams (>20% variance in round-by-round kill patterns) | |

### Phase 2 — 2D match viewer (1-2 weeks)

| Item | Acceptance |
|---|---|
| Event-log replay engine — viewer is pure consumer, no independent state | Toggle file → viewer renders a saved match |
| Haven render — sites, callouts, player dots, utility markers | Matches showcase.html styling |
| Kill feed + scoreline bound to events | Updates in playback |
| Playback controls: 1× / 4× / 16× / instant, pause, scrub | Skippable as locked in design |

### Phase 3 — Tycoon loop (2-3 weeks)

| Item | Acceptance |
|---|---|
| Calendar + week ticker | `advance_week()` fires scheduled events deterministically |
| Action system — ~15 actions (TRAIN, REST, SCRIM, HIRE/RELEASE/RENEW, SIGN_SPONSOR, UPGRADE_FACILITY…) | All actions typed + validated + emit events |
| Weekly training / rest effects on attributes + stamina + morale | Week-over-week deltas observable |
| Contracts + basic finance (payroll, sponsors, bankruptcy gate) | A 52-week season runs without degenerate loops |
| Single-region VCT-flavoured structure (Kickoff → Split → Playoffs) | One full season playable end-to-end |

### Phase 4 — Narrative (1-2 weeks)

| Item | Acceptance |
|---|---|
| Event-driven narrative engine | Template-based news items from event stream |
| Match recaps from event log | "Vortex clutched a 1v3 on Haven to force OT" reads clean |
| News ticker on the dashboard | Narrative items visible in UI |

### Phase 5 — Headless API + LLM playtest (1-2 weeks)

| Item | Acceptance |
|---|---|
| Stable `sim.advance(actions, ticks) → events` entry point | UI + tests + agents all go through the same contract |
| CLI harness: `simulate_season(seed, policy) → JSONL` | Reproducible seasons from the command line |
| LLM-plays-tycoon loop | Claude (or any LLM) receives state + legal actions, picks, sim advances |
| Automated playtest report generator | LLM plays 10 seasons, writes narrative critique |
| **Acceptance gate**: an LLM plays a full season without bankruptcy or illegal actions | |

---

## Later (post-MVP — 3-12+ months)

Three parallel tracks. **Not sequential.** Once the MVP is real, pick the track the MVP's flaws suggest first. Probably start with Track A for a month to deepen the sim before the RL work rewards it.

### Track A — Depth & realism ("feels more like life")

Shipped from this track already: scouting fog + subsystem, the pairwise
relationship graph, multi-region VCT + Challengers, all planned maps and
agents, coaching staff/analyst/physio, the coaching-dial tactics system,
sponsorship depth, insolvency, traits/potential/development — and, as of
the coaching-loop pass (2026-07-09): tilt spirals + heaters (in-match
momentum amplifying confidence deviation, plus cross-week threshold
events), the community-sentiment layer (feed → sentiment →
confidence/morale + sponsor pressure), meta patch cycles (usage-driven
agent buffs/nerfs held on GameState), pre-match game plans (per-match
dial overrides, focus targets, scouting-scaled prep edge), and
one-match lineups over the 7-man bench — and, as of the Legacy Mode
pass (2026-07-09, GDD section 10): the career Chronicle (append-only
history every legacy system reads), two game modes (sandbox = classic,
legacy = career offers + manager contracts + board patience + dismissal
+ job market, solo and LAN), chronicle-derived manager reputation and
earned philosophies, personality axes under the tags, player/org
memories (loyalty in renewals/talks, board posture on reunions),
rivalries, the Hall of Fame, living-history title callbacks, per-save
media voices, the coaching tree (retirees into the staff pool),
organizational knowledge (playbooks/anti-strats/methodology feeding the
game-plan prep edge, guarded by the new dynasty gate), a psychologist +
performance-coach department with weekly analytics briefings, and
strategy diffusion with chronicled meta eras. Still open:

- Mid-series (between-map) substitutions — lineups are per-match today
- AI orgs setting game plans / carrying benches (documented parity choice)
- Memories/relationship arcs beyond loyalty (grudges, mentor bonds)

### Track B — RL research arm

Shipped (2026-07-10): the data substrate — every human decision recorded
as a typed `action_log` on GameState, weekly per-seat state feature
snapshots, shared reward shaping (`manager/telemetry.py`), and
`scripts/export_telemetry.py` emitting (state, actions, reward, next
state) JSONL episodes from any save. Still open:

- Gym-style `env` wrapper over the headless API (obs/reward now exist —
  the wrapper should consume `telemetry.state_features` and
  `reward_components`, never re-derive its own)
- Baseline single-agent PPO on the tycoon role (proves the wrapper)
- Per-player RL policies — multi-agent; distinct "thinking" per player archetype
- Population-based self-play across organisations (not just players)
- Distilling policy archetypes ("aggressive entry", "passive anchor", "tilt-prone clutch hero") into named personalities

### Track C — World model

Shipped (2026-07-10): the match-level tokenizer —
`scripts/dump_season_tokens.py` turns deterministic match corpora into
side-attributed token streams (75-token pinned vocab v1: round flow,
buy tiers, kills by weapon class/headshot/trade, utility, spike,
gimmicks). Still open:

- Season-level event tokenizer (campaign events as token streams)
- Transformer pretraining on agent-played seasons
- Conditional generation (dream a season given a roster)
- Counterfactual play ("what if we'd hired X instead of Y")
- Decision: symbolic-state WM vs. pixel-space WM (the fork we deferred in design)

---

## Dependencies & risks

| Risk | Severity | Mitigation |
|---|---|---|
| Match engine fails the "feels alive" gate | **High** | Budget 5 weeks, not 3. The variance gate is non-negotiable; don't move to Phase 2 until it passes. |
| Determinism drift as the codebase grows | **High** | North-star determinism test gates the suite from Phase 1 onward. Strict `xfail` → strict `pass` is the only transition. |
| Decision-logic sprawl out of policy module | Medium | Guardrails skill enforces "one heuristic module". Code review keyed on it. |
| Scope creep from Track A into MVP phases | Medium | Later items are locked out of MVP phases. New ask → trade something off, don't add. |
| World model needs pixel data (not event tokens) | Medium | Design fork deferred until event-sequence WM is actually tried. If it fails, re-open the fork with data. |
| LLM playtest shows the action space is wrong | Low-Medium | Intentional — the playtest *is* the probe. Phase 5 failure is a Phase 3 action-space redesign, not a blocker. |

---

## Out of scope (year 1)

Explicit non-goals. Calling these out so we don't drift.

- ~~Real Valorant pro names or their real statistical profiles~~ **Amended 2026-07-09 (owner call):** the game is private (never publishing), so an optional VCT 2026 roster pack imports the real teams/players; the shipped default world stays fictional and pack attributes are original estimates, not scraped stats.
- ~~3D match rendering (callout-graph + 2D is the whole thesis)~~ **Amended 2026-07-07 (owner call):** the sim keeps the callout graph as its decision vocabulary, but maps now carry floor-plan geometry (`data/maps/geometry/`) rendered as an isometric viewer, and the engine consumes physical distances (range-aware duels). True 3D remains out of scope.
- Multiplayer / network play
- Mobile port
- Steam / commercial release
- Real-time voice comms in the sim
- Esports betting / fantasy mechanics
- Valorant-API scraping or Riot data partnerships

---

## Changelog

- **2026-07-09 (Legacy Mode)** — GDD section 10 shipped in one pass,
  phases P0-P5 on a chronicle-first architecture (see
  `docs/proposals/2026-07-09-new-systems-proposal.md`): career
  Chronicle + schema v5, sandbox/legacy game modes with career offers,
  manager contracts, board reviews, dismissal and the job market;
  derived reputation + earned philosophies; personality axes +
  memories; rivalries, Hall of Fame, living history, per-save media
  voices; coaching tree, org knowledge + dynasty gate, expanded
  backroom department; strategy diffusion + chronicled meta eras.
- **2026-07-09** — The game grew past the MVP frame: Sprint 2 and the
  whole "Next" block shipped (web app + isometric viewer, narrative,
  analytics, veto/fog), then kept going — floor geometry with
  continuous movement and the floor-connection audit gate, micro-combat,
  authored map gimmicks, multi-region VCT through Champions, the
  neutral-safe coaching-dial system with per-player roster fit
  (ADR-007), inbox, player/team profiles, dashboard hub, the painted
  office and painted map backdrops via the blockout→beautify art
  pipeline, and a trained Scenario style LoRA. Suite is 179 tests + five
  report gates. "Now" is the LLM-playtest harness (bet #2).
- **2026-07-07** — MVP built in one push: Phase 1 (match engine, determinism gate strict-passing), Phase 3 (tycoon loop: league/training/economy/market/save-load), and the headless half of Phase 5 (`--auto` CLI) are done; 33 tests, CI live. Repo published to github.com/stateful-ai/esports-tycoon (old prototype preserved on `legacy-tycoon`; salvage in `docs/salvage/`). Phases 2 + 4 fold into **Sprint 2 — "See the game"** (`docs/sprints/sprint-02.md`) alongside analytics, veto, scouting fog, and content.
- **2026-04-22** — First roadmap. Sprint 0 scaffold, design system v0, and engineering guardrails skill marked Done. Heuristic policy v0 is the next active item.
