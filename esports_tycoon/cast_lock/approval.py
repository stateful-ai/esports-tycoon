"""The founder's single batched approve/reject pass over the tone + cast lock.

The locked decision (mem_20260525T150603Z_b9788c) is that the founder approves the
*whole batch* in one pass: the tone 1-pager plus the canned save (cast, clash
pairs, rivals, >=30 memories, last-week scoreline, last-week feed). There is no
per-name round-tripping.

Mechanically that means:

  * The batch is the two files together; their combined content has one digest.
  * There is exactly ONE decision field (approve | reject) over the whole batch.
  * A batch that fails acceptance validation cannot be approved.
  * The recorded decision is bound to the content digest, so any later edit makes
    the approval `stale` until the gate is re-run.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .spec import (
    DEFAULT_DOC_PATH,
    DEFAULT_SAVE_PATH,
    ValidationResult,
    load_save,
    validate_save,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_PATH = _REPO_ROOT / "saves" / "week6.approval.yaml"

VALID_DECISIONS = {"approve", "reject"}


def _file_digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def batch_digest(
    save_path: str | Path = DEFAULT_SAVE_PATH,
    doc_path: str | Path = DEFAULT_DOC_PATH,
) -> str:
    """A single digest over the whole batch (1-pager + canned save).

    Order is fixed (doc, then save) and the two file digests are joined with a
    separator so the batch digest changes if *either* file changes.
    """
    parts = [f"doc:{_file_digest(doc_path)}", f"save:{_file_digest(save_path)}"]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass
class Batch:
    """The reviewable unit: the two files, the parsed save, and the verdict."""

    save_path: Path
    doc_path: Path
    save: dict[str, Any]
    validation: ValidationResult
    digest: str

    @property
    def approvable(self) -> bool:
        return self.validation.ok


def build_batch(
    save_path: str | Path = DEFAULT_SAVE_PATH,
    doc_path: str | Path = DEFAULT_DOC_PATH,
) -> Batch:
    """Load both files, validate the save, and compute the batch digest."""
    save_path = Path(save_path)
    doc_path = Path(doc_path)
    if not doc_path.exists():
        raise FileNotFoundError(f"tone 1-pager not found: {doc_path}")
    save = load_save(save_path)
    validation = validate_save(save)
    return Batch(
        save_path=save_path,
        doc_path=doc_path,
        save=save,
        validation=validation,
        digest=batch_digest(save_path, doc_path),
    )


def record_decision(
    batch: Batch,
    decision: str,
    approver: str,
    reason: str = "",
    when: datetime | None = None,
    record_path: str | Path = DEFAULT_RECORD_PATH,
) -> dict[str, Any]:
    """Record ONE atomic approve/reject decision over the whole batch.

    Approving a batch that fails validation is rejected — the founder can only
    lock a batch that meets the acceptance bar. Returns the written record.
    """
    decision = decision.lower().strip()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(VALID_DECISIONS)}, got {decision!r}")
    if not approver.strip():
        raise ValueError("approver is required (who made the call)")
    if decision == "approve" and not batch.approvable:
        failed = ", ".join(c.name for c in batch.validation.failures)
        raise ValueError(f"cannot approve a batch that fails validation: {failed}")
    if decision == "reject" and not reason.strip():
        raise ValueError("a rejection must include a reason")

    when = when or datetime.now(timezone.utc)
    record: dict[str, Any] = {
        "batch": "tone_and_cast_lock+week6",
        "decision": decision,
        "approver": approver.strip(),
        "reason": reason.strip(),
        "decided_at": when.replace(microsecond=0).isoformat(),
        "batch_digest": batch.digest,
        "files": {
            "doc": _relpath(batch.doc_path),
            "save": _relpath(batch.save_path),
        },
        "acceptance": {c.name: c.passed for c in batch.validation.checks},
        "note": "One batched decision over the whole cast/tone lock. Bound to "
        "batch_digest; any edit to either file invalidates this until re-run.",
    }
    record_path = Path(record_path)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        yaml.safe_dump(record, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return record


def load_record(record_path: str | Path = DEFAULT_RECORD_PATH) -> dict[str, Any] | None:
    """Load the approval record, or None if no decision has been recorded yet."""
    record_path = Path(record_path)
    if not record_path.exists():
        return None
    data = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def approval_status(batch: Batch, record: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the current lock state of the batch.

    States:
      * ``unreviewed``  — no decision recorded.
      * ``approved``    — decision == approve and digest still matches.
      * ``rejected``    — decision == reject and digest still matches.
      * ``stale``       — a decision exists but the batch content has changed.
    """
    if record is None:
        return {"status": "unreviewed", "approved": False}

    matches = record.get("batch_digest") == batch.digest
    decision = record.get("decision")
    if not matches:
        return {
            "status": "stale",
            "approved": False,
            "recorded_decision": decision,
            "detail": "batch content changed since the decision; re-run the gate",
        }
    return {
        "status": "approved" if decision == "approve" else "rejected",
        "approved": decision == "approve",
        "recorded_decision": decision,
        "approver": record.get("approver"),
        "decided_at": record.get("decided_at"),
        "reason": record.get("reason"),
    }


def _relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)
