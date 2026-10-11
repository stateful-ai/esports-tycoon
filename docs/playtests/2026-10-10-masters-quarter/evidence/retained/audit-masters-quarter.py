import hashlib,json,os,shutil,socket,subprocess,sys
from collections import Counter,defaultdict
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import psutil
root=Path(r'C:/Users/aidan/workspace/esports-sponsor-playtest-20261010')
topic='2026-10-10-masters-quarter';run=root/'runs/playtests'/topic;docs=root/'docs/playtests'/topic;ev=docs/'evidence';ev.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (ev/'audit.json').exists()
b=read(run/'save-before.json');pre=read(run/'save-pre-advance.json');save_path=run/'saves/campaign_f2977bf6e97d789a.json';s=read(save_path)
assert s['seed']==b['seed']==2038
assert len(b['action_log'])==72 and len(pre['action_log'])==74 and len(s['action_log'])==75
assert s['action_log'][:72]==b['action_log'] and s['action_log'][:74]==pre['action_log']
new=s['action_log'][72:];assert [a['kind'] for a in new]==['set_dev_plan','set_game_plan','advance']
assert all(a['source']=='web' and a['team_id']=='team_nexus' and (a['season'],a['week'])==(1,17) for a in new)
assert new[0]['params']==dict(dev_focus='rest',intensity='normal',learning_language='',player_id='ghost')
assert json.loads(new[1]['params']['starter_ids'])==['apex','echo','fa_0','fa_13','vortex']
assert new[1]['params']['fixture_id']=='s1mqf1' and new[1]['params']['one_match_lineup']=='True' and new[1]['params']['n_dials']=='0'
assert (s['season'],s['week'],s['phase'])==(1,18,'playoffs')
assert s['teams']['team_nexus']['balance']==1499208 and b['teams']['team_nexus']['balance']==989505
assert 1499208-989505==556803-47100==509703
assert s['teams']['team_nexus']['lineup_ids']==b['teams']['team_nexus']['lineup_ids']==['apex','vortex','ghost','fa_13','echo']
assert 'team_nexus' not in s['game_plans_by'] and 'team_nexus' not in pre['preparation_plans_by']
for k,v in b['telemetry_snaps'].items():assert s['telemetry_snaps'][k][:len(v)]==v
assert len(s['telemetry_snaps'])==1 and len(b['telemetry_snaps']['mgr_team_nexus'])==16 and len(s['telemetry_snaps']['mgr_team_nexus'])==17
fixture=next(f for f in s['fixtures'] if f['id']=='s1mqf1')
assert fixture['winner_id']=='team_nexus' and [(r['map_id'],r['score_b'],r['score_a']) for r in fixture['results']]==[('ascent',11,13),('lotus',16,14),('split',13,9)]
for r in fixture['results']:
 ids={l['player_id'] for l in r['lines']};assert 'fa_0' in ids and 'ghost' not in ids
assert b['players']['ghost']['stamina']==pre['players']['ghost']['stamina']==35.5 and s['players']['ghost']['stamina']==59.5
assert pre['players']['ghost']['dev_focus']==s['players']['ghost']['dev_focus']=='rest'
manifest=read(run/'source-manifest.json');assert len(manifest['source_sha256'])==545 and all(sha(root/p)==h for p,h in manifest['source_sha256'].items())
server=read(run/'server-running.json');assert sha(Path(server['fixture_source'])/save_path.name)==server['fixture_sha256']=='32d6564f38d0adff259bd59e53aaf3b45d44df3de8b10470ca301e1b6719bba6'
events=[json.loads(line) for p in sorted((run/'saves/usage').glob('*.jsonl')) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
assert all(e['world']=='26UHC' and e['team']=='team_nexus' for e in events)
groups=defaultdict(list)
for e in events:
 if e['kind'] in ['attempt','result']:groups[(e['session_id'],e['request_id'],e['target'])].append(e)
pairs=[dict(session_id=sid,request_id=rid,target=t,events=v) for (sid,rid,t),v in groups.items()]
assert len(pairs)==5 and Counter(p['target'] for p in pairs)==Counter({'/api/actions/dev_plan':1,'/api/actions/gameplan':1,'/api/actions/advance':1,'/api/actions/save':2})
for p in pairs:assert sorted(e['kind'] for e in p['events'])==['attempt','result'] and next(e for e in p['events'] if e['kind']=='result')['status']==200
exitcodes={}
for label,args in [('decision',['scripts/telemetry_report.py',str(run/'saves')]),('usage',['scripts/ui_usage_report.py',str(run/'saves/usage')])]:
 result=subprocess.run([sys.executable,*args],cwd=root,env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONUTF8='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (ev/(label+'-report.txt')).write_bytes(result.stdout);exitcodes[label]=result.returncode;assert result.returncode==0
for p in run.iterdir():
 if p.suffix in ['.txt','.json','.yml','.png'] and p.name!='browser-identity-restored.json':shutil.copy2(p,ev/p.name)
for p in (run/'saves/usage').glob('*.jsonl'):shutil.copy2(p,ev/p.name)
(ev/'decision-indexed.json').write_text(json.dumps([dict(index=72+i,**a) for i,a in enumerate(new)],indent=2),encoding='utf-8')
(ev/'request-pairs.json').write_text(json.dumps(pairs,indent=2),encoding='utf-8')
(ev/'realized-state-readback.json').write_text(json.dumps(dict(fixture=fixture,ghost_before=b['players']['ghost']['stamina'],ghost_after=s['players']['ghost']['stamina'],standing=s['teams']['team_nexus']['lineup_ids'],review=s['last_review_by']['team_nexus']),indent=2),encoding='utf-8')
sys.path.insert(0,r'C:/Users/aidan/workspace/agora');from flywheel.recorder import record
common=dict(domain='esports-playtest',source=topic+' main64ee15f browser8513 world26UHC seed2038 W17-W18',code='26UHC',tags=['browser','recovery','one-match-lineup','veto','telemetry'])
findings=[dict(topic='One-match rotation preserves default five and recovery',problem='Rest fatigued Ghost without losing quarterfinal roster control',solution='Save GhostRest and five-player fixture plan replacing him with Hollowlock, skip extra scrim then Advance once',lesson='Hollowlock plays all3 maps, Ghost none, defaultfive restored after consumption; Ghost35.5->59.5. Fullreport separates benchscrims under0.01 from Hollowlock match+0.01. Win2-1 is descriptive, not causal.',confidence='high',kind='learning'),dict(topic='Fixture guidance must acknowledge locked veto',problem='Find useful map prep advice for Masters quarterfinal',solution='Compare Dashboard suggestions to actual public fixture veto and Prep legalmaps',lesson='ActualAscent/Lotus/Split only, Haven/Bind alreadybanned; generic all-history BanHaven/PickBind advice is unavailable. Gap33 measured patch shows locked veto/playablemap records while preserving historicalmaps.',confidence='high',kind='learning'),dict(topic='Post-match bench advice ignores consumed rotation',problem='Understand coach advice after temporary Hollowlock start',solution='Read fresh Dashboard and current upcoming roster after one-match plan consumed',lesson='Hollowlock alreadybench, currentVanguardmapfives exclude him and plannull, yet WhattoTweak saysconsiderbench. Gap34 owns currentselection-aware advice. Historical0.69 review remains valid. Root wrong effectivearray claim corrected separately inrow7.',confidence='high',kind='pain-point')]
(ev/'flywheel-after.json').write_text(json.dumps([asdict(record(**common,**f)) for f in findings],indent=2),encoding='utf-8')
proc=psutil.Process(server['pid']);family=proc.children(recursive=True)+[proc];owned=[]
for p in family:
 command=p.cmdline()
 if p.name().lower()=='conhost.exe':assert server['pid'] in [x.pid for x in p.parents()]
 else:assert p.cwd().lower()==str(run).lower() and '--web' in command and '8513' in command
 owned.append(dict(pid=p.pid,command=command))
for p in family:p.terminate()
_,live=psutil.wait_procs(family,timeout=5);assert not live
with socket.socket() as probe:assert probe.connect_ex(('127.0.0.1',8513))!=0
proof=dict(audited_at_utc=datetime.now(timezone.utc).isoformat(),commit=manifest['commit'],actual_seed=2038,baseline_actions=72,final_actions=75,old_prefix_unchanged=True,accepted_coverage=dict(matched=3,accepted=3),standing_five_unchanged=True,one_fixture_plan_consumed=True,snapshot_prefix_unchanged=True,manager_streams=1,snapshots_before_after=[16,17],bank_before_after=[989505,1499208],report_income=556803,report_expenses=47100,bank_delta=509703,unreported_cash=0,ghost_condition=[35.5,59.5],hollowlock_maps=3,ghost_maps=0,source_paths_unchanged=545,fixture_unchanged=True,end_save_sha256=sha(save_path),usage_events_at_audit=len(events),usage_kind_counts=dict(Counter(e['kind'] for e in events)),usage_target_counts={k:dict(Counter(e['target'] for e in events if e['kind']==k)) for k in ['view','interaction','replay']},request_pairs=5,pairs=[{k:p[k] for k in ['session_id','request_id','target']} for p in pairs],unmatched_attempts=0,orphan_results=0,report_exitcodes=exitcodes,server_stopped=owned,limits='Bounded usage is not attention or complete funnels. Interpretation and public readbacks lack semantic hooks; failed observer404 and overlayinterception are not rejected gamechoices. No causal inference from2-1. Gap33 and34 delegated; originalrow4 corrected7.')
(ev/'audit.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof))
