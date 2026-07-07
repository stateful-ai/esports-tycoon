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


def compute_match_stats(events: list[Event]) -> MatchStats:
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
        elif e.type == "round.kill":
            k, v = line(e.killer_id), line(e.victim_id)
            k.kills += 1
            v.deaths += 1
            if e.headshot:
                k.headshots += 1
            if e.is_trade:
                k.trade_kills += 1
            if not first_kill_done:
                k.first_kills += 1
                first_kill_done = True
            if current is not None:
                current.kills.append((e.killer_id, e.victim_id, e.weapon_id))
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
