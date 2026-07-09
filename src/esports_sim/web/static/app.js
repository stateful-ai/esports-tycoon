/* Campaign hub. Pure API consumer — all state lives server-side. */

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const money = (n) => (n == null ? "—" : n.toLocaleString() + " cr");

function toast(msg) {
  const t = el("div", "t", msg);
  $("#toast").appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

async function api(path, body) {
  const opts = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : undefined;
  const r = await fetch(path, opts);
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    toast(e.detail || "request failed");
    throw new Error(e.detail);
  }
  return r.json();
}

const App = { tab: "dashboard", state: null };

/* -- boot ------------------------------------------------------------------ */

async function boot() {
  if (App.tab === "dashboard") App.tab = "office"; // land on the visual HQ
  const b = await api("/api/bootstrap");
  if (!b.campaign) {
    const grid = $("#ng-teams");
    grid.innerHTML = "";
    // Pick screen groups the world by region (authored orgs first).
    const regions = [...new Set(b.teams.map((t) => t.region))].sort();
    for (const region of regions) {
      const head = el("div", "muted", region ? region.toUpperCase() : "");
      head.style.gridColumn = "1 / -1";
      head.style.marginTop = "6px";
      grid.appendChild(head);
      for (const t of b.teams.filter((x) => x.region === region)) {
        const btn = el(
          "button",
          "team-pick",
          `<b>${t.name}</b> <span class="pill">${t.tag}</span><br>
           <span class="muted">rep ${t.reputation} · ${money(t.balance)}</span>`
        );
        btn.onclick = async () => {
          await api("/api/new", { team_id: t.id, seed: parseInt($("#ng-seed").value) || 2026 });
          $("#newgame").classList.add("hidden");
          refresh();
        };
        grid.appendChild(btn);
      }
    }
    $("#newgame").classList.remove("hidden");
    return;
  }
  refresh();
  // Prime the Inbox tab badge on load (inbox.js is loaded after us, but this
  // runs post-await so its globals are defined; guard keeps boot resilient).
  if (typeof refreshInboxBadge === "function") refreshInboxBadge();
}

async function refresh() {
  App.state = await api("/api/state");
  const s = App.state;
  $("#context").textContent =
    `Season ${s.season} · Week ${s.week} · ${s.phase}  —  ${s.user_team.name}`;
  $("#balance").textContent = money(s.user_team.balance);
  render();
}

/* -- tabs ------------------------------------------------------------------- */

document.querySelectorAll(".tab").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    App.tab = b.dataset.tab;
    render();
  };
});

function render() {
  if (!App.state) return;
  // Each render gets a fresh container; a slower, superseded async render
  // finishes into a detached node instead of double-appending.
  const container = el("div");
  $("#view").replaceChildren(container);
  ({ office, inbox, dashboard, roster, tactics, standings, schedule, market, scouting, stats, finances })[App.tab](container);
}

/* -- helpers ------------------------------------------------------------------ */

function bar(value, opts = {}) {
  const cls = opts.invert
    ? value < 35 ? "good" : value < 65 ? "warn" : "bad"
    : value < 35 ? "bad" : value < 65 ? "warn" : "good";
  return `<div class="bar ${cls}" title="${Math.round(value)}"><i style="width:${Math.max(2, Math.min(100, value))}%"></i></div>`;
}

function stylePill(p) {
  return `<span class="pill">${p.role}</span> <span class="pill">${p.playstyle}</span>`;
}

// `sm` gives a 20px chip for inline use in buttons/veto text; the default
// (no cls) is the 40px card-style thumbnail. Hides itself on 404 so a
// missing asset degrades to just the map name instead of a broken-image box.
function mapThumb(mapId, cls = "") {
  return `<img class="map-thumb ${cls}" src="/assets/maps/${mapId}.webp" alt="${mapId}" onerror="this.style.display='none'">`;
}

// EHM-style star band: "★★★½–★★★★" for [3.5, 4]; single value collapses.
function starsRange(band) {
  if (!band) return `<span class="muted">unknown</span>`;
  const one = (v) => "★".repeat(Math.floor(v)) + (v % 1 >= 0.5 ? "½" : "");
  const [lo, hi] = band;
  return `<span class="stars" title="${lo}–${hi} of 5">${one(lo)}${
    hi > lo ? "–" + one(hi) : ""
  }</span>`;
}

/* -- screens --------------------------------------------------------------------- */

function dashboard(v) {
  const s = App.state;
  const g = el("div", "grid2");

  const team = el("div", "card");
  team.innerHTML = `<h2><img class="logo" src="${s.user_team.logo}" alt="">${s.user_team.name}</h2>
    <table><tbody>
      <tr><td>World rank</td><td class="num">#${s.user_team.world_rank ?? "—"}</td></tr>
      <tr><td>Record</td><td class="num">${s.user_team.record ? s.user_team.record.wins + "–" + s.user_team.record.losses : "—"}</td></tr>
      <tr><td>Reputation</td><td class="num">${s.user_team.reputation}</td></tr>
      <tr><td>Chemistry</td><td class="num">${s.user_team.chemistry}</td></tr>
      <tr><td>Fans</td><td class="num">${s.user_team.fan_count.toLocaleString()}</td></tr>
    </tbody></table>`;
  g.appendChild(team);

  const next = el("div", "card");
  if (s.next_fixture) {
    const f = s.next_fixture;
    next.innerHTML = `<h2>This week — ${f.stage} (BO${f.best_of})</h2>
      <p><b>${f.team_a_name}</b> vs <b>${f.team_b_name}</b></p>
      <div class="row" style="flex-wrap:wrap"><span class="muted">maps:</span> ${f.maps
        .map((m) => `${mapThumb(m)}<span class="muted" style="margin-right:8px">${m}</span>`)
        .join("")}</div>`;
  } else {
    next.innerHTML = `<h2>This week</h2><p class="muted">No fixture — ${s.phase}.</p>`;
  }
  const focus = el("div", "row");
  focus.innerHTML = `<label>Training focus&nbsp;</label>`;
  const sel = el("select");
  for (const o of s.focus_options) {
    const opt = el("option", "", o);
    opt.value = o;
    if (o === s.training_focus) opt.selected = true;
    sel.appendChild(opt);
  }
  sel.onchange = async () => {
    await api("/api/actions/training", { focus: sel.value });
    toast(`Training focus set: ${sel.value}`);
  };
  focus.appendChild(sel);
  next.appendChild(focus);
  if (s.scout && s.scout.target) {
    next.appendChild(el("p", "muted",
      `Scouting ${s.scout.target_name}: ${Math.round(s.scout.progress * 100)}% ` +
      `(assign from a rival's roster page)`));
  }
  g.appendChild(next);
  v.appendChild(g);

  const top = el("div", "card");
  top.innerHTML = `<h2>Top of the table</h2>`;
  const tt = el("table");
  tt.innerHTML =
    `<thead><tr><th>#</th><th>Team</th><th class="num">W</th><th class="num">L</th></tr></thead>`;
  const tb = el("tbody");
  s.standings_top.forEach((r, i) => {
    tb.appendChild(el("tr", r.team_id === s.user_team.id ? "me" : "", `
      <td>${i + 1}</td><td>${r.name}</td>
      <td class="num">${r.wins}</td><td class="num">${r.losses}</td>`));
  });
  tt.appendChild(tb);
  top.appendChild(tt);
  v.appendChild(top);

  if ((s.transfer_offers ?? []).length) {
    const oc = el("div", "card");
    oc.innerHTML = `<h2>Transfer offers</h2>`;
    for (const o of s.transfer_offers) {
      const row = el("div", "row", `
        <span style="min-width:280px"><b>${o.to_team_name}</b> bid
        <b class="mono">${money(o.fee)}</b> for <b>${o.handle}</b></span>
        <span class="muted">expires week ${o.expires_week}</span>`);
      const sell = el("button", "btn btn-sm", "Sell");
      sell.onclick = async () => {
        if (!confirm(`Sell ${o.handle} to ${o.to_team_name} for ${money(o.fee)}?`)) return;
        const r = await api("/api/actions/transfer_offer", { player_id: o.player_id, accept: true });
        toast(r.message); refresh();
      };
      const keep = el("button", "btn btn-sm", "Decline");
      keep.onclick = async () => {
        const r = await api("/api/actions/transfer_offer", { player_id: o.player_id, accept: false });
        toast(r.message); refresh();
      };
      row.appendChild(sell);
      row.appendChild(keep);
      oc.appendChild(row);
    }
    v.appendChild(oc);
  }

  const news = el("div", "card");
  news.innerHTML = `<h2>News</h2>` + s.news.map((n) => `<div class="newsline">${n}</div>`).join("");
  v.appendChild(news);
}

async function roster(v) {
  const teamId = App.rosterTeam ?? App.state.user_team.id;
  const data = await api(`/api/roster/${teamId}`);
  const card = el("div", "card");
  const fogNote = data.fog > 0
    ? ` <span class="muted">— scouted estimates ±${data.fog}</span>`
    : "";
  card.innerHTML = `<h2>Roster — ${data.team.name} (${data.players.length}/5)${fogNote}</h2>`;
  if ((data.tendencies ?? []).length) {
    card.appendChild(el("p", "muted",
      `Scouting book: ${data.tendencies.join(" · ")}`));
  }
  const cp = data.chemistry_pairs ?? { duos: [], feuds: [] };
  if (cp.duos.length || cp.feuds.length) {
    const bits = [
      ...cp.duos.map(([a, b]) => `🤝 ${a} + ${b}`),
      ...cp.feuds.map(([a, b]) => `⚡ ${a} vs ${b}`),
    ];
    card.appendChild(el("p", "muted", `Locker room: ${bits.join(" · ")}`));
  }
  if (!data.is_user_team) {
    const row = el("div", "row");
    const back = el("button", "btn btn-sm", "← My team");
    back.onclick = () => { App.rosterTeam = null; render(); };
    row.appendChild(back);
    const scout = el(
      "button", "btn btn-sm",
      data.scouting_this
        ? `Scouting… ${Math.round(data.scout_progress * 100)}%`
        : "Assign scout"
    );
    scout.disabled = data.scouting_this && data.scout_progress >= 1;
    scout.onclick = async () => {
      const r = await api("/api/actions/scout", { team_id: teamId });
      toast(r.message); render();
    };
    row.appendChild(scout);
    card.appendChild(row);
  }
  const t = el("table");
  t.innerHTML = `<thead><tr>
    <th>Player</th><th>Role</th><th class="num">Age</th><th class="num">OVR</th>
    <th>Ceiling</th>
    <th>Form</th><th>Morale</th><th>Stamina</th>
    <th class="num">Salary</th><th class="num">Contract</th><th></th></tr></thead>`;
  const tb = el("tbody");
  for (const p of data.players) {
    const fogged = p.fog > 0;
    const ovr = fogged ? `~${Math.round(p.overall)}` : p.overall;
    const actions = data.is_user_team
      ? `<button class="btn btn-sm" data-act="talk">Talk</button>
         <button class="btn btn-sm" data-act="renew">Renew</button>
         <button class="btn btn-sm" data-act="release">Release</button>`
      : p.transfer_ask != null
        ? `<button class="btn btn-sm" data-act="bid" title="buy out this contract">Bid ${money(p.transfer_ask)}</button>`
        : "";
    const tr = el("tr", "", `
      <td><img class="portrait" src="${p.portrait}" alt=""><b>${p.handle}</b>${p.id === data.team.captain_id ? ' <span class="pill">IGL</span>' : ""}</td>
      <td>${stylePill(p)}</td>
      <td class="num">${p.age}</td>
      <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${ovr}</td>
      <td>${p.potential_stars != null ? starsRange([p.potential_stars, p.potential_stars]) : '<span class="muted">scout</span>'}</td>
      <td>${bar(p.form)}</td><td>${bar(p.morale)}</td><td>${bar(p.stamina)}</td>
      <td class="num">${money(p.salary)}/wk</td>
      <td class="num">${p.contract_weeks_left}w</td>
      <td>${actions}</td>`);
    if (!data.is_user_team && p.transfer_ask != null) {
      tr.querySelector('[data-act="bid"]').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`Buy ${p.handle} from ${data.team.name} for ${money(p.transfer_ask)}?`)) return;
        const r = await api("/api/actions/bid", { player_id: p.id });
        toast(r.message); refresh(); render();
      };
    }
    if (data.is_user_team) {
      tr.querySelector('[data-act="talk"]').onclick = (e) => {
        e.stopPropagation();
        openTalk(p);
      };
      tr.querySelector('[data-act="renew"]').onclick = async (e) => {
        e.stopPropagation();
        const r = await api("/api/actions/renew", { player_id: p.id });
        toast(r.message); refresh(); render();
      };
      tr.querySelector('[data-act="release"]').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`Release ${p.handle}? Severance = 6 weeks salary.`)) return;
        const r = await api("/api/actions/release", { player_id: p.id });
        toast(r.message); refresh(); render();
      };
    }
    tr.style.cursor = "pointer";
    let detail = null;
    tr.onclick = () => {
      if (detail) { detail.remove(); detail = null; return; }
      detail = el("tr", "", `<td colspan="10">${attrDetail(p)}</td>`);
      tr.after(detail);
    };
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  card.appendChild(t);
  v.appendChild(card);

  if (data.is_user_team) await staffCard(v);
}

async function staffCard(v) {
  const data = await api("/api/staff");
  const card = el("div", "card");
  card.innerHTML = `<h2>Backroom staff — ${money(data.weekly_cost)}/wk</h2>`;
  for (const role of data.roles) {
    const row = el("div", "row", "");
    const hired = data.hired[role];
    const head = `<span style="min-width:280px"><span class="pill">${role}</span> `;
    if (hired) {
      row.innerHTML = `${head}<b>${hired.name}</b>
        <span class="muted">q${Math.round(hired.quality)} · ${money(hired.salary)}/wk — boosts ${data.blurbs[role]}</span></span>`;
      const rel = el("button", "btn btn-sm", "Release");
      rel.onclick = async () => {
        const r = await api("/api/actions/release_staff", { role });
        toast(r.message); render();
      };
      row.appendChild(rel);
    } else {
      row.innerHTML = `${head}<span class="muted">vacant — ${data.blurbs[role]}</span></span>`;
      for (const c of data.candidates[role] ?? []) {
        const b = el("button", "btn btn-sm",
          `${c.name} (q${Math.round(c.quality)}, ${money(c.salary)}/wk)`);
        b.onclick = async () => {
          const r = await api("/api/actions/hire_staff", { candidate_id: c.id });
          toast(r.message); refresh(); render();
        };
        row.appendChild(b);
      }
    }
    card.appendChild(row);
  }
  v.appendChild(card);
}

function attrDetail(p) {
  const rows = Object.entries(p.attributes)
    .map(([k, val]) => `<tr><td>${k.replaceAll("_", " ")}</td><td>${bar(val)}</td><td class="num">${Math.round(val)}</td></tr>`)
    .join("");
  const agents = p.agents.map((a) => `${a.agent_id} (${Math.round(a.mastery)})`).join(", ");
  return `<div class="grid2">
    <table><tbody>${rows}</tbody></table>
    <div>
      <p class="muted">agents: ${agents || "—"}</p>
      <p class="muted">personality: ${
        (p.personality || [])
          .map((t) => `<span class="pill" title="${t.blurb || ""}">${t.id}</span>`)
          .join(" ") || "—"
      }</p>
      ${p.potential_stars != null
        ? `<p class="muted">ability: ${starsRange([p.ca_stars, p.ca_stars])} now · ${starsRange([p.potential_stars, p.potential_stars])} ceiling</p>`
        : ""}
      <p class="muted">asking salary next deal: ${money(p.asking_salary)}/wk</p>
    </div></div>`;
}

const TACTIC_DIALS = [
  ["aggression", "Aggression", "passive angles ↔ swing everything"],
  ["pace", "Pace", "slow defaults ↔ fast executes"],
  ["util_discipline", "Utility discipline", "dump on the hit ↔ hold for retakes"],
  ["eco_greed", "Eco greed", "save on broke rounds ↔ force-buy often"],
];

async function tactics(v) {
  const data = await api("/api/tactics");
  const tac = data.tactics;
  const card = el("div", "card");
  card.innerHTML = `<h2>Coaching strategy</h2>
    <p class="muted">The identity your team plays with. 50 is neutral on
    every dial; the effects run through the match engine itself.</p>`;
  const pending = {};
  for (const [key, label, hint] of TACTIC_DIALS) {
    const row = el("div", "row", `
      <span style="min-width:190px"><b>${label}</b><br><span class="muted">${hint}</span></span>`);
    const slider = el("input");
    slider.type = "range"; slider.min = 0; slider.max = 100;
    slider.value = tac[key];
    slider.style.flex = "1";
    const val = el("span", "mono", String(Math.round(tac[key])));
    val.style.minWidth = "34px";
    slider.oninput = () => { val.textContent = slider.value; pending[key] = parseFloat(slider.value); };
    row.appendChild(slider);
    row.appendChild(val);
    card.appendChild(row);
  }
  const siteRow = el("div", "row", `<span style="min-width:190px"><b>Site focus</b><br>
    <span class="muted">bias the attack toward one site</span></span>`);
  const sel = el("select");
  for (const o of ["balanced", "a", "b", "c"]) {
    const opt = el("option", "", o === "balanced" ? "balanced" : o.toUpperCase());
    opt.value = o;
    if (o === tac.site_focus) opt.selected = true;
    sel.appendChild(opt);
  }
  sel.onchange = () => { pending.site_focus = sel.value; };
  siteRow.appendChild(sel);
  card.appendChild(siteRow);

  const save = el("button", "btn btn-primary", "Set strategy");
  save.onclick = async () => {
    const r = await api("/api/actions/tactics", pending);
    toast(r.message);
  };
  card.appendChild(save);
  card.appendChild(el("p", "muted",
    "Scout a rival to at least 50% to read their coaching identity on their roster page."));
  v.appendChild(card);
}

async function standings(v) {
  const data = await api("/api/standings");
  for (const league of data.regions) {
    const card = el("div", "card");
    card.innerHTML = `<h2>${league.region.toUpperCase()} league${league.is_user ? " — your region" : ""}</h2>`;
    const t = el("table");
    t.innerHTML = `<thead><tr><th>#</th><th>Team</th><th class="num">W</th><th class="num">L</th>
      <th class="num">RW</th><th class="num">RL</th><th class="num">+/-</th><th class="num">Rep</th></tr></thead>`;
    const tb = el("tbody");
    const rowFor = (r, i) => {
      const tr = el("tr", r.id === App.state.user_team.id ? "me" : "", `
        <td>${i + 1}</td><td><img class="logo" src="${r.logo}" alt=""><b>${r.name}</b> <span class="pill">${r.tag}</span></td>
        <td class="num">${r.wins}</td><td class="num">${r.losses}</td>
        <td class="num">${r.rounds_won}</td><td class="num">${r.rounds_lost}</td>
        <td class="num">${r.diff > 0 ? "+" : ""}${r.diff}</td>
        <td class="num">${r.reputation}</td>`);
      tr.style.cursor = "pointer";
      tr.title = "view roster";
      tr.onclick = () => {
        App.rosterTeam = r.id === App.state.user_team.id ? null : r.id;
        document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
        document.querySelector('[data-tab="roster"]').classList.add("active");
        App.tab = "roster";
        render();
      };
      return tr;
    };
    league.rows.forEach((r, i) => tb.appendChild(rowFor(r, i)));
    t.appendChild(tb);
    card.appendChild(t);

    // Challengers underneath: the development circuit scouts live in.
    if ((league.tier2_rows ?? []).length) {
      const h = el("h2", "", `${league.region.toUpperCase()} Challengers <span class="muted" style="font-weight:400">— tier 2, click through to scout</span>`);
      h.style.marginTop = "14px";
      card.appendChild(h);
      const t2 = el("table");
      t2.innerHTML = t.querySelector("thead").outerHTML;
      const tb2 = el("tbody");
      league.tier2_rows.forEach((r, i) => tb2.appendChild(rowFor(r, i)));
      t2.appendChild(tb2);
      card.appendChild(t2);
    }
    v.appendChild(card);
  }
}

const REGION_CODES = { am: "Americas", em: "EMEA", pa: "Pacific", ch: "China" };
const STAGE_LABELS = {
  regular: "league",
  semi: "semifinal",
  final: "regional final",
  masters_qf: "Masters QF",
  masters_sf: "Masters semi",
  masters_final: "MASTERS FINAL",
};
const stageLabel = (s) => STAGE_LABELS[s] ?? s;

function bracketNode(f) {
  if (!f) return el("div", "bracket-node muted", "TBD");
  const line = (tid, name) => {
    const winner = f.played && f.winner_id === tid;
    const score = f.played
      ? (tid === f.team_a ? f.map_score[0] : f.map_score[1])
      : "";
    return `<div class="bracket-team ${winner ? "w" : ""}">
      <span>${name}</span><b class="mono">${score}</b></div>`;
  };
  const n = el("div", "bracket-node",
    line(f.team_a, f.team_a_name) + line(f.team_b, f.team_b_name));
  if (f.played) {
    n.style.cursor = "pointer";
    n.title = "see schedule for maps";
  }
  return n;
}

function bracketCard(title, columns) {
  // columns: list of fixture-lists, left to right (TBD-padded).
  if (!columns[0]?.some(Boolean)) return null;
  const card = el("div", "card");
  card.innerHTML = `<h2>${title}</h2>`;
  const wrap = el("div", "bracket");
  for (const colFixtures of columns) {
    const col = el("div", "bracket-col");
    for (const f of colFixtures) col.appendChild(bracketNode(f));
    wrap.appendChild(col);
  }
  card.appendChild(wrap);
  return card;
}

function regionCodeOf(fixtureId) {
  const m = fixtureId.match(/^s\d+(am|em|pa|ch)(semi|final)/);
  return m ? m[1] : null;
}

async function schedule(v) {
  const data = await api("/api/schedule");

  // Masters bracket (QF -> SF -> Final), once it exists.
  const mqf = data.fixtures.filter((f) => f.stage === "masters_qf");
  const msf = data.fixtures.filter((f) => f.stage === "masters_sf");
  const mf = data.fixtures.filter((f) => f.stage === "masters_final");
  if (mqf.length) {
    const card = bracketCard("MASTERS — world championship", [
      mqf, msf.length ? msf : [null, null], mf.length ? mf : [null],
    ]);
    if (card) v.appendChild(card);
  }

  // One regional bracket per league, user's region first.
  const regional = data.fixtures.filter((f) => regionCodeOf(f.id));
  const codes = [...new Set(regional.map((f) => regionCodeOf(f.id)))];
  const userRegion = (App.state.user_team.region || "").slice(0, 2);
  codes.sort((a, b) => (a === userRegion ? -1 : b === userRegion ? 1 : a < b ? -1 : 1));
  for (const code of codes) {
    const rf = regional.filter((f) => regionCodeOf(f.id) === code);
    const semis = rf.filter((f) => f.stage === "semi");
    const final = rf.filter((f) => f.stage === "final");
    const card = bracketCard(
      `${REGION_CODES[code] ?? code} playoffs`,
      [semis, final.length ? final : [null]],
    );
    if (card) v.appendChild(card);
  }
  const byWeek = new Map();
  for (const f of data.fixtures) {
    if (!byWeek.has(f.week)) byWeek.set(f.week, []);
    byWeek.get(f.week).push(f);
  }
  for (const [week, fixtures] of byWeek) {
    const card = el("div", "card");
    const tag = week === data.current_week ? " — this week" : "";
    card.innerHTML = `<h2>Week ${week}${tag}</h2>`;
    for (const f of fixtures) {
      const mine = [f.team_a, f.team_b].includes(App.state.user_team.id);
      const line = el("div", "row", "");
      let score = "";
      if (f.played) {
        score = f.best_of > 1
          ? `<b class="mono">${f.map_score[0]}–${f.map_score[1]}</b>`
          : `<b class="mono">${f.results[0].score_a}–${f.results[0].score_b}</b>`;
      }
      line.innerHTML = `
        <span class="pill">${stageLabel(f.stage)}</span>
        <span style="min-width:340px">${mine ? "<b>" : ""}${f.team_a_name} vs ${f.team_b_name}${mine ? "</b>" : ""}</span>
        ${score}`;
      for (let i = 0; i < f.results.length; i++) {
        const r = f.results[i];
        const b = el(
          "button", "btn btn-sm",
          `${mapThumb(r.map_id, "sm")}${r.map_id} ${r.score_a}–${r.score_b}${r.has_replay ? " ▶" : ""}`
        );
        b.disabled = !r.has_replay;
        b.title = r.has_replay ? "watch replay" : "replay only kept for the latest week";
        b.onclick = () => openReplay(f.id, i);
        line.appendChild(b);
      }
      card.appendChild(line);
      if (f.veto.length) {
        const vetoRow = el("div", "veto-row");
        vetoRow.appendChild(el("span", "muted", "veto:"));
        for (const entry of f.veto) {
          const mapId = entry.trim().split(" ").pop();
          vetoRow.appendChild(el("span", "veto-chip", `${mapThumb(mapId, "sm")}${entry}`));
        }
        card.appendChild(vetoRow);
      }
    }
    v.appendChild(card);
  }
}

async function market(v) {
  const data = await api("/api/market");
  const card = el("div", "card");
  card.innerHTML = `<h2>Free agents (${data.free_agents.length})</h2>` +
    (data.market_scouting < 1
      ? `<p class="muted">Market coverage ${Math.round(data.market_scouting * 100)}% —
         numbers below are estimates${data.market_scouting === 0 ? "; assign your scout to the market to see ceilings" : ""}.</p>`
      : "");
  const t = el("table");
  t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th class="num">Age</th>
    <th class="num">OVR</th><th>Ability</th><th>Ceiling</th>
    <th class="num">Asking</th><th></th></tr></thead>`;
  const tb = el("tbody");
  for (const p of data.free_agents) {
    const fogged = p.fog > 0;
    const tr = el("tr", "", `
      <td><img class="portrait" src="${p.portrait}" alt=""><b>${p.handle}</b></td><td>${stylePill(p)}</td>
      <td class="num">${p.age}</td>
      <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${fogged ? "~" + Math.round(p.overall) : p.overall}</td>
      <td>${starsRange(p.scout?.ca_stars)}</td>
      <td>${starsRange(p.scout?.pa_stars)}</td>
      <td class="num">${money(p.asking_salary)}/wk</td>
      <td><button class="btn btn-sm" ${p.can_sign ? "" : "disabled"}
        title="${p.block_reason || "sign to a 40-week deal"}">Sign</button></td>`);
    tr.querySelector("button").onclick = async () => {
      const r = await api("/api/actions/sign", { player_id: p.id });
      toast(r.message); refresh(); render();
    };
    let detail = null;
    tr.style.cursor = "pointer";
    tr.onclick = (e) => {
      if (e.target.tagName === "BUTTON") return;
      if (detail) { detail.remove(); detail = null; return; }
      detail = el("tr", "", `<td colspan="8">${attrDetail(p)}</td>`);
      tr.after(detail);
    };
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  card.appendChild(t);
  v.appendChild(card);
}

async function scouting(v) {
  const data = await api("/api/scouting");
  const card = el("div", "card");
  card.innerHTML = `<h2>Scouting desk</h2>`;
  const row = el("div", "row");
  const sel = el("select");
  sel.appendChild(el("option", "", "— assign the scout —"));
  const mkt = el("option", "", "Free-agent market");
  mkt.value = "market";
  if (data.target === "market") mkt.selected = true;
  sel.appendChild(mkt);
  for (const t of data.teams) {
    const o = el("option", "", t.name);
    o.value = t.id;
    if (t.id === data.target) o.selected = true;
    sel.appendChild(o);
  }
  sel.onchange = async () => {
    if (!sel.value) return;
    const r = await api("/api/actions/scout", { team_id: sel.value });
    toast(r.message);
    render();
  };
  row.appendChild(sel);
  if (data.target) {
    row.appendChild(el("span", "muted",
      `coverage: ${Math.round(data.progress * 100)}%`));
  }
  card.appendChild(row);
  if (!data.target) {
    card.appendChild(el("p", "muted",
      "Nobody is being watched. Reports on rivals reveal ability bands; " +
      "market coverage exposes free agents' ceilings before you pay for them."));
  }
  v.appendChild(card);

  if (data.reports.length) {
    const rc = el("div", "card");
    rc.innerHTML = `<h2>Reports — ${data.target_name}</h2>`;
    const t = el("table");
    t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th class="num">Age</th>
      <th>Ability</th><th>Ceiling</th><th>Character</th><th>Read</th></tr></thead>`;
    const tb = el("tbody");
    for (const r of data.reports) {
      const traits = r.traits
        .map((t) => `<span class="pill" title="${t.blurb}">${t.id}</span>`)
        .join(" ") +
        (r.traits_hidden ? ` <span class="muted">+${r.traits_hidden}?</span>` : "");
      const read = r.strengths.length
        ? `<span class="muted">+${r.strengths.map((s) => s.replaceAll("_", " ")).join(", ")}` +
          (r.weaknesses.length ? ` · −${r.weaknesses.map((s) => s.replaceAll("_", " ")).join(", ")}` : "") +
          `</span>`
        : `<span class="muted">needs more time</span>`;
      tb.appendChild(el("tr", "", `
        <td><b>${r.handle}</b></td>
        <td><span class="pill">${r.role}</span> <span class="pill">${r.playstyle}</span></td>
        <td class="num">${r.age}</td>
        <td>${starsRange(r.ca_stars)}</td>
        <td>${starsRange(r.pa_stars)}</td>
        <td>${traits || '<span class="muted">—</span>'}</td>
        <td>${read}</td>`));
    }
    t.appendChild(tb);
    rc.appendChild(t);
    v.appendChild(rc);
  }
}

async function stats(v) {
  const data = await api("/api/stats");

  const champs = App.state.champions ?? [];
  if (champs.length) {
    const hc = el("div", "card");
    hc.innerHTML = `<h2>Champions</h2>` + [...champs].reverse()
      .map((c) => `<div class="newsline"><span class="pill">S${c.season}</span> <b>${c.team_name}</b></div>`)
      .join("");
    v.appendChild(hc);
  }

  if (data.awards.length) {
    const aw = el("div", "card");
    aw.innerHTML = `<h2>Awards</h2>` + data.awards
      .map((a) => `<div class="newsline"><span class="pill">S${a.season}</span>
        <b>${a.award}</b> — ${a.handle} (${a.team_name}), ${a.value}</div>`)
      .join("");
    v.appendChild(aw);
  }

  const lead = el("div", "card");
  lead.innerHTML = `<h2>League leaders — season ${App.state.season}</h2>`;
  if (!data.players.length) {
    lead.innerHTML += `<p class="muted">No maps played yet this season.</p>`;
  } else {
    const t = el("table");
    t.innerHTML = `<thead><tr><th>#</th><th>Player</th><th>Team</th>
      <th class="num">Maps</th><th class="num">Rating</th><th class="num">K</th>
      <th class="num">D</th><th class="num">K/D</th><th class="num">FK</th>
      <th class="num">HS%</th><th class="num">Plants</th><th class="num">Defuses</th></tr></thead>`;
    const tb = el("tbody");
    data.players.slice(0, 25).forEach((r, i) => {
      tb.appendChild(el("tr", r.is_user ? "me" : "", `
        <td>${i + 1}</td><td><b>${r.handle}</b></td><td class="muted">${r.team}</td>
        <td class="num">${r.maps}</td><td class="num"><b>${r.rating.toFixed(2)}</b></td>
        <td class="num">${r.kills}</td><td class="num">${r.deaths}</td>
        <td class="num">${r.kd.toFixed(2)}</td><td class="num">${r.first_kills}</td>
        <td class="num">${r.hs_pct}</td><td class="num">${r.plants}</td>
        <td class="num">${r.defuses}</td>`));
    });
    t.appendChild(tb);
    lead.appendChild(t);
  }
  v.appendChild(lead);

  if (data.teams.length) {
    const tc = el("div", "card");
    tc.innerHTML = `<h2>Team tendencies</h2>`;
    const t = el("table");
    t.innerHTML = `<thead><tr><th>Team</th><th class="num">Maps</th>
      <th class="num">ATK round %</th><th class="num">DEF round %</th>
      <th class="num">Pistol %</th></tr></thead>`;
    const tb = el("tbody");
    for (const r of data.teams) {
      tb.appendChild(el("tr", r.is_user ? "me" : "", `
        <td><b>${r.name}</b></td><td class="num">${r.maps}</td>
        <td class="num">${r.atk_pct}</td><td class="num">${r.def_pct}</td>
        <td class="num">${r.pistol_pct}</td>`));
    }
    t.appendChild(tb);
    tc.appendChild(t);
    v.appendChild(tc);
  }
}

function dealLine(d) {
  const bits = [];
  if (d.signing_bonus) bits.push(`${money(d.signing_bonus)} up front`);
  if (d.weekly) bits.push(`${money(d.weekly)}/wk`);
  if (d.per_win) bits.push(`${money(d.per_win)} per win`);
  return `${bits.join(" · ")} — ${d.weeks_left} weeks`;
}

const SLOT_LABELS = {
  title: "Title", jersey: "Jersey", peripheral: "Peripheral",
  stream: "Stream", apparel: "Apparel",
};
const FACILITY_LABELS = {
  training_center: "Training center",
  analytics_suite: "Analytics suite",
  marketing_office: "Marketing office",
};

async function finances(v) {
  const data = await api("/api/finances");

  const card = el("div", "card");
  card.innerHTML = `<h2>Finances</h2>
    <table><tbody>
      <tr><td>Balance</td><td class="num">${money(data.balance)}</td></tr>
      <tr><td>Weekly payroll</td><td class="num">${money(data.weekly_payroll)}</td></tr>
      <tr><td>Last week income</td><td class="num">${money(data.last_week_income)}</td></tr>
      <tr><td>Last week expenses</td><td class="num">${money(data.last_week_expenses)}</td></tr>
    </tbody></table>
    <p class="muted" style="margin-top:8px">Income = base sponsorship + slot deals + merch + tickets + prize money. Expenses = payroll + staff + facility upkeep + severance.</p>`;
  v.appendChild(card);

  // -- sponsor slots -------------------------------------------------------
  const slotsCard = el("div", "card");
  slotsCard.innerHTML = `<h2>Sponsorship slots
    <span class="muted" style="font-weight:400">— marketability ${data.marketability ?? "?"}</span></h2>`;
  const objChips = (objs) => (objs ?? [])
    .map((o) => {
      const mark = o.met === true ? "✓ " : o.met === false ? "✗ " : "";
      const cls = o.met === true ? "good" : o.met === false ? "bad" : "";
      return `<span class="pill obj ${cls}" title="${money(o.bonus)}">${mark}${o.label} → ${money(o.bonus)}</span>`;
    })
    .join(" ");
  for (const slot of ["title", "jersey", "peripheral", "stream", "apparel"]) {
    const s = data.slots[slot];
    if (!s) continue;
    const row = el("div", "slot-row");
    if (s.deal) {
      row.innerHTML = `<span class="pill">${SLOT_LABELS[slot] ?? slot}</span>
        <b>${s.deal.name}</b> <span class="pill">${s.deal.kind}</span><br>
        <span class="muted">${dealLine(s.deal)}</span><br>${objChips(s.objective_labels_deal)}`;
    } else if (!s.unlocked) {
      row.innerHTML = `<span class="pill">${SLOT_LABELS[slot] ?? slot}</span>
        <span class="muted">locked — ${s.locked_reason ?? "unavailable"}</span>`;
    } else {
      row.innerHTML = `<span class="pill">${SLOT_LABELS[slot] ?? slot}</span>
        <span class="muted">no active deal — ${s.market.length ? "offers below" : "no suitors yet"}</span>`;
    }
    slotsCard.appendChild(row);

    // Legacy single-offer (old saves).
    if (s.offer) {
      const box = el("div", "row");
      box.innerHTML = `<span><b>Offer: ${s.offer.name}</b> <span class="pill">${s.offer.kind}</span><br>
        <span class="muted">${dealLine(s.offer)} — expires if unanswered this week</span></span>`;
      const yes = el("button", "btn btn-primary btn-sm", "Accept");
      yes.onclick = async () => {
        const r = await api("/api/actions/sponsor", { slot, accept: true });
        toast(r.message); refresh(); render();
      };
      const no = el("button", "btn btn-sm", "Decline");
      no.onclick = async () => {
        const r = await api("/api/actions/sponsor", { slot, accept: false });
        toast(r.message); render();
      };
      box.appendChild(yes);
      box.appendChild(no);
      slotsCard.appendChild(box);
    }

    // The market: competing brands, pick a payment structure.
    for (const o of s.market ?? []) {
      const box = el("div", "row offer-row");
      const relTag = o.relation > 55 ? " · warm relations" : o.relation < 45 ? " · cool relations" : "";
      box.innerHTML = `<span style="min-width:340px"><b>${o.brand}</b>
        <span class="muted">${o.weeks}w · until wk ${o.expires_week}${relTag}</span><br>
        ${objChips(o.objective_labels)}</span>`;
      const structures = [
        ["upfront", `${money(o.upfront.signing_bonus)} now + ${money(o.upfront.weekly)}/wk`],
        ["steady", `${money(o.steady.weekly)}/wk`],
        ["performance", `${money(o.performance.weekly)}/wk + ${money(o.performance.per_win)}/win`],
      ];
      for (const [structure, label] of structures) {
        const b = el("button", "btn btn-sm", `${structure}: ${label}`);
        b.disabled = !!s.deal;
        b.title = s.deal ? "slot occupied" : "objective bonuses scale: upfront ×0.7, steady ×1.0, performance ×1.4";
        b.onclick = async () => {
          const r = await api("/api/actions/sponsor", { slot, accept: true, brand: o.brand, structure });
          toast(r.message); refresh(); render();
        };
        box.appendChild(b);
      }
      const no = el("button", "btn btn-sm", "✕");
      no.title = "decline (the brand remembers)";
      no.onclick = async () => {
        const r = await api("/api/actions/sponsor", { slot, accept: false, brand: o.brand });
        toast(r.message); render();
      };
      box.appendChild(no);
      slotsCard.appendChild(box);
    }
  }
  v.appendChild(slotsCard);

  // -- facilities ------------------------------------------------------------
  const facCard = el("div", "card");
  facCard.innerHTML = `<h2>Facilities</h2>`;
  for (const name of ["training_center", "analytics_suite", "marketing_office"]) {
    const f = data.facilities[name];
    if (!f) continue;
    const row = el("div", "row facility-row");
    row.innerHTML = `<span style="min-width:240px"><b>${FACILITY_LABELS[name]}</b><br>
      <span class="muted">level ${f.level}/${f.max_level} · ${money(f.upkeep)}/wk upkeep</span></span>`;
    if (f.next_cost != null) {
      const affordable = data.balance >= f.next_cost;
      const btn = el("button", "btn btn-sm", `Upgrade — ${money(f.next_cost)}`);
      btn.disabled = !affordable;
      btn.title = affordable ? "" : "not enough banked";
      btn.onclick = async () => {
        const r = await api("/api/actions/facility_upgrade", { facility: name });
        toast(r.message); refresh(); render();
      };
      row.appendChild(btn);
    } else {
      row.appendChild(el("span", "pill", "max level"));
    }
    facCard.appendChild(row);
  }
  v.appendChild(facCard);

  // -- itemized weekly breakdown ----------------------------------------------
  const b = data.breakdown;
  const bkCard = el("div", "card");
  bkCard.innerHTML = `<h2>This week's run rate</h2>
    <table><tbody>
      <tr><td>Base sponsorship</td><td class="num">${money(b.sponsors_base)}</td></tr>
      <tr><td>Title sponsor</td><td class="num">${money(b.sponsors_by_slot.title || 0)}</td></tr>
      <tr><td>Jersey sponsor</td><td class="num">${money(b.sponsors_by_slot.jersey || 0)}</td></tr>
      <tr><td>Peripheral sponsor</td><td class="num">${money(b.sponsors_by_slot.peripheral || 0)}</td></tr>
      <tr><td>Merchandise</td><td class="num">${money(b.merch)}</td></tr>
      <tr><td>Ticket sales</td><td class="num">${money(b.tickets)}</td></tr>
      <tr><td>Prize money</td><td class="num">${money(b.prizes)}</td></tr>
      <tr><td class="mono"><b>Income total</b></td><td class="num mono"><b>${money(b.income_total)}</b></td></tr>
      <tr><td>Salaries</td><td class="num">-${money(b.salaries)}</td></tr>
      <tr><td>Staff</td><td class="num">-${money(b.staff)}</td></tr>
      <tr><td>Facility upkeep</td><td class="num">-${money(b.facility_upkeep)}</td></tr>
      <tr><td class="mono"><b>Expense total</b></td><td class="num mono"><b>-${money(b.expense_total)}</b></td></tr>
      <tr><td><b>Net</b></td><td class="num"><b>${b.net >= 0 ? "+" : ""}${money(b.net)}</b></td></tr>
    </tbody></table>
    <p class="muted" style="margin-top:8px">A live run-rate snapshot from the current roster, staff, sponsors and facilities — not a ledger of a specific past week.</p>`;
  v.appendChild(bkCard);

  // -- 8-week cash projection -----------------------------------------------
  const projCard = el("div", "card");
  const rows = data.projection.map((p) => `
    <tr><td>W${p.week}</td>
      <td class="num">${p.net >= 0 ? "+" : ""}${money(p.net)}</td>
      <td class="num">${money(p.balance)}</td></tr>`).join("");
  projCard.innerHTML = `<h2>8-week cash projection</h2>
    <table><thead><tr><th>Week</th><th class="num">Net</th><th class="num">Balance</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="muted" style="margin-top:8px">Assumes current sponsors, facilities and roster hold steady; sponsor slot deals drop off as they expire. Prize money and roster moves aren't modeled.</p>`;
  v.appendChild(projCard);
}

/* -- talk 1:1 ---------------------------------------------------------------------- */

async function openTalk(p) {
  const data = await api(`/api/talk/${p.id}`);
  if (!data.available) {
    toast(data.reason);
    return;
  }
  $("#talk-title").textContent = `1:1 — ${p.handle}`;
  $("#talk-text").textContent = data.topic.text;
  const box = $("#talk-options");
  box.innerHTML = "";
  for (const o of data.options) {
    const b = el("button", "btn", o.label);
    b.onclick = async () => {
      const r = await api("/api/actions/talk", { player_id: p.id, option_id: o.id });
      closeTalk();
      const fx = Object.entries(r.effects)
        .filter(([, v]) => v !== 0)
        .map(([k, v]) => `${k} ${v > 0 ? "+" : ""}${v}`)
        .join(", ");
      toast(`${r.message}${fx ? " (" + fx + ")" : ""}`);
      render();
    };
    box.appendChild(b);
  }
  $("#talk").classList.remove("hidden");
}

function closeTalk() {
  $("#talk").classList.add("hidden");
}

/* -- advance week ------------------------------------------------------------------ */

$("#advance-btn").onclick = async () => {
  $("#advance-btn").disabled = true;
  try {
    const rep = await api("/api/actions/advance", {});
    showReport(rep);
    await refresh();
    // Refresh the Inbox badge and toast any newly-arrived unread mail.
    if (typeof inboxAfterAdvance === "function") await inboxAfterAdvance();
  } finally {
    $("#advance-btn").disabled = false;
  }
};

function showReport(rep) {
  $("#report-title").textContent =
    rep.phase === "offseason" ? "Offseason" : `Season ${rep.season} · Week ${rep.week} results`;
  const body = $("#report-body");
  body.innerHTML = "";
  for (const f of rep.fixtures) {
    const mine = [f.team_a, f.team_b].includes(App.state?.user_team?.id);
    const row = el("div", "row", "");
    const score = f.best_of > 1
      ? `${f.map_score[0]}–${f.map_score[1]}`
      : f.results.length ? `${f.results[0].score_a}–${f.results[0].score_b}` : "";
    row.innerHTML = `<span class="pill">${stageLabel(f.stage)}</span>
      <span style="min-width:320px">${mine ? "<b>" : ""}${f.team_a_name} vs ${f.team_b_name}${mine ? "</b>" : ""}</span>
      <b class="mono">${score}</b>`;
    for (let i = 0; i < f.results.length; i++) {
      const r = f.results[i];
      if (r.has_replay) {
        const b = el("button", "btn btn-sm", `▶ ${r.map_id}`);
        b.onclick = () => openReplay(f.id, i);
        row.appendChild(b);
      }
    }
    body.appendChild(row);
  }
  if (rep.notes.length) {
    body.appendChild(el("div", "card", rep.notes.map((n) => `<div class="newsline">${n}</div>`).join("")));
  }
  body.appendChild(el("p", "muted",
    `income ${money(rep.user_income)} · expenses ${money(rep.user_expenses)}`));
  $("#report").classList.remove("hidden");
}

function closeReport() {
  $("#report").classList.add("hidden");
  render();
}

boot();
