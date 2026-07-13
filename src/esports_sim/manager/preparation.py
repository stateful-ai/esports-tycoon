"""Deterministic scrim and bootcamp preparation.

Preparation is a campaign-layer decision made against one upcoming fixture.
It produces a grounded report, spends player condition, and grows the existing
organizational-knowledge stock.  The match engine remains unaware of scrims:
knowledge pays off through the established game-plan prep edge.

The module deliberately does not import ``GameState`` at runtime.  State owns
the persisted ``PrepPlan``/``PrepReport`` models and can therefore import them
without creating a cycle.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from esports_sim.manager.state import Fixture, GameState, TeamMapStats


PrepObjective = Literal["anti_exec", "retakes", "lineup_test", "mental_reset"]
PrepIntensity = Literal["light", "normal", "intense"]

OBJECTIVES: tuple[str, ...] = (
    "anti_exec",
    "retakes",
    "lineup_test",
    "mental_reset",
)
INTENSITIES: tuple[str, ...] = ("light", "normal", "intense")

_STAMINA_COST = {"light": 1.5, "normal": 4.0, "intense": 7.5}
_KNOWLEDGE_BASE = {"light": 1.0, "normal": 1.7, "intense": 2.5}
_CAP = 100.0


class PrepPlan(BaseModel):
    """One team's current preparation booking (at most one per team)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    team_id: str
    fixture_id: str
    opponent_id: str
    partner_id: str
    map_id: str
    objective: PrepObjective
    intensity: PrepIntensity
    created_season: int
    created_week: int


class PrepEvidence(BaseModel):
    """Numbers behind the finding, stored so UI copy never invents a fact."""

    model_config = ConfigDict(extra="forbid")

    own_map_samples: int = 0
    opponent_map_samples: int = 0
    partner_map_samples: int = 0
    own_attack_win_pct: float = 0.0
    own_defense_win_pct: float = 0.0
    opponent_attack_win_pct: float = 0.0
    opponent_defense_win_pct: float = 0.0
    partner_map_win_pct: float = 0.0
    scouting_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    average_stamina: float = Field(default=0.0, ge=0.0, le=100.0)
    average_morale: float = Field(default=0.0, ge=0.0, le=100.0)
    rotation_candidate_id: str = ""


class PrepReport(BaseModel):
    """Latest completed/cancelled preparation report for one team."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    team_id: str
    fixture_id: str
    opponent_id: str
    partner_id: str
    map_id: str
    objective: PrepObjective
    intensity: PrepIntensity
    season: int
    week: int
    status: Literal["completed", "cancelled"] = "completed"
    finding_code: str = ""
    finding: str = ""
    evidence: PrepEvidence = Field(default_factory=PrepEvidence)
    participant_ids: list[str] = Field(default_factory=list)
    knowledge_key: str = ""
    knowledge_gain: float = 0.0
    stamina_cost: float = 0.0
    morale_delta: float = 0.0
    chemistry_delta: float = 0.0


def _stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.blake2b(raw, digest_size=8).hexdigest()


def _fixture(gs: "GameState", fixture_id: str) -> "Fixture | None":
    return next((f for f in gs.fixtures if f.id == fixture_id), None)


def _opponent(fixture: "Fixture", team_id: str) -> str:
    return fixture.team_b if fixture.team_a == team_id else fixture.team_a


def schedule(
    gs: "GameState",
    team_id: str,
    fixture_id: str,
    partner_id: str,
    map_id: str,
    objective: str,
    intensity: str,
) -> PrepPlan:
    """Book preparation for an upcoming fixture, replacing any prior plan.

    A scrim opponent cannot be the team being prepared for: that would make
    the report's anti-strat premise nonsensical and hand private preparation
    to the opponent.  The selected map must be in the fixture's planned pool.
    """
    if team_id not in gs.teams:
        raise ValueError(f"unknown team {team_id!r}")
    fixture = _fixture(gs, fixture_id)
    if fixture is None:
        raise ValueError(f"unknown fixture {fixture_id!r}")
    if team_id not in (fixture.team_a, fixture.team_b):
        raise ValueError("team is not in that fixture")
    if fixture.played or fixture.week < gs.week:
        raise ValueError("fixture has already been played")
    opponent_id = _opponent(fixture, team_id)
    if partner_id not in gs.teams:
        raise ValueError(f"unknown preparation partner {partner_id!r}")
    if partner_id in (team_id, opponent_id):
        raise ValueError("preparation partner must be a third team")
    if not gs.teams[partner_id].player_ids:
        raise ValueError("preparation partner has no roster")
    if map_id not in fixture.maps:
        raise ValueError("preparation map is not in the fixture map pool")
    if objective not in OBJECTIVES:
        raise ValueError(f"unknown preparation objective {objective!r}")
    if intensity not in INTENSITIES:
        raise ValueError(f"unknown preparation intensity {intensity!r}")

    plan = PrepPlan(
        id=_stable_id(
            gs.seed,
            gs.season,
            gs.week,
            team_id,
            fixture_id,
            partner_id,
            map_id,
            objective,
            intensity,
        ),
        team_id=team_id,
        fixture_id=fixture_id,
        opponent_id=opponent_id,
        partner_id=partner_id,
        map_id=map_id,
        objective=objective,
        intensity=intensity,
        created_season=gs.season,
        created_week=gs.week,
    )
    gs.preparation_plans_by[team_id] = plan
    return plan


def _rate(stats: "TeamMapStats | None", side: str) -> float:
    if stats is None:
        return 0.0
    won = stats.atk_won if side == "attack" else stats.def_won
    rounds = stats.atk_rounds if side == "attack" else stats.def_rounds
    return round(100.0 * won / max(rounds, 1), 1)


def _map_win_rate(stats: "TeamMapStats | None") -> float:
    if stats is None:
        return 0.0
    return round(100.0 * stats.wins / max(stats.maps, 1), 1)


def _participants(gs: "GameState", team_id: str) -> list[str]:
    """Stable whole-squad practice group; a bootcamp taxes the bench too."""
    return sorted(pid for pid in gs.teams[team_id].player_ids if pid in gs.players)


def _rotation_candidate(gs: "GameState", team_id: str, map_id: str) -> str:
    team = gs.teams[team_id]
    roster = _participants(gs, team_id)
    starters = [pid for pid in team.lineup_ids if pid in roster]
    if len(starters) < min(5, len(roster)):
        starters = sorted(
            roster,
            key=lambda pid: (
                -sum(gs.players[pid].attributes.values())
                / max(len(gs.players[pid].attributes), 1),
                pid,
            ),
        )[:5]
    bench = [pid for pid in roster if pid not in starters]
    if not bench:
        return ""
    return min(
        bench,
        key=lambda pid: (-gs.players[pid].map_mastery(map_id), pid),
    )


def _evidence(gs: "GameState", plan: PrepPlan) -> PrepEvidence:
    own = gs.team_map_stats.get(plan.team_id, {}).get(plan.map_id)
    opp = gs.team_map_stats.get(plan.opponent_id, {}).get(plan.map_id)
    partner = gs.team_map_stats.get(plan.partner_id, {}).get(plan.map_id)
    players = [gs.players[pid] for pid in _participants(gs, plan.team_id)]
    return PrepEvidence(
        own_map_samples=own.maps if own is not None else 0,
        opponent_map_samples=opp.maps if opp is not None else 0,
        partner_map_samples=partner.maps if partner is not None else 0,
        own_attack_win_pct=_rate(own, "attack"),
        own_defense_win_pct=_rate(own, "defense"),
        opponent_attack_win_pct=_rate(opp, "attack"),
        opponent_defense_win_pct=_rate(opp, "defense"),
        partner_map_win_pct=_map_win_rate(partner),
        scouting_confidence=round(
            min(
                1.0,
                max(
                    0.0,
                    gs.scout_progress_by.get(plan.team_id, {}).get(
                        plan.opponent_id, 0.0
                    ),
                ),
            ),
            2,
        ),
        average_stamina=round(
            sum(p.stamina for p in players) / max(len(players), 1), 1
        ),
        average_morale=round(
            sum(p.morale for p in players) / max(len(players), 1), 1
        ),
        rotation_candidate_id=_rotation_candidate(gs, plan.team_id, plan.map_id),
    )


def _finding(plan: PrepPlan, ev: PrepEvidence, variant: int) -> tuple[str, str]:
    """Turn stored evidence into one restrained, auditable conclusion."""
    if plan.objective == "anti_exec":
        if ev.opponent_map_samples == 0:
            return (
                "thin_opponent_sample",
                f"No {plan.map_id} sample exists for the opponent; "
                "the anti-exec read is provisional.",
            )
        if ev.opponent_attack_win_pct >= 55.0:
            return (
                "opponent_attack_pressure",
                f"The opponent has won {ev.opponent_attack_win_pct:.1f}% "
                f"of recorded attack rounds on {plan.map_id}.",
            )
        return (
            "opponent_attack_containable",
            f"The opponent has won {ev.opponent_attack_win_pct:.1f}% "
            f"of recorded attack rounds on {plan.map_id}.",
        )
    if plan.objective == "retakes":
        if ev.own_map_samples == 0:
            return (
                "retake_baseline_needed",
                f"The team has no recorded {plan.map_id} sample; "
                "this session established a retake baseline.",
            )
        if ev.own_defense_win_pct < ev.own_attack_win_pct:
            return (
                "retake_gap",
                f"Defense trails attack on {plan.map_id}, "
                f"{ev.own_defense_win_pct:.1f}% to "
                f"{ev.own_attack_win_pct:.1f}% round wins.",
            )
        return (
            "retake_structure_holds",
            f"Defense is holding at {ev.own_defense_win_pct:.1f}% "
            f"of recorded rounds on {plan.map_id}.",
        )
    if plan.objective == "lineup_test":
        if ev.rotation_candidate_id:
            return (
                "rotation_candidate",
                f"The session identified {ev.rotation_candidate_id} as the "
                f"leading bench option for {plan.map_id}.",
            )
        return (
            "lineup_confirmed",
            f"No eligible bench alternative displaced the current five on {plan.map_id}.",
        )
    if ev.average_morale < 60.0:
        return (
            "morale_risk",
            f"Squad morale entered the reset at {ev.average_morale:.1f}/100.",
        )
    suffix = (
        "with a lighter load"
        if variant == 0
        else "without changing the game plan"
    )
    return (
        "composure_ready",
        f"Squad morale entered at {ev.average_morale:.1f}/100; the group reset {suffix}.",
    )


def _knowledge_key(plan: PrepPlan) -> str:
    if plan.objective == "anti_exec":
        return f"antistrat:{plan.opponent_id}"
    if plan.objective in ("retakes", "lineup_test"):
        return f"playbook:{plan.map_id}"
    return "methodology"


def _knowledge_gain(plan: PrepPlan, ev: PrepEvidence) -> float:
    gain = _KNOWLEDGE_BASE[plan.intensity]
    # A proven sparring partner makes the reps more useful, while scouting
    # improves anti-strat interpretation without revealing hidden state.
    gain *= 1.0 + min(0.25, ev.partner_map_samples * 0.025)
    if plan.objective == "anti_exec":
        gain *= 0.75 + 0.5 * ev.scouting_confidence
    elif plan.objective == "mental_reset":
        gain *= 0.65
    return round(gain, 2)


def _apply_tradeoffs(
    gs: "GameState", plan: PrepPlan, participant_ids: list[str]
) -> tuple[float, float]:
    cost = _STAMINA_COST[plan.intensity]
    total_stamina = 0.0
    total_morale = 0.0
    if plan.objective == "mental_reset":
        base_morale = {"light": 2.5, "normal": 3.5, "intense": 4.0}[plan.intensity]
    elif plan.objective == "lineup_test":
        base_morale = 0.8 if plan.intensity != "intense" else -0.4
    else:
        base_morale = 0.3 if plan.intensity == "light" else (
            0.0 if plan.intensity == "normal" else -0.8
        )
    for pid in participant_ids:
        player = gs.players[pid]
        before_stamina = player.stamina
        before = player.morale
        player.stamina = round(max(0.0, player.stamina - cost), 1)
        player.morale = round(min(100.0, max(0.0, player.morale + base_morale)), 1)
        total_stamina += before_stamina - player.stamina
        total_morale += player.morale - before
    average_stamina = total_stamina / max(len(participant_ids), 1)
    average_morale = total_morale / max(len(participant_ids), 1)
    return round(average_stamina, 1), round(average_morale, 1)


def _chemistry_delta(plan: PrepPlan) -> float:
    if plan.objective == "retakes":
        return {"light": 0.4, "normal": 0.7, "intense": 0.9}[plan.intensity]
    if plan.objective == "lineup_test":
        return {"light": -0.1, "normal": -0.3, "intense": -0.6}[plan.intensity]
    if plan.objective == "mental_reset":
        return {"light": 0.3, "normal": 0.5, "intense": 0.6}[plan.intensity]
    return {"light": 0.2, "normal": 0.3, "intense": 0.3}[plan.intensity]


def _resolve(
    gs: "GameState", plan: PrepPlan, rng: np.random.Generator | None
) -> PrepReport:
    fixture = _fixture(gs, plan.fixture_id)
    if (
        fixture is None
        or fixture.played
        or plan.team_id not in gs.teams
        or plan.partner_id not in gs.teams
    ):
        return PrepReport(
            plan_id=plan.id,
            team_id=plan.team_id,
            fixture_id=plan.fixture_id,
            opponent_id=plan.opponent_id,
            partner_id=plan.partner_id,
            map_id=plan.map_id,
            objective=plan.objective,
            intensity=plan.intensity,
            season=gs.season,
            week=gs.week,
            status="cancelled",
            finding_code="booking_invalidated",
            finding="The preparation booking was invalidated before the session.",
        )
    evidence = _evidence(gs, plan)
    participants = _participants(gs, plan.team_id)
    if not participants:
        return PrepReport(
            plan_id=plan.id,
            team_id=plan.team_id,
            fixture_id=plan.fixture_id,
            opponent_id=plan.opponent_id,
            partner_id=plan.partner_id,
            map_id=plan.map_id,
            objective=plan.objective,
            intensity=plan.intensity,
            season=gs.season,
            week=gs.week,
            status="cancelled",
            finding_code="no_practice_roster",
            finding="The session was cancelled because no players were available.",
            evidence=evidence,
        )

    # A caller may supply a dedicated weekly stream. Without one, a stable
    # hash provides the tiny copy variant without perturbing any other RNG.
    variant = (
        int(rng.integers(0, 2))
        if rng is not None
        else int(_stable_id(gs.seed, plan.id, "finding"), 16) % 2
    )
    code, finding = _finding(plan, evidence, variant)
    key = _knowledge_key(plan)
    gain = _knowledge_gain(plan, evidence)
    book = gs.org_knowledge.setdefault(plan.team_id, {})
    before_knowledge = min(_CAP, max(0.0, book.get(key, 0.0)))
    after_knowledge = round(min(_CAP, before_knowledge + gain), 2)
    book[key] = after_knowledge
    actual_gain = round(after_knowledge - before_knowledge, 2)

    stamina_cost, morale_delta = _apply_tradeoffs(gs, plan, participants)
    chemistry_delta = _chemistry_delta(plan)
    team = gs.teams[plan.team_id]
    before_chemistry = team.chemistry
    team.chemistry = round(
        min(100.0, max(0.0, team.chemistry + chemistry_delta)), 1
    )
    actual_chemistry = round(team.chemistry - before_chemistry, 1)
    return PrepReport(
        plan_id=plan.id,
        team_id=plan.team_id,
        fixture_id=plan.fixture_id,
        opponent_id=plan.opponent_id,
        partner_id=plan.partner_id,
        map_id=plan.map_id,
        objective=plan.objective,
        intensity=plan.intensity,
        season=gs.season,
        week=gs.week,
        finding_code=code,
        finding=finding,
        evidence=evidence,
        participant_ids=participants,
        knowledge_key=key,
        knowledge_gain=actual_gain,
        stamina_cost=stamina_cost,
        morale_delta=morale_delta,
        chemistry_delta=actual_chemistry,
    )


def _ai_partner(gs: "GameState", team_id: str, opponent_id: str, map_id: str) -> str:
    candidates = [
        tid
        for tid in sorted(gs.teams)
        if tid not in (team_id, opponent_id) and gs.teams[tid].player_ids
    ]
    if not candidates:
        return ""
    # Prefer a partner with useful experience on the selected map, then stable
    # id. This is public performance evidence, not access to hidden ability.
    return min(
        candidates,
        key=lambda tid: (
            -gs.team_map_stats.get(tid, {}).get(map_id).maps
            if gs.team_map_stats.get(tid, {}).get(map_id) is not None
            else 0,
            tid,
        ),
    )


def auto_schedule_ai(gs: "GameState") -> list[PrepPlan]:
    """Give AI teams the same light preparation access for current fixtures."""
    made: list[PrepPlan] = []
    for fixture in sorted(gs.fixtures_for_week(), key=lambda f: f.id):
        if fixture.played or not fixture.maps:
            continue
        for team_id in sorted((fixture.team_a, fixture.team_b)):
            if gs.is_human(team_id) or team_id in gs.preparation_plans_by:
                continue
            opponent_id = _opponent(fixture, team_id)
            map_id = fixture.maps[0]
            partner_id = _ai_partner(gs, team_id, opponent_id, map_id)
            if not partner_id:
                continue
            roster = _participants(gs, team_id)
            average_morale = sum(gs.players[p].morale for p in roster) / max(len(roster), 1)
            average_stamina = sum(gs.players[p].stamina for p in roster) / max(len(roster), 1)
            own = gs.team_map_stats.get(team_id, {}).get(map_id)
            if average_morale < 55.0 or average_stamina < 45.0:
                objective = "mental_reset"
            elif own is not None and _rate(own, "defense") < _rate(own, "attack"):
                objective = "retakes"
            else:
                objective = "anti_exec"
            made.append(
                schedule(
                    gs,
                    team_id,
                    fixture.id,
                    partner_id,
                    map_id,
                    objective,
                    "light",
                )
            )
    return made


def weekly_tick(
    gs: "GameState", rng: np.random.Generator | None = None
) -> list[PrepReport]:
    """Resolve due preparation before matches, in deterministic team order.

    Future plans remain live. AI plans are created before resolution;
    pass a generator derived solely for preparation if copy variation is
    desired, e.g. ``tree.derive(..., "preparation")``.
    """
    auto_schedule_ai(gs)
    reports: list[PrepReport] = []
    for team_id in sorted(list(gs.preparation_plans_by)):
        plan = gs.preparation_plans_by[team_id]
        fixture = _fixture(gs, plan.fixture_id)
        if fixture is not None and fixture.week > gs.week and not fixture.played:
            continue
        report = _resolve(gs, plan, rng)
        gs.preparation_reports_by[team_id] = report
        del gs.preparation_plans_by[team_id]
        reports.append(report)
        if gs.is_human(team_id):
            gs.push_private_news(
                f"Preparation report ({plan.map_id}, {plan.objective.replace('_', ' ')}): "
                f"{report.finding}",
                owner=team_id,
            )
    return reports


def view(gs: "GameState", team_id: str) -> dict[str, dict | None]:
    """Serializer-friendly current booking plus the latest resolved report."""
    current = gs.preparation_plans_by.get(team_id)
    last = gs.preparation_reports_by.get(team_id)
    return {
        "current": current.model_dump(mode="json") if current is not None else None,
        "last": last.model_dump(mode="json") if last is not None else None,
    }
