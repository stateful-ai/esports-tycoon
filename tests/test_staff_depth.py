from __future__ import annotations

import json

from esports_sim.manager import staff, staff_effects
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.state import GameState, StaffMember
from esports_sim.registry import load_all
from esports_sim.schemas.team import TeamTactics


def _coach(
    staff_id: str, rating: float, preferences: dict[str, float], *,
    adaptability: float = 50.0, traits: list[str] | None = None,
) -> StaffMember:
    attributes = {key: rating for key in staff_effects.ATTRIBUTE_LABELS}
    attributes["adaptability"] = adaptability
    return StaffMember(
        id=staff_id,
        name=staff_id,
        role="coach",
        quality=rating,
        salary=1,
        specialty="tactical",
        traits=traits or [],
        attributes=attributes,
        style_identity="pragmatic",
        style_preferences=preferences,
    )


def test_every_tier_one_team_has_a_distinct_concrete_coach() -> None:
    gs = new_campaign(load_all(), seed=8801)
    coaches = [
        gs.staff_by[team_id]["coach"]
        for team_id in sorted(gs.teams)
        if gs.teams[team_id].tier == 1
    ]
    assert len(coaches) == len({coach.id for coach in coaches})
    assert all(set(coach.attributes) == set(staff_effects.ATTRIBUTE_LABELS) for coach in coaches)
    assert all(coach.style_identity in staff_effects.STYLE_ARCHETYPES for coach in coaches)


def test_compatible_lower_overall_coach_can_outperform_mismatched_star() -> None:
    tactics = TeamTactics()
    compatible = _coach(
        "compatible", 75.0,
        {dial: float(getattr(tactics, dial)) for dial in staff_effects.STYLE_ARCHETYPES["pragmatic"]},
        adaptability=75.0,
    )
    mismatched = _coach(
        "mismatched", 82.0,
        {dial: 0.0 for dial in staff_effects.STYLE_ARCHETYPES["pragmatic"]},
        adaptability=50.0,
    )
    assert staff_effects.overall(compatible) < staff_effects.overall(mismatched)
    assert staff_effects.coach_training_multiplier(
        compatible, tactics, None
    ) > staff_effects.coach_training_multiplier(mismatched, tactics, None)


def test_traits_change_only_their_documented_context() -> None:
    tactics = TeamTactics()
    base = _coach("base", 70.0, staff_effects.STYLE_ARCHETYPES["pragmatic"])
    developer = _coach(
        "developer", 70.0, staff_effects.STYLE_ARCHETYPES["pragmatic"],
        traits=["developer"],
    )
    young = type("PlayerStub", (), {"age": 20, "morale": 60.0, "training_intensity": "normal"})()
    veteran = type("PlayerStub", (), {"age": 29, "morale": 60.0, "training_intensity": "normal"})()
    assert staff_effects.coach_player_multiplier(developer, young, tactics) > 1.0
    assert staff_effects.coach_player_multiplier(developer, veteran, tactics) == 1.0
    assert staff_effects.coach_player_multiplier(base, young, tactics) == 1.0


def test_grounded_contributions_unlock_evidence_only_badges() -> None:
    member = StaffMember(
        id="physio", name="Physio", role="physio", quality=70.0, salary=1,
        attributes={key: 70.0 for key in staff_effects.ATTRIBUTE_LABELS},
    )
    gs = new_campaign(load_all(), seed=8802)
    team_id = gs.user_team_id
    gs.staff_by[team_id]["physio"] = member
    staff.add_contribution(gs, team_id, "physio", "stamina_restored", 500.0)
    assert member.badges == ["iron_squad"]
    assert staff_effects.badge_views(member)[0]["label"] == "Iron Squad"


def test_v26_save_migrates_staff_profiles_deterministically(tmp_path) -> None:
    gs = new_campaign(load_all(), seed=8803)
    raw = gs.model_dump(mode="json")
    raw["schema_version"] = 26
    for member in raw["staff_pool"]:
        for field in ("attributes", "style_identity", "style_preferences", "badges", "career_stats"):
            member.pop(field, None)
    for team_staff in raw["staff_by"].values():
        for member in team_staff.values():
            for field in ("attributes", "style_identity", "style_preferences", "badges", "career_stats"):
                member.pop(field, None)
    path = tmp_path / "v26.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    first = GameState.load(path)
    second = GameState.load(path)
    assert first.schema_version == 29
    assert first.model_dump_json() == second.model_dump_json()
    assert all(member.attributes for member in first.staff_pool)


def test_staff_market_serializer_exposes_server_computed_fit_and_comparison() -> None:
    from esports_sim.web import server

    gs = new_campaign(load_all(), seed=8804)
    gs.set_acting(gs.user_team_id)
    candidate = next(member for member in gs.staff_pool if member.role == "coach")
    view = server._staff_member_view(gs, candidate)
    assert view["overall"] == staff_effects.overall(candidate)
    assert view["style"]["fit"] == staff_effects.system_fit(
        candidate, gs.teams[gs.user_team_id].tactics
    )
    assert len(view["attributes_view"]) == 7
    assert set(view["comparison"]) == {
        "current_id", "overall_delta", "fit_delta", "salary_delta",
    }
    assert view["effects"]
