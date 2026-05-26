"""The structured-output adherence spike: can a local 7B/8B model hold the contract?

Before the vLLM content backend (:mod:`esports_tycoon.content.llm`) can be trusted
in a demo, one question has to be answered empirically: does a candidate local
model reliably return **schema-valid JSON for the adapter contract** — the
``{text, cites}`` :class:`~esports_tycoon.content.llm._LLMReply` shape, produced
*under the per-kind token cap* — often enough to ship? This module answers it.

It is a **spike that runs parallel to the spine**: it imports the resolver and the
content backend read-only, never mutates ``world``, and is never on the game's
default (templated, zero-API) path — importing it is a deliberate act, exactly
like the vLLM backend it qualifies. The whole job is measurement → a verdict.

The discipline that makes the verdict meaningful is that the sampled prompts are
the **exact prompts the game would send**: the corpus is built by calling the real
:func:`esports_tycoon.content.llm._build_request` for each kind against the canned
world, asking for the real :class:`~esports_tycoon.content.llm._LLMReply` schema
under the real :data:`~esports_tycoon.content.llm.MAX_TOKENS` cap. Reaching into
those module-privates is intentional (it mirrors how :mod:`smoke` reaches into
``game_llm._DEFAULTS``): a spike that re-derived the prompts would be testing a
*copy* of the contract that could silently drift from what the adapter actually
asks for, which would defeat its purpose.

The candidate model is reached through the **game's own client path**
(:meth:`game_llm.GameLLM.structured` — prompted JSON validated into a pydantic
model, with its repair retry), so a green spike means the model adheres on the
*same* path the slice will use, not on some idealised one. The client is injected
(``client=`` / the env-configured :func:`game_llm.get_llm` default), so the CLI
runs it against a live local endpoint while the tests exercise every branch with a
duck-typed stand-in and no network.

The output is the deliverable the task names: a **chosen model + settings** —
:attr:`AdherenceReport.chosen` — populated only when the candidate cleared the
``≥9/10`` bar, recording the model and the temperature / retry / token-cap /
decode settings it cleared it under.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from esports_tycoon import resolver
from esports_tycoon.content import game_llm, llm
from esports_tycoon.content.context import GenerationContext
from esports_tycoon.cost import estimate_tokens
from esports_tycoon.schema import Decisions, TacticalStance, WorldState

__all__ = [
    "DEFAULT_THRESHOLD",
    "MIN_SAMPLES",
    "DEFAULT_ARTIFACTS_DIR",
    "REPORT_FILENAME",
    "SamplePrompt",
    "SampleResult",
    "RunSettings",
    "AdherenceReport",
    "build_sample_prompts",
    "run_adherence_spike",
    "write_report",
]

#: Where the spike's evidence lands when written. Kept under ``artifacts/`` (the
#: same neighbourhood as the vLLM-demo bundle), not ``runs/`` (which is the
#: byte-deterministic templated output) — a spike run is non-deterministic.
DEFAULT_ARTIFACTS_DIR = Path("artifacts") / "model_spike"

#: The evidence file :func:`write_report` writes.
REPORT_FILENAME = "adherence.json"

#: The acceptance bar, as a fraction: a candidate must return schema-valid JSON on
#: at least this share of the sampled prompts. ``0.9`` is the task's "≥9/10".
DEFAULT_THRESHOLD = 0.9

#: The minimum sample size the spike will draw a *pass* from. The built corpus is
#: exactly this many (see :func:`build_sample_prompts`); a smaller custom sample
#: can still be run, but it can never pass — ``9/10`` is not a verdict you can
#: reach from three prompts.
MIN_SAMPLES = 10


# --------------------------------------------------------------------------- #
# The sampled-prompt corpus: the real adapter contract, exercised broadly.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SamplePrompt:
    """One sampled prompt, carrying exactly what the adapter would send the model.

    ``system`` / ``user`` come straight from
    :func:`esports_tycoon.content.llm._build_request`, and ``max_tokens`` from
    :data:`~esports_tycoon.content.llm.MAX_TOKENS` — so running this sample puts the
    candidate model under the identical contract the game's vLLM backend imposes.
    ``name`` is a stable, human label for the report; ``kind`` is the content kind.
    """

    name: str
    kind: str
    system: str
    user: str
    max_tokens: int


@dataclass(frozen=True)
class _SampleSpec:
    """A recipe for one sample — the inputs that build its ``GenerationContext``.

    Deliberately small and declarative so the corpus reads as a table: which kind,
    against which fixture (opponent/map/stance/seed → the resolved ``WhyRecord``),
    in whose voice, and (for half-time) at what scoreline and second-half stance.
    """

    name: str
    kind: str
    opponent: str = "apex_foundry"
    map: str = "Helix"
    stance: TacticalStance = "default"
    seed: int = 6
    author: Optional[str] = None
    halftime_scoreline: Optional[tuple[int, int]] = None
    second_half_stance: Optional[TacticalStance] = None


#: The sampled corpus, fixed and ordered so the spike is reproducible. Ten prompts
#: spanning all three content kinds, every per-kind token cap (narration 320,
#: chirper 80, half-time 200), both outcomes (win and loss), and all five player
#: personas — so adherence is measured across the breadth the real game spans, not
#: one easy shape.
_SAMPLE_SPECS: tuple[_SampleSpec, ...] = (
    _SampleSpec("narration_apex_default", "narration", opponent="apex_foundry", stance="default", seed=6),
    _SampleSpec("narration_northwind_aggressive", "narration", opponent="northwind", stance="aggressive", seed=11),
    _SampleSpec("chirper_rook_apex", "chirper_post", author="rook", opponent="apex_foundry", seed=6),
    _SampleSpec("chirper_vex_apex", "chirper_post", author="vex", opponent="apex_foundry", seed=6),
    _SampleSpec("chirper_sable_northwind", "chirper_post", author="sable", opponent="northwind", seed=11),
    _SampleSpec("chirper_pixie_apex", "chirper_post", author="pixie", opponent="apex_foundry", seed=6),
    _SampleSpec("chirper_coyote_northwind", "chirper_post", author="coyote", opponent="northwind", seed=11),
    _SampleSpec("halftime_down_aggressive", "halftime_ack", halftime_scoreline=(4, 8), second_half_stance="aggressive"),
    _SampleSpec("halftime_up_disciplined", "halftime_ack", halftime_scoreline=(8, 4), second_half_stance="disciplined"),
    _SampleSpec("halftime_even_default", "halftime_ack", halftime_scoreline=(6, 6), second_half_stance="default"),
)


def _context_for(world: WorldState, spec: _SampleSpec) -> GenerationContext:
    """Build the typed context one spec needs, resolving a match where the kind wants one."""
    if spec.kind == "halftime_ack":
        # Half-time needs no resolved match — only the scoreline and the stance.
        return GenerationContext(
            world=world,
            halftime_scoreline=spec.halftime_scoreline,
            second_half_stance=spec.second_half_stance,
        )
    decisions = Decisions(opponent=spec.opponent, map=spec.map, tactical_stance=spec.stance)
    why = resolver.run(world, decisions, spec.seed)
    return GenerationContext(world=world, why=why, decisions=decisions, author=spec.author)


def build_sample_prompts(world: WorldState) -> list[SamplePrompt]:
    """The fixed corpus of sampled prompts, each rendered through the real contract.

    For every spec, this builds the context the kind needs and asks the *production*
    :func:`esports_tycoon.content.llm._build_request` for the exact ``(system, user)``
    the adapter would send, pairing it with the kind's real
    :data:`~esports_tycoon.content.llm.MAX_TOKENS` cap. The result is deterministic
    (the resolver is pure given its seed), so two spike runs sample identical prompts.
    """
    prompts: list[SamplePrompt] = []
    for spec in _SAMPLE_SPECS:
        ctx = _context_for(world, spec)
        # _build_request / MAX_TOKENS are the production contract, used verbatim so
        # the spike measures what the game sends, not a re-derived copy of it.
        system, user = llm._build_request(spec.kind, ctx)
        prompts.append(
            SamplePrompt(
                name=spec.name,
                kind=spec.kind,
                system=system,
                user=user,
                max_tokens=llm.MAX_TOKENS[spec.kind],
            )
        )
    return prompts


# --------------------------------------------------------------------------- #
# The run: settings under test, per-sample verdicts, the aggregate report.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RunSettings:
    """The model + decode settings the candidate was sampled under.

    This *is* the recommendation's second half: a chosen model is only meaningful
    alongside the settings it cleared the bar under. ``decode`` names the strategy
    the game's client uses (prompted JSON + repair retry, which works on any
    OpenAI-compatible endpoint), and ``token_caps`` is the per-kind output budget
    the contract enforces.
    """

    model: str
    temperature: Optional[float]
    max_retries: Optional[int]
    decode: str
    token_caps: dict[str, int]

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_retries": self.max_retries,
            "decode": self.decode,
            "token_caps": dict(self.token_caps),
        }


@dataclass(frozen=True)
class SampleResult:
    """The verdict of running one sampled prompt against the candidate model.

    ``ok`` means the call returned a schema-valid :class:`_LLMReply` under the cap.
    ``error`` names the failure when it did not (a parse miss after the client's
    repair retries, or a transport error) so a red sample is actionable rather than
    just a tally. ``tokens_out`` is the estimated size of the model's completion
    (its prose + offered cites), priced exactly as the backend prices it, so the
    report shows how much headroom under the cap the valid replies used.
    """

    name: str
    kind: str
    max_tokens: int
    ok: bool
    latency_seconds: float
    tokens_out: int
    error: Optional[str]


@dataclass(frozen=True)
class AdherenceReport:
    """Everything one adherence spike produced, and whether the candidate passes.

    :attr:`passed` is the gate: a full-size sample with at least
    ``ceil(threshold × total)`` schema-valid replies and no top-level failure.
    :attr:`chosen` is the deliverable — the model + settings to adopt — populated
    only when the candidate passed.
    """

    settings: RunSettings
    threshold: float
    results: list[SampleResult]
    error: Optional[str] = None

    @property
    def model(self) -> str:
        return self.settings.model

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def valid(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def required(self) -> int:
        """The minimum valid count needed to pass at this threshold and sample size."""
        return math.ceil(self.threshold * self.total)

    @property
    def pass_rate(self) -> float:
        return self.valid / self.total if self.total else 0.0

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.total >= MIN_SAMPLES
            and self.valid >= self.required
        )

    @property
    def chosen(self) -> Optional[dict]:
        """The chosen model + settings, or ``None`` if the candidate did not pass."""
        if not self.passed:
            return None
        return {"model": self.settings.model, "settings": self.settings.as_dict()}

    def evidence(self) -> dict:
        """A compact, JSON-serialisable summary — the record the CLI writes/prints."""
        return {
            "kind": "model_adherence_spike",
            "passed": self.passed,
            "threshold": self.threshold,
            "valid": self.valid,
            "total": self.total,
            "required": self.required,
            "min_samples": MIN_SAMPLES,
            "pass_rate": self.pass_rate,
            "chosen": self.chosen,
            "settings": self.settings.as_dict(),
            "error": self.error,
            "samples": [
                {
                    "name": r.name,
                    "kind": r.kind,
                    "max_tokens": r.max_tokens,
                    "ok": r.ok,
                    "tokens_out": r.tokens_out,
                    "latency_seconds": r.latency_seconds,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def _settings_from_client(client: object) -> RunSettings:
    """Read the candidate's model + decode settings off the client (defensively)."""
    return RunSettings(
        model=getattr(client, "model", None) or game_llm._DEFAULTS["GAME_LLM_MODEL"],
        temperature=getattr(client, "temperature", None),
        max_retries=getattr(client, "_max_retries", None),
        decode="prompted-json",
        token_caps=dict(llm.MAX_TOKENS),
    )


def run_adherence_spike(
    world: WorldState,
    *,
    client: Optional[object] = None,
    threshold: float = DEFAULT_THRESHOLD,
    samples: Optional[Sequence[SamplePrompt]] = None,
) -> AdherenceReport:
    """Sample the candidate model against the adapter contract and report a verdict.

    ``client`` defaults to the env-configured process client
    (:func:`game_llm.get_llm`) — the real local endpoint; pass a stand-in to run
    the spike without a live server. ``samples`` defaults to the fixed corpus
    (:func:`build_sample_prompts`). ``threshold`` is the pass fraction (``0.9`` ⇒
    "≥9/10").

    Each sample is run through the game's own structured-output path under the
    kind's token cap; a returned schema-valid :class:`_LLMReply` counts as adhering,
    anything else (a parse miss after the client's repair retry, or a transport
    error) is recorded against the sample with its error. The spike never raises:
    a client that cannot even be constructed (e.g. the ``vllm`` extra not
    installed) is reported as a top-level :attr:`AdherenceReport.error` with no
    samples run, so a caller/CLI can branch on the result.
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0, 1], got {threshold!r}")

    prompts = list(samples) if samples is not None else build_sample_prompts(world)

    # Resolve the client before sampling so a construction failure (missing extra,
    # bad env) is reported once, not once per prompt.
    try:
        delegate = client if client is not None else game_llm.get_llm()
    except Exception as exc:  # noqa: BLE001 — dep/env failure is the verdict, not a crash
        settings = RunSettings(
            model=game_llm._DEFAULTS["GAME_LLM_MODEL"],
            temperature=None,
            max_retries=None,
            decode="prompted-json",
            token_caps=dict(llm.MAX_TOKENS),
        )
        return AdherenceReport(
            settings=settings,
            threshold=threshold,
            results=[],
            error=f"{type(exc).__name__}: {exc}",
        )

    settings = _settings_from_client(delegate)

    results: list[SampleResult] = []
    for prompt in prompts:
        start = time.perf_counter()
        try:
            reply = delegate.structured(
                prompt.user, llm._LLMReply, system=prompt.system, max_tokens=prompt.max_tokens
            )
        except Exception as exc:  # noqa: BLE001 — a failed call is a non-adhering sample
            results.append(
                SampleResult(
                    name=prompt.name,
                    kind=prompt.kind,
                    max_tokens=prompt.max_tokens,
                    ok=False,
                    latency_seconds=time.perf_counter() - start,
                    tokens_out=0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        latency = time.perf_counter() - start
        ok = isinstance(reply, llm._LLMReply)
        results.append(
            SampleResult(
                name=prompt.name,
                kind=prompt.kind,
                max_tokens=prompt.max_tokens,
                ok=ok,
                latency_seconds=latency,
                # Price the completion the way the backend does, so the headroom
                # the report shows matches what the game would record.
                tokens_out=estimate_tokens(llm._completion_text(reply)) if ok else 0,
                error=None if ok else f"returned {type(reply).__name__}, not _LLMReply",
            )
        )

    return AdherenceReport(settings=settings, threshold=threshold, results=results)


def write_report(
    report: AdherenceReport,
    output_dir: Path | str = DEFAULT_ARTIFACTS_DIR,
) -> Path:
    """Write the spike's evidence (:meth:`AdherenceReport.evidence`) as JSON.

    Returns the written path. This is the durable form of the deliverable: the
    chosen model + settings plus the per-sample verdicts that justify it, so a
    later reader (or the founder) can see *why* a model was chosen, not just which.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / REPORT_FILENAME
    path.write_text(
        json.dumps(report.evidence(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
