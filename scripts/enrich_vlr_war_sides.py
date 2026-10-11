"""Extract attacking/defending player box scores from the immutable cache.

These facts stay at a separate grain. They never join the same-map outcome
prediction as features, and incomplete round histories have blank exposure.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re

from bs4 import SoupStrainer

from analyze_vlr_research import read_csv
from collect_vlr_research import Cache, MAP_COLS, ROOT, number, source_id, text


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'data/research/war-history')
    p.add_argument('--cache',type=Path,required=True);args=p.parse_args();data=args.data
    cache=Cache(args.cache,offline=True)
    by_url=defaultdict(list)
    for m in read_csv(data/'map_outcomes.csv'):by_url[m['source_url']].append(m)
    allowed={(r['map_id'],r['vlr_player_id']) for r in read_csv(data/'player_map_stats.csv')}
    eligible={r['map_id'] for r in read_csv(data/'round_model_eligibility.csv') if r['round_model_eligible']=='True'}
    exposure=Counter()
    maps={m['map_id']:m for ms in by_url.values() for m in ms}
    for r in read_csv(data/'round_outcomes.csv'):
        if r['map_id'] in eligible:
            m=maps[r['map_id']]
            for i in [1,2]:exposure[(r['map_id'],m[f'team{i}_id'],r[f'team{i}_side'])]+=1
    count=0;fields=['match_id','map_id','vlr_player_id','team_id','side','rounds_played','reported_fields',*MAP_COLS.values()]
    output=data/'player_map_side_stats.csv'
    with output.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for url,ms in by_url.items():
            soup,source=cache.get(url,parse_only=SoupStrainer(class_=re.compile(r'^vm-stats')))
            if any(m['source_sha256']!=source['sha256'] for m in ms):raise ValueError('Side stats cache/source mismatch')
            for m in ms:
                game=soup.select_one(f'.vm-stats-game[data-game-id="{m["map_id"]}"]')
                for i,table in enumerate(game.select('.ovw-table'),1):
                    for tr in table.select('.ovw-row:not(.mod-head)'):
                        link=tr.select_one('a[href^="/player/"]')
                        if not link:continue
                        pid=source_id(link['href'],'player')
                        if (m['map_id'],pid) not in allowed:raise ValueError('Orphan side identity')
                        tid=m[f'team{i}_id']
                        for css,label in [('mod-t','attack'),('mod-ct','defense')]:
                            stats={field:number(text(tr.select_one(f'[data-col="{col}"] .side.{css}'))) for col,field in MAP_COLS.items()}
                            row=dict(match_id=m['match_id'],map_id=m['map_id'],vlr_player_id=pid,team_id=tid,side=label,
                                     rounds_played=exposure[(m['map_id'],tid,label)] if m['map_id'] in eligible else None,
                                     reported_fields=sum(v is not None for v in stats.values()),**stats)
                            writer.writerow(row);count+=1
    receipt=dict(rows=count,source_pages=len(by_url),offline=True,
                 sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                 code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 exposure_rule='Count validated displayed rounds for that team and side; blank when round history is ineligible.',
                 source_rule='Join map_id to map_context.csv for overview source URL/hash/timestamp. Unknown player identities and series aggregates excluded.')
    (data/'side_stats_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
