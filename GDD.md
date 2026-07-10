# Game Design Document --- ESports Simulator

**Working title:** ESports Simulator (repo: `esports-tycoon`) **Genre:**
Esports management sim / tycoon, tick-level tactical shooter sim
underneath **Reference point:** *Esports Manager 2026* (Steam #2749950),
Valorant (setting/flavor), Football Manager (management-depth ambition)
**Status:** Playable, multi-season, browser + terminal. Actively in
development. **Last updated:** 2026-07-09

------------------------------------------------------------------------

## 1. Vision

You run a professional Valorant-flavored esports organization. You don't
aim, peek, or spray --- your players do that, and how well they do it is
a function of who you signed, how you trained them, how tired and happy
they are, what utility they popped, and where they were standing when
the fight started. Your job is everything around the ten minutes of a
round: scouting and signing talent, building a training program,
managing morale and burnout, calling in a coach, negotiating contracts,
chasing sponsors, picking (and banning) maps, and reading the story the
season tells through its results.

The foundational bet, stated plainly: **a deterministic simulation can
feel alive.** Two matches between the same two rosters, seeded
differently, should read as genuinely different stories --- not because
the engine rolls noise on top of a fixed outcome, but because who was
standing where, who peeked first, who popped a smoke a half-second late,
and who was on a three-game losing streak all compound into a different
match. Nothing in the sim is theater; every number the manager sees
traces back to an event in the log, and every event traces back to a
player attribute, a map feature, or a decision the manager made.

### Design pillars

1.  **The sim is the truth, not a curtain.** No hidden dice roll decides
    a match and then generates flavor text to match. Positions, ranges,
    cover, line-of-sight, and attributes produce the outcome; the
    outcome is what gets narrated.
2.  **Determinism is a feature, not an implementation detail.** Same
    seed, same decisions → byte-identical replay, forever. This is what
    makes "why did we lose that round" answerable, what makes an LLM or
    an RL agent a viable player, and what will eventually make a world
    model trainable on real play data.
3.  **You manage humans, not spreadsheets.** Morale, tilt, contract
    anxiety, and personality clashes are first-class systems, not flavor
    text bolted onto a stat block.
4.  **Depth without pixels.** The tactical layer doesn't need a game
    engine to feel real --- a floor plan, real distances, cover, and
    elevation get you 90% of the tactical richness of a full 3D shooter
    at a fraction of the complexity, and it stays fast enough to sim a
    whole season in seconds.
5.  **Everything is data until proven otherwise.** Agents, weapons,
    maps, and their floor geometry are YAML. A new agent or map is a
    content change, not a code change.

------------------------------------------------------------------------

## 2. The core loop

     ┌──────────────────────────────────────────────────────────────┐
     │  WEEKLY LOOP (repeats ~14-18 times per regular season)        │
     │                                                                │
     │  1. Review state    — roster health, standings, finances,     │
     │                        news, scouting reports                 │
     │  2. Set training    — pick a focus (mechanical/tactical/       │
     │                        mental/team/rest) for the week          │
     │  3. Work the market — sign/release/renew, respond to           │
     │                        sponsorship offers, assign a scout       │
     │  4. Talk to a player — one 1:1 conversation, topic driven by   │
     │                        that player's actual state               │
     │  5. Advance the week — the engine plays every scheduled        │
     │                        fixture, applies training/aging/         │
     │                        finances, and reports what happened      │
     │  6. Watch & read     — open a match replay, read the recap,    │
     │                        check the stat leaders and news ticker   │
     └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
            Regular season → Playoffs (BO3, map veto) → Champion
                                  │
                                  ▼
                  Offseason: aging, awards, roster churn, restart

Above this loop sits the **season loop** (regular season → playoffs →
offseason → next season, indefinitely) and beneath it sits the **match
loop**, which the manager mostly *watches* rather than plays --- an
entire tactical shooter's worth of simulation resolves in milliseconds,
then gets replayed at whatever pace the manager wants.

------------------------------------------------------------------------

## 3. The management layer

### 3.1 Your organization

You pick one team from the league to manage (two hand-authored "starter"
orgs exist --- Team Nexus and Team Vanguard --- plus generated league
teams). Your org has a roster (5 active players), a balance sheet,
reputation, fan count, world rank, and team chemistry.

### 3.2 Players

Every player is a bundle of ten numeric attributes across five
categories, scaled 1--99 (Football-Manager-style, not a 0--1 float,
because humans read that scale better):

  Category         Attributes
  ---------------- -------------------------------------------
  **Mechanical**   Aim Precision, Aim Reactivity, Movement
  **Tactical**     Game Sense, Utility Usage, Positioning
  **Mental**       Clutch Factor, Tilt Resistance, Composure
  **Team**         Comms Quality

Attributes are a registry (`data/attributes.yaml`), not a hardcoded
struct --- adding an eleventh attribute is a data change. On top of
attributes, every player carries:

-   **Role** (Duelist / Controller / Initiator / Sentinel / Flex) and
    **Playstyle** (IGL, Entry, Anchor, Lurker, AWPer, Support) ---
    orthogonal axes that drive both squad-building decisions and
    in-match behavior.
-   **Agent pool & map pool** --- per-agent and per-map mastery, so a
    player's third-best agent is meaningfully worse than their main.
-   **Career state** --- salary, contract length, morale, stamina, form,
    age, and free-form personality tags (`hot_head`, `veteran`,
    `rookie`, `star_player`, `volatile`, ...) that modulate how they
    respond to talks, tilt, and pressure.
-   **Condition** --- morale/stamina/form move week to week from
    training, match results, and rest, and they feed back into match
    performance (a burnt-out star plays worse than their attributes
    suggest).
-   **Relationships** --- teammates carry a pairwise chemistry graph
    that drifts toward trait-driven affinities (kindred tags bond,
    clashing tags grate), is pushed by shared wins and losses, and
    outlives roster moves. Two players chasing the same spotlight role
    (two would-be entries/AWPers/IGLs) develop friction. Team chemistry
    chases the roster's mean relationship and feeds back into how well
    the team executes a coordinated system (§3.11).
-   **Identity flavour** --- generated players carry region-appropriate
    names (an EMEA player no longer reads as "Minho Nakamura") and
    role-shaped attribute archetypes (entries out-aim, IGLs out-think).

### 3.3 Training

Each week you set one focus --- mechanical, tactical, mental, team, or
rest --- for your whole roster (the AI picks independently for its own
teams, weighting the choice by roster youth and its own tactical
identity). Growth follows age curves (young players improve faster,
veterans decay), and rest recovers stamina at the cost of growth. A
hired **coach** multiplies training gains. **System fit** matters too: a
player whose playstyle suits the coach's tactics (see 3.11) gets more
meaningful reps and develops faster; a mismatch develops slower.

### 3.4 Transfer market & contracts

A pool of free agents (deterministically generated, refreshed every
offseason) is available to sign. Players ask for salaries scaled to
their quality; signing, releasing (with a severance cost), and renewing
are all manager actions. Contracts run down week by week; a player
inside \~8 weeks of free agency with good form will press you for a
renewal conversation --- ignore it and morale suffers. AI teams work the
same market against you --- and a premium free agent is **contested**: a
rival org with a matching need may sign the best available FA out from
under you, so a marquee grab isn't guaranteed.

### 3.5 Scouting

Rival rosters aren't shown at full fidelity --- attributes render with a
noise band (`visibility`/`scouting_uncertainty`, reserved from day one
for exactly this). Assign your scout to a target team; the fog shrinks
over roughly three weeks of dedicated scouting, faster with a hired
**analyst** --- who also improves the *accuracy* of the read, not just
its speed (an elite analyst's bands hug the truth tighter at the same
progress). The report resets every offseason as rosters change.

### 3.6 Staff

Three backroom hires, each multiplying one system: a **coach** (training
growth), an **analyst** (scouting speed), a **physio** (weekly stamina
recovery). A small candidate market regenerates deterministically every
season; hiring is instant, releasing is free.

### 3.7 The Talk module

Once a week you can sit down with one of your players. The topic isn't
picked by the manager --- it's read off that player's actual state, in
priority order: **low morale** → **expiring contract** → **low stamina**
→ **poor form** → a generic check-in if nothing's actually wrong. You
pick one of three approaches (reassure / challenge / listen, or the
topic-appropriate equivalent), and the outcome is modulated by that
player's personality tags with a deterministic roll --- a `hot_head`
bristles at being challenged more often than a `calm veteran` does.
Effects are small on purpose: a talk is a nudge, not a lever you crank.

### 3.8 Finances

Weekly income (sponsorships scaled by reputation and fan count, plus
prize money) against weekly expenses (payroll, facilities).
**Sponsorship deals** arrive as time-limited offers --- upfront, steady,
or performance-scaled payout structures, some carrying achievement
objectives that reward results *or* squad-building (e.g. "field an
under-21 talent") --- that you accept or decline. **Insolvency now
bites**: an org running a negative balance takes escalating reputation
and squad-morale penalties and a board warning, with a harsher one past
a debt floor. The finances tab projects a **runway** --- weeks until the
balance would cross that floor at the current run rate.

### 3.9 Season structure

Three regional leagues of 8 (Americas / EMEA / Pacific) each run a
double round-robin regular season (14 weeks), then a 4-team BO3 playoff
bracket (1v4, 2v3) with **map veto** (mastery-driven ban/pick over the
5-map pool) down to a regional champion; the top teams advance to
**Masters** (cross-region) and then **Champions**. The world shape is
data, not code: a **roster pack** (§6) can reshape it to 3 or 4 regions
of 4--16 teams --- with 4 regions, Masters becomes a full 8-side
quarterfinal bracket (instead of 6 sides with two byes) and Champions
fields the Masters eight. A per-region Challengers circuit develops
prospects underneath. Standings break ties by wins → round differential
→ **head-to-head** (regular-season meetings only, so a playoff rematch
never reorders the table) → rounds won → id. Then an offseason (aging,
retirements, rookie classes, awards, free-agent refresh) before the next
season. Campaigns run indefinitely --- there is no scripted ending.

### 3.10 Analytics & storylines

Season-long stat aggregation (K/D/A, an HLTV-flavored rating, first
kills/first deaths, trade kills, headshot %, plants/defuses, plus
highlight stats --- **clutches** (1vX round wins), **multikills**, and
**aces** --- per player; attack/defense round-win % and pistol
conversion per team) feeds a league-leaders board, a team-tendencies
view, and **season awards** (MVP, Top Fragger, Opening King, Rookie, and
a team-level **Best Defensive Team**) handed out at season end. Every
highlight stat is derived purely from the match event log, so richer
stats never alter the match itself.

News isn't generic --- recaps are **templated and grounded**: every fact
in a recap sentence resolves to a real event in that match's log (a
`head_to_head` helper tracks in-season streaks, revenge results, and
"beat the reigning champions" storylines, and cites them only when
genuinely notable --- silence beats invented drama). A recap also names
the **winner's tactical identity** when a coaching dial is genuinely
extreme ("on the back of relentless aggression"). Phrasing is seeded per
event so the same result always reads the same way, but different
results read differently, in a dry, understated, no-hype voice (see
`docs/salvage/tone_and_cast_lock.md` for the style bible this follows).

### 3.11 Coaching & tactics

You don't just pick players --- you stamp an **identity** on the team
through `TeamTactics`: five numeric dials (each 0--100, **50 =
neutral**) plus a separate site-focus selector.

The five numeric dials:

-   **Aggression** --- swing/peek appetite, refrag spacing, forward vs
    anchored defensive setups, and how wide the team holds post-plant.
-   **Pace** --- execute-vs-default lean and go timing, whether a
    floundering hit is rammed through or aborted and re-defaulted, and
    defensive rotation tempo.
-   **Utility discipline** --- dump everything on the hit vs hold util
    for the retake, and whether players save a flash to pop on a swing.
-   **Eco greed** --- force-buy appetite; on save rounds, run-it-down vs
    play-for-picks; how aggressively defenders commit a retake.
-   **Map control** --- stack tight and hit as five vs spread for map
    presence and peel a **lurker** who baits at a flank, then strikes
    the site as a late second wave.

And, separately, **site focus** --- not a numeric dial but a string
selector (`balanced`, or a specific site) that biases which site the
attack picks. Its neutral state is `balanced` (no bias); it has no
0--100 / neutral-50 axis, so the numeric-dial rules below don't apply to
it in the same way.

Two factors decide how *well* a system is actually executed: **roster
fit** (does the attribute mix suit the dials --- aim for aggression,
game-sense and comms for map control) and **team chemistry**
(coordination-heavy systems like splits and disciplined retakes misfire
without cohesion). Fit is scored **per player** against a baseline, and
a player *below* the baseline is amplified before summing --- a teammate
who can't run the system drags harder than an equally-good fit lifts.
That's the deliberate design guard against "crank every dial": a couple
of stars can't average away the misfits, and a high-variance roster nets
*negative* at an extreme. The fit maths live in one module
(`sim/tactics_fit.py`) shared by the match engine and the web
serializer, so the "duel edge" the tactics screen previews is exactly
what the engine applies --- the UI only interpolates between
server-computed poles, holding no formula of its own (per-dial impact is
piecewise-linear with its knot at neutral 50, so two endpoints fully
describe it).

The AI is not frozen: each rival coach derives a season identity from
its roster and then **adapts it in-season** --- winners entrench their
identity, strugglers drift back toward vanilla, and pistol-round form
nudges their eco appetite --- so the league feels reactive over a
season.

**The load-bearing design rule:** every numeric dial's effect is an
*exact no-op at the neutral value 50* (and site focus is neutral at
`balanced`). A default team plays exactly like the pre-tactics engine,
so the coach's identity reaches all the way into round micro without
ever destabilising the balance or golden gates (which run neutral
tactics). This is what let the tactics system get deep in small,
low-risk increments; it's documented as
[ADR-007](docs/adr/ADR-007-neutral-safe-tactics.md).

------------------------------------------------------------------------

## 4. The match simulation

This is the part of the game the manager mostly *watches*, but it's
where almost all of the engineering lives, because it's the thing that
has to convincingly justify every result the management layer reports.

### 4.1 What a match is

A best-of-1 (or, in playoffs, one map of a BO3) plays out as **first to
13 rounds, halftime side swap at 12, overtime if tied 12--12** (win by
2, capped). Each round is simulated tick by tick (1 tick = 0.5
game-seconds) through: a buy phase, live round play, post-plant (if the
spike goes down), and round end. A full match resolves in roughly 50
milliseconds and produces a canonical, replayable event log.

### 4.2 The map: a floor plan, not just a graph

Under the hood, a map is a directed graph of named **callouts** ("A
Site", "Mid Courtyard", "B Long") with traversal edges and sightlines
--- this is the sim's *decision* vocabulary, and it's what keeps the
tactical AI and the eventual RL/world-model work legible (an agent
reasons in terms of "hold A short" or "rotate to B," not raw pixels).

But every callout also has a **physical room**: an axis-aligned rect on
a shared 0--100 grid, with:

-   **Corridors** --- explicit waypoint paths for connections whose
    rooms don't directly touch, so a rotate traces an actual hallway
    instead of teleporting.
-   **Props** --- half-height crates (cover: you can shoot over them,
    but they block shots from the far side) and full-height boxes (they
    break line-of-sight outright --- even between two players standing
    in the same room, like Ascent's mid box).
-   **Elevation** --- rooms like Haven's A-Heaven or Split's B-Rafters
    sit above the ground floor and grant a real high-ground bonus to
    anyone looking down into the site below.

Five maps currently exist, each individually hand-tuned: **Haven**
(3-site), **Ascent** (2-site, open mid), **Bind** (2-site, no mid ---
its identity is the direct site-to-site link, not verticality),
**Lotus** (3-site), **Split** (2-site, tall mid spine). Authoring a map
is a YAML content change (`data/maps/<id>.yaml` for the graph, plus
`data/maps/geometry/<id>.yaml` for the floor plan) validated by a test
suite that guarantees no movement clips through a wall and every room
sits where its callout anchor says it should.

**Map gimmicks** --- rotating doors (Lotus), teleporters (Bind), and
breakable doors that can start a round shut (Ascent) --- are a real
edge-level mechanic in the schema and engine, and are **authored onto
the live map data**: Bind's A-Short↔B-Window teleporter, Lotus's
rotating door into A, Ascent's breakable garden door. Every use is
*loud*, and enemies within a noise radius react (a watch direction snaps
toward the sound; a pre-plant defense can treat it as a rotation
trigger), which is also what makes faking a gimmick a legitimate read.
Teleporter travel is instantaneous --- the engine collapses the move to
its endpoints, so players beam rather than walk the gap (and the
floor-connection rule below exempts those edges).

**The floor contract:** paint, movement, and geometry are held to one
walkability rule, enforced by a permanent gate
(`scripts/map_floor_audit.py`): every adjacency pair's floor plates must
physically touch, every callout center must sit on its own plate, and
every path polyline must stay on the plate union. This is what
guarantees players in the viewer never walk across the painted void
between rooms.

### 4.3 Continuous movement

Players are not graph tokens --- every player holds a real `(x, y)`
position every tick. At round start, they don't stack on a room's
center; they take a **tactical slot**: a spot behind a specific crate
(cover), just inside a doorway (portal, for holding an angle out), or
one of several interior spread points, chosen deterministically
(hash-spread per player+room, so five teammates never pile onto the same
box). Movement between rooms follows a real path --- slot →
corridor/portal → slot --- at a speed scaled by the player's Movement
attribute, so a fast player's rotate is genuinely faster, not just
flavor text.

**Pacing is a designed, measured constant**, not an emergent accident:
an attacker rotating from one site's approach to another's, through
their own spawn, takes roughly 30 seconds --- matching real Valorant's
rhythm. A defender's equivalent rotate, through their own interior
lines, is always meaningfully faster than the attacker's version of the
same trip --- that speed gap *is* the defense's structural advantage for
having to guess which of several sites gets hit. Every map is measured
against this rule by an automated pacing report and re-tuned when it
drifts.

### 4.4 Duels

When two players from opposing teams have a mutual sightline, they may
engage. Whether they do, and who wins if they do, is a function of real
things:

-   **Range.** The fight happens at the actual distance between the two
    players' positions --- not an abstract "room A vs room B." Snipers
    want long sightlines and are penalized close up; SMGs and pistols
    are the reverse; rifles are flat everywhere.
-   **Cover & elevation.** A player tucked behind the right crate
    relative to the shooter gets a real bonus; the higher player across
    an elevation gap gets a real bonus.
-   **Line of sight.** A full-height prop between the two exact
    positions breaks the engagement outright, even mid-room.
-   **Facing.** Stationary players pre-aim toward the threat side. That
    bonus only pays out inside the cone they're actually watching --- a
    shot from outside it is a **flank**, and flanks are punished, not
    just ignored. Lurking through a cleared angle is a real, rewarded
    tactic now.
-   **Weapon, armor, agent mastery, map mastery**, and all ten player
    attributes (aim precision/reactivity, movement, positioning vs. game
    sense depending on who's holding vs. entering, clutch factor in 1vX,
    tilt resistance on a losing streak, composure).
-   **Day form** --- correlated per-match noise (a whole team can show
    up "hot" or "cold" for the match, scaled down by composure), which
    is why two matches between the same rosters produce genuinely
    different stories instead of the stronger side grinding out an
    identical win every time.

### 4.5 Micro-combat

Below the duel-resolution layer, individual fights have texture:

-   **Peeking** --- an aggressive player (entries, AWPers) on a
    stalemated angle will sometimes swing it deliberately, trading their
    holder status for initiative. Peeks fizzle (both sides bail) more
    often than a standard poke --- that's the "jiggle-peek" pattern ---
    and a peeker with a flash charge in reserve will sometimes pop it on
    the way in.
-   **Fizzled duels and post-kill repositioning** trigger real
    micro-movement: a player shuffles a few units to a nearby cover
    slot, emitted as an actual movement event, so a replay shows the
    footwork of a fight, not just its resolution.
-   **Utility** is individually attributed and consumed: smokes block
    sightlines for a window, flashes debuff whoever they catch, info
    abilities (recon darts, drones) can trigger an IGL to re-call a
    stacked site to the weaker one mid-approach, or let a defending
    initiator shave time off a rotation call once a round.

### 4.6 Economy, retakes, and saves

Valorant's real credit rules apply: pistol rounds, win/loss bonuses that
scale with consecutive losses, a plant bonus, an armor/weapon economy,
and force-buy/eco/full-buy decisions the (AI) IGL makes off the team's
average bank. Post-plant, defenders don't feed into a retake one at a
time --- outnumbered site defenders **fall back** instead of dying in
place (breaking contact with a brief disengage grace), rally with
rotating teammates, and either mount a **grouped retake** with real
numbers or **save** their weapons and concede the round if the situation
is hopeless. This asymmetric behavior --- not any symmetric tuning knob
--- is what finally got the attack/defense round-win balance into a
realistic band; the design history here is a genuine lesson (see §7).

### 4.7 Determinism

Every stochastic decision in the sim draws from a hierarchical RNG
(`rng/tree.py`) seeded by a label path ---
`(match, round, player, event)` --- derived via keyed hashing from a
single root seed. Two runs of the same match, same seed, produce a
**byte-identical event log**, guaranteed by a dedicated test
(`tests/test_determinism.py`) and reinforced by a **golden-file gate**:
a canonical match's log hash is committed to the repo, and any engine
change that alters it --- intentionally or not --- fails CI until the
fixture is deliberately re-blessed. This is the load-bearing
architectural bet: it's what makes replays trustworthy, what will make
an RL agent's or LLM's play reproducible for debugging, and what will
eventually make a world model trainable on logged play.

The golden gate has two fixtures --- a single canonical match and a
multi-seed `sweep_neutral` aggregate (every map × several seeds) that
catches drift the single match would miss. Both run **neutral tactics**,
so the coaching dials (§3.11) are held to a strict rule: every dial term
must be a no-op at 50, verified simply by the golden staying
byte-identical. The campaign is deterministic on the same terms --- same
seed → byte-identical `GameState` --- even though it never runs inside
the match gates. Balance, pacing, snowball, and tactics-sweep gates
round out the defence.

### 4.8 The event log is the only truth

Every kill, plant, defuse, buy, utility use, movement, round-start, and
match-end is a typed Pydantic event (`schemas/events.py`), appended to
an ordered, JSONL-persistable log. Nothing downstream --- the CLI
scoreboard, the web viewer, the season stats, the recap generator ---
holds independent state. They are all pure readers of the same log. This
is enforced as a standing architecture-review rule on every change to
the UI layer.

------------------------------------------------------------------------

## 5. Presentation

### 5.1 The web app

A FastAPI backend (`web/server.py`) exposes the same `GameState` the
terminal CLI drives, as JSON views (dashboard, roster, tactics,
standings, schedule, scouting, market, stats, finances, inbox, office)
and typed actions (train, sign, release, renew, talk, scout, sponsor
respond, hire/release staff, set tactics, advance week). The frontend is
a no-build-step vanilla-JS app on a custom design system
(`ui/design-system/` --- dark-first navy, information-dense, a Rajdhani
display face, a Valorant-red accent used sparingly with teal/amber
support colors).

Notable screens beyond the table-stakes tabs:

-   **Dashboard hub** --- next-match spotlight, stat tiles, recent-form
    squares, and "danger men" scouting callouts, so the week's decisions
    start from one screen.
-   **Inbox** --- a weekly digest of the most important events (results,
    transfer and sponsorship offers, player-conversation prompts, news),
    with unread tracking and **inline actions**: offers can be accepted
    or declined right from the message, and the action list is derived
    live from the current game state so a stale message can't fire a
    dead offer.
-   **Player & team profiles** --- click any player or team name
    anywhere in the app to open a profile overlay: attribute bars
    (scouting-fogged for rivals), weekly form sparklines, season stat
    charts, contract and chemistry context. Served by dedicated profile
    endpoints; the weekly series derive from stored fixture lines.
-   **Tactics** --- the coaching dials as bipolar two-tone sliders
    (named poles, neutral notch at 50, live descriptor that reads
    "Neutral" inside the engine's actual neutral band), roster chips
    showing which players suit each pole, a per-dial "±X.X duel" impact
    readout, and an execution edge banner --- all fed by server-computed
    fit (§3.11), never by formulas mirrored in JS.
-   **Office** --- a painted isometric office as the campaign's home
    screen: one AI-painted shell plus per-furniture transparent sprites
    composited and z-sorted at runtime (so furniture placement is data,
    not paint), with hotspots into the management screens and seated
    character sprites at the desks. Ambient audio (a main theme + office
    room tone) plays behind it.

### 5.2 The match viewer

Any played match can be replayed from a floor-plan **isometric** view
(with a 2D top-down toggle): real rooms, extruded walls, tinted sites,
corridor walkways, players walking their actual paths with motion
trails, kill markers, utility markers (color- and shape-coded by ability
type --- smoke, flash, damage, info, ultimate), gimmick markers with
tooltips (teleporter links, door states), a live agent-forward
kill/utility feed and lineup panel, the round clock (with a post-plant
amber state), and full playback control --- 1×/4×/16×/instant speed,
pause, scrub, round-skip. The isometric floor is an **AI-painted
backdrop** per map (see §5.3), pinned under the vector overlay at an
exact shared transform so hit positions, walkways, and paint never drift
apart; each map gets a tight per-map viewBox (crop-to-content) and the
viewer shell scales up to fill large monitors, so the map reads big
relative to the player icons. The viewer is a pure consumer of the event
log; it holds no simulation state of its own, and a legacy-log fallback
keeps older replays (pre-geometry, pre-continuous-movement) playable.
Replays are captured at sim time and kept for the latest week only ---
rosters mutate immediately after a week resolves, so an old seed
wouldn't reproduce its log.

### 5.3 Art

All art is AI-generated through a documented, gated pipeline
(`docs/art-pipeline.md`), committed once rather than generated on
demand. The core doctrine is **blockout→beautify**: structure comes from
a flat guide image rasterized from the actual plan/geometry data,
appearance comes from text prompts, and every generated scene is gated
against its guide with a footprint-IoU structure check before acceptance
--- so the art can never quietly disagree with the gameplay data
underneath it.

The committed pack:

-   **Identity art** --- a title splash, team logos, and role-based
    player portraits, assigned deterministically by entity-id hash so
    the same team or role always gets the same art; agent icons and
    painted map thumbnails for match UI.
-   **Map backdrops** --- five painted isometric floors (one per map)
    generated from geometry-derived guides, plus per-map style briefs
    researched from the real maps' visual identities. Guides, briefs,
    and winning prompts are kept in `assets/maps/` so a repaint is
    reproducible.
-   **The office** --- a sprite-decomposed scene: one furniture-free
    painted shell plus per-furniture-type transparent sprites (and
    seated-character variants), composited and z-sorted by the runtime
    from `office_plan.json`/`office_sprites.json`, so layout changes
    never require repainting.
-   **Audio** --- a looping main theme and office ambiance (Lyria).
-   **A trained style LoRA** --- `esports-sim-diorama` (Scenario, FLUX.2
    Dev) trained on the accepted diorama art, locking the style for
    future volume generation.

### 5.4 The terminal

The original interface --- a `rich`-based CLI (`app/cli.py`) --- remains
fully supported alongside the web app: `python -m esports_sim` for an
interactive session, or `--auto N --seed S --team T` for a fully
headless N-week run with no UI at all, which doubles as the sim's
load-bearing regression harness.

------------------------------------------------------------------------

## 6. Content roster (current)

  -----------------------------------------------------------------------
  Category                Count                   Examples
  ----------------------- ----------------------- -----------------------
  **Agents**              13                      Jett, Raze, Reyna,
                                                  Phoenix (duelists) ·
                                                  Omen, Viper, Clove
                                                  (controllers) · Sova,
                                                  Breach, Skye
                                                  (initiators) · Killjoy,
                                                  Cypher, Chamber
                                                  (sentinels)

  **Weapons**             7                       Classic, Ghost, Sheriff
                                                  (pistols) · Spectre
                                                  (SMG) · Phantom, Vandal
                                                  (rifles) · Operator
                                                  (sniper)

  **Maps**                5                       Haven, Ascent, Bind,
                                                  Lotus, Split --- each
                                                  with an authored
                                                  floor-plan geometry
                                                  layer

  **Attributes**          10                      Registry-driven; adding
                                                  an 11th is a data
                                                  change

  **Teams**               2 starter + generated   Team Nexus, Team
                          league                  Vanguard, plus a
                                                  deterministically
                                                  generated league fill
  -----------------------------------------------------------------------

All of the above are YAML under `data/`. The shipped default world is
original fictional content in a Valorant-flavored idiom --- no Riot
Games assets, no real player likenesses.

**Roster packs** (`data/rosters/<id>/`) --- importable league worlds. A
pack is a `pack.yaml` (name + world shape: which regions, how many teams
per league) plus team files in the exact starter-team bundle format; at
new-game it replaces the fictional starters, and generation only fills
any shortfall. Packs are built from compact hand-editable research
sheets by `scripts/build_roster_pack.py`, which expands each player
(handle, role, playstyle, quality, signature agents) into full
attributes deterministically (blake2-jittered per player id) --- so a
pack player has the same sheet in every campaign at any seed. One pack
ships: **VCT 2026** --- the real four-region VCT (48 partner orgs, real
mid-2026 starting fives, notable Challengers orgs underneath),
researched from vlr.gg/Liquipedia. Since this game is private (see §9),
real names here are a personal-use convenience, not published content.

------------------------------------------------------------------------

## 7. Design history worth knowing

A few hard-won lessons are encoded in the current tuning and worth
preserving so future work doesn't relearn them the expensive way:

-   **Symmetric knobs can't fix an asymmetric problem.** Early
    attack/defense balance sat 63--72% in attackers' favor. Every
    symmetric lever tried --- hold-advantage buffs, utility stalls,
    raising the pre-commit poke rate --- either didn't move it or made
    it *worse* (raising poke rate favors whichever side has more bodies
    to spend attacking a 5-vs-2 site, which is the attackers). The fix
    that actually worked was asymmetric: give outnumbered defenders a
    real fallback/retake/save behavior instead of feeding them into the
    crossfire one at a time. That dropped the range to a realistic
    45--65% band across all five maps.
-   **A single stronger-roster-always-wins simulation isn't "alive."**
    Correlated per-match "day form" noise (scaled down by composure) was
    necessary so that two matches between the same two rosters produce
    visibly different stories --- upsets happen, and they happen for a
    legible reason (a team ran cold, not a coin flip).
-   **Geometry choices are gameplay choices, not art choices.** Moving a
    room's center to make an isometric floor plan look better changes
    duel ranges and therefore changes who wins --- which is why any
    geometry edit drifts the golden-file fixture and has to be a
    deliberate, re-blessed decision, and why a dedicated pacing report
    (not eyeballing) gates rotation-timing changes.
-   **Multi-season play reveals different failure modes than one match
    does.** A league-balance overhaul (tracked via
    `scripts/snowball_report.py`) was needed after headless multi-season
    runs showed condition (form/ morale) snowballing into repeated
    13--0/13--1 blowouts that single-match testing never surfaced.
-   **An average can hide a broken roster.** The first roster-fit model
    for the coaching dials scored the roster *mean* against a baseline,
    which made every above-average squad's optimum "crank a dial to a
    pole" --- a free bonus, not an identity choice. Scoring per player
    and amplifying below-baseline misfits (so they drag harder than
    stars lift) restored the intended trade-off; league-wide the mean
    edge at full crank moved from +0.16 to \~0.00 duel points.
-   **Paint and geometry drift apart silently.** Players "walking on the
    background" traced to floor plates that never physically touched ---
    the sim pathed through gaps the paint never covered. The fix was a
    contract (plates touch, callouts on-plate, paths on the plate union)
    enforced by a permanent audit gate, plus the lesson that a
    footprint-IoU check alone can't detect *stale paint* after a
    localized geometry fix --- only a per-seam overlay read catches it.

------------------------------------------------------------------------

## 8. Roadmap (see `ROADMAP.md` for the living version)

**North-star bets** the whole project is aimed at:

1.  **Matches feel alive** --- different seeds, same rosters, visibly
    different legible stories. (Substantially proven out; ongoing
    tuning.)
2.  **An LLM can competently play a full season** through the headless
    state/action API --- the same contract the web UI and any future RL
    agent use. (API shape exists; a dedicated playtest harness is next.)
3.  **A world model can sample a plausible season** from event-sequence
    data --- the research capstone, gated on the first two bets holding
    up over real logged play.

**Shipped so far** (see `ROADMAP.md` changelog for exact commits): the
full match engine with the fallback/retake model; the full management
loop across multiple seasons (multi-region VCT, Challengers, Masters,
Champions); the web app with inbox, profiles, dashboard hub, and the
painted office home screen; the isometric viewer over painted map
backdrops; floor geometry with props, elevation, continuous movement,
and the floor-connection contract; map gimmicks authored onto Ascent,
Bind, and Lotus; micro-combat (peeks, flanks, footwork); rotation pacing
tuned to a real-feel \~30s rule; the neutral-safe coaching-dial system
with per-player roster fit; season analytics and grounded narrative;
scouting fog, map veto, staff, sponsorships, relationships, and the Talk
module; the art pipeline with a trained style LoRA.

**Next candidates** (unscheduled, in rough order of how they were left):
a headless LLM-playtest harness (north-star bet #2); camera follow/zoom
in the viewer; Scenario-API sampling of the trained LoRA (currently
web-UI only); development-milestone inbox items (needs prior-week state
tracking); animated office characters; an RL `env` wrapper over the same
headless contract (Track B); deepening personality/relationship systems
beyond the current tag-based model (Track A); and, eventually, the
event-sequence world-model research arm (Track C). None of this is
committed scope until it lands on the roadmap's Now/Next list --- this
section is a map of the terrain, not a promise.

------------------------------------------------------------------------

## 9. Explicit non-goals

-   ~~Real Valorant pro names or real statistical profiles~~ **Amended
    2026-07-09 (owner call):** the game is private --- for personal play
    with friends, not publication --- so an optional real-roster import
    now exists (the VCT 2026 roster pack, §6). The shipped *default*
    world remains fully fictional, attributes in packs are original
    estimates rather than scraped statistical profiles, and Riot Games
    assets stay excluded entirely. If this project were ever to be
    published, the packs go.
-   True 3D rendering --- the isometric floor-plan viewer is the
    intentional ceiling; it gets most of the tactical legibility of 3D
    without the engine-building cost.
-   Multiplayer/network play, a mobile port, a commercial Steam release,
    real-time voice comms, betting/fantasy mechanics, or scraping real
    Valorant API/Riot data. None of these serve the north-star bets
    above.

------------------------------------------------------------------------

# 10. Legacy Mode

**Status: SHIPPED (first cut) 2026-07-09** --- implemented as phases
P0-P5 on the chronicle-first architecture in
`docs/proposals/2026-07-09-new-systems-proposal.md`: the career
Chronicle, two game modes (sandbox = classic / legacy = career offers +
manager contracts + board dismissal + job market), derived manager
reputation, personality axes + player/org memories, rivalries, the Hall
of Fame, living-history callbacks, per-save media voices, the coaching
tree, earned philosophies, organizational knowledge (guarded by
`scripts/dynasty_report.py`), the expanded backroom department, and
strategy diffusion with chronicled meta eras. The section below is the
design it was built from.

## Vision

The campaign is not about winning a single tournament---it is about
building a career that leaves a permanent mark on the esport. The player
is managing a coach, organization, and long-term legacy rather than
simply optimizing a roster.

Legacy Mode sits above the existing season loop and transforms the
simulation into a decades-long narrative.

## Career Offers

Rather than selecting any organization freely, each new save begins with
several coaching offers that differ in:

-   Budget
-   Facilities
-   Staff quality
-   Fanbase
-   Academy strength
-   Board expectations
-   Job security
-   Regional reputation

Example archetypes include:

-   **Dynasty** -- Immediate championship expectations.
-   **Rebuilder** -- Limited resources but patience.
-   **Academy Specialist** -- Strong development infrastructure.
-   **Sleeping Giant** -- Historic organization needing revival.

Different starts should create fundamentally different stories rather
than simply different difficulty levels.

## Manager Reputation

Managers accumulate reputation based on historical decisions rather than
experience points.

Possible dimensions include:

-   Player Development
-   Tactical Innovation
-   Team Culture
-   Analytics
-   International Success
-   Pressure Handling

Organizations recruit based on these reputations.

## Career Profile

Rather than displaying only trophies, the game builds a complete
coaching biography.

Example career statistics:

-   Career Record
-   Championships
-   International Titles
-   Players Developed
-   Academy Promotions
-   Hall of Famers Coached

The game also generates "Known For" summaries from actual historical
behavior.

## Persistent Memory

### Player Memories

Players remember important events:

-   First professional opportunity
-   Public support
-   Benching
-   Championship runs
-   Contract disputes

Memories influence negotiations, morale, loyalty, and future reunions.

### Organization Memories

Organizations remember previous eras.

Examples include:

-   First international championship
-   Academy system built
-   Historic roster
-   Manager departure

Returning to a previous organization should feel meaningfully different.

## Coaching Tree

Former players may become:

-   Assistant Coaches
-   Head Coaches
-   Analysts
-   Scouts
-   General Managers

Coaching philosophies propagate across generations, allowing the player
to indirectly shape the esport.

## Philosophy System

Separate from tactical sliders, managers develop philosophical
identities.

Examples:

-   Trust Rookies
-   Veteran Leadership
-   Heavy Analytics
-   Creative Freedom
-   Strict Structure
-   Long Practice Weeks
-   Mental Wellness

Players and organizations respond to these identities.

## Living History

The simulation should remember historical events.

Examples:

-   Passing on a future superstar
-   Historic playoff collapses
-   Revenge matches
-   Redemption arcs

Historical callbacks appear naturally in media, commentary, and player
interactions years later.

## Social Media & Media Ecosystem

Replace isolated news stories with a persistent ecosystem containing:

-   News outlets
-   Social media
-   Podcasts
-   Rumors
-   Community discussion

Narratives evolve over many seasons instead of resetting every week.

## Hall of Fame

Track:

-   Managers
-   Players
-   Organizations
-   Dynasties
-   Rivalries
-   Historic Matches
-   Greatest Upsets
-   Greatest Teams

The Hall of Fame becomes the long-term history of the save.

## Rivalries

Persistent rivalries emerge automatically between:

-   Managers
-   Organizations
-   Players
-   Regions
-   Academies

Repeated encounters strengthen rivalries and influence fan engagement,
media attention, sponsorship value, and player motivation.

## Organizational Knowledge

Organizations accumulate institutional knowledge instead of only
accumulating player talent.

Knowledge includes:

-   Playbooks
-   Anti-strats
-   Utility combinations
-   Practice methodologies
-   Development systems
-   Analytical discoveries

Knowledge can be created, shared, transferred, forgotten, stolen through
staff departures, and become obsolete after balance patches.

This becomes one of the primary reasons dynasties emerge.

## Expanded Analytics Department

Expand the current Analyst role into an entire competitive intelligence
department including:

-   Replay Analysts
-   Data Scientists
-   Performance Coaches
-   Sports Psychologists
-   AI Systems Engineers

Departments generate actionable reports, identify weaknesses, discover
opponent tendencies, and improve organizational learning.

## Dynamic Meta

Strategies spread organically throughout the esport.

Successful approaches are copied.

Counter-strategies emerge.

Balance patches disrupt the ecosystem.

Every long-running save develops its own unique tactical history.

## Suggested Roadmap

### Track A --- Living World

-   Legacy Mode
-   Memories
-   Reputation
-   Rivalries
-   Hall of Fame
-   Social Media

### Track B --- Organizational Simulation

-   Organizational Knowledge
-   Expanded Staff
-   Analytics Department
-   Academy Development
-   Ownership Personalities

### Track C --- Competitive Evolution

-   Dynamic Meta
-   Strategy Diffusion
-   AI Coach Adaptation
-   Balance Patch Evolution
-   Long-term Esports History