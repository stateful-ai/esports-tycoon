"""Tactics reach: the coaching dials must actually bend the match micro.

Two guarantees are pinned here:

1. Neutral (50) is an exact no-op — the whole balance/golden gate stack is
   measured at neutral, so every tactic term has to vanish there.
2. Each micro dial is genuinely wired into the engine and moves its signal
   in the right direction (aggressive teams refrag more, disciplined teams
   hold utility, spread teams peel a lurker off the hit).

If a future engine refactor silently severs a dial from the sim, one of
these fails long before it reaches a player.
"""

from __future__ import annotations

import hashlib

from esports_sim.registry import load_all
from esports_sim.schemas.team import TeamTactics
from esports_sim.sim import simulate_match

A, B, MAP = "team_nexus", "team_vanguard", "lotus"  # 2 entries/site, 3 mids


def _sim(seed: int, **dials):
    """One match log with the user team's dials set to `dials`."""
    gd = load_all()
    tac = gd.teams[A].tactics
    for k, v in dials.items():
        setattr(tac, k, v)
    return simulate_match(gd, A, B, MAP, seed)


def _hash(seeds, **dials) -> str:
    h = hashlib.sha256()
    for s in seeds:
        for e in _sim(s, **dials):
            h.update(e.model_dump_json().encode())
    return h.hexdigest()


def _count(seeds, etype, pred=lambda e: True, **dials) -> int:
    n = 0
    for s in seeds:
        for e in _sim(s, **dials):
            if e.type == etype and pred(e):
                n += 1
    return n


def test_explicit_neutral_equals_default() -> None:
    """Setting every dial to 50 by hand reproduces the default log."""
    neutral = TeamTactics().model_dump()
    assert all(
        v == 50.0 for k, v in neutral.items() if k != "site_focus"
    )
    default_log = _hash(range(6))
    explicit_log = _hash(range(6), aggression=50.0, pace=50.0,
                         util_discipline=50.0, eco_greed=50.0, map_control=50.0)
    assert default_log == explicit_log


def test_each_micro_dial_is_wired() -> None:
    """Cranking any single micro dial off neutral must change the log —
    otherwise the engine isn't reading it."""
    base = _hash(range(8))
    for dial in ("aggression", "pace", "util_discipline", "map_control"):
        hi = _hash(range(8), **{dial: 100.0})
        lo = _hash(range(8), **{dial: 0.0})
        assert hi != base, f"{dial}=100 did not change the match log"
        assert lo != base, f"{dial}=0 did not change the match log"


def test_aggression_increases_refrags() -> None:
    """Aggressive teams stack tight and trade harder."""
    seeds = range(40)
    trades = lambda a: _count(  # noqa: E731
        seeds, "round.kill", lambda e: getattr(e, "is_trade", False), aggression=a
    )
    assert trades(100.0) > trades(0.0)


def test_discipline_holds_utility() -> None:
    """Disciplined books throw less utility on the hit (saved for retakes
    and swings); dump-it-all books burn more."""
    seeds = range(40)
    util = lambda d: _count(seeds, "round.utility_used", util_discipline=d)  # noqa: E731
    assert util(100.0) < util(0.0)


def test_lurker_that_grabs_spike_rejoins_the_hit(monkeypatch) -> None:
    """A lurker who picks up a dropped spike must abandon the lurk role and
    rejoin the hit — otherwise the team would execute without the spike and
    lose on time. Guard the invariant at ordering time across a spread
    (map_control=100) sweep, where lurkers are common. Verified to fire
    ~hundreds of times if the clear-on-pickup is removed."""
    from esports_sim.sim import engine as eng

    violations = 0
    orig = eng._MatchSim._update_orders

    def checkpoint(self, *a, **k):
        nonlocal violations
        if any(self.p[q].has_spike for q in self._lurkers):
            violations += 1
        return orig(self, *a, **k)

    monkeypatch.setattr(eng._MatchSim, "_update_orders", checkpoint)
    for s in range(40):
        _sim(s, map_control=100.0)
    assert violations == 0, f"a lurker held the spike at ordering time ({violations} ticks)"


def test_spike_carrier_never_parks_off_site_mid_execute(monkeypatch) -> None:
    """A fresh spike carrier (e.g. an ex-lurker who fetched a dropped spike)
    must be moving, on-site, or ordered toward site once the execute is
    live — never parked at an off-site pickup spot, which would stall the
    round out to a time loss. Verified to fire ~200 ticks if the on-pickup
    site re-route is removed."""
    from esports_sim.sim import engine as eng

    stalls = 0
    orig = eng._MatchSim._update_orders

    def checkpoint(self, tick, alive_atk, alive_dfn, target_site, spike_planted,
                   planted_at, plant_tick, went, rotate_at, post_plant_spots):
        nonlocal stalls
        if went and not spike_planted:
            site_cs = set(self._site_callouts(target_site))
            for q in alive_atk:
                ps = self.p[q]
                if not ps.has_spike:
                    continue
                moving = ps.move_eta >= 0
                on_site = ps.callout in site_cs
                to_site = ps.order.startswith("goto:") and ps.order.split(":", 1)[1] in site_cs
                if not (moving or on_site or to_site or ps.order == "plant"):
                    stalls += 1
        return orig(self, tick, alive_atk, alive_dfn, target_site, spike_planted,
                    planted_at, plant_tick, went, rotate_at, post_plant_spots)

    monkeypatch.setattr(eng._MatchSim, "_update_orders", checkpoint)
    for s in range(40):
        _sim(s, map_control=100.0)
    assert stalls == 0, f"spike carrier parked off-site during execute ({stalls} ticks)"
