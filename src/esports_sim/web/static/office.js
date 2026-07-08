/* Office v3 — blockout→beautify pipeline.

   office_plan.json is the single source of truth for the HQ layout.
   scripts/render_office_guide.py rasterizes the SAME plan as flat guide
   images; Scenario repaints them (img2img, structure preserved) into
   assets/office/painted/. This file renders the plan interactively:

   - PAINTED mode (when painted/base.webp exists): the Scenario art is
     the scene; the SVG on top carries only hotspots, labels, hover
     glows, empty-lot dashes, per-annex painted patches, and dynamic
     bits (trophies). Art and hotspots can't drift apart because both
     derive from the same plan + the same projection.
   - GEOMETRY mode (fallback): full flat render — floors, walls with
     doorways, furniture boxes. This is also exactly what the guide
     images look like, so what you ship is what Scenario saw.

   Desk anchors in the plan are reserved for future PixiJS characters.
   Relies on app.js globals: $, el, api, money, toast, App. */

const OFFICE_ART = "/assets/office";

let OFFICE_DATA = null; // cached office_plan.json
let OFFICE_PAINTED = null; // true/false once probed

/* -- projection (same 2:1 iso as the match viewer + guide script) ---------- */

const oiso = (x, y) => [x + y, (x - y) / 2];

const OSVG = "http://www.w3.org/2000/svg";
function osvg(tag, attrs, parent) {
  const n = document.createElementNS(OSVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

const opts = (pts) => pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");

function roomCorners(r) {
  return [
    [r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h],
  ].map(([x, y]) => oiso(x, y));
}

/* World rect shared with the guide renderer — MUST match GuideRenderer's
   bounds math so painted art lands exactly on the geometry. */
function officeWorldRect(plan) {
  const pts = [...plan.rooms, ...plan.annexes].flatMap(roomCorners);
  const pad = plan.render.pad;
  const minX = Math.min(...pts.map((p) => p[0])) - pad;
  const minY = Math.min(...pts.map((p) => p[1])) - pad;
  const maxX = Math.max(...pts.map((p) => p[0])) + pad;
  const maxY = Math.max(...pts.map((p) => p[1])) + pad + plan.render.wall_h + 4;
  return [minX, minY, maxX - minX, maxY - minY];
}

/* -- shared-edge analysis (geometry mode) ---------------------------------- */

function edgeSegments(rooms) {
  const exterior = [];
  const interior = [];
  for (const r of rooms) {
    const edges = [
      { fixed: r.y,       lo: r.x, hi: r.x + r.w, axis: "h", side: "front" },
      { fixed: r.y + r.h, lo: r.x, hi: r.x + r.w, axis: "h", side: "back" },
      { fixed: r.x,       lo: r.y, hi: r.y + r.h, axis: "v", side: "left" },
      { fixed: r.x + r.w, lo: r.y, hi: r.y + r.h, axis: "v", side: "right" },
    ];
    for (const e of edges) {
      let spans = [[e.lo, e.hi]];
      for (const o of rooms) {
        if (o === r) continue;
        const touches =
          e.axis === "h"
            ? (o.y === e.fixed || o.y + o.h === e.fixed) && o.x < e.hi && o.x + o.w > e.lo
            : (o.x === e.fixed || o.x + o.w === e.fixed) && o.y < e.hi && o.y + o.h > e.lo;
        if (!touches) continue;
        const s = Math.max(e.lo, e.axis === "h" ? o.x : o.y);
        const t = Math.min(e.hi, e.axis === "h" ? o.x + o.w : o.y + o.h);
        if (t - s > 0.5 && r.id < o.id) {
          interior.push({ axis: e.axis, fixed: e.fixed, lo: s, hi: t });
        }
        spans = spans.flatMap(([a, b]) => {
          const out = [];
          if (s > a) out.push([a, Math.min(b, s)]);
          if (t < b) out.push([Math.max(a, t), b]);
          return out.filter(([p, q]) => q - p > 0.3);
        });
      }
      for (const [a, b] of spans) {
        exterior.push({ axis: e.axis, fixed: e.fixed, lo: a, hi: b, side: e.side });
      }
    }
  }
  return { exterior, interior };
}

function segPoints(seg) {
  const [a, b] =
    seg.axis === "h"
      ? [[seg.lo, seg.fixed], [seg.hi, seg.fixed]]
      : [[seg.fixed, seg.lo], [seg.fixed, seg.hi]];
  return [oiso(a[0], a[1]), oiso(b[0], b[1])];
}

/* -- furniture (geometry mode; boxes come from the plan) --------------------- */

function isoBox(g, x, y, w, d, h, cls) {
  const c = [oiso(x, y), oiso(x + w, y), oiso(x + w, y + d), oiso(x, y + d)];
  const lift = (p) => [p[0], p[1] - h];
  osvg("polygon", { points: opts([c[3], c[0], lift(c[0]), lift(c[3])]), class: `${cls} face-a` }, g);
  osvg("polygon", { points: opts([c[0], c[1], lift(c[1]), lift(c[0])]), class: `${cls} face-b` }, g);
  osvg("polygon", { points: opts(c.map(lift)), class: `${cls} face-top` }, g);
}

function furnitureFor(room, level) {
  if (room.furniture) return room.furniture;
  if (room.furniture_by_level) {
    return room.furniture_by_level[level >= 3 ? "3" : "1"] ?? [];
  }
  return [];
}

function drawFurniture(g, room, level) {
  for (const f of furnitureFor(room, level)) {
    isoBox(g, room.x + f.x, room.y + f.y, f.w, f.d, f.h, `furn-${f.type}`);
  }
}

/* Trophies are dynamic (one per championship) so they render in BOTH modes
   as an overlay on the lounge shelf. */
function drawTrophies(svg, plan) {
  const lounge = plan.rooms.find((r) => r.id === "lounge");
  if (!lounge) return;
  const cups = Math.min(6, (App.state?.champions ?? []).length);
  const g = osvg("g", { class: "office-trophies" }, svg);
  for (let i = 0; i < cups; i++) {
    isoBox(g, lounge.x + 9.4 + i * 0.62, lounge.y + 1.3, 0.4, 0.4, 2.1, "furn-trophy");
  }
}

/* -- navigation ------------------------------------------------------------ */

function officeGoTab(names) {
  for (const n of names.split("|")) {
    const btn = document.querySelector(`#tabs [data-tab="${n}"]`);
    if (btn) { btn.click(); return; }
  }
}

function officeCloseFocusPicker() {
  const pop = document.getElementById("office-pop");
  if (pop) pop.remove();
}

function officeOpenFocusPicker(stage) {
  officeCloseFocusPicker();
  const s = App.state;
  const pop = el("div", "office-pop");
  pop.id = "office-pop";
  pop.onclick = (e) => e.stopPropagation();
  pop.appendChild(el("div", "office-pop-title", "Training focus"));
  for (const o of s.focus_options ?? []) {
    const b = el("button", "btn btn-sm" + (o === s.training_focus ? " active" : ""), o);
    b.onclick = async (e) => {
      e.stopPropagation();
      await api("/api/actions/training", { focus: o });
      App.state.training_focus = o;
      toast(`Training focus set: ${o}`);
      officeCloseFocusPicker();
    };
    pop.appendChild(b);
  }
  stage.appendChild(pop);
  setTimeout(() => document.addEventListener("click", officeCloseFocusPicker, { once: true }), 0);
}

/* -- painted-scene compositor -------------------------------------------------- */

/* Cache: one composed object-URL per facility-state signature. */
const OFFICE_SCENE_CACHE = { sig: null, url: null };

function officeLoadImage(src) {
  return new Promise((resolve, reject) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = reject;
    i.src = src;
  });
}

async function officeComposeScene(built, facilities) {
  const sig = built
    .map((a) => `${a.id}:${(facilities[a.id]?.level ?? 1) >= 3 ? 3 : 1}`)
    .sort()
    .join("|");
  if (OFFICE_SCENE_CACHE.sig === sig) return OFFICE_SCENE_CACHE.url;
  if (!built.length) return null; // bare base is already showing

  let baseImg;
  try {
    baseImg = await officeLoadImage(`${OFFICE_ART}/painted/base.webp`);
  } catch (e) {
    return null;
  }
  const W = baseImg.naturalWidth, H = baseImg.naturalHeight;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(baseImg, 0, 0);
  const base = ctx.getImageData(0, 0, W, H);
  const out = ctx.getImageData(0, 0, W, H);

  const scratch = document.createElement("canvas");
  scratch.width = W;
  scratch.height = H;
  const sctx = scratch.getContext("2d", { willReadFrequently: true });

  for (const a of built) {
    const variant = (facilities[a.id]?.level ?? 1) >= 3 ? "l3" : "l1";
    let img;
    try {
      img = await officeLoadImage(`${OFFICE_ART}/painted/${a.id}_${variant}.webp`);
    } catch (e) {
      continue; // missing variant: that wing just stays bare
    }
    sctx.clearRect(0, 0, W, H);
    sctx.drawImage(img, 0, 0, W, H);
    const layer = sctx.getImageData(0, 0, W, H).data;
    const O = out.data, B = base.data;
    // Copy pixels where this state's render differs from the bare base.
    // Threshold mirrors the art pipeline's diff mask (webp noise floor).
    for (let i = 0; i < O.length; i += 4) {
      const d =
        Math.abs(layer[i] - B[i]) +
        Math.abs(layer[i + 1] - B[i + 1]) +
        Math.abs(layer[i + 2] - B[i + 2]);
      if (d > 42) {
        O[i] = layer[i];
        O[i + 1] = layer[i + 1];
        O[i + 2] = layer[i + 2];
      }
    }
  }
  ctx.putImageData(out, 0, 0);

  const url = await new Promise((resolve) =>
    canvas.toBlob((b) => resolve(b ? URL.createObjectURL(b) : null), "image/png")
  );
  if (OFFICE_SCENE_CACHE.url) URL.revokeObjectURL(OFFICE_SCENE_CACHE.url);
  OFFICE_SCENE_CACHE.sig = sig;
  OFFICE_SCENE_CACHE.url = url;
  return url;
}

/* -- loading ----------------------------------------------------------------- */

async function officeLoadPlan() {
  if (!OFFICE_DATA) {
    OFFICE_DATA = await (await fetch("/office_plan.json")).json();
  }
  if (OFFICE_PAINTED === null) {
    OFFICE_PAINTED = await new Promise((resolve) => {
      const probe = new Image();
      probe.onload = () => resolve(true);
      probe.onerror = () => resolve(false);
      probe.src = `${OFFICE_ART}/painted/base.webp`;
    });
  }
  return OFFICE_DATA;
}

/* -- the scene -------------------------------------------------------------- */

async function office(v) {
  if (!App.state) return;
  const s = App.state;
  const plan = await officeLoadPlan();

  let facilities = {};
  try {
    facilities = (await api("/api/finances")).facilities ?? {};
  } catch (e) { /* pre-campaign */ }

  const card = el("div", "card office-card");
  card.innerHTML = `<h2>Headquarters
    <span class="muted" style="text-transform:none;letter-spacing:0">— click a room to jump to its desk</span></h2>
    <div class="office-head">
      <img class="logo" src="${s.user_team.logo}" alt="">
      <b>${s.user_team.name}</b>
      <span class="office-head-dim">S${s.season} · W${s.week} · ${s.phase}</span>
      <span class="spacer"></span>
      <span class="mono">${money(s.user_team.balance)}</span>
    </div>`;

  const stage = el("div", "office-stage" + (OFFICE_PAINTED ? " painted" : ""));

  const built = plan.annexes.filter((a) => (facilities[a.id]?.level ?? 0) > 0);
  const lots = plan.annexes.filter((a) => (facilities[a.id]?.level ?? 0) === 0);
  const rooms = [...plan.rooms, ...built];

  const vb = officeWorldRect(plan);
  const svg = osvg("svg", {
    viewBox: vb.map((n) => n.toFixed(1)).join(" "),
    class: "office-svg",
    preserveAspectRatio: "xMidYMid meet",
  });

  if (OFFICE_PAINTED) {
    // The painted scene IS the office; same transform as the guide.
    // Facility states composite per-PIXEL: each annex file is identical
    // to the base outside its own wing (guaranteed by the art pipeline's
    // diff-mask), so "copy where it differs" reconstructs any facility
    // combination seam-free — no clip geometry, no per-combination
    // renders. Composed asynchronously; base paints immediately.
    const img = osvg("image", {
      x: vb[0], y: vb[1], width: vb[2], height: vb[3],
      preserveAspectRatio: "none", class: "office-painted-base",
    }, svg);
    img.setAttribute("href", `${OFFICE_ART}/painted/base.webp`);
    officeComposeScene(built, facilities).then((url) => {
      if (url) img.setAttribute("href", url);
    });
    // Room borders are drawn as a VECTOR overlay from the plan — the
    // paint supplies texture and furniture, but the lines that must
    // match the hotspots come from the same geometry as the hotspots.
    // (Generated interiors drift; ours can't.)
    const { exterior, interior } = edgeSegments(rooms);
    for (const w of interior) {
      const mid = (w.lo + w.hi) / 2;
      const half = Math.min(plan.render.door_w, (w.hi - w.lo) * 0.5) / 2;
      for (const [a, b] of [[w.lo, mid - half], [mid + half, w.hi]]) {
        if (b - a < 0.3) continue;
        const [p1, p2] = segPoints({ ...w, lo: a, hi: b });
        osvg("line", {
          x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1],
          class: "office-wall-in painted-line",
        }, svg);
      }
    }
    for (const w of exterior) {
      const [p1, p2] = segPoints(w);
      osvg("line", {
        x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1],
        class: "office-wall-crown painted-line",
      }, svg);
    }
  } else {
    // Geometry mode: the guide look, interactive.
    const { exterior, interior } = edgeSegments(rooms);
    const ordered = [...rooms].sort(
      (a, b) =>
        Math.max(...roomCorners(a).map((p) => p[1])) -
        Math.max(...roomCorners(b).map((p) => p[1]))
    );
    for (const r of ordered) {
      const g = osvg("g", { class: `office-geom room-${r.id}` }, svg);
      const level = facilities[r.id]?.level ?? 0;
      osvg("polygon", {
        points: opts(roomCorners(r)),
        class: "office-floor" + (level >= 3 ? " floor-lux" : ""),
      }, g);
      drawFurniture(g, r, level);
    }
    for (const w of interior) {
      const mid = (w.lo + w.hi) / 2;
      const half = Math.min(plan.render.door_w, (w.hi - w.lo) * 0.5) / 2;
      for (const [a, b] of [[w.lo, mid - half], [mid + half, w.hi]]) {
        if (b - a < 0.3) continue;
        const [p1, p2] = segPoints({ ...w, lo: a, hi: b });
        osvg("line", { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1], class: "office-wall-in" }, svg);
      }
    }
    for (const w of exterior) {
      const [p1, p2] = segPoints(w);
      if (w.side === "front" || w.side === "right") {
        osvg("polygon", {
          points: opts([p1, p2, [p2[0], p2[1] + plan.render.wall_h], [p1[0], p1[1] + plan.render.wall_h]]),
          class: "office-wall-out",
        }, svg);
      }
      osvg("line", { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1], class: "office-wall-crown" }, svg);
    }
  }

  drawTrophies(svg, plan);

  // Interaction layer (both modes): transparent room polygons that ARE the
  // hotspots, plus labels and empty-lot dashes.
  for (const r of rooms) {
    const g = osvg("g", { class: "office-room-g" }, svg);
    const hot = osvg("polygon", {
      points: opts(roomCorners(r)), class: "office-hot",
    }, g);
    const level = facilities[r.id]?.level ?? 0;
    const [lx, ly] = oiso(r.x + r.w / 2, r.y + r.h / 2);
    const label = osvg("text", { x: lx, y: ly + r.h / 4 + 2.4, class: "office-label" }, g);
    label.textContent = r.label + (facilities[r.id] ? ` · L${level}` : "");
    const sub = osvg("text", { x: lx, y: ly + r.h / 4 + 5.0, class: "office-sub" }, g);
    sub.textContent = r.sub;
    if (r.go || r.training || facilities[r.id]) {
      g.classList.add("clickable");
      g.onclick = (e) => {
        e.stopPropagation();
        if (r.training) officeOpenFocusPicker(stage);
        else if (r.go) officeGoTab(r.go);
        else officeGoTab("finances");
      };
    }
  }
  for (const a of lots) {
    const g = osvg("g", { class: "office-room-g office-lot clickable" }, svg);
    osvg("polygon", { points: opts(roomCorners(a)), class: "office-lot-floor" }, g);
    const [lx, ly] = oiso(a.x + a.w / 2, a.y + a.h / 2);
    const label = osvg("text", { x: lx, y: ly + 1.2, class: "office-label lot" }, g);
    label.textContent = `+ ${a.label}`;
    const sub = osvg("text", { x: lx, y: ly + 3.8, class: "office-sub" }, g);
    sub.textContent = "build in Finances";
    g.onclick = (e) => { e.stopPropagation(); officeGoTab("finances"); };
  }

  stage.appendChild(svg);
  card.appendChild(stage);
  v.appendChild(card);
}
