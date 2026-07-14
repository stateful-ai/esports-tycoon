"""Interactive headquarters facility contracts."""

from __future__ import annotations

import pytest

from esports_sim.manager import campaign as campaign_mod
from esports_sim.manager import facilities, new_campaign, staff
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData


FACILITY_KEYS = {
    "id",
    "label",
    "description",
    "level",
    "max_level",
    "level_name",
    "status",
    "operator_label",
    "operator",
    "operator_detail",
    "current_effects",
    "next_level",
    "next_level_name",
    "next_effects",
    "next_cost",
    "current_upkeep",
    "next_upkeep",
    "affordable",
    "maxed",
}
EFFECT_KEYS = {"label", "value", "detail"}


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=4401)


def test_menu_view_is_exact_and_mutation_free(campaign: GameState) -> None:
    before = campaign.model_dump_json()
    view = facilities.menu_view(campaign)

    assert set(view) == {
        "balance", "total_upkeep", "built_count", "total_levels", "facilities",
    }
    assert [item["id"] for item in view["facilities"]] == list(
        facilities.FACILITY_ORDER
    )
    assert all(set(item) == FACILITY_KEYS for item in view["facilities"])
    assert all(
        set(effect) == EFFECT_KEYS
        for item in view["facilities"]
        for effect in item["current_effects"] + item["next_effects"]
    )
    assert campaign.model_dump_json() == before


def test_vod_room_previews_analyst_efficiency_and_reporting(
    campaign: GameState,
) -> None:
    analyst = next(member for member in campaign.staff_pool if member.role == "analyst")
    campaign.staff["analyst"] = analyst
    campaign.teams[campaign.acting_team_id].balance = 1_000_000

    initial = facilities.facility_view(campaign, "analytics_suite")
    assert initial["label"] == "VOD Review Room"
    assert set(initial["operator"]) == {"id", "name", "role", "effectiveness"}
    assert initial["operator"]["id"] == analyst.id
    assert initial["operator"]["name"] == analyst.name
    assert initial["operator"]["role"] == "analyst"
    assert initial["operator"]["effectiveness"] > 0
    assert initial["operator_detail"].endswith(" effectiveness")
    assert initial["affordable"] is True
    assert initial["next_effects"][0]["value"] == "+8%"

    campaign.facilities["analytics_suite"] = 2
    upgraded = facilities.facility_view(campaign, "analytics_suite")
    assert upgraded["level_name"] == "Data Lab"
    assert upgraded["current_effects"][0]["value"] == "+16%"
    assert upgraded["current_effects"][1]["value"] == (
        f"Tier {staff.analytics_tier(campaign)}/3"
    )
    assert upgraded["next_effects"][0]["value"] == "+24%"


def test_maxed_facility_has_no_phantom_upgrade(campaign: GameState) -> None:
    campaign.facilities["training_center"] = 3
    view = facilities.facility_view(campaign, "training_center")

    assert view["maxed"] is True
    assert view["status"] == "Max level"
    assert view["next_level"] is None
    assert view["next_level_name"] is None
    assert view["next_effects"] == []
    assert view["next_cost"] is None
    assert view["next_upkeep"] is None
    assert view["affordable"] is False


def test_new_departments_preview_distinct_campaign_benefits(
    campaign: GameState,
) -> None:
    campaign.facilities["recovery_suite"] = 2
    campaign.facilities["strategy_lab"] = 3
    campaign.facilities["team_house"] = 1

    recovery = facilities.facility_view(campaign, "recovery_suite")
    strategy = facilities.facility_view(campaign, "strategy_lab")
    wellbeing = facilities.facility_view(campaign, "team_house")

    assert recovery["current_effects"][0]["value"] == "+3"
    assert [effect["value"] for effect in strategy["current_effects"]] == [
        "+30%", "-1.5",
    ]
    assert [effect["value"] for effect in wellbeing["current_effects"]] == [
        "+0.5/wk", "+0.5/wk",
    ]
    assert recovery["current_upkeep"] == 3_400
    assert strategy["current_upkeep"] == 7_500


def test_recovery_and_team_house_apply_bounded_weekly_support(
    campaign: GameState,
) -> None:
    team_id = campaign.user_team_id
    campaign.staff_by[team_id] = {}
    campaign.facilities_by[team_id] = {"recovery_suite": 2, "team_house": 2}
    for player in campaign.roster(team_id):
        player.stamina = 60.0
        player.confidence = 40.0
        player.morale = 40.0

    campaign_mod._apply_backroom_effects(campaign)

    assert all(player.stamina == 63.0 for player in campaign.roster(team_id))
    assert all(player.confidence == 41.0 for player in campaign.roster(team_id))
    assert all(player.morale == 41.0 for player in campaign.roster(team_id))
