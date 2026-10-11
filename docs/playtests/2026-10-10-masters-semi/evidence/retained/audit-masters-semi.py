import hashlib,json,os,shutil,socket,subprocess,sys,urllib.request
from collections import Counter,defaultdict
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import psutil
root=Path('C:/Users/aidan/workspace/esports-sponsor-playtest-20261010')
topic='2026-10-10-masters-semi';run=root/'runs/playtests'/topic;docs=root/'docs/playtests'/topic;ev=docs/'evidence';ev.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (ev/'audit.json').exists()
b=read(run/'save-before.json');pre=read(run/'save-pre-advance.json');save_path=run/'saves/campaign_f2977bf6e97d789a.json';s=read(save_path)
assert (len(b['action_log']),len(pre['action_log']),len(s['action_log']))==(75,78,79)
assert s['action_log'][:75]==b['action_log'] and s['action_log'][:78]==pre['action_log']
new=s['action_log'][75:];assert [a['kind'] for a in new]==['set_scout','series_directive','set_game_plan','advance']
assert all(a['source']=='web' and a['team_id']=='team_nexus' and (a['season'],a['week'])==(1,18) for a in new)
assert new[0]['params']=={'target':'player:slice'}
assert new[1]['params']==dict(clear='False',fixture_id='s1msf0',response='stabilize',substitute_in='fa_0',substitute_out='ghost',trigger='after_loss')
assert new[2]['params']['focus_target']=='slice' and new[2]['params']['fixture_id']=='s1msf0' and new[2]['params']['n_dials']=='0' and json.loads(new[2]['params']['starter_ids'])==[]
assert s['week']==19 and s['teams']['team_nexus']['balance']==1564014
assert s['teams']['team_nexus']['lineup_ids']==b['teams']['team_nexus']['lineup_ids']==['apex','vortex','ghost','fa_13','echo']
assert 'team_nexus' not in s['game_plans_by'] and 'team_nexus' not in s['series_directives_by'] and 'team_nexus' not in pre['preparation_plans_by']
for k,v in b['telemetry_snaps'].items():assert s['telemetry_snaps'][k][:len(v)]==v
assert len(s['telemetry_snaps'])==1 and (len(b['telemetry_snaps']['mgr_team_nexus']),len(s['telemetry_snaps']['mgr_team_nexus']))==(17,18)
fixture=next(f for f in s['fixtures'] if f['id']=='s1msf0')
assert fixture['winner_id']=='team_vanguard' and [(r['map_id'],r['score_b'],r['score_a']) for r in fixture['results']]==[('haven',17,19),('ascent',14,12),('lotus',6,13)]
assert fixture['series_notes']==['NXS: Hollowlock replaces Ghost after map 1.','NXS: stabilize response after map 1.']
for i,r in enumerate(fixture['results']):
 ids={l['player_id'] for l in r['lines']};assert ('ghost' in ids)==(i==0) and ('fa_0' in ids)==(i>0)
assert b['scout_progress_by']['team_nexus'].get('player:slice',0)==0 and s['scout_progress_by']['team_nexus']['player:slice']==0.29 and s['scout_progress_by']['team_nexus']['team_vanguard']==0.5
assert (b['players']['ghost']['stamina'],s['players']['ghost']['stamina'])==(59.5,70.5)
manifest=read(run/'source-manifest.json');assert len(manifest['source_sha256'])==545 and all(sha(root/p)==h for p,h in manifest['source_sha256'].items())
server=read(run/'server-running.json');assert sha(Path(server['fixture_source'])/save_path.name)==server['fixture_sha256']=='999038d35e4e45460fa2b495591599dcf4042fc44206fdb4b84d586dca18186f'
assert sha(run/'pre-advance-fixture'/save_path.name)=='e8c864a4fb5f6e5894cab49cb4e7e40939a9335286aa1a7f1506036c7a100743'
# Read only public APIs under the copied test identity; never retain credentials.
members=read(run/'saves/sessions.json')['sessions'];sid=[k for k,v in members.items() if v==['26UHC','team_nexus']];assert len(sid)==1
public={}
for label,url in [('report','/api/report'),('scouting','/api/scouting'),('club','/api/club'),('state','/api/state')]:
 request=urllib.request.Request('http://127.0.0.1:8516'+url,headers={'Cookie':'esports_sid='+sid[0]})
 with urllib.request.urlopen(request,timeout=20) as response:public[label]=json.load(response)
 (ev/('public-'+label+'.json')).write_text(json.dumps(public[label],indent=2),encoding='utf-8')
report=public['report']['report'];assert report['user_income']==111906 and report['user_expenses']==47100
assert s['teams']['team_nexus']['balance']-b['teams']['team_nexus']['balance']==111906-47100==64806
assert public['scouting']['target']=='player:slice' and public['scouting']['progress']==0.5
assert public['club']['series']['directive'] is None
events=[json.loads(line) for p in sorted((run/'saves/usage').glob('*.jsonl')) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
assert all(e['world']=='26UHC' and e['team']=='team_nexus' for e in events)
groups=defaultdict(list)
for e in events:
 if e['kind'] in ('attempt','result'):groups[(e['session_id'],e['request_id'],e['target'])].append(e)
pairs=[dict(session_id=ses,request_id=rid,target=t,events=v) for (ses,rid,t),v in groups.items()]
assert len(pairs)==6 and Counter(p['target'] for p in pairs)==Counter({'/api/actions/scout':1,'/api/actions/series_directive':1,'/api/actions/gameplan':1,'/api/actions/advance':1,'/api/actions/save':2})
for p in pairs:assert sorted(e['kind'] for e in p['events'])==['attempt','result'] and next(e for e in p['events'] if e['kind']=='result')['status']==200
exitcodes={}
for label,args in [('decision',['scripts/telemetry_report.py',str(run/'saves')]),('usage',['scripts/ui_usage_report.py',str(run/'saves/usage')])]:
 result=subprocess.run([sys.executable,*args],cwd=root,env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONUTF8='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (ev/(label+'-report.txt')).write_bytes(result.stdout);exitcodes[label]=result.returncode;assert result.returncode==0
for p in run.iterdir():
 if p.suffix in ('.txt','.json','.yml','.png') and p.name!='browser-identity-restored.json':shutil.copy2(p,ev/p.name)
for p in (run/'saves/usage').glob('*.jsonl'):shutil.copy2(p,ev/p.name)
(ev/'decision-indexed.json').write_text(json.dumps([dict(index=75+i,**a) for i,a in enumerate(new)],indent=2),encoding='utf-8')
(ev/'request-pairs.json').write_text(json.dumps(pairs,indent=2),encoding='utf-8')
(ev/'realized-state-readback.json').write_text(json.dumps(dict(fixture=fixture,condition={k:[b['players'][k]['stamina'],s['players'][k]['stamina']] for k in ['ghost','fa_0']},scout_deep=[0,0.29],scout_broad=0.5,review=s['last_review_by']['team_nexus']),indent=2),encoding='utf-8')
sys.path.insert(0,'C:/Users/aidan/workspace/agora');from flywheel.recorder import record
common=dict(domain='esports-playtest',source=topic+' main64ee15f browser8516 world26UHC seed2038 W18-W19',code='26UHC',tags=['browser','series-card','scouting','telemetry'])
findings=[dict(topic='Conditional substitution executes and explains itself',problem='Protect Ghost after a lost opener without changing opening five',solution='Save AfterLoss/Stabilize/Hollowlockin/Ghostout, no scrim, Slice focus then Advance once',lesson='Ghost plays Haven17-19; named notes show Hollowlock replaces him aftermap1 and Stabilize. Hollowlock plays Ascent14-12/Lotus6-13. Directives consumed, defaultfive unchanged, Ghost59.5->70.5; loss1-2 does not prove causal benefit.',confidence='high',kind='learning'),dict(topic='Effective scouting depth can mask early deep-dive progress',problem='Slice still displays50percent after assignment and Advance',solution='Compare public effective depth with saved per-player work after completing decisions',lesson='Individual player:slice progresses0->0.29; broadVanguard0.50 remains effectivefloor. UI50percent alone cannot establish stalled scouting. Standing upcoming lane alreadyVanguard despite Dashboard warning; existingPR358 owns warning.',confidence='high',kind='learning'),dict(topic='Series-card editor must reflect saved substitution',problem='Revisit saved conditional card without accidentally overwriting it',solution='Save AfterLoss/Stabilize/fa_0in/ghostout, compare fresh Prep form with public exactdirective',lesson='Save correct; form resetsTrailing/Steady/no substitutes, current summary omits pair. Confirmed gap35 explicit6.1-sol/medium owner has immutable preAdvance e8c864a4... fixture. Actual match substitution stillworks; editor feedback is separate.',confidence='high',kind='pain-point')]
(ev/'flywheel-after.json').write_text(json.dumps([asdict(record(**common,**f)) for f in findings],indent=2),encoding='utf-8')
proc=psutil.Process(server['pid']);family=proc.children(recursive=True)+[proc];owned=[]
for p in family:
 command=p.cmdline()
 if p.name().lower()=='conhost.exe':assert server['pid'] in [x.pid for x in p.parents()]
 else:assert p.cwd().lower()==str(run).lower() and '--web' in command and '8516' in command
 owned.append(dict(pid=p.pid,command=command))
for p in family:p.terminate()
_,live=psutil.wait_procs(family,timeout=5);assert not live
with socket.socket() as probe:assert probe.connect_ex(('127.0.0.1',8516))!=0
proof=dict(audited_at_utc=datetime.now(timezone.utc).isoformat(),commit=manifest['commit'],actual_seed=2038,baseline_actions=75,final_actions=79,old_prefix_unchanged=True,accepted_coverage=dict(matched=4,accepted=4),standing_five_unchanged=True,plans_consumed=True,snapshot_prefix_unchanged=True,manager_streams=1,snapshots_before_after=[17,18],bank_before_after=[1499208,1564014],report_income=111906,report_expenses=47100,bank_delta=64806,unreported_cash=0,ghost_condition=[59.5,70.5],hollowlock_condition=[97,100],hollowlock_maps=2,ghost_maps=1,scout_deep=[0,0.29],effective_scout_progress=0.5,source_paths_unchanged=545,fixture_unchanged=True,end_save_sha256=sha(save_path),usage_events_at_audit=len(events),usage_kind_counts=dict(Counter(e['kind'] for e in events)),usage_target_counts={k:dict(Counter(e['target'] for e in events if e['kind']==k)) for k in ['view','interaction','replay']},request_pairs=6,pairs=[{k:p[k] for k in ['session_id','request_id','target']} for p in pairs],unmatched_attempts=0,orphan_results=0,report_exitcodes=exitcodes,server_stopped=owned,limits='Bounded usage is not attention or complete funnels. Interpretation and public readbacks lack semantic hooks; observer reference/file/kind assertions are not rejected gamechoices. No causal inference from1-2. Gap35 delegated; existing358/33/34 not duplicated.')
(ev/'audit.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof))
