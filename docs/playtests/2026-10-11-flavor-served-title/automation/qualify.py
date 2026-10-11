import hashlib, json, subprocess
from pathlib import Path
root=Path.cwd(); run=root/'runs/playtests/2026-10-11-flavor-served-title'; docs=root/'docs/playtests/2026-10-11-flavor-served-title'
files={}
for path in sorted(docs.rglob('*')):
    if not path.is_file() or path.name=='git-byte-qualification.json':continue
    relative=path.relative_to(root).as_posix()
    raw=path.read_bytes()
    staged=subprocess.check_output(['git','show',':'+relative])
    assert staged==raw, relative
    files[relative]={'sha256':hashlib.sha256(raw).hexdigest(),'git_blob':subprocess.check_output(['git','rev-parse',':'+relative],text=True).strip(),'bytes':len(raw),'raw_equals_staged_blob':True}
sources={}
for name in ['src/esports_sim/web/static/app.js','tests/flavor_feedback_check.cjs']:
    snapshot=(docs/'source'/name).read_bytes(); work=(root/name).read_bytes()
    staged=subprocess.check_output(['git','show',':'+name])
    assert snapshot==work
    assert snapshot.replace(b'\r\n',b'\n')==staged.replace(b'\r\n',b'\n')
    sources[name]={'raw_snapshot_equals_working_source':True,'git_source_equals_snapshot_after_only_crlf_normalization':True,'raw_sha256':hashlib.sha256(work).hexdigest(),'git_source_blob':subprocess.check_output(['git','rev-parse',':'+name],text=True).strip(),'git_source_sha256':hashlib.sha256(staged).hexdigest()}
out={'parent_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'raw_scoped_attributes':'docs/playtests/2026-10-11-flavor-served-title/** -text -whitespace','files':files,'source_qualification':sources,'historical_qualification':'historical-preservation.json; original files unchanged','self_exclusion':'This qualification file is excluded from its own recursive manifest; verify its Git blob directly.','local_pytest':'UNRUN','local_node_regressions':'UNRUN','expensive_gates':'UNRUN'}
(docs/'git-byte-qualification.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print({'raw_files_qualified':len(files),'source_files_qualified':len(sources)})
