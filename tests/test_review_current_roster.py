"""Historical match findings must not offer unavailable squad actions."""
import pytest

pytest.importorskip("fastapi")

from esports_sim.manager import new_campaign
from esports_sim.manager.state import MatchReview, ReviewPoint, StaffMember
from esports_sim.web import server


@pytest.mark.parametrize("second_manager", [False, True])
@pytest.mark.parametrize("status", ["current", "departed", "missing", "missing_record"])
@pytest.mark.parametrize("young", [False, True])
def test_review_player_advice_requires_current_acting_squad(
    game_data, second_manager, status, young, monkeypatch
):
    gs = new_campaign(game_data, seed=2038)
    tid = next(t for t in gs.teams if t != gs.user_team_id) if second_manager else gs.user_team_id
    if second_manager:
        gs.human_team_ids.append(tid)
    gs.set_acting(tid)
    pid, current_pid = gs.teams[tid].player_ids[:2]
    gs.players[pid].age = 20 if young else 29
    monkeypatch.setattr(server, "_player_developing", lambda gs, pl: (young, [80, 90]))
    if status in {"departed", "missing"}:
        gs.teams[tid].player_ids.remove(pid)
    if status in {"missing", "missing_record"}:
        del gs.players[pid]
    gs.staff["coach"] = StaffMember(id="co", name="Coach", role="coach", quality=85, salary=1, specialty="team")
    gs.last_review_by[tid] = MatchReview(
        fixture_id="historical", team_id=tid,
        breaking=[
            ReviewPoint(code="player_under", category="player", tone="bad", player_id=pid, value=.72, lever_code="player_form"),
            ReviewPoint(code="player_under", category="player", tone="bad", player_id=current_pid, value=.75, lever_code="player_form"),
            ReviewPoint(code="atk_side", category="team", tone="bad", value=.2, lever_code="atk_tempo"),
        ],
    )
    # Existing state accessors initialize manager buckets on first access.
    gs.facilities
    before = gs.model_dump_json()
    view = server._last_match_review(gs)
    assert gs.model_dump_json() == before
    point = view["breaking"][0]
    assert point["player_id"] == pid and "0.72" in point["detail"]
    form = next(l for l in view["levers"] if l["code"] == "player_form")
    if status == "current":
        assert gs.players[pid].handle in form["text"]
        assert "mentor" in form["text"] if young else "bench or agent" in form["text"]
        assert "Historical" not in point["dev_note"]
    else:
        assert "no longer in your squad" in point["dev_note"]
        assert "proj." not in point["dev_note"]
        assert gs.players[current_pid].handle in form["text"]
        assert (gs.players[pid].handle if pid in gs.players else pid) not in form["text"]
    assert any(l["code"] == "atk_tempo" and l["adjustment"] for l in view["levers"])
    gs.staff.pop("coach")
    assert server._last_match_review(gs)["levers"] == []
