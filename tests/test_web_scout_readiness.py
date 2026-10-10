"""Current-fixture guidance reconciles standing coverage with optional deep dives."""
import pytest
from esports_sim.manager import new_campaign
from esports_sim.web import server

@pytest.mark.parametrize('progress,playbook', [(0,0),(.34,.85),(.499,.85),(.5,0)])
def test_standing_coverage_without_deep_dive(game_data, progress, playbook):
    gs = new_campaign(game_data, seed=2038, user_team_id='team_nexus')
    tid = gs.acting_team_id
    fix = gs.team_fixture(tid)
    opp = fix.team_b if fix.team_a == tid else fix.team_a
    gs.scout_lanes_by[tid] = {'pro':'scout_opponents'}
    gs.scout_targets[tid] = None
    gs.scout_progress_by[tid] = {opp:progress}
    gs.scout_playbook_by[tid] = {opp:{'value':playbook}}
    before = gs.model_dump_json()
    view = server._fixture_scout_readiness(gs, tid)
    assert gs.model_dump_json() == before
    assert view['assigned'] and view['source'] == 'Standing pro lane'
    assert 'Unassigned' not in view['status']
    assert view['measured'] == bool(progress or playbook)
    assert view['ready'] == (progress >= .5)
    assert (view['tone'] == 'ready') == (progress >= .5)
    counter = server._gameplan_counter_reads(gs, fix, None)
    assert view['ready'] == counter['opponent_revealed']
    if progress and progress < .5:
        assert 'unlock at 50% scouting depth' in view['copy']
    if not progress:
        assert view['status'] == 'Assigned'
        assert 'No measured intel yet' in view['copy']

@pytest.mark.parametrize('assignment', ['other','current','match','none','fill_gap'])
def test_one_off_and_unassigned_contracts(game_data, assignment):
    gs = new_campaign(game_data, seed=2038, user_team_id='team_nexus')
    tid = gs.acting_team_id
    fix = gs.team_fixture(tid)
    opp = fix.team_b if fix.team_a == tid else fix.team_a
    targets = {'other':'player:vortex','current':opp,'match':f'match:{fix.id}', 'none':None,'fill_gap':None}
    gs.scout_targets[tid] = targets[assignment]
    gs.scout_lanes_by[tid] = {'pro':'fill_gap:duelist:prospect'} if assignment == 'fill_gap' else {}
    view = server._fixture_scout_readiness(gs, tid)
    assert view['assigned'] == (assignment in ('current','match'))
    if not view['assigned']:
        assert view['status'] == 'Unassigned'


def test_team_specific_and_stored_intel(game_data):
    gs = new_campaign(game_data, seed=2038, user_team_id='team_nexus')
    first = gs.acting_team_id
    other = next(tid for tid in gs.teams if tid != first and gs.team_fixture(tid))
    gs.human_team_ids.append(other)
    gs.scout_lanes_by[first] = {'pro':'scout_opponents'}
    assert server._fixture_scout_readiness(gs, first)['assigned']
    assert not server._fixture_scout_readiness(gs, other)['assigned']
    gs.set_acting(other)
    fix = gs.team_fixture(other)
    opp = fix.team_b if fix.team_a == other else fix.team_a
    gs.scout_progress_by[other] = {opp:.6}
    before = gs.model_dump_json()
    view = server._fixture_scout_readiness(gs, other)
    assert not view['assigned'] and view['measured'] and view['ready']
    assert 'Stored intel' in view['copy']
    assert gs.model_dump_json() == before
    gs.fixtures.clear()
    assert server._fixture_scout_readiness(gs, other) is None


