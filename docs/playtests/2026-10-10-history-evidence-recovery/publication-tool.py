import csv, datetime, hashlib, io, json, pathlib, shutil, subprocess
root=pathlib.Path(__file__).resolve().parents[3]
primary=pathlib.Path('C:/Users/aidan/workspace/esports-simulator/ESports Simulator')
out=pathlib.Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
rows=lambda b:list(csv.DictReader(io.StringIO(b.decode('utf-8'))))
original=(root/'docs/playtests/actions.csv').read_bytes()
audit_raw=(out/'recovery-audit.json').read_bytes()
original_audit=json.loads(audit_raw)
assert len(rows(original))==685 and sha(original)==original_audit['final_sha256']
gate=json.loads((out/'full-result.json').read_text())
assert gate['exit_code']==0 and gate['source_unchanged'] and gate['source_files']==612
manifest=json.loads((out/'source-freeze.json').read_text())
assert all(sha((root/p).read_bytes())==v for p,v in manifest.items())
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert head==gate['base']=='64ee15f19f7acf80a2dbb7e5035d8c037128fea6'
snapshot=(primary/'runs/playtests/history-publication-snapshot-724.csv').read_bytes()
assert sha(snapshot)=='0597857c221b2f60818472dfd1c07eca7435d081759d6e00b6ac659393604697'
published=subprocess.check_output(['git','show',head+':docs/playtests/actions.csv'],cwd=root)
shard=(out/'actions.csv').read_bytes()
record=shard[shard.index(b'\n')+1:]
prefix698=(primary/'runs/playtests/history-forensic-correction-appended-before.csv').read_bytes()
prefix699=(primary/'runs/playtests/history-publication-snapshot-699.csv').read_bytes()
prefix706=(primary/'runs/playtests/promise-renewal-history-appended-before.csv').read_bytes()
assert len(rows(prefix698))==698 and len(rows(prefix699))==699 and len(rows(prefix706))==706
assert prefix699==prefix698+record
prefix684=original[:-len(record)]
prefixes={}
for count,b in [(597,published),(684,prefix684),(698,prefix698),(699,prefix699),(706,prefix706)]:
    assert len(rows(b))==count and snapshot.startswith(b)
    prefixes[str(count)]={'sha256':sha(b),'byte_length':len(b),'exact_prefix':True}
allrows=rows(snapshot)
assert len(allrows)==724 and len({(r['session_id'],r['step']) for r in allrows})==724
assert allrows[698]==rows(shard)[0]
assert all(sha((root/p).read_bytes())==v for p,v in original_audit['copied_files_sha256'].items())
assert not (out/'snapshot-685.csv').exists()
(out/'snapshot-685.csv').write_bytes(original)
(out/'snapshot-699.csv').write_bytes(prefix699)
copied={}
for name in ['2026-10-10-sponsor-obligation','2026-10-10-rookie-clinic','2026-10-10-play-time-promise-clarity','2026-10-10-play-time-promise-renewal']:
    source=primary/'docs/playtests'/name; dest=root/'docs/playtests'/name
    assert not dest.exists()
    shutil.copytree(source,dest)
    for p in source.rglob('*'):
        if p.is_file():
            rel=p.relative_to(source); target=dest/rel
            assert p.read_bytes()==target.read_bytes()
            copied[str(target.relative_to(root)).replace('\\','/')]=sha(p.read_bytes())
receipts={}
for n in ['history-forensic-correction-appended.json','sponsor-obligation-history-appended.json','rookie-clinic-history-appended.json','promise-renewal-history-appended.json']:
    b=(primary/'runs/playtests'/n).read_bytes(); (out/n).write_bytes(b); receipts[n]=sha(b)
(root/'docs/playtests/actions.csv').write_bytes(snapshot)
assert (out/'recovery-audit.json').read_bytes()==audit_raw
assert all(sha((root/p).read_bytes())==v for p,v in manifest.items())
result={'published_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tested_base':head,'full_gate':gate,'source_manifest_files':len(manifest),'source_manifest_raw_match':True,'original685_sha256':sha(original),'original_recovery_audit_sha256':sha(audit_raw),'original_recovery_audit_unchanged':True,'historical_prefixes':prefixes,'published_rows':len(allrows),'published_unique_keys':len({(r['session_id'],r['step']) for r in allrows}),'published_sha256':sha(snapshot),'exact_correction_record_position':699,'correction_shard_sha256':sha(shard),'correction_record_raw_sha256':sha(record),'original132_copy_hashes_verified':True,'additional_files_sha256':copied,'append_receipts_sha256':receipts,'new_sessions_counts':dict((s,sum(r['session_id']==s for r in allrows)) for s in ['2026-10-10-sponsor-obligation','2026-10-10-rookie-clinic','2026-10-10-play-time-promise-clarity','2026-10-10-play-time-promise-renewal']),'scope':'Documentation publication only; runtime proof covers unchanged64ee15f source. Later histories not imported.'}
(out/'publication-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'rows':len(allrows),'sha':sha(snapshot),'additional_files':len(copied),'source_files':len(manifest)}))
