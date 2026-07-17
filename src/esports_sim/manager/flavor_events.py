"""Choice-gated campaign flavor events.

The campaign stores a compact, grounded fallback event (including the hidden
outcome table) and the web layer exposes only its title, prompt, and choices.
That keeps the weekly decision deterministic while allowing an optional LLM to
rephrase the visible copy at serve time. One event is rolled per team per week
at ``WEEKLY_CHANCE``; human teams keep it pending, while AI teams make a
deterministic off-screen choice so the small morale/social effects stay fair.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from esports_sim.manager.state import FlavorChoice, FlavorEvent, FlavorOutcome
from esports_sim.rng.tree import RngTree

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState


WEEKLY_CHANCE = 0.50
RECENT_WINDOW = 3


# These are deliberately authored as compact templates, not generated prose:
# the fallback is always available and all variants have comparable upside and
# downside. `{team}` and `{player}` make the otherwise reusable events specific
# to the current campaign.
_TEMPLATES = (
    {
        "id": "press_scrum",
        "subject": "player",
        "title": "The microphones are waiting for {player}",
        "prompt": (
            "A producer wants a quick interview with {player} before the next "
            "match. The question is about {team}'s expectations this split."
        ),
        "choices": (
            ("team_first", "Keep the answer team-first", (
                ("The answer lands as composed and the room settles.", {"player_morale": 2, "team_sentiment": 1}),
                ("The safe answer disappears into the media cycle.", {"player_confidence": -1, "team_sentiment": -1}),
            )),
            ("swing_big", "Set a public target", (
                ("The clip travels well and fans buy into the ambition.", {"player_confidence": 2, "player_followers": 1200, "team_sentiment": 2}),
                ("The headline becomes bulletin-board material for a rival.", {"player_confidence": -2, "team_sentiment": -2}),
            )),
            ("keep_private", "Decline and keep it internal", (
                ("The extra quiet time helps {player} reset.", {"player_stamina": 2, "player_morale": 1}),
                ("A few fans read the silence as distance.", {"player_followers": -500, "team_sentiment": -1}),
            )),
        ),
    },
    {
        "id": "behind_the_scenes",
        "subject": "player",
        "title": "A behind-the-scenes cut for {player}",
        "prompt": (
            "{team}'s content lead has an opening for a short video centered on "
            "{player}. They need a direction before the crew is released."
        ),
        "choices": (
            ("film_grind", "Film the practice-room grind", (
                ("The process-focused cut earns respect from the core fanbase.", {"player_followers": 900, "player_confidence": 1}),
                ("The crew runs long and leaves {player} a little flat.", {"player_stamina": -2, "player_morale": -1}),
            )),
            ("let_loose", "Make it playful", (
                ("A loose moment catches on and brightens the squad.", {"player_followers": 1700, "player_morale": 2}),
                ("The joke misses its audience and draws a few groans.", {"team_sentiment": -2, "player_confidence": -1}),
            )),
            ("skip_video", "Skip it this week", (
                ("The team gets a clean, uninterrupted practice block.", {"player_stamina": 2, "player_form": 1}),
                ("The channel goes quiet just as followers were checking in.", {"player_followers": -700}),
            )),
        ),
    },
    {
        "id": "community_clinic",
        "subject": "team",
        "title": "A community clinic asks for {team}",
        "prompt": (
            "A local organizer can put {team} in front of a youth clinic this "
            "week. It is good visibility, but it takes time away from the routine."
        ),
        "choices": (
            ("full_roster", "Send the full roster", (
                ("The clinic feels personal and the local crowd becomes louder.", {"team_sentiment": 3, "team_reputation": 1}),
                ("The schedule runs late and the squad loses a little freshness.", {"team_sentiment": 1, "team_stamina": -1}),
            )),
            ("small_group", "Send a small group", (
                ("A focused appearance still makes a good impression.", {"team_sentiment": 1, "team_reputation": 1}),
                ("The limited turnout is noted, but quickly forgotten.", {"team_sentiment": -1}),
            )),
            ("decline", "Protect the practice schedule", (
                ("The team keeps the week clean and arrives sharper.", {"team_stamina": 1, "team_form": 1}),
                ("The organizer books a rival instead.", {"team_sentiment": -2, "team_reputation": -1}),
            )),
        ),
    },
    {
        "id": "brand_shoot",
        "subject": "team",
        "title": "A sponsor wants a quick {team} shoot",
        "prompt": (
            "A partner offers {team} a compact campaign shoot with a modest "
            "appearance fee. The crew can work around practice, but not invisibly."
        ),
        "choices": (
            ("take_shoot", "Take the shoot", (
                ("The campaign looks polished and the appearance fee clears.", {"team_balance": 5000, "team_reputation": 1}),
                ("The shoot feels staged and practice loses some edge.", {"team_balance": 2500, "team_form": -1}),
            )),
            ("negotiate", "Ask for a leaner setup", (
                ("The crew agrees to a quick, professional setup.", {"team_balance": 3500, "team_stamina": 1}),
                ("The partner balks at the changes and the deal fades.", {"team_reputation": -1}),
            )),
            ("pass", "Pass on the campaign", (
                ("The team keeps its routine exactly as planned.", {"team_form": 1, "team_stamina": 1}),
                ("A small commercial opportunity moves elsewhere.", {"team_sentiment": -1}),
            )),
        ),
    },
    {
        "id": "rival_quote",
        "subject": "player",
        "title": "A rival quote puts {player} on the spot",
        "prompt": (
            "A rival has dismissed {team}'s recent form on a livestream. The "
            "social desk asks whether {player} should answer before the story runs."
        ),
        "choices": (
            ("measured", "Answer with a measured line", (
                ("The response reads confident without feeding the story.", {"player_confidence": 1, "team_sentiment": 1}),
                ("The clipped answer sounds flatter than intended.", {"player_confidence": -1}),
            )),
            ("fire_back", "Answer sharply", (
                ("The comeback has teeth and the fanbase rallies around it.", {"player_confidence": 2, "player_followers": 1000, "team_sentiment": 2}),
                ("The exchange keeps growing and becomes an unwanted distraction.", {"player_form": -2, "team_sentiment": -2}),
            )),
            ("no_comment", "Decline to engage", (
                ("The story expires quickly and focus stays on the server.", {"player_form": 1, "player_stamina": 1}),
                ("Some supporters wish the team had shown more edge.", {"team_sentiment": -1}),
            )),
        ),
    },
)


def _event_id(gs: "GameState", team_id: str, type_id: str, player_id: str) -> str:
    raw = f"flavor|{gs.seed}|{gs.season}|{gs.week}|{team_id}|{type_id}|{player_id}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()


def _stable_index(size: int, *parts: str) -> int:
    raw = "|".join(parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big") % size


def pending_for(gs: "GameState", team_id: str | None = None) -> FlavorEvent | None:
    """Return a manager's unresolved event, if one is waiting."""
    return gs.flavor_events_by.get(team_id or gs.acting_team_id)


def _build_event(gs: "GameState", team_id: str, rng) -> FlavorEvent:
    recent = set(gs.flavor_event_recent_by.get(team_id, [])[-RECENT_WINDOW:])
    eligible = [t for t in _TEMPLATES if t["id"] not in recent]
    if not eligible:
        eligible = list(_TEMPLATES)
    template = eligible[int(rng.integers(0, len(eligible)))]
    roster = sorted(gs.teams[team_id].player_ids)
    player_id = ""
    if template["subject"] == "player" and roster:
        player_id = roster[int(rng.integers(0, len(roster)))]
    player = gs.players.get(player_id)
    values = {
        "team": gs.teams[team_id].name,
        "player": player.handle if player is not None else gs.teams[team_id].name,
    }
    event_id = _event_id(gs, team_id, str(template["id"]), player_id)
    choices = []
    for choice_id, label, outcomes in template["choices"]:
        choices.append(
            FlavorChoice(
                id=choice_id,
                label=label.format(**values),
                outcomes=[
                    FlavorOutcome(text=text.format(**values), effects=effects)
                    for text, effects in outcomes
                ],
            )
        )
    return FlavorEvent(
        id=event_id,
        season=gs.season,
        week=gs.week,
        team_id=team_id,
        player_id=player_id,
        type_id=str(template["id"]),
        title=str(template["title"]).format(**values),
        prompt=str(template["prompt"]).format(**values),
        choices=choices,
    )


def _apply_effects(gs: "GameState", event: FlavorEvent, effects: dict[str, float]) -> None:
    team = gs.teams[event.team_id]
    player = gs.players.get(event.player_id)
    for key, value in sorted(effects.items()):
        if key == "team_balance":
            team.balance = max(0, team.balance + int(value))
        elif key == "team_reputation":
            team.reputation = round(max(0.0, min(100.0, team.reputation + value)), 1)
        elif key == "team_sentiment":
            current = gs.team_sentiment.get(event.team_id, 50.0)
            gs.team_sentiment[event.team_id] = round(max(0.0, min(100.0, current + value)), 1)
        elif key in ("team_stamina", "team_form"):
            attr = key.removeprefix("team_")
            for pid in sorted(team.player_ids):
                p = gs.players.get(pid)
                if p is not None:
                    setattr(p, attr, round(max(0.0, min(100.0, getattr(p, attr) + value)), 1))
        elif player is not None and key == "player_followers":
            player.followers = max(0, player.followers + int(value))
        elif player is not None and key in ("player_confidence", "player_morale", "player_form", "player_stamina"):
            attr = key.removeprefix("player_")
            setattr(player, attr, round(max(0.0, min(100.0, getattr(player, attr) + value)), 1))


def _remember(gs: "GameState", team_id: str, type_id: str) -> None:
    recent = gs.flavor_event_recent_by.setdefault(team_id, [])
    recent.append(type_id)
    del recent[:-RECENT_WINDOW]


def _resolve(gs: "GameState", event: FlavorEvent, choice_id: str) -> tuple[bool, str, dict[str, float]]:
    choice = next((c for c in event.choices if c.id == choice_id), None)
    if choice is None:
        return False, "That response is no longer available.", {}
    if not choice.outcomes:
        return False, "That response has no outcome configured.", {}
    outcome = choice.outcomes[_stable_index(len(choice.outcomes), event.id, choice.id)]
    _apply_effects(gs, event, outcome.effects)
    # F8: score this public choice against the team's committed identity. A
    # no-op (returns None, no mutation, no rng) for uncommitted/AI teams, so it
    # fires safely from the AI queue_weekly_events path too. Local import avoids
    # an import cycle at module load (mirrors the media_events seam).
    from esports_sim.manager import culture

    culture.register_choice(
        gs, event.team_id, "flavor", event.type_id, choice_id, event.player_id
    )
    _remember(gs, event.team_id, event.type_id)
    return True, outcome.text, dict(outcome.effects)


def resolve(gs: "GameState", team_id: str, choice_id: str) -> tuple[bool, str, dict[str, float]]:
    """Resolve and clear one human manager's pending event."""
    event = gs.flavor_events_by.get(team_id)
    if event is None:
        return False, "No flavor event is waiting for this team.", {}
    ok, text, effects = _resolve(gs, event, choice_id)
    if ok:
        del gs.flavor_events_by[team_id]
    return ok, text, effects


def queue_weekly_events(gs: "GameState") -> None:
    """Roll the new week's events on an isolated labelled RNG stream.

    Human teams receive a persistent decision; AI teams take a deterministic
    invisible option immediately. This preserves AI parity without making the
    player wait on simulated opponents or exposing an extra difficulty lever.
    """
    tree = RngTree(gs.seed)
    for team_id in sorted(gs.teams):
        if gs.is_human(team_id) and (
            team_id in gs.flavor_events_by or team_id in gs.media_events_by
        ):
            continue
        rng = tree.derive("season", gs.season, "week", gs.week, "flavor", team_id)
        if float(rng.random()) >= WEEKLY_CHANCE:
            continue
        event = _build_event(gs, team_id, rng)
        if gs.is_human(team_id):
            gs.flavor_events_by[team_id] = event
            continue
        choice = event.choices[int(rng.integers(0, len(event.choices)))]
        _resolve(gs, event, choice.id)


def to_api(event: FlavorEvent) -> dict:
    """Visible event wire shape. Outcomes and effects intentionally stay off it."""
    return {
        "id": event.id,
        "season": event.season,
        "week": event.week,
        "team_id": event.team_id,
        "player_id": event.player_id,
        "type_id": event.type_id,
        "title": event.title,
        "prompt": event.prompt,
        "choices": [{"id": c.id, "label": c.label} for c in event.choices],
    }
