"""Your own fixtures are always yours to see, whatever tier you play in.

`/api/schedule` broadcasts tier-1 only, on purpose: tier 2 plays but is not
covered, and its results reach you through standings, stats and scout reports
instead. That rule is about OTHER clubs. Applied to your own team it emptied
the one screen whose entire job is "when do I play and who" -- a synthetic
player managing a tier-2 club opened Season > Fixtures on its default
"My matches" filter and got "No fixtures match this filter" for eleven weeks
and ten played matches. The client filters `mine` over whatever the server
sent, so a fixture stripped server-side can never come back.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

import esports_sim.web.server as server_mod
from esports_sim.manager import new_campaign
from esports_sim.registry import GameData


def _tier2_campaign(game_data: GameData):
    """A campaign whose user manages a tier-2 club, or a skip if none exists."""
    gs = new_campaign(game_data, seed=2026, user_team_id="team_nexus")
    tier2 = sorted(tid for tid, team in gs.teams.items() if team.tier == 2)
    if not tier2:
        pytest.skip("this world has no tier-2 clubs")
    return gs, tier2[0]


@pytest.mark.web
def test_a_tier2_manager_can_see_their_own_fixtures(game_data: GameData) -> None:
    gs, me = _tier2_campaign(game_data)
    game = server_mod._Game(game_data, "TIER2", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, me))

    played = [f for f in gs.fixtures if me in (f.team_a, f.team_b)]
    assert played, "the fixture generator gave this tier-2 club no games at all"

    shown = server_mod.schedule()["fixtures"]
    mine = [f for f in shown if me in (f["team_a"], f["team_b"])]
    assert mine, (
        "Season > Fixtures serves a tier-2 manager nothing about their own "
        "season — the client's 'My matches' filter reads this payload, so a "
        "fixture dropped here is unreachable in the UI."
    )
    assert len(mine) == len(played), (
        f"only {len(mine)} of this club's {len(played)} fixtures were served"
    )


@pytest.mark.web
def test_tier2_is_still_unbroadcast_for_everyone_else(game_data: GameData) -> None:
    """The fix must not turn the fixture list into a full tier-2 broadcast."""
    gs, me = _tier2_campaign(game_data)
    game = server_mod._Game(game_data, "TIER2", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, me))

    by_id = {f.id: f for f in gs.fixtures}
    others = [
        f for f in server_mod.schedule()["fixtures"]
        if me not in (f["team_a"], f["team_b"]) and by_id[f["id"]].tier == 2
    ]
    assert not others, (
        f"{len(others)} tier-2 fixtures for other clubs leaked into the "
        "broadcast list; only your own club is exempt from the tier-1 rule."
    )


@pytest.mark.web
def test_a_tier1_manager_sees_the_same_list_as_before(game_data: GameData) -> None:
    """A tier-1 manager's payload is unchanged: every fixture served is tier 1."""
    gs = new_campaign(game_data, seed=2026, user_team_id="team_nexus")
    assert gs.teams["team_nexus"].tier == 1, "test assumes team_nexus is tier 1"
    game = server_mod._Game(game_data, "TIER1", gs=gs)
    server_mod._ctx.set(server_mod._ReqCtx(game, "team_nexus"))

    by_id = {f.id: f for f in gs.fixtures}
    served = server_mod.schedule()["fixtures"]
    assert served, "a tier-1 manager should see a fixture list"
    assert all(by_id[f["id"]].tier == 1 for f in served)
