/* Fantasy-draft screen. The whole app routes here while gs.fantasy_draft is
   active (app.js refresh() checks state.draft_active). Server-computed
   everything: pool rows, recommendations (same value function the AI drafts
   with), projected lineup and language coverage arrive ready to render —
   this file only filters/sorts presentation-side and posts picks. */

/* Client-only presentation state (search/filter/sort survive repaints). */
const DraftUI = {
  data: null,
  search: "",
  role: "all",
  sort: "skill",
  timer: null,
  busy: false,
};

function stopDraftPolling() {
  if (DraftUI.timer) {
    clearInterval(DraftUI.timer);
    DraftUI.timer = null;
  }
}
window.stopDraftPolling = stopDraftPolling;

/* Poll while the board can move without us: before the start (waiting on the
   host) and on anyone else's turn. Quiet on our own turn — the board only
   changes when we pick. */
function scheduleDraftPoll() {
  stopDraftPolling();
  const d = DraftUI.data;
  if (!d || d.complete) return;
  if (d.started && d.your_turn) return;
  DraftUI.timer = setInterval(async () => {
    if (DraftUI.busy) return;
    try {
      const fresh = await api("/api/draft");
      const before = DraftUI.data;
      DraftUI.data = fresh;
      if (fresh.complete) return draftFinished();
      // Repaint only on movement so an open search box isn't disturbed.
      if (
        !before ||
        fresh.overall !== before.overall ||
        fresh.started !== before.started
      ) {
        paintDraft();
        scheduleDraftPoll();
      }
    } catch (e) {
      /* transient — keep polling */
    }
  }, 2500);
}

async function draftFinished() {
  stopDraftPolling();
  toast("Draft complete — your squad is signed. Season 1 begins.");
  await refresh(); // state.draft_active is now false -> normal app
}

async function renderDraftScreen() {
  try {
    DraftUI.data = await api("/api/draft");
  } catch (e) {
    $("#view").innerHTML = '<p class="muted">Could not load the draft.</p>';
    return;
  }
  if (DraftUI.data.complete) return draftFinished();
  paintDraft();
  scheduleDraftPoll();
}
window.renderDraftScreen = renderDraftScreen;

/* -- little renderers ------------------------------------------------------ */

function draftStars(band) {
  if (!band) return '<span class="muted">?</span>';
  const one = (v) => "★".repeat(Math.floor(v)) + (v % 1 >= 0.5 ? "½" : "");
  const [lo, hi] = band;
  const txt = lo === hi ? one(lo) : `${one(lo)}–${one(hi)}`;
  return `<span class="stars" title="projected ceiling ${lo}–${hi} of 5">${txt}</span>`;
}

function draftLangs(langs) {
  return (langs || [])
    .map(
      (l) =>
        `<span class="chip" title="${esc(l.lang)} — proficiency ${esc(l.level)}">${esc(l.lang)}</span>`
    )
    .join(" ");
}

function draftPlayerName(p) {
  return plink(p.id, p.handle);
}

/* -- screen ---------------------------------------------------------------- */

function draftStatusLine(d) {
  if (!d.started) {
    return d.is_host
      ? "Waiting for you to open the draft."
      : "Waiting for the host to open the draft.";
  }
  if (d.your_turn) return "You're on the clock.";
  return `${esc(d.on_clock_name || "…")} are on the clock.`;
}

function draftHead(d) {
  const head = el("div", "card draft-head");
  const pickNo = Math.min(d.overall + 1, d.total_picks);
  const beginBtn =
    !d.started && d.is_host
      ? '<button id="draft-begin" class="btn btn-primary">Open the draft ▸</button>'
      : "";
  const humans = (d.humans || [])
    .map((h) => `<span class="pill${h.is_you ? " you" : ""}">${esc(h.name)}</span>`)
    .join(" ");
  head.innerHTML = `
    <div class="draft-head-row">
      <div>
        <span class="microlabel">Fantasy draft</span>
        <h2>Round ${d.round}/${d.rounds} · Pick ${pickNo}/${d.total_picks}</h2>
        <p class="${d.your_turn ? "draft-onclock" : "muted"}">${draftStatusLine(d)}</p>
      </div>
      <div class="draft-head-side">
        ${beginBtn}
        <div class="muted">Managers: ${humans}</div>
      </div>
    </div>
    <div class="draft-order-strip">${draftUpcoming(d)}</div>`;
  const b = head.querySelector("#draft-begin");
  if (b)
    b.onclick = async () => {
      DraftUI.busy = true;
      try {
        DraftUI.data = await api("/api/draft/begin", {});
      } finally {
        DraftUI.busy = false;
      }
      if (DraftUI.data.complete) return draftFinished();
      paintDraft();
      scheduleDraftPoll();
    };
  return head;
}

function draftUpcoming(d) {
  if (!d.started || !d.upcoming.length) return "";
  return d.upcoming
    .map(
      (u, i) =>
        `<span class="draft-order-team${u.is_you ? " you" : ""}${i === 0 ? " now" : ""}"
           title="Round ${u.round} — ${esc(u.name)}">
           ${i === 0 ? "▶ " : ""}${esc(u.tag)}</span>`
    )
    .join('<span class="muted"> · </span>');
}

function draftRecent(d) {
  const card = el("div", "card");
  const rows = d.recent_picks
    .map(
      (r) => `
      <div class="draft-feed-row${r.is_you ? " you" : ""}">
        <span class="mono muted">R${r.round}·${r.overall + 1}</span>
        <span class="pill">${esc(r.tag)}</span>
        <span>${plink(r.player_id, r.handle)}</span>
        <span class="muted">${esc(r.role)} · ${r.skill}</span>
      </div>`
    )
    .join("");
  card.innerHTML = `
    <span class="microlabel">Latest picks</span>
    ${rows || '<p class="muted">No picks yet.</p>'}`;
  return card;
}

function draftPrefsCard(d) {
  const card = el("div", "card");
  const opts = d.strategies
    .map(
      (s) =>
        `<button class="btn draft-strat${d.prefs.strategy === s ? " btn-primary" : ""}"
           data-strat="${s}">${esc(s.replace("_", " "))}</button>`
    )
    .join(" ");
  card.innerHTML = `
    <span class="microlabel">Draft board preferences</span>
    <p class="muted">Steers your recommendations — the AI orgs run their own
    boards with the same math.</p>
    <div class="row" style="gap:6px;flex-wrap:wrap">${opts}</div>
    <label class="row" style="gap:6px;margin-top:8px;align-items:center">
      <input type="checkbox" id="draft-lang-focus" ${d.prefs.language_focus ? "checked" : ""}>
      <span>Favour shared comms languages</span>
    </label>`;
  const post = async (strategy, language_focus) => {
    DraftUI.busy = true;
    try {
      DraftUI.data = await api("/api/draft/prefs", {
        strategy,
        language_focus,
      });
    } finally {
      DraftUI.busy = false;
    }
    paintDraft();
    scheduleDraftPoll();
  };
  card.querySelectorAll(".draft-strat").forEach((b) => {
    b.onclick = () => post(b.dataset.strat, $("#draft-lang-focus").checked);
  });
  card.querySelector("#draft-lang-focus").onchange = (ev) =>
    post(DraftUI.data.prefs.strategy, ev.target.checked);
  return card;
}

function draftRecsCard(d) {
  const card = el("div", "card");
  const rows = (d.recommendations || [])
    .map(
      (r) => `
      <div class="draft-rec">
        <div class="draft-rec-top">
          <span>${draftPlayerName(r)} <span class="muted">${r.age}y · ${esc(r.role)}</span></span>
          <span>
            <span class="mono" title="fit score under your preferences">${r.score}</span>
            ${d.your_turn ? `<button class="btn btn-primary btn-sm draft-pick-btn" data-draft-pid="${r.id}">Draft</button>` : ""}
          </span>
        </div>
        <div class="draft-rec-line">
          <span class="mono">${r.skill}</span> ${draftStars(r.potential_stars)}
          ${draftLangs(r.languages)}
        </div>
        ${(r.reasons || []).map((x) => `<span class="draft-reason">${esc(x)}</span>`).join(" ")}
      </div>`
    )
    .join("");
  card.innerHTML = `
    <span class="microlabel">Recommended for your board</span>
    ${rows || '<p class="muted">The board opens with the draft.</p>'}`;
  return card;
}

function draftSquadCard(d) {
  const card = el("div", "card");
  const byId = {};
  for (const p of d.your_picks) byId[p.id] = p;
  const starters = d.projected_lineup.map((pid) => byId[pid]).filter(Boolean);
  const depth = d.your_picks.filter((p) => !d.projected_lineup.includes(p.id));
  const row = (p, tag) => `
    <div class="draft-squad-row">
      <span class="pill">${esc(tag)}</span>
      <span>${draftPlayerName(p)}</span>
      <span class="muted">${p.age}y · ${esc(p.playstyle)}</span>
      <span class="mono">${p.skill}</span>
      ${draftStars(p.potential_stars)}
    </div>`;
  const langs = (d.squad_langs || [])
    .map(
      (l) =>
        `<span class="chip" title="${l.speakers} of your picks speak ${esc(l.lang)}">${esc(l.lang)} ×${l.speakers}</span>`
    )
    .join(" ");
  card.innerHTML = `
    <span class="microlabel">Your squad (${d.your_picks.length}/${d.rounds})</span>
    ${starters.length
      ? starters.map((p) => row(p, p.role)).join("")
      : '<p class="muted">Your first five picks project as your starting lineup.</p>'}
    ${depth.length
      ? `<span class="microlabel" style="margin-top:6px">Depth / academy</span>` +
        depth.map((p) => row(p, p.age <= 20 ? "academy" : "bench")).join("")
      : ""}
    ${langs ? `<div style="margin-top:8px"><span class="microlabel">Comms languages</span> ${langs}</div>` : ""}`;
  return card;
}

function draftPoolRows(d) {
  const q = DraftUI.search.trim().toLowerCase();
  let rows = d.pool;
  if (DraftUI.role !== "all") rows = rows.filter((p) => p.role === DraftUI.role);
  if (q)
    rows = rows.filter(
      (p) =>
        p.handle.toLowerCase().includes(q) ||
        (p.real_name || "").toLowerCase().includes(q) ||
        p.region.toLowerCase().includes(q) ||
        (p.languages || []).some((l) => l.lang.toLowerCase().includes(q))
    );
  const potMid = (p) =>
    p.potential_stars ? (p.potential_stars[0] + p.potential_stars[1]) / 2 : 0;
  const sorters = {
    skill: (a, b) => b.skill - a.skill,
    age: (a, b) => a.age - b.age,
    potential: (a, b) => potMid(b) - potMid(a) || b.skill - a.skill,
  };
  return [...rows].sort(sorters[DraftUI.sort] || sorters.skill);
}

function draftPoolCard(d) {
  const card = el("div", "card draft-pool");
  const roles = ["all", ...new Set(d.pool.map((p) => p.role))];
  const roleBtns = roles
    .map(
      (r) =>
        `<button class="btn btn-sm draft-role${DraftUI.role === r ? " btn-primary" : ""}"
           data-role="${r}">${esc(r)}</button>`
    )
    .join(" ");
  const sortBtns = ["skill", "potential", "age"]
    .map(
      (s) =>
        `<button class="btn btn-sm draft-sort${DraftUI.sort === s ? " btn-primary" : ""}"
           data-sort="${s}">${s}</button>`
    )
    .join(" ");
  const rows = draftPoolRows(d);
  const body = rows
    .slice(0, 150)
    .map(
      (p) => `
      <tr>
        <td>${d.your_turn ? `<button class="btn btn-primary btn-sm draft-pick-btn" data-draft-pid="${p.id}">Draft</button>` : ""}</td>
        <td>${draftPlayerName(p)}${p.is_igl ? ' <span class="pill">IGL</span>' : ""}</td>
        <td class="mono">${p.age}</td>
        <td>${esc(p.role)}</td>
        <td>${esc(p.playstyle)}</td>
        <td class="mono">${p.skill}</td>
        <td>${draftStars(p.potential_stars)}</td>
        <td>${draftLangs(p.languages)}</td>
        <td class="muted">${esc(p.region)}</td>
      </tr>`
    )
    .join("");
  card.innerHTML = `
    <div class="draft-pool-controls">
      <span class="microlabel">Available players (${rows.length})</span>
      <input id="draft-search" placeholder="Search name / region / language"
        value="${esc(DraftUI.search)}">
      <span class="row" style="gap:4px;flex-wrap:wrap">${roleBtns}</span>
      <span class="row" style="gap:4px">sort: ${sortBtns}</span>
    </div>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th></th><th>Player</th><th>Age</th><th>Role</th><th>Style</th>
          <th title="combine read: mean visible attribute">Skill</th>
          <th title="projected ceiling band">Ceiling</th>
          <th>Languages</th><th>Region</th>
        </tr></thead>
        <tbody>${body}</tbody>
      </table>
      ${rows.length > 150 ? `<p class="muted">Showing the top 150 of ${rows.length} — search or filter to narrow.</p>` : ""}
    </div>`;
  const search = card.querySelector("#draft-search");
  search.oninput = () => {
    DraftUI.search = search.value;
    const fresh = draftPoolCard(DraftUI.data);
    card.replaceWith(fresh);
    const inp = fresh.querySelector("#draft-search");
    inp.focus();
    inp.setSelectionRange(inp.value.length, inp.value.length);
  };
  card.querySelectorAll(".draft-role").forEach(
    (b) =>
      (b.onclick = () => {
        DraftUI.role = b.dataset.role;
        card.replaceWith(draftPoolCard(DraftUI.data));
      })
  );
  card.querySelectorAll(".draft-sort").forEach(
    (b) =>
      (b.onclick = () => {
        DraftUI.sort = b.dataset.sort;
        card.replaceWith(draftPoolCard(DraftUI.data));
      })
  );
  return card;
}

async function draftPick(pid) {
  if (DraftUI.busy) return;
  DraftUI.busy = true;
  try {
    DraftUI.data = await api("/api/draft/pick", { player_id: pid });
  } catch (e) {
    return; // api() already toasts the server's reason
  } finally {
    DraftUI.busy = false;
  }
  if (DraftUI.data.complete) return draftFinished();
  paintDraft();
  scheduleDraftPoll();
}

function paintDraft() {
  const d = DraftUI.data;
  if (!d) return;
  const view = $("#view");
  const wrap = el("div", "tab-panel-active");
  const grid = el("div", "ws");
  const left = el("div", "ws-8 ws-col");
  left.append(draftHead(d), draftPoolCard(d));
  const right = el("div", "ws-4 ws-col");
  right.append(draftRecsCard(d), draftSquadCard(d), draftPrefsCard(d), draftRecent(d));
  grid.append(left, right);
  wrap.appendChild(grid);
  view.replaceChildren(wrap);
  // One delegated handler catches every Draft button (pool + recs). The
  // buttons carry data-DRAFT-pid — a bare data-pid would be swallowed by
  // profile.js's global [data-pid] delegation (it stopPropagation()s and
  // opens the player profile overlay instead).
  wrap.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".draft-pick-btn");
    if (btn) draftPick(btn.dataset.draftPid);
  });
}
