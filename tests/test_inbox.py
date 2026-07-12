"""Weekly inbox: generation, bounds, determinism, persistence, read-marking.

The inbox aggregates each tick's real outcomes into a bounded, deterministic
feed. These tests pin the invariants the frontend and save format rely on.
"""

from __future__ import annotations

import json

import pytest

from esports_sim.manager import advance_week, inbox, market, new_campaign, sponsors
from esports_sim.manager.state import (
    GameState,
    InboxItem,
    SponsorOffer,
    SponsorPackage,
    TransferOffer,
)
from esports_sim.registry import GameData

# Enough ticks to cover a regular season, both internationals, and the
# offseason roll (so match/news/development categories all get exercised).
LIFECYCLE_WEEKS = 25


def _advance(gs: GameState, gd: GameData, n: int) -> None:
    for _ in range(n):
        advance_week(gs, gd)


@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    """Fresh, un-advanced seed=123 campaign for the cheap tests that only
    tick a week or two (or none)."""
    return new_campaign(game_data, seed=123)


# The whole-season tests below all wanted the same thing: one seed=123
# campaign advanced through a full lifecycle. Simulating 25 weeks per test
# dominated the file's runtime (~9 independent season sims). Build it ONCE
# per module and share it; mutation-free tests read `season` directly,
# mutating ones take a cheap deep copy via `season_copy`. `--dist loadscope`
# (see pyproject) keeps this file on one worker so the fixture is built once.
@pytest.fixture(scope="module")
def season(game_data: GameData) -> GameState:
    gs = new_campaign(game_data, seed=123)
    _advance(gs, game_data, LIFECYCLE_WEEKS)
    return gs


@pytest.fixture()
def season_copy(season: GameState) -> GameState:
    """An isolated deep copy of the shared season for tests that mutate the
    feed (read-marking, save/load). Copying is far cheaper than re-simming."""
    return season.model_copy(deep=True)


@pytest.fixture(scope="module")
def det_pair(game_data: GameData) -> tuple[GameState, GameState]:
    """Two independent seed=777 campaigns advanced identically — the raw
    material for the inbox determinism checks. Built once, read-only."""
    a = new_campaign(game_data, seed=777)
    b = new_campaign(game_data, seed=777)
    _advance(a, game_data, LIFECYCLE_WEEKS)
    _advance(b, game_data, LIFECYCLE_WEEKS)
    return a, b


# ---------------------------------------------------------------------------
# (a) items are produced and stay within the per-week and 200-item bounds


def test_items_generated_and_well_formed(season: GameState) -> None:
    campaign = season
    assert campaign.inbox, "advancing a seeded campaign should produce inbox items"

    for it in campaign.inbox:
        assert isinstance(it, InboxItem)
        assert it.category in inbox.CATEGORIES
        assert 0 < len(it.title) <= 70
        assert it.body  # non-empty plain text
        assert len(it.id) == 16 and all(c in "0123456789abcdef" for c in it.id)
        assert it.tab in (
            None, "market", "roster", "scouting", "finances", "standings",
            "stats", "social",  # the movement-wire digest deep-links here
        )

    # A real campaign surfaces more than one kind of thing over a season.
    cats = {it.category for it in campaign.inbox}
    assert "match" in cats
    assert len(cats) >= 3


def test_per_week_and_total_bounds(season: GameState) -> None:
    campaign = season
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


def test_determinism(det_pair: tuple[GameState, GameState]) -> None:
    a, b = det_pair

    ia = [inbox.to_api(it) for it in a.inbox]
    ib = [inbox.to_api(it) for it in b.inbox]
    assert ia == ib  # ids, order, titles, bodies, tabs — all identical
    # Sorted (wire) order is deterministic too.
    assert [inbox.to_api(it) for it in inbox.sorted_items(a)] == [
        inbox.to_api(it) for it in inbox.sorted_items(b)
    ]


def test_sorted_items_newest_first(season: GameState) -> None:
    campaign = season
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
    base = {"id", "season", "week", "category", "title", "body", "unread", "tab"}
    for it in campaign.inbox:
        # Without gs: always the frozen 8-field shape (backward compatible).
        assert set(inbox.to_api(it)) == base
        # With gs: base plus an OPTIONAL "actions" list, only on live offers.
        api = inbox.to_api(it, campaign)
        assert base <= set(api) <= base | {"actions"}
        if "actions" in api:
            assert it.category in ("transfer", "sponsor")
            for a in api["actions"]:
                assert set(a) == {"id", "label", "endpoint", "payload"}
                assert a["id"] in ("accept", "decline")
                assert isinstance(a["payload"], dict)


# ---------------------------------------------------------------------------
# (c) save/load round-trips items + unread; old saves without inbox load


def test_save_load_roundtrip(season_copy: GameState, tmp_path) -> None:
    campaign = season_copy
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
    data.pop("inboxes")  # simulate a save written before the feature existed
    loaded = GameState.model_validate_json(json.dumps(data))
    assert loaded.inbox == []
    # And the loaded save keeps ticking + generating a feed normally.
    advance_week(loaded, game_data)
    assert loaded.inbox


# ---------------------------------------------------------------------------
# (d) read-marking updates unread counts, including {"all": true}


def test_read_marking(season_copy: GameState) -> None:
    campaign = season_copy
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


# ---------------------------------------------------------------------------
# (e) Accept/Decline actions on transfer + sponsor offer items. Actions are
#     derived live from GameState (reconstructing the item's id from each live
#     offer) and point ONLY at the app's existing mutation endpoints.


def _a_rival(gs: GameState) -> str:
    return next(tid for tid in sorted(gs.teams) if tid != gs.user_team_id)


def _inject_transfer(gs: GameState) -> tuple[str, str, "InboxItem"]:
    """Put one live bid for a user player on the table and return the real
    inbox item the generator emits for it."""
    uid = gs.user_team_id
    pid = gs.teams[uid].player_ids[0]
    rival = _a_rival(gs)
    gs.transfer_offers = [
        TransferOffer(
            player_id=pid, from_team=uid, to_team=rival, fee=400_000,
            expires_week=gs.week + 4,
        )
    ]
    want = inbox._hash_id(gs.season, gs.week, "transfer", f"{pid}|{rival}")
    it = next(i for _p, i in inbox._transfer_items(gs, gs.season, gs.week) if i.id == want)
    return pid, rival, it


def _inject_sponsor(gs: GameState, brand: str = "ZZ Testworks") -> tuple[str, str, "InboxItem"]:
    slot = sponsors.SLOT_ORDER[0]
    gs.sponsor_market[slot] = [
        SponsorOffer(
            brand=brand, slot=slot, weeks=10,
            expires_week=gs.week + sponsors.OFFER_SHELF_LIFE,
            upfront=SponsorPackage(signing_bonus=50_000, weekly=1_000),
            steady=SponsorPackage(weekly=2_000),
            performance=SponsorPackage(weekly=1_500, per_win=3_000),
            objectives=[],
        )
    ]
    want = inbox._hash_id(gs.season, gs.week, "sponsor", f"offer|{slot}|{brand}")
    it = next(i for _p, i in inbox._sponsor_items(gs, gs.season, gs.week) if i.id == want)
    return slot, brand, it


def test_transfer_item_carries_accept_decline_actions(
    campaign: GameState, game_data: GameData
) -> None:
    _advance(campaign, game_data, 1)
    pid, _rival, it = _inject_transfer(campaign)

    acts = inbox.actions_for(campaign, it)
    assert [a["id"] for a in acts] == ["accept", "decline"]
    assert all(a["endpoint"] == "/api/actions/transfer_offer" for a in acts)
    assert acts[0]["payload"] == {"player_id": pid, "to_team": _rival, "accept": True}
    assert acts[1]["payload"] == {"player_id": pid, "to_team": _rival, "accept": False}
    # to_api only surfaces actions when gs is supplied.
    assert "actions" not in inbox.to_api(it)
    assert inbox.to_api(it, campaign)["actions"] == acts


def test_sponsor_offer_item_carries_accept_decline_actions(
    campaign: GameState, game_data: GameData
) -> None:
    _advance(campaign, game_data, 1)
    slot, brand, it = _inject_sponsor(campaign)

    acts = inbox.actions_for(campaign, it)
    assert [a["id"] for a in acts] == ["accept", "decline"]
    assert all(a["endpoint"] == "/api/actions/sponsor" for a in acts)
    # Accept signs the default "steady" structure (no multi-step flow inline).
    assert acts[0]["payload"] == {
        "slot": slot, "accept": True, "brand": brand, "structure": "steady",
    }
    assert acts[1]["payload"] == {"slot": slot, "accept": False, "brand": brand}
    assert inbox.to_api(it, campaign)["actions"] == acts


def test_non_offer_items_have_no_actions(season: GameState) -> None:
    campaign = season
    non_offer = [it for it in campaign.inbox if it.category not in ("transfer", "sponsor")]
    assert non_offer  # a full season surfaces plenty of non-offer notices
    for it in non_offer:
        assert inbox.actions_for(campaign, it) == []
        assert "actions" not in inbox.to_api(it, campaign)


def test_actions_are_deterministic_across_seeds(
    det_pair: tuple[GameState, GameState]
) -> None:
    a, b = det_pair
    # Serialised WITH gs (so any live-offer actions ride along) — byte-identical.
    assert [inbox.to_api(it, a) for it in inbox.sorted_items(a)] == [
        inbox.to_api(it, b) for it in inbox.sorted_items(b)
    ]


def test_declining_transfer_via_action_resolves_and_drops_future_actions(
    campaign: GameState, game_data: GameData
) -> None:
    _advance(campaign, game_data, 1)
    pid, _rival, it = _inject_transfer(campaign)
    season, week = campaign.season, campaign.week

    decline = next(a for a in inbox.actions_for(campaign, it) if a["id"] == "decline")
    # Execute the exact mutation the endpoint runs, using the action's payload.
    ok, _msg = market.respond_offer(campaign, **decline["payload"])
    assert ok
    assert all(o.player_id != pid for o in campaign.transfer_offers)  # resolved

    # The same stored item now carries no actions, and a later regeneration
    # produces no transfer item for the vanished offer.
    assert inbox.actions_for(campaign, it) == []
    assert "actions" not in inbox.to_api(it, campaign)
    assert all(i.id != it.id for _p, i in inbox._transfer_items(campaign, season, week + 1))


def test_declining_sponsor_via_action_resolves_and_drops_future_actions(
    campaign: GameState, game_data: GameData
) -> None:
    _advance(campaign, game_data, 1)
    slot, brand, it = _inject_sponsor(campaign)
    season, week = campaign.season, campaign.week

    decline = next(a for a in inbox.actions_for(campaign, it) if a["id"] == "decline")
    payload = dict(decline["payload"])
    payload.pop("accept")  # the endpoint routes accept->sign / decline->this fn
    ok, _msg = sponsors.decline_market_offer(campaign, payload["slot"], payload["brand"])
    assert ok
    assert all(o.brand != brand for o in campaign.sponsor_market.get(slot, []))

    assert inbox.actions_for(campaign, it) == []
    assert "actions" not in inbox.to_api(it, campaign)
    assert all(i.id != it.id for _p, i in inbox._sponsor_items(campaign, season, week))


# ---------------------------------------------------------------------------
# (h) shared world: private events (scouting / sponsors / retirements) stay
#     with their owner and never leak into another manager's inbox or news feed


def test_private_events_do_not_leak_across_managers(campaign: GameState) -> None:
    gs = campaign
    a = gs.user_team_id
    b = next(t.id for t in gs.teams.values() if t.id != a)
    gs.human_team_ids = [a, b]  # two live managers in one world
    season, week = gs.season, gs.week

    # A's scout finishes; B's sponsor objective pays out (each in its own
    # acting context, exactly as the weekly tick pushes them).
    gs.set_acting(a)
    gs.push_private_news(f"Scouting report on {gs.teams[b].name} complete.")
    gs.set_acting(b)
    gs.push_private_news("Objective met - ZZ Testworks pay 100,000 cr (make playoffs).")
    gs.set_acting(None)

    # Neither line reaches the shared dashboard feed.
    assert not any("Scouting report on" in n for n in gs.news)
    assert not any("Objective met" in n for n in gs.news)

    # But each manager's inbox detectors only surface their OWN event.
    gs.set_acting(a)
    a_scout = inbox._scouting_items(gs, season, week)
    a_obj = [it for _p, it in inbox._sponsor_items(gs, season, week) if "Objective met" in it.body]
    gs.set_acting(b)
    b_scout = inbox._scouting_items(gs, season, week)
    b_obj = [it for _p, it in inbox._sponsor_items(gs, season, week) if "Objective met" in it.body]
    gs.set_acting(None)

    assert len(a_scout) == 1 and not b_scout   # scouting stays with A
    assert len(b_obj) == 1 and not a_obj        # objective stays with B
