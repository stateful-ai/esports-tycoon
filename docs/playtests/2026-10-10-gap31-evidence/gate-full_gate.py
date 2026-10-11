import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
def freeze():
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root, text=True).splitlines()
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sorted(set(paths))
            if "/" not in p or p.split("/")[0] in {"src", "tests", "data", "scripts", "config", ".github"}}
before = freeze()
(out / "freeze-before.json").write_text(json.dumps(before, indent=2))
env = os.environ.copy()
env["PYTHONPATH"] = str(root / "src")
command = [sys.executable, "-m", "pytest", "-q", "-n", "2"]
with (out / "full-pytest.log").open("w", encoding="utf-8") as log:
    process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
    receipt = {"runner_pid": os.getpid(), "pytest_pid": process.pid, "cwd": str(root), "command": command,
               "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2))
    code = process.wait()
after = freeze()
(out / "freeze-after.json").write_text(json.dumps(after, indent=2))
receipt.update(exit_code=code, status="completed", completed_at=datetime.now(timezone.utc).isoformat(),
               freeze_unchanged=before == after, frozen_file_count=len(before))
(out / "receipt.json").write_text(json.dumps(receipt, indent=2))
sys.exit(code if before == after else 99)
