"""Regression coverage for compact matrix identities and accessible names."""
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.web


def test_season_h2h_team_identity():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend verification")
    subprocess.run(
        [node, "tests/season_h2h_identity_check.cjs"],
        check=True, capture_output=True, text=True,
    )
