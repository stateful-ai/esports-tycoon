"""Historical grain, round placeholders, identity and sparse model contracts."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

BeautifulSoup=pytest.importorskip('bs4').BeautifulSoup
pytest.importorskip('scipy')
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import collect_vlr_research as collector
import collect_vlr_war_history as history
import analyze_vlr_war_history as analysis


def test_historical_match_dates_are_opt_in():
    spec=importlib.util.spec_from_file_location('vlr_fixture',SCRIPTS.parent/'tests/test_vlr_research.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    soup=fixture.match_fixture();EVENT=fixture.EVENT;SOURCE=fixture.SOURCE
    soup.select_one('[data-utc-ts]')['data-utc-ts']='2024-04-01 10:00:00'
    assert collector.parse_match(soup,EVENT,SOURCE,'2026-10-08')[2]=='outside_cutoff_or_missing_date'
    assert len(collector.parse_match(soup,EVENT,SOURCE,'2026-10-08','2024-01-01')[0])==1


def test_round_placeholder_is_not_a_played_round():
    html='''<div class="vlr-rounds-row-col" title="0-1"><div class="rnd-num">1</div>
    <div class="rnd-sq"></div><div class="rnd-sq mod-win mod-ct"><img src="/round/defuse.webp"></div></div>
    <div class="vlr-rounds-row-col"><div class="rnd-num">2</div><div class="rnd-sq"></div><div class="rnd-sq"></div></div>'''
    rows=history.parse_rounds(BeautifulSoup(html,'html.parser'),dict(match_id='1',map_id='2',team1_id='3',team2_id='4'))
    assert len(rows)==1
    assert rows[0]['team1_side']=='attack' and rows[0]['team2_side']=='defense'
    assert rows[0]['winner_team_id']=='4' and rows[0]['win_condition']=='defuse'


def test_economy_loadout_is_separate_from_rounded_bank():
    html='''<table class="mod-econ"><td><div class="round-num">1</div><div class="bank">0.3k</div>
    <div class="rnd-sq" title="3800"></div><div class="rnd-sq mod-win mod-ct" title="3550"></div><div class="bank">0.2k</div></td></table>'''
    rows=history.parse_economy(BeautifulSoup(html,'html.parser'),dict(match_id='1',map_id='2',team1_id='3',team2_id='4'))
    assert rows[0]['loadout_value']==3800 and rows[0]['bank_display']=='0.3k'
    assert rows[0]['buy_category_display']=='' and rows[0]['round_win']==0
    assert rows[1]['round_win']==1


def test_performance_ignores_hidden_hover_text_and_requires_unique_identity():
    html='''<table class="mod-adv-stats"><tr><th></th><th></th><th>2K</th><th>1v1</th><th>DE</th></tr>
    <tr><td><div class="team"><div>Name<div class="team-tag">TAG</div></div></div></td><td></td>
    <td><div class="stats-sq">5<div class="vm-perf-notable-scope">Round 99 Victim</div></div></td>
    <td><div class="stats-sq"></div></td><td><div class="stats-sq">0</div></td></tr></table>'''
    soup=BeautifulSoup(html,'html.parser');m=dict(match_id='1',map_id='2')
    players=[dict(map_id='2',handle='Name',team_tag_at_match='TAG',vlr_player_id='3',team_id='4')]
    row=history.parse_performance(soup,m,players)[0]
    assert row['two_k_rounds']==5 and row['clutch_1v1_wins'] is None and row['defuses']==0
    with pytest.raises(ValueError,match='Unresolved performance identity'):
        history.parse_performance(soup,m,players+players)


def test_sparse_fit_matches_existing_solver_and_preserves_orientation():
    from scipy.sparse import csr_matrix
    from analyze_vlr_research import fit_logistic
    x=np.array([[1,1,-1],[1,1,-1],[-1,-1,1],[1,1,-1]],dtype=float);y=np.array([1,1,0,0],dtype=float)
    coef=analysis.fit_sparse(csr_matrix(x),y,5)
    assert coef==pytest.approx(fit_logistic(x,y,5),abs=1e-6)
    assert analysis.fit_sparse(csr_matrix(-x),1-y,5)==pytest.approx(coef,abs=1e-6)


def test_model_design_cannot_consume_same_map_box_scores():
    maps=[dict(map_id='1',map_name='Haven',team1_id='A',team2_id='B',played_at_utc='2026-01-01')]
    rows={'1':[dict(vlr_player_id='p',team_id='A',kills=999,map_win=1),dict(vlr_player_id='q',team_id='B',kills=0,map_win=0)]}
    x,features=analysis.design(maps,rows,{'1':dict(team1_start_side='attack')},'hybrid')
    rows['1'][0].update(kills=0,map_win=0);rows['1'][1].update(kills=999,map_win=1)
    again,_=analysis.design(maps,rows,{'1':dict(team1_start_side='attack')},'hybrid')
    assert np.array_equal(x.toarray(),again.toarray())
    assert all(f[0] in {'player','team_year','team_map','map_start_side'} for f in features)


def test_series_bootstrap_is_deterministic_and_zero_for_identical_predictions():
    y=np.array([1.,0.,1.]);p=np.array([.8,.4,.7])
    result=analysis.bootstrap_difference(y,p,p,['a','a','b'])
    assert result['series']==2 and result['bootstrap_95pct_interval']==[0.,0.]
    assert result==analysis.bootstrap_difference(y,p,p,['a','a','b'])


def test_partial_lineup_is_not_treated_as_complete_opening_duel_totals(tmp_path):
    spec=importlib.util.spec_from_file_location('vlr_partial_fixture',SCRIPTS.parent/'tests/test_vlr_research.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    maps,players,_=collector.parse_match(fixture.match_fixture(),fixture.EVENT,fixture.SOURCE,'2026-10-08')
    players=players[1:];players[0]['first_kills']=1
    collector.write_csv(tmp_path/'map_outcomes.csv',maps)
    collector.write_csv(tmp_path/'player_map_stats.csv',players)
    collector.write_csv(tmp_path/'events.csv',[dict(event_id='10',collect_maps=False)])
    collector.write_csv(tmp_path/'player_event_stats.csv',[],['event_id','vlr_player_id'])
    from analyze_vlr_research import validate
    warnings=validate(tmp_path)['warnings']
    assert any('excluded from lineup model' in w for w in warnings)
    assert not any('FK ' in w and 'FD ' in w for w in warnings)


def test_academy_tag_difference_requires_unique_team_logo_and_agent():
    html='''<table class="mod-adv-stats"><tr><th></th><th></th><th>2K</th></tr><tr>
    <td><div class="team"><img class="team-logo" src="club.png"><div>Kring<div class="team-tag">MIBR</div></div></div></td>
    <td><img src="/viper.png"></td><td><div class="stats-sq">2</div></td></tr></table>'''
    soup=BeautifulSoup(html,'html.parser');m=dict(match_id='1',map_id='2')
    players=[dict(map_id='2',handle='Kring',team_tag_at_match='MIBR.AC',vlr_player_id='3',team_id='4',agent='viper')]
    with pytest.raises(ValueError,match='Unresolved performance identity'):
        history.parse_performance(soup,m,players)
    audit=[]
    assert history.parse_performance(soup,m,players,{'4':'club.png','5':'other.png'},audit)[0]['vlr_player_id']=='3'
    assert audit[0]['join_rule']=='unique_match_team_logo_local_handle_and_agent'
    with pytest.raises(ValueError,match='Unresolved performance identity'):
        history.parse_performance(soup,m,players,{'4':'club.png','5':'club.png'})
    # Distinct non-Latin handles must not collapse to the same empty ASCII key.
    players[0]['handle']='김'
    unicode_row=BeautifulSoup(html.replace('Kring','이'),'html.parser')
    with pytest.raises(ValueError,match='Unresolved performance identity'):
        history.parse_performance(unicode_row,m,players,{'4':'club.png','5':'other.png'})


def test_economy_model_excludes_disagreement_without_changing_source_facts(tmp_path):
    source=dict(source_url='https://www.vlr.gg/1/example',sha256='abc',retrieved_at_utc='2026-01-01')
    provenance=dict(source_url=source['source_url'],source_sha256='abc',retrieved_at_utc='2026-01-01')
    m=dict(match_id='1',map_id='2',rounds='2',team1_id='3',team2_id='4',team1_rounds='2',team2_rounds='0')
    rr=[dict(match_id='1',map_id='2',round_number=str(n),winner_team_id='3',team1_side='attack',
             team2_side='defense',team1_score_after=str(n),team2_score_after='0') for n in [1,2]]
    econ=[dict(match_id='1',map_id='2',round_number=str(n),team_id=tid,loadout_value='4000',
               round_win=int(tid=='3'),side='attack' if tid=='3' else 'defense') for n in [1,2] for tid in ['3','4']]
    collector.write_csv(tmp_path/'sources.csv',[source])
    collector.write_csv(tmp_path/'map_context.csv',[dict(map_id='2',**provenance)])
    collector.write_csv(tmp_path/'round_outcomes.csv',rr)
    collector.write_csv(tmp_path/'player_map_performance.csv',[],['map_id'])
    collector.write_csv(tmp_path/'tab_coverage.csv',[
        dict(match_id='1',map_id='2',tab=tab,rows=count,**provenance)
        for tab,count in [('overview_rounds',2),('economy',4),('performance',0)]])
    collector.write_csv(tmp_path/'round_economy.csv',econ)
    assert analysis.audit_context(tmp_path,[m],[])['economy_eligible_maps']==1
    econ[0]['round_win']=0
    collector.write_csv(tmp_path/'round_economy.csv',econ)
    raw=(tmp_path/'round_economy.csv').read_bytes()
    assert analysis.audit_context(tmp_path,[m],[])['economy_eligible_maps']==0
    row=analysis.read_csv(tmp_path/'economy_model_eligibility.csv')[0]
    assert 'winner_disagrees_with_overview' in row['reasons']
    assert (tmp_path/'round_economy.csv').read_bytes()==raw


def test_resume_discards_only_uncheckpointed_event_rows(tmp_path):
    collector.write_csv(tmp_path/'events.csv',[dict(event_id='10',map_rows=1)])
    collector.write_csv(tmp_path/'map_outcomes.csv',[dict(event_id='10',map_id='1'),dict(event_id='20',map_id='2')])
    names=['player_map_stats.csv','round_outcomes.csv','round_economy.csv','player_map_performance.csv']
    for name in names:collector.write_csv(tmp_path/name,[dict(map_id='1',value='kept'),dict(map_id='2',value='partial')])
    assert len(history.resume_checkpoint(tmp_path))==1
    for name in names:assert analysis.read_csv(tmp_path/name)==[dict(map_id='1',value='kept')]
    assert analysis.read_csv(tmp_path/'map_outcomes.csv')==[dict(event_id='10',map_id='1')]
    collector.write_csv(tmp_path/'events.csv',[dict(event_id='10',map_rows=2)])
    before=(tmp_path/'map_outcomes.csv').read_bytes()
    with pytest.raises(ValueError,match='refusing to resume'):history.resume_checkpoint(tmp_path)
    assert (tmp_path/'map_outcomes.csv').read_bytes()==before


def test_incomplete_http_body_is_retried_and_never_cached(tmp_path,monkeypatch):
    import gzip,hashlib,http.client
    calls=[];body=b'<h1>Complete</h1>'
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):
            if len(calls)==1:raise http.client.IncompleteRead(b'partial')
            return body
    def open_response(*args,**kwargs):calls.append(1);return Response()
    monkeypatch.setattr(collector.urllib.request,'urlopen',open_response)
    monkeypatch.setattr(collector.time,'sleep',lambda seconds:None)
    cache=collector.Cache(tmp_path);soup,source=cache.get('https://www.vlr.gg/example')
    assert len(calls)==2 and soup.h1.text=='Complete'
    assert source['sha256']==hashlib.sha256(body).hexdigest()
    assert gzip.decompress(next(tmp_path.glob('*.html.gz')).read_bytes())==body


def test_forfeit_placeholders_do_not_count_as_played_lineups():
    m=dict(map_id='1',map_name='Breeze',team1_id='A',team2_id='B',team1_rounds=0,team2_rounds=13)
    rows=[dict(vlr_player_id=str(i),team_id='A' if i<=5 else 'B',kills='0',deaths='0') for i in range(1,11)]
    context=dict(veto_note='Team has forfeited the match.')
    assert analysis.map_eligibility_reason(m,rows,context)=='administrative_scoreline_without_observed_play'
    rows[0]['kills']='13';rows[5]['deaths']='13'
    assert analysis.map_eligibility_reason(m,rows,context)=='ten_identified_players'
    m['map_name']='TBD'
    assert analysis.map_eligibility_reason(m,rows,{})=='unknown_map_requires_review'
