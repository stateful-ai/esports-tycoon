/* 2D match replay. Pure consumer of one event log — no sim logic here.
   New logs carry authoritative control-frame position/facing poles;
   round.move remains the route contract and old-log fallback. */

const MOVE_TICKS = 6;
const TICKS_PER_SEC = 2; // 1 tick = 0.5 s of game time
const UTIL_MARKER_TICKS = 8; // how long a utility marker lingers after use
const KILL_FLASH_TICKS = 3;  // how long the death ring lingers after a kill
const TRAIL_SPAN = 0.4;      // fraction of a move segment covered by the fading trail

let V = null; // active replay session

/* -- painted backdrop + agent helpers -------------------------------------- */

// Iso viewBox — MUST match scripts/render_map_guide.py's VIEWBOX and the
// painted-backdrop <image> box in drawStatic(). Guide pixels map linearly
// onto this rectangle, so the paint lands pixel-true under the SVG layers.
const ISO_VIEWBOX = [-110, -12, 220, 128];

// Per-map probe cache: mapId -> painted URL when the asset exists, else null.
// One <img> load decides it; absent files (404) fall through to the current
// geometry rendering unchanged.
const paintedCache = {};
function probePainted(mapId) {
  const url = `/assets/maps/painted/${mapId}.webp`;
  if (mapId in paintedCache) return Promise.resolve(paintedCache[mapId]);
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve((paintedCache[mapId] = url));
    img.onerror = () => resolve((paintedCache[mapId] = null));
    img.src = url;
  });
}

// Agent-forward identity. The serializer sends agent_id + agent_icon per
// player but no agent DISPLAY name, so derive it from the slug (title-cased);
// fall back to the icon URL slug if agent_id is ever absent.
function agentSlug(pid) {
  const p = V.players[pid];
  if (!p) return "";
  if (p.agent_id) return p.agent_id;
  return (p.agent_icon || "").split("/").pop().replace(/\.webp$/, "");
}
function agentName(pid) {
  const slug = agentSlug(pid);
  return slug
    ? slug.split(/[_\s]+/).map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(" ")
    : "";
}
function handleOf(pid) {
  return V.players[pid]?.handle ?? pid;
}
// Feed/ticker label: small agent icon + agent name (primary), player handle
// dimmed in parens (secondary) — e.g. "[icon] Jett (Vortex)".
function feedLabel(pid) {
  const name = agentName(pid);
  const handle = handleOf(pid);
  const src = V.players[pid]?.agent_icon;
  const icon = src
    ? `<img class="feed-agent" src="${src}" onerror="this.style.display='none'" alt="">`
    : "";
  if (!name) return `${icon}<b class="feed-name plink" data-pid="${pid}">${handle}</b>`;
  return `${icon}<b class="feed-name plink" data-pid="${pid}">${name}</b> <span class="muted feed-handle">(${handle})</span>`;
}

/* -- parsing ---------------------------------------------------------------- */

function parseReplay(data) {
  const rounds = [];
  let cur = null;
  let scoreA = 0, scoreB = 0;
  for (const e of data.events) {
    switch (e.type) {
      case "round.start":
        cur = {
          num: e.round_num, attacker: e.attacking_team_id,
          placements: {}, placeXY: {}, moves: {}, controls: {}, kills: [], utility: [],
          whiffs: [], comms: [],
          gimmicks: [], closedDoors: new Set(e.closed_doors || []),
          plant: null, defuse: null, end: null,
          scoreBefore: [scoreA, scoreB], maxTick: 1,
        };
        rounds.push(cur);
        break;
      case "round.move":
        if (!cur) break;
        if (e.from_callout === null) {
          cur.placements[e.player_id] = e.to_callout;
          if (e.waypoints?.length) cur.placeXY[e.player_id] = e.waypoints[0];
        } else {
          // New logs: emitted at move START with waypoints + arrive_tick
          // (a re-paced move emits again and supersedes). Legacy logs:
          // emitted at arrival, straight MOVE_TICKS window.
          const isNew = e.arrive_tick != null;
          (cur.moves[e.player_id] ??= []).push({
            start: isNew ? e.tick : e.tick - MOVE_TICKS,
            arrive: isNew ? e.arrive_tick : e.tick,
            from: e.from_callout,
            to: e.to_callout,
            pts: e.waypoints?.length >= 2 ? e.waypoints : null,
          });
          cur.maxTick = Math.max(cur.maxTick, isNew ? e.arrive_tick : e.tick);
        }
        break;
      case "round.control":
        if (!cur) break;
        (cur.controls[e.player_id] ??= []).push(e);
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.kill":
        cur.kills.push(e);
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.utility_used":
        cur.utility.push(e);
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.whiff":
        cur.whiffs.push(e);
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.comms":
        cur.comms.push(e);
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.gimmick":
        cur.gimmicks.push(e);
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.spike_plant":
        cur.plant = e;
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.spike_defuse":
        cur.defuse = e;
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.end":
        cur.end = e;
        cur.maxTick = Math.max(cur.maxTick, e.tick) + 4;
        if (e.winner_id === data.team_a) scoreA++; else scoreB++;
        break;
    }
  }
  return rounds;
}

/* -- geometry ----------------------------------------------------------------- */

// World space: the map's 0-100 grid with y flipped so defenders sit at the
// top of the screen. Screen space: world, or a 2:1 isometric projection of
// it. The projection is AFFINE, so interpolation can happen after it —
// every downstream consumer (trails, markers, midpoints) works unchanged.
const world = (cid) => {
  const c = V.map.callouts[cid];
  return c ? [c.x, 100 - c.y] : [50, 50];
};

function P(x, y) {
  return MapTransform.project(x, 100 - y, 0, V.iso);
}
const PP = (pt) => P(pt[0], pt[1]);
// Marker/dot sizes read smaller on the iso viewBox (it's ~2x wider) — scale.
// Kept modest on purpose: the map should dwarf the players, not vice versa.
// (The viewer shell now fills large monitors, so icons are physically big
// even at a small world size.)
const S = (v) => (V.iso ? v * 1.15 : v);

// Floor elevation of a room (0 when no geometry). Applied as an upward
// screen shift in iso mode so heaven visibly floats above its site.
const zOf = (cid) => (V.iso && V.floor?.regions?.[cid]?.z) || 0;

const pos = (cid) => {
  const p = PP(world(cid));
  return [p[0], p[1] - zOf(cid)];
};

// Projected floor rect corners for a region (grid coords, y-flip applied,
// elevation shift included), ordered around the parallelogram.
function regionCorners(rid) {
  const r = V.floor.regions[rid];
  const z = V.iso ? (r.z || 0) : 0;
  const g = [
    [r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h],
  ];
  return g.map(([x, y]) => {
    const p = P(x, 100 - y);
    return [p[0], p[1] - z];
  });
}

// Movement polyline for one hop, projected. Falls back to a straight line
// when the map has no floor geometry (or the pair has no authored path).
function hopPath(a, b) {
  const raw = V.floor?.paths?.[`${a}|${b}`];
  if (raw && raw.length >= 2) return raw.map(([x, y]) => P(x, 100 - y));
  return [pos(a), pos(b)];
}

function pointAlong(pts, f) {
  const lens = [];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    lens.push(d);
    total += d;
  }
  if (total === 0) return pts[0];
  let target = f * total;
  for (let i = 0; i < lens.length; i++) {
    if (target <= lens[i] || i === lens.length - 1) {
      const g = lens[i] === 0 ? 0 : target / lens[i];
      return [
        pts[i][0] + (pts[i + 1][0] - pts[i][0]) * g,
        pts[i][1] + (pts[i + 1][1] - pts[i][1]) * g,
      ];
    }
    target -= lens[i];
  }
  return pts[pts.length - 1];
}

// Richer variant of playerPos: also reports whether the player is mid-move
// and a trail-start point, so callers can draw a short fading line without
// re-deriving the interpolation math.
// Project a raw grid point (event coordinates) to screen, riding a room's
// floor elevation.
function gpoint(x, y, z) {
  const p = P(x, 100 - y);
  return [p[0], p[1] - (V.iso ? z || 0 : 0)];
}

function motorAt(round, pid, t) {
  let latest = null;
  for (const control of round.controls?.[pid] ?? []) {
    if (control.tick > t) break;
    latest = control;
  }
  return latest;
}

// Interpolate only between server-emitted control poles. Pace, pauses, and
// path resolution remain engine facts; the viewer never mirrors them.
function motorSample(round, pid, t) {
  const controls = round.controls?.[pid] ?? [];
  let index = -1;
  for (let i = 0; i < controls.length; i++) {
    if (controls[i].tick > t) break;
    index = i;
  }
  if (index < 0) return null;
  const current = controls[index];
  const next = controls[index + 1] ?? null;
  const fraction = next && next.tick > current.tick
    ? Math.min(1, Math.max(0, (t - current.tick) / (next.tick - current.tick)))
    : 0;
  const x = next ? current.x + (next.x - current.x) * fraction : current.x;
  const y = next ? current.y + (next.y - current.y) * fraction : current.y;
  const backFraction = Math.max(0, fraction - TRAIL_SPAN);
  const backX = next
    ? current.x + (next.x - current.x) * backFraction
    : current.x;
  const backY = next
    ? current.y + (next.y - current.y) * backFraction
    : current.y;
  const headingDelta = next
    ? ((next.heading_degrees - current.heading_degrees + 540) % 360) - 180
    : 0;
  const heading = (current.heading_degrees + headingDelta * fraction + 360) % 360;
  return {
    ...current,
    x,
    y,
    heading_degrees: heading,
    backX,
    backY,
    advancing: current.movement === "advance" || next?.movement === "advance",
  };
}

function playerMoveInfo(round, pid, t) {
  // Resting spot: room + (for new logs) the exact placement coordinate.
  let atRoom = round.placements[pid] ?? null;
  let atXY = round.placeXY[pid] ?? null;
  let flight = null;
  for (const m of round.moves[pid] ?? []) {
    if (m.start > t) break;
    if (m.arrive <= t) {
      atRoom = m.to;
      atXY = m.pts ? m.pts[m.pts.length - 1] : null;
      flight = null; // any earlier in-flight record is superseded
    } else {
      flight = m; // latest event governs (stall re-pacing)
    }
  }
  const motor = motorSample(round, pid, t);
  if (motor) {
    const z = zOf(motor.callout_id || atRoom);
    const p = gpoint(motor.x, motor.y, z);
    const back = gpoint(motor.backX, motor.backY, z);
    const displaced = Math.hypot(p[0] - back[0], p[1] - back[1]) > 0.02;
    return {
      pos: p,
      moving: !!motor.route_active && motor.advancing && displaced,
      from: back,
      f: 1,
    };
  }
  if (flight) {
    const m = flight;
    const f = Math.min(1, (t - m.start) / Math.max(1, m.arrive - m.start));
    const pts = m.pts
      ? m.pts.map(([x, y]) => P(x, 100 - y))
      : hopPath(m.from, m.to);
    const p = pointAlong(pts, f);
    const back = pointAlong(pts, Math.max(0, f - TRAIL_SPAN));
    // Ramp between floor heights while crossing rooms.
    const z = V.iso ? zOf(m.from) + (zOf(m.to) - zOf(m.from)) * f : 0;
    return {
      pos: [p[0], p[1] - z], moving: true,
      from: [back[0], back[1] - z], f,
    };
  }
  if (atRoom === null) return null;
  if (atXY) return { pos: gpoint(atXY[0], atXY[1], zOf(atRoom)), moving: false };
  return { pos: pos(atRoom), moving: false };
}

function playerPos(round, pid, t) {
  const info = playerMoveInfo(round, pid, t);
  return info ? info.pos : null;
}

function deathOf(round, pid) {
  const k = round.kills.find((k) => k.victim_id === pid);
  return k ? k : null;
}

// Utility ability -> visual marker kind. Falls back to "generic" when the
// abilities map is missing (older replay payloads) or the id is unknown.
function abilityKind(ability) {
  if (!ability) return "generic";
  if (ability.ult) return "ult";
  if (ability.smoke) return "smoke";
  if (ability.flash) return "flash";
  if (ability.damage) return "damage";
  if (ability.info) return "info";
  return "generic";
}

/* -- svg --------------------------------------------------------------------- */

const SVG = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

// A small deterministic offset so several abilities thrown at the SAME target
// callout spread into a little cluster instead of stacking on one point.
function utilJitter(seed) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (Math.imul(h, 31) + seed.charCodeAt(i)) | 0;
  const ang = ((h >>> 0) % 628) / 100;
  const rad = S(0.8 + (((h >>> 5) >>> 0) % 90) / 100);
  return [Math.cos(ang) * rad, Math.sin(ang) * rad];
}

// Utility markers: recomputed from scratch every frame (deterministic in
// (round, tick)), so their fade/pulse is plain JS math rather than a CSS
// animation — the transient layer is fully rebuilt every frame and a
// keyframe animation would just restart each time. The effect is drawn where
// the ability LANDS (its target callout), with a short throw line back to the
// caster so you can read who deployed it and where it's going.
function drawUtilityMarkers(round, t) {
  const abilities = V.abilities || {};
  for (const u of round.utility) {
    const age = t - u.tick;
    if (age < 0 || age > UTIL_MARKER_TICKS) continue;
    const cast = playerPos(round, u.player_id, u.tick);
    const land = u.target_callout && V.map.callouts[u.target_callout]
      ? pos(u.target_callout)
      : cast;
    if (!land) continue;
    const [jx, jy] = utilJitter(u.player_id + u.ability_id);
    const x = land[0] + jx, y = land[1] + jy;
    const fade = 1 - age / UTIL_MARKER_TICKS;
    const kind = abilityKind(abilities[u.ability_id]);
    // The throw: a brief dashed line from the caster to the landing spot.
    if (cast && land !== cast && age <= 3) {
      V.dyn.appendChild(svgEl("line", {
        x1: cast[0].toFixed(2), y1: cast[1].toFixed(2),
        x2: x.toFixed(2), y2: y.toFixed(2),
        class: `util-throw util-throw-${kind}`,
        opacity: ((1 - age / 3) * 0.7).toFixed(2),
      }));
    }
    switch (kind) {
      case "smoke":
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: S(3), class: "util-marker util-smoke",
          opacity: (fade * 0.5).toFixed(2),
        }));
        break;
      case "flash": {
        const r = S(1.7);
        const d = `M${x} ${y - r} L${x + r * .4} ${y - r * .4} L${x + r} ${y} L${x + r * .4} ${y + r * .4} ` +
          `L${x} ${y + r} L${x - r * .4} ${y + r * .4} L${x - r} ${y} L${x - r * .4} ${y - r * .4} Z`;
        V.dyn.appendChild(svgEl("path", { d, class: "util-marker util-flash", opacity: fade.toFixed(2) }));
        break;
      }
      case "damage": {
        const d = S(1.8);
        V.dyn.appendChild(svgEl("path", {
          d: `M${x - d} ${y} L${x + d} ${y} M${x} ${y - d} L${x} ${y + d}`,
          class: "util-marker util-damage", opacity: fade.toFixed(2),
        }));
        break;
      }
      case "info":
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: S(1.4 + age * 0.35).toFixed(2),
          class: "util-marker util-info", opacity: (fade * 0.9).toFixed(2),
        }));
        break;
      case "ult":
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: S(4 + Math.sin(age * 1.3) * 0.7).toFixed(2),
          class: "util-marker util-ult", opacity: (fade * 0.7).toFixed(2),
        }));
        break;
      default:
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: S(1.6), class: "util-marker util-generic", opacity: (fade * 0.5).toFixed(2),
        }));
    }
  }
}

/* -- vision cones ----------------------------------------------------------- */

const CONE_R = 9;         // sight-cone length in world units (scaled by S)
const CONE_HALF = 0.42;   // half-angle of the wedge (~24 deg each side)
const FACE_RECENT = 5;    // ticks a frag/utility keeps steering the gaze
const FACE_LERP = 0.28;   // per-frame ease toward the target angle (0..1)

// Everyone alive right now, with screen position, team, and move heading.
// One pass per frame feeds both the cones and the nearest-enemy gaze fallback.
function livePositions(round, t) {
  const out = {};
  for (const pid of Object.keys(V.players)) {
    if (!(pid in round.placements)) continue;
    const death = deathOf(round, pid);
    if (death && death.tick <= t) continue;
    const mi = playerMoveInfo(round, pid, t);
    if (!mi) continue;
    out[pid] = { pos: mi.pos, moving: mi.moving, from: mi.from, team: V.players[pid].team_id };
  }
  return out;
}

// Where a player is looking, in SCREEN radians — derived entirely from the
// event log, in priority order: heading while moving, then the target of a
// recent frag, then a recently-thrown ability's landing spot, then (idle) the
// nearest live opponent. Returns null when nothing gives a direction.
function facingAngle(round, pid, t, live) {
  const me = live[pid];
  if (!me) return null;
  const [px, py] = me.pos;
  const ang = (x, y) => Math.atan2(y - py, x - px);

  // New logs make facing a player-issued, engine-resolved fact. Transform
  // the world-space heading through the same projection as the map.
  const control = motorSample(round, pid, t) || motorAt(round, pid, t);
  if (control && Number.isFinite(control.heading_degrees)) {
    const radians = control.heading_degrees * Math.PI / 180;
    const origin = P(0, 0);
    const tip = P(Math.cos(radians), -Math.sin(radians));
    return Math.atan2(tip[1] - origin[1], tip[0] - origin[0]);
  }

  if (me.moving && me.from) {
    const dx = px - me.from[0], dy = py - me.from[1];
    if (dx * dx + dy * dy > 0.04) return Math.atan2(dy, dx);
  }
  // Most recent frag by this player -> look at where the victim fell.
  let frag = null;
  for (const k of round.kills) {
    if (k.killer_id !== pid || k.victim_x == null) continue;
    if (t < k.tick || t - k.tick > FACE_RECENT) continue;
    if (!frag || k.tick > frag.tick) frag = k;
  }
  if (frag) {
    const [vx, vy] = gpoint(frag.victim_x, frag.victim_y, zOf(frag.callout_id));
    return ang(vx, vy);
  }
  // Most recent ability -> look toward where it's going.
  let cast = null;
  for (const u of round.utility) {
    if (u.player_id !== pid || !u.target_callout || !V.map.callouts[u.target_callout]) continue;
    if (t < u.tick || t - u.tick > FACE_RECENT) continue;
    if (!cast || u.tick > cast.tick) cast = u;
  }
  if (cast) {
    const [tx, ty] = pos(cast.target_callout);
    return ang(tx, ty);
  }
  // Idle: hold the angle toward the nearest live opponent.
  let best = Infinity, bang = null;
  for (const q of Object.values(live)) {
    if (q.team === me.team) continue;
    const dx = q.pos[0] - px, dy = q.pos[1] - py, d = dx * dx + dy * dy;
    if (d > 0.04 && d < best) { best = d; bang = Math.atan2(dy, dx); }
  }
  return bang;
}

// Translucent sight wedge per living player. Drawn on the transient layer
// beneath the player dots; the gaze eases between frames (V.facing) so it
// swings smoothly instead of snapping. Reset when the round changes.
function drawVisionCones(round, t) {
  if (V._facingRound !== V.roundIdx) { V.facing = {}; V._facingRound = V.roundIdx; }
  const live = livePositions(round, t);
  const r = S(CONE_R);
  for (const [pid, me] of Object.entries(live)) {
    const target = facingAngle(round, pid, t, live);
    if (target == null) continue;
    let cur = V.facing[pid];
    if (cur == null) cur = target;
    else {
      let diff = target - cur;
      while (diff > Math.PI) diff -= 2 * Math.PI;
      while (diff < -Math.PI) diff += 2 * Math.PI;
      cur += diff * FACE_LERP;
    }
    V.facing[pid] = cur;
    const [px, py] = me.pos;
    const a1 = cur - CONE_HALF, a2 = cur + CONE_HALF;
    const e1x = px + Math.cos(a1) * r, e1y = py + Math.sin(a1) * r;
    const e2x = px + Math.cos(a2) * r, e2y = py + Math.sin(a2) * r;
    const teamCls = me.team === V.teamA ? "a" : "b";
    V.dyn.appendChild(svgEl("path", {
      d: `M${px.toFixed(2)} ${py.toFixed(2)} L${e1x.toFixed(2)} ${e1y.toFixed(2)} ` +
        `A ${r.toFixed(2)} ${r.toFixed(2)} 0 0 1 ${e2x.toFixed(2)} ${e2y.toFixed(2)} Z`,
      class: "vision-cone " + teamCls,
    }));
  }
}

const GIMMICK_PING_TICKS = 10;

// Map-mechanic markers: teleporter pads and doors, drawn every frame so a
// door's open/shut state tracks the round's events; plus loud-use pings.
function drawGimmicks(round, t) {
  for (const g of V.map.gimmicks ?? []) {
    const z = zOf(g.between[0]);
    const [x, y] = gpoint(g.x, g.y, z);
    if (g.type === "teleporter") {
      const outer = svgEl("circle", { cx: x, cy: y, r: S(2.2), class: "gk gk-tp" });
      const inner = svgEl("circle", { cx: x, cy: y, r: S(1.1), class: "gk gk-tp" });
      const tip = svgEl("title", {});
      tip.textContent = `Teleporter: ${g.between.join(" <-> ")}`;
      outer.appendChild(tip);
      V.dyn.appendChild(outer);
      V.dyn.appendChild(inner);
    } else {
      const closed =
        g.type === "breakable_door" &&
        round.closedDoors.has(g.id) &&
        !round.gimmicks.some(
          (e) => e.gimmick_id === g.id && e.action === "broken" && e.tick <= t
        );
      const door = svgEl("rect", {
        x: x - S(1.8), y: y - S(0.55),
        width: S(3.6), height: S(1.1),
        class: "gk gk-door" + (closed ? " gk-closed" : ""),
      });
      const tip = svgEl("title", {});
      tip.textContent =
        (g.type === "breakable_door" ? "Breakable door" : "Door") +
        (closed ? " (closed)" : "") + `: ${g.between.join(" <-> ")}`;
      door.appendChild(tip);
      V.dyn.appendChild(door);
    }
  }
  for (const e of round.gimmicks) {
    const age = t - e.tick;
    if (age < 0 || age > GIMMICK_PING_TICKS || e.x == null) continue;
    const fade = 1 - age / GIMMICK_PING_TICKS;
    const g = (V.map.gimmicks ?? []).find((g) => g.id === e.gimmick_id);
    const [x, y] = gpoint(e.x, e.y, g ? zOf(g.between[0]) : 0);
    V.dyn.appendChild(svgEl("circle", {
      cx: x, cy: y, r: S(2 + age * 0.9).toFixed(2),
      class: "gk-ping", opacity: (fade * 0.8).toFixed(2),
    }));
  }
}

// Whiffed duels: a brief spark where the shots crossed and missed.
function drawWhiffs(round, t) {
  for (const w of round.whiffs ?? []) {
    const age = t - w.tick;
    if (age < 0 || age > 3 || w.x == null) continue;
    const p = gpoint(w.x, w.y, 0);
    const fade = 1 - age / 3;
    const r = S(0.9 + age * 0.4);
    V.dyn.appendChild(svgEl("path", {
      d: `M${p[0] - r} ${p[1]} L${p[0] + r} ${p[1]} M${p[0]} ${p[1] - r} L${p[0]} ${p[1] + r}`,
      class: "whiff-mark", opacity: (fade * 0.7).toFixed(2),
      transform: `rotate(45 ${p[0]} ${p[1]})`,
    }));
  }
}

// Brief fading ring at the death spot, same math-driven approach as above.
function drawKillFlashes(round, t) {
  for (const k of round.kills) {
    const age = t - k.tick;
    if (age < 0 || age > KILL_FLASH_TICKS) continue;
    const p = k.victim_x != null
      ? gpoint(k.victim_x, k.victim_y, zOf(k.callout_id))
      : (k.callout_id ?? round.placements[k.victim_id])
        ? pos(k.callout_id ?? round.placements[k.victim_id])
        : null;
    if (!p) continue;
    const [x, y] = p;
    const fade = 1 - age / KILL_FLASH_TICKS;
    V.dyn.appendChild(svgEl("circle", {
      cx: x, cy: y, r: S(2 + age * 1.4).toFixed(2),
      class: "kill-flash", opacity: (fade * 0.85).toFixed(2),
    }));
  }
}

const WALL_DROP = 3.2; // fake extrusion depth for iso walls (screen units)

function drawFloor(svg) {
  // Painter's algorithm: farthest rooms first (smallest max screen-y).
  const order = Object.keys(V.floor.regions).sort((a, b) => {
    const ay = Math.max(...regionCorners(a).map((p) => p[1]));
    const by = Math.max(...regionCorners(b).map((p) => p[1]));
    return ay - by;
  });
  for (const rid of order) {
    const c = V.map.callouts[rid];
    const corners = regionCorners(rid);
    const isSite = c && c.zone === "site";
    const z = V.iso ? (V.floor.regions[rid].z || 0) : 0;
    if (V.iso) {
      // Extrude the two edges adjacent to the nearest corner downward —
      // a cheap wall face that sells the depth. Elevated rooms drop all
      // the way to ground level.
      const drop = WALL_DROP + z;
      const nearest = corners.reduce((m, p, i) => (p[1] > corners[m][1] ? i : m), 0);
      for (const j of [(nearest + 3) % 4, nearest]) {
        const p1 = corners[j], p2 = corners[(j + 1) % 4];
        svg.appendChild(svgEl("polygon", {
          points: `${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ` +
            `${p2[0]},${p2[1] + drop} ${p1[0]},${p1[1] + drop}`,
          class: "floor-wall",
        }));
      }
    }
    svg.appendChild(svgEl("polygon", {
      points: corners.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" "),
      class: "floor" + (isSite ? " floor-site" : "") + (z > 0 ? " floor-raised" : ""),
    }));
    if (c) {
      const [lx, ly] = pos(rid);
      const label = svgEl("text", { x: lx, y: ly + S(1.2), class: "callout-label" });
      label.textContent = c.name;
      svg.appendChild(label);
    }
  }

  // Props: crates (half) and sight-blocking walls/boxes (full), drawn as
  // little iso boxes after the floors, back to front.
  const props = (V.floor.props ?? []).slice().sort((a, b) => {
    const ay = P(a.x + a.w / 2, 100 - (a.y + a.h / 2))[1];
    const by = P(b.x + b.w / 2, 100 - (b.y + b.h / 2))[1];
    return ay - by;
  });
  for (const p of props) {
    const zr = V.iso ? (V.floor.regions[p.region]?.z || 0) : 0;
    const hgt = V.iso ? (p.height === "full" ? 3.2 : 1.5) : 0;
    const g = [
      [p.x, p.y], [p.x + p.w, p.y],
      [p.x + p.w, p.y + p.h], [p.x, p.y + p.h],
    ];
    const base = g.map(([x, y]) => {
      const q = P(x, 100 - y);
      return [q[0], q[1] - zr];
    });
    const top = base.map(([x, y]) => [x, y - hgt]);
    const cls = p.height === "full" ? "prop-full" : "prop-half";
    if (V.iso) {
      const nearest = top.reduce((m, q, i) => (q[1] > top[m][1] ? i : m), 0);
      for (const j of [(nearest + 3) % 4, nearest]) {
        const p1 = top[j], p2 = top[(j + 1) % 4];
        svg.appendChild(svgEl("polygon", {
          points: `${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ` +
            `${p2[0]},${p2[1] + hgt} ${p1[0]},${p1[1] + hgt}`,
          class: cls + " prop-side",
        }));
      }
    }
    svg.appendChild(svgEl("polygon", {
      points: top.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" "),
      class: cls,
    }));
  }
  // Corridors with authored waypoints get a subtle walkway line.
  for (const [key, raw] of Object.entries(V.floor.paths ?? {})) {
    if (raw.length <= 2) continue;
    const [a, b] = key.split("|");
    if (a > b) continue; // draw each undirected corridor once
    const pts = raw.map(([x, y]) => P(x, 100 - y));
    svg.appendChild(svgEl("polyline", {
      points: pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" "),
      class: "corridor",
    }));
  }
  // Site letters above their rooms.
  const siteAgg = {};
  for (const [cid, c] of Object.entries(V.map.callouts)) {
    if (c.zone === "site") (siteAgg[c.site] ??= []).push(pos(cid));
  }
  for (const [site, pts] of Object.entries(siteAgg)) {
    const x = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const y = pts.reduce((s, p) => s + p[1], 0) / pts.length - S(5.5);
    const t = svgEl("text", { x, y, class: "site-label" });
    t.textContent = site.toUpperCase();
    svg.appendChild(t);
  }
}

function drawGraph(svg) {
  for (const [a, b] of V.map.edges) {
    const [x1, y1] = pos(a), [x2, y2] = pos(b);
    svg.appendChild(svgEl("line", { x1, y1, x2, y2, class: "edge" }));
  }
  const siteAgg = {};
  for (const [cid, c] of Object.entries(V.map.callouts)) {
    const [x, y] = pos(cid);
    const isSite = c.zone === "site";
    svg.appendChild(svgEl("circle", {
      cx: x, cy: y, r: S(isSite ? 3.4 : 2.2),
      class: "callout-dot" + (isSite ? " callout-site" : ""),
    }));
    const label = svgEl("text", { x, y: y + S(4.6), class: "callout-label" });
    label.textContent = c.name;
    svg.appendChild(label);
    if (isSite) (siteAgg[c.site] ??= []).push([x, y]);
  }
  for (const [site, pts] of Object.entries(siteAgg)) {
    const x = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const y = pts.reduce((s, p) => s + p[1], 0) / pts.length - S(4.5);
    const t = svgEl("text", { x, y, class: "site-label" });
    t.textContent = site.toUpperCase();
    svg.appendChild(t);
  }
}

// Tight per-map viewBox: hug the floor geometry so the map fills the panel
// instead of floating in the fixed frame. The painted backdrop keeps its
// ISO_VIEWBOX placement (the guide->paint contract); this only crops what
// the user SEES — same trick as officeWorldRect vs officeViewRect.
function isoContentViewBox() {
  if (!V.floor) return ISO_VIEWBOX;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const rid of Object.keys(V.floor.regions)) {
    for (const [x, y] of regionCorners(rid)) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (minX === Infinity) return ISO_VIEWBOX;
  const pad = 4, plinth = 5.5; // room for the wall drop + glow below
  return [minX - pad, minY - pad, maxX - minX + pad * 2, maxY - minY + pad * 2 + plinth];
}

function drawStatic() {
  const svg = document.getElementById("v-map");
  svg.innerHTML = "";
  svg.setAttribute(
    "viewBox",
    V.iso ? isoContentViewBox().map((n) => n.toFixed(1)).join(" ") : "-6 -6 112 112"
  );
  svg.classList.toggle("iso", !!V.iso);

  // Per-player circular clip paths for agent icons live here (rebuilt with
  // everything else since drawStatic() wipes the whole svg subtree).
  V.defs = svgEl("defs", {});
  svg.appendChild(V.defs);

  // Painted backdrop: bottom-most layer, iso only, placed at the exact
  // guide->viewer transform (scripts/render_map_guide.py). When present the
  // floor/prop vectors become translucent line-work over it (.has-paint CSS)
  // so region borders + callouts stay readable while the paint shows through.
  // Absent painted file => V.painted is null and rendering is unchanged.
  const paint = V.iso ? V.painted : null;
  svg.classList.toggle("has-paint", !!paint);
  if (paint) {
    const [vx, vy, vw, vh] = ISO_VIEWBOX;
    const bg = svgEl("image", {
      x: vx, y: vy, width: vw, height: vh,
      preserveAspectRatio: "none", class: "map-paint",
    });
    bg.setAttributeNS("http://www.w3.org/1999/xlink", "href", paint);
    bg.setAttribute("href", paint);
    svg.appendChild(bg);
  }

  if (V.floor) drawFloor(svg);
  else drawGraph(svg);

  // V.dyn: transient layer, fully cleared + rebuilt every frame (markers,
  // kill flashes, motion trails, death marks).
  V.dyn = svgEl("g", {});
  svg.appendChild(V.dyn);

  // V.persist: elements that live across frames (spike, player dots) so a
  // real CSS transition/animation can run instead of restarting each tick.
  V.persist = svgEl("g", {});
  svg.appendChild(V.persist);
  V.playerEls = {};
  V.spikeEl = svgEl("rect", { width: S(2.8), height: S(2.8), class: "spike" });
  V.spikeEl.style.display = "none";
  V.spikeRingEl = svgEl("circle", { r: S(2.2), class: "spike-ring" });
  V.spikeRingEl.style.display = "none";
  V.persist.appendChild(V.spikeRingEl);
  V.persist.appendChild(V.spikeEl);
}

// Agent-icon dot radius. The tight per-map viewBox (isoContentViewBox) zooms
// the whole scene, so the icon stays readable on screen at a much smaller
// world size — players read as people IN the map, not tokens ON it.
const ICON_R = 1.9;

function hidePlayerEl(pid) {
  const e = V.playerEls[pid];
  if (!e) return;
  e.ring.style.display = "none";
  e.icon.style.display = "none";
  e.fallback.style.display = "none";
  e.label.style.display = "none";
}

// Player dot = team-colored ring + the player's agent icon clipped to a
// circle on top, with a plain colored dot as fallback for missing/broken
// icon assets (older/incomplete art drops, or a 404 caught at runtime).
function getPlayerEls(pid) {
  let e = V.playerEls[pid];
  if (!e) {
    const agentIcon = V.players[pid]?.agent_icon || null;

    const ring = svgEl("circle", { r: S(ICON_R), class: "pdot-ring" });

    // clipPathUnits=objectBoundingBox: the clip circle is relative to the
    // <image>'s own box, so it never needs repositioning as the icon moves.
    const clip = svgEl("clipPath", { id: `pclip-${pid}`, clipPathUnits: "objectBoundingBox" });
    clip.appendChild(svgEl("circle", { cx: 0.5, cy: 0.5, r: 0.5 }));
    V.defs.appendChild(clip);

    const icon = svgEl("image", {
      width: S(ICON_R * 2), height: S(ICON_R * 2),
      class: "pdot-icon", "clip-path": `url(#pclip-${pid})`,
    });
    const fallback = svgEl("circle", { r: S(1.7), class: "pdot" });

    if (agentIcon) {
      icon.setAttributeNS("http://www.w3.org/1999/xlink", "href", agentIcon);
      icon.setAttribute("href", agentIcon);
      // Asset missing (404) or otherwise failed to decode: hide the icon +
      // ring and show the plain team-colored dot instead.
      icon.addEventListener("error", () => {
        icon.dataset.failed = "1";
        icon.style.display = "none";
        fallback.style.display = "";
      });
    } else {
      icon.dataset.failed = "1";
    }

    const label = svgEl("text", { class: "plabel" });

    // Hover tooltip: agent name first line, player handle second.
    const an = agentName(pid);
    const tipText = an ? `${an}\n${handleOf(pid)}` : handleOf(pid);
    for (const host of [ring, icon, fallback]) {
      const tip = svgEl("title", {});
      tip.textContent = tipText;
      host.appendChild(tip);
    }

    V.persist.appendChild(ring);
    V.persist.appendChild(fallback);
    V.persist.appendChild(icon);
    V.persist.appendChild(label);
    e = V.playerEls[pid] = { ring, icon, fallback, label };
  }
  return e;
}

function drawFrame() {
  const round = V.rounds[V.roundIdx];
  const t = V.tick;
  V.dyn.innerHTML = "";

  // Transient overlays first so player dots (persistent layer, drawn after
  // V.dyn in the DOM) render on top of them. Vision cones lead so every other
  // marker (utility, kill flashes, spike) sits above the translucent wedges.
  if (V.cones) drawVisionCones(round, t);
  drawGimmicks(round, t);
  drawKillFlashes(round, t);
  drawWhiffs(round, t);
  drawUtilityMarkers(round, t);

  // Spike — persistent element, updated in place so its CSS pulse animation
  // keeps running instead of restarting every frame.
  const planted = round.plant && round.plant.tick <= t;
  if (planted) {
    const [x, y] = round.plant.x != null
      ? gpoint(round.plant.x, round.plant.y, zOf(round.plant.callout_id))
      : pos(round.plant.callout_id);
    V.spikeEl.setAttribute("x", x - S(1.4));
    V.spikeEl.setAttribute("y", y - S(1.4));
    V.spikeEl.setAttribute("transform", `rotate(45 ${x} ${y})`);
    V.spikeEl.style.display = "";
    V.spikeRingEl.setAttribute("cx", x);
    V.spikeRingEl.setAttribute("cy", y);
    V.spikeRingEl.style.display = "";
  } else {
    V.spikeEl.style.display = "none";
    V.spikeRingEl.style.display = "none";
  }

  // Players.
  for (const [pid, info] of Object.entries(V.players)) {
    if (!(pid in round.placements)) { hidePlayerEl(pid); continue; }
    const death = deathOf(round, pid);
    const dead = death && death.tick <= t;
    const teamCls = info.team_id === V.teamA ? "a" : "b";
    if (dead) {
      hidePlayerEl(pid);
      const p = death.victim_x != null
        ? gpoint(death.victim_x, death.victim_y, zOf(death.callout_id))
        : pos(death.callout_id ?? round.placements[pid]);
      if (p) {
        const r = S(1.2);
        V.dyn.appendChild(svgEl("path", {
          d: `M${p[0] - r} ${p[1] - r} L${p[0] + r} ${p[1] + r} M${p[0] - r} ${p[1] + r} L${p[0] + r} ${p[1] - r}`,
          stroke: "currentColor", class: "pdot " + teamCls + " dead", "stroke-width": S(.7),
        }));
      }
      continue;
    }
    const move = playerMoveInfo(round, pid, t);
    if (!move) { hidePlayerEl(pid); continue; }
    const [x, y] = move.pos;
    const { ring, icon, fallback, label } = getPlayerEls(pid);
    const failed = icon.dataset.failed === "1";
    ring.setAttribute("cx", x);
    ring.setAttribute("cy", y);
    ring.setAttribute("class", "pdot-ring " + teamCls);
    ring.style.display = failed ? "none" : "";
    const iw = S(ICON_R * 2);
    icon.setAttribute("x", x - iw / 2);
    icon.setAttribute("y", y - iw / 2);
    icon.style.display = failed ? "none" : "";
    fallback.setAttribute("cx", x);
    fallback.setAttribute("cy", y);
    fallback.setAttribute("class", "pdot " + teamCls);
    fallback.style.display = failed ? "" : "none";
    label.setAttribute("x", x);
    label.setAttribute("y", y - S(2.6));
    label.style.display = "";
    label.textContent = info.handle;

    // Short fading motion trail while mid-move, so heading reads clearly.
    // move.from is already the trail-start point along the actual path.
    if (move.moving) {
      const [sx, sy] = move.from;
      V.dyn.appendChild(svgEl("line", {
        x1: sx.toFixed(2), y1: sy.toFixed(2), x2: x.toFixed(2), y2: y.toFixed(2),
        class: "ptrail " + teamCls, opacity: Math.min(1, move.f * 2).toFixed(2),
      }));
    }
  }

  // HUD.
  const [sa, sb] = round.scoreBefore;
  const ended = round.end && t >= round.end.tick;
  const fa = ended && round.end.winner_id === V.teamA ? 1 : 0;
  const fb = ended && round.end.winner_id === V.teamB ? 1 : 0;
  document.getElementById("v-score").textContent = `${sa + fa} — ${sb + fb}`;
  const atkName = round.attacker === V.teamA ? V.names[V.teamA] : V.names[V.teamB];
  document.getElementById("v-round").textContent =
    `Round ${round.num} · ATK ${atkName}`;
  document.getElementById("v-banner").textContent = ended
    ? `${V.names[round.end.winner_id]} take the round — ${round.end.reason.replaceAll("_", " ")}`
    : planted ? "Spike planted" : "";

  // Clock: 100s round, 45s post-plant.
  let secs;
  if (planted) secs = Math.max(0, 45 - (t - round.plant.tick) / TICKS_PER_SEC);
  else secs = Math.max(0, 100 - t / TICKS_PER_SEC);
  const mm = String(Math.floor(secs / 60)), ss = String(Math.floor(secs % 60)).padStart(2, "0");
  const clockEl = document.getElementById("v-clock");
  clockEl.textContent = `${mm}:${ss}`;
  clockEl.classList.toggle("post-plant", !!planted);

  // Feed: kills + utility usage, interleaved chronologically, newest first.
  const abilities = V.abilities || {};
  const feedItems = round.kills
    .filter((k) => k.tick <= t)
    .map((k) => ({
      tick: k.tick,
      html: `<div class="k">${feedLabel(k.killer_id)} <span class="${k.headshot ? "hs" : ""}">${k.headshot ? "☠" : "→"}</span> ${feedLabel(k.victim_id)}` +
        ` <span class="muted">${k.weapon_id}${k.is_trade ? " · trade" : ""}</span></div>`,
    }))
    .concat(round.utility
      .filter((u) => u.tick <= t)
      .map((u) => {
        const ability = abilities[u.ability_id];
        const kind = abilityKind(ability);
        const name = ability?.name ?? u.ability_id;
        const who = feedLabel(u.player_id);
        const line = u.failed
          ? `${who} <span class="muted">whiffs ${name} — no effect</span>`
          : `${who} used <span class="muted">${name}</span>`;
        return {
          tick: u.tick,
          html: `<div class="u${u.failed ? " dim" : ""}"><span class="u-chip u-${kind}"></span>${line}</div>`,
        };
      }))
    .concat((round.comms ?? [])
      .filter((c) => c.tick <= t)
      .map((c) => {
        const who = feedLabel(c.player_id);
        const line = c.kind === "miscomm"
          ? `${who} crosses the comms — rotation stalls`
          : `${who} calls the rotate clean`;
        return {
          tick: c.tick,
          html: `<div class="u comms"><span class="u-chip u-comms"></span>${line}</div>`,
        };
      }))
    .concat(round.gimmicks
      .filter((e) => e.tick <= t)
      .map((e) => {
        const verb =
          e.action === "broken" ? "broke a door open"
          : e.kind === "teleporter" ? "took the teleporter"
          : "swung the rotating door";
        return {
          tick: e.tick,
          html: `<div class="u"><span class="u-chip u-gimmick"></span>${feedLabel(e.player_id)} ${verb} <span class="muted">· heard nearby</span></div>`,
        };
      }));

  const feed = document.getElementById("v-feed");
  feed.innerHTML = feedItems
    .sort((a, b) => a.tick - b.tick)
    .reverse()
    .map((it) => it.html)
    .join("");

  document.getElementById("v-scrub").max = round.maxTick;
  document.getElementById("v-scrub").value = Math.min(t, round.maxTick);
}

/* -- playback ------------------------------------------------------------------ */

function loop(ts) {
  if (!V || !V.playing) return;
  const dt = (ts - (V.lastTs ?? ts)) / 1000;
  V.lastTs = ts;
  V.tick += dt * TICKS_PER_SEC * V.speed;
  const round = V.rounds[V.roundIdx];
  if (V.tick > round.maxTick + 6) {
    if (V.roundIdx < V.rounds.length - 1) {
      if (V.roundIdx === 11 && !V.pepTalkTriggered) {
        V.pepTalkTriggered = true;
        V.playing = false;
        updatePlayBtn();
        showPepTalkModal();
        return;
      }
      V.roundIdx++;
      V.tick = 0;
      buildShouts();
    } else {
      V.playing = false;
      updatePlayBtn();
    }
  }
  drawFrame();
  markTimeline();
  requestAnimationFrame(loop);
}

function updatePlayBtn() {
  document.getElementById("v-play").textContent = V && V.playing ? "⏸" : "▶";
}

function setRound(idx) {
  V.roundIdx = Math.max(0, Math.min(V.rounds.length - 1, idx));
  V.tick = 0;
  drawFrame();
  markTimeline();
  buildShouts();
}

/* -- public api ------------------------------------------------------------------ */

// Agent-forward lineup for the side panel: agent icon + agent name primary,
// player handle secondary. The viewer HTML has no static scoreboard, so this
// is injected dynamically (and removed/rebuilt per replay, torn down on close).
function buildLineup() {
  const side = document.querySelector(".viewer-side");
  if (!side) return;
  const existing = document.getElementById("v-lineup");
  if (existing) existing.remove();
  const el = document.createElement("div");
  el.id = "v-lineup";
  el.className = "v-lineup";
  el.innerHTML = [V.teamA, V.teamB]
    .map((tid) => {
      const cls = tid === V.teamA ? "a" : "b";
      const rows = Object.keys(V.players)
        .filter((pid) => V.players[pid].team_id === tid)
        .map((pid) => {
          const src = V.players[pid].agent_icon;
          const icon = src
            ? `<img class="lu-icon" src="${src}" onerror="this.style.visibility='hidden'" alt="">`
            : `<span class="lu-icon"></span>`;
          return `<div class="lu-row plink" data-pid="${pid}">${icon}` +
            `<span class="lu-agent">${agentName(pid) || handleOf(pid)}</span>` +
            `<span class="lu-handle muted">${handleOf(pid)}</span></div>`;
        })
        .join("");
      return `<div class="lu-team"><div class="lu-team-name ${cls} tlink" data-tid="${tid}">${V.names[tid]}</div>${rows}</div>`;
    })
    .join("");
  side.insertBefore(el, document.getElementById("v-feed"));
}

// Round-by-round timeline strip: one chip per round, tinted by winner, with
// a spike marker when the bomb went down. Chips jump the replay to a round.
function buildTimeline() {
  const side = document.querySelector(".viewer-side");
  if (!side) return;
  const existing = document.getElementById("v-timeline");
  if (existing) existing.remove();
  if (!V.summaries || !V.summaries.length) return;
  const el = document.createElement("div");
  el.id = "v-timeline";
  el.className = "v-timeline";
  el.innerHTML = V.summaries
    .map((s, i) => {
      const cls = s.winner_id === V.teamA ? "a" : "b";
      const leaders = Object.entries(V.momentum[i]?.values || {})
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
      const lead = leaders[0];
      const heat = lead && Math.abs(lead[1]) >= .18
        ? (lead[1] > 0 ? " hot" : " cold") : "";
      const plant = s.plant ? '<span class="v-tl-plant">◈</span>' : "";
      const tip = `Round ${s.num}: ${s.score_a}-${s.score_b}${s.plant ? " · spike planted" : ""}`;
      const momentumTip = lead && heat
        ? ` / ${handleOf(lead[0])} ${heat.trim()} (${lead[1].toFixed(2)})` : "";
      return `<button class="v-tl-round ${cls}${heat}" data-round="${i}" title="${tip}${momentumTip}">${s.num}${plant}</button>`;
    })
    .join("");
  el.querySelectorAll(".v-tl-round").forEach((b) => {
    b.onclick = () => {
      setRound(Number(b.dataset.round));
      V.playing = false;
      updatePlayBtn();
    };
  });
  side.insertBefore(el, document.getElementById("v-feed"));
  V._tlRound = -1;
  markTimeline();
}

function markTimeline() {
  const tl = document.getElementById("v-timeline");
  if (!tl || !V || V._tlRound === V.roundIdx) return;
  V._tlRound = V.roundIdx;
  tl.querySelectorAll(".v-tl-round").forEach((b, i) => {
    b.classList.toggle("active", i === V.roundIdx);
  });
}

// Post-match box score: MVP + the top performers by rating (server-computed).
function buildMatchSummary() {
  const side = document.querySelector(".viewer-side");
  if (!side) return;
  const existing = document.getElementById("v-summary");
  if (existing) existing.remove();
  if (!V.boxScore || !V.boxScore.length) return;
  const el = document.createElement("div");
  el.id = "v-summary";
  el.className = "v-summary";
  const mvp = V.mvp;
  const rows = V.boxScore
    .slice(0, 5)
    .map((r) => {
      const cls = r.team_id === V.teamA ? "a" : "b";
      const xdeText = r.xde != null ? ` <span class="muted" style="font-size:0.8em; margin-left: 4px;">(xDE: ${r.xde >= 0 ? "+" : ""}${r.xde.toFixed(2)})</span>` : "";
      return `<div class="v-sum-row"><span class="v-sum-dot ${cls}"></span>` +
        `<span class="plink" data-pid="${r.player_id}">${r.handle}</span>` +
        `<span class="mono muted">${r.kills}/${r.deaths}${xdeText}</span>` +
        `<b class="mono">${r.rating.toFixed(2)}</b></div>`;
    })
    .join("");
  el.innerHTML =
    `<div class="v-sum-lab">Box score${mvp ? ` · MVP <b class="plink" data-pid="${mvp.player_id}">${mvp.handle}</b>` : ""}</div>` +
    rows;
  side.insertBefore(el, document.getElementById("v-feed"));
}

function showPepTalkModal() {
  const existing = document.getElementById("pep-talk-modal");
  if (existing) existing.remove();

  const modal = document.createElement("div");
  modal.id = "pep-talk-modal";
  modal.className = "overlay";
  modal.style.zIndex = "100000";
  
  const summary = V.summaries[11] || { score_a: 0, score_b: 0 };
  const userTeamId = App.state.user_team.id;
  const isA = V.teamA === userTeamId;
  const userScore = isA ? summary.score_a : summary.score_b;
  const oppScore = isA ? summary.score_b : summary.score_a;
  const relativeScore = userScore - oppScore;

  const panel = document.createElement("div");
  panel.className = "panel";
  panel.innerHTML = `
    <h2>Halftime message</h2>
    <p class="muted">Halftime score: ${userScore} - ${oppScore} (${relativeScore >= 0 ? "+" : ""}${relativeScore})</p>
    <p>Set the message for the second half:</p>
    <div style="display:flex; flex-direction:column; gap:8px; margin:16px 0;">
      <button class="btn" data-type="reassure"><b>Settle the group:</b> Protect morale and reset.</button>
      <button class="btn" data-type="fire_up"><b>Raise the urgency:</b> Push confidence and aggression.</button>
      <button class="btn" data-type="focus"><b>Refocus:</b> Bring confidence back to baseline.</button>
    </div>
  `;

  panel.querySelectorAll("button").forEach(btn => {
    btn.onclick = async () => {
      const talkType = btn.dataset.type;
      try {
        await api("/api/actions/pep_talk", {
          fixture_id: V.fixtureId || "",
          talk_type: talkType,
          relative_score: relativeScore
        });
        toast("Halftime message delivered.");
      } catch (err) {
        toast("Halftime message could not be delivered.");
      }
      modal.remove();
      V.playing = true;
      updatePlayBtn();
      requestAnimationFrame(loop);
    };
  });

  modal.appendChild(panel);
  document.body.appendChild(modal);
}

function buildShouts() {
  const side = document.querySelector(".viewer-side");
  if (!side) return;
  const existing = document.getElementById("v-shouts");
  if (existing) existing.remove();

  const userTeamId = App.state.user_team.id;
  let lossStreak = 0;
  for (let idx = 0; idx <= V.roundIdx; idx++) {
    const s = V.summaries[idx];
    if (s) {
      if (s.winner_id !== userTeamId) {
        lossStreak++;
      } else {
        lossStreak = 0;
      }
    }
  }

  const elWidget = document.createElement("div");
  elWidget.id = "v-shouts";
  elWidget.className = "card";
  elWidget.style.cssText = "margin-top:10px; padding:10px;";
  elWidget.innerHTML = `
    <h4>In-round calls</h4>
    <div style="display:flex; flex-direction:column; gap:6px; margin-top:8px;">
      <button class="btn btn-sm" id="shout-focus" title="Ask one player to refocus">Refocus player</button>
      <button class="btn btn-sm" id="shout-encourage" title="Steady the group after three consecutive lost rounds">Steady the group (${lossStreak} lost)</button>
      <button class="btn btn-sm" id="shout-effort" title="Raise aggression at a stamina cost">Raise the pressure</button>
    </div>
  `;

  const appliedThisRound = V.shoutAppliedThisRound === V.roundIdx;
  const focusBtn = elWidget.querySelector("#shout-focus");
  const encourageBtn = elWidget.querySelector("#shout-encourage");
  const effortBtn = elWidget.querySelector("#shout-effort");

  if (appliedThisRound) {
    focusBtn.disabled = true;
    encourageBtn.disabled = true;
    effortBtn.disabled = true;
    focusBtn.textContent += " (Used this round)";
  }

  if (lossStreak < 3) {
    encourageBtn.disabled = true;
    encourageBtn.title = "Available after three consecutive lost rounds.";
  }

  const sendShout = async (type, targetPid = null) => {
    try {
      await api("/api/actions/shout", {
        fixture_id: V.fixtureId,
        shout_type: type,
        target_player_id: targetPid,
        loss_streak: lossStreak
      });
      V.shoutAppliedThisRound = V.roundIdx;
      toast("In-round call delivered.");
      buildShouts();
    } catch (err) {
      toast("In-round call could not be delivered.");
    }
  };

  focusBtn.onclick = () => {
    const players = Object.keys(V.players).filter(pid => V.players[pid].team_id === userTeamId);
    const pNames = players.map(pid => `<button class="btn btn-sm" data-pid="${pid}">${handleOf(pid)}</button>`).join(" ");
    
    const popup = document.createElement("div");
    popup.className = "overlay";
    popup.style.zIndex = "100000";
    popup.innerHTML = `
      <div class="panel">
        <h3>Select a player to refocus</h3>
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin:14px 0;">${pNames}</div>
        <button class="btn" id="close-popup">Cancel</button>
      </div>
    `;
    popup.querySelectorAll("button[data-pid]").forEach(btn => {
      btn.onclick = () => {
        sendShout("demand_focus", btn.dataset.pid);
        popup.remove();
      };
    });
    popup.querySelector("#close-popup").onclick = () => popup.remove();
    document.body.appendChild(popup);
  };

  encourageBtn.onclick = () => sendShout("encourage");
  effortBtn.onclick = () => sendShout("demand_effort");

  side.insertBefore(elWidget, document.getElementById("v-feed"));
}

async function openReplay(fixtureId, mapIndex) {
  const data = await api(`/api/replay/${fixtureId}/${mapIndex}`);
  const names = {};
  names[data.team_a] = data.fixture.team_a_name;
  names[data.team_b] = data.fixture.team_b_name;
  V = {
    fixtureId,
    map: data.map,
    floor: data.map.floor || null,
    iso: !!data.map.floor,
    players: data.players,
    teamA: data.team_a,
    teamB: data.team_b,
    names,
    abilities: data.abilities || {},
    rounds: parseReplay(data),
    summaries: data.round_summaries || [],
    momentum: data.momentum || [],
    boxScore: data.box_score || [],
    mvp: data.mvp || null,
    _tlRound: -1,
    roundIdx: 0,
    tick: 0,
    playing: true,
    speed: 1,
    lastTs: null,
    mapId: data.map.id || null,
    painted: null,
    cones: true,
    facing: {},
    _facingRound: -1,
  };
  V.painted = V.mapId ? await probePainted(V.mapId) : null;
  const isoBtn = document.getElementById("v-view");
  isoBtn.style.display = V.floor ? "" : "none";
  isoBtn.textContent = V.iso ? "2D" : "ISO";
  document.getElementById("v-title").innerHTML =
    `<b class="tlink" data-tid="${data.team_a}">${names[data.team_a]}</b> vs <b class="tlink" data-tid="${data.team_b}">${names[data.team_b]}</b> · ${data.map.display_name}`;
  buildLineup();
  buildTimeline();
  buildShouts();
  buildMatchSummary();
  drawStatic();
  drawFrame();
  document.getElementById("viewer").classList.remove("hidden");
  updatePlayBtn();
  requestAnimationFrame(loop);
}

function closeViewer() {
  if (V) V.playing = false;
  V = null;
  const lineup = document.getElementById("v-lineup");
  if (lineup) lineup.remove();
  const timeline = document.getElementById("v-timeline");
  if (timeline) timeline.remove();
  const shouts = document.getElementById("v-shouts");
  if (shouts) shouts.remove();
  const summary = document.getElementById("v-summary");
  if (summary) summary.remove();
  document.getElementById("viewer").classList.add("hidden");
}

document.getElementById("v-play").onclick = () => {
  if (!V) return;
  V.playing = !V.playing;
  V.lastTs = null;
  updatePlayBtn();
  if (V.playing) requestAnimationFrame(loop);
};
document.getElementById("v-view").onclick = () => {
  if (!V || !V.floor) return;
  V.iso = !V.iso;
  document.getElementById("v-view").textContent = V.iso ? "2D" : "ISO";
  drawStatic(); // rebuilds persist/dyn layers for the new projection
  drawFrame();
};
document.getElementById("v-cones").onclick = () => {
  if (!V) return;
  V.cones = !V.cones;
  const b = document.getElementById("v-cones");
  b.classList.toggle("active", V.cones);
  b.setAttribute("aria-pressed", V.cones ? "true" : "false");
  drawFrame();
};
document.getElementById("v-prev").onclick = () => V && setRound(V.roundIdx - 1);
document.getElementById("v-next").onclick = () => V && setRound(V.roundIdx + 1);
document.getElementById("v-scrub").oninput = (e) => {
  if (!V) return;
  V.tick = parseFloat(e.target.value);
  drawFrame();
};
document.querySelectorAll(".speed").forEach((b) => {
  b.onclick = () => {
    if (!V) return;
    document.querySelectorAll(".speed").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    if (b.dataset.speed === "inst") {
      V.tick = V.rounds[V.roundIdx].maxTick;
      drawFrame();
    } else {
      V.speed = parseFloat(b.dataset.speed);
    }
  };
});
