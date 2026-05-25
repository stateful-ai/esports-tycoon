"""The web app's default bind port must not collide with the services that
commonly hold ports on a dev box — a local LLM server (:8000, where
``GAME_LLM_*`` points), an LLM router (:8001), and a Stable Diffusion UI
(:7860). Regression: the slice used to default to :8000 and fail to bind when a
local model server was already running there.

These tests are Flask-free on purpose (importing the CLI modules never requires
Flask), so they run in CI without the ``[web]`` extra installed.
"""

import unittest

from esports_tycoon.__main__ import web_default_port
from esports_tycoon.web.__main__ import DEFAULT_PORT

COLLIDING_DEV_PORTS = {8000, 8001, 7860}


class WebDefaultPortTest(unittest.TestCase):
    def test_default_port_avoids_known_dev_services(self):
        self.assertNotIn(DEFAULT_PORT, COLLIDING_DEV_PORTS)

    def test_core_cli_play_shares_the_web_default(self):
        # The `play` subcommand must not drift from the web module's default —
        # one source of truth so docs and both entry points agree.
        self.assertEqual(web_default_port(), DEFAULT_PORT)


if __name__ == "__main__":
    unittest.main()
