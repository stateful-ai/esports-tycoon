"""Extract saved Valorant statistics pages into a deterministic research dataset.

The roster-pack builder consumes curated qualitative player sheets.  This tool
is the preceding research step: it preserves event/season observations, source
URLs, file hashes, and parsing warnings without claiming that a scraped rate is
already a gameplay attribute.

It supports the saved 2021 VLR ``/stats`` page and Liquipedia event-stat pages
in the user's download archive.  It uses only the standard library so it can
run in a clean project environment:

    python scripts/extract_historical_stats.py C:\\Users\\me\\Downloads\\rosters out.json
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


PARSER_VERSION = 1


@dataclass
class Cell:
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)
    class_text: dict[str, list[str]] = field(default_factory=dict)

    def value(self) -> str:
        return " ".join("".join(self.text).split())


@dataclass
class Table:
    attrs: dict[str, str]
    rows: list[list[Cell]] = field(default_factory=list)


class TableParser(HTMLParser):
    """Small, deliberately lossless table reader for saved HTML snapshots."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._stack: list[Table] = []
        self._row: list[Cell] | None = None
        self._cell: Cell | None = None
        self._anchor: dict[str, Any] | None = None
        self._element_stack: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "table":
            table = Table(values)
            self.tables.append(table)
            self._stack.append(table)
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = Cell(values)
            self._element_stack = []
        elif tag == "a" and self._cell is not None:
            self._anchor = {**values, "text": []}
            self._cell.links.append(self._anchor)
        elif tag == "img" and self._cell is not None:
            self._cell.images.append(values)
        elif self._cell is not None:
            classes = values.get("class", "").split()
            self._element_stack.append((tag, classes))
            for class_name in classes:
                self._cell.class_text.setdefault(class_name, [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._anchor = None
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
            self._element_stack = []
        elif self._cell is not None:
            for i in range(len(self._element_stack) - 1, -1, -1):
                if self._element_stack[i][0] == tag:
                    self._element_stack.pop(i)
                    break
        elif tag == "tr" and self._row is not None and self._stack:
            self._stack[-1].rows.append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.text.append(data)
            for _, classes in self._element_stack:
                for class_name in classes:
                    self._cell.class_text[class_name].append(data)
        if self._anchor is not None:
            self._anchor["text"].append(data)


def _number(value: str) -> float | int | None:
    value = value.strip().replace(",", "").replace("%", "")
    if not value or value in {"-", "N/A"}:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _url(href: str, host: str) -> str:
    if href.startswith("http"):
        return href
    return host + href if href.startswith("/") else href


def _header_index(table: Table) -> dict[str, int]:
    for row in table.rows:
        names = [cell.value().strip().lower() for cell in row]
        if "player" in names:
            return {name: i for i, name in enumerate(names) if name}
    return {}


def _cell(row: list[Cell], index: dict[str, int], name: str) -> Cell | None:
    i = index.get(name.lower())
    return row[i] if i is not None and i < len(row) else None


def _text(row: list[Cell], index: dict[str, int], name: str) -> str:
    cell = _cell(row, index, name)
    return cell.value() if cell else ""


def _first_link(cell: Cell | None, host: str) -> str | None:
    if not cell or not cell.links:
        return None
    href = cell.links[0].get("href", "")
    return _url(href, host) if href else None


def _link_text(cell: Cell | None) -> str:
    if not cell or not cell.links:
        return ""
    return " ".join("".join(cell.links[0].get("text", [])).split())


def _class_text(cell: Cell | None, class_name: str) -> str:
    return " ".join("".join((cell.class_text.get(class_name, []) if cell else [])).split())


def _event_metadata(path: Path, text: str, source_hash: str) -> dict[str, Any]:
    title_match = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else path.stem
    page_match = re.search(r'"wgPageName":"([^"]+)"', text)
    revision_match = re.search(r'"wgCurRevisionId":(\d+)', text)
    page = page_match.group(1) if page_match else path.stem
    return {
        "source_event_key": f"liquipedia:{page}",
        "title": title,
        "source_url": "https://liquipedia.net/valorant/" + page.replace(" ", "_"),
        "revision_id": int(revision_match.group(1)) if revision_match else None,
        "source_file": path.name,
        "source_sha256": source_hash,
    }


def _agent_titles(cell: Cell | None) -> list[str]:
    if not cell:
        return []
    values = [link["title"] for link in cell.links if link.get("title")]
    values.extend(
        image.get("title") or image.get("alt", "") for image in cell.images
    )
    return list(dict.fromkeys(value for value in values if value))


def _parse_liquipedia(path: Path, tables: list[Table], text: str, source_hash: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    candidates = [table for table in tables if {"player", "acs"}.issubset(_header_index(table))]
    if not candidates:
        return [], None, warnings
    if len(candidates) != 1:
        warnings.append(f"{path.name}: found {len(candidates)} Liquipedia stat tables")
    table = candidates[0]
    headers = _header_index(table)
    event = _event_metadata(path, text, source_hash)
    season = _season_from_name(path.name) or _season_from_name(event["source_event_key"])
    rows: list[dict[str, Any]] = []
    for row in table.rows:
        player_cell = _cell(row, headers, "player")
        player_url = _first_link(player_cell, "https://liquipedia.net")
        if not player_url:
            continue
        source_player_key = player_url.removeprefix("https://liquipedia.net/valorant/")
        team_cell = _cell(row, headers, "team")
        agents = _agent_titles(_cell(row, headers, "agents"))
        record = {
            "source": "liquipedia",
            "scope_type": "event",
            "season": season,
            "source_event_key": event["source_event_key"],
            "source_player_key": source_player_key,
            "player_display_name": _link_text(player_cell) or player_cell.value(),
            "player_url": player_url,
            "team": team_cell.links[0].get("title", "") if team_cell and team_cell.links else _text(row, headers, "team"),
            "team_url": _first_link(team_cell, "https://liquipedia.net"),
            "agents": agents,
            "maps": _number(_text(row, headers, "maps")),
            "acs": _number(_text(row, headers, "acs")),
            "kills": _number(_text(row, headers, "k")),
            "deaths": _number(_text(row, headers, "d")),
            "assists": _number(_text(row, headers, "a")),
            "kd": _number(_text(row, headers, "kd")),
            "kda": _number(_text(row, headers, "kda")),
            "kills_per_map": _number(_text(row, headers, "k/map")),
            "deaths_per_map": _number(_text(row, headers, "d/map")),
            "assists_per_map": _number(_text(row, headers, "a/map")),
            "source_file": path.name,
            "source_sha256": source_hash,
        }
        rows.append(record)
    return rows, event, warnings


def _season_from_name(name: str) -> int | None:
    match = re.search(r"(?<!\d)(20\d{2})(?!\d)", name)
    return int(match.group(1)) if match else None


def _parse_vlr(path: Path, tables: list[Table], source_hash: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    table = next((t for t in tables if t.attrs.get("id") == "st-table"), None)
    if table is None:
        return [], None, []
    headers = _header_index(table)
    event = {
        "source_event_key": f"vlr:stats:{_season_from_name(path.name) or 'unknown'}",
        "title": path.stem,
        "source_url": "https://www.vlr.gg/stats/",
        "revision_id": None,
        "source_file": path.name,
        "source_sha256": source_hash,
    }
    rows: list[dict[str, Any]] = []
    for row in table.rows:
        player_cell = _cell(row, headers, "player")
        player_url = _first_link(player_cell, "https://www.vlr.gg")
        match = re.search(r"/player/(\d+)", player_url or "")
        if not match:
            continue
        by_col = {cell.attrs.get("data-col", ""): cell for cell in row}
        agent_cell = by_col.get("agents")
        agents = []
        for image in agent_cell.images if agent_cell else []:
            src = image.get("src", "")
            agent = Path(src.split("?")[0]).stem.lower()
            agent = re.sub(r"_[a-z0-9]{4,}$", "", agent)
            if agent:
                agents.append(agent)
        record = {
            "source": "vlr",
            "scope_type": "season_aggregate",
            "season": _season_from_name(path.name),
            "source_event_key": event["source_event_key"],
            "source_player_key": match.group(1),
            "player_display_name": _class_text(player_cell, "st-pl-name") or _link_text(player_cell) or player_cell.value(),
            "player_url": player_url,
            "agents_displayed": agents,
            "agents_omitted_count": _omitted_agents(agent_cell.value() if agent_cell else ""),
            "maps": _number(by_col.get("maps", Cell({})).value()),
            "rounds": _number(by_col.get("rnd", Cell({})).value()),
            "rating": _number(by_col.get("rating2", Cell({})).value()),
            "acs": _number(by_col.get("acs", Cell({})).value()),
            "kd": _number(by_col.get("kd", Cell({})).value()),
            "kast_pct": _number(by_col.get("kast", Cell({})).value()),
            "adr": _number(by_col.get("adr", Cell({})).value()),
            "kpr": _number(by_col.get("kpr", Cell({})).value()),
            "apr": _number(by_col.get("apr", Cell({})).value()),
            "fkfd": _number(by_col.get("fkfd", Cell({})).value()),
            "source_file": path.name,
            "source_sha256": source_hash,
        }
        rows.append(record)
    return rows, event, []


def _omitted_agents(value: str) -> int:
    match = re.search(r"\+(\d+)", value)
    return int(match.group(1)) if match else 0


def extract(input_dir: Path, season: int | None = None) -> dict[str, Any]:
    """Parse every unique saved HTML page beneath *input_dir*, deterministically."""
    events: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_hashes: set[str] = set()
    seen_event_keys: set[str] = set()
    # Browser save directories contain hundreds of auxiliary HTML fragments.
    # The top-level files are the user-selected source pages; parsing only
    # those prevents ad/cache fragments from becoming fake tournaments.
    for path in sorted(input_dir.glob("*.htm"), key=lambda p: str(p).lower()):
        text = path.read_text(encoding="utf-8", errors="replace")
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if source_hash in seen_hashes:
            warnings.append(f"{path.name}: duplicate source content skipped")
            continue
        seen_hashes.add(source_hash)
        parser = TableParser()
        parser.feed(text)
        vlr_rows, vlr_event, vlr_warnings = _parse_vlr(path, parser.tables, source_hash)
        liq_rows, liq_event, liq_warnings = _parse_liquipedia(path, parser.tables, text, source_hash)
        event = vlr_event or liq_event
        rows = vlr_rows or liq_rows
        if season is not None:
            rows = [row for row in rows if row["season"] == season]
        if not rows:
            continue
        if event and event["source_event_key"] in seen_event_keys:
            warnings.append(f"{path.name}: duplicate event skipped")
            continue
        if event:
            seen_event_keys.add(event["source_event_key"])
            observations.extend(rows)
            events.append(event)
        warnings.extend(vlr_warnings + liq_warnings)
    observations.sort(key=lambda r: (r["season"] or 0, r["source"], r["source_event_key"], r["source_player_key"]))
    events.sort(key=lambda e: e["source_event_key"])
    return {"parser_version": PARSER_VERSION, "events": events, "observations": observations, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--season", type=int, help="retain only one season")
    args = parser.parse_args()
    if not args.input_dir.is_dir():
        raise SystemExit(f"input directory does not exist: {args.input_dir}")
    result = extract(args.input_dir, season=args.season)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(result['events'])} sources, {len(result['observations'])} observations -> {args.output}")


if __name__ == "__main__":
    main()
