"""Synthetic-player harness: drive the real UI, look at it, file findings.

The campaign already has two agent-facing surfaces — the MCP play server and
``manager.decision_env`` — but both hand an agent a JSON observation. Neither
can answer "is this screen legible?", "is the button reachable?", "does the
number I just changed actually move on screen?". This package adds the third
surface: a synthetic player who navigates the shipped web UI in a real
browser, sees the same pixels a human sees, and writes structured findings.

Layout
------
``dom.py``       DOM snapshot -> readable text digest (pure; no browser).
``findings.py``  the findings ledger + severity/area vocabulary (pure).
``personas.py``  the synthetic-player briefs.
``session.py``   Playwright session: boot the server, drive the UI, screenshot.
``control.py``   HTTP control plane so a CLI client can drive one live session.
"""

from esports_sim.playtest.dom import SCREEN_SCRIPT, render_digest
from esports_sim.playtest.findings import (
    AREAS,
    SEVERITIES,
    Finding,
    aggregate,
    load_findings,
    render_report,
)
from esports_sim.playtest.personas import PERSONAS, Persona, persona

__all__ = [
    "AREAS",
    "PERSONAS",
    "SCREEN_SCRIPT",
    "SEVERITIES",
    "Finding",
    "Persona",
    "aggregate",
    "load_findings",
    "persona",
    "render_digest",
    "render_report",
]
