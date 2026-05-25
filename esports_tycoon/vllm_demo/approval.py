"""The founder's written sign-off on a vLLM-mode demo, bound to its output.

"Founder signs off in writing before any vLLM-mode screenshot is taken or shared"
(``m0_plan_v2.md`` M0.2; ``scope-red-team.md`` #6). Mechanically this mirrors the
cast-lock gate (:mod:`esports_tycoon.cast_lock.approval`): exactly one atomic
approve/reject decision, recorded to a YAML file, **bound to a content digest** so
it cannot silently outlive the thing it approved.

The thing approved here is one :func:`~esports_tycoon.vllm_demo.preflight.run_preflight`
run's *evidence* — the model, the inputs, the safety verdict, and the exact
rendered recap & feed (digested together). Because vLLM output is
non-deterministic, the next generation produces a different digest, so a sign-off
authorises *that one screenshot surface* and goes ``stale`` for anything else.
Three rules fall out of that:

* A preflight whose automated gate failed (a safety leak, unsafe output, or a
  blown latency budget — ``evidence["gate_ready"] is False``) **cannot be
  approved**, the same way a failing cast-lock batch cannot be.
* The decision records ``digest``; :func:`screenshot_allowed` only returns true
  when an *approve* decision's digest still matches the current evidence.
* Any re-run that changes the output makes the prior decision ``stale``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
#: Where the founder's decision is recorded — sibling of the cast-lock approval.
DEFAULT_RECORD_PATH = _REPO_ROOT / "saves" / "vllm_demo.approval.yaml"

VALID_DECISIONS = {"approve", "reject"}

__all__ = [
    "DEFAULT_RECORD_PATH",
    "VALID_DECISIONS",
    "record_decision",
    "load_record",
    "gate_status",
    "screenshot_allowed",
]


def record_decision(
    evidence: Mapping[str, Any],
    decision: str,
    approver: str,
    reason: str = "",
    when: Optional[datetime] = None,
    record_path: str | Path = DEFAULT_RECORD_PATH,
) -> dict[str, Any]:
    """Record ONE atomic approve/reject decision over a preflight's evidence.

    ``evidence`` is a :meth:`PreflightResult.evidence` mapping (live, or loaded
    from ``preflight.json``). Approving a preflight whose automated gate did not
    pass is refused — the founder can only sign off on a demo that already cleared
    safety and any latency budget. A rejection must carry a reason. The written
    record is bound to ``evidence["digest"]``. Returns the written record.
    """
    decision = decision.lower().strip()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(VALID_DECISIONS)}, got {decision!r}")
    if not approver.strip():
        raise ValueError("approver is required (who signed off)")

    digest = evidence.get("digest")
    if not digest:
        raise ValueError("evidence is missing a digest; run the preflight first")
    if decision == "approve" and not evidence.get("gate_ready"):
        raise ValueError(
            "cannot sign off on a preflight that did not pass the automated gate "
            "(safety + latency); re-run the preflight until it is green"
        )
    if decision == "reject" and not reason.strip():
        raise ValueError("a rejection must include a reason")

    when = when or datetime.now(timezone.utc)
    record: dict[str, Any] = {
        "gate": "vllm_demo",
        "decision": decision,
        "approver": approver.strip(),
        "reason": reason.strip(),
        "decided_at": when.replace(microsecond=0).isoformat(),
        "digest": digest,
        "model": evidence.get("model"),
        "slice_id": evidence.get("slice_id"),
        "gate_ready": bool(evidence.get("gate_ready")),
        "note": "Written founder sign-off authorising vLLM-mode screenshots of "
        "exactly this preflight output. Bound to digest; any re-generation that "
        "changes the recap/feed invalidates this until re-run.",
    }
    record_path = Path(record_path)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        yaml.safe_dump(record, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return record


def load_record(record_path: str | Path = DEFAULT_RECORD_PATH) -> Optional[dict[str, Any]]:
    """Load the sign-off record, or ``None`` if no decision has been recorded yet."""
    record_path = Path(record_path)
    if not record_path.exists():
        return None
    data = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def gate_status(
    evidence: Optional[Mapping[str, Any]],
    record: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve the current sign-off state for ``evidence`` against ``record``.

    States:
      * ``no_preflight`` — no preflight evidence to review.
      * ``unreviewed``   — evidence exists, no decision recorded.
      * ``approved``     — an approve decision whose digest still matches.
      * ``rejected``     — a reject decision whose digest still matches.
      * ``stale``        — a decision exists but the preflight output has changed.
    """
    if evidence is None:
        return {"status": "no_preflight", "approved": False}
    if record is None:
        return {"status": "unreviewed", "approved": False, "gate_ready": bool(evidence.get("gate_ready"))}

    matches = record.get("digest") == evidence.get("digest")
    decision = record.get("decision")
    if not matches:
        return {
            "status": "stale",
            "approved": False,
            "recorded_decision": decision,
            "detail": "preflight output changed since the decision; re-run the preflight and sign off again",
        }
    return {
        "status": "approved" if decision == "approve" else "rejected",
        "approved": decision == "approve",
        "recorded_decision": decision,
        "approver": record.get("approver"),
        "decided_at": record.get("decided_at"),
        "reason": record.get("reason"),
        "gate_ready": bool(evidence.get("gate_ready")),
    }


def screenshot_allowed(
    evidence: Optional[Mapping[str, Any]],
    record: Optional[Mapping[str, Any]],
) -> bool:
    """``True`` iff a vLLM-mode screenshot of ``evidence`` may be taken/shared.

    The whole gate in one predicate: a matching, *approved* sign-off exists **and**
    the preflight it approved still passes the automated gate. Defends in depth —
    a digest match already implies the same output and verdict, but we re-check
    ``gate_ready`` so a screenshot is never blessed on a failed run.
    """
    status = gate_status(evidence, record)
    return bool(status.get("approved")) and bool(evidence and evidence.get("gate_ready"))
