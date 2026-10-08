"""Expand cached VLR history at map, round, economy, and performance grains.

No contract, coaching, LAN, trade, or weapon information is inferred. Tab
coverage is the provenance parent for compact round/performance records.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
import hashlib
import http.client
import importlib.metadata
import platform
import urllib.error
import unicodedata

from bs4 import SoupStrainer

from collect_vlr_research import Cache, HOST, ROOT, number, parse_event_stats, parse_match, source_id, text, write_csv


ROUND_FIELDS = ['match_id', 'map_id', 'round_number', 'winner_team_id', 'team1_side', 'team2_side',
                'win_condition', 'team1_score_after', 'team2_score_after']
ECON_FIELDS = ['match_id', 'map_id', 'round_number', 'team_id', 'loadout_value',
               'bank_display', 'buy_category_display', 'round_win', 'side']
PERF_COLS = {'2K': 'two_k_rounds', '3K': 'three_k_rounds', '4K': 'four_k_rounds', '5K': 'five_k_rounds',
             '1v1': 'clutch_1v1_wins', '1v2': 'clutch_1v2_wins', '1v3': 'clutch_1v3_wins',
             '1v4': 'clutch_1v4_wins', '1v5': 'clutch_1v5_wins', 'ECON': 'econ_rating',
             'PL': 'plants', 'DE': 'defuses'}


def read_records(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))


def resume_checkpoint(output):
    if (output/'collection_receipt.json').exists():
        raise ValueError('Collection already finished; rebuild into a separate output instead of resuming.')
    marker=output/'collection_checkpoint.json'
    if marker.exists():
        saved=json.loads(marker.read_text())
        if hashlib.sha256((output/'event_manifest.json').read_bytes()).hexdigest()!=saved['manifest_sha256']:
            raise ValueError('Resume manifest changed since the checkpoint.')
        for name,digest in saved['snapshot_sha256'].items():
            if hashlib.sha256((output/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Unfinished checkpoint write or modified snapshot: '+name)
    events=read_records(output/'events.csv');completed={e['event_id'] for e in events}
    retained=[r for r in read_records(output/'map_outcomes.csv') if r['event_id'] in completed]
    if len(retained)!=sum(int(e['map_rows']) for e in events):
        raise ValueError('Completed event map counts do not reconcile; refusing to resume.')
    allowed={r['map_id'] for r in retained};discarded={}
    for name in ['map_outcomes.csv','player_map_stats.csv','round_outcomes.csv',
                 'round_economy.csv','player_map_performance.csv']:
        path=output/name;records=read_records(path)
        rows=[r for r in records if r['map_id'] in allowed]
        discarded[name]=len(records)-len(rows)
        with path.open(newline='',encoding='utf-8') as f:fields=next(csv.reader(f))
        temp=path.with_suffix('.csv.resume');write_csv(temp,rows,fields);temp.replace(path)
    log=output/'collection_resumes.json'
    history=json.loads(log.read_text()) if log.exists() else []
    history.append(dict(completed_events=len(events),retained_maps=len(retained),discarded_partial_rows=discarded,
                        checkpoint_hashes_verified=marker.exists(),
                        rule='Retain only fully checkpointed event maps; reparse the interrupted event from immutable cache.'))
    log.write_text(json.dumps(history,indent=2)+'\n')
    return events


def side(sq):
    classes = sq.get('class', [])
    return 'attack' if 'mod-t' in classes else 'defense' if 'mod-ct' in classes else ''


def parse_rounds(game, m):
    rows = []
    for col in game.select('.vlr-rounds-row-col'):
        rnd = number(text(col.select_one('.rnd-num')))
        squares = col.select('.rnd-sq')
        if rnd is None or len(squares) != 2:
            continue
        winners = [i for i, sq in enumerate(squares) if 'mod-win' in sq.get('class', [])]
        if not winners and not col.get('title'):
            continue  # Empty trailing regulation-round placeholders.
        if len(winners) != 1:
            raise ValueError('Round must have one displayed winner')
        i = winners[0]
        winner_side = side(squares[i])
        loser_side = {'attack': 'defense', 'defense': 'attack'}.get(winner_side, '')
        sides = [loser_side, loser_side]; sides[i] = winner_side
        scores = col.get('title', '').split('-')
        icon = squares[i].select_one('img')
        rows.append(dict(match_id=m['match_id'], map_id=m['map_id'], round_number=rnd,
                         winner_team_id=m[f'team{i+1}_id'], team1_side=sides[0], team2_side=sides[1],
                         win_condition=Path(icon.get('src', '')).stem if icon else '',
                         team1_score_after=number(scores[0]) if len(scores) == 2 else None,
                         team2_score_after=number(scores[1]) if len(scores) == 2 else None))
    return rows


def parse_economy(game, m):
    rows = []
    for cell in game.select('table.mod-econ td'):
        rnd = number(text(cell.select_one('.round-num')))
        if rnd is None:
            continue
        squares, banks = cell.select('.rnd-sq'), cell.select('.bank')
        if len(squares) != 2 or len(banks) != 2:
            raise ValueError('Unsupported economy round cells')
        winner = next((i for i, sq in enumerate(squares) if 'mod-win' in sq.get('class', [])), None)
        if winner is None and all(number(sq.get('title', '')) is None for sq in squares):
            continue
        for i, sq in enumerate(squares):
            shown_side = side(sq)
            if not shown_side and winner is not None:
                shown_side = {'attack': 'defense', 'defense': 'attack'}.get(side(squares[winner]), '')
            rows.append(dict(match_id=m['match_id'], map_id=m['map_id'], round_number=rnd,
                             team_id=m[f'team{i+1}_id'], loadout_value=number(sq.get('title', '')),
                             bank_display=text(banks[i]), buy_category_display=text(sq),
                             round_win=int('mod-win' in sq.get('class', [])), side=shown_side))
    return rows


def performance_team_logos(soup):
    return {source_id(a.get('href',''),'team'):a.select_one('img').get('src','')
            for a in soup.select('.match-header-vs a.match-header-link') if a.select_one('img')}


def parse_performance(game, m, players, team_logos=None, identity_audit=None):
    # Performance has no player links. Join only within this map using exact
    # handle AND tag; refuse non-unique matches instead of lifetime name joins.
    rows = []
    for table in game.select('table.mod-adv-stats'):
        labels = [text(h) for h in table.select('tr')[0].select('th')]
        for tr in table.select('tr')[1:]:
            cells = tr.select('td')
            node = cells[0].select_one('.team > div') if cells else None
            if node is None or len(cells) != len(labels):
                raise ValueError('Unsupported performance table')
            handle = ' '.join(str(s).strip() for s in node.find_all(string=True, recursive=False)).strip()
            tag = text(node.select_one('.team-tag'))
            found = [p for p in players if p['map_id'] == m['map_id'] and p['handle'] == handle
                     and p['team_tag_at_match'] == tag]
            rule='exact_map_handle_and_tag'
            if len(found)!=1 and team_logos:
                # Some performance tags refer to the parent club (MIBR) while
                # the actual map team is its academy (MIBR.AC). A uniquely
                # matching match-header logo plus local name AND agent supplies
                # independent team evidence without guessing tag aliases.
                logo=tr.select_one('img.team-logo')
                matched=[tid for tid,src in team_logos.items() if logo and src==logo.get('src')]
                agent=cells[1].select_one('img') if len(cells)>1 else None
                shown_agent=Path(agent.get('src','')).stem if agent else ''
                if len(matched)==1 and shown_agent:
                    def local_handle(value):
                        return re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',value).casefold())
                    key=local_handle(handle)
                    found=[p for p in players if key and p['map_id']==m['map_id'] and p['team_id']==matched[0]
                           and local_handle(p['handle'])==key and p['agent']==shown_agent]
                    rule='unique_match_team_logo_local_handle_and_agent'
            if len(found) != 1:
                raise ValueError(f'Unresolved performance identity: {handle} {tag}')
            p = found[0]
            if identity_audit is not None:
                identity_audit.append(dict(match_id=m['match_id'],map_id=m['map_id'],vlr_player_id=p['vlr_player_id'],
                                           performance_handle=handle,performance_tag=tag,overview_handle=p['handle'],
                                           overview_tag=p['team_tag_at_match'],team_id=p['team_id'],join_rule=rule))
            row = dict(match_id=m['match_id'], map_id=m['map_id'], vlr_player_id=p['vlr_player_id'],
                       team_id=p['team_id'])
            for label, cell in zip(labels, cells):
                if label not in PERF_COLS:
                    continue
                sq = cell.select_one('.stats-sq')
                # Ignore hidden hover details (round numbers and victim names).
                direct = ''.join(str(s) for s in sq.find_all(string=True, recursive=False)).strip() if sq else ''
                row[PERF_COLS[label]] = number(direct)
            rows.append(row)
    return rows


def map_context(soup, game, m):
    header = game.select_one('.vm-stats-game-header')
    teams = header.select('.team') if header else []
    row = {k: m[k] for k in ['match_id', 'map_id', 'event_id', 'played_at_utc', 'patch', 'source_url', 'source_sha256', 'retrieved_at_utc']}
    row.update(event_stage=text(soup.select_one('.match-header-event-series')),
               veto_note=text(soup.select_one('.match-header-note')),
               map_duration_display=text(game.select_one('.map-duration')),
               map_picker_slot='', team1_start_side='', team2_start_side='',
               lan_online_status='unverified', coach_status='unverified')
    picked = game.select_one('.picked')
    if picked:
        row['map_picker_slot'] = next((i for i in [1, 2] if f'mod-{i}' in picked.get('class', [])), '')
    for i, team in enumerate(teams[:2], 1):
        displayed = team.select('span.mod-t, span.mod-ct')
        row[f'team{i}_start_side'] = side(displayed[0]) if displayed else ''
        for value in displayed:
            row[f'team{i}_{side(value)}_rounds_won'] = number(text(value))
    return row


def collect(args):
    code_at_start={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
                   for name in ['collect_vlr_research.py','collect_vlr_war_history.py']}
    manifest = json.loads(args.manifest.read_text())
    cache = Cache(args.cache, args.offline, args.delay)
    output = args.output; output.mkdir(parents=True, exist_ok=True)
    if not args.resume:
        (output/'event_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cache.get(HOST + '/robots.txt')
    for event in manifest['events']:
        if event.get('discovery_url'):
            cache.get(event['discovery_url'])
    events, stats, issues, contexts, coverage = [], [], [], [], []
    if args.resume:
        if json.loads((output/'event_manifest.json').read_text())!=manifest:
            raise ValueError('Resume manifest differs from the existing snapshot.')
        prior=read_records(output/'events.csv')
        if [str(e['event_id']) for e in manifest['events'][:len(prior)]] != [e['event_id'] for e in prior]:
            raise ValueError('Completed events are not the selected manifest prefix.')
        events=resume_checkpoint(output)
        issues=read_records(output/'collection_issues.csv')
        contexts=read_records(output/'map_context.csv');coverage=read_records(output/'tab_coverage.csv')
        cache.sources.update({r['source_url']:r for r in read_records(output/'sources.csv')})
        for spec in manifest['events'][:len(events)]:
            soup,src=cache.get(f"{HOST}/event/stats/{spec['event_id']}?min_rounds=0")
            if text(soup.select_one('h1'))!=spec['name']:raise ValueError('Resume event title differs')
            rows=parse_event_stats(soup,spec,src)
            for r in rows:r['season']=spec['season']
            stats.extend(rows)
        print(f'Resuming after {len(events)} checkpointed events',flush=True)
    streams, writers = {}, {}
    def emit(name, rows, fields=None):
        if not rows and fields is None:
            return
        if name not in writers:
            exists=args.resume and (output/name).exists() and (output/name).stat().st_size>0
            streams[name] = (output / name).open('a' if exists else 'w', newline='', encoding='utf-8')
            fields = fields or list(rows[0])
            if exists:
                with (output/name).open(newline='',encoding='utf-8') as f:prior_fields=next(csv.reader(f))
                if fields!=prior_fields:raise ValueError('Resume table schema changed: '+name)
            writers[name] = csv.DictWriter(streams[name], fieldnames=fields, lineterminator='\n')
            if not exists:writers[name].writeheader()
        writers[name].writerows(rows); streams[name].flush()
    emit('round_outcomes.csv', [], ROUND_FIELDS)
    emit('round_economy.csv', [], ECON_FIELDS)
    emit('player_map_performance.csv', [], ['match_id','map_id','vlr_player_id','team_id', *PERF_COLS.values()])
    # Start fresh outputs on a rebuild; immutable cache makes restarts reusable.
    if not args.resume:
        for name in ['map_outcomes.csv', 'player_map_stats.csv','collection_receipt.json','collection_checkpoint.json','collection_resumes.json']:
            (output / name).unlink(missing_ok=True)
    try:
        for spec in manifest['events'][len(events):]:
            event = dict(spec, stats_rows=0, matches_listed=0, matches_parsed=0, map_rows=0)
            eid = spec['event_id']
            try:
                soup, src = cache.get(f'{HOST}/event/stats/{eid}?min_rounds=0')
                if text(soup.select_one('h1')) != spec['name']:
                    raise ValueError(f"Unexpected event title: {text(soup.select_one('h1'))}")
                observations = parse_event_stats(soup, event, src)
                for r in observations:
                    r['season'] = spec['season']
                stats.extend(observations); event['stats_rows'] = len(observations)
                if not observations:
                    issues.append(dict(kind='no_event_stats', source_url=src['source_url'], detail=spec['name']))
                soup, _ = cache.get(f'{HOST}/event/matches/{eid}/?group=all')
                if soup.select('a.btn.mod-page'):
                    raise ValueError('Paginated match list requires explicit handling')
                links = list(dict.fromkeys(HOST+a['href'] for a in soup.select('a.match-item[href]')))
                event['matches_listed'] = len(links)
                for url in links:
                    try:
                        match_sections = SoupStrainer(class_=re.compile(r'^(?:vm-stats|match-header)'))
                        soup, src = cache.get(url, parse_only=match_sections)
                        maps, players, status = parse_match(soup, event, src, manifest['as_of_date'], manifest['start_date'])
                        if status != 'parsed':
                            issues.append(dict(kind=status, source_url=url, detail=spec['name'])); continue
                        emit('map_outcomes.csv', maps); emit('player_map_stats.csv', players)
                        event['matches_parsed'] += 1; event['map_rows'] += len(maps)
                        games = {g['data-game-id']: g for g in soup.select('.vm-stats-game[data-game-id]')}
                        for m in maps:
                            g = games[m['map_id']]
                            contexts.append(map_context(soup, g, m))
                            rr = parse_rounds(g, m); emit('round_outcomes.csv', rr)
                            coverage.append(dict(match_id=m['match_id'], map_id=m['map_id'], tab='overview_rounds',
                                                 rows=len(rr), source_url=src['source_url'], source_sha256=src['sha256'], retrieved_at_utc=src['retrieved_at_utc']))
                        for tab, filename, parser in [('economy','round_economy.csv',parse_economy),
                                                      ('performance','player_map_performance.csv',parse_performance)]:
                            try:
                                ts, provenance = cache.get(url.rstrip('/')+'/?tab='+tab, parse_only=match_sections)
                                gs = {g['data-game-id']: g for g in ts.select('.vm-stats-game[data-game-id]')}
                                for m in maps:
                                    g = gs.get(m['map_id'])
                                    parsed = parser(g, m, players) if tab == 'performance' and g else parser(g, m) if g else []
                                    emit(filename, parsed)
                                    coverage.append(dict(match_id=m['match_id'], map_id=m['map_id'], tab=tab, rows=len(parsed),
                                                         source_url=provenance['source_url'], source_sha256=provenance['sha256'], retrieved_at_utc=provenance['retrieved_at_utc']))
                            except (ValueError, OSError, urllib.error.URLError,http.client.HTTPException) as e:
                                issues.append(dict(kind=tab+'_failed', source_url=url, detail=str(e)))
                    except (ValueError, OSError, urllib.error.URLError,http.client.HTTPException) as e:
                        issues.append(dict(kind='match_failed', source_url=url, detail=str(e)))
            except (ValueError, OSError, urllib.error.URLError,http.client.HTTPException) as e:
                issues.append(dict(kind='event_failed', source_url=f'{HOST}/event/{eid}', detail=str(e)))
            events.append(event)
            print(f"{eid} {spec['name']}: {event['map_rows']} maps ({event['matches_parsed']}/{event['matches_listed']} matches)", flush=True)
            write_csv(output / 'events.csv', events)
            write_csv(output / 'collection_issues.csv', issues, ['kind','source_url','detail'])
            write_csv(output / 'sources.csv', [cache.sources[u] for u in sorted(cache.sources)])
            write_csv(output / 'map_context.csv', contexts)
            write_csv(output / 'tab_coverage.csv', coverage)
            names=['events.csv','collection_issues.csv','sources.csv','map_context.csv','tab_coverage.csv']
            checkpoint=dict(completed_events=len(events),
                            scope='Raw collection checkpoint before offline identity/side enrichment',
                            manifest_sha256=hashlib.sha256((output/'event_manifest.json').read_bytes()).hexdigest(),
                            snapshot_sha256={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in names})
            tmp=output/'collection_checkpoint.json.tmp';tmp.write_text(json.dumps(checkpoint,indent=2)+'\n')
            tmp.replace(output/'collection_checkpoint.json')
        write_csv(output / 'player_event_stats.csv', stats)
        (output / 'event_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        receipt=dict(collector_version=3,python_version=platform.python_version(),
                     dependencies={name:importlib.metadata.version(name) for name in ['beautifulsoup4','lxml','numpy','scipy']},
                     source_cache_metadata_note='sources.csv parser_version is the immutable cache acquisition version; current parser code hashes are recorded here.',
                     code_sha256=code_at_start,
                     code_hash_capture='Files captured at collector startup, before cache reads or requests.',
                     manifest_sha256=hashlib.sha256((output/'event_manifest.json').read_bytes()).hexdigest(),
                     events=len(events),sources=len(cache.sources),issues=len(issues))
        (output/'collection_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    finally:
        for f in streams.values():
            f.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,default=ROOT/'data/research/war-history/event_manifest.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/research/war-history')
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--offline',action='store_true')
    p.add_argument('--resume',action='store_true',help='Resume an unfinished event checkpoint; discard partial next-event rows.')
    p.add_argument('--delay',type=float,default=.6)
    args = p.parse_args()
    if args.delay < .5:
        p.error('--delay must be >=0.5')
    collect(args)
