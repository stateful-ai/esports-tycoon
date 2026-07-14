"""Upgradeable club infrastructure views.

Facility levels and their mechanical effects remain owned by ``economy`` and
``staff``. This module gives every consumer one server-side description of
the current and next level so the web menu can be interactive without
reimplementing campaign formulas in JavaScript.
"""

from __future__ import annotations

from typing import Any

from esports_sim.manager import economy, staff, staff_effects
from esports_sim.manager.state import GameState


FACILITY_ORDER: tuple[str, ...] = (
    "training_center",
    "analytics_suite",
    "marketing_office",
    "recovery_suite",
    "strategy_lab",
    "team_house",
)

_SPECS: dict[str, dict[str, Any]] = {
    "training_center": {
        "label": "Training Centre",
        "description": (
            "A purpose-built practice wing that improves weekly player "
            "development and gives the coaching staff better tools."
        ),
        "operator_role": "coach",
        "operator_label": "Coach",
        "level_names": (
            "Unbuilt",
            "Practice Lab",
            "Performance Centre",
            "Elite Training Campus",
        ),
    },
    "analytics_suite": {
        "label": "VOD Review Room",
        "description": (
            "Screens, servers, and review stations improve your Analyst's "
            "scouting throughput and unlock deeper performance reporting."
        ),
        "operator_role": "analyst",
        "operator_label": "Analyst",
        "level_names": (
            "Unbuilt",
            "VOD Review Room",
            "Data Lab",
            "Analysis Theatre",
        ),
    },
    "marketing_office": {
        "label": "Media Department",
        "description": (
            "A commercial and content wing that improves sponsor value and "
            "opens new partnership categories."
        ),
        "operator_role": None,
        "operator_label": "Commercial team",
        "level_names": (
            "Unbuilt",
            "Content Desk",
            "Media Studio",
            "Brand Campus",
        ),
    },
    "recovery_suite": {
        "label": "Recovery Suite",
        "description": (
            "Sports-science equipment and treatment space restore player "
            "condition every week, whether or not a Physio is on staff."
        ),
        "operator_role": "physio",
        "operator_label": "Physio",
        "level_names": (
            "Unbuilt",
            "Treatment Room",
            "Sports Science Lab",
            "High Performance Unit",
        ),
    },
    "strategy_lab": {
        "label": "Strategy Lab",
        "description": (
            "Dedicated tactical workstations make scheduled preparation more "
            "productive while reducing its physical load on the roster."
        ),
        "operator_role": "coach",
        "operator_label": "Coach",
        "level_names": (
            "Unbuilt",
            "Tactics Room",
            "Simulation Lab",
            "Competitive Intelligence Unit",
        ),
    },
    "team_house": {
        "label": "Team House",
        "description": (
            "Shared living and wellbeing space helps struggling players recover "
            "confidence and morale toward a stable baseline each week."
        ),
        "operator_role": "psychologist",
        "operator_label": "Psychologist",
        "level_names": (
            "Unbuilt",
            "Player Lounge",
            "Team Residence",
            "Wellbeing Campus",
        ),
    },
}


def _effect_lines(gs: GameState, name: str, level: int) -> list[dict[str, str]]:
    """Structured, display-ready effects at one concrete level."""
    level = max(0, min(economy.FACILITY_MAX_LEVEL, level))
    if name == "training_center":
        return [
            {
                "label": "Weekly development",
                "value": f"+{level * 6}%",
                "detail": "Applied after coaching and training-plan effects.",
            }
        ]
    if name == "analytics_suite":
        hired = gs.staff_by.get(gs.acting_team_id, {})
        tier = staff.analytics_tier_for(hired.get("analyst"), level)
        return [
            {
                "label": "Analyst scouting efficiency",
                "value": f"+{level * 8}%",
                "detail": "Multiplies weekly scouting progress.",
            },
            {
                "label": "Reporting access",
                "value": f"Tier {tier}/3",
                "detail": staff.ANALYTICS_TIER_LABEL[tier],
            },
        ]
    if name == "marketing_office":
        access = "Standard sponsor slots"
        if level == 1:
            access = "Stream partnerships unlocked"
        elif level >= 2:
            access = "Stream and apparel partnerships unlocked"
        return [
            {
                "label": "Sponsor offer value",
                "value": f"+{level * 5}%",
                "detail": "Applied to generated sponsorship terms.",
            },
            {
                "label": "Commercial access",
                "value": access,
                "detail": "New sponsor categories stay subject to reputation gates.",
            },
        ]
    if name == "recovery_suite":
        recovery = economy.FACILITY_RECOVERY_PER_LEVEL * level
        return [
            {
                "label": "Weekly stamina recovery",
                "value": f"+{recovery:g}",
                "detail": "Applied to every rostered player after staff recovery.",
            }
        ]
    if name == "strategy_lab":
        knowledge = int(economy.FACILITY_PREP_KNOWLEDGE_PER_LEVEL * level * 100)
        stamina = economy.FACILITY_PREP_STAMINA_REDUCTION_PER_LEVEL * level
        return [
            {
                "label": "Preparation knowledge",
                "value": f"+{knowledge}%",
                "detail": "Multiplies knowledge earned from scheduled preparation.",
            },
            {
                "label": "Preparation stamina cost",
                "value": f"-{stamina:g}" if stamina else "0",
                "detail": "Reduces condition spent by each session participant.",
            },
        ]
    if name == "team_house":
        wellbeing = economy.FACILITY_WELLBEING_PER_LEVEL * level
        return [
            {
                "label": "Confidence recovery",
                "value": f"+{wellbeing:g}/wk",
                "detail": "Pulls confidence toward 50, never above it.",
            },
            {
                "label": "Morale recovery",
                "value": f"+{wellbeing:g}/wk",
                "detail": "Pulls morale toward 50, never above it.",
            },
        ]
    raise ValueError(f"unknown facility {name}")


def facility_view(gs: GameState, name: str) -> dict[str, Any]:
    """Return one exact, mutation-free facility menu contract."""
    if name not in _SPECS:
        raise ValueError(f"unknown facility {name}")
    spec = _SPECS[name]
    owned = gs.facilities_by.get(gs.acting_team_id, {})
    hired = gs.staff_by.get(gs.acting_team_id, {})
    level = max(0, min(economy.FACILITY_MAX_LEVEL, owned.get(name, 0)))
    next_level = level + 1 if level < economy.FACILITY_MAX_LEVEL else None
    next_cost = economy.facility_upgrade_cost(level)
    per_level_upkeep = economy.FACILITY_UPKEEP_PER_LEVEL[name]
    role = spec["operator_role"]
    member = hired.get(role) if role else None
    operator = None
    if member is not None:
        operator = {
            "id": member.id,
            "name": member.name,
            "role": member.role,
            "effectiveness": round(staff_effects.role_effect_score(member), 1),
        }
    operator_detail = (
        f"{operator['effectiveness']} effectiveness"
        if operator is not None
        else f"No {spec['operator_label']} hired"
        if role
        else "Club commercial operations"
    )
    return {
        "id": name,
        "label": spec["label"],
        "description": spec["description"],
        "level": level,
        "max_level": economy.FACILITY_MAX_LEVEL,
        "level_name": spec["level_names"][level],
        "status": (
            "Max level"
            if next_level is None
            else "Operational"
            if level
            else "Planned"
        ),
        "operator_label": spec["operator_label"],
        "operator": operator,
        "operator_detail": operator_detail,
        "current_effects": _effect_lines(gs, name, level),
        "next_level": next_level,
        "next_level_name": spec["level_names"][next_level] if next_level else None,
        "next_effects": _effect_lines(gs, name, next_level) if next_level else [],
        "next_cost": next_cost,
        "current_upkeep": per_level_upkeep * level,
        "next_upkeep": per_level_upkeep * next_level if next_level else None,
        "affordable": next_cost is not None
        and gs.teams[gs.acting_team_id].balance >= next_cost,
        "maxed": next_level is None,
    }


def menu_view(gs: GameState) -> dict[str, Any]:
    """The complete facilities-menu payload for the acting manager."""
    team = gs.teams[gs.acting_team_id]
    owned = gs.facilities_by.get(gs.acting_team_id, {})
    views = [facility_view(gs, name) for name in FACILITY_ORDER]
    return {
        "balance": team.balance,
        "total_upkeep": economy.facility_weekly_upkeep(owned),
        "built_count": sum(view["level"] > 0 for view in views),
        "total_levels": sum(view["level"] for view in views),
        "facilities": views,
    }
