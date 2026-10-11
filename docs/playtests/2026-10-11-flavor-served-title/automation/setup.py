import hashlib, json, os, secrets, socket, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone
root = Path.cwd()
run = root / 'runs/playtests/2026-10-11-flavor-served-title'
docs = root / 'docs/playtests/2026-10-11-flavor-served-title'
docs.mkdir(parents=True, exist_ok=True)
saves = run / 'saves'
saves.mkdir(exist_ok=True)
with socket.socket() as port:
    assert port.connect_ex(('127.0.0.1', 8541)) != 0, 'Port already occupied'
source = root / 'runs/playtests/2026-10-10-flavor-feedback/save-before.json'
before = json.loads(source.read_text(encoding='utf-8'))
code = 'FLV42'
sid = secrets.token_hex(16)
tid = 'team_nexus'
digest = hashlib.blake2b(code.encode(), digest_size=8).hexdigest()
save = saves / f'campaign_{digest}.json'
save.write_bytes(source.read_bytes())
(run / 'save-before.json').write_bytes(source.read_bytes())
(saves / f'campaign_{digest}.meta.json').write_text(json.dumps({'mode':'solo'}), encoding='utf-8')
(saves / 'sessions.json').write_text(json.dumps({'sessions': {sid:[code,tid]}, 'history':{sid:[[code,tid,'Team Nexus','solo']]}}), encoding='utf-8')
event = before['flavor_events_by'][tid]
cache = {event['id']:{'title':'Community clinic: a small group invitation', 'prompt':event['prompt'], 'choices':[c['label'] for c in event['choices']]}}
(saves / f'flavor_llm_{code}.json').write_text(json.dumps(cache), encoding='utf-8')
# Cached overlays remain active; generation is disabled, so no provider is called.
env = dict(os.environ, PYTHONPATH=str(root/'src'), PYTHONUTF8='1', SOCIAL_LLM='off', FLAVOR_LLM='off')
python = r'C:\Users\aidan\workspace\esports-simulator\ESports Simulator\.venv-win\Scripts\python.exe'
sys.path.insert(0, r'C:\Users\aidan\workspace\agora')
from flywheel.recorder import recent
(docs/'flywheel-before.json').write_text(json.dumps(recent(domain='esports-playtest',limit=8),indent=2),encoding='utf-8')
historical = {}
for name in subprocess.check_output(['git','ls-files','docs/playtests/2026-10-10-flavor-feedback','docs/playtests/integration-pr370','docs/playtests/actions.csv'],text=True).splitlines():
    historical[name] = hashlib.sha256((root/name).read_bytes()).hexdigest()
(run/'historical-before.json').write_text(json.dumps(historical,indent=2),encoding='utf-8')
freeze = {}
for name in ['src/esports_sim/web/static/app.js','tests/flavor_feedback_check.cjs']:
    raw = (root/name).read_bytes()
    target = docs/'source'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(raw)
    freeze[name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'dirty_source': True}
(docs/'source-freeze.json').write_text(json.dumps({'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'files':freeze,'local_tests':'UNRUN by explicit user instruction'},indent=2),encoding='utf-8')
cmd = [python,'-m','esports_sim','--web','--port','8541','--no-browser']
with (run/'server.log').open('wb') as log:
    process=subprocess.Popen(cmd,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'private.json').write_text(json.dumps({'sid':sid,'save':str(save),'pid':process.pid}),encoding='utf-8')
(docs/'setup-receipt.json').write_text(json.dumps({'port':8541,'pid':process.pid,'cwd':str(run),'source_fixture_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'seed':before['seed'],'season':before['season'],'week':before['week'],'world':code,'event_id':event['id'],'fallback_title':event['title'],'overlay_title':cache[event['id']]['title'],'no_llm_calls':True,'package_source':str(root/'src')},indent=2),encoding='utf-8')
print({'pid':process.pid,'seed':before['seed'],'season':before['season'],'week':before['week'],'title':event['title']})
