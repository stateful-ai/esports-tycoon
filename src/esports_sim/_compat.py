"""Cross-Python-version shims.

Kept tiny on purpose — only things whose native availability depends on
Python version. On 3.11+ these fall through to the stdlib.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum  # noqa: F401
else:  # pragma: no cover — exercised on 3.10 envs only
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Back-port of 3.11's StrEnum.

        Behaviour we care about:
          - subclass of str, so enum members `==` their string value
          - `str(member)` returns the value (not "Class.MEMBER")
          - serialises identically under Pydantic v2

        Auto-generated values are the *lowercased member name*, matching
        stdlib semantics.
        """

        def __new__(cls, value: str) -> "StrEnum":
            if not isinstance(value, str):
                raise TypeError(
                    f"StrEnum values must be str, got {type(value).__name__}"
                )
            obj = str.__new__(cls, value)
            obj._value_ = value
            return obj

        def __str__(self) -> str:  # match 3.11 behaviour
            return str.__str__(self)

        @staticmethod
        def _generate_next_value_(name, start, count, last_values):  # noqa: D401
            return name.lower()


__all__ = ["StrEnum"]
