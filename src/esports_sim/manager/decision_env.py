"""Headless manager-policy environment and decision-time observations.

This module is the campaign equivalent of a small RL environment.  It exposes
only information visible to the selected manager, publishes explicit legal
action masks, and applies actions through the same manager-domain functions as
the web layer.  It is deliberately framework-agnostic: callers can wrap it in
Gymnasium, TorchRL, a remote policy service, or a simple Python callback.

The observation is derived, not persisted.  That keeps saves compact and makes
it safe to evolve under the explicit ``OBSERVATION_VERSION`` contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from esports_sim.manager import (
    career,
    development,
    economy,
    flavor_events,
    market,
    sponsors,
    staff,
    talk,
    telemetry,
    training,
)
from esports_sim.manager.campaign import TEAM_TALK_APPROACHES, advance_week
from esports_sim.manager.state import GamePlan, GameState
from esports_sim.registry import GameData

OBSERVATION_VERSION = 3
TRACE_VERSION = 1
SUPPORTED_ACTIONS = frozenset(
    {
        "advance",
        "set_training",
        "set_tactics",
        "set_lineup",
        "set_scout",
        "sign",
        "release",
        "renew",
        "swap",
        "set_dev_plan",
        "mentor",
        "hire_staff",
        "release_staff",
        "facility_upgrade",
        "sponsor_respond",
        "set_game_plan",
        "clear_game_plan",
        "talk",
        "resolve_flavor",
        "rein_streaming",
        "negotiate_open",
        "negotiate_offer",
        "negotiate_cancel",
        "accept_job",
    }
)
_TACTIC_DIALS = (
    "aggression",
    "pace",
    "util_discipline",
    "eco_greed",
    "map_control",
)


class InvalidManagerAction(ValueError):
    """The requested action is malformed or illegal in the current state."""


@dataclass(frozen=True)
class StepResult:
    observation: dict[str, Any]
    reward: float
    reward_components: dict[str, float]
    advanced: bool
    done: bool
    message: str


def _player_stats(gs: GameState, pid: str) -> dict[str, float]:
    line = gs.player_stats.get(pid)
    if line is None:
        return {"maps": 0.0, "rating": 0.0, "kd": 0.0, "acs": 0.0}
    return {
        "maps": float(line.maps),
        "rating": round(float(line.rating), 3),
        "kd": round(float(line.kd), 3),
        "acs": round(float(line.acs), 3),
    }


def _own_player(gs: GameState, pid: str) -> dict[str, Any]:
    p = gs.players[pid]
    return {
        "id": p.id,
        "handle": p.handle,
        "age": p.age,
        "role": str(p.role),
        "playstyle": str(p.playstyle),
        "attributes": {k: float(v) for k, v in sorted(p.attributes.items())},
        "ca": round(development.overall(p), 3),
        "pa_projection": list(development.potential_projection(p, own=True)),
        "salary": p.salary,
        "contract_weeks": p.contract_weeks_left,
        "tenure_weeks": p.tenure_weeks,
        "stamina": p.stamina,
        "morale": p.morale,
        "form": p.form,
        "confidence": p.confidence,
        "followers": p.followers,
        "dev_focus": p.dev_focus,
        "training_intensity": p.training_intensity,
        "learning_language": p.learning_language,
        "stats": _player_stats(gs, pid),
    }


def _scouted_player(gs: GameState, team_id: str, pid: str) -> dict[str, Any]:
    owner = market.team_of(gs, pid)
    broad_key = owner if owner is not None else "market"
    progress = max(
        gs.scout_progress.get(broad_key, 0.0),
        gs.scout_progress.get(f"player:{pid}", 0.0),
    )
    report = development.scout_report(gs, gs.players[pid], progress)
    report["perceived_quality"] = round(
        market.perceived_quality(gs, team_id, gs.players[pid]), 3
    )
    report["asking_salary"] = market.asking_salary(gs.players[pid])
    report["stats"] = _player_stats(gs, pid)
    return report


def _legal_actions(gs: GameState, team_id: str) -> dict[str, Any]:
    roster = sorted(gs.teams[team_id].player_ids)
    free_agents = sorted(gs.free_agent_ids)
    signable = [pid for pid in free_agents if market.can_sign(gs, team_id, pid)[0]]
    swaps = [
        {"sign_id": sid, "drop_id": did}
        for sid in free_agents
        for did in roster
        if market.can_swap(gs, team_id, sid, did)[0]
    ]
    fixtures = sorted(
        f.id for f in gs.fixtures if not f.played and team_id not in (f.team_a, f.team_b)
    )
    scout_targets = (
        ["market"]
        + [tid for tid in sorted(gs.teams) if tid != team_id]
        + [f"player:{pid}" for pid in sorted(gs.players) if pid not in roster]
        + [f"match:{fid}" for fid in fixtures]
    )
    ready, ready_reason = market.roster_ready(gs, team_id)
    pending_flavor = flavor_events.pending_for(gs, team_id)
    if pending_flavor is not None:
        ready = False
        ready_reason = "resolve the pending flavor event before advancing"
    if career.blocked_seats(gs):
        ready = False
        ready_reason = "a manager must accept a job before the world can advance"
    dev_plans = {
        "enabled": bool(roster),
        "player_ids": roster,
        "focus_options": list(training.DEV_FOCUS_OPTIONS),
        "intensity_options": list(training.INTENSITY_OPTIONS),
        "language_options": list(training.LANGUAGE_OPTIONS),
        "has_language_coach": "language_coach" in gs.staff,
    }
    mentor_pairs = [
        {"protege_id": protege, "mentor_id": mentor}
        for protege in roster
        for mentor in roster
        if development.mentorship_valid(gs, protege, mentor)
    ]
    hireable = [
        m.id for m in sorted(gs.staff_pool, key=lambda m: m.id)
        if gs.teams[team_id].balance >= m.salary * 8
    ]
    facility_options = []
    for name in economy.FACILITY_NAMES:
        level = gs.facilities.get(name, 0)
        cost = economy.facility_upgrade_cost(level)
        if cost is not None and gs.teams[team_id].balance >= cost:
            facility_options.append({"facility": name, "next_level": level + 1, "cost": cost})
    sponsor_options = []
    for slot in sponsors.SLOT_ORDER:
        for offer in sorted(gs.sponsor_market.get(slot, []), key=lambda o: o.brand):
            sponsor_options.append(
                {
                    "slot": slot,
                    "brand": offer.brand,
                    "accept": False,
                    "structure": "",
                }
            )
            if slot not in gs.sponsor_slots:
                for structure in sponsors.STRUCTURES:
                    sponsor_options.append(
                        {
                            "slot": slot,
                            "brand": offer.brand,
                            "accept": True,
                            "structure": structure,
                        }
                    )
    live_negotiations = [
        {
            "player_id": pid,
            "salary_range": [800, max(800, neg.demand_salary * 2)],
            "weeks_range": [market.MIN_CONTRACT_WEEKS, market.MAX_CONTRACT_WEEKS],
        }
        for pid, neg in sorted(gs.negotiations.items())
    ]
    negotiable = []
    for pid in sorted(set(roster + free_agents)):
        kind, _ = market.negotiation_kind(gs, pid)
        if kind is not None and gs.talks_cooldown.get(pid, 0) <= gs.week:
            negotiable.append(pid)
    talk_options = []
    rein_targets = []
    for pid in roster:
        if talk.can_talk(gs, pid)[0]:
            topic = talk.topic_for(gs, pid)
            for option in topic.options:
                talk_options.append({"player_id": pid, "option_id": option.id})
        if talk.can_rein_streaming(gs, pid)[0]:
            rein_targets.append(pid)
    fixture = gs.team_fixture(team_id)
    plan_enabled = fixture is not None and not fixture.played
    opponent_ids: list[str] = []
    if plan_enabled:
        opponent_id = fixture.team_b if fixture.team_a == team_id else fixture.team_a
        opponent_ids = sorted(gs.teams[opponent_id].player_ids)
    seat = gs.seat_for_session(team_id)
    job_offers = []
    if seat is not None:
        job_offers = [o.team_id for o in gs.career_offers_by.get(seat.id, [])]
    return {
        "advance": {"enabled": ready, "reason": "" if ready else ready_reason},
        "set_training": {"enabled": True, "options": list(training.FOCUS_OPTIONS)},
        "set_tactics": {
            "enabled": True,
            "dials": {dial: [0.0, 100.0] for dial in _TACTIC_DIALS},
            "site_focus": ["balanced", "a", "b", "c"],
        },
        "set_lineup": {
            "enabled": len(roster) >= market.ROSTER_SIZE,
            "player_ids": roster,
            "count": market.ROSTER_SIZE,
        },
        "set_scout": {"enabled": bool(scout_targets), "targets": scout_targets},
        "sign": {"enabled": bool(signable), "player_ids": signable},
        "release": {"enabled": bool(roster), "player_ids": roster},
        "renew": {"enabled": bool(roster), "player_ids": roster},
        "swap": {"enabled": bool(swaps), "pairs": swaps},
        "set_dev_plan": dev_plans,
        "mentor": {"enabled": bool(roster), "pairs": mentor_pairs, "clear_ids": roster},
        "hire_staff": {"enabled": bool(hireable), "candidate_ids": hireable},
        "release_staff": {"enabled": bool(gs.staff), "roles": sorted(gs.staff)},
        "facility_upgrade": {"enabled": bool(facility_options), "options": facility_options},
        "sponsor_respond": {"enabled": bool(sponsor_options), "options": sponsor_options},
        "set_game_plan": {
            "enabled": plan_enabled,
            "fixture_id": fixture.id if fixture is not None else "",
            "focus_target_ids": opponent_ids,
            "starter_ids": roster,
            "team_talk_options": list(TEAM_TALK_APPROACHES),
            "site_focus": ["balanced", "a", "b", "c"],
            "dials": {dial: [0.0, 100.0] for dial in _TACTIC_DIALS},
        },
        "clear_game_plan": {"enabled": gs.game_plan is not None},
        "talk": {"enabled": bool(talk_options), "options": talk_options},
        "resolve_flavor": {
            "enabled": pending_flavor is not None,
            "event_id": pending_flavor.id if pending_flavor is not None else "",
            "choice_ids": [c.id for c in pending_flavor.choices] if pending_flavor is not None else [],
        },
        "rein_streaming": {"enabled": bool(rein_targets), "player_ids": rein_targets},
        "negotiate_open": {"enabled": bool(negotiable), "player_ids": negotiable},
        "negotiate_offer": {"enabled": bool(live_negotiations), "options": live_negotiations},
        "negotiate_cancel": {
            "enabled": bool(gs.negotiations), "player_ids": sorted(gs.negotiations)
        },
        "accept_job": {"enabled": bool(job_offers), "team_ids": sorted(job_offers)},
    }


def manager_observation(
    gs: GameState,
    gd: GameData,
    team_id: str,
    *,
    manager_profile: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return a stable, JSON-safe observation from one manager's viewpoint.

    Rival and free-agent ability is represented by the existing scouting
    report and perceived-quality systems; hidden attributes and exact potential
    never enter the observation.
    """
    if team_id not in gs.teams:
        raise KeyError(f"unknown team {team_id!r}")
    previous = gs.acting_team_id
    gs.set_acting(team_id)
    try:
        team = gs.teams[team_id]
        fixture = gs.team_fixture(team_id)
        opponent_id = None
        if fixture is not None:
            opponent_id = fixture.team_b if fixture.team_a == team_id else fixture.team_a
        opponent = (
            {
                "team_id": opponent_id,
                "team_name": gs.teams[opponent_id].name,
                "scout_progress": gs.scout_progress.get(opponent_id, 0.0),
                "players": [
                    _scouted_player(gs, team_id, pid)
                    for pid in sorted(gs.teams[opponent_id].player_ids)
                ],
            }
            if opponent_id in gs.teams
            else None
        )
        return {
            "observation_version": OBSERVATION_VERSION,
            "manager_profile": dict(sorted((manager_profile or {}).items())),
            "team_id": team_id,
            "season": gs.season,
            "week": gs.week,
            "phase": gs.phase,
            "features": telemetry.state_features(gs, team_id),
            "training_focus": gs.training_focus.get(team_id, "tactical"),
            "tactics": team.tactics.model_dump(),
            "lineup_ids": list(team.lineup_ids),
            "scout_target": gs.scout_target,
            "staff": {
                role: member.model_dump() for role, member in sorted(gs.staff.items())
            },
            "staff_candidates": [
                member.model_dump() for member in sorted(gs.staff_pool, key=lambda m: m.id)
            ],
            "facilities": dict(sorted(gs.facilities.items())),
            "sponsor_market": {
                slot: [offer.model_dump() for offer in sorted(offers, key=lambda o: o.brand)]
                for slot, offers in sorted(gs.sponsor_market.items())
            },
            "negotiations": {
                pid: neg.model_dump() for pid, neg in sorted(gs.negotiations.items())
            },
            "game_plan": gs.game_plan.model_dump() if gs.game_plan is not None else None,
            "career_offers": (
                [o.model_dump() for o in gs.career_offers_by.get(gs.seat_for_session(team_id).id, [])]
                if gs.seat_for_session(team_id) is not None else []
            ),
            "roster": [_own_player(gs, pid) for pid in sorted(team.player_ids)],
            "free_agents": [
                _scouted_player(gs, team_id, pid) for pid in sorted(gs.free_agent_ids)
            ],
            "upcoming_fixture": (
                {
                    "id": fixture.id,
                    "stage": fixture.stage,
                    "best_of": fixture.best_of,
                    "map_ids": list(fixture.maps),
                    "opponent_id": opponent_id,
                }
                if fixture is not None
                else None
            ),
            "opponent": opponent,
            "map_ids": sorted(gd.maps),
            "legal_actions": _legal_actions(gs, team_id),
        }
    finally:
        gs.set_acting(previous)


class HeadlessManagerEnv:
    """Deterministic, single-manager wrapper around a live ``GameState``."""

    def __init__(
        self,
        gs: GameState,
        gd: GameData,
        team_id: str | None = None,
        *,
        manager_profile: dict[str, float] | None = None,
        record_actions: bool = True,
        trace_sink: Callable[[dict[str, Any]], None] | None = None,
        policy_version: str = "unversioned",
    ) -> None:
        self.gs = gs
        self.gd = gd
        self.team_id = team_id or gs.user_team_id
        if self.team_id not in gs.teams:
            raise KeyError(f"unknown team {self.team_id!r}")
        self.manager_profile = dict(manager_profile or {})
        self.record_actions = record_actions
        self.trace_sink = trace_sink
        self.policy_version = policy_version

    def observe(self) -> dict[str, Any]:
        return manager_observation(
            self.gs, self.gd, self.team_id, manager_profile=self.manager_profile
        )

    def _record(self, kind: str, params: dict[str, Any]) -> None:
        if self.record_actions and self.gs.is_human(self.team_id):
            telemetry.record_action(self.gs, kind, params, team_id=self.team_id, source="agent")

    def step(self, action: dict[str, Any]) -> StepResult:
        decision_observation = self.observe()
        kind = str(action.get("kind", ""))
        params = action.get("params", {})
        if kind not in SUPPORTED_ACTIONS:
            raise InvalidManagerAction(f"unsupported manager action {kind!r}")
        if not isinstance(params, dict):
            raise InvalidManagerAction("action params must be an object")

        before = telemetry.state_features(self.gs, self.team_id)
        before_season = self.gs.season
        seat_before = self.gs.manager_for(self.team_id)
        manager_id = seat_before.id if seat_before is not None else ""
        previous = self.gs.acting_team_id
        self.gs.set_acting(self.team_id)
        advanced = False
        message = ""
        try:
            if kind == "set_training":
                focus = str(params.get("focus", ""))
                if focus not in training.FOCUS_OPTIONS:
                    raise InvalidManagerAction(f"unknown training focus {focus!r}")
                self.gs.training_focus[self.team_id] = focus
                message = f"training focus set to {focus}"
            elif kind == "set_tactics":
                tac = self.gs.teams[self.team_id].tactics
                updates: dict[str, float] = {}
                for dial in _TACTIC_DIALS:
                    if dial in params:
                        value = float(params[dial])
                        if not 0.0 <= value <= 100.0:
                            raise InvalidManagerAction(f"{dial} must be between 0 and 100")
                        updates[dial] = value
                site = None
                if "site_focus" in params:
                    site = str(params["site_focus"])
                    if site not in ("balanced", "a", "b", "c"):
                        raise InvalidManagerAction("site_focus must be balanced/a/b/c")
                for dial, value in updates.items():
                    setattr(tac, dial, value)
                if site is not None:
                    tac.site_focus = site
                params = tac.model_dump()
                message = "tactics updated"
            elif kind == "set_lineup":
                picks = list(params.get("player_ids", []))
                roster = set(self.gs.teams[self.team_id].player_ids)
                if len(picks) != market.ROSTER_SIZE or len(set(picks)) != len(picks):
                    raise InvalidManagerAction(f"lineup must contain {market.ROSTER_SIZE} unique players")
                if any(pid not in roster for pid in picks):
                    raise InvalidManagerAction("lineup contains a player outside the roster")
                self.gs.teams[self.team_id].lineup_ids = picks
                params = {"player_ids": picks}
                message = "default lineup updated"
            elif kind == "set_dev_plan":
                pid = str(params.get("player_id", ""))
                if pid not in self.gs.teams[self.team_id].player_ids:
                    raise InvalidManagerAction("player is not on the roster")
                focus = str(params.get("dev_focus", self.gs.players[pid].dev_focus))
                intensity = str(
                    params.get("training_intensity", self.gs.players[pid].training_intensity)
                )
                language = str(
                    params.get("learning_language", self.gs.players[pid].learning_language)
                )
                if focus not in training.DEV_FOCUS_OPTIONS:
                    raise InvalidManagerAction(f"unknown development focus {focus!r}")
                if intensity not in training.INTENSITY_OPTIONS:
                    raise InvalidManagerAction(f"unknown training intensity {intensity!r}")
                if language and language not in training.LANGUAGE_OPTIONS:
                    raise InvalidManagerAction(f"unknown language {language!r}")
                if focus == "language" and "language_coach" not in self.gs.staff:
                    raise InvalidManagerAction("hire a language coach before assigning language practice")
                if focus == "language" and not language:
                    raise InvalidManagerAction("choose a language for language practice")
                self.gs.players[pid].dev_focus = focus
                self.gs.players[pid].training_intensity = intensity
                self.gs.players[pid].learning_language = language
                params = {"player_id": pid, "dev_focus": focus, "intensity": intensity, "learning_language": language}
                message = f"development plan updated for {self.gs.players[pid].handle}"
            elif kind == "mentor":
                protege = str(params.get("protege_id", ""))
                mentor = str(params.get("mentor_id", ""))
                if protege not in self.gs.teams[self.team_id].player_ids:
                    raise InvalidManagerAction("protege is not on the roster")
                if not mentor:
                    self.gs.mentorships.pop(protege, None)
                elif development.mentorship_valid(self.gs, protege, mentor):
                    self.gs.mentorships[protege] = mentor
                else:
                    raise InvalidManagerAction("mentor must be an older, higher-rated teammate")
                params = {"protege_id": protege, "mentor_id": mentor}
                message = "mentorship updated"
            elif kind == "hire_staff":
                candidate = str(params.get("candidate_id", ""))
                ok, message = staff.hire(self.gs, candidate)
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "release_staff":
                role = str(params.get("role", ""))
                ok, message = staff.release(self.gs, role)
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "facility_upgrade":
                facility = str(params.get("facility", ""))
                ok, message = economy.upgrade_facility(self.gs, facility)
                if not ok:
                    raise InvalidManagerAction(message)
                params = {
                    "facility": facility,
                    "level": self.gs.facilities[facility],
                }
            elif kind == "sponsor_respond":
                slot = str(params.get("slot", ""))
                brand = str(params.get("brand", ""))
                accept = bool(params.get("accept", False))
                structure = str(params.get("structure", "steady"))
                if accept:
                    ok, message = sponsors.sign_market_offer(
                        self.gs, slot, brand, structure
                    )
                else:
                    ok, message = sponsors.decline_market_offer(self.gs, slot, brand)
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "set_game_plan":
                fixture = self.gs.team_fixture(self.team_id)
                if fixture is None or fixture.played:
                    raise InvalidManagerAction("no upcoming fixture to plan for")
                opponent = fixture.team_b if fixture.team_a == self.team_id else fixture.team_a
                target = str(params.get("focus_target", "")) or None
                starters = list(params.get("starter_ids", []))
                site = str(params.get("site_focus", "")) or None
                team_talk = str(params.get("team_talk", "")) or None
                if target is not None and target not in self.gs.teams[opponent].player_ids:
                    raise InvalidManagerAction("focus target is not on the opponent roster")
                if starters and (
                    len(starters) != market.ROSTER_SIZE
                    or len(set(starters)) != market.ROSTER_SIZE
                    or any(pid not in self.gs.teams[self.team_id].player_ids for pid in starters)
                ):
                    raise InvalidManagerAction("one-match lineup must name five roster players")
                if site is not None and site not in ("balanced", "a", "b", "c"):
                    raise InvalidManagerAction("invalid site focus")
                if team_talk is not None and team_talk not in TEAM_TALK_APPROACHES:
                    raise InvalidManagerAction("invalid team talk")
                dials: dict[str, float | None] = {}
                for dial in _TACTIC_DIALS:
                    raw = params.get(dial)
                    if raw is None:
                        dials[dial] = None
                    else:
                        value = float(raw)
                        if not 0.0 <= value <= 100.0:
                            raise InvalidManagerAction(f"{dial} must be between 0 and 100")
                        dials[dial] = value
                self.gs.game_plan = GamePlan(
                    fixture_id=fixture.id,
                    site_focus=site,
                    focus_target=target,
                    starter_ids=starters,
                    team_talk=team_talk,
                    **dials,
                )
                params = self.gs.game_plan.model_dump()
                message = "game plan set"
            elif kind == "clear_game_plan":
                self.gs.game_plan = None
                message = "game plan cleared"
            elif kind == "talk":
                pid = str(params.get("player_id", ""))
                option = str(params.get("option_id", ""))
                ok, message, _ = talk.resolve(self.gs, pid, option)
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "resolve_flavor":
                event_id = str(params.get("event_id", ""))
                choice_id = str(params.get("choice_id", ""))
                pending = flavor_events.pending_for(self.gs, self.team_id)
                if pending is None or pending.id != event_id:
                    raise InvalidManagerAction("no matching flavor event is waiting")
                ok, message, _ = flavor_events.resolve(self.gs, self.team_id, choice_id)
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "rein_streaming":
                pid = str(params.get("player_id", ""))
                ok, message, _ = talk.rein_in_streaming(self.gs, pid)
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "negotiate_open":
                pid = str(params.get("player_id", ""))
                ok, message, _ = market.open_negotiation(self.gs, pid)
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "negotiate_offer":
                pid = str(params.get("player_id", ""))
                status, message, _ = market.negotiate_offer(
                    self.gs, pid, int(params.get("salary", 0)), int(params.get("weeks", 0))
                )
                if status == "error":
                    raise InvalidManagerAction(message)
                params = {**params, "status": status}
            elif kind == "negotiate_cancel":
                pid = str(params.get("player_id", ""))
                if pid not in self.gs.negotiations:
                    raise InvalidManagerAction("no talks are open with that player")
                market.cancel_negotiation(self.gs, pid)
                message = "negotiation cancelled"
            elif kind == "accept_job":
                seat = self.gs.seat_for_session(self.team_id)
                if seat is None:
                    raise InvalidManagerAction("no manager seat controls this environment")
                new_team = str(params.get("team_id", ""))
                ok, message = career.accept_offer(self.gs, seat.id, new_team)
                if not ok:
                    raise InvalidManagerAction(message)
                self.team_id = new_team
            elif kind == "set_scout":
                target = str(params.get("target", ""))
                legal = self.observe()["legal_actions"]["set_scout"]["targets"]
                if target not in legal:
                    raise InvalidManagerAction(f"illegal scouting target {target!r}")
                self.gs.scout_target = target
                message = f"scout assigned to {target}"
            elif kind in ("sign", "release", "renew"):
                pid = str(params.get("player_id", ""))
                fn = {
                    "sign": lambda: market.sign_player(self.gs, self.team_id, pid),
                    "release": lambda: market.release_player(self.gs, self.team_id, pid),
                    "renew": lambda: market.renew_contract(self.gs, self.team_id, pid),
                }[kind]
                ok, message = fn()
                if not ok:
                    raise InvalidManagerAction(message)
            elif kind == "swap":
                sign_id = str(params.get("sign_id", ""))
                drop_id = str(params.get("drop_id", ""))
                ok, message = market.swap_player(self.gs, self.team_id, sign_id, drop_id)
                if not ok:
                    raise InvalidManagerAction(message)
            else:  # advance
                if career.blocked_seats(self.gs):
                    raise InvalidManagerAction("a manager must accept a job before advancing")
                if flavor_events.pending_for(self.gs, self.team_id) is not None:
                    raise InvalidManagerAction("resolve the pending flavor event before advancing")
                ok, why = market.roster_ready(self.gs, self.team_id)
                if not ok:
                    raise InvalidManagerAction(why)
                self._record(kind, params)
                advance_week(self.gs, self.gd)
                advanced = True
                message = "week advanced"

            if not advanced:
                self._record(kind, params)
        finally:
            self.gs.set_acting(previous)

        after = telemetry.state_features(self.gs, self.team_id)
        dismissed = bool(
            manager_id
            and manager_id in self.gs.managers
            and not self.gs.managers[manager_id].team_id
        )
        components = (
            telemetry.reward_components(before, after, dismissed=dismissed)
            if advanced and self.gs.season == before_season
            else {}
        )
        reward = float(components.pop("reward", 0.0)) if components else 0.0
        done = dismissed
        result = StepResult(
            observation=self.observe(),
            reward=reward,
            reward_components=components,
            advanced=advanced,
            done=done,
            message=message,
        )
        if self.trace_sink is not None:
            self.trace_sink(
                {
                    "trace_version": TRACE_VERSION,
                    "policy_version": self.policy_version,
                    "season": decision_observation["season"],
                    "week": decision_observation["week"],
                    "team_id": decision_observation["team_id"],
                    "manager_profile": dict(sorted(self.manager_profile.items())),
                    "observation": decision_observation,
                    "action": {"kind": kind, "params": params},
                    "reward": result.reward,
                    "reward_components": result.reward_components,
                    "advanced": result.advanced,
                    "done": result.done,
                    "message": result.message,
                }
            )
        return result
