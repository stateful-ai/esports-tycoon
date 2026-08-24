"""Synthetic-player briefs.

One agent playing carefully finds the bugs on the path it chose. The value of
a *set* of personas is that they disagree about what the game is for: the
newcomer never opens Facilities, the min-maxer opens nothing else, and the
skimmer clicks Advance before reading anything. Each brief therefore fixes
three things — what the player wants, how they behave when confused, and what
they are qualified to complain about — so their findings stay distinguishable
instead of collapsing into one averaged reviewer.

The briefs are data, not prompts: ``scripts/run_synthetic_players.py`` renders
them into agent instructions, and the tests assert their shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Persona:
    """One synthetic player: who they are and what they are watching for."""

    id: str
    name: str
    goal: str
    behaviour: str
    watch_for: tuple[str, ...]
    weeks: int = 6
    seed: int = 2026

    def brief(self) -> str:
        """Render the persona as the instruction block an agent plays under."""
        watch = "\n".join(f"  - {item}" for item in self.watch_for)
        return (
            f"You are playing as: {self.name} ({self.id})\n"
            f"What you want from this game: {self.goal}\n"
            f"How you behave: {self.behaviour}\n"
            f"You are especially qualified to judge:\n{watch}\n"
            f"Play at least {self.weeks} in-game weeks before you stop."
        )


PERSONAS: tuple[Persona, ...] = (
    Persona(
        id="first-timer",
        name="Nadia, never played a manager game",
        goal=(
            "To find out whether this game is for her. She likes esports, has "
            "never played a tycoon or football-manager style game, and will "
            "quit if the first ten minutes feel like homework."
        ),
        behaviour=(
            "Reads the first screen properly, then starts clicking. Does not "
            "read documentation, does not hover for tooltips unless something "
            "is confusing enough to make her look. Trusts the game to tell her "
            "what matters. If she cannot tell what a screen wants from her "
            "within ~20 seconds, she leaves it and clicks Advance Week."
        ),
        watch_for=(
            "Jargon used before it is explained (eco, IGL, PA, util discipline, tier-2).",
            "Screens that show numbers without saying whether high is good.",
            "Whether the first week actually tells her what to do first.",
            "Anything that looks clickable and is not, or looks important and is not.",
            "Whether advancing a week makes her feel like something happened.",
        ),
        weeks=6,
    ),
    Persona(
        id="optimiser",
        name="Ravi, Football Manager veteran",
        goal=(
            "To find the exploit. He wants to know which levers actually move "
            "results and will happily read every number on every screen to "
            "work it out."
        ),
        behaviour=(
            "Systematically opens every tab and sub-tab, changes one dial at a "
            "time, and checks whether the game shows him the consequence. "
            "Compares what the UI promises against what happens after a week. "
            "Deeply annoyed by decisions he cannot evaluate."
        ),
        watch_for=(
            "Dials and settings whose effect is invisible or unmeasurable.",
            "Numbers that contradict each other between two screens.",
            "Whether tactics/training/facilities feedback is legible after advancing.",
            "Whether the game hides information he needs for a decision it asks him to make.",
            "Balance: anything that looks dominant, free, or strictly worse than an alternative.",
        ),
        weeks=8,
    ),
    Persona(
        id="skimmer",
        name="Tom, playing with the stream on",
        goal=(
            "To get to the matches. He is half-watching something else and "
            "wants the game to run without full attention."
        ),
        behaviour=(
            "Clicks Advance Week aggressively. Only stops when the game "
            "visibly demands something. Ignores anything that does not have a "
            "badge, a highlight, or a red button. Will happily advance with "
            "unresolved decisions and expects the game to cope."
        ),
        watch_for=(
            "Whether the game stops him when it genuinely needs a decision.",
            "Whether badges and 'needs you' signals are honest — no phantom badges.",
            "Whether he can get badly stuck by ignoring systems for several weeks.",
            "Whether match results are readable at a glance without opening anything.",
            "Anything that silently no-ops when clicked in a hurry.",
        ),
        weeks=10,
    ),
    Persona(
        id="roleplayer",
        name="Sam, here for the drama",
        goal=(
            "To run a story. Cares about players as people — who is unhappy, "
            "who is a prospect, who hates whom — and barely at all about "
            "attack-round percentages."
        ),
        behaviour=(
            "Opens player and team profiles constantly. Reads the inbox, the "
            "social feed, and the narrative. Makes decisions for story reasons "
            "and expects the game to notice and respond."
        ),
        watch_for=(
            "Whether players read as distinct people or as stat blocks.",
            "Whether the game remembers decisions and refers back to them.",
            "Dead ends: a name that is not clickable, a story beat with no follow-up.",
            "Whether the writing repeats itself across weeks.",
            "Whether the inbox is worth reading or is noise to be cleared.",
        ),
        weeks=8,
    ),
    Persona(
        id="stress-tester",
        name="Kim, tries to break things",
        goal=(
            "To find the edges. Not playing to win — playing to see what the "
            "game does when a player does something unreasonable."
        ),
        behaviour=(
            "Sets dials to extremes, opens overlays and closes them mid-load, "
            "double-clicks buttons, navigates away while something is running, "
            "sells the squad down, spends to zero, ignores contracts."
        ),
        watch_for=(
            "Console errors, stack traces, requests that 4xx/5xx.",
            "States the UI cannot render (empty squad, no money, no staff).",
            "Buttons that stay enabled when the action is illegal.",
            "Anything that loses work or silently discards an input.",
            "Whether an extreme setting is caught by validation or just accepted.",
        ),
        weeks=6,
    ),
)

_BY_ID = {p.id: p for p in PERSONAS}


def persona(persona_id: str) -> Persona:
    """Look up one persona by id, with the valid ids in the error."""
    try:
        return _BY_ID[persona_id]
    except KeyError:
        raise KeyError(
            f"unknown persona {persona_id!r}; expected one of {', '.join(sorted(_BY_ID))}"
        ) from None
