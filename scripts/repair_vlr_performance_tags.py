"""Recover source-backed performance rows when parent/academy tags differ.

Only cached source pages are used. Raw collection issues remain intact; a
separate receipt records resolved and unresolved cases and every fallback.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

from bs4 import SoupStrainer
from analyze_vlr_research import read_csv
from collect_vlr_research import Cache, ROOT, write_csv
from collect_vlr_war_history import parse_performance, performance_team_logos


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'data/research/war-history')
    p.add_argument('--cache',type=Path,required=True);args=p.parse_args();data=args.data
    cache=Cache(args.cache,offline=True)
    maps=defaultdict(list)
    for m in read_csv(data/'map_outcomes.csv'):maps[m['source_url']].append(m)
    players=read_csv(data/'player_map_stats.csv')
    by_match=defaultdict(list)
    for r in players:by_match[r['match_id']].append(r)
    records=read_csv(data/'player_map_performance.csv');coverage=read_csv(data/'tab_coverage.csv')
    existing={(r['match_id'],r['map_id'],r['vlr_player_id']) for r in records}
    cov={(r['map_id'],r['tab']):r for r in coverage}
    audit,resolutions=[],[];added=0
    issues=[r for r in read_csv(data/'collection_issues.csv') if r['kind']=='performance_failed']
    for issue in issues:
        url=issue['source_url']
        soup,source=cache.get(url.rstrip('/')+'/?tab=performance',parse_only=SoupStrainer(class_=re.compile(r'^(?:vm-stats|match-header)')))
        logos=performance_team_logos(soup)
        for m in maps[url]:
            game=soup.select_one(f'.vm-stats-game[data-game-id="{m["map_id"]}"]')
            if game is None:continue
            pending=[]
            try:
                rows=parse_performance(game,m,by_match[m['match_id']],logos,pending)
            except ValueError as e:
                resolutions.append(dict(match_id=m['match_id'],map_id=m['map_id'],status='unresolved',detail=str(e)))
                continue
            audit.extend(pending)
            for r in rows:
                key=(str(r['match_id']),str(r['map_id']),str(r['vlr_player_id']))
                if key not in existing:
                    records.append(r);existing.add(key);added+=1
            entry=dict(match_id=m['match_id'],map_id=m['map_id'],tab='performance',rows=len(rows),
                       source_url=source['source_url'],source_sha256=source['sha256'],retrieved_at_utc=source['retrieved_at_utc'])
            cov[(m['map_id'],'performance')]=entry
            resolutions.append(dict(match_id=m['match_id'],map_id=m['map_id'],status='resolved',detail='Unique match-local identity corroborated; no handle-only lifetime join'))
    write_csv(data/'player_map_performance.csv',sorted(records,key=lambda r:(int(r['match_id']),int(r['map_id']),int(r['vlr_player_id']))))
    write_csv(data/'tab_coverage.csv',sorted(cov.values(),key=lambda r:(int(r['match_id']),int(r['map_id']),r['tab'])))
    write_csv(data/'performance_identity_review.csv',audit,['match_id','map_id','vlr_player_id','performance_handle','performance_tag','overview_handle','overview_tag','team_id','join_rule'])
    write_csv(data/'performance_issue_resolution.csv',resolutions,['match_id','map_id','status','detail'])
    receipt=dict(offline=True,source_issues_reviewed=len(issues),added_player_map_rows=added,
                 resolved_maps=sum(r['status']=='resolved' for r in resolutions),unresolved_maps=sum(r['status']=='unresolved' for r in resolutions),
                 fallback_joins=sum(r['join_rule']!='exact_map_handle_and_tag' for r in audit),
                 code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 source_rule='Only exact match-team-logo + unique normalized local handle + same agent resolves differing source tags. Raw collection issues retained.')
    (data/'performance_repair_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
