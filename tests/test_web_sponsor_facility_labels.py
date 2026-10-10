"""Sponsor requirements and upgrade feedback name the department players can build."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import economy, facilities, new_campaign, sponsors
from esports_sim.web import server


@pytest.mark.parametrize("level", [0, 1, 2])
@pytest.mark.parametrize("reputation", [0, 100])
def test_sponsor_requirements_match_facilities_menu(game_data, level, reputation):
    gs = new_campaign(game_data, seed=2038)
    gs.facilities["marketing_office"] = level
    gs.teams[gs.acting_team_id].reputation = reputation
    token = server._ctx.set(server._ReqCtx(server._Game(game_data, "LABEL", gs=gs), gs.acting_team_id))
    try:
        before = dict(gs.facilities), gs.teams[gs.acting_team_id].balance
        department = next(item for item in server.facilities_view()["facilities"] if item["id"] == "marketing_office")
        slots = server.finances()["slots"]
        assert department["label"] == "Media Department"
        for slot in ("stream", "apparel"):
            cfg = sponsors.SLOT_CONFIG[slot]
            facility_ok = level >= cfg["unlock"]
            assert slots[slot]["unlocked"] == (facility_ok and reputation >= cfg["rep_gate"])
            expected = (
                f"requires {department['label']} level {cfg['unlock']}"
                if not facility_ok else
                f"requires reputation {cfg['rep_gate']:.0f}"
                if reputation < cfg["rep_gate"] else None
            )
            assert slots[slot]["locked_reason"] == expected
        assert (gs.facilities, gs.teams[gs.acting_team_id].balance) == before
    finally:
        server._ctx.reset(token)


@pytest.mark.parametrize("name", economy.FACILITY_NAMES)
def test_upgrade_feedback_matches_menu_and_preserves_history(game_data, name):
    gs = new_campaign(game_data, seed=2038)
    gs.teams[gs.acting_team_id].balance = 1_000_000
    gs.facilities[name] = 0
    gs.push_news("Historical Marketing Office wording")
    history = list(gs.news)
    label = facilities.facility_view(gs, name)["label"]
    for level, cost in [(1, 150_000), (2, 350_000)]:
        balance = gs.teams[gs.acting_team_id].balance
        ok, message = economy.upgrade_facility(gs, name)
        assert ok
        assert message == f"{label} upgraded to level {level}"
        assert gs.facilities[name] == level
        assert gs.teams[gs.acting_team_id].balance == balance - cost
        assert f"upgrade {label} to level {level} ({cost:,} cr)." in gs.news[-1]
        assert gs.news[:len(history)] == history
