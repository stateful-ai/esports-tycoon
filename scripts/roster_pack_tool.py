"""Agent-friendly CLI for portable Roster Studio documents.

Examples:
  python scripts/roster_pack_tool.py schema schema.json
  python scripts/roster_pack_tool.py new my-pack.roster.yaml
  python scripts/roster_pack_tool.py validate my-pack.roster.yaml
  python scripts/roster_pack_tool.py install my-pack.roster.yaml
  python scripts/roster_pack_tool.py export vct-2026 vct-2026.roster.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from esports_sim.registry.roster_workbench import (  # noqa: E402
    dump_document,
    example_document,
    install_document,
    load_document,
    parse_document,
    schema_bundle,
    validate_document,
)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="ascii")
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build portable esports-sim roster packs"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    schema = sub.add_parser("schema", help="write the AI/tool JSON Schema bundle")
    schema.add_argument("output", nargs="?", type=Path)
    new = sub.add_parser("new", help="write a valid starter roster document")
    new.add_argument("output", type=Path)
    validate = sub.add_parser("validate", help="validate a roster document")
    validate.add_argument("input", type=Path)
    install = sub.add_parser(
        "install", help="validate, compile, and install a roster document"
    )
    install.add_argument("input", type=Path)
    export = sub.add_parser(
        "export", help="export an installed pack as one portable document"
    )
    export.add_argument("pack_id")
    export.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.command == "schema":
        text = json.dumps(schema_bundle(), indent=2) + "\n"
        if args.output:
            _write(args.output, text)
        else:
            print(text, end="")
        return 0
    if args.command == "new":
        _write(args.output, dump_document(example_document()))
        return 0
    if args.command == "export":
        _write(args.output, dump_document(load_document(args.pack_id)))
        return 0

    raw = parse_document(args.input.read_text(encoding="utf-8"))
    if args.command == "validate":
        result = validate_document(raw)
        print(json.dumps(result, indent=2))
        return 0 if result["valid"] else 1
    result = install_document(raw)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
