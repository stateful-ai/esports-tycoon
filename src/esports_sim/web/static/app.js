/* Campaign hub. Pure API consumer — all state lives server-side. */

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const money = (n) => (n == null ? "—" : n.toLocaleString() + " cr");
// Prettify a snake_case tag/trait id ("team_player" -> "Team Player") for display.
const humanize = (s) => (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

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

const App = { tab: "dashboard", state: null, mp: null };

/* -- boot ------------------------------------------------------------------ */

async function boot() {
  if (App.tab === "dashboard") App.tab = "office"; // land on the visual HQ
  const lob = await api("/api/lobby");
  if (lob.in_game) {
    App.mp = { code: lob.code, team_id: lob.team_id, mode: lob.mode };
    $("#newgame").classList.add("hidden");
    refresh();
    // Prime the Inbox tab badge on load (inbox.js is loaded after us, but this
    // runs post-await so its globals are defined; guard keeps boot resilient).
    if (typeof refreshInboxBadge === "function") refreshInboxBadge();
    return;
  }
  setupLobby(lob.teams);
  $("#newgame").classList.remove("hidden");
}

/* -- lobby: new (solo/shared) or join -------------------------------------- */

// Render a region-grouped grid of pickable team cards into `grid`. Teams
// flagged `taken` (already claimed by another manager in a shared world)
// render disabled. `onPick(team)` fires for a free pick.
function renderTeamGrid(grid, teams, onPick) {
  grid.innerHTML = "";
  const regions = [...new Set(teams.map((t) => t.region))].sort();
  for (const region of regions) {
    const head = el("div", "muted", region ? region.toUpperCase() : "");
    head.style.gridColumn = "1 / -1";
    head.style.marginTop = "6px";
    grid.appendChild(head);
    for (const t of teams.filter((x) => x.region === region)) {
      const taken = t.taken;
      const btn = el(
        "button",
        "team-pick" + (taken ? " taken" : ""),
        `<b>${t.name}</b> <span class="pill">${t.tag}</span>${taken ? ' <span class="pill">taken</span>' : ""}<br>
         <span class="muted">rep ${t.reputation} · ${money(t.balance)}</span>`
      );
      btn.disabled = !!taken;
      if (!taken) btn.onclick = () => onPick(t);
      grid.appendChild(btn);
    }
  }
}

function setupLobby(previewTeams) {
  const create = $("#lobby-create");
  const join = $("#lobby-join");
  const showCreate = (shared) => {
    create.classList.remove("hidden");
    join.classList.add("hidden");
    $("#lobby-create-hint").textContent = shared
      ? "Pick your team. Others join with the code you'll get next."
      : "Pick your organisation. Seed controls the generated league.";
    renderTeamGrid($("#ng-teams"), previewTeams, (t) => createGame(t.id, shared));
  };
  $("#mode-solo").onclick = () => showCreate(false);
  $("#mode-shared").onclick = () => showCreate(true);
  $("#mode-join").onclick = () => {
    create.classList.add("hidden");
    join.classList.remove("hidden");
    $("#join-teams").innerHTML = "";
  };
  $("#join-load").onclick = async () => {
    const code = ($("#join-code").value || "").trim().toUpperCase();
    if (code.length !== 5) return toast("Enter the 5-character game code.");
    const r = await api("/api/lobby/teams?code=" + encodeURIComponent(code));
    renderTeamGrid($("#join-teams"), r.teams, (t) => joinGame(code, t.id));
  };
  showCreate(false); // default view
}

async function createGame(teamId, shared) {
  const seed = parseInt($("#ng-seed").value) || 2026;
  const r = await api("/api/new", { team_id: teamId, seed, shared });
  App.mp = { code: r.code, team_id: r.team_id, mode: r.mode };
  $("#newgame").classList.add("hidden");
  await refresh();
  if (shared) {
    toast(`Shared game created — code ${r.code}. Share it so others can join.`);
  }
}

async function joinGame(code, teamId) {
  const r = await api("/api/join", { code, team_id: teamId });
  App.mp = { code: r.code, team_id: r.team_id, mode: r.mode };
  $("#newgame").classList.add("hidden");
  await refresh();
  toast(`Joined game ${r.code}.`);
}

async function refresh() {
  App.state = await api("/api/state");
  const s = App.state;
  $("#context").textContent =
    `Season ${s.season} · Week ${s.week} · ${s.phase}  —  ${s.user_team.name}`;
  $("#balance").textContent = money(s.user_team.balance);
  updateMpChip(s.multiplayer);
  render();
}

// Topbar chip for shared games: the join code + how many managers are ready.
// Hidden for solo games (nothing to coordinate). Click copies the code.
function updateMpChip(mp) {
  const chip = $("#mp-chip");
  if (!chip) return;
  if (!mp || mp.mode !== "shared") {
    chip.classList.add("hidden");
    return;
  }
  chip.classList.remove("hidden");
  chip.textContent = `⛨ ${mp.code} · ${mp.ready.length}/${mp.humans.length} ready`;
  chip.onclick = () => {
    if (navigator.clipboard) navigator.clipboard.writeText(mp.code);
    toast(`Join code ${mp.code} copied.`);
  };
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

/* -- dashboard: the "what do I do now" hub --------------------------------
   Aggregates several read endpoints that already exist in the running server
   (state + schedule + standings + rosters) into a dense, scannable HQ. Holds
   no sim state — every value is derived from a fresh API payload. Team and
   player names carry the .tlink/.plink + data-tid/data-pid contract so the
   global (profile.js) delegated listener turns them into profile links. */

const ORD = ["th", "st", "nd", "rd"];
function ordinal(n) {
  if (n == null) return "—";
  const v = n % 100;
  return n + (ORD[(v - 20) % 10] || ORD[v] || ORD[0]);
}
function cap(t) {
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : t;
}

// W/L/D form square — same success/danger language as .pill.win/.loss.
function formSquare(res, title) {
  const r = String(res || "").toUpperCase();
  const cls = r.startsWith("W") ? "win" : r.startsWith("L") ? "loss" : "draw";
  const sq = el("span", `es-form-sq ${cls}`, r.slice(0, 1) || "·");
  if (title) sq.title = title;
  return sq;
}

// Tone from a 0–100 stat (higher = better): green / amber / red bands.
function statTone(x) {
  if (x == null) return null;
  return x >= 65 ? "good" : x >= 35 ? "warn" : "bad";
}

// A dense stat tile: mono numeral + tiny uppercase label (+ optional sub).
// opts: { sub, tone, onClick, title }
function statTile(label, value, opts = {}) {
  const cls =
    "es-tile" +
    (opts.tone ? " tone-" + opts.tone : "") +
    (opts.onClick ? " es-tile-btn" : "");
  const tile = el(
    "div",
    cls,
    `<div class="es-tile-val mono">${value}</div>` +
      `<div class="es-tile-label">${label}</div>` +
      (opts.sub ? `<div class="es-tile-sub">${opts.sub}</div>` : "")
  );
  if (opts.title) tile.title = opts.title;
  if (opts.onClick) {
    tile.tabIndex = 0;
    tile.setAttribute("role", "button");
    tile.onclick = opts.onClick;
    tile.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); opts.onClick(); }
    };
  }
  return tile;
}

// Jump to a top-nav tab by name (same effect as the user clicking it).
function dashGoTab(name) {
  const b = document.querySelector(`#tabs [data-tab="${name}"]`);
  if (b) b.click();
}

async function dashboard(v) {
  const s = App.state;
  const me = s.user_team;
  const myId = me.id;
  const fix = s.next_fixture;
  const oppId = fix ? (fix.team_a === myId ? fix.team_b : fix.team_a) : null;

  // Every endpoint below already exists in the running server.
  const [sched, table, myRoster, oppRoster] = await Promise.all([
    api("/api/schedule").catch(() => null),
    api("/api/standings").catch(() => null),
    api(`/api/roster/${myId}`).catch(() => null),
    oppId ? api(`/api/roster/${oppId}`).catch(() => null) : Promise.resolve(null),
  ]);

  // League position + record + region for any broadcast (tier-1) team.
  const posOf = {}, recOf = {}, regionOf = {};
  if (table) {
    for (const reg of table.regions) {
      reg.rows.forEach((row, i) => {
        posOf[row.id] = i + 1;
        recOf[row.id] = `${row.wins}–${row.losses}`;
        regionOf[row.id] = reg.region;
      });
    }
  }

  // A team's played fixtures, oldest → newest (recent form + streak).
  const playedFor = (tid) =>
    !sched
      ? []
      : sched.fixtures
          .filter((f) => f.played && (f.team_a === tid || f.team_b === tid))
          .sort((a, b) => a.week - b.week || (a.id < b.id ? -1 : 1));

  // One result line from a team's point of view.
  const lineFor = (f, tid) => {
    const isA = f.team_a === tid;
    const oppName = isA ? f.team_b_name : f.team_a_name;
    const res = f.winner_id === tid ? "W" : "L";
    let score = "";
    if (f.best_of > 1) {
      const [a, b] = f.map_score;
      score = isA ? `${a}–${b}` : `${b}–${a}`;
    } else if (f.results.length) {
      const r = f.results[0];
      score = isA ? `${r.score_a}–${r.score_b}` : `${r.score_b}–${r.score_a}`;
    }
    return {
      opp: isA ? f.team_b : f.team_a,
      oppName,
      res,
      score,
      maps: f.results.map((r) => r.map_id),
    };
  };

  const streakOf = (tid) => {
    const games = playedFor(tid);
    if (!games.length) return null;
    const won = games[games.length - 1].winner_id === tid;
    let n = 0;
    for (let i = games.length - 1; i >= 0; i--) {
      if ((games[i].winner_id === tid) === won) n++; else break;
    }
    return { txt: `${won ? "W" : "L"}${n}`, won };
  };

  const oppName = fix ? (fix.team_a === myId ? fix.team_b_name : fix.team_a_name) : "";

  /* -- 1. NEXT MATCH spotlight -------------------------------------------- */
  const spot = el("div", "card es-spotlight");
  spot.appendChild(el("h2", "", "Next match"));
  if (fix) {
    const region = cap(regionOf[myId] || me.region || "");
    const stageTxt =
      fix.stage === "regular"
        ? `${region} League`
        : stageLabel(fix.stage).toUpperCase();

    const teamBlock = (tid, name, logo, side) => {
      const sub = [posOf[tid] ? ordinal(posOf[tid]) : null, recOf[tid]]
        .filter(Boolean)
        .join(" · ");
      return `<div class="es-vs-team ${side}">
        ${logo ? `<img class="logo lg" src="${logo}" alt="" onerror="this.style.display='none'">` : ""}
        <span class="es-vs-name tlink" data-tid="${tid}">${name}</span>
        ${sub ? `<span class="es-vs-sub muted">${sub}</span>` : ""}
      </div>`;
    };
    const oppLogo = oppRoster?.team?.logo || "";
    spot.appendChild(
      el(
        "div",
        "es-vs",
        teamBlock(myId, me.name, me.logo, "left") +
          `<div class="es-vs-mid">
            <div class="es-vs-x">VS</div>
            <div class="es-vs-ctx">S${s.season} · W${fix.week}</div>
            <div class="es-vs-ctx">${stageTxt}</div>
            <span class="pill es-bo">Best of ${fix.best_of}</span>
          </div>` +
          teamBlock(oppId, oppName, oppLogo, "right")
      )
    );

    // Map feature — the veto ladder in playoffs, else the map pool thumbs.
    if (fix.veto && fix.veto.length) {
      const vr = el("div", "es-maps");
      vr.appendChild(el("span", "es-maps-lab muted", "Veto"));
      for (const entry of fix.veto) {
        const mapId = entry.trim().split(" ").pop();
        vr.appendChild(el("span", "veto-chip", `${mapThumb(mapId, "sm")}${entry}`));
      }
      spot.appendChild(vr);
    } else if (fix.maps && fix.maps.length) {
      const mr = el("div", "es-maps");
      mr.appendChild(
        el("span", "es-maps-lab muted", fix.maps.length > 1 ? "Map pool" : "Map")
      );
      for (const mid of fix.maps) {
        mr.appendChild(
          el(
            "figure",
            "es-map",
            `<img src="/assets/maps/${mid}.webp" alt="${mid}" onerror="this.style.display='none'">` +
              `<figcaption>${mid}</figcaption>`
          )
        );
      }
      spot.appendChild(mr);
    }

    // Opponent scouting: last-5 form + danger men.
    if (oppId) {
      const scout = el("div", "es-scout");
      const oppGames = playedFor(oppId).slice(-5);
      if (oppGames.length) {
        const col = el("div", "es-scout-col");
        col.appendChild(
          el("span", "es-scout-lab muted", `${oppName} — last ${oppGames.length}`)
        );
        const strip = el("span", "es-form-strip");
        for (const g of oppGames) {
          const ln = lineFor(g, oppId);
          strip.appendChild(
            formSquare(ln.res, `vs ${ln.oppName}${ln.score ? " · " + ln.score : ""}`)
          );
        }
        col.appendChild(strip);
        scout.appendChild(col);
      }
      if (oppRoster && oppRoster.players.length) {
        const fog = oppRoster.fog > 0;
        const stars = [...oppRoster.players]
          .sort((a, b) => b.overall - a.overall)
          .slice(0, 3);
        const col = el("div", "es-scout-col");
        col.appendChild(el("span", "es-scout-lab muted", "Danger men"));
        const names = el("span", "es-stars");
        for (const p of stars) {
          names.appendChild(
            el(
              "span",
              "es-star",
              `<span class="plink" data-pid="${p.id}">${p.handle}</span>` +
                `<span class="pill">${p.role}</span>` +
                `<span class="mono muted">${fog ? "~" : ""}${Math.round(p.overall)}</span>`
            )
          );
        }
        col.appendChild(names);
        scout.appendChild(col);
      }
      if (scout.childElementCount) spot.appendChild(scout);
    }
  } else {
    spot.appendChild(el("p", "muted", `No fixture scheduled — ${s.phase}.`));
  }
  v.appendChild(spot);

  /* -- 2. TEAM STATUS tiles ----------------------------------------------- */
  const status = el("div", "card es-status");
  status.appendChild(el("h2", "", "Team status"));
  const tiles = el("div", "es-tiles");
  const rec = me.record;

  tiles.appendChild(statTile("Balance", money(me.balance)));
  if (rec) {
    tiles.appendChild(
      statTile("Record", `${rec.wins}–${rec.losses}`, {
        sub: `${rec.diff > 0 ? "+" : ""}${rec.diff} rd`,
      })
    );
  }
  if (posOf[myId]) {
    tiles.appendChild(
      statTile("League", ordinal(posOf[myId]), {
        sub: cap(regionOf[myId] || me.region || ""),
        onClick: () => dashGoTab("standings"),
        title: "Open standings",
      })
    );
  }
  const streak = streakOf(myId);
  if (streak) {
    tiles.appendChild(statTile("Streak", streak.txt, { tone: streak.won ? "good" : "bad" }));
  }
  if (myRoster && myRoster.players.length) {
    const avg = (k) =>
      myRoster.players.reduce((a, p) => a + (p[k] || 0), 0) / myRoster.players.length;
    const mor = avg("morale"), cond = avg("stamina");
    tiles.appendChild(statTile("Morale", Math.round(mor), { tone: statTone(mor) }));
    tiles.appendChild(statTile("Condition", Math.round(cond), { tone: statTone(cond) }));
  }
  if (me.chemistry != null) tiles.appendChild(statTile("Chemistry", Math.round(me.chemistry)));
  if (me.world_rank != null) tiles.appendChild(statTile("World rank", `#${me.world_rank}`));
  if (me.reputation != null) tiles.appendChild(statTile("Reputation", Math.round(me.reputation)));
  if (me.fan_count != null) tiles.appendChild(statTile("Fans", me.fan_count.toLocaleString()));
  if (s.scout && s.scout.target) {
    tiles.appendChild(
      statTile("Scout", `${Math.round((s.scout.progress || 0) * 100)}%`, {
        sub: s.scout.target_name || "",
        onClick: () => dashGoTab("scouting"),
        title: "Open the scouting desk",
      })
    );
  }
  tiles.appendChild(
    statTile("Training", cap(s.training_focus), {
      sub: "office →",
      onClick: () => dashGoTab("office"),
      title: "Set the training focus in the office",
    })
  );
  status.appendChild(tiles);
  v.appendChild(status);

  /* -- 3. Transfer offers (actionable — carried over intact) -------------- */
  if ((s.transfer_offers ?? []).length) {
    const oc = el("div", "card");
    oc.appendChild(el("h2", "", "Transfer offers"));
    for (const o of s.transfer_offers) {
      // Build the "what you get" description: cash and/or incoming players.
      const bits = [];
      if ((o.offer_players ?? []).length) {
        bits.push(o.offer_players.map(pl =>
          `<b class="plink" data-pid="${pl.id}">${pl.handle}</b>`).join(" + "));
      }
      if (o.cash_to_seller) bits.push(`<b class="mono">${money(o.cash_to_seller)}</b>`);
      if (o.cash_to_buyer) bits.push(`<span class="muted">(you send back ${money(o.cash_to_buyer)})</span>`);
      const gets = bits.length ? bits.join(" + ") : `<b class="mono">${money(o.fee)}</b>`;
      const row = el(
        "div",
        "row",
        `<span style="min-width:280px"><b>${o.to_team_name}</b> offer
        ${gets} for <b class="plink" data-pid="${o.player_id}">${o.handle}</b></span>
        <span class="muted">expires week ${o.expires_week}</span>`
      );
      const sell = el("button", "btn btn-sm", "Accept");
      sell.onclick = async () => {
        if (!confirm(`Accept ${o.to_team_name}'s offer for ${o.handle}?`)) return;
        const r = await api("/api/actions/transfer_offer", { player_id: o.player_id, to_team: o.to_team, accept: true });
        toast(r.message); refresh();
      };
      const keep = el("button", "btn btn-sm", "Decline");
      keep.onclick = async () => {
        const r = await api("/api/actions/transfer_offer", { player_id: o.player_id, to_team: o.to_team, accept: false });
        toast(r.message); refresh();
      };
      row.appendChild(sell);
      row.appendChild(keep);
      oc.appendChild(row);
    }
    v.appendChild(oc);
  }

  /* -- 4. Two-column band: RECENT RESULTS | NEWS -------------------------- */
  const band = el("div", "grid2");

  const rc = el("div", "card");
  rc.appendChild(el("h2", "", "Recent results"));
  const myGames = playedFor(myId).slice(-5).reverse();
  if (myGames.length) {
    for (const f of myGames) {
      const ln = lineFor(f, myId);
      const thumbs = ln.maps.map((m) => mapThumb(m, "sm")).join("");
      rc.appendChild(
        el(
          "div",
          "row es-result",
          `<span class="pill ${ln.res === "W" ? "win" : "loss"}">${ln.res}</span>` +
            `<span class="es-result-opp tlink" data-tid="${ln.opp}">${ln.oppName}</span>` +
            `<span class="spacer"></span>` +
            `<b class="mono es-result-score">${ln.score}</b>` +
            `<span class="es-result-maps">${thumbs}</span>`
        )
      );
    }
  } else {
    rc.appendChild(el("p", "muted", "No matches played yet this season."));
  }
  band.appendChild(rc);

  const news = el("div", "card");
  news.appendChild(el("h2", "", "News"));
  if ((s.news ?? []).length) {
    for (const n of s.news) news.appendChild(el("div", "newsline", n));
  } else {
    news.appendChild(el("p", "muted", "No news yet."));
  }
  band.appendChild(news);
  v.appendChild(band);

  /* -- 5. League mini-table (carries the old "Top of the table") ---------- */
  let rows = null;
  if (table) {
    const reg = table.regions.find((r) => r.is_user) || table.regions[0];
    rows = reg ? reg.rows : [];
  } else if ((s.standings_top ?? []).length) {
    rows = s.standings_top.map((r) => ({
      id: r.team_id, name: r.name, wins: r.wins, losses: r.losses, diff: r.diff,
    }));
  }
  if (rows && rows.length) {
    const lc = el("div", "card");
    lc.appendChild(el("h2", "", `${cap(regionOf[myId] || me.region || "")} league`));
    const t = el("table");
    t.innerHTML =
      `<thead><tr><th>#</th><th>Team</th><th class="num">W</th>` +
      `<th class="num">L</th><th class="num">+/-</th></tr></thead>`;
    const tb = el("tbody");
    const myIdx = rows.findIndex((r) => r.id === myId);
    const show = new Set();
    rows.forEach((_, i) => { if (i < 4) show.add(i); });
    if (myIdx >= 0) { if (myIdx > 0) show.add(myIdx - 1); show.add(myIdx); }
    const idxs = [...show].sort((a, b) => a - b);
    let prev = -1;
    for (const i of idxs) {
      if (i - prev > 1) tb.appendChild(el("tr", "es-gap", `<td colspan="5" class="muted">…</td>`));
      const r = rows[i];
      const d = r.diff ?? 0;
      tb.appendChild(
        el(
          "tr",
          r.id === myId ? "me" : "",
          `<td>${i + 1}</td>` +
            `<td><span class="tlink" data-tid="${r.id}">${r.name}</span></td>` +
            `<td class="num">${r.wins}</td><td class="num">${r.losses}</td>` +
            `<td class="num">${d > 0 ? "+" : ""}${d}</td>`
        )
      );
      prev = i;
    }
    t.appendChild(tb);
    lc.appendChild(t);
    v.appendChild(lc);
  }
}

async function roster(v) {
  const teamId = App.rosterTeam ?? App.state.user_team.id;
  const data = await api(`/api/roster/${teamId}`);
  const card = el("div", "card");
  const fogNote = data.fog > 0
    ? ` <span class="muted">— scouted estimates ±${data.fog}</span>`
    : "";
  const cap = data.roster_max ?? 5;
  card.innerHTML = `<h2>Roster — <span class="tlink" data-tid="${data.team.id}">${data.team.name}</span> (${data.players.length}/${cap})${fogNote}</h2>`;
  if (data.is_user_team && data.players.length < (data.roster_min ?? 5)) {
    card.appendChild(el("p", "warn",
      `⚠ You need ${data.roster_min ?? 5} players to advance the week — sign ${(data.roster_min ?? 5) - data.players.length} more.`));
  } else if (data.is_user_team && data.players.length < 6) {
    card.appendChild(el("p", "muted",
      "Tip: a 6-man roster is advised for tournaments (register a bench)."));
  }
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
        ? `<button class="btn btn-sm" data-act="bid" title="buy out this contract">Bid ${money(p.transfer_ask)}</button>
           <button class="btn btn-sm" data-act="offer" title="offer players and/or cash">Offer…</button>`
        : "";
    // Bench/starter marker only matters once a roster runs deeper than five.
    const subMark = (data.is_user_team && data.players.length > 5)
      ? (p.starter ? ' <span class="pill" title="in the starting five">★</span>'
                   : ' <span class="pill muted" title="benched by default">sub</span>')
      : "";
    const tr = el("tr", "", `
      <td><img class="portrait" src="${p.portrait}" alt=""><b class="plink" data-pid="${p.id}">${p.handle}</b>${p.id === data.team.captain_id ? ' <span class="pill">IGL</span>' : ""}${subMark}</td>
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
      tr.querySelector('[data-act="offer"]').onclick = (e) => {
        e.stopPropagation();
        openOffer({ id: p.id, handle: p.handle, ask: p.transfer_ask, team_name: data.team.name });
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

  if (data.is_user_team && data.upcoming) v.appendChild(lineupCard(data));
  if (data.is_user_team) await staffCard(v);
}

// Per-map "dressed five" picker for the upcoming fixture (only shown when the
// roster runs deeper than five, so there's an actual choice to make).
function lineupCard(data) {
  const up = data.upcoming;
  const card = el("div", "card");
  card.innerHTML = `<h2>Lineups — vs ${up.opponent} (Bo${up.best_of})</h2>
    <p class="muted">Dress exactly 5 for each map. A map with no pick uses your default five (★).</p>`;

  const chipRow = (preselected, onSave) => {
    const wrap = el("div", "");
    const chips = el("div", "row");
    const chosen = new Set(preselected);
    const count = el("span", "muted", `${chosen.size}/5`);
    for (const p of data.players) {
      const chip = el("button", "btn btn-sm" + (chosen.has(p.id) ? " btn-primary" : ""), p.handle);
      chip.onclick = () => {
        if (chosen.has(p.id)) { chosen.delete(p.id); chip.classList.remove("btn-primary"); }
        else if (chosen.size >= 5) { toast("five is the max — remove one first"); return; }
        else { chosen.add(p.id); chip.classList.add("btn-primary"); }
        count.textContent = `${chosen.size}/5`;
      };
      chips.appendChild(chip);
    }
    const save = el("button", "btn btn-sm", "Save");
    save.onclick = () => onSave([...chosen]);
    const bar = el("div", "row");
    bar.append(count, save);
    wrap.append(chips, bar);
    return wrap;
  };

  // Default five.
  const dflt = el("div", "lineup-block");
  dflt.appendChild(el("h3", "", "Default five"));
  dflt.appendChild(chipRow(data.lineup_ids ?? [], async (ids) => {
    if (ids.length && ids.length !== 5) { toast("pick exactly 5 (or none for auto)"); return; }
    const r = await api("/api/actions/lineup", { lineup_ids: ids });
    toast(r.message); render();
  }));
  const auto = el("button", "btn btn-sm", "Clear (auto top-5)");
  auto.onclick = async () => {
    const r = await api("/api/actions/lineup", { lineup_ids: [] });
    toast(r.message); render();
  };
  dflt.appendChild(auto);
  card.appendChild(dflt);

  // Per-map overrides.
  for (const m of up.maps) {
    const box = el("div", "lineup-block");
    box.appendChild(el("h3", "", `${m.map_id}${m.has_override ? " · custom" : " · default"}`));
    box.appendChild(chipRow(m.dressed, async (ids) => {
      if (ids.length !== 5) { toast("dress exactly 5 for a map"); return; }
      const r = await api("/api/actions/lineup", { fixture_id: up.fixture_id, map_id: m.map_id, player_ids: ids });
      toast(r.message); render();
    }));
    card.appendChild(box);
  }
  return card;
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
          .map((t) => `<span class="pill" title="${t.blurb || ""}">${humanize(t.id)}</span>`)
          .join(" ") || "—"
      }</p>
      ${p.potential_stars != null
        ? `<p class="muted">ability: ${starsRange([p.ca_stars, p.ca_stars])} now · ${starsRange([p.potential_stars, p.potential_stars])} ceiling</p>`
        : ""}
      <p class="muted">asking salary next deal: ${money(p.asking_salary)}/wk</p>
    </div></div>`;
}

// Each dial is bipolar: pushing off the neutral centre (50) leans the team
// toward one pole. `styles` names the playstyles that thrive at that pole —
// grounded in the match engine (entries/awpers swing on high aggression, a
// lurker peels out on high map control, supports hold util for retakes). The
// attribute dials also carry a `fit` from the server: how well the roster's
// relevant attributes suit an extreme identity there. eco_greed is a pure
// economy lever (`econ`) with no roster fit.
const TACTIC_DIALS = [
  { key: "aggression", label: "Aggression",
    low:  { name: "Hold & anchor", note: "safe spacing, patient angles", styles: ["anchor", "sentinel"] },
    high: { name: "Swing & refrag", note: "peek hard, trade every duel", styles: ["entry", "awper"] } },
  { key: "pace", label: "Pace",
    low:  { name: "Slow default", note: "read it out, pull off bad hits", styles: ["igl", "lurker"] },
    high: { name: "Fast execute", note: "early timings, ram the site", styles: ["entry"] } },
  { key: "util_discipline", label: "Utility discipline",
    low:  { name: "Dump on the hit", note: "spend util entering", styles: ["entry"] },
    high: { name: "Hold for retakes", note: "bank util to swing & retake", styles: ["support", "sentinel"] } },
  { key: "eco_greed", label: "Eco greed", econ: true,
    low:  { name: "Disciplined save", note: "bank credits when broke", styles: [] },
    high: { name: "Force-buy often", note: "gamble on half-buys", styles: [] } },
  { key: "map_control", label: "Map control",
    low:  { name: "Stack & hit five", note: "simple, cohesion-light", styles: ["entry"] },
    high: { name: "Spread & lurk", note: "flank presence, pick timings", styles: ["lurker", "sentinel"] } },
];

const SITE_FOCUS = [
  ["balanced", "Balanced", "read both sites"],
  ["a", "A site", "commit A"],
  ["b", "B site", "commit B"],
  ["c", "C site", "commit C"],
];

// No sim maths in the UI: the server computed the duel impact at each pole
// (impact_lo at value 0, impact_hi at 100) from the same code the match engine
// runs. Impact is piecewise-linear with its knot at the neutral 50, so all the
// client does is interpolate between a pole and that zero.
function dialImpact(fit, value) {
  if (!fit) return 0;
  return value <= 50
    ? fit.impact_lo * (50 - value) / 50
    : fit.impact_hi * (value - 50) / 50;
}

function poleChips(fit, styles) {
  // Roster members whose playstyle suits this pole, tagged with their score.
  const set = new Set(styles);
  const hits = (fit?.players ?? []).filter((p) => set.has(p.playstyle));
  if (!hits.length) return "";
  return hits
    .map((p) => `<span class="tac-who" title="${p.playstyle} · ${p.score}">${p.handle}</span>`)
    .join("");
}

async function tactics(v) {
  const data = await api("/api/tactics");
  const tac = data.tactics;
  const f = data.fit;
  const chem = f.chemistry;
  const fitBy = Object.fromEntries(f.dials.map((d) => [d.key, d]));
  const values = {}; // live working copy; only changed keys get POSTed
  for (const d of TACTIC_DIALS) values[d.key] = tac[d.key];
  let siteVal = tac.site_focus;
  const pending = {};

  const card = el("div", "card", `<h2>Coaching strategy</h2>`);
  const intro = el("p", "muted",
    `The identity your squad plays with. Every dial sits neutral at <b>50</b> —
     push it off centre and the match engine rewards a roster built for that
     style and punishes one that isn't. Team chemistry is <b class="mono">${Math.round(chem)}</b>.`);
  card.appendChild(intro);

  // Live "execution edge" summary — the clamped sum of every dial's duel term.
  const edge = el("div", "tac-edge");
  card.appendChild(edge);

  const dialsWrap = el("div", "tac-dials");
  const refreshEdge = () => {
    let total = 0;
    for (const d of TACTIC_DIALS) total += dialImpact(fitBy[d.key], values[d.key]);
    total = Math.max(-f.mod_cap, Math.min(f.mod_cap, total));
    const tone = Math.abs(total) < 0.2 ? "" : total > 0 ? "good" : "bad";
    const sign = total > 0 ? "+" : "";
    edge.className = `tac-edge ${tone}`;
    edge.innerHTML = `<span class="tac-edge-lab">Execution edge</span>
      <span class="tac-edge-val">${sign}${total.toFixed(1)}</span>
      <span class="tac-edge-sub">duel points from how your roster fits this system
      (neutral = 0, capped ±${f.mod_cap})</span>`;
  };

  for (const d of TACTIC_DIALS) {
    const fit = fitBy[d.key];
    const block = el("div", "tac-dial");

    const head = el("div", "tac-head", `<span class="tac-name">${d.label}</span>`);
    const desc = el("span", "tac-desc");
    const valBadge = el("span", "tac-val mono");
    head.appendChild(desc);
    head.appendChild(valBadge);
    block.appendChild(head);

    // Bipolar poles + slider with a neutral centre notch.
    const poles = el("div", "tac-poles");
    const lo = el("div", "tac-pole lo", `
      <span class="tac-pole-name">${d.low.name}</span>
      <span class="tac-pole-note">${d.low.note}</span>`);
    const hi = el("div", "tac-pole hi", `
      <span class="tac-pole-name">${d.high.name}</span>
      <span class="tac-pole-note">${d.high.note}</span>`);
    poles.appendChild(lo);
    poles.appendChild(hi);
    block.appendChild(poles);

    const track = el("div", "tac-track");
    const slider = el("input");
    slider.type = "range"; slider.min = 0; slider.max = 100; slider.step = 1;
    slider.value = values[d.key];
    track.appendChild(el("span", "tac-notch"));
    track.appendChild(slider);
    block.appendChild(track);

    // Fit line: which players suit each pole + a live per-dial duel term.
    const foot = el("div", "tac-foot");
    if (d.econ) {
      foot.innerHTML = `<span class="tac-fit-lab">Economy call — no duel effect, but a
        greedy force can snowball or bankrupt you.</span>`;
    } else if (fit) {
      const loWho = poleChips(fit, d.low.styles);
      const hiWho = poleChips(fit, d.high.styles);
      foot.innerHTML = `
        <div class="tac-fit">
          <span class="tac-fit-lab">Roster fit
            <span class="muted">(${fit.attrs.join(" · ")})</span></span>
          ${bar(fit.fit)}
          <span class="mono tac-fit-num">${Math.round(fit.fit)}</span>
        </div>
        <div class="tac-who-row">
          <span class="tac-who-side lo">${loWho || '<span class="muted">—</span>'}</span>
          <span class="tac-impact"></span>
          <span class="tac-who-side hi">${hiWho || '<span class="muted">—</span>'}</span>
        </div>
        ${fit.chem_gated
          ? `<span class="tac-chem">↑ side is coordination-heavy — leans on team chemistry (${Math.round(chem)})</span>`
          : ""}`;
    }
    block.appendChild(foot);
    const impactEl = foot.querySelector(".tac-impact");

    const paint = () => {
      const val = values[d.key];
      valBadge.textContent = Math.round(val);
      // Descriptor tracks the neutral band [45,55] the engine treats as a no-op.
      let label = "Neutral", side = "mid";
      if (val < 45) { label = d.low.name; side = "lo"; }
      else if (val > 55) { label = d.high.name; side = "hi"; }
      desc.textContent = label;
      desc.className = `tac-desc ${side}`;
      lo.classList.toggle("on", side === "lo");
      hi.classList.toggle("on", side === "hi");
      if (impactEl && fit) {
        const imp = dialImpact(fit, val);
        const tone = Math.abs(imp) < 0.05 ? "" : imp > 0 ? "good" : "bad";
        impactEl.className = `tac-impact ${tone}`;
        impactEl.textContent = Math.abs(imp) < 0.05
          ? "neutral" : `${imp > 0 ? "+" : ""}${imp.toFixed(1)} duel`;
      }
    };
    slider.oninput = () => {
      values[d.key] = parseFloat(slider.value);
      pending[d.key] = values[d.key];
      paint();
      refreshEdge();
    };
    paint();
    dialsWrap.appendChild(block);
  }
  refreshEdge();
  card.appendChild(dialsWrap);

  // Site focus as a segmented control — cohesive with the dial blocks.
  const siteBlock = el("div", "tac-dial");
  siteBlock.appendChild(el("div", "tac-head",
    `<span class="tac-name">Site focus</span>
     <span class="tac-desc mid">${SITE_FOCUS.find((s) => s[0] === siteVal)[1]}</span>`));
  const seg = el("div", "tac-seg");
  const segDesc = siteBlock.querySelector(".tac-desc");
  for (const [val, label, note] of SITE_FOCUS) {
    const b = el("button", "tac-seg-btn", label);
    b.title = note;
    if (val === siteVal) b.classList.add("on");
    b.onclick = () => {
      siteVal = val;
      pending.site_focus = val;
      seg.querySelectorAll(".tac-seg-btn").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      segDesc.textContent = label;
    };
    seg.appendChild(b);
  }
  siteBlock.appendChild(seg);
  siteBlock.appendChild(el("p", "muted tac-site-note",
    "Bias the attack toward one site. Pure macro — it steers where you hit, not who wins duels."));
  dialsWrap.appendChild(siteBlock);

  // Save bar.
  const barRow = el("div", "tac-savebar");
  const save = el("button", "btn btn-primary", "Set strategy");
  save.onclick = async () => {
    if (!Object.keys(pending).length) { toast("no changes"); return; }
    const r = await api("/api/actions/tactics", pending);
    toast(r.message);
    for (const k of Object.keys(pending)) delete pending[k];
  };
  barRow.appendChild(save);
  barRow.appendChild(el("span", "muted",
    "Scout a rival to 50%+ to read their coaching identity on their roster page."));
  card.appendChild(barRow);
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
        <td>${i + 1}</td><td><img class="logo" src="${r.logo}" alt=""><b class="tlink" data-tid="${r.id}">${r.name}</b> <span class="pill">${r.tag}</span></td>
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
        <span style="min-width:340px">${mine ? "<b>" : ""}<span class="tlink" data-tid="${f.team_a}">${f.team_a_name}</span> vs <span class="tlink" data-tid="${f.team_b}">${f.team_b_name}</span>${mine ? "</b>" : ""}</span>
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
  const cap = data.roster_max ?? 5;
  card.appendChild(el("p", "muted",
    `Squad ${data.roster_count}/${cap}. ${data.phase === "playoffs"
      ? "Rosters are locked during the playoffs." : "Sign to fill a slot, or swap to add + drop in one move."}`));
  const t = el("table");
  t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th class="num">Age</th>
    <th class="num">OVR</th><th>Ability</th><th>Ceiling</th>
    <th class="num">Asking</th><th></th><th>Swap out</th></tr></thead>`;
  const tb = el("tbody");
  const locked = data.phase === "playoffs";
  for (const p of data.free_agents) {
    const fogged = p.fog > 0;
    const tr = el("tr", "", `
      <td><img class="portrait" src="${p.portrait}" alt=""><b class="plink" data-pid="${p.id}">${p.handle}</b></td><td>${stylePill(p)}</td>
      <td class="num">${p.age}</td>
      <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${fogged ? "~" + Math.round(p.overall) : p.overall}</td>
      <td>${starsRange(p.scout?.ca_stars)}</td>
      <td>${starsRange(p.scout?.pa_stars)}</td>
      <td class="num">${money(p.asking_salary)}/wk</td>
      <td><button class="btn btn-sm" data-act="sign" ${p.can_sign ? "" : "disabled"}
        title="${p.block_reason || "sign to a 40-week deal"}">Sign</button></td>
      <td data-swap></td>`);
    tr.querySelector('[data-act="sign"]').onclick = async () => {
      const r = await api("/api/actions/sign", { player_id: p.id });
      toast(r.message); refresh(); render();
    };
    // Swap: pick one of your players to drop, then sign this FA in one move.
    const swapCell = tr.querySelector("[data-swap]");
    if (locked) {
      swapCell.appendChild(el("span", "muted", "locked"));
    } else {
      const sel = el("select", "sel-sm");
      sel.appendChild(el("option", "", "— drop —"));
      for (const mine of data.my_roster) {
        const o = el("option", "", `${mine.handle} (${mine.overall})`);
        o.value = mine.id;
        sel.appendChild(o);
      }
      const go = el("button", "btn btn-sm", "Swap");
      go.onclick = async () => {
        if (!sel.value) { toast("choose a player to drop"); return; }
        const dropName = data.my_roster.find(x => x.id === sel.value)?.handle ?? "player";
        if (!confirm(`Drop ${dropName} and sign ${p.handle}?`)) return;
        const r = await api("/api/actions/swap", { sign_id: p.id, drop_id: sel.value });
        toast(r.message); refresh(); render();
      };
      swapCell.append(sel, go);
    }
    let detail = null;
    tr.style.cursor = "pointer";
    tr.onclick = (e) => {
      if (e.target.tagName === "BUTTON" || e.target.tagName === "SELECT" || e.target.tagName === "OPTION") return;
      if (detail) { detail.remove(); detail = null; return; }
      detail = el("tr", "", `<td colspan="9">${attrDetail(p)}</td>`);
      tr.after(detail);
    };
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  card.appendChild(t);
  v.appendChild(card);
}

// Package-deal builder: offer any of my players + cash (either way) for a rival.
async function openOffer(target) {
  let mine = [];
  try {
    const mkt = await api("/api/market");
    if (mkt.phase === "playoffs") { toast("rosters are locked during the playoffs"); return; }
    mine = mkt.my_roster ?? [];
  } catch { return; }

  const ov = el("div", "overlay");
  const panel = el("div", "panel");
  panel.innerHTML = `<button class="btn btn-sm offer-close" style="float:right">✕</button>
    <h2>Offer for ${target.handle}</h2>
    <p class="muted">${target.team_name} want about <b>${money(target.ask)}</b> of value.</p>`;
  const list = el("div", "");
  const chosen = new Set();
  for (const p of mine) {
    const row = el("label", "row");
    row.style.cursor = "pointer";
    const cb = el("input");
    cb.type = "checkbox";
    cb.onchange = () => { cb.checked ? chosen.add(p.id) : chosen.delete(p.id); recompute(); };
    row.append(cb, el("span", "", `${p.handle} — OVR ${p.overall} · ${money(p.value)}`));
    list.appendChild(row);
  }
  panel.appendChild(el("h3", "", "Players you send"));
  panel.appendChild(list);

  const cashOut = el("input"); cashOut.type = "number"; cashOut.min = "0"; cashOut.value = "0"; cashOut.className = "sel-sm";
  const cashIn = el("input"); cashIn.type = "number"; cashIn.min = "0"; cashIn.value = "0"; cashIn.className = "sel-sm";
  cashOut.oninput = recompute; cashIn.oninput = recompute;
  const cashWrap = el("div", "");
  const oL = el("label", "row"); oL.append(el("span", "", "Cash you send: "), cashOut);
  const iL = el("label", "row"); iL.append(el("span", "", "Cash you want back: "), cashIn);
  cashWrap.append(oL, iL);
  panel.appendChild(cashWrap);

  const meter = el("p", "");
  panel.appendChild(meter);
  function recompute() {
    const players = mine.filter(p => chosen.has(p.id)).reduce((s, p) => s + p.value, 0);
    const co = Math.max(0, parseInt(cashOut.value || "0", 10));
    const ci = Math.max(0, parseInt(cashIn.value || "0", 10));
    const value = players + co - ci;
    const ok = value >= target.ask;
    meter.className = ok ? "good" : "warn";
    meter.textContent = `Package value ${money(value)} vs ask ${money(target.ask)} — ${ok ? "should be accepted" : "short of value"}`;
  }
  recompute();

  const send = el("button", "btn btn-primary", "Send offer");
  send.onclick = async () => {
    const co = Math.max(0, parseInt(cashOut.value || "0", 10));
    const ci = Math.max(0, parseInt(cashIn.value || "0", 10));
    try {
      const r = await api("/api/actions/package", {
        target_pid: target.id,
        out_pids: [...chosen],
        cash_out: co,
        cash_in: ci,
      });
      toast(r.message); close(); refresh(); render();
    } catch { /* api() already toasted the reason */ }
  };
  const actions = el("div", "row");
  actions.append(send);
  panel.appendChild(actions);

  function close() { ov.remove(); }
  ov.onclick = (e) => { if (e.target === ov) close(); };
  panel.querySelector(".offer-close").onclick = close;
  ov.appendChild(panel);
  document.body.appendChild(ov);
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
        .map((t) => `<span class="pill" title="${t.blurb}">${humanize(t.id)}</span>`)
        .join(" ") +
        (r.traits_hidden ? ` <span class="muted">+${r.traits_hidden}?</span>` : "");
      const read = r.strengths.length
        ? `<span class="muted">+${r.strengths.map((s) => s.replaceAll("_", " ")).join(", ")}` +
          (r.weaknesses.length ? ` · −${r.weaknesses.map((s) => s.replaceAll("_", " ")).join(", ")}` : "") +
          `</span>`
        : `<span class="muted">needs more time</span>`;
      tb.appendChild(el("tr", "", `
        <td><b class="plink" data-pid="${r.player_id}">${r.handle}</b></td>
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
        <td>${i + 1}</td><td><b class="plink" data-pid="${r.player_id}">${r.handle}</b></td><td class="muted">${r.team}</td>
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
        <td><b class="tlink" data-tid="${r.team_id}">${r.name}</b></td><td class="num">${r.maps}</td>
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

let mpPolling = false;

$("#advance-btn").onclick = async () => {
  $("#advance-btn").disabled = true;
  const prevWeek = App.state?.week;
  try {
    const rep = await api("/api/actions/advance", {});
    if (rep.advanced === false) {
      // Shared game: you're ready, but the week waits for the others.
      $("#advance-btn").textContent = "Waiting… ⏳";
      toast("Ready — waiting for: " + rep.waiting_on.join(", "));
      await refresh(); // reflect your ready state in the chip
      pollForAdvance(prevWeek);
      return; // stay disabled; pollForAdvance re-enables when the week ticks
    }
    showReport(rep);
    await refresh();
    // Refresh the Inbox badge and toast any newly-arrived unread mail.
    if (typeof inboxAfterAdvance === "function") await inboxAfterAdvance();
  } finally {
    if (!mpPolling) $("#advance-btn").disabled = false;
  }
};

// While waiting for other managers to ready up, poll the shared world until the
// week actually advances, then drop the waiting player into the new week.
function pollForAdvance(prevWeek) {
  if (mpPolling) return;
  mpPolling = true;
  const tick = async () => {
    let s;
    try {
      s = await api("/api/state");
    } catch {
      mpPolling = false;
      $("#advance-btn").textContent = "Advance Week ▸";
      $("#advance-btn").disabled = false;
      return;
    }
    App.state = s;
    updateMpChip(s.multiplayer);
    if (s.week !== prevWeek) {
      mpPolling = false;
      $("#advance-btn").textContent = "Advance Week ▸";
      $("#advance-btn").disabled = false;
      toast(`Week ${s.week} — everyone advanced.`);
      await refresh();
      if (typeof inboxAfterAdvance === "function") await inboxAfterAdvance();
      return;
    }
    setTimeout(tick, 2500);
  };
  setTimeout(tick, 2500);
}

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
