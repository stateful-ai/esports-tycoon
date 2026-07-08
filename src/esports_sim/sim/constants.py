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
# 2.4 grid units/tick makes a typical door-to-door hop ~4-9 ticks, which
# keeps overall round pacing near the old fixed 6-tick hops.
PLAYER_SPEED = 2.4  # grid units per tick at movement=50
MIN_MOVE_TICKS = 2
# Positional cover: a stationary holder hugging a crate that sits between
# them and the shooter is simply harder to kill.
COVER_BONUS = 4.0

# Default-strat attackers commit somewhere in this window (uniform draw).
DEFAULT_GO_EARLIEST = 90
DEFAULT_GO_LATEST = 130
# Execute-strat attackers commit as soon as everyone is staged, but not
# before this tick (utility setup time).
EXECUTE_GO_EARLIEST = 30
# If nothing has happened by here, force the hit regardless of strat.
FORCE_GO_TICK = ROUND_TICKS - 70

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
OPERATOR_THRESHOLD = 5700  # op + armor

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
DUEL_ELO_SCALE = 90.0
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

# Range model (needs map floor geometry; neutral without it). Duels are
# fought at the straight-line distance between the two rooms' centers
# (same room = point blank). Snipers want long, SMGs/pistols want close,
# rifles are flat. Additive duel-score terms, capped small — range colors
# a duel, it doesn't decide it.
RANGE_POINT_BLANK = 4.0  # assumed distance for same-room fights
RANGE_SNIPER_PIVOT = 18.0  # ops break even here, gain beyond, lose inside
RANGE_SNIPER_SLOPE = 0.35
RANGE_SNIPER_CAP = 7.0
RANGE_CQC_PIVOT = 14.0  # smg/pistol break-even
RANGE_CQC_SLOPE = 0.30
RANGE_CQC_CAP = 5.0

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
UTIL_POWER_ULT = 2.0
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
