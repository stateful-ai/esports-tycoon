"""Compare human-transcribed browser screenshots with collected CSV facts.

The observations file is independently transcribed from the rendered pages,
never generated from collector output. This check does not call the parser.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def equivalent(expected, actual):
    if expected is None:
        return actual == ""
    try:
        return Decimal(str(expected)) == Decimal(actual)
    except InvalidOperation:
        return str(expected) == actual


def check(data):
    audit = data / "manual_audit"
    spec = json.loads((audit / "observations.json").read_text())
    names = sorted({o['table'] for p in spec['pages'] for o in p['observations']})
    tables = {name: rows(data / name) for name in names}
    checks = []
    for page in spec["pages"]:
        screenshot = audit / page["screenshot"]
        digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        for observation in page["observations"]:
            candidates = [r for r in tables[observation["table"]]
                          if all(r[k] == str(v) for k, v in observation["key"].items())]
            for field, expected in observation["fields"].items():
                actual = candidates[0].get(field, "<missing field>") if len(candidates) == 1 else f"<rows={len(candidates)}>"
                checks.append({"page": page["label"], "source_url": page["url"],
                               "screenshot": page["screenshot"], "screenshot_sha256": digest,
                               "table": observation["table"], "key": json.dumps(observation["key"], sort_keys=True),
                               "field": field, "expected": "" if expected is None else expected,
                               "actual": actual, "passed": len(candidates) == 1 and equivalent(expected, actual)})
    with (audit / "checks.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(checks[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(checks)
    receipt = {"method": spec["method"], "reviewed_at_utc": spec["reviewed_at_utc"],
               "observations_sha256": hashlib.sha256((audit / "observations.json").read_bytes()).hexdigest(),
               "checked_csv_sha256": {name: hashlib.sha256((data / name).read_bytes()).hexdigest() for name in tables},
               "pages": len({p["url"] for p in spec["pages"]}), "screenshots": len(spec["pages"]), "field_checks": len(checks),
               "passed": sum(r["passed"] for r in checks), "failed": sum(not r["passed"] for r in checks),
               "scope": spec.get('scope', "Purposive sample: tier 1, tier 2, overtime, event totals, missing stats/lineups, and free-agent profile identity/current versus past listings; not a statistical accuracy estimate.")}
    (audit / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    if receipt["failed"]:
        raise SystemExit("Browser audit mismatch; see manual_audit/checks.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/research/vct-2026")
    check(parser.parse_args().data)
