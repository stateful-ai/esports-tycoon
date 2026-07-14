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
    """A deterministic manager baseline that actively uses the club layer.

    This policy is deliberately an *observation-only* expert: it makes no
    assumptions about hidden player attributes, relationships, or event
    outcomes.  Its profile axes shape priorities, but all final candidates and
    parameters come from ``manager_observation`` and its legal action mask.
    """

    version = "heuristic-manager-v2"

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

    @staticmethod
    def _mean(rows: list[dict[str, Any]], key: str, default: float = 50.0) -> float:
        values = [float(row.get(key, default)) for row in rows]
        return sum(values) / len(values) if values else default

    def _roster_score(self, player: dict[str, Any]) -> float:
        """Rank own players from the public manager read, not hidden potential."""
        projection = player.get("pa_projection", [player.get("ca", 50.0)] * 2)
        future = float(projection[-1]) if projection else float(player.get("ca", 50.0))
        return (
            float(player.get("ca", 50.0)) * 0.72
            + float(player.get("form", 50.0)) * 0.14
            + float(player.get("confidence", 50.0)) * 0.08
            + float(player.get("morale", 50.0)) * 0.06
            + max(0.0, future - float(player.get("ca", 50.0))) * self.profile.youth * 0.15
        )

    def _lineup(self, obs: dict[str, Any]) -> list[str]:
        return [
            player["id"]
            for player in sorted(
                obs["roster"],
                key=lambda player: (-self._roster_score(player), player["id"]),
            )[:5]
        ]

    def _site_focus(self) -> str:
        if self.profile.experimentation < 0.62:
            return "balanced"
        digest = hashlib.blake2b(
            f"manager-site|{self.profile.id}".encode(), digest_size=1
        ).digest()[0]
        return ("a", "b", "c")[digest % 3]

    def _media_choice(self, obs: dict[str, Any]) -> str:
        """Choose a public stance whose trade-off fits the manager identity."""
        pending = obs.get("club", {}).get("media", {}).get("pending") or {}
        choices = {choice["id"] for choice in pending.get("choices", [])}
        if not choices:
            choices = set(obs["legal_actions"]["resolve_media"]["choice_ids"])
        trust_first = (
            "take_responsibility", "defend_publicly", "deny_and_back",
            "respect_rival", "shield_group", "redirect_to_team",
        )
        commercial_first = (
            "set_high_bar", "standards_apply", "acknowledge_market",
            "hold_to_standard", "no_comment", "respect_rival",
        )
        ordered = (
            trust_first
            if self.profile.loyalty + self.profile.youth >= self.profile.risk + self.profile.investment
            else commercial_first
        )
        return next((choice for choice in ordered if choice in choices), min(choices))

    def _training_focus(self, obs: dict[str, Any]) -> str:
        roster = obs["roster"]
        stamina = self._mean(roster, "stamina")
        morale = self._mean(roster, "morale")
        confidence = self._mean(roster, "confidence")
        if stamina < 55:
            return "rest"
        if morale < 48 or confidence < 45:
            return "mental"
        if self.profile.youth >= max(self.profile.analytics, self.profile.loyalty):
            return "mechanical"
        if self.profile.analytics >= self.profile.loyalty:
            return "tactical"
        return "team"

    def _initiative(self, obs: dict[str, Any]) -> dict[str, Any] | None:
        """Select one meaningful club project so weeks remain decisive, not noisy."""
        legal = obs["legal_actions"]
        club = obs.get("club", {})
        roster = obs["roster"]
        culture = club.get("culture", {})
        delegation = club.get("delegation", {}).get("policy", {})

        candidates: list[tuple[float, str, dict[str, Any]]] = []
        if legal["set_delegation"]["enabled"] and not (
            delegation.get("auto_renew_core") or delegation.get("auto_scout")
        ):
            regions = legal["set_delegation"]["regions"]
            roles = legal["set_delegation"]["roles"]
            alert_levels = legal["set_delegation"]["alert_levels"]
            region_index = int(self.profile.analytics * len(regions)) % len(regions)
            role_index = int(self.profile.youth * len(roles)) % len(roles)
            balance = max(0.0, float(obs["features"].get("balance", 0.0)))
            salary_ceiling = max(800, min(100_000, int(balance / 40)))
            candidates.append((
                120.0,
                "set_delegation",
                {
                    "auto_renew_core": self.profile.loyalty >= 0.42,
                    "renewal_salary_min": 800,
                    "renewal_salary_max": salary_ceiling,
                    "renewal_trigger_weeks": 6 if self.profile.risk >= 0.6 else 8,
                    "auto_scout": True,
                    "scout_region": regions[region_index],
                    "scout_roles": [roles[role_index]],
                    "scout_max_age": 19 if self.profile.youth >= 0.7 else 23,
                    "alert_level": (
                        alert_levels[-1]
                        if self.profile.youth >= 0.7
                        else "tier1_ready" if "tier1_ready" in alert_levels else alert_levels[0]
                    ),
                },
            ))

        registered = club.get("tournament_roster") or []
        if legal["tournament_registration"]["enabled"] and not registered:
            picks = [player["id"] for player in sorted(
                roster, key=lambda player: (-self._roster_score(player), player["id"])
            )[:6]]
            candidates.append((90.0 + self.profile.experimentation * 12, "tournament_registration", {
                "player_ids": picks,
            }))

        principle = (
            "development" if self.profile.youth >= 0.68
            else "accountability" if self.profile.analytics >= 0.68
            else "player_led" if self.profile.loyalty >= 0.72
            else "balanced"
        )
        if (
            legal["set_leadership"]["enabled"]
            and culture.get("captain_id")
            and culture.get("principle") != principle
        ):
            candidates.append((68.0 + self.profile.loyalty * 12, "set_leadership", {
                "captain_id": culture["captain_id"],
                "council_ids": list(culture.get("council_ids", [])),
                "principle": principle,
            }))

        available_sessions = legal["culture_session"]["actions"]
        flags = set(culture.get("flags", []))
        if legal["culture_session"]["enabled"]:
            if flags & {"fractured", "leadership_gap", "captain_isolated"}:
                action = "reset"
            elif "new_group" in flags and "welcome" in available_sessions:
                action = "welcome"
            elif principle == "accountability":
                action = "accountability"
            else:
                action = "player_led"
            params: dict[str, Any] = {"action": action}
            if action == "welcome":
                welcome_ids = legal["culture_session"]["player_ids"]
                if welcome_ids:
                    params["player_id"] = min(
                        welcome_ids,
                        key=lambda pid: next(
                            player["tenure_weeks"] for player in roster if player["id"] == pid
                        ),
                    )
            candidates.append((
                88.0 if flags else 46.0 + self.profile.loyalty * 18,
                "culture_session",
                params,
            ))

        current_prep = club.get("preparation", {}).get("current")
        if legal["set_preparation"]["enabled"] and current_prep is None:
            low_morale = self._mean(roster, "morale") < 55
            has_bench = len(roster) > 5
            objective = (
                "mental_reset" if low_morale
                else "lineup_test" if has_bench and self.profile.experimentation >= 0.65
                else "anti_exec" if self.profile.analytics >= 0.58
                else "retakes"
            )
            intensity = (
                "light" if self._mean(roster, "stamina") < 64
                else "intense" if self.profile.risk >= 0.78
                else "normal"
            )
            candidates.append((
                78.0 + self.profile.analytics * 16,
                "set_preparation",
                {
                    "fixture_id": legal["set_preparation"]["fixture_id"],
                    "partner_id": legal["set_preparation"]["partner_ids"][0],
                    "map_id": legal["set_preparation"]["map_ids"][0],
                    "objective": objective,
                    "intensity": intensity,
                },
            ))

        fixture = obs.get("upcoming_fixture") or {}
        if legal["series_directive"]["enabled"] and fixture.get("best_of", 0) >= 3:
            response = "press" if self.profile.risk >= 0.7 else "stabilize"
            candidates.append((62.0 + self.profile.experimentation * 14, "series_directive", {
                "fixture_id": legal["series_directive"]["fixture_id"],
                "trigger": "after_loss" if self.profile.analytics >= 0.65 else "trailing",
                "response": response,
            }))

        present_roles = set(obs.get("staff", {}))
        staff_needs = (
            "analyst" if self.profile.analytics >= 0.67
            else "performance_coach" if self.profile.youth >= 0.67
            else "psychologist" if self._mean(roster, "confidence") < 48
            else "coach"
        )
        if legal["hire_staff"]["enabled"] and staff_needs not in present_roles:
            permitted = set(legal["hire_staff"]["candidate_ids"])
            options = [
                member for member in obs["staff_candidates"]
                if member["id"] in permitted and member["role"] == staff_needs
            ]
            if options:
                best = max(options, key=lambda member: (
                    float(member.get("overall", member["quality"]))
                    + (float(member.get("system_fit", 100.0)) - 75.0) * (
                        0.18 if member["role"] == "coach" else 0.0
                    )
                    - float(member["salary"]) / 3_000,
                    member["id"],
                ))
                candidates.append((54.0 + self.profile.investment * 20, "hire_staff", {
                    "candidate_id": best["id"],
                }))

        if legal["facility_upgrade"]["enabled"] and self.profile.investment >= 0.72:
            preference = (
                "analytics_suite" if self.profile.analytics >= 0.6
                else "training_center" if self.profile.youth >= 0.6
                else "marketing_office"
            )
            options = legal["facility_upgrade"]["options"]
            choice = next((option for option in options if option["facility"] == preference), options[0])
            candidates.append((48.0 + self.profile.investment * 18, "facility_upgrade", {
                "facility": choice["facility"],
            }))

        if not candidates:
            return None
        _score, kind, params = max(candidates, key=lambda row: (row[0], row[1]))
        return {"kind": kind, "params": params}

    def choose_action(self, obs: dict[str, Any]) -> dict[str, Any]:
        legal = obs["legal_actions"]

        if legal["accept_job"]["enabled"]:
            return {
                "kind": "accept_job",
                "params": {"team_id": legal["accept_job"]["team_ids"][0]},
            }

        # Flavor outcomes are hidden from every manager, including this
        # baseline. Pick a stable visible option so rollouts cannot deadlock on
        # a human-only choice gate.
        if legal["resolve_flavor"]["enabled"]:
            choices = legal["resolve_flavor"]["choice_ids"]
            pick = choices[int(self.profile.risk * len(choices)) % len(choices)]
            return {
                "kind": "resolve_flavor",
                "params": {"event_id": legal["resolve_flavor"]["event_id"], "choice_id": pick},
            }

        if legal["resolve_media"]["enabled"]:
            return {
                "kind": "resolve_media",
                "params": {
                    "event_id": legal["resolve_media"]["event_id"],
                    "choice_id": self._media_choice(obs),
                },
            }

        if len(obs["roster"]) < 5 and legal["sign"]["enabled"]:
            signable = set(legal["sign"]["player_ids"])
            candidates = [p for p in obs["free_agents"] if p["player_id"] in signable]
            pick = max(candidates, key=lambda p: (p["perceived_quality"], p["player_id"]))
            return {"kind": "sign", "params": {"player_id": pick["player_id"]}}

        expiring = sorted(
            (p for p in obs["roster"] if p["contract_weeks"] <= 6),
            key=lambda p: (p["contract_weeks"], -self._roster_score(p), p["id"]),
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

        if len(obs["roster"]) > 5 and legal["set_lineup"]["enabled"] and self._once(obs, "lineup"):
            lineup = self._lineup(obs)
            if set(lineup) != set(obs.get("lineup_ids", [])):
                return {"kind": "set_lineup", "params": {"player_ids": lineup}}

        if legal["swap"]["enabled"] and self._once(obs, "market"):
            roster = {player["id"]: player for player in obs["roster"]}
            free_agents = {player["player_id"]: player for player in obs["free_agents"]}
            swaps = [
                pair for pair in legal["swap"]["pairs"]
                if pair["sign_id"] in free_agents and pair["drop_id"] in roster
            ]
            if swaps:
                best = max(
                    swaps,
                    key=lambda pair: (
                        float(free_agents[pair["sign_id"]]["perceived_quality"])
                        - self._roster_score(roster[pair["drop_id"]]),
                        pair["sign_id"],
                        pair["drop_id"],
                    ),
                )
                edge = (
                    float(free_agents[best["sign_id"]]["perceived_quality"])
                    - self._roster_score(roster[best["drop_id"]])
                )
                threshold = 9.0 - self.profile.risk * 4.0 - self.profile.experimentation * 2.0
                if edge >= threshold:
                    return {"kind": "swap", "params": best}

        if self._once(obs, "initiative"):
            initiative = self._initiative(obs)
            if initiative is not None:
                return initiative

        if self._once(obs, "training"):
            return {"kind": "set_training", "params": {"focus": self._training_focus(obs)}}

        if self.profile.youth >= 0.65 and self._once(obs, "development"):
            youngest = min(
                obs["roster"],
                key=lambda p: (p["age"], -self._roster_score(p), p["id"]),
            )
            return {
                "kind": "set_dev_plan",
                "params": {
                    "player_id": youngest["id"],
                    "dev_focus": "mechanical",
                    "training_intensity": "normal",
                },
            }

        if legal["mentor"]["enabled"] and legal["mentor"]["pairs"] and self._once(obs, "mentor"):
            pairs = legal["mentor"]["pairs"]
            return {"kind": "mentor", "params": pairs[0]}

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
                    "eco_greed": round(50 + (self.profile.investment - 0.5) * 24, 1),
                    "map_control": round(50 + spread, 1),
                    "site_focus": self._site_focus(),
                },
            }

        if legal["set_game_plan"]["enabled"] and self._once(obs, "game_plan"):
            targets = legal["set_game_plan"]["focus_target_ids"]
            opponent = obs.get("opponent") or {}
            reports = {player.get("player_id", ""): player for player in opponent.get("players", [])}
            target = max(
                targets,
                key=lambda pid: (
                    float(reports.get(pid, {}).get("perceived_quality", 0.0)),
                    pid,
                ),
                default="",
            )
            low_confidence = self._mean(obs["roster"], "confidence") < 48
            return {
                "kind": "set_game_plan",
                "params": {
                    "aggression": round(50 + (self.profile.risk - 0.5) * 26, 1),
                    "pace": round(50 + (self.profile.risk - 0.5) * 28, 1),
                    "util_discipline": round(50 + (self.profile.analytics - 0.5) * 24, 1),
                    "eco_greed": round(50 + (self.profile.investment - 0.5) * 18, 1),
                    "map_control": round(50 + (self.profile.experimentation - 0.5) * 24, 1),
                    "site_focus": self._site_focus(),
                    "focus_target": target,
                    "team_talk": "reassure" if low_confidence else "fire_up" if self.profile.risk >= 0.7 else "focus",
                },
            }

        return {"kind": "advance", "params": {}}
