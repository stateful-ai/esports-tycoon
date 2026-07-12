/* Campaign hub. Pure API consumer — all state lives server-side. */

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const money = (n) => (n == null ? "—" : n.toLocaleString() + " cr");
const askBreakdown = (parts) => !parts?.length ? "" :
  `<details class="ask-breakdown"><summary class="chip">Why this price?</summary>` +
  parts.map((p) => `<div class="rowbar"><span>${esc(p.label)}</span>` +
    `<span class="rowbar-val mono">${p.delta >= 0 ? "+" : "−"}${money(Math.abs(p.delta))}</span></div>`).join("") +
  `</details>`;
// Prettify a snake_case tag/trait id ("team_player" -> "Team Player") for display.
const humanize = (s) => (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// HTML-escape untrusted text destined for an innerHTML string.
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* Entity links. profile.js turns any [data-pid]/[data-tid]/[data-sid] into a
   profile-overlay link via one delegated listener — these helpers are the ONE
   way to render a linked name, so coverage and affordance can't drift. */
const plink = (id, text, cls = "") =>
  id ? `<span class="plink ${cls}" data-pid="${esc(id)}">${esc(text)}</span>` : esc(text);
const tlink = (id, text, cls = "") =>
  id ? `<span class="tlink ${cls}" data-tid="${esc(id)}">${esc(text)}</span>` : esc(text);
const slink = (id, text, cls = "") =>
  id ? `<span class="slink ${cls}" data-sid="${esc(id)}">${esc(text)}</span>` : esc(text);

/* Screen header band: title · segmented sub-tabs · right-side extras.
   subtabs: [{id, label}], active id, onPick(id). Returns the band element. */
function screenHead(title, opts = {}) {
  const head = el("div", "screen-head");
  head.appendChild(el("span", "screen-title", esc(title)));
  if (opts.sub) head.appendChild(el("span", "screen-sub", opts.sub));
  if ((opts.subtabs || []).length) {
    const seg = el("div", "seg");
    for (const t of opts.subtabs) {
      const b = el("button", "seg-btn" + (t.id === opts.active ? " on" : ""), esc(t.label));
      b.onclick = () => opts.onPick && opts.onPick(t.id);
      seg.appendChild(b);
    }
    head.appendChild(seg);
  }
  head.appendChild(el("span", "spacer"));
  for (const node of opts.right || []) head.appendChild(node);
  return head;
}

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

const MARKET_FILTER_DEFAULTS = Object.freeze({
  caMax: "", potentialMax: "", language: "", languageMin: "",
  streamRevenueMin: "", role: "", style: "", igl: "",
});

function marketFilters() {
  if (!App.marketFilters) App.marketFilters = { ...MARKET_FILTER_DEFAULTS };
  return App.marketFilters;
}

function filteredMarketPlayers(players, filters) {
  const underStarCap = (band, cap) =>
    cap === "" || (Array.isArray(band) && Number(band[1]) <= Number(cap));
  const aboveMinimum = (value, minimum) =>
    minimum === "" || Number(value || 0) >= Number(minimum);

  return players.filter((p) => {
    const speaksLanguage = !filters.language || (p.languages || []).some((l) =>
      l.lang === filters.language && aboveMinimum(l.level, filters.languageMin));
    return underStarCap(p.scout?.ca_stars, filters.caMax) &&
      underStarCap(p.scout?.pa_stars, filters.potentialMax) &&
      speaksLanguage &&
      aboveMinimum(p.stream_income, filters.streamRevenueMin) &&
      (!filters.role || p.role === filters.role) &&
      (!filters.style || p.playstyle === filters.style) &&
      (!filters.igl || (filters.igl === "yes" ? p.is_igl : !p.is_igl));
  });
}

function marketFilterControls(players, filters) {
  const controls = el("div", "market-filters");
  controls.appendChild(el("b", "market-filters-title", "Filter free agents"));

  const options = (values) => [...new Set(values.filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b)));
  const addSelect = (key, label, values, anyLabel = "Any") => {
    const wrap = el("label", "market-filter");
    wrap.appendChild(el("span", "muted", label));
    const input = el("select", "select");
    input.appendChild(el("option", "", anyLabel));
    for (const value of values) input.appendChild(el("option", "", humanize(value)));
    input.value = filters[key];
    input.onchange = () => { filters[key] = input.value; render(); };
    wrap.appendChild(input);
    controls.appendChild(wrap);
    return input;
  };
  const addNumber = (key, label, placeholder, attrs = {}) => {
    const wrap = el("label", "market-filter");
    wrap.appendChild(el("span", "muted", label));
    const input = el("input", "field mono");
    input.type = "number";
    input.placeholder = placeholder;
    Object.assign(input, attrs);
    input.value = filters[key];
    input.onchange = () => { filters[key] = input.value; render(); };
    wrap.appendChild(input);
    controls.appendChild(wrap);
    return input;
  };

  addSelect("caMax", "CA stars at most", ["0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"], "No cap");
  addSelect("potentialMax", "Potential stars at most", ["0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"], "No cap");
  const language = addSelect("language", "Language", options(players.flatMap((p) => (p.languages || []).map((l) => l.lang))));
  const languageMin = addNumber("languageMin", "Language minimum", "0-100", { min: 0, max: 100, step: 1 });
  languageMin.disabled = !filters.language;
  language.onchange = () => {
    filters.language = language.value;
    if (!language.value) filters.languageMin = "";
    render();
  };
  addNumber("streamRevenueMin", "Min stream revenue", "cr / wk", { min: 0, step: 100 });
  addSelect("role", "Role", options(players.map((p) => p.role)));
  addSelect("style", "Style", options(players.map((p) => p.playstyle)));
  addSelect("igl", "IGL", ["yes", "no"], "Any");

  if (Object.values(filters).some((value) => value !== "")) {
    const reset = el("button", "btn btn-sm market-filter-reset", "Clear filters");
    reset.onclick = () => { App.marketFilters = { ...MARKET_FILTER_DEFAULTS }; render(); };
    controls.appendChild(reset);
  }
  return controls;
}

/* -- sortable tables --------------------------------------------------------
   Click any column header to sort its table (first click: numbers high-to-low,
   text A-to-Z; click again to flip). One delegated listener covers every
   table, including re-renders. Opt out per-table or per-header with
   data-nosort (the H2H matrix opts out — its rows/columns must stay aligned).
   Rows keep their event handlers: sorting just re-appends the same nodes. */
function _sortKey(cell) {
  const t = (cell?.textContent || "").trim();
  if (!t || t === "—") return null; // always sorts to the bottom
  const stars = (t.match(/★/g) || []).length;
  if (stars) return stars + (t.includes("½") ? 0.5 : 0);
  const m = t.replace(/,/g, "").match(/-?\d+(\.\d+)?/);
  if (m) return parseFloat(m[0]);
  return t.toLowerCase();
}

document.addEventListener("click", (e) => {
  const th = e.target.closest("th");
  if (!th || "nosort" in th.dataset) return;
  if (!(th.textContent || "").trim()) return; // blank headers (action columns)
  const table = th.closest("table");
  const tbody = table?.querySelector("tbody");
  if (!table || !tbody || "nosort" in table.dataset) return;
  if (table.classList.contains("es-h2hm")) return; // matrix: keep alignment
  const col = th.cellIndex;
  // Expanded detail rows (roster attrs, market FA attrs, stats per-map) are
  // transient children of their parent row — drop them before sorting so
  // they can't be orphaned into the wrong slot. Row-click closures guard
  // with isConnected and recreate them on demand.
  for (const d of tbody.querySelectorAll("tr[data-detail]")) d.remove();
  const rows = [...tbody.rows];
  if (rows.length < 2) return;
  // First click sorts numeric columns high-to-low (top performers first) and
  // text columns A-to-Z; a second click flips.
  const keys = rows.map((r) => _sortKey(r.cells[col]));
  const numeric = keys.filter((k) => typeof k === "number").length >= keys.filter((k) => k != null).length / 2;
  const dir = th.dataset.dir ? (th.dataset.dir === "asc" ? "desc" : "asc") : numeric ? "desc" : "asc";
  for (const h of th.parentElement.cells) delete h.dataset.dir;
  th.dataset.dir = dir;
  const sign = dir === "asc" ? 1 : -1;
  rows
    .map((r, i) => [r, keys[i], i])
    .sort((a, b) => {
      const [ka, kb] = [a[1], b[1]];
      if (ka == null && kb == null) return a[2] - b[2];
      if (ka == null) return 1; // blanks stay at the bottom either way
      if (kb == null) return -1;
      if (typeof ka === "number" && typeof kb === "number") return sign * (ka - kb) || a[2] - b[2];
      return sign * String(ka).localeCompare(String(kb)) || a[2] - b[2];
    })
    .forEach(([r]) => tbody.appendChild(r));
});

/* -- boot ------------------------------------------------------------------ */

async function boot() {
  const lob = await api("/api/lobby");
  if (lob.in_game) {
    App.mp = { code: lob.code, team_id: lob.team_id, mode: lob.mode };
    $("#newgame").classList.add("hidden");
    $("#worlds-btn").classList.remove("hidden");
    refresh();
    // Prime the Inbox tab badge on load (inbox.js is loaded after us, but this
    // runs post-await so its globals are defined; guard keeps boot resilient).
    if (typeof refreshInboxBadge === "function") refreshInboxBadge();
    return;
  }
  $("#worlds-btn").classList.add("hidden");
  setupLobby(lob);
  $("#newgame").classList.remove("hidden");
}

// Topbar "Worlds": detach from the current world (it stays saved and listed
// under "Your worlds") and drop back to the lobby to resume/create/join.
$("#worlds-btn").onclick = async () => {
  const code = App.mp && App.mp.code ? ` (${App.mp.code})` : "";
  if (!confirm(`Back to the lobby? This world${code} stays saved — resume it anytime from "Your worlds".`)) return;
  await api("/api/leave", {});
  location.reload();
};

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
      // Roster-pack teams come straight from pack data (no economy preview);
      // world-preview teams carry rep/balance.
      const sub =
        t.reputation !== undefined
          ? `rep ${t.reputation} · ${money(t.balance)}`
          : t.region.toUpperCase();
      const btn = el(
        "button",
        "team-pick" + (taken ? " taken" : ""),
        `<b>${t.name}</b> <span class="pill">${t.tag}</span>${taken ? ' <span class="pill">taken</span>' : ""}<br>
         <span class="muted">${sub}</span>`
      );
      btn.disabled = !!taken;
      if (!taken) btn.onclick = () => onPick(t);
      grid.appendChild(btn);
    }
  }
}

// Legacy-career offer cards (lobby + job market). Each offer is an org
// courting the manager with an archetype, a contract, and a board goal.
function renderOfferGrid(grid, offers, onPick) {
  grid.innerHTML = "";
  for (const o of offers) {
    const arch = (o.archetype || "").replace(/_/g, " ");
    const btn = el(
      "button",
      "team-pick",
      `<b>${o.team_name}</b> <span class="pill">${arch}</span><br>
       <span class="muted">${(o.region || "").toUpperCase()} · ${o.seasons}-season deal · board: ${o.goal}</span><br>
       <span class="muted">${o.blurb || ""}</span>`
    );
    btn.onclick = () => onPick(o);
    grid.appendChild(btn);
  }
}

function setupLobby(lob) {
  const create = $("#lobby-create");
  const join = $("#lobby-join");
  const packs = lob.packs || [];
  // Worlds this browser can jump straight back into (incl. solo saves).
  const worlds = lob.worlds || [];
  const resume = $("#lobby-resume");
  if (worlds.length) {
    resume.classList.remove("hidden");
    const list = $("#resume-list");
    list.innerHTML = "";
    for (const w of worlds) {
      const row = el("span", "resume-world");
      const b = el(
        "button",
        "btn",
        `<b>${w.team_name}</b> <span class="pill">${w.code} · ${w.mode}</span>`
      );
      b.onclick = () => resumeGame(w.code);
      const del = el("button", "btn resume-world-delete", "Delete");
      del.title = `Permanently delete ${w.team_name}`;
      del.onclick = () => deleteWorld(w);
      row.append(b, del);
      list.appendChild(row);
    }
  } else {
    resume.classList.add("hidden");
  }
  // Randomize the default seed each lobby visit so a new game (and its
  // legacy offer slate) isn't the same every time; still overridable by
  // hand for a reproducible/shared world.
  $("#ng-seed").value = 1 + Math.floor(Math.random() * 999999);
  // null = generated fictional world; otherwise a roster-pack id.
  let world = null;
  let shared_ = false;
  // "sandbox" = classic (pick any org, manage forever);
  // "legacy" = career mode (offers, contracts, boards that fire you).
  let gameMode = "sandbox";
  const worldTeams = () =>
    world === null ? lob.teams : packs.find((p) => p.id === world).teams;
  const renderModes = () => {
    const box = $("#ng-modes");
    box.innerHTML = "";
    const mk = (label, id) => {
      const b = el(
        "button",
        "btn" + (gameMode === id ? " btn-primary" : ""),
        label
      );
      b.onclick = () => {
        gameMode = id;
        renderModes();
        renderPick();
      };
      box.appendChild(b);
    };
    mk("Sandbox", "sandbox");
    mk("Legacy career", "legacy");
    $("#ng-mode-desc").textContent =
      gameMode === "legacy"
        ? "Start from real job offers. Your board sets a goal and can " +
          "fire you; your career and reputation outlive any one club."
        : "Pick any organisation and manage it forever. No contracts, " +
          "no sack race - the classic game.";
  };
  const renderWorlds = () => {
    const box = $("#ng-worlds");
    box.innerHTML = "";
    if (!packs.length) return;
    const mk = (label, id) => {
      const b = el(
        "button",
        "btn" + ((world === id) ? " btn-primary" : ""),
        label
      );
      b.onclick = () => {
        world = id;
        renderWorlds();
        renderPick();
      };
      box.appendChild(b);
    };
    mk("Fictional world", null);
    for (const p of packs) mk(p.name, p.id);
  };
  const renderPick = () => {
    const p = packs.find((x) => x.id === world);
    const desc = $("#ng-world-desc");
    if (p) {
      desc.textContent =
        `${p.regions.length} regions x ${p.teams_per_region} teams — ` +
        (p.description || "");
      desc.classList.remove("hidden");
    } else {
      desc.classList.add("hidden");
    }
    if (gameMode === "legacy") {
      // Career offers come from the server (same seed/pack derivation
      // the create call validates against). Repaint on seed edits.
      const grid = $("#ng-teams");
      grid.innerHTML = '<span class="muted">Fetching offers…</span>';
      const seed = parseInt($("#ng-seed").value) || 2026;
      api(
        `/api/lobby/offers?seed=${seed}` +
          (world ? `&pack=${encodeURIComponent(world)}` : "")
      )
        .then((r) =>
          renderOfferGrid(grid, r.offers, (o) =>
            createGame(o.team_id, shared_, world, "legacy")
          )
        )
        .catch(() => (grid.innerHTML = '<span class="muted">Offer fetch failed.</span>'));
      return;
    }
    if (world === null) {
      // Fictional-world teams are GENERATED from the seed, so re-fetch at
      // the CURRENT seed — otherwise a solo start at a random seed builds a
      // different league than the grid shows (and the pick 422s). Pack
      // worlds are static data, so they keep using the packs payload.
      const grid = $("#ng-teams");
      grid.innerHTML = '<span class="muted">Generating league…</span>';
      const seed = parseInt($("#ng-seed").value) || 2026;
      api(`/api/lobby/preview?seed=${seed}`)
        .then((r) =>
          renderTeamGrid(grid, r.teams, (t) => createGame(t.id, shared_, world))
        )
        .catch(
          () => (grid.innerHTML = '<span class="muted">Team fetch failed.</span>')
        );
      return;
    }
    renderTeamGrid($("#ng-teams"), worldTeams(), (t) =>
      createGame(t.id, shared_, world)
    );
  };
  $("#ng-seed").addEventListener("change", () => renderPick());
  const showCreate = (shared) => {
    shared_ = shared;
    create.classList.remove("hidden");
    join.classList.add("hidden");
    $("#lobby-create-hint").textContent = shared
      ? "Pick your team. Others join with the code you'll get next."
      : "Pick your organisation. Seed controls the generated league.";
    renderModes();
    renderWorlds();
    renderPick();
  };
  // Only the active lobby mode carries the primary highlight.
  const modeBtns = [$("#mode-solo"), $("#mode-shared"), $("#mode-join")];
  const setActiveMode = (active) =>
    modeBtns.forEach((b) => b.classList.toggle("btn-primary", b === active));
  $("#mode-solo").onclick = () => { setActiveMode($("#mode-solo")); showCreate(false); };
  $("#mode-shared").onclick = () => { setActiveMode($("#mode-shared")); showCreate(true); };
  $("#mode-join").onclick = () => {
    setActiveMode($("#mode-join"));
    create.classList.add("hidden");
    join.classList.remove("hidden");
    $("#join-teams").innerHTML = "";
  };
  $("#join-load").onclick = async () => {
    const code = ($("#join-code").value || "").trim().toUpperCase();
    if (code.length !== 5) return toast("Enter the 5-character game code.");
    const r = await api("/api/lobby/teams?code=" + encodeURIComponent(code));
    if (r.game_mode === "legacy") {
      // A legacy world: joiners pick from THEIR offer slate, not the
      // full team list.
      const o = await api("/api/lobby/offers?code=" + encodeURIComponent(code));
      renderOfferGrid($("#join-teams"), o.offers, (of) =>
        joinGame(code, of.team_id)
      );
      return;
    }
    renderTeamGrid($("#join-teams"), r.teams, (t) => joinGame(code, t.id));
  };
  showCreate(false); // default view
}

async function createGame(teamId, shared, pack = null, gameMode = "sandbox") {
  const seed = parseInt($("#ng-seed").value) || 2026;
  const r = await api("/api/new", {
    team_id: teamId, seed, shared, pack, game_mode: gameMode,
  });
  App.mp = { code: r.code, team_id: r.team_id, mode: r.mode };
  $("#newgame").classList.add("hidden");
  $("#worlds-btn").classList.remove("hidden");
  await refresh();
  if (shared) {
    toast(`Shared game created — code ${r.code}. Share it so others can join.`);
  }
}

async function joinGame(code, teamId) {
  const r = await api("/api/join", { code, team_id: teamId });
  App.mp = { code: r.code, team_id: r.team_id, mode: r.mode };
  $("#newgame").classList.add("hidden");
  $("#worlds-btn").classList.remove("hidden");
  await refresh();
  toast(`Joined game ${r.code}.`);
}

async function resumeGame(code) {
  const r = await api("/api/resume", { code });
  App.mp = { code: r.code, team_id: r.team_id, mode: r.mode };
  $("#newgame").classList.add("hidden");
  $("#worlds-btn").classList.remove("hidden");
  await refresh();
  toast(`Resumed world ${r.code}.`);
}

async function deleteWorld(world) {
  const label = `${world.team_name} (${world.code})`;
  if (!confirm(`Permanently delete ${label}? This cannot be undone.`)) return;
  await api("/api/delete_world", { code: world.code });
  toast(`Deleted ${label}.`);
  setupLobby(await api("/api/lobby"));
}

async function refresh() {
  App.state = await api("/api/state");
  const s = App.state;
  $("#context").textContent =
    `Season ${s.season} · Week ${s.week} · ${s.phase}  —  ${s.user_team.name}`;
  $("#balance").textContent = money(s.user_team.balance);
  updateMpChip(s.multiplayer);
  updateSaveControls(s.save);
  render();
}

// Topbar save controls: the explicit Save button (dot = unsaved changes)
// and the autosave policy select. Server-owned state; this only paints.
function updateSaveControls(sv) {
  const btn = $("#save-btn"), sel = $("#autosave-sel");
  if (!btn || !sel) return;
  if (!sv) { btn.classList.add("hidden"); sel.classList.add("hidden"); return; }
  btn.classList.remove("hidden");
  sel.classList.remove("hidden");
  btn.textContent = sv.dirty ? "Save •" : "Save";
  btn.classList.toggle("save-dirty", !!sv.dirty);
  sel.value = sv.autosave_enabled ? String(sv.autosave_every_weeks) : "0";
  btn.onclick = async () => {
    const r = await api("/api/actions/save", {});
    toast(r.message);
    btn.textContent = "Save";
    btn.classList.remove("save-dirty");
  };
  sel.onchange = async () => {
    const v = parseInt(sel.value, 10);
    const r = await api("/api/actions/save_settings", {
      autosave_enabled: v > 0,
      autosave_every_weeks: Math.max(1, v),
    });
    toast(r.message);
  };
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
  chip.textContent = `CODE ${mp.code} ⧉ · ${mp.ready.length}/${mp.humans.length} ready`;
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

// Old tab ids -> [new tab, Season sub-tab]. The Standings and Schedule tabs
// merged into the Season workspace; dashGoTab() and render() both consult
// this map so pre-merge deep links (inbox "Go to", stale App.tab values,
// old onclick handlers) land on the right Season sub-tab.
const TAB_ALIASES = {
  standings: ["season", "league"],
  schedule: ["season", "fixtures"],
};

function render() {
  if (!App.state) return;
  // Merged-tab alias: a stale App.tab from before the Standings+Schedule
  // merge lands on Season with the right sub-tab preselected (and the nav
  // highlight follows, since no button carries the old id anymore).
  const alias = TAB_ALIASES[App.tab];
  if (alias) {
    App.seasonTab = alias[1];
    App.tab = alias[0];
    const b = document.querySelector(`#tabs [data-tab="${alias[0]}"]`);
    if (b && !b.classList.contains("active")) {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
    }
  }
  // Each render gets a fresh container; a slower, superseded async render
  // finishes into a detached node instead of double-appending.
  const container = el("div");
  $("#view").replaceChildren(container);
  // Office screen is parked for now (office.js stays on disk, unloaded).
  ({ inbox, dashboard, roster, tactics, season, market, scouting, stats, social, finances })[App.tab](container);
}

/* -- helpers ------------------------------------------------------------------ */

function bar(value, opts = {}) {
  const cls = opts.invert
    ? value < 35 ? "good" : value < 65 ? "warn" : "bad"
    : value < 35 ? "bad" : value < 65 ? "warn" : "good";
  return `<div class="bar ${cls}" title="${Math.round(value)}"><i style="width:${Math.max(2, Math.min(100, value))}%"></i></div>`;
}

function stylePill(p) {
  return `<span class="pill-pair"><span class="pill">${p.role}</span> <span class="pill">${p.playstyle}</span></span>`;
}

// Spoken-language chips for a player row — comms fit is visible right at the
// signing decision. The proficiency rides each chip's title. Server sends a
// list of {lang, level}; a missing/empty list degrades to "".
function langChips(langs) {
  return (langs || [])
    .map((l) => `<span class="chip" title="${esc(l.lang)} — proficiency ${esc(l.level)}">${esc(l.lang)}</span>`)
    .join(" ");
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
// Pre-merge names route through TAB_ALIASES — the Season sub-tab must be
// set BEFORE the click, because the click triggers the render.
function dashGoTab(name) {
  const alias = TAB_ALIASES[name];
  if (alias) { App.seasonTab = alias[1]; name = alias[0]; }
  const b = document.querySelector(`#tabs [data-tab="${name}"]`);
  if (b) b.click();
}

// Legacy career: the job-market takeover panel a dismissed manager sees
// instead of the normal hub. Accepting rebinds the session server-side,
// so a full reload is the honest refresh.
function renderJobMarket(v, careerState) {
  v.innerHTML = "";
  const panel = el("div", "panel");
  panel.appendChild(el("h2", "", "The board has made a change"));
  panel.appendChild(
    el(
      "p",
      "muted",
      "You've been relieved of your duties - but the phone is ringing. " +
        "Pick your next project; the world waits until you do."
    )
  );
  const grid = el("div", "team-grid");
  renderOfferGrid(grid, careerState.offers, async (o) => {
    try {
      await api("/api/actions/accept_job", { team_id: o.team_id });
      toast(`Appointed at ${o.team_name}.`);
      location.reload();
    } catch (e) {
      toast(String(e.message || e));
    }
  });
  panel.appendChild(grid);
  v.appendChild(panel);
}

/* -- dashboard: the weekly command center ----------------------------------
   One viewport, three zones: a status strip (the org's vitals), a main column
   (next match + match review — the two things a manager reads every week),
   and a rail (decisions pending, objectives, form, league context, news,
   career). Every entity name is a profile link; every module that outgrows
   its panel scrolls inside it. */
async function dashboard(v) {
  const s = App.state;
  // A dismissed legacy manager sees the job market, nothing else.
  if (s.career && s.career.seat && s.career.seat.unemployed) {
    renderJobMarket(v, s.career);
    return;
  }
  const me = s.user_team;
  const myId = me.id;
  const fix = s.next_fixture;
  const oppId = fix ? (fix.team_a === myId ? fix.team_b : fix.team_a) : null;

  // Every endpoint below already exists in the running server.
  const [sched, table, myRoster, oppRoster, career, gameplan] = await Promise.all([
    api("/api/schedule").catch(() => null),
    api("/api/standings").catch(() => null),
    api(`/api/roster/${myId}`).catch(() => null),
    oppId ? api(`/api/roster/${oppId}`).catch(() => null) : Promise.resolve(null),
    api("/api/career").catch(() => null),
    fix ? api("/api/gameplan").catch(() => null) : Promise.resolve(null),
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
  const badgeStrip = (bs) => (bs || []).map((bd) =>
    ` <span class="roster-badge ${bd.polarity < 0 ? "badge-neg" : "badge-pos"}" title="${esc(bd.name)}: ${esc(bd.blurb)}">${bd.emoji}</span>`).join("");

  v.appendChild(screenHead("Dashboard", {
    sub: `S${s.season} · W${s.week} · ${cap(String(s.phase || "").replace(/_/g, " "))}`,
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);

  /* -- 1. STATUS STRIP: the org's vitals in one saccade --------------------- */
  const strip = el("div", "card ws-12 es-status");
  const tiles = el("div", "es-tiles");
  const rec = me.record;
  if (rec) {
    tiles.appendChild(statTile("Record", `${rec.wins}–${rec.losses}`, {
      sub: `${rec.diff > 0 ? "+" : ""}${rec.diff} rd`,
    }));
  }
  if (posOf[myId]) {
    tiles.appendChild(statTile("League", ordinal(posOf[myId]), {
      sub: cap(regionOf[myId] || me.region || ""),
      onClick: () => dashGoTab("standings"),
      title: "Open standings",
    }));
  }
  const streak = streakOf(myId);
  if (streak) tiles.appendChild(statTile("Streak", streak.txt, { tone: streak.won ? "good" : "bad" }));
  // Legacy job security: the sack-race stake stays readable, not hover-only.
  if (s.board) {
    const b = s.board;
    const tone = b.band === "secure" || b.band === "stable" ? "good"
      : b.band === "under pressure" ? "warn" : "bad";
    const term = b.seasons_left
      ? `${b.seasons_left} season${b.seasons_left > 1 ? "s" : ""} left`
      : "final season";
    tiles.appendChild(statTile("Board", cap(b.band), {
      tone,
      sub: `${b.goal} · ${(b.goal_state || "").replace(/_/g, " ")} · ${term}`,
      title: `Board goal: ${b.goal}`,
    }));
  }
  tiles.appendChild(statTile("Balance", money(me.balance), {
    onClick: () => dashGoTab("finances"),
    title: "Open finances",
  }));
  if (myRoster && myRoster.players.length) {
    const avg = (k) =>
      myRoster.players.reduce((a, p) => a + (p[k] || 0), 0) / myRoster.players.length;
    const mor = avg("morale"), cond = avg("stamina");
    tiles.appendChild(statTile("Morale", Math.round(mor), { tone: statTone(mor) }));
    tiles.appendChild(statTile("Condition", Math.round(cond), { tone: statTone(cond) }));
  }
  if (me.chemistry != null) tiles.appendChild(statTile("Chemistry", Math.round(me.chemistry)));
  if (s.scout && s.scout.target) {
    tiles.appendChild(statTile("Scout", `${Math.round((s.scout.progress || 0) * 100)}%`, {
      sub: s.scout.target_name || "",
      onClick: () => dashGoTab("scouting"),
      title: "Open the scouting desk",
    }));
  }
  tiles.appendChild(statTile("Training", cap(s.training_focus), { sub: "weekly focus" }));
  strip.appendChild(tiles);
  // Weekly training focus setter — an every-week call, so it lives on the strip.
  const trainRow = el("div", "row", `<span class="microlabel">Training focus</span>`);
  for (const o of s.focus_options ?? []) {
    const b = el("button", "btn btn-sm" + (o === s.training_focus ? " active" : ""), cap(o));
    b.onclick = async () => {
      await api("/api/actions/training", { focus: o });
      toast(`Training focus: ${o}`);
      refresh();
    };
    trainRow.appendChild(b);
  }
  trainRow.style.marginTop = "8px";
  strip.appendChild(trainRow);
  ws.appendChild(strip);

  /* -- 2. ACTION BAND: offers + suggested five (only when actionable) ------- */
  const sug = s.suggested_lineup;
  const flavor = s.flavor_event;
  if (flavor || (s.transfer_offers ?? []).length || (sug && sug.changed)) {
    const ac = el("div", "card ws-12 alert");
    ac.appendChild(el("h2", "", "Action required"));
    if (flavor) {
      const event = el("div", "flavor-event");
      event.appendChild(el("div", "microlabel", "Team moment"));
      event.appendChild(el("h3", "", flavor.title || "A decision is waiting"));
      event.appendChild(el("p", "", flavor.prompt || "Choose how to respond."));
      const choices = el("div", "row flavor-choices");
      for (const choice of flavor.choices ?? []) {
        const button = el("button", "btn btn-sm", choice.label || "Respond");
        button.onclick = async () => {
          const all = [...choices.querySelectorAll("button")];
          all.forEach((b) => (b.disabled = true));
          try {
            const r = await api("/api/actions/flavor_event", {
              event_id: flavor.id,
              choice_id: choice.id,
            });
            toast(r.message || "Your response is out in the world.");
            refresh();
          } catch (_e) {
            all.forEach((b) => (b.disabled = false));
          }
        };
        choices.appendChild(button);
      }
      event.appendChild(choices);
      ac.appendChild(event);
    }
    for (const o of s.transfer_offers ?? []) {
      const bits = [];
      if ((o.offer_players ?? []).length) {
        bits.push(o.offer_players.map((pl) => `<b>${plink(pl.id, pl.handle)}</b>`).join(" + "));
      }
      if (o.cash_to_seller) bits.push(`<b class="mono">${money(o.cash_to_seller)}</b>`);
      if (o.cash_to_buyer) bits.push(`<span class="muted">(you send back ${money(o.cash_to_buyer)})</span>`);
      const gets = bits.length ? bits.join(" + ") : `<b class="mono">${money(o.fee)}</b>`;
      const row = el("div", "row offer-row",
        `<span><b>${tlink(o.to_team, o.to_team_name)}</b> offer ${gets} for <b>${plink(o.player_id, o.handle)}</b></span>
         <span class="muted">expires week ${o.expires_week}</span><span class="spacer"></span>`);
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
      ac.appendChild(row);
    }
    // Suggested five: only surfaced when it diverges from the dressed five.
    if (sug && sug.changed) {
      const row = el("div", "row offer-row", `<span class="microlabel">Suggested five</span>`);
      for (const p of sug.players) {
        row.appendChild(el("span", "pill",
          `${plink(p.id, p.handle)} <b class="mono">${p.quality}</b>` +
          (p.dressed ? "" : ' <span class="trend-up">▲ in</span>')));
      }
      const go = el("button", "btn btn-sm", "Set lineup ▸");
      go.onclick = () => dashGoTab("roster");
      row.appendChild(el("span", "spacer"));
      row.appendChild(go);
      ac.appendChild(row);
    }
    ws.appendChild(ac);
  }

  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  /* -- 3. NEXT MATCH spotlight (main) --------------------------------------- */
  const spot = el("div", "card es-spotlight");
  spot.appendChild(el("h2", "", "Next match"));
  if (fix) {
    const region = cap(regionOf[myId] || me.region || "");
    const stageTxt =
      fix.stage === "regular" ? `${region} League` : stageLabel(fix.stage).toUpperCase();

    const teamBlock = (tid, name, logo, side) => {
      const sub = [posOf[tid] ? ordinal(posOf[tid]) : null, recOf[tid]]
        .filter(Boolean)
        .join(" · ");
      return `<div class="es-vs-team ${side}">
        ${logo ? `<img class="logo lg" src="${logo}" alt="" onerror="this.style.display='none'">` : ""}
        ${tlink(tid, name, "es-vs-name")}
        ${sub ? `<span class="es-vs-sub muted">${sub}</span>` : ""}
      </div>`;
    };
    const oppLogo = oppRoster?.team?.logo || "";
    spot.appendChild(el("div", "es-vs",
      teamBlock(myId, me.name, me.logo, "left") +
        `<div class="es-vs-mid">
          <div class="es-vs-x">VS</div>
          <div class="es-vs-ctx">S${s.season} · W${fix.week}</div>
          <div class="es-vs-ctx">${stageTxt}</div>
          <span class="pill es-bo">Best of ${fix.best_of}</span>
          ${fix.rivalry ? `<span class="pill es-rivalry" title="Grudge match — rivalry heat ${fix.rivalry}">⚔ RIVALRY</span>` : ""}
        </div>` +
        teamBlock(oppId, oppName, oppLogo, "right")));

    const cols = el("div", "es-snap-cols");
    const colL = el("div", "es-snap-col");
    const colR = el("div", "es-snap-col");

    // Head-to-head this season vs the upcoming opponent.
    if (fix.h2h) {
      const h = fix.h2h;
      const lead = h.wins === h.losses ? "level" : h.you_lead ? "you lead" : "you trail";
      const hstreak =
        h.streak_len > 1 ? ` · ${h.streak_team === myId ? "W" : "L"}${h.streak_len}` : "";
      colL.appendChild(el("div", "es-h2h muted",
        `Head-to-head this season: <b>${h.wins}–${h.losses}</b> (${lead})${hstreak}`));
    }
    // Grounded prose preview.
    if ((fix.preview || []).length) {
      colL.appendChild(el("p", "es-preview muted", fix.preview.join(" ")));
    }
    // Game-plan state: the natural moment to set one is when reading this card.
    {
      const has = !!(gameplan && gameplan.plan);
      const row = el("div", "row");
      row.appendChild(el("span", "pill" + (has ? " gp-live" : ""), has ? "Game plan: set" : "Game plan: none"));
      const go = el("button", "btn btn-sm", has ? "Review plan ▸" : "Set a plan ▸");
      go.onclick = () => { App.tacticsTab = "gameplan"; dashGoTab("tactics"); };
      row.appendChild(go);
      colL.appendChild(row);
    }
    // Map feature — the veto ladder in playoffs, else the map pool thumbs.
    if (fix.veto && fix.veto.length) {
      const vr = el("div", "es-maps");
      vr.appendChild(el("span", "es-maps-lab muted", "Veto"));
      for (const entry of fix.veto) {
        const mapId = entry.trim().split(" ").pop();
        vr.appendChild(el("span", "veto-chip", `${mapThumb(mapId, "sm")}${esc(entry)}`));
      }
      colL.appendChild(vr);
    } else if (fix.maps && fix.maps.length) {
      const mr = el("div", "es-maps");
      mr.appendChild(el("span", "es-maps-lab muted", fix.maps.length > 1 ? "Map pool" : "Map"));
      for (const mid of fix.maps) {
        mr.appendChild(el("figure", "es-map",
          `<img src="/assets/maps/${mid}.webp" alt="${mid}" onerror="this.style.display='none'">` +
            `<figcaption>${mid}</figcaption>`));
      }
      colL.appendChild(mr);
    }
    // Run-in: the next few weeks at a glance.
    if ((s.run_in || []).length) {
      const wrap = el("div", "");
      wrap.appendChild(el("span", "es-scout-lab muted", "Run-in"));
      const strip2 = el("div", "es-runin");
      for (const f of s.run_in) {
        strip2.appendChild(el("span", `es-runin-chip diff-${f.difficulty}`,
          `<span class="muted">W${f.week}</span> ${tlink(f.opponent_id, f.opponent)}`));
      }
      wrap.appendChild(strip2);
      colL.appendChild(wrap);
    }

    // Opponent scouting: last-5 form + danger men + coaching read.
    if (oppId) {
      const oppGames = playedFor(oppId).slice(-5);
      if (oppGames.length) {
        const col = el("div", "es-scout-col");
        col.appendChild(el("span", "es-scout-lab muted", `${esc(oppName)} — last ${oppGames.length}`));
        const strip3 = el("span", "es-form-strip");
        for (const g of oppGames) {
          const ln = lineFor(g, oppId);
          strip3.appendChild(formSquare(ln.res, `vs ${ln.oppName}${ln.score ? " · " + ln.score : ""}`));
        }
        col.appendChild(strip3);
        colR.appendChild(col);
      }
      if (oppRoster && oppRoster.players.length) {
        const fog = oppRoster.fog > 0;
        const stars = [...oppRoster.players].sort((a, b) => b.overall - a.overall).slice(0, 3);
        const col = el("div", "es-scout-col");
        col.appendChild(el("span", "es-scout-lab muted", "Danger men"));
        const names = el("span", "es-stars");
        for (const p of stars) {
          names.appendChild(el("span", "es-star",
            plink(p.id, p.handle) +
              `<span class="pill">${esc(p.role)}</span>` +
              `<span class="mono muted">${fog ? "~" : ""}${Math.round(p.overall)}</span>`));
        }
        col.appendChild(names);
        colR.appendChild(col);
      }
      if (oppRoster && (oppRoster.identity || (oppRoster.tendencies ?? []).length)) {
        const col = el("div", "es-scout-col");
        col.appendChild(el("span", "es-scout-lab muted", "Playstyle"));
        if (oppRoster.identity) col.appendChild(el("span", "pill es-identity", esc(oppRoster.identity)));
        if ((oppRoster.tendencies ?? []).length) {
          col.appendChild(el("span", "es-tendencies muted", oppRoster.tendencies.map(esc).join(" · ")));
        }
        colR.appendChild(col);
      }
    }
    // Map pool & veto: your map win rates + a suggested ban/pick vs this opp.
    // Guard on ACTUAL content — early in a season there are no map win rates
    // and no veto ban/pick yet, so the section (and its label) must stay hidden
    // rather than render an empty box.
    const mp = fix.map_pool;
    if (mp && (mp.maps.length || (mp.veto && (mp.veto.ban || mp.veto.pick)))) {
      const board = el("div", "es-mappool");
      if (mp.veto && (mp.veto.ban || mp.veto.pick)) {
        const vr = el("div", "es-veto");
        if (mp.veto.ban) {
          vr.appendChild(el("span", "es-veto-chip ban",
            `Ban ${mp.veto.ban.map} <span class="muted">(${mp.veto.ban.map ? mp.veto.opponent : ""} ${mp.veto.ban.their_wr}% · you ${mp.veto.ban.our_wr}%)</span>`));
        }
        if (mp.veto.pick) {
          vr.appendChild(el("span", "es-veto-chip pick",
            `Pick ${mp.veto.pick.map} <span class="muted">(you ${mp.veto.pick.our_wr}% · them ${mp.veto.pick.their_wr}%)</span>`));
        }
        board.appendChild(vr);
      }
      if (mp.maps.length) {
        const bars = el("div", "es-mapbars");
        for (const m of mp.maps.slice(0, 7)) {
          const wr = m.win_rate == null ? 0 : m.win_rate;
          bars.appendChild(el("div", "es-mapbar",
            `<span class="es-mapbar-name">${m.map}</span>` +
            `<span class="es-mapbar-track"><span class="es-mapbar-fill" style="width:${wr}%"></span></span>` +
            `<span class="mono es-mapbar-wr">${m.win_rate == null ? "—" : m.win_rate + "%"}</span>` +
            `<span class="muted es-mapbar-n">${m.wins}/${m.played}</span>`));
        }
        board.appendChild(bars);
      }
      const wrap = el("div", "es-spot-sub");
      wrap.appendChild(el("span", "es-scout-lab muted", "Map pool & veto"));
      wrap.appendChild(board);
      colR.appendChild(wrap);
    }

    if (colL.childElementCount) cols.appendChild(colL);
    if (colR.childElementCount) cols.appendChild(colR);
    if (cols.childElementCount) spot.appendChild(cols);
  } else {
    spot.appendChild(el("p", "muted", `No fixture scheduled — ${esc(String(s.phase || ""))}.`));
  }
  main.appendChild(spot);

  /* -- 4. MATCH REVIEW (main): why you won/lost + what to tweak ------------- */
  const lmr = s.last_match_review;
  const debrief = s.debrief || {};
  if (lmr || debrief.result || s.press) {
    const card = el("div", "card");
    card.appendChild(el("h2", "", "Match review"));
    // Last-time-out debrief + pundit line lead the card (relocated from the
    // old Manager's desk so the whole post-match read lives in one place).
    if (debrief.result) {
      const parts = [`<b class="${debrief.won ? "wl-w" : "wl-l"}">${esc(debrief.result)}</b>.`];
      if (debrief.standout) parts.push(`Standout: ${esc(debrief.standout)}.`);
      if (debrief.underperformer) parts.push(`Off-colour: ${esc(debrief.underperformer)}.`);
      card.appendChild(el("p", "muted", "Last time out — " + parts.join(" ")));
    }
    if (s.press) card.appendChild(el("p", "es-press", `“${esc(s.press)}”`));
    if (lmr) {
      const scoreTxt = lmr.best_of > 1
        ? `${lmr.your_maps}–${lmr.their_maps}`
        : `${lmr.your_rounds}–${lmr.their_rounds}`;
      card.appendChild(el("div", "row es-review-head",
        `<span class="pill ${lmr.won ? "win" : "loss"}">${lmr.won ? "W" : "L"}</span>` +
        `<span class="es-review-opp">vs ${tlink(lmr.opp_id, lmr.opp_name)}</span>` +
        `<span class="spacer"></span>` +
        `<b class="mono es-review-score">${scoreTxt}</b>`));
      if (lmr.potm) {
        card.appendChild(el("div", "potm-chip",
          `<span class="potm-star">★</span> POTM ${plink(lmr.potm.player_id, lmr.potm.handle)}` +
          badgeStrip(lmr.potm.badges)));
      }
      if (lmr.momentum_beat) {
        const mb = lmr.momentum_beat;
        card.appendChild(el("div", "rowbar es-momentum-beat",
          `<span class="chip ${mb.tone === "hot" ? "tone-good" : "tone-brand"}">${esc(mb.tone)}</span>` +
          `<span>${plink(mb.player_id, mb.handle)} ${esc(mb.text)}</span>`));
      }
      if (!lmr.contested) {
        card.appendChild(el("p", "muted", "Match not contested — no breakdown."));
      } else {
        const mkCol = (label, points) => {
          const col = el("div", "es-snap-col");
          col.appendChild(el("span", "es-scout-lab muted", label));
          const list = el("div", "es-review-list");
          if (!points.length) list.appendChild(el("div", "muted es-review-d", "—"));
          for (const p of points) {
            const note = p.dev_note ? `<span class="es-review-d muted">${esc(p.dev_note)}</span>` : "";
            const pt = el("div", "es-review-pt " + (p.tone === "good" ? "good" : "bad"),
              `<b class="es-review-h">${esc(p.headline)}${badgeStrip(p.badges)}</b>` +
              `<span class="es-review-d muted">${esc(p.detail)}</span>` + note);
            if (p.player_id) pt.dataset.pid = p.player_id;  // whole row -> profile
            list.appendChild(pt);
          }
          col.appendChild(list);
          return col;
        };
        const cols2 = el("div", "es-snap-cols");
        cols2.appendChild(mkCol("What worked", lmr.working));
        cols2.appendChild(mkCol("Where it broke down", lmr.breaking));
        card.appendChild(cols2);
        if (lmr.levers && lmr.levers.length) {
          card.appendChild(el("span", "es-scout-lab muted", "What to tweak"));
          const tabOf = { tactics: "tactics", training: "roster", roster: "roster" };
          const ll = el("div", "es-review-levers");
          for (const lv of lmr.levers) {
            const row = el("div", "es-review-lever" + (lv.on_focus ? " on-focus" : ""),
              `<span class="es-review-arrow">▸</span> ${esc(lv.text)}`);
            row.onclick = () => dashGoTab(tabOf[lv.tab] || "tactics");
            ll.appendChild(row);
          }
          card.appendChild(ll);
        } else if (lmr.coach && !lmr.coach.present) {
          card.appendChild(el("p", "muted es-review-d", "Hire a coach for tailored fixes."));
        }
        if (lmr.locked && lmr.locked_hint) {
          card.appendChild(el("p", "muted es-review-d", esc(lmr.locked_hint)));
        }
      }
    }
    main.appendChild(card);
  }

  /* -- 5. RAIL: decisions first, then context ------------------------------- */

  // 5a. Action items: everything waiting on the manager, deep-linked.
  {
    const card = el("div", "card");
    card.appendChild(el("h2", "", "Action items"));
    const list = el("div", "es-obj");
    const item = (html, go) => {
      const row = el("div", "es-obj-row es-action", `<span class="es-review-arrow">▸</span> ${html}`);
      if (go) { row.style.cursor = "pointer"; row.onclick = go; }
      list.appendChild(row);
    };
    for (const e of (s.squad_profile?.expiries ?? []).filter((e) => e.weeks_left > 0 && e.weeks_left <= 8)) {
      item(`${plink(e.id, e.handle)} contract up in <b class="mono">${e.weeks_left}w</b>`,
        () => dashGoTab("roster"));
    }
    for (const o of s.transfer_offers ?? []) {
      item(`Offer in for ${plink(o.player_id, o.handle)} — expires W${o.expires_week}`, null);
    }
    if (s.scout && s.scout.target && (s.scout.progress || 0) >= 1) {
      item(`Scout report ready — ${esc(s.scout.target_name || "target")}`, () => dashGoTab("scouting"));
    }
    if (fix && gameplan && !gameplan.plan) {
      item(`No game plan set for W${fix.week}`, () => { App.tacticsTab = "gameplan"; dashGoTab("tactics"); });
    }
    const unread = (typeof inboxUnread !== "undefined" && inboxUnread) ? inboxUnread : 0;
    if (unread > 0) {
      item(`${unread} unread inbox message${unread > 1 ? "s" : ""}`, () => dashGoTab("inbox"));
    }
    if (!list.childElementCount) {
      list.appendChild(el("div", "muted", "All clear — advance when ready."));
    }
    card.appendChild(list);
    rail.appendChild(card);
  }

  // 5b. Objectives: board line + what to chase.
  const objectives = s.objectives_hub || [];
  if (s.board || objectives.length) {
    const card = el("div", "card");
    card.appendChild(el("h2", "", "Objectives"));
    if (s.board) {
      const bcls = s.board.band === "secure" || s.board.band === "stable" ? "good"
        : s.board.band === "under pressure" ? "warn" : "bad";
      card.appendChild(el("p", "es-board",
        `<span class="pill obj ${bcls}">Board: ${esc(s.board.band)}</span> ` +
        `Goal — ${esc(s.board.goal)} <span class="muted">(${esc((s.board.goal_state || "").replace("_", " "))}` +
        `${s.board.seasons_left ? " · " + s.board.seasons_left + " season" + (s.board.seasons_left > 1 ? "s" : "") + " left" : ", final season"})</span>`));
    }
    if (objectives.length) {
      const list = el("div", "es-obj");
      for (const o of objectives.slice(0, 6)) {
        const cls = o.state === "achieved" || o.state === "on_track" || o.state === "leading" ? "good"
          : o.state === "missed" ? "bad" : "warn";
        list.appendChild(el("div", "es-obj-row",
          `<span class="pill obj ${cls}">${esc(o.kind)}</span> ${esc(o.label)} ` +
          `<span class="muted">${esc((o.state || "").replace("_", " "))}${o.detail ? " · " + esc(o.detail) : ""}</span>`));
      }
      card.appendChild(list);
    }
    rail.appendChild(card);
  }

  // 5c. Form & fitness: movers, burnout, the season's shape.
  const movers = s.movers || [];
  const burnt = (s.rotation || []).filter((r) => r.burnout);
  const trend = s.form_trend || [];
  if (movers.length || burnt.length || trend.length >= 2) {
    const card = el("div", "card");
    card.appendChild(el("h2", "", "Form & fitness"));
    if (movers.length) {
      card.appendChild(el("span", "es-scout-lab muted", "Your movers · this week"));
      const list = el("div", "es-movers");
      for (const m of movers) {
        const up = m.delta > 0;
        list.appendChild(el("div", "es-mover",
          `${plink(m.pid, m.handle)} ` +
          `<span class="mover-delta ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${Math.abs(m.delta).toFixed(1)}</span>`));
      }
      card.appendChild(list);
    }
    if (burnt.length) {
      card.appendChild(el("span", "es-scout-lab muted", "Burnout watch"));
      const list = el("div", "es-movers");
      for (const r of burnt) {
        list.appendChild(el("div", "es-mover",
          `${plink(r.id, r.handle)} ` +
          `<span class="muted">${r.maps} maps</span> <b class="mono trend-down">${r.stamina} sta</b>`));
      }
      card.appendChild(list);
    }
    if (trend.length >= 2) {
      card.appendChild(el("span", "es-scout-lab muted", "Cumulative wins"));
      const W = 220, H = 46, maxW = trend[trend.length - 1].wins || 1;
      const pts = trend.map((p, i) => {
        const x = trend.length > 1 ? (i / (trend.length - 1)) * (W - 4) + 2 : 2;
        const y = H - 4 - (p.wins / maxW) * (H - 8);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      const dots = trend.map((p, i) => {
        const x = trend.length > 1 ? (i / (trend.length - 1)) * (W - 4) + 2 : 2;
        const y = H - 4 - (p.wins / maxW) * (H - 8);
        return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2" class="${p.won ? "es-spark-w" : "es-spark-l"}"/>`;
      }).join("");
      const spark = el("div", "es-spark",
        `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="cumulative wins">` +
        `<polyline points="${pts}" fill="none" class="es-spark-line"/>${dots}</svg>` +
        `<span class="muted">${maxW}W in ${trend.length} played</span>`);
      card.appendChild(spark);
    }
    rail.appendChild(card);
  }

  // 5d. League + recent results: a two-up band at the bottom of the main
  // column (the rail keeps the always-on modules; these two are context).
  const band = el("div", "grid2");
  const bandL = el("div", "ws-col");
  const bandR = el("div", "ws-col");
  band.appendChild(bandL);
  band.appendChild(bandR);
  main.appendChild(band);
  let rows = null;
  if (table) {
    const reg = table.regions.find((r) => r.is_user) || table.regions[0];
    rows = reg ? reg.rows : [];
  } else if ((s.standings_top ?? []).length) {
    rows = s.standings_top.map((r) => ({
      id: r.team_id, name: r.name, wins: r.wins, losses: r.losses, diff: r.diff,
    }));
  }
  {
    const card = el("div", "card");
    card.appendChild(el("h2", "", `${cap(regionOf[myId] || me.region || "")} league`));
    if (rows && rows.length) {
      const t = el("table");
      t.dataset.nosort = "1";
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
        tb.appendChild(el("tr", r.id === myId ? "me" : "",
          `<td>${i + 1}</td>` +
            `<td>${tlink(r.id, r.name)}</td>` +
            `<td class="num">${r.wins}</td><td class="num">${r.losses}</td>` +
            `<td class="num">${d > 0 ? "+" : ""}${d}</td>`));
        prev = i;
      }
      t.appendChild(tb);
      card.appendChild(t);
    }
    // Rating leaders (league-wide top performers).
    if ((s.leaders || []).length) {
      card.appendChild(el("span", "es-scout-lab muted", "Rating leaders"));
      const list = el("div", "es-movers");
      for (const l of s.leaders) {
        list.appendChild(el("div", "es-mover",
          `<span>${plink(l.pid, l.handle)} <span class="muted">${tlink(l.team_id, l.team)}</span></span> ` +
          `<b class="mono">${l.rating.toFixed(2)}</b>`));
      }
      card.appendChild(list);
    }
    // Org standing one-liner (fans/world rank/reputation live here, not tiles).
    const orgBits = [];
    if (me.world_rank != null) orgBits.push(`World <b class="mono">#${me.world_rank}</b>`);
    if (me.reputation != null) orgBits.push(`Rep <b class="mono">${Math.round(me.reputation)}</b>`);
    if (me.fan_count != null) orgBits.push(`Fans <b class="mono">${fmtFollowers(me.fan_count)}</b>`);
    if (orgBits.length) card.appendChild(el("p", "muted es-org-line", orgBits.join(" · ")));
    const full = el("button", "btn btn-sm", "Full table ▸");
    full.onclick = () => dashGoTab("standings");
    card.appendChild(full);
    bandL.appendChild(card);
  }

  // 5e. Recent results.
  {
    const rc = el("div", "card");
    rc.appendChild(el("h2", "", "Recent results"));
    const myGames = playedFor(myId).slice(-5).reverse();
    if (myGames.length) {
      for (const f of myGames) {
        const ln = lineFor(f, myId);
        const thumbs = ln.maps.map((m) => mapThumb(m, "sm")).join("");
        rc.appendChild(el("div", "row es-result",
          `<span class="pill ${ln.res === "W" ? "win" : "loss"}">${ln.res}</span>` +
            `${tlink(ln.opp, ln.oppName, "es-result-opp")}` +
            `<span class="spacer"></span>` +
            `<b class="mono es-result-score">${ln.score}</b>` +
            `<span class="es-result-maps">${thumbs}</span>`));
      }
    } else {
      rc.appendChild(el("p", "muted", "No matches played yet this season."));
    }
    bandR.appendChild(rc);
  }

  // 5f. News + on this day.
  {
    const news = el("div", "card");
    news.appendChild(el("h2", "", "News"));
    const scroll = el("div", "card-scroll");
    scroll.style.setProperty("--scroll-max", "300px");
    if ((s.news ?? []).length) {
      for (const n of s.news) scroll.appendChild(el("div", "newsline", n));
    } else {
      scroll.appendChild(el("p", "muted", "No news yet."));
    }
    news.appendChild(scroll);
    if ((s.on_this_day || []).length) {
      news.appendChild(el("span", "es-scout-lab muted", "On this day"));
      const list = el("div", "es-otd");
      for (const o of s.on_this_day) {
        list.appendChild(el("div", "muted", `<b class="mono">${o.seasons_ago}yr</b> ${esc(o.text)}`));
      }
      news.appendChild(list);
    }
    rail.appendChild(news);
  }

  // 5g. Manager career — the chronicle in brief; detail one click away.
  if (career && career.name) {
    const cc = el("div", "card es-career");
    cc.appendChild(el("h2", "", "Manager career"));
    const sub = [career.name, career.archetype ? cap(career.archetype.replace(/_/g, " ")) : null]
      .filter(Boolean)
      .join(" · ");
    cc.appendChild(el("div", "muted es-career-sub", esc(sub)));
    if (career.contract && career.contract.goal) {
      const gst = career.contract.goal_status || {};
      const st = gst.state || "pending";
      const cls = st === "achieved" || st === "on_track" ? "good" : st === "missed" ? "bad" : "warn";
      cc.appendChild(el("div", "es-goal",
        `Board goal: <b>${esc(career.contract.goal)}</b> · ` +
        `<span class="goal-${cls}">${esc(st.replace("_", " "))}</span>` +
        (gst.detail ? ` <span class="muted">(${esc(gst.detail)})</span>` : "")));
    }
    cc.appendChild(el("p", "es-career-line",
      `Titles <b class="mono">${(career.titles || []).length}</b> · ` +
      `Developed <b class="mono">${career.players_developed ?? 0}</b> · ` +
      `Debuts <b class="mono">${career.debuts_given ?? 0}</b> · ` +
      `Signings <b class="mono">${career.signings ?? 0}</b>`));
    // Reputation axes — the numbers that gate career offers.
    if (career.reputation && Object.keys(career.reputation).length) {
      cc.appendChild(el("span", "es-scout-lab muted", "Reputation"));
      const list = el("div", "es-mb");
      for (const [axis, val] of Object.entries(career.reputation)) {
        list.appendChild(el("div", "rowbar",
          `<span class="muted">${esc(humanize(axis))}</span>` +
          `<span class="bar"><i style="width:${Math.max(2, Math.min(100, val))}%"></i></span>` +
          `<span class="rowbar-val">${Math.round(val)}</span>`));
      }
      cc.appendChild(list);
    }
    const tagRow = (label, items) => {
      const vals = (items || []).map((x) => x && (x.name || x)).filter(Boolean);
      if (!vals.length) return;
      const row = el("div", "es-career-tags");
      row.appendChild(el("span", "muted es-career-lab", label));
      for (const val of vals) row.appendChild(el("span", "pill", esc(val)));
      cc.appendChild(row);
    };
    tagRow("Known for", career.known_for);
    tagRow("Philosophy", career.philosophies);
    if (typeof openManagerProfile === "function") {
      const btn = el("button", "btn btn-sm", "Career ▸");
      btn.onclick = () => openManagerProfile(career);
      cc.appendChild(btn);
    }
    rail.appendChild(cc);
  }
}

// Compact follower count: 12,400 -> "12.4K", 1,200,000 -> "1.2M".
function fmtFollowers(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
}

async function roster(v) {
  const teamId = App.rosterTeam ?? App.state.user_team.id;
  const data = await api(`/api/roster/${teamId}`);
  const s = App.state;
  const cols = App.rosterCols ?? "overview";
  const overview = cols !== "development";
  const cap = data.roster_max ?? 5;
  const handleOf = Object.fromEntries(data.players.map((p) => [p.id, p.handle]));

  // Default-lineup working set: with a bench, the manager names the five who
  // dress by default (per-map overrides live on the map-lineups band).
  const hasBench = data.is_user_team && data.players.length > 5;
  const lineup = new Set(data.players.filter((p) => p.starter).map((p) => p.id));
  let lineupBar = null;
  const paintLineupBar = () => {
    if (!lineupBar) return;
    const n = lineup.size;
    lineupBar.querySelector("b").textContent = `${n}/5`;
    lineupBar.querySelector("button").disabled = n !== 5;
  };

  /* -- screen head: title · team · view seg · right-side actions ------------ */
  const right = [];
  if (hasBench) {
    lineupBar = el("div", "row",
      `<span class="microlabel" title="Toggle ★ in the table to change who dresses. Bench players scrim (reduced growth) and good ones want minutes.">Default five</span> <b class="mono">${lineup.size}/5</b>`);
    const save = el("button", "btn btn-sm btn-primary", "Save lineup");
    save.onclick = async () => {
      const r = await api("/api/actions/lineup", { lineup_ids: [...lineup] });
      toast(r.message); render();
    };
    lineupBar.appendChild(save);
    right.push(lineupBar);
    paintLineupBar();
  }
  if (!data.is_user_team) {
    const back = el("button", "btn btn-sm", "← My team");
    back.onclick = () => { App.rosterTeam = null; render(); };
    right.push(back);
    const scout = el("button", "btn btn-sm",
      data.scouting_this
        ? `Scouting… ${Math.round(data.scout_progress * 100)}%`
        : "Assign scout");
    scout.disabled = data.scouting_this && data.scout_progress >= 1;
    scout.onclick = async () => {
      const r = await api("/api/actions/scout", { team_id: teamId });
      toast(r.message); render();
    };
    right.push(scout);
  }
  const fogSub = data.fog > 0 ? ` · <span class="muted">±${data.fog} fog</span>` : "";
  v.appendChild(screenHead("Roster", {
    sub: `${tlink(data.team.id, data.team.name)} <span class="muted">· ${data.players.length}/${cap}</span>${fogSub}`,
    subtabs: [
      { id: "overview", label: "Overview" },
      { id: "development", label: "Development" },
    ],
    active: cols,
    onPick: (id) => { App.rosterCols = id; render(); },
    right,
  }));

  const ws = el("div", "ws roster-ws");
  v.appendChild(ws);
  // The roster table is wide (13 columns) — give it the full content width so
  // every column, including the actions, is visible without a horizontal
  // scroll. The supporting cards tile in a row beneath it (.roster-support).
  const main = el("div", "ws-12 roster-main");
  const rail = el("div", "ws-12 roster-support");
  ws.appendChild(main);
  ws.appendChild(rail);

  /* -- main ws-9: the roster table ----------------------------------------- */
  const card = el("div", "card roster-card");
  if (data.is_user_team && data.players.length < (data.roster_min ?? 5)) {
    card.appendChild(el("p", "warn",
      `⚠ You need ${data.roster_min ?? 5} players to advance the week — sign ${(data.roster_min ?? 5) - data.players.length} more.`));
  } else if (data.is_user_team && data.players.length < 6) {
    card.appendChild(el("p", "muted",
      "Tip: a 6-man roster is advised for tournaments (register a bench)."));
  }

  const starTh = hasBench ? "<th>★</th>" : "";
  const t = el("table", "roster-table");
  t.innerHTML = overview
    ? `<thead><tr>${starTh}<th>Player</th><th>Role</th><th>Agent</th>
       <th class="num">Age</th><th class="num">OVR</th><th>Ceiling</th>
       <th>Form</th><th>Morale</th><th class="num">Sta</th><th>Conf</th>
       <th class="num">Salary</th><th class="num">Wks</th><th></th></tr></thead>`
    : `<thead><tr>${starTh}<th>Player</th><th class="num">Age</th><th class="num">OVR</th>
       <th>Ceiling</th><th>Form</th><th>Conf</th>
       <th>Dev focus</th><th>Language</th><th>Intensity</th><th>Mentor</th></tr></thead>`;
  // Detail-row colspan must match the ACTUAL current column count.
  const ncols = t.querySelector("thead tr").children.length;
  const tb = el("tbody");

  for (const p of data.players) {
    const fogged = p.fog > 0;
    const ovr = fogged ? `~${Math.round(p.overall)}` : p.overall;
    // Own-club condition trend arrows (server sends condition_trend only for
    // your roster, and only once there are two dev-history points).
    const ct = p.condition_trend || {};
    const tArrow = (d) =>
      d === "up" ? ' <span class="trend-up" title="trending up">▲</span>'
        : d === "down" ? ' <span class="trend-down" title="trending down">▼</span>' : "";
    const benchPill = hasBench && !lineup.has(p.id) ? ' <span class="pill">bench</span>' : "";
    // Heavy-streamer chip: streaming slows this player's development.
    const streamChip = p.stream_heavy
      ? ' <span class="chip" title="heavy streaming slows this player\'s development">📺</span>'
      : "";
    const badges = (p.badges || []).map((bd) =>
      ` <span class="roster-badge ${bd.polarity < 0 ? "badge-neg" : "badge-pos"}" title="${esc(bd.name)}: ${esc(bd.blurb)}">${bd.emoji}</span>`).join("");
    const starCell = hasBench
      ? `<td><button class="btn btn-sm starter-toggle ${lineup.has(p.id) ? "active" : ""}" data-act="star" title="starter / bench">${lineup.has(p.id) ? "★" : "☆"}</button></td>`
      : "";
    const playerCell = `<td><img class="portrait" src="${p.portrait}" alt=""><b>${plink(p.id, p.handle)}</b>${p.id === data.team.captain_id ? ' <span class="pill">IGL</span>' : ""}${p.mentor_id ? ' <span class="pill mentor-pill" title="under a mentor\'s wing">🎓</span>' : ""}${badges}${benchPill}${streamChip}</td>`;
    const ceilingCell = `<td>${p.potential_stars != null ? starsRange([p.potential_stars, p.potential_stars]) : '<span class="muted">scout</span>'}</td>`;

    let rowHtml;
    if (overview) {
      const actions = data.is_user_team
        ? `<button class="btn btn-sm" data-act="talk">Talk</button>
           <button class="btn btn-sm" data-act="renew">Renew</button>
           <button class="btn btn-sm" data-act="release">Release</button>`
        : p.buyout != null
          // Tier-2 contract: the buyout clause is the fast lane — pay it and
          // the player arrives, no negotiation, the org can't refuse.
          ? `<button class="btn btn-sm" data-act="buyout" title="trigger the buyout clause — the org can't refuse">Buy out ${money(p.buyout)}</button>`
          : p.transfer_ask != null
            ? `<button class="btn btn-sm" data-act="bid" title="buy out this contract">Bid ${money(p.transfer_ask)}</button>
               <button class="btn btn-sm" data-act="offer" title="offer players and/or cash">Offer…</button>`
            : "";
      rowHtml = `
        ${starCell}
        ${playerCell}
        <td>${stylePill(p)}</td>
        <td>${p.planned_agent
          ? `<span class="pill" title="${p.planned_locked ? "locked by their coach" : "likely auto-pick"}">${esc(p.planned_agent)}${p.planned_locked ? "" : " ?"}</span>`
          : '<span class="muted">scout</span>'}</td>
        <td class="num">${p.age}</td>
        <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${ovr}</td>
        ${ceilingCell}
        <td>${bar(p.form)}${tArrow(ct.form)}</td><td>${bar(p.morale)}</td><td>${bar(p.stamina)}</td>
        <td title="confidence — feeds duels, peeks and clutch nerve">${bar(p.confidence)}${tArrow(ct.confidence)}</td>
        <td class="num">${money(p.salary)}/wk</td>
        <td class="num">${p.contract_weeks_left}w</td>
        <td><div class="roster-actions">${actions}</div>${askBreakdown(p.ask_breakdown)}</td>`;
    } else {
      // Development view: the per-player weekly plan, one interaction each.
      // Mentorship: older, higher-rated teammates can mentor this player,
      // sorted by hidden teaching ability (mentor_skill) so the best teacher
      // is first — a strong mentor raises the protege's ceiling.
      const eligibleMentors = data.is_user_team
        ? data.players
            .filter((q) => q.id !== p.id && q.age > p.age && (q.overall ?? 0) > (p.overall ?? 0))
            .sort((a, b) => (b.mentor_skill ?? 0) - (a.mentor_skill ?? 0))
        : [];
      const focusSel = data.is_user_team
        ? `<select data-act="focus" title="training focus (auto = team week; rest = recover instead)">
             ${(data.dev_focus_options ?? []).map((o) => `<option value="${o}" ${o === p.dev_focus ? "selected" : ""} ${o === "language" && !data.has_language_coach ? "disabled" : ""}>${o}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      const languageSel = data.is_user_team
        ? `<select data-act="language" title="language to practise; it replaces game-skill training for the week" ${data.has_language_coach ? "" : "disabled"}>
             <option value="">choose language</option>
             ${(data.language_options ?? []).map((o) => `<option value="${o}" ${o === p.learning_language ? "selected" : ""}>${o.toUpperCase()}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      const intSel = data.is_user_team
        ? `<select data-act="intensity" title="intensity: light spares legs, intense grows faster but risks burnout">
             ${(data.intensity_options ?? []).map((o) => `<option value="${o}" ${o === p.training_intensity ? "selected" : ""}>${o}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      const mentorSel = data.is_user_team && (eligibleMentors.length || p.mentor_id)
        ? `<select data-act="mentor" title="pair with a veteran mentor: faster growth + a higher ceiling on the mentor's best skills (teach = teaching ability)">
             <option value="">no mentor</option>
             ${eligibleMentors.map((q) => `<option value="${q.id}" ${q.id === p.mentor_id ? "selected" : ""}>🎓 ${esc(q.handle)}${q.mentor_skill != null ? ` (teach ${q.mentor_skill})` : ""}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      rowHtml = `
        ${starCell}
        ${playerCell}
        <td class="num">${p.age}</td>
        <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${ovr}</td>
        ${ceilingCell}
        <td>${bar(p.form)}${tArrow(ct.form)}</td>
        <td title="confidence — feeds duels, peeks and clutch nerve">${bar(p.confidence)}${tArrow(ct.confidence)}</td>
        <td class="dev-plan">${focusSel}</td>
        <td class="dev-plan">${languageSel}</td>
        <td class="dev-plan">${intSel}</td>
        <td class="dev-plan">${mentorSel}</td>`;
    }
    const tr = el("tr", "", rowHtml);

    if (hasBench) {
      tr.querySelector('[data-act="star"]').onclick = (e) => {
        e.stopPropagation();
        const btn = e.currentTarget;
        if (lineup.has(p.id)) lineup.delete(p.id);
        else lineup.add(p.id);
        btn.classList.toggle("active", lineup.has(p.id));
        btn.textContent = lineup.has(p.id) ? "★" : "☆";
        paintLineupBar();
      };
    }
    if (!overview && data.is_user_team) {
      const post = async (field, value) => {
        const r = await api("/api/actions/dev_plan", { player_id: p.id, [field]: value });
        toast(r.message);
      };
      const fSel = tr.querySelector('[data-act="focus"]');
      if (fSel) { fSel.onclick = (e) => e.stopPropagation(); fSel.onchange = () => post("dev_focus", fSel.value); }
      const lSel = tr.querySelector('[data-act="language"]');
      if (lSel) { lSel.onclick = (e) => e.stopPropagation(); lSel.onchange = () => post("learning_language", lSel.value); }
      const iSel = tr.querySelector('[data-act="intensity"]');
      if (iSel) { iSel.onclick = (e) => e.stopPropagation(); iSel.onchange = () => post("training_intensity", iSel.value); }
      const mSel = tr.querySelector('[data-act="mentor"]');
      if (mSel) {
        mSel.onclick = (e) => e.stopPropagation();
        mSel.onchange = async () => {
          const r = await api("/api/actions/mentor", {
            protege_id: p.id,
            mentor_id: mSel.value || null,
          });
          toast(r.message);
          if (App.tab === "roster") render();
        };
      }
    }
    if (overview && !data.is_user_team && p.buyout != null) {
      tr.querySelector('[data-act="buyout"]').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`Trigger ${p.handle}'s buyout clause for ${money(p.buyout)}? ${data.team.name} can't refuse.`)) return;
        const r = await api("/api/actions/buyout", { player_id: p.id });
        toast(r.message); refresh(); render();
      };
    } else if (overview && !data.is_user_team && p.transfer_ask != null) {
      tr.querySelector('[data-act="bid"]').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`Buy ${p.handle} from ${data.team.name} for ${money(p.transfer_ask)}?`)) return;
        const r = await api("/api/actions/bid", { player_id: p.id });
        toast(r.message); refresh(); render();
      };
      tr.querySelector('[data-act="offer"]').onclick = (e) => {
        e.stopPropagation();
        openOffer({ id: p.id, handle: p.handle, ask: p.transfer_ask,
          team_name: data.team.name, ask_breakdown: p.ask_breakdown });
      };
    }
    if (overview && data.is_user_team) {
      tr.querySelector('[data-act="talk"]').onclick = (e) => {
        e.stopPropagation();
        openTalk(p);
      };
      tr.querySelector('[data-act="renew"]').onclick = (e) => {
        e.stopPropagation();
        openNegotiation({ id: p.id, handle: p.handle }); // a table, not a button
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
    tr.onclick = (e) => {
      if (e.target.tagName === "SELECT" || e.target.tagName === "OPTION") return;
      // isConnected: the sort delegate removes detail rows before sorting,
      // so a stale reference means "recreate", not "collapse".
      if (detail && detail.isConnected) { detail.remove(); detail = null; return; }
      detail = el("tr", "", `<td colspan="${ncols}">${attrDetail(p)}</td>`);
      detail.dataset.detail = "1";
      tr.after(detail);
    };
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  // The wide roster table scrolls horizontally inside its card rather than
  // pushing the page — it stays on-screen in the ws-9 cell.
  const tScroll = el("div", "table-scroll");
  tScroll.appendChild(t);
  card.appendChild(tScroll);
  main.appendChild(card);

  /* -- rail ws-3: squad profile · scouting book · locker room · map lineups - */

  // Squad profile: avg age + youth/prime/vet buckets. Ages are public, so
  // computed from the roster; the server's rounded avg is preferred for the
  // user team when present.
  {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Squad profile"));
    const ages = data.players.map((p) => p.age);
    const buckets = { youth: 0, prime: 0, veteran: 0 };
    for (const a of ages) {
      if (a <= 21) buckets.youth++;
      else if (a <= 26) buckets.prime++;
      else buckets.veteran++;
    }
    const sp = data.is_user_team ? (s.squad_profile || null) : null;
    const avgAge = sp?.avg_age ?? (ages.length ? Math.round((ages.reduce((x, y) => x + y, 0) / ages.length) * 10) / 10 : 0);
    const bk = sp?.buckets ?? buckets;
    const total = data.players.length || 1;
    c.appendChild(el("p", "muted", `Average age <b class="mono">${avgAge}</b>`));
    const bucketRow = (label, n) => el("div", "rowbar",
      `<span class="muted">${label}</span>` +
      `<span class="bar"><i style="width:${Math.max(2, (n / total) * 100)}%"></i></span>` +
      `<span class="rowbar-val">${n}</span>`);
    c.appendChild(bucketRow("Youth ≤21", bk.youth));
    c.appendChild(bucketRow("Prime 22–26", bk.prime));
    c.appendChild(bucketRow("Veteran 27+", bk.veteran));
    rail.appendChild(c);
  }

  // Scouting book: coaching identity + tendencies, own club or a scouted rival.
  if (data.identity || (data.tendencies ?? []).length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Scouting book"));
    if (data.identity) c.appendChild(el("p", "", `<b>${esc(data.identity)}</b>`));
    if ((data.tendencies ?? []).length) {
      c.appendChild(el("p", "muted", data.tendencies.map(esc).join(" · ")));
    }
    rail.appendChild(c);
  }

  // Locker room: duos/feuds (linked via chemistry_pair_ids) + comms cohesion.
  {
    const cpi = data.chemistry_pair_ids ?? { duos: [], feuds: [] };
    const cc = data.comms_cohesion;
    if (cpi.duos.length || cpi.feuds.length || cc != null) {
      const c = el("div", "card");
      c.appendChild(el("h2", "", "Locker room"));
      if (cpi.duos.length || cpi.feuds.length) {
        for (const [a, b] of cpi.duos) {
          c.appendChild(el("div", "entity",
            `<span>🤝 ${plink(a, handleOf[a] || a)} <span class="muted">+</span> ${plink(b, handleOf[b] || b)}</span>`));
        }
        for (const [a, b] of cpi.feuds) {
          c.appendChild(el("div", "entity",
            `<span>⚡ ${plink(a, handleOf[a] || a)} <span class="muted">vs</span> ${plink(b, handleOf[b] || b)}</span>`));
        }
      } else if (data.is_user_team) {
        c.appendChild(el("p", "muted", "No standout duos or feuds."));
      }
      if (cc != null) {
        const tone = cc >= 75 ? "tone-good" : cc >= 50 ? "" : cc >= 35 ? "tone-warn" : "tone-bad";
        c.appendChild(el("p", "muted",
          `<span class="chip ${tone}" title="pairwise language overlap — pairs with no common tongue never fully gel">Comms ${Math.round(cc)}</span> ` +
          `shared languages feed chemistry.`));
      }
      rail.appendChild(c);
    }
  }

  // Map-lineups: a compact per-map summary in the rail; the full chip editor
  // rides a ws-12 band below the grid (only when a bench makes it a choice).
  if (hasBench && data.upcoming) {
    const up = data.upcoming;
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Map lineups"));
    c.appendChild(el("p", "muted",
      `vs ${up.opponent_id ? tlink(up.opponent_id, up.opponent) : esc(up.opponent)} · Bo${up.best_of}`));
    for (const m of up.maps) {
      c.appendChild(el("div", "row",
        `<span class="microlabel">${esc(m.map_id)}</span> ` +
        `<span class="chip ${m.has_override ? "tone-accent" : ""}" title="${m.has_override ? "custom five" : "uses your default five"}">${m.has_override ? "custom" : "default"}</span>`));
      c.appendChild(el("div", "muted",
        (m.dressed || []).map((id) => plink(id, handleOf[id] || id)).join(" · ")));
    }
    const edit = el("button", "btn btn-sm", "Edit ▸");
    edit.onclick = () => {
      const band = document.getElementById("es-maplineups");
      if (band) band.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    c.appendChild(edit);
    rail.appendChild(c);

    // The full editor as a ws-12 band on row 2 of the same grid (.ws-col so
    // the card takes the grid's rhythm, not its own bottom margin).
    const cell = el("div", "ws-12 ws-col");
    const mlc = mapLineupCard(data);
    mlc.id = "es-maplineups";
    cell.appendChild(mlc);
    ws.appendChild(cell);
  }
}

// Per-map "dressed five" picker for the upcoming fixture (only shown when the
// roster runs deeper than five, so there's an actual choice to make). NOTE:
// distinct from lineupCard(v, lineup) below (the weekly agent-lock table) —
// the two used to share a name, and the later declaration hoisted over this
// one, crashing the roster tab for any benched roster.
function mapLineupCard(data) {
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

function attrDetail(p) {
  const rows = Object.entries(p.attributes)
    .map(([k, val]) => `<tr><td>${k.replaceAll("_", " ")}</td><td>${bar(val)}</td><td class="num">${Math.round(val)}</td></tr>`)
    .join("");
  // Every player now carries a baseline on the whole cast — show the top
  // comfort picks, not all 13.
  const agents = p.agents.slice(0, 5).map((a) => `${a.agent_id} (${Math.round(a.mastery)})`).join(", ")
    + (p.agents.length > 5 ? `, +${p.agents.length - 5} more` : "");
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
      <p class="muted">social reach: ${fmtFollowers(p.followers)} followers · confidence ${Math.round(p.confidence ?? 50)}</p>
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
  // Roster members whose playstyle suits this pole, each a profile link. The
  // fit payload now carries the player id, so the chip routes to the overlay.
  const set = new Set(styles);
  const hits = (fit?.players ?? []).filter((p) => set.has(p.playstyle));
  if (!hits.length) return "";
  return hits.map((p) => plink(p.id, p.handle, "tac-who")).join("");
}

async function tactics(v) {
  const s = App.state;
  const sub = App.tacticsTab ?? "strategy";
  v.appendChild(screenHead("Tactics", {
    sub: `S${s.season} · W${s.week} · ${cap(String(s.phase || "").replace(/_/g, " "))}`,
    subtabs: [
      { id: "strategy", label: "Strategy" },
      { id: "gameplan", label: "Game plan" },
    ],
    active: sub,
    onPick: (id) => { App.tacticsTab = id; render(); },
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);
  const data = await api("/api/tactics");
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  if (sub === "gameplan") {
    // Main = the one-match prep; rail = this week's agent locks (match prep,
    // so they live with the plan, not the standing strategy).
    await gameplanPanel(main);
    lineupCard(rail, data.lineup);
  } else {
    tacticsStrategy(main, rail, data);
  }
}

/* -- Tactics · Strategy: the standing coaching identity ----------------------
   Main holds the execution-edge banner + dial cards; the rail holds the
   site-focus segment and the (dirty-aware) "Set strategy" save. */
function tacticsStrategy(main, rail, data) {
  const tac = data.tactics;
  const f = data.fit;
  const chem = f.chemistry;
  const fitBy = Object.fromEntries(f.dials.map((d) => [d.key, d]));
  const values = {}; // live working copy; only changed keys get POSTed
  for (const d of TACTIC_DIALS) values[d.key] = tac[d.key];
  let siteVal = tac.site_focus;
  const pending = {};
  // Loaded snapshot: the save button lights amber (.save-dirty) whenever any
  // dial or the site focus differs from what was fetched.
  const loaded = { ...values, site_focus: siteVal };
  const save = el("button", "btn btn-primary", "Set strategy");
  const paintDirty = () => {
    let dirty = siteVal !== loaded.site_focus;
    for (const d of TACTIC_DIALS) if (values[d.key] !== loaded[d.key]) dirty = true;
    save.classList.toggle("save-dirty", dirty);
  };

  const card = el("div", "card", `<h2>Coaching strategy</h2>`);
  card.appendChild(el("p", "muted",
    `The identity your squad plays with. Every dial sits neutral at <b>50</b> —
     push it off centre and the match engine rewards a roster built for that
     style and punishes one that isn't. Team chemistry is <b class="mono">${Math.round(chem)}</b>.`));

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
      paintDirty();
    };
    paint();
    dialsWrap.appendChild(block);
  }
  refreshEdge();
  card.appendChild(dialsWrap);
  main.appendChild(card);

  /* -- rail: site focus + save --------------------------------------------- */
  const siteCard = el("div", "card", `<h2>Site focus</h2>`);
  siteCard.appendChild(el("p", "muted",
    "Bias the attack toward one site. Pure macro — it steers where you hit, not who wins duels."));
  const seg = el("div", "tac-seg");
  for (const [val, label, note] of SITE_FOCUS) {
    const b = el("button", "tac-seg-btn", label);
    b.title = note;
    if (val === siteVal) b.classList.add("on");
    b.onclick = () => {
      siteVal = val;
      pending.site_focus = val;
      seg.querySelectorAll(".tac-seg-btn").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      paintDirty();
    };
    seg.appendChild(b);
  }
  siteCard.appendChild(seg);
  rail.appendChild(siteCard);

  const saveCard = el("div", "card", `<h2>Set strategy</h2>`);
  saveCard.appendChild(el("p", "muted",
    "Scout a rival to 50%+ to read their coaching identity on their roster page."));
  save.onclick = async () => {
    if (!Object.keys(pending).length) { toast("no changes"); return; }
    const r = await api("/api/actions/tactics", pending);
    toast(r.message);
    for (const k of Object.keys(pending)) delete pending[k];
    // Rebase the loaded snapshot to the just-saved state and clear the flag.
    for (const d of TACTIC_DIALS) loaded[d.key] = values[d.key];
    loaded.site_focus = siteVal;
    paintDirty();
  };
  const saveRow = el("div", "row");
  saveRow.appendChild(save);
  saveCard.appendChild(saveRow);
  rail.appendChild(saveCard);
}

// This week's committed agents — one lock per player, chosen before you know
// the map. "Auto" leaves the engine to field their best-mastery agent (the
// default). Rivals must scout you to 50%+ to read this on your roster page.
function lineupCard(v, lineup) {
  const card = el("div", "card lineup-card", `<h2>This week's lineup</h2>`);
  card.appendChild(el("p", "muted",
    `Lock the agent each player runs this week. You won't know the map when it's
     played, so it's one agent per player — pick for comfort. <b>Auto</b> fields
     their best-mastery agent. Off-role picks work but low mastery hurts duels.`));
  const t = el("table");
  t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th>Agent</th>
    <th class="num">Mastery</th></tr></thead>`;
  const tb = el("tbody");
  const pending = {}; // pid -> agent_id ("" = auto)
  for (const p of lineup.players) {
    const sel = el("select", "select lineup-sel");
    const auto = el("option", "", `Auto — ${p.auto_name}`);
    auto.value = "";
    sel.appendChild(auto);
    for (const o of p.options) {
      const opt = el("option", "", o.name);
      opt.value = o.id;
      sel.appendChild(opt);
    }
    sel.value = p.assigned ?? "";
    const mCell = el("td", "num");
    const paintM = () => {
      const id = sel.value || p.auto_id;
      const o = p.options.find((x) => x.id === id);
      mCell.textContent = o ? o.mastery : "—";
      mCell.className = "num" + (o && o.mastery < 40 ? " bad" : "");
    };
    const tr = el("tr");
    tr.appendChild(el("td", "", `<b>${plink(p.id, p.handle)}</b>`));
    tr.appendChild(el("td", "", stylePill(p)));
    const aCell = el("td");
    aCell.appendChild(sel);
    tr.appendChild(aCell);
    tr.appendChild(mCell);
    tb.appendChild(tr);
    paintM();
    sel.onchange = () => { pending[p.id] = sel.value; paintM(); };
  }
  t.appendChild(tb);
  card.appendChild(t);

  const barRow = el("div", "tac-savebar");
  const save = el("button", "btn btn-primary", "Lock agents");
  save.onclick = async () => {
    // Send the full desired map so a cleared pick reverts to auto server-side.
    const agents = {};
    for (const p of lineup.players) {
      const cur = p.id in pending ? pending[p.id] : (p.assigned ?? "");
      if (cur) agents[p.id] = cur;
    }
    const r = await api("/api/actions/lineup", { agents });
    toast(r.message);
    // Sync local state to the server's fresh view: a POST replaces the whole
    // agent map, so a later save must resend the locks this one just made.
    const byId = Object.fromEntries((r.lineup?.players ?? []).map((q) => [q.id, q]));
    for (const p of lineup.players) {
      if (byId[p.id]) p.assigned = byId[p.id].assigned;
    }
    for (const k of Object.keys(pending)) delete pending[k];
  };
  barRow.appendChild(save);
  barRow.appendChild(el("span", "muted",
    "Committed before map pick — rivals need 50%+ scouting to read it."));
  card.appendChild(barRow);
  v.appendChild(card);
}

// -- game plan: one match's prep, layered over the standing book ------------
// All numbers (prep edge, fogged opponent view, suggested target) come from
// the server — the client renders and posts choices, nothing more.
async function gameplanPanel(v) {
  const gp = await api("/api/gameplan");
  const card = el("div", "card");
  if (!gp.fixture) {
    card.innerHTML = `<h2>Game plan</h2>
      <p class="muted">No upcoming fixture — nothing to plan for this week.</p>`;
    v.appendChild(card);
    return;
  }
  const fx = gp.fixture;
  const opp = fx.opponent;
  const plan = gp.plan;
  // Stored plans can go stale under roster churn: drop starters who left
  // the roster (no chip could ever deselect a ghost) and a focus target
  // no longer among the rendered starters (the radio group would render
  // with nothing selected while silently re-saving the hidden pid).
  const ownIds = new Set(gp.own_roster.map((r) => r.player_id));
  const oppStarterIds = new Set(
    gp.opponent_roster.filter((r) => r.is_starter).map((r) => r.player_id));
  const storedTarget = plan?.focus_target ?? null;
  const state = {
    dials: {},          // key -> value, only for overridden dials
    site_focus: plan?.site_focus ?? null,
    focus_target: oppStarterIds.has(storedTarget) ? storedTarget : null,
    starters: new Set((plan?.starter_ids ?? []).filter((pid) => ownIds.has(pid))),
    team_talk: plan?.team_talk ?? null,
  };
  for (const d of TACTIC_DIALS) {
    if (plan && plan[d.key] != null) state.dials[d.key] = plan[d.key];
  }

  // Dirty tracking: the save button lights amber (.save-dirty) whenever the
  // working plan diverges from what was loaded. Declared here so every input
  // handler below can flag it; wired to its POST at the save bar.
  const saveBtn = el("button", "btn btn-primary", plan ? "Update game plan" : "Lock in game plan");
  const gpSig = () => JSON.stringify({
    dials: Object.fromEntries(TACTIC_DIALS.map((d) => [d.key, state.dials[d.key] ?? null])),
    site: state.site_focus,
    target: state.focus_target,
    starters: [...state.starters].sort(),
    talk: state.team_talk,
  });
  const loadedGpSig = gpSig();
  const paintGpDirty = () => saveBtn.classList.toggle("save-dirty", gpSig() !== loadedGpSig);

  card.innerHTML = `<h2>Game plan — vs <b>${tlink(opp.id, opp.name)}</b>
    <span class="pill">${esc(opp.tag)}</span>
    ${plan ? '<span class="pill gp-live">plan set</span>' : ""}</h2>`;
  card.appendChild(el("p", "muted",
    `${stageLabel(fx.stage)} · best of ${fx.best_of} · ${fx.maps.join(", ")}
     · their record ${opp.record || "0-0"}${opp.world_rank ? ` · world #${opp.world_rank}` : ""}.
     A plan is one match's prep — consumed when the match sims; your standing
     strategy above is untouched.`));

  // Prep meter: setting a plan brings the baseline edge; scouting raises it.
  const pct = Math.round(gp.scout_knowledge * 100);
  const prep = el("div", "gp-prep");
  prep.innerHTML = `<span class="gp-prep-lab">Prep edge</span>
    <span class="gp-prep-val mono">+${gp.prep_edge.toFixed(1)}</span>
    <span class="gp-prep-sub">duel points while a plan is set. ${opp.name} is
    ${pct}% scouted — deeper scouting raises this (max +${gp.prep_edge_max.toFixed(1)}).</span>`;
  card.appendChild(prep);

  // Matchup-aware counter read. The server owns the formula and withholds the
  // opponent-specific number behind scouting; public map-meta is always safe.
  const counter = gp.counter;
  const shownCounter = counter.opponent_revealed
    ? counter.opponent_edge : counter.meta_edge;
  const fmtCounter = (value) => value == null
    ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
  const counterTone = shownCounter == null || Math.abs(shownCounter) < 0.05
    ? "" : shownCounter > 0 ? "good" : "bad";
  const counterRead = el("div", "gp-prep");
  const source = counter.opponent_revealed
    ? `against ${opp.name}'s scouted standing identity`
    : counter.meta_team_maps > 0
      ? `against the public meta on these maps (${counter.meta_team_maps} team-maps)`
      : "public map-meta needs completed matches";
  counterRead.innerHTML = `<span class="gp-prep-lab">Counter-strat</span>
    <span class="gp-prep-val mono ${counterTone}">${fmtCounter(shownCounter)}</span>
    <span class="gp-prep-sub">duel points ${source}. Opposing their dial lean helps;
    matching it reinforces their strength. Range ±${counter.max_edge.toFixed(1)}.
    ${counter.opponent_revealed ? "" : `Scout ${opp.name} to 50% for their private read.`}</span>`;
  card.appendChild(counterRead);

  // Focus target: hunt one opponent — an edge on him, a small tax elsewhere.
  const tgtWrap = el("div", "gp-block");
  tgtWrap.appendChild(el("div", "tac-head",
    `<span class="tac-name">Focus target</span>
     <span class="tac-desc mid">edge vs the hunted man, a small tax vs everyone else</span>`));
  const tgtTable = el("table");
  tgtTable.innerHTML = `<thead><tr><th></th><th>Player</th><th>Role</th>
    <th>Style</th><th class="num">CA</th><th class="num">Form</th><th></th></tr></thead>`;
  const tb = el("tbody");
  const noneRow = el("tr", "", `<td><input type="radio" name="gp-tgt"
    ${state.focus_target == null ? "checked" : ""}></td>
    <td colspan="6" class="muted">No target — play our own game</td>`);
  noneRow.querySelector("input").onchange = () => { state.focus_target = null; paintGpDirty(); };
  tb.appendChild(noneRow);
  for (const r of gp.opponent_roster.filter((r) => r.is_starter)) {
    const fogp = r.fogged ? "~" : "";
    const sug = r.player_id === gp.suggested_target
      ? ' <span class="pill gp-sug">scout&#39;s pick</span>' : "";
    const tr = el("tr", "", `
      <td><input type="radio" name="gp-tgt" ${state.focus_target === r.player_id ? "checked" : ""}></td>
      <td><b>${plink(r.player_id, r.handle)}</b>${sug}</td>
      <td>${esc(r.role)}</td><td>${esc(r.playstyle)}</td>
      <td class="num mono">${fogp}${Math.round(r.overall)}</td>
      <td class="num mono">${fogp}${Math.round(r.form)}</td><td></td>`);
    tr.querySelector("input").onchange = () => { state.focus_target = r.player_id; paintGpDirty(); };
    tb.appendChild(tr);
  }
  tgtTable.appendChild(tb);
  tgtWrap.appendChild(tgtTable);
  if (gp.suggested_target == null && pct < 35) {
    tgtWrap.appendChild(el("p", "muted gp-note",
      "Scout them past 35% and your analyst will name the weak link."));
  }
  card.appendChild(tgtWrap);

  // Per-match dial overrides: check a dial to bend it for this match only.
  const ovWrap = el("div", "gp-block");
  ovWrap.appendChild(el("div", "tac-head",
    `<span class="tac-name">Dial overrides</span>
     <span class="tac-desc mid">unchecked dials play the standing book</span>`));
  for (const d of TACTIC_DIALS) {
    const standing = gp.tactics[d.key];
    const row = el("div", "gp-dial");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = d.key in state.dials;
    const lab = el("span", "gp-dial-lab", d.label);
    const slider = el("input");
    slider.type = "range"; slider.min = 0; slider.max = 100; slider.step = 1;
    slider.value = state.dials[d.key] ?? standing;
    slider.disabled = !cb.checked;
    const val = el("span", "gp-dial-val mono",
      `${Math.round(slider.value)}${cb.checked ? "" : " (book)"}`);
    // Ghost reference: while a dial is overridden, show the standing "book: N"
    // it's deviating from (the payload carries both).
    const book = el("span", "microlabel", `book ${Math.round(standing)}`);
    const paint = () => {
      val.textContent = `${Math.round(slider.value)}${cb.checked ? "" : " (book)"}`;
      book.hidden = !cb.checked;
      row.classList.toggle("on", cb.checked);
    };
    cb.onchange = () => {
      slider.disabled = !cb.checked;
      if (cb.checked) {
        state.dials[d.key] = parseFloat(slider.value);
      } else {
        delete state.dials[d.key];
        slider.value = standing; // "(book)" must show the book's number
      }
      paint();
      paintGpDirty();
    };
    slider.oninput = () => { state.dials[d.key] = parseFloat(slider.value); paint(); paintGpDirty(); };
    row.appendChild(cb); row.appendChild(lab); row.appendChild(slider); row.appendChild(val); row.appendChild(book);
    ovWrap.appendChild(row);
    paint();
  }
  // Site focus override rides the same block.
  const siteRow = el("div", "gp-dial gp-site");
  siteRow.appendChild(el("span", "gp-dial-lab", "Site focus"));
  const seg = el("div", "tac-seg");
  const siteOpts = [["", "Book"], ...SITE_FOCUS.map((s) => [s[0], s[1]])];
  for (const [valKey, label] of siteOpts) {
    const b = el("button", "tac-seg-btn", label);
    const isOn = (state.site_focus ?? "") === valKey;
    if (isOn) b.classList.add("on");
    b.onclick = () => {
      state.site_focus = valKey === "" ? null : valKey;
      seg.querySelectorAll(".tac-seg-btn").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      paintGpDirty();
    };
    seg.appendChild(b);
  }
  siteRow.appendChild(seg);
  ovWrap.appendChild(siteRow);
  card.appendChild(ovWrap);

  // One-match lineup (only when there is a bench to rotate from).
  if (gp.own_roster.length > 5) {
    const luWrap = el("div", "gp-block");
    luWrap.appendChild(el("div", "tac-head",
      `<span class="tac-name">One-match lineup</span>
       <span class="tac-desc mid">pick exactly five, or leave the standing five</span>`));
    const count = el("span", "gp-lu-count mono");
    const chips = el("div", "gp-lineup");
    const paintCount = () => {
      const n = state.starters.size;
      count.textContent = n === 0 ? "standing five" : `${n}/5 picked`;
      count.className = `gp-lu-count mono ${n === 0 || n === 5 ? "" : "bad"}`;
    };
    for (const r of gp.own_roster) {
      const chip = el("button", "gp-chip", `
        <b>${r.handle}</b> <span class="muted">${r.playstyle}</span>
        <span class="mono">${Math.round(r.overall)}</span>
        <span class="mono ${r.stamina < 30 ? "bad" : ""}">${Math.round(r.stamina)} sta</span>
        ${r.is_starter ? '<span class="pill">starter</span>' : ""}`);
      const paint = () => chip.classList.toggle("on", state.starters.has(r.player_id));
      chip.onclick = () => {
        if (state.starters.has(r.player_id)) state.starters.delete(r.player_id);
        else state.starters.add(r.player_id);
        paint(); paintCount(); paintGpDirty();
      };
      paint();
      chips.appendChild(chip);
    }
    luWrap.appendChild(chips);
    const luFoot = el("div", "gp-lu-foot");
    const clearLu = el("button", "btn", "Use standing five");
    clearLu.onclick = () => {
      state.starters.clear();
      chips.querySelectorAll(".gp-chip").forEach((c) => c.classList.remove("on"));
      paintCount(); paintGpDirty();
    };
    luFoot.appendChild(clearLu);
    luFoot.appendChild(count);
    paintCount();
    luWrap.appendChild(luFoot);
    for (const h of gp.rotation_hints) {
      luWrap.appendChild(el("p", "muted gp-note", h));
    }
    card.appendChild(luWrap);
  }

  // Team talk — a pre-match motivational choice (bounded confidence nudge).
  const talkWrap = el("div", "gp-talk");
  talkWrap.appendChild(el("span", "tac-fit-lab", "Team talk"));
  const TALKS = [
    ["", "None — let them focus"],
    ["fire_up", "Fire them up (lift, best for ambitious players)"],
    ["reassure", "Reassure (steadies fragile nerves)"],
    ["focus", "Refocus (settle tilt and hubris alike)"],
  ];
  const talkRow = el("div", "row gp-talk-row");
  for (const [val, label] of TALKS) {
    const b = el("button", "btn btn-sm" + ((state.team_talk || "") === val ? " active" : ""), label);
    b.onclick = () => {
      state.team_talk = val || null;
      talkRow.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      paintGpDirty();
    };
    talkRow.appendChild(b);
  }
  talkWrap.appendChild(talkRow);
  card.appendChild(talkWrap);

  // Save / clear.
  const barRow2 = el("div", "tac-savebar");
  saveBtn.onclick = async () => {
    const n = state.starters.size;
    if (n !== 0 && n !== 5) { toast("pick exactly five, or none"); return; }
    const body = {
      site_focus: state.site_focus,
      focus_target: state.focus_target,
      starter_ids: [...state.starters],
      team_talk: state.team_talk,
    };
    for (const d of TACTIC_DIALS) body[d.key] = state.dials[d.key] ?? null;
    const r = await api("/api/actions/gameplan", body);
    toast(r.message);
    render();
  };
  barRow2.appendChild(saveBtn);
  if (plan) {
    const clearBtn = el("button", "btn", "Scrap the plan");
    clearBtn.onclick = async () => {
      const r = await api("/api/actions/gameplan", { clear: true });
      toast(r.message);
      render();
    };
    barRow2.appendChild(clearBtn);
  }
  card.appendChild(barRow2);
  v.appendChild(card);
}

// Last-5 W/L chips for the league tables (oldest first, most recent
// rightmost). Each chip tips to its scoreline — the sim's own record.
const formSquares = (form) =>
  (form || [])
    .map(
      (g) =>
        `<span class="form-sq ${g.result === "W" ? "w" : "l"}" title="${g.result} ${g.score} vs ${g.opponent} (W${g.week})">${g.result}</span>`
    )
    .join("") || '<span class="muted">—</span>';

const STAGE_LABELS = {
  regular: "league",
  semi: "semifinal",
  final: "regional final",
  masters_qf: "Masters QF",
  masters_sf: "Masters semi",
  masters_final: "MASTERS FINAL",
  champ_qf: "Champions QF",
  champ_sf: "Champions semi",
  champ_final: "CHAMPIONS FINAL",
};
const stageLabel = (s) => STAGE_LABELS[s] ?? s;

/* -- season: league · fixtures · playoffs · records --------------------------
   One workspace replacing the old Standings + Schedule tabs (the old tab ids
   alias here via TAB_ALIASES). Sub-tab state lives on App.seasonTab; each
   sub-tab fetches exactly the endpoints its content needs — between them the
   four cover every call the two old screens made. */

const SEASON_TABS = [
  { id: "league", label: "League" },
  { id: "fixtures", label: "Fixtures" },
  { id: "playoffs", label: "Playoffs" },
  { id: "records", label: "Records" },
];

// team id -> region name, from the standings payload (both tiers). Fixtures
// carry no region field, so team regions are the payload-true source — this
// also works for roster-pack worlds whose fixture ids embed no region code.
function teamRegionMap(table) {
  const of = {};
  for (const reg of table?.regions ?? []) {
    for (const r of reg.rows ?? []) of[r.id] = reg.region;
    for (const r of reg.tier2_rows ?? []) of[r.id] = reg.region;
  }
  return of;
}

async function season(v) {
  const s = App.state;
  const sub = App.seasonTab ?? "league";
  v.appendChild(screenHead("Season", {
    sub: `S${s.season} · W${s.week} · ${cap(String(s.phase || "").replace(/_/g, " "))}`,
    subtabs: SEASON_TABS,
    active: sub,
    onPick: (id) => { App.seasonTab = id; render(); },
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);
  if (sub === "fixtures") {
    const [sched, table] = await Promise.all([
      api("/api/schedule"),
      api("/api/standings").catch(() => null),
    ]);
    seasonFixtures(ws, sched, table);
  } else if (sub === "playoffs") {
    const [sched, table] = await Promise.all([
      api("/api/schedule"),
      api("/api/standings").catch(() => null),
    ]);
    seasonPlayoffs(ws, sched, table);
  } else if (sub === "records") {
    const records = await api("/api/records").catch(() => null);
    seasonRecords(ws, records);
  } else {
    const [table, league, power] = await Promise.all([
      api("/api/standings"),
      api("/api/league").catch(() => null),
      api("/api/power").catch(() => null),
    ]);
    seasonLeague(ws, table, league, power);
  }
}

/* -- Season · League: the tables + this-season context ---------------------- */

function seasonLeague(ws, data, league, power) {
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  // Regional tables, user's region first (the server orders regions that
  // way). Ranked tables opt out of the th-sort delegate — the baked "#"
  // column must stay aligned with the standings order.
  const mkTable = (rows, cut) => {
    const t = el("table");
    t.dataset.nosort = "1";
    t.innerHTML = `<thead><tr><th>#</th><th>Team</th><th class="num">W</th><th class="num">L</th>
      <th class="num">RW</th><th class="num">RL</th><th class="num">+/-</th><th class="num">Rep</th><th>Form</th></tr></thead>`;
    const tb = el("tbody");
    rows.forEach((r, i) => {
      const outTag = r.eliminated
        ? ' <span class="pill elim-pill" title="Cannot reach the top-4 playoff cut">OUT</span>'
        : "";
      const dynTag = r.dynasty
        ? ` <span class="pill dynasty-pill" title="Dynasty index — recent-title dominance">${esc(r.dynasty)}</span>`
        : "";
      const cls = [r.id === App.state.user_team.id ? "me" : "", r.eliminated ? "elim" : ""]
        .filter(Boolean)
        .join(" ");
      tb.appendChild(el("tr", cls, `
        <td>${i + 1}</td><td><img class="logo" src="${r.logo}" alt=""><b>${tlink(r.id, r.name)}</b> <span class="pill">${esc(r.tag)}</span>${dynTag}${outTag}</td>
        <td class="num">${r.wins}</td><td class="num">${r.losses}</td>
        <td class="num">${r.rounds_won}</td><td class="num">${r.rounds_lost}</td>
        <td class="num">${r.diff > 0 ? "+" : ""}${r.diff}</td>
        <td class="num">${r.reputation}</td>
        <td class="form-cell">${formSquares(r.recent_form)}</td>`));
      // The top-4 playoff cutoff line inside the tier-1 table during the
      // regular season (server sends the cut + phase; rows are ranked).
      if (cut && i === cut - 1 && i < rows.length - 1) {
        tb.appendChild(el("tr", "playoff-cut", `<td colspan="9">Playoff cutoff</td>`));
      }
    });
    t.appendChild(tb);
    return t;
  };

  for (const lg of data.regions) {
    const card = el("div", "card");
    card.innerHTML = `<h2>${esc(lg.region.toUpperCase())} league${lg.is_user ? " — your region" : ""}</h2>`;
    const cut = data.in_regular_season ? data.playoff_cut : 0;
    card.appendChild(mkTable(lg.rows, cut));
    // Challengers underneath: the tier-2 development circuit.
    if ((lg.tier2_rows ?? []).length) {
      const h = el("h2", "", `${esc(lg.region.toUpperCase())} Challengers <span class="muted" style="font-weight:400">— the tier-2 development circuit</span>`);
      h.style.marginTop = "14px";
      card.appendChild(h);
      card.appendChild(mkTable(lg.tier2_rows, 0));
    }
    main.appendChild(card);
  }

  /* rail: this-season context — TotW, projection, power, H2H, results. */

  // Team of the Week: the best five of the latest completed match week.
  const totw = league?.team_of_week;
  if (totw && totw.players?.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", `Team of the Week <span class="muted" style="font-weight:400">— week ${totw.week}</span>`));
    const list = el("div", "es-totw");
    for (const p of totw.players) {
      list.appendChild(el("div", "es-totw-row",
        `<span class="pill">${esc(p.role)}</span>` +
        plink(p.id, p.handle) +
        `<span class="muted es-totw-team">${p.team_id ? tlink(p.team_id, p.team) : esc(p.team)}</span>` +
        `<b class="mono">${p.rating.toFixed(2)}</b>`));
    }
    c.appendChild(list);
    rail.appendChild(c);
  }

  // Form-hold projection (regular season only; playoffs live on their tab).
  if (league?.in_regular_season && (league?.projection || []).length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", `Projected finish <span class="muted" style="font-weight:400">— if current form holds</span>`));
    const scroll = el("div", "card-scroll");
    const t = el("table", "es-proj");
    t.dataset.nosort = "1";
    t.innerHTML = `<thead><tr><th>#</th><th>Team</th><th class="num">W</th><th class="num">Rem</th><th class="num">Proj W</th></tr></thead>`;
    const tb = el("tbody");
    for (const r of league.projection) {
      tb.appendChild(el("tr", "",
        `<td class="mono">${r.proj_pos}</td>` +
        `<td>${tlink(r.team_id, r.name)}</td>` +
        `<td class="num mono">${r.wins}</td>` +
        `<td class="num mono muted">${r.remaining}</td>` +
        `<td class="num mono"><b>${r.proj_wins}</b></td>`));
    }
    t.appendChild(tb);
    scroll.appendChild(t);
    c.appendChild(scroll);
    rail.appendChild(c);
  }

  // Global pundit power ranking (across regions), with movement vs world rank.
  const pr = power?.rankings || [];
  if (pr.length) {
    const pc = el("div", "card");
    pc.appendChild(el("h2", "", `Power rankings <span class="muted" style="font-weight:400">— global form book</span>`));
    const list = el("div", "es-power");
    for (const r of pr.slice(0, 10)) {
      const mv = r.movement;
      const arrow = mv == null ? "" : mv > 0
        ? `<span class="trend-up">▲${mv}</span>` : mv < 0
        ? `<span class="trend-down">▼${-mv}</span>` : '<span class="muted">–</span>';
      list.appendChild(el("div", "es-power-row",
        `<span class="es-power-rank mono">${r.rank}</span>` +
        tlink(r.team_id, r.name) +
        `<span class="muted">${esc((r.region || "").toUpperCase())}</span>` +
        `<span class="es-power-mv">${arrow}</span>`));
    }
    pc.appendChild(list);
    rail.appendChild(pc);
  }

  // Head-to-head matrix: each team's series record vs every other this season.
  const mx = league?.h2h_matrix;
  if (mx && mx.teams.length > 1) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", `Head-to-head <span class="muted" style="font-weight:400">— series record</span>`));
    const scroll = el("div", "card-scroll");
    const wrap = el("div", "es-h2hm-wrap");
    const t = el("table", "es-h2hm");
    const head = mx.teams.map((tm) => `<th title="${esc(tm.name)}">${esc(tm.name.slice(0, 3).toUpperCase())}</th>`).join("");
    t.innerHTML = `<thead><tr><th></th>${head}</tr></thead>`;
    const tb = el("tbody");
    mx.rows.forEach((row, i) => {
      const cells = row.cells.map((cell) => {
        if (cell == null) return '<td class="es-h2hm-self">—</td>';
        if (!cell.played) return '<td class="muted">·</td>';
        const cls = cell.w > cell.l ? "good" : cell.w < cell.l ? "bad" : "";
        return `<td class="${cls}">${cell.w}-${cell.l}</td>`;
      }).join("");
      tb.appendChild(el("tr", "",
        `<th class="es-h2hm-row">${tlink(row.team_id, mx.teams[i].name.slice(0, 3).toUpperCase())}</th>${cells}`));
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    scroll.appendChild(wrap);
    c.appendChild(scroll);
    rail.appendChild(c);
  }

  // Results archive: recent played fixtures in the region, newest first.
  const results = league?.results || [];
  if (results.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Recent results"));
    const scroll = el("div", "card-scroll");
    const list = el("div", "es-results");
    for (const r of results) {
      const aWon = r.winner_id === r.team_a_id;
      list.appendChild(el("div", "es-result-line",
        `<span class="muted es-result-wk">W${r.week}</span>` +
        `<span class="es-result-t ${aWon ? "good" : ""}">${tlink(r.team_a_id, r.team_a)}</span>` +
        `<b class="mono es-result-score">${r.score_a}-${r.score_b}</b>` +
        `<span class="es-result-t ${!aWon ? "good" : ""}" style="text-align:right">${tlink(r.team_b_id, r.team_b)}</span>`));
    }
    scroll.appendChild(list);
    c.appendChild(scroll);
    rail.appendChild(c);
  }
}

/* -- Season · Fixtures: the week-by-week fixture browser -------------------- */

function seasonFixtures(ws, sched, table) {
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  const myId = App.state.user_team.id;
  const regionOf = teamRegionMap(table);
  const filter = App.seasonFixFilter ?? "mine";
  const cw = sched.current_week;

  // One fixture line: stage pill · teams · score · per-map chips (the Replay
  // button renders ONLY where the payload says a replay survives — replays
  // are kept for the latest week only, so old rows get plain score chips).
  const appendFixture = (box, f) => {
    const mine = f.team_a === myId || f.team_b === myId;
    let score = "";
    if (f.played) {
      score = f.best_of > 1
        ? `<b class="mono">${f.map_score[0]}–${f.map_score[1]}</b>`
        : f.results.length
          ? `<b class="mono">${f.results[0].score_a}–${f.results[0].score_b}</b>`
          : "";
    }
    const line = el("div", "row", `
      <span class="pill">${esc(stageLabel(f.stage))}</span>
      <span style="min-width:340px">${mine ? "<b>" : ""}${tlink(f.team_a, f.team_a_name)} vs ${tlink(f.team_b, f.team_b_name)}${mine ? "</b>" : ""}</span>
      ${score}`);
    for (let i = 0; i < f.results.length; i++) {
      const r = f.results[i];
      if (r.has_replay) {
        const b = el("button", "btn btn-sm",
          `${mapThumb(r.map_id, "sm")}${esc(r.map_id)} ${r.score_a}–${r.score_b} ▶`);
        b.title = "watch replay";
        b.onclick = () => openReplay(f.id, i);
        line.appendChild(b);
      } else {
        line.appendChild(el("span", "pill",
          `${mapThumb(r.map_id, "sm")}${esc(r.map_id)} ${r.score_a}–${r.score_b}`));
      }
    }
    // Player of the Match — the series' standout box-score line (server
    // derives it; plink opens the profile overlay).
    if (f.played && f.potm) {
      const p = f.potm;
      line.appendChild(el("span", "potm-chip",
        `<span class="potm-star">★</span> POTM ` +
        `<b>${plink(p.player_id, p.handle)}</b> ` +
        `<span class="muted">${p.rating.toFixed(2)} · ${p.kills}K</span>`));
    }
    box.appendChild(line);
    if ((f.veto ?? []).length) {
      const vetoRow = el("div", "veto-row");
      vetoRow.appendChild(el("span", "muted", "veto:"));
      for (const entry of f.veto) {
        const mapId = entry.trim().split(" ").pop();
        vetoRow.appendChild(el("span", "veto-chip", `${mapThumb(mapId, "sm")}${esc(entry)}`));
      }
      box.appendChild(vetoRow);
    }
  };

  // Filter chips: My matches / All / one per region in the league. Regions
  // come from the standings payload's team->region map, not fixture ids.
  const userRegion = regionOf[myId] || App.state.user_team.region || "";
  const regions = [...new Set(
    sched.fixtures.flatMap((f) => [regionOf[f.team_a], regionOf[f.team_b]]).filter(Boolean))];
  regions.sort((a, b) => (a === userRegion ? -1 : b === userRegion ? 1 : a < b ? -1 : 1));
  const filterCard = el("div", "card");
  const chips = el("div", "row");
  const mkChip = (id, label) => {
    const b = el("button", "btn btn-sm" + (filter === id ? " active" : ""), esc(label));
    b.onclick = () => { App.seasonFixFilter = id; render(); };
    chips.appendChild(b);
  };
  mkChip("mine", "My matches");
  mkChip("all", "All");
  for (const r of regions) mkChip("r:" + r, cap(r));
  filterCard.appendChild(chips);
  main.appendChild(filterCard);

  const matches = (f) =>
    filter === "all" ? true
      : filter === "mine" ? f.team_a === myId || f.team_b === myId
      : regionOf[f.team_a] === filter.slice(2) || regionOf[f.team_b] === filter.slice(2);
  const shown = sched.fixtures.filter(matches);

  const byWeek = new Map();
  for (const f of shown) {
    if (!byWeek.has(f.week)) byWeek.set(f.week, []);
    byWeek.get(f.week).push(f);
  }
  const weeks = [...byWeek.keys()].sort((a, b) => a - b);
  const upcoming = weeks.filter((w) => w >= cw); // current week first, ascending
  const past = weeks.filter((w) => w < cw).reverse(); // newest played first

  if (!weeks.length) {
    main.appendChild(el("div", "card", `<p class="muted">No fixtures match this filter.</p>`));
  }
  for (const w of upcoming) {
    const card = el("div", "card");
    card.innerHTML = `<h2>Week ${w}${w === cw ? " — this week" : ""}</h2>`;
    for (const f of byWeek.get(w)) appendFixture(card, f);
    main.appendChild(card);
  }
  if (past.length) {
    const wrap = el("details", "card");
    const sum = el("summary");
    sum.appendChild(el("h2", "", `Played weeks <span class="muted" style="font-weight:400">— ${past.length} week${past.length > 1 ? "s" : ""}</span>`));
    wrap.appendChild(sum);
    past.forEach((w, i) => {
      const d = el("details");
      d.open = i === 0; // latest played week open
      d.appendChild(el("summary", "", `<b>Week ${w}</b> <span class="muted">· ${byWeek.get(w).length} match${byWeek.get(w).length > 1 ? "es" : ""}</span>`));
      for (const f of byWeek.get(w)) appendFixture(d, f);
      wrap.appendChild(d);
    });
    main.appendChild(wrap);
  }

  /* rail: your next fixture + this week across the league. */
  const tw = el("div", "card");
  tw.appendChild(el("h2", "", "This week"));
  const fix = App.state.next_fixture;
  if (fix) {
    const oppId = fix.team_a === myId ? fix.team_b : fix.team_a;
    const oppName = fix.team_a === myId ? fix.team_b_name : fix.team_a_name;
    tw.appendChild(el("div", "row",
      `<span class="pill">W${fix.week}</span> <b>vs ${tlink(oppId, oppName)}</b> ` +
      `<span class="muted">Bo${fix.best_of} · ${esc(stageLabel(fix.stage))}</span>`));
  } else {
    tw.appendChild(el("p", "muted", "No fixture scheduled for you."));
  }
  const thisWeek = sched.fixtures.filter((f) => f.week === cw);
  if (thisWeek.length) {
    tw.appendChild(el("span", "es-scout-lab muted", "Across the league"));
    const scroll = el("div", "card-scroll");
    const list = el("div", "es-results");
    for (const f of thisWeek) {
      const scoreTxt = !f.played ? "vs"
        : f.best_of > 1 ? `${f.map_score[0]}–${f.map_score[1]}`
        : f.results.length ? `${f.results[0].score_a}–${f.results[0].score_b}` : "—";
      const aWon = f.played && f.winner_id === f.team_a;
      const bWon = f.played && f.winner_id === f.team_b;
      list.appendChild(el("div", "es-result-line",
        `<span class="muted es-result-wk">${esc(stageLabel(f.stage)).slice(0, 6)}</span>` +
        `<span class="es-result-t ${aWon ? "good" : ""}">${tlink(f.team_a, f.team_a_name)}</span>` +
        `<b class="mono es-result-score">${scoreTxt}</b>` +
        `<span class="es-result-t ${bWon ? "good" : ""}" style="text-align:right">${tlink(f.team_b, f.team_b_name)}</span>`));
    }
    scroll.appendChild(list);
    tw.appendChild(scroll);
  }
  rail.appendChild(tw);
}

/* -- Season · Playoffs: every bracket through ONE renderer ------------------- */

// The one bracket renderer. rounds = [{label, matches: [m|null, ...]}] where
// m = {team_a_id, team_a, score_a, team_b_id, team_b, score_b, played,
// winner_id} and null renders a TBD slot.
function esBracket(rounds) {
  const cols = el("div", "es-bracket");
  for (const round of rounds) {
    const col = el("div", "es-bracket-col");
    col.appendChild(el("span", "es-scout-lab muted", esc(round.label)));
    for (const m of round.matches) {
      if (!m) { col.appendChild(el("div", "es-bracket-m muted", "TBD")); continue; }
      const aWon = m.played && m.winner_id === m.team_a_id;
      const bWon = m.played && m.winner_id === m.team_b_id;
      col.appendChild(el("div", "es-bracket-m",
        `<div class="${aWon ? "bw-win" : m.played ? "bw-out" : ""}">${tlink(m.team_a_id, m.team_a)} <b class="mono">${m.score_a ?? ""}</b></div>` +
        `<div class="${bWon ? "bw-win" : m.played ? "bw-out" : ""}">${tlink(m.team_b_id, m.team_b)} <b class="mono">${m.score_b ?? ""}</b></div>`));
    }
    cols.appendChild(col);
  }
  return cols;
}

// Adapt a schedule fixture into the bracket-match shape above.
const bracketMatch = (f) => f && {
  team_a_id: f.team_a, team_a: f.team_a_name,
  team_b_id: f.team_b, team_b: f.team_b_name,
  score_a: f.played ? f.map_score[0] : "",
  score_b: f.played ? f.map_score[1] : "",
  played: f.played, winner_id: f.winner_id,
};

function seasonPlayoffs(ws, sched, table) {
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  const myId = App.state.user_team.id;
  const regionOf = teamRegionMap(table);
  const stageF = (st) => sched.fixtures.filter((f) => f.stage === st);
  const pad = (arr, n) => (arr.length ? arr : Array(n).fill(null));
  const bracketCardEl = (title, rounds) => {
    const c = el("div", "card");
    c.appendChild(el("h2", "", title));
    c.appendChild(esBracket(rounds));
    return c;
  };

  // Regional playoffs, user's region first (regional playoff fixtures pair
  // teams of one region, so team_a's region names the bracket).
  const semis = stageF("semi");
  const finals = stageF("final");
  const userRegion = regionOf[myId] || App.state.user_team.region || "";
  const regions = [...new Set([...semis, ...finals].map((f) => regionOf[f.team_a]).filter(Boolean))];
  regions.sort((a, b) => (a === userRegion ? -1 : b === userRegion ? 1 : a < b ? -1 : 1));
  for (const r of regions) {
    const rs = semis.filter((f) => regionOf[f.team_a] === r);
    const rf = finals.filter((f) => regionOf[f.team_a] === r);
    main.appendChild(bracketCardEl(`${esc(cap(r))} playoffs`, [
      { label: "Semifinals", matches: pad(rs.map(bracketMatch), 2) },
      { label: "Final", matches: pad(rf.map(bracketMatch), 1) },
    ]));
  }

  // Masters — the mid-season international (QF -> SF -> Final).
  const mqf = stageF("masters_qf");
  if (mqf.length) {
    main.appendChild(bracketCardEl("Masters — world championship", [
      { label: "Quarterfinals", matches: mqf.map(bracketMatch) },
      { label: "Semifinals", matches: pad(stageF("masters_sf").map(bracketMatch), 2) },
      { label: "Final", matches: pad(stageF("masters_final").map(bracketMatch), 1) },
    ]));
  }

  // Champions — the season finale (QF -> SF -> Final).
  const cqf = stageF("champ_qf");
  if (cqf.length) {
    main.appendChild(bracketCardEl("Champions — season finale", [
      { label: "Quarterfinals", matches: cqf.map(bracketMatch) },
      { label: "Semifinals", matches: pad(stageF("champ_sf").map(bracketMatch), 2) },
      { label: "Final", matches: pad(stageF("champ_final").map(bracketMatch), 1) },
    ]));
  }

  // Pre-playoffs: no bracket fixtures exist yet — say when they will.
  if (!semis.length && !mqf.length && !cqf.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Playoffs"));
    const regWeeks = sched.fixtures.filter((f) => f.stage === "regular").map((f) => f.week);
    const lastReg = regWeeks.length ? Math.max(...regWeeks) : 0;
    const cut = table?.playoff_cut;
    c.appendChild(el("p", "muted", lastReg
      ? `Playoffs lock at W${lastReg}${cut ? ` — the top ${cut} in each region advance` : ""}. The projected finish on the League tab shows who's in the hunt.`
      : "Playoffs begin after the regular season."));
    main.appendChild(c);
  }

  // Champions history — every crowned season, newest first.
  const champs = App.state.champions ?? [];
  const hc = el("div", "card");
  hc.appendChild(el("h2", "", "Champions history"));
  if (champs.length) {
    const scroll = el("div", "card-scroll");
    for (const c of [...champs].reverse()) {
      scroll.appendChild(el("div", "newsline",
        `<span class="pill">S${c.season}</span> <b>${tlink(c.team_id, c.team_name)}</b>`));
    }
    hc.appendChild(scroll);
  } else {
    hc.appendChild(el("p", "muted", "No champion crowned yet."));
  }
  rail.appendChild(hc);
}

/* -- Season · Records: the all-time book -------------------------------------- */

function seasonRecords(ws, records) {
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  const rc = el("div", "card es-records");
  rc.appendChild(el("h2", "", "Record book"));
  if (records?.records?.length) {
    const grid = el("div", "es-rec-grid");
    for (const r of records.records) {
      const who = r.team_id ? tlink(r.team_id, r.name) : plink(r.player_id, r.handle);
      grid.appendChild(el("div", "es-rec",
        `<div class="es-rec-lab muted">${esc(r.label)}</div>` +
        `<div class="es-rec-val">${who} <b class="mono">${r.count}</b></div>`));
    }
    rc.appendChild(grid);
  } else {
    rc.appendChild(el("p", "muted", "No records yet — history is written one season at a time."));
  }
  main.appendChild(rc);

  if (records?.dynasties?.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Dynasties"));
    const row = el("div", "es-career-tags");
    for (const d of records.dynasties) {
      row.appendChild(el("span", "pill dynasty-pill",
        `${tlink(d.team_id, d.name)} · ${esc(d.label || "Rising")}`));
    }
    c.appendChild(row);
    rail.appendChild(c);
  }

  if (records?.parity && records.parity.titles > 0) {
    const p = records.parity;
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Parity"));
    c.appendChild(el("div", "muted es-parity",
      `${p.distinct_champions} distinct champion${p.distinct_champions !== 1 ? "s" : ""} ` +
      `across ${p.titles} title${p.titles !== 1 ? "s" : ""} · ` +
      `top team's share ${Math.round(p.top_share * 100)}%`));
    rail.appendChild(c);
  }
}

// Segmented [Players | Staff] shared by both market desks; each desk builds
// its own screen-head so the head can carry desk-specific right-side extras
// (the players desk adds a signing-headroom chip).
const MARKET_TABS = [
  { id: "players", label: "Players" },
  { id: "staff", label: "Staff" },
];

async function market(v) {
  // Two desks: players (free agents + transfers) and backroom staff. Thin
  // dispatcher — the sub-screen owns the head + workspace.
  const sub = App.marketTab ?? "players";
  if (sub === "staff") return marketStaff(v);
  return marketPlayers(v);
}

async function marketStaff(v) {
  const data = await api("/api/staff");

  v.appendChild(screenHead("Market", {
    subtabs: MARKET_TABS,
    active: "staff",
    onPick: (id) => { App.marketTab = id; render(); },
  }));

  const ws = el("div", "ws");
  v.appendChild(ws);
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  /* -- main ws-8: the free-agent staff pool, filtered by role -------------- */
  const poolCard = el("div", "card");
  poolCard.appendChild(el("h2", "",
    `Staff market <span class="muted" style="font-weight:400">— ${data.pool.length} free agents</span>`));
  poolCard.appendChild(el("p", "muted",
    `One shared pool — in a shared world, rival managers hire from the same market. ` +
    `Hiring replaces your current ${data.roles.map((r) => humanize(r)).join(" / ")} in that role (they return ` +
    `to the pool). Click a name for the full profile.`));

  const rolePlural = {
    coach: "Coaches", analyst: "Analysts", physio: "Physios",
    psychologist: "Psychologists", performance_coach: "Performance coaches",
  };
  // Role filter chips (client-only): "All" plus one per role. Repaints the
  // tables area in place — no re-fetch, tables keep their sortable headers.
  let activeRole = "all";
  const chipRow = el("div", "seg");
  const chips = [];
  const mkChip = (id, label) => {
    const b = el("button", "seg-btn" + (activeRole === id ? " on" : ""), label);
    b.onclick = () => { activeRole = id; paint(); };
    chips.push([id, b]);
    chipRow.appendChild(b);
  };
  mkChip("all", "All");
  for (const role of data.roles) mkChip(role, rolePlural[role] ?? cap(role));
  poolCard.appendChild(chipRow);

  const tablesBox = el("div", "staff-tables");
  const paint = () => {
    for (const [id, b] of chips) b.classList.toggle("on", id === activeRole);
    tablesBox.innerHTML = "";
    for (const role of data.roles) {
      if (activeRole !== "all" && role !== activeRole) continue;
      const members = data.pool.filter((m) => m.role === role);
      if (!members.length) continue;
      tablesBox.appendChild(el("h2", "staff-section-title",
        `${rolePlural[role] ?? cap(role)} <span class="muted" style="font-weight:400">— ${esc(data.blurbs[role])}</span>`));
      const t = el("table");
      t.innerHTML = `<thead><tr><th>Name</th><th class="num">Age</th><th>Region</th>
        <th>Specialty</th><th>Quality</th><th class="num">Salary</th>
        <th class="num">Exp</th><th></th></tr></thead>`;
      const tb = el("tbody");
      for (const m of members) {
        const tr = el("tr", "", `
          <td><b>${slink(m.id, m.name)}</b>${
            (m.titles ?? []).length ? ` <span class="pill" title="${esc(m.titles.join(", "))}">🏆 ${m.titles.length}</span>` : ""
          }</td>
          <td class="num">${m.age}</td>
          <td>${esc(m.region || "—")}</td>
          <td title="${esc(m.specialty_blurb || "")}"><span class="pill">${esc(m.specialty || "—")}</span></td>
          <td>${bar(m.quality)}</td>
          <td class="num">${money(m.salary)}/wk</td>
          <td class="num">${m.seasons_experience}s</td>
          <td><button class="btn btn-sm">Hire</button></td>`);
        tr.querySelector("button").onclick = async (e) => {
          e.stopPropagation();
          const r = await api("/api/actions/hire_staff", { candidate_id: m.id });
          toast(r.message); refresh(); render();
        };
        tb.appendChild(tr);
      }
      t.appendChild(tb);
      const scroll = el("div", "table-scroll");
      scroll.appendChild(t);
      tablesBox.appendChild(scroll);
    }
    if (!tablesBox.childElementCount) tablesBox.appendChild(el("p", "muted", "No free agents in this role."));
  };
  paint();
  poolCard.appendChild(tablesBox);
  main.appendChild(poolCard);

  /* -- rail ws-4: current backroom + analytics-tier ladder ----------------- */
  const backroom = el("div", "card");
  backroom.appendChild(el("h2", "",
    `Your backroom <span class="muted" style="font-weight:400">— ${money(data.weekly_cost)}/wk</span>`));
  for (const role of data.roles) {
    const hired = data.hired[role];
    const block = el("div", "");
    if (hired) {
      const row = el("div", "entity",
        `<span class="pill">${humanize(role)}</span> <span class="entity-name"><b>${slink(hired.id, hired.name)}</b></span>`);
      const rel = el("button", "btn btn-sm", "Release");
      rel.style.marginLeft = "auto";
      rel.onclick = async () => {
        const r = await api("/api/actions/release_staff", { role });
        toast(r.message); render();
      };
      row.appendChild(rel);
      block.appendChild(row);
      block.appendChild(el("div", "muted",
        `q${Math.round(hired.quality)} · ${esc(hired.specialty || "—")} · ${money(hired.salary)}/wk`));
      const fx = (hired.effects || []);
      if (fx.length) {
        block.appendChild(el("div", "",
          fx.map((e) => `<span class="chip tone-good">${esc(e)}</span>`).join(" ")));
      }
    } else {
      block.appendChild(el("div", "entity",
        `<span class="pill">${humanize(role)}</span> <span class="entity-meta">vacant</span>`));
      block.appendChild(el("div", "muted", esc(data.blurbs[role])));
    }
    backroom.appendChild(block);
  }
  rail.appendChild(backroom);

  // Analytics-tier ladder: how deep the stat views go, and what unlocks next.
  const an = data.analytics || {};
  if (an.tier != null) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Analytics department"));
    c.appendChild(el("div", "rowbar",
      `<span class="muted">Tier</span>` +
      `<span class="bar"><i style="width:${Math.max(6, Math.min(100, (an.tier / 3) * 100))}%"></i></span>` +
      `<span class="rowbar-val">${an.tier}/3</span>`));
    c.appendChild(el("p", "", `<b>${esc(an.label ?? "—")}</b>`));
    c.appendChild(el("p", "muted",
      an.next_unlock ? `Next unlock: ${esc(an.next_unlock)}` : "Deepest stat views unlocked."));
    rail.appendChild(c);
  }
}

// Search any player league-wide by handle/real name; act on the result
// (Sign a free agent, open the package-offer flow on a rival).
function playerSearchCard() {
  const card = el("div", "card");
  card.innerHTML = `<h2>Find a player</h2>`;
  const row = el("div", "row", "");
  const inp = el("input", "field mono player-search-input");
  inp.placeholder = "search by handle or real name…";
  row.appendChild(inp);
  card.appendChild(row);
  const box = el("div", "");
  card.appendChild(box);
  let timer = null, seq = 0;
  const run = async () => {
    const q = inp.value.trim();
    const my = ++seq;
    if (q.length < 2) { box.innerHTML = ""; return; }
    let r;
    try { r = await api("/api/market/search?q=" + encodeURIComponent(q)); }
    catch { return; }
    if (my !== seq) return; // a newer query superseded this one
    box.innerHTML = "";
    if (!r.results.length) {
      box.appendChild(el("p", "muted", "no players match"));
      return;
    }
    const t = el("table");
    t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th class="num">Age</th>
      <th class="num">OVR</th><th>Club</th><th class="num">Price</th><th data-nosort></th></tr></thead>`;
    const tb = el("tbody");
    for (const p of r.results) {
      const price = p.is_free_agent
        ? `${money(p.asking_salary)}/wk`
        : p.buyout != null ? money(p.buyout)
          : p.transfer_ask != null ? money(p.transfer_ask) : "—";
      const club = p.is_free_agent
        ? '<span class="pill">free agent</span>'
        : `${tlink(p.team_id, p.team_name)}${p.mine ? ' <span class="pill">yours</span>' : ""}`;
      const langs = langChips(p.languages);
      const tr = el("tr", "", `
        <td><img class="portrait" src="${p.portrait}" alt=""><b>${plink(p.id, p.handle)}</b>
          ${p.real_name ? `<span class="muted"> ${esc(p.real_name)}</span>` : ""}${
            langs ? `<div class="es-langs">${langs}</div>` : ""}</td>
        <td>${stylePill(p)}</td>
        <td class="num">${p.age}</td>
        <td class="num">${p.fogged ? "~" : ""}${p.overall}</td>
        <td>${club}</td>
        <td class="num">${price}${p.seller_stance ? `<div><span class="pill">${esc(p.seller_stance)}</span></div>` : ""}${askBreakdown(p.ask_breakdown)}</td>
        <td data-act></td>`);
      const actCell = tr.querySelector("[data-act]");
      if (p.is_free_agent) {
        const b = el("button", "btn btn-sm", "Negotiate…");
        b.onclick = () => openNegotiation({ id: p.id, handle: p.handle });
        actCell.appendChild(b);
      } else if (!p.mine && p.buyout != null) {
        const b = el("button", "btn btn-sm", "Buy out");
        b.title = "trigger the buyout clause — the org can't refuse";
        b.onclick = async () => {
          if (!confirm(`Trigger ${p.handle}'s buyout clause for ${money(p.buyout)}?`)) return;
          const res = await api("/api/actions/buyout", { player_id: p.id });
          toast(res.message); refresh(); render();
        };
        actCell.appendChild(b);
      } else if (!p.mine && p.transfer_ask != null) {
        const b = el("button", "btn btn-sm", "Offer…");
        b.onclick = () => openOffer({
          id: p.id, handle: p.handle, ask: p.transfer_ask, team_name: p.team_name,
          ask_breakdown: p.ask_breakdown, seller_stance: p.seller_stance,
        });
        actCell.appendChild(b);
      }
      tb.appendChild(tr);
    }
    t.appendChild(tb);
    box.appendChild(t);
  };
  inp.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 250); };
  inp.onkeydown = (e) => { if (e.key === "Enter") { clearTimeout(timer); run(); } };
  return card;
}

async function marketPlayers(v) {
  const data = await api("/api/market");
  const head = data.signing_headroom || {};
  const filters = marketFilters();
  const freeAgents = filteredMarketPlayers(data.free_agents, filters);

  // Screen head: [Players | Staff] + an optional signing-headroom chip
  // (defensive — hidden if the payload doesn't carry finances).
  const right = [];
  if (head.balance != null) {
    const runway = head.runway_weeks == null ? "stable"
      : head.runway_weeks === 0 ? "insolvent now" : `${head.runway_weeks}w runway`;
    const tone = head.runway_weeks === 0 ? "tone-bad"
      : (head.runway_weeks != null && head.runway_weeks <= 6) ? "tone-warn" : "tone-good";
    right.push(el("span", `chip ${tone}`,
      `~${money(head.affordable_wage)}/wk free · ${runway}`));
  }
  v.appendChild(screenHead("Market", {
    subtabs: MARKET_TABS,
    active: "players",
    onPick: (id) => { App.marketTab = id; render(); },
    right,
  }));

  const ws = el("div", "ws");
  v.appendChild(ws);
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  /* -- main ws-8: search card, then the free-agent table (the primary object) */
  main.appendChild(playerSearchCard());

  const card = el("div", "card");
  const filterActive = Object.values(filters).some((value) => value !== "");
  const count = filterActive ? `${freeAgents.length} of ${data.free_agents.length}` : data.free_agents.length;
  card.innerHTML = `<h2>Free agents <span class="muted" style="font-weight:400">— ${count}</span></h2>` +
    (data.market_scouting < 1
      ? `<p class="muted">Market coverage ${Math.round(data.market_scouting * 100)}% —
         numbers below are estimates${data.market_scouting === 0 ? "; assign your scout to the market to see ceilings" : ""}.</p>`
      : "");
  card.appendChild(marketFilterControls(data.free_agents, filters));
  const cap = data.roster_max ?? 5;
  card.appendChild(el("p", "muted",
    `Squad ${data.roster_count}/${cap}. ${data.phase === "playoffs"
      ? "Rosters are locked during the playoffs." : "Sign to fill a slot, or swap to add + drop in one move."}`));
  const t = el("table");
  t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th class="num">Age</th>
    <th class="num">OVR</th><th>Ability</th><th>Ceiling</th>
    <th>Languages</th><th class="num">Stream revenue</th><th class="num">Asking</th><th></th><th>Swap out</th></tr></thead>`;
  const tb = el("tbody");
  const locked = data.phase === "playoffs";
  for (const p of freeAgents) {
    const fogged = p.fog > 0;
    const langs = langChips(p.languages);
    const fit = p.locker_room_fit;
    const roomFit = fit ? `<div class="muted" title="Existing player history with your current roster">Room fit ${Math.round(fit.score)}${fit.duos ? ` · ${fit.duos} duo` : ""}${fit.feuds ? ` · ${fit.feuds} feud` : ""}</div>` : "";
    const tr = el("tr", "", `
      <td><img class="portrait" src="${p.portrait}" alt=""><b>${plink(p.id, p.handle)}</b>${roomFit}</td><td>${stylePill(p)}</td>
      <td class="num">${p.age}</td>
      <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${fogged ? "~" + Math.round(p.overall) : p.overall}</td>
      <td>${starsRange(p.scout?.ca_stars)}</td>
      <td>${starsRange(p.scout?.pa_stars)}</td>
      <td>${langs || '<span class="muted">—</span>'}</td>
      <td class="num">${money(p.stream_income)}/wk</td>
      <td class="num">${money(p.asking_salary)}/wk</td>
      <td><button class="btn btn-sm" data-act="sign" ${p.can_sign ? "" : "disabled"}
        title="${p.block_reason || "open contract talks — their ask is an opening number"}">Negotiate…</button></td>
      <td data-swap></td>`);
    tr.querySelector('[data-act="sign"]').onclick = () => {
      // Signing is a negotiation now — the ask column is their OPENING
      // number, not the price.
      openNegotiation({ id: p.id, handle: p.handle });
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
      // isConnected: the sort delegate removes detail rows before sorting,
      // so a stale reference means "recreate", not "collapse".
      if (detail && detail.isConnected) { detail.remove(); detail = null; return; }
      detail = el("tr", "", `<td colspan="11">${attrDetail(p)}</td>`);
      detail.dataset.detail = "1";
      tr.after(detail);
    };
    tb.appendChild(tr);
  }
  if (!freeAgents.length) {
    tb.appendChild(el("tr", "", '<td colspan="11" class="muted">No free agents match these filters.</td>'));
  }
  t.appendChild(tb);
  // The full free-agent list (~90 rows) scrolls INSIDE its panel — vertically
  // (bounded height, sticky header) and horizontally — so it never grows the
  // page into a giant scroll. Keeps the advisory rail in view alongside it.
  const tScroll = el("div", "card-scroll table-scroll");
  tScroll.style.setProperty("--scroll-max", "62vh");
  tScroll.appendChild(t);
  card.appendChild(tScroll);
  main.appendChild(card);

  /* -- rail ws-4: the advisory cards that used to stack above the table ----- */
  const needs = data.squad_needs, targets = data.target_suggestions || [];
  const cw = data.contract_watch || {};

  // Squad intelligence: role balance + the thinnest position.
  if (needs) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Squad intelligence"));
    const rolebar = el("div", "es-roles");
    for (const [role, n] of Object.entries(needs.role_counts || {})) {
      const gap = (needs.gaps || []).includes(role);
      rolebar.appendChild(el("span", "pill" + (gap ? " elim-pill" : ""), `${role} ${n}`));
    }
    c.appendChild(rolebar);
    if (needs.weakest_role) {
      c.appendChild(el("p", "muted",
        `Weakest: ${esc(needs.weakest_role.role)} (${needs.weakest_role.quality})`));
    }
    rail.appendChild(c);
  }

  // Signing headroom: the wage the org can absorb + runway.
  if (head.balance != null) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Signing headroom"));
    const box = el("div", "es-head");
    const runway = head.runway_weeks == null ? "stable"
      : head.runway_weeks === 0 ? "insolvent now" : `${head.runway_weeks}w runway`;
    const netCls = head.weekly_net >= 0 ? "trend-up" : "trend-down";
    box.innerHTML =
      `<div>Weekly net <b class="mono ${netCls}">${money(head.weekly_net)}</b></div>` +
      `<div>Affordable wage <b class="mono">${money(head.affordable_wage)}/wk</b></div>` +
      `<div class="muted">${runway}</div>`;
    c.appendChild(box);
    rail.appendChild(c);
  }

  // Suggested signings: quick fits for the thin spots.
  if (targets.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Suggested signings"));
    for (const tgt of targets) {
      c.appendChild(el("div", "entity",
        `<span class="entity-name"><b>${plink(tgt.id, tgt.handle)}</b></span>` +
        `<span class="entity-meta">${esc(tgt.role)}</span>` +
        `<b class="entity-num">${tgt.quality}${tgt.affordable ? "" : ' <span class="muted" title="over budget">✗</span>'}</b>`));
    }
    rail.appendChild(c);
  }

  // Contract watch: your expiries (renewal urgency) + rivals nearing free agency.
  const own = cw.expiring_own || [], watch = cw.market_watch || [];
  if (own.length || watch.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Contract watch"));
    for (const p of own) {
      c.appendChild(el("div", "entity",
        `<span class="entity-name"><b>${plink(p.id, p.handle)}</b></span>` +
        `<span class="entity-meta">yours · ${esc(p.role)}</span>` +
        `<b class="entity-num trend-down">${p.weeks_left}w</b>`));
    }
    for (const p of watch) {
      c.appendChild(el("div", "entity",
        `<span class="entity-name"><b>${plink(p.id, p.handle)}</b></span>` +
        `<span class="entity-meta">${tlink(p.team_id, p.team)} · ${esc(p.role)}</span>` +
        `<b class="entity-num">${p.weeks_left}w</b>`));
    }
    rail.appendChild(c);
  }

  // Wonderkids: the league-wide "next big thing" watch (≤20).
  const wk = data.wonderkids || [], chal = data.challengers || [];
  if (wk.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", `Wonderkids <span class="muted" style="font-weight:400">— ≤20</span>`));
    for (const p of wk) {
      c.appendChild(el("div", "entity",
        `<span class="entity-name"><b>${plink(p.id, p.handle)}</b></span>` +
        `<span class="entity-meta">${p.age}y · ${esc(p.role)} · ${tlink(p.team_id, p.team)}</span>` +
        `<b class="entity-num stars">${"★".repeat(Math.round(p.potential_stars))}</b>`));
    }
    rail.appendChild(c);
  }

  // Challengers standouts: the region's tier-2 form book.
  if (chal.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Challengers standouts"));
    for (const p of chal) {
      c.appendChild(el("div", "entity",
        `<span class="entity-name"><b>${plink(p.id, p.handle)}</b></span>` +
        `<span class="entity-meta">${p.age}y · ${esc(p.role)} · ${tlink(p.team_id, p.team)}</span>` +
        `<b class="entity-num">${p.rating.toFixed(2)}</b>`));
    }
    rail.appendChild(c);
  }

  // Rumour mill: plain-text whispers (server sends no ids). The long list
  // scrolls inside its card so the rail stays near one viewport.
  const rumors = data.rumors || [];
  if (rumors.length) {
    const c = el("div", "card");
    c.appendChild(el("h2", "", "Rumour mill"));
    const scroll = el("div", "card-scroll");
    scroll.style.setProperty("--scroll-max", "260px");
    for (const r of rumors) {
      scroll.appendChild(el("div", `es-rumor muted ${r.kind}`, esc(r.text)));
    }
    c.appendChild(scroll);
    rail.appendChild(c);
  }
}

// Package-deal builder: offer any of my players + cash (either way) for a rival.
async function openOffer(target) {
  let mine = [];
  try {
    const mkt = await api("/api/market");
    if (mkt.phase === "playoffs") { toast("rosters are locked during the playoffs"); return; }
    mine = mkt.my_roster ?? [];
  } catch { return; }

  const ov = el("div", "overlay trade-overlay");
  const panel = el("div", "panel trade-room");
  panel.innerHTML = `<button class="btn btn-sm offer-close" style="float:right">✕</button>
    <div class="trade-kicker">Trade room</div><h2>${plink(target.id, target.handle)} <span class="muted">· ${esc(target.team_name)}</span></h2>
    <p class="muted">Build the deal in players and cash. The balance is your coach and analyst's
    internal valuation; ${esc(target.team_name)} decide using their own scouting and economics.</p>`;
  panel.insertAdjacentHTML("beforeend", askBreakdown(target.ask_breakdown));
  const deal = el("div", "trade-deal");
  const sendSide = el("section", "trade-side");
  const receiveSide = el("section", "trade-side");
  sendSide.appendChild(el("h3", "", "You send"));
  receiveSide.appendChild(el("h3", "", "You receive"));
  deal.append(sendSide, receiveSide);
  panel.appendChild(deal);
  const list = el("div", "");
  const chosen = new Set();
  for (const p of mine) {
    const row = el("label", "trade-pick");
    row.style.cursor = "pointer";
    const cb = el("input");
    cb.type = "checkbox";
    cb.onchange = () => { cb.checked ? chosen.add(p.id) : chosen.delete(p.id); recompute(); };
    row.append(cb, el("span", "", `${p.handle} · OVR ${p.overall}`), el("b", "", money(p.value)));
    list.appendChild(row);
  }
  sendSide.appendChild(list);

  const cashOut = el("input"); cashOut.type = "number"; cashOut.min = "0"; cashOut.value = "0"; cashOut.className = "sel-sm";
  const cashIn = el("input"); cashIn.type = "number"; cashIn.min = "0"; cashIn.value = "0"; cashIn.className = "sel-sm";
  cashOut.oninput = recompute; cashIn.oninput = recompute;
  const cashWrap = el("div", "trade-cash");
  const oL = el("label", "row"); oL.append(el("span", "", "Cash you send: "), cashOut);
  const iL = el("label", "row"); iL.append(el("span", "", "Cash you want back: "), cashIn);
  cashWrap.append(oL, iL);
  sendSide.appendChild(cashWrap);

  const summary = el("div", "trade-summary");
  panel.appendChild(summary);
  let previewSeq = 0;
  const assetCard = (p) => `<article class="trade-asset">
    <div class="trade-asset-head"><img class="portrait" src="${p.portrait}" alt=""><b>${plink(p.id, p.handle)}</b><span class="pill">${esc(p.role)}</span></div>
    <div class="trade-stats"><span>OVR <b>${p.overall_estimated ? "~" : ""}${p.overall}</b></span><span>POT <b>${p.potential.low}-${p.potential.high}</b></span>
    <span>Contract <b>${money(p.contract.salary)}/wk · ${p.contract.weeks_left}w</b></span><span>Stream <b>${money(p.stream_revenue)}/wk</b></span></div>
    <div class="trade-value">Staff value <b>${money(p.value.consensus)}</b></div></article>`;
  async function recompute() {
    const seq = ++previewSeq;
    const co = Math.max(0, parseInt(cashOut.value || "0", 10));
    const ci = Math.max(0, parseInt(cashIn.value || "0", 10));
    let p;
    try { p = await api("/api/trade/preview", { target_pid: target.id, out_pids: [...chosen], cash_out: co, cash_in: ci }); }
    catch { return; }
    if (seq !== previewSeq) return;
    receiveSide.querySelectorAll(".trade-asset,.trade-cash-chip").forEach((n) => n.remove());
    receiveSide.insertAdjacentHTML("beforeend", assetCard(p.target));
    if (p.cash.receive) receiveSide.insertAdjacentHTML("beforeend", `<div class="trade-cash-chip">+ ${money(p.cash.receive)} cash</div>`);
    sendSide.querySelectorAll(".trade-asset-selected,.trade-cash-chip").forEach((n) => n.remove());
    for (const a of p.offered_players) sendSide.insertAdjacentHTML("beforeend", `<div class="trade-asset-selected">${assetCard(a)}</div>`);
    if (p.cash.send) sendSide.insertAdjacentHTML("beforeend", `<div class="trade-cash-chip">+ ${money(p.cash.send)} cash</div>`);
    const o = p.opinions;
    summary.innerHTML = `<div class="trade-balance-head"><b>${esc(p.verdict)}</b><span>Give ${money(o.consensus.send)} · Receive ${money(o.consensus.receive)}</span></div>
      <div class="trade-balance"><i style="width:${p.balance_pct}%"></i><span style="left:${p.balance_pct}%"></span></div>
      <div class="trade-opinions"><span>${esc(p.staff.coach)}: <b>${money(o.coach.receive - o.coach.send)}</b></span>
      <span>${esc(p.staff.analyst)}: <b>${money(o.analyst.receive - o.analyst.send)}</b></span></div>`;
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

// Contract negotiation modal (renewals + free-agent signings): the player
// opens with DEMANDS, you counter with a salary + term, they accept /
// counter / walk. Three rejected offers — or an insulting number — and
// they leave the table (cooldown before they'll talk again).
async function openNegotiation(target) {
  let neg;
  try {
    const r = await api("/api/negotiation/open", { player_id: target.id });
    neg = r.negotiation;
  } catch { return; } // api() toasted the reason (cooldown, wrong target...)

  const ov = el("div", "overlay contract-overlay");
  const panel = el("div", "panel contract-room");
  const title = neg.kind === "renew" ? "Contract talks" : "Free-agent talks";
  panel.innerHTML = `<button class="btn btn-sm neg-close" style="float:right">✕</button>
    <h2>${title} — ${plink(target.id, neg.handle)}</h2>` +
    (neg.kind === "renew"
      ? `<p class="muted">Current deal: <b>${money(neg.current_salary)}/wk</b>, ${neg.contract_weeks_left}w ·
        ${neg.current_terms.stream_share}% streams · ${money(neg.current_terms.release_fee)} release ·
        ${neg.current_terms.buyout ? money(neg.current_terms.buyout) + " buyout" : "no buyout"} ·
        ${esc(neg.current_terms.role)}${neg.current_terms.no_transfer ? " · no-transfer clause" : ""}.</p>`
      : "");
  if (neg.locker_room_fit) {
    const fit = neg.locker_room_fit;
    panel.appendChild(el("p", "muted", `Locker-room fit: ${Math.round(fit.score)}/100${fit.duos ? ` · ${fit.duos} existing duo${fit.duos === 1 ? "" : "s"}` : ""}${fit.feuds ? ` · ${fit.feuds} active feud${fit.feuds === 1 ? "" : "s"}` : ""}.`));
  }
  const demand = el("div", "contract-dialogue", "");
  const log = el("div", "contract-dialogue");
  const rounds = el("p", "muted", "");
  const paint = () => {
    demand.innerHTML = `<div class="contract-bubble player"><span class="microlabel">${esc(neg.handle)}</span>
      ${esc(neg.opening_line)}<div class="contract-ask"><b>${money(neg.demand_salary)}/wk</b> · ${neg.demand_weeks}w ·
      ${neg.demand_stream_share}% streams · ${money(neg.demand_release_fee)} release ·
      ${neg.demand_buyout ? money(neg.demand_buyout) + " buyout" : "no buyout"}${neg.demand_no_transfer ? " · no-transfer clause" : ""}</div></div>`;
    rounds.textContent = `${neg.rounds_left} offer${neg.rounds_left !== 1 ? "s" : ""} before they walk away.`;
  };
  paint();
  panel.append(demand, rounds);

  const sal = el("input"); sal.type = "number"; sal.min = "800"; sal.step = "100";
  sal.value = String(neg.demand_salary); sal.className = "sel-sm mono";
  const wks = el("input"); wks.type = "number"; wks.min = "16"; wks.max = "80";
  wks.value = String(neg.demand_weeks); wks.className = "sel-sm mono";
  const stream = el("input"); stream.type = "number"; stream.min = "0"; stream.max = "100";
  stream.value = String(neg.demand_stream_share); stream.className = "sel-sm mono";
  const releaseFee = el("input"); releaseFee.type = "number"; releaseFee.min = "0"; releaseFee.step = "1000";
  releaseFee.value = String(neg.demand_release_fee); releaseFee.className = "sel-sm mono";
  const buyout = el("input"); buyout.type = "number"; buyout.min = "0"; buyout.step = "1000";
  buyout.value = String(neg.demand_buyout); buyout.className = "sel-sm mono";
  const ntc = el("input"); ntc.type = "checkbox"; ntc.checked = neg.demand_no_transfer;
  const role = el("select", "sel-sm");
  for (const [id, label] of [["starter", "Starter"], ["bench", "Bench / rotation"], ["academy", "Academy / youth"]]) {
    const o = el("option", "", label); o.value = id; o.selected = id === neg.demand_role; role.appendChild(o);
  }
  const sL = el("label", "row"); sL.append(el("span", "", "Salary/wk: "), sal);
  const wL = el("label", "row"); wL.append(el("span", "", "Weeks: "), wks);
  const stL = el("label", "row"); stL.append(el("span", "", "Player keeps streaming: "), stream, el("span", "muted", "%"));
  const rfL = el("label", "row"); rfL.append(el("span", "", "Release fee: "), releaseFee);
  const boL = el("label", "row"); boL.append(el("span", "", "Buyout for other teams: "), buyout);
  const ntL = el("label", "row"); ntL.append(el("span", "", "No-transfer clause: "), ntc);
  const roL = el("label", "row"); roL.append(el("span", "", "Promised role: "), role);
  const terms = el("div", "contract-terms"); terms.append(sL, wL, stL, rfL, boL, ntL, roL);
  terms.appendChild(el("p", "muted contract-goal", neg.role_goal));
  panel.appendChild(terms);

  const offerBtn = el("button", "btn btn-primary", "Make the offer");
  const walkBtn = el("button", "btn btn-sm", "Leave the table");
  offerBtn.onclick = async () => {
    let r;
    try {
      r = await api("/api/negotiation/offer", {
        player_id: target.id,
        salary: Math.max(0, parseInt(sal.value || "0", 10)),
        weeks: Math.max(16, parseInt(wks.value || "40", 10)),
        stream_share: Math.max(0, Math.min(100, parseInt(stream.value || "0", 10))),
        release_fee: Math.max(0, parseInt(releaseFee.value || "0", 10)),
        buyout: Math.max(0, parseInt(buyout.value || "0", 10)),
        no_transfer: ntc.checked,
        role: role.value,
      });
    } catch { return; } // error keeps the table open; reason toasted
    if (r.status === "accepted") {
      toast(r.message); close(); refresh(); render();
      return;
    }
    if (r.status === "collapsed") {
      log.appendChild(el("div", "contract-bubble player bad", esc(r.message)));
      offerBtn.disabled = true; walkBtn.textContent = "Close";
      return;
    }
    neg = r.negotiation;
    log.appendChild(el("div", "contract-bubble manager",
      `We offer ${money(parseInt(sal.value || "0", 10))}/wk as a ${esc(role.value)}.`));
    log.appendChild(el("div", "contract-bubble player", esc(r.message)));
    sal.value = String(neg.demand_salary); wks.value = String(neg.demand_weeks);
    stream.value = String(neg.demand_stream_share);
    releaseFee.value = String(neg.demand_release_fee); buyout.value = String(neg.demand_buyout);
    ntc.checked = neg.demand_no_transfer; role.value = neg.demand_role;
    paint();
  };
  walkBtn.onclick = async () => {
    try { await api("/api/negotiation/cancel", { player_id: target.id }); } catch {}
    close();
  };
  const actions = el("div", "row");
  actions.append(offerBtn, walkBtn);
  panel.append(actions, log);

  function close() { ov.remove(); }
  ov.onclick = (e) => { if (e.target === ov) close(); };
  panel.querySelector(".neg-close").onclick = close;
  ov.appendChild(panel);
  document.body.appendChild(ov);
}

// Book-depth tier label for a player deep-dive (mirrors the unlock
// thresholds in development.scout_report — server decides, this labels).
function scoutTier(p) {
  if (p >= 0.95) return "complete book";
  if (p >= 0.75) return "mental read";
  if (p >= 0.5) return "style read";
  if (p >= 0.25) return "basics";
  return "first looks";
}

async function scouting(v) {
  const data = await api("/api/scouting");
  const s = App.state;

  // Next opponent (from the state payload) powers the "Scout next opponent"
  // quick-assign — defensive: no fixture (bye/offseason) hides the button.
  const nf = s && s.next_fixture;
  const myId = s && s.user_team && s.user_team.id;
  const nextOppId = nf ? (nf.team_a === myId ? nf.team_b : nf.team_a) : null;
  const nextOppName = nf ? (nf.team_a === myId ? nf.team_b_name : nf.team_a_name) : null;

  v.appendChild(screenHead("Scouting", { sub: "One scout · one assignment" }));

  const ws = el("div", "ws");
  v.appendChild(ws);
  const main = el("div", "ws-7 ws-col");
  const rail = el("div", "ws-5 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  /* -- main ws-7: the scout desk (assignment + active job) ------------------ */
  const card = el("div", "card scout-desk");
  card.appendChild(el("h2", "", "Scout desk"));
  card.appendChild(el("p", "muted",
    "One scout, one assignment: cover a team (steady, ~3 weeks), sweep the " +
    "market (slower, wider), attend a match (one-shot intel on both sides), or " +
    "build the book on one player (fastest — and it goes deeper: comfort picks, " +
    "how they play, their mentality, the full verdict)."));
  card.appendChild(el("div", "scout-one-note",
    `<span class="chip tone-accent">One active job</span>` +
    `<b>Choose one of the three assignments below.</b> ` +
    `<span class="muted">Starting another immediately replaces the current job.</span>`));

  // Current assignment: the team name LINKS when covering a team (id in scope).
  if (data.target) {
    const kindLabel = { team: "Covering", market: "Sweeping", player: "Deep-diving", match: "Attending" };
    const name = data.target_kind === "team"
      ? tlink(data.target, data.target_name ?? data.target)
      : esc(data.target_name ?? data.target);
    const status = el("p", "");
    status.innerHTML =
      `<span class="chip tone-good">${kindLabel[data.target_kind] ?? "On"}</span> <b>${name}</b> ` +
      (data.target_kind === "match"
        ? '<span class="muted">— intel lands after the match is played</span>'
        : `<span class="muted">— coverage ${Math.round(data.progress * 100)}%` +
          (data.target_kind === "player" ? ` · ${scoutTier(data.progress)}` : "") + "</span>");
    card.appendChild(status);
    if (data.target_kind !== "match") {
      card.appendChild(el("div", "", bar(Math.round(data.progress * 100))));
    }
  } else {
    card.appendChild(el("p", "muted", "Nobody is being watched."));
  }

  // -- assignment pickers ----------------------------------------------------
  const choices = el("div", "scout-choices");
  const coverageChoice = el("div", "tile scout-choice");
  coverageChoice.appendChild(el("div", "scout-choice-head",
    `<span class="chip">1</span><b>Cover a beat</b>`));
  coverageChoice.appendChild(el("span", "muted scout-choice-copy", "Build team or market coverage over time."));
  const sel = el("select", "select");
  sel.appendChild(el("option", "", "— cover a team / market —"));
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
  coverageChoice.appendChild(sel);
  choices.appendChild(coverageChoice);

  // Attend a match (next two weeks, not your own games).
  const matchChoice = el("div", "tile scout-choice");
  matchChoice.appendChild(el("div", "scout-choice-head",
    `<span class="chip">2</span><b>Attend a match</b>`));
  matchChoice.appendChild(el("span", "muted scout-choice-copy", "One-shot intel on both teams after they play."));
  const fsel = el("select", "select");
  fsel.appendChild(el("option", "", (data.upcoming ?? []).length
    ? "— choose a fixture —" : "No attendable matches"));
  fsel.disabled = !(data.upcoming ?? []).length;
  if ((data.upcoming ?? []).length) {
    for (const f of data.upcoming) {
      const o = el("option", "", `${f.label} (W${f.week}${f.stage !== "regular" ? " · " + f.stage : ""})`);
      o.value = f.id;
      if (data.target === "match:" + f.id) o.selected = true;
      fsel.appendChild(o);
    }
    fsel.onchange = async () => {
      if (!fsel.value) return;
      const r = await api("/api/actions/scout", { fixture_id: fsel.value });
      toast(r.message);
      render();
    };
  }
  matchChoice.appendChild(fsel);
  choices.appendChild(matchChoice);

  // Deep-dive a player: search league-wide, click to assign.
  const playerChoice = el("div", "tile scout-choice");
  playerChoice.appendChild(el("div", "scout-choice-head",
    `<span class="chip">3</span><b>Deep-dive a player</b>`));
  playerChoice.appendChild(el("span", "muted scout-choice-copy", "Fastest route to comfort, style and mentality reads."));
  const pin = el("input", "field mono");
  pin.placeholder = "deep-dive a player: search by name…";
  playerChoice.appendChild(pin);
  const pbox = el("div", "");
  let ptimer = null;
  pin.oninput = () => {
    clearTimeout(ptimer);
    ptimer = setTimeout(async () => {
      const q = pin.value.trim();
      pbox.innerHTML = "";
      if (q.length < 2) return;
      let r;
      try { r = await api("/api/market/search?q=" + encodeURIComponent(q)); }
      catch { return; }
      for (const p of r.results.slice(0, 6)) {
        if (p.mine) continue;
        const b = el("button", "btn btn-sm",
          `${esc(p.handle)} <span class="muted">${esc(p.team_name ?? "free agent")}</span>`);
        b.onclick = async () => {
          const res = await api("/api/actions/scout", { player_id: p.id });
          toast(res.message);
          render();
        };
        pbox.appendChild(b);
      }
      if (!pbox.childElementCount) pbox.appendChild(el("span", "muted", "no players match"));
    }, 250);
  };
  playerChoice.appendChild(pbox);
  choices.appendChild(playerChoice);
  card.appendChild(choices);
  main.appendChild(card);

  if (data.match_report) {
    const mr = data.match_report;
    const rc = el("div", "card");
    rc.innerHTML = `<h2>Match-scout report <span class="chip tone-good">W${mr.week}</span></h2>` +
      `<div class="rowbar"><span>${tlink(mr.team_a_id, mr.team_a_name)} vs ${tlink(mr.team_b_id, mr.team_b_name)}</span>` +
      `<b class="rowbar-val mono">${esc(mr.score)}</b></div>` +
      (mr.danger_man ? `<div class="rowbar"><span>Danger man</span><span class="rowbar-val">` +
        `${plink(mr.danger_man.player_id, mr.danger_man.handle)} <span class="chip">${mr.danger_man.rating.toFixed(2)}</span></span></div>` : "") +
      `<div class="rowbar"><span>Veto lean</span><span class="rowbar-val">${esc(mr.veto_lean)}</span></div>` +
      `<div class="tile"><b>${tlink(mr.team_a_id, mr.team_a_name)}</b><div class="muted">` +
        `${(mr.team_a_tendencies || []).map(esc).join(" · ") || "no strong tendency observed"}</div></div>` +
      `<div class="tile"><b>${tlink(mr.team_b_id, mr.team_b_name)}</b><div class="muted">` +
        `${(mr.team_b_tendencies || []).map(esc).join(" · ") || "no strong tendency observed"}</div></div>`;
    main.appendChild(rc);
  }

  /* -- main ws-7: the report(s). CRITICAL FIX — the desk (above) and any
     report BOTH render; a deep-dive no longer early-returns and hides the
     team-coverage table. reports[] is single-kind, so it's one or the other. */
  if (data.target_kind === "player" && data.reports.length) {
    const r = data.reports[0];
    const dc = el("div", "card");
    dc.innerHTML = `<h2>The book on <b>${plink(r.player_id, r.handle)}</b>
      <span class="muted" style="font-weight:400">— ${scoutTier(data.progress)} (${Math.round(data.progress * 100)}%)</span></h2>`;
    const lines = [];
    const proj = (r.pa_projection ?? []).length === 2
      ? ` <span class="muted" title="A ceiling is a projection, never an exact read — and it keeps moving.">(proj. ${r.pa_projection[0]}–${r.pa_projection[1]})</span>`
      : "";
    lines.push(`<div><span class="pill">${esc(r.role)}</span> <span class="pill">${esc(r.playstyle)}</span>
      <span class="muted">age ${r.age}</span> · ability ${starsRange(r.ca_stars)} · ceiling ${starsRange(r.pa_stars)}${proj}</div>`);
    if ((r.agent_comfort ?? []).length) {
      lines.push(`<div><b>Comfort picks:</b> ` + r.agent_comfort
        .map((a) => `<span class="pill">${esc(a.agent_id)} ${a.mastery}</span>`).join(" ") + `</div>`);
    } else {
      lines.push(`<div class="muted">Comfort picks unlock at 25%.</div>`);
    }
    lines.push(r.style_read
      ? `<div><b>How they play:</b> ${esc(r.style_read)}</div>`
      : `<div class="muted">Style read unlocks at 50%.</div>`);
    lines.push(r.mental_read
      ? `<div><b>Mentality:</b> ${esc(r.mental_read)}</div>`
      : `<div class="muted">Mental read unlocks at 75%.</div>`);
    if (r.curve_read) {
      lines.push(`<div><b>Development path:</b> ${esc(r.curve_read)}</div>`);
    }
    if ((r.traits ?? []).length || r.traits_hidden) {
      lines.push(`<div><b>Character:</b> ` + r.traits
        .map((t) => `<span class="pill" title="${esc(t.blurb)}">${humanize(t.id)}</span>`).join(" ") +
        (r.traits_hidden ? ` <span class="muted">+${r.traits_hidden} unknown</span>` : "") + `</div>`);
    }
    if ((r.strengths ?? []).length) {
      lines.push(`<div><b>Read:</b> <span class="muted">+${r.strengths.map((s) => esc(s.replaceAll("_", " "))).join(", ")}` +
        ((r.weaknesses ?? []).length ? ` · −${r.weaknesses.map((s) => esc(s.replaceAll("_", " "))).join(", ")}` : "") + `</span></div>`);
    }
    if ((r.ceiling_reads ?? []).length) {
      lines.push(`<div><b>Ceilings:</b> ` + r.ceiling_reads
        .map((c) => `<span class="pill" title="how much room this skill has left to its ceiling">${humanize(c.attr)}: ${esc(c.read)}</span>`).join(" ") + `</div>`);
    }
    lines.push(r.verdict
      ? `<div><b>Verdict:</b> ${esc(r.verdict)}</div>`
      : `<div class="muted">The verdict lands with the complete book.</div>`);
    dc.appendChild(el("div", "es-obj", lines.join("")));
    main.appendChild(dc);
  } else if (data.reports.length) {
    const rc = el("div", "card");
    // Heading links when covering a team (data.target is the team id here).
    const heading = data.target_kind === "team"
      ? tlink(data.target, data.target_name)
      : esc(data.target_name);
    rc.innerHTML = `<h2>Reports <span class="muted" style="font-weight:400">— ${heading}</span></h2>`;
    const t = el("table");
    t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th class="num">Age</th>
      <th>Ability</th><th>Ceiling</th><th>Character</th><th>Read</th></tr></thead>`;
    const tb = el("tbody");
    for (const r of data.reports) {
      const traits = r.traits
        .map((t) => `<span class="pill" title="${esc(t.blurb)}">${humanize(t.id)}</span>`)
        .join(" ") +
        (r.traits_hidden ? ` <span class="muted">+${r.traits_hidden}?</span>` : "");
      const read = r.strengths.length
        ? `<span class="muted">+${r.strengths.map((s) => esc(s.replaceAll("_", " "))).join(", ")}` +
          (r.weaknesses.length ? ` · −${r.weaknesses.map((s) => esc(s.replaceAll("_", " "))).join(", ")}` : "") +
          `</span>`
        : `<span class="muted">needs more time</span>`;
      tb.appendChild(el("tr", "", `
        <td><b>${plink(r.player_id, r.handle)}</b></td>
        <td><span class="pill">${esc(r.role)}</span> <span class="pill">${esc(r.playstyle)}</span></td>
        <td class="num">${r.age}</td>
        <td>${starsRange(r.ca_stars)}</td>
        <td>${starsRange(r.pa_stars)}</td>
        <td>${traits || '<span class="muted">—</span>'}</td>
        <td>${read}</td>`));
    }
    t.appendChild(tb);
    const scroll = el("div", "table-scroll");
    scroll.appendChild(t);
    rc.appendChild(scroll);
    main.appendChild(rc);
  }

  /* -- rail ws-5: intel-tier ladder + quick-assign buttons ------------------ */
  const ladder = el("div", "card");
  ladder.appendChild(el("h2", "", "Player intel tiers"));
  const active = data.target_kind === "player";
  const prog = active ? data.progress : 0;
  if (active) {
    ladder.appendChild(el("p", "muted",
      `Deep-diving ${esc(data.target_name)} — ${scoutTier(prog)} (${Math.round(prog * 100)}%)`));
    ladder.appendChild(el("div", "", bar(Math.round(prog * 100))));
  } else {
    ladder.appendChild(el("p", "muted", "What a player deep-dive reveals, stage by stage."));
  }
  const stages = [
    [0, "First looks", "role, ability band"],
    [0.25, "Basics", "comfort picks (agents + mastery)"],
    [0.5, "Style read", "how they play"],
    [0.75, "Mental read", "mentality under pressure"],
    [0.95, "Complete book", "the verdict + full ceilings"],
  ];
  for (const [thr, name, desc] of stages) {
    const reached = active && prog >= thr;
    ladder.appendChild(el("div", "entity",
      `<span class="entity-name"><b>${reached ? "✓ " : ""}${esc(name)}</b></span>` +
      `<span class="entity-meta">${esc(desc)}</span>` +
      `<span class="entity-num ${reached ? "trend-up" : "muted"}">${Math.round(thr * 100)}%</span>`));
  }
  rail.appendChild(ladder);

  // Quick assign: point the scout at the next opponent or the market in a click.
  const qa = el("div", "card");
  qa.appendChild(el("h2", "", "Quick assign"));
  // Each button on its own line (block wrapper) so long labels don't crowd.
  const addQuick = (btn) => { const w = el("div", ""); w.appendChild(btn); qa.appendChild(w); };
  if (nextOppId) {
    const b = el("button", "btn btn-sm" + (data.target === nextOppId ? " active" : ""),
      `Scout next opponent — ${esc(nextOppName ?? "")}`);
    b.onclick = async () => {
      const r = await api("/api/actions/scout", { team_id: nextOppId });
      toast(r.message); render();
    };
    addQuick(b);
  }
  const bm = el("button", "btn btn-sm" + (data.target === "market" ? " active" : ""),
    "Sweep the free-agent market");
  bm.onclick = async () => {
    const r = await api("/api/actions/scout", { team_id: "market" });
    toast(r.message); render();
  };
  addQuick(bm);
  rail.appendChild(qa);
}

// Player-table columns per analytics tier. The server already dropped the
// fields your department can't compile — a column renders only when its
// key is present in the rows (never recomputed client-side).
const STAT_COLS = [
  { k: "maps", h: "Maps" },
  { k: "rating", h: "Rating", f: (v) => `<b>${v.toFixed(2)}</b>` },
  { k: "acs", h: "ACS" },
  { k: "kills", h: "K" },
  { k: "deaths", h: "D" },
  { k: "assists", h: "A" },
  { k: "kd", h: "K/D", f: (v) => v.toFixed(2) },
  { k: "kast_pct", h: "KAST%" },
  { k: "first_kills", h: "FK" },
  { k: "first_deaths", h: "FD" },
  { k: "fk_fd", h: "FK:FD", f: (v) => v.toFixed(2) },
  { k: "hs_pct", h: "HS%" },
  { k: "trade_kills", h: "Trades" },
  { k: "clutches", h: "Clutch", t: "clutch round wins (1v1 + 1v2 + 1vX)" },
  { k: "multikills", h: "3K+" },
  { k: "aces", h: "Aces" },
  { k: "pistol_kills", h: "Pistol K" },
  { k: "eco_kills", h: "Eco K", t: "kills while your side was under-gunned" },
  { k: "save_kills", h: "Save K", t: "kills on a sidearm save" },
  { k: "plants", h: "Pl" },
  { k: "defuses", h: "Df" },
];

const STATS_TABS = [
  { id: "leaders", label: "Leaders" },
  { id: "races", label: "Races & Awards" },
  { id: "meta", label: "Meta" },
  { id: "history", label: "History" },
];

/* -- Stats: four task tabs over the analytics endpoints. The split
   (season/map/agent) and league-tier controls live in the screen-head right
   slot and set ONLY App.statsSplit / App.statsTier — never App.statsTab — so
   re-rendering after a split/tier change keeps you on the sub-tab you were
   reading. Every sub-tab fetches exactly what it needs (races/meta/perf are
   only pulled on their own tab). */
async function stats(v) {
  const sub = App.statsTab ?? "leaders";
  const split = App.statsSplit; // {kind, key} | null
  const lgTier = App.statsTier ?? 1; // 1 = top flight, 2 = Challengers
  const parts = [`league_tier=${lgTier}`];
  if (split) parts.push(`split=${split.kind}`, `key=${encodeURIComponent(split.key)}`);
  const qs = "?" + parts.join("&");
  const [data, racesResp, metaResp, perf] = await Promise.all([
    api("/api/stats" + qs),
    sub === "races" ? api("/api/races").catch(() => null) : Promise.resolve(null),
    sub === "meta" ? api("/api/meta").catch(() => null) : Promise.resolve(null),
    sub === "history" ? api("/api/perf").catch(() => null) : Promise.resolve(null),
  ]);
  const tier = data.analytics.tier;

  // Right slot: league-tier segmented control + (tier-3) split picker. Both
  // handlers touch only App.statsSplit / App.statsTier, so App.statsTab
  // survives the render() they trigger — the sub-tab never resets.
  const right = [];
  const tierSeg = el("div", "seg");
  const mkTier = (label, tval) => {
    const b = el("button", "seg-btn" + (lgTier === tval ? " on" : ""), label);
    b.onclick = () => { App.statsTier = tval; render(); };
    tierSeg.appendChild(b);
  };
  mkTier("Tier 1", 1);
  mkTier("Challengers", 2);
  right.push(tierSeg);
  if (data.split_keys) {
    const splitRow = el("div", "row");
    const seasonBtn = el("button", "btn btn-sm" + (split ? "" : " active"), "Season");
    seasonBtn.onclick = () => { App.statsSplit = null; render(); };
    splitRow.appendChild(seasonBtn);
    const mkSel = (label, kind, keys) => {
      const sel = el("select");
      sel.appendChild(el("option", "", label));
      for (const k of keys) {
        const o = el("option", "", k);
        o.value = k;
        if (split && split.kind === kind && split.key === k) o.selected = true;
        sel.appendChild(o);
      }
      sel.onchange = () => { if (sel.value) { App.statsSplit = { kind, key: sel.value }; render(); } };
      return sel;
    };
    splitRow.appendChild(mkSel("— by map —", "map", data.split_keys.maps));
    splitRow.appendChild(mkSel("— by agent —", "agent", data.split_keys.agents));
    right.push(splitRow);
  }

  v.appendChild(screenHead("Stats", {
    sub: `Season ${App.state.season} · analytics tier ${tier}`,
    subtabs: STATS_TABS,
    active: sub,
    onPick: (id) => { App.statsTab = id; render(); },
    right,
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);

  if (sub === "races") statsRaces(ws, data, racesResp);
  else if (sub === "meta") statsMeta(ws, data, metaResp, tier);
  else if (sub === "history") statsHistory(ws, data, perf);
  else statsLeaders(ws, data, tier, split, lgTier);
}

/* Stats · Leaders: the season leaderboard table first (full width — it's the
   primary read; server-gated columns via STAT_COLS), then the analytics-
   department context line. Team column tlinks via the row's team_id (degrades
   to plain text when absent). */
function statsLeaders(ws, data, tier, split, lgTier) {
  const lead = el("div", "card ws-12");
  const splitLabel = split ? ` — ${split.kind}: ${esc(split.key)}` : "";
  lead.innerHTML = `<h2>${lgTier === 2 ? "Challengers leaders" : "League leaders"} — season ${App.state.season}${splitLabel}</h2>`;
  if (!data.players.length) {
    lead.appendChild(el("p", "muted", "No maps played yet."));
  } else {
    const cols = STAT_COLS.filter((c) => data.players[0][c.k] !== undefined);
    const wrap = el("div", "table-scroll");
    const t = el("table");
    t.innerHTML = `<thead><tr><th>#</th><th>Player</th><th>Team</th>${cols
      .map((c) => `<th class="num" ${c.t ? `title="${c.t}"` : ""}>${c.h}</th>`)
      .join("")}</tr></thead>`;
    const tb = el("tbody");
    data.players.slice(0, 40).forEach((r, i) => {
      const cells = cols
        .map((c) => `<td class="num">${c.f ? c.f(r[c.k]) : r[c.k]}</td>`)
        .join("");
      tb.appendChild(el("tr", r.is_user ? "me" : "", `
        <td>${i + 1}</td><td><b>${plink(r.player_id, r.handle)}</b></td>
        <td class="muted">${tlink(r.team_id, r.team)}</td>${cells}`));
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    lead.appendChild(wrap);
    if (tier < 3) {
      lead.appendChild(el("p", "muted",
        "Per-map and per-agent leaderboards need a tier-3 analytics department."));
    }
  }
  ws.appendChild(lead);

  const banner = el("div", "card ws-12");
  banner.innerHTML = `<h2>Analytics department — tier ${data.analytics.tier}</h2>
    <p class="muted">${esc(data.analytics.label)}${
      data.analytics.next_unlock
        ? ` · hire a better analyst / upgrade the analytics suite to unlock: <b>${esc(data.analytics.next_unlock)}</b>`
        : " · everything unlocked"
    }</p>`;
  ws.appendChild(banner);
}

/* Stats · Races & Awards: live award races + impact leaderboards (main),
   with the full awards history in the rail (player plinked via player_id;
   team stays plain text). */
function statsRaces(ws, data, racesResp) {
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  const races = racesResp?.races || {};
  const raceKeys = Object.keys(races);
  if (raceKeys.length) {
    const rc = el("div", "card");
    rc.appendChild(el("h2", "", "Award races"));
    const grid = el("div", "es-rec-grid");
    for (const [award, leaders] of Object.entries(races)) {
      const rows = leaders.map((l, i) =>
        `<div class="es-race-row"><span class="mono muted">${i + 1}</span>` +
        plink(l.player_id, l.handle) +
        `<b class="mono">${esc(l.value)}</b></div>`).join("");
      grid.appendChild(el("div", "es-rec",
        `<div class="es-rec-lab muted">${esc(award)}</div>${rows}`));
    }
    rc.appendChild(grid);
    main.appendChild(rc);
  }

  const impact = data.impact || {};
  const impactCats = Object.entries(impact).filter(([, c]) => c.leaders?.length);
  if (impactCats.length) {
    const ic = el("div", "card");
    ic.appendChild(el("h2", "", `Impact leaders${data.league_tier === 2 ? " — Challengers" : ""}`));
    const grid = el("div", "es-rec-grid");
    for (const [, cat] of impactCats) {
      const rows = cat.leaders.map((l, i) =>
        `<div class="es-race-row"><span class="mono muted">${i + 1}</span>` +
        plink(l.player_id, l.handle) +
        `<b class="mono">${esc(l.value)}</b></div>`).join("");
      grid.appendChild(el("div", "es-rec",
        `<div class="es-rec-lab muted">${esc(cat.label)}</div>${rows}`));
    }
    ic.appendChild(grid);
    main.appendChild(ic);
  }

  if (!raceKeys.length && !impactCats.length) {
    main.appendChild(el("div", "card",
      `<h2>Award races</h2><p class="muted">No races yet — play some matches to seed the leaderboards.</p>`));
  }

  const aw = el("div", "card");
  aw.appendChild(el("h2", "", "Awards history"));
  if (data.awards.length) {
    const scroll = el("div", "card-scroll");
    for (const a of data.awards) {
      scroll.appendChild(el("div", "newsline",
        `<span class="pill">S${a.season}</span> <b>${esc(a.award)}</b> — ` +
        `${plink(a.player_id, a.handle)} <span class="muted">(${esc(a.team_name)})</span>, ${esc(a.value)}`));
    }
    aw.appendChild(scroll);
  } else {
    aw.appendChild(el("p", "muted", "No awards handed out yet."));
  }
  rail.appendChild(aw);
}

/* Stats · Meta: agent meta + team tendencies (main), patch-notes history
   (rail). Tendency rows expand to a per-map record; the detail row is tagged
   data-detail so the th-sort delegate drops it before sorting, and the row-
   click closure guards on isConnected (a dropped row means "recreate", not
   "collapse"). */
function statsMeta(ws, data, metaResp, tier) {
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  if (metaResp && (metaResp.tier_list?.length || metaResp.latest_patch)) {
    const mc = el("div", "card");
    mc.appendChild(el("h2", "", "Agent meta"));
    const lp = metaResp.latest_patch;
    if (lp) {
      mc.appendChild(el("p", "muted",
        `Patch ${esc(lp.version)} (S${lp.season} W${lp.week}) — ${esc(lp.lines.join("; "))}`));
    }
    const patched = metaResp.patched_agents || [];
    if (patched.length) {
      const chips = el("div", "es-meta-chips");
      for (const a of patched) {
        chips.appendChild(el("span", `es-meta-chip ${a.direction}`,
          `${esc(a.name)} ${a.direction === "buff" ? "▲" : a.direction === "nerf" ? "▼" : "–"}`));
      }
      mc.appendChild(chips);
    }
    const tl = metaResp.tier_list || [];
    if (tl.length) {
      const list = el("div", "es-meta-tier");
      const top = tl[0].maps || 1;
      for (const a of tl) {
        const w = Math.round(100 * a.maps / top);
        list.appendChild(el("div", "es-meta-row",
          `<span class="es-meta-name">${esc(a.name)}</span>` +
          `<span class="es-meta-track"><span class="es-meta-fill" style="width:${w}%"></span></span>` +
          `<span class="mono muted">${a.pick_rate}%</span>`));
      }
      mc.appendChild(el("span", "es-scout-lab muted", "Most-picked this season"));
      mc.appendChild(list);
    }
    main.appendChild(mc);
  } else {
    main.appendChild(el("div", "card",
      `<h2>Agent meta</h2><p class="muted">No meta data compiled yet.</p>`));
  }

  const mapTrends = metaResp?.map_trends || [];
  const dialLabels = {
    aggression: "Aggression", pace: "Pace", util_discipline: "Utility",
    eco_greed: "Eco greed", map_control: "Map control",
  };
  if (mapTrends.length) {
    const trends = el("div", "card");
    trends.innerHTML = `<h2>Map trends</h2><p class="muted">Public league data from completed maps. Use it to match the field or prepare a counter; team-specific plans remain scouting intel.</p>`;
    const grid = el("div", "es-map-meta-grid");
    for (const trend of mapTrends) {
      const agents = trend.agents.length
        ? trend.agents.map((a) => `${esc(a.name)} <span class="muted">${a.pick_rate}%</span>`).join(" · ")
        : "No agent picks yet";
      const tactics = trend.tactics.map((t) =>
        `<span class="es-map-meta-dial"><b>${esc(dialLabels[t.key] || t.key)}</b> ${t.average}</span>`
      ).join("");
      grid.appendChild(el("div", "es-map-meta", `
        <div class="es-map-meta-head">${mapThumb(trend.map_id, "sm")}<b>${esc(trend.map_id)}</b>
          <span class="mono muted">${trend.team_maps} team maps</span></div>
        <div><span class="muted">Top agents</span> ${agents}</div>
        <div class="es-map-meta-dials">${tactics}</div>
        <span class="muted">Most focused site: ${esc(trend.site_focus)}</span>`));
    }
    trends.appendChild(grid);
    main.appendChild(trends);
  }

  if (data.teams.length) {
    const tc = el("div", "card");
    tc.innerHTML = `<h2>Team tendencies</h2>` +
      (tier >= 2 ? `<p class="muted">Click a team row for its per-map record.</p>` : "");
    const t = el("table");
    t.innerHTML = `<thead><tr><th>Team</th><th class="num">Maps</th>
      <th class="num">ATK round %</th><th class="num">DEF round %</th>
      <th class="num">Pistol %</th></tr></thead>`;
    const tb = el("tbody");
    for (const r of data.teams) {
      const tr = el("tr", r.is_user ? "me" : "", `
        <td><b>${tlink(r.team_id, r.name)}</b></td><td class="num">${r.maps}</td>
        <td class="num">${r.atk_pct}</td><td class="num">${r.def_pct}</td>
        <td class="num">${r.pistol_pct}</td>`);
      if ((r.maps_detail ?? []).length) {
        tr.style.cursor = "pointer";
        let detail = null;
        tr.onclick = (e) => {
          if (e.target.closest("[data-tid]")) return;
          // isConnected: the sort delegate removes detail rows before sorting,
          // so a stale reference means "recreate", not "collapse".
          if (detail && detail.isConnected) { detail.remove(); detail = null; return; }
          const rows = r.maps_detail
            .map((m) => `<tr><td>${mapThumb(m.map_id, "sm")}${esc(m.map_id)}</td>
              <td class="num">${m.maps}</td><td class="num">${m.wins}</td>
              <td class="num">${m.win_pct}%</td><td class="num">${m.atk_pct}%</td>
              <td class="num">${m.def_pct}%</td></tr>`)
            .join("");
          detail = el("tr", "", `<td colspan="5"><table>
            <thead><tr><th>Map</th><th class="num">Played</th><th class="num">W</th>
            <th class="num">Win%</th><th class="num">ATK%</th><th class="num">DEF%</th></tr></thead>
            <tbody>${rows}</tbody></table></td>`);
          detail.dataset.detail = "1";
          tr.after(detail);
        };
      }
      tb.appendChild(tr);
    }
    t.appendChild(tb);
    tc.appendChild(t);
    main.appendChild(tc);
  }

  if ((data.patches ?? []).length) {
    const pc = el("div", "card");
    pc.innerHTML = `<h2>Patch notes</h2>
      <p class="muted">The meta moves twice a season — mid-split and over the break.
      Rosters built around a nerfed kit feel it.</p>`;
    const scroll = el("div", "card-scroll");
    for (const n of data.patches) {
      scroll.appendChild(el("div", "newsline",
        `<span class="pill">Patch ${esc(n.version)}</span> ` +
        `<span class="muted">S${n.season} W${n.week}</span> — ${esc(n.lines.join("; "))}`));
    }
    pc.appendChild(scroll);
    rail.appendChild(pc);
  } else {
    rail.appendChild(el("div", "card",
      `<h2>Patch notes</h2><p class="muted">No balance patches yet this season.</p>`));
  }
}

/* Stats · History: champions + Hall of Fame (main). Champions tlink their team
   via team_id; HoF names stay PLAIN TEXT — retirees are deleted from
   gs.players, so a profile link would always dead-end. The perf/dev-telemetry
   card lives in the rail, collapsed inside a <details> so it stops dominating
   the screen. */
function statsHistory(ws, data, perf) {
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  const champs = App.state.champions ?? [];
  const cc = el("div", "card");
  cc.appendChild(el("h2", "", "Champions"));
  if (champs.length) {
    const scroll = el("div", "card-scroll");
    for (const c of [...champs].reverse()) {
      scroll.appendChild(el("div", "newsline",
        `<span class="pill">S${c.season}</span> <b>${tlink(c.team_id, c.team_name)}</b>`));
    }
    cc.appendChild(scroll);
  } else {
    cc.appendChild(el("p", "muted", "No champion crowned yet."));
  }
  main.appendChild(cc);

  if ((data.hall_of_fame ?? []).length) {
    const hf = el("div", "card");
    hf.appendChild(el("h2", "", "Hall of Fame"));
    const scroll = el("div", "card-scroll");
    for (const h of data.hall_of_fame) {
      scroll.appendChild(el("div", "newsline",
        `<span class="pill">S${h.season}</span> <b>${esc(h.handle)}</b>` +
        `${h.team_name ? ` <span class="muted">(${esc(h.team_name)})</span>` : ""} — ${esc(h.blurb)}`));
    }
    hf.appendChild(scroll);
    main.appendChild(hf);
  }

  // Performance observability (this server session): read-only view of
  // /api/perf, best-effort. Collapsed by default so it never dominates.
  const pc = el("div", "card");
  const det = el("details");
  det.appendChild(el("summary", "es-details-summary",
    "Performance — this session, resets on restart"));
  const ticks = perf?.ticks || [];
  if (!perf) {
    det.appendChild(el("p", "muted", "Performance telemetry unavailable."));
  } else if (!ticks.length) {
    det.appendChild(el("p", "muted", "No weeks advanced this session yet."));
  } else {
    const last = ticks[ticks.length - 1];
    const maxMs = Math.max(...ticks.map((t) => t.total_ms), 1);
    const bars = ticks.slice(-40).map((t) =>
      `<span title="S${t.season} W${t.week}: ${t.total_ms}ms" style="display:inline-block;width:7px;margin-right:1px;vertical-align:bottom;height:${Math.max(2, Math.round(36 * t.total_ms / maxMs))}px;background:var(--es-color-accent,#4fd8c0)"></span>`
    ).join("");
    det.appendChild(el("p", "", `Advance time, last ${Math.min(ticks.length, 40)} weeks
      (peak ${Math.round(maxMs)}ms):<br>${bars}`));
    const phases = Object.entries(last.phases || {}).sort((a, b) => b[1] - a[1]);
    const pt = el("table");
    pt.dataset.nosort = "1";
    pt.innerHTML = `<thead><tr><th>Phase (last tick: ${last.total_ms}ms)</th><th class="num">ms</th></tr></thead>`;
    const ptb = el("tbody");
    for (const [name, ms] of phases) {
      ptb.appendChild(el("tr", "", `<td>${esc(name)}</td><td class="num">${ms}</td>`));
    }
    pt.appendChild(ptb);
    det.appendChild(pt);
    const sizes = Object.entries(last.sizes || {})
      .map(([k, n]) => `${k} ${n.toLocaleString()}`).join(" · ");
    const saveB = perf.gauges?.["save.bytes"];
    det.appendChild(el("p", "muted",
      `State growth: ${esc(sizes)}${saveB ? ` · save ${(saveB / 1024 / 1024).toFixed(1)}MB` : ""}`));
  }
  if (perf) {
    const api5 = Object.entries(perf.spans || {})
      .filter(([k]) => k.startsWith("api."))
      .sort((a, b) => b[1].p95_ms - a[1].p95_ms).slice(0, 5);
    if (api5.length) {
      det.appendChild(el("p", "muted",
        "Slowest endpoints (p95): " + api5
          .map(([k, s]) => `${esc(k.slice(4))} ${s.p95_ms}ms×${s.count}`).join(" · ")));
    }
    const save = perf.spans?.["save.write"];
    if (save) {
      det.appendChild(el("p", "muted",
        `Save write: last ${save.last_ms}ms · p95 ${save.p95_ms}ms · ${save.count} writes`));
    }
  }
  pc.appendChild(det);
  rail.appendChild(pc);
}

/* -- social: the feed + follower economy ----------------------------------- */

const POST_KIND_ICON = {
  result: "🏁", hype: "🔥", viral: "📈", drama: "⚡", milestone: "🎉", transfer: "✍",
};

async function social(v) {
  const data = await api("/api/social");

  // Mood word/tone come from the server (social.mood_view) — the UI never
  // re-derives sim thresholds.
  const mood = data.your_sentiment ?? 50;
  const moodWord = data.your_mood?.word ?? "neutral";
  const moodTone = data.your_mood?.tone ?? "";

  v.appendChild(screenHead("Social", {
    sub: `S${App.state.season} · W${App.state.week}`,
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  /* -- main ws-8: the feed, scrolling inside its own card -------------------- */
  const feedCard = el("div", "card");
  feedCard.appendChild(el("h2", "", "Feed"));
  if (!data.feed.length) {
    feedCard.appendChild(el("p", "muted", "Nothing posted yet — play a week."));
  } else {
    const scroll = el("div", "card-scroll");
    scroll.style.setProperty("--scroll-max", "70vh");
    for (const post of data.feed) {
      const who = post.author_kind === "player"
        ? `<b>${plink(post.author_id, "@" + post.author)}</b>`
        : post.author_kind === "team"
          ? `<b>${tlink(post.author_id, "@" + post.author)}</b>`
          : `<b>${esc(post.author)}</b>`;
      const node = el("div", "post",
        `<div class="post-head">${POST_KIND_ICON[post.kind] ?? "·"} ${who}
           <span class="muted">S${post.season} W${post.week}</span></div>
         <div class="post-body">${post.text}</div>
         <div class="post-likes muted">♥ ${fmtFollowers(post.likes)}</div>`);
      // LLM-ghost-written posts keep the grounded fact on hover; the server
      // only ever rephrases real outcomes (web/llm_social.py).
      if (post.ai && post.fact) {
        node.querySelector(".post-body").title = post.fact;
      }
      scroll.appendChild(node);
    }
    feedCard.appendChild(scroll);
  }
  main.appendChild(feedCard);

  /* -- rail ws-4: org reach, fanbase mood, reach board, movement ------------- */

  // Org card: reach + fan mood + the streaming-income line (→ Finances), then
  // the roster's individual streamers.
  const org = el("div", "card");
  org.appendChild(el("h2", "", "Your reach"));
  org.appendChild(el("div", "row",
    `<span class="chip">roster reach ${fmtFollowers(data.your_reach)}</span>` +
    `<span class="chip">org fans ${fmtFollowers(data.fan_count)}</span>` +
    `<span class="pill ${moodTone}">fanbase ${esc(moodWord)} (${Math.round(mood)})</span>`));
  const streamRow = el("div", "tile stream-income-tile",
    `<span class="stream-income-icon">↗</span>` +
    `<span><span class="microlabel">Streamer revenue</span>` +
    `<b class="mono stream-income-value">${money(data.your_stream_income || 0)}/wk</b>` +
    `<span class="muted">direct weekly org income</span></span><span class="spacer"></span>`);
  const finBtn = el("button", "btn btn-sm", "→ Finances");
  finBtn.onclick = () => dashGoTab("finances");
  streamRow.appendChild(finBtn);
  org.appendChild(streamRow);
  org.appendChild(el("p", "muted",
    "Reach feeds sponsor marketability; streaming pays the org a cut (heavy streamers " +
    "develop slower — rein one in with a 1:1); the crowd's mood leaks into the locker " +
    "room, and brands read the room too."));
  if (data.your_roster.length) {
    org.appendChild(el("span", "es-scout-lab muted", "Your streamers"));
    const rr = el("div", "row offer-row");
    for (const p of data.your_roster) {
      rr.appendChild(el("span", "pill",
        `<b>${plink(p.player_id, p.handle)}</b> ${fmtFollowers(p.followers)} ` +
        `<span class="muted" title="${esc(p.stream_status)} — org cut ${money(p.stream_income)}/wk">· ${money(p.stream_income)}/wk</span>`));
    }
    org.appendChild(rr);
  }
  rail.appendChild(org);

  // Community mood board: whose fans are euphoric, whose are done.
  if ((data.sentiment ?? []).length) {
    const sc = el("div", "card");
    sc.appendChild(el("h2", "", "Fanbase mood"));
    const st = el("table");
    st.innerHTML = `<thead><tr><th>Team</th><th class="num">Mood</th></tr></thead>`;
    const stb = el("tbody");
    const hot = data.sentiment.slice(0, 5);
    const cold = data.sentiment.slice(-3);
    const rows = [...hot, ...cold.filter((r) => !hot.includes(r))];
    for (const r of rows) {
      stb.appendChild(el("tr", r.is_user ? "me" : "", `
        <td><b>${tlink(r.team_id, r.name)}</b> <span class="pill">${esc(r.tag)}</span></td>
        <td class="num ${r.tone ?? ""}">${Math.round(r.sentiment)}
          <span class="muted">${esc(r.word ?? "")}</span></td>`));
    }
    st.appendChild(stb);
    sc.appendChild(st);
    rail.appendChild(sc);
  }

  // Reach leaderboard — the most-followed players; team column tlinks.
  const lb = el("div", "card");
  lb.appendChild(el("h2", "", "Most followed"));
  const t = el("table");
  t.innerHTML = `<thead><tr><th>#</th><th>Player</th><th>Team</th>
    <th class="num">Followers</th></tr></thead>`;
  const tb = el("tbody");
  data.leaderboard.forEach((r, i) => {
    tb.appendChild(el("tr", r.is_user ? "me" : "", `
      <td>${i + 1}</td>
      <td><b>${plink(r.player_id, r.handle)}</b></td>
      <td class="muted">${tlink(r.team_id, r.team_tag)}</td>
      <td class="num">${fmtFollowers(r.followers)}</td>`));
  });
  t.appendChild(tb);
  lb.appendChild(t);
  rail.appendChild(lb);

  // Movement tracker: every signing/release/renewal/transfer league-wide —
  // including AI-to-AI moves — straight off the chronicle. Names are regex-
  // plinked in the prose; the team tag becomes a tlink via the row's team_id.
  const moves = data.movement || [];
  if (moves.length) {
    const mv = el("div", "card");
    mv.appendChild(el("h2", "", "Movement tracker"));
    mv.appendChild(el("p", "muted",
      "Every move in the league, newest first — watch what rival orgs are doing."));
    const KIND_BADGE = {
      signing: ["signing", "good"], release: ["release", "bad"],
      renewal: ["renewal", ""], transfer: ["transfer", "warn"], poach: ["poach", "bad"],
    };
    const scroll = el("div", "card-scroll");
    scroll.style.setProperty("--scroll-max", "340px");
    const list = el("div", "es-movement");
    for (const m of moves) {
      const [label, tone] = KIND_BADGE[m.kind] || [m.kind, ""];
      const text = m.player_id
        ? m.text.replace(/^([\w' .-]+?)(?= joins| re-signs| retires|\.)/,
            `<span class="plink" data-pid="${esc(m.player_id)}">$1</span>`)
        : m.text;
      const teamPill = m.team_tag ? `<span class="pill">${tlink(m.team_id, m.team_tag)}</span> ` : "";
      list.appendChild(el("div", "es-move" + (m.mine ? " mine" : ""),
        `<span class="pill ${tone}">${label}</span> ` +
        `<span class="muted mono">S${m.season}·W${m.week}</span> ` +
        teamPill + text));
    }
    scroll.appendChild(list);
    mv.appendChild(scroll);
    rail.appendChild(mv);
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
  const b = data.breakdown;

  v.appendChild(screenHead("Finances", {
    sub: `${money(data.balance)} banked · net ${b.net >= 0 ? "+" : ""}${money(b.net)}/wk`,
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);
  const main = el("div", "ws-7 ws-col");
  const rail = el("div", "ws-5 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  // Objective chips (shared by active deals + market offers): visible label +
  // bonus, tone from met/live-status, tip from the server's status detail.
  const objChips = (objs) => (objs ?? [])
    .map((o) => {
      const mark = o.met === true ? "✓ " : o.met === false ? "✗ " : "";
      let cls = o.met === true ? "good" : o.met === false ? "bad" : "";
      let prog = "";
      // Undecided objectives show their live in-season status (server aid).
      if (o.met == null && o.status) {
        const st = o.status.state;
        cls = st === "achieved" || st === "on_track" ? "good"
          : st === "missed" ? "bad" : "warn";
        prog = ` · ${st.replace("_", " ")}`;
      }
      const tip = o.status?.detail || money(o.bonus);
      return `<span class="pill obj ${cls}" title="${esc(tip)}">${mark}${esc(o.label)} → ${money(o.bonus)}${prog}</span>`;
    })
    .join(" ");

  /* -- main ws-7: sponsorship slots (restructured — state chip + brand +
     terms + objective chips + action row per slot; no <br> layout) --------- */
  const slotsCard = el("div", "card");
  slotsCard.appendChild(el("h2", "",
    `Sponsorships <span class="muted" style="font-weight:400">— marketability ${data.marketability ?? "?"}</span>`));
  for (const slot of ["title", "jersey", "peripheral", "stream", "apparel"]) {
    const s = data.slots[slot];
    if (!s) continue;
    const block = el("div", "slot-row");
    let stateChip, brand;
    if (s.deal) {
      stateChip = `<span class="chip tone-good">active</span>`;
      brand = `<b>${esc(s.deal.name)}</b> <span class="chip">${esc(s.deal.kind)}</span>`;
    } else if (!s.unlocked) {
      stateChip = `<span class="chip">locked</span>`;
      brand = `<span class="muted">${esc(s.locked_reason ?? "unavailable")}</span>`;
    } else {
      stateChip = `<span class="chip tone-info">open</span>`;
      brand = `<span class="muted">no active deal — ${s.market.length ? "offers below" : "no suitors yet"}</span>`;
    }
    block.appendChild(el("div", "row",
      `${stateChip}<span class="microlabel">${esc(SLOT_LABELS[slot] ?? slot)}</span> ${brand}`));
    if (s.deal) {
      block.appendChild(el("div", "row", `<span class="muted">${esc(dealLine(s.deal))}</span>`));
      const oc = objChips(s.objective_labels_deal);
      if (oc) block.appendChild(el("div", "row offer-row", oc));
    }
    slotsCard.appendChild(block);

    // Legacy single-offer (old saves).
    if (s.offer) {
      const box = el("div", "slot-row");
      box.appendChild(el("div", "row",
        `<span class="chip tone-info">offer</span><b>${esc(s.offer.name)}</b> ` +
        `<span class="chip">${esc(s.offer.kind)}</span> ` +
        `<span class="muted">${esc(dealLine(s.offer))} — expires if unanswered this week</span>`));
      const actions = el("div", "row offer-row");
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
      actions.appendChild(yes);
      actions.appendChild(no);
      box.appendChild(actions);
      slotsCard.appendChild(box);
    }

    // The market: competing brands, pick a payment structure.
    for (const o of s.market ?? []) {
      const box = el("div", "slot-row");
      const relTag = o.relation > 55 ? " · warm relations" : o.relation < 45 ? " · cool relations" : "";
      box.appendChild(el("div", "row",
        `<span class="chip tone-info">offer</span><b>${esc(o.brand)}</b> ` +
        `<span class="muted">${o.weeks}w · until wk ${o.expires_week}${esc(relTag)}</span>`));
      const oc = objChips(o.objective_labels);
      if (oc) box.appendChild(el("div", "row offer-row", oc));
      const actions = el("div", "row offer-row");
      const structures = [
        ["upfront", `${money(o.upfront.signing_bonus)} now + ${money(o.upfront.weekly)}/wk`],
        ["steady", `${money(o.steady.weekly)}/wk`],
        ["performance", `${money(o.performance.weekly)}/wk + ${money(o.performance.per_win)}/win`],
      ];
      for (const [structure, label] of structures) {
        const btn = el("button", "btn btn-sm", `${structure}: ${label}`);
        btn.disabled = !!s.deal;
        btn.title = s.deal ? "slot occupied" : "objective bonuses scale: upfront ×0.7, steady ×1.0, performance ×1.4";
        btn.onclick = async () => {
          const r = await api("/api/actions/sponsor", { slot, accept: true, brand: o.brand, structure });
          toast(r.message); refresh(); render();
        };
        actions.appendChild(btn);
      }
      const no = el("button", "btn btn-sm", "✕");
      no.title = "decline (the brand remembers)";
      no.onclick = async () => {
        const r = await api("/api/actions/sponsor", { slot, accept: false, brand: o.brand });
        toast(r.message); render();
      };
      actions.appendChild(no);
      box.appendChild(actions);
      slotsCard.appendChild(box);
    }
  }
  main.appendChild(slotsCard);

  /* -- main ws-7: facilities ------------------------------------------------- */
  const facCard = el("div", "card");
  facCard.appendChild(el("h2", "", "Facilities"));
  for (const name of ["training_center", "analytics_suite", "marketing_office"]) {
    const f = data.facilities[name];
    if (!f) continue;
    const row = el("div", "row facility-row");
    row.appendChild(el("span", "",
      `<b>${esc(FACILITY_LABELS[name])}</b> ` +
      `<span class="muted">level ${f.level}/${f.max_level} · ${money(f.upkeep)}/wk upkeep</span>`));
    row.appendChild(el("span", "spacer"));
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
  main.appendChild(facCard);

  /* -- rail ws-5: tiles, run-rate, projection, brand value ------------------- */

  // Balance + weekly-net tiles (plus last week's realised figures).
  const tilesCard = el("div", "card");
  tilesCard.appendChild(el("h2", "", "This week"));
  const tiles = el("div", "es-tiles");
  tiles.appendChild(statTile("Balance", money(data.balance)));
  tiles.appendChild(statTile("Net / wk", `${b.net >= 0 ? "+" : ""}${money(b.net)}`,
    { tone: b.net >= 0 ? "good" : "bad" }));
  tiles.appendChild(statTile("Income", money(b.income_total), { tone: "good" }));
  tiles.appendChild(statTile("Expenses", money(b.expense_total), { tone: "bad" }));
  if (data.last_week_income != null) tiles.appendChild(statTile("Last income", money(data.last_week_income)));
  if (data.last_week_expenses != null) tiles.appendChild(statTile("Last exp.", money(data.last_week_expenses)));
  tilesCard.appendChild(tiles);
  rail.appendChild(tilesCard);

  // Itemized weekly run-rate; payroll links to Roster, streaming to Social.
  const bkCard = el("div", "card");
  bkCard.appendChild(el("h2", "", "This week's run rate"));
  const rt = el("table");
  rt.dataset.nosort = "1";
  rt.innerHTML = `<thead><tr><th>Item</th><th class="num">cr / wk</th></tr></thead>`;
  const rtb = el("tbody");
  const line = (label, val, link) => {
    const tr = el("tr", "", `<td>${label}</td><td class="num">${val}</td>`);
    if (link) {
      tr.cells[0].appendChild(document.createTextNode(" "));
      const btn = el("button", "btn btn-sm", link.label);
      btn.onclick = link.onClick;
      tr.cells[0].appendChild(btn);
    }
    return tr;
  };
  rtb.appendChild(line("Base sponsorship", money(b.sponsors_base)));
  rtb.appendChild(line("Title sponsor", money(b.sponsors_by_slot.title || 0)));
  rtb.appendChild(line("Jersey sponsor", money(b.sponsors_by_slot.jersey || 0)));
  rtb.appendChild(line("Peripheral sponsor", money(b.sponsors_by_slot.peripheral || 0)));
  rtb.appendChild(line("Merchandise", money(b.merch)));
  rtb.appendChild(line("Ticket sales", money(b.tickets)));
  rtb.appendChild(line("Streaming", money(b.streaming || 0),
    { label: "→ Social", onClick: () => dashGoTab("social") }));
  rtb.appendChild(line("Prize money", money(b.prizes)));
  rtb.appendChild(el("tr", "", `<td class="mono"><b>Income total</b></td><td class="num mono"><b>${money(b.income_total)}</b></td>`));
  rtb.appendChild(line("Salaries", `-${money(b.salaries)}`,
    { label: "→ Roster", onClick: () => dashGoTab("roster") }));
  rtb.appendChild(line("Staff", `-${money(b.staff)}`));
  rtb.appendChild(line("Facility upkeep", `-${money(b.facility_upkeep)}`));
  rtb.appendChild(el("tr", "", `<td class="mono"><b>Expense total</b></td><td class="num mono"><b>-${money(b.expense_total)}</b></td>`));
  rtb.appendChild(el("tr", "", `<td><b>Net</b></td><td class="num"><b>${b.net >= 0 ? "+" : ""}${money(b.net)}</b></td>`));
  rt.appendChild(rtb);
  bkCard.appendChild(rt);
  bkCard.appendChild(el("p", "muted",
    "A live run-rate snapshot from the current roster, staff, sponsors and facilities — not a ledger of a specific past week."));
  rail.appendChild(bkCard);

  // 8-week cash projection + a tiny balance sparkline.
  const projCard = el("div", "card");
  projCard.appendChild(el("h2", "", "8-week cash projection"));
  const proj = data.projection || [];
  if (proj.length >= 2) {
    const W = 220, H = 46;
    const bals = proj.map((p) => p.balance);
    const lo = Math.min(...bals), hi = Math.max(...bals), span = (hi - lo) || 1;
    const pts = proj.map((p, i) => {
      const x = (i / (proj.length - 1)) * (W - 4) + 2;
      const y = H - 4 - ((p.balance - lo) / span) * (H - 8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    projCard.appendChild(el("div", "es-spark",
      `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="projected balance">` +
      `<polyline points="${pts}" fill="none" class="es-spark-line"/></svg>` +
      `<span class="muted">${money(proj[proj.length - 1].balance)} in ${proj.length}w</span>`));
  }
  const pt = el("table");
  pt.dataset.nosort = "1";
  pt.innerHTML = `<thead><tr><th>Week</th><th class="num">Net</th><th class="num">Balance</th></tr></thead>` +
    `<tbody>${proj.map((p) => `<tr><td>W${p.week}</td>` +
      `<td class="num">${p.net >= 0 ? "+" : ""}${money(p.net)}</td>` +
      `<td class="num">${money(p.balance)}</td></tr>`).join("")}</tbody>`;
  projCard.appendChild(pt);
  projCard.appendChild(el("p", "muted",
    "Assumes current sponsors, facilities and roster hold steady; sponsor slot deals drop off as they expire. Prize money and roster moves aren't modeled."));
  rail.appendChild(projCard);

  // Brand value / marketability drivers.
  const mb = data.marketability_breakdown;
  if (mb && mb.drivers?.length) {
    const mbCard = el("div", "card");
    mbCard.appendChild(el("h2", "",
      `Brand value <span class="muted" style="font-weight:400">— marketability ${mb.score} (facility ×${mb.facility_mult})</span>`));
    const list = el("div", "es-mb");
    const maxAbs = Math.max(...mb.drivers.map((d) => Math.abs(d.contrib)), 0.01);
    for (const d of mb.drivers) {
      const pos = d.contrib >= 0;
      const w = Math.round(100 * Math.abs(d.contrib) / maxAbs);
      list.appendChild(el("div", "es-mb-row",
        `<span class="es-mb-lab">${esc(d.label)}</span>` +
        `<span class="es-mb-track"><span class="es-mb-fill ${pos ? "pos" : "neg"}" style="width:${w}%"></span></span>` +
        `<span class="mono ${pos ? "trend-up" : "trend-down"}">${pos ? "+" : ""}${d.contrib}</span>`));
    }
    mbCard.appendChild(list);
    rail.appendChild(mbCard);
  }
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
      // Show the played week's report (results + replay buttons) — the
      // manager whose ready-up ticked the world got it from advance();
      // everyone else fetches the same report here.
      try {
        const r = await api("/api/report");
        if (r.report) showReport(r.report);
        else toast(`Week ${s.week} — everyone advanced.`);
      } catch {
        toast(`Week ${s.week} — everyone advanced.`);
      }
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
    row.innerHTML = `<span class="pill">${esc(stageLabel(f.stage))}</span>
      <span style="min-width:320px">${mine ? "<b>" : ""}${tlink(f.team_a, f.team_a_name)} vs ${tlink(f.team_b, f.team_b_name)}${mine ? "</b>" : ""}</span>
      <b class="mono">${esc(score)}</b>`;
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
