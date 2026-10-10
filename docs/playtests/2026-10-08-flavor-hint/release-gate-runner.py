import hashlib
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

run = Path(__file__).resolve().parent
root = run.parents[2]
out = root / 'docs/playtests/2026-10-08-flavor-hint'
freeze_path = run / 'source-freeze.json'
freeze = json.loads(freeze_path.read_text(encoding='utf-8'))

def now():
    return datetime.now(timezone.utc).isoformat()

def verify_source():
    mismatches = [p for p, h in freeze['sha256'].items()
                  if not (root / p).exists()
                  or hashlib.sha256((root / p).read_bytes()).hexdigest() != h]
    if mismatches:
        raise AssertionError(f'Frozen source changed: {mismatches}')
    return len(freeze['sha256'])

def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)

result = {'started_at_utc': now(), 'runner_pid': os.getpid(),
          'source_freeze_sha256': hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
          'base_head': freeze['head'], 'cwd': str(root),
          'command': [sys.executable, '-m', 'pytest', '-q'],
          'superseded_log': str(out / 'full-pytest.log'),
          'superseded_exit_code': None}
try:
    result['source_files_verified_before'] = verify_source()
    env = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONUTF8='1', SOCIAL_LLM='off')
    result['imported_package'] = subprocess.check_output(
        [sys.executable, '-c', 'import esports_sim; print(esports_sim.__file__)'],
        cwd=root, env=env, text=True).strip()
    assert str(root / 'src').lower() in result['imported_package'].lower()
    with (out / 'release-full-pytest.log').open('wb') as log:
        p = subprocess.Popen(result['command'], cwd=root, env=env,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        result['pytest_pid'] = p.pid
        write_json(run / 'release-full-running.json', result)
        result['pytest_exit_code'] = p.wait()
        write_json(out / 'release-pytest-exit.json',
                   {'runner_pid': os.getpid(), 'pytest_pid': p.pid,
                    'pytest_exit_code': result['pytest_exit_code'], 'received_at_utc': now()})
    result['source_files_verified_after'] = verify_source()
    result['source_unchanged'] = True
    result['exit_code'] = result['pytest_exit_code']
except BaseException:
    result['exception'] = traceback.format_exc()
    result['exit_code'] = 1
finally:
    result['finished_at_utc'] = now()
    write_json(out / 'release-full-result.json', result)
