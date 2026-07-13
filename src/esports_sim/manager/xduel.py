from __future__ import annotations
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esports_sim.manager.state import GameState


def calculate_xduel_probability(rating_a: float, rating_b: float) -> float:
    """Win probability using ELO equation with numerical stability clamping."""
    diff = (rating_b - rating_a) / 400.0
    # Clamping diff to avoid overflow/underflow in power calculation
    diff = max(-20.0, min(20.0, diff))
    return 1.0 / (1.0 + 10.0 ** diff)


def calculate_xde(outcome: int, expected_probability: float) -> float:
    """Calculate Expected Duel Edge (xDE) = outcome - expected_probability."""
    return float(outcome) - expected_probability


def accumulate_xde_stats(stats: object, outcome: int, expected_probability: float) -> None:
    """Accumulate actual and expected wins into stats object."""
    stats.expected_wins = getattr(stats, "expected_wins", 0.0) + expected_probability
    stats.actual_wins = getattr(stats, "actual_wins", 0) + outcome


def reset_xde_season(stats: object) -> None:
    """Reset expected/actual duel stats for season rollover."""
    stats.expected_wins = 0.0
    stats.actual_wins = 0


def filter_telemetry_for_save(state_dict: dict) -> dict:
    """Exclude detailed telemetry events from the GameState save."""
    out = dict(state_dict)
    out.pop("telemetry_logs", None)
    return out


def record_telemetry(gs: GameState, event: dict) -> None:
    """Record telemetry event in GameState logs."""
    logs = gs.__dict__.get("telemetry_logs")
    if logs is None:
        logs = []
        object.__setattr__(gs, "telemetry_logs", logs)
    logs.append(event)


def export_season_telemetry(gs: GameState) -> list:
    """Export season telemetry logs."""
    return gs.__dict__.get("telemetry_logs", [])


def simulate_duel_with_telemetry(gs: GameState, shooter_id: str, target_id: str, events_out: list | None = None) -> str:
    """Simulate duel with deterministic outcome and log telemetry event."""
    h = hashlib.md5(f"duel_{shooter_id}_{target_id}_{getattr(gs, 'seed', 42)}".encode()).digest()
    winner = shooter_id if (h[0] % 2 == 0) else target_id

    event = {
        "event_type": "duel_telemetry",
        "attacker_id": shooter_id,
        "defender_id": target_id,
        "winner_id": winner,
    }

    if events_out is not None:
        events_out.append(event)

    record_telemetry(gs, event)

    return winner
