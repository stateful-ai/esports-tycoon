"""Exercise rendered CLI accounting, including primary-manager isolation."""
from io import StringIO

import pytest
from rich.console import Console

from esports_sim.app import cli
from esports_sim.manager.campaign import WeekReport, new_campaign


class AsciiCapture(StringIO):
    @property
    def encoding(self):
        return "ascii"


@pytest.mark.parametrize("upkeep", [1500, 0])
def test_cli_weekly_finances_render_expenses_and_actual_primary_upkeep(game_data, monkeypatch, upkeep):
    gs = new_campaign(game_data, seed=4308)
    other = next(t for t in gs.teams if t != gs.user_team_id)
    gs.human_team_ids.append(other)
    gs.set_acting(other)
    report = WeekReport(
        season=1, week=10, phase="regular", user_income=110732,
        user_expenses=47100 + upkeep,
        facility_upkeep_by={gs.user_team_id: upkeep, other: 99000},
    )
    before = gs.model_dump_json()
    output = AsciiCapture()
    monkeypatch.setattr(cli, "console", Console(file=output, color_system=None, width=120))
    cli.render_week_results(gs, report)
    rendered = output.getvalue()
    expected_net = 110732 - 47100 - upkeep
    assert f"weekly finances: +110,732 income, -{47100 + upkeep:,} expenses (net {expected_net:+,})" in rendered
    if upkeep:
        assert "facility upkeep: -1,500 (included in expenses)" in rendered
    else:
        assert "facility upkeep" not in rendered
    assert "payroll" not in rendered and "sponsor" not in rendered
    assert "99,000" not in rendered
    assert rendered.isascii()
    assert gs.model_dump_json() == before


def test_cli_negative_income_uses_one_sign_and_reconciles_net(game_data, monkeypatch):
    gs = new_campaign(game_data, seed=4308)
    report = WeekReport(season=1, week=10, phase="regular", user_income=-2500, user_expenses=1500)
    output = AsciiCapture()
    monkeypatch.setattr(cli, "console", Console(file=output, color_system=None, width=120))
    cli.render_week_results(gs, report)
    assert "weekly finances: -2,500 income, -1,500 expenses (net -4,000)" in output.getvalue()
    assert output.getvalue().isascii()
