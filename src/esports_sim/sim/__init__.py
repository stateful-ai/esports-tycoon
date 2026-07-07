"""Match simulation. `simulate_match` is the stable entry point; the
engine internals are free to change behind it."""

from esports_sim.sim.engine import MatchResult, simulate_match, simulate_match_result

__all__ = ["MatchResult", "simulate_match", "simulate_match_result"]
