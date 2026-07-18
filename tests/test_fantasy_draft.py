"""Fantasy-draft campaign start: pool construction, snake order, AI parity,
completion settlement, determinism, and save round-trip."""

import pytest

from esports_sim.manager import fantasy_draft as fd
from esports_sim.manager import market
from esports_sim.manager.campaign import advance_week, new_campaign
from esports_sim.manager.state import GameState


def _autodraft(gs):
    """Resolve every remaining pick (human turns via the same value fn)."""
    fd.begin(gs)
    while gs.fantasy_draft.active:
        fd.ai_pick(gs, fd.on_clock(gs.fantasy_draft))
        fd.run_ai(gs)


@pytest.fixture(scope="module")
def drafted(game_data):
    """One fully autodrafted world, shared across this module's reads."""
    gs = new_campaign(game_data, seed=4242, fantasy_draft=True)
    _autodraft(gs)
    return gs


def test_setup_strips_tier1_into_pool(game_data):
    gs = new_campaign(game_data, seed=555, fantasy_draft=True)
    d = gs.fantasy_draft
    assert d is not None and d.active and not d.started
    tier1 = sorted(t for t, team in gs.teams.items() if team.tier == 1)
    assert set(d.order) == set(tier1)
    # Every tier-1 roster emptied; tier-2 (Challengers) untouched.
    for tid in tier1:
        assert gs.teams[tid].player_ids == []
        assert gs.teams[tid].captain_id is None
    for tid, team in gs.teams.items():
        if team.tier == 2:
            assert team.player_ids
    # FA pool folded into the draft pool, topped up to cover every pick.
    assert gs.free_agent_ids == []
    assert len(d.pool_ids) >= len(tier1) * d.rounds
    assert all(pid in gs.players for pid in d.pool_ids)


def test_sandbox_only_and_no_scenario(game_data):
    with pytest.raises(ValueError):
        new_campaign(game_data, seed=1, mode="legacy", fantasy_draft=True)
    with pytest.raises(ValueError):
        new_campaign(
            game_data, seed=1, scenario="youth_project", fantasy_draft=True
        )


def test_snake_order_and_turn_enforcement(game_data):
    gs = new_campaign(game_data, seed=77, fantasy_draft=True)
    d = gs.fantasy_draft
    # Picks are illegal before the host opens the board.
    with pytest.raises(ValueError):
        fd.make_pick(gs, d.order[0], d.pool_ids[0])
    fd.begin(gs)
    n = len(d.order)
    # Snake: round 1 forward, round 2 reversed (last picker goes twice).
    assert fd.pick_team(d, 0) == d.order[0]
    assert fd.pick_team(d, n - 1) == d.order[-1]
    assert fd.pick_team(d, n) == d.order[-1]
    assert fd.pick_team(d, 2 * n - 1) == d.order[0]
    turn = fd.on_clock(d)
    assert turn == gs.user_team_id  # begin() ran the AI up to the human
    off_turn = next(t for t in d.order if t != turn)
    with pytest.raises(ValueError):
        fd.make_pick(gs, off_turn, d.pool_ids[0])
    with pytest.raises(ValueError):
        fd.make_pick(gs, turn, "nope_not_a_player")
    # A legal human pick lands on the roster and leaves the pool.
    pid = d.pool_ids[0]
    fd.make_pick(gs, turn, pid)
    assert pid in gs.teams[turn].player_ids
    assert pid not in d.pool_ids


def test_completion_settles_squads(drafted):
    gs = drafted
    d = gs.fantasy_draft
    assert not d.active and d.started
    assert len(d.picks) == d.rounds * len(d.order)
    for tid in d.order:
        team = gs.teams[tid]
        assert len(team.player_ids) == d.rounds
        assert len(team.lineup_ids) == market.ROSTER_SIZE
        assert team.captain_id in team.player_ids
        roles = [gs.players[p].roster_role for p in team.player_ids]
        assert roles.count("starter") == market.ROSTER_SIZE
        for pid in team.player_ids:
            p = gs.players[pid]
            assert p.salary > 0
            assert p.contract_weeks_left >= 16
            assert p.tenure_weeks == 0
    # Leftovers become the season's free agents, uncontracted.
    assert gs.free_agent_ids
    assert d.pool_ids == []
    for pid in gs.free_agent_ids:
        assert gs.players[pid].contract_weeks_left == 0
    # Every team drafted exactly its own picks.
    for pk in d.picks:
        assert pk.player_id in gs.teams[pk.team_id].player_ids


def test_ai_prefs_are_stable_and_varied(drafted):
    gs = drafted
    prefs = {tid: fd.prefs_for(gs, tid).strategy for tid in gs.fantasy_draft.order}
    assert prefs == {
        tid: fd.prefs_for(gs, tid).strategy for tid in gs.fantasy_draft.order
    }
    assert len(set(prefs.values())) > 1  # the league isn't one hive mind


def test_recommendations_shape(game_data):
    gs = new_campaign(game_data, seed=31, fantasy_draft=True)
    fd.begin(gs)
    me = gs.user_team_id
    recs = fd.recommendations(gs, me, limit=5)
    assert len(recs) == 5
    scores = [r["score"] for r in recs]
    assert scores == sorted(scores, reverse=True)
    for r in recs:
        assert r["player_id"] in gs.fantasy_draft.pool_ids
        assert isinstance(r["reasons"], list)
    # Prefs move the board: a youth board should not equal a win-now board.
    from esports_sim.manager.state import DraftPrefs

    gs.fantasy_draft.prefs_by[me] = DraftPrefs(strategy="win_now")
    now = [r["player_id"] for r in fd.recommendations(gs, me, limit=10)]
    gs.fantasy_draft.prefs_by[me] = DraftPrefs(strategy="youth")
    youth = [r["player_id"] for r in fd.recommendations(gs, me, limit=10)]
    assert now != youth


def test_autodraft_deterministic(game_data):
    def build():
        gs = new_campaign(game_data, seed=909, fantasy_draft=True)
        _autodraft(gs)
        return gs

    assert build().model_dump_json() == build().model_dump_json()


def test_save_roundtrip_mid_draft(game_data, tmp_path):
    gs = new_campaign(game_data, seed=606, fantasy_draft=True)
    fd.begin(gs)
    path = tmp_path / "mid_draft.json"
    path.write_text(gs.model_dump_json(), encoding="utf-8")
    loaded = GameState.model_validate_json(path.read_text(encoding="utf-8"))
    d = loaded.fantasy_draft
    assert d is not None and d.active and d.started
    assert d.picks == gs.fantasy_draft.picks
    assert d.pool_ids == gs.fantasy_draft.pool_ids
    # The reloaded world drafts on identically.
    _autodraft(loaded)
    assert not loaded.fantasy_draft.active


def test_drafted_world_ticks(game_data):
    gs = new_campaign(game_data, seed=1213, fantasy_draft=True)
    _autodraft(gs)
    week = gs.week
    advance_week(gs, game_data)
    assert gs.week == week + 1
