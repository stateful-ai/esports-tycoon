"""The one-week slice runner: orchestration + the auto-recap artifact.

This package is the headless heart of the M0 slice — it plays one week
(practice → match → fallout) and emits the ``recap.md`` + ``feed.snapshot.html``
artifact, with no UI and no web dependency. The Flask app in
:mod:`esports_tycoon.web` is a thin shell over it.

    from esports_tycoon.canned import loader
    from esports_tycoon.runner import SliceConfig, SliceDecisions, run_slice, write_artifacts

    world = loader.load()
    result = run_slice(world, SliceConfig(seed=6), SliceDecisions(practice_focus="defaults"))
    recap_path, feed_path = write_artifacts(result, world, "runs")
"""

from esports_tycoon.runner.engine import halftime_scoreline, run_slice, slice_id
from esports_tycoon.runner.events import (
    EVENTS_FILENAME,
    SliceEvent,
    read_events,
    slice_events,
    write_events,
)
from esports_tycoon.runner.model import (
    OPEN_TEXT_MAX,
    PRACTICE_CHOICES,
    FeedPost,
    SliceConfig,
    SliceDecisions,
    SliceResult,
    normalize_open_text,
)
from esports_tycoon.runner.recap import (
    FEED_FILENAME,
    RECAP_FILENAME,
    render_feed_html,
    render_recap_md,
    write_artifacts,
)

__all__ = [
    "run_slice",
    "slice_id",
    "halftime_scoreline",
    "SliceConfig",
    "SliceDecisions",
    "SliceResult",
    "FeedPost",
    "PRACTICE_CHOICES",
    "OPEN_TEXT_MAX",
    "normalize_open_text",
    "render_recap_md",
    "render_feed_html",
    "write_artifacts",
    "RECAP_FILENAME",
    "FEED_FILENAME",
    "EVENTS_FILENAME",
    "SliceEvent",
    "slice_events",
    "read_events",
    "write_events",
]
