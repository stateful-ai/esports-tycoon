"""Pure reconstruction of in-match momentum from the canonical event log."""

from __future__ import annotations

from dataclasses import dataclass

from esports_sim.schemas import Event
from esports_sim.sim import constants as C


@dataclass(frozen=True)
class MomentumRound:
    round_num: int
    values: dict[str, float]


def momentum_trace(events: list[Event], team_of: dict[str, str]) -> list[MomentumRound]:
    """Return each player's momentum after every completed round."""
    players = sorted(team_of)
    momentum = {pid: 0.0 for pid in players}
    rosters: dict[str, set[str]] = {}
    for pid, tid in team_of.items():
        rosters.setdefault(tid, set()).add(pid)
    alive: dict[str, set[str]] = {}
    out: list[MomentumRound] = []
    for event in events:
        if event.type == "round.start":
            alive = {tid: set(pids) for tid, pids in rosters.items()}
        elif event.type == "round.kill":
            if event.killer_id in momentum:
                momentum[event.killer_id] = min(C.MOMENTUM_CAP, momentum[event.killer_id] + C.MOMENTUM_KILL)
            if event.victim_id in momentum:
                momentum[event.victim_id] = max(-C.MOMENTUM_CAP, momentum[event.victim_id] - C.MOMENTUM_DEATH)
            tid = team_of.get(event.victim_id)
            if tid is not None:
                alive.get(tid, set()).discard(event.victim_id)
        elif event.type == "round.end":
            winners_alive = alive.get(event.winner_id, set())
            clutcher = next(iter(winners_alive)) if len(winners_alive) == 1 else None
            for pid in players:
                momentum[pid] *= C.MOMENTUM_DECAY
            if clutcher is not None:
                momentum[clutcher] = min(C.MOMENTUM_CAP, momentum[clutcher] + C.MOMENTUM_CLUTCH)
            out.append(MomentumRound(event.round_num, {pid: round(momentum[pid], 4) for pid in players}))
    return out


def momentum_beat(trace: list[MomentumRound]) -> dict | None:
    """Pick the strongest sustained hot/cold run for compact narration."""
    if not trace:
        return None
    candidates: list[tuple[int, float, str, str, int, int]] = []
    for pid in sorted({pid for row in trace for pid in row.values}):
        for tone, threshold in (("hot", 0.18), ("cold", -0.18)):
            start = None
            peak = 0.0
            sentinel = MomentumRound(0, {pid: 0.0})
            for i, row in enumerate([*trace, sentinel]):
                value = row.values.get(pid, 0.0)
                active = value >= threshold if tone == "hot" else value <= threshold
                if active:
                    start = i if start is None else start
                    peak = max(peak, abs(value))
                elif start is not None:
                    candidates.append((i - start, peak, pid, tone, start, i - 1))
                    start, peak = None, 0.0
    if not candidates:
        return None
    length, peak, pid, tone, start, end = max(candidates, key=lambda c: (c[0], c[1], c[2], c[3] == "hot"))
    return {"player_id": pid, "tone": tone, "rounds": length,
            "start_round": trace[start].round_num, "end_round": trace[end].round_num,
            "peak": round(peak, 2)}
