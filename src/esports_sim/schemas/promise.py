from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ManagerPromise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    team_id: str
    player_id: str
    promise_type: str  # "play_time" / "renew_contract" / "make_captain"
    target_value: str | int | None = None
    weeks_left: int
    created_week: int
    created_season: int
    status: str = "active"  # "active", "kept", "broken"
    dressed_count: int = 0
    initial_duration: int = 0
    # Provenance of this promise, for inbox copy + dedup:
    # talk | llm | negotiation | transfer_request | bench_demand | leadership.
    source: str = "talk"

