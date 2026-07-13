"""Rare, grounded media decisions with durable non-random consequences."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from esports_sim.manager import chronicle, rivalries, social, sponsors
from esports_sim.manager.state import (
    MediaChoice,
    MediaCommitment,
    MediaDecision,
    MediaEvent,
)
from esports_sim.rng.tree import RngTree

if TYPE_CHECKING:  # pragma: no cover
    from esports_sim.manager.state import GameState


WEEKLY_CHANCE = 0.20
COOLDOWN_WEEKS = 6
HISTORY_CAP = 20


def _stamp(gs: "GameState") -> int:
    return gs.season * 100 + gs.week


def _id(gs: "GameState", team_id: str, kind: str, subject: str) -> str:
    raw = f"media|{gs.seed}|{gs.season}|{gs.week}|{team_id}|{kind}|{subject}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()


def _choice(choice_id: str, label: str, impact: str) -> MediaChoice:
    return MediaChoice(id=choice_id, label=label, impact=impact)


def _event_candidates(gs: "GameState", team_id: str) -> list[tuple[str, str, str]]:
    """Return (kind, player_id, fixture_id) from facts already in the save."""
    candidates: list[tuple[str, str, str]] = []
    fixture = gs.team_fixture(team_id)
    if fixture is not None:
        opponent = fixture.team_b if fixture.team_a == team_id else fixture.team_a
        if rivalries.get(gs, team_id, opponent) >= 20.0 or fixture.stage != "regular":
            candidates.append(("derby_expectations", "", fixture.id))

    offers = sorted(
        (
            offer
            for offer in gs.transfer_offers
            if offer.from_team == team_id and offer.player_id in gs.players
        ),
        key=lambda offer: (offer.expires_week, offer.player_id, offer.to_team),
    )
    if offers:
        candidates.append(("roster_rumor", offers[0].player_id, ""))

    roster = [gs.players[pid] for pid in sorted(gs.teams[team_id].player_ids)]
    rookies = [p for p in roster if p.age <= 20 and min(p.form, p.confidence) < 52.0]
    if rookies:
        rookie = min(rookies, key=lambda p: (min(p.form, p.confidence), p.id))
        candidates.append(("protect_rookie", rookie.id, ""))
    struggling = [p for p in roster if min(p.form, p.confidence, p.morale) < 45.0]
    if struggling:
        player = min(
            struggling,
            key=lambda p: (min(p.form, p.confidence, p.morale), p.id),
        )
        candidates.append(("defend_player", player.id, ""))
    return candidates


def _build_event(gs: "GameState", team_id: str, rng) -> MediaEvent | None:
    candidates = _event_candidates(gs, team_id)
    if not candidates:
        return None
    kind, player_id, fixture_id = candidates[int(rng.integers(0, len(candidates)))]
    team = gs.teams[team_id]
    player = gs.players.get(player_id)
    voice = social.media_voices(gs)["wire"]

    if kind == "derby_expectations":
        fixture = next(f for f in gs.fixtures if f.id == fixture_id)
        opponent_id = fixture.team_b if fixture.team_a == team_id else fixture.team_a
        opponent = gs.teams[opponent_id]
        title = f"{voice} asks what {team.name} expects from {opponent.name}"
        prompt = (
            f"The next series carries real history. Set the public bar now; "
            f"the result will settle the promise after the match."
        )
        choices = [
            _choice("set_high_bar", "Set winning as the public standard", "More sponsor and fan upside; a loss will be remembered."),
            _choice("respect_rival", "Respect the rival, back the group", "Builds trust with a smaller result-dependent swing."),
            _choice("shield_group", "Keep the focus inside the club", "Protects player trust but cools sponsor excitement."),
        ]
    elif kind == "roster_rumor":
        assert player is not None
        title = f"{voice} asks whether {player.handle} is available"
        prompt = (
            f"A real bid has put {player.handle}'s future into the news cycle. "
            "Choose the club's public position before the story hardens."
        )
        choices = [
            _choice("deny_and_back", "Call the player part of the plan", "Strong player trust; modest sponsor cost."),
            _choice("acknowledge_market", "Confirm the club will consider offers", "Commercial credibility; player trust falls."),
            _choice("no_comment", "Decline to comment", "Avoids sponsor friction; supporters and the player get less reassurance."),
        ]
    elif kind == "protect_rookie":
        assert player is not None
        title = f"{voice} puts rookie {player.handle} under the microscope"
        prompt = (
            f"Recent form has made {player.handle} the easy story. The answer "
            "will define whether the rookie sees the manager as cover or pressure."
        )
        choices = [
            _choice("take_responsibility", "Put the responsibility on yourself", "Large trust and sentiment gain; sponsors prefer a cleaner line."),
            _choice("standards_apply", "Say the standards apply to everyone", "Sponsors approve; rookie trust falls."),
            _choice("redirect_to_team", "Return the focus to the team", "Some trust protection with less public momentum."),
        ]
    else:
        assert player is not None
        title = f"{voice} asks if {player.handle} is letting {team.name} down"
        prompt = (
            f"The criticism is grounded in a difficult run for {player.handle}. "
            "Choose whether to absorb it, amplify standards, or keep the response private."
        )
        choices = [
            _choice("defend_publicly", "Defend the player publicly", "Player trust and fan sentiment rise; sponsors absorb some controversy."),
            _choice("demand_response", "Set a public performance standard", "Sponsors like the accountability; player trust falls."),
            _choice("keep_internal", "Keep the response inside the room", "Small trust protection; supporters read the silence cautiously."),
        ]
    return MediaEvent(
        id=_id(gs, team_id, kind, player_id or fixture_id),
        season=gs.season,
        week=gs.week,
        team_id=team_id,
        type_id=kind,
        title=title,
        prompt=prompt,
        player_id=player_id,
        fixture_id=fixture_id,
        choices=choices,
    )


_EFFECTS: dict[tuple[str, str], tuple[str, float, float, float]] = {
    ("defend_player", "defend_publicly"): ("The manager stands between the player and the criticism.", 3, -2, 8),
    ("defend_player", "demand_response"): ("The manager makes performance the public standard.", 1, 3, -6),
    ("defend_player", "keep_internal"): ("The club closes ranks without feeding the story.", -1, 0, 2),
    ("protect_rookie", "take_responsibility"): ("The manager takes the heat away from the rookie.", 3, -2, 9),
    ("protect_rookie", "standards_apply"): ("The rookie is publicly held to the senior standard.", 1, 3, -5),
    ("protect_rookie", "redirect_to_team"): ("The answer makes the rookie part of a collective process.", -1, 0, 4),
    ("roster_rumor", "deny_and_back"): ("The club publicly names the player as part of its plans.", 2, -1, 8),
    ("roster_rumor", "acknowledge_market"): ("The club confirms that the market remains open.", 0, 3, -7),
    ("roster_rumor", "no_comment"): ("The club leaves the rumor unanswered.", -2, 0, -2),
    ("derby_expectations", "set_high_bar"): ("The manager publicly sets winning as the derby standard.", 2, 1, 1),
    ("derby_expectations", "respect_rival"): ("The manager backs the group without dismissing the rival.", 1, 0, 3),
    ("derby_expectations", "shield_group"): ("The manager keeps the derby from becoming a public test.", -1, -1, 4),
}


def _active_brands(gs: "GameState", team_id: str) -> list[str]:
    brands = {
        deal.name for deal in gs.sponsor_slots_by.get(team_id, {}).values()
    }
    legacy = gs.sponsor_by.get(team_id)
    if legacy is not None:
        brands.add(legacy.name)
    return sorted(brands)


def trust(gs: "GameState", team_id: str, player_id: str) -> float:
    return gs.manager_player_trust_by.get(team_id, {}).get(player_id, 50.0)


def _apply(
    gs: "GameState", team_id: str, player_id: str,
    sentiment_delta: float, sponsor_delta: float, trust_delta: float,
) -> float:
    gs.team_sentiment[team_id] = round(
        min(100.0, max(0.0, gs.sentiment(team_id) + sentiment_delta)), 1
    )
    for brand in _active_brands(gs, team_id):
        sponsors.nudge_relation(gs, brand, sponsor_delta, team_id=team_id)
    targets = [player_id] if player_id else sorted(gs.teams[team_id].player_ids)
    book = gs.manager_player_trust_by.setdefault(team_id, {})
    for pid in targets:
        if pid in gs.players:
            book[pid] = round(min(100.0, max(0.0, book.get(pid, 50.0) + trust_delta)), 1)
    return sponsor_delta if _active_brands(gs, team_id) else 0.0


def pending_for(gs: "GameState", team_id: str | None = None) -> MediaEvent | None:
    return gs.media_events_by.get(team_id or gs.acting_team_id)


def resolve(
    gs: "GameState", team_id: str, choice_id: str, *, announce: bool = True
) -> tuple[bool, str, dict]:
    event = gs.media_events_by.get(team_id)
    if event is None:
        return False, "No media decision is waiting for this team.", {}
    if choice_id not in {choice.id for choice in event.choices}:
        return False, "That media response is no longer available.", {}
    key = (event.type_id, choice_id)
    if key not in _EFFECTS:
        return False, "That media response has no consequence configured.", {}
    summary, sent, sponsor, trust_delta = _EFFECTS[key]
    actual_sponsor = _apply(
        gs, team_id, event.player_id, sent, sponsor, trust_delta
    )
    decision = MediaDecision(
        event_id=event.id,
        season=event.season,
        week=event.week,
        team_id=team_id,
        type_id=event.type_id,
        choice_id=choice_id,
        player_id=event.player_id,
        fixture_id=event.fixture_id,
        summary=summary,
        sentiment_delta=sent,
        sponsor_delta=actual_sponsor,
        trust_delta=trust_delta,
    )
    history = gs.media_history_by.setdefault(team_id, [])
    history.append(decision)
    del history[:-HISTORY_CAP]
    if event.type_id == "derby_expectations" and choice_id != "shield_group":
        gs.media_commitments_by[team_id] = MediaCommitment(
            event_id=event.id,
            team_id=team_id,
            fixture_id=event.fixture_id,
            choice_id=choice_id,
            player_id=event.player_id,
        )
    chronicle.record(
        gs,
        "media",
        summary,
        team_id=team_id,
        player_id=event.player_id,
        data={"event": event.type_id, "choice": choice_id},
    )
    if announce:
        gs.push_news(summary)
    del gs.media_events_by[team_id]
    return True, summary, {
        "sentiment": sent, "sponsor_relation": actual_sponsor, "trust": trust_delta
    }


def settle_commitments(gs: "GameState", report) -> None:
    """Settle public derby promises from the real match result, never a roll."""
    for team_id in sorted(list(gs.media_commitments_by)):
        commitment = gs.media_commitments_by[team_id]
        fixture = next(
            (f for f in report.fixtures if f.id == commitment.fixture_id and f.played),
            None,
        )
        if fixture is None:
            if not any(f.id == commitment.fixture_id for f in gs.fixtures):
                del gs.media_commitments_by[team_id]
            continue
        won = fixture.winner_id == team_id
        if commitment.choice_id == "set_high_bar":
            deltas = (5.0, 3.0, 2.0) if won else (-6.0, -3.0, -3.0)
        else:
            deltas = (2.0, 1.0, 2.0) if won else (-1.0, 0.0, 1.0)
        sent, sponsor, trust_delta = deltas
        actual_sponsor = _apply(gs, team_id, "", sent, sponsor, trust_delta)
        result = "won" if won else "lost"
        settlement = (
            f"The public derby stance is settled: {gs.teams[team_id].name} {result}, "
            "and the earlier words now carry weight."
        )
        for decision in reversed(gs.media_history_by.get(team_id, [])):
            if decision.event_id == commitment.event_id:
                decision.settlement = settlement
                decision.sentiment_delta += sent
                decision.sponsor_delta += actual_sponsor
                decision.trust_delta += trust_delta
                break
        gs.push_news(settlement)
        del gs.media_commitments_by[team_id]


def queue_weekly_events(gs: "GameState") -> None:
    """Queue at most one contextual media decision after a six-week cooldown."""
    tree = RngTree(gs.seed)
    now = _stamp(gs)
    for team_id in sorted(gs.teams):
        if team_id in gs.media_events_by:
            continue
        if gs.is_human(team_id) and team_id in gs.flavor_events_by:
            continue
        if now - gs.media_last_week_by.get(team_id, -10_000) < COOLDOWN_WEEKS:
            continue
        rng = tree.derive("season", gs.season, "week", gs.week, "media", team_id)
        if float(rng.random()) >= WEEKLY_CHANCE:
            continue
        event = _build_event(gs, team_id, rng)
        if event is None:
            continue
        gs.media_last_week_by[team_id] = now
        if gs.is_human(team_id):
            gs.media_events_by[team_id] = event
        else:
            # AI clubs take the low-exposure final option. Their durable
            # tradeoff remains, but off-screen press does not randomly erase
            # the sentiment signal from a real win/loss or flood world news.
            choice = event.choices[-1]
            gs.media_events_by[team_id] = event
            resolve(gs, team_id, choice.id, announce=False)


def to_api(gs: "GameState", event: MediaEvent) -> dict:
    return {
        **event.model_dump(mode="json"),
        "outlet": social.media_voices(gs)["wire"],
    }


def view(gs: "GameState", team_id: str) -> dict:
    roster = [
        {
            "id": pid,
            "handle": gs.players[pid].handle,
            "trust": trust(gs, team_id, pid),
        }
        for pid in sorted(gs.teams[team_id].player_ids)
        if pid in gs.players
    ]
    return {
        "pending": to_api(gs, gs.media_events_by[team_id])
        if team_id in gs.media_events_by else None,
        "commitment": gs.media_commitments_by.get(team_id).model_dump(mode="json")
        if team_id in gs.media_commitments_by else None,
        "history": [row.model_dump(mode="json") for row in gs.media_history_by.get(team_id, [])[-5:]],
        "player_trust": roster,
        "cooldown_weeks": max(
            0, COOLDOWN_WEEKS - (_stamp(gs) - gs.media_last_week_by.get(team_id, -10_000))
        ),
    }
