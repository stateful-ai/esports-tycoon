from pathlib import Path
import hashlib,json,subprocess,os,sys,time
root=Path.cwd(); out=root/'runs/full-gate-gap35';out.mkdir(parents=True,exist_ok=True)
def manifest():
 paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],text=True).splitlines()
 names=sorted(set(p for p in paths if p.split('/')[0] in {'src','tests','data','scripts','config','.github','.claude'} or ('/' not in p and Path(p).suffix in {'.toml','.ini','.cfg','.yaml','.yml','.json','.ps1'})))
 return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in names if (root/p).is_file()}
before=manifest();(out/'pre.json').write_text(json.dumps(before,indent=2),encoding='utf8')
receipt={'supervisor_pid':os.getpid(),'command':[sys.executable,'-m','pytest','-q'],'cwd':str(root),'pythonpath':str(root/'src'),'started':time.time()}
(out/'running.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
env=os.environ.copy();env['PYTHONPATH']=str(root/'src');env['PYTHONIOENCODING']='utf-8'
with (out/'pytest.log').open('w',encoding='utf8') as log:
 child=subprocess.Popen(receipt['command'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 receipt['pytest_pid']=child.pid;(out/'running.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');code=child.wait()
after=manifest();(out/'post.json').write_text(json.dumps(after,indent=2),encoding='utf8')
receipt.update(exit_code=code,finished=time.time(),manifest_equal=before==after,files=len(before),pre_digest=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),post_digest=hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest())
(out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt));sys.exit(code or (0 if before==after else 98))
