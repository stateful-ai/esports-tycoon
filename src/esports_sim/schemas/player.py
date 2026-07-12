"""Player entity. Attributes are a dict keyed by attribute-registry ids —
adding a new attribute is a config change, not a schema migration.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim.schemas.common import Playstyle, Region, Role


class AgentMastery(BaseModel):
    """Per-agent mastery — a player's third-best Jett is not their main Jett."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    mastery: float = Field(ge=0.0, le=100.0)


class MapMastery(BaseModel):
    """Per-map comfort. Teams have map pool depth; so do individuals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    map_id: str
    mastery: float = Field(ge=0.0, le=100.0)


class LanguageSkill(BaseModel):
    """One language a player speaks, with fluency 0-100. Up to three per
    player. Shared languages drive comms cohesion (relationships layer)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lang: str  # ISO-ish code: "en", "pt", "ko", ...
    level: float = Field(ge=0.0, le=100.0)


class PlayerBadge(BaseModel):
    """One badge a player currently holds (manager/badges.py). Rolled at a
    career moment, not guaranteed. `applied` is the REVERSIBLE current-ability
    edge actually applied on earn (subtracted back on decay); `pa_applied` is
    the PERMANENT ceiling revision, kept for the record only (never reverted).
    `last_qualified` is the season the badge was last (re-)earned, which drives
    decay timing."""

    model_config = ConfigDict(extra="forbid")

    id: str
    season: int = 0
    week: int = 0
    applied: dict[str, float] = Field(default_factory=dict)
    pa_applied: float = 0.0
    last_qualified: int = 0


class Player(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Identity
    id: str
    handle: str
    real_name: str = ""
    region: Region = Region.AMERICAS
    age: int = 20
    # Nationality + spoken languages (up to 3, with fluency). "" / empty on
    # older saves — gen.assign_identity backfills deterministically.
    country: str = ""
    languages: list[LanguageSkill] = Field(default_factory=list)

    # Role / style
    role: Role
    playstyle: Playstyle

    # Attributes: dict keyed by attribute-registry id. Sim code reads by id
    # with a default if a key is missing, so adding attributes is non-breaking.
    attributes: dict[str, float] = Field(default_factory=dict)

    # Per-agent / per-map mastery. MVP uses these in future match-engine tuning;
    # the data is authored now so policies can start reading it immediately.
    agent_pool: list[AgentMastery] = Field(default_factory=list)
    map_pool: list[MapMastery] = Field(default_factory=list)

    # Hidden ceiling (EHM-style Potential Ability, 1-99 like attributes).
    # 0 = not assigned; manager/development.py derives a stable fallback.
    potential: float = Field(default=0.0, ge=0.0, le=99.0)

    # Per-skill ceilings (EHM per-attribute Potential Ability). Sparse: keyed
    # by attribute-registry id, value 0-99. EMPTY by default and on old saves;
    # development.skill_ceiling derives a stable per-skill ceiling from the
    # scalar `potential` plus a blake2 spread when a key is absent, so the
    # default growth math is unchanged. Mentorship and monumental moments
    # WRITE specific entries here to raise the ceiling on chosen skills — the
    # only mutable per-skill state a scalar `potential` couldn't carry.
    skill_potential: dict[str, float] = Field(default_factory=dict)

    # Badges the player currently holds (manager/badges.py) — rolled at career
    # moments, decaying, with reversible CA edges + permanent ceiling revisions.
    # Empty by default and on old saves.
    badges: list[PlayerBadge] = Field(default_factory=list)

    # Career / contract
    salary: int = 0  # per week
    contract_weeks_left: int = 0
    # Weeks at the current club (ticks weekly, resets when they move).
    # Feeds loyalty: tenured players are pricier to pry away and protected
    # from AI churn. 0 on old saves — heals as weeks tick.
    tenure_weeks: int = 0
    morale: float = Field(default=70.0, ge=0.0, le=100.0)
    stamina: float = Field(default=100.0, ge=0.0, le=100.0)
    form: float = Field(default=50.0, ge=0.0, le=100.0)

    # Confidence: belief in their own game right now. The match engine
    # reads it NEUTRAL-SAFE (exact no-op at 50 — see ADR-007), so the
    # default keeps the golden gates byte-stable; the campaign layer moves
    # it on results, personal ratings, dev events and the social layer.
    confidence: float = Field(default=50.0, ge=0.0, le=100.0)

    # Social reach. 0 = not seeded yet; manager/social.py derives a stable
    # per-player baseline (ability + id hash) on first touch.
    followers: int = 0

    # Streaming load: how much of the player's week goes to streaming vs
    # practice (0-100). Drives org stream revenue (economy.py) and a
    # current-ability growth penalty (training.py). 0 = not seeded yet;
    # manager/social.py heals it toward a follower-driven baseline each week
    # (famous players stream more), so the default keeps synthetic players
    # (no followers) penalty-free and the growth/gate math unchanged. A
    # manager's "rein it in" 1:1 (talk.py) pushes it down for more practice at
    # the cost of morale + revenue; it drifts back toward the baseline.
    stream_load: float = Field(default=0.0, ge=0.0, le=100.0)

    # Individual development plan, user-set (AI players stay on defaults).
    # dev_focus: "auto" follows the team's weekly focus, otherwise pins one
    # training category for this player every week.
    dev_focus: str = "auto"  # auto | mechanical | tactical | mental | team
    # Intensity trades growth for stamina (and burnout risk at "intense").
    training_intensity: str = "normal"  # light | normal | intense

    # Free-form tags for personality. The narrative layer keys off these.
    personality_tags: list[str] = Field(default_factory=list)

    def attr(self, attr_id: str, default: float = 50.0) -> float:
        """Read an attribute by id with a default, never raises."""
        return self.attributes.get(attr_id, default)

    def agent_mastery(self, agent_id: str, default: float = 0.0) -> float:
        for m in self.agent_pool:
            if m.agent_id == agent_id:
                return m.mastery
        return default

    def map_mastery(self, map_id: str, default: float = 0.0) -> float:
        for mastery in self.map_pool:
            if mastery.map_id == map_id:
                return mastery.mastery
        return default
