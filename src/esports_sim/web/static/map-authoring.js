/* Pure geometry helpers shared by the Studio tools and their regression checks. */
(function(root) {
  const rectangle = (a, b) => {
    const x0 = Math.min(a[0], b[0]), x1 = Math.max(a[0], b[0]);
    const y0 = Math.min(a[1], b[1]), y1 = Math.max(a[1], b[1]);
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  };
  const isRectangle = pts => pts.length === 4 &&
    pts.every((p, i) => p[0] === pts[(i + 1) % 4][0] || p[1] === pts[(i + 1) % 4][1]) &&
    new Set(pts.map(p => p[0])).size === 2 && new Set(pts.map(p => p[1])).size === 2;
  const snapPoint = (p, step) => p.map(v => step > 0 ? Math.round(v / step) * step : Math.round(v * 100) / 100);
  // Keep the dragged corner index stable even when it crosses its opposite.
  function resizeRectangle(pts, index, point) {
    const opposite = pts[(index + 2) % 4];
    if (point[0] === opposite[0] || point[1] === opposite[1]) return pts;
    const old = pts[index];
    return pts.map(p => [p[0] === old[0] ? point[0] : p[0], p[1] === old[1] ? point[1] : p[1]]);
  }
  function nextId(doc, prefix) {
    const ids = new Set(['walkable_surfaces', 'semantic_zones', 'props', 'walls', 'traversal_links']
      .flatMap(key => (doc[key] || []).map(e => e.id)));
    let n = 1;
    while (ids.has(`${prefix}_${n}`) || ids.has(`surf_${prefix}_${n}`)) n++;
    return `${prefix}_${n}`;
  }
  function floorOutline(surface) {
    const core = surface.polygon;
    if (!isRectangle(core)) return core.map((p,i)=>[p,core[(i+1)%core.length]]);
    const rectangles = [{x:Math.min(...core.map(p=>p[0])), y:Math.min(...core.map(p=>p[1])),
      w:Math.max(...core.map(p=>p[0]))-Math.min(...core.map(p=>p[0])),
      h:Math.max(...core.map(p=>p[1]))-Math.min(...core.map(p=>p[1]))}, ...(surface.floor_extensions || [])];
    const xs = [...new Set(rectangles.flatMap(r=>[r.x,r.x+r.w]))].sort((a,b)=>a-b);
    function merge(intervals) {
      const result=[];
      for (const interval of intervals.sort((a,b)=>a[0]-b[0] || a[1]-b[1])) {
        const last=result[result.length-1];
        if (last && interval[0]<=last[1]+1e-8) last[1]=Math.max(last[1],interval[1]);
        else result.push([...interval]);
      }
      return result;
    }
    const at = x => merge(rectangles.filter(r=>r.x<x && x<r.x+r.w).map(r=>[r.y,r.y+r.h]));
    const segments=[], horizontals=new Map();
    const horizontal=(y,a,b)=> { if (!horizontals.has(y)) horizontals.set(y,[]); horizontals.get(y).push([a,b]); };
    let left=[];
    for (let i=0;i<xs.length;i++) {
      const x=xs[i], right=i+1<xs.length ? at((x+xs[i+1])/2) : [];
      const ys=[...new Set([...left,...right].flat())].sort((a,b)=>a-b);
      for (let j=0;j+1<ys.length;j++) {
        const y=(ys[j]+ys[j+1])/2;
        if (left.some(([a,b])=>a<y && y<b)!==right.some(([a,b])=>a<y && y<b))
          segments.push([[x,ys[j]],[x,ys[j+1]]]);
      }
      if (i+1<xs.length) for (const [a,b] of right) { horizontal(a,x,xs[i+1]); horizontal(b,x,xs[i+1]); }
      left=right;
    }
    for (const [y,intervals] of horizontals) for (const [a,b] of merge(intervals)) segments.push([[a,y],[b,y]]);
    return segments;
  }
  const api = { rectangle, isRectangle, resizeRectangle, snapPoint, nextId, floorOutline };
  root.MapAuthoring = api;
  if (typeof module !== 'undefined') module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
