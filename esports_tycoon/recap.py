"""Per-slice grounding / safety / cost metrics, written into ``recap.md``.

Every slice run auto-emits a markdown recap (``scope-m0.md``: "Auto-emit a
markdown recap ... every slice run. Always on"). This module owns the part of
that recap the render-time gate produces: the **grounding-rate** and
**drop-rate** the grounding ticket requires be logged, plus the safety and cost
lines from the same gate.

A :class:`SliceReport` is the accumulator the slice runner feeds one
:class:`~esports_tycoon.gate.GateResult` at a time as it generates; the cost meter
is shared with the gate, so the report reads the authoritative per-slice spend
straight off it. :func:`render_markdown` turns the report into the recap section,
and :func:`write_recap` writes a standalone ``recap.md`` (the M0.3 slice runner
embeds the same section into the full recap).

The drop-rate carries the model/prompt-health signal the plan calls out
(``m0_plan_v2.md``: ">20% drop rate is a model/prompt smell"): the rendered recap
flags it when it crosses that threshold.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from esports_tycoon.cost import CostMeter
from esports_tycoon.gate import GateResult

__all__ = [
    "DROP_RATE_SMELL_THRESHOLD",
    "SliceReport",
    "render_markdown",
    "write_recap",
]

#: Cite drop-rate above which the recap flags a model/prompt-health smell.
DROP_RATE_SMELL_THRESHOLD = 0.20


@dataclass
class SliceReport:
    """Running per-slice aggregate of the render-time gate's bookkeeping."""

    pieces: int = 0
    status_counts: Counter = field(default_factory=Counter)  # ok / regen / dropped
    blocked: int = 0  # completions withheld by the safety post-filter
    safety_categories: Counter = field(default_factory=Counter)
    cites_offered: int = 0
    cites_resolved: int = 0
    cites_dropped: int = 0

    def add(self, result: GateResult) -> None:
        """Fold one gate result into the running totals."""
        self.pieces += 1
        self.status_counts[result.grounding.status] += 1
        self.cites_offered += result.grounding.offered
        self.cites_resolved += result.grounding.resolved
        self.cites_dropped += result.grounding.dropped
        if result.blocked:
            self.blocked += 1
        for category in result.safety.categories:
            self.safety_categories[category] += 1

    @property
    def grounding_rate(self) -> float:
        """Fraction of offered cites that resolved (vacuously 1.0 if none offered)."""
        if self.cites_offered == 0:
            return 1.0
        return self.cites_resolved / self.cites_offered

    @property
    def drop_rate(self) -> float:
        """Fraction of offered cites that were dropped (0.0 if none offered)."""
        if self.cites_offered == 0:
            return 0.0
        return self.cites_dropped / self.cites_offered


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(
    report: SliceReport,
    *,
    meter: Optional[CostMeter] = None,
    halted: bool = False,
) -> str:
    """Render the gate's per-slice metrics as a markdown section.

    ``meter`` (the slice's :class:`~esports_tycoon.cost.CostMeter`) supplies the
    cost line; omit it to skip cost. ``halted`` marks a run stopped early by the
    cost ceiling.
    """
    status = report.status_counts
    lines: list[str] = []
    lines.append("## Grounding")
    lines.append("")
    lines.append(f"- grounding-rate: {_pct(report.grounding_rate)} "
                 f"({report.cites_resolved}/{report.cites_offered} cites resolved)")
    drop_line = (f"- drop-rate: {_pct(report.drop_rate)} "
                 f"({report.cites_dropped}/{report.cites_offered} cites dropped)")
    if report.drop_rate > DROP_RATE_SMELL_THRESHOLD:
        drop_line += f" — ⚠ above the {_pct(DROP_RATE_SMELL_THRESHOLD)} model/prompt-smell threshold"
    lines.append(drop_line)
    lines.append(f"- pieces: {report.pieces} "
                 f"(ok {status['ok']}, regen {status['regen']}, dropped {status['dropped']})")
    lines.append("")

    lines.append("## Safety")
    lines.append("")
    lines.append(f"- pieces screened: {report.pieces}")
    lines.append(f"- withheld (post-filter): {report.blocked}")
    if report.safety_categories:
        breakdown = ", ".join(
            f"{category} {count}" for category, count in sorted(report.safety_categories.items())
        )
        lines.append(f"- blocked categories: {breakdown}")
    lines.append("")

    if meter is not None:
        lines.append("## Cost")
        lines.append("")
        ceiling = "none" if meter.ceiling_usd is None else f"${meter.ceiling_usd:.4f}"
        lines.append(f"- spend: ${meter.spent_usd:.4f} / ceiling {ceiling}")
        lines.append(f"- tokens: {meter.tokens_in} in, {meter.tokens_out} out "
                     f"({meter.calls} metered call(s))")
        if halted:
            lines.append("- ⚠ run HALTED: per-slice cost ceiling exceeded")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_recap(
    path: Union[str, Path],
    report: SliceReport,
    *,
    meter: Optional[CostMeter] = None,
    halted: bool = False,
    title: str = "Slice recap",
) -> Path:
    """Write a standalone ``recap.md`` with the gate's per-slice metrics.

    Returns the path written. The M0.3 slice runner embeds
    :func:`render_markdown` into the full recap instead; this standalone writer is
    what makes "grounding-rate + drop-rate written into recap.md" true today.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = f"# {title}\n\n" + render_markdown(report, meter=meter, halted=halted)
    target.write_text(body, encoding="utf-8")
    return target
