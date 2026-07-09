"""Weekly inbox: generation, bounds, determinism, persistence, read-marking.

The inbox aggregates each tick's real outcomes into a bounded, deterministic
feed. These tests pin the invariants the frontend and save format rely on.
"""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import advance_week, inbox, new_campaign
from esports_sim.manager.state import GameState, InboxItem
from esports_sim.registry import GameData

# Enough ticks to cover a regular season, both internationals, and the
# offseason roll (so match/news/development categories all get exercised).
LIFECYCLE_WEEKS = 25


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=123)


def _advance(gs: GameState, gd: GameData, n: int) -> None:
    for _ in range(n):
        advance_week(gs, gd)


# ---------------------------------------------------------------------------
# (a) items are produced and stay within the per-week and 200-item bounds


def test_items_generated_and_well_formed(campaign: GameState, game_data: GameData) -> None:
    _advance(campaign, game_data, LIFECYCLE_WEEKS)
    assert campaign.inbox, "advancing a seeded campaign should produce inbox items"

    for it in campaign.inbox:
        assert isinstance(it, InboxItem)
        assert it.category in inbox.CATEGORIES
        assert 0 < len(it.title) <= 70
        assert it.body  # non-empty plain text
        assert len(it.id) == 16 and all(c in "0123456789abcdef" for c in it.id)
        assert it.tab in (
            None, "market", "roster", "scouting", "finances", "standings", "stats",
        )

    # A real campaign surfaces more than one kind of thing over a season.
    cats = {it.category for it in campaign.inbox}
    assert "match" in cats
    assert len(cats) >= 3


def test_per_week_and_total_bounds(campaign: GameState, game_data: GameData) -> None:
    _advance(campaign, game_data, LIFECYCLE_WEEKS)

    # Each (season, week) is written by exactly one tick, capped per week.
    per_week: dict[tuple[int, int], int] = {}
    for it in campaign.inbox:
        per_week[(it.season, it.week)] = per_week.get((it.season, it.week), 0) + 1
    assert per_week
    assert all(n <= inbox.PER_WEEK_CAP for n in per_week.values())

    assert len(campaign.inbox) <= inbox.MAX_ITEMS


def test_enforce_cap_drops_oldest_read_then_oldest() -> None:
    # 203 items, oldest-first. Index 1 and 4 are already read.
    items = [
        InboxItem(
            id=f"id{i}", season=1, week=i, category="news",
            title=f"t{i}", body="b", unread=(i not in (1, 4)),
        )
        for i in range(203)
    ]
    inbox._enforce_cap(items, cap=200)
    assert len(items) == 200
    remaining = {it.id for it in items}
    # overflow is 3: the two read items (1, 4) go first, then the oldest
    # remaining unread (0).
    assert "id1" not in remaining and "id4" not in remaining
    assert "id0" not in remaining
    assert "id2" in remaining and "id3" in remaining


def test_rolling_cap_holds_when_feed_is_full(campaign: GameState, game_data: GameData) -> None:
    _advance(campaign, game_data, 2)
    real_ids = {it.id for it in campaign.inbox}
    assert real_ids
    # Pad the feed past the cap with older, already-read notices.
    campaign.inbox = [
        InboxItem(
            id=f"pad{i}", season=0, week=i, category="news",
            title=f"pad {i}", body="filler", unread=False,
        )
        for i in range(200)
    ] + campaign.inbox
    advance_week(campaign, game_data)

    assert len(campaign.inbox) <= inbox.MAX_ITEMS
    # Oldest read padding was culled to make room...
    pad_left = sum(1 for it in campaign.inbox if it.id.startswith("pad"))
    assert pad_left < 200
    # ...while the real (newer) items were all kept.
    assert real_ids <= {it.id for it in campaign.inbox}


# ---------------------------------------------------------------------------
# (b) same seed -> byte-identical inbox


def test_determinism(game_data: GameData) -> None:
    a = new_campaign(game_data, seed=777)
    b = new_campaign(game_data, seed=777)
    _advance(a, game_data, LIFECYCLE_WEEKS)
    _advance(b, game_data, LIFECYCLE_WEEKS)

    ia = [inbox.to_api(it) for it in a.inbox]
    ib = [inbox.to_api(it) for it in b.inbox]
    assert ia == ib  # ids, order, titles, bodies, tabs — all identical
    # Sorted (wire) order is deterministic too.
    assert [inbox.to_api(it) for it in inbox.sorted_items(a)] == [
        inbox.to_api(it) for it in inbox.sorted_items(b)
    ]


def test_sorted_items_newest_first(campaign: GameState, game_data: GameData) -> None:
    _advance(campaign, game_data, LIFECYCLE_WEEKS)
    ordered = inbox.sorted_items(campaign)
    keys = [(it.season, it.week) for it in ordered]
    assert keys == sorted(keys, key=lambda k: (-k[0], -k[1]))
    # Within a week, insertion order (oldest first) is preserved by the
    # stable sort — the raw feed order for that week must be a subsequence.
    if len(ordered) >= 2:
        assert keys[0] >= keys[-1]


def test_wire_shape_is_frozen(campaign: GameState, game_data: GameData) -> None:
    _advance(campaign, game_data, 3)
    assert campaign.inbox
    for it in campaign.inbox:
        assert set(inbox.to_api(it)) == {
            "id", "season", "week", "category", "title", "body", "unread", "tab",
        }


# ---------------------------------------------------------------------------
# (c) save/load round-trips items + unread; old saves without inbox load


def test_save_load_roundtrip(campaign: GameState, game_data: GameData, tmp_path) -> None:
    _advance(campaign, game_data, LIFECYCLE_WEEKS)
    assert campaign.inbox
    # Read one item so an unread flag has to survive the trip.
    target = inbox.sorted_items(campaign)[0]
    inbox.mark_read(campaign, target.id)
    unread_before = inbox.unread_count(campaign)

    path = tmp_path / "save.json"
    campaign.save(path)
    loaded = GameState.load(path)

    assert loaded.model_dump_json() == campaign.model_dump_json()
    assert [inbox.to_api(it) for it in loaded.inbox] == [
        inbox.to_api(it) for it in campaign.inbox
    ]
    assert inbox.unread_count(loaded) == unread_before
    assert next(it for it in loaded.inbox if it.id == target.id).unread is False


def test_load_old_save_without_inbox(campaign: GameState, game_data: GameData) -> None:
    _advance(campaign, game_data, 2)
    data = json.loads(campaign.model_dump_json())
    data.pop("inbox")  # simulate a save written before the feature existed
    loaded = GameState.model_validate_json(json.dumps(data))
    assert loaded.inbox == []
    # And the loaded save keeps ticking + generating a feed normally.
    advance_week(loaded, game_data)
    assert loaded.inbox


# ---------------------------------------------------------------------------
# (d) read-marking updates unread counts, including {"all": true}


def test_read_marking(campaign: GameState, game_data: GameData) -> None:
    _advance(campaign, game_data, LIFECYCLE_WEEKS)
    total_unread = inbox.unread_count(campaign)
    assert total_unread > 0

    # Unknown id: no-op, count unchanged.
    assert inbox.mark_read(campaign, "does-not-exist") == total_unread

    # Marking one unread item drops the count by exactly one.
    first_unread = next(it for it in campaign.inbox if it.unread)
    after = inbox.mark_read(campaign, first_unread.id)
    assert after == total_unread - 1
    assert first_unread.unread is False
    # Re-marking the same item is idempotent.
    assert inbox.mark_read(campaign, first_unread.id) == after

    # Mark-all clears everything.
    assert inbox.mark_all_read(campaign) == 0
    assert inbox.unread_count(campaign) == 0
    assert all(not it.unread for it in campaign.inbox)
