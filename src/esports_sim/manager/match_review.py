"""Match diagnosis — the "why you won/lost" synthesis.

Derives, from a team's most recent series, a ranked set of signals about where
the team is breaking down vs working: side-of-ball round splits, pistols,
opening duels, trades, clutches, post-plant / retake conversion, economy, comms
and utility discipline, plus a standout / off-colour player read.

Everything is DERIVED from the box score (`sim.stats.MatchStats`) and the raw
event log — this module emits no events and draws no rng, so it is
golden-safe and campaign-deterministic (same seed -> byte-identical review).
It is also TIER-AGNOSTIC: it computes every signal it can and tags each with the
analyst `min_tier` that unlocks it; the web serializer filters by the team's
current tier and turns each `code` into display copy + a concrete fix lever.

The heavy lifting is a single event walk per map that reuses the same
under-gunned / isolation reads as `sim.stats`, so the round-context denominators
(clutches faced, plants, retakes, eco rounds) stay consistent with the box score.
"""

from __future__ import annotations

from esports_sim.manager.state import MatchReview, ReviewPoint
from esports_sim.sim.stats import PISTOL_ROUNDS, RIFLE_TIER, MatchStats
from esports_sim.schemas import Event

# Neutral value for weighting (the "even" reference each rate is measured from)
# and a per-category priority (how decisive it is to the result). weight =
# |value - neutral| * priority, so side-of-ball and pistols float to the top.
_PRIORITY = {
    "attack": 3.0,
    "defense": 3.0,
    "pistol": 2.6,
    "opening": 2.0,
    "player": 1.8,
    "clutch": 1.6,
    "acs": 0.02,  # gap is on the 0-100 ACS scale, not a 0-1 rate
    "trades": 1.5,
    "economy": 1.3,
    "post_plant": 1.3,
    "retake": 1.3,
    "comms": 1.0,
    "utility": 1.0,
}


def _rate(num: int, den: int) -> float:
    return num / den if den else 0.0


def _under_gunned(pids: set[str], loadout: dict, weapon_class_of: dict) -> bool:
    """Fewer than 3 of the five hold a rifle-tier primary after the buy —
    the same read `sim.stats.team_under_gunned` uses for the economy splits."""
    if not weapon_class_of or not pids:
        return False
    armed = sum(
        1
        for pid in pids
        if weapon_class_of.get(loadout.get(pid, ("classic", 0))[0]) in RIFLE_TIER
    )
    return armed < 3


def _walk_map(
    stats: MatchStats,
    events: list[Event],
    team_of: dict[str, str],
    team_id: str,
    opp_id: str,
    weapon_class_of: dict,
    c: dict[str, int],
) -> None:
    """Fold one map's round context into the team-perspective accumulator `c`.
    Only the attacking team can plant, so a plant's team == the round's
    attacker; a defended round where the enemy planted is a retake chance."""
    rosters: dict[str, set[str]] = {}
    for pid, tid in team_of.items():
        rosters.setdefault(tid, set()).add(pid)
    ours = rosters.get(team_id, set())

    attacker = ""
    loadout: dict[str, tuple[str, int]] = {}
    planted_by = ""
    round_num = 0

    for e in events:
        if e.type == "round.start":
            attacker = e.attacking_team_id
            round_num = e.round_num
            loadout = {}
            planted_by = ""
        elif e.type == "round.buy":
            loadout[e.player_id] = (e.weapon_id, e.armor)
        elif e.type == "round.spike_plant":
            planted_by = team_of.get(e.player_id, "")
        elif e.type == "round.comms":
            if e.team_id == team_id:
                if e.kind == "miscomm":
                    c["miscomms"] += 1
                else:
                    c["comms_calls"] += 1
        elif e.type == "round.utility_used":
            if team_of.get(e.player_id) == team_id:
                c["util_used"] += 1
                if e.failed:
                    c["util_failed"] += 1
        elif e.type == "round.end":
            won = e.winner_id == team_id
            if attacker == team_id:
                c["atk_rounds"] += 1
                c["atk_won"] += 1 if won else 0
            else:
                c["def_rounds"] += 1
                c["def_won"] += 1 if won else 0
            if round_num in PISTOL_ROUNDS:
                c["pistol_played"] += 1
                c["pistol_won"] += 1 if won else 0
            if planted_by == team_id:
                c["plants"] += 1
                c["plants_won"] += 1 if won else 0
            elif planted_by == opp_id:
                c["opp_plants"] += 1
                c["retakes_won"] += 1 if won else 0
            # Eco round = we were under-gunned on a gun round; did we steal it?
            if round_num not in PISTOL_ROUNDS and _under_gunned(
                ours, loadout, weapon_class_of
            ):
                c["eco_rounds"] += 1
                c["eco_won"] += 1 if won else 0
            attacker = ""


def _clutch_pass(
    events: list[Event], team_of: dict[str, str], team_id: str, c: dict[str, int]
) -> None:
    """Count clutches FACED (we were reduced to our last man) and WON (that
    last man was still alive when we took the round) — mirrors the isolation
    read in sim.stats, from our team's perspective."""
    ours = {pid for pid, tid in team_of.items() if tid == team_id}
    alive: set[str] = set()
    isolated_pid = ""
    faced_this_round = False
    for e in events:
        if e.type == "round.start":
            alive = set(ours)
            isolated_pid = ""
            faced_this_round = False
        elif e.type == "round.kill":
            if e.victim_id in alive:
                alive.discard(e.victim_id)
                if len(alive) == 1 and not faced_this_round:
                    isolated_pid = next(iter(alive))
                    faced_this_round = True
                    c["clutch_faced"] += 1
        elif e.type == "round.end":
            if faced_this_round and e.winner_id == team_id and isolated_pid in alive:
                c["clutch_won"] += 1


def _emit(
    points: list[ReviewPoint],
    code: str,
    category: str,
    min_tier: int,
    value: float,
    num: int,
    den: int,
    neutral: float,
    *,
    tone: str,
    player_id: str = "",
    lever_code: str = "",
) -> None:
    weight = round(abs(value - neutral) * _PRIORITY[category], 4)
    points.append(
        ReviewPoint(
            code=code,
            category=category,
            tone=tone,
            min_tier=min_tier,
            value=round(value, 4),
            num=int(num),
            den=int(den),
            weight=weight,
            player_id=player_id,
            lever_code=lever_code,
        )
    )


def build_match_review(
    season: int,
    week: int,
    fixture_id: str,
    team_id: str,
    opp_id: str,
    best_of: int,
    per_map_bundles: list[tuple[MatchStats, list[Event], dict[str, str]]],
    weapon_class_of: dict[str, str],
) -> MatchReview:
    """Synthesize the review for `team_id`'s series. `per_map_bundles` is one
    (box score, event log, dressed roster map) tuple per played map."""
    if not per_map_bundles:
        return MatchReview(
            fixture_id=fixture_id,
            season=season,
            week=week,
            team_id=team_id,
            opp_id=opp_id,
            best_of=best_of,
            contested=False,
        )

    c: dict[str, int] = {}
    for k in (
        "atk_rounds", "atk_won", "def_rounds", "def_won",
        "pistol_played", "pistol_won", "plants", "plants_won",
        "opp_plants", "retakes_won", "clutch_faced", "clutch_won",
        "comms_calls", "miscomms", "util_used", "util_failed",
        "eco_rounds", "eco_won",
    ):
        c[k] = 0

    your_maps = their_maps = your_rounds = their_rounds = 0
    your_combat = their_combat = 0.0
    total_rounds = 0
    fk = fd = deaths = traded = 0
    # pid -> [rating_sum, maps, kills]; kept for both teams (potm) and ours.
    pr: dict[str, list[float]] = {}

    for stats, events, team_of in per_map_bundles:
        # Orient the scoreline to our side.
        if stats.team_a_id == team_id:
            your_rounds += stats.score_a
            their_rounds += stats.score_b
        else:
            your_rounds += stats.score_b
            their_rounds += stats.score_a
        if stats.winner_id == team_id:
            your_maps += 1
        elif stats.winner_id:
            their_maps += 1
        total_rounds += len(stats.rounds)

        for pid, ln in sorted(stats.lines.items()):
            tid = team_of.get(pid, "")
            a = pr.setdefault(pid, [0.0, 0.0, 0.0])
            a[0] += ln.rating
            a[1] += 1
            a[2] += ln.kills
            if tid == team_id:
                your_combat += ln.combat_score
                fk += ln.first_kills
                fd += ln.first_deaths
                deaths += ln.deaths
                traded += ln.traded_deaths
            elif tid == opp_id:
                their_combat += ln.combat_score

        _walk_map(stats, events, team_of, team_id, opp_id, weapon_class_of, c)
        _clutch_pass(events, team_of, team_id, c)

    won = your_maps > their_maps
    working: list[ReviewPoint] = []
    breaking: list[ReviewPoint] = []

    def add(tone: str, *args, **kw) -> None:
        _emit(working if tone == "good" else breaking, *args, tone=tone, **kw)

    # -- side of ball (tier 0) ------------------------------------------------
    if c["atk_rounds"] >= 5:
        v = _rate(c["atk_won"], c["atk_rounds"])
        if v >= 0.55:
            add("good", "atk_side", "attack", 0, v, c["atk_won"], c["atk_rounds"], 0.5)
        elif v <= 0.40:
            add("bad", "atk_side", "attack", 0, v, c["atk_won"], c["atk_rounds"], 0.5,
                lever_code="atk_tempo")
    if c["def_rounds"] >= 5:
        v = _rate(c["def_won"], c["def_rounds"])
        if v >= 0.60:
            add("good", "def_side", "defense", 0, v, c["def_won"], c["def_rounds"], 0.5)
        elif v <= 0.45:
            add("bad", "def_side", "defense", 0, v, c["def_won"], c["def_rounds"], 0.5,
                lever_code="def_setups")
    if c["pistol_played"] >= 2:
        v = _rate(c["pistol_won"], c["pistol_played"])
        if v >= 1.0:
            add("good", "pistol", "pistol", 0, v, c["pistol_won"], c["pistol_played"], 0.5)
        elif v <= 0.0:
            add("bad", "pistol", "pistol", 0, v, c["pistol_won"], c["pistol_played"], 0.5,
                lever_code="pistol_prep")

    # -- players (tier 0) -----------------------------------------------------
    ours = sorted(
        (pid for pid, a in pr.items() if _map_team(pid, per_map_bundles) == team_id),
        key=lambda pid: (-(pr[pid][0] / pr[pid][1]) if pr[pid][1] else 0.0, pid),
    )
    if ours:
        top = ours[0]
        top_r = pr[top][0] / pr[top][1] if pr[top][1] else 0.0
        if top_r >= 1.15:
            add("good", "player_std", "player", 0, top_r, 0, 0, 1.0, player_id=top)
        low = ours[-1]
        low_r = pr[low][0] / pr[low][1] if pr[low][1] else 0.0
        if low_r <= 0.85 and low != top:
            add("bad", "player_under", "player", 0, low_r, 0, 0, 1.0, player_id=low,
                lever_code="player_form")

    # -- duels / impact (tier 1) ---------------------------------------------
    if fk + fd >= 8:
        v = _rate(fk, fk + fd)
        if v >= 0.55:
            add("good", "opening", "opening", 1, v, fk, fk + fd, 0.5)
        elif v <= 0.45:
            add("bad", "opening", "opening", 1, v, fk, fk + fd, 0.5,
                lever_code="entry_support")
    if c["clutch_faced"] >= 3 and c["clutch_won"] == 0:
        add("bad", "clutch", "clutch", 1, 0.0, 0, c["clutch_faced"], 0.5,
            lever_code="clutch_mental")
    elif c["clutch_faced"] >= 2 and c["clutch_won"] >= 2:
        v = _rate(c["clutch_won"], c["clutch_faced"])
        add("good", "clutch", "clutch", 1, v, c["clutch_won"], c["clutch_faced"], 0.5)
    if total_rounds:
        gap = your_combat / total_rounds / 5.0 - their_combat / total_rounds / 5.0
        if gap >= 15.0:
            add("good", "acs_gap", "acs", 1, gap,
                int(round(your_combat / total_rounds / 5.0)),
                int(round(their_combat / total_rounds / 5.0)), 0.0)
        elif gap <= -15.0:
            add("bad", "acs_gap", "acs", 1, gap,
                int(round(your_combat / total_rounds / 5.0)),
                int(round(their_combat / total_rounds / 5.0)), 0.0,
                lever_code="aim_training")

    # -- round context (tier 2) ----------------------------------------------
    if deaths >= 10:
        v = _rate(traded, deaths)
        if v >= 0.50:
            add("good", "trades", "trades", 2, v, traded, deaths, 0.4)
        elif v <= 0.30:
            add("bad", "trades", "trades", 2, v, traded, deaths, 0.4,
                lever_code="trade_discipline")
    if c["plants"] >= 4:
        v = _rate(c["plants_won"], c["plants"])
        if v >= 0.70:
            add("good", "post_plant", "post_plant", 2, v, c["plants_won"], c["plants"], 0.6)
        elif v <= 0.45:
            add("bad", "post_plant", "post_plant", 2, v, c["plants_won"], c["plants"], 0.6,
                lever_code="post_plant")
    if c["opp_plants"] >= 4:
        v = _rate(c["retakes_won"], c["opp_plants"])
        if v >= 0.35:
            add("good", "retake", "retake", 2, v, c["retakes_won"], c["opp_plants"], 0.25)
        elif v <= 0.10 and c["opp_plants"] >= 5:
            add("bad", "retake", "retake", 2, v, c["retakes_won"], c["opp_plants"], 0.25,
                lever_code="retake_util")
    if c["eco_rounds"] >= 4:
        v = _rate(c["eco_won"], c["eco_rounds"])
        if v >= 0.35:
            add("good", "economy", "economy", 2, v, c["eco_won"], c["eco_rounds"], 0.25)
        elif c["eco_won"] == 0 and c["eco_rounds"] >= 5:
            add("bad", "economy", "economy", 2, 0.0, 0, c["eco_rounds"], 0.25,
                lever_code="eco_discipline")
    rounds_played = c["atk_rounds"] + c["def_rounds"]
    if rounds_played >= 12:
        v = _rate(c["miscomms"], rounds_played)
        if v >= 0.15:
            add("bad", "comms", "comms", 2, v, c["miscomms"], rounds_played, 0.0,
                lever_code="comms_cohesion")
        elif c["miscomms"] == 0:
            add("good", "comms", "comms", 2, 0.0, 0, rounds_played, 0.0)
    if c["util_used"] >= 10:
        v = _rate(c["util_failed"], c["util_used"])
        if v >= 0.30:
            add("bad", "utility", "utility", 2, v, c["util_failed"], c["util_used"], 0.0,
                lever_code="util_discipline")
        elif v <= 0.12:
            add("good", "utility", "utility", 2, v, c["util_failed"], c["util_used"], 0.0)

    working.sort(key=lambda p: (-p.weight, p.code))
    breaking.sort(key=lambda p: (-p.weight, p.code))

    return MatchReview(
        fixture_id=fixture_id,
        season=season,
        week=week,
        team_id=team_id,
        opp_id=opp_id,
        won=won,
        best_of=best_of,
        your_maps=your_maps,
        their_maps=their_maps,
        your_rounds=your_rounds,
        their_rounds=their_rounds,
        potm_id=_potm(pr, per_map_bundles, team_id if won else opp_id),
        contested=True,
        working=working,
        breaking=breaking,
    )


def _map_team(
    pid: str, bundles: list[tuple[MatchStats, list[Event], dict[str, str]]]
) -> str:
    for _stats, _events, team_of in bundles:
        if pid in team_of:
            return team_of[pid]
    return ""


def _potm(
    pr: dict[str, list[float]],
    bundles: list[tuple[MatchStats, list[Event], dict[str, str]]],
    winner_id: str,
) -> str:
    """Player of the match: best mean rating, preferring the winning side, with
    a sorted-id tie-break (deterministic, mirrors web _series_potm)."""
    if not pr:
        return ""

    def mean(pid: str) -> float:
        rs, mp, _ = pr[pid]
        return rs / mp if mp else 0.0

    winners = [pid for pid in pr if _map_team(pid, bundles) == winner_id]
    pool = winners or list(pr)
    return max(sorted(pool), key=mean)
