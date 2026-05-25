"""The vLLM-mode demo preflight: run the slice, measure it, screen it.

This is the automated half of the vLLM-mode demo gate (``m0_plan_v2.md`` M0.2
exit criterion; ``scope-red-team.md`` failure mode #6, "safety gates any LLM-mode
demo"). Before a vLLM-mode screenshot may be taken or shared, :func:`run_preflight`
runs the **whole slice** (practice → match → fallout) end-to-end through the
content adapter in ``vllm`` mode against the configured local Qwen endpoint and
produces one :class:`PreflightResult` bundling the three things the gate turns on:

* **latency** — the total wall-clock of the slice run, plus the per-model-call
  aggregate, *measured and recorded* (no founder-set ceiling exists yet, so it is
  reported, not failed, unless a ``latency_budget_seconds`` is supplied);
* **safety** — the adversarial-seed corpus (:data:`safety.ADVERSARIAL_SEED_CORPUS`)
  must be wholly blocked (proving the filter holds), *and* every piece of prose
  this run actually generated must screen clean (proving the demo output itself is
  safe to show); and
* the **founder-reviewable artifact** — the exact ``recap.md`` + ``feed.snapshot``
  the founder will screenshot, content-addressed by :attr:`PreflightResult.digest`
  so the written sign-off (see :mod:`~esports_tycoon.vllm_demo.approval`) binds to
  *this* output and goes stale the moment a re-generation changes it.

The LLM client is injected (``client=`` / the env-configured ``game_llm.get_llm()``
default), so the slice can be run against a real endpoint by the CLI and against a
canned stand-in by the tests, with no network in the latter. The preflight never
mutates ``world`` and is otherwise pure given its client's replies.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from esports_tycoon import safety
from esports_tycoon.content import game_llm
from esports_tycoon.content.config import ContentConfig
from esports_tycoon.runner import (
    SliceConfig,
    SliceDecisions,
    SliceResult,
    render_feed_html,
    render_recap_md,
    run_slice,
)
from esports_tycoon.schema import WorldState

__all__ = [
    "PREFLIGHT_FILENAME",
    "RECAP_FILENAME",
    "FEED_FILENAME",
    "DEFAULT_ARTIFACTS_DIR",
    "CorpusResult",
    "OutputFinding",
    "SafetyReport",
    "LatencyReport",
    "PreflightResult",
    "screen_corpus",
    "screen_output",
    "run_preflight",
    "write_preflight",
    "load_evidence",
    "verify_artifacts",
]

#: The evidence file the preflight writes; the founder's sign-off reads its digest.
PREFLIGHT_FILENAME = "preflight.json"
#: The founder-reviewable artifacts written alongside it (the actual screenshot
#: surface), rendered exactly as the in-app recap/feed render them.
RECAP_FILENAME = "recap.md"
FEED_FILENAME = "feed.snapshot.html"

#: Where the preflight bundle lands. Kept out of ``runs/`` (which is the
#: byte-deterministic *templated* output, content-addressed on inputs only — a
#: vLLM run shares the same ``slice_id`` and would otherwise clobber it).
DEFAULT_ARTIFACTS_DIR = Path("artifacts") / "vllm_demo"


# --------------------------------------------------------------------------- #
# Safety: the adversarial corpus must be blocked, the output must be clean.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CorpusResult:
    """The verdict of running the adversarial-seed corpus through the filter.

    ``passed`` is the gate signal: a non-empty corpus with **zero** leaks (every
    seed was blocked). ``leaks`` names any seed that slipped through, so a failure
    is actionable rather than just a red light.
    """

    total: int
    blocked: int
    leaks: list[str]
    by_category: dict[str, int]

    @property
    def passed(self) -> bool:
        return self.total > 0 and not self.leaks


@dataclass(frozen=True)
class OutputFinding:
    """One line of this run's founder-reviewable surface that the filter rejected.

    ``source`` locates it (``"narration"``, ``"halftime"``, ``"team_talk"``, or
    ``"feed:<handle>"``); its presence means the demo output itself is unsafe and
    the gate must not open. Most sources are *generated* prose, but ``team_talk``
    is the manager's own open-text line — it is rendered in ``recap.md`` and so is
    screened here too (unlike the ``fallout_post``, which already reaches the feed).
    """

    source: str
    text: str
    categories: list[str]


@dataclass(frozen=True)
class SafetyReport:
    """The two safety conditions the vLLM demo turns on, together.

    The corpus proves the *filter* works; the output findings prove *this run's*
    prose is clean. Both must hold — a working filter does not excuse unsafe
    output, and clean output does not excuse a filter that lets seeds through.
    """

    corpus: CorpusResult
    output_findings: list[OutputFinding]

    @property
    def passed(self) -> bool:
        return self.corpus.passed and not self.output_findings


def screen_corpus(
    corpus: Optional[Mapping[str, Sequence[str]]] = None,
) -> CorpusResult:
    """Screen every adversarial seed; a seed that is not blocked is a leak.

    ``corpus`` defaults to :data:`safety.ADVERSARIAL_SEED_CORPUS`; it is a
    parameter so the gate's own behaviour on a *failing* corpus can be tested. A
    seed counts toward ``by_category`` only when it is blocked under the category
    it was filed under (the contract the safety unit tests pin); a seed that clears
    the filter entirely is a leak and fails the gate.
    """
    source = safety.ADVERSARIAL_SEED_CORPUS if corpus is None else corpus
    total = 0
    blocked = 0
    leaks: list[str] = []
    by_category: dict[str, int] = {}
    for category, seeds in source.items():
        for seed in seeds:
            total += 1
            verdict = safety.screen(seed)
            if verdict.ok:
                leaks.append(seed)
                continue
            blocked += 1
            if category in verdict.categories:
                by_category[category] = by_category.get(category, 0) + 1
    return CorpusResult(total=total, blocked=blocked, leaks=leaks, by_category=by_category)


def screen_output(result: SliceResult) -> list[OutputFinding]:
    """Screen every rendered line of the slice; return any the filter rejects.

    Covers the narration, the half-time ack, the manager's pre-match ``team_talk``,
    and every Chirper post (which already includes the manager's ``fallout_post``).
    The two manager open-text lines come straight from CLI input — they are not
    safety-prefiltered before this gate — yet ``recap.md`` renders ``team_talk``, so
    it must be screened here or an unsafe line could pass the gate while being shown.
    An empty list means nothing the founder would see trips the safety filter.
    """
    findings: list[OutputFinding] = []

    def check(source: str, text: str) -> None:
        verdict = safety.screen(text)
        if not verdict.ok:
            findings.append(OutputFinding(source=source, text=text, categories=list(verdict.categories)))

    check("narration", result.narration.text)
    check("halftime", result.halftime.text)
    check("team_talk", result.decisions.team_talk)
    for post in result.feed:
        check(f"feed:{post.author_handle}", post.text)
    return findings


# --------------------------------------------------------------------------- #
# Latency: measured and recorded.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LatencyReport:
    """The slice's measured latency. The headline is ``total_seconds`` (the whole
    run wall-clock); the per-model-call aggregate shows where that time went.

    ``budget_seconds`` is an *optional* founder ceiling — there is no agreed figure
    yet (the cost ceiling's twin, deferred to when it can fail), so it defaults to
    unset and :attr:`within_budget` is vacuously true. When supplied it becomes a
    live pass/fail on the total.
    """

    total_seconds: float
    model_calls: int
    model_seconds: float
    slowest_call_seconds: float
    mean_call_seconds: float
    budget_seconds: Optional[float] = None

    @property
    def within_budget(self) -> bool:
        return self.budget_seconds is None or self.total_seconds <= self.budget_seconds

    @classmethod
    def measure(
        cls,
        total_seconds: float,
        call_durations: Sequence[float],
        *,
        budget_seconds: Optional[float] = None,
    ) -> "LatencyReport":
        calls = len(call_durations)
        model_seconds = sum(call_durations)
        return cls(
            total_seconds=total_seconds,
            model_calls=calls,
            model_seconds=model_seconds,
            slowest_call_seconds=max(call_durations) if call_durations else 0.0,
            mean_call_seconds=(model_seconds / calls) if calls else 0.0,
            budget_seconds=budget_seconds,
        )


class _TimingClient:
    """Wraps an :class:`~esports_tycoon.content.llm.LLMClient` to time each call.

    Conforms to the same ``structured(...)`` slice the vllm backend depends on, so
    it drops in transparently and records the wall-clock of every model round-trip
    the slice makes — which is how the preflight reports per-call latency without
    the engine knowing it is being measured.
    """

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self.durations: list[float] = []

    def structured(self, prompt, schema, *, system=None, max_tokens=None):
        start = time.perf_counter()
        try:
            return self._delegate.structured(prompt, schema, system=system, max_tokens=max_tokens)
        finally:
            self.durations.append(time.perf_counter() - start)


# --------------------------------------------------------------------------- #
# The preflight result + its content-addressed digest.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PreflightResult:
    """Everything one vLLM-mode preflight produced, and whether the gate may open.

    :attr:`digest` content-addresses the founder-facing output (model + inputs +
    safety verdict + the rendered recap & feed): the written sign-off binds to it,
    so any change to what would be screenshotted invalidates the approval.
    """

    model: str
    config: SliceConfig
    decisions: SliceDecisions
    slice_id: str
    safety: SafetyReport
    latency: LatencyReport
    grounded_ok: int
    grounded_total: int
    recap_md: str
    feed_html: str
    digest: str

    @property
    def gate_ready(self) -> bool:
        """The automated gate: safety holds and the run is within any latency budget.

        The founder's written sign-off is still required on top of this — this only
        answers whether the run is *eligible* to be signed off.
        """
        return self.safety.passed and self.latency.within_budget

    @property
    def grounding_rate(self) -> float:
        return self.grounded_ok / self.grounded_total if self.grounded_total else 1.0

    def evidence(self) -> dict:
        """The compact, serialisable summary the sign-off and ``status`` read back.

        Self-describing and digest-bearing; deliberately excludes the full recap /
        feed bodies (those are written as their own files), keeping the record the
        founder's decision binds to small and reviewable.
        """
        return {
            "kind": "vllm_demo_preflight",
            "model": self.model,
            "slice_id": self.slice_id,
            "digest": self.digest,
            "gate_ready": self.gate_ready,
            "config": {
                "opponent": self.config.opponent,
                "map": self.config.map,
                "seed": self.config.seed,
                "stance": self.config.tactical_stance,
            },
            "decisions": {
                "practice_focus": self.decisions.practice_focus,
                "team_talk": self.decisions.team_talk,
                "fallout_post": self.decisions.fallout_post,
            },
            "safety": {
                "passed": self.safety.passed,
                "corpus_total": self.safety.corpus.total,
                "corpus_blocked": self.safety.corpus.blocked,
                "corpus_leaks": list(self.safety.corpus.leaks),
                "corpus_by_category": dict(self.safety.corpus.by_category),
                "output_findings": [
                    {"source": f.source, "text": f.text, "categories": list(f.categories)}
                    for f in self.safety.output_findings
                ],
            },
            "latency": {
                "total_seconds": self.latency.total_seconds,
                "model_calls": self.latency.model_calls,
                "model_seconds": self.latency.model_seconds,
                "slowest_call_seconds": self.latency.slowest_call_seconds,
                "mean_call_seconds": self.latency.mean_call_seconds,
                "budget_seconds": self.latency.budget_seconds,
                "within_budget": self.latency.within_budget,
            },
            "grounding": {
                "grounded_ok": self.grounded_ok,
                "grounded_total": self.grounded_total,
                "rate": self.grounding_rate,
            },
        }


def _digest_from_fields(
    model: Optional[str],
    config_fields: Mapping[str, object],
    decisions_fields: Mapping[str, object],
    safety_passed: bool,
    recap_md: str,
    feed_html: str,
) -> str:
    """Content-address the founder-facing demo output from its primitive fields.

    Kept separate from :func:`_digest` so the *same* payload can be rebuilt two
    ways: from a live run's typed objects (at preflight time) and from the written
    evidence + on-disk recap/feed (at verify time, see :func:`verify_artifacts`).
    Both must hash identically or the binding would be meaningless.
    """
    payload = json.dumps(
        {
            "model": model,
            "config": dict(config_fields),
            "decisions": dict(decisions_fields),
            "safety_passed": safety_passed,
            "recap_md": recap_md,
            "feed_html": feed_html,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _digest(
    model: str,
    config: SliceConfig,
    decisions: SliceDecisions,
    safety_passed: bool,
    recap_md: str,
    feed_html: str,
) -> str:
    """Content-address the founder-facing demo output.

    Includes the rendered recap and feed verbatim, so two preflights that produced
    *different* prose (vLLM is non-deterministic) get different digests — exactly
    what makes a sign-off bind to the one output the founder reviewed, and go stale
    on the next generation.
    """
    return _digest_from_fields(
        model,
        {
            "opponent": config.opponent,
            "map": config.map,
            "seed": config.seed,
            "stance": config.tactical_stance,
        },
        {
            "practice_focus": decisions.practice_focus,
            "team_talk": decisions.team_talk,
            "fallout_post": decisions.fallout_post,
        },
        safety_passed,
        recap_md,
        feed_html,
    )


def run_preflight(
    world: WorldState,
    config: SliceConfig,
    decisions: SliceDecisions,
    *,
    client: Optional[object] = None,
    latency_budget_seconds: Optional[float] = None,
) -> PreflightResult:
    """Run the whole slice in ``vllm`` mode, then measure, screen, and bundle it.

    ``client`` is the LLM client to talk through; it defaults to the env-configured
    process client (:func:`game_llm.get_llm`), which is the real local-Qwen
    endpoint. Pass a stand-in to exercise the gate without a live server.
    ``latency_budget_seconds`` is the optional total-latency ceiling (unset ⇒ the
    latency is recorded but never fails the gate).
    """
    delegate = client if client is not None else game_llm.get_llm()
    model = getattr(delegate, "model", None) or game_llm._DEFAULTS["GAME_LLM_MODEL"]
    timing = _TimingClient(delegate)

    started = time.perf_counter()
    result = run_slice(
        world,
        config,
        decisions,
        content_config=ContentConfig(backend="vllm"),
        client=timing,
    )
    total_seconds = time.perf_counter() - started

    latency = LatencyReport.measure(total_seconds, timing.durations, budget_seconds=latency_budget_seconds)
    report = SafetyReport(corpus=screen_corpus(), output_findings=screen_output(result))

    recap_md = render_recap_md(result, world)
    feed_html = render_feed_html(result, world)
    digest = _digest(model, config, decisions, report.passed, recap_md, feed_html)

    return PreflightResult(
        model=model,
        config=config,
        decisions=decisions,
        slice_id=result.slice_id,
        safety=report,
        latency=latency,
        grounded_ok=result.grounded_ok,
        grounded_total=result.grounded_total,
        recap_md=recap_md,
        feed_html=feed_html,
        digest=digest,
    )


def write_preflight(
    result: PreflightResult,
    output_dir: Path | str = DEFAULT_ARTIFACTS_DIR,
) -> dict[str, Path]:
    """Write the evidence record + the founder-reviewable recap & feed.

    Returns the three written paths keyed ``preflight`` / ``recap`` / ``feed``. The
    JSON evidence (:meth:`PreflightResult.evidence`) is what the sign-off and
    ``status`` commands read; the ``recap.md`` and ``feed.snapshot.html`` are the
    actual screenshot surface the founder reviews before signing off.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    preflight_path = out / PREFLIGHT_FILENAME
    recap_path = out / RECAP_FILENAME
    feed_path = out / FEED_FILENAME
    preflight_path.write_text(
        json.dumps(result.evidence(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    recap_path.write_text(result.recap_md, encoding="utf-8", newline="\n")
    feed_path.write_text(result.feed_html, encoding="utf-8", newline="\n")
    return {"preflight": preflight_path, "recap": recap_path, "feed": feed_path}


def load_evidence(
    output_dir: Path | str = DEFAULT_ARTIFACTS_DIR,
) -> Optional[dict]:
    """Load the written preflight evidence, or ``None`` if no preflight has run.

    A vLLM preflight cannot be *re-derived* on demand the way the cast-lock batch
    can (its output is non-deterministic and needs the live endpoint), so the one
    run the founder reviewed is persisted and read back here — this is the evidence
    the sign-off binds to.
    """
    path = Path(output_dir) / PREFLIGHT_FILENAME
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def verify_artifacts(
    evidence: Mapping[str, object],
    output_dir: Path | str = DEFAULT_ARTIFACTS_DIR,
) -> bool:
    """Re-derive the digest from the on-disk recap/feed and confirm it still matches.

    The founder's sign-off binds to ``evidence["digest"]`` (recorded in
    ``preflight.json``), but the thing actually screenshotted is the ``recap.md`` /
    ``feed.snapshot.html`` *files*. This re-hashes those files together with the
    evidence's own model/config/decisions/safety fields and checks the result
    equals the recorded digest — so a file edited or regenerated out-of-band after
    the preflight (i.e. not the byte-exact output the founder approved) cannot ride
    a stale approval. ``False`` if either file is missing or anything differs.
    """
    expected = evidence.get("digest")
    if not expected:
        return False
    out = Path(output_dir)
    recap_path = out / RECAP_FILENAME
    feed_path = out / FEED_FILENAME
    if not recap_path.exists() or not feed_path.exists():
        return False

    config = evidence.get("config") or {}
    decisions = evidence.get("decisions") or {}
    safety = evidence.get("safety") or {}
    redigest = _digest_from_fields(
        evidence.get("model"),  # type: ignore[arg-type]
        {
            "opponent": config.get("opponent"),
            "map": config.get("map"),
            "seed": config.get("seed"),
            "stance": config.get("stance"),
        },
        {
            "practice_focus": decisions.get("practice_focus"),
            "team_talk": decisions.get("team_talk"),
            "fallout_post": decisions.get("fallout_post"),
        },
        bool(safety.get("passed")),
        recap_path.read_text(encoding="utf-8"),
        feed_path.read_text(encoding="utf-8"),
    )
    return redigest == expected
