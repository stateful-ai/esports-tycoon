"""Event log — the canonical record of a simulation.

The log keeps an in-memory list for hot-loop access, and optionally writes
each event to an append-only JSONL file so that runs are persistable and
reloadable.

The log is write-once-ordered: events may only be appended. Replays read
events in the order they were produced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from pydantic import TypeAdapter

from esports_sim.schemas.events import Event, EventUnion

# One adapter for the whole module — safe to share.
_EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(EventUnion)


class EventLog:
    """Append-only event log with optional JSONL persistence.

    Parameters
    ----------
    path:
        If provided, every appended event is also written to this file
        (append mode, flushed per event). The file is created on first write.
    """

    def __init__(self, path: Path | str | None = None):
        self._events: list[Event] = []
        self._path: Path | None = Path(path) if path is not None else None
        self._file = None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Open in append-text mode; one JSON object per line.
            self._file = self._path.open("a", encoding="utf-8")

    # -- writes ------------------------------------------------------------

    def append(self, event: Event) -> None:
        self._events.append(event)
        if self._file is not None:
            line = event.model_dump_json()
            self._file.write(line + "\n")
            self._file.flush()

    def extend(self, events: Iterable[Event]) -> None:
        for e in events:
            self.append(e)

    # -- reads -------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    def __getitem__(self, idx: int) -> Event:
        return self._events[idx]

    def events(self) -> list[Event]:
        return list(self._events)

    def filter_type(self, type_name: str) -> list[Event]:
        return [e for e in self._events if e.type == type_name]

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- loading -----------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str) -> "EventLog":
        """Load an event log back from a JSONL file (read-only replay)."""
        log = cls()
        with Path(path).open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = _EVENT_ADAPTER.validate_python(json.loads(line))
                except Exception as exc:  # re-raise with line context
                    raise ValueError(
                        f"Failed to parse event on line {line_no}: {exc}"
                    ) from exc
                log._events.append(event)
        return log
