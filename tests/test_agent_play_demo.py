"""The demo policy can operate with only manager observations and actions."""

from pathlib import Path
import runpy

import pytest


@pytest.mark.parametrize("events_enabled", [False, True])
def test_demo_uses_current_legal_events_without_hidden_state(events_enabled):
    scripted_turn = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "agent_play_demo.py")
    )["scripted_turn"]

    class ObservationOnlyWorld:
        trained = False
        flavor_resolved = False
        media_resolved = False

        @property
        def gs(self):
            raise AssertionError("a manager policy cannot read hidden GameState")

        def observe(self, team_id):
            return {"legal_actions": {
                "set_training": {"enabled": True, "options": ["team"]},
                "set_scout": {"enabled": False, "targets": []},
                "resolve_flavor": {
                    "enabled": events_enabled and self.trained and not self.flavor_resolved,
                    "event_id": "flavor-current" if self.trained else "flavor-stale",
                    "choice_ids": ["flavor-choice"],
                },
                "resolve_media": {
                    "enabled": events_enabled and self.flavor_resolved and not self.media_resolved,
                    "event_id": "media-current" if self.flavor_resolved else "media-stale",
                    "choice_ids": ["media-choice"],
                },
            }}

        def act(self, team_id, action):
            kind, params = action["kind"], action["params"]
            if kind == "set_training":
                self.trained = True
                return {"message": "trained"}
            if kind == "advance":
                assert not events_enabled or (self.flavor_resolved and self.media_resolved)
                return {"advanced": False, "waiting_on": ["other"]}
            legal = self.observe(team_id)["legal_actions"][kind]
            assert legal["enabled"]
            assert params["event_id"] == legal["event_id"]
            assert params["choice_id"] in legal["choice_ids"]
            if kind == "resolve_flavor":
                self.flavor_resolved = True
            else:
                self.media_resolved = True
            return {"message": "resolved"}

    world = ObservationOnlyWorld()
    scripted_turn(world, "seat", 0)
    assert world.trained
    assert world.flavor_resolved == events_enabled
    assert world.media_resolved == events_enabled
