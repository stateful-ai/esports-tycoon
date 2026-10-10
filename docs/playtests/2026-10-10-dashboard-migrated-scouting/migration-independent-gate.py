import hashlib,json,os,subprocess,sys,traceback
from datetime import datetime,timezone
from pathlib import Path
run=Path(__file__).resolve().parent
root=run.parents[2]
result={'started_at_utc':datetime.now(timezone.utc).isoformat(),'runner_pid':os.getpid(),'cwd':str(root),'command':[sys.executable,'-m','pytest','-q','-n','2']}
freeze=json.loads((run/'migration-independent-source-freeze.json').read_text(encoding='utf-8'))
def check():
    return all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in freeze['sha256'].items())
try:
    assert check()
    env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONUTF8='1',SOCIAL_LLM='off')
    with (run/'migration-independent-full.log').open('wb') as log:
        p=subprocess.Popen(result['command'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        result['pytest_pid']=p.pid
        (run/'migration-independent-running.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        result['exit_code']=p.wait()
        (run/'migration-independent-exit.json').write_text(json.dumps({'pytest_pid':p.pid,'exit_code':result['exit_code'],'finished_at_utc':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
    result['source_unchanged']=check()
    assert result['source_unchanged']
except BaseException:
    result['exception']=traceback.format_exc()
    result.setdefault('exit_code',1)
finally:
    result['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    (run/'migration-independent-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

