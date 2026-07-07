"""Event log roundtrip. Any event we write to JSONL we must be able to
load back byte-equivalent — otherwise replay breaks."""

from __future__ import annotations

from pathlib import Path

from esports_sim.events import EventLog
from esports_sim.schemas.events import (
    BuyEvent,
    KillEvent,
    MatchEndEvent,
    MatchStartEvent,
    RoundEndEvent,
    RoundStartEvent,
    SpikePlantEvent,
)


def _sample_events() -> list:
    return [
        MatchStartEvent(
            tick=0,
            match_id="m1",
            map_id="haven",
            team_a_id="team_nexus",
            team_b_id="team_vanguard",
            seed=42,
        ),
        RoundStartEvent(
            tick=0,
            round_num=1,
            attacking_team_id="team_nexus",
            defending_team_id="team_vanguard",
        ),
        BuyEvent(
            tick=1,
            player_id="phantom",
            weapon_id="classic",
            armor=0,
            abilities_bought=[],
            spent=0,
        ),
        KillEvent(
            tick=27,
            killer_id="phantom",
            victim_id="warden",
            weapon_id="classic",
            headshot=True,
            callout_id="a_site",
            is_trade=False,
        ),
        SpikePlantEvent(tick=42, player_id="phantom", callout_id="a_site"),
        RoundEndEvent(tick=120, round_num=1, winner_id="team_nexus", reason="spike_detonation"),
        MatchEndEvent(tick=2400, match_id="m1", winner_id="team_nexus", score_a=13, score_b=7),
    ]


def test_event_log_in_memory_roundtrip() -> None:
    log = EventLog()
    for e in _sample_events():
        log.append(e)
    assert len(log) == 7
    assert log.filter_type("round.kill")[0].killer_id == "phantom"


def test_event_log_file_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    original = _sample_events()
    with EventLog(path) as log:
        for e in original:
            log.append(e)

    loaded = EventLog.load(path)
    assert len(loaded) == len(original)
    for a, b in zip(original, loaded.events()):
        # Pydantic round-trip via JSON should preserve content.
        assert a.model_dump() == b.model_dump()


def test_event_log_roundtrip_is_byte_stable(tmp_path: Path) -> None:
    """Same events, written twice with fresh logs, must produce identical
    file bytes. Our non-negotiable determinism guarantee."""
    events = _sample_events()
    p1 = tmp_path / "a.jsonl"
    p2 = tmp_path / "b.jsonl"

    with EventLog(p1) as log:
        for e in events:
            log.append(e)
    with EventLog(p2) as log:
        for e in events:
            log.append(e)

    assert p1.read_bytes() == p2.read_bytes()
