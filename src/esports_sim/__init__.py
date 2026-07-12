"""esports_sim — Valorant-inspired tycoon simulator core.

Design invariants this package enforces:

1. The sim is the source of truth. UI, LLM agents, and RL harnesses are
   consumers over a deterministic event stream.
2. Every stochastic decision goes through an injected RNG derived from a
   seeded `RngTree`. No direct calls to `random.random()` or `time.time()`
   inside sim code. Same seed -> byte-identical event log.
3. Every state mutation emits a typed `Event`. The event log is canonical;
   state is derivable from events.
4. Every available player is queried through `PlayerPolicy` on every live
   tick. A `TeamPolicy` forms round plans, while a `CoachPolicy` may enter
   a live map only through a timeout between rounds. Heuristics (MVP), RL
   agents (later), and LLM playtesters all implement these same interfaces.
"""

__version__ = "0.0.1"
