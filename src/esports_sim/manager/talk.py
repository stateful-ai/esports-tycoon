"""Talk module — one 1:1 conversation per week.

The topic is read off the player's actual state (their biggest problem
first); the manager picks one of three approaches; the outcome depends on
the player's personality tags with a deterministic roll from the campaign
seed. Small numbers on purpose: a talk is a nudge, not a lever you crank.

Tone follows docs/salvage/tone_and_cast_lock.md: dry, no melodrama.
"""

from __future__ import annotations

from dataclasses import dataclass

from esports_sim.manager.state import GameState
from esports_sim.rng.tree import RngTree
from esports_sim.schemas import Player

RISKY_TAGS = {"hot_head", "volatile", "perfectionist"}
STEADY_TAGS = {"calm", "veteran", "reliable", "team_player"}
YOUNG_TAGS = {"rookie", "underrated"}


@dataclass
class TalkOption:
    id: str
    label: str


@dataclass
class Topic:
    id: str
    text: str
    options: list[TalkOption]


def week_key(gs: GameState) -> str:
    return f"s{gs.season}w{gs.week}"


def can_talk(gs: GameState, pid: str) -> tuple[bool, str]:
    if pid not in gs.teams[gs.user_team_id].player_ids:
        return False, "not on your roster"
    if gs.talked_week == week_key(gs):
        return False, "you already held this week's 1:1"
    return True, ""


def topic_for(gs: GameState, pid: str) -> Topic:
    """The player's most pressing issue, by priority."""
    p = gs.players[pid]
    if p.morale < 50:
        return Topic(
            "morale",
            f"{p.handle} has been quiet all week. Morale is low "
            f"({p.morale:.0f}) and it's starting to show in reviews.",
            [
                TalkOption("reassure", "Back them publicly — the slump isn't on them"),
                TalkOption("challenge", "Be blunt — the level isn't good enough"),
                TalkOption("listen", "Ask what's actually going on and listen"),
            ],
        )
    if 0 < p.contract_weeks_left <= 8:
        return Topic(
            "contract",
            f"{p.handle}'s deal runs out in {p.contract_weeks_left} weeks "
            f"and they know it. The agent has started calling.",
            [
                TalkOption("commit", "Promise renewal talks start this week"),
                TalkOption("honest", "Be honest — no decision until the season ends"),
                TalkOption("deflect", "Keep it light and change the subject"),
            ],
        )
    if p.stamina < 40:
        return Topic(
            "workload",
            f"{p.handle} is running on fumes ({p.stamina:.0f} stamina). "
            f"Another full week and something gives.",
            [
                TalkOption("rest", "Pull them from parts of practice this week"),
                TalkOption("push", "Ask for one more hard week before a break"),
                TalkOption("routine", "Bring in a routine review instead"),
            ],
        )
    if p.form < 45:
        return Topic(
            "form",
            f"{p.handle}'s numbers have dipped ({p.form:.0f} form). "
            f"They've noticed the bench conversation online.",
            [
                TalkOption("film", "Do a film session together on the losses"),
                TalkOption("back", "Tell them the spot is safe regardless"),
                TalkOption("bench_threat", "Make clear the spot has to be earned"),
            ],
        )
    return Topic(
        "check_in",
        f"Nothing is on fire with {p.handle}. A regular check-in.",
        [
            TalkOption("praise", "Call out what they've done well lately"),
            TalkOption("goals", "Set a concrete goal for the next block"),
            TalkOption("banter", "Keep it social — no shop talk"),
        ],
    )


def _tags(p: Player) -> set[str]:
    return set(p.personality_tags)


def resolve(gs: GameState, pid: str, option_id: str) -> tuple[bool, str, dict]:
    """Apply the chosen approach. Returns (ok, message, effects)."""
    ok, why = can_talk(gs, pid)
    if not ok:
        return False, why, {}
    p = gs.players[pid]
    topic = topic_for(gs, pid)
    if option_id not in {o.id for o in topic.options}:
        return False, "that approach doesn't fit this conversation", {}

    rng = RngTree(gs.seed).derive("talk", gs.season, gs.week, pid, option_id)
    tags = _tags(p)
    risky = tags & RISKY_TAGS
    steady = tags & STEADY_TAGS
    young = tags & YOUNG_TAGS

    d_morale = 0.0
    d_form = 0.0
    d_chem = 0.0
    msg = ""

    if option_id in ("reassure", "back", "commit", "praise"):
        d_morale = 4.0 + (1.5 if young else 0.0)
        if steady:
            d_morale -= 1.0  # veterans don't need the pep talk
        msg = f"{p.handle} takes it well."
    elif option_id in ("challenge", "bench_threat", "push"):
        if risky and rng.random() < 0.55:
            d_morale = -5.0
            d_chem = -1.0
            msg = f"{p.handle} bristles. That landed badly."
        else:
            d_morale = 2.0
            d_form = 3.0
            msg = f"{p.handle} answers the challenge."
    elif option_id in ("listen", "film", "goals", "routine"):
        d_morale = 2.5
        d_form = 1.5 if option_id == "film" else 0.5
        if steady:
            d_morale += 1.0
        msg = f"Solid conversation. {p.handle} leaves with a plan."
    elif option_id == "rest":
        p.stamina = min(100.0, p.stamina + 10.0)
        d_morale = 3.0
        d_form = -1.0
        msg = f"{p.handle} gets a lighter week."
    elif option_id == "honest":
        if steady:
            d_morale = 1.5
            msg = f"{p.handle} respects the straight answer."
        else:
            d_morale = -2.0
            msg = f"{p.handle} wanted more than that."
    elif option_id in ("deflect", "banter"):
        d_morale = 1.0 if rng.random() < 0.7 else -1.0
        msg = f"Nothing settled, nothing broken."

    p.morale = round(min(100.0, max(0.0, p.morale + d_morale)), 1)
    p.form = round(min(100.0, max(0.0, p.form + d_form)), 1)
    team = gs.teams[gs.user_team_id]
    team.chemistry = round(min(100.0, max(0.0, team.chemistry + d_chem)), 1)

    gs.talked_week = week_key(gs)
    if abs(d_morale) >= 4.0:
        gs.push_news(f"1:1 with {p.handle}: {msg}")
    effects = {"morale": d_morale, "form": d_form, "chemistry": d_chem}
    return True, msg, effects
