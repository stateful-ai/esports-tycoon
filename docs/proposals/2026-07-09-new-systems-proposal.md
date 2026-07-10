# Path forward — Legacy Mode (GDD §10) + remaining candidates

**Source:** `GDD.md` (2026-07-09, evening revision) — new §10 "Legacy Mode
(Proposed)" — plus §8 next candidates and `ROADMAP.md`.
**Baseline:** PR #199 is merged. The coaching loop (game plans, momentum/tilt,
sentiment, meta patches, one-match lineups) is now substrate, not future work.
Supersedes the earlier draft of this document.

---

## The architectural centerpiece: extend "the log is the only truth" to career scale

Every Legacy Mode system in §10 — career profile, "Known For", player/org
memories, Hall of Fame, rivalries, living history, the coaching tree's
lineage — is a *view over history*. If each stores its own history, twelve
copies drift apart (the exact failure ADR-003 exists to prevent at match
scale). So the first deliverable is the one they all read:

**The Chronicle** — an append-only list of typed `ChronicleEntry` records on
`GameState` (`manager/chronicle.py`): kind (title, playoff run, collapse,
upset, signing, release, benching, debut, retirement, record, milestone,
poach, dismissal, ...), the entities involved (player/team/staff/manager
ids), season/week, a compact payload, and an importance score. Entries are
emitted from the seams that already know when something happened
(`campaign.advance_week`, offseason, `market.py`, awards). Everything
downstream is a pure reader, mirroring how `sim/stats.py` reads the match
log and can't drift it.

Practical constraints designed in from day one:

- **Retention:** owner has waived a save-size budget, so the chronicle simply
  records everything — no pruning machinery. Entries stay typed and compact,
  and the importance score is still stored (memories/rivalries/HoF select by
  it), but nothing is ever dropped. If a 50-season save ever gets slow,
  pruning can be added then without a schema change.
- **Derived, never stored:** reputation, career stats, HoF eligibility, and
  "Known For" strings are computed from the chronicle on read. No cached
  aggregates that can drift.
- **Migration:** schema bump; backfill a skeleton chronicle from the history
  GameState already keeps (`champions`, `awards`, `retired`, `patch_history`),
  so existing saves get a usable past.
- **Determinism:** entries are pure functions of state transitions — no rng.
  Where selection needs tie-breaks, blake2 of stable ids, sorted iteration.

One pleasant unification: §8's "development-milestone inbox items" stops
being its own feature — a milestone is just a chronicle entry whose emission
also surfaces an inbox item. The prior-week snapshot problem is solved by
the chronicle being the record of crossings.

---

## Phased plan

Each phase is independently shippable and gated. GDD §10's suggested tracks
(Living World / Organizational Simulation / Competitive Evolution) map onto
phases 1–3 / 4 / 5.

### Phase 0 — Chronicle substrate (1–2 sessions)

As above: `manager/chronicle.py`, `ChronicleEntry`, emission hooks, migration
+ backfill, determinism tests, and the milestone→inbox surfacing. No gameplay
effects yet — pure recording — so no gate risk.

### Phase 1 — The manager career frame (2–3 sessions)

The frame change that makes it "Legacy Mode": you are a *coach with a
career*, not an org picked once and held forever.

- **Two game modes (locked):** `game_mode: "sandbox" | "legacy"` on
  `GameState`, chosen at new game in the lobby (web world selector + CLI
  prompt). **Sandbox** is exactly today's behavior — pick any org, manage
  forever, no contracts. **Legacy** adds the career layer. Both modes
  support single-player and LAN multiplayer; the host's mode choice applies
  to the whole session. Legacy-only systems gate on the field, so sandbox
  saves, the LLM-harness acceptance criteria, and every existing test run
  unchanged. Migration: old saves load as sandbox.
- **`Manager` entity** — id, name, and career read entirely off the
  chronicle. **Reputation** = the six GDD axes (development, tactical
  innovation, culture, analytics, international success, pressure handling)
  derived with recency weighting from chronicle entries — historical
  behavior, not XP, exactly as the GDD asks.
- **Career offers at new game (legacy):** 3–4 generated org offers instead
  of the full team list. The archetypes (Dynasty / Rebuilder / Academy
  Specialist / Sleeping Giant) are parameter bundles over org fields that
  *all already exist* — balance, facility level, staff quality, fan count,
  academy (tier-2 affiliate strength), board expectation + patience. In a
  multiplayer lobby each seat gets its own deterministic offer set (blake2
  of seed + seat), picks in join order, and offers never collide.
- **Manager contract & firing (locked):** in legacy mode each seat holds a
  contract with its org — length in seasons plus per-season board goals
  (reuse the `SponsorObjective` kind vocabulary — `make_playoffs`,
  `win_split`, `make_masters`...) scaled to the org archetype. Missing goals
  burns board patience; exhausting it (or finishing a contract the board
  won't renew) = **dismissal** → the job market: offers generated from org
  need + manager reputation, at season end (mid-season firing only past a
  deep patience floor, so one bad split isn't instant death). Getting fired
  continues the career; it doesn't end the save. Sandbox has none of this.
- **Career profile screen** (`/web-screen` pattern: server-side serializer,
  pure chronicle reader): career record, titles, players developed, academy
  promotions, HoF'ers coached, and generated "Known For" lines.
- **LAN note:** contracts, patience, and dismissal are per manager seat
  (`human_team_ids`); a fired seat re-enters the job market while the
  others play on — a fired player picking a new org mid-session is a
  feature, not an edge case.

### Phase 2 — Persistent memory (1–2 sessions)

- **Player memories:** a deterministic selector over chronicle entries
  involving that player (debut given, public backing, benching, title runs,
  contract disputes; cap ~10, importance-retained). Effects are small and
  bounded, riding existing seams: renewal willingness/asking price
  (`market.py`), talk outcome weights (`talk.py`), loyalty on contested FA
  bids, reunion affinity when an old manager/teammate reappears
  (`relationships.affinity_target`). The talks doctrine applies: a memory
  is a nudge, not a lever.
- **Org memories:** same mechanism at org scope — eras, first titles, how a
  manager left. Returning to a former org changes the board's starting
  patience and fan sentiment posture.
- Surfaced in profiles and the inbox ("remembers you gave him his debut").
- **Gate watch:** memory → morale → results is a feedback loop; run the
  snowball gate over multi-season sims before merge.

### Phase 3 — Living-world texture (2–3 sessions)

- **Rivalries:** persistent pair records (org–org, player–player,
  manager–manager, region–region) whose intensity accumulates from
  chronicle-worthy meetings — playoff eliminations, finals, upsets, poached
  players — and decays seasonally. Feeds fan engagement and sponsor value
  through the existing social/sponsor seams, and player motivation as a
  bounded per-match modifier through the **optional-param engine seam #199
  established** (`plans=` pattern: gates never construct one → zero golden
  risk).
- **Hall of Fame:** offseason induction pass over chronicle + career stats
  (players, managers, dynasties, greatest teams/matches/upsets); a dedicated
  screen that is a pure reader. Induction thresholds are constants in one
  place, tuned against a long headless run so the Hall isn't empty or
  crowded.
- **Living history in narrative:** `narrative.py` recap templates gain
  chronicle citations — "first title since S3", "revenge for the S5 final",
  "the org that passed on him" — extending the grounded-recap doctrine
  (every cited fact resolves to a chronicle entry; silence beats invented
  drama). `head_to_head` already does this within a season; the chronicle
  extends its reach across seasons.
- **Media ecosystem:** keep the append-only social stream as the single
  channel (#199), but give the save persistent named voices — deterministic
  per-save outlets, pundits, a podcast — as authors, with multi-week threads
  (a rumor opens, develops, resolves) driven by chronicle + current state.
  Evolving narrative without a second truth store.

### Phase 4 — Organizational simulation (3–4 sessions)

- **Coaching tree:** at retirement, eligible players (IGL playstyle, high
  game-sense/comms, personality fit) convert into staff-pool candidates —
  `staff.py`'s model already carries `history`/`titles`/
  `seasons_experience`, so this extends rather than replaces. Lineage links
  (played under manager X, in system Y) are chronicle-derived; their
  generated specialty/traits echo the systems they played in. Your
  ex-players coaching rivals *is* the "indirectly shape the esport" fantasy.
- **Philosophy system:** manager identities (Trust Rookies, Veteran
  Leadership, Heavy Analytics, Mental Wellness, ...) are *earned labels* —
  derived from repeated observed behavior in the chronicle, like reputation,
  rather than picked from a menu. Each grants a small campaign-layer effect
  (dev multiplier shading, talk weights, staff-hire affinity) and shapes
  which orgs/players want to work with you. Zero engine reach; distinct
  from `TeamTactics` per the GDD.
- **Organizational knowledge:** per-org knowledge items — playbook depth
  per map, anti-strat vs a specific org, practice methodology, analytical
  discoveries — accumulated from play and staff, applied through the
  **existing prep-edge / game-plan seam** (bounded, campaign-only). Staff
  departures leak items to the hiring org; meta patches (`meta.py`)
  obsolete map/agent-specific items. This is the designed dynasty engine
  and therefore the biggest balance risk in §10: add a **dynasty report**
  (long-run headless: title concentration, e.g. Gini/top-org share over 20
  seasons) as a new gate before it merges.
- **Analytics department:** generalize the three staff slots into
  department roles (replay analyst, data scientist, sports psychologist,
  performance coach), each mapped to exactly one existing lever — scout
  accuracy, `analytics_tier` stat depth, confidence regression rate,
  stamina recovery — the mapping pattern `staff.py` already uses. Weekly
  department reports (opponent tendencies from real stat splits) arrive as
  inbox items.

### Phase 5 — Competitive evolution (1–2 sessions)

Dynamic meta on top of what #199 shipped: AI coaches already adapt in-season
and patches already shift agents. Add **strategy diffusion** — AI orgs
imitate the dial identities of recent winners (with noise), and teams facing
a known extreme identity counter through the game-plan seam — and record
meta eras in the chronicle so every long save accretes its own tactical
history ("the S7 double-controller era"). Guarded by the tactics-sweep,
balance, and snowball gates; all campaign-layer.

---

## Where the §8 candidates land now

| Item | Status in this plan |
|---|---|
| LLM-playtest harness | **Stays the committed "Now" item** — do it first/parallel; Legacy Mode multiplies its value (an agent grinding 20-season careers is exactly how phases 2–5 get playtested). Design unchanged from the earlier draft: extract `manager/actions.py` (typed `WeeklyAction`, `legal_actions()`, `apply_action()`) from the web endpoints, state-view serializer, transcript-as-replayable-action-log for determinism. |
| Dev-milestone inbox items | Absorbed into Phase 0 (chronicle entries surfaced as inbox items). |
| Viewer camera follow/zoom | Unchanged, independent, 1 session — animate the SVG `viewBox` only (backdrop shares the coordinate space, transform contract untouched); lerped follow of a player or event centroid. Schedule anytime. |
| Scenario LoRA sampling | Unchanged, half-session research task; independent. |
| Personality axes | Folded into the Legacy arc: do the tag→axis migration alongside Phase 2 (memories) — memories and philosophies want continuous personality reads, so build them on axes rather than retrofitting later. |
| RL env wrapper | After the harness (shares the action contract). A Legacy-aware reward (career reputation) is a natural later extension. |
| World-model tokenizer | Opportunistic one session; harness runs generate its data for free. |
| Animated office characters | Still parked with office.js. |
| Mid-series subs / AI bench parity | Small follow-ons, unscheduled. |

## Recommended sequence

1. **LLM-playtest harness** (roadmap's committed item; unblocks RL env, feeds world-model data).
2. **Phase 0 — Chronicle** (small, zero-risk, everything in §10 needs it).
3. **Phase 1 — Career frame** (the visible "Legacy Mode exists" release).
4. **Phase 2 — Memories + personality axes.**
5. **Phase 3 — Rivalries / HoF / living history / media.**
6. **Phase 4 — Org sim** (with the new dynasty-report gate).
7. **Phase 5 — Dynamic meta diffusion.**

Camera, LoRA sampling, and the tokenizer slot into gaps as palate cleansers.

## Locked decisions (owner, 2026-07-09)

1. **Two game modes:** Sandbox (current behavior) and Legacy, selected at
   new game; both single-player and multiplayer.
2. **Manager contracts with firing:** legacy managers hold a contract and
   can be dismissed for missing board goals.
3. **No save-size budget:** the chronicle records everything; no pruning.

## Cross-cutting rules (unchanged)

- Campaign determinism: rng only via `RngTree` labels / blake2 of stable
  ids; sorted iteration; no wall clock. Chronicle emission is rng-free.
- Every `GameState` shape change: `SCHEMA_VERSION` bump + `_MIGRATIONS`
  entry, even pass-through.
- Engine reach only through optional params defaulting to None (the #199
  pattern); gates never construct them; golden stays byte-identical.
- UI holds no sim state; new screens are thin serializers; analytics depth
  gated server-side by `analytics_tier`.
- ASCII-only CLI/report output; `/ship` before any push.
