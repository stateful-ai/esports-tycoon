"""CLI for the structured-output adherence spike.

    python -m esports_tycoon.model_spike [--model M] [--temperature T] \\
        [--max-retries N] [--threshold 0.9] [--save SAVE] [--no-write]

Samples a candidate local model against the content adapter's contract — the
``{text, cites}`` reply under each kind's token cap — across a fixed corpus of ten
prompts spanning all three content kinds and all five player personas. It reports
how many returned schema-valid JSON and, if the candidate cleared the ``≥9/10``
bar, prints (and writes) the **chosen model + settings**.

With no ``--model`` / ``--temperature`` / ``--max-retries`` the spike samples the
env-configured client (``GAME_LLM_*``; needs ``pip install -e .[vllm]``). Pass any
of them to pin the settings under test, so the spike doubles as a settings sweep:
run it at a couple of temperatures and adopt the model + settings that pass.

Exit code is the verdict: 0 only when the candidate passed. Run
``python -m esports_tycoon.vllm_demo smoke`` first so a down/cold endpoint is not
mistaken for a non-adhering model.
"""

from __future__ import annotations

import argparse
import sys

from esports_tycoon.canned import loader
from esports_tycoon.content import game_llm
from esports_tycoon.model_spike.adherence import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_THRESHOLD,
    run_adherence_spike,
    write_report,
)

_OK = "✓"
_NO = "✗"


def _build_client(args):
    """The client to sample. Env-configured by default; pinned when flags are given.

    Returns ``None`` when no settings are pinned, so the core falls back to the
    process default (:func:`game_llm.get_llm`) and the no-flags path stays the
    plain "test what env says" case.
    """
    if args.model is None and args.temperature is None and args.max_retries is None:
        return None
    kwargs = {}
    if args.model is not None:
        kwargs["model"] = args.model
    if args.temperature is not None:
        kwargs["temperature"] = args.temperature
    if args.max_retries is not None:
        kwargs["max_retries"] = args.max_retries
    return game_llm.GameLLM(**kwargs)


def _endpoint_hint() -> None:
    print(
        "    Check the local endpoint is up and GAME_LLM_* are set "
        "(and `pip install -e .[vllm]`); smoke it first with "
        "`python -m esports_tycoon.vllm_demo smoke`.",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esports_tycoon.model_spike", description=__doc__)
    parser.add_argument("--save", default=str(loader.DEFAULT_SAVE_PATH), help="path to the canned save YAML")
    parser.add_argument("--model", default=None, help="model name to pin (default: GAME_LLM_MODEL from env)")
    parser.add_argument("--temperature", type=float, default=None, help="decode temperature to pin")
    parser.add_argument("--max-retries", type=int, default=None, help="client repair-retry budget to pin")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"pass fraction (default: {DEFAULT_THRESHOLD} = 9/10)",
    )
    parser.add_argument("--artifacts-dir", default=str(DEFAULT_ARTIFACTS_DIR), help="where to write the report")
    parser.add_argument("--no-write", action="store_true", help="do not write the evidence JSON")
    args = parser.parse_args(argv)

    world = loader.load(args.save)
    try:
        client = _build_client(args)
    except Exception as exc:  # noqa: BLE001 — surface a bad client build plainly
        print(f"{_NO} could not construct the LLM client: {exc}", file=sys.stderr)
        _endpoint_hint()
        return 2

    report = run_adherence_spike(world, client=client, threshold=args.threshold)

    print("=" * 70)
    print(" STRUCTURED-OUTPUT ADHERENCE SPIKE")
    print("=" * 70)
    print(f" Model     : {report.model}")
    s = report.settings
    print(f" Settings  : temperature={s.temperature} max_retries={s.max_retries} decode={s.decode}")
    print(f" Token caps: {s.token_caps}")
    if report.error is not None:
        print(f" Reachable : {_NO} {report.error}")
        print("=" * 70)
        print(f"{_NO} SPIKE FAILED — could not sample the model.")
        _endpoint_hint()
        return 1

    print("-" * 70)
    for r in report.results:
        mark = _OK if r.ok else _NO
        detail = f"{r.tokens_out} tok out, {r.latency_seconds:.3f}s" if r.ok else (r.error or "")
        print(f"  {mark} {r.name:<32} (cap {r.max_tokens:>3}) {detail}")
    print("-" * 70)
    rate_mark = _OK if report.passed else _NO
    print(
        f" Adherence : {rate_mark} {report.valid}/{report.total} schema-valid "
        f"(need {report.required}/{report.total} at threshold {report.threshold})"
    )

    if not args.no_write:
        path = write_report(report, args.artifacts_dir)
        print(f" Report    : {path}")
    print("=" * 70)

    if report.passed:
        print(f"{_OK} CHOSEN MODEL : {report.model}")
        print(
            f"   settings    : temperature={s.temperature}, max_retries={s.max_retries}, "
            f"decode={s.decode}, token_caps={s.token_caps}"
        )
        print(f"{_OK} SPIKE PASSED — this model + settings clears the adherence bar.")
        return 0
    print(
        f"{_NO} SPIKE FAILED — {report.valid}/{report.total} valid is below the "
        f"{report.required}/{report.total} bar; do not adopt this model + settings."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
