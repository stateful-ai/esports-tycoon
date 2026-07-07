/* 2D match replay. Pure consumer of one event log — no sim logic here.
   Positions come from round.move events (placement + arrivals); a move
   takes MOVE_TICKS (6) ticks, so dots interpolate over [arrival-6, arrival]. */

const MOVE_TICKS = 6;
const TICKS_PER_SEC = 2; // 1 tick = 0.5 s of game time
const UTIL_MARKER_TICKS = 8; // how long a utility marker lingers after use
const KILL_FLASH_TICKS = 3;  // how long the death ring lingers after a kill
const TRAIL_SPAN = 0.4;      // fraction of a move segment covered by the fading trail

let V = null; // active replay session

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
          placements: {}, moves: {}, kills: [], utility: [],
          plant: null, defuse: null, end: null,
          scoreBefore: [scoreA, scoreB], maxTick: 1,
        };
        rounds.push(cur);
        break;
      case "round.move":
        if (!cur) break;
        if (e.from_callout === null) cur.placements[e.player_id] = e.to_callout;
        else {
          (cur.moves[e.player_id] ??= []).push({ tick: e.tick, from: e.from_callout, to: e.to_callout });
          cur.maxTick = Math.max(cur.maxTick, e.tick);
        }
        break;
      case "round.kill":
        cur.kills.push(e);
        cur.maxTick = Math.max(cur.maxTick, e.tick);
        break;
      case "round.utility_used":
        cur.utility.push(e);
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

const pos = (cid) => {
  const c = V.map.callouts[cid];
  return c ? [c.x, 100 - c.y] : [50, 50];
};

// Richer variant of playerPos: also reports whether the player is mid-move
// and where the current segment started, so callers (motion trail) can
// draw a short fading line without re-deriving the interpolation math.
function playerMoveInfo(round, pid, t) {
  let at = round.placements[pid] ?? null;
  const moves = round.moves[pid] ?? [];
  for (const m of moves) {
    if (m.tick <= t) { at = m.to; }
    else if (m.tick - MOVE_TICKS <= t) {
      const [x1, y1] = pos(m.from), [x2, y2] = pos(m.to);
      const f = (t - (m.tick - MOVE_TICKS)) / MOVE_TICKS;
      return { pos: [x1 + (x2 - x1) * f, y1 + (y2 - y1) * f], moving: true, from: [x1, y1], f };
    } else break;
  }
  return at ? { pos: pos(at), moving: false } : null;
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

// Utility markers: recomputed from scratch every frame (deterministic in
// (round, tick)), so their fade/pulse is plain JS math rather than a CSS
// animation — the transient layer is fully rebuilt every frame and a
// keyframe animation would just restart each time.
function drawUtilityMarkers(round, t) {
  const abilities = V.abilities || {};
  for (const u of round.utility) {
    const age = t - u.tick;
    if (age < 0 || age > UTIL_MARKER_TICKS) continue;
    const p = playerPos(round, u.player_id, u.tick);
    if (!p) continue;
    const [x, y] = p;
    const fade = 1 - age / UTIL_MARKER_TICKS;
    const kind = abilityKind(abilities[u.ability_id]);
    switch (kind) {
      case "smoke":
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: 3, class: "util-marker util-smoke",
          opacity: (fade * 0.5).toFixed(2),
        }));
        break;
      case "flash": {
        const r = 1.7;
        const d = `M${x} ${y - r} L${x + r * .4} ${y - r * .4} L${x + r} ${y} L${x + r * .4} ${y + r * .4} ` +
          `L${x} ${y + r} L${x - r * .4} ${y + r * .4} L${x - r} ${y} L${x - r * .4} ${y - r * .4} Z`;
        V.dyn.appendChild(svgEl("path", { d, class: "util-marker util-flash", opacity: fade.toFixed(2) }));
        break;
      }
      case "damage":
        V.dyn.appendChild(svgEl("path", {
          d: `M${x - 1.8} ${y} L${x + 1.8} ${y} M${x} ${y - 1.8} L${x} ${y + 1.8}`,
          class: "util-marker util-damage", opacity: fade.toFixed(2),
        }));
        break;
      case "info":
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: (1.4 + age * 0.35).toFixed(2),
          class: "util-marker util-info", opacity: (fade * 0.9).toFixed(2),
        }));
        break;
      case "ult":
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: (4 + Math.sin(age * 1.3) * 0.7).toFixed(2),
          class: "util-marker util-ult", opacity: (fade * 0.7).toFixed(2),
        }));
        break;
      default:
        V.dyn.appendChild(svgEl("circle", {
          cx: x, cy: y, r: 1.6, class: "util-marker util-generic", opacity: (fade * 0.5).toFixed(2),
        }));
    }
  }
}

// Brief fading ring at the death spot, same math-driven approach as above.
function drawKillFlashes(round, t) {
  for (const k of round.kills) {
    const age = t - k.tick;
    if (age < 0 || age > KILL_FLASH_TICKS) continue;
    const cid = k.callout_id ?? round.placements[k.victim_id];
    if (!cid) continue;
    const [x, y] = pos(cid);
    const fade = 1 - age / KILL_FLASH_TICKS;
    V.dyn.appendChild(svgEl("circle", {
      cx: x, cy: y, r: (2 + age * 1.4).toFixed(2),
      class: "kill-flash", opacity: (fade * 0.85).toFixed(2),
    }));
  }
}

function drawStatic() {
  const svg = document.getElementById("v-map");
  svg.innerHTML = "";
  for (const [a, b] of V.map.edges) {
    const [x1, y1] = pos(a), [x2, y2] = pos(b);
    svg.appendChild(svgEl("line", { x1, y1, x2, y2, class: "edge" }));
  }
  const siteAgg = {};
  for (const [cid, c] of Object.entries(V.map.callouts)) {
    const [x, y] = pos(cid);
    const isSite = c.zone === "site";
    svg.appendChild(svgEl("circle", {
      cx: x, cy: y, r: isSite ? 3.4 : 2.2,
      class: "callout-dot" + (isSite ? " callout-site" : ""),
    }));
    const label = svgEl("text", { x, y: y + 4.6, class: "callout-label" });
    label.textContent = c.name;
    svg.appendChild(label);
    if (isSite) {
      (siteAgg[c.site] ??= []).push([x, y]);
    }
  }
  for (const [site, pts] of Object.entries(siteAgg)) {
    const x = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const y = pts.reduce((s, p) => s + p[1], 0) / pts.length - 4.5;
    const t = svgEl("text", { x, y, class: "site-label" });
    t.textContent = site.toUpperCase();
    svg.appendChild(t);
  }
  // V.dyn: transient layer, fully cleared + rebuilt every frame (markers,
  // kill flashes, motion trails, death marks).
  V.dyn = svgEl("g", {});
  svg.appendChild(V.dyn);

  // V.persist: elements that live across frames (spike, player dots) so a
  // real CSS transition/animation can run instead of restarting each tick.
  V.persist = svgEl("g", {});
  svg.appendChild(V.persist);
  V.playerEls = {};
  V.spikeEl = svgEl("rect", { width: 2.8, height: 2.8, class: "spike" });
  V.spikeEl.style.display = "none";
  V.spikeRingEl = svgEl("circle", { r: 2.2, class: "spike-ring" });
  V.spikeRingEl.style.display = "none";
  V.persist.appendChild(V.spikeRingEl);
  V.persist.appendChild(V.spikeEl);
}

function hidePlayerEl(pid) {
  const e = V.playerEls[pid];
  if (e) { e.circle.style.display = "none"; e.label.style.display = "none"; }
}

function getPlayerEls(pid) {
  let e = V.playerEls[pid];
  if (!e) {
    const circle = svgEl("circle", { r: 1.7, class: "pdot" });
    const label = svgEl("text", { class: "plabel" });
    V.persist.appendChild(circle);
    V.persist.appendChild(label);
    e = V.playerEls[pid] = { circle, label };
  }
  return e;
}

function drawFrame() {
  const round = V.rounds[V.roundIdx];
  const t = V.tick;
  V.dyn.innerHTML = "";

  // Transient overlays first so player dots (persistent layer, drawn after
  // V.dyn in the DOM) render on top of them.
  drawKillFlashes(round, t);
  drawUtilityMarkers(round, t);

  // Spike — persistent element, updated in place so its CSS pulse animation
  // keeps running instead of restarting every frame.
  const planted = round.plant && round.plant.tick <= t;
  if (planted) {
    const [x, y] = pos(round.plant.callout_id);
    V.spikeEl.setAttribute("x", x - 1.4);
    V.spikeEl.setAttribute("y", y - 1.4);
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
      const p = pos(death.callout_id ?? round.placements[pid]);
      if (p) {
        V.dyn.appendChild(svgEl("path", {
          d: `M${p[0] - 1.2} ${p[1] - 1.2} L${p[0] + 1.2} ${p[1] + 1.2} M${p[0] - 1.2} ${p[1] + 1.2} L${p[0] + 1.2} ${p[1] - 1.2}`,
          stroke: "currentColor", class: "pdot " + teamCls + " dead", "stroke-width": .7,
        }));
      }
      continue;
    }
    const move = playerMoveInfo(round, pid, t);
    if (!move) { hidePlayerEl(pid); continue; }
    const [x, y] = move.pos;
    const { circle, label } = getPlayerEls(pid);
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("class", "pdot " + teamCls);
    circle.style.display = "";
    label.setAttribute("x", x);
    label.setAttribute("y", y - 2.3);
    label.style.display = "";
    label.textContent = info.handle;

    // Short fading motion trail while mid-move, so heading reads clearly.
    if (move.moving) {
      const [fx, fy] = move.from;
      const f0 = Math.max(0, move.f - TRAIL_SPAN);
      const sx = fx + (x - fx) * f0, sy = fy + (y - fy) * f0;
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
    ? `${V.names[round.end.winner_id]} win — ${round.end.reason.replaceAll("_", " ")}`
    : planted ? "SPIKE PLANTED" : "";

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
    .map((k) => {
      const kn = V.players[k.killer_id]?.handle ?? k.killer_id;
      const vn = V.players[k.victim_id]?.handle ?? k.victim_id;
      return {
        tick: k.tick,
        html: `<div class="k">${kn} <span class="${k.headshot ? "hs" : ""}">${k.headshot ? "☠" : "→"}</span> ${vn}` +
          ` <span class="muted">${k.weapon_id}${k.is_trade ? " · trade" : ""}</span></div>`,
      };
    })
    .concat(round.utility
      .filter((u) => u.tick <= t)
      .map((u) => {
        const pn = V.players[u.player_id]?.handle ?? u.player_id;
        const ability = abilities[u.ability_id];
        const kind = abilityKind(ability);
        const name = ability?.name ?? u.ability_id;
        return {
          tick: u.tick,
          html: `<div class="u"><span class="u-chip u-${kind}"></span>${pn} used <span class="muted">${name}</span></div>`,
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
      V.roundIdx++;
      V.tick = 0;
    } else {
      V.playing = false;
      updatePlayBtn();
    }
  }
  drawFrame();
  requestAnimationFrame(loop);
}

function updatePlayBtn() {
  document.getElementById("v-play").textContent = V && V.playing ? "⏸" : "▶";
}

function setRound(idx) {
  V.roundIdx = Math.max(0, Math.min(V.rounds.length - 1, idx));
  V.tick = 0;
  drawFrame();
}

/* -- public api ------------------------------------------------------------------ */

async function openReplay(fixtureId, mapIndex) {
  const data = await api(`/api/replay/${fixtureId}/${mapIndex}`);
  const names = {};
  names[data.team_a] = data.fixture.team_a_name;
  names[data.team_b] = data.fixture.team_b_name;
  V = {
    map: data.map,
    players: data.players,
    teamA: data.team_a,
    teamB: data.team_b,
    names,
    abilities: data.abilities || {}, // guard: older payloads may omit this
    rounds: parseReplay(data),
    roundIdx: 0,
    tick: 0,
    playing: true,
    speed: 1,
    lastTs: null,
  };
  document.getElementById("v-title").innerHTML =
    `<b>${names[data.team_a]}</b> vs <b>${names[data.team_b]}</b> · ${data.map.display_name}`;
  drawStatic();
  drawFrame();
  document.getElementById("viewer").classList.remove("hidden");
  updatePlayBtn();
  requestAnimationFrame(loop);
}

function closeViewer() {
  if (V) V.playing = false;
  V = null;
  document.getElementById("viewer").classList.add("hidden");
}

document.getElementById("v-play").onclick = () => {
  if (!V) return;
  V.playing = !V.playing;
  V.lastTs = null;
  updatePlayBtn();
  if (V.playing) requestAnimationFrame(loop);
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
