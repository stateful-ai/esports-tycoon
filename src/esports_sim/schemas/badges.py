"""Player badges — rolled, decaying, ability-moving honours (and stigmas).

Leaf module (like traits.py) so both the campaign layer and the web serializers
read the catalog without an import cycle. A badge is NOT guaranteed by the
moment that can earn it: the campaign ROLLS for it (manager/badges.py) on a
dedicated rng stream, so winning Clutch King only gives you a *chance* at the
Clutch Master badge.

Effects (owner decision "ceiling stays, edge fades", moderate magnitude):
  * ``ca``  -- a REVERSIBLE current-ability edge (a dict of attribute deltas).
    Applied on earn, subtracted back out if the badge later decays. Negative
    badges carry a negative ``ca`` drag only.
  * ``pa`` / ``pa_skills`` -- a PERMANENT ceiling revision (scalar potential and
    optional per-skill ceilings). Never reverted: you proved the potential, and
    losing the badge doesn't un-prove it. Negative badges leave ``pa`` at 0.

Gating / decay:
  * ``eligible`` -- minimum attribute values to even roll (you can't become an
    Aim Demon with mediocre aim), so a badge feels earned.
  * ``decay_attr`` / ``decay_floor`` -- a positive badge decays if the skill it
    celebrates falls below the floor (the edge is gone).
  * ``decay_seasons`` -- a badge auto-decays this many seasons after it was last
    (re-)qualified; re-earning refreshes the clock. Negative badges simply
    recover after this many quiet seasons unless re-triggered.
"""

from __future__ import annotations

BADGES: dict[str, dict] = {
    # -- positive: earned honours -------------------------------------------
    "aim_demon": {
        "name": "Aim Demon", "emoji": "\U0001F3AF", "polarity": 1,
        "blurb": "raw mechanical menace",
        "ca": {"aim_precision": 3.0, "aim_reactivity": 2.0},
        "pa": 2.0, "pa_skills": ["aim_precision", "aim_reactivity"],
        "eligible": {"aim_precision": 70.0},
        "decay_attr": "aim_precision", "decay_floor": 76.0, "decay_seasons": 2,
    },
    "clutch_master": {
        "name": "Clutch Master", "emoji": "❄️", "polarity": 1,
        "blurb": "wants the round with the game on the line",
        "ca": {"clutch_factor": 3.0, "composure": 2.0},
        "pa": 2.0, "pa_skills": ["clutch_factor"],
        "eligible": {"clutch_factor": 65.0},
        "decay_attr": "clutch_factor", "decay_floor": 68.0, "decay_seasons": 2,
    },
    "superstar": {
        "name": "Superstar", "emoji": "⭐", "polarity": 1,
        "blurb": "carries a team and a broadcast",
        "ca": {"game_sense": 2.0, "composure": 2.0},
        "pa": 2.5, "pa_skills": [],
        "eligible": {}, "decay_seasons": 2,
    },
    "phenom": {
        "name": "Phenom", "emoji": "\U0001F331", "polarity": 1,
        "blurb": "a ceiling scouts argue about",
        "ca": {}, "pa": 3.5, "pa_skills": [],
        "eligible": {}, "decay_seasons": 3,  # the label fades as they establish
    },
    "big_game_player": {
        "name": "Big-Game Player", "emoji": "\U0001F3C6", "polarity": 1,
        "blurb": "turns up when the lights are brightest",
        "ca": {"composure": 2.0, "clutch_factor": 2.0},
        "pa": 1.5, "pa_skills": ["composure"],
        "eligible": {}, "decay_seasons": 2,
    },
    "ascending": {
        "name": "Ascending", "emoji": "\U0001F4C8", "polarity": 1,
        "blurb": "still climbing while others plateau",
        "ca": {"game_sense": 1.0}, "pa": 3.0, "pa_skills": [],
        "eligible": {}, "decay_seasons": 2,
    },
    # -- negative: stigmas (reversible CA drag, no permanent harm) -----------
    "choker": {
        "name": "Choker", "emoji": "\U0001F976", "polarity": -1,
        "blurb": "tightens up when it matters most",
        "ca": {"clutch_factor": -3.0, "composure": -2.0},
        "pa": 0.0, "pa_skills": [],
        "eligible": {}, "decay_seasons": 2,
    },
    "injury_prone": {
        "name": "Injury Prone", "emoji": "\U0001FA79", "polarity": -1,
        "blurb": "the physio's on speed dial",
        "ca": {"movement": -2.0, "aim_reactivity": -1.0},
        "pa": 0.0, "pa_skills": [],
        "eligible": {}, "decay_seasons": 2,
    },
    "inconsistent": {
        "name": "Inconsistent", "emoji": "\U0001F3B2", "polarity": -1,
        "blurb": "a different player week to week",
        "ca": {"composure": -2.0}, "pa": 0.0, "pa_skills": [],
        "eligible": {}, "decay_seasons": 2,
    },
}


def is_badge(bid: str) -> bool:
    return bid in BADGES


def polarity(bid: str) -> int:
    return int(BADGES.get(bid, {}).get("polarity", 1))
