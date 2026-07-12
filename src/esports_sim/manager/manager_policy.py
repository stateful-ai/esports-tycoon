"""Profile-conditioned baseline policies for headless manager rollouts.

These heuristics are a competent, deterministic floor for future imitation and
online-learning policies.  They consume only ``manager_observation`` output and
therefore obey the same fog-of-war and action-mask contract as a learned model.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ManagerProfile:
    id: str
    risk: float
    youth: float
    loyalty: float
    analytics: float
    investment: float
    experimentation: float

    def to_dict(self) -> dict[str, float]:
        return {
            key: float(value)
            for key, value in asdict(self).items()
            if key != "id"
        }


def generate_profile(seed: int, manager_key: str) -> ManagerProfile:
    """Generate stable profile axes from the world seed and manager identity."""

    def axis(name: str) -> float:
        digest = hashlib.blake2b(
            f"manager-profile|{seed}|{manager_key}|{name}".encode(), digest_size=8
        ).digest()
        return round(int.from_bytes(digest, "big") / (2**64 - 1), 4)

    return ManagerProfile(
        id=manager_key,
        risk=axis("risk"),
        youth=axis("youth"),
        loyalty=axis("loyalty"),
        analytics=axis("analytics"),
        investment=axis("investment"),
        experimentation=axis("experimentation"),
    )


class HeuristicManagerPolicy:
    """A deterministic masked baseline with visible profile differentiation."""

    version = "heuristic-manager-v1"

    def __init__(self, profile: ManagerProfile) -> None:
        self.profile = profile
        self._used: dict[tuple[int, int], set[str]] = {}

    def _once(self, obs: dict[str, Any], key: str) -> bool:
        week = (int(obs["season"]), int(obs["week"]))
        used = self._used.setdefault(week, set())
        if key in used:
            return False
        used.add(key)
        return True

    def choose_action(self, obs: dict[str, Any]) -> dict[str, Any]:
        legal = obs["legal_actions"]

        if legal["accept_job"]["enabled"]:
            return {
                "kind": "accept_job",
                "params": {"team_id": legal["accept_job"]["team_ids"][0]},
            }

        if len(obs["roster"]) < 5 and legal["sign"]["enabled"]:
            signable = set(legal["sign"]["player_ids"])
            candidates = [p for p in obs["free_agents"] if p["player_id"] in signable]
            pick = max(candidates, key=lambda p: (p["perceived_quality"], p["player_id"]))
            return {"kind": "sign", "params": {"player_id": pick["player_id"]}}

        expiring = sorted(
            (p for p in obs["roster"] if p["contract_weeks"] <= 6),
            key=lambda p: (p["contract_weeks"], -p["ca"], p["id"]),
        )
        if expiring and self.profile.loyalty >= 0.45 and self._once(obs, "renew"):
            return {"kind": "renew", "params": {"player_id": expiring[0]["id"]}}

        if legal["sponsor_respond"]["enabled"] and self._once(obs, "sponsor"):
            accepts = [o for o in legal["sponsor_respond"]["options"] if o["accept"]]
            if accepts:
                preferred = (
                    "performance" if self.profile.risk >= 0.67
                    else "upfront" if self.profile.investment >= 0.67
                    else "steady"
                )
                pick = next((o for o in accepts if o["structure"] == preferred), accepts[0])
                return {"kind": "sponsor_respond", "params": pick}

        if (
            self.profile.investment >= 0.72
            and legal["facility_upgrade"]["enabled"]
            and self._once(obs, "facility")
        ):
            preference = (
                "analytics_suite" if self.profile.analytics >= 0.6
                else "training_center" if self.profile.youth >= 0.6
                else "marketing_office"
            )
            options = legal["facility_upgrade"]["options"]
            pick = next((o for o in options if o["facility"] == preference), options[0])
            return {"kind": "facility_upgrade", "params": {"facility": pick["facility"]}}

        if legal["hire_staff"]["enabled"] and self._once(obs, "staff"):
            legal_ids = set(legal["hire_staff"]["candidate_ids"])
            candidates = [m for m in obs["staff_candidates"] if m["id"] in legal_ids]
            role = "analyst" if self.profile.analytics >= 0.6 else "coach"
            choices = [m for m in candidates if m["role"] == role]
            if choices:
                best = max(choices, key=lambda m: (m["quality"], -m["salary"], m["id"]))
                return {"kind": "hire_staff", "params": {"candidate_id": best["id"]}}

        if self._once(obs, "training"):
            stamina = sum(p["stamina"] for p in obs["roster"]) / max(len(obs["roster"]), 1)
            focus = (
                "rest" if stamina < 55
                else "mechanical" if self.profile.youth >= 0.65
                else "tactical" if self.profile.analytics >= 0.6
                else "team" if self.profile.loyalty >= 0.65
                else "mental"
            )
            return {"kind": "set_training", "params": {"focus": focus}}

        if self.profile.youth >= 0.65 and self._once(obs, "development"):
            youngest = min(obs["roster"], key=lambda p: (p["age"], p["id"]))
            return {
                "kind": "set_dev_plan",
                "params": {
                    "player_id": youngest["id"],
                    "dev_focus": "mechanical",
                    "training_intensity": "normal",
                },
            }

        if legal["set_scout"]["enabled"] and self._once(obs, "scout"):
            opponent = obs.get("opponent")
            target = (
                opponent["team_id"]
                if opponent is not None and self.profile.analytics >= 0.5
                else "market"
            )
            return {"kind": "set_scout", "params": {"target": target}}

        if self._once(obs, "tactics"):
            spread = (self.profile.experimentation - 0.5) * 40.0
            return {
                "kind": "set_tactics",
                "params": {
                    "aggression": round(50 + (self.profile.risk - 0.5) * 40, 1),
                    "pace": round(50 + spread, 1),
                    "util_discipline": round(50 + (self.profile.analytics - 0.5) * 35, 1),
                    "map_control": round(50 + spread, 1),
                },
            }

        if (
            self.profile.experimentation >= 0.7
            and legal["set_game_plan"]["enabled"]
            and self._once(obs, "game_plan")
        ):
            targets = legal["set_game_plan"]["focus_target_ids"]
            return {
                "kind": "set_game_plan",
                "params": {
                    "pace": round(55 + self.profile.risk * 20, 1),
                    "focus_target": targets[0] if targets else "",
                    "team_talk": "focus",
                },
            }

        return {"kind": "advance", "params": {}}
