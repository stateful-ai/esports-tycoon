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
  const b = await api("/api/bootstrap");
  if (!b.campaign) {
    const grid = $("#ng-teams");
    grid.innerHTML = "";
    for (const t of b.teams) {
      const btn = el(
        "button",
        "team-pick",
        `<b>${t.name}</b> <span class="pill">${t.tag}</span><br>
         <span class="muted">rank #${t.world_rank ?? "?"} · rep ${t.reputation} · ${money(t.balance)}</span>`
      );
      btn.onclick = async () => {
        await api("/api/new", { team_id: t.id, seed: parseInt($("#ng-seed").value) || 2026 });
        $("#newgame").classList.add("hidden");
        refresh();
      };
      grid.appendChild(btn);
    }
    $("#newgame").classList.remove("hidden");
    return;
  }
  refresh();
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
  const v = $("#view");
  v.innerHTML = "";
  ({ dashboard, roster, standings, schedule, market, stats, finances })[App.tab](v);
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
      <p class="muted">maps: ${f.maps.join(", ")}</p>`;
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
      : "";
    const tr = el("tr", "", `
      <td><img class="portrait" src="${p.portrait}" alt=""><b>${p.handle}</b>${p.id === data.team.captain_id ? ' <span class="pill">IGL</span>' : ""}</td>
      <td>${stylePill(p)}</td>
      <td class="num">${p.age}</td>
      <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${ovr}</td>
      <td>${bar(p.form)}</td><td>${bar(p.morale)}</td><td>${bar(p.stamina)}</td>
      <td class="num">${money(p.salary)}/wk</td>
      <td class="num">${p.contract_weeks_left}w</td>
      <td>${actions}</td>`);
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
      <p class="muted">personality: ${p.personality.join(", ") || "—"}</p>
      <p class="muted">asking salary next deal: ${money(p.asking_salary)}/wk</p>
    </div></div>`;
}

async function standings(v) {
  const data = await api("/api/standings");
  const card = el("div", "card");
  card.innerHTML = `<h2>Standings</h2>`;
  const t = el("table");
  t.innerHTML = `<thead><tr><th>#</th><th>Team</th><th class="num">W</th><th class="num">L</th>
    <th class="num">RW</th><th class="num">RL</th><th class="num">+/-</th><th class="num">Rep</th></tr></thead>`;
  const tb = el("tbody");
  data.rows.forEach((r, i) => {
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
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  card.appendChild(t);
  v.appendChild(card);
}

function bracketCard(fixtures) {
  const semis = fixtures.filter((f) => f.stage === "semi");
  const final = fixtures.find((f) => f.stage === "final");
  if (!semis.length) return null;
  const card = el("div", "card");
  card.innerHTML = `<h2>Playoff bracket</h2>`;
  const wrap = el("div", "bracket");
  const col1 = el("div", "bracket-col");
  const col2 = el("div", "bracket-col");
  const node = (f) => {
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
  };
  for (const s of semis) col1.appendChild(node(s));
  col2.appendChild(node(final));
  wrap.appendChild(col1);
  wrap.appendChild(col2);
  card.appendChild(wrap);
  return card;
}

async function schedule(v) {
  const data = await api("/api/schedule");
  const bracket = bracketCard(data.fixtures);
  if (bracket) v.appendChild(bracket);
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
        <span class="pill">${f.stage}</span>
        <span style="min-width:340px">${mine ? "<b>" : ""}${f.team_a_name} vs ${f.team_b_name}${mine ? "</b>" : ""}</span>
        ${score}`;
      for (let i = 0; i < f.results.length; i++) {
        const r = f.results[i];
        const b = el(
          "button", "btn btn-sm",
          `${r.map_id} ${r.score_a}–${r.score_b}${r.has_replay ? " ▶" : ""}`
        );
        b.disabled = !r.has_replay;
        b.title = r.has_replay ? "watch replay" : "replay only kept for the latest week";
        b.onclick = () => openReplay(f.id, i);
        line.appendChild(b);
      }
      card.appendChild(line);
      if (f.veto.length) {
        card.appendChild(el("div", "muted",
          `<small>veto: ${f.veto.join(" · ")}</small>`));
      }
    }
    v.appendChild(card);
  }
}

async function market(v) {
  const data = await api("/api/market");
  const card = el("div", "card");
  card.innerHTML = `<h2>Free agents (${data.free_agents.length})</h2>`;
  const t = el("table");
  t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th class="num">Age</th>
    <th class="num">OVR</th><th class="num">Asking</th><th></th></tr></thead>`;
  const tb = el("tbody");
  for (const p of data.free_agents) {
    const tr = el("tr", "", `
      <td><img class="portrait" src="${p.portrait}" alt=""><b>${p.handle}</b></td><td>${stylePill(p)}</td>
      <td class="num">${p.age}</td><td class="num">${p.overall}</td>
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
      detail = el("tr", "", `<td colspan="6">${attrDetail(p)}</td>`);
      tr.after(detail);
    };
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  card.appendChild(t);
  v.appendChild(card);
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
    <p class="muted" style="margin-top:8px">Income = sponsors (reputation + fans) + prize money. Expenses = payroll + facilities.</p>`;
  v.appendChild(card);
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
    row.innerHTML = `<span class="pill ${f.winner_id ? "" : ""}">${f.stage}</span>
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
