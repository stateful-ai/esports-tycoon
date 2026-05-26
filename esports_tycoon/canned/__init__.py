"""The canned-save layer: YAML on disk, typed :class:`WorldState` in memory.

M0 ships one hand-authored save as package data
(``esports_tycoon/canned/data/week6.yaml``). Tools import this loader rather than
re-parsing the YAML themselves, keeping a single typed entry point.
"""

from .loader import (
    DEFAULT_SAVE_PATH,
    RefIssue,
    SaveReferentialIntegrityError,
    SchemaVersionError,
    check_referential_integrity,
    dumps,
    load,
    migrate,
    to_save_dict,
)

__all__ = [
    "DEFAULT_SAVE_PATH",
    "RefIssue",
    "SaveReferentialIntegrityError",
    "SchemaVersionError",
    "check_referential_integrity",
    "load",
    "to_save_dict",
    "dumps",
    "migrate",
]
