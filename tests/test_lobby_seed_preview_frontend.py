"""Exercise seed-bound lobby previews and stale-response behavior in actual JS."""
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.web


def test_lobby_seed_preview_refresh():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    subprocess.run(
        [node, "tests/lobby_seed_preview_check.cjs"],
        check=True, capture_output=True, text=True,
    )
