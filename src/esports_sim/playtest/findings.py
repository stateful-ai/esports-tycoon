"""The findings ledger — what a synthetic player is actually for.

A playtest that ends in prose is a playtest nobody acts on. Findings are
append-only JSONL with a fixed vocabulary so that runs from different personas
(and different days) aggregate into one prioritised list instead of a pile of
opinions. The rules that make that work:

* **Severity is about the player, not the code.** ``blocker`` means the run
  could not continue; ``confusing`` outranks ``cosmetic`` because a system
  nobody understands is a system nobody uses.
* **Every finding names where it happened** (``area`` + ``screen``) and, when
  the harness took one, the screenshot that shows it. A finding you cannot
  navigate back to is a finding you cannot fix.
* **Nothing is ever rewritten.** Two personas hitting the same wall is the
  strongest signal in the file; deduping at write time would destroy it, so
  ``aggregate`` groups on read instead.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Ordered worst-first: `aggregate` sorts on this, so the order *is* the triage
# policy. "confusing" sits above "cosmetic" deliberately.
SEVERITIES: tuple[str, ...] = ("blocker", "bug", "confusing", "balance", "cosmetic", "praise")

AREAS: tuple[str, ...] = (
    "onboarding",
    "dashboard",
    "inbox",
    "match",
    "club",
    "facilities",
    "season",
    "market",
    "stats",
    "company",
    "viewer",
    "performance",
    "other",
)

_SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITIES)}


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing a synthetic player noticed, in a form a maintainer can act on."""

    severity: str
    area: str
    title: str
    detail: str
    persona: str = "unknown"
    screen: str = ""
    screenshot: str = ""
    repro: str = ""
    week: int = 0
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.severity not in _SEVERITY_RANK:
            raise ValueError(
                f"unknown severity {self.severity!r}; expected one of {', '.join(SEVERITIES)}"
            )
        if self.area not in AREAS:
            raise ValueError(f"unknown area {self.area!r}; expected one of {', '.join(AREAS)}")
        if not self.title.strip():
            raise ValueError("finding title must not be empty")
        if not self.detail.strip():
            raise ValueError("finding detail must not be empty")

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self.severity]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001 - dataclass API
        payload = {k: v for k, v in data.items() if k in known}
        payload["tags"] = tuple(payload.get("tags") or ())
        return cls(**payload)


def append_finding(path: Path | str, finding: Finding) -> Path:
    """Append one finding to the ledger at *path*, creating it if needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(finding.to_dict(), sort_keys=True, ensure_ascii=True) + "\n")
    return target


def load_findings(path: Path | str) -> list[Finding]:
    """Load a ledger. Missing file -> empty list; a bad line raises with its number."""
    target = Path(path)
    if not target.exists():
        return []
    findings: list[Finding] = []
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            findings.append(Finding.from_dict(json.loads(line)))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{target}:{number}: bad finding — {exc}") from exc
    return findings


def load_all(root: Path | str, pattern: str = "**/findings.jsonl") -> list[Finding]:
    """Load every ledger under *root* — one run per persona, merged."""
    base = Path(root)
    if not base.exists():
        return []
    findings: list[Finding] = []
    for path in sorted(base.glob(pattern)):
        findings.extend(load_findings(path))
    return findings


def _group_key(finding: Finding) -> tuple[str, str, str]:
    return (finding.severity, finding.area, " ".join(finding.title.lower().split()))


def aggregate(findings: Iterable[Finding]) -> list[dict[str, Any]]:
    """Group findings by (severity, area, title), worst-first.

    Corroboration is the point: a group's ``personas`` list is how a reader
    tells "one player's taste" from "everybody hit this". Ties inside a
    severity break on that count, then on area/title so the output is stable.
    """
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        key = _group_key(finding)
        group = groups.setdefault(
            key,
            {
                "severity": finding.severity,
                "area": finding.area,
                "title": finding.title,
                "count": 0,
                "personas": [],
                "details": [],
                "screenshots": [],
                "repros": [],
            },
        )
        group["count"] += 1
        if finding.persona not in group["personas"]:
            group["personas"].append(finding.persona)
        if finding.detail not in group["details"]:
            group["details"].append(finding.detail)
        if finding.screenshot and finding.screenshot not in group["screenshots"]:
            group["screenshots"].append(finding.screenshot)
        if finding.repro and finding.repro not in group["repros"]:
            group["repros"].append(finding.repro)

    ordered = sorted(
        groups.values(),
        key=lambda g: (_SEVERITY_RANK[g["severity"]], -g["count"], g["area"], g["title"].lower()),
    )
    for group in ordered:
        group["personas"].sort()
    return ordered


def render_report(findings: Iterable[Finding], *, title: str = "Synthetic playtest report") -> str:
    """Render the aggregated ledger as Markdown, worst-first."""
    findings = list(findings)
    groups = aggregate(findings)
    personas = sorted({f.persona for f in findings})

    lines = [f"# {title}", ""]
    if not groups:
        lines.append("No findings recorded.")
        return "\n".join(lines) + "\n"

    counts = {severity: 0 for severity in SEVERITIES}
    for group in groups:
        counts[group["severity"]] += group["count"]
    summary = ", ".join(f"{counts[s]} {s}" for s in SEVERITIES if counts[s])
    lines.append(
        f"{len(findings)} findings ({summary}) across {len(groups)} distinct issues "
        f"from {len(personas)} personas: {', '.join(personas) or 'none'}."
    )
    lines.append("")

    current = ""
    for group in groups:
        if group["severity"] != current:
            current = group["severity"]
            lines.append(f"## {current.upper()}")
            lines.append("")
        corroboration = (
            f" — reported {group['count']}x by {', '.join(group['personas'])}"
            if group["count"] > 1
            else f" — {group['personas'][0] if group['personas'] else 'unknown'}"
        )
        lines.append(f"### [{group['area']}] {group['title']}{corroboration}")
        for detail in group["details"]:
            lines.append(f"- {detail}")
        for repro in group["repros"]:
            lines.append(f"- _Repro:_ {repro}")
        for shot in group["screenshots"][:3]:
            lines.append(f"- _Screenshot:_ `{shot}`")
        lines.append("")
    return "\n".join(lines) + "\n"
