"""Exercise seed-bound lobby previews and stale-response behavior in actual JS."""
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.web


def test_lobby_seed_preview_refresh():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    result = subprocess.run(
        [node, "tests/lobby_seed_preview_check.cjs"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"Lobby seed frontend check exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
