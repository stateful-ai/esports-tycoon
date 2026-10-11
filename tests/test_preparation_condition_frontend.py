"""Verify preparation condition presentation against the actual frontend row."""
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.web


def test_preparation_condition_presentation():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    subprocess.run(
        [node, "tests/preparation_condition_check.cjs"],
        check=True, capture_output=True, text=True,
    )
