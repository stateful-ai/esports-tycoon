"""Weapons. MVP economy uses 6-7 weapons and one armor tier."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from esports_sim._compat import StrEnum


class WeaponClass(StrEnum):
    PISTOL = "pistol"
    SMG = "smg"
    RIFLE = "rifle"
    SNIPER = "sniper"
    SHOTGUN = "shotgun"
    LMG = "lmg"


class Weapon(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    display_name: str
    weapon_class: WeaponClass
    price: int
    # Damage at head / body / leg at point-blank. The match engine scales by
    # range + armor later. Values kept coarse for MVP tuning.
    dmg_head: int
    dmg_body: int
    dmg_leg: int
    # Rough abstract accuracy baseline — how forgiving the weapon is. Player
    # aim_precision then modulates this.
    accuracy_base: float = 0.5
    # Higher = punishes strafe shots more. Used later by movement penalty.
    movement_penalty: float = 0.5
    # Kill reward paid to the killer (Valorant standard is 200 cr for most).
    kill_reward: int = 200
