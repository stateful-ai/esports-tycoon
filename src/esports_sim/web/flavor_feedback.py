"""Read actual flavor settlement deltas without changing campaign resolution."""
from esports_sim.manager import culture
from esports_sim.manager.state import FlavorEvent, GameState

MeterValues = dict[tuple[str, str], tuple[str, float | int]]


def _number(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:,}"


def snapshot(gs: GameState, event: FlavorEvent) -> MeterValues:
    """Capture affected public meters, including possible culture consequences."""
    team = gs.teams[event.team_id]
    values = {}

    def add(key, label, value):
        values[key] = (label, value)

    for attr, label in (("balance", "Bank balance"), ("reputation", "Reputation"), ("chemistry", "Chemistry")):
        add(("team_" + attr, event.team_id), f"{team.name}: {label}", getattr(team, attr))
    add(("team_sentiment", event.team_id), f"{team.name}: Community sentiment", gs.team_sentiment.get(event.team_id, 50.0))
    add(("culture_conviction", event.team_id), f"{team.name}: Culture conviction", culture.conviction(gs, event.team_id))
    roster = sorted(set(team.player_ids) | {event.player_id})
    for pid in roster:
        player = gs.players.get(pid)
        if player is None:
            continue
        for attr, label in (("followers", "Followers"), ("confidence", "Confidence"), ("morale", "Morale"), ("form", "Form"), ("stamina", "Condition")):
            add(("player_" + attr, pid), f"{player.handle}: {label}", getattr(player, attr))
        add(("player_trust", pid), f"{player.handle}: Manager trust", gs.manager_player_trust_by.get(event.team_id, {}).get(pid, 50.0))
    for pid in sorted(team.player_ids):
        if pid == event.player_id or pid not in gs.players or event.player_id not in gs.players:
            continue
        pair = "|".join(sorted((pid, event.player_id)))
        add(("relationship", pair), f"{gs.players[event.player_id].handle} / {gs.players[pid].handle}: Relationship", gs.relationships.get(pair, 50.0))
    return values


def settlement(
    gs: GameState, event: FlavorEvent, nominal: dict[str, float], before: MeterValues
) -> list[dict]:
    """Include changed meters and selected effects that realized no change."""
    attempted = set()
    for key in nominal:
        if key in ("team_stamina", "team_form"):
            attempted.update((key.replace("team_", "player_"), pid) for pid in gs.teams[event.team_id].player_ids)
        elif key.startswith("player_"):
            attempted.add((key, event.player_id))
        else:
            attempted.add((key, event.team_id))
    rows = []
    for key, (label, after) in snapshot(gs, event).items():
        old = before[key][1]
        if after == old and key not in attempted:
            continue
        delta = round(after - old, 4)
        # Text is server-authored; the client never computes effect formulas.
        change = ("+" if delta > 0 else "") + _number(delta)
        text = f"{label}: {_number(old)} -> {_number(after)} ({change})"
        if delta == 0:
            text += "; no net change."
        rows.append({"metric": key[0], "subject_id": key[1], "label": label, "before": old, "after": after, "delta": delta, "text": text})
    return rows
