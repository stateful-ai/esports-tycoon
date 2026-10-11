"""Exercise development control readback and failure handling in the actual JS."""
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.web


def test_development_plan_feedback_refresh():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    subprocess.run(
        [node, "tests/development_feedback_check.cjs"],
        check=True, capture_output=True, text=True,
    )
