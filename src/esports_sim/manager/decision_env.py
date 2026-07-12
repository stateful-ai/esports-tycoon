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
from typing import Any

from esports_sim.manager import career, development, market, telemetry, training
from esports_sim.manager.campaign import advance_week
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData

OBSERVATION_VERSION = 1
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
    if career.blocked_seats(gs):
        ready = False
        ready_reason = "a manager must accept a job before the world can advance"
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
    ) -> None:
        self.gs = gs
        self.gd = gd
        self.team_id = team_id or gs.user_team_id
        if self.team_id not in gs.teams:
            raise KeyError(f"unknown team {self.team_id!r}")
        self.manager_profile = dict(manager_profile or {})
        self.record_actions = record_actions

    def observe(self) -> dict[str, Any]:
        return manager_observation(
            self.gs, self.gd, self.team_id, manager_profile=self.manager_profile
        )

    def _record(self, kind: str, params: dict[str, Any]) -> None:
        if self.record_actions and self.gs.is_human(self.team_id):
            telemetry.record_action(self.gs, kind, params, team_id=self.team_id, source="agent")

    def step(self, action: dict[str, Any]) -> StepResult:
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
        return StepResult(
            observation=self.observe(),
            reward=reward,
            reward_components=components,
            advanced=advanced,
            done=done,
            message=message,
        )
