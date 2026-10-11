"""Project a pinned public Valorant-API snapshot into auditable agent roles."""
from __future__ import annotations

import gzip
import hashlib
import json

from collect_vlr_research import ROOT, normalize, write_csv


def main():
    data=ROOT/'data/research/war-history'
    body=gzip.decompress((data/'reference/valorant-agents.json.gz').read_bytes())
    source=json.loads((data/'reference/valorant-agent-source.json').read_text())
    if hashlib.sha256(body).hexdigest()!=source['sha256']:
        raise ValueError('Agent snapshot hash mismatch')
    rows=[]
    for agent in json.loads(body)['data']:
        role=agent.get('role')
        if not agent.get('isPlayableCharacter') or not role:continue
        role_name=role['displayName'].lower()
        if role_name not in {'controller','duelist','initiator','sentinel'}:
            raise ValueError('Unknown source role '+role_name)
        rows.append(dict(agent_key=normalize(agent['displayName']),display_name=agent['displayName'],
                         role=role_name,agent_uuid=agent['uuid'],role_uuid=role['uuid'],
                         source_url=source['source_url'],source_sha256=source['sha256'],retrieved_at_utc=source['retrieved_at_utc']))
    write_csv(data/'agent_role_reference.csv',sorted(rows,key=lambda r:r['agent_key']))
    print(f'{len(rows)} source-backed agent roles')


if __name__=='__main__':main()
