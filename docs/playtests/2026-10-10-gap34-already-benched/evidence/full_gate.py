import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent


def freeze():
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
    ).decode().split("\0")
    prefixes = ("src/", "tests/", "data/", "scripts/", "config/", ".github/")
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in sorted(set(paths)) if path and ("/" not in path or path.startswith(prefixes))
            and (ROOT / path).is_file()}


if "--launch" in sys.argv:
    initial = freeze()
    (RUN / "freeze-before.json").write_text(json.dumps(initial, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    with (RUN / "gate-writer.log").open("w") as stream:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve())], cwd=ROOT, env=env,
                                stdout=stream, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    (RUN / "gate-launch.json").write_text(json.dumps({
        "pid": proc.pid, "native_python": sys.executable, "cwd": str(ROOT),
        "command": [sys.executable, "-m", "pytest", "-q", "-n2"],
        "writer": str(Path(__file__).resolve()), "receipt": str(RUN / "gate-receipt.json"),
        "launched_at_utc": datetime.now(timezone.utc).isoformat(), "source_files": len(initial),
    }, indent=2), encoding="utf-8")
    print(f"Durable gate writer PID {proc.pid}; {len(initial)} frozen source/config files")
else:
    started = datetime.now(timezone.utc).isoformat()
    with (RUN / "full-pytest.log").open("w", encoding="utf-8") as stream:
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-n2"], cwd=ROOT,
                                stdout=stream, stderr=subprocess.STDOUT)
    final = freeze()
    (RUN / "freeze-after.json").write_text(json.dumps(final, indent=2), encoding="utf-8")
    initial = json.loads((RUN / "freeze-before.json").read_text(encoding="utf-8"))
    changed = sorted(path for path in initial.keys() | final.keys() if initial.get(path) != final.get(path))
    receipt = {"exit_code": result.returncode, "source_freeze_matches": not changed,
               "changed_source_files": changed, "started_at_utc": started,
               "finished_at_utc": datetime.now(timezone.utc).isoformat(),
               "native_python": sys.executable, "cwd": str(ROOT),
               "command": [sys.executable, "-m", "pytest", "-q", "-n2"]}
    (RUN / "gate-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt), flush=True)
