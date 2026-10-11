"""Refresh the vendored frontend modules under web/static/vendor/.

The UI imports preact and htm as ES modules. Fetching them from a CDN at page
load makes an outside host a hard runtime dependency (see vendor/README.md), so
the builds live in the repo and this script is how they get updated.

Usage:
    python scripts/vendor_frontend_deps.py            # re-download the pins
    python scripts/vendor_frontend_deps.py --check    # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "src/esports_sim/web/static/vendor"

# (package, version, path inside the tarball, destination filename)
PINS: tuple[tuple[str, str, str, str], ...] = (
    ("preact", "10.19.2", "package/dist/preact.mjs", "preact.mjs"),
    ("preact", "10.19.2", "package/hooks/dist/hooks.mjs", "preact-hooks.mjs"),
    ("htm", "3.1.1", "package/dist/htm.mjs", "htm.mjs"),
)

# hooks.mjs ships `import{options as n}from"preact"` — a bare specifier no
# browser resolves without an import map. Point it at its sibling instead.
REWRITES: dict[str, tuple[tuple[str, str], ...]] = {
    "preact-hooks.mjs": (('from"preact"', 'from"./preact.mjs"'),),
}


def _fetch(package: str, version: str, member: str) -> str:
    url = f"https://registry.npmjs.org/{package}/-/{package}-{version}.tgz"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        raw = response.read()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        extracted = tar.extractfile(member)
        if extracted is None:
            raise SystemExit(f"{member} missing from {package}@{version}")
        text = extracted.read().decode("utf-8")
    for old, new in REWRITES.get(member.rsplit("/", 1)[-1], ()):
        text = text.replace(old, new)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="compare against what is on disk instead of writing (exit 1 on drift)",
    )
    args = parser.parse_args()

    VENDOR.mkdir(parents=True, exist_ok=True)
    drift: list[str] = []
    for package, version, member, dest in PINS:
        text = _fetch(package, version, member)
        for old, new in REWRITES.get(dest, ()):
            text = text.replace(old, new)
        target = VENDOR / dest
        if args.check:
            on_disk = target.read_text(encoding="utf-8") if target.exists() else ""
            if on_disk != text:
                drift.append(dest)
            continue
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {target.relative_to(VENDOR.parents[4])} ({len(text)} bytes)")

    if drift:
        print("FAIL vendored modules drifted from their pins: " + ", ".join(drift))
        return 1
    if args.check:
        print("OK vendored modules match their pins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
