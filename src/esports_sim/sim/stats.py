"""Box score computed from an event log.

Everything here is derived — the event log stays the single source of
truth, and any UI (CLI scoreboard, future web viewer) reads these. This
module never emits events, so it cannot drift the golden gate.

Optional context deepens the derivation without changing the log:
- `team_of` (player -> team, both FULL playing rosters) unlocks clutch
  detection, KAST and survival tracking.
- `weapon_class_of` (weapon id -> class string, from the weapon registry)
  unlocks the economy splits (eco / save kills).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from esports_sim.schemas import Event

# Pistol rounds under the standard MR12 format (mirrors sim.constants:
# round 1 and ROUNDS_PER_HALF + 1).
PISTOL_ROUNDS = (1, 13)

# Rifle-tier weapon classes: a team where fewer than 3 players hold one is
# "under-gunned" (mirrors the engine's _under_gunned eco read).
RIFLE_TIER = {"rifle", "sniper", "lmg"}

# ACS proxy weights. The sim has no damage model, so combat score is
# rebuilt from what the log does record; calibrated so the league-average
# ~0.7 KPR lands near the familiar ~190 band and star carries push 280+.
ACS_KILL = 250.0
ACS_HEADSHOT = 25.0
ACS_ASSIST = 50.0
ACS_OBJECTIVE = 40.0  # plant / defuse
ACS_FIRST_KILL = 25.0


@dataclass
class PlayerLine:
    player_id: str
    agent_id: str = ""  # agent locked for this map ("" in old logs)
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    first_kills: int = 0
    trade_kills: int = 0
    headshots: int = 0
    plants: int = 0
    defuses: int = 0
    # Richer counters, all derived from the same event log (no new events):
    first_deaths: int = 0  # died in the round's opening duel
    multikills: int = 0  # rounds with 3+ kills
    aces: int = 0  # rounds with all 5 kills
    clutches: int = 0  # legacy: won a round as last alive vs 2+ enemies
    clutch_1v1: int = 0
    clutch_1v2: int = 0
    clutch_1v3: int = 0  # 1v3 or worse
    survived: int = 0  # rounds alive at the horn (needs team_of)
    traded_deaths: int = 0  # deaths a teammate avenged on the spot
    kast_rounds: int = 0  # rounds with a Kill/Assist/Survival/Trade
    combat_score: float = 0.0  # ACS points total (acs = per round)
    pistol_kills: int = 0
    eco_kills: int = 0  # kills while own team was under-gunned
    save_kills: int = 0  # kills on a personal sidearm save
    kills_by_weapon: dict[str, int] = field(default_factory=dict)
    rating: float = 0.0


@dataclass
class RoundSummary:
    round_num: int
    attacking_team_id: str
    winner_id: str
    reason: str
    kills: list[tuple[str, str, str]] = field(default_factory=list)  # killer, victim, weapon


@dataclass
class MatchStats:
    match_id: str
    map_id: str
    team_a_id: str
    team_b_id: str
    score_a: int
    score_b: int
    winner_id: str
    rounds: list[RoundSummary]
    lines: dict[str, PlayerLine]


def compute_match_stats(
    events: list[Event],
    team_of: dict[str, str] | None = None,
    weapon_class_of: dict[str, str] | None = None,
) -> MatchStats:
    """Box score from the event log. Without the optional context maps the
    basic counters are unchanged from the original derivation, so existing
    callers keep working and the log is untouched."""
    match_id = ""
    map_id = ""
    team_a_id = ""
    team_b_id = ""
    score_a = score_b = 0
    winner_id = ""
    agent_of: dict[str, str] = {}
    rounds: list[RoundSummary] = []
    lines: dict[str, PlayerLine] = {}
    current: RoundSummary | None = None
    first_kill_done = False

    # Per-round scratch for the deeper derivations.
    rosters: dict[str, set[str]] = {}
    if team_of:
        for pid, tid in team_of.items():
            rosters.setdefault(tid, set()).add(pid)
    round_kills: dict[str, int] = {}  # killer -> kills this round
    round_assists: set[str] = set()  # players with an assist this round
    round_traded: set[str] = set()  # victims avenged this round
    round_num_cur = 0
    alive: dict[str, set[str]] = {}  # team -> alive players this round
    # First moment a team was isolated to one player: (player, enemy count).
    isolated: dict[str, tuple[str, int]] = {}
    # Post-buy loadout this round (from BuyEvents): pid -> (weapon, armor).
    loadout: dict[str, tuple[str, int]] = {}
    # The most recent kill, for pairing a trade with the death it avenges.
    last_kill: tuple[str, str] | None = None  # (killer, victim)

    def line(pid: str) -> PlayerLine:
        if pid not in lines:
            lines[pid] = PlayerLine(player_id=pid, agent_id=agent_of.get(pid, ""))
        return lines[pid]

    def team_under_gunned(tid: str | None) -> bool:
        """Under-gunned = fewer than 3 of the team's five hold a rifle-tier
        primary after the buy (same read as the engine's eco logic)."""
        if not weapon_class_of or tid is None or not rosters.get(tid):
            return False
        armed = sum(
            1
            for pid in rosters[tid]
            if weapon_class_of.get(loadout.get(pid, ("classic", 0))[0])
            in RIFLE_TIER
        )
        return armed < 3

    for e in events:
        if e.type == "match.start":
            match_id, map_id = e.match_id, e.map_id
            team_a_id, team_b_id = e.team_a_id, e.team_b_id
            agent_of = dict(e.agents)
        elif e.type == "round.start":
            current = RoundSummary(
                round_num=e.round_num,
                attacking_team_id=e.attacking_team_id,
                winner_id="",
                reason="",
            )
            round_num_cur = e.round_num
            first_kill_done = False
            round_kills = {}
            round_assists = set()
            round_traded = set()
            loadout = {}
            last_kill = None
            alive = {tid: set(pids) for tid, pids in rosters.items()}
            isolated = {}
        elif e.type == "round.buy":
            loadout[e.player_id] = (e.weapon_id, e.armor)
        elif e.type == "round.kill":
            k, v = line(e.killer_id), line(e.victim_id)
            k.kills += 1
            v.deaths += 1
            round_kills[e.killer_id] = round_kills.get(e.killer_id, 0) + 1
            k.kills_by_weapon[e.weapon_id] = (
                k.kills_by_weapon.get(e.weapon_id, 0) + 1
            )
            if e.headshot:
                k.headshots += 1
            if e.assist_id:
                line(e.assist_id).assists += 1
                round_assists.add(e.assist_id)
            if e.is_trade:
                k.trade_kills += 1
                # The trade avenges the most recent kill BY this trade's
                # victim — that kill's victim died traded.
                if last_kill is not None and last_kill[0] == e.victim_id:
                    line(last_kill[1]).traded_deaths += 1
                    round_traded.add(last_kill[1])
            if not first_kill_done:
                k.first_kills += 1
                v.first_deaths += 1
                first_kill_done = True
            # Economy splits (need the weapon registry's class map).
            killer_team = team_of.get(e.killer_id) if team_of else None
            victim_team = team_of.get(e.victim_id) if team_of else None
            if round_num_cur in PISTOL_ROUNDS:
                k.pistol_kills += 1
            else:
                # Eco kill = punching UP: own team under-gunned, enemy not.
                if team_under_gunned(killer_team) and not team_under_gunned(
                    victim_team
                ):
                    k.eco_kills += 1
                # Save kill = converted on a true personal save: sidearm in
                # hand, no armor bought, on a gun round.
                kw, karmor = loadout.get(e.killer_id, ("", -1))
                if (
                    weapon_class_of
                    and karmor == 0
                    and weapon_class_of.get(kw) == "pistol"
                ):
                    k.save_kills += 1
            last_kill = (e.killer_id, e.victim_id)
            if current is not None:
                current.kills.append((e.killer_id, e.victim_id, e.weapon_id))
            # Track isolation for clutch detection.
            vteam = team_of.get(e.victim_id) if team_of else None
            if vteam is not None and e.victim_id in alive.get(vteam, ()):
                alive[vteam].discard(e.victim_id)
                if len(alive[vteam]) == 1 and vteam not in isolated:
                    last = next(iter(alive[vteam]))
                    enemies = sum(
                        len(a) for t, a in alive.items() if t != vteam
                    )
                    isolated[vteam] = (last, enemies)
        elif e.type == "round.spike_plant":
            line(e.player_id).plants += 1
        elif e.type == "round.spike_defuse":
            line(e.player_id).defuses += 1
        elif e.type == "round.end":
            if current is not None:
                current.winner_id = e.winner_id
                current.reason = e.reason
                rounds.append(current)
                current = None
            # Multi-kills / aces from this round's kill counts.
            for pid, n in round_kills.items():
                if n >= 5:
                    line(pid).aces += 1
                    line(pid).multikills += 1
                elif n >= 3:
                    line(pid).multikills += 1
            # Survival + KAST need full rosters (team_of).
            for tid, pids in alive.items():
                for pid in pids:
                    line(pid).survived += 1
            if rosters:
                for tid, pids in rosters.items():
                    for pid in pids:
                        if (
                            round_kills.get(pid)
                            or pid in round_assists
                            or pid in alive.get(tid, ())
                            or pid in round_traded
                        ):
                            line(pid).kast_rounds += 1
            # Clutch: the winner's last-man-standing — still ALIVE at the
            # end (a post-plant detonation after the last man dies is a win
            # but not a clutch). Bucketed by how outnumbered they were when
            # isolated; the legacy `clutches` counter keeps its original
            # 1v2-or-worse meaning.
            clutch = isolated.get(e.winner_id)
            if clutch is not None and clutch[0] in alive.get(e.winner_id, ()):
                pl = line(clutch[0])
                if clutch[1] == 1:
                    pl.clutch_1v1 += 1
                elif clutch[1] == 2:
                    pl.clutch_1v2 += 1
                    pl.clutches += 1
                elif clutch[1] >= 3:
                    pl.clutch_1v3 += 1
                    pl.clutches += 1
        elif e.type == "match.end":
            winner_id = e.winner_id
            score_a, score_b = e.score_a, e.score_b

    n_rounds = max(len(rounds), 1)
    for pl in lines.values():
        # Simple impact rating around 1.0, HLTV-flavoured (unchanged from
        # the original derivation — awards and form movement ride on it).
        kpr = pl.kills / n_rounds
        dpr = pl.deaths / n_rounds
        impact = (pl.first_kills * 0.5 + pl.plants * 0.25 + pl.defuses * 0.25) / n_rounds
        pl.rating = round(0.75 * (kpr / 0.7) + 0.35 * ((1 - dpr) / 0.4) * 0.4 + impact, 2)
        # ACS proxy from logged contributions (see module docstring).
        pl.combat_score = round(
            ACS_KILL * pl.kills
            + ACS_HEADSHOT * pl.headshots
            + ACS_ASSIST * pl.assists
            + ACS_OBJECTIVE * (pl.plants + pl.defuses)
            + ACS_FIRST_KILL * pl.first_kills,
            1,
        )

    return MatchStats(
        match_id=match_id,
        map_id=map_id,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        score_a=score_a,
        score_b=score_b,
        winner_id=winner_id,
        rounds=rounds,
        lines=lines,
    )
