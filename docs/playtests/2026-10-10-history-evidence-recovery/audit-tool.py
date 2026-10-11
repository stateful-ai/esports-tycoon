import csv, collections, datetime, hashlib, io, json, pathlib, shutil, subprocess
root=pathlib.Path(__file__).resolve().parents[3]
primary=pathlib.Path(r'C:/Users/aidan/workspace/esports-simulator/ESports Simulator')
out=root/'docs/playtests/2026-10-10-history-evidence-recovery'
sha=lambda b: hashlib.sha256(b).hexdigest()
published=(root/'docs/playtests/actions.csv').read_bytes()
canonical=(primary/'docs/playtests/actions.csv').read_bytes()
rows=list(csv.DictReader(io.StringIO(canonical.decode('utf-8'))))
assert len(rows)==684 and sha(canonical)=='8bd8fa790427a14beeed479f805483e9e77002966a28b035872adbb500333556'
assert canonical.startswith(published)
(root/'docs/playtests/actions.csv').write_bytes(canonical)
copied={}
for name in ['2026-10-10-financial-planning','2026-10-10-history-reconciliation','2026-10-10-leadership-obligations','2026-10-10-media-sponsor','2026-10-10-rotation-preparation']:
    source=primary/'docs/playtests'/name
    dest=root/'docs/playtests'/name
    assert not dest.exists()
    shutil.copytree(source,dest)
    for p in source.rglob('*'):
        if p.is_file():
            rel=p.relative_to(source)
            assert p.read_bytes()==(dest/rel).read_bytes()
            copied[str((dest/rel).relative_to(root)).replace('\\','/')]=sha(p.read_bytes())
session=root/'docs/playtests/2026-10-08-roster-hint'
retained={p.name:sha(p.read_bytes()) for p in session.iterdir() if p.is_file()}
assert all((primary/'docs/playtests/2026-10-08-roster-hint'/n).read_bytes()==(session/n).read_bytes() for n in retained)
usage=json.loads((session/'usage-evidence.json').read_text())
attempts={(e['session_id'],e['request_id']):e for e in usage if e['kind']=='attempt'}
results={(e['session_id'],e['request_id']):e for e in usage if e['kind']=='result'}
pairs=[]
for key,event in attempts.items():
    result=results.get(key)
    pairs.append({'session_id':key[0],'request_id':key[1],'target':event['target'],'status':result.get('status') if result else None,'same_target':result is not None and result['target']==event['target']})
decisions=json.loads((session/'decision-evidence.json').read_text())
assert [x['index'] for x in decisions['action_log']]==list(range(5))
assert [x['kind'] for x in decisions['action_log']]==['release','negotiate_open','negotiate_open','negotiate_offer','advance']
assert len(attempts)==len(results)==8 and all(p['same_target'] for p in pairs)
assert collections.Counter(p['status'] for p in pairs)=={200:7,409:1}
blank=[r for r in rows if not r['analytics_status']]
assert len(blank)==5 and {r['session_id'] for r in blank}=={'2026-10-08-mid-split-budget'}
assert {r['step'] for r in blank}==set('12345')
worktrees=[line[9:] for line in subprocess.check_output(['git','worktree','list','--porcelain'],cwd=root,text=True).splitlines() if line.startswith('worktree ')]
searched=[]; found=[]
for wt in worktrees:
    for suffix in ['docs/playtests/2026-10-08-roster-hint','runs/playtests/2026-10-08-roster-hint']:
        path=pathlib.Path(wt)/suffix
        searched.append(str(path))
        if path.exists(): found.extend(str(p) for p in path.rglob('market.png'))
for wt in worktrees:
    if any(k in wt for k in ['eight-gap','badge-attribution','current-main','playtest-wave']) or wt==str(primary).replace('\\','/'):
        for suffix in ['runs','.playwright-mcp']:
            path=pathlib.Path(wt)/suffix; searched.append(str(path))
            if path.exists():found.extend(str(p) for p in path.rglob('market.png'))
audit={'recovered_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'published_rows':len(list(csv.DictReader(io.StringIO(published.decode())))),'published_sha256':sha(published),'canonical_rows':len(rows),'canonical_sha256':sha(canonical),'published_byte_prefix_preserved':canonical.startswith(published),'canonical_unique_keys':len({(r['session_id'],r['step']) for r in rows}),'copied_files_sha256':copied,'roster_retained_files_sha256':retained,'roster_evidence_currentmain_commit':'4b04824','roster_usage_events':len(usage),'roster_world_events':sum(e.get('world')=='95WTN' for e in usage),'roster_request_pairs':pairs,'unmatched_attempts':len(attempts.keys()-results.keys()),'orphan_results':len(results.keys()-attempts.keys()),'roster_decision_records':decisions,'budget_effective_annotations':[{'session_id':r['session_id'],'step':r['step'],'historical_status':r['analytics_status'],'effective_status':'unverified','evidence':'../2026-10-08-mid-split-budget/report.md; historical correction step7'} for r in blank],'market_png_found':found,'market_png_search_paths':searched,'limitations':['No original roster save recovered; exported ledger independently recountable but saved-setting readback cannot be repeated from this export.','market.png not recovered in scoped search; visual screenshot claim remains unverified.','Budget steps1-5 absent receipts remain unverified; no historical annotations edited.']}
(out/'recovery-audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'rows':len(rows),'sha':sha(canonical),'copied_files':len(copied),'usage':len(usage),'pairs':len(pairs),'screenshot_found':found}))
