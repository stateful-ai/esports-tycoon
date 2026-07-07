# Roadmap

**Project:** esports-sim — Valorant-inspired tycoon + RL substrate + world-model research target
**Format:** Now / Next / Later. Avoids false precision for a solo long-horizon project.
**Last updated:** 2026-04-22

---

## North-star bets

Three outcomes the whole project is aiming at. Everything on the roadmap should serve at least one. If an initiative doesn't ladder up to one of these, it goes on the parking lot, not on the roadmap.

1. **Matches feel alive.** Two replays of the same teams with different seeds produce visibly different, legible stories. Mechanical skill doesn't overwhelm intangibles; chemistry, tilt, and clutch moments show up on screen.
2. **An LLM can run a full season competently through the headless API.** Proves the state-view + legal-actions contract is legible enough for external players — which is the same contract RL agents and human UIs will use.
3. **A world model trained on agent gameplay can sample a plausible season.** The research capstone. Success = unconditional + conditional season generation that reads as "yeah, that could have happened."

---

## Now (active, 0-2 weeks)

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | **Sprint 0** — schemas, RNG tree, event log, data files, tests | ✅ Done | 18 passing + 1 xfail north-star test |
| 2 | **Design system v0** — tokens, components, showcase | ✅ Done | `ui/design-system/` |
| 3 | **Engineering guardrails** — skill enforcing determinism / typed-boundary / data-driven rules | ✅ Done | `skills/esports-sim-guardrails` |
| 4 | **Heuristic player policy v0** | Not started | Attribute-weighted decision function fulfilling `PlayerPolicy` contract. Seeds the match engine. |

---

## Next (MVP game loop — target ~3 months)

Five phases in order. Each phase gates the next. **Don't start the next phase until the previous phase's acceptance criterion passes.**

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
- Partial observability / fog-of-war on attributes (uses the `scouting_uncertainty` column already reserved)
- Scouting subsystem — hired scouts, attribute-noise shrinks with effort + time
- Pairwise relationship graph — replaces team-chemistry scalar; chemistry emerges from edges
- Personality / tilt-spiral event system — threshold-triggered attribute deltas
- Media & community sentiment layer — reactions feed back into morale
- Meta evolution — patch cycles that nerf / buff agents; meta becomes a driver of fortunes
- Multi-region VCT structure + Challengers / Ascension pathway
- Additional maps (Ascent, Bind, Lotus)
- Additional agents (Chamber, Skye, Viper, Cypher, Breach, Clove)
- Coaching staff, substitutes, analyst roles

### Track B — RL research arm
- Gym-style `env` wrapper over the headless API
- Baseline single-agent PPO on the tycoon role (proves the wrapper)
- Per-player RL policies — multi-agent; distinct "thinking" per player archetype
- Population-based self-play across organisations (not just players)
- Distilling policy archetypes ("aggressive entry", "passive anchor", "tilt-prone clutch hero") into named personalities

### Track C — World model
- Event-sequence tokenizer — seasons as token streams
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

- Real Valorant pro names or their real statistical profiles (legal + fictional roster works fine)
- 3D match rendering (callout-graph + 2D is the whole thesis)
- Multiplayer / network play
- Mobile port
- Steam / commercial release
- Real-time voice comms in the sim
- Esports betting / fantasy mechanics
- Valorant-API scraping or Riot data partnerships

---

## Changelog

- **2026-04-22** — First roadmap. Sprint 0 scaffold, design system v0, and engineering guardrails skill marked Done. Heuristic policy v0 is the next active item.
