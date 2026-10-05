"""Trace six new Studio layouts from extracted minimaps and game callout coordinates.

Writes revision-safe drafts through Map MCP; never publishes. Cached source
assets and their provenance are retained for reproducibility and review.
Existing drafts are preserved. Source coordinates are centimetres; floor is
quantized to 0.5 map-unit rectangles in the project's 0-100 coordinate frame,
with routes constrained to adjacent owners.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import deque
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.request

import numpy as np
from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from build_layout_drafts import call
from esports_sim.registry import map_workbench
from esports_sim.registry.map_reference import GRID_STEP, merge_cells
from esports_sim.schemas.studio import MapStudioDocumentV1

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['pearl', 'fracture', 'corrode', 'abyss', 'breeze', 'sunset']
ROTATIONS = {n: ('ccw' if n in ('corrode', 'abyss') else '180') for n in NAMES}
NEIGHBORS = ((-1, 0), (0, -1), (0, 1), (1, 0))


def components(mask):
    remaining = mask.copy()
    result = []
    rows, cols = mask.shape
    for y, x in zip(*np.nonzero(mask)):
        if not remaining[y, x]: continue
        remaining[y, x] = False
        queue, cells = deque([(y, x)]), []
        while queue:
            y, x = queue.popleft(); cells.append((y, x))
            for dy, dx in NEIGHBORS:
                ny, nx = y+dy, x+dx
                if 0 <= ny < rows and 0 <= nx < cols and remaining[ny, nx]:
                    remaining[ny, nx] = False; queue.append((ny, nx))
        result.append(cells)
    return sorted(result, key=lambda c: (-len(c), c[0]))


def orient(u, v, rotation):
    return (v, 1-u) if rotation == 'ccw' else (1-u, 1-v)


def nearest(mask, point):
    ys, xs = np.nonzero(mask)
    return tuple(int(v) for v in (ys[np.argmin((xs-point[0])**2+(ys-point[1])**2)],
                                  xs[np.argmin((xs-point[0])**2+(ys-point[1])**2)]))


def point(cell):
    return ((cell[1]+.5)*GRID_STEP, (cell[0]+.5)*GRID_STEP)


def largest_core(mask):
    ys, xs = np.nonzero(mask)
    x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(max(xs))+1, int(max(ys))+1
    heights = np.zeros(x1-x0, dtype=int)
    best_area, best = 0, None
    for y in range(y0, y1):
        heights = np.where(mask[y, x0:x1], heights+1, 0)
        stack = []
        for i in range(len(heights)+1):
            height = int(heights[i]) if i < len(heights) else 0
            start = i
            while stack and stack[-1][1] > height:
                left, h = stack.pop(); area = (i-left)*h
                if area > best_area:
                    best_area, best = area, (x0+left, y+1-h, x0+i, y+1)
                start = left
            if height and (not stack or stack[-1][1] < height): stack.append((start, height))
    return best


def anchored_core(mask, seed):
    """Largest symmetric rectangle at the measured callout, not a remote lobe."""
    y,x=seed; hw=0
    while x-hw-1>=0 and x+hw+1<mask.shape[1] and mask[y,x-hw-1] and mask[y,x+hw+1]: hw+=1
    best=(x-hw,y,x+hw+1,y+1); area=2*hw+1
    for hh in range(1,min(y,mask.shape[0]-y-1)+1):
        if not mask[y-hh,x] or not mask[y+hh,x]: break
        while hw>0 and not (mask[y-hh,x-hw:x+hw+1].all() and mask[y+hh,x-hw:x+hw+1].all()): hw-=1
        candidate=(2*hw+1)*(2*hh+1)
        if candidate>area: area=candidate;best=(x-hw,y-hh,x+hw+1,y+hh+1)
    return best


def clear_segment(mask,a,b):
    dy,dx=b[0]-a[0],b[1]-a[1]; y,x=a[0]+.5,a[1]+.5
    cuts={0.,1.}
    if dx:
        cuts.update((v-x)/dx for v in range(min(a[1],b[1])+1,max(a[1],b[1])+1))
    if dy:
        cuts.update((v-y)/dy for v in range(min(a[0],b[0])+1,max(a[0],b[0])+1))
    ordered=sorted(cuts)
    return all(mask[int(y+dy*(lo+hi)/2),int(x+dx*(lo+hi)/2)] for lo,hi in zip(ordered,ordered[1:]))


def polygon(box, inset=0):
    x0, y0, x1, y1 = box
    return [(x0+inset, y0+inset), (x1-inset, y0+inset), (x1-inset, y1-inset), (x0+inset, y1-inset)]


def contour(mask):
    # Exterior of the largest connected olive region. Interior holes remain
    # non-walkable in the physical floor, independently of this semantic overlay.
    edges = set()
    for y, x in zip(*np.nonzero(mask)):
        for a, b in [((x,y),(x+1,y)), ((x+1,y),(x+1,y+1)), ((x+1,y+1),(x,y+1)), ((x,y+1),(x,y))]:
            if (b,a) in edges: edges.remove((b,a))
            else: edges.add((a,b))
    loops = []
    while edges:
        a, b = min(edges); edges.remove((a,b)); loop=[a,b]
        while b != a:
            following=sorted(e for e in edges if e[0] == b)
            if not following: break
            e=following[0]; edges.remove(e); b=e[1]; loop.append(b)
        if loop[-1] == a: loops.append(loop[:-1])
    loop = max(loops, key=lambda l: abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(l,l[1:]+l[:1]))))
    return [(x*GRID_STEP,y*GRID_STEP) for i,(x,y) in enumerate(loop)
            if (loop[i-1][0]-x)*(loop[(i+1)%len(loop)][1]-y) != (loop[i-1][1]-y)*(loop[(i+1)%len(loop)][0]-x)]


def route(mask, start, end):
    rows, cols = mask.shape
    prev={start:None}; distance={start:0}; queue=[(0,0,start)]
    while queue:
        _, cost, cur = heapq.heappop(queue)
        if cur == end: break
        if cost != distance[cur]: continue
        for dy,dx in NEIGHBORS:
            nxt=(cur[0]+dy,cur[1]+dx)
            if not (0 <= nxt[0] < rows and 0 <= nxt[1] < cols and mask[nxt]): continue
            nc=cost+1
            if nc < distance.get(nxt,math.inf):
                distance[nxt]=nc; prev[nxt]=cur
                heapq.heappush(queue,(nc+abs(nxt[0]-end[0])+abs(nxt[1]-end[1]),nc,nxt))
    if end not in prev: raise ValueError(f'No on-floor route from {start} to {end}')
    cells=[end]
    while cells[-1] != start: cells.append(prev[cells[-1]])
    cells.reverse()
    # Pull straight walking lanes through visible floor. Every crossed cell
    # is checked, so diagonal stairs are shortened without cutting corners.
    pulled=[cells[0]];i=0
    while i<len(cells)-1:
        j=len(cells)-1
        while j>i+1 and not clear_segment(mask,cells[i],cells[j]): j-=1
        pulled.append(cells[j]);i=j
    return [point(c) for c in pulled]


def construct(source, scratch):
    name=source['displayName'].lower(); rotation=ROTATIONS[name]
    raw=scratch / f'{name}-api.png'
    pinned=ROOT/'assets/maps/references'/f'{name}-source.png'
    if not raw.exists() and pinned.exists(): raw.write_bytes(pinned.read_bytes())
    if not raw.exists(): urllib.request.urlretrieve(source['displayIcon'], raw)
    provenance=ROOT/'assets/maps/references'/f'{name}-source.json'
    if provenance.exists() and hashlib.sha256(raw.read_bytes()).hexdigest()!=json.loads(provenance.read_text())['source_sha256']:
        raise ValueError(f'{name}: source pixels changed; calibrate a new snapshot rather than silently overwrite')
    im=Image.open(raw).convert('RGBA').transpose(Image.Transpose.ROTATE_90 if rotation=='ccw' else Image.Transpose.ROTATE_180)
    extent=100.0
    size=int(round(extent/GRID_STEP)); indices=((np.arange(size)+.5)/size*im.width).astype(int)
    pixels=np.asarray(im)[indices[:,None],indices]
    floor=(pixels[:,:,3]>200)&(pixels[:,:,0]>70)&(pixels[:,:,0]<200)
    all_components=components(floor)
    # Tiny disconnected decoration is not a traversable room. Abyss's
    # separate danger ledge remains explicitly recorded in the provenance.
    connected=np.zeros_like(floor); connected[tuple(np.array(all_components[0]).T)]=True
    floor=connected
    olive=floor & (pixels[:,:,0].astype(int)-pixels[:,:,2]>20) & (np.abs(pixels[:,:,0].astype(int)-pixels[:,:,1])<5)
    ref_dir=ROOT/'assets/maps/references'; ref_dir.mkdir(parents=True,exist_ok=True)
    # Preserve the original pixels for independent registration checks.
    traced=np.full((size,size,3),(30,12,27),dtype=np.uint8)
    traced[floor]=(118,118,118); traced[olive]=(152,152,118)
    target=ref_dir/f'{name}.png'
    im.save(target)
    Image.fromarray(traced).save(scratch/f'{name}-trace-mask.png')
    (ref_dir/f'{name}-source.png').write_bytes(raw.read_bytes())
    anchors=[]
    for c in source['callouts']:
        sr=c['superRegionName']; label=f"{sr} {c['regionName']}"
        zid=re.sub(r'[^a-z0-9]+','_',label.lower()).strip('_').replace('attacker_side_spawn','attacker_spawn').replace('defender_side_spawn','defender_spawn')
        u,v=orient(c['location']['y']*source['xMultiplier']+source['xScalarToAdd'],
                   c['location']['x']*source['yMultiplier']+source['yScalarToAdd'],rotation)
        seed=nearest(floor,(u*size-.5,v*size-.5))
        # Pearl's API places Shops and Club at exactly the same x/y on
        # different storeys. Keep one physical partition and both names.
        duplicate=next((a for a in anchors if a['seed']==seed),None)
        if duplicate:
            duplicate['label']+=' / '+label; duplicate['aliases'].append(c); continue
        site=sr.lower() if sr.lower() in ('a','b','mid') else 'none'
        kind='spawn' if zid in ('attacker_spawn','defender_spawn') else ('site' if c['regionName']=='Site' else 'callout')
        tactical= ('attacker_spawn' if zid=='attacker_spawn' else 'defender_spawn' if zid=='defender_spawn' else
                  'site' if kind=='site' else 'mid' if sr=='Mid' else
                  'defender_side' if sr=='Defender Side' or c['regionName'] in ('Tower','Back','Link','Secret','Flowers','Hall','Security','Water','Records','Canteen','Generator','Arches','Window') else 'attacker_side')
        # Map-specific labels with a common word have different tactical roles.
        if name=='fracture' and zid in ('a_link','b_link','a_drop','b_tower'): tactical='defender_side'
        if name=='fracture' and zid in ('a_hall','a_dish','a_gate','attacker_side_bridge'): tactical='attacker_side'
        if name=='breeze' and zid=='b_window': tactical='attacker_side'
        defensive = {
            'pearl': {'a_dugout','b_screen','b_tunnel'},
            'fracture': {'b_generator','b_canteen'},
            'corrode': {'a_crane','a_elbow','a_pocket','b_arch','b_elbow','b_tower'},
            'abyss': {'a_bridge','a_vent'},
            'breeze': {'a_pyramids','b_wall','b_tunnel'},
            'sunset': {'b_boba','b_market','a_alley'},
        }
        if zid in defensive[name]: tactical='defender_side'
        anchors.append(dict(id=zid,label=label,seed=seed,source=c,aliases=[],site=site,kind=kind,tactical=tactical))
    owners=np.full(floor.shape,-1,dtype=int)
    for i,a in enumerate(anchors): owners[a['seed']]=i
    sites=[i for i,a in enumerate(anchors) if a['kind']=='site']
    plant_sites=np.full(floor.shape,-1,dtype=int)
    for component in components(olive):
        if len(component)*GRID_STEP**2 < .5: continue
        center=np.array(component).mean(axis=0)
        i=min(sites,key=lambda i:sum((center-np.array(anchors[i]['seed']))**2))
        plant_sites[tuple(np.array(component).T)]=i
    # Semantic plant extents never steal the bridge, tower or other physical
    # callout's floor. Each overlay references its existing supporting floor.
    queue=deque(zip(*np.nonzero(owners>=0)))
    while queue:
        y,x=queue.popleft()
        for dy,dx in NEIGHBORS:
            ny,nx=y+dy,x+dx
            if 0 <= ny < size and 0 <= nx < size and floor[ny,nx] and owners[ny,nx]<0:
                owners[ny,nx]=owners[y,x];queue.append((ny,nx))
    # A site seed can wrap around an obstacle. Keep disconnected pieces as
    # explicit annex rooms, rather than hiding disconnected floor extensions.
    for i,a in list(enumerate(anchors)):
        cs=components(owners==i)
        for j,cells in enumerate(cs):
            if a['seed'] in cells: continue
            k=len(anchors); owners[tuple(np.array(cells).T)]=k
            anchors.append({**a,'id':f"{a['id']}_annex_{j+1}",'label':f"{a['label']} Annex {j+1}",'seed':cells[0],'kind':'site' if a['kind']=='site' else 'callout','aliases':[]})
    surfaces=[]; zones=[]; centers=[]
    baseline=min(a['source']['location']['z'] for a in anchors)
    for i,a in enumerate(anchors):
        selected=owners==i; box=anchored_core(selected,a['seed']);x0,y0,x1,y1=box
        core=tuple(v*GRID_STEP for v in box)
        remaining=selected.copy();remaining[y0:y1,x0:x1]=False
        # Cell centers (including even-width cores) are exact on the floor.
        center=(int((y0+y1-1)//2),int((x0+x1-1)//2));centers.append(center)
        # Center the navigational core on a cell center to avoid a waypoint
        # shift at even-width rectangles. These trim strips remain floor.
        cx,cy=point(center);cw=min(cx-core[0],core[2]-cx)*2;ch=min(cy-core[1],core[3]-cy)*2
        core=(cx-cw/2,cy-ch/2,cx+cw/2,cy+ch/2)
        # Include the full initial box as an extension if the centered core trims it.
        extensions=merge_cells(remaining,0,0)
        if core != tuple(v*GRID_STEP for v in box):
            extensions.append(dict(x=x0*GRID_STEP,y=y0*GRID_STEP,w=(x1-x0)*GRID_STEP,h=(y1-y0)*GRID_STEP))
        sid='surf_'+a['id'];elevation=round((a['source']['location']['z']-baseline)*abs(source['xMultiplier'])*extent,2)
        surfaces.append(dict(id=sid,polygon=polygon(core),floor_extensions=extensions,elevation=elevation))
        ys,xs=np.nonzero(selected)
        semantic_extent=selected | (plant_sites==i) if a['kind']=='site' else selected
        by,bx=np.nonzero(semantic_extent)
        bounds=(min(bx)*GRID_STEP-.01,min(by)*GRID_STEP-.01,(max(bx)+1)*GRID_STEP+.01,(max(by)+1)*GRID_STEP+.01)
        zones.append(dict(id=a['id'],display_name=a['label'],kind=a['kind'],polygon=polygon(bounds) if a['kind']=='site' else polygon(core),
                          surface_ids=[sid],label_position=point(a['seed']),site_id=a['site'],legacy_zone=a['tactical']))
    # A semantic planting area can span several named physical subrooms
    # (bridge/site/dugout). It must not create or reassign movement floor.
    for site_index in sites:
        for j,cells in enumerate(components(plant_sites==site_index)):
            if len(cells)*GRID_STEP**2<.5: continue
            site_id=anchors[site_index]['site']
            plant_mask=np.zeros_like(floor);plant_mask[tuple(np.array(cells).T)]=True
            support=['surf_'+anchors[k]['id'] for k in sorted(set(int(owners[c]) for c in cells))]
            bx0,by0,bx1,by1=largest_core(plant_mask)
            anchor=(int((by0+by1-1)//2),int((bx0+bx1-1)//2))
            zones.append(dict(id=f"{site_id}_plant_{j+1}",display_name=f"{site_id.upper()} Plant {j+1}",kind='plant',
                              polygon=contour(plant_mask),surface_ids=support,label_position=point(anchor),site_id=site_id))
    pairs=set()
    for y,x in zip(*np.nonzero(floor)):
        for dy,dx in ((0,1),(1,0)):
            if y+dy<size and x+dx<size and floor[y+dy,x+dx] and owners[y,x]!=owners[y+dy,x+dx]:
                pairs.add(tuple(sorted((int(owners[y,x]),int(owners[y+dy,x+dx])))))
    links=[]
    for i,j in sorted(pairs,key=lambda ij:(anchors[ij[0]]['id'],anchors[ij[1]]['id'])):
        path=route((owners==i)|(owners==j),centers[i],centers[j]);a,b=anchors[i]['id'],anchors[j]['id']
        links.append(dict(id=f'route_{a}_{b}',kind='ramp',from_pos=[*point(centers[i]),'surf_'+a],to_pos=[*point(centers[j]),'surf_'+b],
                          via=path[1:-1],include_endpoints_in_path=True,noise_radius=0,start_closed_prob=0))
    if name=='fracture':
        a=next(a for a in anchors if a['id']=='attacker_spawn');b=next(a for a in anchors if a['id']=='attacker_side_bridge')
        # Two opposing one-way ropes visible in the original icon. Docking
        # positions are measured from its white cable x / floor lip y pixels.
        ai,bi=anchors.index(a),anchors.index(b)
        for link_id,raw_x,reverse in [('central_zipline',493,False),('central_zipline_return',529,True)]:
            u=1-raw_x/1024
            south=point(nearest(owners==ai,(u*size-.5,(1-778/1024)*size-.5)))
            north=point(nearest(owners==bi,(u*size-.5,(1-200/1024)*size-.5)))
            start=[*south,'surf_'+a['id']];end=[*north,'surf_'+b['id']]
            links.append(dict(id=link_id,kind='rope',runtime_enabled=False,
                              description=f"{'Southbound' if reverse else 'Northbound'} attacker zipline over the void. Recorded only: the current motor has no zipline transport.",
                              from_pos=end if reverse else start,to_pos=start if reverse else end,via=[],noise_radius=25,start_closed_prob=0))
    doc=MapStudioDocumentV1(id=f'{name}-layout-v2',display_name=f'{name.title()} - Layout v2',movement_model='free',sites=['a','b'],
                           reference=dict(image_path=f'/assets/maps/references/{name}.png',description=f'{name.title()} - extracted game minimap/callouts, retrieved 2026-10-04; floor excludes white wall marks',
                                          source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),rotation=rotation,floor_color_max=200,width=extent,height=extent),
                           links_define_adjacency=True,walkable_surfaces=surfaces,semantic_zones=zones,traversal_links=links)
    manifest=dict(source_url='https://valorant-api.com/v1/maps',asset_url=source['displayIcon'],retrieved='2026-10-04',source_sha256=doc.reference.source_sha256,
                  map_uuid=source['uuid'],rotation=rotation,metres_per_source_unit=.01,
                  map_units_per_source_unit=abs(source['xMultiplier'])*extent,grid_step=GRID_STEP,
                  transform={k:source[k] for k in ('xMultiplier','yMultiplier','xScalarToAdd','yScalarToAdd')},
                  original_callouts=source['callouts'],omitted_disconnected_floor_areas=[len(c)*GRID_STEP**2 for c in all_components[1:]],
                  aliases=[a for a in anchors if a['aliases']],
                  limitations=['Callout z is a coarse floor elevation; vertical overlap and ramps are approximated.',
                               'Minimap does not supply reliable crate height; cover props are not surveyed.',
                               'Death drops and jump/zipline traversal need engine support; no false floor is added.'])
    (ref_dir/f'{name}-source.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    _,_,errors=map_workbench.validate_document(doc)
    if errors: raise ValueError(f'{name}: {errors[:25]}')
    return doc


async def build(names, refine=False):
    scratch=ROOT/'runs/layout-trace/sources';scratch.mkdir(parents=True,exist_ok=True)
    cache=ROOT/'runs/layout-trace/valorant-api-maps.json'
    sources=[]; missing=[]
    for name in names:
        manifest=ROOT/'assets/maps/references'/f'{name}-source.json'
        if manifest.exists():
            pinned=json.loads(manifest.read_text())
            sources.append({'displayName':name.title(),'uuid':pinned['map_uuid'],'displayIcon':pinned['asset_url'],
                            'callouts':pinned['original_callouts'],**pinned['transform']})
        else: missing.append(name)
    if missing:
        if not cache.exists(): urllib.request.urlretrieve('https://valorant-api.com/v1/maps',cache)
        sources.extend(s for s in json.loads(cache.read_text())['data'] if s['displayName'].lower() in missing)
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),ESPORTS_MAP_DATA_DIR=str(ROOT/'data'))
    params=StdioServerParameters(command=sys.executable,args=['-m','esports_sim.mcp.map_server'],env=env)
    async with stdio_client(params) as (read,write),ClientSession(read,write) as session:
        await session.initialize();await call(session,'get_map_schema',{})
        existing={m['id'] for m in (await call(session,'list_maps',{}))['maps']}
        for name in names:
            mid=f'{name}-layout-v2'
            if mid in existing and not refine: print(f'{mid}: preserving existing draft',flush=True);continue
            created=None
            if mid in existing:
                created=await call(session,'get_map',dict(map_id=mid))
                prior=json.loads((scratch/f'{mid}-review.json').read_text())
                if created['revision_hash']!=prior['revision_hash']:
                    raise ValueError(f'{mid}: draft changed since generation; preserve and reconcile the human edit')
            doc=construct(next(s for s in sources if s['displayName'].lower()==name),scratch)
            if created is None: created=await call(session,'create_map',dict(map_id=mid,display_name=doc.display_name,template='empty'))
            raw=doc.model_dump(mode='json')
            removals=[dict(element_type=typ,element_id=e['id']) for collection,typ in [('walkable_surfaces','surface'),('semantic_zones','zone'),('traversal_links','link')]
                      for e in created['document'][collection] if e['id'] not in {v['id'] for v in raw[collection]}]
            result=await call(session,'apply_map_patch',dict(map_id=mid,if_match_hash=created['revision_hash'],removals=removals,
                       metadata={k:raw[k] for k in ('reference','sites','attacker_spawn','defender_spawn','movement_model','links_define_adjacency')},
                       walkable_surfaces=raw['walkable_surfaces'],semantic_zones=raw['semantic_zones'],traversal_links=raw['traversal_links'],adjacency_overrides={}))
            if not result['validation']['valid']: raise ValueError(result['validation'])
            final=await call(session,'get_map',dict(map_id=mid))
            (scratch/f'{mid}-review.json').write_text(json.dumps(final,indent=2),encoding='utf-8')
            print(f'{mid}: {len(doc.walkable_surfaces)} rooms, {len(doc.traversal_links)} routes; revision {final["revision_hash"]}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--maps',nargs='+',choices=NAMES,default=NAMES)
    parser.add_argument('--refine-generated',action='store_true',help='Refine only drafts still matching their recorded generated revision')
    args=parser.parse_args();asyncio.run(build(args.maps,args.refine_generated))
