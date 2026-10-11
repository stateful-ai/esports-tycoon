import hashlib,json,os,shutil,socket,subprocess,sys
from collections import Counter,defaultdict
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import psutil
root=Path(r'C:/Users/aidan/workspace/esports-sponsor-playtest-20261010')
topic='2026-10-10-regional-final';run=root/'runs/playtests'/topic;docs=root/'docs/playtests'/topic;ev=docs/'evidence';ev.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (ev/'audit.json').exists()
b=read(run/'save-before.json');pre=read(run/'save-pre-advance.json');save_path=run/'saves/campaign_f2977bf6e97d789a.json';s=read(save_path)
assert s['seed']==b['seed']==2038
assert len(b['action_log'])==68 and len(pre['action_log'])==71 and len(s['action_log'])==72
assert s['action_log'][:68]==b['action_log'] and s['action_log'][:71]==pre['action_log']
new=s['action_log'][68:];assert [a['kind'] for a in new]==['media_choice','set_preparation','set_game_plan','advance']
assert all(a['source']=='web' and a['team_id']=='team_nexus' and (a['season'],a['week'])==(1,16) for a in new)
assert new[0]['params']==dict(choice_id='respect_rival',event_id='d2c6ee7fa625f074')
assert new[1]['params']['map_id']=='haven' and new[1]['params']['objective']=='anti_exec' and new[1]['params']['intensity']=='light'
assert new[2]['params']['focus_target']=='pulse' and new[2]['params']['starter_ids']=='[]' and new[2]['params']['n_dials']=='0'
assert (s['season'],s['week'],s['phase'])==(1,17,'playoffs')
assert s['teams']['team_nexus']['balance']==989505 and b['teams']['team_nexus']['balance']==805569
assert 989505-805569-(111036-47100)==120000
assert s['teams']['team_nexus']['lineup_ids']==b['teams']['team_nexus']['lineup_ids']==['apex','vortex','ghost','fa_13','echo']
for k,v in b['telemetry_snaps'].items():assert s['telemetry_snaps'][k][:len(v)]==v
assert len(s['telemetry_snaps'])==1 and len(b['telemetry_snaps']['mgr_team_nexus'])==15 and len(s['telemetry_snaps']['mgr_team_nexus'])==16
fixture=next(f for f in s['fixtures'] if f['id']=='s1amfinal')
assert fixture['winner_id']=='team_vanguard' and [(r['map_id'],r['score_b'],r['score_a']) for r in fixture['results']]==[('haven',8,13),('ascent',4,13)]
assert all('fa_0' not in [l['player_id'] for l in r['lines']] for r in fixture['results'])
trust={pid:dict(before=b['manager_player_trust_by']['team_nexus'].get(pid,50.0),pre_advance=pre['manager_player_trust_by']['team_nexus'][pid],after=value) for pid,value in s['manager_player_trust_by']['team_nexus'].items()}
assert all(v['pre_advance']-v['before']==3 and v['after']-v['pre_advance']==1 for v in trust.values())
manifest=read(run/'source-manifest.json');assert len(manifest['source_sha256'])==545 and all(sha(root/p)==h for p,h in manifest['source_sha256'].items())
server=read(run/'server-running.json');assert sha(Path(server['fixture_source'])/save_path.name)==server['fixture_sha256']=='7ed0ae942affd1e1da074e1f88c6075435735bb2d5dacf4c34378627bf3f2cae'
events=[json.loads(line) for p in sorted((run/'saves/usage').glob('*.jsonl')) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
assert all(e['world']=='26UHC' and e['team']=='team_nexus' for e in events)
groups=defaultdict(list)
for e in events:
 if e['kind'] in ['attempt','result']:groups[(e['session_id'],e['request_id'],e['target'])].append(e)
pairs=[dict(session_id=sid,request_id=rid,target=t,events=v) for (sid,rid,t),v in groups.items()]
assert len(pairs)==6 and Counter(p['target'] for p in pairs)==Counter({'/api/actions/media_event':1,'/api/actions/preparation':1,'/api/actions/gameplan':1,'/api/actions/advance':1,'/api/actions/save':2})
for p in pairs:assert sorted(e['kind'] for e in p['events'])==['attempt','result'] and next(e for e in p['events'] if e['kind']=='result')['status']==200
exitcodes={}
for label,args in [('decision',['scripts/telemetry_report.py',str(run/'saves')]),('usage',['scripts/ui_usage_report.py',str(run/'saves/usage')])]:
 result=subprocess.run([sys.executable,*args],cwd=root,env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONUTF8='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (ev/(label+'-report.txt')).write_bytes(result.stdout);exitcodes[label]=result.returncode;assert result.returncode==0
for p in run.iterdir():
 if p.suffix in ['.txt','.json','.yml','.png'] and p.name!='browser-identity-restored.json':shutil.copy2(p,ev/p.name)
for p in (run/'saves/usage').glob('*.jsonl'):shutil.copy2(p,ev/p.name)
(ev/'decision-indexed.json').write_text(json.dumps([dict(index=68+i,**a) for i,a in enumerate(new)],indent=2),encoding='utf-8')
(ev/'request-pairs.json').write_text(json.dumps(pairs,indent=2),encoding='utf-8')
(ev/'realized-state-readback.json').write_text(json.dumps(dict(fixture=fixture,trust=trust,media=s['media_history_by']['team_nexus'][-1],preparation=s['preparation_reports_by'].get('team_nexus'),review=s['last_review_by'].get('team_nexus')),indent=2),encoding='utf-8')
sys.path.insert(0,r'C:/Users/aidan/workspace/agora');from flywheel.recorder import record
common=dict(domain='esports-playtest',source=topic+' main64ee15f browser8500 world26UHC seed2038 W16-W17',code='26UHC',tags=['browser','media','preparation','prize','telemetry'])
findings=[dict(topic='Regional runner-up prize report omits actual cash credit',problem='Explain bank change after regional final',solution='Read report and saved bank arithmetic independently',lesson='Bank delta183936 versus report net63936 differs exactly120000. Existing gap31 patch produces income231036 and expenses47100 with byte-identical saved state. No unexplained100 residual.',confidence='high',kind='learning'),dict(topic='Retained map books differ from newly booked anti-exec preparation',problem='Check whether Haven anti-exec booking and Pulse focus executed',solution='Read actual preparation report and Dashboard calls, not just generic series notes',lesson='Current Haven anti-exec knowledge gain1.1 and calls focusPulse are present. Broader Haven/Ascent/Lotus map-book summary is retained institutional knowledge, not evidence of wrong latest booking. Loss0-2 is descriptive, not causal.',confidence='high',kind='learning'),dict(topic='Media feedback omits measured change explanation',problem='Understand Respect rival choice and delayed loss settlement',solution='Compare immediate acknowledgement and Operations history to independent pre/post trust',lesson='Visible feedback is generic and Operations shows absolute trust54/62. Saved trust actually rises3 immediately then1 after settlement for six players. Nominal record totals do not establish realized clamped effects. New gap32 owns measured server-side feedback; root row8 visibility overstatement requires correction.',confidence='high',kind='pain-point')]
(ev/'flywheel-after.json').write_text(json.dumps([asdict(record(**common,**f)) for f in findings],indent=2),encoding='utf-8')
proc=psutil.Process(server['pid']);family=proc.children(recursive=True)+[proc];owned=[]
for p in family:
 command=p.cmdline()
 if p.name().lower()=='conhost.exe':assert server['pid'] in [x.pid for x in p.parents()]
 else:assert p.cwd().lower()==str(run).lower() and '--web' in command and '8500' in command
 owned.append(dict(pid=p.pid,command=command))
for p in family:p.terminate()
_,live=psutil.wait_procs(family,timeout=5);assert not live
with socket.socket() as probe:assert probe.connect_ex(('127.0.0.1',8500))!=0
proof=dict(audited_at_utc=datetime.now(timezone.utc).isoformat(),commit=manifest['commit'],actual_seed=2038,baseline_actions=68,final_actions=72,old_prefix_unchanged=True,accepted_coverage=dict(matched=4,accepted=4),standing_five_unchanged=True,snapshot_prefix_unchanged=True,manager_streams=1,snapshots_before_after=[15,16],bank_before_after=[805569,989505],report_income=111036,report_expenses=47100,bank_delta=183936,unreported_prize=120000,source_paths_unchanged=545,fixture_unchanged=True,end_save_sha256=sha(save_path),usage_events_at_audit=len(events),usage_kind_counts=dict(Counter(e['kind'] for e in events)),usage_target_counts={k:dict(Counter(e['target'] for e in events if e['kind']==k)) for k in ['view','interaction','replay']},request_pairs=6,pairs=[{k:p[k] for k in ['session_id','request_id','target']} for p in pairs],unmatched_attempts=0,orphan_results=0,report_exitcodes=exitcodes,server_stopped=owned,limits='Bounded usage is not attention or complete funnels. Media interpretation and readback lack semantic hooks. Failed CLI refs and observer errors are qualitative, not HTTP rejections. No causal inference from0-2 loss. Gap31 reused; gap32 delegated.')
(ev/'audit.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof))
