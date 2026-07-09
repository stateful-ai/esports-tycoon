/* Inbox — weekly notifications / news feed.

   Pure API consumer, like every other screen: the UI holds NO sim state.
   The only truth about what is unread lives on the server; this file keeps
   just transient view state (the active filter, the last-seen unread count
   used to drive the tab badge).

   Contract (backend built to this exactly):
     GET  /api/inbox            -> { unread:int, items:[{id, season, week,
            category, title, body, unread, tab}] }  (items newest first)
     POST /api/inbox/read {id}     -> { unread:int }
     POST /api/inbox/read {all:true} -> { unread:int }

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

let inboxFilter = "all";   // transient: active category filter
let inboxUnread = 0;       // transient: last unread count seen from the server

const inboxCap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/* -- silent transport ------------------------------------------------------
   Deliberately NOT the shared api() helper: api() toasts + throws on any
   non-2xx, which would spam the UI before the backend ships. Here a failure
   just degrades to an empty inbox. */

async function inboxFetch() {
  if (INBOX_MOCK) return inboxMockData();
  try {
    const r = await fetch("/api/inbox");
    if (!r.ok) return { unread: 0, items: [] };
    const d = await r.json();
    return { unread: d.unread || 0, items: Array.isArray(d.items) ? d.items : [] };
  } catch {
    return { unread: 0, items: [] };
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
  setInboxBadge(d.unread || 0);
  return inboxUnread;
}

// Called by the advance-week flow: repaint the badge and, when the advance
// produced new unread mail, toast the count of newly-arrived messages.
async function inboxAfterAdvance() {
  const before = inboxUnread;
  const after = await refreshInboxBadge();
  const gained = after - before;
  if (gained > 0) toast(`${gained} new inbox message${gained === 1 ? "" : "s"}`);
}

// Jump to another screen by clicking its tab button (same mechanism the
// office HQ uses). Self-contained so inbox.js has no cross-file coupling.
function inboxGoTab(tab) {
  const btn = document.querySelector(`#tabs [data-tab="${tab}"]`);
  if (btn) btn.click();
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
  setInboxBadge(data.unread || 0);

  const card = el("div", "card inbox");

  const head = el("div", "inbox-head");
  head.appendChild(el("h2", "", "Inbox"));
  const markAll = el("button", "btn btn-sm", "Mark all read");
  markAll.onclick = async () => {
    const res = await inboxPost({ all: true });
    if (res && typeof res.unread === "number") setInboxBadge(res.unread);
    card.querySelectorAll(".inbox-item.unread")
      .forEach((n) => n.classList.remove("unread"));
    markAll.style.display = "none";
  };
  if (!(data.unread > 0)) markAll.style.display = "none";
  head.appendChild(markAll);
  card.appendChild(head);

  // Category filter chips (pure client-side).
  const chips = el("div", "inbox-filters");
  const chipEls = {};
  for (const [key, label] of INBOX_CATEGORIES) {
    const c = el("button", "inbox-chip" + (inboxFilter === key ? " active" : ""), label);
    c.onclick = () => {
      inboxFilter = key;
      for (const k in chipEls) chipEls[k].classList.toggle("active", k === key);
      drawList();
    };
    chipEls[key] = c;
    chips.appendChild(c);
  }
  card.appendChild(chips);

  const listWrap = el("div", "inbox-list");
  card.appendChild(listWrap);
  v.appendChild(card);

  function drawList() {
    listWrap.replaceChildren();
    const all = data.items || [];
    const items = all.filter((it) => inboxFilter === "all" || it.category === inboxFilter);
    if (!items.length) {
      const msg = all.length
        ? "No messages in this category."
        : "No messages yet - advance the week.";
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
    const res = await inboxPost({ id: it.id });
    if (res && typeof res.unread === "number") setInboxBadge(res.unread);
    if (inboxUnread <= 0) markAll.style.display = "none";
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
          toast((r && r.message) || `${act.label} done`);
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

    const body = el("div", "inbox-body hidden");
    const text = el("div", "inbox-body-text");
    text.textContent = it.body || "";           // textContent preserves newlines
    body.appendChild(text);
    if (it.tab) {
      const go = el("button", "btn btn-sm inbox-goto", `Go to ${inboxCap(it.tab)}`);
      go.onclick = (e) => { e.stopPropagation(); inboxGoTab(it.tab); };
      body.appendChild(go);
    }
    // Actionable offer items (transfer/sponsor) get an Accept/Decline row.
    if (Array.isArray(it.actions) && it.actions.length) {
      body.appendChild(inboxActionRow(it, row));
    }
    row.appendChild(body);

    let open = false;
    rowHead.onclick = async () => {
      open = !open;
      body.classList.toggle("hidden", !open);
      row.classList.toggle("open", open);
      // Expanding an unread item marks it read on the server.
      if (open) await markItemRead(it, row);
    };
    return row;
  }

  drawList();
}

/* -- dev mock (INBOX_MOCK only) -------------------------------------------- */

function inboxMockData() {
  const season = App.state?.season ?? 1;
  const week = App.state?.week ?? 6;
  const items = [
    { id: "m1", season, week, category: "match", tab: "schedule", unread: true,
      title: "Match report: you beat Sentinels 2-1",
      body: "A tense series on Ascent decided it.\nWatch the replay from the Schedule tab." },
    { id: "m2", season, week, category: "sponsor", tab: "finances", unread: true,
      title: "New jersey sponsor offer",
      body: "A brand is interested in your jersey slot.\nReview the structures in Finances." },
    { id: "m3", season, week, category: "talk", tab: "roster", unread: true,
      title: "A player wants a word",
      body: "Morale is dipping. Hold your weekly 1:1 from the Roster tab." },
    { id: "m4", season, week: week - 1, category: "board", tab: null, unread: false,
      title: "Board: on track",
      body: "The board is content with the current trajectory." },
    { id: "m5", season, week: week - 1, category: "news", tab: null, unread: false,
      title: "Roster shakeups across the league",
      body: "Several rivals made moves in the market this week." },
  ];
  return { unread: items.filter((i) => i.unread).length, items };
}
