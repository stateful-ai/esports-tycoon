"""Match-engine tuning constants.

Everything gameplay-feel lives here so balance passes are config edits, not
code archaeology. Time unit: 1 tick = 0.5 s.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Timing (ticks; 1 tick = 0.5 s)

ROUND_TICKS = 200  # 100 s round timer
SPIKE_TICKS = 90  # 45 s from plant to detonation
PLANT_TICKS = 8  # 4 s plant channel
DEFUSE_TICKS = 14  # 7 s full defuse
HALF_DEFUSE_TICKS = 7  # progress checkpoint
MOVE_TICKS_PER_EDGE = 6  # legacy fallback pacing (no-geometry maps)

# Continuous movement: players hold real positions and travel at speed.
# 2.5 grid units/tick keeps a typical door-to-door hop brisk without
# compressing the pacing gate's 8-18s staging and 25-35s long rotates.
PLAYER_SPEED = 2.5  # grid units per tick at movement=50
MIN_MOVE_TICKS = 2
# Walking is deliberately slower than the route's normal run cadence. Noise
# propagation will consume this same authored pace in the next interaction
# pass; keeping it explicit now avoids encoding pace in raw coordinate deltas.
MOTOR_WALK_SPEED_MULT = 0.55
MOTOR_TURN_CANDIDATES = (-45.0, -15.0, -5.0, 0.0, 5.0, 15.0, 45.0)
# Free-roam collision uses a small player hull and sub-steps so a fast player
# cannot tunnel through a narrow traced doorway or prop between ticks.
FREE_MOVE_PLAYER_RADIUS = 0.35
FREE_MOVE_COLLISION_STEP = 0.20
# Running advertises a coarse location to nearby enemy observations; walking
# deliberately produces no footstep readout in this first motor pass.
RUN_FOOTSTEP_RADIUS = 24.0
RUN_FOOTSTEP_MIN_CONFIDENCE = 0.55
RUN_FOOTSTEP_MAX_CONFIDENCE = 0.85
# Positional cover: a stationary holder hugging a crate that sits between
# them and the shooter is simply harder to kill.
COVER_BONUS = 4.0

# ---------------------------------------------------------------------------
# Micro combat

# Watch directions: a stationary player is pre-aimed toward what they're
# watching (usually the enemy-spawn side). The holder bonus only pays out
# when the threat comes from that cone; a shot from behind is a flank.
PREAIM_FACING_COS = 0.4  # cos threshold: inside the watched cone
FLANK_FACING_COS = -0.2  # behind this: caught from the back
FLANK_MALUS = 8.0

# Peeking: an aggressive player on a stalemated angle briefly swings it.
# The peeker trades their holder status for initiative, and bails out of
# losing fights more often (jiggle bait).
PEEK_PROB = 0.02  # per tick baseline; playstyle/reactivity add to it
PEEK_PROB_AGGRO = 0.03  # extra for entry/awper playstyles
PEEK_PROB_CAP = 0.25
PEEK_AGGRESSION_DIV = 166.0
PEEK_TIMEOUT_PRESSURE_MULT = 1.35
PEEK_TIMEOUT_STABILIZE_MULT = 0.75
PEEK_ROLE_MULTIPLIERS = {
    "entry": 1.35,
    "lurker": 1.12,
    "flex": 1.0,
    "support": 0.88,
    "holder": 0.84,
    "anchor": 0.82,
    "carrier": 0.72,
}
PEEK_POSTPLANT_ATTACK_MULT = 0.78
PEEK_RETAKE_DEFENSE_MULT = 1.25
PEEK_LOW_NUMBERS_MULT = 0.84
PEEK_LATE_ATTACK_MULT = 1.30
PEEK_LATE_ATTACK_TICK = 140
PEEK_INITIATIVE = 5.0
PEEK_FIZZLE_MULT = 2.0
PEEK_FLASH_PROB = 0.5  # chance a peeker with a flash charge pops it

# Micro-repositioning: after a fizzled duel (and often after a kill) the
# survivor shifts a few units — to cover when there is some.
MICRO_MOVE_RADIUS = 7.0
MICRO_MOVE_MIN = 2.0
KILLER_REPOSITION_PROB = 0.5

# Rotation info: an initiator burns an info charge to call the hit early.
INFO_ROTATE_BONUS = 4  # ticks shaved off every rotator's delay

# ---------------------------------------------------------------------------
# Micro texture: whiffed utility and comms quality

# Chance a thrown basic ability just misses its lineup (scaled by the
# thrower's utility_usage — a 55 thrower whiffs ~5%, a 30 thrower ~15%).
UTIL_FAIL_BASE = 0.05
UTIL_FAIL_MAX = 0.30
# Team comms on rotations: below the threshold, calls can cross and the
# whole rotation stalls; above the high bar, the call is clean (flavor).
MISCOMM_COMMS_THRESHOLD = 62.0
MISCOMM_MAX_PROB = 0.35
MISCOMM_DELAY = 5  # extra ticks on every rotator when comms cross
CALL_COMMS_THRESHOLD = 72.0

# Learned-policy communication channel and receiver memory. The policy chooses
# whether to speak; these bounds determine how faithfully the claim arrives
# and how long each teammate retains it.
COMMS_SPEAK_BASE = 0.42
COMMS_SPEAK_QUALITY_DIV = 175.0
COMMS_SPEAK_MIN = 0.42
COMMS_SPEAK_MAX = 0.97
COMMS_TRANSMIT_BASE = 0.55
COMMS_TRANSMIT_QUALITY_DIV = 220.0
COMMS_TRANSMIT_MAX = 0.995
COMMS_CORRUPT_THRESHOLD = 72.0
COMMS_CORRUPT_DIV = 150.0
COMMS_CORRUPT_MAX = 0.42
COMMS_CORRUPT_FORGET_ENEMY_PROB = 0.35
COMMS_CORRUPT_OVERCONFIDENCE = 0.18
COMMS_DELAY_QUALITY_DIV = 18.0
COMMS_MAX_VISIBLE_BELIEFS = 12
COMMS_LOCATION_HALF_LIFE = 36.0
COMMS_INTENT_HALF_LIFE = 24.0
COMMS_OBJECTIVE_HALF_LIFE = 90.0
COMMS_TEAM_INTENT_HALF_LIFE = 45.0
COMMS_RECALL_BASE = 0.65
COMMS_RECALL_QUALITY_DIV = 285.0
COMMS_FORGET_CONFIDENCE = 0.08
COMMS_MISREMEMBER_THRESHOLD = 68.0
COMMS_MISREMEMBER_DIV = 155.0
COMMS_MISREMEMBER_AGE_DIV = 900.0
COMMS_MISREMEMBER_MAX = 0.45
COMMS_MISREMEMBER_LOCATION_PROB = 0.55
COMMS_MISREMEMBER_CONFIDENCE_MULT = 0.82
PRIVATE_ENEMY_MEMORY_HALF_LIFE = 42.0
PRIVATE_ENEMY_FORGET_CONFIDENCE = 0.08

# ---------------------------------------------------------------------------
# Map gimmicks (rotating doors, teleporters, breakable doors)

TELEPORT_TICKS = 3  # in-transit time; no fighting mid-teleport
ROTATING_DOOR_DELAY = 2  # extra ticks to swing a shut door through
DOOR_BREAK_TICKS = 8  # shooting a shut door open (4 s, very loud)
# Doors are switch-operated: breakables start OPEN and get shut by a
# nearby player mid-round (the per-door setup inclination lives in map
# data as `start_closed_prob`); rotating stone doors reset shut every
# round. Post-plant, whichever side holds the site may slam an adjacent
# door to cut the retake/entry path.
DOOR_SETUP_CLOSE_TICKS = 24  # defender setup window for shutting doors (12 s)
DOOR_POSTPLANT_CLOSE_PROB = 0.6  # site holders cutting a path post-plant
# Every gimmick use is loud. Enemies inside the noise radius snap their
# watch toward it, and pre-plant defenders treat sound near a site as a
# rotation trigger — which is also exactly why fakes work.

# Default-strat attackers commit somewhere in this window (uniform draw).
DEFAULT_GO_EARLIEST = 75
DEFAULT_GO_LATEST = 115
# Execute-strat attackers commit as soon as everyone is staged, but not
# before this tick (utility setup time).
EXECUTE_GO_EARLIEST = 24
# If nothing has happened by here, force the hit regardless of strat.
FORCE_GO_TICK = ROUND_TICKS - 80

# ---------------------------------------------------------------------------
# Policy / timeout layer

# The IGL is a player, not a hidden engine modifier.  Their game sense and
# comms bend whether a team turns its standing book into an early execute.
# This is deliberately small: the static tactics dial remains the dominant
# preference, while the five-player policy supplies the actual decision.
POLICY_IGL_EXECUTE_SPAN = 0.08

# A timeout is the only live coach intervention.  A coach who has watched at
# least this many consecutive lost rounds may use the team's one map timeout
# if their quality plus the current urgency clears the threshold.
TIMEOUT_MIN_LOSS_STREAK = 3
TIMEOUT_URGENCY_PER_LOSS = 8.0
TIMEOUT_SCORE_DEFICIT_WEIGHT = 2.0
TIMEOUT_CALL_THRESHOLD = 65.0

# Timeout instructions affect the next policy plan only; they never add a
# direct combat modifier.  Quality determines how clearly the players can
# turn the timeout into a plan.
TIMEOUT_PRESSURE_EXECUTE_SPAN = 0.16
TIMEOUT_STABILIZE_EXECUTE_SPAN = 0.16
TIMEOUT_GO_TICK_SHIFT = 12

# Scouting preparation belongs in the team policy as well as the existing
# small duel term: a prepared side reads the opponent's likely deployment and
# avoids its heaviest site. Campaign-only game plans supply this value, so the
# bare engine's neutral gates remain unaffected.
PREP_POLICY_SITE_READ_SPAN = 0.45

# ---------------------------------------------------------------------------
# Economy (credits)

STARTING_CREDITS = 800  # pistol round
WIN_REWARD = 3000
LOSS_BONUS = [1900, 2400, 2900]  # indexed by consecutive-loss streak (cap last)
PLANT_BONUS = 300  # to every attacker if the spike was planted
CREDIT_CAP = 9000
OVERTIME_CREDITS = 6000  # flat stipend, both teams, every OT round
ARMOR_PRICE = 1000
ARMOR_VALUE = 50

# Buy-tier thresholds used by the IGL's team call and the heuristic policy.
FULL_BUY_THRESHOLD = 3900  # rifle + armor + some util
FORCE_BUY_THRESHOLD = 2400
# A dedicated AWPer may buy the Operator without armor; the buy resolver adds
# armor whenever the player can afford the full 5700-credit package.
OPERATOR_THRESHOLD = 4700
# Aim profile nudges rifle preference without making high-precision authored
# players pick the Vandal almost exclusively.
RIFLE_PREFERENCE_ATTRIBUTE_SCALE = 0.5

# ---------------------------------------------------------------------------
# Match format

ROUNDS_PER_HALF = 12
ROUNDS_TO_WIN = 13
MAX_ROUNDS = 40  # OT safety cap; ties broken by kills, then coin flip

# ---------------------------------------------------------------------------
# Combat model

# Per-tick chance that two players with an open mutual sightline actually
# commit to a duel (they might be jiggling, repositioning, waiting).
ENGAGE_PROB = 0.28
# Same-callout contact always engages.
ENGAGE_PROB_SAME_CALLOUT = 1.0
# Chance a duel resolves with no kill (both disengage).
DUEL_FIZZLE_PROB = 0.10
# Elo-style scale: a 90-point effective-skill gap ≈ 72% duel win. Duels
# must stay close to coin flips even between mismatched teams — man
# advantage, trades, and economy already compound every small edge over
# a 5v5 round, so a 20-pt attribute gap should mean ~57% per duel, not
# 70%+. Blowout scorelines killed the league before this was softened
# (see scripts/snowball_report.py).
DUEL_ELO_SCALE = 86.0
# Attribute mix for the base duel score. Precision is the primary separator;
# movement still matters but is more valuable in routing than raw aim duels.
DUEL_AIM_PRECISION_WEIGHT = 0.48
DUEL_AIM_REACTIVITY_WEIGHT = 0.27
DUEL_MOVEMENT_WEIGHT = 0.12
DUEL_POSITIONING_WEIGHT = 0.13
DUEL_GAME_SENSE_WEIGHT = 0.19
# Flat bonus for holding a defense-advantaged sightline (negated by smokes).
# Sized against DUEL_ELO_SCALE: at scale 90 this is ~57% for the holder —
# the angle matters, structure beats raw aim, but it's not a free kill.
HOLD_ADVANTAGE = 14.0
# A stationary player duelling someone mid-move is pre-aimed. Applies both
# ways (defenders on sites pre-plant, attackers in post-plant positions),
# is not negated by smokes, and stacks with HOLD_ADVANTAGE.
HOLDER_BONUS = 6.0
# Attacker bonus when entering behind good utility (scaled by util power).
# Short window: utility opens the door, it doesn't win the whole fight.
ENTRY_BONUS_MAX = 8.0
ENTRY_BONUS_TICKS = 14
# Flash debuff on the defender caught by an entry flash.
FLASH_DEBUFF = 15.0
FLASH_TICKS = 6
# Operator gets a bonus when holding a long angle, a malus when pushed close.
OPERATOR_HOLD_BONUS = 8.0
OPERATOR_CLOSE_MALUS = 6.0
# Kits built around the op (Jett's dash out, Chamber's TP — agents flagged
# op_affinity in data/agents.yaml) add a small edge to every operator duel.
# You can op on anyone; you only get the buff on these.
OPERATOR_AGENT_AFFINITY = 2.5

# Weapon model. Accuracy and body damage establish a weapon's floor; range
# then determines where it is allowed to express that strength.
WEAPON_ACCURACY_SCORE = 50.0
WEAPON_DAMAGE_PIVOT = 30.0
WEAPON_DAMAGE_SCORE = 1.0
WEAPON_DAMAGE_CAP = 12.0

# Range model (needs map floor geometry; neutral without it). Duels are
# fought at the straight-line distance between the two rooms' centers
# (same room = point blank). Snipers want long, SMGs/pistols want close,
# rifles are flat. Additive duel-score terms, capped small — range colors
# a duel, it doesn't decide it.
RANGE_POINT_BLANK = 4.0  # assumed distance for same-room fights
RANGE_SNIPER_PIVOT = 18.0  # ops break even here, gain beyond, lose inside
RANGE_SNIPER_SLOPE = 0.35
RANGE_SNIPER_CAP = 7.0
RANGE_PISTOL_PIVOT = 12.0
RANGE_PISTOL_SLOPE = 0.33
RANGE_PISTOL_CAP = 5.0
RANGE_SMG_PIVOT = 16.0
RANGE_SMG_SLOPE = 0.25
RANGE_SMG_CAP = 4.0
RANGE_SHOTGUN_PIVOT = 10.0
RANGE_SHOTGUN_SLOPE = 0.50
RANGE_SHOTGUN_CAP = 6.0

# Match form produces upsets, but it cannot routinely erase a clear skill
# edge. Composure narrows an individual's spread; team form is correlated.
DAY_FORM_BASE_SIGMA = 10.0
DAY_FORM_COMPOSURE_DIV = 25.0
DAY_FORM_MIN_SIGMA = 2.0
DAY_FORM_CAP = 14.0
TEAM_FORM_SIGMA = 4.0
TEAM_FORM_CAP = 8.0

# Map detail (props + elevation, from floor geometry):
# High ground: duel bonus per unit of floor-height difference, capped.
HEIGHT_PER_Z = 1.0
HEIGHT_CAP = 6.0
# Cover: a stationary holder anchored in a room with half-height props is
# harder to kill from other rooms. Per-prop, capped.
COVER_PER_PROP = 1.5
COVER_CAP = 4.5
# A full-height prop across a sightline breaks the angle: engagements on
# that line become rare repositioning skirmishes and neither side holds
# an advantage through a box.
SIGHT_BLOCK_ENGAGE_FACTOR = 0.45

# Trade window: teammates nearby can punish the killer.
TRADE_BASE_PROB = 0.35

# Headshot chance: base + precision-scaled.
HEADSHOT_BASE = 0.15

# Tilt: after this many consecutive lost rounds, low tilt_resistance bites.
TILT_STREAK = 3

# Ult economy: points gained per event; ability "power" weights for the
# coarse utility model.
ULT_POINTS_KILL = 1
ULT_POINTS_OBJECTIVE = 1
ULT_POINTS_ROUND = 1
UTIL_POWER_SMOKE = 2.0
UTIL_POWER_FLASH = 1.5
UTIL_POWER_DAMAGE = 1.0
UTIL_POWER_INFO = 1.0
UTIL_POWER_MOBILITY = 1.2
UTIL_POWER_ULT = 2.0
# One ability can have several effects (for example a Boom Bot scouts and
# damages). These tables make utility choice phase-aware instead of treating
# every kit as one generic strongest button. Keys are AbilityEffect values so
# tuning remains data/config driven without a schema import in this module.
UTILITY_INTENT_WEIGHTS = {
    "execute": {"smoke": 4.0, "flash": 3.5, "info": 3.0, "damage": 2.0, "mobility": 3.0},
    "stall": {"smoke": 3.0, "flash": 3.5, "info": 2.5, "damage": 4.0, "mobility": 1.0},
    "retake": {"smoke": 3.0, "flash": 4.0, "info": 3.5, "damage": 3.0, "mobility": 2.0},
}
UTILITY_SIGNATURE_PRIORITY = 0.15
# A dash/blast/teleport only accelerates the move it opens. It is deliberately
# bounded: mobility gets an entry angle, not an instantaneous site take.
MOBILITY_MOVE_MULT = 0.72
MOBILITY_TICKS = 12
# Chance per unit of post-plant damage-util power to kill the first defuser.
POST_PLANT_DENIAL_PROB = 0.12
# Max ticks a site's defensive utility can delay incoming attackers when a
# hit commits (scaled by util power). Stalls buy rotation time — the main
# lever against the 5-versus-few numbers math on executes.
STALL_TICKS_MAX = 10

# Defender fallback: outnumbered site defenders break contact instead of
# dying in place — the asymmetric piece the attack/defense balance needs
# (symmetric levers all failed; see git history). Falling back grants a
# short no-engage grace (off-angle repositioning), defenders rally toward
# spawn, and the existing post-plant grouped retake arrives with numbers.
FALLBACK_OUTNUMBER = 2  # attackers minus on-site defenders to trigger rolls
FALLBACK_BASE_PROB = 0.45  # + game_sense scaling; heroes sometimes stay
FALLBACK_GRACE_TICKS = 8  # covers the retreat hop out of the crossfire

# ---------------------------------------------------------------------------
# Tactics reach: how far each coaching dial bends the *micro* of a round.
# Every term below is written so a neutral 50 dial is an EXACT no-op — the
# golden log and the balance band are both measured with default (neutral)
# tactics, so neutrality here is what keeps those gates byte-stable.

# Aggression also shapes refrag spacing: aggressive teams stack tighter and
# hunt the trade, passive teams give up some refrags for safer spacing.
# Scales the trade probability by +/- this fraction across the full dial.
AGGRO_TRADE_GAIN_SPAN = 0.12
AGGRO_TRADE_COST_SPAN = 0.18
# Both aggressive teams take more live fights; two passive teams let more
# contact fizzle or wait. Neutral aggression remains an exact no-op.
AGGRO_ENGAGE_SPAN = 0.18
# A passive system converts positioning/sense/composure into stronger holds.
# An aggressive peeker pays an overextension cost, mitigated by the pole's
# mechanical fit. Together these are the explicit price of extra initiative.
AGGRO_PASSIVE_HOLD_SPAN = 4.0
AGGRO_OVEREXTENSION_SPAN = 12.0
AGGRO_OVEREXTENSION_MIN_FACTOR = 0.20
# Taking space without an explicit PEEK is less exposed, but still pays part
# of the same aggression risk when the player has surrendered holder status.
AGGRO_COMMITTED_RISK_FACTOR = 1.0

# Utility discipline shapes flash-for-peek: a disciplined player keeps a
# flash in the pocket to pop on a swing instead of dumping it on the group
# execute. Scales PEEK_FLASH_PROB by +/- this fraction across the dial.
DISC_PEEK_FLASH_SPAN = 0.50
# Good utility books turn difficult lineups into fewer whiffs. The sign is
# deliberately centered at 50 so neutral tactic fixtures stay unchanged.
UTIL_DISCIPLINE_FAIL_SPAN = 0.05
# Low discipline layers more power into the initial hit; high discipline
# realizes its saved charges during stalls and retakes. Each applies only in
# its own phase, making conservation an allocation rather than a free buff.
UTIL_DUMP_POWER_SPAN = 0.20
UTIL_RETAIN_POWER_SPAN = 0.20

# Pace shapes commitment on a floundering hit: fast books ram the entry
# through, slow books pull out and re-default. Shifts the abort threshold
# (attackers-down minus defenders-down) by +/- this many bodies. At pace 0
# the team pulls out at -1, at pace 100 it only bails at -3.
PACE_ABORT_SPAN = 1
# Pace shifts the actual call time in addition to choosing execute vs default.
# At the poles this creates a 10s early/late separation; 50 is exact no-op.
PACE_GO_TICK_SPAN = 10
# Both pace poles can create a clean entry window: slow teams through setup,
# fast teams through surprise. Pole-specific roster quality scales the bonus;
# the existing clock/rotation and abort behavior supplies each side's cost.
PACE_ENTRY_BONUS_SPAN = 6.0

# Map control (attack default): stack tight onto one entry and hit as five,
# or spread wide for map presence and peel a lurker onto a flank. Neutral
# and below keeps the current grouped staging; above neutral concentrates
# the stack less and rolls for a lurker.
LURK_MIN_CONTROL = 50.0  # no lurker at or below neutral
LURK_MAX_PROB = 0.55  # lurk chance at map_control=100
# The lurker baits at its flank, then strikes into the site this many ticks
# after the main hit commits — a late second wave onto defenders who have
# collapsed on the entry or are mid-rotation.
LURK_STRIKE_DELAY = 18
# A roster with the sense/positioning/comms for a spread system synchronizes
# its lurker sooner. At the high pole an elite fit can cut most of this span.
LURK_STRIKE_ACCEL_SPAN = 8
# Below neutral, collapse the staging onto fewer entry callouts (a hard
# stack). At control 0 the whole team funnels through a single entry.
STACK_MIN_CONTROL = 50.0

# Execution fit: every dial pole is a distinct system. Its edge is the
# roster's per-player fit for that pole relative to the opposite pole, plus an
# absolute readiness tax below EXEC_FIT_BASELINE. The term is ZERO when every
# dial is neutral, so it cannot move the golden/balance gates. See the shared
# engine/UI implementation in sim/tactics_fit.py.
EXEC_FIT_BASELINE = 55.0
EXEC_FIT_DIV = 30.0
# Players who fall BELOW the fit baseline are amplified by this factor before
# the per-player scores are summed, so a team-mate who can't run the system
# drags harder than an equally-good fit lifts. This is what keeps "crank every
# dial" from being free: a couple of stars can't average away the misfits, and
# a high-variance roster nets NEGATIVE at an extreme. 1.0 = the old
# roster-average behaviour (no extra penalty).
EXEC_MISFIT_PENALTY = 2.5
# A player's authored match identity is composition evidence in addition to
# raw attributes. Aligned entries/awpers, anchors/supports, IGLs, and lurkers
# add this many points to that pole's per-player fit before comparison.
EXEC_PLAYSTYLE_FIT_BONUS = 10.0
# Chemistry: coordination-heavy systems (spread/lurk map control,
# disciplined grouped retakes) lean on team cohesion. Complexity counts
# only the ABOVE-neutral deviation of those two dials — the low side
# (stacking tight, dumping utility) is the simpler read and isn't gated on
# chemistry. Chemistry above the baseline sharpens the system, below it
# makes the system misfire.
EXEC_CHEM_BASELINE = 65.0
EXEC_CHEM_DIV = 20.0
# Total execution modifier is clamped to keep it a colour on the duel, not
# the decider — squad quality and man-advantage still dominate.
EXEC_MOD_CAP = 8.0

# Confidence (campaign-fed, neutral-safe): 50 is an EXACT no-op on every
# term below, so default players keep the golden/balance gates byte-stable.
# The campaign layer moves confidence on results, personal ratings and the
# social layer; the engine reads it three ways — an additive duel term
# (mechanics), a peek-probability scale (tendencies: confident players
# swing angles), and a clutch-factor scale (belief in the big moment).
CONFIDENCE_COND_DIV = 10.0  # duel points per confidence point (/ div)
CONFIDENCE_COND_CAP = 3.0  # clamp on the additive duel term
CONFIDENCE_PEEK_DIV = 250.0  # +/-20% peek appetite across the dial
CONFIDENCE_CLUTCH_DIV = 200.0  # +/-25% clutch-factor leverage

# In-match momentum (neutral-safe): kills build it, deaths bleed it, and it
# decays every round — but it only ever AMPLIFIES a player's existing
# confidence deviation (eff = dev + m * SPAN * |dev|), so a default-50
# player feels nothing and the golden/balance gates stay byte-stable. In a
# campaign, where confidence spreads immediately, a heater lifts a shaky
# player back toward level and a tilt dims a swaggering one — mental state
# sets the ceiling, momentum decides how much of it shows up tonight.
MOMENTUM_KILL = 0.08  # per kill
MOMENTUM_DEATH = 0.10  # per death (dying stings more than killing thrills)
MOMENTUM_CLUTCH = 0.25  # winning a round as the last one standing
MOMENTUM_DECAY = 0.85  # per-round decay toward flat
MOMENTUM_CAP = 1.0  # |momentum| clamp before the span applies
MOMENTUM_SPAN = 0.6  # max fraction of |dev| that momentum adds/removes

# Game-plan reach (campaign-fed, default-off): the bare-engine gates never
# construct a plan, so every term below is gated on a plan existing.
# prep_edge is the scouting-driven duel bonus a prepared side brings
# (campaign computes it from scout knowledge; clamped here so prep stays a
# colour, not a decider). Focus targeting trades a real edge in duels
# against the hunted opponent for a small tax everywhere else —
# over-indexing your anti-strat on one man has a cost.
PREP_EDGE_CAP = 1.5
FOCUS_TARGET_EDGE = 2.5  # duel points vs the hunted player
FOCUS_OFF_MALUS = 0.5  # duel points given up vs everyone else

# A one-match dial override becomes a real counter-strat only when it leans
# against the opponent's actual identity. Each of the four execution dials is
# compared at [-1, +1] around neutral; matching their lean is a penalty and
# opposing it is a bonus. The average is multiplied by this span, then capped,
# so a coherent four-dial counter can move a close matchup without bridging an
# elite-vs-50-overall talent gap by itself.
COUNTER_STRAT_SPAN = 7.5
COUNTER_STRAT_CAP = 3.0

# Eco discipline: on a save/force round eco_greed decides whether the team
# runs it down (a fast aggressive hit to catch the buy off-guard) or plays
# slow for picks and the exit. Shifts the execute probability by +/- this
# on non-full-buy rounds only; neutral eco_greed leaves it untouched.
ECO_EXECUTE_SPAN = 0.30
# Neutral teams save until they are just short of a full rifle buy instead of
# chaining Spectre forces after ordinary losses.  Eco-greedy teams still open
# a meaningful force window; disciplined teams bank for the next rifle round.
ECO_FORCE_BASE_MULT = 1.55
ECO_FORCE_MULT_SPAN = 0.20

# Pace also has a defensive dimension — tempo, not appetite. A fast book
# rotates onto a hit sooner and commits the retake without waiting for a
# partner; a slow book plays patient and grouped. Shifts each rotator's
# delay by +/- this many ticks across the dial; neutral pace is unchanged.
PACE_ROTATE_SPAN = 3
# Expose the non-dial rotation timing in the tuning table. These values keep
# the existing base behavior; pace contributes the neutral-safe span above.
ROTATE_DELAY_BASE = 12
ROTATE_SKILL_DIV = 20.0
