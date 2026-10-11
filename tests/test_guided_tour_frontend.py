"""Exercise tour lifecycle without starting a campaign or browser."""
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.web


@pytest.mark.parametrize("script", ["guided_tour_check.cjs", "help_preference_check.cjs"])
def test_guided_tour_lifecycle(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    subprocess.run(
        [node, f"tests/{script}"],
        cwd=Path(__file__).resolve().parents[1],
        check=True, capture_output=True, text=True,
    )
