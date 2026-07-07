"""pytest shared fixtures."""

from __future__ import annotations

import pytest

from esports_sim.registry import GameData, load_all


@pytest.fixture(scope="session")
def game_data() -> GameData:
    return load_all()
