"""Import players first observed in supplied post-2021 stat-page downloads.

The generated source sheets deliberately remain separate from the curated 2021
free-agent/prospect sheets.  That lets the archive intake be regenerated and
audited without hand-editing hundreds of rows.

Usage: python scripts/import_future_archive_players.py C:/Users/name/Downloads/rosters
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[1]
PACK = REPO / "data" / "rosters" / "vct-2021"
SRC = PACK / "src"


def identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def ascii_name(value: str) -> str:
    value = re.sub(r"\s*\([^)]*\)$", "", value).strip()
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


class StatRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_row = False
        self.links: list[str] = []
        self.country = ""
        self.rows: list[tuple[str, str, str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "tr" and "table2__row--body" in (attr.get("class") or ""):
            self.in_row, self.links, self.country = True, [], ""
        elif self.in_row and tag == "a":
            href = attr.get("href") or ""
            if href.startswith("https://liquipedia.net/valorant/"):
                self.links.append(attr.get("title") or "")
        elif self.in_row and tag == "img" and not self.country:
            self.country = attr.get("alt") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self.in_row:
            if len(self.links) >= 2:
                self.rows.append((self.links[0], self.links[1], self.country, self.links[2:]))
            self.in_row = False


AMERICAS = {
    "Argentina", "Brazil", "Canada", "Chile", "Colombia", "Costa Rica",
    "Dominican Republic", "Ecuador", "Guatemala", "Mexico", "Peru",
    "United States", "Uruguay", "Venezuela",
}
EMEA = {
    "Albania", "Austria", "Belarus", "Belgium", "Bosnia and Herzegovina",
    "Bulgaria", "Croatia", "Czech Republic", "Denmark", "Egypt", "Estonia",
    "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Israel",
    "Italy", "Jordan", "Latvia", "Lebanon", "Lithuania", "Morocco", "Netherlands",
    "North Macedonia", "Norway", "Poland", "Portugal", "Romania", "Russia",
    "Serbia", "Slovakia", "Slovenia", "Spain", "Sweden", "Switzerland", "Turkey",
    "Ukraine", "United Kingdom",
}
CHINA = {"China", "Hong Kong", "Macau", "Taiwan"}


def region_for(country: str) -> str:
    if country in AMERICAS:
        return "americas"
    if country in EMEA:
        return "emea"
    if country in CHINA:
        return "china"
    return "pacific"


def main() -> None:
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "rosters"
    agent_data = yaml.safe_load((REPO / "data" / "agents.yaml").read_text(encoding="utf-8"))
    agents = {
        str(a["display_name"]).lower(): (str(a["id"]), str(a["role"]))
        for a in agent_data["agents"]
    }
    existing: set[str] = set()
    for name in ("americas", "emea", "pacific"):
        for team in yaml.safe_load((SRC / f"{name}.yaml").read_text(encoding="utf-8"))["teams"]:
            existing.update(identity_key(p["handle"]) for p in team["players"])
    for name, key in (("free_agents", "free_agents"), ("future_prospects", "future_prospects")):
        raw = yaml.safe_load((SRC / f"{name}.yaml").read_text(encoding="utf-8")) or {}
        existing.update(identity_key(p["handle"]) for p in raw.get(key, []))

    # Verified under-17-at-start exceptions among early future appearances.
    # The rest use the conservative first-observed-year rule below.
    birth_overrides = {"less": 2005, "cauanzin": 2005, "n4rrate": 2005, "florescent": 2006}
    observed: dict[str, tuple[int, str, str, list[str]]] = {}
    for page in archive.glob("*Statistics*.htm"):
        match = re.search(r"202([2-6])", page.name)
        if not match:
            continue
        year = 2020 + int(match.group(1))
        parser = StatRows()
        parser.feed(page.read_text(encoding="utf-8", errors="ignore"))
        for raw_name, _team, country, links in parser.rows:
            handle = ascii_name(raw_name)
            key = identity_key(handle)
            if not key or key in existing:
                continue
            picks = [agents[a.lower()] for a in links if a.lower() in agents][:3]
            # A few archived rows omit agent icons. Keep those competitors in
            # the database with a neutral flex profile rather than discarding
            # them from the historical universe.
            if not picks:
                picks = [("sage", "flex")]
            old = observed.get(key)
            if old is None or year < old[0]:
                observed[key] = (year, handle, country, picks)

    free_agents, prospects = [], []
    for key, (first_year, handle, country, picks) in sorted(observed.items()):
        agent_ids = list(dict.fromkeys(agent_id for agent_id, _role in picks))[:3]
        role = picks[0][1]
        playstyle = {
            "duelist": "entry", "initiator": "support", "controller": "anchor",
            "sentinel": "anchor", "flex": "lurker",
        }[role]
        common = {
            "handle": handle, "region": region_for(country), "role": role,
            "playstyle": playstyle, "igl": False,
            "quality": max(58, min(72, 62 + (2026 - first_year))),
            "agents": agent_ids,
        }
        birth_year = birth_overrides.get(key)
        # A first appearance from 2024 onward is held as a prospect until that
        # observed year. Earlier entries are signable at the 2021 start unless
        # their verified birth year says otherwise.
        if birth_year is not None or first_year >= 2024:
            common["birth_year"] = birth_year or first_year - 17
            prospects.append(common)
        else:
            common["age"] = max(17, 2021 - (first_year - 19))
            free_agents.append(common)

    (SRC / "future_archive_free_agents.yaml").write_text(
        yaml.safe_dump({"free_agents": free_agents}, sort_keys=False, width=100), encoding="ascii"
    )
    (SRC / "future_archive_prospects.yaml").write_text(
        yaml.safe_dump({"future_prospects": prospects}, sort_keys=False, width=100), encoding="ascii"
    )
    print(f"future archive: {len(free_agents)} free agents, {len(prospects)} prospects")


if __name__ == "__main__":
    main()
