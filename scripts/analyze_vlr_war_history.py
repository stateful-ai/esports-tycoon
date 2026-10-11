"""Validate historical round facts and evaluate WAR research on future series.

Historical matches supply lineup variation, not causal identification. Current
map box scores/economy/clutches never predict that same map's outcome here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re

import numpy as np
from scipy.optimize import minimize
from scipy.sparse import csr_matrix

from analyze_vlr_research import agent_roles, lineup_eligible, metrics, read_csv, role_for, sigmoid, validate
from collect_vlr_research import ROOT, normalize, write_csv


def fit_sparse(x, y, penalty, weights=None):
    weights = np.ones(len(y)) if weights is None else weights
    def objective(coef):
        z = x @ coef
        loss = np.sum(weights * (np.logaddexp(0, z) - y*z)) + penalty/2 * (coef @ coef)
        grad = x.T @ (weights * (sigmoid(z)-y)) + penalty * coef
        return loss, grad
    result = minimize(objective, np.zeros(x.shape[1]), jac=True, method='L-BFGS-B',
                      options=dict(maxiter=1000, ftol=1e-12, gtol=1e-7))
    if not result.success:
        raise ValueError(f'Sparse fit failed: {result.message}')
    return result.x


def map_eligibility_reason(m,rows,context):
    if not lineup_eligible(m,rows):return 'incomplete_or_ambiguous_source_lineup'
    combat=[r.get(field) for r in rows for field in ['kills','deaths']]
    no_combat=all(v in [None,''] or float(v)==0 for v in combat)
    administrative=re.search(r'forfeit|disqualif|\bDQ\b',context.get('veto_note',''),re.I)
    if administrative and no_combat:return 'administrative_scoreline_without_observed_play'
    if m['map_name'].strip().lower() in {'','tbd','unknown','n/a'}:return 'unknown_map_requires_review'
    if no_combat and all(v not in [None,''] for v in combat):return 'zero_combat_placeholder_requires_review'
    return 'ten_identified_players'


def audit_context(data, maps, players):
    sources = {r['source_url']: r for r in read_csv(data/'sources.csv')}
    coverage = read_csv(data/'tab_coverage.csv')
    errors, warnings = [], []
    if (data/'roster_evidence_sources.csv').exists():
        roster_sources={r['source_url']:r for r in read_csv(data/'roster_evidence_sources.csv')}
        for name in ['profile_team_history.csv','roster_news_index.csv']:
            for r in read_csv(data/name):
                src=roster_sources.get(r['source_url'],{})
                if src.get('sha256')!=r['source_sha256'] or src.get('retrieved_at_utc')!=r['retrieved_at_utc']:
                    errors.append('Roster evidence source mismatch: '+r['source_url'])
    contexts=read_csv(data/'map_context.csv')
    for r in coverage + contexts:
        src = sources.get(r['source_url'], {})
        if src.get('sha256') != r['source_sha256'] or src.get('retrieved_at_utc') != r['retrieved_at_utc']:
            errors.append('Context source mismatch: '+r['source_url'])
    if (data/'agent_role_reference.csv').exists():
        import gzip
        import hashlib
        ref_source=json.loads((data/'reference/valorant-agent-source.json').read_text())
        body=gzip.decompress((data/'reference/valorant-agents.json.gz').read_bytes())
        if hashlib.sha256(body).hexdigest()!=ref_source['sha256']:errors.append('Agent reference body hash mismatch')
        for r in read_csv(data/'agent_role_reference.csv'):
            if r['source_sha256']!=ref_source['sha256'] or r['retrieved_at_utc']!=ref_source['retrieved_at_utc']:
                errors.append('Agent reference provenance mismatch')
    outcomes = {m['map_id']: m for m in maps}
    context_keys=[r['map_id'] for r in contexts]
    if len(context_keys)!=len(set(context_keys)):
        errors.append('Duplicate map context')
    missing_context=set(outcomes)-set(context_keys)
    if missing_context:
        warnings.append(f'{len(missing_context)} maps lack context after a source parsing issue')
    rr = read_csv(data/'round_outcomes.csv'); econ = read_csv(data/'round_economy.csv')
    perf = read_csv(data/'player_map_performance.csv')
    for name, records, key in [('rounds',rr,['match_id','map_id','round_number']),
                               ('economy',econ,['match_id','map_id','round_number','team_id']),
                               ('performance',perf,['match_id','map_id','vlr_player_id']),
                               ('tab_coverage',coverage,['match_id','map_id','tab'])]:
        keys = [tuple(r[k] for k in key) for r in records]
        if len(keys) != len(set(keys)):
            errors.append(name+': duplicate keys')
    grouped = defaultdict(list)
    for r in rr:
        grouped[r['map_id']].append(r)
    round_index = {(r['map_id'],r['round_number']):r for r in rr}
    eligibility = []
    for m in maps:
        observed = sorted(grouped[m['map_id']],key=lambda r:int(r['round_number']))
        reasons = []
        if len(observed) != int(m['rounds']):
            reasons.append('round_count_differs_from_scoreline')
        scores = [0,0]
        for n,r in enumerate(observed,1):
            if int(r['round_number']) != n:
                reasons.append('non_contiguous_round_numbers')
            if r['winner_team_id'] not in [m['team1_id'],m['team2_id']]:
                errors.append('Invalid round winner '+m['map_id']); continue
            i = int(r['winner_team_id']==m['team2_id']); scores[i] += 1
            shown = [r['team1_score_after'],r['team2_score_after']]
            if all(shown) and scores != [int(v) for v in shown]:
                reasons.append('cumulative_score_discrepancy')
            if set([r['team1_side'],r['team2_side']]) != {'attack','defense'}:
                reasons.append('missing_side')
        if scores != [int(m['team1_rounds']),int(m['team2_rounds'])]:
            reasons.append('round_winner_totals_differ_from_scoreline')
        eligibility.append(dict(match_id=m['match_id'],map_id=m['map_id'],round_rows=len(observed),
                                round_model_eligible=not reasons, reasons='|'.join(sorted(set(reasons)))))
    lookup = {(p['map_id'],p['vlr_player_id']):p for p in players}
    tab_keys = {(c['map_id'],c['tab']) for c in coverage}
    for r in rr + econ + perf:
        m = outcomes.get(r['map_id'])
        if not m or m['match_id'] != r['match_id']:
            errors.append('Orphan context row '+r['map_id'])
    econ_by_round=defaultdict(list)
    for r in econ:
        econ_by_round[(r['map_id'],r['round_number'])].append(r)
        m = outcomes.get(r['map_id'],{})
        if r['team_id'] not in [m.get('team1_id'),m.get('team2_id')] or (r['map_id'],'economy') not in tab_keys:
            errors.append('Invalid economy join '+r['map_id'])
        if r['loadout_value'] and float(r['loadout_value']) < 0:
            errors.append('Negative loadout '+r['map_id'])
        ref = round_index.get((r['map_id'],r['round_number']))
        if not ref and grouped[r['map_id']]:
            warnings.append('Economy round missing from overview '+r['map_id']+' round '+r['round_number'])
        if ref and int(r['round_win']) != int(ref['winner_team_id']==r['team_id']):
            warnings.append('Economy/overview winner differs '+r['map_id']+' round '+r['round_number'])
    for key,observed in econ_by_round.items():
        if len(observed)!=2 or sum(int(r['round_win']) for r in observed)!=1:
            warnings.append('Incomplete or ambiguous economy round '+str(key))
    overview_valid={r['map_id'] for r in eligibility if r['round_model_eligible']}
    economy_by_map=defaultdict(list)
    for r in econ:economy_by_map[r['map_id']].append(r)
    economy_eligibility=[]
    for m in maps:
        mid=m['map_id'];observed=economy_by_map[mid];reasons=set()
        expected={str(n) for n in range(1,int(m['rounds'])+1)}
        if mid not in overview_valid:reasons.add('overview_round_history_ineligible')
        if len(observed)!=2*int(m['rounds']) or {r['round_number'] for r in observed}!=expected:
            reasons.add('economy_round_coverage_incomplete')
        for rnd in expected:
            rows=econ_by_round[(mid,rnd)];ref=round_index.get((mid,rnd))
            if {r['team_id'] for r in rows}!={m['team1_id'],m['team2_id']} or len(rows)!=2:
                reasons.add('missing_or_ambiguous_team_round')
            for r in rows:
                if not r['loadout_value']:reasons.add('missing_loadout_value')
                if not ref:continue
                if int(r['round_win'])!=int(ref['winner_team_id']==r['team_id']):
                    reasons.add('winner_disagrees_with_overview')
                slot=1 if r['team_id']==m['team1_id'] else 2
                if r['side']!=ref[f'team{slot}_side']:reasons.add('side_disagrees_with_overview')
        economy_eligibility.append(dict(match_id=m['match_id'],map_id=mid,team_round_rows=len(observed),
                                        economy_model_eligible=not reasons,reasons='|'.join(sorted(reasons))))
    write_csv(data/'economy_model_eligibility.csv',economy_eligibility)
    performance_review=[]
    for r in perf:
        ref = lookup.get((r['map_id'],r['vlr_player_id']))
        if not ref or ref['team_id'] != r['team_id'] or (r['map_id'],'performance') not in tab_keys:
            errors.append('Invalid performance identity join '+r['map_id'])
        for field,value in r.items():
            if field not in {'match_id','map_id','vlr_player_id','team_id'} and value:
                numeric=float(value)
                if field=='econ_rating' and numeric<0:
                    warnings.append('Source-negative ECON retained for review: '+r['map_id']+' player '+r['vlr_player_id'])
                    performance_review.append(dict(match_id=r['match_id'],map_id=r['map_id'],vlr_player_id=r['vlr_player_id'],
                                                   field=field,source_value=value,use_for_performance_model=False,
                                                   review_state='negative_source_econ_requires_definition_review'))
                elif numeric<0 or (field!='econ_rating' and not numeric.is_integer()):
                    errors.append('Invalid performance value '+r['map_id']+' '+field)
    write_csv(data/'performance_value_review.csv',performance_review,
              ['match_id','map_id','vlr_player_id','field','source_value','use_for_performance_model','review_state'])
    actual_counts = Counter((r['map_id'],'overview_rounds') for r in rr)
    actual_counts.update((r['map_id'],'economy') for r in econ)
    actual_counts.update((r['map_id'],'performance') for r in perf)
    for c in coverage:
        if int(c['rows']) != actual_counts[(c['map_id'],c['tab'])]:
            errors.append('Tab count mismatch '+c['map_id']+' '+c['tab'])
    write_csv(data/'round_model_eligibility.csv',eligibility)
    side_receipt={}
    if (data/'player_map_side_stats.csv').exists():
        sides=read_csv(data/'player_map_side_stats.csv')
        keys=[(r['map_id'],r['vlr_player_id'],r['side']) for r in sides]
        if len(keys)!=len(set(keys)):errors.append('Duplicate player-map-side keys')
        split_stats=defaultdict(list)
        valid_rounds={r['map_id'] for r in eligibility if r['round_model_eligible']}
        exposure=Counter()
        for r in rr:
            m=outcomes[r['map_id']]
            for i in [1,2]:exposure[(r['map_id'],m[f'team{i}_id'],r[f'team{i}_side'])]+=1
        for r in sides:
            ref=lookup.get((r['map_id'],r['vlr_player_id']))
            if not ref or ref['team_id']!=r['team_id'] or r['side'] not in {'attack','defense'}:
                errors.append('Invalid side-stat identity '+r['map_id'])
            if r['map_id'] in valid_rounds:
                if r['rounds_played']!=str(exposure[(r['map_id'],r['team_id'],r['side'])]):
                    errors.append('Incorrect side exposure '+r['map_id'])
            elif r['rounds_played']:
                errors.append('Exposure invented for invalid round history '+r['map_id'])
            split_stats[(r['map_id'],r['vlr_player_id'])].append(r)
        for key,records in split_stats.items():
            if len(records)!=2:errors.append('Missing side row '+str(key))
            ref=lookup.get(key,{})
            for field in ['kills','deaths','assists','first_kills','first_deaths']:
                if ref.get(field) and all(r[field] for r in records):
                    if sum(float(r[field]) for r in records)!=float(ref[field]):
                        warnings.append('Side count differs from both '+str(key)+' '+field)
        side_receipt=dict(player_map_side_rows=len(sides),side_rows_with_no_reported_stats=sum(r['reported_fields']=='0' for r in sides))
    receipt = dict(round_rows=len(rr),economy_team_round_rows=len(econ),performance_player_map_rows=len(perf),**side_receipt,
                   round_eligible_maps=sum(r['round_model_eligible'] for r in eligibility),
                   round_ineligible_maps=sum(not r['round_model_eligible'] for r in eligibility),
                   economy_eligible_maps=sum(r['economy_model_eligible'] for r in economy_eligibility),
                   economy_ineligible_maps=sum(not r['economy_model_eligible'] for r in economy_eligibility),
                   performance_values_requiring_review=len(performance_review),
                   maps_with_economy=len({r['map_id'] for r in econ}), maps_with_performance=len({r['map_id'] for r in perf}),
                   errors=sorted(set(errors)),warnings=sorted(set(warnings)),
                   missingness='Unreported values remain blank; displayed bank strings are rounded. Performance blanks do not become zero.',
                   provenance='Compact round/performance facts join map_id + tab to tab_coverage.csv, which reconciles hash and timestamp to sources.csv.')
    (data/'context_validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if errors:
        raise ValueError('Context validation failed')
    return receipt


def lineup_history(data, maps, by_map,contexts):
    last_team, last_player = {}, {}
    appearances, changes, moves = [], [], []
    for m in maps:
        if map_eligibility_reason(m,by_map[m['map_id']],contexts.get(m['map_id'],{}))!='ten_identified_players':
            continue
        for i in [1,2]:
            tid = m[f'team{i}_id']
            lineup = sorted([r['vlr_player_id'] for r in by_map[m['map_id']] if r['team_id']==tid],key=int)
            row = dict(match_id=m['match_id'],map_id=m['map_id'],played_at_utc=m['played_at_utc'],
                       event_id=m['event_id'],team_id=tid,team_name=m[f'team{i}_name'],lineup_ids='|'.join(lineup),source_url=m['source_url'])
            appearances.append(row)
            prev = last_team.get(tid)
            if prev and prev['lineup_ids'] != row['lineup_ids']:
                old = set(prev['lineup_ids'].split('|')); new = set(lineup)
                changes.append({**row,'previous_map_id':prev['map_id'],'previous_observed_at_utc':prev['played_at_utc'],
                                'previous_lineup_ids':prev['lineup_ids'],'players_in':'|'.join(sorted(new-old,key=int)),
                                'players_out':'|'.join(sorted(old-new,key=int)),
                                'status':'observed_lineup_change_not_verified_signing'})
            last_team[tid] = row
            for pid in lineup:
                old = last_player.get(pid)
                if old and old['team_id'] != tid:
                    moves.append(dict(vlr_player_id=pid,previous_team_id=old['team_id'],observed_team_id=tid,
                                      previous_observed_at_utc=old['played_at_utc'],first_observed_new_team_at_utc=m['played_at_utc'],
                                      previous_map_id=old['map_id'],observed_map_id=m['map_id'],source_url=m['source_url'],
                                      status='appearance_change_may_be_transfer_standin_or_affiliate'))
                last_player[pid] = row
    write_csv(data/'team_map_lineups.csv',appearances)
    write_csv(data/'observed_lineup_changes.csv',changes)
    write_csv(data/'observed_player_team_changes.csv',moves)
    return appearances, changes, moves


def design(maps, by_map, contexts, kind):
    rr,cc,vv = [],[],[]; feature_ids = {}
    def add(i,key,value):
        j=feature_ids.setdefault(key,len(feature_ids)); rr.append(i);cc.append(j);vv.append(value)
    for i,m in enumerate(maps):
        if kind in {'lineup','hybrid'}:
            for r in by_map[m['map_id']]:
                add(i,('player',r['vlr_player_id']),1 if r['team_id']==m['team1_id'] else -1)
        if kind in {'team','hybrid'}:
            for t,sign in [(m['team1_id'],1),(m['team2_id'],-1)]:
                add(i,('team_year',t,m['played_at_utc'][:4]),sign)
                add(i,('team_map',t,m['map_name']),sign)
        c=contexts.get(m['map_id'],{})
        start=c.get('team1_start_side')
        if start in {'attack','defense'}:
            add(i,('map_start_side',m['map_name']),1 if start=='attack' else -1)
    return csr_matrix((vv,(rr,cc)),shape=(len(maps),len(feature_ids))),feature_ids


def bootstrap_difference(y, p, baseline, matches):
    # Deterministic resampling of entire series, preserving within-series dependence.
    def losses(q):
        q=np.clip(q,1e-8,1-1e-8);return -(y*np.log(q)+(1-y)*np.log(1-q))
    diff=losses(p)-losses(baseline)
    sums=defaultdict(float);counts=Counter()
    for mid,d in zip(matches,diff):
        sums[mid]+=d;counts[mid]+=1
    ids=sorted(sums);ss=np.array([sums[i] for i in ids]);nn=np.array([counts[i] for i in ids])
    seed=int.from_bytes(hashlib.blake2b(b'vlr-war-history:series-bootstrap:20261008',digest_size=8).digest(),'little')
    rng=np.random.default_rng(seed)
    ix=rng.integers(0,len(ids),size=(2000,len(ids)))
    samples=ss[ix].sum(axis=1)/nn[ix].sum(axis=1)
    return dict(lineup_minus_team_log_loss=float(diff.mean()),
                bootstrap_95pct_interval=np.quantile(samples,[.025,.975]).tolist(),series=len(ids),
                method='2000 paired series-cluster bootstrap resamples; blake2b-derived seed from vlr-war-history:series-bootstrap:20261008. Conditional on fixed fitted models; not player-coefficient uncertainty.')


def evaluate(data,maps,by_map,contexts):
    maps=[m for m in maps if map_eligibility_reason(m,by_map[m['map_id']],contexts.get(m['map_id'],{}))=='ten_identified_players']
    y=np.array([int(m['winner_team_id']==m['team1_id']) for m in maps],dtype=float)
    dates=np.array([m['played_at_utc'][:10] for m in maps])
    inner=dates<'2026-04-01';val=(dates>='2026-04-01')&(dates<'2026-07-15')
    train=dates<'2026-07-15';test=~train
    if not all(a.any() for a in [inner,val,train,test]):
        raise ValueError('Insufficient dates for fixed historical split')
    fitted,predictions,tuning={}, {}, {}
    # Every model is evaluated on the same later maps. Season-only ablation
    # distinguishes extra history from merely expanding test coverage.
    for label,kind,history in [('team_year_map','team',True),('lineup_history','lineup',True),
                               ('lineup_2026_only','lineup',False),('hybrid_history','hybrid',True)]:
        x,features=design(maps,by_map,contexts,kind)
        available=np.ones(len(maps),dtype=bool) if history else dates>='2026-01-01'
        choices=[]
        half_lives=[None,365] if history else [None]
        def weights_for(anchor,half_life):
            age=(np.datetime64(anchor)-dates.astype('datetime64[D]')).astype(float)
            return np.exp2(-np.maximum(age,0)/half_life) if half_life else np.ones(len(dates))
        for half_life in half_lives:
            weights=weights_for('2026-04-01',half_life)
            for penalty in [1.,5.,20.]:
                mask=inner&available
                coef=fit_sparse(x[mask],y[mask],penalty,weights[mask])
                choices.append(dict(penalty=penalty,half_life_days=half_life,**metrics(y[val],sigmoid(x[val]@coef))))
        selected=min(choices,key=lambda c:c['log_loss']);penalty=selected['penalty'];half_life=selected['half_life_days']
        weights=weights_for('2026-07-15',half_life)
        mask=train&available
        coef=fit_sparse(x[mask],y[mask],penalty,weights[mask])
        predictions[label]=sigmoid(x[test]@coef)
        fitted[label]=(x,features,coef,penalty,half_life)
        tuning[label]=dict(validation=choices,selected_penalty=penalty,selected_half_life_days=half_life,train_maps=int((train&available).sum()),
                           test=metrics(y[test],predictions[label]))
    baseline=predictions['team_year_map']
    comparison={label:bootstrap_difference(y[test],p,baseline,[m['match_id'] for m,t in zip(maps,test) if t])
                for label,p in predictions.items() if label!='team_year_map'}
    latest={};changed=[]
    for m,t in zip(maps,train):
        lineups={m[f'team{i}_id']:frozenset(r['vlr_player_id'] for r in by_map[m['map_id']] if r['team_id']==m[f'team{i}_id']) for i in [1,2]}
        if t:
            latest.update(lineups)
        else:
            changed.append(any(tid in latest and latest[tid]!=ps for tid,ps in lineups.items()))
    changed=np.array(changed)
    subset={label:metrics(y[test][changed],p[changed]) for label,p in predictions.items()} if changed.any() else {}
    test_maps=[m for m,t in zip(maps,test) if t]
    write_csv(data/'heldout_map_predictions.csv',[dict(match_id=m['match_id'],map_id=m['map_id'],
              played_at_utc=m['played_at_utc'],team1_win=int(target),changed_from_training_lineup=bool(ch),
              **{label:round(float(predictions[label][i]),8) for label in predictions})
              for i,(m,target,ch) in enumerate(zip(test_maps,y[test],changed))])
    # Diagnose exact identity columns on all collected maps; no causal claim.
    x,features,coef,penalty,half_life=fitted['lineup_history']
    anchor=json.loads((data/'event_manifest.json').read_text())['as_of_date']
    age=(np.datetime64(anchor)-dates.astype('datetime64[D]')).astype(float)
    weights=np.exp2(-np.maximum(age,0)/half_life) if half_life else np.ones(len(dates))
    full=fit_sparse(x,y,penalty,weights)
    ids=sorted({r['vlr_player_id'] for m in maps for r in by_map[m['map_id']]},key=int)
    signatures=defaultdict(list); observed=defaultdict(list); teammates=defaultdict(Counter); parent={p:p for p in ids}
    xc=x.tocsc()
    for p in ids:
        j=features[('player',p)]; col=xc[:,j]
        signatures[(col.indices.tobytes(),col.data.tobytes())].append(p)
    x2026=xc[dates>='2026-01-01',:].tocsc();season_signatures=defaultdict(list)
    for p in ids:
        col=x2026[:,features[('player',p)]]
        if col.nnz:season_signatures[(col.indices.tobytes(),col.data.tobytes())].append(p)
    season_players={p for group in season_signatures.values() for p in group}
    season_tied={p for group in season_signatures.values() if len(group)>1 for p in group}
    historical_tied={p for group in signatures.values() if len(group)>1 for p in group}
    matched_cohort=dict(players_2026=len(season_players),inseparable_with_2026_only=len(season_tied),
                        inseparable_with_history=len(season_players&historical_tied),
                        exact_ties_resolved_by_history=len(season_tied-historical_tied))
    def root(p):
        while parent[p]!=p:
            parent[p]=parent[parent[p]];p=parent[p]
        return p
    for m in maps:
        rows=by_map[m['map_id']];ps=[r['vlr_player_id'] for r in rows]
        for p in ps[1:]:parent[root(p)]=root(ps[0])
        for r in rows:
            p=r['vlr_player_id'];observed[p].append(r)
            teammates[p].update(s['vlr_player_id'] for s in rows if s['team_id']==r['team_id'] and s['vlr_player_id']!=p)
    components={p:root(p) for p in ids};roles=agent_roles()
    if (data/'agent_role_reference.csv').exists():
        reference={r['agent_key']:r['role'] for r in read_csv(data/'agent_role_reference.csv')}
        for obs in observed.values():
            for r in obs:
                agent=r['agent'].split('|')[0]
                if normalize(agent) in reference:roles[agent]=reference[normalize(agent)]
    role_observations={p:[r for r in observed[p] if r['played_at_utc'][:4]=='2026'] or observed[p] for p in ids}
    role={p:Counter(role_for(r,roles) for r in role_observations[p]).most_common(1)[0][0] for p in ids}
    role_scope={p:'2026' if any(r['played_at_utc'][:4]=='2026' for r in observed[p]) else 'historical_fallback' for p in ids}
    pool=[p for p in ids if sum(r['competition_tier']=='2' and r['played_at_utc'][:4]=='2026' for r in observed[p])>=10]
    profile_rows=read_csv(ROOT/'data/research/vct-2026/player_profiles.csv')
    profiles={r['vlr_player_id']:r for r in profile_rows}
    write_csv(data/'replacement_pool_review.csv',[
        dict(vlr_player_id=p,handle=observed[p][-1]['handle'],observed_role=role[p],observed_role_scope=role_scope[p],component_id=components[p],
             tier2_maps_2026=sum(r['competition_tier']=='2' and r['played_at_utc'][:4]=='2026' for r in observed[p]),
             observed_regions_2026='|'.join(sorted({r['region'] for r in observed[p] if r['played_at_utc'][:4]=='2026'})),
             last_observed_match_utc=observed[p][-1]['played_at_utc'],
             last_observed_team_id=observed[p][-1]['team_id'],last_observed_team_name=observed[p][-1]['team_name'],
             current_team_listing_evidence=profiles.get(p,{}).get('current_team_evidence',''),
             inactive_news_evidence=profiles.get(p,{}).get('inactive_news_evidence',''),
             profile_source_url=profiles.get(p,{}).get('source_url',''),
             profile_retrieved_at_utc=profiles.get(p,{}).get('retrieved_at_utc',''),
             contract_availability='unverified',regional_eligibility='unverified',
             review_state='statistical_candidate_requires_availability_check') for p in pool])
    output=[]
    full_logits=x@full
    for group in signatures.values():
        for p in group:
            j=features[('player',p)];obs=observed[p]
            peers=[q for q in pool if role[p]!='unknown' and components[q]==components[p] and role[q]==role[p] and q!=p]
            replacement=float(np.quantile([full[features[('player',q)]] for q in peers],.25)) if len(peers)>=8 else None
            col=xc[:,j]; ix=col.indices; own=full_logits[ix]*col.data
            delta=full[j]-replacement if replacement is not None else None
            win_deltas=sigmoid(own)-sigmoid(own-delta) if delta is not None else None
            wins=float(win_deltas.sum()) if win_deltas is not None else None
            season=dates[ix]>='2026-01-01'
            season_wins=float(win_deltas[season].sum()) if win_deltas is not None and season.any() else None
            closest,shared=sorted(teammates[p].items(),key=lambda item:(-item[1],int(item[0])))[0]
            output.append(dict(vlr_player_id=p,handle=obs[-1]['handle'],maps=len(obs),maps_2026=sum(r['played_at_utc'][:4]=='2026' for r in obs),
                               teams_observed=len({r['team_id'] for r in obs}),observed_role=role[p],observed_role_scope=role_scope[p],component_id=components[p],
                               inseparable_teammates='|'.join(q for q in group if q!=p),lineup_coefficient=round(float(full[j]),6),
                               most_frequent_teammate_id=closest,most_frequent_teammate_shared_maps=shared,
                               max_teammate_coappearance_fraction=shared/len(obs),maps_without_most_frequent_teammate=len(obs)-shared,
                               replacement_pool_players=len(peers),replacement_coefficient=replacement,
                               experimental_historical_war_proxy=wins,
                               experimental_2026_war_proxy=season_wins,
                               experimental_2026_war_per_100_maps=100*season_wins/int(season.sum()) if season_wins is not None else None,
                               replacement_availability='unverified_statistical_tier2_pool',use_for_game_overall=False))
    write_csv(data/'experimental_historical_war.csv',sorted(output,key=lambda r:int(r['vlr_player_id'])))
    inputs=['event_manifest.json','map_outcomes.csv','player_map_stats.csv','map_context.csv',
            'agent_role_reference.csv']
    receipt=dict(model_version=2,
                  input_sha256={name:hashlib.sha256((data/name).read_bytes()).hexdigest()
                                for name in inputs if (data/name).exists()},
                  code_sha256={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
                               for name in ['analyze_vlr_war_history.py','analyze_vlr_research.py']},
                  dependencies={name:importlib.metadata.version(name) for name in ['numpy','scipy']},
                  cutoffs=dict(validation_start='2026-04-01',test_start='2026-07-15'),
                  split_unit='UTC calendar date; entire series kept together',eligible_maps=len(maps),players=len(ids),
                  exactly_inseparable_players=sum(bool(r['inseparable_teammates']) for r in output),connected_components=len(set(components.values())),
                  matched_2026_cohort_identification=matched_cohort,
                  unknown_role_players=sum(role[p]=='unknown' for p in ids),
                  train_maps=int(train.sum()),test_maps=int(test.sum()),models=tuning,paired_comparison=comparison,
                  changed_lineup_test_maps=int(changed.sum()),changed_lineup_test_metrics=subset,
                  feature_rules='Signed player identities; team-year and team-map identities for baseline/hybrid; map starting side. Same-map outcome stats are excluded. Unseen columns fit to zero under ridge.',
                  historical_weighting='Equal weights versus 365-day half-life chosen on validation only; age measured before each fitting boundary. Team-year baseline permits team strength to change by year.',
                  war_rules='Full-history refit after heldout evaluation; replace player coefficient with 25th percentile same-component/same-role >=10-map 2026 tier2 pool; blank when <8 peers. Dominant role uses 2026 appearances, with historical fallback for players absent in 2026.',
                  limits=['Observational, not causal WAR','Lineup variation does not eliminate near-collinearity, coaching or selection confounds',
                          '2024/2025 coverage is tier1 plus Ascension; historical tier2 league coverage is incomplete',
                          'Bank/economy are rounded source displays; no weapon inventory/trades/utility event feed',
                          'Replacement pool is not a verified available free-agent market','No coefficient uncertainty or automatic overall updates'])
    (data/'model_evaluation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'data/research/war-history')
    p.add_argument('--validate-only',action='store_true');args=p.parse_args();data=args.data
    receipt=validate(data)
    maps=sorted(read_csv(data/'map_outcomes.csv'),key=lambda r:(r['played_at_utc'],int(r['match_id']),int(r['map_id'])))
    players=read_csv(data/'player_map_stats.csv');by_map=defaultdict(list)
    for r in players:by_map[r['map_id']].append(r)
    contexts={r['map_id']:r for r in read_csv(data/'map_context.csv')}
    write_csv(data/'map_model_eligibility.csv',[
        dict(match_id=m['match_id'],map_id=m['map_id'],event_id=m['event_id'],
             observed_player_rows=len(by_map[m['map_id']]),
             lineup_model_eligible=map_eligibility_reason(m,by_map[m['map_id']],contexts.get(m['map_id'],{}))=='ten_identified_players',
             reason=map_eligibility_reason(m,by_map[m['map_id']],contexts.get(m['map_id'],{})),
             source_url=m['source_url']) for m in maps])
    context=audit_context(data,maps,players)
    if args.validate_only:return
    appearances,changes,moves=lineup_history(data,maps,by_map,contexts)
    model=evaluate(data,maps,by_map,contexts)
    summary=dict(**receipt['counts'],**{k:v for k,v in context.items() if k not in ['errors','warnings']},
                 map_eligibility_reasons=dict(Counter(map_eligibility_reason(m,by_map[m['map_id']],contexts.get(m['map_id'],{})) for m in maps)),
                 maps_by_year=dict(Counter(m['played_at_utc'][:4] for m in maps)),
                 observed_lineup_changes=len(changes),observed_player_team_changes=len(moves),
                 players_observed_with_multiple_teams=len({r['vlr_player_id'] for r in moves}),
                 model=model,runtime_roster_edits=False)
    (data/'research_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='model'},indent=2),flush=True)
    print(json.dumps(model,indent=2),flush=True)


if __name__=='__main__':main()
