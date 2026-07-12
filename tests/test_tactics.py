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
from esports_sim.sim import constants as C
from esports_sim.sim import tactics_fit

A, B, MAP = "team_nexus", "team_vanguard", "lotus"  # 2 entries/site, 3 mids


def test_counter_strat_is_signed_bounded_and_override_only() -> None:
    opponent = TeamTactics(
        aggression=90.0, pace=90.0, util_discipline=90.0, map_control=90.0
    )
    assert tactics_fit.counter_strat_edge({}, opponent) == 0.0
    assert tactics_fit.counter_strat_edge(
        {dial: 50.0 for dial in tactics_fit.COUNTER_DIALS}, opponent
    ) == 0.0

    correct = tactics_fit.counter_strat_edge(
        {dial: 0.0 for dial in tactics_fit.COUNTER_DIALS}, opponent
    )
    mirror = tactics_fit.counter_strat_edge(
        {dial: 100.0 for dial in tactics_fit.COUNTER_DIALS}, opponent
    )
    assert correct > 0.0
    assert mirror == -correct

    extreme = TeamTactics(
        aggression=100.0, pace=100.0, util_discipline=100.0, map_control=100.0
    )
    assert tactics_fit.counter_strat_edge(
        {dial: 0.0 for dial in tactics_fit.COUNTER_DIALS}, extreme
    ) == C.COUNTER_STRAT_CAP


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
    for dial in ("aggression", "pace", "util_discipline", "eco_greed", "map_control"):
        hi = _hash(range(8), **{dial: 100.0})
        lo = _hash(range(8), **{dial: 0.0})
        assert hi != base, f"{dial}=100 did not change the match log"
        assert lo != base, f"{dial}=0 did not change the match log"


def test_under_gunned_reads_loadout_not_credits() -> None:
    """The eco tempo shift must key off the actual loadout, not the credit-
    based buy call: a team carrying rifles through a broke round is on a gun
    round, not an eco."""
    from esports_sim.sim import engine as eng

    gd = load_all()
    sim = eng._MatchSim(gd, A, B, "haven", 1)
    rifle = next(w.id for w in gd.weapons.values() if str(w.weapon_class) == "rifle")
    pistol = next(w.id for w in gd.weapons.values() if str(w.weapon_class) == "pistol")
    # Rifles in hand but near-zero cash (survived a lost round) -> gun round.
    for pid in sim.roster[A]:
        sim.p[pid].weapon = rifle
        sim.p[pid].credits = 100
    assert sim._under_gunned(A) is False
    # Stripped back to pistols -> genuine eco.
    for pid in sim.roster[A]:
        sim.p[pid].weapon = pistol
    assert sim._under_gunned(A) is True


def test_eco_tempo_skips_pistol_and_gun_rounds() -> None:
    """The eco tempo shift only fires on a genuine save/force round: never
    on a pistol round (fixed loadout by rule), never on a gun round (rifles
    in hand), and never at neutral eco_greed."""
    from esports_sim.sim import engine as eng

    gd = load_all()
    sim = eng._MatchSim(gd, A, B, "haven", 1)
    pistol = next(w.id for w in gd.weapons.values() if str(w.weapon_class) == "pistol")
    rifle = next(w.id for w in gd.weapons.values() if str(w.weapon_class) == "rifle")
    for pid in sim.roster[A]:
        sim.p[pid].weapon = pistol  # under-gunned by loadout

    gd.teams[A].tactics.eco_greed = 100.0
    # Pistol rounds (1 and 13) are excluded even though under-gunned + greedy.
    assert sim._eco_tempo_shift(A, 1) == 0.0
    assert sim._eco_tempo_shift(A, 13) == 0.0
    # A genuine eco round shifts.
    assert sim._eco_tempo_shift(A, 4) > 0.0
    # Neutral eco_greed is a no-op.
    gd.teams[A].tactics.eco_greed = 50.0
    assert sim._eco_tempo_shift(A, 4) == 0.0
    # Rifles in hand -> gun round, no shift.
    gd.teams[A].tactics.eco_greed = 100.0
    for pid in sim.roster[A]:
        sim.p[pid].weapon = rifle
    assert sim._eco_tempo_shift(A, 4) == 0.0


def test_execution_mod_zero_at_neutral_and_scales_with_chemistry() -> None:
    """The roster/chemistry execution modifier must vanish at neutral
    tactics (so it can't touch the golden or balance gates) and, once a
    complex system is dialled in, a high-chemistry team executes it better
    than a low-chemistry one."""
    from esports_sim.sim import engine as eng

    gd = load_all()
    neutral = eng._MatchSim(gd, A, B, "haven", 1)
    assert neutral.exec_mod[A] == 0.0 and neutral.exec_mod[B] == 0.0

    gd.teams[A].tactics.map_control = 100.0  # coordination-heavy system
    gd.teams[A].chemistry = 100.0
    high_chem = eng._MatchSim(gd, A, B, "haven", 1)._execution_mod(A)
    gd.teams[A].chemistry = 20.0
    low_chem = eng._MatchSim(gd, A, B, "haven", 1)._execution_mod(A)
    assert high_chem > low_chem

    # The SIMPLE side of the dials (stack tight / dump utility) is not a
    # coordinated system, so chemistry must not swing it either way.
    gd.teams[A].tactics.map_control = 0.0
    gd.teams[A].tactics.util_discipline = 0.0
    gd.teams[A].chemistry = 100.0
    simple_hi = eng._MatchSim(gd, A, B, "haven", 1)._execution_mod(A)
    gd.teams[A].chemistry = 20.0
    simple_lo = eng._MatchSim(gd, A, B, "haven", 1)._execution_mod(A)
    assert simple_hi == simple_lo


def test_misfit_players_drag_execution_fit() -> None:
    """Running an extreme system is a real trade-off, not a free bonus:
    a team-mate below the fit baseline must subtract MORE than an equally
    good fit adds, so a couple of stars can't average away the players who
    can't run the system. Without this, any above-average roster gets a
    positive edge at every extreme and cranking every dial is strictly best."""
    from esports_sim.sim import constants as C
    from esports_sim.sim import tactics_fit as tf

    base = C.EXEC_FIT_BASELINE
    hi, lo = base + 20.0, base - 20.0

    # A roster sitting exactly on the baseline is a no-op either way.
    assert tf.fit_edge([base] * 5) == 0.0

    # Same MEAN as that flat roster (== baseline), but split into stars and
    # scrubs: the penalty amplifies the below-baseline players, so the
    # high-variance book nets NEGATIVE — an extreme identity misfires.
    assert tf.fit_edge([hi, hi, lo, lo, base]) < 0.0

    # Better rosters still earn a positive edge (we didn't kill the upside),
    # and a strictly stronger roster fits strictly better.
    assert tf.fit_edge([70.0] * 5) > tf.fit_edge([60.0] * 5) > 0.0


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


def test_eco_greed_drives_retake_commitment() -> None:
    """A greedy book values the round over the rifles and commits retakes
    even a body down; a thrifty book concedes to save weapons. More retake
    commitment shows up as more defuse attempts reaching the spike."""
    seeds = range(60)
    defuses = lambda g: _count(seeds, "round.spike_defuse", eco_greed=g)  # noqa: E731
    assert defuses(100.0) > defuses(0.0)


def test_passive_defense_sets_up_differently_than_aggressive() -> None:
    """The aggression setup dial is two-sided: a passive book anchors the
    site, an aggressive book holds forward on the overlooks — the two must
    produce distinct logs (and neither equals neutral)."""
    passive = _hash(range(8), aggression=20.0)
    aggressive = _hash(range(8), aggression=80.0)
    neutral = _hash(range(8))
    assert passive != aggressive
    assert passive != neutral and aggressive != neutral


def test_lurker_strikes_the_site(monkeypatch) -> None:
    """map_control spread doesn't just park a lurker — once the hit lands
    the lurker peels off its flank and strikes the site as a second wave.
    Assert those strike orders actually fire."""
    from esports_sim.sim import engine as eng

    strikes = 0
    orig = eng._MatchSim._order

    def spy(self, pid, order):
        nonlocal strikes
        if pid in self._lurkers and order.startswith("goto:"):
            c = self.map.callouts.get(order.split(":", 1)[1])
            if c is not None and str(c.zone) == "site":
                strikes += 1
        return orig(self, pid, order)

    monkeypatch.setattr(eng._MatchSim, "_order", spy)
    for s in range(30):
        _sim(s, map_control=100.0)
    assert strikes > 0, "map_control lurkers never struck the site"


def test_lurk_strike_held_while_hit_not_live() -> None:
    """The strike must be gated on a live execute: if a hit aborts and
    re-defaults (went -> False), the armed lurker is NOT sent into the site
    alone during the regroup. Only the `went` flag should flip the gate;
    all other conditions are held equal."""
    from esports_sim.sim import engine as eng

    gd = load_all()
    sim = eng._MatchSim(gd, A, B, "ascent", 0)
    lurker = sorted(gd.teams[A].player_ids)[0]
    sim._lurkers = {lurker}
    # armed (lurk_strike reached), spike not planted, a lurker present:
    assert sim._lurk_strike_due(10, 30, went=True, spike_planted=False) is True
    assert sim._lurk_strike_due(10, 30, went=False, spike_planted=False) is False
    # never strike once the spike is down, or before the timer, or unarmed:
    assert sim._lurk_strike_due(10, 30, went=True, spike_planted=True) is False
    assert sim._lurk_strike_due(10, 5, went=True, spike_planted=False) is False
    assert sim._lurk_strike_due(-1, 30, went=True, spike_planted=False) is False
    sim._lurkers = set()
    assert sim._lurk_strike_due(10, 30, went=True, spike_planted=False) is False


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
    """A fresh spike carrier who fetched a dropped spike must be moving,
    on-site, or ordered toward site once the execute is live — never parked
    at an off-site pickup spot, which stalls the round to a time loss. This
    guards BOTH the neutral case (any carrier) and the lurker case. Verified
    to fire thousands of ticks at neutral if the on-pickup re-route is
    removed."""
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
    for s in range(30):
        _sim(s)  # neutral: the general carrier case
        _sim(s, map_control=100.0)  # lurker case
    assert stalls == 0, f"spike carrier parked off-site during execute ({stalls} ticks)"
