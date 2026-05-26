"""The canned-save layer: YAML on disk, typed :class:`WorldState` in memory.

M0 ships one hand-authored save at the canonical save root
(``saves/week6.yaml``, shipped as package data via the ``saves`` package).
Tools import this loader rather than re-parsing the YAML themselves, keeping a
single typed entry point and a single documented location.
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
