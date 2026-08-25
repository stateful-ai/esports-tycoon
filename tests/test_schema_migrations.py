"""Every schema version step must have a migration entry.

`GameState.load` walks the registry one step at a time:

    while version < SCHEMA_VERSION:
        data = _MIGRATIONS[version](data)

so a version bump WITHOUT a registry entry raises KeyError and no existing
save loads at all. That is exactly what shipped when SCHEMA_VERSION went
35 -> 36 for `recovery_booked_by`: the field itself needed no migration
logic (it has a default), and the absent entry still broke every save in
the wild. CI caught it as 16 simultaneous KeyError failures across nine
files, all of them incidental save-round-trip tests.

This is the cheap structural check none of those files were making: the
registry must be gapless, so the next bump fails here — in one obvious
test — instead of sixteen unrelated ones.
"""

from __future__ import annotations

import pytest

from esports_sim.manager.state import _MIGRATIONS, SCHEMA_VERSION


@pytest.mark.campaign
def test_every_version_step_has_a_migration() -> None:
    missing = [v for v in range(1, SCHEMA_VERSION) if v not in _MIGRATIONS]
    assert not missing, (
        f"SCHEMA_VERSION is {SCHEMA_VERSION} but no migration is registered "
        f"from version(s) {missing}. GameState.load walks every step, so a "
        "save at that version raises KeyError. Add a pass-through returning "
        "`data` unchanged if the bump is purely additive."
    )


@pytest.mark.campaign
def test_the_registry_stops_at_the_current_version() -> None:
    """A migration FROM the current version would never run, and hints that
    SCHEMA_VERSION was not bumped alongside it."""
    stray = sorted(v for v in _MIGRATIONS if v >= SCHEMA_VERSION)
    assert not stray, (
        f"migrations registered from version(s) {stray}, at or beyond "
        f"SCHEMA_VERSION {SCHEMA_VERSION} — they can never run. Bump "
        "SCHEMA_VERSION or drop them."
    )


@pytest.mark.campaign
def test_every_migration_is_callable_and_returns_a_dict() -> None:
    """A pass-through that forgets to `return data` yields None and the next
    step fails somewhere far away from the cause."""
    for version in sorted(_MIGRATIONS):
        migrate = _MIGRATIONS[version]
        assert callable(migrate), f"migration {version} is not callable"
        out = migrate({"schema_version": version})
        assert isinstance(out, dict), (
            f"migration v{version} returned {type(out).__name__}, not a dict "
            "— a pass-through must `return data`"
        )
