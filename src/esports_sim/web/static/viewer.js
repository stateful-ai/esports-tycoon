/* 2D match replay. Pure consumer of one event log — no sim logic here.
   Positions come from round.move events (placement + arrivals); a move
   takes MOVE_TICKS (6) ticks, so dots interpolate over [arrival-6, arrival]. */

const MOVE_TICKS = 6;
const TICKS_PER_SEC = 2; // 1 tick = 0.5 s of game time

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

function playerPos(round, pid, t) {
  let at = round.placements[pid] ?? null;
  const moves = round.moves[pid] ?? [];
  let prev = at;
  for (const m of moves) {
    if (m.tick <= t) { at = m.to; prev = m.to; }
    else if (m.tick - MOVE_TICKS <= t) {
      const [x1, y1] = pos(m.from), [x2, y2] = pos(m.to);
      const f = (t - (m.tick - MOVE_TICKS)) / MOVE_TICKS;
      return [x1 + (x2 - x1) * f, y1 + (y2 - y1) * f];
    } else break;
  }
  return at ? pos(at) : null;
}

function deathOf(round, pid) {
  const k = round.kills.find((k) => k.victim_id === pid);
  return k ? k : null;
}

/* -- svg --------------------------------------------------------------------- */

const SVG = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

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
  V.dyn = svgEl("g", {});
  svg.appendChild(V.dyn);
}

function drawFrame() {
  const round = V.rounds[V.roundIdx];
  const t = V.tick;
  V.dyn.innerHTML = "";

  // Spike.
  if (round.plant && round.plant.tick <= t) {
    const [x, y] = pos(round.plant.callout_id);
    V.dyn.appendChild(svgEl("rect", {
      x: x - 1.4, y: y - 1.4, width: 2.8, height: 2.8,
      transform: `rotate(45 ${x} ${y})`, class: "spike",
    }));
  }

  // Players.
  for (const [pid, info] of Object.entries(V.players)) {
    if (!(pid in round.placements)) continue;
    const death = deathOf(round, pid);
    const dead = death && death.tick <= t;
    const p = dead ? pos(death.callout_id ?? round.placements[pid]) : playerPos(round, pid, t);
    if (!p) continue;
    const cls = "pdot " + (info.team_id === V.teamA ? "a" : "b") + (dead ? " dead" : "");
    if (dead) {
      V.dyn.appendChild(svgEl("path", {
        d: `M${p[0] - 1.2} ${p[1] - 1.2} L${p[0] + 1.2} ${p[1] + 1.2} M${p[0] - 1.2} ${p[1] + 1.2} L${p[0] + 1.2} ${p[1] - 1.2}`,
        stroke: "currentColor", class: cls, "stroke-width": .7,
      }));
    } else {
      V.dyn.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: 1.7, class: cls }));
      const label = svgEl("text", { x: p[0], y: p[1] - 2.3, class: "plabel" });
      label.textContent = info.handle;
      V.dyn.appendChild(label);
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
    : round.plant && round.plant.tick <= t ? "SPIKE PLANTED" : "";

  // Clock: 100s round, 45s post-plant.
  let secs;
  if (round.plant && round.plant.tick <= t) secs = Math.max(0, 45 - (t - round.plant.tick) / TICKS_PER_SEC);
  else secs = Math.max(0, 100 - t / TICKS_PER_SEC);
  const mm = String(Math.floor(secs / 60)), ss = String(Math.floor(secs % 60)).padStart(2, "0");
  document.getElementById("v-clock").textContent = `${mm}:${ss}`;

  // Kill feed (events up to t, newest first).
  const feed = document.getElementById("v-feed");
  feed.innerHTML = round.kills
    .filter((k) => k.tick <= t)
    .map((k) => {
      const kn = V.players[k.killer_id]?.handle ?? k.killer_id;
      const vn = V.players[k.victim_id]?.handle ?? k.victim_id;
      return `<div class="k">${kn} <span class="${k.headshot ? "hs" : ""}">${k.headshot ? "☠" : "→"}</span> ${vn}` +
        ` <span class="muted">${k.weapon_id}${k.is_trade ? " · trade" : ""}</span></div>`;
    })
    .reverse()
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
