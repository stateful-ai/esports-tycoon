/* Player & team profile screens — modal overlays over the campaign hub.

   Pure API consumer, like every other screen: the UI holds NO sim state.
   The overlay renders whatever the profile endpoints return and degrades
   gracefully when a section is empty or the endpoint is absent.

   Contract (backend built to this exactly):
     GET /api/players/{pid}/profile ->
       { player:{id,handle,age,role,team_id,team_name,team_logo,portrait,
                 is_user_team,is_free_agent},
         overview:{ovr,potential,form,morale,condition,market_value,salary,
                   contract_weeks,playstyle,fogged},
         traits:[{name,desc,revealed}],
         attributes:[{key,label,value,band}]   (value null + band when fogged),
         agents:[{agent_id,name,icon,mastery}],
         season:{matches,kills,deaths,assists,kd,acs,first_kills,clutches},
         weekly:[{season,week,opponent,result,kills,deaths,acs}]  (oldest first),
         relationships:[{pid,handle,kind,strength}],
         career:[{season,team,matches,kd,acs}] }
     GET /api/teams/{tid}/profile ->
       { team:{id,name,logo,region,league_tier,is_user_team},
         record:{wins,losses,round_diff,position,streak},
         splits:{attack_round_rate,defense_round_rate},
         maps:[{map,played,wins,losses}],
         players:[{pid,handle,role,matches,kd,acs}],
         form:[{season,week,opponent,result,score}]  (oldest first),
         honors:[str] }

   Every value may be null / every array empty; each section hides itself or
   shows a quiet "not tracked yet" line rather than rendering NaN/undefined.

   Navigation: opening a relationship chip or a roster row from inside a
   profile replaces the overlay content in place (no back-stack). A single
   document-level, capture-phase click listener (installed here) turns any
   [data-pid]/[data-tid] element across the whole app into a profile link.

   Relies on app.js globals: el, money. */

/* -- silent transport ------------------------------------------------------
   Deliberately NOT the shared api(): api() toasts + throws on any non-2xx,
   which would spam the UI before the profile endpoints ship. A failure here
   just degrades to the "profile unavailable" card. */
async function profileFetch(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

/* -- small formatting helpers ---------------------------------------------- */

// Round/format a numeric, degrading null/undefined/NaN to an em dash.
function pfNum(v, digits = 0) {
  if (v == null || (typeof v === "number" && isNaN(v))) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  return digits ? n.toFixed(digits) : String(Math.round(n));
}

// Round-rate values may arrive as a fraction (0..1) or a percent (0..100).
function pfPct(v) {
  if (v == null || isNaN(v)) return null;
  const n = Number(v);
  return Math.round(n <= 1 ? n * 100 : n);
}

const pfWk = (w) => `S${w.season}·W${w.week}`;

// A token-styled horizontal fill bar (accent gradient — see profile.css).
function pfBar(value, max = 100) {
  const w = Math.max(2, Math.min(100, (Number(value) / max) * 100));
  return `<span class="pf-hbar"><i style="width:${w}%"></i></span>`;
}

function pfSection(title) {
  const s = el("div", "pf-section");
  if (title) s.appendChild(el("h3", "pf-section-title", title));
  return s;
}

function pfTile(label, value, sub) {
  return el(
    "div",
    "pf-tile",
    `<div class="pf-tile-val mono">${value}</div>` +
      `<div class="pf-tile-label">${label}</div>` +
      (sub ? `<div class="pf-tile-sub">${sub}</div>` : "")
  );
}

// Small quiet placeholder for a section that has no data yet.
function pfEmpty(msg) {
  return el("p", "pf-empty muted", msg);
}

/* -- charts (hand-rolled inline SVG, no libraries) -------------------------- */

// ACS across the played weeks. 2px line, dots on hover only, min/max on the
// y-axis in tiny tertiary mono. Renders with a single point (lone dot) and
// returns null for an empty series so the caller can hide the block.
function pfSparkline(weekly) {
  const pts = (weekly || []).filter((w) => w && w.acs != null && !isNaN(w.acs));
  if (!pts.length) return null;
  const W = 280, H = 64, ml = 6, mr = 6, mt = 12, mb = 10;
  const pw = W - ml - mr, ph = H - mt - mb;
  const vals = pts.map((w) => +w.acs);
  let mn = Math.min(...vals), mx = Math.max(...vals);
  if (mn === mx) { mn -= 1; mx += 1; }
  const x = (i) => (pts.length === 1 ? ml + pw / 2 : ml + (i / (pts.length - 1)) * pw);
  const y = (v) => mt + ph - ((v - mn) / (mx - mn)) * ph;
  const coords = pts.map((w, i) => [x(i), y(+w.acs)]);
  const dots = coords
    .map(
      (c, i) =>
        `<circle class="pf-spark-dot" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="2.6">` +
        `<title>${pfWk(pts[i])}: ${Math.round(pts[i].acs)} ACS</title></circle>`
    )
    .join("");
  const poly =
    pts.length > 1
      ? `<polyline class="pf-spark-line" points="${coords.map((c) => `${c[0].toFixed(1)},${c[1].toFixed(1)}`).join(" ")}"/>`
      : "";
  const yLabels =
    `<text class="pf-axis" x="${ml}" y="${mt - 3}">${Math.round(mx)}</text>` +
    `<text class="pf-axis" x="${ml}" y="${H - 2}">${Math.round(mn)}</text>`;
  return `<svg class="pf-chart pf-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="ACS by week">${poly}${dots}${yLabels}</svg>`;
}

// Kills (up) vs deaths (down) per week, mirrored around a centre axis.
// Returns null for an empty series.
function pfMirrorBars(weekly) {
  const pts = (weekly || []).filter((w) => w && (w.kills != null || w.deaths != null));
  if (!pts.length) return null;
  const W = 280, H = 88, mt = 6, mb = 6, ml = 6, mr = 6;
  const pw = W - ml - mr;
  const half = (H - mt - mb) / 2;
  const cy = mt + half;
  const mx = Math.max(1, ...pts.map((w) => Math.max(w.kills || 0, w.deaths || 0)));
  const slot = pw / pts.length;
  const bw = Math.min(18, slot * 0.6);
  let bars = "";
  pts.forEach((w, i) => {
    const cx = ml + slot * i + slot / 2;
    const kh = ((w.kills || 0) / mx) * half;
    const dh = ((w.deaths || 0) / mx) * half;
    bars +=
      `<rect class="pf-bar-k" x="${(cx - bw / 2).toFixed(1)}" y="${(cy - kh).toFixed(1)}" width="${bw.toFixed(1)}" height="${kh.toFixed(1)}" rx="0.8">` +
      `<title>${pfWk(w)}: ${w.kills || 0} kills</title></rect>` +
      `<rect class="pf-bar-d" x="${(cx - bw / 2).toFixed(1)}" y="${cy.toFixed(1)}" width="${bw.toFixed(1)}" height="${dh.toFixed(1)}" rx="0.8">` +
      `<title>${pfWk(w)}: ${w.deaths || 0} deaths</title></rect>`;
  });
  const axis = `<line class="pf-bar-axis" x1="${ml}" y1="${cy}" x2="${W - mr}" y2="${cy}"/>`;
  return `<svg class="pf-chart pf-mirror" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Kills and deaths by week">${axis}${bars}</svg>`;
}

/* -- player profile --------------------------------------------------------- */

function renderPlayerProfile(data) {
  const frag = document.createDocumentFragment();
  const p = data.player || {};
  const ov = data.overview || {};

  // Header ------------------------------------------------------------------
  const header = el("div", "pf-header");
  const portrait = p.portrait
    ? `<img class="pf-portrait" src="${p.portrait}" alt="" onerror="this.style.visibility='hidden'">`
    : `<span class="pf-portrait pf-portrait-blank"></span>`;
  const teamBit =
    !p.is_free_agent && p.team_id
      ? `<span class="pf-team tlink" data-tid="${p.team_id}" title="View team">` +
        (p.team_logo ? `<img class="pf-team-logo" src="${p.team_logo}" alt="" onerror="this.style.display='none'">` : "") +
        `<span>${p.team_name ?? "—"}</span></span>`
      : `<span class="pill">free agent</span>`;
  const meta = [
    p.role ? `<span class="pill">${p.role}</span>` : "",
    ov.playstyle ? `<span class="pill">${ov.playstyle}</span>` : "",
    p.age != null ? `<span class="pf-age">age ${p.age}</span>` : "",
  ].filter(Boolean).join("");
  const contract = p.is_free_agent
    ? "Free agent — unsigned"
    : `${ov.contract_weeks != null ? ov.contract_weeks + "w left" : "—"} · ${money(ov.salary)}/wk`;
  header.innerHTML =
    portrait +
    `<div class="pf-id">` +
    `<div class="pf-handle">${p.handle ?? "Unknown"}</div>` +
    `<div class="pf-meta">${meta}${teamBit}</div>` +
    `<div class="pf-contract muted">${contract}</div>` +
    `</div>`;
  frag.appendChild(header);

  // Overview stat tiles -----------------------------------------------------
  const tiles = el("div", "pf-tiles");
  const ovrSub = ov.fogged ? "scouted" : "";
  tiles.appendChild(pfTile("OVR", (ov.fogged && ov.ovr != null ? "~" : "") + pfNum(ov.ovr), ovrSub));
  tiles.appendChild(pfTile("Potential", pfNum(ov.potential)));
  tiles.appendChild(pfTile("Form", pfNum(ov.form)));
  tiles.appendChild(pfTile("Morale", pfNum(ov.morale)));
  tiles.appendChild(pfTile("Condition", pfNum(ov.condition)));
  tiles.appendChild(pfTile("Value", ov.market_value != null ? money(ov.market_value) : "—"));
  frag.appendChild(tiles);

  // Attributes | traits + agents (two columns) ------------------------------
  const grid = el("div", "pf-grid2");

  const attrSec = pfSection("Attributes");
  const attrs = data.attributes || [];
  if (attrs.length) {
    const list = el("div", "pf-attrs");
    for (const a of attrs) {
      const lbl = a.label || a.key || "";
      if (a.value != null) {
        list.appendChild(
          el(
            "div",
            "pf-attr",
            `<span class="pf-attr-label">${lbl}</span>` +
              `<span class="pf-attr-bar">${pfBar(a.value, 100)}</span>` +
              `<span class="pf-attr-val mono">${Math.round(a.value)}</span>`
          )
        );
      } else {
        list.appendChild(
          el(
            "div",
            "pf-attr",
            `<span class="pf-attr-label">${lbl}</span>` +
              `<span class="pf-attr-band"><span class="pf-band" title="scouting estimate">${a.band ?? "?"}</span></span>`
          )
        );
      }
    }
    attrSec.appendChild(list);
  } else {
    attrSec.appendChild(pfEmpty("Attributes not scouted yet."));
  }
  grid.appendChild(attrSec);

  const rightCol = el("div", "pf-col");

  const traitSec = pfSection("Traits");
  const traits = (data.traits || []).filter(Boolean);
  if (traits.length) {
    const chips = el("div", "pf-chips");
    for (const t of traits) {
      if (t.revealed === false) {
        chips.appendChild(el("span", "pf-chip pf-chip-locked", "?"));
      } else {
        const c = el("span", "pf-chip", t.name ?? "");
        if (t.desc) c.title = t.desc;
        chips.appendChild(c);
      }
    }
    traitSec.appendChild(chips);
  } else {
    traitSec.appendChild(pfEmpty("No traits revealed."));
  }
  rightCol.appendChild(traitSec);

  const agentSec = pfSection("Agent pool");
  const agents = data.agents || [];
  if (agents.length) {
    const list = el("div", "pf-agents");
    for (const a of agents) {
      const icon = a.icon
        ? `<img class="pf-agent-icon" src="${a.icon}" alt="" onerror="this.style.visibility='hidden'">`
        : `<span class="pf-agent-icon"></span>`;
      list.appendChild(
        el(
          "div",
          "pf-agent",
          icon +
            `<span class="pf-agent-name">${a.name || a.agent_id || ""}</span>` +
            `<span class="pf-agent-bar">${pfBar(a.mastery, 100)}</span>` +
            `<span class="pf-agent-mv mono">${pfNum(a.mastery)}</span>`
        )
      );
    }
    agentSec.appendChild(list);
  } else {
    agentSec.appendChild(pfEmpty("No agent pool data."));
  }
  rightCol.appendChild(agentSec);

  grid.appendChild(rightCol);
  frag.appendChild(grid);

  // Season analytics --------------------------------------------------------
  const s = data.season;
  const weekly = data.weekly || [];
  if (s || weekly.length) {
    const sec = pfSection(`Season — analytics`);
    if (s) {
      const st = el("div", "pf-tiles pf-tiles-sm");
      st.appendChild(pfTile("K/D", pfNum(s.kd, 2)));
      st.appendChild(pfTile("ACS", pfNum(s.acs)));
      st.appendChild(pfTile("First kills", pfNum(s.first_kills)));
      st.appendChild(pfTile("Clutches", pfNum(s.clutches)));
      sec.appendChild(st);
      sec.appendChild(
        el(
          "p",
          "pf-season-line muted",
          `${pfNum(s.matches)} matches · ${pfNum(s.kills)} / ${pfNum(s.deaths)} / ${pfNum(s.assists)} K / D / A`
        )
      );
    }
    const spark = pfSparkline(weekly);
    const mirror = pfMirrorBars(weekly);
    if (spark) {
      const box = el("div", "pf-chart-box");
      box.innerHTML = `<div class="pf-chart-cap">ACS by week</div>${spark}`;
      sec.appendChild(box);
    }
    if (mirror) {
      const box = el("div", "pf-chart-box");
      box.innerHTML =
        `<div class="pf-chart-cap">Kills &amp; deaths by week` +
        `<span class="pf-legend"><span class="pf-sw pf-sw-k"></span>K` +
        `<span class="pf-sw pf-sw-d"></span>D</span></div>${mirror}`;
      sec.appendChild(box);
    }
    if (!s && !spark && !mirror) sec.appendChild(pfEmpty("No matches played yet."));
    frag.appendChild(sec);
  }

  // Relationships -----------------------------------------------------------
  const rels = data.relationships || [];
  if (rels.length) {
    const sec = pfSection("Relationships");
    const chips = el("div", "pf-chips");
    for (const r of rels) {
      const chip = el(
        "span",
        `pf-rel-chip plink rel-${r.kind || "neutral"}`,
        `${r.handle ?? "—"}<span class="pf-rel-kind">${r.kind ?? ""}</span>`
      );
      if (r.pid) chip.dataset.pid = r.pid;
      if (r.strength != null) chip.title = `${r.kind ?? "bond"} · strength ${Math.round(r.strength)}`;
      chips.appendChild(chip);
    }
    sec.appendChild(chips);
    frag.appendChild(sec);
  }

  // Career ------------------------------------------------------------------
  const career = data.career || [];
  if (career.length) {
    const sec = pfSection("Career");
    const t = el("table", "pf-table");
    t.innerHTML =
      `<thead><tr><th>Season</th><th>Team</th><th class="num">Maps</th>` +
      `<th class="num">K/D</th><th class="num">ACS</th></tr></thead>`;
    const tb = el("tbody");
    for (const c of career) {
      tb.appendChild(
        el(
          "tr",
          "",
          `<td>S${c.season ?? "—"}</td><td>${c.team ?? "—"}</td>` +
            `<td class="num">${pfNum(c.matches)}</td>` +
            `<td class="num">${pfNum(c.kd, 2)}</td>` +
            `<td class="num">${pfNum(c.acs)}</td>`
        )
      );
    }
    t.appendChild(tb);
    sec.appendChild(t);
    frag.appendChild(sec);
  }

  return frag;
}

/* -- team profile ----------------------------------------------------------- */

function renderTeamProfile(data) {
  const frag = document.createDocumentFragment();
  const t = data.team || {};
  const rec = data.record || {};

  // Header ------------------------------------------------------------------
  const header = el("div", "pf-header");
  const logo = t.logo
    ? `<img class="pf-team-badge" src="${t.logo}" alt="" onerror="this.style.visibility='hidden'">`
    : `<span class="pf-team-badge pf-portrait-blank"></span>`;
  const tierBits = [t.region ? String(t.region).toUpperCase() : "", t.league_tier]
    .filter((x) => x != null && x !== "")
    .join(" · ");
  const recBits = [];
  if (rec.wins != null || rec.losses != null) recBits.push(`${pfNum(rec.wins)}–${pfNum(rec.losses)}`);
  if (rec.position != null) recBits.push(`#${rec.position}`);
  if (rec.round_diff != null) recBits.push(`${rec.round_diff > 0 ? "+" : ""}${rec.round_diff} rd`);
  if (rec.streak) recBits.push(String(rec.streak));
  header.innerHTML =
    logo +
    `<div class="pf-id">` +
    `<div class="pf-handle">${t.name ?? "Unknown"}</div>` +
    (tierBits ? `<div class="pf-meta"><span class="pill">${tierBits}</span></div>` : "") +
    (recBits.length ? `<div class="pf-contract mono">${recBits.join("  ·  ")}</div>` : "") +
    `</div>`;
  frag.appendChild(header);

  // Attack / defense round-rate split --------------------------------------
  const sp = data.splits || {};
  const atk = pfPct(sp.attack_round_rate);
  const def = pfPct(sp.defense_round_rate);
  if (atk != null || def != null) {
    const sec = pfSection("Round-win split");
    const wrap = el("div", "pf-split");
    wrap.innerHTML =
      `<div class="pf-split-lab pf-split-atk">ATK <b class="mono">${atk != null ? atk + "%" : "—"}</b></div>` +
      `<div class="pf-split-bar">` +
      `<div class="pf-split-fill atk" style="width:${(atk ?? 0) / 2}%"></div>` +
      `<div class="pf-split-fill def" style="width:${(def ?? 0) / 2}%"></div>` +
      `<span class="pf-split-mid"></span>` +
      `</div>` +
      `<div class="pf-split-lab pf-split-def"><b class="mono">${def != null ? def + "%" : "—"}</b> DEF</div>`;
    sec.appendChild(wrap);
    frag.appendChild(sec);
  }

  // Map winrates ------------------------------------------------------------
  const maps = data.maps || [];
  if (maps.length) {
    const sec = pfSection("Map winrate");
    const list = el("div", "pf-maps");
    for (const m of maps) {
      const wr = m.played ? Math.round((m.wins / m.played) * 100) : null;
      const cls = wr == null ? "" : wr >= 55 ? "good" : wr >= 45 ? "warn" : "bad";
      list.appendChild(
        el(
          "div",
          "pf-map",
          `<span class="pf-map-name">${m.map ?? "—"}</span>` +
            `<span class="pf-map-bar"><span class="pf-hbar ${cls}"><i style="width:${wr ?? 0}%"></i></span></span>` +
            `<span class="pf-map-rec mono muted">${pfNum(m.wins)}–${pfNum(m.losses)}</span>` +
            `<span class="pf-map-wr mono">${wr != null ? wr + "%" : "—"}</span>`
        )
      );
    }
    sec.appendChild(list);
    frag.appendChild(sec);
  }

  // Roster contribution -----------------------------------------------------
  const players = data.players || [];
  if (players.length) {
    const sec = pfSection("Roster");
    const maxAcs = Math.max(1, ...players.map((pl) => pl.acs || 0));
    const tb = el("tbody");
    for (const pl of players) {
      const tr = el(
        "tr",
        "pf-rrow plink",
        `<td><b>${pl.handle ?? "—"}</b></td>` +
          `<td>${pl.role ? `<span class="pill">${pl.role}</span>` : ""}</td>` +
          `<td class="num">${pfNum(pl.matches)}</td>` +
          `<td class="num">${pfNum(pl.kd, 2)}</td>` +
          `<td class="pf-acs-cell"><span class="pf-hbar">${`<i style="width:${Math.max(2, Math.min(100, ((pl.acs || 0) / maxAcs) * 100))}%"></i>`}</span><span class="mono pf-acs-val">${pfNum(pl.acs)}</span></td>`
      );
      if (pl.pid) tr.dataset.pid = pl.pid;
      tb.appendChild(tr);
    }
    const table = el("table", "pf-table pf-roster");
    table.innerHTML =
      `<thead><tr><th>Player</th><th>Role</th><th class="num">Maps</th>` +
      `<th class="num">K/D</th><th>ACS</th></tr></thead>`;
    table.appendChild(tb);
    sec.appendChild(table);
    frag.appendChild(sec);
  }

  // Form strip (oldest -> newest) ------------------------------------------
  const form = data.form || [];
  if (form.length) {
    const sec = pfSection("Form");
    const strip = el("div", "pf-form");
    for (const f of form) {
      const res = (f.result || "").toString().toUpperCase();
      const cls = res.startsWith("W") ? "w" : res.startsWith("L") ? "l" : "d";
      const sq = el("span", `pf-form-sq ${cls}`, res.slice(0, 1) || "·");
      sq.title = `${f.opponent ? "vs " + f.opponent : ""}${f.score ? " · " + f.score : ""}`.trim() || "—";
      strip.appendChild(sq);
    }
    sec.appendChild(strip);
    frag.appendChild(sec);
  }

  // Honors ------------------------------------------------------------------
  const honors = (data.honors || []).filter(Boolean);
  if (honors.length) {
    const sec = pfSection("Honors");
    for (const h of honors) sec.appendChild(el("div", "pf-honor", `★ ${h}`));
    frag.appendChild(sec);
  }

  return frag;
}

/* -- overlay plumbing ------------------------------------------------------- */

let pfOverlayEl = null;

function pfEnsureOverlay() {
  if (pfOverlayEl) return pfOverlayEl;
  const ov = document.createElement("div");
  ov.id = "profile";
  ov.className = "overlay hidden";
  ov.innerHTML =
    `<div class="panel pf-panel">` +
    `<button class="pf-close" aria-label="Close profile">✕</button>` +
    `<div id="profile-body" class="pf-body"></div>` +
    `</div>`;
  // Click-outside closes; clicks inside the panel do not reach here.
  ov.addEventListener("click", (e) => { if (e.target === ov) closeProfile(); });
  ov.querySelector(".pf-close").addEventListener("click", closeProfile);
  document.body.appendChild(ov);
  pfOverlayEl = ov;
  return ov;
}

function pfShow(node) {
  const ov = pfEnsureOverlay();
  const body = ov.querySelector("#profile-body");
  body.replaceChildren(node);
  body.scrollTop = 0;
  ov.classList.remove("hidden");
}

function pfLoading() {
  return el("div", "pf-loading muted", "Loading profile…");
}

function pfUnavailable() {
  return el(
    "div",
    "pf-unavailable",
    `<div class="pf-unavailable-mark">◌</div>` +
      `<p class="pf-unavailable-title">Profile unavailable</p>` +
      `<p class="muted">This profile can't be loaded right now.</p>`
  );
}

function closeProfile() {
  if (pfOverlayEl) pfOverlayEl.classList.add("hidden");
}

function isProfileOpen() {
  return !!pfOverlayEl && !pfOverlayEl.classList.contains("hidden");
}

/* -- public entry points ---------------------------------------------------- */

async function openPlayerProfile(pid) {
  if (pid == null) return;
  pfShow(pfLoading());
  const data = await profileFetch(`/api/players/${encodeURIComponent(pid)}/profile`);
  if (!isProfileOpen()) return; // user closed it while the request was in flight
  pfShow(data ? renderPlayerProfile(data) : pfUnavailable());
}

async function openTeamProfile(tid) {
  if (tid == null) return;
  pfShow(pfLoading());
  const data = await profileFetch(`/api/teams/${encodeURIComponent(tid)}/profile`);
  if (!isProfileOpen()) return;
  pfShow(data ? renderTeamProfile(data) : pfUnavailable());
}

/* -- one delegated listener for the whole app ------------------------------
   Capture phase + stopPropagation: a click on a profile link opens the
   profile and is consumed, so an underlying row handler (roster expand,
   standings->roster nav, etc.) does NOT also fire. Non-link clicks fall
   straight through untouched. */
function pfDelegatedClick(e) {
  const node = e.target;
  if (!(node instanceof Element)) return;
  const pl = node.closest("[data-pid]");
  if (pl) {
    e.stopPropagation();
    e.preventDefault();
    openPlayerProfile(pl.getAttribute("data-pid"));
    return;
  }
  const tl = node.closest("[data-tid]");
  if (tl) {
    e.stopPropagation();
    e.preventDefault();
    openTeamProfile(tl.getAttribute("data-tid"));
  }
}

(function pfInit() {
  document.addEventListener("click", pfDelegatedClick, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isProfileOpen()) {
      e.stopPropagation();
      closeProfile();
    }
  });
})();
