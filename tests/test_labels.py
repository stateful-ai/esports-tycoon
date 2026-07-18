import pytest

from esports_sim.labels import humanize_identifier, humanize_phrase


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("team_player", "Team Player"),
        ("on-track", "On Track"),
        ("eco_greed", "Eco Greed"),
        ("igl", "IGL"),
        ("kayo", "KAY/O"),
        ("kda", "K/D/A"),
    ],
)
def test_humanize_identifier_formats_internal_labels(value, expected):
    assert humanize_identifier(value) == expected


def test_humanize_phrase_keeps_sentence_flow():
    assert humanize_phrase("youth_project") == "youth project"
