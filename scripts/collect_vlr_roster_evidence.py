"""Preserve dated team-history and roster-news evidence from cached profiles.

Profile lists are retrospective snapshots, not verified contracts or precise
transfer dates. Publication dates are distinct from effective signing dates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from analyze_vlr_research import read_csv
from collect_vlr_research import Cache, ROOT, source_id, text, write_csv


def profile_evidence(soup, source, pid):
    context=dict(vlr_player_id=pid,source_url=source['source_url'],source_sha256=source['sha256'],
                 retrieved_at_utc=source['retrieved_at_utc'])
    teams,news=[],[]
    for heading in soup.select('h2.wf-label'):
        section=text(heading)
        if section not in {'Current Teams','Past Teams'}:
            continue
        following=heading.find_next_sibling()
        if not following:
            continue
        for a in following.select('a[href^="/team/"]'):
            divs=a.select('div[style*="line-height"] > div')
            name=text(divs[0]) if divs else ''
            dates=text(divs[-1]) if len(divs)>1 else ''
            tags='|'.join(text(tag) for tag in a.select('.wf-tag'))
            # Month text has no day precision. Preserve it without filling in
            # the first of the month or assuming a contract end date.
            teams.append({**context,'team_id':source_id(a['href'],'team'),'team_name':name,
                          'profile_section':section,'role_status_badges':tags,'date_display':dates,
                          'date_precision':'source_month_or_unspecified',
                          'contract_status':'unverified','team_url':'https://www.vlr.gg'+a['href']})
    for a in soup.select('a.wf-module-item[href]'):
        label=' '.join(text(a).split())
        date=re.match(r'(\d{4})/(\d{2})/(\d{2})\s+(.+)',label)
        if not date or not '2024' <= date[1] <= '2026':
            continue
        headline=date[4]
        if not re.search(r'join|sign|depart|release|roster|bench|inactive|retir|stand.in|coach|free agent|moves? to|rebuild|replace',headline,re.I):
            continue
        news.append({**context,'news_published_date':'-'.join(date.groups()[:3]),'headline':headline,
                     'article_url':'https://www.vlr.gg'+a['href'],'effective_change_date':'',
                     'verification_status':'headline_index_from_profile_article_not_verified'})
    return teams,news


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--profiles',type=Path,default=ROOT/'data/research/vct-2026/player_profiles.csv')
    p.add_argument('--output',type=Path,default=ROOT/'data/research/war-history')
    args=p.parse_args();cache=Cache(args.cache,offline=True)
    teams,news=[],[]
    for profile in read_csv(args.profiles):
        soup,source=cache.get(profile['source_url'])
        tt,nn=profile_evidence(soup,source,profile['vlr_player_id']);teams.extend(tt);news.extend(nn)
    write_csv(args.output/'profile_team_history.csv',teams)
    write_csv(args.output/'roster_news_index.csv',news)
    write_csv(args.output/'roster_evidence_sources.csv',[cache.sources[u] for u in sorted(cache.sources)])
    receipt=dict(profiles=len(cache.sources),team_history_rows=len(teams),news_headline_rows=len(news),
                 date_rules='Profile month labels preserved verbatim. News publication dates do not imply effective signing dates.',
                 source_scope='441 previously selected pack-player profile candidates; not every player in historical maps.',
                 current_availability='Unverified; this index does not certify a realistic available replacement pool.')
    (args.output/'roster_evidence_summary.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
