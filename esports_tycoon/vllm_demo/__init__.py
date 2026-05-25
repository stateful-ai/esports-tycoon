"""The vLLM-mode demo gate: safety + latency preflight, plus founder sign-off.

The gate that stands between a vLLM-mode slice run and a screenshot of it
(``m0_plan_v2.md`` M0.2; ``scope-red-team.md`` #6). Two halves:

* :mod:`~esports_tycoon.vllm_demo.preflight` — runs the whole slice end-to-end
  through the content adapter in ``vllm`` mode against the local Qwen endpoint,
  *measures and records* total latency, screens the adversarial-seed safety corpus
  and the run's own output, and bundles it all into a digest-bearing
  :class:`~esports_tycoon.vllm_demo.preflight.PreflightResult`.
* :mod:`~esports_tycoon.vllm_demo.approval` — the founder's single written
  approve/reject decision, bound to that digest, and the
  :func:`~esports_tycoon.vllm_demo.approval.screenshot_allowed` predicate the
  whole gate collapses to.

    python -m esports_tycoon.vllm_demo smoke        # is the endpoint up + structured + warm-fast?
    python -m esports_tycoon.vllm_demo preflight   # run + measure + screen + write
    python -m esports_tycoon.vllm_demo status       # gate state for the latest preflight
    python -m esports_tycoon.vllm_demo sign-off --approver <founder> [--reason ...]
    python -m esports_tycoon.vllm_demo reject   --approver <founder>  --reason ...

:mod:`~esports_tycoon.vllm_demo.smoke` is step zero of the bring-up: a single
cheap call that proves the local endpoint is reachable, returns a structured
reply, and answers within a warm-latency budget — run it before ``preflight`` so a
down or cold server isn't mistaken for a bad model.
"""

from esports_tycoon.vllm_demo.approval import (
    DEFAULT_RECORD_PATH,
    gate_status,
    load_record,
    record_decision,
    screenshot_allowed,
)
from esports_tycoon.vllm_demo.smoke import (
    DEFAULT_BUDGET_SECONDS,
    SmokeResult,
    run_smoke,
)
from esports_tycoon.vllm_demo.preflight import (
    DEFAULT_ARTIFACTS_DIR,
    CorpusResult,
    LatencyReport,
    OutputFinding,
    PreflightResult,
    SafetyReport,
    load_evidence,
    run_preflight,
    screen_corpus,
    screen_output,
    verify_artifacts,
    write_preflight,
)

__all__ = [
    "run_preflight",
    "write_preflight",
    "load_evidence",
    "verify_artifacts",
    "screen_corpus",
    "screen_output",
    "PreflightResult",
    "SafetyReport",
    "CorpusResult",
    "OutputFinding",
    "LatencyReport",
    "DEFAULT_ARTIFACTS_DIR",
    "record_decision",
    "load_record",
    "gate_status",
    "screenshot_allowed",
    "DEFAULT_RECORD_PATH",
    "run_smoke",
    "SmokeResult",
    "DEFAULT_BUDGET_SECONDS",
]
