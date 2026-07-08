/* Office — tycoon-style visual HQ, the campaign's landing tab.
   The backdrop and cut-out room sprites are AI-generated art in
   /assets/office/. Facility pods read their level from GET /api/finances,
   so upgrades bought on the Finances tab visibly change the scene the next
   time the office renders (office() re-fetches on every render).
   Relies on app.js globals: $, el, api, money, toast, App. */

const OFFICE_ART = "/assets/office";

/* Rooms pinned onto the scene. Coords/width are % of the stage so the whole
   scene scales with the card. `go` is a tab button name ("a|b" = feature-
   detect a, fall back to b); `training: true` opens the inline focus picker
   instead of switching tabs. */
const OFFICE_ROOMS = [
  { id: "boardroom",     label: "Boardroom",     sub: "sponsors · finances",  go: "finances",       x: 1.5,  y: 2,    w: 13 },
  { id: "lounge",        label: "Lounge",        sub: "standings · trophies", go: "standings",      x: 66.5, y: 1.5,  w: 12 },
  { id: "scout_desk",    label: "Scout Desk",    sub: "scouting reports",     go: "scouting",       x: 80.5, y: 1,    w: 12.5 },
  { id: "medical",       label: "Physio Corner", sub: "roster · staff",       go: "roster",         x: 1,    y: 57,   w: 11 },
  { id: "war_room",      label: "War Room",      sub: "stats · tactics",      go: "tactics|stats",  x: 13,   y: 66,   w: 14 },
  { id: "practice_room", label: "Practice Room", sub: "set training focus",   training: true,       x: 70,   y: 62,   w: 15 },
];

const OFFICE_FACILITY_ROOMS = [
  { id: "training_center",  label: "Training Center",  sub: "player development" },
  { id: "analytics_suite",  label: "Analytics Suite",  sub: "scouting & prep" },
  { id: "marketing_office", label: "Marketing Office", sub: "fans & sponsors" },
];

/* Switch tabs by driving the real tab buttons so active-state and App.tab
   stay owned by app.js. "a|b" tries a first (e.g. a future tactics tab). */
function officeGoTab(names) {
  for (const n of names.split("|")) {
    const btn = document.querySelector(`#tabs [data-tab="${n}"]`);
    if (btn) { btn.click(); return; }
  }
}

function officeCloseFocusPicker() {
  const pop = document.getElementById("office-pop");
  if (pop) pop.remove();
}

/* Inline training-focus quick picker (same action the dashboard select
   drives: POST /api/actions/training). Anchored over the practice room. */
function officeOpenFocusPicker(stage) {
  officeCloseFocusPicker();
  const s = App.state;
  const pop = el("div", "office-pop");
  pop.id = "office-pop";
  pop.onclick = (e) => e.stopPropagation();
  pop.appendChild(el("div", "office-pop-title", "Training focus"));
  for (const o of s.focus_options ?? []) {
    const b = el("button", "btn btn-sm" + (o === s.training_focus ? " active" : ""), o);
    b.onclick = async (e) => {
      e.stopPropagation();
      await api("/api/actions/training", { focus: o });
      App.state.training_focus = o;
      toast(`Training focus set: ${o}`);
      officeCloseFocusPicker();
    };
    pop.appendChild(b);
  }
  stage.appendChild(pop);
  // Any click outside the popover dismisses it.
  setTimeout(() => document.addEventListener("click", officeCloseFocusPicker, { once: true }), 0);
}

async function office(v) {
  if (!App.state) return;
  const s = App.state;

  const card = el("div", "card office-card");
  card.innerHTML = `<h2>Headquarters <span class="muted" style="text-transform:none;letter-spacing:0">— click a room to jump to its desk</span></h2>`;

  /* -- the scene --------------------------------------------------------- */
  const stage = el("div", "office-stage");

  const base = el("img", "office-base");
  base.src = `${OFFICE_ART}/office_base.webp`;
  base.alt = "team headquarters";
  base.draggable = false;
  stage.appendChild(base);

  // Ambient header strip: org identity + week + balance (already in App.state).
  stage.appendChild(el("div", "office-head", `
    <img class="logo" src="${s.user_team.logo}" alt="">
    <b>${s.user_team.name}</b>
    <span class="office-head-dim">S${s.season} · W${s.week} · ${s.phase}</span>
    <span class="spacer"></span>
    <span class="mono">${money(s.user_team.balance)}</span>`));

  // Center of the HQ = the team desks -> roster.
  const hq = el("div", "office-room office-hq");
  Object.assign(hq.style, { left: "30%", top: "32%", width: "38%", height: "42%" });
  hq.appendChild(el("span", "office-label", `Team Desks<i>open roster</i>`));
  hq.onclick = () => officeGoTab("roster");
  stage.appendChild(hq);

  for (const r of OFFICE_ROOMS) {
    const d = el("div", "office-room");
    Object.assign(d.style, { left: r.x + "%", top: r.y + "%", width: r.w + "%" });
    const img = el("img");
    img.src = `${OFFICE_ART}/${r.id}.png`;
    img.alt = r.label;
    img.draggable = false;
    // Missing art degrades to a labeled dashed pad instead of a broken image.
    img.onerror = () => { img.remove(); d.classList.add("office-room-flat"); };
    d.appendChild(img);
    d.appendChild(el("span", "office-label", `${r.label}<i>${r.sub}</i>`));
    d.onclick = r.training
      ? (e) => { e.stopPropagation(); officeOpenFocusPicker(stage); }
      : () => officeGoTab(r.go);
    stage.appendChild(d);
  }
  card.appendChild(stage);

  /* -- facilities wing ---------------------------------------------------- */
  // Re-fetched every render so an upgrade made in Finances shows up as soon
  // as the player comes back to the office.
  let fin = null;
  try { fin = await api("/api/finances"); } catch (e) { /* wing renders unleveled */ }

  const wing = el("div", "office-wing");
  wing.appendChild(el("div", "office-wing-title",
    `Facilities wing <span class="muted">— build & upgrade under Finances</span>`));
  const row = el("div", "office-wing-row");
  for (const f of OFFICE_FACILITY_ROOMS) {
    const info = fin && fin.facilities ? fin.facilities[f.id] : null;
    const level = info ? info.level : 1;
    const built = level > 0;
    const d = el("div", "office-fac" + (built ? "" : " locked"));
    const img = el("img");
    img.src = `${OFFICE_ART}/${f.id}_l${level >= 3 ? 3 : 1}.png`;
    img.alt = f.label;
    img.draggable = false;
    d.appendChild(img);
    d.appendChild(el("span", "office-badge" + (built ? "" : " off"), built ? `L${level}` : "not built"));
    const sub = built
      ? `level ${level}/${info ? info.max_level : 3}` +
        (info && info.upkeep ? ` · ${money(info.upkeep)}/wk` : "") + ` · ${f.sub}`
      : `empty lot — ${f.sub}`;
    d.appendChild(el("div", "office-fac-name", `<b>${f.label}</b><br><span class="muted">${sub}</span>`));
    d.title = built
      ? `${f.label} (level ${level}) — manage in Finances`
      : `${f.label} not built yet — open Finances to invest`;
    d.onclick = () => officeGoTab("finances");
    row.appendChild(d);
  }
  wing.appendChild(row);
  card.appendChild(wing);

  v.appendChild(card);
}
