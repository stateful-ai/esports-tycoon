"""Box score computed from an event log.

Everything here is derived — the event log stays the single source of
truth, and any UI (CLI scoreboard, future web viewer) reads these.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from esports_sim.schemas import Event


@dataclass
class PlayerLine:
    player_id: str
    kills: int = 0
    deaths: int = 0
    first_kills: int = 0
    trade_kills: int = 0
    headshots: int = 0
    plants: int = 0
    defuses: int = 0
    # Richer counters, all derived from the same event log (no new events):
    first_deaths: int = 0  # died in the round's opening duel
    multikills: int = 0  # rounds with 3+ kills
    aces: int = 0  # rounds with all 5 kills
    clutches: int = 0  # won a round as the last player alive vs 2+ enemies
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
    events: list[Event], team_of: dict[str, str] | None = None
) -> MatchStats:
    """Box score from the event log. Pass `team_of` (player_id -> team_id
    for both full rosters) to also detect clutches — a 1vX round win by the
    last player alive. Without it clutches stay 0 and everything else is
    unchanged, so existing callers keep working and the log is untouched."""
    match_id = ""
    map_id = ""
    team_a_id = ""
    team_b_id = ""
    score_a = score_b = 0
    winner_id = ""
    rounds: list[RoundSummary] = []
    lines: dict[str, PlayerLine] = {}
    current: RoundSummary | None = None
    first_kill_done = False

    # Per-round scratch for the new derivations.
    rosters: dict[str, set[str]] = {}
    if team_of:
        for pid, tid in team_of.items():
            rosters.setdefault(tid, set()).add(pid)
    round_kills: dict[str, int] = {}  # killer -> kills this round
    alive: dict[str, set[str]] = {}  # team -> alive players this round
    # First moment a team was isolated to one player: (player, enemy count).
    isolated: dict[str, tuple[str, int]] = {}

    def line(pid: str) -> PlayerLine:
        if pid not in lines:
            lines[pid] = PlayerLine(player_id=pid)
        return lines[pid]

    for e in events:
        if e.type == "match.start":
            match_id, map_id = e.match_id, e.map_id
            team_a_id, team_b_id = e.team_a_id, e.team_b_id
        elif e.type == "round.start":
            current = RoundSummary(
                round_num=e.round_num,
                attacking_team_id=e.attacking_team_id,
                winner_id="",
                reason="",
            )
            first_kill_done = False
            round_kills = {}
            alive = {tid: set(pids) for tid, pids in rosters.items()}
            isolated = {}
        elif e.type == "round.kill":
            k, v = line(e.killer_id), line(e.victim_id)
            k.kills += 1
            v.deaths += 1
            round_kills[e.killer_id] = round_kills.get(e.killer_id, 0) + 1
            if e.headshot:
                k.headshots += 1
            if e.is_trade:
                k.trade_kills += 1
            if not first_kill_done:
                k.first_kills += 1
                v.first_deaths += 1
                first_kill_done = True
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
            # Clutch: the winner's last-man-standing, isolated vs 2+ enemies.
            clutch = isolated.get(e.winner_id)
            if clutch is not None and clutch[1] >= 2:
                line(clutch[0]).clutches += 1
        elif e.type == "match.end":
            winner_id = e.winner_id
            score_a, score_b = e.score_a, e.score_b

    n_rounds = max(len(rounds), 1)
    for pl in lines.values():
        # Simple impact rating around 1.0, HLTV-flavoured.
        kpr = pl.kills / n_rounds
        dpr = pl.deaths / n_rounds
        impact = (pl.first_kills * 0.5 + pl.plants * 0.25 + pl.defuses * 0.25) / n_rounds
        pl.rating = round(0.75 * (kpr / 0.7) + 0.35 * ((1 - dpr) / 0.4) * 0.4 + impact, 2)

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
