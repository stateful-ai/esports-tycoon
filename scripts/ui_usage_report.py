"""Read-only aggregate of the retained local UI usage sidecar."""
import json
from pathlib import Path
import sys

from esports_sim.web.usage_telemetry import UsageStore

if __name__ == "__main__":
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("saves/usage")
    print(json.dumps(UsageStore(directory).report(), indent=2, sort_keys=True))
