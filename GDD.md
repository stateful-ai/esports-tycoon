Game Design Document --- ESports Simulator
Working title: ESports Simulator (repo: esports-tycoon) Genre: Esports management sim / tycoon, tick-level tactical shooter sim underneath Reference point: Esports Manager 2026 (Steam #2749950), Valorant (setting/flavor), Football Manager (management-depth ambition) Status: Playable, multi-season, browser + terminal. Actively in development. Last updated: 2026-07-18

This document holds design intent and the reasoning behind it. It describes shipped player-facing systems as of the date above; planned work belongs in ROADMAP.md. For the ordered weekly tick, every campaign system, and the module that owns each, see docs/game-systems.md, which is kept in sync with campaign.advance_week rather than with the design narrative.

1. Vision
You run a professional Valorant-flavored esports organization. You don't aim, peek, or spray --- your players do that, and how well they do it is a function of who you signed, how you trained them, how tired and happy they are, what utility they popped, and where they were standing when the fight started. Your job is everything around the ten minutes of a round: scouting and signing talent, building a training program, managing morale and burnout, calling in a coach, negotiating contracts, chasing sponsors, picking (and banning) maps, and reading the story the season tells through its results.

The foundational bet, stated plainly: a deterministic simulation can feel alive. Two matches between the same two rosters, seeded differently, should read as genuinely different stories --- not because the engine rolls noise on top of a fixed outcome, but because who was standing where, who peeked first, who popped a smoke a half-second late, and who was on a three-game losing streak all compound into a different match. Nothing in the sim is theater; every number the manager sees traces back to an event in the log, and every event traces back to a player attribute, a map feature, or a decision the manager made.

Design pillars
The sim is the truth, not a curtain. No hidden dice roll decides a match and then generates flavor text to match. Positions, ranges, cover, line-of-sight, and attributes produce the outcome; the outcome is what gets narrated.
Determinism is a feature, not an implementation detail. Same seed, same decisions → byte-identical replay, forever. This is what makes "why did we lose that round" answerable, what makes an LLM or an RL agent a viable player, and what will eventually make a world model trainable on real play data.
You manage humans, not spreadsheets. Morale, tilt, contract anxiety, and personality clashes are first-class systems, not flavor text bolted onto a stat block.
Depth without pixels. The tactical layer doesn't need a game engine to feel real --- a floor plan, real distances, cover, and elevation get you 90% of the tactical richness of a full 3D shooter at a fraction of the complexity, and it stays fast enough to sim a whole season in seconds.
Everything is data until proven otherwise. Agents, weapons, maps, and their floor geometry are YAML. A new agent or map is a content change, not a code change.
2. The core loop
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
Above this loop sits the season loop (regular season → playoffs → offseason → next season, indefinitely) and beneath it sits the match loop, which the manager mostly watches rather than plays --- an entire tactical shooter's worth of simulation resolves in milliseconds, then gets replayed at whatever pace the manager wants.

New careers have three deliberately distinct starts. Classic sandbox begins with authored or generated squads. Sandbox scenario starts reshape only the human club into an Insolvent Giant, Youth Project, Crisis Club, or Superteam Headache; each is deterministic and preserves the rest of the world. The optional sandbox Fantasy Draft begins with a short interview about manager identity, play style, region, comms, and preferred org life, then offers four contrasting jobs. After the player chooses, every tier-one team snake-drafts a ten-player squad from one shared pool before week 1. The interview gives the player's board preference real drafting teeth; it is not a cosmetic quiz. Legacy Mode is a separate career start governed by board offers rather than scenarios or the fantasy draft.

3. The management layer
3.1 Your organization
You pick one team from the league to manage. A club may carry up to ten players, while only a dressed five plays a map; the default lineup can be overridden per fixture/map and tournament registration can name a five- or six-player pool. Non-dressed players still scrim, develop more slowly, and eventually care about playing time. Your org also has a balance sheet, reputation, fan count, world rank, academy affiliation, facilities, staff, and team chemistry.

3.2 Players
Every player is a bundle of ten numeric attributes across five categories, scaled 1--99 (Football-Manager-style, not a 0--1 float, because humans read that scale better):

Category Attributes

Mechanical Aim Precision, Aim Reactivity, Movement Tactical Game Sense, Utility Usage, Positioning Mental Clutch Factor, Tilt Resistance, Composure Team Comms Quality

Attributes are a registry (data/attributes.yaml), not a hardcoded struct --- adding an eleventh attribute is a data change. On top of attributes, every player carries:

Role (Duelist / Controller / Initiator / Sentinel / Flex) and Playstyle (IGL, Entry, Anchor, Lurker, AWPer, Support) --- orthogonal axes that drive both squad-building decisions and in-match behavior.
Agent pool & map pool --- per-agent and per-map mastery, so a player's third-best agent is meaningfully worse than their main.
Career state --- salary, contract length, morale, stamina, form, age, and free-form personality tags (hot_head, veteran, rookie, star_player, volatile, ...) that modulate how they respond to talks, tilt, and pressure.
Condition --- morale, stamina, form, and confidence move week to week from training, match results, rest, sentiment, and staff support, and they feed back into match performance (a burnt-out star plays worse than their attributes suggest).
Relationships --- teammates carry a pairwise chemistry graph that drifts toward trait-driven affinities (kindred tags bond, clashing tags grate), is pushed by shared wins and losses, and outlives roster moves. Two players chasing the same spotlight role (two would-be entries/AWPers/IGLs) develop friction. Team chemistry chases the roster's mean relationship and feeds back into how well the team executes a coordinated system (§3.11).
Identity flavour --- generated players carry region-appropriate names (an EMEA player no longer reads as "Minho Nakamura"), languages, role-shaped attribute archetypes (entries out-aim, IGLs out-think), and deterministic personality axes behind the visible tags.
Development visibility --- public reports show current trend, outcome bands, role-fit projections, agent/map mastery growth, and meaningful milestones without exposing the hidden career curve or a false precise ceiling.
3.3 Training
Each week you set one focus --- mechanical, tactical, mental, team, or rest --- for the team and can set player development plans for the details. You can delegate the weekly choice to the coach. AI clubs use the same roster-aware picker. Growth follows age curves (young players improve faster, veterans decay), and rest recovers stamina at the cost of growth. A hired coach multiplies training gains. System fit matters too: a player whose playstyle suits the coach's tactics (see 3.11) gets more meaningful reps and develops faster; a mismatch develops slower. Match XP, bench scrims, mentorship, facilities, scouting guidance, language fit, and the wider environment feed this same development picture rather than creating disconnected upgrade systems.

3.4 Transfer market & contracts
A pool of free agents (deterministically generated, refreshed every offseason) is available to sign. Players ask for salaries scaled to their quality; signing, releasing (with a severance cost), renewing, bids, and buyouts are manager actions. Opening and mid-split transfer windows, roster locks, negotiation leverage, and deadlines make timing matter. Contracts run down week by week; a player inside ~8 weeks of free agency with good form will press you for a renewal conversation --- ignore it and morale suffers. AI teams work the same market against you --- and a premium free agent is contested: a rival org with a matching need may sign the best available FA out from under you, so a marquee grab isn't guaranteed.

3.5 Scouting
Rival rosters aren't shown at full fidelity --- attributes render with a noise band. Scouting is two persistent lanes rather than a single disposable assignment: the pro lane either auto-scouts the next opponent for match preparation or continually searches the market for a role/caliber gap; the amateur lane follows the academy/youth pool. Team playbook reads come quickly but decay when a balance patch changes the meta. Player reads deepen more slowly into tighter ranges and, at the highest analyst-supported tier, role-fit projections. The report resets or decays when its underlying world has changed.

3.6 Staff
Backroom staff are people rather than flat multipliers. Every member carries seven 1--99 attributes (expertise, tactical knowledge, analysis, teaching, people management, motivation, adaptability), a role-weighted overall, one or two mechanical traits, grounded career statistics, history, titles, and milestone badges. Badges are evidence of real accomplishments rather than another power stack. The shared deterministic market covers coaches, analysts, physios, psychologists, performance coaches, and language coaches; hiring replaces the incumbent in that chair and the outgoing member returns to the market.

Every tier-one club employs a concrete head coach. Coaches carry a preferred tactical identity across the five numeric tactics dials, and a server-computed system-fit score measures how well that identity matches the team's actual approach. Fit scales only the coach's contribution (training, preparation, and timeout advice), never supplies a raw always-on combat buff and never replaces roster fit. A compatible lower-overall coach can therefore be the better hire for a particular system. AI clubs use the same coach profiles for training, tactical adaptation, timeouts, and deterministic offseason replacement decisions; non-coach AI departments remain abstract for now.

3.7 The Talk module
Once a week you can sit down with one of your players. The topic isn't picked by the manager --- it's read off that player's actual state, in priority order: low morale → expiring contract → low stamina → poor form → a generic check-in if nothing's actually wrong. You pick one of three approaches (reassure / challenge / listen, or the topic-appropriate equivalent), and the outcome is modulated by that player's personality tags with a deterministic roll --- a hot_head bristles at being challenged more often than a calm veteran does. Effects are small on purpose: a talk is a nudge, not a lever you crank.

3.8 Finances
Weekly income (sponsorships scaled by reputation and fan count, plus prize money) sits against weekly expenses (payroll, staff, and facilities). Sponsorship deals arrive as time-limited offers --- upfront, steady, or performance-scaled payout structures --- and some carry live demands such as results, reach, or squad-building objectives. Those demands can be accepted, refused, or answered when they mature, so a deal is a management obligation rather than passive income. Insolvency bites: an org running a negative balance takes escalating reputation and squad-morale penalties and a board warning, with a harsher one past a debt floor. The Finances workspace projects a runway --- weeks until the balance would cross that floor at the current run rate.

3.9 Season structure
Three regional leagues of 8 (Americas / EMEA / Pacific) each run a double round-robin regular season (14 weeks), then a 4-team BO3 playoff bracket (1v4, 2v3) with map veto (mastery-driven ban/pick over the 5-map pool) down to a regional champion; the top teams advance to Masters (cross-region) and then Champions. The world shape is data, not code: a roster pack (§6) can reshape it to 3 or 4 regions of 4--16 teams --- with 4 regions, Masters becomes a full 8-side quarterfinal bracket (instead of 6 sides with two byes) and Champions fields the Masters eight. A per-region Challengers circuit develops prospects underneath. Standings break ties by wins → round differential → head-to-head (regular-season meetings only, so a playoff rematch never reorders the table) → rounds won → id. Then an offseason (aging, retirements, rookie classes, awards, free-agent refresh) before the next season. Campaigns run indefinitely --- there is no scripted ending.

3.10 Analytics & storylines
Season-long stat aggregation (K/D/A, an HLTV-flavored rating, first kills/first deaths, trade kills, headshot %, plants/defuses, plus highlight stats --- clutches (1vX round wins), multikills, and aces --- per player; attack/defense round-win % and pistol conversion per team) feeds league leaders, award races, team tendencies, map/agent meta, and season awards (MVP, Top Fragger, Opening King, Rookie, and a team-level Best Defensive Team). Analytics depth is intentionally gated by the analytics department, so investment expands what can be known without changing what happened. Every highlight stat is derived purely from the match event log, so richer stats never alter the match itself.

News isn't generic --- recaps are templated and grounded: every fact in a recap sentence resolves to a real event in that match's log (a head_to_head helper tracks in-season streaks, revenge results, and "beat the reigning champions" storylines, and cites them only when genuinely notable --- silence beats invented drama). A recap also names the winner's tactical identity when a coaching dial is genuinely extreme ("on the back of relentless aggression"). Phrasing is seeded per event so the same result always reads the same way, but different results read differently, in a dry, understated, no-hype voice (see docs/salvage/tone_and_cast_lock.md for the style bible this follows).

3.11 Coaching & tactics
You don't just pick players --- you stamp an identity on the team through TeamTactics: five numeric dials (each 0--100, 50 = neutral) plus a separate site-focus selector.

The five numeric dials:

Aggression --- swing/peek appetite, refrag spacing, forward vs anchored defensive setups, and how wide the team holds post-plant.
Pace --- execute-vs-default lean and go timing, whether a floundering hit is rammed through or aborted and re-defaulted, and defensive rotation tempo.
Utility discipline --- dump everything on the hit vs hold util for the retake, and whether players save a flash to pop on a swing.
Eco greed --- force-buy appetite; on save rounds, run-it-down vs play-for-picks; how aggressively defenders commit a retake.
Map control --- stack tight and hit as five vs spread for map presence and peel a lurker who baits at a flank, then strikes the site as a late second wave.
And, separately, site focus --- not a numeric dial but a string selector (balanced, or a specific site) that biases which site the attack picks. Its neutral state is balanced (no bias); it has no 0--100 / neutral-50 axis, so the numeric-dial rules below don't apply to it in the same way.

Two factors decide how well a system is actually executed: roster fit (does the attribute mix suit the dials --- aim for aggression, game-sense and comms for map control) and team chemistry (coordination-heavy systems like splits and disciplined retakes misfire without cohesion). Fit is scored per player against a baseline, and a player below the baseline is amplified before summing --- a teammate who can't run the system drags harder than an equally-good fit lifts. That's the deliberate design guard against "crank every dial": a couple of stars can't average away the misfits, and a high-variance roster nets negative at an extreme. The fit maths live in one module (sim/tactics_fit.py) shared by the match engine and the web serializer, so the "duel edge" the tactics screen previews is exactly what the engine applies --- the UI only interpolates between server-computed poles, holding no formula of its own (per-dial impact is piecewise-linear with its knot at neutral 50, so two endpoints fully describe it).

The AI is not frozen: each rival team derives a season identity from its roster and its concrete coach's preferred system, then adapts it in-season --- winners entrench their identity, strugglers drift toward what is working, adaptable coaches move more freely, and pistol-round form nudges eco appetite --- so coaching changes visibly alter how clubs play.

The load-bearing design rule: every numeric dial's effect is an exact no-op at the neutral value 50 (and site focus is neutral at balanced). A default team plays exactly like the pre-tactics engine, so the pre-match strategy identity can reach round micro without destabilising the balance or golden gates (which run neutral tactics). The live coach does not steer ticks: their only in-map input is a timeout, whose advice is consumed by the next team-policy plan. This is what lets tactics stay deep in small, low-risk increments; it's documented as ADR-007.

3.12 Squad, people, and the locker room
The Talk module (§3.7) is the oldest of a family of people systems that now surround it, all of them bounded nudges rather than levers:

Culture --- a captain and leadership council, an explicit team principle, and bounded relationship arcs. Culture sessions are a manager action; AI orgs manage their own. A public culture choice can become an identity-betrayal arc if repeated decisions contradict it.
Mentorship --- a manager-set mentor/protege pair raises the protege's ceiling on the mentor's best skills (a great aimer lifts a young player's aim ceiling), gated by the mentor's hidden mentor_skill. It moves the forecast, not the current ability.
Promises --- commitments made to a player (minutes, a signing, a role) that settle against what actually happened. Breaking one costs trust durably.
Transfer requests --- a benched player good enough to start elsewhere will ask out. Bench treatment is keyed off who actually dressed, so a per-map rotation counts as minutes.
Pep talks and shouts --- a pre-match team talk and in-series shouts, alongside the weekly 1:1.
Role fit --- assignment comfort and IGL experience accrue with reps, and accrue after the week's fixtures, so a last-minute switch is never fully comfortable on match day.
Academy --- tier-one parents sit over the real tier-two Challengers affiliates: intake, promotion and send-down, and minutes-based growth that reads the affiliate's actual results.
Player development is a forecast, not a cap: hidden deterministic career curves vary arrival time, volatility, peak duration, and decline, and a strong environment (mentorship, morale, confidence, cohesion) adds real headroom. Current ability can exceed the original potential forecast --- that records an outlier career rather than quietly rewriting the old forecast.

3.13 Organizational operations
Facilities --- six upgrade tracks (Training Centre, VOD Review Room, Media Department, Recovery Suite, Strategy Lab, Team House), each a menu-based card showing its staff operator, current benefit, next-level gain, build cost, and upkeep. Wellbeing benefits only pull players toward a neutral 50; they never inflate an already-healthy squad.
Preparation --- scrim and bootcamp plans that resolve before kickoff into grounded reports and organizational knowledge, paid for in physical load.
Series management --- tournament sixes and conditional between-map responses inside a BO3.
Delegation --- human staff policies over renewal, scouting, and training capacity. This is the deliberate pressure valve on a weekly action surface with many meaningful options: the manager chooses how much of it they personally own.
Media events --- rare contextual choices with persistent trust, sponsor, and sentiment consequences.
Social --- follower counts and a deterministic weekly feed; roster reach feeds sponsor marketability, and a per-team community sentiment chases weekly results and feeds back into confidence, morale, and sponsor pressure.
Badges --- grounded milestone and feat badges rolled from real box scores and development events, for players and staff alike. Evidence of accomplishment, not another power stack.

3.14 The weekly attention loop
The systems above are intentionally bounded --- a talk is a nudge, wellbeing pulls only toward neutral, mentorship moves a ceiling slowly. The design challenge is therefore not adding louder levers; it is making consequential calls visible, legible, and optional to own. The game now closes that loop with four connected surfaces: a leverage-ranked Actionable Items inbox distinct from lower-priority League Feed; Dashboard "Needs you" prompts and matching navigation badges; a decision ledger that settles recent human calls as paid off, neutral, or backfired from the actual subsequent state; and match review "Your calls" attribution for lineup, tactics, focus, talk, and preparation. Sim Ahead can advance up to four weeks under the manager's delegation settings and stops before a hard decision point. The aim is a campaign in which a manager can understand what mattered without turning every minor adjustment into a dashboard alarm.

4. The match simulation
This is the part of the game the manager mostly watches, but it's where almost all of the engineering lives, because it's the thing that has to convincingly justify every result the management layer reports.

4.1 What a match is
A best-of-1 (or, in playoffs, one map of a BO3) plays out as first to 13 rounds, halftime side swap at 12, overtime if tied 12--12 (win by 2, capped). Each round is simulated tick by tick (1 tick = 0.5 game-seconds) through: a buy phase, live round play, post-plant (if the spike goes down), and round end. A full match resolves well under a second and produces a canonical, replayable event log.

The match engine is a referee, not an invisible coach. Every available player receives a legal-action decision on every live tick; a team policy turns the five players' attributes and the standing strategy into the round plan (economy, site, pace, carrier, roles, defensive setup, and rotation holdback). Coaches are deliberately thin: one coach per side may call one timeout between rounds, and the resulting instruction only changes the next policy plan. It never becomes a direct aim, duel, or hidden combat modifier.

4.2 The map: a floor plan, not just a graph
Under the hood, a map is a directed graph of named callouts ("A Site", "Mid Courtyard", "B Long") with traversal edges and sightlines --- this is the sim's decision vocabulary, and it's what keeps the tactical AI and the eventual RL/world-model work legible (an agent reasons in terms of "hold A short" or "rotate to B," not raw pixels).

But every callout also has a physical room: an axis-aligned rect on a shared 0--100 grid, with:

Corridors --- explicit waypoint paths for connections whose rooms don't directly touch, so a rotate traces an actual hallway instead of teleporting.
Props --- half-height crates (cover: you can shoot over them, but they block shots from the far side) and full-height boxes (they break line-of-sight outright --- even between two players standing in the same room, like Ascent's mid box).
Elevation --- rooms like Haven's A-Heaven or Split's B-Rafters sit above the ground floor and grant a real high-ground bonus to anyone looking down into the site below.
Five maps currently exist, each individually hand-tuned: Haven (3-site), Ascent (2-site, open mid), Bind (2-site, no mid --- its identity is the direct site-to-site link, not verticality), Lotus (3-site), Split (2-site, tall mid spine). Authoring a map is a YAML content change (data/maps/<id>.yaml for the graph, plus data/maps/geometry/<id>.yaml for the floor plan) validated by a test suite that guarantees no movement clips through a wall and every room sits where its callout anchor says it should.

Map gimmicks --- rotating doors (Lotus), teleporters (Bind), and breakable doors that can start a round shut (Ascent) --- are a real edge-level mechanic in the schema and engine, and are authored onto the live map data: Bind's A-Short↔B-Window teleporter, Lotus's rotating door into A, Ascent's breakable garden door. Every use is loud, and enemies within a noise radius react (a watch direction snaps toward the sound; a pre-plant defense can treat it as a rotation trigger), which is also what makes faking a gimmick a legitimate read. Teleporter travel is instantaneous --- the engine collapses the move to its endpoints, so players beam rather than walk the gap (and the floor-connection rule below exempts those edges).

The floor contract: paint, movement, and geometry are held to one walkability rule, enforced by a permanent gate (scripts/map_floor_audit.py): every adjacency pair's floor plates must physically touch, every callout center must sit on its own plate, and every path polyline must stay on the plate union. This is what guarantees players in the viewer never walk across the painted void between rooms.

4.3 Continuous movement
Players are not graph tokens --- every player holds a real (x, y) position every tick. At round start, they don't stack on a room's center; they take a tactical slot: a spot behind a specific crate (cover), just inside a doorway (portal, for holding an angle out), or one of several interior spread points, chosen deterministically (hash-spread per player+room, so five teammates never pile onto the same box). Movement between rooms follows a real path --- slot → corridor/portal → slot --- at a speed scaled by the player's Movement attribute, so a fast player's rotate is genuinely faster, not just flavor text.

Pacing is a designed, measured constant, not an emergent accident: an attacker rotating from one site's approach to another's, through their own spawn, takes roughly 30 seconds --- matching real Valorant's rhythm. A defender's equivalent rotate, through their own interior lines, is always meaningfully faster than the attacker's version of the same trip --- that speed gap is the defense's structural advantage for having to guess which of several sites gets hit. Every map is measured against this rule by an automated pacing report and re-tuned when it drifts.

4.4 Duels
When two players from opposing teams have a mutual sightline, they may engage. Whether they do, and who wins if they do, is a function of real things:

Range. The fight happens at the actual distance between the two players' positions --- not an abstract "room A vs room B." Snipers want long sightlines and are penalized close up; SMGs and pistols are the reverse; rifles are flat everywhere.
Cover & elevation. A player tucked behind the right crate relative to the shooter gets a real bonus; the higher player across an elevation gap gets a real bonus.
Line of sight. A full-height prop between the two exact positions breaks the engagement outright, even mid-room.
Facing. Stationary players pre-aim toward the threat side. That bonus only pays out inside the cone they're actually watching --- a shot from outside it is a flank, and flanks are punished, not just ignored. Lurking through a cleared angle is a real, rewarded tactic now.
Weapon, armor, agent mastery, map mastery, and all ten player attributes (aim precision/reactivity, movement, positioning vs. game sense depending on who's holding vs. entering, clutch factor in 1vX, tilt resistance on a losing streak, composure).
Day form --- correlated per-match noise (a whole team can show up "hot" or "cold" for the match, scaled down by composure), which is why two matches between the same rosters produce genuinely different stories instead of the stronger side grinding out an identical win every time.
4.5 Micro-combat
Below the duel-resolution layer, individual fights have texture:

Peeking --- an aggressive player (entries, AWPers) on a stalemated angle will sometimes swing it deliberately, trading their holder status for initiative. Peeks fizzle (both sides bail) more often than a standard poke --- that's the "jiggle-peek" pattern --- and a peeker with a flash charge in reserve will sometimes pop it on the way in.
Fizzled duels and post-kill repositioning trigger real micro-movement: a player shuffles a few units to a nearby cover slot, emitted as an actual movement event, so a replay shows the footwork of a fight, not just its resolution.
Utility is individually attributed, context-selected, and consumed: each player uses the charged ability that fits an execute, stall, or retake rather than a generic kit-power button. Smokes and flashes are targeted at one called site (a smoke cannot erase angles across the map; an unused flash expires instead of catching a later rotate), while mobility abilities such as dashes and blast packs shorten the actual move they open. Info abilities (recon darts, drones) can trigger an IGL to re-call a stacked site to the weaker one mid-approach, or let a defending initiator shave time off a rotation call once a round.
4.6 Economy, retakes, and saves
Valorant's real credit rules apply: pistol rounds, win/loss bonuses that scale with consecutive losses, a plant bonus, an armor/weapon economy, and force-buy/eco/full-buy decisions the (AI) IGL makes off the team's average bank. Post-plant, defenders don't feed into a retake one at a time --- outnumbered site defenders fall back instead of dying in place (breaking contact with a brief disengage grace), rally with rotating teammates, and either mount a grouped retake with real numbers or save their weapons and concede the round if the situation is hopeless. This asymmetric behavior --- not any symmetric tuning knob --- is what finally got the attack/defense round-win balance into a realistic band; the design history here is a genuine lesson (see §7).

4.7 Determinism
Every stochastic decision in the sim draws from a hierarchical RNG (rng/tree.py) seeded by a label path --- (match, round, player, event) --- derived via keyed hashing from a single root seed. Two runs of the same match, same seed, produce a byte-identical event log, guaranteed by a dedicated test (tests/test_determinism.py) and reinforced by a golden-file gate: a canonical match's log hash is committed to the repo, and any engine change that alters it --- intentionally or not --- fails CI until the fixture is deliberately re-blessed. This is the load-bearing architectural bet: it's what makes replays trustworthy, what will make an RL agent's or LLM's play reproducible for debugging, and what will eventually make a world model trainable on logged play.

The golden gate has two fixtures --- a single canonical match and a multi-seed sweep_neutral aggregate (every map × several seeds) that catches drift the single match would miss. Both run neutral tactics, so the coaching dials (§3.11) are held to a strict rule: every dial term must be a no-op at 50, verified simply by the golden staying byte-identical. The campaign is deterministic on the same terms --- same seed → byte-identical GameState --- even though it never runs inside the match gates. Balance, pacing, snowball, and tactics-sweep gates round out the defence.

4.8 The event log is the only truth
Every kill, plant, defuse, buy, utility use, movement, round-start, and match-end is a typed Pydantic event (schemas/events.py), appended to an ordered, JSONL-persistable log. Nothing downstream --- the CLI scoreboard, the web viewer, the season stats, the recap generator --- holds independent state. They are all pure readers of the same log. This is enforced as a standing architecture-review rule on every change to the UI layer.

5. Presentation
5.1 The web app
A FastAPI backend (web/server.py) exposes the same GameState the terminal CLI drives, as JSON views and typed, validated actions. The frontend is a no-build-step vanilla-JS app on a custom dark-first design system: navy surfaces, information-dense hierarchy, Rajdhani display type, and restrained red/teal/amber accents. It is a pure GameState/event-log consumer; calculations and privacy gates stay server-side.

Notable screens beyond the table-stakes tabs:

Navigation --- the top level is Dashboard, Inbox, Match, Club, Facilities, Season, Market, Stats, and Company. Match is the single home for tactics, game plans, opponent prep, tournament sixes, and series instructions. Club groups Squad, Development, Locker Room, and Operations; Season groups league, fixtures, playoffs, and records; Market groups Players, Scouting, and Staff; Company groups Finances and Brand. Legacy deep links route into the appropriate workspace rather than creating duplicate screens.
Dashboard hub --- a tightly limited weekly read: next-match spotlight, core stat tiles, form, headlines, and only the highest-leverage "Needs you" calls. A staged advance reveal and match-day briefing make the immediate decision context clear without making the dashboard a second management screen.
Inbox --- a weekly digest split into Actionable Items and League Feed, with unread tracking and inline actions. Offers can be accepted or declined right from the message, and the action list is derived live from the current game state so a stale message cannot fire a dead offer. The primary badge tracks actionable work, not generic results.
Player & team profiles --- click any player or team name anywhere in the app to open a profile overlay: attribute bars (scouting-fogged for rivals), weekly form sparklines, season stat charts, contract and chemistry context. Served by dedicated profile endpoints; the weekly series derive from stored fixture lines.
Tactics --- the Match workspace presents coaching dials as bipolar two-tone sliders (named poles, neutral notch at 50, live descriptor that reads "Neutral" inside the engine's actual neutral band), roster chips showing which players suit each pole, a per-dial impact readout, and an execution edge banner --- all fed by server-computed fit (§3.11), never by formulas mirrored in JS.
Facilities --- a menu-based infrastructure screen with six upgrade tracks: Training Centre, VOD Review Room, Media Department, Recovery Suite, Strategy Lab, and Team House. Each department card shows its assigned staff member, current benefits, next-level gains, build cost, and weekly upkeep, and lets the manager fund the upgrade in place. The tracks affect distinct parts of the management loop: player development, Analyst scouting and reporting, sponsor value and access, weekly condition recovery, preparation learning and physical load, and bounded confidence/morale recovery. Wellbeing benefits only pull players toward a neutral 50 rather than inflating an already healthy squad. The painted isometric office remains parked for a later interaction pass rather than being used as the upgrade interface.
5.2 The match viewer
Any played match can be replayed from a floor-plan isometric view (with a 2D top-down toggle): real rooms, extruded walls, tinted sites, corridor walkways, players walking their actual paths with motion trails, kill markers, utility markers (color- and shape-coded by ability type --- smoke, flash, damage, info, ultimate), gimmick markers with tooltips (teleporter links, door states), a live agent-forward kill/utility feed and lineup panel, the round clock (with a post-plant amber state), and full playback control --- 1×/4×/16×/instant speed, pause, scrub, round-skip. The viewer also has a spectator camera: mouse pan/zoom, player follow, and an optional event-follow action camera, plus synthesized event cues that sit beside the separate ambient music. The isometric floor is an AI-painted backdrop per map (see §5.3), pinned under the vector overlay at an exact shared transform so hit positions, walkways, and paint never drift apart; each map gets a tight per-map viewBox (crop-to-content) and the viewer shell scales up to fill large monitors, so the map reads big relative to the player icons. The viewer is a pure consumer of the event log; it holds no simulation state of its own, and a legacy-log fallback keeps older replays (pre-geometry, pre-continuous-movement) playable. Replays are captured at sim time and kept for the latest week only --- rosters mutate immediately after a week resolves, so an old seed wouldn't reproduce its log.

5.3 Art
All art is AI-generated through a documented, gated pipeline (docs/art-pipeline.md), committed once rather than generated on demand. The core doctrine is blockout→beautify: structure comes from a flat guide image rasterized from the actual plan/geometry data, appearance comes from text prompts, and every generated scene is gated against its guide with a footprint-IoU structure check before acceptance --- so the art can never quietly disagree with the gameplay data underneath it.

The committed pack:

Identity art --- a title splash, team logos, and role-based player portraits, assigned deterministically by entity-id hash so the same team or role always gets the same art; agent icons and painted map thumbnails for match UI.
Map backdrops --- five painted isometric floors (one per map) generated from geometry-derived guides, plus per-map style briefs researched from the real maps' visual identities. Guides, briefs, and winning prompts are kept in assets/maps/ so a repaint is reproducible.
The office --- a sprite-decomposed scene: one furniture-free painted shell plus per-furniture-type transparent sprites (and seated-character variants), composited and z-sorted from office_plan.json/office_sprites.json. This art pack is currently parked; the live facility-upgrade interface is menu-based.
Audio --- a looping main theme and office ambiance (Lyria).
A trained style LoRA --- esports-sim-diorama (Scenario, FLUX.2 Dev) trained on the accepted diorama art, locking the style for future volume generation.
5.4 The terminal
The original interface --- a rich-based CLI (app/cli.py) --- remains fully supported alongside the web app: python -m esports_sim for an interactive session, or --auto N --seed S --team T for a fully headless N-week run with no UI at all, which doubles as the sim's load-bearing regression harness.

6. Content roster (current)
Category Count Examples

Agents 13 Jett, Raze, Reyna, Phoenix (duelists) · Omen, Viper, Clove (controllers) · Sova, Breach, Skye (initiators) · Killjoy, Cypher, Chamber (sentinels)

Weapons 7 Classic, Ghost, Sheriff (pistols) · Spectre (SMG) · Phantom, Vandal (rifles) · Operator (sniper)

Maps 5 Haven, Ascent, Bind, Lotus, Split --- each with an authored floor-plan geometry layer

Attributes 10 Registry-driven; adding an 11th is a data change

Teams Fictional default world plus deterministic league fill; roster packs can replace the world shape and clubs
All of the above are YAML under data/. The shipped default world is original fictional content in a Valorant-flavored idiom --- no Riot Games assets, no real player likenesses.

Roster packs (data/rosters/<id>/) --- importable league worlds. A pack is a pack.yaml (name + world shape: which regions, how many teams per league) plus team files in the exact starter-team bundle format; at new-game it replaces the fictional starters, and generation only fills any shortfall. Packs are built from compact hand-editable research sheets by scripts/build_roster_pack.py, which expands each player (handle, role, playstyle, quality, signature agents) into full attributes deterministically (blake2-jittered per player id) --- so a pack player has the same sheet in every campaign at any seed. Two historical packs ship: VCT 2021 and VCT 2026. Since this game is private (see §9), real names are a personal-use convenience, attributes remain original estimates rather than scraped statistics, and no Riot assets are included.

7. Design history worth knowing
A few hard-won lessons are encoded in the current tuning and worth preserving so future work doesn't relearn them the expensive way:

Symmetric knobs can't fix an asymmetric problem. Early attack/defense balance sat 63--72% in attackers' favor. Every symmetric lever tried --- hold-advantage buffs, utility stalls, raising the pre-commit poke rate --- either didn't move it or made it worse (raising poke rate favors whichever side has more bodies to spend attacking a 5-vs-2 site, which is the attackers). The fix that actually worked was asymmetric: give outnumbered defenders a real fallback/retake/save behavior instead of feeding them into the crossfire one at a time. That dropped the range to a realistic 45--65% band across all five maps.
A single stronger-roster-always-wins simulation isn't "alive." Correlated per-match "day form" noise (scaled down by composure) was necessary so that two matches between the same two rosters produce visibly different stories --- upsets happen, and they happen for a legible reason (a team ran cold, not a coin flip).
Geometry choices are gameplay choices, not art choices. Moving a room's center to make an isometric floor plan look better changes duel ranges and therefore changes who wins --- which is why any geometry edit drifts the golden-file fixture and has to be a deliberate, re-blessed decision, and why a dedicated pacing report (not eyeballing) gates rotation-timing changes.
Multi-season play reveals different failure modes than one match does. A league-balance overhaul (tracked via scripts/snowball_report.py) was needed after headless multi-season runs showed condition (form/ morale) snowballing into repeated 13--0/13--1 blowouts that single-match testing never surfaced.
An average can hide a broken roster. The first roster-fit model for the coaching dials scored the roster mean against a baseline, which made every above-average squad's optimum "crank a dial to a pole" --- a free bonus, not an identity choice. Scoring per player and amplifying below-baseline misfits (so they drag harder than stars lift) restored the intended trade-off; league-wide the mean edge at full crank moved from +0.16 to ~0.00 duel points.
Paint and geometry drift apart silently. Players "walking on the background" traced to floor plates that never physically touched --- the sim pathed through gaps the paint never covered. The fix was a contract (plates touch, callouts on-plate, paths on the plate union) enforced by a permanent audit gate, plus the lesson that a footprint-IoU check alone can't detect stale paint after a localized geometry fix --- only a per-seam overlay read catches it.
8. Research direction (see ROADMAP.md for the living roadmap)
The three north-star bets remain: matches should create varied but legible stories; an external manager should be able to operate a full season through the same public decision contract; and eventually a model should be able to generate plausible campaign history from the resulting data.

The enabling substrate is shipped. Every human decision is recorded in an append-only action log; seed plus that log reproduces a career. Weekly manager-visible feature snapshots and shared reward components export into RL episodes, while a pinned match-token vocabulary can dump training corpora. The deterministic headless manager environment exposes only manager-visible observations and legal-action masks. It supports a masked heuristic manager baseline, generated policy profiles, reproducible rollouts, a dependency-light learned imitation checkpoint, and champion/challenger online improvement guarded by disjoint seeds, legality, reward, balance, wins, and profile-distinctness checks. Player policies use the same discipline: fog-safe typed observations and engine-supplied legal actions.

The LLM manager playtest harness is also shipped: it gives an LLM the state and legal choices, advances the campaign through the shared environment, and writes a grounded season critique. The remaining research work is quality and scale rather than an absent API: evaluate how well external managers handle the growing campaign surface, refine the promotion gates, and then attempt season-level tokenization and conditional world-model experiments. Separate presentation work (for example, richer generated art or animated office life) is deliberately not allowed to change deterministic save state.

9. Explicit non-goals
Real Valorant pro names or real statistical profiles Amended 2026-07-09 (owner call): the game is private --- for personal play with friends, not publication --- so an optional real-roster import now exists (the VCT 2026 roster pack, §6). The shipped default world remains fully fictional, attributes in packs are original estimates rather than scraped statistical profiles, and Riot Games assets stay excluded entirely. If this project were ever to be published, the packs go.
True 3D rendering --- the isometric floor-plan viewer is the intentional ceiling; it gets most of the tactical legibility of 3D without the engine-building cost.
Multiplayer/network play, a mobile port, a commercial Steam release, real-time voice comms, esports betting, or scraping real Valorant API/Riot data. The optional Fantasy Draft is an internal campaign start, not a betting or spectator-fantasy product. None of these serve the north-star bets above.
10. Legacy Mode
Legacy Mode is shipped. It sits above the season loop and turns a club save into a long-running manager career: the manager has a seat, contract, board goal, patience, dismissal risk, and a job market. Sandbox remains the classic pick-any-club experience; its manager seat does not carry a contract or dismissal risk. Legacy careers begin from deterministic board offers rather than the sandbox scenario or Fantasy Draft starts.

Career Offers
Each Legacy save begins with several coaching offers that differ in:

Budget
Facilities
Staff quality
Fanbase
Academy strength
Board expectations
Job security
Regional reputation
The active offer archetypes are:

Dynasty -- Immediate championship expectations.
Rebuilder -- Limited resources but patience.
Academy Specialist -- Strong development infrastructure.
Sleeping Giant -- Historic organization needing revival.
The offers create different careers rather than simple difficulty settings. Board reviews use the contract goal and club situation; a dismissed manager must accept a new job before the world can advance.

Manager Reputation
Manager reputation is derived from the append-only Chronicle rather than awarded as experience points. The public career profile summarizes actual historical behavior across dimensions including:

Player Development
Tactical Innovation
Team Culture
Analytics
International Success
Pressure Handling
Organizations recruit against those Chronicle-derived reads. The game never stores a loose reputation number that could drift from the events that earned it.

Player Potential and Career Curves

Potential is a forecast of upside, not a hard attribute cap. Historical roster packs can author the expected center of a real player's career plus a 0-100 volatility envelope. A new campaign samples future potential and curve shape inside that envelope while leaving opening skill intact: proven greats stay relatively consistent across saves, while uncertain or boom-bust players can take wider alternate careers.

Young players
carry hidden, deterministic career curves which vary in arrival time,
development volatility, peak duration, decline timing, and how much of their
upside they naturally realize. This keeps a broad population of plausible
stars without guaranteeing that every high-potential prospect becomes one.

Scouting reports show outcome bands and qualitative curve clues, never an
exact maximum. Strong environments can change the outcome: mentorship, close
duos, morale, confidence, and locker-room cohesion add development headroom.
In exceptional cases Current Ability can exceed the original potential
forecast, recording an outlier career rather than silently raising the old
forecast to match it.

Career profile and memory
The Chronicle is the long-term history of the save: titles, awards, moves, debuts, milestones, manager changes, and meta eras are append-only career events. Career profile, manager reputation, philosophies, living-history callbacks, and "Known For" reads are derived from that record instead of being a parallel narrative database. Player and board memories add bounded loyalty and reunion/board-posture nudges; they do not override the event history that explains them.

Legacy world systems
Retiring players can deterministically enter the staff market, creating a coaching tree. The Hall of Fame records retirement induction as the one stored historical view. Rivalries grow out of playoff meetings and poaches, then cool in the offseason. Named rival managers give AI-run tier-one clubs persistent human faces, tenure, board reviews, and Chronicle-visible career moves without granting hidden match modifiers.

Organizational knowledge and meta
Organizations accumulate playbooks, anti-strats, and methodology. Knowledge can feed preparation only through a set game plan, leaks with staff moves, and dates when a balance patch changes the relevant landscape; this prevents it from becoming an invisible permanent combat bonus. Twice each season, usage-driven agent buffs and nerfs create a save-specific patch history. Rival teams adapt their tactical identities, struggling clubs can copy a successful meta, and season-end meta eras are chronicled. The dynasty gate remains the guardrail: accumulated history may create an advantage, but never an unbreakable league.

Media and history
The weekly social feed, grounded recaps, Chronicle, profiles, badges, and career movement feed form the persistent media layer. Serve-time LLM rewrites may improve social, 1:1, or flavor copy, but the deterministic fact record remains in the save and the model is not permitted to invent events. The result is a world that remembers a player, manager, club, or strategy because the simulation recorded what they did.
