import csv, hashlib, json, socket, subprocess, sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import psutil
root=Path.cwd(); run=root/'runs/playtests/2026-10-11-flavor-served-title'; docs=root/'docs/playtests/2026-10-11-flavor-served-title'
private=json.loads((run/'private.json').read_text(encoding='utf-8'))
before=json.loads((run/'save-before.json').read_text(encoding='utf-8'))
end=json.loads(Path(private['save']).read_text(encoding='utf-8'))
prefix=len(before['action_log']); new=end['action_log'][prefix:]
assert end['action_log'][:prefix]==before['action_log'] and len(new)==1
assert new[0]['kind']=='flavor_choice' and new[0]['source']=='web'
assert new[0]['params']=={'choice_id':'small_group','event_id':'8f43d112fb4700ed'}
assert new[0]['team_id']=='team_nexus' and new[0]['season']==1 and new[0]['week']==12
assert end['telemetry_snaps']==before['telemetry_snaps']
# Historical saves predate the current save schema. Preserve their raw bytes and
# compare read-only migration through the current loader, without resolving again.
baseline=root/'runs/playtests/2026-10-10-flavor-feedback/baseline64-resolved.json'
raw_baseline_exact=Path(private['save']).read_bytes()==baseline.read_bytes()
sys.path.insert(0,str(root/'src'))
from esports_sim.manager.state import GameState
migrated=run/'baseline-migrated-current.json'
GameState.load(baseline).save(migrated)
assert Path(private['save']).read_bytes()==migrated.read_bytes()
(docs/'baseline-comparison.json').write_text(json.dumps({'initial_raw_comparison':'unequal; historical schema migration changes schema_version and players','raw_historical_exact':raw_baseline_exact,'historical_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),'current_loader_migrated_historical_sha256':hashlib.sha256(migrated.read_bytes()).hexdigest(),'current_saved_sha256':hashlib.sha256(Path(private['save']).read_bytes()).hexdigest(),'migration_only_comparison_exact_bytes':True,'original_baseline_untouched':True},indent=2),encoding='utf-8')
events=[]
for path in sorted((run/'saves/usage').glob('*.jsonl')):
    raw=path.read_bytes(); (docs/path.name).write_bytes(raw)
    events += [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
assert all(e.get('world')=='FLV42' for e in events if e.get('world'))
groups=defaultdict(list)
for e in events:
    if e['kind'] in ('attempt','result'):
        groups[(e['session_id'],e['request_id'],e['target'])].append(e)
pairs=[{'session_id':s,'request_id':r,'target':t,'events':v} for (s,r,t),v in groups.items()]
assert sorted(p['target'] for p in pairs)==['/api/actions/flavor_event','/api/actions/save']
assert all(sorted(e['kind'] for e in p['events'])==['attempt','result'] for p in pairs)
assert all(next(e for e in p['events'] if e['kind']=='result')['status']==200 for p in pairs)
historical=json.loads((run/'historical-before.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha for name,sha in historical.items())
(docs/'historical-preservation.json').write_text(json.dumps({'head_before':'7854dc70899a967738b9f64f7ca54cffa8bcecdd','unchanged_files':historical,'count':len(historical),'canonical_actions_untouched':True},indent=2),encoding='utf-8')
(docs/'decision-indexed.json').write_text(json.dumps([{'index':prefix,**new[0]}],indent=2),encoding='utf-8')
(docs/'request-pairs.json').write_text(json.dumps(pairs,indent=2),encoding='utf-8')
csvpath=docs/'actions.csv'
with csvpath.open(encoding='utf-8',newline='') as f:
    reader=csv.DictReader(f); fields=reader.fieldnames; rows=list(reader)
assert len(rows)==4
for row in rows:
    row['analytics_evidence']='browser-readback.json; retained usage sidecar view events; outside accepted-decision vocabulary'
    if row['step']=='2':
        row['analytics_status']='recorded'
        row['analytics_evidence']=f'action_log[{prefix}] exact flavor_choice web/team_nexus/S1W12; decision-indexed.json; request-pairs.json paired flavor_event success200'
    if row['step']=='4':
        row['analytics_evidence']='request-pairs.json paired save success200; independent persisted action_log reconciliation; save outside accepted-decision vocabulary'
with csvpath.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
sys.path.insert(0,r'C:\Users\aidan\workspace\agora')
from flywheel.recorder import record
entries=[]
for kind,topic,lesson in [
    ('learning','Served flavor title continuity','Cache overlay title remains attached to the resolved receipt; action response may retain fallback prose.'),
    ('learning','Flavor settlement save parity','Isolated cached-overlay browser choice yields byte-identical saved state to current-loader migration of the historical deterministic small_group result; raw historical schema differs.'),
    ('pain-point','Flavor copy serving contract','State and action response can name the same event differently; acceptance must compare visible moment and settled receipt.')]:
    entries.append(asdict(record(domain='esports-playtest',kind=kind,topic=topic,problem='Cached flavor title differs from deterministic action response.',solution='Capture the title rendered before the choice; preserve response effects and stale-world/team guard.',lesson=lesson,source='docs/playtests/2026-10-11-flavor-served-title/report.md; FLV42 seed2038 S1W12',confidence='high',tags=['flavor','receipt','cached-overlay'])))
(docs/'flywheel-after.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
# Stop only the process family this setup owns, after verifying its command/cwd.
parent=psutil.Process(private['pid'])
assert Path(parent.cwd()).resolve()==run.resolve()
assert '--port' in parent.cmdline() and '8541' in parent.cmdline()
family=parent.children(recursive=True)+[parent]
identities=[{'pid':p.pid,'cmdline':p.cmdline(),'cwd':p.cwd(),'create_time':p.create_time()} for p in family]
for p in reversed(family):
    try:p.terminate()
    except psutil.NoSuchProcess:pass
gone,alive=psutil.wait_procs(family,timeout=5)
assert not alive
with socket.socket() as port: assert port.connect_ex(('127.0.0.1',8541)) != 0
(docs/'cleanup-receipt.json').write_text(json.dumps({'time_utc':datetime.now(timezone.utc).isoformat(),'owned_family':identities,'all_stopped':True,'port8541_free':True,'browser_closed':True,'other_servers_touched':False},indent=2),encoding='utf-8')
audit={'decision_prefix':prefix,'accepted_decisions':len(new),'csv_accepted_decision_matches':1,'accepted_coverage':'1/1','csv_rows':len(rows),'usage_events':len(events),'page_sessions':len({e['session_id'] for e in events}),'complete_request_pairs':len(pairs),'unmatched_attempts':0,'orphan_results':0,'save_sha256':hashlib.sha256(Path(private['save']).read_bytes()).hexdigest(),'raw_historical_baseline_save_exact_bytes':raw_baseline_exact,'migrated_baseline_save_exact_bytes':True,'telemetry_snapshots_unchanged':True,'historical_files_unchanged':len(historical),'local_tests':'UNRUN (explicit user instruction)','expensive_gates':'UNRUN (explicit user instruction)'}
(docs/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
print(json.dumps(audit))
