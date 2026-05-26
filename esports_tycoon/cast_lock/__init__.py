"""cast_lock — the M0.0 tone + cast lock gate.

This package owns the *acceptance bar* for the hand-authored canned save and the
founder's single batched approve/reject pass. It deliberately does NOT define the
game's runtime schema (Player / MemoryEntry / WhyRecord / ...) — that is the
separate schema ticket. Here we only validate that the draft canned save (shipped
as package data) plus the tone 1-pager are complete enough to lock, and we record
one atomic decision over the whole batch.
"""

from .spec import (
    Check,
    ValidationResult,
    DEFAULT_SAVE_PATH,
    DEFAULT_DOC_PATH,
    load_save,
    validate_save,
)
from .approval import (
    DEFAULT_RECORD_PATH,
    Batch,
    batch_digest,
    build_batch,
    record_decision,
    load_record,
    approval_status,
)

__all__ = [
    "Check",
    "ValidationResult",
    "DEFAULT_SAVE_PATH",
    "DEFAULT_DOC_PATH",
    "DEFAULT_RECORD_PATH",
    "load_save",
    "validate_save",
    "Batch",
    "batch_digest",
    "build_batch",
    "record_decision",
    "load_record",
    "approval_status",
]
