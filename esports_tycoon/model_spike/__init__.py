"""The local-model structured-output adherence spike.

A standalone spike that runs **parallel to the spine**: it answers, empirically,
whether a candidate local 7B/8B model returns schema-valid JSON for the content
adapter's contract (the ``{text, cites}`` reply, under the per-kind token cap) on
enough sampled prompts to ship — and, when it does, emits the **chosen model +
settings**.

    python -m esports_tycoon.model_spike                       # sample env-configured model
    python -m esports_tycoon.model_spike --model qwen3-8b      # pin the model under test
    python -m esports_tycoon.model_spike --temperature 0.2     # sweep a decode setting

See :mod:`~esports_tycoon.model_spike.adherence` for the corpus + verdict. Run
:mod:`esports_tycoon.vllm_demo` ``smoke`` first so a down/cold endpoint isn't
mistaken for a non-adhering model.
"""

from esports_tycoon.model_spike.adherence import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_THRESHOLD,
    MIN_SAMPLES,
    REPORT_FILENAME,
    AdherenceReport,
    RunSettings,
    SamplePrompt,
    SampleResult,
    build_sample_prompts,
    run_adherence_spike,
    write_report,
)

__all__ = [
    "DEFAULT_ARTIFACTS_DIR",
    "DEFAULT_THRESHOLD",
    "MIN_SAMPLES",
    "REPORT_FILENAME",
    "AdherenceReport",
    "RunSettings",
    "SamplePrompt",
    "SampleResult",
    "build_sample_prompts",
    "run_adherence_spike",
    "write_report",
]
