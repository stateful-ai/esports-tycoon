import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root=Path('C:/Users/aidan/.codex/worktrees/masters-aftermath-playtest/ESports Simulator')
run=root/'runs/playtests/2026-10-11-champions-quarterfinal'
raw=(run/'saves/sessions.json').read_bytes()
sessions=json.loads(raw)['sessions']
matching=[sid for sid, membership in sessions.items() if membership==['26UHC','team_nexus']]
assert len(matching)==1
out=run/'browser-identity-restored.json'
assert not out.exists()
result=subprocess.run([r'C:\Program Files\nodejs\npx.cmd','--package','@playwright/cli','playwright-cli','-s=champions-quarterfinal','cookie-set','esports_sid',matching[0],'--domain','127.0.0.1','--path','/'],cwd=root,capture_output=True,text=True)
# CLI may echo the cookie value; retain neither stream and never print it.
assert result.returncode==0, 'Cookie restoration command failed; secret-bearing output withheld'
proof={'restored_at_utc':datetime.now(timezone.utc).isoformat(),'browser_session':'champions-quarterfinal','cookie_name':'esports_sid','domain':'127.0.0.1','fixture_sessions_sha256':hashlib.sha256(raw).hexdigest(),'matching_test_memberships':1,'world':'26UHC','team':'team_nexus','command_exit_code':0,'limits':'Harness restoration of copied test identity only; no gameplay decision or user browser change.'}
out.write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof))



