/* Campaign hub. Pure API consumer — all state lives server-side. */

import { h, render } from 'https://esm.sh/preact@10.19.2';
import { useState, useEffect, useMemo, useRef } from 'https://esm.sh/preact@10.19.2/hooks';
import htm from 'https://esm.sh/htm@3.1.1';
const html = htm.bind(h);

const $ = (s) => document.querySelector(s);
const el = (tag, cls, htmlContent) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (htmlContent !== undefined) n.innerHTML = htmlContent;
  return n;
};
const money = (n) => (n == null ? "—" : n.toLocaleString() + " cr");

window.$ = $;
window.el = el;
window.money = money;

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

window.askBreakdown = askBreakdown;
window.humanize = humanize;
window.esc = esc;
window.plink = plink;
window.tlink = tlink;
window.slink = slink;
window.screenHead = screenHead;
window.toast = toast;
window.api = api;
window.App = App;
window.render = renderApp;
window.fmtFollowers = fmtFollowers;
window.refresh = refresh;
window.dashGoTab = dashGoTab;
window.openNegotiation = (...args) => openNegotiation(...args);
window.openOffer = (...args) => openOffer(...args);
window.attrDetail = (...args) => attrDetail(...args);
window.advanceWeek = async () => {
  const btn = document.getElementById("advance-btn");
  if (btn) btn.click();
};


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
    input.onchange = () => { filters[key] = input.value; renderApp(); };
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
    input.onchange = () => { filters[key] = input.value; renderApp(); };
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
    renderApp();
  };
  addNumber("streamRevenueMin", "Min stream revenue", "cr / wk", { min: 0, step: 100 });
  addSelect("role", "Role", options(players.map((p) => p.role)));
  addSelect("style", "Style", options(players.map((p) => p.playstyle)));
  addSelect("igl", "IGL", ["yes", "no"], "Any");

  if (Object.values(filters).some((value) => value !== "")) {
    const reset = el("button", "btn btn-sm market-filter-reset", "Clear filters");
    reset.onclick = () => { App.marketFilters = { ...MARKET_FILTER_DEFAULTS }; renderApp(); };
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
  if (!confirm(`Return to the lobby? This world${code} remains saved and can be resumed from "Your worlds".`)) return;
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
  // null = the classic start; otherwise a sandbox scenario preset id
  // (server-applied at creation — the client only picks and renders).
  let scenario = null;
  // Sandbox-only fantasy-draft start: tier-1 rosters enter one shared pool
  // and every org (human + AI) snake-drafts its ten before week 1.
  let fantasyDraft = false;
  const worldTeams = () =>
    world === null ? lob.teams : packs.find((p) => p.id === world).teams;
  const renderScenarios = () => {
    const row = $("#ng-scenario-row");
    const box = $("#ng-scenarios");
    const desc = $("#ng-scenario-desc");
    const list = lob.scenarios || [];
    if (gameMode !== "sandbox" || !list.length) {
      scenario = null;
      row.classList.add("hidden");
      desc.classList.add("hidden");
      return;
    }
    row.classList.remove("hidden");
    box.innerHTML = "";
    const mk = (label, id) => {
      const b = el(
        "button",
        "btn" + (scenario === id ? " btn-primary" : ""),
        label
      );
      b.onclick = () => {
        scenario = id;
        renderScenarios();
      };
      box.appendChild(b);
    };
    mk("Standard start", null);
    for (const sc of list) mk(sc.name, sc.id);
    const cur = list.find((x) => x.id === scenario);
    desc.textContent = cur ? cur.blurb : "";
    desc.classList.toggle("hidden", !cur);
  };
  const renderDraftToggle = () => {
    const row = $("#ng-draft-row");
    const box = $("#ng-draft");
    const desc = $("#ng-draft-desc");
    if (gameMode !== "sandbox") {
      fantasyDraft = false;
      row.classList.add("hidden");
      desc.classList.add("hidden");
      return;
    }
    row.classList.remove("hidden");
    box.innerHTML = "";
    const mk = (label, on) => {
      const b = el(
        "button",
        "btn" + (fantasyDraft === on ? " btn-primary" : ""),
        label
      );
      b.onclick = () => {
        fantasyDraft = on;
        renderDraftToggle();
        renderPick(); // the pick grid narrows to tier-1 orgs while drafting
      };
      box.appendChild(b);
    };
    mk("Existing rosters", false);
    mk("Fantasy draft", true);
    desc.textContent =
      "Every pro enters one shared pool and all orgs — you and the AI — " +
      "take turns drafting ten players each (five starters plus " +
      "bench/academy depth) before the season starts.";
    desc.classList.toggle("hidden", !fantasyDraft);
  };
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
        renderScenarios();
        renderDraftToggle();
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
      grid.innerHTML = '<span class="muted">Loading offers…</span>';
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
        .catch(() => (grid.innerHTML = '<span class="muted">Could not load offers.</span>'));
      return;
    }
    if (world === null) {
      // Fictional-world teams are GENERATED from the seed, so re-fetch at
      // the CURRENT seed — otherwise a solo start at a random seed builds a
      // different league than the grid shows (and the pick 422s). Pack
      // worlds are static data, so they keep using the packs payload.
      const grid = $("#ng-teams");
      grid.innerHTML = '<span class="muted">Preparing league…</span>';
      const seed = parseInt($("#ng-seed").value) || 2026;
      api(`/api/lobby/preview?seed=${seed}`)
        .then((r) =>
          renderTeamGrid(
            grid,
            // The fantasy draft is a tier-1 event; Challengers clubs
            // don't enter it, so hide them when the toggle is on.
            fantasyDraft ? r.teams.filter((t) => t.tier === 1) : r.teams,
            (t) =>
              createGame(t.id, shared_, world, "sandbox", scenario, fantasyDraft)
          )
        )
        .catch(
          () => (grid.innerHTML = '<span class="muted">Could not load teams.</span>')
        );
      return;
    }
    renderTeamGrid($("#ng-teams"), worldTeams(), (t) =>
      createGame(t.id, shared_, world, "sandbox", scenario, fantasyDraft)
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
    renderScenarios();
    renderDraftToggle();
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
    renderTeamGrid(
      $("#join-teams"),
      r.fantasy_draft_active ? r.teams.filter((t) => t.tier === 1) : r.teams,
      (t) => joinGame(code, t.id)
    );
  };
  showCreate(false); // default view
}

async function createGame(
  teamId, shared, pack = null, gameMode = "sandbox", scenario = null,
  fantasyDraft = false
) {
  const seed = parseInt($("#ng-seed").value) || 2026;
  const r = await api("/api/new", {
    team_id: teamId, seed, shared, pack, game_mode: gameMode, scenario,
    fantasy_draft: fantasyDraft,
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
  // Fantasy draft in progress: the draft screen (draft.js) IS the app until
  // the last pick resolves — rosters are mid-build, so no tab makes sense.
  if (s.draft_active) {
    $("#context").textContent =
      `Season ${s.season} · Fantasy draft  —  ${s.user_team.name}`;
    $("#balance").textContent = money(s.user_team.balance);
    $("#tabs").classList.add("hidden");
    updateMpChip(s.multiplayer);
    updateSaveControls(s.save);
    renderDraftScreen();
    return;
  }
  $("#tabs").classList.remove("hidden");
  if (typeof stopDraftPolling === "function") stopDraftPolling();
  $("#context").textContent =
    `Season ${s.season} · Week ${s.week} · ${s.phase}  —  ${s.user_team.name}`;
  $("#balance").textContent = money(s.user_team.balance);
  updateMpChip(s.multiplayer);
  updateSaveControls(s.save);
  refreshTabBadges(s); // fire-and-forget: nav badges repaint off this state
  renderApp();
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
  // Sim ahead is solo-only (the endpoint 409s in shared worlds, where the
  // week advances by ready-up) — hide the control rather than tease it.
  const sim = $("#simahead-btn");
  if (sim) sim.classList.toggle("hidden", !!(mp && mp.mode === "shared"));
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
    renderApp();
  };
});

// Old/absorbed tab ids -> [new tab, App sub-tab field, sub-tab id]. Several
// screens merged into workspaces: Standings/Schedule into Season, Roster into
// Club, Scouting into Market. dashGoTab(), renderApp() and inboxGoTab() consult
// this map so every pre-merge deep link (inbox "Go to", stale App.tab values,
// old onclick handlers) lands on the right host tab AND sub-tab.
const TAB_ALIASES = {
  standings: ["season", "seasonTab", "league"],
  schedule: ["season", "seasonTab", "fixtures"],
  scouting: ["market", "marketTab", "scouting"],
  // "Match" is the visible label for the tactics tab; the internal key stays
  // "tactics" so old links keep working, and this alias lets new code say
  // dashGoTab("match") without caring about the internal id.
  match: ["tactics", "tacticsTab", "strategy"],
  // Company replaces the old top-level Finances screen with real Finances /
  // Brand sub-tabs. Keep both retired ids working for inbox and stale links.
  finances: ["company", "companyTab", "finances"],
  social: ["company", "companyTab", "brand"],
};

function renderApp() {
  if (!App.state) return;
  if (App.state.draft_active) return renderDraftScreen();
  // Merged-tab alias: a stale App.tab from before a screen merge lands on its
  // host tab with the right sub-tab preselected (and the nav highlight
  // follows, since no button carries the old id anymore). "roster" is
  // deliberately NOT aliased — a bare roster route still renders the
  // standalone (other-team) roster view opened from a team profile.
  const alias = TAB_ALIASES[App.tab];
  if (alias) {
    App[alias[1]] = alias[2];
    App.tab = alias[0];
    const b = document.querySelector(`#tabs [data-tab="${alias[0]}"]`);
    if (b && !b.classList.contains("active")) {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
    }
  }
  // Each render gets a fresh container; a slower, superseded async render
  // finishes into a detached node instead of double-appending.
  const container = el("div", "tab-panel-active");
  $("#view").replaceChildren(container);
  ({ inbox, dashboard, facilities: window.facilitiesScreen, roster, club, tactics, season, market, stats, company })[App.tab](container);
}

/* -- helpers ------------------------------------------------------------------ */

function bar(value, opts = {}) {
  const cls = opts.invert
    ? value < 35 ? "good" : value < 65 ? "warn" : "bad"
    : value < 35 ? "bad" : value < 65 ? "warn" : "good";
  return `<div class="bar ${cls}" title="${Math.round(value)}"><i style="--target-width:${Math.max(2, Math.min(100, value))}%; width:${Math.max(2, Math.min(100, value))}%"></i></div>`;
}

function stylePill(p) {
  return `<span class="pill-pair"><span class="pill">${p.role}</span> <span class="pill">${p.playstyle}</span></span>`;
}

// Tiny inline trajectory sparkline from a numeric series (e.g. a player's CA
// across dev-history snapshots). Pure presentation — the server owns every
// value; this only maps points into an SVG polyline. A rising line reads
// green, falling red, flat neutral. Degrades to "" for <2 points.
function sparkline(points, opts = {}) {
  const pts = (points || []).filter((n) => n != null).map(Number);
  if (pts.length < 2) return `<span class="es-spark-empty muted">—</span>`;
  const w = opts.w ?? 84, hgt = opts.h ?? 24, pad = 3;
  const lo = Math.min(...pts), hi = Math.max(...pts);
  // Do not turn a tenth-point move into a violent full-height zig-zag. Keep
  // at least 1.5 CA of visual range, centered around the observed series.
  const visualSpan = Math.max(1.5, hi - lo);
  const visualLo = (lo + hi - visualSpan) / 2;
  const dx = (w - pad * 2) / (pts.length - 1);
  const coords = pts.map((v, i) => {
    const x = pad + i * dx;
    const y = pad + (hgt - pad * 2) * (1 - (v - visualLo) / visualSpan);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const trend = pts[pts.length - 1] - pts[0];
  const cls = Math.abs(trend) < 1e-6 ? "flat" : trend > 0 ? "up" : "down";
  const last = coords[coords.length - 1].split(",");
  return `<svg class="es-spark ${cls}" width="${w}" height="${hgt}" viewBox="0 0 ${w} ${hgt}" ` +
    `preserveAspectRatio="xMidYMid meet" aria-hidden="true">` +
    `<polyline points="${coords.join(" ")}" fill="none" stroke-width="1.5" ` +
    `stroke-linejoin="round" stroke-linecap="round"/>` +
    `<circle cx="${last[0]}" cy="${last[1]}" r="1.8"/></svg>`;
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

/* -- club: the squad HQ ------------------------------------------------------
   One workspace for everything about your own org, split into four sub-tabs:
     Squad        — the roster (overview) + lineup + support cards
     Development  — the roster's per-player development plans
     Locker Room  — hierarchy, cliques, duos/feuds + manager promises
     Operations   — academy + staff delegation + culture/media
                    (match prep moved to Match · Prep)
   Squad/Development are the roster() screen hosted here (host: "club"); the
   other two read /api/club. Absorbed the old top-level Roster tab. */
const CLUB_TABS = [
  { id: "squad", label: "Squad" },
  { id: "development", label: "Development" },
  { id: "locker_room", label: "Locker Room" },
  { id: "operations", label: "Operations" },
];

// Retired club sub-tab ids -> new home (promises folded into Locker Room,
// culture into Operations). Keeps stale deep links / saved App state working.
const CLUB_TAB_ALIAS = { promises: "locker_room", culture: "operations" };

async function club(v) {
  let sub = App.clubTab ?? "squad";
  if (CLUB_TAB_ALIAS[sub]) { sub = CLUB_TAB_ALIAS[sub]; App.clubTab = sub; }
  if (sub === "squad" || sub === "development") {
    // Club always shows YOUR squad; a stale opponent-roster selection (from a
    // team profile's "View roster") must not leak into the Club workspace.
    App.rosterTeam = null;
    App.rosterCols = sub === "development" ? "development" : "overview";
    return roster(v, { host: "club" });
  }
  return clubOps(v, sub);
}

// Locker Room / Operations sub-tabs: hierarchy + promises, and academy,
// delegation, media trust + leadership. (Match preparation, the tournament
// six and the series card moved to the Match tab's Prep sub-tab —
// tacticsPrep().)
async function clubOps(v, sub) {
  const d = await api("/api/club");
  v.appendChild(screenHead("Club", {
    sub: `S${App.state.season} · W${App.state.week}`,
    subtabs: CLUB_TABS,
    active: sub,
    onPick: (id) => { App.clubTab = id; renderApp(); },
  }));

  // The transfer window gates academy promotions and releases — surface it on
  // Operations (where those live), not on the Locker Room view.
  if (sub === "operations") {
    const windowCard = el("div", `card ${d.market_window.open ? "" : "alert"}`);
    windowCard.innerHTML = `<h3>${esc(d.market_window.label)}</h3><p class="muted">${esc(d.market_window.detail)}</p>`;
    v.appendChild(windowCard);
  }

  const ws = el("div", "ws");

  if (sub === "operations") {
  // Academy: the affiliate is a real tier-2 team with real results and minutes.
  const ac = el("div", "card ws-6");
  const a = d.academy;
  ac.innerHTML = `<h2>Academy <span class="pill">level ${a.level}</span></h2>` +
    `<p class="muted">Affiliate: ${a.affiliate_id ? tlink(a.affiliate_id, a.affiliate_name) : "None"}. Promotions and send-downs obey the market window.</p>`;
  if (a.next_upgrade_cost) {
    const up = el("button", "btn btn-sm", `Upgrade · ${money(a.next_upgrade_cost)}`);
    up.onclick = async () => { const r = await api("/api/actions/academy_upgrade", {}); toast(r.message); refresh(); };
    ac.appendChild(up);
  }
  const academyRows = el("div", "card-scroll");
  for (const p of a.roster || []) {
    const row = el("div", "entity");
    row.innerHTML = `<span class="entity-name">${plink(p.id, p.handle)}</span><span class="entity-meta">${p.age} · ${esc(p.role)} · CA ${p.ability} / PA ${p.potential_band[0]}–${p.potential_band[1]}</span>`;
    const b = el("button", "btn btn-sm", "Promote");
    b.disabled = !p.owned;
    b.title = p.owned ? "Promote to the first team" : "Another parent organization holds this pathway";
    b.onclick = async () => { const r = await api("/api/actions/academy_move", { player_id: p.id, direction: "promote" }); toast(r.message); refresh(); };
    row.appendChild(b); academyRows.appendChild(row);
  }
  ac.appendChild(academyRows);
  const eligibleDown = (d.registration.players || []).filter((p) => p.age <= 23);
  if (eligibleDown.length) {
    ac.appendChild(el("p", "microlabel", "First team pathways"));
    for (const p of eligibleDown) {
      const row = el("div", "entity");
      row.innerHTML = `<span class="entity-name">${plink(p.id, p.handle)}</span><span class="entity-meta">${p.age} · ${esc(p.role)}</span>`;
      const b = el("button", "btn btn-sm", "Send down");
      b.onclick = async () => { const r = await api("/api/actions/academy_move", { player_id: p.id, direction: "send_down" }); toast(r.message); refresh(); };
      row.appendChild(b); ac.appendChild(row);
    }
  }
  ws.appendChild(ac);

  // Staff policies automate existing renewal/scouting work, not extra output.
  const dc = el("div", "card ws-12");
  const dp = d.delegation.policy;
  dc.innerHTML = `<h2>Staff responsibilities</h2><p class="muted">Delegate repeatable work; staff return only exceptions and the prospect alerts you request.</p>`;
  const trainOn = el("input"); trainOn.type = "checkbox"; trainOn.checked = dp.auto_training;
  const renewOn = el("input"); renewOn.type = "checkbox"; renewOn.checked = dp.auto_renew_core;
  const scoutOn = el("input"); scoutOn.type = "checkbox"; scoutOn.checked = dp.auto_scout;
  const salaryMin = el("input", "sel-sm"); salaryMin.type = "number"; salaryMin.min = "800"; salaryMin.value = dp.renewal_salary_min;
  const salaryMax = el("input", "sel-sm"); salaryMax.type = "number"; salaryMax.min = "800"; salaryMax.value = dp.renewal_salary_max;
  const trigger = el("input", "sel-sm"); trigger.type = "number"; trigger.min = "1"; trigger.max = "16"; trigger.value = dp.renewal_trigger_weeks;
  const region = el("select", "sel-sm");
  for (const x of d.delegation.regions) { const o = el("option", "", humanize(x)); o.value = x; o.selected = x === dp.scout_region; region.appendChild(o); }
  const role = el("select", "sel-sm");
  for (const x of d.delegation.roles) { const o = el("option", "", humanize(x)); o.value = x; o.selected = dp.scout_roles.includes(x); role.appendChild(o); }
  const age = el("input", "sel-sm"); age.type = "number"; age.min = "16"; age.max = "40"; age.value = dp.scout_max_age;
  const alert = el("select", "sel-sm");
  for (const x of d.delegation.alert_levels) { const o = el("option", "", humanize(x)); o.value = x; o.selected = x === dp.alert_level; alert.appendChild(o); }
  const trainPolicyRow = el("div", "row"); trainPolicyRow.append(trainOn, el("span", "", "Delegate weekly training to coach"), el("span", "muted", "Roster-aware focus; rests the squad when needed"));
  const renewRow = el("div", "row"); renewRow.append(renewOn, el("span", "", "Renew core starters automatically"), el("span", "muted", "salary band"), salaryMin, salaryMax, el("span", "muted", "weeks left \u2264"), trigger);
  const scoutRow = el("div", "row"); scoutRow.append(scoutOn, el("span", "", "Scout all"), region, role, el("span", "muted", "age \u2264"), age, el("span", "muted", "alert"), alert);
  const savePolicy = el("button", "btn btn-primary", "Save staff policies");
  savePolicy.onclick = async () => {
    const r = await api("/api/actions/delegation_policy", {
      auto_training: trainOn.checked,
      auto_renew_core: renewOn.checked,
      renewal_salary_min: Number(salaryMin.value),
      renewal_salary_max: Number(salaryMax.value),
      renewal_trigger_weeks: Number(trigger.value),
      auto_scout: scoutOn.checked,
      scout_region: region.value,
      scout_roles: [role.value],
      scout_max_age: Number(age.value),
      alert_level: alert.value,
    });
    toast(r.message); refresh();
  };
  dc.append(trainPolicyRow, renewRow, scoutRow, savePolicy);
  dc.appendChild(el("p", "muted", `${d.delegation.matching_count} players match the current scouting rule${d.delegation.active_scout_player_id ? ` \u00b7 active assignment set` : ""}.`));
  const dr = d.delegation.latest_report;
  if (dr) dc.appendChild(el("div", "newsline", `Last run: ${dr.renewed_player_ids.length} renewals \u00b7 ${dr.alerts.length} alerts \u00b7 ${dr.exceptions.length} exceptions.`));
  ws.appendChild(dc);

  // Media trust + leadership (moved here from the retired Culture sub-tab).
  const mc = el("div", "card ws-12");
  mc.innerHTML = `<h2>Media trust</h2><p class="muted">Press choices persist in player trust, community sentiment and active sponsor relationships. High-stakes prompts have a six-week cooldown.</p>`;
  const trustRow = el("div", "row");
  for (const p of d.media.player_trust || []) trustRow.appendChild(el("span", "pill", `${p.handle} ${Math.round(p.trust)}`));
  mc.appendChild(trustRow);
  for (const h of d.media.history || []) mc.appendChild(el("div", "newsline", `<b>${humanize(h.type_id)}</b> · ${esc(h.summary)}${h.settlement ? `<div class="muted">${esc(h.settlement)}</div>` : ""}`));
  if (d.media.commitment) mc.appendChild(el("p", "muted", "A public derby expectation will settle after the fixture."));
  ws.appendChild(mc);

  // Leadership group and culture sessions.
  const cc = el("div", "card ws-12");
  const c = d.culture;
  cc.innerHTML = `<h2>Culture & leadership</h2><div class="row"><span class="pill">overall ${c.overall}</span><span class="pill">cohesion ${c.cohesion}</span><span class="pill">leadership ${c.leadership}</span><span class="pill">stability ${c.stability}</span></div>`;
  const capSel = el("select", "sel-sm"), c1 = el("select", "sel-sm"), c2 = el("select", "sel-sm"), principle = el("select", "sel-sm");
  for (const p of c.players) {
    for (const sel of [capSel, c1, c2]) { const o = el("option", "", `${p.handle} · ${p.leadership}`); o.value = p.id; sel.appendChild(o); }
  }
  capSel.value = c.captain_id || ""; c1.value = c.council_ids?.[0] || ""; c2.value = c.council_ids?.[1] || "";
  for (const x of d.principles) { const o = el("option", "", humanize(x)); o.value = x; o.selected = x === c.principle; principle.appendChild(o); }
  const controls = el("div", "row"); controls.append(capSel, c1, c2, principle);
  const saveLeaders = el("button", "btn btn-primary", "Set leadership group");
  saveLeaders.onclick = async () => { const council_ids = [...new Set([c1.value, c2.value])].filter((x) => x && x !== capSel.value); const r = await api("/api/actions/leadership", { captain_id: capSel.value, council_ids, principle: principle.value }); toast(r.message); refresh(); };
  const sessions = el("div", "row");
  const welcomeIds = d.culture_sessions.welcome_player_ids || [];
  const newcomer = [...c.players].filter((p) => welcomeIds.includes(p.id)).sort((a, b) => a.tenure_weeks - b.tenure_weeks || a.id.localeCompare(b.id))[0];
  for (const x of d.culture_sessions.available_actions || []) { const b = el("button", "btn btn-sm", humanize(x)); b.onclick = async () => { const r = await api("/api/actions/culture_session", { action: x, player_id: x === "welcome" ? newcomer?.id : null }); toast(r.message); refresh(); }; sessions.appendChild(b); }
  if (d.culture_sessions.cooldown_weeks) sessions.appendChild(el("span", "muted", `${d.culture_sessions.cooldown_weeks}w cooldown`));
  cc.append(controls, saveLeaders, el("p", "microlabel", "Culture session"), sessions);
  cc.appendChild(el("p", "microlabel", "Culture session"));

  // F8 — team identity: a stated commitment to a principle that media and
  // team-moment choices can honor or violate, with real trust/chemistry
  // consequences. Conviction, commitment state and recent violations are all
  // server-computed (culture.culture_snapshot).
  const commitment = c.commitment;
  if (commitment) {
    const idBox = el("div", "culture-identity");
    const conv = Math.round(commitment.conviction ?? 50);
    const committed = !!commitment.committed;
    const principleName = humanize(commitment.principle || c.principle || "balanced");
    idBox.innerHTML = `<h3 class="culture-identity-h">Team identity` +
      `${committed ? ` <span class="pill tone-good">committed</span>` : ` <span class="pill">uncommitted</span>`}</h3>` +
      `<p class="muted">A committed identity is a promise the locker room holds you to. Choices that betray it cost trust, chemistry and morale; choices that honor it deepen conviction.</p>`;
    if (committed) {
      idBox.innerHTML += `<div class="rowbar"><span>Playing as <b>${esc(principleName)}</b></span>` +
        `<span class="rowbar-val">conviction <b class="mono">${conv}</b></span></div>`;
      const convBar = el("div", "");
      convBar.innerHTML = bar(conv);
      idBox.appendChild(convBar);
      if (commitment.identity_betrayed) {
        idBox.appendChild(el("p", "warn", "⚠ A recent public choice betrayed this identity — the room noticed."));
      }
    } else {
      idBox.appendChild(el("p", "muted",
        `Commit to <b>${esc(principleName)}</b> to make it a stated identity. "Balanced" stays uncommitted.`));
    }
    // Commit / re-commit action (disabled for the inert "balanced" principle).
    const canCommit = (commitment.principle || c.principle) && (commitment.principle || c.principle) !== "balanced";
    const commitBtn = el("button", "btn btn-sm" + (committed ? "" : " btn-primary"),
      committed ? "Re-affirm identity" : "Commit to this identity");
    commitBtn.disabled = !canCommit;
    commitBtn.title = canCommit
      ? "Publicly commit the current principle as your team identity"
      : "Choose a principle other than Balanced first (set it in the leadership group above).";
    commitBtn.onclick = async () => {
      const r = await api("/api/actions/commit-principle", { principle: commitment.principle || c.principle });
      toast(r.message); refresh();
    };
    idBox.appendChild(commitBtn);

    const violations = commitment.recent_violations || c.recent_violations || [];
    if (violations.length) {
      idBox.appendChild(el("p", "microlabel", "Identity moments"));
      for (const vln of violations) {
        const honored = vln.honored || vln.kind === "honor";
        idBox.appendChild(el("div", `newsline ${honored ? "" : "culture-violation"}`,
          `<span class="chip ${honored ? "tone-good" : "tone-bad"}">${honored ? "honored" : "violated"}</span> ` +
          `${esc(vln.text || vln.summary || `${humanize(vln.source || "")} · ${humanize(vln.choice_id || "")}`)}` +
          `${vln.week != null ? ` <span class="muted">W${vln.week}</span>` : ""}`));
      }
    }
    cc.appendChild(idBox);
  }
  ws.appendChild(cc);
  } // end operations

  if (sub === "locker_room") {
    // Render Locker Room
    const lrc = el("div", "card ws-12");
    lrc.innerHTML = `<h2>Locker Room</h2><p class="muted">Check the squad hierarchy, cliques, duos, feuds and manager promises.</p>`;
    
    const rosterTeamId = App.state.user_team.id;
    const rd = await api(`/api/roster/${rosterTeamId}`);
    
    const groups = {
      "Team Leaders": [],
      "Influential": [],
      "Core & Rookies": [],
      "Rebels & Outcasts": []
    };
    
    for (const p of rd.players || []) {
      const role = p.hierarchy_role || "core";
      if (role === "incumbent_leader" || role === "council_member") {
        groups["Team Leaders"].push(p);
      } else if (role === "key_influencer" || role === "loyal_lieutenant") {
        groups["Influential"].push(p);
      } else if (role === "volatile_rebel" || role === "outcast") {
        groups["Rebels & Outcasts"].push(p);
      } else {
        groups["Core & Rookies"].push(p);
      }
    }
    
    const groupDiv = el("div", "row", null);
    groupDiv.style.cssText = "display:flex; flex-wrap:wrap; gap:16px; align-items:stretch;";
    for (const [gName, pList] of Object.entries(groups)) {
      const col = el("div", "card", null);
      col.style.cssText = "flex:1; min-width:220px; margin-bottom:0; display:flex; flex-direction:column;";
      col.innerHTML = `<h3 style="border-bottom:1px solid var(--es-color-border-primary, #26324a); padding-bottom:8px; margin-bottom:12px; font-size:13px; text-transform:uppercase; letter-spacing:0.05em;">${gName}</h3>`;
      
      const listContainer = el("div", "", null);
      listContainer.style.cssText = "flex:1; display:flex; flex-direction:column; gap:12px;";
      
      if (!pList.length) {
        listContainer.appendChild(el("p", "muted", "None"));
      } else {
        for (const p of pList) {
          const roleLabel = humanize(p.hierarchy_role);
          const isDanger = ["volatile_rebel", "outcast"].includes(p.hierarchy_role);
          const isLeader = ["incumbent_leader", "council_member"].includes(p.hierarchy_role);
          const isInfluential = ["key_influencer", "loyal_lieutenant"].includes(p.hierarchy_role);
          
          let toneClass = "muted";
          if (isDanger) toneClass = "loss";
          else if (isLeader) toneClass = "win";
          else if (isInfluential) toneClass = "warn";
          
          const item = el("div", "", `
            <div style="font-weight:600; font-size:14px; margin-bottom:4px;">${plink(p.id, p.handle)}</div>
            <div><span class="pill ${toneClass}" style="font-size:10px; padding:2px 6px; text-transform:uppercase;">${roleLabel}</span></div>
          `);
          listContainer.appendChild(item);
        }
      }
      col.appendChild(listContainer);
      groupDiv.appendChild(col);
    }
    lrc.appendChild(groupDiv);
    
    const relSec = el("div", "", null);
    relSec.style.cssText = "margin-top:24px;";
    relSec.innerHTML = `<h2 style="margin-bottom:16px;">Relationships & Cliques</h2>`;
    
    const rels = rd.relationships || { duos: [], feuds: [] };
    const duosList = rels.duos || [];
    const feudsList = rels.feuds || [];
    
    const relDiv = el("div", "row", null);
    relDiv.style.cssText = "display:flex; flex-wrap:wrap; gap:16px;";
    
    const duosCard = el("div", "card ws-6", null);
    duosCard.style.cssText = "flex:1; min-width:300px; margin-bottom:0;";
    duosCard.innerHTML = `<h3 style="display:flex; align-items:center; gap:8px; margin-bottom:14px; font-size:13px; text-transform:uppercase; letter-spacing:0.05em; border-bottom:1px solid var(--es-color-border-primary, #26324a); padding-bottom:8px;">Duos <span class="pill win">Active</span></h3>`;
    if (!duosList.length) {
      duosCard.appendChild(el("p", "muted", "No close duos in the squad."));
    } else {
      const list = el("div", "", null);
      list.style.cssText = "display:flex; flex-direction:column; gap:8px;";
      for (const pair of duosList) {
        const p1 = rd.players.find(p => p.id === pair[0]) || { handle: pair[0] };
        const p2 = rd.players.find(p => p.id === pair[1]) || { handle: pair[1] };
        list.innerHTML += `<div style="padding:4px 0; display:flex; align-items:center; gap:12px;">` +
          `<strong>${plink(p1.id, p1.handle)}</strong> <span class="muted">&harr;</span> <strong>${plink(p2.id, p2.handle)}</strong> ` +
          `<span class="pill win" style="font-size:10px; margin-left:auto;">Friendship Bond</span>` +
          `</div>`;
      }
      duosCard.appendChild(list);
    }
    
    const feudsCard = el("div", "card ws-6", null);
    feudsCard.style.cssText = "flex:1; min-width:300px; margin-bottom:0;";
    feudsCard.innerHTML = `<h3 style="display:flex; align-items:center; gap:8px; margin-bottom:14px; font-size:13px; text-transform:uppercase; letter-spacing:0.05em; border-bottom:1px solid var(--es-color-border-primary, #26324a); padding-bottom:8px;">Feuds <span class="pill loss">Tension</span></h3>`;
    if (!feudsList.length) {
      feudsCard.appendChild(el("p", "muted", "No active feuds in the squad."));
    } else {
      const list = el("div", "", null);
      list.style.cssText = "display:flex; flex-direction:column; gap:8px;";
      for (const pair of feudsList) {
        const p1 = rd.players.find(p => p.id === pair[0]) || { handle: pair[0] };
        const p2 = rd.players.find(p => p.id === pair[1]) || { handle: pair[1] };
        list.innerHTML += `<div style="padding:4px 0; display:flex; align-items:center; gap:12px;">` +
          `<strong>${plink(p1.id, p1.handle)}</strong> <span class="muted">&harr;</span> <strong>${plink(p2.id, p2.handle)}</strong> ` +
          `<span class="pill loss" style="font-size:10px; margin-left:auto;">Grave Friction</span>` +
          `</div>`;
      }
      feudsCard.appendChild(list);
    }
    
    relDiv.appendChild(duosCard);
    relDiv.appendChild(feudsCard);
    relSec.appendChild(relDiv);
    lrc.appendChild(relSec);

    // Promises (moved here from the retired Promises sub-tab — promises are
    // relationship state, so they live below the relationship graph).
    const promSec = el("div", "", null);
    promSec.style.cssText = "margin-top:24px;";
    promSec.innerHTML = `<h2 style="margin-bottom:4px;">Promises</h2><p class="muted">Monitor active manager promises, kept/broken history and morale/chemistry outcomes.</p>`;
    const promisesList = rd.promises || [];
    
    const active = promisesList.filter(p => p.status === "active");
    const history = promisesList.filter(p => p.status !== "active");
    
    const activeDiv = el("div", "", null);
    activeDiv.innerHTML = `<h3>Active Promises</h3>`;
    if (!active.length) {
      activeDiv.appendChild(el("p", "muted", "No active promises at the moment."));
    } else {
      const activeGrid = el("div", "row", null);
      activeGrid.style.cssText = "display:flex; flex-wrap:wrap; gap:12px;";
      for (const prom of active) {
        const duration = prom.initial_duration || 1;
        const pct = Math.max(0, Math.min(100, Math.round((prom.weeks_left / duration) * 100)));
        const pPlayer = rd.players.find(p => p.id === prom.player_id) || { handle: prom.player_id };
        
        let progressInfo = "";
        if (prom.promise_type === "play_time") {
          progressInfo = ` · Dressed ${prom.dressed_count} weeks`;
        }
        
        const card = el("div", "card ws-4", null);
        card.style.cssText = "padding:10px; background:var(--es-color-bg-alt, #0b0e14); border:1px solid var(--es-color-border, #1f2a3d); border-radius:4px;";
        card.innerHTML = `<div>` +
          `<strong>${plink(pPlayer.id, pPlayer.handle)}</strong>: ` +
          `<span style="text-transform:uppercase; font-size:0.85em; color:var(--es-color-accent, #00f0ff);">${prom.promise_type.replace(/_/g, " ")}</span>` +
        `</div>` +
        `<div style="font-size:0.9em; margin:6px 0;">Target: ${prom.target_value || "N/A"}${progressInfo}</div>` +
        `<div style="display:flex; justify-content:space-between; font-size:0.8em; margin-bottom:4px;">` +
          `<span>Progress</span><span>${prom.weeks_left} weeks left</span>` +
        `</div>` +
        `<div class="pf-hbar" style="height:6px; background:var(--es-color-bg, #05070a); border-radius:3px; overflow:hidden;">` +
          `<i style="display:block; height:100%; width:${pct}%; background:var(--es-color-accent, #00f0ff); border-radius:3px;"></i>` +
        `</div>`;
        activeGrid.appendChild(card);
      }
      activeDiv.appendChild(activeGrid);
    }
    promSec.appendChild(activeDiv);
    
    const histDiv = el("div", "", null);
    histDiv.style.cssText = "margin-top:20px;";
    histDiv.innerHTML = `<h3>Promise History</h3>`;
    if (!history.length) {
      histDiv.appendChild(el("p", "muted", "No resolved promise history."));
    } else {
      const histList = el("div", "card-scroll", null);
      for (const prom of history) {
        const pPlayer = rd.players.find(p => p.id === prom.player_id) || { handle: prom.player_id };
        const isKept = prom.status === "kept";
        const badgeClass = isKept ? "win" : "loss";
        const color = isKept ? "#28a745" : "var(--es-color-danger, #ff4655)";
        
        const row = el("div", "entity", null);
        row.innerHTML = `<span class="entity-name">${plink(pPlayer.id, pPlayer.handle)} &middot; ${prom.promise_type.replace(/_/g, " ")}</span>` +
          `<span class="pill ${badgeClass}" style="background:${color}; color:#fff; text-transform:uppercase;">${prom.status}</span>`;
        histList.appendChild(row);
      }
      histDiv.appendChild(histList);
    }
    promSec.appendChild(histDiv);
    lrc.appendChild(promSec);
    ws.appendChild(lrc);
  }

  v.appendChild(ws);
}

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
  if (opts.tooltip) {
    tile.setAttribute("data-tooltip", opts.tooltip);
  } else if (opts.title) {
    tile.title = opts.title;
  }
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
// Pre-merge names route through TAB_ALIASES — the host sub-tab must be
// set BEFORE the click, because the click triggers the render.
function dashGoTab(name) {
  const alias = TAB_ALIASES[name];
  if (alias) { App[alias[1]] = alias[2]; name = alias[0]; }
  const b = document.querySelector(`#tabs [data-tab="${name}"]`);
  if (b) b.click();
}

/* -- Match-day buildup overlay (#matchday) ----------------------------------
   The full pre-match briefing: one composed GET /api/matchday read (enriched
   fixture board, both sides' form + danger men, the opposing bench) laid out
   on the workspace grid. Presentation only — every number arrives computed;
   this renders, deep-links names, and hands off to the game-plan screen. */
async function openMatchday() {
  let md = null;
  try { md = await api("/api/matchday"); } catch (_e) { return; }
  const ov = $("#matchday");
  if (!ov) return;
  ov.innerHTML = "";
  ov.classList.remove("hidden");
  ov.onclick = (e) => { if (e.target === ov) closeMatchday(); };
  const wrap = el("div", "md-wrap");
  ov.appendChild(wrap);

  const f = md && md.fixture;
  if (!f) {
    const empty = el("div", "card");
    empty.appendChild(el("h2", "", "Match day"));
    empty.appendChild(el("p", "muted", "No fixture scheduled this week."));
    const btn = el("button", "btn", "Close");
    btn.onclick = closeMatchday;
    empty.appendChild(btn);
    wrap.appendChild(empty);
    return;
  }
  const you = md.you, them = md.them;
  const season = App.state?.season;
  const ws = el("div", "ws");
  wrap.appendChild(ws);

  // Last-5 form as W/L squares (oldest -> newest, the server's order).
  const formStrip = (chips) => {
    const strip = el("span", "es-form-strip");
    if (!(chips || []).length) strip.appendChild(el("span", "muted", "No results yet"));
    for (const c of chips || []) {
      strip.appendChild(formSquare(c.result, `W${c.week} vs ${c.opponent}${c.score ? " · " + c.score : ""}`));
    }
    return strip;
  };
  // Season danger men: handle + role + rating over the map sample.
  const dangerList = (rows) => {
    const box = el("div", "es-stars md-danger");
    if (!(rows || []).length) {
      box.appendChild(el("span", "muted", "No season sample yet."));
      return box;
    }
    for (const d of rows) {
      box.appendChild(el("span", "es-star",
        plink(d.player_id, d.handle) +
        `<span class="pill">${esc(d.role)}</span>` +
        `<span class="mono muted">${d.rating.toFixed(2)} · ${d.maps} maps</span>`));
    }
    return box;
  };

  // 1. Tale of the tape: VS header, rivalry flag, both form strips, h2h.
  const head = el("div", "card es-matchday ws-12 md-head");
  head.appendChild(el("div", "es-matchday-kicker",
    `${esc(stageLabel(f.stage))}${season ? ` · S${season}` : ""} · W${f.week} · Pre-match briefing`));
  head.appendChild(el("div", "es-vs",
    `<div class="es-vs-team left">${tlink(you.id, you.name, "es-vs-name")}</div>` +
    `<div class="es-vs-mid">
      <div class="es-vs-x">VS</div>
      <span class="pill es-bo">Best of ${f.best_of}</span>
      ${f.rivalry ? `<span class="pill es-rivalry" title="Grudge match — rivalry heat ${f.rivalry}">⚔ RIVALRY</span>` : ""}
    </div>` +
    `<div class="es-vs-team right">${tlink(them.id, them.name, "es-vs-name")}</div>`));
  const forms = el("div", "md-forms");
  const fL = el("div", "md-form left");
  fL.appendChild(el("span", "es-scout-lab muted", `Last ${(you.form || []).length || 0}`));
  fL.appendChild(formStrip(you.form));
  const fR = el("div", "md-form right");
  fR.appendChild(el("span", "es-scout-lab muted", `Last ${(them.form || []).length || 0}`));
  fR.appendChild(formStrip(them.form));
  forms.append(fL, fR);
  head.appendChild(forms);
  if (f.h2h) {
    const h = f.h2h;
    const lead = h.wins === h.losses ? "level" : h.you_lead ? "you lead" : "you trail";
    const hstreak = h.streak_len > 1 ? ` · ${h.streak_team === you.id ? "W" : "L"}${h.streak_len}` : "";
    head.appendChild(el("div", "md-h2h muted",
      `Head-to-head this season: <b>${h.wins}–${h.losses}</b> (${lead})${hstreak}`));
  }
  ws.appendChild(head);

  // 2. Storylines: the grounded prose preview.
  const story = el("div", "card ws-6");
  story.appendChild(el("h2", "", "Storylines"));
  if ((f.preview || []).length) {
    for (const line of f.preview) story.appendChild(el("p", "es-preview muted", esc(line)));
  } else {
    story.appendChild(el("p", "muted", "Nothing on the wire yet — the season will write these."));
  }
  ws.appendChild(story);

  // 3. Opposition read: manager persona, coach, scouted identity, danger men.
  const opp = el("div", "card ws-6");
  opp.appendChild(el("h2", "", `${esc(them.name)} — the read`));
  if (f.opp_manager) {
    opp.appendChild(el("div", "md-row",
      `<span class="es-scout-lab muted">Manager</span>` +
      `<span><b>${esc(f.opp_manager.name)}</b> <span class="pill es-identity">${esc(f.opp_manager.identity)}</span></span>`));
  }
  if (them.coach) {
    opp.appendChild(el("div", "md-row",
      `<span class="es-scout-lab muted">Coach</span>` +
      `<span><b>${esc(them.coach.name)}</b> <span class="pill es-identity">${esc(them.coach.style)}</span> ` +
      `<span class="muted">${esc(them.coach.specialty)} specialist</span></span>`));
  }
  if (them.identity || (them.tendencies || []).length) {
    const row = el("div", "md-row");
    row.appendChild(el("span", "es-scout-lab muted", "Playstyle"));
    const body = el("span", "");
    if (them.identity) body.appendChild(el("span", "pill es-identity", esc(them.identity)));
    if ((them.tendencies || []).length) {
      body.appendChild(el("span", "es-tendencies muted", " " + them.tendencies.map(esc).join(" · ")));
    }
    row.appendChild(body);
    opp.appendChild(row);
  } else if (!them.scouted) {
    opp.appendChild(el("p", "muted", "Their tactical identity is unread — assign your scout to unlock it."));
  }
  opp.appendChild(el("span", "es-scout-lab muted", "Danger men"));
  opp.appendChild(dangerList(them.danger_men));
  ws.appendChild(opp);

  // 4. Map pool & suggested veto (the server's board; hidden until it has data).
  const mp = f.map_pool;
  const maps = el("div", "card ws-6");
  maps.appendChild(el("h2", "", "Map pool & veto"));
  if (mp && mp.veto && (mp.veto.ban || mp.veto.pick)) {
    const vr = el("div", "es-veto");
    if (mp.veto.ban) {
      vr.appendChild(el("span", "es-veto-chip ban",
        `Ban ${mp.veto.ban.map} <span class="muted">(${mp.veto.opponent} ${mp.veto.ban.their_wr}% · you ${mp.veto.ban.our_wr}%)</span>`));
    }
    if (mp.veto.pick) {
      vr.appendChild(el("span", "es-veto-chip pick",
        `Pick ${mp.veto.pick.map} <span class="muted">(you ${mp.veto.pick.our_wr}% · them ${mp.veto.pick.their_wr}%)</span>`));
    }
    maps.appendChild(vr);
  }
  if (mp && mp.maps.length) {
    const bars = el("div", "es-mapbars");
    for (const m of mp.maps.slice(0, 7)) {
      const wr = m.win_rate == null ? 0 : m.win_rate;
      bars.appendChild(el("div", "es-mapbar",
        `<span class="es-mapbar-name">${esc(m.map)}</span>` +
        `<span class="es-mapbar-track"><span class="es-mapbar-fill" style="width:${wr}%"></span></span>` +
        `<span class="mono es-mapbar-wr">${m.win_rate == null ? "—" : m.win_rate + "%"}</span>` +
        `<span class="muted es-mapbar-n">${m.wins}/${m.played}</span>`));
    }
    maps.appendChild(bars);
  }
  if (maps.childElementCount <= 1) {
    maps.appendChild(el("p", "muted", "No map record yet this season."));
  }
  ws.appendChild(maps);

  // 5. Your side: who the opposition will be worrying about.
  const mine = el("div", "card ws-6");
  mine.appendChild(el("h2", "", `${esc(you.name)} — your threats`));
  mine.appendChild(dangerList(you.danger_men));
  ws.appendChild(mine);

  // 6. Hand-off: into the game-plan screen, or back to the dashboard.
  const foot = el("div", "card ws-12 md-foot");
  foot.appendChild(el("span", "muted",
    md.plan_set
      ? "A game plan is locked for this fixture."
      : "No opponent-specific plan is set yet — lock the approach before you advance."));
  foot.appendChild(el("span", "spacer"));
  const plan = el("button", "btn btn-primary",
    (md.plan_set ? "Review game plan" : "Set game plan") + " ▸");
  plan.onclick = () => { closeMatchday(); App.tacticsTab = "gameplan"; dashGoTab("tactics"); };
  const cont = el("button", "btn", "Continue");
  cont.onclick = closeMatchday;
  foot.append(plan, cont);
  ws.appendChild(foot);
}

function closeMatchday() {
  const ov = $("#matchday");
  if (!ov) return;
  ov.classList.add("hidden");
  ov.innerHTML = "";
  ov.onclick = null;
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

  // The manager-career overlay's entry point rides the screen head (the old
  // "Manager career" card is gone — the profile overlay owns that detail).
  const headRight = [];
  if (career && career.name && typeof openManagerProfile === "function") {
    const careerBtn = el("button", "btn btn-sm", "Career ▸");
    careerBtn.onclick = () => openManagerProfile(career);
    headRight.push(careerBtn);
  }
  v.appendChild(screenHead("Dashboard", {
    sub: `S${s.season} · W${s.week} · ${cap(String(s.phase || "").replace(/_/g, " "))}`,
    right: headRight,
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);

  /* -- 1. STATUS STRIP: six core vitals in one saccade ----------------------
     Deliberately lean — Record, League, the season stake (Board in legacy,
     else current Streak), Balance, Morale, Condition. Chemistry, scout
     progress and the training focus each have a fuller home below (Club squad
     profile, the match-day readiness pills / action items, and the match-day
     development card), so they're not duplicated as tiles here. */
  const strip = el("div", "card ws-12 es-status");
  const tiles = el("div", "es-tiles");
  const rec = me.record;
  if (rec) {
    tiles.appendChild(statTile("Record", `${rec.wins}–${rec.losses}`, {
      sub: `${rec.diff > 0 ? "+" : ""}${rec.diff} rd`,
      tooltip: "<h4>Match Record</h4><div class='tooltip-desc'>Your team's current win-loss record for the regular season, plus total round differential.</div>"
    }));
  }
  if (posOf[myId]) {
    tiles.appendChild(statTile("League", ordinal(posOf[myId]), {
      sub: cap(regionOf[myId] || me.region || ""),
      onClick: () => dashGoTab("standings"),
      tooltip: "<h4>League Standing</h4><div class='tooltip-desc'>Your current position in the regional league standings. Click to view the full Season table.</div>"
    }));
  }
  // Season stake: the board's sack-race band in legacy, else the live streak.
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
      tooltip: `<h4>Board confidence</h4><div class='tooltip-desc'>The board's current patience: <b>${b.band}</b>. Target: <b>${b.goal}</b> (${b.goal_state}). If it runs out, you may be dismissed.</div>`
    }));
  } else {
    const streak = streakOf(myId);
    if (streak) {
      tiles.appendChild(statTile("Streak", streak.txt, {
        tone: streak.won ? "good" : "bad",
        tooltip: "<h4>Win/Loss Streak</h4><div class='tooltip-desc'>Your team's consecutive wins (W) or losses (L) streak.</div>"
      }));
    }
  }
  tiles.appendChild(statTile("Balance", money(me.balance), {
    onClick: () => dashGoTab("finances"),
    tooltip: "<h4>Club balance</h4><div class='tooltip-desc'>Total club funds. Running out of money can lead to insolvency. Open Finances to manage sponsors and costs.</div>"
  }));
  if (myRoster && myRoster.players.length) {
    const avg = (k) =>
      myRoster.players.reduce((a, p) => a + (p[k] || 0), 0) / myRoster.players.length;
    const mor = avg("morale"), cond = avg("stamina");
    tiles.appendChild(statTile("Morale", Math.round(mor), {
      tone: statTone(mor),
      tooltip: "<h4>Squad morale</h4><div class='tooltip-desc'>Average squad morale. It affects player confidence and response to development plans.</div>"
    }));
    tiles.appendChild(statTile("Condition", Math.round(cond), {
      tone: statTone(cond),
      onClick: () => { App.clubTab = "squad"; dashGoTab("club"); },
      tooltip: "<h4>Squad condition</h4><div class='tooltip-desc'>Average physical condition. Low condition reduces match performance. Open Club to adjust training plans.</div>"
    }));
  }
  strip.appendChild(tiles);
  ws.appendChild(strip);

  // (The old ws-12 "Action required" band is gone — media/flavor prompts and
  // transfer offers now live in the rail's merged "Needs you" card.)
  const sug = s.suggested_lineup;
  const flavor = s.flavor_event;
  const media = s.media_event;

  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  /* -- 3. MATCH DAY hero: the staff's one-stop prep briefing ---------------- */
  const spot = el("div", "card ws-12 es-spotlight es-matchday");
  if (fix) {
    const region = cap(regionOf[myId] || me.region || "");
    const stageTxt =
      fix.stage === "regular" ? `${region} League` : stageLabel(fix.stage).toUpperCase();
    const burnoutWatch = (s.rotation || []).filter((r) => r.burnout);
    const scoutOnOpponent = s.scout && s.scout.target === oppId;
    const scoutPct = scoutOnOpponent ? Math.round((s.scout.progress || 0) * 100) : 0;
    const planSet = !!(gameplan && gameplan.plan);

    const heroTop = el("div", "es-matchday-top");
    heroTop.appendChild(el("div", "",
      `<span class="es-matchday-kicker">W${fix.week} · Staff briefing</span>` +
      `<h2>Match day</h2>` +
      `<p class="muted">Everything to settle before you advance the week.</p>`));
    const readiness = el("div", "es-readiness",
      `<span class="pill ${planSet ? "good" : "warn"}">${planSet ? "Plan locked" : "Plan needed"}</span>` +
      `<span class="pill ${scoutPct >= 50 ? "good" : ""}">${scoutOnOpponent ? scoutPct + "% scouted" : "Scout elsewhere"}</span>` +
      `<span class="pill ${burnoutWatch.length ? "warn" : "good"}">${burnoutWatch.length ? burnoutWatch.length + " load risk" : "Squad ready"}</span>`);
    const mdBtn = el("button", "btn btn-sm md-open", "Match day briefing ▸");
    mdBtn.title = "The full pre-match buildup: storylines, form, danger men, maps";
    mdBtn.onclick = openMatchday;
    readiness.appendChild(mdBtn);
    heroTop.appendChild(readiness);
    spot.appendChild(heroTop);

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
          ${fix.opp_manager ? `<div class="es-vs-ctx es-opp-mgr" title="The manager across the aisle">vs ${esc(fix.opp_manager.name)} · <i>${esc(fix.opp_manager.identity)}</i></div>` : ""}
        </div>` +
        teamBlock(oppId, oppName, oppLogo, "right")));

    // Staff briefing: facts already computed by the campaign/server become
    // concise decisions here. Each recommendation deep-links to its owner.
    const prep = el("div", "es-prep");
    prep.appendChild(el("div", "es-prep-head",
      `<div><span class="microlabel">Today's prep</span><b>${esc(oppName)} in W${fix.week}</b></div>` +
      `<span class="muted">Set the five, build the plan, sharpen the week.</span>`));
    const prepGrid = el("div", "es-prep-grid");
    const prepCard = (role, title, copy, status, tone, action, onClick) => {
      const card = el("div", `es-prep-card ${tone || ""}`,
        `<div class="es-prep-role"><span>${role}</span><span class="pill ${tone === "urgent" ? "warn" : tone === "ready" ? "good" : ""}">${status}</span></div>` +
        `<b class="es-prep-title">${title}</b>` +
        `<p class="muted">${copy}</p>`);
      const go = el("button", "btn btn-sm", action + " ▸");
      go.onclick = onClick;
      card.appendChild(go);
      prepGrid.appendChild(card);
      return card;
    };

    const lineupIns = (sug?.players || []).filter((p) => !p.dressed);
    const rosterTitle = sug?.changed ? "Review the suggested five"
      : burnoutWatch.length ? `Protect ${esc(burnoutWatch[0].handle)}'s legs`
      : "Keep the match five settled";
    const rosterCopy = sug?.changed
      ? `${lineupIns.map((p) => plink(p.id, p.handle)).join(" and ")} rate among your best available options. Confirm the five and any map overrides.`
      : burnoutWatch.length
        ? `${plink(burnoutWatch[0].id, burnoutWatch[0].handle)} is carrying a heavy map load. Check the rotation before locking the lineup.`
        : "No lineup change is being flagged. Use the roster desk for roles, map lineups, and final availability.";
    prepCard("Assistant coach", rosterTitle, rosterCopy, sug?.changed || burnoutWatch.length ? "Review" : "Stable",
      sug?.changed || burnoutWatch.length ? "urgent" : "ready", "Open roster", () => {
        App.clubTab = "squad"; dashGoTab("club");
      });

    prepCard("Head coach", planSet ? "Pressure-test the game plan" : "Turn the brief into a game plan",
      planSet ? "The plan is locked. Recheck the approach, target, map ideas, and match-day team talk."
        : "No opponent-specific plan is set yet. Commit the tactical approach and prep edge before the match.",
      planSet ? "Set" : "Priority", planSet ? "ready" : "urgent", planSet ? "Review plan" : "Build plan", () => {
        App.tacticsTab = "gameplan"; dashGoTab("tactics");
      });

    prepCard("Analyst", scoutOnOpponent ? `Turn ${scoutPct}% coverage into edges` : `Put the book on ${esc(oppName)}`,
      scoutOnOpponent
        ? (scoutPct >= 50 ? "The identity read is coming into focus. Review tendencies, danger players, and map evidence before finalizing the plan."
          : "Coverage is building. Keep the assignment active, then use verified reads instead of guessing at their setup.")
        : `Your scout is not assigned to ${esc(oppName)}. Switch coverage if this match is the priority.`,
      scoutOnOpponent ? `${scoutPct}%` : "Unassigned", scoutPct >= 50 ? "ready" : "urgent", "Scouting desk", () => dashGoTab("scouting"));

    const devPlayer = (s.movers || []).find((m) => m.delta < 0) || (s.movers || [])[0];
    const devTitle = burnoutWatch.length ? "Ease the load, keep growth targeted"
      : devPlayer ? `Check ${esc(devPlayer.handle)}'s development plan`
      : `Align development with ${cap(s.training_focus)}`;
    const devCopy = burnoutWatch.length
      ? "Balance individual intensity against match readiness, then choose the team focus for the week."
      : devPlayer
        ? `${plink(devPlayer.pid, devPlayer.handle)} moved ${devPlayer.delta > 0 ? "up" : "down"} this week. Confirm focus, intensity, and mentorship while setting team training.`
        : "Set the weekly team focus, then make sure individual focus and intensity support the players who need the work.";
    // The team-training-focus selector itself lives on Club → Development
    // (teamTrainingFocusCard) — the hero only deep-links there.
    prepCard("Performance", devTitle, devCopy, cap(s.training_focus),
      burnoutWatch.length ? "urgent" : "", "Development plans", () => {
        App.clubTab = "development"; dashGoTab("club");
      });
    prep.appendChild(prepGrid);
    spot.appendChild(prep);

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
    if (cols.childElementCount) {
      const intel = el("div", "es-intel");
      intel.appendChild(el("div", "es-intel-head",
        `<span class="microlabel">Match intelligence</span><span class="muted">Opponent, form, maps and run-in</span>`));
      intel.appendChild(cols);
      spot.appendChild(intel);
    }
  } else {
    spot.appendChild(el("h2", "", "Match day"));
    spot.appendChild(el("p", "muted", `No fixture scheduled — ${esc(String(s.phase || ""))}.`));
  }
  ws.insertBefore(spot, main);

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
          // Lever -> destination. "training"/"roster" both land in the Club
          // squad HQ (development plans / squad); "tactics" is standalone.
          const goOf = {
            tactics: () => dashGoTab("tactics"),
            training: () => { App.clubTab = "development"; dashGoTab("club"); },
            roster: () => { App.clubTab = "squad"; dashGoTab("club"); },
          };
          const ll = el("div", "es-review-levers");
          for (const lv of lmr.levers) {
            const row = el("div", "es-review-lever" + (lv.on_focus ? " on-focus" : ""),
              `<span class="es-review-arrow">▸</span> ${esc(lv.text)}`);
            row.onclick = goOf[lv.tab] || goOf.tactics;
            ll.appendChild(row);
          }
          card.appendChild(ll);
        } else if (lmr.coach && !lmr.coach.present) {
          card.appendChild(el("p", "muted es-review-d", "Hire a coach for tailored fixes."));
        }
        // ("Your calls" — the manager-attribution block — moved to its own
        // rail card, merged with the settled-decision ledger.)
        if (lmr.locked && lmr.locked_hint) {
          card.appendChild(el("p", "muted es-review-d", esc(lmr.locked_hint)));
        }
      }
    }
    main.appendChild(card);
  }

  /* -- 5. RAIL: decisions first, then context ------------------------------- */

  // 5a. Needs you: ONE card for everything waiting on the manager — the old
  // Action items, Objectives, and transfer-offer alert cards merged. The list
  // comes from computeNeedsYou (pure, reused later for nav badges); the
  // media/flavor prompts and transfer offers keep their inline actions.
  {
    const unread = (typeof inboxUnread !== "undefined" && inboxUnread) ? inboxUnread : 0;
    const needs = computeNeedsYou(Object.assign({}, s, { gameplan, inbox_unread: unread }));
    const urgent = needs.some((n) => n.kind === "media" || n.kind === "flavor" || n.kind === "offer");
    const card = el("div", "card" + (urgent ? " alert" : ""));
    card.appendChild(el("h2", "", "Needs you"));

    // Interactive event prompts render in full (a list row can't hold the
    // choice buttons); computeNeedsYou still counts them for the badges.
    const eventBlock = (ev, kicker, endpoint, fallbackDone) => {
      const event = el("div", "flavor-event");
      event.appendChild(el("div", "microlabel", kicker));
      event.appendChild(el("h3", "", ev.title || "A decision is waiting"));
      event.appendChild(el("p", "", ev.prompt || "Choose how to respond."));
      const choices = el("div", "row flavor-choices");
      for (const choice of ev.choices ?? []) {
        const wrap = el("div", "tile");
        const button = el("button", "btn btn-sm", choice.label || "Respond");
        button.onclick = async () => {
          const all = [...choices.querySelectorAll("button")];
          all.forEach((b) => (b.disabled = true));
          try {
            const r = await api(endpoint, { event_id: ev.id, choice_id: choice.id });
            toast(r.message || fallbackDone); refresh();
          } catch (_e) {
            all.forEach((b) => (b.disabled = false));
          }
        };
        wrap.appendChild(button);
        if (choice.impact) wrap.appendChild(el("div", "muted", choice.impact));
        choices.appendChild(wrap);
      }
      event.appendChild(choices);
      card.appendChild(event);
    };
    if (media) {
      eventBlock(media, `High-stakes media · ${media.outlet || "press wire"}`,
        "/api/actions/media_event", "Answered.");
    }
    if (flavor) {
      eventBlock(flavor, "Team moment",
        "/api/actions/flavor_event", "Your response is out in the world.");
    }

    const list = el("div", "es-obj");
    const goOf = (it) => () => {
      if (it.tab === "club" && it.subtab) App.clubTab = it.subtab;
      if (it.tab === "tactics" && it.subtab) App.tacticsTab = it.subtab;
      dashGoTab(it.tab);
    };
    for (const it of needs) {
      if (it.kind === "media" || it.kind === "flavor") continue; // rendered above
      const row = el("div", "es-obj-row es-action",
        `<span class="es-review-arrow">▸</span> <span>${it.label}` +
        `${it.detail ? ` <span class="muted">${it.detail}</span>` : ""}</span>`);
      if (it.kind === "offer" && it.offer) {
        const o = it.offer;
        row.appendChild(el("span", "spacer"));
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
      } else if (it.tab && it.tab !== "dashboard") {
        row.style.cursor = "pointer";
        row.onclick = goOf(it);
      }
      list.appendChild(row);
    }
    if (!list.childElementCount && !media && !flavor) {
      list.appendChild(el("div", "muted", "All clear — advance when ready."));
    }
    card.appendChild(list);
    rail.appendChild(card);
  }

  // 5b. Your calls: the manager-attribution block (formerly inside Match
  // review) merged with the settled-decision ledger. Every number arrives
  // computed from the server (tactics_fit impact, prep edge, ratings,
  // decision_ledger) — this only formats rows. The week-reveal overlay keeps
  // its own ledger rendering.
  {
    const yc = lmr && lmr.contested ? lmr.your_calls : null;
    const ledger = s.decision_ledger || [];
    if (yc || ledger.length) {
      const card = el("div", "card");
      card.appendChild(el("h2", "", "Your calls"));
      if (yc) {
        const yl = el("div", "es-review-calls");
        const yrow = (html) => yl.appendChild(
          el("div", "es-review-call", `<span class="es-review-arrow">▸</span> ${html}`));
        for (const d of yc.dials || []) {
          let imp = "";
          if (d.impact_delta != null) {
            const v = d.impact_delta;
            const cls = v > 0 ? "wl-w" : v < 0 ? "wl-l" : "";
            imp = ` <span class="${cls} mono">(${v > 0 ? "+" : ""}${v.toFixed(1)} execution)</span>`;
          }
          yrow(`${esc(d.label)} <b class="mono">${d.planned}</b> vs book <span class="mono">${d.base}</span>${imp}`);
        }
        if (yc.site_focus && yc.site_focus !== "balanced") {
          yrow(`Site call: <b class="mono">${esc(String(yc.site_focus).toUpperCase())}</b>`);
        }
        if (yc.focus_target) {
          yrow(`Focused prep on ${plink(yc.focus_target.player_id, yc.focus_target.handle)}`);
        }
        if (yc.team_talk) {
          const t = yc.team_talk;
          yrow(`${esc(t.label)} — confidence ${t.avg_delta >= 0 ? "+" : ""}${t.avg_delta.toFixed(1)} per starter`);
        }
        if (yc.lineup) {
          if (yc.lineup.override) yrow("One-match lineup set for this fixture");
          for (const p of yc.lineup.picked || []) {
            const r = p.rating != null ? ` — went <b class="mono">${p.rating.toFixed(2)}</b>` : "";
            yrow(`Dressed ${plink(p.player_id, p.handle)} over the suggested five${r}`);
          }
          if ((yc.lineup.benched || []).length) {
            yrow(`Sat from the suggestion: ${yc.lineup.benched.map((p) => plink(p.player_id, p.handle)).join(", ")}`);
          }
          if (yc.lineup.followed && yc.lineup.override) {
            yrow("Lineup matched the suggested five");
          }
        }
        if (yc.prep) {
          const bits = [];
          if (yc.prep.edge != null) bits.push(`prep edge <b class="mono">+${yc.prep.edge.toFixed(2)}</b> applied`);
          if ((yc.prep.maps_played || []).length) bits.push(`book on ${yc.prep.maps_played.map(esc).join(", ")}`);
          if ((yc.prep.maps_missed || []).length) bits.push(`prepped ${yc.prep.maps_missed.map(esc).join(", ")} (never played)`);
          if (bits.length) yrow(`Preparation: ${bits.join(" · ")}`);
        }
        if (yl.childElementCount) {
          card.appendChild(el("span", "es-scout-lab muted", "Last match"));
          card.appendChild(yl);
        }
      }
      if (ledger.length) {
        card.appendChild(el("span", "es-scout-lab muted", "Decisions settled"));
        const list = el("div", "es-obj");
        const vcls = { paid_off: "good", backfired: "bad", neutral: "" };
        const vlab = { paid_off: "paid off", backfired: "backfired", neutral: "neutral" };
        for (const r of ledger.slice(0, 3)) {
          list.appendChild(el("div", "es-obj-row",
            `<span class="pill obj ${vcls[r.verdict] ?? ""}">${esc(vlab[r.verdict] || r.verdict)}</span> ` +
            `<span>${esc(r.text)}</span>`));
        }
        card.appendChild(list);
      }
      if (card.childElementCount > 1) rail.appendChild(card);
    }
  }

  // 5c. League snapshot: the mini-table plus your last result, one card at
  // the bottom of the main column. Season owns the full results list and
  // Stats owns the rating leaders.
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
    // Last result folded in (the old Recent results card is gone — Season
    // owns the full list).
    const lastGame = playedFor(myId).slice(-1)[0];
    if (lastGame) {
      const ln = lineFor(lastGame, myId);
      card.appendChild(el("span", "es-scout-lab muted", "Last result"));
      card.appendChild(el("div", "row es-result",
        `<span class="pill ${ln.res === "W" ? "win" : "loss"}">${ln.res}</span>` +
          `${tlink(ln.opp, ln.oppName, "es-result-opp")}` +
          `<span class="spacer"></span>` +
          `<b class="mono es-result-score">${ln.score}</b>` +
          `<span class="es-result-maps">${ln.maps.map((m) => mapThumb(m, "sm")).join("")}</span>`));
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
    main.appendChild(card);
  }

  // 5d. News + on this day.
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

  // (The "Manager career" card is gone — the head's Career button opens the
  // manager profile overlay, which carries the reputation bars, tags, goal
  // detail and timeline.)
}

// Compact follower count: 12,400 -> "12.4K", 1,200,000 -> "1.2M".
function fmtFollowers(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
}

// Everything currently waiting on the manager, as plain data — derived ONLY
// from already-serialized state. `data` is the /api/state payload, optionally
// augmented with `gameplan` (the /api/gameplan payload) and `inbox_unread`
// (a count) when the caller has them. Pure (no DOM, no fetches) so the
// dashboard card and the nav badges can share it. Each item:
//   { tab, subtab?, kind, label, detail, action, needs_action } — label/detail
// may carry plink/tlink HTML strings. `needs_action` marks a genuine decision
// waiting on the manager (an offer, an expiring contract, an unset game plan);
// informational context (board posture, objective pacing) stays false so the
// nav badges never light up for mere news.
function computeNeedsYou(data) {
  const s = data || {};
  const items = [];
  if (s.media_event) {
    items.push({ tab: "dashboard", kind: "media", action: "Respond", needs_action: true,
      label: `Media: ${esc(s.media_event.title || "the press wants an answer")}`,
      detail: esc(s.media_event.outlet || "press wire") });
  }
  if (s.flavor_event) {
    items.push({ tab: "dashboard", kind: "flavor", action: "Respond", needs_action: true,
      label: esc(s.flavor_event.title || "A decision is waiting"),
      detail: "team moment" });
  }
  for (const o of s.transfer_offers ?? []) {
    const bits = [];
    if ((o.offer_players ?? []).length) {
      bits.push(o.offer_players.map((pl) => `<b>${plink(pl.id, pl.handle)}</b>`).join(" + "));
    }
    if (o.cash_to_seller) bits.push(`<b class="mono">${money(o.cash_to_seller)}</b>`);
    if (o.cash_to_buyer) bits.push(`<span class="muted">(you send back ${money(o.cash_to_buyer)})</span>`);
    const gets = bits.length ? bits.join(" + ") : `<b class="mono">${money(o.fee)}</b>`;
    items.push({ tab: "dashboard", kind: "offer", action: "Decide", offer: o, needs_action: true,
      label: `${tlink(o.to_team, o.to_team_name)} offer ${gets} for <b>${plink(o.player_id, o.handle)}</b>`,
      detail: `expires W${o.expires_week}` });
  }
  for (const e of (s.squad_profile?.expiries ?? []).filter((e) => e.weeks_left > 0 && e.weeks_left <= 8)) {
    items.push({ tab: "club", subtab: "squad", kind: "contract", action: "Renew", needs_action: true,
      label: `${plink(e.id, e.handle)} contract up in <b class="mono">${e.weeks_left}w</b>`,
      detail: "" });
  }
  if (s.scout && s.scout.target && (s.scout.progress || 0) >= (s.scout.cap || 1)) {
    items.push({ tab: "scouting", kind: "scout", action: "Read", needs_action: true,
      label: `Scout report ready — ${esc(s.scout.target_name || "target")}`, detail: "" });
  }
  if (s.next_fixture && s.gameplan && !s.gameplan.plan) {
    items.push({ tab: "tactics", subtab: "gameplan", kind: "gameplan", action: "Build", needs_action: true,
      label: `No game plan set for W${s.next_fixture.week}`, detail: "" });
  }
  if ((s.inbox_unread || 0) > 0) {
    items.push({ tab: "inbox", kind: "inbox", action: "Open", needs_action: true,
      label: `${s.inbox_unread} unread inbox message${s.inbox_unread > 1 ? "s" : ""}`,
      detail: "" });
  }
  // F3 — a player is owed a decision (a bench-minutes demand / promise
  // doorway is open in the Locker Room).
  if (s.promise_pending) {
    const n = Number(s.promise_pending) || 1;
    items.push({ tab: "club", subtab: "locker_room", kind: "promise", action: "Respond", needs_action: true,
      label: `${n > 1 ? n + " players are" : "A player is"} waiting on a promise`, detail: "Locker Room" });
  }
  // F7 — the coach has a scrim plan proposed for the next fixture (one-click
  // accept lives on Match · Prep).
  if (s.scrim_proposal_pending) {
    items.push({ tab: "tactics", subtab: "prep", kind: "scrim", action: "Accept", needs_action: true,
      label: "Coach proposed a scrim plan", detail: "Match · Prep" });
  }
  // F8 — a public choice betrayed the committed team identity; acknowledge it
  // on Operations.
  if (s.culture_violation_unack) {
    items.push({ tab: "club", subtab: "operations", kind: "culture", action: "Review", needs_action: true,
      label: "A choice betrayed your team identity", detail: "Culture" });
  }
  // F4 — the pro fill-gap sweep produced a fresh shortlist (a recommendation,
  // not a decision, so it surfaces without lighting a nav badge).
  if (s.scout_shortlist_ready) {
    items.push({ tab: "scouting", kind: "shortlist", action: "Review", needs_action: false,
      label: "Scouting shortlist updated", detail: "Market · Scouting" });
  }
  // Board + objectives appear only when they actually need attention — but
  // they're context, not decisions, so they never drive a nav badge.
  if (s.board && !(s.board.band === "secure" || s.board.band === "stable")) {
    items.push({ tab: "standings", kind: "board", action: "Review", needs_action: false,
      label: `Board ${esc(s.board.band)} — goal: ${esc(s.board.goal || "")}`,
      detail: esc((s.board.goal_state || "").replace(/_/g, " ")) });
  }
  for (const o of (s.objectives_hub ?? []).slice(0, 6)) {
    const ok = o.state === "achieved" || o.state === "on_track" || o.state === "leading";
    if (ok) continue;
    items.push({ tab: "standings", kind: "objective", action: "Chase", needs_action: false,
      label: esc(o.label),
      detail: `${esc(o.kind)} · ${esc((o.state || "").replace(/_/g, " "))}${o.detail ? " · " + esc(o.detail) : ""}` });
  }
  return items;
}
window.computeNeedsYou = computeNeedsYou;

// One attention model: the SAME computeNeedsYou list that fills the Dashboard
// "Needs you" card drives small count badges on the nav tab buttons. Only
// items tagged needs_action count (a decision genuinely waiting) — board
// posture and objective pacing never light a tab. The Inbox tab is skipped
// entirely: its badge keeps its own unread-count source (inbox.js).
function updateTabBadges(data) {
  const counts = {};
  for (const it of computeNeedsYou(data || {})) {
    if (!it.needs_action) continue;
    // Resolve merged-screen tabs (scouting -> market, standings -> season)
    // to the nav button that actually exists.
    const tab = TAB_ALIASES[it.tab] ? TAB_ALIASES[it.tab][0] : it.tab;
    if (tab === "inbox") continue; // inbox.js owns that badge
    counts[tab] = (counts[tab] || 0) + 1;
  }
  document.querySelectorAll("#tabs .tab").forEach((btn) => {
    if (btn.dataset.tab === "inbox") return;
    const n = counts[btn.dataset.tab] || 0;
    let badge = btn.querySelector(".tab-badge");
    if (!n) { if (badge) badge.remove(); return; }
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "tab-badge";
      btn.appendChild(badge);
    }
    badge.textContent = n > 99 ? "99+" : String(n);
  });
}

// Badge refresh rides every state refresh. The game-plan check needs
// /api/gameplan (not part of /api/state), so pull it here — same payload the
// dashboard card fetches — then repaint. Callers fire-and-forget: badges
// land right after the screen render, never blocking it.
async function refreshTabBadges(s) {
  let gameplan = null;
  if (s.next_fixture) { try { gameplan = await api("/api/gameplan"); } catch (_e) {} }
  updateTabBadges(Object.assign({}, s, { gameplan }));
}

const TRAINING_FOCUS_DESCRIPTIONS = {
  mechanical: "<h4>Mechanical Focus</h4><div class='tooltip-desc'>Train aim precision, aim reactivity, and movement. Crucial for winning physical duel engagements.</div>",
  tactical: "<h4>Tactical Focus</h4><div class='tooltip-desc'>Train game sense, positioning, and utility usage. Enhances spacing, rotation speeds, and utility impact.</div>",
  mental: "<h4>Mental Focus</h4><div class='tooltip-desc'>Train composure, tilt resistance, and clutch factor. Helps players stay steady in tense late-round situations.</div>",
  team: "<h4>Team Focus</h4><div class='tooltip-desc'>Train comms quality. High communication makes players callout enemy positions earlier, aiding the whole squad.</div>",
  rest: "<h4>Rest Focus</h4><div class='tooltip-desc'>Spend the week resting. Dramatically recovers player stamina/condition and lowers burnout risk, at the cost of development.</div>"
};

// Team training focus — the compact header card on Club → Development
// (relocated from the Match Day hero, whose Performance prep card deep-links
// here). Same /api/actions/training endpoint; all options and the current
// pick arrive serialized on the app state.
function teamTrainingFocusCard(s) {
  const card = el("div", "card es-focus-card");
  card.appendChild(el("h2", "", "Team training focus"));
  card.appendChild(el("p", "muted",
    "The squad-wide focus for the week. Players on “auto” follow it; the per-player plans below override it."));
  const row = el("div", "es-prep-focus");
  for (const o of s.focus_options ?? []) {
    const b = el("button", "btn btn-sm" + (o === s.training_focus ? " active" : ""), cap(o));
    b.disabled = !!s.training_delegated;
    const desc = TRAINING_FOCUS_DESCRIPTIONS[o.toLowerCase()] || "";
    if (desc) b.setAttribute("data-tooltip", desc);
    b.onclick = async () => {
      await api("/api/actions/training", { focus: o });
      toast(`Training focus: ${o}`);
      refresh();
    };
    row.appendChild(b);
  }
  card.appendChild(row);
  const delegateLabel = el("label", "row");
  const delegateTraining = el("input");
  delegateTraining.type = "checkbox";
  delegateTraining.checked = !!s.training_delegated;
  delegateTraining.onchange = async () => {
    await api("/api/actions/training", { delegate_to_coach: delegateTraining.checked });
    toast(delegateTraining.checked
      ? "Weekly training delegated to the coach."
      : "Weekly training returned to manual control.");
    refresh();
  };
  delegateLabel.append(
    delegateTraining,
    el("span", "", "Delegate to Coach"),
    el("span", "muted", s.training_delegated
      ? "Coach chooses the focus when the week advances"
      : "Keep choosing the weekly focus yourself"),
  );
  card.appendChild(delegateLabel);
  return card;
}

// Form & fitness — weekly movers, burnout watch, and the season's shape
// (cumulative-wins sparkline) beside the Club → Squad roster (relocated from
// the dashboard; same serialized state, only formatted here). Null when
// there's nothing to show.
function squadFormFitnessCard(s) {
  const movers = s.movers || [];
  const burnt = (s.rotation || []).filter((r) => r.burnout);
  const trend = s.form_trend || [];
  if (!movers.length && !burnt.length && trend.length < 2) return null;
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
  return card;
}

// Roster screen. Two host contexts:
//   - standalone (opts.host absent): reached from a team profile's "View
//     roster" for an OPPONENT — renders its own "Roster" head with an
//     Overview/Development segment and the back / scout actions.
//   - hosted in Club (opts.host === "club"): always your own squad; the head
//     is the shared Club workspace head and the Squad/Development split rides
//     the Club sub-tabs, so no second segment is drawn.
async function roster(v, opts = {}) {
  const clubHost = opts.host === "club";
  const teamId = clubHost ? App.state.user_team.id : (App.rosterTeam ?? App.state.user_team.id);
  const data = await api(`/api/roster/${teamId}`);
  const s = App.state;
  const canRelease = !s.window || s.window.open;
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
  if (hasBench && overview) {
    lineupBar = el("div", "row",
      `<span class="microlabel" title="Toggle ★ in the table to change who dresses. Bench players scrim (reduced growth) and good ones want minutes.">Default five</span> <b class="mono">${lineup.size}/5</b>`);
    const save = el("button", "btn btn-sm btn-primary", "Save lineup");
    save.onclick = async () => {
      const r = await api("/api/actions/lineup", { lineup_ids: [...lineup] });
      toast(r.message); renderApp();
    };
    lineupBar.appendChild(save);
    right.push(lineupBar);
    paintLineupBar();
  }
  if (!data.is_user_team) {
    const back = el("button", "btn btn-sm", "← My squad");
    back.onclick = () => { App.rosterTeam = null; App.clubTab = "squad"; dashGoTab("club"); };
    right.push(back);
    const scout = el("button", "btn btn-sm",
      data.scouting_this
        ? (data.scout_progress >= data.scout_cap
            ? "Broad survey complete"
            : `Scouting… ${Math.round(data.scout_progress * 100)}%`)
        : "Assign scout");
    scout.disabled = data.scouting_this && data.scout_progress >= data.scout_cap;
    scout.onclick = async () => {
      const r = await api("/api/actions/scout", { team_id: teamId });
      toast(r.message); renderApp();
    };
    right.push(scout);
  }
  const fogSub = data.fog > 0 ? ` · <span class="muted">±${data.fog} fog</span>` : "";
  if (clubHost) {
    // Hosted in Club: the Squad/Development split is carried by the Club
    // sub-tabs, so the head shows those instead of a second Overview/Dev seg.
    v.appendChild(screenHead("Club", {
      sub: `${tlink(data.team.id, data.team.name)} <span class="muted">· ${data.players.length}/${cap}</span>${fogSub}`,
      subtabs: CLUB_TABS,
      active: App.clubTab ?? "squad",
      onPick: (id) => { App.clubTab = id; renderApp(); },
      right,
    }));
  } else {
    v.appendChild(screenHead("Roster", {
      sub: `${tlink(data.team.id, data.team.name)} <span class="muted">· ${data.players.length}/${cap}</span>${fogSub}`,
      subtabs: [
        { id: "overview", label: "Overview" },
        { id: "development", label: "Development" },
      ],
      active: cols,
      onPick: (id) => { App.rosterCols = id; renderApp(); },
      right,
    }));
  }

  const ws = el("div", "ws roster-ws");
  v.appendChild(ws);
  // The roster table is wide (13 columns) — give it the full content width so
  // every column, including the actions, is visible without a horizontal
  // scroll. The supporting cards tile in a row beneath it (.roster-support).
  const main = el("div", "ws-12 roster-main");
  const rail = el("div", "ws-12 roster-support");
  ws.appendChild(main);
  ws.appendChild(rail);

  // Club → Development leads with the team-wide training focus (moved out of
  // the dashboard's Match Day hero); Club → Squad opens its support row with
  // the form/fitness digest (moved off the dashboard).
  if (clubHost && !overview && data.is_user_team) {
    main.appendChild(teamTrainingFocusCard(s));
  }
  if (clubHost && overview && data.is_user_team) {
    const ff = squadFormFitnessCard(s);
    if (ff) rail.appendChild(ff);
  }

  /* -- main ws-9: the roster table ----------------------------------------- */
  const card = el("div", "card roster-card");
  if (data.is_user_team && data.players.length < (data.roster_min ?? 5)) {
    card.appendChild(el("p", "warn",
      `⚠ You need ${data.roster_min ?? 5} players to advance the week — sign ${(data.roster_min ?? 5) - data.players.length} more.`));
  } else if (data.is_user_team && data.players.length < 6) {
    card.appendChild(el("p", "muted",
      "Tip: a 6-man roster is advised for tournaments (register a bench)."));
  }

  const starTh = hasBench && overview ? "<th>★</th>" : "";
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
    const benchPill = overview && hasBench && !lineup.has(p.id) ? ' <span class="pill">bench</span>' : "";
    // Heavy-streamer chip: streaming slows this player's development.
    const streamChip = p.stream_heavy
      ? ' <span class="chip" title="heavy streaming slows this player\'s development">📺</span>'
      : "";
    const requestChip = p.transfer_request
      ? ' <span class="chip tone-bad" title="This player has submitted a transfer request">TRANSFER REQUEST</span>'
      : "";
    const badges = (p.badges || []).map((bd) =>
      ` <span class="roster-badge ${bd.polarity < 0 ? "badge-neg" : "badge-pos"}" title="${esc(bd.name)}: ${esc(bd.blurb)}">${bd.emoji}</span>`).join("");
    const starCell = hasBench && overview
      ? `<td><button class="btn btn-sm starter-toggle ${lineup.has(p.id) ? "active" : ""}" data-act="star" title="starter / bench">${lineup.has(p.id) ? "★" : "☆"}</button></td>`
      : "";
    const playerCell = `<td><img class="portrait" src="${p.portrait}" alt=""><b>${plink(p.id, p.handle)}</b>${p.id === data.team.captain_id ? ' <span class="pill">IGL</span>' : ""}${p.mentor_id ? ' <span class="pill mentor-pill" title="under a mentor\'s wing">🎓</span>' : ""}${badges}${benchPill}${streamChip}</td>`;
    const ceilingCell = `<td>${p.potential_stars != null ? starsRange([p.potential_stars, p.potential_stars]) : '<span class="muted">scout</span>'}</td>`;

    let rowHtml;
    if (overview) {
      const actions = data.is_user_team
        ? `${requestChip}<button class="btn btn-sm" data-act="talk">Talk</button>
           <button class="btn btn-sm" data-act="renew">Renew</button>
           <button class="btn btn-sm" data-act="release" ${canRelease ? "" : "disabled"} title="${canRelease ? "Release player" : esc(s.window.detail)}">Release</button>`
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
        <td title="Confidence shapes duels, peeks, and clutch nerve.">${bar(p.confidence)}${tArrow(ct.confidence)}</td>
        <td class="num">${money(p.salary)}/wk</td>
        <td class="num">${p.contract_weeks_left}w</td>
        <td><div class="roster-actions">${actions}</div>${askBreakdown(p.ask_breakdown)}</td>`;
    } else {
      // Development view: the per-player weekly plan, one interaction each.
      // Mentorship: older, higher-rated teammates can mentor this player,
      // sorted by hidden teaching ability (mentor_skill) so the best teacher
      // is first — a strong mentor raises the protege's ceiling.
      const eligibleMentors = (data.is_user_team && p.age <= 20)
        ? data.players
            .filter((q) => q.id !== p.id && q.age >= 25 && (q.age - p.age) >= 3)
            .sort((a, b) => (b.mentor_skill ?? 0) - (a.mentor_skill ?? 0))
        : [];
      const focusSel = data.is_user_team
        ? `<select data-act="focus" data-tooltip="<h4>Training Focus</h4><div class='tooltip-desc'>Set the skill area this player trains. <b>auto</b> matches the team training focus; <b>rest</b> helps recover stamina; <b>language</b> practises communication.</div>">
             ${(data.dev_focus_options ?? []).map((o) => `<option value="${o}" ${o === p.dev_focus ? "selected" : ""} ${o === "language" && !data.has_language_coach ? "disabled" : ""}>${o}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      const languageSel = data.is_user_team
        ? `<select data-act="language" data-tooltip="<h4>Language Training</h4><div class='tooltip-desc'>Choose a language to learn. Requires a language coach. Replaces game-skill training but builds chemistry for multinational rosters.</div>" ${data.has_language_coach ? "" : "disabled"}>
             <option value="">choose language</option>
             ${(data.language_options ?? []).map((o) => `<option value="${o}" ${o === p.learning_language ? "selected" : ""}>${o.toUpperCase()}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      const intSel = data.is_user_team
        ? `<select data-act="intensity" data-tooltip="<h4>Training Intensity</h4><div class='tooltip-desc'><b>light</b>: slows growth, spares legs (recovers condition).<br><b>normal</b>: default growth.<br><b>intense</b>: accelerates growth, but drains condition and risks burnout.</div>">
             ${(data.intensity_options ?? []).map((o) => `<option value="${o}" ${o === p.training_intensity ? "selected" : ""}>${o}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      const mentorSel = data.is_user_team && (eligibleMentors.length || p.mentor_id)
        ? `<select data-act="mentor" data-tooltip="<h4>Mentorship</h4><div class='tooltip-desc'>Pair this player with a veteran mentor. Accelerates growth and increases skill ceilings based on the mentor's stats and teaching ability (teach).</div>">
             <option value="">no mentor</option>
             ${eligibleMentors.map((q) => `<option value="${q.id}" ${q.id === p.mentor_id ? "selected" : ""}>🎓 ${esc(q.handle)}${q.mentor_skill != null ? ` (teach ${q.mentor_skill})` : ""}</option>`).join("")}
           </select>`
        : '<span class="muted">—</span>';
      const progressPercent = p.mentor_progress != null ? Math.round(p.mentor_progress) : 0;
      const progressBar = p.mentor_id ? `<div class="pf-hbar" style="height:4px; margin-top:4px; background:var(--es-color-bg, #05070a);"><i style="display:block; height:100%; width:${progressPercent}%; background:var(--es-color-accent, #00f0ff);"></i></div><span style="font-size:0.75em; display:block;" class="muted">${progressPercent}% complete</span>` : "";
      // F2 — "not developing this week" warning. The server decides the reason
      // (language plan with no coach, exhausted legs, or already at ceiling);
      // we only translate it to a chip so a silently-stalled plan is visible.
      const NOT_DEV_LABEL = {
        no_language_coach: "language study, no coach",
        exhausted: "too exhausted to train",
        at_ceiling: "at skill ceiling",
      };
      const ndReason = p.not_developing;
      const notDevChip = ndReason
        ? ` <span class="chip tone-bad dev-warn-chip" title="This week's plan isn't building attributes: ${esc(NOT_DEV_LABEL[ndReason] || ndReason)}.">⚠ ${esc(NOT_DEV_LABEL[ndReason] || humanize(ndReason))}</span>`
        : "";
      rowHtml = `
        ${starCell}
        ${playerCell}
        <td class="num">${p.age}</td>
        <td class="num" title="${fogged ? "estimate ±" + p.fog : "exact"}">${ovr}</td>
        ${ceilingCell}
        <td>${bar(p.form)}${tArrow(ct.form)}</td>
        <td title="Confidence shapes duels, peeks, and clutch nerve.">${bar(p.confidence)}${tArrow(ct.confidence)}</td>
        <td class="dev-plan">${focusSel}${notDevChip}</td>
        <td class="dev-plan">${languageSel}</td>
        <td class="dev-plan">${intSel}</td>
        <td class="dev-plan">${mentorSel}${progressBar}</td>`;
    }
    const tr = el("tr", "", rowHtml);

    if (hasBench && overview) {
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
          if (App.tab === "roster" || App.tab === "club") renderApp();
        };
      }
    }
    if (overview && !data.is_user_team && p.buyout != null) {
      tr.querySelector('[data-act="buyout"]').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`Trigger ${p.handle}'s buyout clause for ${money(p.buyout)}? ${data.team.name} can't refuse.`)) return;
        const r = await api("/api/actions/buyout", { player_id: p.id });
        toast(r.message); refresh(); renderApp();
      };
    } else if (overview && !data.is_user_team && p.transfer_ask != null) {
      tr.querySelector('[data-act="bid"]').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`Buy ${p.handle} from ${data.team.name} for ${money(p.transfer_ask)}?`)) return;
        const r = await api("/api/actions/bid", { player_id: p.id });
        toast(r.message); refresh(); renderApp();
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
      const releaseBtn = tr.querySelector('[data-act="release"]');
      releaseBtn.onclick = async (e) => {
        e.stopPropagation();
        if (!canRelease) return;
        if (!confirm(`Release ${p.handle}? Severance = 6 weeks salary.`)) return;
        const r = await api("/api/actions/release", { player_id: p.id });
        toast(r.message); refresh(); renderApp();
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
      `<span class="bar"><i style="--target-width:${Math.max(2, (n / total) * 100)}%; width:${Math.max(2, (n / total) * 100)}%"></i></span>` +
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
          `<span class="chip ${tone}" title="Shared language affects comms. Pairs without a common language rarely reach full chemistry.">Comms ${Math.round(cc)}</span> ` +
          `shared languages feed chemistry.`));
      }
      rail.appendChild(c);
    }
  }

  // Map-lineups: a compact per-map summary in the rail; the full chip editor
  // rides a ws-12 band below the grid (only when a bench makes it a choice).
  if (overview && hasBench && data.upcoming) {
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

  // F1 — "Future of the Org": the fortnightly dev digest + the pipeline board
  // (youth -> academy -> bench -> starters, each with a CA trajectory
  // sparkline). Both are pure reads of server-computed values.
  if (!overview && data.is_user_team && data.dev_digest) {
    const digestCell = el("div", "ws-12 ws-col");
    digestCell.appendChild(devDigestCard(data.dev_digest));
    ws.appendChild(digestCell);
  }
  if (!overview && data.is_user_team && data.pipeline) {
    const pipeCell = el("div", "ws-12 ws-col");
    pipeCell.appendChild(pipelineBoardCard(data.pipeline));
    ws.appendChild(pipeCell);
  }

  // Season-long development accounting belongs at the bottom of the
  // Development view. Deltas come from persisted server-side snapshots.
  if (!overview && data.is_user_team && data.development_report) {
    const reportCell = el("div", "ws-12 ws-col");
    reportCell.appendChild(developmentReportCard(data.development_report));
    ws.appendChild(reportCell);
  }
}

// F1 — the "Future of the Org" digest. Reads server-built lists (risers,
// milestones, academy standouts, prospect updates); renders nothing the
// server didn't compute. Signed attribute deltas arrive pre-formatted or as
// numbers; we only choose the tone class.
function devDigestCard(digest) {
  const card = el("div", "card dev-digest");
  const signed = (v) => (v > 0 ? "+" : "") + Number(v).toFixed(1);
  card.innerHTML = `<div class="dev-digest-head">
      <h2>Future of the Org</h2>
      <p class="muted">${esc(digest.subtitle || "Where the roster is trending — risers, milestones and the prospects behind them.")}</p>
    </div>`;

  const grid = el("div", "dev-digest-grid");

  const risers = digest.risers || [];
  const riserCol = el("div", "dev-digest-col");
  riserCol.innerHTML = `<h3 class="dev-digest-col-h">Risers</h3>`;
  if (!risers.length) {
    riserCol.appendChild(el("p", "muted", "No standout climbers this window."));
  } else {
    for (const r of risers) {
      const spark = sparkline(r.ca_series || r.series);
      riserCol.appendChild(el("div", "dev-digest-row",
        `<span class="dev-digest-name">${plink(r.id, r.handle)}` +
        `${r.age != null ? ` <span class="muted">${r.age}</span>` : ""}</span>` +
        `<span class="es-spark-wrap">${spark}</span>` +
        `<span class="chip ${(r.delta ?? 0) >= 0 ? "tone-good" : "tone-bad"}" ` +
        `title="ability change over the tracked window">CA ${signed(r.delta ?? 0)}</span>`));
    }
  }
  grid.appendChild(riserCol);

  const milestones = digest.milestones || [];
  const mCol = el("div", "dev-digest-col");
  mCol.innerHTML = `<h3 class="dev-digest-col-h">Milestones</h3>`;
  if (!milestones.length) {
    mCol.appendChild(el("p", "muted", "No milestones crossed."));
  } else {
    for (const m of milestones) {
      mCol.appendChild(el("div", "newsline",
        `${m.player_id ? plink(m.player_id, m.handle || m.player_id) + " · " : ""}${esc(m.text || m.label || "")}`));
    }
  }
  grid.appendChild(mCol);

  const acad = digest.academy_standouts || [];
  const aCol = el("div", "dev-digest-col");
  aCol.innerHTML = `<h3 class="dev-digest-col-h">Academy standouts</h3>`;
  if (!acad.length) {
    aCol.appendChild(el("p", "muted", "Quiet week in the academy."));
  } else {
    for (const a of acad) {
      aCol.appendChild(el("div", "dev-digest-row",
        `<span class="dev-digest-name">${plink(a.id, a.handle)}</span>` +
        `<span class="es-spark-wrap">${sparkline(a.ca_series || a.series)}</span>` +
        `<span class="chip">${a.note ? esc(a.note) : "CA " + Math.round(a.ca ?? 0)}</span>`));
    }
  }
  grid.appendChild(aCol);

  const prospects = digest.prospect_updates || [];
  const pCol = el("div", "dev-digest-col");
  pCol.innerHTML = `<h3 class="dev-digest-col-h">Prospect updates</h3>`;
  if (!prospects.length) {
    pCol.appendChild(el("p", "muted", "No new scouting movement."));
  } else {
    for (const pr of prospects) {
      pCol.appendChild(el("div", "newsline",
        `${pr.id ? plink(pr.id, pr.handle || pr.id) + " · " : ""}${esc(pr.text || pr.note || "")}`));
    }
  }
  grid.appendChild(pCol);

  card.appendChild(grid);
  return card;
}

// F1 — the talent pipeline board: four columns youth -> academy -> bench ->
// starters, each entry carrying a CA sparkline so a manager can see the
// trajectory at a glance. Column contents are server-supplied lists.
function pipelineBoardCard(pipeline) {
  const card = el("div", "card pipeline-board");
  card.innerHTML = `<h2>Talent pipeline</h2>
    <p class="muted">The path from intake to the starting five — trajectory sparklines are ability over recent snapshots.</p>`;
  const cols = [
    ["youth", "Youth intake"],
    ["academy", "Academy"],
    ["bench", "Bench"],
    ["starters", "Starters"],
  ];
  const grid = el("div", "pipeline-grid");
  for (const [key, label] of cols) {
    const list = pipeline[key] || [];
    const col = el("div", "pipeline-col");
    col.innerHTML = `<h3 class="pipeline-col-h">${label} <span class="pill">${list.length}</span></h3>`;
    if (!list.length) {
      col.appendChild(el("p", "muted", "Empty"));
    } else {
      for (const p of list) {
        const stars = p.potential_stars != null
          ? `<span class="pipeline-stars">${starsRange([p.potential_stars, p.potential_stars])}</span>` : "";
        col.appendChild(el("div", "pipeline-card-row",
          `<div class="pipeline-row-top"><span class="dev-digest-name">${plink(p.id, p.handle)}</span>` +
          `${p.age != null ? `<span class="muted pipeline-age">${p.age}</span>` : ""}</div>` +
          `<div class="pipeline-row-bot"><span class="es-spark-wrap">${sparkline(p.ca_series || p.series)}</span>` +
          `<span class="pipeline-ca mono" title="current ability">${Math.round(p.ability ?? 0)}</span>${stars}</div>`));
      }
    }
    grid.appendChild(col);
  }
  card.appendChild(grid);
  return card;
}

function developmentReportCard(report) {
  const card = el("div", "card development-report");
  const signed = (value) => `${value > 0 ? "+" : ""}${Number(value).toFixed(1)}`;
  const range = report.start_week == null
    ? "No tracked weeks yet"
    : `Week ${report.start_week} to Week ${report.end_week}`;
  card.innerHTML = `<div class="dev-report-head">
      <div><h2>Development Report</h2><p class="muted">Season ${report.season} · ${range}</p></div>
      <div class="dev-report-summary">
        <span class="chip ${report.overall_delta > 0 ? "tone-good" : report.overall_delta < 0 ? "tone-bad" : ""}">Squad OVR ${signed(report.overall_delta)}</span>
        <span class="chip tone-good">${report.grown} grown</span>
        <span class="chip tone-bad">${report.regressed} regressed</span>
        <span class="chip">${report.steady} steady</span>
      </div>
    </div>`;

  if (!(report.players || []).length) {
    card.appendChild(el("p", "muted", "Development tracking begins after this roster records its first season snapshot."));
    return card;
  }

  const table = el("table", "dev-report-table");
  table.innerHTML = `<thead><tr><th>Player</th><th>Tracked</th><th class="num">Start</th><th class="num">Now</th><th class="num">Change</th><th>Skills changed</th></tr></thead>`;
  const body = el("tbody");
  for (const p of report.players) {
    const tone = p.status === "grown" ? "trend-up" : p.status === "regressed" ? "trend-down" : "muted";
    let changes = (p.changes || []).map((change) => {
      const cls = change.delta > 0 ? "dev-gain" : "dev-loss";
      return `<span class="chip ${cls}" title="${esc(change.category || "attribute")} · ${change.start} to ${change.current}">${esc(change.name)} ${signed(change.delta)}</span>`;
    }).join(" ");
    if (!p.attribute_tracking) {
      changes = '<span class="muted">Skill tracking starts with the next snapshot</span>';
    } else if (!changes) {
      changes = '<span class="muted">No skill movement yet</span>';
    }
    body.appendChild(el("tr", "", `<td><b>${plink(p.id, p.handle)}</b></td>
      <td class="muted">W${p.start_week}–W${p.end_week} · ${p.tracked_points} pts</td>
      <td class="num">${Number(p.overall_start).toFixed(1)}</td>
      <td class="num">${Number(p.overall_current).toFixed(1)}</td>
      <td class="num"><span class="${tone}">${signed(p.overall_delta)}</span></td>
      <td><div class="dev-change-list">${changes}</div></td>`));
  }
  table.appendChild(body);
  const scroll = el("div", "table-scroll");
  scroll.appendChild(table);
  card.appendChild(scroll);
  return card;
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
    toast(r.message); renderApp();
  }));
  const auto = el("button", "btn btn-sm", "Clear (auto top-5)");
  auto.onclick = async () => {
    const r = await api("/api/actions/lineup", { lineup_ids: [] });
    toast(r.message); renderApp();
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
      toast(r.message); renderApp();
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
  v.appendChild(screenHead("Match", {
    sub: `S${s.season} · W${s.week} · ${cap(String(s.phase || "").replace(/_/g, " "))}`,
    subtabs: [
      { id: "strategy", label: "Strategy" },
      { id: "gameplan", label: "Game plan" },
      { id: "prep", label: "Prep" },
    ],
    active: sub,
    onPick: (id) => { App.tacticsTab = id; renderApp(); },
  }));
  const ws = el("div", "ws");
  v.appendChild(ws);

  if (sub === "prep") {
    // The week's match logistics (scrims, tournament six, series card) —
    // moved here from Club · Operations so all match prep lives on one tab.
    return tacticsPrep(ws);
  }

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

/* -- Match · Prep: the week's logistics around the fixture -------------------
   Scrim/bootcamp booking, tournament-six registration and the between-map
   series card. Reads /api/club (these are campaign-layer prep systems);
   moved out of Club · Operations so match prep has a single home. */
async function tacticsPrep(ws) {
  const d = await api("/api/club");

  // Preparation lab: every selectable value is server-supplied.
  const pc = el("div", "card ws-6");
  pc.innerHTML = `<h2>Match preparation</h2>`;
  const pr = d.preparation;
  if (!pr.fixture) {
    pc.appendChild(el("p", "muted", "No fixture is available to prepare for."));
  } else {
    pc.appendChild(el("p", "muted", `Next: ${esc(pr.fixture.team_a_name)} vs ${esc(pr.fixture.team_b_name)} · week ${pr.fixture.week}`));
    const partner = el("select", "sel-sm");
    for (const x of pr.partners) { const o = el("option", "", x.name); o.value = x.id; partner.appendChild(o); }
    const map = el("select", "sel-sm");
    for (const x of pr.maps) { const o = el("option", "", humanize(x)); o.value = x; map.appendChild(o); }
    const obj = el("select", "sel-sm");
    for (const x of pr.objectives) { const o = el("option", "", humanize(x)); o.value = x; obj.appendChild(o); }
    const intensity = el("select", "sel-sm");
    for (const x of pr.intensities) { const o = el("option", "", humanize(x)); o.value = x; intensity.appendChild(o); }
    const form = el("div", "row"); form.append(partner, map, obj, intensity);
    const book = el("button", "btn btn-primary", "Book session");
    book.onclick = async () => {
      const r = await api("/api/actions/preparation", { fixture_id: pr.fixture.id, partner_id: partner.value, map_id: map.value, objective: obj.value, intensity: intensity.value });
      toast(r.message); refresh();
    };
    pc.append(form, book);
  }
  // F7 — the coach proposes a concrete scrim plan for the next fixture, one
  // click to accept. The whole proposal (map/partner/objective) is
  // server-computed (preparation.propose); we render and POST accept=true.
  if (pr.proposal) {
    const prop = pr.proposal;
    const propBox = el("div", "prep-proposal");
    propBox.innerHTML = `<div class="prep-proposal-head"><span class="chip tone-accent">Coach proposal</span>` +
      `<b>${humanize(prop.objective || "scrim")} on ${humanize(prop.map_id || "")}</b></div>` +
      `<p class="muted">${esc(prop.rationale || `Recommended against ${prop.partner_name || "a sparring partner"} to prep the next fixture.`)}` +
      `${prop.partner_name ? ` Partner: <b>${esc(prop.partner_name)}</b>.` : ""}` +
      `${prop.expected_edge != null ? ` Expected +${Number(prop.expected_edge).toFixed(1)} prep edge.` : ""}</p>`;
    const acceptBtn = el("button", "btn btn-sm btn-primary", "Accept coach plan");
    acceptBtn.onclick = async () => {
      const r = await api("/api/actions/preparation", { accept: true });
      toast(r.message); refresh();
    };
    propBox.appendChild(acceptBtn);
    pc.appendChild(propBox);
  }
  if (pr.current) pc.appendChild(el("p", "muted", `Booked: ${humanize(pr.current.objective)} on ${humanize(pr.current.map_id)} (${pr.current.intensity}).`));
  if (pr.last) {
    // F7 — surface the named artifact the last session produced (not just the
    // prose finding), so scrims read as consequential.
    const artifact = pr.last.artifact_label
      ? `<b>Prep artifact:</b> ${esc(pr.last.artifact_label)}` +
        (pr.last.prep_edge_contribution != null ? ` <span class="chip tone-good">+${Number(pr.last.prep_edge_contribution).toFixed(1)} edge</span>` : "")
      : `<b>Last report:</b> ${esc(pr.last.finding)}`;
    pc.appendChild(el("div", "newsline", `${artifact} <span class="muted">Knowledge +${pr.last.knowledge_gain}; stamina −${pr.last.stamina_cost}.</span>`));
    if (pr.last.artifact_label && pr.last.finding) {
      pc.appendChild(el("p", "muted prep-finding", esc(pr.last.finding)));
    }
    if (pr.last.dev_suggestion) {
      pc.appendChild(el("div", "newsline prep-dev-hint",
        `<b>Dev note:</b> ${pr.last.dev_suggestion_player_id ? plink(pr.last.dev_suggestion_player_id, pr.last.dev_suggestion_handle || pr.last.dev_suggestion_player_id) + " — " : ""}${esc(pr.last.dev_suggestion)}`));
    }
  }
  ws.appendChild(pc);

  // Tournament roster registration.
  const rc = el("div", "card ws-6");
  rc.innerHTML = `<h2>Tournament six ${d.registration.locked ? '<span class="pill bad">locked</span>' : ""}</h2><p class="muted">Five starters plus one between-map substitute.</p>`;
  const chosen = new Set(d.registration.player_ids || []);
  for (const p of d.registration.players) {
    const lab = el("label", "entity");
    const cb = el("input"); cb.type = "checkbox"; cb.checked = chosen.has(p.id); cb.disabled = d.registration.locked;
    cb.onchange = () => cb.checked ? chosen.add(p.id) : chosen.delete(p.id);
    lab.append(cb, el("span", "entity-name", plink(p.id, p.handle)), el("span", "entity-meta", `${p.age} · ${p.role}`)); rc.appendChild(lab);
  }
  if (!d.registration.locked) {
    const save = el("button", "btn btn-primary", "Submit roster");
    save.onclick = async () => { const r = await api("/api/actions/tournament_registration", { player_ids: [...chosen] }); toast(r.message); refresh(); };
    rc.appendChild(save);
  }
  ws.appendChild(rc);

  // Conditional between-map response.
  const sc = el("div", "card ws-6");
  sc.innerHTML = `<h2>Series plan</h2><p class="muted">Set a between-map response that applies after map one when its condition is met.</p>`;
  if (!d.series.fixture) {
    sc.appendChild(el("p", "muted", "No upcoming best-of-three is on the calendar."));
  } else {
    const trigger = el("select", "sel-sm"), response = el("select", "sel-sm");
    for (const x of d.series.triggers) { const o = el("option", "", humanize(x)); o.value = x; trigger.appendChild(o); }
    for (const x of d.series.responses) { const o = el("option", "", humanize(x)); o.value = x; response.appendChild(o); }
    const sin = el("select", "sel-sm"), sout = el("select", "sel-sm");
    for (const [sel, ids] of [[sin, d.series.bench_ids], [sout, d.series.starter_ids]]) { const none = el("option", "", "No substitution"); none.value = ""; sel.appendChild(none); for (const p of d.registration.players.filter((x) => ids.includes(x.id))) { const o = el("option", "", p.handle); o.value = p.id; sel.appendChild(o); } }
    const row = el("div", "row"); row.append(trigger, response, sin, sout);
    const save = el("button", "btn btn-primary", "Save series card");
    save.onclick = async () => { const r = await api("/api/actions/series_directive", { fixture_id: d.series.fixture.id, trigger: trigger.value, response: response.value, substitute_in: sin.value || null, substitute_out: sout.value || null }); toast(r.message); refresh(); };
    sc.append(row, save);
    if (d.series.directive) sc.appendChild(el("p", "muted", `Current: ${humanize(d.series.directive.trigger)} → ${humanize(d.series.directive.response)}.`));
  }
  ws.appendChild(sc);
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

  const DIAL_DESCRIPTIONS = {
    aggression: "Aggression controls how aggressively your team takes duel engagements. High = peek/swing hard and trade actively; Low = anchor sites patiently and play spacing.",
    pace: "Pace controls execution tempo and rotation speed. High = fast executes, early timings; Low = slow defaults, pulling off bad hits to wait it out.",
    util_discipline: "Utility discipline governs utility timing. High = bank utility for retakes and pop-flashes; Low = spend all utility entering the site.",
    eco_greed: "Eco greed controls buying behavior when money is low. High = gamble on force-buys and retakes; Low = save credits disciplinedly when broke.",
    map_control: "Map control governs team spacing. High = spread across map to hold flank presence and lurk; Low = stack and hit sites together as five."
  };

  for (const d of TACTIC_DIALS) {
    const fit = fitBy[d.key];
    const block = el("div", "tac-dial");

    const tooltipText = `<h4>${d.label}</h4><div class='tooltip-desc'>${DIAL_DESCRIPTIONS[d.key]}</div>`;
    const head = el("div", "tac-head", `<span class="tac-name">${d.label} <span class="info-btn" data-tooltip="${tooltipText}">i</span></span>`);
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
  const siteCard = el("div", "card", `<h2>Site focus <span class="info-btn" data-tooltip="<h4>Site Focus</h4><div class='tooltip-desc'>Biases which bomb site your team targets on attack. Balanced has no bias. Commit A/B/C will heavily favor that site.</div>">i</span></h2>`);
  siteCard.appendChild(el("p", "muted",
    "Bias the attack toward one site. Pure macro — it steers where you hit, not who wins duels."));
  const seg = el("div", "tac-seg");
  for (const [val, label, note] of SITE_FOCUS) {
    const b = el("button", "tac-seg-btn", label);
    b.setAttribute("data-tooltip", `<h4>Site Focus: ${label}</h4><div class='tooltip-desc'>${note}</div>`);
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
  // F6 — the mastery-derived duel edge per pick is server-computed
  // (development.agent_pick_edge, matching the engine's (mastery-50)/25 read).
  // We only show whichever field the server attaches; if edge is absent the
  // column silently degrades to "—".
  const hasEdge = lineup.players.some((p) => (p.options || []).some((o) => o.edge != null));
  const edgeTh = hasEdge ? `<th class="num" title="duel points this agent's mastery adds or costs at match time">Edge</th>` : "";
  const t = el("table");
  t.innerHTML = `<thead><tr><th>Player</th><th>Role</th><th>Agent</th>
    <th class="num">Mastery</th>${edgeTh}</tr></thead>`;
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
    const eCell = hasEdge ? el("td", "num edge-cell") : null;
    const fmtEdge = (v) => (v > 0 ? "+" : "") + Number(v).toFixed(1);
    const paintM = () => {
      const id = sel.value || p.auto_id;
      const o = p.options.find((x) => x.id === id);
      mCell.textContent = o ? o.mastery : "—";
      mCell.className = "num" + (o && o.mastery < 40 ? " bad" : "");
      if (eCell) {
        if (o && o.edge != null) {
          eCell.textContent = fmtEdge(o.edge);
          eCell.className = "num edge-cell " + (o.edge > 0.05 ? "good" : o.edge < -0.05 ? "bad" : "muted");
        } else {
          eCell.textContent = "—";
          eCell.className = "num edge-cell muted";
        }
      }
    };
    const tr = el("tr");
    tr.appendChild(el("td", "", `<b>${plink(p.id, p.handle)}</b>`));
    tr.appendChild(el("td", "", stylePill(p)));
    const aCell = el("td");
    aCell.appendChild(sel);
    tr.appendChild(aCell);
    tr.appendChild(mCell);
    if (eCell) tr.appendChild(eCell);
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
  // F7 — the prep edge is now a {scout, book, coach, total, cap} breakdown
  // (preparation.prep_edge_breakdown) so the manager sees where the edge comes
  // from. Fall back to the legacy scalar if the server hasn't shipped it.
  const bd = (gp.prep_edge_breakdown && typeof gp.prep_edge_breakdown === "object")
    ? gp.prep_edge_breakdown
    : (gp.prep_edge && typeof gp.prep_edge === "object") ? gp.prep_edge : null;
  const prep = el("div", "gp-prep");
  if (bd) {
    const num = (v) => (v > 0 ? "+" : "") + Number(v || 0).toFixed(1);
    const part = (lab, v) => `<span class="gp-prep-part" title="${lab}"><span class="muted">${lab}</span> <b class="mono">${num(v)}</b></span>`;
    prep.innerHTML = `<span class="gp-prep-lab">Prep edge</span>
      <span class="gp-prep-val mono">${num(bd.total)}</span>
      <span class="gp-prep-parts">${part("scout", bd.scout)}${part("book", bd.book)}${part("coach", bd.coach)}</span>
      <span class="gp-prep-sub">duel points while a plan is set — from scouting, your
      map book and your coach. ${esc(opp.name)} is ${pct}% scouted${bd.cap != null ? ` · capped at +${Number(bd.cap).toFixed(1)}` : ""}.</span>`;
  } else {
    prep.innerHTML = `<span class="gp-prep-lab">Prep edge</span>
      <span class="gp-prep-val mono">+${Number(gp.prep_edge || 0).toFixed(1)}</span>
      <span class="gp-prep-sub">duel points while a plan is set. ${esc(opp.name)} is
      ${pct}% scouted — deeper scouting raises this (max +${Number(gp.prep_edge_max || 0).toFixed(1)}).</span>`;
  }
  card.appendChild(prep);
  // F7 — last named prep artifact, if the coach's most recent session produced
  // one. Server supplies the label + edge contribution.
  if (gp.last_artifact && (gp.last_artifact.artifact_label || gp.last_artifact.label)) {
    const la = gp.last_artifact;
    const contrib = la.prep_edge_contribution ?? la.contribution;
    card.appendChild(el("div", "newsline gp-artifact",
      `<b>Prep artifact:</b> ${esc(la.artifact_label || la.label)}` +
      (contrib != null ? ` <span class="chip tone-good">+${Number(contrib).toFixed(1)} edge</span>` : "")));
  }

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
    renderApp();
  };
  barRow2.appendChild(saveBtn);
  if (plan) {
    const clearBtn = el("button", "btn", "Scrap the plan");
    clearBtn.onclick = async () => {
      const r = await api("/api/actions/gameplan", { clear: true });
      toast(r.message);
      renderApp();
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
    onPick: (id) => { App.seasonTab = id; renderApp(); },
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
    if ((f.series_notes ?? []).length) {
      box.appendChild(el("div", "veto-row",
        `<span class="muted">series notes:</span> ${f.series_notes.map((n) => `<span class="chip">${esc(n)}</span>`).join(" ")}`));
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
    b.onclick = () => { App.seasonFixFilter = id; renderApp(); };
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

  // Champions history lives on the Records sub-tab — link there instead of
  // rendering the same list twice.
  const hc = el("div", "card");
  const go = el("p", "muted");
  const goLink = el("a", "", "Champions history in Records");
  goLink.href = "#";
  goLink.onclick = (e) => { e.preventDefault(); App.seasonTab = "records"; renderApp(); };
  go.appendChild(goLink);
  hc.appendChild(go);
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

  // Champions history — every crowned season, newest first (moved here from
  // the Playoffs sub-tab; this is its only home).
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

// Segmented [Players | Staff] shared by both market desks; each desk builds
// its own screen-head so the head can carry desk-specific right-side extras
// (the players desk adds a signing-headroom chip).
const MARKET_TABS = [
  { id: "players", label: "Players" },
  { id: "scouting", label: "Scouting" },
  { id: "staff", label: "Staff" },
];

async function market(v) {
  v.innerHTML = "";
  render(html`<${MarketTab} />`, v);
}

const ProgressBar = ({ value, invert = false }) => {
  const cls = invert
    ? value < 35 ? "good" : value < 65 ? "warn" : "bad"
    : value < 35 ? "bad" : value < 65 ? "warn" : "good";
  const cappedValue = Math.max(2, Math.min(100, value));
  return html`
    <div class=${`bar ${cls}`} title=${Math.round(value)}>
      <i style=${{ '--target-width': `${cappedValue}%` }}></i>
    </div>
  `;
};

const MarketHeader = ({ activeTab, onPick, head, windowData }) => {
  return html`
    <div class="screen-head">
      <span class="screen-title">Market</span>
      <div class="seg">
        ${MARKET_TABS.map(t => html`
          <button 
            class=${`seg-btn ${activeTab === t.id ? "on" : ""}`} 
            onClick=${() => onPick(t.id)}
            key=${t.id}
          >
            ${t.label}
          </button>
        `)}
      </div>
      <span class="spacer"></span>
      ${head && head.balance != null && (() => {
        const runway = head.runway_weeks == null ? "stable"
          : head.runway_weeks === 0 ? "insolvent now" : `${head.runway_weeks}w runway`;
        const tone = head.runway_weeks === 0 ? "tone-bad"
          : (head.runway_weeks != null && head.runway_weeks <= 6) ? "tone-warn" : "tone-good";
        return html`<span class=${`chip ${tone}`}>~${money(head.affordable_wage)}/wk free · ${runway}</span>`;
      })()}
      ${windowData && html`
        <span class=${`chip ${windowData.open ? "tone-good" : "tone-warn"}`}>
          ${windowData.label} · ${windowData.detail}
        </span>
      `}
    </div>
  `;
};

const StylePill = ({ player }) => html`
  <span class="pill-pair">
    <span class="pill">${player.role}</span>
    <span class="pill">${player.playstyle}</span>
  </span>
`;

const LangChips = ({ langs }) => html`
  ${(langs || []).map((l, idx) => html`
    <span class="chip" title="${l.lang} — proficiency ${l.level}" key=${idx}>${l.lang}</span>
  `)}
`;

const PlayerSearch = ({ myRoster, triggerRefresh }) => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  const performSearch = async (q) => {
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const r = await api("/api/market/search?q=" + encodeURIComponent(q.trim()));
      setResults(r.results || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      performSearch(query);
    }, 250);
    return () => clearTimeout(timerRef.current);
  }, [query]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      if (timerRef.current) clearTimeout(timerRef.current);
      performSearch(query);
    }
  };

  const handleBuyout = async (p) => {
    if (!confirm(`Trigger ${p.handle}'s buyout clause for ${money(p.buyout)}?`)) return;
    try {
      const res = await api("/api/actions/buyout", { player_id: p.id });
      toast(res.message);
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  return html`
    <div class="card">
      <h2>Find a player</h2>
      <div class="row">
        <input 
          class="field mono player-search-input" 
          placeholder="search by handle or real name…" 
          value=${query}
          onInput=${(e) => setQuery(e.target.value)}
          onKeyDown=${handleKeyDown}
        />
      </div>
      <div>
        ${loading && html`<p class="muted">Searching...</p>`}
        ${!loading && query.trim().length >= 2 && results.length === 0 && html`
          <p class="muted">no players match</p>
        `}
        ${!loading && results.length > 0 && html`
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Role</th>
                <th class="num">Age</th>
                <th class="num">OVR</th>
                <th>Club</th>
                <th class="num">Price</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${results.map(p => {
                const price = p.is_free_agent
                  ? `${money(p.asking_salary)}/wk`
                  : p.buyout != null ? money(p.buyout)
                    : p.transfer_ask != null ? money(p.transfer_ask) : "—";
                const club = p.is_free_agent
                  ? html`<span class="pill">free agent</span>`
                  : html`
                      <span>
                        <span class="tlink" data-tid=${p.team_id}>${p.team_name}</span>
                        ${p.mine && html` <span class="pill">yours</span>`}
                      </span>
                    `;
                return html`
                  <tr key=${p.id}>
                    <td>
                      <img class="portrait" src=${p.portrait} alt="" />
                      <b class="plink" data-pid=${p.id}>${p.handle}</b>
                      ${p.real_name && html`<span class="muted"> ${p.real_name}</span>`}
                      ${p.languages && p.languages.length > 0 && html`
                        <div class="es-langs">
                          <${LangChips} langs=${p.languages} />
                        </div>
                      `}
                    </td>
                    <td><${StylePill} player=${p} /></td>
                    <td class="num">${p.age}</td>
                    <td class="num">${p.fogged ? "~" : ""}${p.overall}</td>
                    <td>${club}</td>
                    <td class="num">
                      <div>${price}</div>
                      ${p.seller_stance && html`
                        <div><span class="pill">${p.seller_stance}</span></div>
                      `}
                      ${p.ask_breakdown && p.ask_breakdown.length > 0 && html`
                        <details class="ask-breakdown">
                          <summary class="chip">Why this price?</summary>
                          ${p.ask_breakdown.map((b_item, idx) => html`
                            <div class="rowbar" key=${idx}>
                              <span>${b_item.label}</span>
                              <span class="rowbar-val mono">
                                ${b_item.delta >= 0 ? "+" : "−"}${money(Math.abs(b_item.delta))}
                              </span>
                            </div>
                          `)}
                        </details>
                      `}
                    </td>
                    <td>
                      ${p.is_free_agent && html`
                        <button class="btn btn-sm" onClick=${() => openNegotiation({ id: p.id, handle: p.handle })}>Negotiate…</button>
                      `}
                      ${!p.mine && p.buyout != null && html`
                        <button 
                          class="btn btn-sm" 
                          title="trigger the buyout clause — the org can't refuse"
                          onClick=${() => handleBuyout(p)}
                        >
                          Buy out
                        </button>
                      `}
                      ${!p.mine && p.transfer_ask != null && html`
                        <button 
                          class="btn btn-sm" 
                          onClick=${() => openOffer({
                            id: p.id, handle: p.handle, ask: p.transfer_ask, team_name: p.team_name,
                            ask_breakdown: p.ask_breakdown, seller_stance: p.seller_stance,
                          })}
                        >
                          Offer…
                        </button>
                      `}
                    </td>
                  </tr>
                `;
              })}
            </tbody>
          </table>
        `}
      </div>
    </div>
  `;
};

const MarketFilters = ({ players, filters, onChange }) => {
  const [isCollapsed, setIsCollapsed] = useState(true);

  const options = (values) => [...new Set(values.filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b)));

  const handleSelectChange = (key, val) => {
    let newFilters = { ...filters, [key]: val };
    if (key === "language" && !val) {
      newFilters.languageMin = "";
    }
    onChange(newFilters);
  };

  const handleNumberChange = (key, val) => {
    onChange({ ...filters, [key]: val });
  };

  const hasActiveFilters = Object.values(filters).some((value) => value !== "");

  return html`
    <div class="market-filters-container">
      <div class="market-filters-trigger" onClick=${() => setIsCollapsed(!isCollapsed)}>
        <span class="market-filters-label">
          🛠️ Filter free agents ${hasActiveFilters && html`<span class="pill win" style="margin-left:8px; font-size:10px; padding:2px 6px;">Active</span>`}
        </span>
        <button class="btn btn-sm">${isCollapsed ? "Show Filters ▾" : "Hide Filters ▴"}</button>
      </div>
      
      ${!isCollapsed && html`
        <div class="market-filters">
          <label class="market-filter">
            <span class="muted">CA stars at most</span>
            <select class="select" value=${filters.caMax} onChange=${(e) => handleSelectChange("caMax", e.target.value)}>
              <option value="">No cap</option>
              ${["0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"].map(v => html`<option key=${v} value=${v}>${v}</option>`)}
            </select>
          </label>

          <label class="market-filter">
            <span class="muted">Potential stars at most</span>
            <select class="select" value=${filters.potentialMax} onChange=${(e) => handleSelectChange("potentialMax", e.target.value)}>
              <option value="">No cap</option>
              ${["0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"].map(v => html`<option key=${v} value=${v}>${v}</option>`)}
            </select>
          </label>

          <label class="market-filter">
            <span class="muted">Language</span>
            <select class="select" value=${filters.language} onChange=${(e) => handleSelectChange("language", e.target.value)}>
              <option value="">Any</option>
              ${options(players.flatMap((p) => (p.languages || []).map((l) => l.lang))).map(lang => html`
                <option key=${lang} value=${lang}>${humanize(lang)}</option>
              `)}
            </select>
          </label>

          <label class="market-filter">
            <span class="muted">Language minimum</span>
            <input 
              type="number" 
              class="field mono" 
              placeholder="0-100" 
              min="0" 
              max="100" 
              step="1"
              disabled=${!filters.language}
              value=${filters.languageMin} 
              onChange=${(e) => handleNumberChange("languageMin", e.target.value)} 
            />
          </label>

          <label class="market-filter">
            <span class="muted">Min stream revenue</span>
            <input 
              type="number" 
              class="field mono" 
              placeholder="cr / wk" 
              min="0" 
              step="100"
              value=${filters.streamRevenueMin} 
              onChange=${(e) => handleNumberChange("streamRevenueMin", e.target.value)} 
            />
          </label>

          <label class="market-filter">
            <span class="muted">Role</span>
            <select class="select" value=${filters.role} onChange=${(e) => handleSelectChange("role", e.target.value)}>
              <option value="">Any</option>
              ${options(players.map((p) => p.role)).map(r => html`
                <option key=${r} value=${r}>${humanize(r)}</option>
              `)}
            </select>
          </label>

          <label class="market-filter">
            <span class="muted">Style</span>
            <select class="select" value=${filters.style} onChange=${(e) => handleSelectChange("style", e.target.value)}>
              <option value="">Any</option>
              ${options(players.map((p) => p.playstyle)).map(s => html`
                <option key=${s} value=${s}>${humanize(s)}</option>
              `)}
            </select>
          </label>

          <label class="market-filter">
            <span class="muted">IGL</span>
            <select class="select" value=${filters.igl} onChange=${(e) => handleSelectChange("igl", e.target.value)}>
              <option value="">Any</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </label>

          ${hasActiveFilters && html`
            <button class="btn btn-sm market-filter-reset" onClick=${() => onChange({ ...MARKET_FILTER_DEFAULTS })}>
              Clear filters
            </button>
          `}
        </div>
      `}
    </div>
  `;
};

const FreeAgentTable = ({ data, freeAgents, triggerRefresh }) => {
  const [expandedPlayerId, setExpandedPlayerId] = useState(null);
  const [swapSelections, setSwapSelections] = useState({});

  const locked = data.window ? !data.window.open : data.phase === "playoffs";

  const handleRowClick = (e, playerId) => {
    if (e.target.closest("button") || e.target.closest("select") || e.target.closest("option") || e.target.closest(".plink")) return;
    setExpandedPlayerId(prev => (prev === playerId ? null : playerId));
  };

  const handleSwapChange = (faId, dropId) => {
    setSwapSelections(prev => ({ ...prev, [faId]: dropId }));
  };

  const handleSwapSubmit = async (fa) => {
    const dropId = swapSelections[fa.id];
    if (!dropId) {
      toast("choose a player to drop");
      return;
    }
    const dropPlayer = data.my_roster.find(x => x.id === dropId);
    const dropName = dropPlayer ? dropPlayer.handle : "player";
    if (!confirm(`Drop ${dropName} and sign ${fa.handle}?`)) return;

    try {
      const r = await api("/api/actions/swap", { sign_id: fa.id, drop_id: dropId });
      toast(r.message);
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  return html`
    <table>
      <thead>
        <tr>
          <th>Player</th>
          <th>Role</th>
          <th class="num">Age</th>
          <th class="num">OVR</th>
          <th>Ability</th>
          <th>Ceiling</th>
          <th>Languages</th>
          <th class="num">Stream revenue</th>
          <th class="num">Asking</th>
          <th></th>
          <th>Swap out</th>
        </tr>
      </thead>
      <tbody>
        ${freeAgents.map(p => {
          const fogged = p.fog > 0;
          const isExpanded = expandedPlayerId === p.id;
          
          return html`
            <tr key=${p.id} onClick=${(e) => handleRowClick(e, p.id)} style=${{ cursor: 'pointer' }}>
              <td>
                <img class="portrait" src=${p.portrait} alt="" />
                <b class="plink" data-pid=${p.id}>${p.handle}</b>
                ${p.locker_room_fit && (() => {
                  const fit = p.locker_room_fit;
                  return html`
                    <div class="muted" title="Existing player history with your current roster">
                      Room fit ${Math.round(fit.score)}${fit.duos ? ` · ${fit.duos} duo` : ""}${fit.feuds ? ` · ${fit.feuds} feud` : ""}
                    </div>
                  `;
                })()}
              </td>
              <td><${StylePill} player=${p} /></td>
              <td class="num">${p.age}</td>
              <td class="num" title=${fogged ? `estimate ±${p.fog}` : "exact"}>
                ${fogged ? `~${Math.round(p.overall)}` : p.overall}
              </td>
              <td dangerouslySetInnerHTML=${{ __html: starsRange(p.scout?.ca_stars) }}></td>
              <td dangerouslySetInnerHTML=${{ __html: starsRange(p.scout?.pa_stars) }}></td>
              <td>
                ${p.languages && p.languages.length > 0
                  ? html`<${LangChips} langs=${p.languages} />`
                  : html`<span class="muted">—</span>`
                }
              </td>
              <td class="num">${money(p.stream_income)}/wk</td>
              <td class="num">${money(p.asking_salary)}/wk</td>
              <td>
                <button 
                  class="btn btn-sm" 
                  disabled=${!p.can_sign}
                  title=${p.block_reason || "open contract talks — their ask is an opening number"}
                  onClick=${() => openNegotiation({ id: p.id, handle: p.handle })}
                >
                  Negotiate…
                </button>
              </td>
              <td>
                ${locked ? html`
                  <span class="muted">locked</span>
                ` : html`
                  <div style=${{ display: 'flex', gap: '4px' }}>
                    <select 
                      class="sel-sm" 
                      value=${swapSelections[p.id] || ""} 
                      onChange=${(e) => handleSwapChange(p.id, e.target.value)}
                    >
                      <option value="">— drop —</option>
                      ${data.my_roster.map(mine => html`
                        <option key=${mine.id} value=${mine.id}>${mine.handle} (${mine.overall})</option>
                      `)}
                    </select>
                    <button class="btn btn-sm" onClick=${() => handleSwapSubmit(p)}>Swap</button>
                  </div>
                `}
              </td>
            </tr>
            ${isExpanded && html`
              <tr key=${`${p.id}-detail`}>
                <td colspan="11" dangerouslySetInnerHTML=${{ __html: attrDetail(p) }}></td>
              </tr>
            `}
          `;
        })}
        ${freeAgents.length === 0 && html`
          <tr>
            <td colspan="11" class="muted">No free agents match these filters.</td>
          </tr>
        `}
      </tbody>
    </table>
  `;
};

const PlayerRecruitment = ({ data, triggerRefresh }) => {
  const [filters, setFilters] = useState({ ...MARKET_FILTER_DEFAULTS });
  
  const freeAgents = useMemo(() => {
    return filteredMarketPlayers(data.free_agents, filters);
  }, [data.free_agents, filters]);

  const filterActive = Object.values(filters).some((value) => value !== "");
  const count = filterActive ? `${freeAgents.length} of ${data.free_agents.length}` : data.free_agents.length;

  const needs = data.squad_needs;
  const targets = data.target_suggestions || [];
  const cw = data.contract_watch || {};
  const wk = data.wonderkids || [];
  const chal = data.challengers || [];
  const rumors = data.rumors || [];

  return html`
    <div class="ws">
      <div class="ws-8 ws-col">
        <${PlayerSearch} myRoster=${data.my_roster} triggerRefresh=${triggerRefresh} />
        
        <div class="card">
          <h2>Free agents <span class="muted" style=${{ fontWeight: 400 }}>— ${count}</span></h2>
          ${data.market_scouting < 1 && html`
            <p class="muted">
              Market coverage ${Math.round(data.market_scouting * 100)}% — estimates only
              ${data.market_scouting === 0 && "; assign your scout to the market to see ceilings"}.
            </p>
          `}
          
          <${MarketFilters} 
            players=${data.free_agents} 
            filters=${filters} 
            onChange=${setFilters} 
          />
          
          <div style=${{ height: '12px' }}></div>
          
          <div class="card-scroll table-scroll" style=${{ '--scroll-max': '62vh' }}>
            <${FreeAgentTable} 
              data=${data} 
              freeAgents=${freeAgents} 
              triggerRefresh=${triggerRefresh} 
            />
          </div>
        </div>
      </div>
      
      <div class="ws-4 ws-col">
        ${needs && html`
          <div class="card">
            <h2>Squad intelligence</h2>
            <div class="es-roles">
              ${Object.entries(needs.role_counts || {}).map(([role, n]) => {
                const gap = (needs.gaps || []).includes(role);
                return html`
                  <span class=${`pill ${gap ? "elim-pill" : ""}`} key=${role}>
                    ${role} ${n}
                  </span>
                `;
              })}
            </div>
            ${needs.weakest_role && html`
              <p class="muted">
                Weakest: ${needs.weakest_role.role} (${needs.weakest_role.quality})
              </p>
            `}
          </div>
        `}
        
        ${data.signing_headroom && data.signing_headroom.balance != null && (() => {
          const head = data.signing_headroom;
          const runway = head.runway_weeks == null ? "stable"
            : head.runway_weeks === 0 ? "insolvent now" : `${head.runway_weeks}w runway`;
          const netCls = head.weekly_net >= 0 ? "trend-up" : "trend-down";
          return html`
            <div class="card">
              <h2>Signing headroom</h2>
              <div class="es-head">
                <div>Weekly net <b class=${`mono ${netCls}`}>${money(head.weekly_net)}</b></div>
                <div>Affordable wage <b class="mono">${money(head.affordable_wage)}/wk</b></div>
                <div class="muted">${runway}</div>
              </div>
            </div>
          `;
        })()}
        
        ${targets.length > 0 && html`
          <div class="card">
            <h2>Suggested signings</h2>
            ${targets.map(tgt => html`
              <div class="entity" key=${tgt.id}>
                <span class="entity-name"><b class="plink" data-pid=${tgt.id}>${tgt.handle}</b></span>
                <span class="entity-meta">${tgt.role}</span>
                <b class="entity-num">
                  ${tgt.quality}
                  ${!tgt.affordable && html` <span class="muted" title="over budget">✗</span>`}
                </b>
              </div>
            `)}
          </div>
        `}
        
        ${(cw.expiring_own?.length > 0 || cw.market_watch?.length > 0) && html`
          <div class="card">
            <h2>Contract watch</h2>
            ${(cw.expiring_own || []).map(p => html`
              <div class="entity" key=${p.id}>
                <span class="entity-name"><b class="plink" data-pid=${p.id}>${p.handle}</b></span>
                <span class="entity-meta">yours · ${p.role}</span>
                <b class="entity-num trend-down">${p.weeks_left}w</b>
              </div>
            `)}
            ${(cw.market_watch || []).map(p => html`
              <div class="entity" key=${p.id}>
                <span class="entity-name"><b class="plink" data-pid=${p.id}>${p.handle}</b></span>
                <span class="entity-meta">
                  <span class="tlink" data-tid=${p.team_id}>${p.team}</span> · ${p.role}
                </span>
                <b class="entity-num">${p.weeks_left}w</b>
              </div>
            `)}
          </div>
        `}
        
        ${wk.length > 0 && html`
          <div class="card">
            <h2>Wonderkids <span class="muted" style=${{ fontWeight: 400 }}>— ≤20</span></h2>
            ${wk.map(p => html`
              <div class="entity" key=${p.id}>
                <span class="entity-name"><b class="plink" data-pid=${p.id}>${p.handle}</b></span>
                <span class="entity-meta">
                  ${p.age}y · ${p.role} · <span class="tlink" data-tid=${p.team_id}>${p.team}</span>
                </span>
                <b class="entity-num stars">${"★".repeat(Math.round(p.potential_stars))}</b>
              </div>
            `)}
          </div>
        `}
        
        ${chal.length > 0 && html`
          <div class="card">
            <h2>Challengers standouts</h2>
            ${chal.map(p => html`
              <div class="entity" key=${p.id}>
                <span class="entity-name"><b class="plink" data-pid=${p.id}>${p.handle}</b></span>
                <span class="entity-meta">
                  ${p.age}y · ${p.role} · <span class="tlink" data-tid=${p.team_id}>${p.team}</span>
                </span>
                <b class="entity-num">${p.rating.toFixed(2)}</b>
              </div>
            `)}
          </div>
        `}
        
        ${rumors.length > 0 && html`
          <div class="card">
            <h2>Rumour mill</h2>
            <div class="card-scroll" style=${{ '--scroll-max': '260px' }}>
              ${rumors.map((r, idx) => html`
                <div class=${`es-rumor muted ${r.kind}`} key=${idx}>
                  ${r.text}
                </div>
              `)}
            </div>
          </div>
        `}
      </div>
    </div>
  `;
};

const BackroomStaff = ({ data, triggerRefresh }) => {
  const [activeRole, setActiveRole] = useState("all");
  const [filters, setFilters] = useState({
    qualityMin: "",
    salaryMax: "",
    specialty: "",
    region: ""
  });
  const [isFiltersCollapsed, setIsFiltersCollapsed] = useState(true);

    const rolePlural = {
      coach: "Coaches", analyst: "Analysts", physio: "Physios",
      psychologist: "Psychologists", performance_coach: "Performance coaches",
      language_coach: "Language coaches",
    };

  const handleHire = async (mId) => {
    try {
      const r = await api("/api/actions/hire_staff", { candidate_id: mId });
      toast(r.message);
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  const handleRelease = async (role) => {
    try {
      const r = await api("/api/actions/release_staff", { role });
      toast(r.message);
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  const filteredPool = useMemo(() => {
    return data.pool.filter(m => {
      // 1. Role filter
      if (activeRole !== "all" && m.role !== activeRole) return false;
      // 2. Quality min
        if (filters.qualityMin && (m.overall ?? m.quality) < Number(filters.qualityMin)) return false;
      // 3. Salary max
      if (filters.salaryMax && m.salary > Number(filters.salaryMax)) return false;
      // 4. Specialty
      if (filters.specialty && m.specialty !== filters.specialty) return false;
      // 5. Region
      if (filters.region && m.region !== filters.region) return false;
      return true;
    });
  }, [data.pool, activeRole, filters]);

  const specialties = useMemo(() => {
    return [...new Set(data.pool.map(m => m.specialty).filter(Boolean))].sort();
  }, [data.pool]);

  const regions = useMemo(() => {
    return [...new Set(data.pool.map(m => m.region).filter(Boolean))].sort();
  }, [data.pool]);

  const hasActiveFilters = filters.qualityMin !== "" || filters.salaryMax !== "" || filters.specialty !== "" || filters.region !== "";
  const hasFA = filteredPool.length > 0;

  return html`
    <div class="ws">
      <div class="ws-8 ws-col">
        <div class="card">
          <h2>
            Staff market <span class="muted" style=${{ fontWeight: 400 }}>— ${data.pool.length} free agents</span>
          </h2>
          <p class="muted">
            One shared pool — in a shared world, rival managers hire from the same market. 
            Hiring replaces your current ${data.roles.map(r => humanize(r)).join(" / ")} in that role (they return to the pool). 
            Click a name for the full profile.
          </p>

          <div class="seg">
            <button class=${`seg-btn ${activeRole === "all" ? "on" : ""}`} onClick=${() => setActiveRole("all")}>All</button>
            ${data.roles.map(role => html`
              <button 
                class=${`seg-btn ${activeRole === role ? "on" : ""}`} 
                onClick=${() => setActiveRole(role)}
                key=${role}
              >
                ${rolePlural[role] || humanize(role)}
              </button>
            `)}
          </div>

          <div class="market-filters-container">
            <div class="market-filters-trigger" onClick=${() => setIsFiltersCollapsed(!isFiltersCollapsed)}>
              <span class="market-filters-label">
                🛠️ Filter staff candidates ${hasActiveFilters && html`<span class="pill win" style="margin-left:8px; font-size:10px; padding:2px 6px;">Active</span>`}
              </span>
              <button class="btn btn-sm">${isFiltersCollapsed ? "Show Filters ▾" : "Hide Filters ▴"}</button>
            </div>
            
            ${!isFiltersCollapsed && html`
              <div class="market-filters">
                <label class="market-filter">
                    <span class="muted">Min Overall</span>
                  <select class="select" value=${filters.qualityMin} onChange=${(e) => setFilters({ ...filters, qualityMin: e.target.value })}>
                    <option value="">No min</option>
                    ${["50", "60", "70", "80", "90"].map(v => html`<option key=${v} value=${v}>${v}+</option>`)}
                  </select>
                </label>

                <label class="market-filter">
                  <span class="muted">Max Salary</span>
                  <input 
                    type="number" 
                    class="field mono" 
                    placeholder="cr / wk" 
                    min="0"
                    value=${filters.salaryMax} 
                    onChange=${(e) => setFilters({ ...filters, salaryMax: e.target.value })} 
                  />
                </label>

                <label class="market-filter">
                  <span class="muted">Specialty</span>
                  <select class="select" value=${filters.specialty} onChange=${(e) => setFilters({ ...filters, specialty: e.target.value })}>
                    <option value="">Any</option>
                    ${specialties.map(spec => html`
                      <option key=${spec} value=${spec}>${spec}</option>
                    `)}
                  </select>
                </label>

                <label class="market-filter">
                  <span class="muted">Region</span>
                  <select class="select" value=${filters.region} onChange=${(e) => setFilters({ ...filters, region: e.target.value })}>
                    <option value="">Any</option>
                    ${regions.map(r => html`
                      <option key=${r} value=${r}>${r}</option>
                    `)}
                  </select>
                </label>

                <button 
                  class="btn btn-sm market-filter-reset" 
                  disabled=${!hasActiveFilters}
                  onClick=${() => setFilters({ qualityMin: "", salaryMax: "", specialty: "", region: "" })}
                >
                  Reset
                </button>
              </div>
            `}
          </div>

          <div class="staff-tables">
            <div class="card-scroll table-scroll" style=${{ marginTop: '16px', '--scroll-max': '62vh' }}>
              ${!hasFA ? html`
                <p class="muted" style=${{ padding: '16px 0' }}>No staff candidates match your active filters.</p>
              ` : html`
                <table>
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Name</th>
                      <th class="num">Age</th>
                      <th>Region</th>
                      <th>Specialty</th>
                        <th>Identity / strengths</th>
                        <th>OVR</th>
                      <th class="num">Salary</th>
                      <th class="num">Exp</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    ${filteredPool.map(m => html`
                      <tr key=${m.id}>
                        <td><span class="pill">${humanize(m.role)}</span></td>
                          <td>
                            <b class="slink" data-sid=${m.id}>${m.name}</b>
                            ${m.titles && m.titles.length > 0 && html`
                              <span class="pill" title=${m.titles.join(", ")}>🏆 ${m.titles.length}</span>
                            `}
                            ${m.comparison?.current_id && html`
                              <div class=${`muted ${Number(m.comparison.overall_delta || 0) > 0 ? "tone-good" : Number(m.comparison.overall_delta || 0) < 0 ? "tone-bad" : ""}`}>
                                ${Number(m.comparison.overall_delta || 0) >= 0 ? "+" : ""}${Number(m.comparison.overall_delta || 0).toFixed(1)} OVR vs current
                              </div>
                            `}
                          </td>
                        <td class="num">${m.age}</td>
                          <td>${m.region || "—"}</td>
                          <td title=${m.specialty_blurb || ""}><span class="pill">${m.specialty || "—"}</span></td>
                          <td>
                            ${m.style ? html`
                              <span class="pill">${m.style.label}</span> <span class="mono">fit ${Math.round(m.style.fit)}</span>
                            ` : (m.attributes_view || []).slice().sort((a, b) => b.value - a.value).slice(0, 2)
                              .map(a => `${a.label} ${Math.round(a.value)}`).join(" · ") || "—"}
                          </td>
                          <td><${ProgressBar} value=${m.overall ?? m.quality} /></td>
                        <td class="num">${money(m.salary)}/wk</td>
                        <td class="num">${m.seasons_experience}s</td>
                        <td>
                          <button class="btn btn-sm" onClick=${() => handleHire(m.id)}>Hire</button>
                        </td>
                      </tr>
                    `)}
                  </tbody>
                </table>
              `}
            </div>
          </div>
        </div>
      </div>

      <div class="ws-4 ws-col">
        <div class="card">
          <h2>
            Your backroom <span class="muted" style=${{ fontWeight: 400 }}>— ${money(data.weekly_cost)}/wk</span>
          </h2>
          ${data.roles.map(role => {
            const hired = data.hired[role];
            return html`
              <div key=${role} style=${{ marginBottom: '12px' }}>
                ${hired ? html`
                  <div>
                    <div class="entity" style=${{ display: 'flex', alignItems: 'center' }}>
                      <span class="pill">${humanize(role)}</span>
                      <span class="entity-name">
                        <b class="slink" data-sid=${hired.id}>${hired.name}</b>
                      </span>
                      <button class="btn btn-sm" style=${{ marginLeft: 'auto' }} onClick=${() => handleRelease(role)}>Release</button>
                    </div>
                      <div class="muted">
                        OVR ${Math.round(hired.overall ?? hired.quality)} · ${hired.specialty || "—"}${hired.style ? ` · ${hired.style.label} (${Math.round(hired.style.fit)} fit)` : ""} · ${money(hired.salary)}/wk
                      </div>
                    ${hired.effects && hired.effects.length > 0 && html`
                      <div style=${{ marginTop: '4px' }}>
                        ${hired.effects.map((e, idx) => html`
                          <span class="chip tone-good" key=${idx} style=${{ marginRight: '4px' }}>${e}</span>
                        `)}
                      </div>
                    `}
                  </div>
                ` : html`
                  <div>
                    <div class="entity">
                      <span class="pill">${humanize(role)}</span>
                      <span class="entity-meta">vacant</span>
                    </div>
                    <div class="muted">${data.blurbs[role]}</div>
                  </div>
                `}
              </div>
            `;
          })}
        </div>

        ${data.analytics && data.analytics.tier != null && (() => {
          const an = data.analytics;
          const pct = Math.max(6, Math.min(100, (an.tier / 3) * 100));
          return html`
            <div class="card">
              <h2>Analytics department</h2>
              <div class="rowbar">
                <span class="muted">Tier</span>
                <span class="bar"><i style=${{ '--target-width': `${pct}%` }}></i></span>
                <span class="rowbar-val">${an.tier}/3</span>
              </div>
              <p><b>${an.label || "—"}</b></p>
              <p class="muted">
                ${an.next_unlock ? `Next unlock: ${an.next_unlock}` : "Deepest stat views unlocked."}
              </p>
            </div>
          `;
        })()}
      </div>
    </div>
  `;
};

const MarketTab = () => {
  const [marketTab, setMarketTab] = useState(App.marketTab ?? "players");
  const [data, setData] = useState(null);
  const [staffData, setStaffData] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    App.marketTab = marketTab;
  }, [marketTab]);

  useEffect(() => {
    if (marketTab === "players") {
      api("/api/market").then(setData).catch(console.error);
    } else if (marketTab === "staff") {
      api("/api/staff").then(setStaffData).catch(console.error);
    }
  }, [marketTab, refreshTrigger]);

  const triggerRefresh = () => {
    if (window.refresh) {
      window.refresh().then(() => {
        setRefreshTrigger(prev => prev + 1);
      });
    } else {
      setRefreshTrigger(prev => prev + 1);
    }
  };

  const handleTabPick = (tabId) => {
    setMarketTab(tabId);
  };

  if (marketTab === "scouting") {
    return html`
      <div>
        <${MarketHeader} activeTab="scouting" onPick=${handleTabPick} />
        <${ScoutingPanel} />
      </div>
    `;
  }

  if (marketTab === "staff") {
    if (!staffData) return html`<div class="loading">Loading staff market...</div>`;
    return html`
      <div>
        <${MarketHeader} activeTab="staff" onPick=${handleTabPick} />
        <${BackroomStaff} data=${staffData} triggerRefresh=${triggerRefresh} />
      </div>
    `;
  }

  if (!data) return html`<div class="loading">Loading player market...</div>`;

  return html`
    <div>
      <${MarketHeader} 
        activeTab="players" 
        onPick=${handleTabPick} 
        head=${data.signing_headroom} 
        windowData=${data.window} 
      />
      <${PlayerRecruitment} data=${data} triggerRefresh=${triggerRefresh} />
    </div>
  `;
};

// Keep the legacy DOM-built scouting desk behind its own component boundary.
// MarketTab used to call hooks only inside the scouting branch, so switching
// Players -> Scouting changed its hook order and left the first render blank.
const ScoutingPanel = () => {
  const containerRef = useRef(null);
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    node.innerHTML = "";
    scouting(node).catch(console.error);
    return () => { node.innerHTML = ""; };
  }, []);
  return html`<div ref=${containerRef}></div>`;
};


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
      toast(r.message); close(); refresh(); renderApp();
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
  panel.appendChild(el("div", "contract-leverage",
    `<span class="pill ${neg.leverage >= 75 ? "bad" : ""}">Leverage ${neg.leverage}/100</span> ` +
    `<span class="pill">Interest ${neg.interest}/100</span> ` +
    `<span class="pill">${neg.competing_clubs} alternative${neg.competing_clubs === 1 ? "" : "s"}</span> ` +
    `<span class="pill">deadline W${neg.deadline_week}</span>` +
    ((neg.leverage_reasons || []).length ? `<p class="muted">Why: ${neg.leverage_reasons.map(esc).join(" · ")}.</p>` : "")));
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
      toast(r.message); close(); refresh(); renderApp();
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

// F4/F5 — the two-lane standing-directive desk. Both lanes run in parallel
// every week with no re-pick: the pro lane scouts upcoming opponents (fast
// team-identity reads that decay on meta patches) or runs a continuous market
// sweep for a roster gap; the amateur lane tracks the academy and youth
// intake. Directive options, the auto-rotated opponent, progress and any
// role/caliber choices are all server-supplied; this only renders + POSTs.
function scoutLanesCard(lanes) {
  const card = el("div", "card scout-lanes");
  card.appendChild(el("h2", "", "Scouting lanes"));
  card.appendChild(el("p", "muted",
    "Two standing directives run in parallel — set them once and the department " +
    "works them every week. No weekly re-picks."));

  const post = async (body) => {
    const r = await api("/api/actions/scout-directive", body);
    toast(r.message); renderApp();
  };

  const grid = el("div", "scout-lanes-grid");

  // -- Pro lane --------------------------------------------------------------
  const pro = lanes.pro || {};
  const proTile = el("div", "tile scout-lane");
  proTile.appendChild(el("div", "scout-lane-head",
    `<span class="chip tone-accent">Pro</span><b>Opponents & market</b>`));
  const proOpts = pro.options && pro.options.length ? pro.options : [
    { value: "scout_opponents", label: "Scout upcoming opponents" },
    { value: "fill_gap", label: "Find a player to fill a gap" },
  ];
  const proBase = String(pro.directive || "").split(":")[0] || "";
  const proSel = el("select", "select");
  proSel.appendChild(el("option", "", "— no standing directive —"));
  for (const o of proOpts) {
    const opt = el("option", "", o.label || humanize(o.value));
    opt.value = o.value;
    if (o.value === proBase) opt.selected = true;
    proSel.appendChild(opt);
  }
  proTile.appendChild(proSel);

  // fill_gap needs a role + caliber; only shown when that directive is picked.
  const gapWrap = el("div", "scout-gap-row");
  const roleOpts = pro.role_options && pro.role_options.length ? pro.role_options
    : ["duelist", "controller", "initiator", "sentinel", "flex"];
  const calOpts = pro.caliber_options && pro.caliber_options.length ? pro.caliber_options
    : ["star", "tier1", "starter", "tier2"];
  const parts = String(pro.directive || "").split(":");
  const roleSel = el("select", "sel-sm");
  for (const x of roleOpts) { const o = el("option", "", humanize(x)); o.value = x; if (x === parts[1]) o.selected = true; roleSel.appendChild(o); }
  const calSel = el("select", "sel-sm");
  for (const x of calOpts) { const o = el("option", "", humanize(x)); o.value = x; if (x === parts[2]) o.selected = true; calSel.appendChild(o); }
  gapWrap.append(el("span", "muted", "gap:"), roleSel, calSel);
  const syncGap = () => { gapWrap.style.display = proSel.value === "fill_gap" ? "" : "none"; };
  syncGap();
  proTile.appendChild(gapWrap);

  const proSave = el("button", "btn btn-sm btn-primary", "Set pro lane");
  proSave.onclick = () => {
    if (!proSel.value) return post({ lane: "pro", directive: null });
    if (proSel.value === "fill_gap") {
      return post({ lane: "pro", directive: "fill_gap", role: roleSel.value, caliber: calSel.value });
    }
    return post({ lane: "pro", directive: proSel.value });
  };
  proSel.onchange = syncGap;
  proTile.appendChild(proSave);

  // Current standing + auto-rotated opponent.
  if (pro.opponent) {
    proTile.appendChild(el("div", "newsline",
      `<b>This week:</b> ${tlink(pro.opponent.id, pro.opponent.name)}` +
      `${pro.opponent.week != null ? ` <span class="muted">(W${pro.opponent.week})</span>` : ""}` +
      `${pro.progress != null ? ` <span class="chip">${Math.round(pro.progress * 100)}%</span>` : ""}`));
  } else if (pro.status_label) {
    proTile.appendChild(el("p", "muted", esc(pro.status_label)));
  }
  grid.appendChild(proTile);

  // -- Amateur lane ----------------------------------------------------------
  const am = lanes.amateur || {};
  const amTile = el("div", "tile scout-lane");
  amTile.appendChild(el("div", "scout-lane-head",
    `<span class="chip">Amateur</span><b>Academy & youth</b>`));
  const amOpts = am.options && am.options.length ? am.options : [
    { value: "track_academy", label: "Track our academy & youth intake" },
  ];
  const amSel = el("select", "select");
  amSel.appendChild(el("option", "", "— no standing directive —"));
  for (const o of amOpts) {
    const opt = el("option", "", o.label || humanize(o.value));
    opt.value = o.value;
    if (o.value === (am.directive || "")) opt.selected = true;
    amSel.appendChild(opt);
  }
  amTile.appendChild(amSel);
  const amSave = el("button", "btn btn-sm btn-primary", "Set amateur lane");
  amSave.onclick = () => post({ lane: "amateur", directive: amSel.value || null });
  amTile.appendChild(amSave);
  const focus = am.focus || am.tracked || [];
  if (focus.length) {
    amTile.appendChild(el("p", "microlabel", "Tracking"));
    for (const f of focus) {
      amTile.appendChild(el("div", "newsline",
        `${plink(f.id, f.handle)}${f.note ? ` <span class="muted">${esc(f.note)}</span>` : ""}` +
        `${f.progress != null ? ` <span class="chip">${Math.round(f.progress * 100)}%</span>` : ""}`));
    }
  } else if (am.status_label) {
    amTile.appendChild(el("p", "muted", esc(am.status_label)));
  }
  grid.appendChild(amTile);

  card.appendChild(grid);
  return card;
}

// F4 — the continuous market-sweep shortlist the pro "fill_gap" directive
// produces. Recommendations only; no re-pick. Each row deep-links the player
// profile and offers a one-click deep-dive assignment.
function scoutShortlistCard(shortlist, proLane) {
  const card = el("div", "card scout-shortlist");
  const gap = proLane && proLane.directive && proLane.directive.startsWith("fill_gap")
    ? proLane.directive.split(":").slice(1).map(humanize).filter(Boolean).join(" · ")
    : "";
  card.innerHTML = `<h2>Shortlist${gap ? ` <span class="muted" style="font-weight:400">— ${esc(gap)}</span>` : ""}</h2>` +
    `<p class="muted">Continuous market sweep — the department keeps this list fresh.</p>`;
  for (const p of shortlist) {
    const row = el("div", "entity");
    const band = (p.uncertainty_low != null && p.uncertainty_high != null)
      ? ` <span class="muted" title="scout-precision uncertainty band">±${starsRange([p.uncertainty_low, p.uncertainty_high])}</span>`
      : "";
    row.innerHTML = `<span class="entity-name">${plink(p.player_id, p.handle)}</span>` +
      `<span class="entity-meta">${esc(p.role || "")}${p.team_name ? " · " + esc(p.team_name) : " · free agent"}` +
      `${p.ca_stars ? " · " + starsRange(p.ca_stars) : ""}${band}</span>`;
    const b = el("button", "btn btn-sm", "Deep-dive");
    b.onclick = async () => {
      const r = await api("/api/actions/scout", { player_id: p.player_id });
      toast(r.message); renderApp();
    };
    row.appendChild(b);
    card.appendChild(row);
  }
  return card;
}

// Scouting desk body. Only reachable as the Market tab's Scouting sub-tab
// (the old standalone Scouting screen was removed; TAB_ALIASES routes the
// old tab id to market/scouting). MarketTab renders the Market head with
// the Players / Scouting / Staff segment, so this owns just the workspace.
async function scouting(v) {
  const data = await api("/api/scouting");
  const surveyPct = Math.round((data.caps?.survey ?? 0) * 100);
  const matchPct = Math.round((data.caps?.match ?? 0) * 100);
  const deepPct = Math.round((data.caps?.deep_dive ?? 0) * 100);

  // Preparation target comes from the server: the opponent after the match
  // currently being planned. No following fixture (bye/offseason) hides it.
  const planningOpp = data.planning_opponent;

  const ws = el("div", "ws");
  v.appendChild(ws);
  const main = el("div", "ws-7 ws-col");
  const rail = el("div", "ws-5 ws-col");
  ws.appendChild(main);
  ws.appendChild(rail);

  // F4/F5 — parallel standing-directive lanes replace the single-slot picker.
  // The department advances both the pro and amateur lanes every week with no
  // re-pick; the pro lane auto-rotates onto the next opponent or runs a
  // continuous market sweep that produces a shortlist. Rendered only when the
  // server ships lanes; otherwise the legacy single-slot desk below stands in.
  const lanes = data.lanes;
  if (lanes) {
    main.appendChild(scoutLanesCard(lanes));
    const shortlist = data.shortlist || [];
    if (shortlist.length) main.appendChild(scoutShortlistCard(shortlist, lanes.pro));
  }

  /* -- main ws-7: the scout desk (assignment + active job) ------------------ */
  const card = el("div", "card scout-desk");
  card.appendChild(el("h2", "", lanes ? "Deep-dive desk" : "Scout desk"));
  card.appendChild(el("p", "muted", lanes
    ? `Your standing lanes run continuously above. Use the desk for a one-off ` +
      `deep assignment: attend a specific match, or build the book on one player ` +
      `(${deepPct}% depth — comfort picks, how they play, their mentality, the full verdict).`
    : `One scout, one assignment: survey a team or the market (broad read, capped ` +
      `at ${surveyPct}%), attend a match (behavioral intel up to ${matchPct}%), or build the book on ` +
      `one player (${deepPct}% information depth — still not own-roster certainty): comfort picks, ` +
      "how they play, their mentality, the full verdict)."));
  if (!lanes) {
    card.appendChild(el("div", "scout-one-note",
      `<span class="chip tone-accent">One active job</span>` +
      `<b>Choose one of the three assignments below.</b> ` +
      `<span class="muted">Starting another immediately replaces the current job.</span>`));
  }

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
  coverageChoice.appendChild(el("span", "muted scout-choice-copy", `Survey everyone on the beat up to ${surveyPct}% information.`));
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
    renderApp();
  };
  coverageChoice.appendChild(sel);
  // The single-slot "cover a beat" survey is exactly what the standing pro
  // lane replaces, so hide it once lanes are live.
  if (!lanes) choices.appendChild(coverageChoice);

  // Attend a match (next two weeks, not your own games).
  const matchChoice = el("div", "tile scout-choice");
  matchChoice.appendChild(el("div", "scout-choice-head",
    `<span class="chip">${lanes ? 1 : 2}</span><b>Attend a match</b>`));
  matchChoice.appendChild(el("span", "muted scout-choice-copy", `One-shot behavioral intel on both teams, up to ${matchPct}%.`));
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
      renderApp();
    };
  }
  matchChoice.appendChild(fsel);
  choices.appendChild(matchChoice);

  // Deep-dive a player: search league-wide, click to assign.
  const playerChoice = el("div", "tile scout-choice");
  playerChoice.appendChild(el("div", "scout-choice-head",
    `<span class="chip">${lanes ? 2 : 3}</span><b>Deep-dive a player</b>`));
  playerChoice.appendChild(el("span", "muted scout-choice-copy", "External full books stay uncertain; own-player books add weekly training guidance."));
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
        const b = el("button", "btn btn-sm",
          `${esc(p.handle)} <span class="muted">${p.mine ? "our player · development" : esc(p.team_name ?? "free agent")}</span>`);
        b.onclick = async () => {
          const res = await api("/api/actions/scout", { player_id: p.id });
          toast(res.message);
          renderApp();
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
    if (r.training_hint) {
      lines.push(`<div><b>Training recommendation:</b> <span class="pill">${esc(r.training_hint.focus)}</span> ` +
        `${esc(r.training_hint.reason)}</div>`);
      if (r.own_player) {
        lines.push(`<div class="muted">Match this player's focus this week for the active-scout development bonus.</div>`);
      }
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
    [0.75, "Mental read", "mentality, development fit"],
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

  // F4/F5 — the department's recommended deep-dives: targeted assignments the
  // scouting staff surfaces (roster gaps, promising prospects). One click
  // points the deep-dive desk at the recommended player.
  const recs = data.deep_dive_recommendations || [];
  if (recs.length) {
    const rc = el("div", "card");
    rc.appendChild(el("h2", "", "Recommended deep-dives"));
    rc.appendChild(el("p", "muted", "The department flags these for a closer look — click to build the book."));
    for (const rec of recs) {
      const row = el("div", "entity");
      row.innerHTML = `<span class="entity-name">${plink(rec.id, rec.handle)}</span>` +
        `<span class="entity-meta">${esc(rec.reason || rec.note || "flagged by scouting")}</span>`;
      const b = el("button", "btn btn-sm", "Assign");
      b.onclick = async () => {
        const r = await api("/api/actions/scout", { player_id: rec.id });
        toast(r.message); renderApp();
      };
      row.appendChild(b);
      rc.appendChild(row);
    }
    rail.appendChild(rc);
  }

  // Quick assign: point the scout at the next opponent or the market in a click.
  const qa = el("div", "card");
  qa.appendChild(el("h2", "", "Quick assign"));
  // Each button on its own line (block wrapper) so long labels don't crowd.
  const addQuick = (btn) => { const w = el("div", ""); w.appendChild(btn); qa.appendChild(w); };
  if (planningOpp) {
    const b = el("button", "btn btn-sm" + (data.target === planningOpp.id ? " active" : ""),
      `Scout next week's opponent — ${esc(planningOpp.name)} (W${planningOpp.week})`);
    b.onclick = async () => {
      const r = await api("/api/actions/scout", { team_id: planningOpp.id });
      toast(r.message); renderApp();
    };
    addQuick(b);
  }
  const bm = el("button", "btn btn-sm" + (data.target === "market" ? " active" : ""),
    "Sweep the free-agent market");
  bm.onclick = async () => {
    const r = await api("/api/actions/scout", { team_id: "market" });
    toast(r.message); renderApp();
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
  { k: "xduel_expected_wins", h: "xDuel Exp" },
  { k: "xduel_actual_wins", h: "xDuel Act" },
  { k: "xde", h: "xDE", f: (v) => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
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
  // survives the renderApp() they trigger — the sub-tab never resets.
  const right = [];
  const tierSeg = el("div", "seg");
  const mkTier = (label, tval) => {
    const b = el("button", "seg-btn" + (lgTier === tval ? " on" : ""), label);
    b.onclick = () => { App.statsTier = tval; renderApp(); };
    tierSeg.appendChild(b);
  };
  mkTier("Tier 1", 1);
  mkTier("Challengers", 2);
  right.push(tierSeg);
  if (data.split_keys) {
    const splitRow = el("div", "row");
    const seasonBtn = el("button", "btn btn-sm" + (split ? "" : " active"), "Season");
    seasonBtn.onclick = () => { App.statsSplit = null; renderApp(); };
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
      sel.onchange = () => { if (sel.value) { App.statsSplit = { kind, key: sel.value }; renderApp(); } };
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
    onPick: (id) => { App.statsTab = id; renderApp(); },
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

/* -- brand: the social feed + follower economy, in Company ----------------- */

const POST_KIND_ICON = {
  result: "🏁", hype: "🔥", viral: "📈", drama: "⚡", milestone: "🎉", transfer: "✍",
};

/* The old standalone Social tab is now Company's "Brand" sub-tab
   (TAB_ALIASES routes "social" here). Same /api/social read, ported to compact
   htm components. Link markup (plink/tlink) arrives as HTML strings, so rows
   render via dangerouslySetInnerHTML — the document-level [data-pid]/[data-tid]
   delegation in profile.js picks the links up like everywhere else. */

const BrandFeedPost = ({ post }) => {
  const who = post.author_kind === "player"
    ? `<b>${plink(post.author_id, "@" + post.author)}</b>`
    : post.author_kind === "team"
      ? `<b>${tlink(post.author_id, "@" + post.author)}</b>`
      : `<b>${esc(post.author)}</b>`;
  // LLM-ghost-written posts keep the grounded fact on hover; the server only
  // ever rephrases real outcomes (web/llm_social.py).
  const fact = post.ai && post.fact ? ` title="${esc(post.fact)}"` : "";
  const inner =
    `<div class="post-head">${POST_KIND_ICON[post.kind] ?? "·"} ${who}
       <span class="muted">S${post.season} W${post.week}</span></div>
     <div class="post-body"${fact}>${post.text}</div>
     <div class="post-likes muted">♥ ${fmtFollowers(post.likes)}</div>`;
  return html`<div class="post" dangerouslySetInnerHTML=${{ __html: inner }}></div>`;
};

const BrandReachCard = ({ data }) => {
  // Mood word/tone come from the server (social.mood_view) — the UI never
  // re-derives sim thresholds.
  const mood = data.your_sentiment ?? 50;
  const moodWord = data.your_mood?.word ?? "neutral";
  const moodTone = data.your_mood?.tone ?? "";
  return html`
    <div class="card">
      <h2>Your reach</h2>
      <div class="row">
        <span class="chip">roster reach ${fmtFollowers(data.your_reach)}</span>
        <span class="chip">org fans ${fmtFollowers(data.fan_count)}</span>
        <span class=${`pill ${moodTone}`}>fanbase ${moodWord} (${Math.round(mood)})</span>
      </div>
      <div class="tile stream-income-tile">
        <span class="stream-income-icon">↗</span>
        <span>
          <span class="microlabel">Streamer revenue</span>
          <b class="mono stream-income-value">${money(data.your_stream_income || 0)}/wk</b>
          <span class="muted">direct weekly org income</span>
        </span>
      </div>
      <p class="muted">
        Reach feeds sponsor marketability; streaming pays the org a cut (heavy streamers
        develop slower — rein one in with a 1:1); the crowd's mood leaks into the locker
        room, and brands read the room too.
      </p>
      ${data.your_roster.length > 0 && html`
        <span class="es-scout-lab muted">Your streamers</span>
        <div class="row offer-row">
          ${data.your_roster.map((p) => html`
            <span class="pill" key=${p.player_id} dangerouslySetInnerHTML=${{ __html:
              `<b>${plink(p.player_id, p.handle)}</b> ${fmtFollowers(p.followers)} ` +
              `<span class="muted" title="${esc(p.stream_status)} — org cut ${money(p.stream_income)}/wk">· ${money(p.stream_income)}/wk</span>` }}></span>
          `)}
        </div>
      `}
    </div>
  `;
};

const BrandMoodCard = ({ sentiment }) => {
  // Community mood board: whose fans are euphoric, whose are done.
  if (!sentiment.length) return null;
  const hot = sentiment.slice(0, 5);
  const cold = sentiment.slice(-3);
  const rows = [...hot, ...cold.filter((r) => !hot.includes(r))];
  return html`
    <div class="card">
      <h2>Fanbase mood</h2>
      <table>
        <thead><tr><th>Team</th><th class="num">Mood</th></tr></thead>
        <tbody>
          ${rows.map((r) => html`
            <tr class=${r.is_user ? "me" : ""} key=${r.team_id} dangerouslySetInnerHTML=${{ __html: `
              <td><b>${tlink(r.team_id, r.name)}</b> <span class="pill">${esc(r.tag)}</span></td>
              <td class="num ${r.tone ?? ""}">${Math.round(r.sentiment)}
                <span class="muted">${esc(r.word ?? "")}</span></td>` }}></tr>
          `)}
        </tbody>
      </table>
    </div>
  `;
};

const BrandLeaderboardCard = ({ leaderboard }) => html`
  <div class="card">
    <h2>Most followed</h2>
    <table>
      <thead><tr><th>#</th><th>Player</th><th>Team</th>
        <th class="num">Followers</th></tr></thead>
      <tbody>
        ${leaderboard.map((r, i) => html`
          <tr class=${r.is_user ? "me" : ""} key=${r.player_id} dangerouslySetInnerHTML=${{ __html: `
            <td>${i + 1}</td>
            <td><b>${plink(r.player_id, r.handle)}</b></td>
            <td class="muted">${tlink(r.team_id, r.team_tag)}</td>
            <td class="num">${fmtFollowers(r.followers)}</td>` }}></tr>
        `)}
      </tbody>
    </table>
  </div>
`;

const BrandMovementCard = ({ moves }) => {
  // Movement tracker: every signing/release/renewal/transfer league-wide —
  // including AI-to-AI moves — straight off the chronicle. Names are regex-
  // plinked in the prose; the team tag becomes a tlink via the row's team_id.
  if (!moves.length) return null;
  const KIND_BADGE = {
    signing: ["signing", "good"], release: ["release", "bad"],
    renewal: ["renewal", ""], transfer: ["transfer", "warn"], poach: ["poach", "bad"],
    dismissal: ["sacked", "bad"], appointment: ["hired", "good"],
  };
  return html`
    <div class="card">
      <h2>Movement tracker</h2>
      <p class="muted">Every move in the league, newest first — watch what rival orgs are doing.</p>
      <div class="card-scroll" style=${{ "--scroll-max": "340px" }}>
        <div class="es-movement">
          ${moves.map((m, i) => {
            const [label, tone] = KIND_BADGE[m.kind] || [m.kind, ""];
            const text = m.player_id
              ? m.text.replace(/^([\w' .-]+?)(?= joins| re-signs| retires|\.)/,
                  `<span class="plink" data-pid="${esc(m.player_id)}">$1</span>`)
              : m.text;
            const teamPill = m.team_tag ? `<span class="pill">${tlink(m.team_id, m.team_tag)}</span> ` : "";
            return html`
              <div class=${"es-move" + (m.mine ? " mine" : "")} key=${i} dangerouslySetInnerHTML=${{ __html:
                `<span class="pill ${tone}">${label}</span> ` +
                `<span class="muted mono">S${m.season}·W${m.week}</span> ` +
                teamPill + text }}></div>
            `;
          })}
        </div>
      </div>
    </div>
  `;
};

const BrandSection = () => {
  const [soc, setSoc] = useState(null);

  useEffect(() => {
    api("/api/social").then(setSoc).catch(console.error);
  }, []);

  if (!soc) return html`<div class="loading">Loading brand...</div>`;
  return html`
    <div id="fin-brand">
      <p class="screen-sub">Reach ${fmtFollowers(soc.your_reach)} · ${fmtFollowers(soc.fan_count)} fans</p>
      <div class="ws">
        <div class="ws-7 ws-col">
          <div class="card">
            <h2>Feed</h2>
            ${soc.feed.length === 0
              ? html`<p class="muted">Nothing posted yet — play a week.</p>`
              : html`
                <div class="card-scroll" style=${{ "--scroll-max": "48vh" }}>
                  ${soc.feed.map((post, i) => html`<${BrandFeedPost} post=${post} key=${i} />`)}
                </div>
              `}
          </div>
        </div>
        <div class="ws-5 ws-col">
          <${BrandReachCard} data=${soc} />
          <${BrandMoodCard} sentiment=${soc.sentiment ?? []} />
          <${BrandLeaderboardCard} leaderboard=${soc.leaderboard} />
          <${BrandMovementCard} moves=${soc.movement || []} />
        </div>
      </div>
    </div>
  `;
};

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
async function company(v) {
  v.innerHTML = "";
  render(html`<${CompanyTab} />`, v);
}

const COMPANY_TABS = [
  { id: "finances", label: "Finances" },
  { id: "brand", label: "Brand" },
];

const CompanyTab = () => {
  const [active, setActive] = useState(App.companyTab ?? "finances");
  useEffect(() => { App.companyTab = active; }, [active]);
  return html`
    <div>
      <div class="screen-head">
        <span class="screen-title">Company</span>
        <div class="seg">
          ${COMPANY_TABS.map((tab) => html`
            <button key=${tab.id} class=${`seg-btn${active === tab.id ? " on" : ""}`}
              onClick=${() => setActive(tab.id)}>${tab.label}</button>
          `)}
        </div>
      </div>
      ${active === "brand"
        ? html`<${BrandSection} />`
        : html`<${FinancesTab} onOpenBrand=${() => setActive("brand")} />`}
    </div>
  `;
};

const ObjectiveChip = ({ obj }) => {
  const mark = obj.met === true ? "✓ " : obj.met === false ? "✗ " : "";
  let cls = obj.met === true ? "good" : obj.met === false ? "bad" : "";
  let prog = "";
  if (obj.met == null && obj.status) {
    const st = obj.status.state;
    cls = st === "achieved" || st === "on_track" ? "good"
      : st === "missed" ? "bad" : "warn";
    prog = ` · ${st.replace("_", " ")}`;
  }
  const tip = obj.status?.detail || money(obj.bonus);
  return html`
    <span class=${`pill obj ${cls}`} title=${tip}>
      ${mark}${obj.label} → ${money(obj.bonus)}${prog}
    </span>
  `;
};

const ObjectiveChipsList = ({ objs }) => {
  if (!objs || objs.length === 0) return null;
  return html`
    <div class="row offer-row">
      ${objs.map((o, idx) => html`<${ObjectiveChip} obj=${o} key=${idx} />`)}
    </div>
  `;
};

const StatTile = ({ label, value, tone, sub, tooltip, onClick }) => {
  const cls = "es-tile" + (tone ? " tone-" + tone : "") + (onClick ? " es-tile-btn" : "");
  return html`
    <div class=${cls} title=${tooltip} onClick=${onClick} style=${onClick ? { cursor: 'pointer' } : undefined}>
      <div class="es-tile-val mono">${value}</div>
      <div class="es-tile-label">${label}</div>
      ${sub && html`<div class="es-tile-sub">${sub}</div>`}
    </div>
  `;
};

const CashProjectionSparkline = ({ projection }) => {
  if (!projection || projection.length < 2) return null;
  const W = 220, H = 46;
  const bals = projection.map((p) => p.balance);
  const lo = Math.min(...bals), hi = Math.max(...bals), span = (hi - lo) || 1;
  const pts = projection.map((p, i) => {
    const x = (i / (projection.length - 1)) * (W - 4) + 2;
    const y = H - 4 - ((p.balance - lo) / span) * (H - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return html`
    <div class="es-spark">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="projected balance">
        <polyline points=${pts} fill="none" class="es-spark-line" />
      </svg>
      <span class="muted">${money(projection[projection.length - 1].balance)} in ${projection.length}w</span>
    </div>
  `;
};

const FinancesTab = ({ onOpenBrand }) => {
  const [data, setData] = useState(null);
  const [actionInProgress, setActionInProgress] = useState(null);

  const fetchData = async () => {
    try {
      const res = await api("/api/finances");
      setData(res);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSponsorAction = async (slot, accept, brand, structure) => {
    const actionKey = `sponsor-${slot}-${brand || 'decline'}`;
    setActionInProgress(actionKey);
    try {
      const payload = { slot, accept };
      if (brand) payload.brand = brand;
      if (structure) payload.structure = structure;
      
      const r = await api("/api/actions/sponsor", payload);
      toast(r.message);
      
      if (window.refresh) {
        await window.refresh();
      }
      await fetchData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionInProgress(null);
    }
  };

  if (!data) return html`<div class="loading">Loading finances...</div>`;

  const b = data.breakdown;
  const SLOT_LABELS = {
    title: "Title", jersey: "Jersey", peripheral: "Peripheral",
    stream: "Stream", apparel: "Apparel",
  };

  const handleDemandAction = async (demandId, accept) => {
    const actionKey = `demand-${demandId}`;
    setActionInProgress(actionKey);
    try {
      const r = await api("/api/actions/sponsor_demand", {
        demand_id: demandId, accept,
      });
      toast(r.message);
      if (window.refresh) await window.refresh();
      await fetchData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionInProgress(null);
    }
  };

  return html`
    <div>
      <p class="screen-sub">${money(data.balance)} banked · net ${b.net >= 0 ? "+" : ""}${money(b.net)}/wk</p>
      
      <div class="ws">
        <div class="ws-7 ws-col">
          <div class="card">
            <h2>
              Sponsorships <span class="muted" style=${{ fontWeight: 400 }}>— marketability ${data.marketability ?? "?"}</span>
            </h2>
            ${data.demands && data.demands.length > 0 && html`
              <div class="slot-row" style=${{ borderLeftColor: "var(--es-color-accent-warm)" }}>
                <div class="row">
                  <span class="microlabel">Sponsor demands</span>
                  <span class="muted">specific match obligations with real financial stakes</span>
                </div>
                ${data.demands.map(d => {
                  const isBusy = actionInProgress === `demand-${d.id}`;
                  const tone = d.status === "met" ? "tone-good"
                    : d.status === "missed" || d.status === "expired" ? "tone-bad"
                    : d.status === "accepted" ? "tone-info" : "";
                  return html`
                    <div class="slot-row" key=${d.id} style=${{ borderLeft: "none", paddingLeft: 0, paddingRight: 0 }}>
                      <div class="row">
                        <span class=${`chip ${tone}`}>${d.status}</span>
                        <b>${d.brand}</b>
                        <span class="chip">${SLOT_LABELS[d.slot] || d.slot}</span>
                        <span class="muted">week ${d.deadline_week}</span>
                      </div>
                      <div>
                        <b>
                          ${d.kind === "field_rookie" ? html`
                            Play <span data-pid=${d.player_id}>${d.player_name}</span>
                            against <span data-tid=${d.opponent_id}>${d.opponent_name}</span>
                          ` : html`
                            Beat rivals <span data-tid=${d.opponent_id}>${d.opponent_name}</span>
                          `}
                        </b>
                      </div>
                      <div class="muted">${d.detail}</div>
                      <div class="row">
                        <span class="chip tone-good">reward ${money(d.reward)}</span>
                        <span class="chip tone-bad">failure -${money(d.penalty)}</span>
                        <span class="muted">brand relation ${d.relation}</span>
                      </div>
                      ${d.can_respond && html`
                        <div class="row offer-row">
                          <button class="btn btn-primary btn-sm" disabled=${isBusy}
                            onClick=${() => handleDemandAction(d.id, true)}>
                            ${isBusy ? "Saving..." : "Accept demand"}
                          </button>
                          <button class="btn btn-sm" disabled=${isBusy}
                            onClick=${() => handleDemandAction(d.id, false)}>
                            ${isBusy ? "..." : "Decline"}
                          </button>
                        </div>
                      `}
                    </div>
                  `;
                })}
              </div>
            `}
            ${["title", "jersey", "peripheral", "stream", "apparel"].map(slot => {
              const s = data.slots[slot];
              if (!s) return null;

              let stateChip, brand, rowClass = "slot-row";
              if (s.deal) {
                stateChip = html`<span class="chip tone-good">active</span>`;
                brand = html`<b>${s.deal.name}</b> <span class="chip">${s.deal.kind}</span>`;
                rowClass = "slot-row active-deal";
              } else if (!s.unlocked) {
                stateChip = html`<span class="chip">locked</span>`;
                brand = html`<span class="muted">${s.locked_reason ?? "unavailable"}</span>`;
              } else {
                stateChip = html`<span class="chip tone-info">open</span>`;
                brand = html`<span class="muted">no active deal — ${s.market && s.market.length ? "offers below" : "no suitors yet"}</span>`;
              }

              return html`
                <div key=${slot} class=${rowClass}>
                  <div class="row">
                    ${stateChip}
                    <span class="microlabel">${SLOT_LABELS[slot] || slot}</span>
                    ${brand}
                  </div>
                  ${s.deal && html`
                    <div class="row">
                      <span class="muted">${dealLine(s.deal)}</span>
                    </div>
                    <${ObjectiveChipsList} objs=${s.objective_labels_deal} />
                  `}

                  ${s.offer && (() => {
                    const isBusy = actionInProgress && actionInProgress.startsWith(`sponsor-${slot}`);
                    return html`
                      <div class="slot-row" style=${{ borderLeft: 'none', paddingLeft: 0, paddingRight: 0 }}>
                        <div class="row">
                          <span class="chip tone-info">offer</span>
                          <b>${s.offer.name}</b> 
                          <span class="chip">${s.offer.kind}</span> 
                          <span class="muted">${dealLine(s.offer)} — expires if unanswered this week</span>
                        </div>
                        <div class="row offer-row">
                          <button 
                            class="btn btn-primary btn-sm" 
                            disabled=${isBusy}
                            onClick=${() => handleSponsorAction(slot, true)}
                          >
                            ${isBusy ? "Saving..." : "Accept"}
                          </button>
                          <button 
                            class="btn btn-sm" 
                            disabled=${isBusy}
                            onClick=${() => handleSponsorAction(slot, false)}
                          >
                            ${isBusy ? "..." : "Decline"}
                          </button>
                        </div>
                      </div>
                    `;
                  })()}

                  ${s.market && s.market.map(o => {
                    const relationTag = o.relation > 55 ? " · warm relations" : o.relation < 45 ? " · cool relations" : "";
                    const structures = [
                      ["upfront", `${money(o.upfront.signing_bonus)} now + ${money(o.upfront.weekly)}/wk`],
                      ["steady", `${money(o.steady.weekly)}/wk`],
                      ["performance", `${money(o.performance.weekly)}/wk + ${money(o.performance.per_win)}/win`],
                    ];
                    const isBusy = actionInProgress && actionInProgress.startsWith(`sponsor-${slot}-${o.brand}`);
                    
                    return html`
                      <div class="slot-row" key=${o.brand} style=${{ borderLeft: 'none', paddingLeft: 0, paddingRight: 0 }}>
                        <div class="row">
                          <span class="chip tone-info">offer</span>
                          <b>${o.brand}</b> 
                          <span class="muted">${o.weeks}w · until wk ${o.expires_week}${relationTag}</span>
                        </div>
                        <${ObjectiveChipsList} objs=${o.objective_labels} />
                        <div class="row offer-row">
                          ${structures.map(([structure, label]) => {
                            const btnTitle = s.deal ? "slot occupied" : "objective bonuses scale: upfront ×0.7, steady ×1.0, performance ×1.4";
                            return html`
                              <button 
                                class="btn btn-sm" 
                                disabled=${!!s.deal || isBusy}
                                title=${btnTitle}
                                onClick=${() => handleSponsorAction(slot, true, o.brand, structure)}
                                key=${structure}
                              >
                                ${isBusy ? "Saving..." : `${structure}: ${label}`}
                              </button>
                            `;
                          })}
                          <button 
                            class="btn btn-sm" 
                            title="decline (the brand remembers)"
                            disabled=${isBusy}
                            onClick=${() => handleSponsorAction(slot, false, o.brand)}
                          >
                            ${isBusy ? "..." : "✕"}
                          </button>
                        </div>
                      </div>
                    `;
                  })}
                </div>
              `;
            })}
          </div>

        </div>

        <div class="ws-5 ws-col">
          <div class="card">
            <h2>This week</h2>
            <div class="es-tiles">
              <${StatTile} label="Balance" value=${money(data.balance)} />
              <${StatTile} 
                label="Net / wk" 
                value=${`${b.net >= 0 ? "+" : ""}${money(b.net)}`} 
                tone=${b.net >= 0 ? "good" : "bad"} 
              />
              <${StatTile} label="Income" value=${money(b.income_total)} tone="good" />
              <${StatTile} label="Expenses" value=${money(b.expense_total)} tone="bad" />
              ${data.last_week_income != null && html`
                <${StatTile} label="Last income" value=${money(data.last_week_income)} />
              `}
              ${data.last_week_expenses != null && html`
                <${StatTile} label="Last exp." value=${money(data.last_week_expenses)} />
              `}
            </div>
          </div>

          <div class="card">
            <h2>This week's run rate</h2>
            <table data-nosort="1">
              <thead>
                <tr>
                  <th>Item</th>
                  <th class="num">cr / wk</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Base sponsorship</td>
                  <td class="num">${money(b.sponsors_base)}</td>
                </tr>
                <tr>
                  <td>Title sponsor</td>
                  <td class="num">${money(b.sponsors_by_slot.title || 0)}</td>
                </tr>
                <tr>
                  <td>Jersey sponsor</td>
                  <td class="num">${money(b.sponsors_by_slot.jersey || 0)}</td>
                </tr>
                <tr>
                  <td>Peripheral sponsor</td>
                  <td class="num">${money(b.sponsors_by_slot.peripheral || 0)}</td>
                </tr>
                <tr>
                  <td>Merchandise</td>
                  <td class="num">${money(b.merch)}</td>
                </tr>
                <tr>
                  <td>Ticket sales</td>
                  <td class="num">${money(b.tickets)}</td>
                </tr>
                <tr>
                  <td>
                    Streaming
                    <button class="btn btn-sm" onClick=${onOpenBrand}>→ Brand</button>
                  </td>
                  <td class="num">${money(b.streaming || 0)}</td>
                </tr>
                <tr>
                  <td>Prize money</td>
                  <td class="num">${money(b.prizes)}</td>
                </tr>
                <tr>
                  <td class="mono"><b>Income total</b></td>
                  <td class="num mono"><b>${money(b.income_total)}</b></td>
                </tr>
                <tr>
                  <td>
                    Salaries 
                    <button class="btn btn-sm" onClick=${() => { App.clubTab = "squad"; window.dashGoTab("club"); }}>→ Squad</button>
                  </td>
                  <td class="num">-${money(b.salaries)}</td>
                </tr>
                <tr>
                  <td>Staff</td>
                  <td class="num">-${money(b.staff)}</td>
                </tr>
                <tr>
                  <td>
                    Facility upkeep
                    <button class="btn btn-sm" onClick=${() => window.dashGoTab("facilities")}>→ Facilities</button>
                  </td>
                  <td class="num">-${money(b.facility_upkeep)}</td>
                </tr>
                <tr>
                  <td class="mono"><b>Expense total</b></td>
                  <td class="num mono"><b>-${money(b.expense_total)}</b></td>
                </tr>
                <tr>
                  <td><b>Net</b></td>
                  <td class="num"><b>${b.net >= 0 ? "+" : ""}${money(b.net)}</b></td>
                </tr>
              </tbody>
            </table>
            <p class="muted">
              A live run-rate snapshot from the current roster, staff, sponsors and facilities — not a ledger of a specific past week.
            </p>
          </div>

          <div class="card">
            <h2>8-week cash projection</h2>
            <${CashProjectionSparkline} projection=${data.projection} />
            <table data-nosort="1">
              <thead>
                <tr>
                  <th>Week</th>
                  <th class="num">Net</th>
                  <th class="num">Balance</th>
                </tr>
              </thead>
              <tbody>
                ${data.projection && data.projection.map(p => html`
                  <tr key=${p.week}>
                    <td>W${p.week}</td>
                    <td class="num">${p.net >= 0 ? "+" : ""}${money(p.net)}</td>
                    <td class="num">${money(p.balance)}</td>
                  </tr>
                `)}
              </tbody>
            </table>
            <p class="muted">
              Assumes current sponsors, facilities and roster hold steady; sponsor slot deals drop off as they expire. Prize money and roster moves aren't modeled.
            </p>
          </div>

          ${data.marketability_breakdown && data.marketability_breakdown.drivers && data.marketability_breakdown.drivers.length > 0 && (() => {
            const mb = data.marketability_breakdown;
            const maxAbs = Math.max(...mb.drivers.map((d) => Math.abs(d.contrib)), 0.01);
            return html`
              <div class="card">
                <h2>
                  Brand value <span class="muted" style=${{ fontWeight: 400 }}>— marketability ${mb.score} (facility ×${mb.facility_mult})</span>
                </h2>
                <div class="es-mb">
                  ${mb.drivers.map(d => {
                    const pos = d.contrib >= 0;
                    const w = Math.round(100 * Math.abs(d.contrib) / maxAbs);
                    return html`
                      <div class="es-mb-row" key=${d.label}>
                        <span class="es-mb-lab">${d.label}</span>
                        <span class="es-mb-track">
                          <span class=${`es-mb-fill ${pos ? "pos" : "neg"}`} style=${{ width: `${w}%` }}></span>
                        </span>
                        <span class=${`mono ${pos ? "trend-up" : "trend-down"}`}>
                          ${pos ? "+" : ""}${d.contrib}
                        </span>
                      </div>
                    `;
                  })}
                </div>
              </div>
            `;
          })()}
        </div>
      </div>

    </div>
  `;
};


/* -- talk 1:1 ---------------------------------------------------------------------- */

async function openTalk(p) {
  const data = await api(`/api/talk/${p.id}`);
  
  $("#talk-title").textContent = `1:1 — ${p.handle}`;
  
  const textEl = $("#talk-text");
  const logBox = $("#talk-chat-logs");
  const choicesEl = $("#talk-chat-choices");
  
  logBox.innerHTML = "";
  choicesEl.innerHTML = "";

  if (!data.available) {
    if (data.history) {
      textEl.textContent = "You already held this week's 1:1 with this player.";
      
      const managerBubble = el("div", "contract-bubble manager", "You initiated 1:1 conversation.");
      logBox.appendChild(managerBubble);
      
      const reply = data.history.message || "";
      const playerBubble = el("div", "contract-bubble player");
      playerBubble.innerHTML = `<span class="microlabel" style="display:block;margin-bottom:4px;">${esc(p.handle)}</span>${esc(reply)}`;
      logBox.appendChild(playerBubble);
      
      if (data.history.effects) {
        const fx = Object.entries(data.history.effects)
          .filter(([, v]) => v !== 0)
          .map(([k, v]) => `${k} ${v > 0 ? "+" : ""}${v}`)
          .join(", ");
        if (fx) {
          const sysMsg = el("div", "muted", `System: Resolve effects (${fx})`);
          sysMsg.style.cssText = "font-size:11px;text-align:center;margin:4px 0;";
          logBox.appendChild(sysMsg);
        }
      }
      
      choicesEl.innerHTML = `<div class="muted" style="text-align:center;padding:8px;">Talk session resolved for this week.</div>`;
    } else {
      toast(data.reason);
      return;
    }
    $("#talk").classList.remove("hidden");
    return;
  }

  textEl.textContent = `Topic: ${data.topic.text}`;
  
  let history = [];
  
  const renderChoices = (choices, isFinal) => {
    choicesEl.innerHTML = "";
    for (const choice of choices) {
      const btn = el("button", "btn btn-primary", choice.text);
      btn.style.cssText = "text-align:left;padding:8px 12px;font-size:12px;white-space:normal;display:block;width:100%;";
      btn.onclick = async () => {
        choicesEl.innerHTML = "";
        const mBubble = el("div", "contract-bubble manager", esc(choice.text));
        logBox.appendChild(mBubble);
        logBox.scrollTop = logBox.scrollHeight;
        
        history.push({ sender: "manager", text: choice.text });
        
        const typingBubble = el("div", "contract-bubble player muted", "Typing...");
        logBox.appendChild(typingBubble);
        logBox.scrollTop = logBox.scrollHeight;
        
        try {
          if (!isFinal) {
            const res = await api("/api/talk/generate_choices", { player_id: p.id, history: history });
            typingBubble.remove();
            
            if (res && res.ok) {
              const reply = res.player_response || "";
              const pBubble = el("div", "contract-bubble player");
              pBubble.innerHTML = `<span class="microlabel" style="display:block;margin-bottom:4px;">${esc(p.handle)}</span>${esc(reply)}`;
              logBox.appendChild(pBubble);
              
              history.push({ sender: "player", text: reply });
              logBox.scrollTop = logBox.scrollHeight;
              
              renderChoices(res.choices, true);
            } else {
              typingBubble.remove();
              toast("Failed to get player reply.");
            }
          } else {
            const res = await api("/api/talk/chat", { player_id: p.id, text: choice.text, intent: choice.intent });
            typingBubble.remove();
            
            if (res && res.ok) {
              const reply = res.message || "";
              const pBubble = el("div", "contract-bubble player");
              pBubble.innerHTML = `<span class="microlabel" style="display:block;margin-bottom:4px;">${esc(p.handle)}</span>${esc(reply)}`;
              logBox.appendChild(pBubble);
              
              const fx = Object.entries(res.effects)
                .filter(([, v]) => v !== 0)
                .map(([k, v]) => `${k} ${v > 0 ? "+" : ""}${v}`)
                .join(", ");
              if (fx) {
                const sysMsg = el("div", "muted", `System: Resolve effects (${fx})`);
                sysMsg.style.cssText = "font-size:11px;text-align:center;margin:4px 0;";
                logBox.appendChild(sysMsg);
              }
              
              logBox.scrollTop = logBox.scrollHeight;
              choicesEl.innerHTML = `<div class="muted" style="text-align:center;padding:8px;">Talk session resolved for this week.</div>`;
              toast("1:1 conversation resolved!");
              renderApp();
            } else {
              typingBubble.remove();
              toast("Failed to resolve conversation.");
            }
          }
        } catch (err) {
          typingBubble.remove();
          toast("Error communicating with player.");
        }
      };
      choicesEl.appendChild(btn);
    }
  };

  choicesEl.innerHTML = `<div class="muted" style="text-align:center;padding:8px;">Generating dialogue...</div>`;
  $("#talk").classList.remove("hidden");
  
  try {
    const res = await api("/api/talk/generate_choices", { player_id: p.id, history: [] });
    if (res && res.ok) {
      const greeting = res.player_response || "";
      const pBubble = el("div", "contract-bubble player");
      pBubble.innerHTML = `<span class="microlabel" style="display:block;margin-bottom:4px;">${esc(p.handle)}</span>${esc(greeting)}`;
      logBox.appendChild(pBubble);
      
      history.push({ sender: "player", text: greeting });
      logBox.scrollTop = logBox.scrollHeight;
      
      renderChoices(res.choices, false);
    } else {
      choicesEl.innerHTML = `<div class="muted" style="text-align:center;padding:8px;color:var(--es-color-danger);">Failed to load dialogue.</div>`;
    }
  } catch (err) {
    choicesEl.innerHTML = `<div class="muted" style="text-align:center;padding:8px;color:var(--es-color-danger);">Error generating dialogue.</div>`;
  }
}

function closeTalk() {
  $("#talk").classList.add("hidden");
}
window.closeTalk = closeTalk;

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
    // Refresh FIRST so the dashboard behind the reveal (and the reveal's
    // "Decisions settled" stage) render the new week's state.
    await refresh();
    if (!startWeekReveal(rep)) showReport(rep);
    // Refresh the Inbox badge and toast any newly-arrived unread mail.
    if (typeof inboxAfterAdvance === "function") await inboxAfterAdvance();
  } finally {
    if (!mpPolling) $("#advance-btn").disabled = false;
  }
};

// Sim ahead: batch up to 4 weeks in one press; the server stops the moment a
// trigger fires (playoff match up, expiring starter deal, incoming bid, board
// or money trouble, pending decision, offseason). Toast the stop reason, then
// stage the LAST advanced week through the usual reveal.
$("#simahead-btn").onclick = async () => {
  const btn = $("#simahead-btn");
  btn.disabled = true;
  $("#advance-btn").disabled = true;
  try {
    const res = await api("/api/actions/sim_ahead", {});
    await refresh(); // reveal stages read fresh App.state (see advance-btn)
    const label = res.stop_label;
    if (res.weeks > 0) {
      const n = `${res.weeks} week${res.weeks === 1 ? "" : "s"}`;
      toast(label ? `Simmed ${n} — stopped: ${label}.` : `Simmed ${n}.`);
    } else {
      toast(label ? `Not simming ahead — ${label}.` : "Nothing to sim.");
    }
    if (res.report) {
      if (!startWeekReveal(res.report)) showReport(res.report);
    }
    if (typeof inboxAfterAdvance === "function") await inboxAfterAdvance();
  } finally {
    btn.disabled = false;
    $("#advance-btn").disabled = false;
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
      await refresh();
      try {
        const r = await api("/api/report");
        if (r.report) {
          if (!startWeekReveal(r.report)) showReport(r.report);
        } else toast(`Week ${s.week} — everyone advanced.`);
      } catch {
        toast(`Week ${s.week} — everyone advanced.`);
      }
      if (typeof inboxAfterAdvance === "function") await inboxAfterAdvance();
      return;
    }
    setTimeout(tick, 2500);
  };
  setTimeout(tick, 2500);
}

/* -- advance-week staged reveal -----------------------------------------------
   The advance beat, staged instead of dumped: (1) your own series result,
   map scores counting up, (2) standings movement across the tick, (3) the
   "Decisions settled" grades — then the dashboard. Pure presentation over
   the advance payload (week_reveal is a thin server read) and the already-
   refreshed App.state; one click anywhere skips straight to the dashboard.
   Motion is CSS transitions — JS only schedules class flips + count-ups. */

let wrCancels = [];

function wrLater(fn, ms) {
  const id = setTimeout(fn, ms);
  wrCancels.push(() => clearTimeout(id));
}

function closeWeekReveal() {
  for (const cancel of wrCancels) cancel();
  wrCancels = [];
  const ov = $("#week-reveal");
  ov.classList.add("hidden");
  ov.innerHTML = "";
}

// Tiny numeric count-up (the entrance motion itself is CSS).
function wrCountUp(node, to, ms) {
  if (to <= 0) { node.textContent = String(to); return; }
  const steps = Math.max(1, Math.min(to, Math.round(ms / 40)));
  let i = 0;
  const iv = setInterval(() => {
    i++;
    node.textContent = String(Math.round((to * i) / steps));
    if (i >= steps) clearInterval(iv);
  }, ms / steps);
  wrCancels.push(() => clearInterval(iv));
}

// Returns false when the week holds nothing to stage (no own played
// fixture), so callers fall back to the classic report modal.
function startWeekReveal(rep) {
  const wr = rep.week_reveal;
  const myId = App.state?.user_team?.id;
  const f = wr && wr.fixture_id ? rep.fixtures.find((x) => x.id === wr.fixture_id) : null;
  if (!f || !myId) return false;
  closeWeekReveal(); // reset any prior run
  const ov = $("#week-reveal");
  ov.onclick = closeWeekReveal; // one click anywhere = skip to dashboard
  const wrap = el("div", "wr-wrap");
  ov.appendChild(wrap);

  const mineIsA = f.team_a === myId;
  const myName = mineIsA ? f.team_a_name : f.team_b_name;
  const oppName = mineIsA ? f.team_b_name : f.team_a_name;
  const won = f.winner_id === myId;

  // Stage 1 — your result, map by map.
  const s1 = el("div", "wr-stage");
  s1.appendChild(el("div", "wr-kicker",
    `${esc(stageLabel(f.stage))} · Season ${rep.season} · Week ${rep.week}`));
  s1.appendChild(el("div", "wr-vs",
    `${esc(myName)} <span class="wr-dim">vs</span> ${esc(oppName)}`));
  const maps = el("div", "wr-maps");
  s1.appendChild(maps);
  const rows = [];
  for (const r of f.results) {
    const mine = mineIsA ? r.score_a : r.score_b;
    const theirs = mineIsA ? r.score_b : r.score_a;
    const row = el("div", "wr-map",
      `<span>${esc(r.map_id)}</span>` +
      `<span class="mono"><b class="wr-n1">0</b>–<b class="wr-n2">0</b></span>`);
    maps.appendChild(row);
    rows.push({ row, mine, theirs });
  }
  const myMaps = mineIsA ? f.map_score[0] : f.map_score[1];
  const oppMaps = mineIsA ? f.map_score[1] : f.map_score[0];
  const verdict = el("div", `wr-verdict ${won ? "good" : "bad"}`,
    (won ? "Victory" : "Defeat") + (f.best_of > 1 ? ` ${myMaps}–${oppMaps}` : ""));
  s1.appendChild(verdict);
  wrap.appendChild(s1);

  // Stage timings: stage 1 in, then one map row (with count-up) at a time,
  // then the verdict, then the later stages.
  wrLater(() => s1.classList.add("on"), 60);
  rows.forEach((m, i) => {
    wrLater(() => {
      m.row.classList.add("on");
      wrCountUp(m.row.querySelector(".wr-n1"), m.mine, 650);
      wrCountUp(m.row.querySelector(".wr-n2"), m.theirs, 650);
    }, 550 + i * 950);
  });
  let t = 550 + rows.length * 950;
  wrLater(() => verdict.classList.add("on"), t);
  t += 1000;

  // Stage 2 — standings movement (regular season only; prev is unknown
  // right after a server restart, so it degrades to just the position).
  const st = wr.standings;
  if (st) {
    const s2 = el("div", "wr-stage");
    s2.appendChild(el("div", "wr-kicker", "League position"));
    let moveHtml;
    if (st.prev && st.prev !== st.now) {
      const up = st.now < st.prev;
      moveHtml = `${esc(ordinal(st.prev))} <span class="${up ? "up" : "down"}">` +
        `${up ? "▲" : "▼"} ${esc(ordinal(st.now))}</span> of ${st.of}`;
    } else {
      moveHtml = `${st.prev ? "Holding " : ""}${esc(ordinal(st.now))} of ${st.of}`;
    }
    s2.appendChild(el("div", "wr-move", moveHtml));
    wrap.appendChild(s2);
    wrLater(() => s2.classList.add("on"), t);
    t += 1000;
  }

  // Stage 3 — decisions settled (from the refreshed dashboard state).
  const ledger = App.state?.decision_ledger || [];
  if (ledger.length) {
    const s3 = el("div", "wr-stage");
    s3.appendChild(el("div", "wr-kicker", "Decisions settled"));
    const list = el("div", "es-obj wr-ledger");
    const vcls = { paid_off: "good", backfired: "bad", neutral: "" };
    const vlab = { paid_off: "paid off", backfired: "backfired", neutral: "neutral" };
    for (const r of ledger.slice(0, 3)) {
      list.appendChild(el("div", "es-obj-row",
        `<span class="pill obj ${vcls[r.verdict] ?? ""}">${esc(vlab[r.verdict] || r.verdict)}</span> ` +
        `<span>${esc(r.text)}</span>`));
    }
    s3.appendChild(list);
    wrap.appendChild(s3);
    wrLater(() => s3.classList.add("on"), t);
    t += 1000;
  }

  // Final — continue to the dashboard, or open the classic full report.
  const fin = el("div", "wr-stage wr-actions");
  const cont = el("button", "btn btn-primary", "Continue");
  cont.onclick = closeWeekReveal; // the overlay click would do it anyway
  const full = el("button", "btn", "Full report");
  full.onclick = (e) => {
    e.stopPropagation();
    closeWeekReveal();
    showReport(rep);
  };
  fin.appendChild(cont);
  fin.appendChild(full);
  wrap.appendChild(fin);
  wrLater(() => fin.classList.add("on"), t);

  const hint = el("div", "wr-stage wr-skip", "click anywhere to skip");
  wrap.appendChild(hint);
  wrLater(() => hint.classList.add("on"), 1400);

  ov.classList.remove("hidden");
  return true;
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
  renderApp();
}
window.closeReport = closeReport;
window.render = render;

/* -- Global Tooltip System ---------------------------------------------------- */
(function initTooltipSystem() {
  let tooltipEl = document.getElementById("es-tooltip");
  if (!tooltipEl) {
    tooltipEl = document.createElement("div");
    tooltipEl.id = "es-tooltip";
    document.body.appendChild(tooltipEl);
  }

  let activeTooltipTarget = null;

  function showTooltip(target, html) {
    if (!html) return;
    activeTooltipTarget = target;
    tooltipEl.innerHTML = html;
    tooltipEl.classList.add("active");
    positionTooltip(target);
  }

  function hideTooltip(target) {
    if (activeTooltipTarget === target) {
      activeTooltipTarget = null;
      tooltipEl.classList.remove("active");
    }
  }

  function positionTooltip(target) {
    if (activeTooltipTarget !== target) return;
    const rect = target.getBoundingClientRect();
    
    // Temporarily set display to measure height/width
    tooltipEl.style.visibility = "hidden";
    tooltipEl.style.display = "block";
    const tooltipRect = tooltipEl.getBoundingClientRect();
    tooltipEl.style.display = "";
    tooltipEl.style.visibility = "";
    
    let top = rect.top - tooltipRect.height - 8;
    let left = rect.left + (rect.width - tooltipRect.width) / 2;
    
    // If off the top of screen, show below target instead
    if (top < 8) {
      top = rect.bottom + 8;
    }
    
    // Constraint boundaries
    if (left < 8) {
      left = 8;
    } else if (left + tooltipRect.width > window.innerWidth - 8) {
      left = window.innerWidth - tooltipRect.width - 8;
    }
    
    tooltipEl.style.top = `${top}px`;
    tooltipEl.style.left = `${left}px`;
  }

  // Event Delegation for mouse hover
  document.addEventListener("mouseover", (e) => {
    const target = e.target.closest("[data-tooltip], [title]");
    if (!target) return;

    let html = target.getAttribute("data-tooltip");
    
    // Auto-intercept standard browser title and elevate to custom tooltip styling
    if (!html && target.hasAttribute("title")) {
      const titleVal = target.getAttribute("title");
      if (titleVal && titleVal.trim()) {
        html = `<div class="tooltip-desc">${esc(titleVal)}</div>`;
        target.setAttribute("data-tooltip", html);
      }
      target.removeAttribute("title"); // remove native tooltip
    }

    if (html) {
      showTooltip(target, html);
    }
  });

  document.addEventListener("mouseout", (e) => {
    const target = e.target.closest("[data-tooltip]");
    if (!target) return;
    
    // Ensure we are genuinely leaving the target boundary
    if (!e.relatedTarget || !target.contains(e.relatedTarget)) {
      hideTooltip(target);
    }
  });

  // Keep positioning accurate during viewport actions
  window.addEventListener("scroll", () => {
    if (activeTooltipTarget) positionTooltip(activeTooltipTarget);
  }, { passive: true });

  window.addEventListener("resize", () => {
    if (activeTooltipTarget) positionTooltip(activeTooltipTarget);
  }, { passive: true });
})();

boot();
