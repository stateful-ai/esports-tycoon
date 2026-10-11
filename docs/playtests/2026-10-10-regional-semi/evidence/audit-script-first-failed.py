import hashlib,json,os,shutil,socket,subprocess,sys
from collections import Counter,defaultdict
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import psutil
root=Path(r'C:/Users/aidan/workspace/esports-sponsor-playtest-20261010')
topic='2026-10-10-regional-semi';run=root/'runs/playtests'/topic;docs=root/'docs/playtests'/topic;ev=docs/'evidence';ev.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (ev/'audit.json').exists()
b=read(run/'save-before.json');pre=read(run/'save-pre-advance.json');save_path=run/'saves/campaign_f2977bf6e97d789a.json';s=read(save_path)
assert s['seed']==b['seed']==2038
assert len(b['action_log'])==65 and len(s['action_log'])==68 and s['action_log'][:65]==b['action_log']
new=s['action_log'][65:];assert [a['kind'] for a in new]==['series_directive','set_game_plan','advance']
assert all(a['source']=='web' and a['team_id']=='team_nexus' and (a['season'],a['week'])==(1,15) for a in new)
assert new[0]['params']==dict(clear='False',fixture_id='s1amsemi1',response='reset',substitute_in='fa_0',substitute_out='ghost',trigger='always')
assert new[1]['params']['starter_ids']=='[]' and new[1]['params']['one_match_lineup']=='False' and new[1]['params']['n_dials']=='0'
assert len(pre['action_log'])==67 and pre['series_directives_by']['team_nexus']['trigger']=='always'
assert (s['season'],s['week'],s['phase'])==(1,16,'playoffs')
assert s['teams']['team_nexus']['balance']==805569==741367+111302-47100
assert s['teams']['team_nexus']['lineup_ids']==b['teams']['team_nexus']['lineup_ids']==['apex','vortex','ghost','fa_13','echo']
assert 'team_nexus' not in s['game_plans_by'] and 'team_nexus' not in s['series_directives_by']
for k,v in b['telemetry_snaps'].items():assert s['telemetry_snaps'][k][:len(v)]==v
assert len(s['telemetry_snaps'])==1 and len(b['telemetry_snaps']['mgr_team_nexus'])==14 and len(s['telemetry_snaps']['mgr_team_nexus'])==15
manifest=read(run/'source-manifest.json');assert len(manifest['source_sha256'])==545 and all(sha(root/p)==h for p,h in manifest['source_sha256'].items())
server=read(run/'server-running.json');assert sha(Path(server['fixture_source'])/save_path.name)==server['fixture_sha256']=='8e8b3f1706501000e8599c0951633f506f7f43d4ea1f0e3b8ef45691f3b03984'
events=[json.loads(line) for p in sorted((run/'saves/usage').glob('*.jsonl')) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
assert all(e['world']=='26UHC' and e['team']=='team_nexus' for e in events)
groups=defaultdict(list)
for e in events:
 if e['kind'] in ['attempt','result']:groups[(e['session_id'],e['request_id'],e['target'])].append(e)
pairs=[dict(session_id=sid,request_id=rid,target=t,events=v) for (sid,rid,t),v in groups.items()]
assert len(pairs)==6 and Counter(p['target'] for p in pairs)==Counter({'/api/actions/series-directive':1,'/api/actions/gameplan':1,'/api/actions/advance':1,'/api/actions/save':3})
for p in pairs:assert sorted(e['kind'] for e in p['events'])==['attempt','result'] and next(e for e in p['events'] if e['kind']=='result')['status']==200
exitcodes={}
for label,args in [('decision',['scripts/telemetry_report.py',str(run/'saves')]),('usage',['scripts/ui_usage_report.py',str(run/'saves/usage')])]:
 result=subprocess.run([sys.executable,*args],cwd=root,env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONUTF8='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (ev/(label+'-report.txt')).write_bytes(result.stdout);exitcodes[label]=result.returncode;assert result.returncode==0
for p in run.iterdir():
 if p.suffix in ['.txt','.json','.yml','.png'] and p.name!='browser-identity-restored.json':shutil.copy2(p,ev/p.name)
for p in (run/'saves/usage').glob('*.jsonl'):shutil.copy2(p,ev/p.name)
(ev/'decision-indexed.json').write_text(json.dumps([dict(index=65+i,**a) for i,a in enumerate(new)],indent=2),encoding='utf-8')
(ev/'request-pairs.json').write_text(json.dumps(pairs,indent=2),encoding='utf-8')
sys.path.insert(0,r'C:/Users/aidan/workspace/agora');from flywheel.recorder import record
common=dict(domain='esports-playtest',source=topic+' main64ee15f browser8499 world26UHC seed2038 W15-W16',code='26UHC',tags=['browser','series-response','substitution','telemetry'])
findings=[dict(topic='Between-map response preserves standing starters',problem='Rotate Hollowlock into a playoff series after its opener',solution='Save Always Reset with fa_0 in and ghost out; resolve one BO3 and read actual map participants',lesson='Ghost opener, Hollowlock maps2/3; series notes in Season Fixtures Played weeks name substitution and reset. Standing five unchanged and both plans consumed. Nexus2-1 is descriptive, not causal proof.',confidence='high',kind='learning'),dict(topic='Reconcile accepted choices separately from browser usage',problem='Measure a saved playoff coaching choice',solution='Compare exact IDs and old prefixes against session/request pairs',lesson='65->68 decisions and14->15 snapshot entries; three exact web choices matched. Saves are separate usage. Stale refs and bad observer fields did not produce accepted choices.',confidence='high',kind='learning'),dict(topic='Series outcome notes require a second results route',problem='Find whether a response executed after opening Full report',solution='Inspect Season Fixtures and expand Played weeks',lesson='Full report shows map counts but the explicit response/substitution notes are in played fixtures. Existing route is functional; this session records discoverability friction without declaring missing implementation.',confidence='high',kind='pain-point')]
(ev/'flywheel-after.json').write_text(json.dumps([asdict(record(**common,**f)) for f in findings],indent=2),encoding='utf-8')
proc=psutil.Process(server['pid']);family=proc.children(recursive=True)+[proc];owned=[]
for p in family:
 command=p.cmdline()
 if p.name().lower()=='conhost.exe':assert server['pid'] in [x.pid for x in p.parents()]
 else:assert p.cwd().lower()==str(run).lower() and '--web' in command and '8499' in command
 owned.append(dict(pid=p.pid,command=command))
for p in family:p.terminate()
_,live=psutil.wait_procs(family,timeout=5);assert not live
with socket.socket() as probe:assert probe.connect_ex(('127.0.0.1',8499))!=0
proof=dict(audited_at_utc=datetime.now(timezone.utc).isoformat(),commit=manifest['commit'],actual_seed=2038,baseline_actions=65,final_actions=68,old_prefix_unchanged=True,accepted_coverage=dict(matched=3,accepted=3),standing_five_unchanged=True,plan_and_directive_consumed=True,snapshot_prefix_unchanged=True,manager_streams=1,snapshots_before_after=[14,15],bank_before_after=[741367,805569],report_income=111302,report_expenses=47100,bank_delta=64202,source_paths_unchanged=545,fixture_unchanged=True,end_save_sha256=sha(save_path),usage_events_at_audit=len(events),usage_kind_counts=dict(Counter(e['kind'] for e in events)),usage_target_counts={k:dict(Counter(e['target'] for e in events if e['kind']==k)) for k in ['view','interaction','replay']},request_pairs=6,pairs=[{k:p[k] for k in ['session_id','request_id','target']} for p in pairs],unmatched_attempts=0,orphan_results=0,report_exitcodes=exitcodes,server_stopped=owned,limits='Retained visibility is not attention or complete funnels. Series interpretation has no semantic browser event. CLI stale refs, unsupported command and observer failures are preserved qualitatively, not HTTP rejections. No causal inference from2-1 result. No new confirmed product gap.')
(ev/'audit.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof))
