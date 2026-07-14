/* Inbox — weekly notifications / news feed.

   Pure API consumer, like every other screen: the UI holds NO sim state.
   The only truth about what is unread lives on the server; this file keeps
   just transient view state (the active filter, the last-seen unread count
   used to drive the tab badge).

   Contract (backend built to this exactly):
     GET  /api/inbox            -> { unread:int, actionable_unread:int,
            league_unread:int, actionable_items:[...], league_feed:[...] }
     POST /api/inbox/read {id}     -> the same unread-count fields
     POST /api/inbox/read {all:true} -> the same unread-count fields

   Before the backend exists the GET simply 404s; we swallow that silently
   (no toast, no console noise) and render the empty state with the badge
   hidden. Relies on app.js globals: $, el, api, money, toast, App. */

/* Dev-only: synth a few items when the backend is absent. MUST stay false
   in shipped code — the graceful 404 path is what real users hit. */
const INBOX_MOCK = false;

const INBOX_CATEGORIES = [
  ["all", "All"],
  ["news", "News"],
  ["talk", "Talks"],
  ["transfer", "Transfers"],
  ["sponsor", "Sponsors"],
  ["scouting", "Scouting"],
  ["development", "Development"],
  ["match", "Matches"],
  ["board", "Board"],
];

// Chip label per item category (singular; the filter bar uses the plurals above).
const INBOX_CAT_LABEL = {
  news: "News", talk: "Talk", transfer: "Transfer", sponsor: "Sponsor",
  scouting: "Scouting", development: "Development", match: "Match", board: "Board",
};

let inboxSection = "actionable"; // primary work queue or secondary league feed
let inboxFilter = "all";          // transient category filter inside that section
let inboxUnread = 0;       // actionable unread count; drives the primary badge
let inboxLeagueUnread = 0; // secondary feed count; shown only inside the screen

const inboxCap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/* -- silent transport ------------------------------------------------------
   Deliberately NOT the shared api() helper: api() toasts + throws on any
   non-2xx, which would spam the UI before the backend ships. Here a failure
   just degrades to an empty inbox. */

async function inboxFetch() {
  if (INBOX_MOCK) return inboxMockData();
  try {
    const r = await fetch("/api/inbox");
    if (!r.ok) return { unread: 0, actionable_unread: 0, league_unread: 0, actionable_items: [], league_feed: [] };
    const d = await r.json();
    return {
      unread: d.unread || 0,
      actionable_unread: d.actionable_unread || 0,
      league_unread: d.league_unread || 0,
      actionable_items: Array.isArray(d.actionable_items) ? d.actionable_items : [],
      league_feed: Array.isArray(d.league_feed) ? d.league_feed : [],
    };
  } catch {
    return { unread: 0, actionable_unread: 0, league_unread: 0, actionable_items: [], league_feed: [] };
  }
}

async function inboxPost(body) {
  if (INBOX_MOCK) return { unread: Math.max(0, inboxUnread - (body.all ? inboxUnread : 1)) };
  try {
    const r = await fetch("/api/inbox/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

/* -- tab badge -------------------------------------------------------------- */

function setInboxBadge(n) {
  inboxUnread = Math.max(0, n | 0);
  const badge = document.getElementById("inbox-badge");
  if (!badge) return;
  badge.textContent = inboxUnread > 99 ? "99+" : String(inboxUnread);
  badge.classList.toggle("hidden", inboxUnread <= 0);
}

// Pull the current unread count and repaint the badge. Returns the count.
// Hooked on app load (boot) and after read actions.
async function refreshInboxBadge() {
  const d = await inboxFetch();
  inboxLeagueUnread = d.league_unread || 0;
  setInboxBadge(d.actionable_unread || 0);
  return inboxUnread;
}

// Called by the advance-week flow: repaint the badge and, when the advance
// produced new unread mail, toast the count of newly-arrived messages.
async function inboxAfterAdvance() {
  const before = inboxUnread;
  const after = await refreshInboxBadge();
  const gained = after - before;
  if (gained > 0) toast(`${gained} new inbox item${gained === 1 ? "" : "s"}`);
}

// Jump to another screen by clicking its tab button (same mechanism the
// office HQ uses). Self-contained so inbox.js has no cross-file coupling.
// Retired tabs alias to their new home as [target tab, App.seasonTab value];
// App.seasonTab is set BEFORE the click so the season render picks it up.
// The alias never depends on the old Standings/Schedule buttons existing.
// [host tab, App sub-tab field, sub-tab id] — mirrors TAB_ALIASES in app.js.
// Roster folded into Club (Squad), Scouting into Market.
const INBOX_TAB_ALIAS = {
  standings: ["season", "seasonTab", "league"],
  schedule: ["season", "seasonTab", "fixtures"],
  roster: ["club", "clubTab", "squad"],
  scouting: ["market", "marketTab", "scouting"],
};
function inboxGoTab(tab) {
  const alias = INBOX_TAB_ALIAS[tab];
  const target = alias ? alias[0] : tab;
  const btn = document.querySelector(`#tabs [data-tab="${target}"]`);
  if (!btn) return; // unknown tab: silent no-op, same as before
  if (alias && typeof App !== "undefined") App[alias[1]] = alias[2];
  btn.click();
}

// Quietly re-pull GameState into App.state after an inbox action resolves, so
// the Market / Finances / Dashboard screens agree — WITHOUT re-rendering the
// inbox (a full refresh() would wipe the just-placed "Resolved" chip). Those
// screens fetch their own endpoints on navigation; this mainly keeps App.state
// and the header (context + balance) current. Silent on failure.
async function inboxSyncState() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) return;
    const s = await r.json();
    if (typeof App !== "undefined") App.state = s;
    if (s.user_team) {
      const ctx = document.getElementById("context");
      if (ctx) {
        ctx.textContent =
          `Season ${s.season} · Week ${s.week} · ${s.phase}  —  ${s.user_team.name}`;
      }
      const bal = document.getElementById("balance");
      if (bal && typeof money === "function") bal.textContent = money(s.user_team.balance);
    }
  } catch {
    /* header stays as-is; screens still fetch fresh on navigation */
  }
}

/* -- screen ----------------------------------------------------------------- */

async function inbox(v) {
  const data = await inboxFetch();
  inboxLeagueUnread = data.league_unread || 0;
  setInboxBadge(data.actionable_unread || 0);

  // Workspace layout: main column = header + filter chips + the list
  // (scrolling INSIDE its card); rail = a "This week" digest whose lines
  // jump into (and expand) the matching list item.
  const ws = el("div", "ws");
  const main = el("div", "ws-8 ws-col");
  const rail = el("div", "ws-4 ws-col");
  ws.append(main, rail);
  v.appendChild(ws);

  const card = el("div", "card inbox");
  main.appendChild(card);

  const head = el("div", "inbox-head");
  const sectionTitle = el("h2", "", inboxSection === "actionable" ? "Actionable Items" : "League Feed");
  head.appendChild(sectionTitle);
  const markAll = el("button", "btn btn-sm", "Mark all as read");
  markAll.onclick = async () => {
    const res = await inboxPost({ all: true });
    if (res && typeof res.actionable_unread === "number") {
      setInboxBadge(res.actionable_unread);
      inboxLeagueUnread = res.league_unread || 0;
    }
    // Flip the local flags too, so re-renders (filter switches) and the
    // per-category chip counts agree with the server.
    for (const it of [...(data.actionable_items || []), ...(data.league_feed || [])]) it.unread = false;
    refreshChipCounts();
    refreshSectionCounts();
    card.querySelectorAll(".inbox-item.unread")
      .forEach((n) => n.classList.remove("unread"));
    markAll.style.display = "none";
  };
  if (!(data.unread > 0)) markAll.style.display = "none";
  head.appendChild(markAll);
  card.appendChild(head);

  // Primary/secondary split comes from the server's live classification.
  // The primary badge ignores League Feed unread items, so generic results
  // never recreate the notification noise this screen is meant to remove.
  const sections = el("div", "inbox-filters");
  const sectionButtons = {};
  const sectionDefs = [
    ["actionable", "Actionable Items"],
    ["league", "League Feed"],
  ];
  const selectedItems = () => inboxSection === "actionable"
    ? (data.actionable_items || [])
    : (data.league_feed || []);
  function refreshSectionCounts() {
    for (const [key, label] of sectionDefs) {
      const items = key === "actionable" ? data.actionable_items : data.league_feed;
      const n = (items || []).filter((it) => it.unread).length;
      sectionButtons[key].textContent = n > 0 ? `${label} (${n})` : label;
    }
  }
  function setSection(key) {
    inboxSection = key;
    inboxFilter = "all";
    sectionTitle.textContent = key === "actionable" ? "Actionable Items" : "League Feed";
    for (const k in sectionButtons) sectionButtons[k].classList.toggle("active", k === key);
    refreshChipCounts();
    drawList();
    drawDigest();
  }
  for (const [key, label] of sectionDefs) {
    const n = key === "actionable" ? data.actionable_unread : data.league_unread;
    const b = el("button", "inbox-chip" + (inboxSection === key ? " active" : ""), n > 0 ? `${label} (${n})` : label);
    b.onclick = () => setSection(key);
    sectionButtons[key] = b;
    sections.appendChild(b);
  }
  card.appendChild(sections);

  // Category filter chips (pure client-side) with live unread counts.
  const unreadIn = (key) =>
    selectedItems().filter(
      (it) => it.unread && (key === "all" || it.category === key)).length;
  function refreshChipCounts() {
    const visibleCategories = new Set(selectedItems().map((it) => it.category));
    for (const [key, label] of INBOX_CATEGORIES) {
      const n = unreadIn(key);
      chipEls[key].textContent = n > 0 ? `${label} (${n})` : label;
      chipEls[key].classList.toggle(
        "hidden", key !== "all" && !visibleCategories.has(key),
      );
    }
  }
  function setFilter(key) {
    inboxFilter = key;
    for (const k in chipEls) chipEls[k].classList.toggle("active", k === key);
    drawList();
  }
  const chips = el("div", "inbox-filters");
  const chipEls = {};
  for (const [key, label] of INBOX_CATEGORIES) {
    const c = el("button", "inbox-chip" + (inboxFilter === key ? " active" : ""), label);
    c.onclick = () => setFilter(key);
    chipEls[key] = c;
    chips.appendChild(c);
  }
  refreshChipCounts();
  card.appendChild(chips);

  // The list scrolls inside its card so the page stays one viewport tall.
  const scroll = el("div", "card-scroll");
  scroll.style.setProperty("--scroll-max", "72vh");
  const listWrap = el("div", "inbox-list");
  scroll.appendChild(listWrap);
  card.appendChild(scroll);

  // item.id -> { row, openRow } so the digest can expand a list row through
  // the exact same path as a click on the row itself. Rebuilt by every
  // drawList (filter switches produce fresh row nodes).
  const rowCtl = new Map();

  function drawList() {
    rowCtl.clear();
    listWrap.replaceChildren();
    const all = selectedItems();
    const items = all.filter((it) => inboxFilter === "all" || it.category === inboxFilter);
    if (!items.length) {
      const msg = all.length
        ? "Nothing in this category."
        : inboxSection === "actionable"
          ? "Nothing needs your attention. New offers, contracts, and urgent talks will appear here."
          : "No league updates yet. Advance the week to continue.";
      listWrap.appendChild(el("p", "inbox-empty muted", msg));
      return;
    }
    // Items arrive newest-first; emit an "S1 - W6" header whenever the
    // (season, week) key changes as we walk down the list.
    let groupKey = null;
    for (const it of items) {
      const key = `${it.season}-${it.week}`;
      if (key !== groupKey) {
        groupKey = key;
        listWrap.appendChild(el("div", "inbox-weekhead", `S${it.season} - W${it.week}`));
      }
      listWrap.appendChild(inboxRow(it));
    }
  }

  // Mark one item read on the server (idempotent) + repaint the badge. Shared
  // by row-expand and by a resolved Accept/Decline action.
  async function markItemRead(it, row) {
    if (!it.unread) return;
    it.unread = false;
    row.classList.remove("unread");
    refreshChipCounts();
    refreshSectionCounts();
    const res = await inboxPost({ id: it.id });
    if (res && typeof res.actionable_unread === "number") {
      setInboxBadge(res.actionable_unread);
      inboxLeagueUnread = res.league_unread || 0;
    }
    if (res && res.unread <= 0) markAll.style.display = "none";
  }

  // Accept/Decline row for transfer/sponsor offer items. Each action is a
  // verbatim {endpoint, payload} the backend derived from live state; we POST
  // it as-is (via the shared api() helper, which toasts + throws on any non-2xx)
  // and never invent business logic here.
  function inboxActionRow(it, row) {
    const wrap = el("div", "inbox-actions");
    const settle = (label, tone) =>
      wrap.replaceChildren(el("span", `inbox-outcome ${tone}`, label));
    const btns = [];
    for (const act of it.actions) {
      const primary = act.id === "accept";
      const b = el(
        "button",
        "btn btn-sm" + (primary ? " btn-primary" : ""),
        act.label || (primary ? "Accept" : "Decline"),
      );
      btns.push(b);
      b.onclick = async (e) => {
        e.stopPropagation();
        btns.forEach((x) => (x.disabled = true));
        try {
          const r = await api(act.endpoint, act.payload); // toasts + throws on 4xx
          toast((r && r.message) || `${act.label} confirmed.`);
          await markItemRead(it, row);
          settle("Resolved", "ok");
          await inboxSyncState(); // keep Market/Finances/Dashboard in agreement
        } catch (_e) {
          // api() already surfaced the endpoint's detail (e.g. "offer no
          // longer available") in a toast; just retire the stale row.
          settle("No longer available", "stale");
        }
      };
      wrap.appendChild(b);
    }
    return wrap;
  }

  function inboxRow(it) {
    const cat = it.category || "news";
    const row = el("div", "inbox-item" + (it.unread ? " unread" : ""));

    const rowHead = el("div", "inbox-row-head");
    const chip = el("span", `inbox-cat cat-${cat}`);
    chip.textContent = INBOX_CAT_LABEL[cat] || cat;
    const title = el("span", "inbox-title");
    title.textContent = it.title || "";
    const week = el("span", "inbox-week mono muted");
    week.textContent = `W${it.week}`;
    const dot = el("span", "inbox-dot");
    rowHead.append(chip, title, week, dot);
    row.appendChild(rowHead);

    const body = el("div", "inbox-body collapsed");
    const text = el("div", "inbox-body-text");
    text.textContent = it.body || "";           // textContent preserves newlines
    body.appendChild(text);
    if (it.tab) {
      const go = el("button", "btn btn-sm inbox-goto", `Open ${inboxCap(it.tab)}`);
      go.onclick = (e) => { e.stopPropagation(); inboxGoTab(it.tab); };
      body.appendChild(go);
    }
    // Actionable offer items (transfer/sponsor) get an Accept/Decline row.
    if (Array.isArray(it.actions) && it.actions.length) {
      body.appendChild(inboxActionRow(it, row));
    }
    row.appendChild(body);

    let open = false;
    const setOpen = async (want) => {
      if (want === open) return;
      open = want;
      body.classList.toggle("collapsed", !open);
      row.classList.toggle("open", open);
      // Expanding an unread item marks it read on the server.
      if (open) await markItemRead(it, row);
    };
    rowHead.onclick = () => setOpen(!open);
    if (it.id != null) rowCtl.set(it.id, { row, openRow: () => setOpen(true) });
    return row;
  }

  /* -- rail: "This week" digest ------------------------------------------- */
  // The latest week's items grouped by category; each line jumps to (and
  // expands) the matching row in the main list, marking it read via the
  // same path as a normal row click.
  const digest = el("div", "card");
  const digestTitle = el("h2", "", "This week");
  digest.appendChild(digestTitle);
  function drawDigest() {
    digest.querySelectorAll(":scope > :not(h2)").forEach((node) => node.remove());
    digestTitle.textContent = inboxSection === "actionable" ? "This week's priorities" : "This week's league feed";
    const allItems = selectedItems();
    if (!allItems.length) {
      digest.appendChild(el("p", "muted", inboxSection === "actionable"
        ? "No pending manager decisions."
        : "No league updates this week."));
    } else {
      const latest = allItems[0]; // items arrive newest-first
      const wkKey = `${latest.season}-${latest.week}`;
      digest.appendChild(el("div", "microlabel", `S${latest.season} - W${latest.week}`));
      const catOrder = INBOX_CATEGORIES.map(([k]) => k);
      const catRank = (c) => {
        const i = catOrder.indexOf(c);
        return i < 0 ? catOrder.length : i;
      };
      const wkItems = allItems
        .filter((it) => `${it.season}-${it.week}` === wkKey)
        .sort((a, b) => catRank(a.category) - catRank(b.category));
      for (const it of wkItems) {
        const cat = it.category || "news";
        const line = el("div", "inbox-row-head");
        line.title = "Open item";
        const chip = el("span", `inbox-cat cat-${cat}`);
        chip.textContent = INBOX_CAT_LABEL[cat] || cat;
        const title = el("span", "inbox-title");
        title.textContent = it.title || "";
        line.append(chip, title);
        line.onclick = () => {
          // Make sure the target row is rendered before jumping to it.
          if (inboxFilter !== "all" && inboxFilter !== it.category) setFilter("all");
          const ctl = rowCtl.get(it.id);
          if (!ctl) return;
          ctl.openRow();
          ctl.row.scrollIntoView({ behavior: "smooth", block: "center" });
        };
        digest.appendChild(line);
      }
    }
  }
  rail.appendChild(digest);

  drawList();
  drawDigest();
}

/* -- dev mock (INBOX_MOCK only) -------------------------------------------- */

function inboxMockData() {
  const season = App.state?.season ?? 1;
  const week = App.state?.week ?? 6;
  const items = [
    { id: "m1", season, week, category: "match", tab: "schedule", unread: true,
      title: "Match report: 2-1 over Sentinels",
      body: "Ascent decided a close series.\nReview the replay in Fixtures." },
    { id: "m2", season, week, category: "sponsor", tab: "finances", unread: true,
      title: "Jersey sponsor offer",
      body: "A brand is interested in the jersey placement.\nReview the terms in Finances." },
    { id: "m3", season, week, category: "talk", tab: "roster", unread: true,
      title: "Player meeting requested",
      body: "Morale is slipping. Use this week's 1:1 from Squad." },
    { id: "m4", season, week: week - 1, category: "board", tab: null, unread: false,
      title: "Board update: on track",
      body: "The board is satisfied with the club's current direction." },
    { id: "m5", season, week: week - 1, category: "news", tab: null, unread: false,
      title: "League market activity",
      body: "Several rivals made moves in the market this week." },
  ];
  const actionable_items = items.filter((i) => ["talk", "board", "sponsor"].includes(i.category));
  const league_feed = items.filter((i) => !actionable_items.includes(i));
  return {
    unread: items.filter((i) => i.unread).length,
    actionable_unread: actionable_items.filter((i) => i.unread).length,
    league_unread: league_feed.filter((i) => i.unread).length,
    actionable_items,
    league_feed,
  };
}
