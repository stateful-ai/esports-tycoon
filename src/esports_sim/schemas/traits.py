"""Trait catalog — personality tags with mechanical teeth.

Lives in the schemas layer (a leaf) so BOTH the management layer and the
match engine can read trait effects without an import cycle. Effects by
key:

  Management: dev_mult, growth_floor, decline_age, chem_regen, fan_mult,
  salary_mult (consumed in manager/development.py, training, market).

  Match engine: peek_mult (angle-swinging appetite), day_sigma (added to
  the day-form spread — volatility as a mechanic), trade_bonus (refrag
  instinct), fallback_bonus (disciplined retreats off lost sites).
"""

from __future__ import annotations

from esports_sim.schemas.player import Player

TRAITS: dict[str, dict] = {
    # development
    "workhorse": {"blurb": "trains like it's a shift", "dev_mult": 1.25},
    "lazy": {"blurb": "coasts on talent", "dev_mult": 0.7},
    "prodigy": {"blurb": "arrived early, peaks early", "dev_mult": 1.2, "decline_age": 26},
    "late_bloomer": {"blurb": "keeps improving when others plateau", "growth_floor": 0.3, "decline_age": 31},
    "student": {"blurb": "film-room devotee", "dev_mult": 1.1},
    # temperament (talk module keys on several; the ENGINE now does too)
    "hot_head": {"blurb": "combustible under critique", "peek_mult": 1.3},
    "volatile": {"blurb": "week to week, a different player", "day_sigma": 3.0},
    "perfectionist": {"blurb": "own worst critic", "day_sigma": 1.5},
    "calm": {"blurb": "flat heartbeat", "peek_mult": 0.75, "day_sigma": -1.5},
    "ice_cold": {"blurb": "wants the last round", "day_sigma": -2.0},
    # social / org
    "leader": {"blurb": "locker-room gravity", "chem_regen": 0.4},
    "team_player": {"blurb": "glue", "chem_regen": 0.2, "trade_bonus": 0.06},
    "streamer": {"blurb": "brings an audience", "fan_mult": 1.5},
    "star_player": {"blurb": "the poster", "fan_mult": 1.3},
    "mercenary": {"blurb": "plays for the number", "salary_mult": 1.25},
    "loyal": {"blurb": "stays where it started", "salary_mult": 0.9},
    "veteran": {"blurb": "seen every meta"},
    "rookie": {"blurb": "first contract"},
    "underrated": {"blurb": "always the discount pick"},
    "quiet": {"blurb": "lets the clips talk"},
    "reliable": {"blurb": "never the reason you lost", "day_sigma": -1.5},
    "independent": {"blurb": "self-managed"},
    "shotcaller": {"blurb": "runs the room"},
    "mechanical": {"blurb": "aim first, questions later", "peek_mult": 1.2},
    "analytical": {"blurb": "spreadsheet gamer", "fallback_bonus": 0.15},
    "patient": {"blurb": "plays the long round", "peek_mult": 0.7, "fallback_bonus": 0.1},
}


def trait_value(p: Player, key: str, default: float) -> float:
    """Strongest value of `key` among the player's traits."""
    vals = [
        TRAITS[t][key]
        for t in p.personality_tags
        if t in TRAITS and key in TRAITS[t]
    ]
    if not vals:
        return default
    return max(vals) if max(vals) >= default else min(vals)
