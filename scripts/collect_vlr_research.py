"""Collect source-backed event, player-map, outcome, and profile CSVs.

Install .[research]; see docs/vlr-2026-research.md. Cached rebuilds are offline.
This is research tooling: it never edits the installed roster or game ratings.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import http.client
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOST = "https://www.vlr.gg"
VERSION = 1
STAT_COLS = {
    "maps": "maps", "rnd": "rounds", "rating2": "vlr_rating", "acs": "acs",
    "kd": "kd", "kast": "kast_pct", "adr": "adr", "kpr": "kpr",
    "apr": "apr", "fbpr": "fk_rate_reported", "fdpr": "fd_rate_reported",
    "hsp": "hs_pct", "clp": "clutch_pct", "kmax": "max_kills",
    "k": "kills", "d": "deaths", "a": "assists", "fk": "first_kills",
    "fd": "first_deaths", "fkfd": "fk_fd_ratio",
}
MAP_COLS = {
    "rating2": "vlr_rating", "acs": "acs", "kills": "kills", "deaths": "deaths",
    "assists": "assists", "kast": "kast_pct", "adr": "adr", "hsp": "hs_pct",
    "fb": "first_kills", "fd": "first_deaths",
}


def text(node):
    return node.get_text(" ", strip=True) if node else ""


def number(value):
    value = value.strip().replace("%", "").replace(",", "").replace("−", "-")
    if value in {"", "-", "–", "N/A"}:
        return None
    try:
        v = float(value)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def source_id(url, kind):
    m = re.search(r"/" + kind + r"/(\d+)", url)
    return m.group(1) if m else ""


def normalize(value):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower())


def write_csv(path, rows, fields=None):
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


class Cache:
    def __init__(self, path, offline=False, delay=0.6):
        self.path, self.offline, self.delay = path, offline, delay
        path.mkdir(parents=True, exist_ok=True)
        self.sources = {}
        self.last_request = 0.0

    def get(self, url, parse_only=None):
        key = hashlib.sha256(url.encode()).hexdigest()
        p, meta = self.path / (key + ".html.gz"), self.path / (key + ".json")
        if p.exists() and meta.exists():
            body = gzip.decompress(p.read_bytes())
            record = json.loads(meta.read_text())
            if hashlib.sha256(body).hexdigest() != record["sha256"]:
                raise ValueError(f"Cache hash mismatch: {url}")
        else:
            if self.offline:
                raise FileNotFoundError(f"Not cached: {url}")
            # Respect the source's robots policy and keep requests sequential.
            if not url.startswith(HOST + "/") or "/search/auto" in url or "/rr/" in url:
                raise ValueError(f"Unsupported URL: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "esports-tycoon-research/1.0 (public match statistics; cached)"})
            for attempt in range(3):
                time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
                try:
                    with urllib.request.urlopen(req, timeout=40) as response:
                        body = response.read()
                    break
                except (http.client.IncompleteRead, TimeoutError, ConnectionResetError, urllib.error.URLError) as error:
                    if attempt == 2 or isinstance(error,urllib.error.HTTPError) and error.code<500:
                        raise
                    time.sleep(attempt + 1)
            record = {"source_url": url, "sha256": hashlib.sha256(body).hexdigest(),
                      "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "bytes": len(body), "parser_version": VERSION}
            p.write_bytes(gzip.compress(body, mtime=0))
            meta.write_text(json.dumps(record, sort_keys=True) + "\n")
        self.sources[url] = record
        return BeautifulSoup(body, "lxml", parse_only=parse_only), record


def parse_event_stats(soup, event, provenance):
    table = soup.select_one("table#st-table")
    if table is None:
        # Older VLR markup uses the same data-col contract on a differently named table.
        table = soup.select_one("table.wf-table")
    if table is None:
        return []
    rows = []
    for tr in table.select("tbody tr"):
        a = tr.select_one('a[href^="/player/"]')
        if a is None:
            continue
        name = tr.select_one(".st-pl-name, .text-of")
        country = tr.select_one(".flag")
        country = next((c[4:].upper() for c in country.get("class", []) if c.startswith("mod-")), "") if country else ""
        row = {"event_id": event["event_id"], "season": 2026, "competition_tier": event["competition_tier"],
               "region": event["region"], "vlr_player_id": source_id(a["href"], "player"),
               "handle": text(name) or text(a), "team_tag_at_event": text(tr.select_one(".st-pl-country")),
               "country": country, "player_url": HOST + a["href"],
               "agents": "|".join(Path(i.get("src", "")).stem for i in tr.select('td[data-col="agents"] img')),
               "source_url": provenance["source_url"], "source_sha256": provenance["sha256"],
               "retrieved_at_utc": provenance["retrieved_at_utc"]}
        for col, field in STAT_COLS.items():
            row[field] = number(text(tr.select_one(f'td[data-col="{col}"]')))
        cl = tr.select_one('td[data-col="cl"]')
        pair = text(cl).replace(" ", "").split("/")
        row["clutches_won"] = number(pair[0]) if len(pair) == 2 else None
        row["clutch_attempts"] = number(pair[1]) if len(pair) == 2 else None
        # VLR has changed FK% presentation; derive comparable rates from counts.
        for field, count in [("fkpr", "first_kills"), ("fdpr", "first_deaths")]:
            row[field] = round(row[count] / row["rounds"], 6) if row[count] is not None and row["rounds"] else None
        rows.append(row)
    return rows


def parse_match(soup, event, provenance, cutoff, start_date="2026-01-01"):
    date = soup.select_one(".match-header-date [data-utc-ts]")
    stamp = date.get("data-utc-ts", "") if date else ""
    if not stamp or not start_date <= stamp[:10] <= cutoff:
        return [], [], "outside_cutoff_or_missing_date"
    links = soup.select(".match-header-vs a.match-header-link")
    if len(links) != 2 or any(not a.get("href", "").startswith("/team/") for a in links):
        return [], [], "missing_teams"
    teams = [{"id": source_id(a["href"], "team"), "name": text(a.select_one(".wf-title-med"))} for a in links]
    patch_match = re.search(r"Patch\s+([\d.]+)", text(soup.select_one(".match-header-date")))
    match_id = re.search(r"vlr.gg/(\d+)", provenance["source_url"]).group(1)
    context = {"event_id": event["event_id"], "match_id": match_id,
               "competition_tier": event["competition_tier"], "region": event["region"],
               "played_at_utc": stamp, "patch": patch_match.group(1) if patch_match else "",
               "source_url": provenance["source_url"], "source_sha256": provenance["sha256"],
               "retrieved_at_utc": provenance["retrieved_at_utc"]}
    maps, players = [], []
    for g in soup.select(".vm-stats-game[data-game-id]"):
        gid = g["data-game-id"]
        if gid == "all":
            continue  # Never double-count the series aggregate.
        header = g.select_one(".vm-stats-game-header")
        if not header:
            continue
        scores = [number(text(x)) for x in header.select(".score")]
        if len(scores) != 2 or any(s is None for s in scores):
            continue
        # Selected VCT/Challengers maps use MR12 and win by two in overtime.
        # A live 12-10 or 13-12 lead is not a completed map outcome.
        if max(scores) < 13 or abs(scores[0] - scores[1]) < 2:
            continue  # Unplayed, cancelled, or unfinished map.
        name_node = header.select_one(".map > div > span")
        map_name = " ".join(name_node.find_all(string=True, recursive=False)).strip() if name_node else ""
        tables = g.select(".ovw-table")
        if len(tables) != 2:
            return [], [], "unsupported_stat_markup"
        map_row = {**context, "map_id": gid, "map_name": map_name,
                   "team1_id": teams[0]["id"], "team1_name": teams[0]["name"],
                   "team2_id": teams[1]["id"], "team2_name": teams[1]["name"],
                   "team1_rounds": scores[0], "team2_rounds": scores[1],
                   "rounds": sum(scores), "winner_team_id": teams[int(scores[1] > scores[0])]["id"]}
        for i, table in enumerate(tables):
            for r in table.select(".ovw-row:not(.mod-head)"):
                a = r.select_one('a[href^="/player/"]')
                if not a:
                    continue
                row = {**context, "map_id": gid, "map_name": map_name,
                       "vlr_player_id": source_id(a["href"], "player"),
                       "handle": text(r.select_one(".ovw-player-name")), "player_url": HOST + a["href"],
                       "team_id": teams[i]["id"], "team_name": teams[i]["name"],
                       "team_tag_at_match": text(r.select_one(".ovw-player-tag")),
                       "opponent_id": teams[1-i]["id"], "rounds": sum(scores),
                       "rounds_won": scores[i], "rounds_lost": scores[1-i],
                       "map_win": int(scores[i] > scores[1-i]),
                       "agent": "|".join(Path(im.get("src", "")).stem for im in r.select(".ovw-agents img"))}
                for col, field in MAP_COLS.items():
                    row[field] = number(text(r.select_one(f'[data-col="{col}"] .side.mod-both')))
                players.append(row)
        maps.append(map_row)
    return maps, players, "parsed" if maps else "no_played_maps"


def parse_profile(soup, provenance):
    heading = next((h for h in soup.select('h2.wf-label') if text(h) == 'Current Teams'), None)
    section = heading.find_next_sibling() if heading else None
    current_teams = text(section)
    news = [text(a) for a in soup.select('a.wf-module-item')
            if re.search(r'retir|steps? back|inactive|bench', text(a), re.I)]
    return {"vlr_player_id": source_id(provenance["source_url"], "player"),
            "handle": text(soup.select_one(".player-header .wf-title")),
            "real_name": text(soup.select_one(".player-real-name")),
            "current_team_evidence": current_teams,
            "team_listing_status": "current_team_listed" if current_teams else "no_current_team_listed",
            "inactive_news_evidence": "|".join(news),
            "source_url": provenance["source_url"], "source_sha256": provenance["sha256"],
            "retrieved_at_utc": provenance["retrieved_at_utc"]}


def roster_rows():
    """Read compact sheets; keep the pack snapshot separate from present-day status."""
    rows = []
    for p in sorted((ROOT / "data/rosters/vct-2026/src").glob("*.yaml")):
        sheet = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        groups = [(t.get("players", []), {"pack_team": t["name"], "pack_team_tag": t["tag"],
                   "pack_tier": t.get("tier", 1), "region": sheet["region"], "pack_status": "rostered"}) for t in sheet.get("teams", [])]
        groups += [(sheet.get("free_agents", []), {"pack_team": "", "pack_team_tag": "", "pack_tier": "", "pack_status": "free_agent"})]
        for ps, context in groups:
            for spec in ps:
                rows.append({**context, "region": spec.get("region", context.get("region", "")),
                             "handle": spec["handle"], "real_name": spec.get("real_name", ""),
                             "country": spec.get("country", ""), "pack_role": spec["role"],
                             "pack_quality": spec["quality"], "source_sheet": p.relative_to(ROOT).as_posix()})
    return rows


def collect(args):
    manifest = json.loads(args.manifest.read_text())
    cache = Cache(args.cache, args.offline, args.delay)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    manifest["as_of_date"] = args.as_of
    (output / "event_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    events, stats, maps, player_maps, issues = [], [], [], [], []
    # Make the source's access policy part of the provenance ledger.
    cache.get(HOST + "/robots.txt")
    for spec in manifest["events"]:
        event = {**spec, "stats_rows": 0, "matches_listed": 0, "matches_parsed": 0, "map_rows": 0}
        eid = spec["event_id"]
        try:
            soup, src = cache.get(f"{HOST}/event/stats/{eid}?min_rounds=0")
            title = text(soup.select_one("h1"))
            if title and normalize(title) != normalize(spec["name"]):
                raise ValueError(f"Unexpected event title {title!r}")
            rows = parse_event_stats(soup, event, src)
            stats.extend(rows)
            event["stats_rows"] = len(rows)
            if not rows:
                issues.append({"kind": "no_event_stats", "source_url": src["source_url"], "detail": spec["name"]})
            if spec["collect_maps"]:
                soup, _ = cache.get(f"{HOST}/event/matches/{eid}/?group=all")
                links = list(dict.fromkeys(HOST + a["href"] for a in soup.select("a.match-item[href]")))
                # Refuse silent pagination gaps.
                if soup.select('a.btn.mod-page'):
                    raise ValueError("Match list pagination requires explicit handling")
                event["matches_listed"] = len(links)
                for url in links:
                    try:
                        match_soup, source = cache.get(url)
                        ms, ps, status = parse_match(match_soup, event, source, args.as_of)
                        if status != "parsed":
                            issues.append({"kind": status, "source_url": url, "detail": spec["name"]})
                        else:
                            maps.extend(ms); player_maps.extend(ps)
                            event["matches_parsed"] += 1; event["map_rows"] += len(ms)
                    except (ValueError, OSError, urllib.error.URLError) as e:
                        issues.append({"kind": "match_failed", "source_url": url, "detail": str(e)})
        except (ValueError, OSError, urllib.error.URLError) as e:
            issues.append({"kind": "event_failed", "source_url": f"{HOST}/event/{eid}", "detail": str(e)})
        events.append(event)
        print(f"{eid} {spec['name']}: {event['stats_rows']} players, {event['map_rows']} maps", flush=True)
        # Durable progress: an interrupted run resumes from the cache.
        write_csv(output / "events.csv", events)
        write_csv(output / "player_event_stats.csv", stats)
        if maps:
            write_csv(output / "map_outcomes.csv", sorted(maps, key=lambda r: (r["played_at_utc"], int(r["match_id"]), int(r["map_id"]))))
            write_csv(output / "player_map_stats.csv", sorted(player_maps, key=lambda r: (r["played_at_utc"], int(r["map_id"]), int(r["vlr_player_id"]))))
        write_csv(output / "collection_issues.csv", issues, ["kind", "source_url", "detail"])
        write_csv(output / "sources.csv", [cache.sources[u] for u in sorted(cache.sources)])
    collect_profiles(cache, stats, issues, output, args.profile_candidates)


def collect_profiles(cache, stats, issues, output, candidate_path):
    roster = roster_rows()
    # Name lookup produces candidates only; a second identity signal is mandatory.
    by_handle = {}
    evidence = list(stats)
    if (output / "player_map_stats.csv").exists():
        with (output / "player_map_stats.csv").open(encoding="utf-8") as f:
            evidence.extend({**r, "team_tag_at_event": r["team_tag_at_match"], "country": ""} for r in csv.DictReader(f))
    for r in evidence:
        # Map rows lack country; do not overwrite richer event identity evidence.
        by_handle.setdefault(normalize(r["handle"]), {}).setdefault(r["vlr_player_id"], r)
    if candidate_path.exists():
        for c in json.loads(candidate_path.read_text())["players"]:
            pid = source_id(c["url"], "player")
            by_handle.setdefault(normalize(c["handle"]), {}).setdefault(pid, {
                "handle": c["handle"], "vlr_player_id": pid, "player_url": c["url"], "country": ""})
    candidates_by_id = {r["vlr_player_id"]: r for candidates in by_handle.values() for r in candidates.values()}
    profiles = []
    for pid in sorted({r["vlr_player_id"] for p in roster for r in by_handle.get(normalize(p["handle"]), {}).values()}, key=int):
        row = candidates_by_id[pid]
        try:
            s, src = cache.get(row["player_url"])
            profiles.append(parse_profile(s, src))
        except (ValueError, OSError, urllib.error.URLError) as e:
            issues.append({"kind": "profile_failed", "source_url": row["player_url"], "detail": str(e)})
    prof = {p["vlr_player_id"]: p for p in profiles}
    crosswalk = []
    for p in roster:
        candidates = list(by_handle.get(normalize(p["handle"]), {}).values())
        row = {**p, "candidate_vlr_ids": "|".join(sorted(r["vlr_player_id"] for r in candidates)),
               "vlr_player_id": "", "identity_status": "unobserved", "identity_evidence": "", "profile_url": "",
               "current_team_evidence": "", "current_team_listing_status": "unverified",
               "inactive_news_evidence": "", "profile_real_name": ""}
        if len(candidates) == 1:
            c = candidates[0]; profile = prof.get(c["vlr_player_id"], {})
            real_name = normalize(p["real_name"])
            name_match = real_name not in {"", "unknown", normalize(p["handle"])} and real_name == normalize(profile.get("real_name", ""))
            tag_match = p["pack_team_tag"] and any(r["team_tag_at_event"] == p["pack_team_tag"] for r in evidence if r["vlr_player_id"] == c["vlr_player_id"])
            country_match = p["country"].upper() == c["country"] and bool(p["country"])
            row.update(identity_status="candidate_needs_review", profile_url=c["player_url"])
            if name_match or (tag_match and country_match):
                row.update(vlr_player_id=c["vlr_player_id"], identity_status="corroborated",
                           identity_evidence="handle+profile_real_name" if name_match else "handle+event_team_tag+country",
                           current_team_evidence=profile.get("current_team_evidence", ""),
                           current_team_listing_status=profile.get("team_listing_status", "unverified"),
                           inactive_news_evidence=profile.get("inactive_news_evidence", ""),
                           profile_real_name=profile.get("real_name", ""))
        elif len(candidates) > 1:
            row["identity_status"] = "ambiguous"
        crosswalk.append(row)
    write_csv(output / "roster_crosswalk.csv", crosswalk)
    write_csv(output / "free_agent_review.csv", [{**r,
              "contract_status": "unverified",
              "review_state": "current_team_listing_needs_review" if r["current_team_evidence"] else "availability_requires_review",
              "warning": "A pack free agent may be retired, inactive, a stand-in, or rostered; no team listing does not prove availability."}
              for r in crosswalk if r["pack_status"] == "free_agent"])
    write_csv(output / "player_profiles.csv", profiles)
    write_csv(output / "collection_issues.csv", issues, ["kind", "source_url", "detail"])
    write_csv(output / "sources.csv", [cache.sources[u] for u in sorted(cache.sources)])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / "data/research/vct-2026/event_manifest.json")
    p.add_argument("--output", type=Path, default=ROOT / "data/research/vct-2026")
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--as-of", default="2026-10-06", help="Inclusive UTC match-date cutoff; event aggregates remain the source's current snapshot")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--profiles-only", action="store_true", help="Reuse event/map CSVs and refresh identities/status evidence")
    p.add_argument("--profile-candidates", type=Path, default=ROOT / "data/research/vct-2026/profile_candidates.json")
    p.add_argument("--delay", type=float, default=0.6, help="Minimum seconds between requests (>=0.5)")
    args = p.parse_args()
    datetime.strptime(args.as_of, "%Y-%m-%d")
    if args.delay < 0.5:
        p.error("--delay must be >=0.5")
    if args.profiles_only:
        cache = Cache(args.cache, args.offline, args.delay)
        if (args.output / "sources.csv").exists():
            with (args.output / "sources.csv").open(encoding="utf-8") as f:
                cache.sources = {r["source_url"]: r for r in csv.DictReader(f)}
        with (args.output / "player_event_stats.csv").open(encoding="utf-8") as f:
            stats = list(csv.DictReader(f))
        with (args.output / "collection_issues.csv").open(encoding="utf-8") as f:
            issues = list(csv.DictReader(f))
        collect_profiles(cache, stats, issues, args.output, args.profile_candidates)
    else:
        collect(args)


if __name__ == "__main__":
    main()
