"""Manager economy/scouting/sponsor depth (loop iteration 2).

All manager-layer — none of it runs inside the match gates, so the golden
and balance stacks are untouched. Guarantees pinned here: debt now has
consequences, analyst quality improves scouting PRECISION (not just speed),
and the sponsor youth objective rewards squad-building.
"""

from __future__ import annotations

from esports_sim.manager import development, economy, sponsors
from esports_sim.manager.state import SponsorObjective, StaffMember
from esports_sim.registry import load_all
from esports_sim.manager import new_campaign


def _campaign(seed: int = 4):
    gd = load_all()
    return gd, new_campaign(gd, seed=seed)


# -- insolvency ---------------------------------------------------------------

def test_debt_penalises_reputation_and_morale_and_warns_user() -> None:
    _, gs = _campaign()
    team = gs.teams[gs.user_team_id]
    team.balance = economy.INSOLVENCY_FLOOR - 50_000  # deep in the red
    rep0 = team.reputation
    mor0 = [p.morale for p in gs.roster(gs.user_team_id)]
    economy.check_solvency(gs)
    assert team.reputation < rep0
    assert all(p.morale <= m0 for p, m0 in zip(gs.roster(gs.user_team_id), mor0))
    assert any("BOARD WARNING" in n for n in gs.news[-3:])


def test_solvent_team_is_untouched() -> None:
    _, gs = _campaign()
    team = gs.teams[gs.user_team_id]
    team.balance = 500_000
    rep0, news0 = team.reputation, len(gs.news)
    economy.check_solvency(gs)
    assert team.reputation == rep0 and len(gs.news) == news0


def test_runway_none_when_net_nonnegative() -> None:
    _, gs = _campaign()
    # A fresh org runs a positive weekly net, so it isn't heading for the floor.
    assert economy.weeks_until_insolvent(gs) is None


def test_runway_ceils_the_crossing_week() -> None:
    """A cushion of 1 credit over a large weekly burn still crosses the floor
    on the next tick — the helper must round the week count up, not truncate
    it to 0."""
    _, gs = _campaign()
    gs.teams[gs.user_team_id].balance = economy.INSOLVENCY_FLOOR + 1
    # A huge staff cost forces a large negative weekly net.
    assert economy.weeks_until_insolvent(gs, staff_cost=10_000_000) == 1


def test_runway_zero_when_already_insolvent() -> None:
    """An org already at or past the floor is insolvent NOW — report 0 even
    if the current run rate is positive (e.g. after cutting payroll), not
    None."""
    _, gs = _campaign()
    gs.teams[gs.user_team_id].balance = economy.INSOLVENCY_FLOOR - 50_000
    # staff_cost 0 -> a fresh org runs a positive net, yet it's already under.
    assert economy.weeks_until_insolvent(gs) == 0


# -- scout precision ----------------------------------------------------------

def test_analyst_never_widens_the_scout_band() -> None:
    """An elite analyst reads more accurately: for the same player and
    progress the band is never WIDER than with no analyst (and at no analyst
    the report is exactly the pre-existing one — multiplier 1.0)."""
    gd, gs = _campaign()
    players = list(gs.players.values())[:12]

    def widths(g):
        out = []
        for p in players:
            for prog in (0.2, 0.5, 0.8):
                r = development.scout_report(g, p, prog)
                out.append(r["ca_stars"][1] - r["ca_stars"][0])
        return out

    none = widths(gs)
    gs.staff["analyst"] = StaffMember(
        id="a", name="Ana Lyst", role="analyst", quality=88.0, salary=5000
    )
    elite = widths(gs)
    assert all(e <= n for e, n in zip(elite, none))
    assert any(e < n for e, n in zip(elite, none)), "analyst never tightened anything"


# -- sponsor youth objective --------------------------------------------------

def test_field_youth_objective_pays_when_under21_rostered() -> None:
    _, gs = _campaign()
    assert "field_youth" in sponsors.OBJECTIVE_LABELS
    # Guarantee a sub-21 talent on the roster.
    gs.roster(gs.user_team_id)[0].age = 20
    obj = SponsorObjective(kind="field_youth", bonus=30_000)
    bal0 = gs.teams[gs.user_team_id].balance
    paid = sponsors._eval_objective(gs, obj, "Kitline")
    assert paid == 30_000 and obj.met is True
    assert gs.teams[gs.user_team_id].balance == bal0 + 30_000


def test_field_youth_stays_pending_for_a_veteran_roster() -> None:
    _, gs = _campaign()
    for p in gs.roster(gs.user_team_id):
        p.age = 27  # no youth
    obj = SponsorObjective(kind="field_youth", bonus=30_000)
    assert sponsors._eval_objective(gs, obj, "Kitline") == 0
    assert obj.met is None  # pending, never a penalty
