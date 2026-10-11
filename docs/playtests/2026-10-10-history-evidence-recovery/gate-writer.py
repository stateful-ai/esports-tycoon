import hashlib, json, os, pathlib, subprocess, sys, datetime
root = pathlib.Path(__file__).resolve().parents[3]
out = root / 'docs/playtests/2026-10-10-history-evidence-recovery'
out.mkdir(parents=True, exist_ok=True)
def freeze():
    names = subprocess.check_output(['git','ls-files','src','tests','scripts','data','.github','pyproject.toml','uv.lock','pytest.ini','setup.cfg'], cwd=root, text=True).splitlines()
    return {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names if (root/n).is_file()}
before = freeze()
(out/'source-freeze.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
env = os.environ.copy(); env['PYTHONPATH'] = str(root/'src'); env['PYTHONIOENCODING']='utf-8'
py = r'C:/Users/aidan/workspace/esports-simulator/ESports Simulator/.venv-win/Scripts/python.exe'
import_path = subprocess.check_output([py,'-c','import esports_sim; print(esports_sim.__file__)'],cwd=root,env=env,text=True).strip()
assert str(root/'src').replace('\\','/').lower() in import_path.replace('\\','/').lower()
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
with (out/'full-pytest.log').open('wb') as log:
    process = subprocess.Popen([py,'-m','pytest','-q','-n','2'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    (out/'gate-running.json').write_text(json.dumps({'writer_pid':os.getpid(),'pytest_pid':process.pid,'base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'started_at':started,'import_path':import_path},indent=2)+'\n',encoding='utf-8')
    code = process.wait()
after = freeze()
result={'command':[py,'-m','pytest','-q','-n','2'],'exit_code':code,'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'import_path':import_path,'source_files':len(before),'source_unchanged':before==after,'changed_files':sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k)),'base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
(out/'full-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
sys.exit(code if before==after else 99)
