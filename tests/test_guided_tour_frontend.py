"""Exercise tour lifecycle without starting a campaign or browser."""
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.web


def test_guided_tour_lifecycle():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    subprocess.run(
        [node, "tests/guided_tour_check.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        check=True, capture_output=True, text=True,
    )
