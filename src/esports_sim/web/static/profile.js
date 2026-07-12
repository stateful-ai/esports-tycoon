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
   profile pushes the current view onto a back-stack ("← Back" in the panel
   chrome walks it; closing the overlay clears it). Every open captures a
   ++pfSeq token before fetching and drops its response if a newer open
   superseded it, so rapid clicks can't race a stale profile onto screen.
   A single document-level, capture-phase click listener (installed here)
   turns any [data-pid]/[data-tid]/[data-sid] element across the whole app
   into a profile link.

   Relies on app.js globals: el, money, esc, humanize, plink/tlink/slink,
   api, toast, App. */

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

// Coarse star quick-glance ("★★★½") from a 0.5-5.0 rating — the number is
// the real signal; stars are just a fast read.
function pfStars(v) {
  if (v == null || isNaN(v)) return "";
  const full = Math.floor(v);
  return "★".repeat(full) + (v % 1 >= 0.5 ? "½" : "");
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

// Generic single-metric line over a weekly series (same visual language as
// pfSparkline, different accessor). Returns null when the series is empty.
function pfMetricLine(series, get, fmt, aria) {
  const pts = (series || []).filter((w) => w && get(w) != null && !isNaN(get(w)));
  if (!pts.length) return null;
  const W = 280, H = 64, ml = 6, mr = 6, mt = 12, mb = 10;
  const pw = W - ml - mr, ph = H - mt - mb;
  const vals = pts.map(get).map(Number);
  let mn = Math.min(...vals), mx = Math.max(...vals);
  if (mn === mx) { mn -= 1; mx += 1; }
  const x = (i) => (pts.length === 1 ? ml + pw / 2 : ml + (i / (pts.length - 1)) * pw);
  const y = (v) => mt + ph - ((v - mn) / (mx - mn)) * ph;
  const coords = vals.map((v, i) => [x(i), y(v)]);
  const dots = coords
    .map(
      (c, i) =>
        `<circle class="pf-spark-dot" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="2.6">` +
        `<title>${pfWk(pts[i])}: ${fmt(vals[i])}</title></circle>`
    )
    .join("");
  const poly =
    pts.length > 1
      ? `<polyline class="pf-spark-line" points="${coords.map((c) => `${c[0].toFixed(1)},${c[1].toFixed(1)}`).join(" ")}"/>`
      : "";
  const yLabels =
    `<text class="pf-axis" x="${ml}" y="${mt - 3}">${fmt(mx)}</text>` +
    `<text class="pf-axis" x="${ml}" y="${H - 2}">${fmt(mn)}</text>`;
  return `<svg class="pf-chart pf-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${aria}">${poly}${dots}${yLabels}</svg>`;
}

function pfRatingLine(series) {
  return pfMetricLine(series, (w) => w.rating, (v) => Number(v).toFixed(2), "Rating by week");
}

// Two-line development chart: current ability + confidence, shared x-axis.
function pfDevChart(series) {
  const pts = (series || []).filter((w) => w && w.ca != null);
  if (!pts.length) return null;
  const W = 280, H = 88, ml = 6, mr = 6, mt = 12, mb = 10;
  const pw = W - ml - mr, ph = H - mt - mb;
  const caVals = pts.map((w) => +w.ca);
  const cfVals = pts.map((w) => +(w.confidence ?? 50));
  let mn = Math.min(...caVals, ...cfVals), mx = Math.max(...caVals, ...cfVals);
  if (mx - mn < 4) { mn -= 2; mx += 2; }
  const x = (i) => (pts.length === 1 ? ml + pw / 2 : ml + (i / (pts.length - 1)) * pw);
  const y = (v) => mt + ph - ((v - mn) / (mx - mn)) * ph;
  const line = (vals, cls) =>
    pts.length > 1
      ? `<polyline class="${cls}" points="${vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}"/>`
      : `<circle class="pf-spark-dot" cx="${x(0)}" cy="${y(vals[0])}" r="2.6"/>`;
  const tips = pts
    .map(
      (w, i) =>
        `<circle class="pf-spark-dot" cx="${x(i).toFixed(1)}" cy="${y(caVals[i]).toFixed(1)}" r="2.4">` +
        `<title>${pfWk(w)}: CA ${caVals[i].toFixed(1)} / conf ${Math.round(cfVals[i])}</title></circle>`
    )
    .join("");
  const yLabels =
    `<text class="pf-axis" x="${ml}" y="${mt - 3}">${Math.round(mx)}</text>` +
    `<text class="pf-axis" x="${ml}" y="${H - 2}">${Math.round(mn)}</text>`;
  return `<svg class="pf-chart pf-dev" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Ability and confidence over time">` +
    `${line(caVals, "pf-spark-line")}${line(cfVals, "pf-spark-line pf-line-alt")}${tips}${yLabels}</svg>`;
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
  // Languages read as "PT 95 · EN 60" — the fluency number matters (shared
  // languages drive the locker room's comms cohesion).
  const langBit = (p.languages || [])
    .map((l) => `${(l.lang || "").toUpperCase()} ${l.level}`)
    .join(" · ");
  const meta = [
    p.role ? `<span class="pill">${p.role}</span>` : "",
    ov.playstyle ? `<span class="pill">${ov.playstyle}</span>` : "",
    p.country ? `<span class="pill" title="nationality">${p.country}</span>` : "",
    langBit ? `<span class="pill" title="spoken languages (fluency)">${langBit}</span>` : "",
    p.age != null ? `<span class="pf-age">age ${p.age}</span>` : "",
    p.is_starter === false ? `<span class="pill">bench</span>` : "",
    p.followers != null && typeof fmtFollowers === "function"
      ? `<span class="pill" title="social reach">${fmtFollowers(p.followers)} followers</span>`
      : "",
    p.stream_load != null && p.stream_load > 5
      ? `<span class="pill" title="org cut ${money(p.stream_income)}/wk · heavy streaming slows development to ×${p.stream_growth_mult}">🎥 ${p.stream_status} · ${money(p.stream_income)}/wk</span>`
      : "",
    // Long tenure = a club fixture (serializer sends raw weeks; render-only).
    p.tenure_weeks != null && p.tenure_weeks >= 26
      ? `<span class="pill" title="long tenure builds loyalty — affects transfer asks and renewals">${pfNum(p.tenure_weeks)}w at club</span>`
      : "",
    p.dev_focus
      ? `<span class="pill" title="development plan">${p.dev_focus} · ${p.training_intensity}</span>`
      : "",
  ].filter(Boolean).join("");
  const contract = p.is_free_agent
    ? "Free agent — unsigned"
    : `${ov.contract_weeks != null ? ov.contract_weeks + "w left" : "—"} · ${money(ov.salary)}/wk`;
  const contractDetail = ov.contract_terms;
  const contractTerms = (!p.is_free_agent && contractDetail)
    ? `${contractDetail.stream_share}% streams · ${money(contractDetail.release_fee)} release · ` +
      `${contractDetail.buyout ? money(contractDetail.buyout) + " buyout" : "no buyout"} · ${contractDetail.roster_role}` +
      `${contractDetail.no_transfer ? " · no-transfer" : ""}`
    : "";
  header.innerHTML =
    portrait +
    `<div class="pf-id">` +
    `<div class="pf-handle">${p.handle ?? "Unknown"}</div>` +
    (data.epithet ? `<div class="pf-epithet">${data.epithet}</div>` : "") +
    `<div class="pf-meta">${meta}${teamBit}</div>` +
    `<div class="pf-contract muted">${contract}</div>` +
    (contractTerms ? `<div class="pf-contract muted">${contractTerms}</div>` : "") +
    `</div>`;
  // Rival contracted player → offer a package (players and/or cash).
  if (!p.is_free_agent && !p.is_user_team && p.transfer_ask != null
      && typeof openOffer === "function") {
    const offer = el("button", "btn btn-sm", "Make an offer…");
    offer.onclick = () => {
      closeProfile();
      openOffer({ id: p.id, handle: p.handle, ask: p.transfer_ask, team_name: p.team_name });
    };
    header.appendChild(offer);
  }
  // Own player streaming enough to matter → spend the week's 1:1 asking them
  // to cut back and grind: more practice (faster growth) for less streaming
  // revenue and a morale knock. Drifts back toward their baseline over weeks.
  if (p.is_user_team && p.can_rein_streaming) {
    const rein = el("button", "btn btn-sm", "Rein in streaming…");
    rein.title = "Spend this week's 1:1 telling them to stream less and practice more";
    rein.onclick = async () => {
      try {
        await api("/api/actions/rein_streaming", { player_id: p.id });
        openPlayerProfile(p.id);  // refresh: new load/status, button now gone
      } catch { /* api() already surfaced the reason (e.g. 1:1 already used) */ }
    };
    header.appendChild(rein);
  }
  if (isAdminMode()) {
    const slot = el("div", "pf-admin-slot");
    const editBtn = el("button", "btn btn-sm", "🛠 Correct data");
    editBtn.onclick = () => pfOpenAdminEdit("player", p.id, slot);
    header.appendChild(editBtn);
    frag.appendChild(header);
    frag.appendChild(slot);
  } else {
    frag.appendChild(header);
  }

  // Overview stat tiles -----------------------------------------------------
  const tiles = el("div", "pf-tiles");
  const ovrSub = ov.fogged ? "scouted" : pfStars(ov.ovr_stars);
  tiles.appendChild(pfTile("OVR", (ov.fogged && ov.ovr != null ? "~" : "") + pfNum(ov.ovr), ovrSub));
  // Peak: a PROJECTION band even for your own club. It can be missed or beaten;
  // a fogged rival shows the scout's banded tier.
  const potIsNum = typeof ov.potential === "number";
  const potBand = ov.potential_band;
  tiles.appendChild(pfTile(
    "Potential",
    potBand ? `${potBand[0]}–${potBand[1]}`
      : (potIsNum ? pfNum(ov.potential) : (ov.potential || "—")),
    potBand ? "peak forecast"
      : (potIsNum ? pfStars(ov.potential_stars) : "scouted")
  ));
  tiles.appendChild(pfTile("Form", pfNum(ov.form)));
  tiles.appendChild(pfTile("Morale", pfNum(ov.morale)));
  tiles.appendChild(pfTile("Condition", pfNum(ov.condition)));
  tiles.appendChild(pfTile("Confidence", pfNum(p.confidence), "drives duels & nerve"));
  tiles.appendChild(pfTile("Value", ov.market_value != null ? money(ov.market_value) : "—"));
  frag.appendChild(tiles);

  // Badges — rolled, decaying honours (and stigmas) that move a player.
  const badges = data.badges || [];
  if (badges.length) {
    const bSec = pfSection("Badges");
    const chips = el("div", "pf-chips");
    for (const bd of badges) {
      const icon = bd.art
        ? `<img class="pf-badge-art" src="${bd.art}" alt="">`
        : `<span class="pf-badge-emoji">${bd.emoji}</span>`;
      const chip = el(
        "span",
        `pf-chip pf-badge ${bd.polarity < 0 ? "pf-badge-neg" : "pf-badge-pos"}`,
        `${icon} ${bd.name}`
      );
      chip.title = bd.blurb + (bd.season ? ` — earned S${bd.season}` : "");
      chips.appendChild(chip);
    }
    bSec.appendChild(chips);
    frag.appendChild(bSec);
  }

  // Attributes | traits + agents (two columns) ------------------------------
  const grid = el("div", "pf-grid2");

  const attrSec = pfSection("Attributes");
  const attrs = data.attributes || [];
  if (attrs.length) {
    const list = el("div", "pf-attrs");
    for (const a of attrs) {
      const lbl = a.label || a.key || "";
      if (a.value != null) {
        // Per-skill ceiling: show remaining headroom on the skill (own club).
        const ceil = (ov.skill_ceilings || {})[a.key];
        const ceilHi = Array.isArray(ceil) ? ceil[1] : ceil;
        const ceilLabel = Array.isArray(ceil) ? `${ceil[0]}–${ceil[1]}` : ceil;
        const ceilTxt = (ceilHi != null && ceilHi > Math.round(a.value) + 1)
          ? ` <span class="muted" title="projected outcome range for this skill">→${ceilLabel}</span>`
          : "";
        list.appendChild(
          el(
            "div",
            "pf-attr",
            `<span class="pf-attr-label">${lbl}</span>` +
              `<span class="pf-attr-bar">${pfBar(a.value, 100)}</span>` +
              `<span class="pf-attr-val mono">${Math.round(a.value)}${ceilTxt}</span>`
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
        const c = el("span", "pf-chip", humanize(t.name ?? ""));
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
      st.appendChild(pfTile("Rating", pfNum(s.rating, 2)));
      st.appendChild(pfTile("K/D", pfNum(s.kd, 2)));
      st.appendChild(pfTile("ACS", pfNum(s.acs)));
      st.appendChild(pfTile("KAST%", pfNum(s.kast_pct)));
      st.appendChild(pfTile("HS%", pfNum(s.hs_pct)));
      st.appendChild(
        pfTile(
          "FK : FD",
          s.first_deaths != null ? `${pfNum(s.first_kills)} : ${pfNum(s.first_deaths)}` : pfNum(s.first_kills),
          s.fk_fd != null ? `ratio ${pfNum(s.fk_fd, 2)}` : ""
        )
      );
      st.appendChild(pfTile("Clutches", pfNum(s.clutches)));
      sec.appendChild(st);
      if (s.clutch_1v1 != null) {
        sec.appendChild(el("p", "pf-season-line muted",
          `Clutches: ${pfNum(s.clutch_1v1)}x 1v1, ${pfNum(s.clutch_1v2)}x 1v2, ${pfNum(s.clutch_1v3)}x 1vX` +
          ` / Kills: ${pfNum(s.pistol_kills)} pistol, ${pfNum(s.eco_kills)} eco, ${pfNum(s.save_kills)} save` +
          (s.trade_kills != null ? `, ${pfNum(s.trade_kills)} trades` : "")));
      }
      if (s.kills_by_weapon && Object.keys(s.kills_by_weapon).length) {
        const chips = el("div", "pf-chips");
        chips.innerHTML = Object.entries(s.kills_by_weapon)
          .slice(0, 8)
          .map(([w, n]) => `<span class="pf-chip" title="kills with ${w}">${w} ${n}</span>`)
          .join("");
        sec.appendChild(chips);
      }
      if ((s.analytics_tier ?? 0) < 2) {
        sec.appendChild(el("p", "pf-empty muted",
          "Deeper numbers (KAST, trades, weapons, eco/save splits, trend charts) need a stronger analytics department."));
      }
      sec.appendChild(
        el(
          "p",
          "pf-season-line muted",
          `${pfNum(s.matches)} matches · ${pfNum(s.kills)} / ${pfNum(s.deaths)} / ${pfNum(s.assists)} K / D / A`
        )
      );
    }
    // ACS trend prefers the persisted weekly series (analytics tier 2+),
    // falling back to this season's derivable match lines.
    const perf = (data.charts && data.charts.performance) || [];
    const spark = pfSparkline(perf.length ? perf : weekly);
    const rating = pfRatingLine(perf);
    const mirror = pfMirrorBars(weekly);
    if (spark) {
      const box = el("div", "pf-chart-box");
      box.innerHTML = `<div class="pf-chart-cap">ACS by week</div>${spark}`;
      sec.appendChild(box);
    }
    if (rating) {
      const box = el("div", "pf-chart-box");
      box.innerHTML = `<div class="pf-chart-cap">Rating by week</div>${rating}`;
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

  // Development trend (own players): ability + confidence over the weeks.
  const devSeries = (data.charts && data.charts.development) || [];
  if (devSeries.length) {
    const sec = pfSection("Development");
    const dev = pfDevChart(devSeries);
    if (dev) {
      const box = el("div", "pf-chart-box");
      box.innerHTML =
        `<div class="pf-chart-cap">Ability &amp; confidence over time` +
        `<span class="pf-legend"><span class="pf-sw pf-sw-k"></span>CA` +
        `<span class="pf-sw pf-sw-d"></span>Conf</span></div>${dev}`;
      sec.appendChild(box);
    }
    const first = devSeries[0], last = devSeries[devSeries.length - 1];
    sec.appendChild(el("p", "pf-season-line muted",
      `CA ${pfNum(first.ca, 1)} to ${pfNum(last.ca, 1)} over ${devSeries.length} weeks` +
      (typeof fmtFollowers === "function" ? ` / ${fmtFollowers(last.followers)} followers` : "")));
    frag.appendChild(sec);
  }

  // Per-map / per-agent splits (analytics tier 3) ----------------------------
  const splits = data.splits;
  if (splits && ((splits.maps || []).length || (splits.agents || []).length)) {
    const sec = pfSection("Splits");
    const grid2 = el("div", "pf-grid2");
    const mkTable = (rows, label) => {
      const col = el("div");
      const t = el("table", "pf-table");
      t.innerHTML = `<thead><tr><th>${label}</th><th class="num">Maps</th>
        <th class="num">Rating</th><th class="num">ACS</th><th class="num">K/D</th>
        <th class="num">KAST%</th></tr></thead>`;
      const tb = el("tbody");
      for (const r of rows) {
        tb.appendChild(el("tr", "", `
          <td>${r.label}</td><td class="num">${r.maps}</td>
          <td class="num">${pfNum(r.rating, 2)}</td><td class="num">${pfNum(r.acs)}</td>
          <td class="num">${pfNum(r.kd, 2)}</td><td class="num">${pfNum(r.kast_pct)}</td>`));
      }
      t.appendChild(tb);
      col.appendChild(t);
      return col;
    };
    if ((splits.maps || []).length) grid2.appendChild(mkTable(splits.maps, "Map"));
    if ((splits.agents || []).length) grid2.appendChild(mkTable(splits.agents, "Agent"));
    sec.appendChild(grid2);
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

  // Career --------------------------------------------------------------
  // ONE section for the player's whole history: lifetime totals, the
  // chronicle timeline, honours, memories and the season-by-season table
  // as sub-blocks (small muted labels) — all server-selected reads.
  const ct = data.career_totals;
  const arc = data.career_arc || [];
  const honours = data.honours || [];
  const mems = data.memories || [];
  const career = data.career || [];
  if (ct || arc.length || honours.length || mems.length || career.length) {
    const sec = pfSection("Career");

    // Lifetime totals (completed seasons + the live one), from the server's
    // career_totals (gs.career_stats rolled up + the current season).
    if (ct) {
      const ctTiles = el("div", "pf-tiles pf-tiles-sm");
      ctTiles.appendChild(pfTile("Seasons", pfNum(ct.seasons)));
      ctTiles.appendChild(pfTile("Maps", pfNum(ct.maps)));
      ctTiles.appendChild(pfTile("Kills", pfNum(ct.kills)));
      ctTiles.appendChild(pfTile("K/D", ct.kd.toFixed(2)));
      ctTiles.appendChild(pfTile("Honours", pfNum(ct.honours)));
      ctTiles.appendChild(pfTile("MVPs", pfNum(ct.mvps)));
      ctTiles.appendChild(pfTile("All-Star", pfNum(ct.all_stars)));
      sec.appendChild(ctTiles);
    }

    // The player's chronicle as a per-season timeline (newest first).
    if (arc.length) {
      sec.appendChild(el("div", "pf-career-sub muted", "Timeline"));
      const list = el("div", "pf-arc");
      for (const yr of arc) {
        const row = el("div", "pf-arc-row");
        row.appendChild(el("span", "pf-arc-season mono", `S${yr.season}`));
        const evs = el("div", "pf-arc-evs");
        for (const e of yr.events) {
          evs.appendChild(el("span", `pf-arc-ev arc-${e.kind}`, e.text));
        }
        row.appendChild(evs);
        list.appendChild(row);
      }
      sec.appendChild(list);
    }

    // The trophy cabinet: this player's individual season awards, newest
    // first (server-selected chronicle read; renders as-is).
    if (honours.length) {
      sec.appendChild(el("div", "pf-career-sub muted", `Honours (${honours.length})`));
      const list = el("ul", "pf-honours");
      list.style.cssText = "margin:0;padding:0;list-style:none";
      for (const h of honours) {
        const li = el("li", "pf-honour");
        const award = el("span", "pf-honour-award");
        award.textContent = `S${h.season} · ${h.award}`;
        li.appendChild(award);
        if (h.detail) {
          const det = el("span", "pf-honour-detail muted");
          det.textContent = h.detail;
          li.appendChild(det);
        }
        list.appendChild(li);
      }
      sec.appendChild(list);
    }

    // The player's defining chronicle entries — what their career will be
    // remembered for (server-selected; pure history, renders as-is).
    if (mems.length) {
      sec.appendChild(el("div", "pf-career-sub muted", "Memories"));
      const list = el("ul", "pf-memories");
      list.style.cssText = "margin:0;padding-left:18px";
      for (const m of mems) {
        const li = el("li", "muted", "");
        li.textContent = m;
        list.appendChild(li);
      }
      sec.appendChild(list);
    }

    // Season by season (team names are plain text — no ids in the payload).
    if (career.length) {
      sec.appendChild(el("div", "pf-career-sub muted", "Season by season"));
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
    }

    frag.appendChild(sec);
  }

  // Compare -----------------------------------------------------------------
  // A lightweight side-by-side vs a teammate, fetched on demand.
  if (p.team_id) {
    const sec = pfSection("Compare");
    const sel = el("select", "pf-compare-sel");
    sel.innerHTML = `<option value="">compare with a teammate…</option>`;
    sec.appendChild(sel);
    const out = el("div", "pf-compare");
    sec.appendChild(out);
    frag.appendChild(sec);
    api(`/api/roster/${p.team_id}`)
      .then((rd) => {
        for (const q of rd.players || []) {
          if (q.id === p.id) continue;
          const o = document.createElement("option");
          o.value = q.id;
          o.textContent = q.handle;
          sel.appendChild(o);
        }
      })
      .catch(() => {});
    sel.onchange = async () => {
      if (!sel.value) { out.innerHTML = ""; return; }
      const c = await api(`/api/compare?a=${p.id}&b=${sel.value}`).catch(() => null);
      if (c) out.innerHTML = compareTable(c);
    };
  }

  return frag;
}

// Compact side-by-side comparison table (higher value wins each row).
function compareTable(c) {
  const better = (x, y) => x != null && y != null && x > y;
  const row = (label, av, bv) =>
    `<tr><td class="num ${better(av, bv) ? "cmp-win" : ""}">${av ?? "—"}</td>` +
    `<th>${label}</th>` +
    `<td class="num ${better(bv, av) ? "cmp-win" : ""}">${bv ?? "—"}</td></tr>`;
  const rows = [
    row("Overall", c.a.overall, c.b.overall),
    row("Rating", c.a.rating, c.b.rating),
    row("K/D", c.a.kd, c.b.kd),
  ];
  const bm = Object.fromEntries((c.b.attributes || []).map((x) => [x.key, x]));
  for (const a of c.a.attributes || []) {
    const b = bm[a.key];
    rows.push(row(a.label, a.value, b ? b.value : null));
  }
  return `<table class="pf-table cmp"><thead><tr><th class="num">${c.a.handle}</th>` +
    `<th></th><th class="num">${c.b.handle}</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
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
    (tierBits || data.identity
      ? `<div class="pf-meta">` +
        (tierBits ? `<span class="pill">${tierBits}</span>` : "") +
        (data.identity ? ` <span class="pill pf-identity">${data.identity}</span>` : "") +
        `</div>`
      : "") +
    (recBits.length ? `<div class="pf-contract mono">${recBits.join("  ·  ")}</div>` : "") +
    `</div>`;
  // Jump straight to this team's roster screen (own team = the default view,
  // matching the standings-row convention in app.js).
  const rosterBtn = el("button", "btn btn-sm", "View roster ▸");
  rosterBtn.onclick = () => {
    if (typeof App === "object") {
      App.rosterTeam = t.is_user_team ? null : t.id;
    }
    closeProfile();
    const tab = document.querySelector('#tabs [data-tab="roster"]');
    if (tab) tab.click();
  };
  header.appendChild(rosterBtn);
  // Rival orgs: point the scout at them from here (api() toasts errors).
  if (!t.is_user_team && t.id) {
    const scoutBtn = el("button", "btn btn-sm", "Assign scout");
    scoutBtn.title = "Retask your scout onto this org (replaces the current assignment)";
    scoutBtn.onclick = async () => {
      try {
        const r = await api("/api/actions/scout", { team_id: t.id });
        toast(r.message || "Scout assigned.");
      } catch { /* api() already surfaced the reason */ }
    };
    header.appendChild(scoutBtn);
  }
  if (isAdminMode()) {
    const slot = el("div", "pf-admin-slot");
    const editBtn = el("button", "btn btn-sm", "🛠 Correct data");
    editBtn.onclick = () => pfOpenAdminEdit("team", t.id, slot);
    header.appendChild(editBtn);
    frag.appendChild(header);
    frag.appendChild(slot);
  } else {
    frag.appendChild(header);
  }

  // Playstyle — coaching identity's tendency reads (own club or a scouted
  // rival; server sends [] otherwise).
  const tend = data.tendencies || [];
  if (tend.length) {
    const sec = pfSection("Playstyle");
    sec.appendChild(el("p", "muted", tend.join(" · ")));
    frag.appendChild(sec);
  }

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
        `<td><b>${pl.handle ?? "—"}</b>${pl.retirement_risk ? ` <span class="pill retire-pill" title="A veteran carrying real retirement odds this offseason">TWILIGHT</span>` : ""}</td>` +
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

  // Rivalries ---------------------------------------------------------------
  // The pairs whose history means something (server-ranked).
  const rivals = data.rivals || [];
  if (rivals.length) {
    const sec = pfSection("Rivalries");
    const chips = el("div", "pf-chips");
    for (const r of rivals) {
      const chip = el(
        "span",
        "pf-rel-chip tlink rel-clash",
        `${r.name}<span class="pf-rel-kind">heat ${Math.round(r.intensity)}</span>`
      );
      if (r.team_id) chip.dataset.tid = r.team_id;
      chips.appendChild(chip);
    }
    sec.appendChild(chips);
    frag.appendChild(sec);
  }

  // Squad chemistry ---------------------------------------------------------
  // Own-club only: cohesion + the strongest bonds and worst frictions.
  const chem = data.chemistry;
  if (chem && (chem.cohesion != null)) {
    const sec = pfSection(`Squad chemistry · cohesion ${Math.round(chem.cohesion)}`);
    // Each name in the pair is its own profile link (a_id/b_id from server).
    const pairChip = (p, cls) => {
      const chip = el("span", `pf-rel-chip ${cls}`,
        `${plink(p.a_id, p.a)} + ${plink(p.b_id, p.b)}` +
        `<span class="pf-rel-kind">${Math.round(p.strength)}</span>`);
      return chip;
    };
    const chips = el("div", "pf-chips");
    for (const b of chem.bonds) chips.appendChild(pairChip(b, "rel-duo"));
    for (const f of chem.frictions) chips.appendChild(pairChip(f, "rel-feud"));
    if (!chem.bonds.length && !chem.frictions.length) {
      chips.appendChild(el("span", "muted", "a settled, unremarkable dressing room"));
    }
    sec.appendChild(chips);
    frag.appendChild(sec);
  }

  // Development headroom ------------------------------------------------------
  // Own-club only: how current ability compares with the peak forecast and
  // which way it is trending. The forecast may be missed or exceeded.
  const dev = data.dev_progress;
  if (dev && dev.length) {
    const sec = pfSection("Development");
    const list = el("div", "pf-dev");
    for (const d of dev) {
      const arrow = d.overperforming ? "★" : d.maxed ? "◆" : d.trajectory === "climbing" ? "▲"
        : d.trajectory === "declining" ? "▼" : "—";
      const acls = d.overperforming ? "trend-up" : d.maxed ? "trend-flat" : d.trajectory === "climbing" ? "trend-up"
        : d.trajectory === "declining" ? "trend-down" : "muted";
      const row = el("div", "pf-dev-row");
      const ceilTxt = d.potential_band
        ? `${d.potential_band[0]}–${d.potential_band[1]}` : d.potential;
      const teach = d.mentor_skill >= 55 ? ` · <span title="strong mentor — worth pairing with a prospect">🎓${d.mentor_skill}</span>` : "";
      const above = d.overperforming ? ` · <span class="trend-up">above original projection</span>` : "";
      const support = d.support_bonus > 0 ? ` · support +${d.support_bonus.toFixed(1)}` : "";
      row.innerHTML =
        `<span class="plink pf-dev-name" data-pid="${d.id}">${d.handle}</span>` +
        `<span class="muted pf-dev-meta" title="${esc(d.curve_read)}">${d.age}y · CA ${d.ca} · peak ${ceilTxt}${above}${support}${teach}</span>` +
        `<span class="pf-dev-bar"><span class="pf-dev-fill" style="width:${d.progress_pct}%"></span></span>` +
        `<span class="mono ${acls}">${d.progress_pct}% ${arrow}</span>`;
      list.appendChild(row);
    }
    sec.appendChild(list);
    frag.appendChild(sec);
  }

  // Squad strength profile -----------------------------------------------------
  // Aim / tactical / mentals / teamplay, from the dressed five's attributes.
  // Own club shows exact means; a scouted rival shows the band only.
  const strength = data.strength;
  if (strength && strength.length) {
    const sec = pfSection("Squad strength");
    const list = el("div", "pf-str");
    for (const a of strength) {
      const w = a.value != null ? a.value : { elite: 92, strong: 78, solid: 62, average: 48, weak: 32 }[a.band] || 50;
      list.appendChild(el("div", "pf-str-row",
        `<span class="pf-str-lab">${a.label}</span>` +
        `<span class="pf-str-bar"><span class="pf-str-fill" style="width:${w}%"></span></span>` +
        `<span class="mono ${a.value == null ? "muted" : ""}">${a.value != null ? a.value : a.band}</span>`));
    }
    sec.appendChild(list);
    frag.appendChild(sec);
  }

  // Agent-pool coverage (own club) --------------------------------------------
  const pool = data.agent_pool;
  if (pool && (pool.covered?.length || pool.meta_gaps?.length)) {
    const sec = pfSection("Agent pool");
    if (pool.covered.length) {
      const chips = el("div", "pf-chips");
      for (const a of pool.covered) {
        chips.appendChild(el("span", "pf-pool-chip",
          `${a.name} <span class="pf-rel-kind">${a.players}x·${a.mastery}</span>`));
      }
      sec.appendChild(chips);
    }
    if (pool.meta_gaps.length) {
      sec.appendChild(el("div", "muted pf-pool-gaps",
        "Meta gaps: " + pool.meta_gaps.map((g) => g.name).join(", ")));
    }
    frag.appendChild(sec);
  }

  // Playbook & knowledge --------------------------------------------------
  // Institutional knowledge (own org only — the server sends null for
  // rivals): methodology, per-map playbook depth, and the anti-strat books
  // that feed prep edge through a set game plan. Renders defensively —
  // only the keys that exist.
  const know = data.knowledge;
  if (know && (know.methodology != null
      || (know.playbooks || []).length || (know.antistrats || []).length)) {
    const sec = pfSection("Playbook & knowledge");
    if (know.methodology != null) {
      sec.appendChild(el("p", "pf-season-line muted",
        `Methodology <b class="mono">${pfNum(know.methodology, 1)}</b>` +
        ` — training-ground know-how that survives roster churn`));
    }
    if ((know.playbooks || []).length) {
      sec.appendChild(el("div", "pf-career-sub muted", "Map playbooks"));
      const chips = el("div", "pf-chips");
      for (const pb of know.playbooks) {
        const c = el("span", "pf-chip",
          `${esc(humanize(pb.map))}<span class="pf-rel-kind">${pfNum(pb.depth, 1)}</span>`);
        c.title = "playbook depth on this map";
        chips.appendChild(c);
      }
      sec.appendChild(chips);
    }
    if ((know.antistrats || []).length) {
      sec.appendChild(el("div", "pf-career-sub muted", "Anti-strat books"));
      const chips = el("div", "pf-chips");
      for (const a of know.antistrats) {
        const c = el("span", "pf-chip",
          `${tlink(a.team_id, a.name || a.team_id)}<span class="pf-rel-kind">${pfNum(a.depth, 1)}</span>`);
        c.title = "opponent book depth — feeds prep edge through a set game plan";
        chips.appendChild(c);
      }
      sec.appendChild(chips);
    }
    frag.appendChild(sec);
  }

  const honors = (data.honors || []).filter(Boolean);
  if (honors.length) {
    const sec = pfSection("Honours");
    for (const h of honors) sec.appendChild(el("div", "pf-honor", `★ ${h}`));
    frag.appendChild(sec);
  }

  return frag;
}

/* -- staff profile ----------------------------------------------------------- */

function renderStaffProfile(data) {
  const frag = document.createDocumentFragment();
  const m = data.member || {};

  const header = el("div", "pf-header");
  const initial = (m.name || "?").charAt(0).toUpperCase();
  const meta = [
    m.role ? `<span class="pill">${m.role}</span>` : "",
    m.specialty ? `<span class="pill" title="${m.specialty_blurb || ""}">${m.specialty}</span>` : "",
    m.age != null ? `<span class="pf-age">age ${m.age}</span>` : "",
    m.region ? `<span class="pill">${m.region}</span>` : "",
  ].filter(Boolean).join("");
  // Employer name links through to the org when the id is in the payload.
  const employ = m.employer_name
    ? `${tlink(m.employer_id, m.employer_name)}${data.is_yours ? " (your org)" : ""}`
    : "Free agent";
  header.innerHTML =
    `<span class="pf-portrait pf-portrait-blank pf-staff-initial">${initial}</span>` +
    `<div class="pf-id">` +
    `<div class="pf-handle">${m.name ?? "Unknown"}</div>` +
    `<div class="pf-meta">${meta}</div>` +
    `<div class="pf-contract muted">${employ} · ${money(m.salary)}/wk</div>` +
    `</div>`;
  frag.appendChild(header);

  const tiles = el("div", "pf-tiles");
  tiles.appendChild(pfTile("Quality", pfNum(m.quality)));
  tiles.appendChild(pfTile("Experience", `${pfNum(m.seasons_experience)}s`));
  tiles.appendChild(pfTile("Titles", pfNum((m.titles || []).length)));
  frag.appendChild(tiles);

  const eff = pfSection("What they do");
  for (const line of data.effects || []) eff.appendChild(el("div", "pf-honor", `▸ ${line}`));
  if (data.in_pool && data.hire_cost_note) {
    eff.appendChild(el("p", "muted", `Hire from the Market tab (${data.hire_cost_note}).`));
  }
  frag.appendChild(eff);

  const traits = (m.traits || []).filter(Boolean);
  if (traits.length) {
    const sec = pfSection("Style");
    const chips = el("div", "pf-chips");
    for (const t of traits) chips.appendChild(el("span", "pf-chip", t.replaceAll("_", " ")));
    sec.appendChild(chips);
    frag.appendChild(sec);
  }

  const honors = (m.titles || []).filter(Boolean);
  if (honors.length) {
    const sec = pfSection("Honours");
    for (const h of honors) sec.appendChild(el("div", "pf-honor", `★ ${h}`));
    frag.appendChild(sec);
  }

  const history = (m.history || []).filter(Boolean);
  if (history.length) {
    const sec = pfSection("Career");
    for (const h of history) sec.appendChild(el("div", "newsline", h));
    frag.appendChild(sec);
  } else {
    const sec = pfSection("Career");
    sec.appendChild(pfEmpty("No paper trail — a newcomer to the scene."));
    frag.appendChild(sec);
  }

  return frag;
}

async function openStaffProfile(sid, opts) {
  if (sid == null) return;
  const seq = pfNavTo({ kind: "staff", id: sid }, opts);
  pfShow(pfLoading());
  const data = await profileFetch(`/api/staff/${encodeURIComponent(sid)}/profile`);
  if (seq !== pfSeq || !isProfileOpen()) return; // superseded or closed
  pfShow(data ? renderStaffProfile(data) : pfUnavailable());
}

/* -- manager profile ---------------------------------------------------------
   The acting manager's career overlay, fed the /api/career payload directly
   (the dashboard's "Career ▸" button passes the object it already fetched).
   Same pf- chrome as every other profile; participates in the back-stack as
   kind:'manager' (Back re-fetches /api/career for freshness, falling back to
   the payload it was opened with). */

function renderManagerProfile(career) {
  const frag = document.createDocumentFragment();
  const c = career || {};

  // Header ------------------------------------------------------------------
  const header = el("div", "pf-header");
  const initial = (c.name || "?").charAt(0).toUpperCase();
  const meta = [
    c.archetype ? `<span class="pill">${esc(humanize(c.archetype))}</span>` : "",
    c.team_id && c.team_name
      ? tlink(c.team_id, c.team_name)
      : `<span class="pill">between clubs</span>`,
  ].filter(Boolean).join(" ");
  const conBits = [];
  const con = c.contract;
  if (con) {
    if (con.goal) {
      const st = con.goal_status && con.goal_status.state;
      conBits.push(`Board goal: ${esc(con.goal)}` +
        (st ? ` (${esc(String(st).replace(/_/g, " "))})` : ""));
    }
    if (con.patience != null) conBits.push(`patience ${pfNum(con.patience)}`);
    if (con.seasons != null && con.start_season != null) {
      conBits.push(`S${con.start_season}–S${con.start_season + con.seasons - 1}`);
    }
  }
  header.innerHTML =
    `<span class="pf-portrait pf-portrait-blank pf-staff-initial">${initial}</span>` +
    `<div class="pf-id">` +
    `<div class="pf-handle">${esc(c.name ?? "Manager")}</div>` +
    `<div class="pf-meta">${meta}</div>` +
    `<div class="pf-contract muted">${conBits.length ? conBits.join(" · ") : "No active contract"}</div>` +
    `</div>`;
  frag.appendChild(header);

  // Chronicle counts ----------------------------------------------------------
  const tiles = el("div", "pf-tiles");
  tiles.appendChild(pfTile("Titles", pfNum((c.titles || []).length)));
  tiles.appendChild(pfTile("Developed", pfNum(c.players_developed)));
  tiles.appendChild(pfTile("Debuts", pfNum(c.debuts_given)));
  tiles.appendChild(pfTile("Signings", pfNum(c.signings)));
  frag.appendChild(tiles);

  // Reputation axes — the numbers that gate career offers.
  const rep = c.reputation || {};
  if (Object.keys(rep).length) {
    const sec = pfSection("Reputation");
    const list = el("div", "pf-attrs");
    for (const [axis, val] of Object.entries(rep)) {
      list.appendChild(el("div", "pf-attr",
        `<span class="pf-attr-label">${esc(humanize(axis))}</span>` +
        `<span class="pf-attr-bar">${pfBar(val, 100)}</span>` +
        `<span class="pf-attr-val mono">${pfNum(val)}</span>`));
    }
    sec.appendChild(list);
    frag.appendChild(sec);
  }

  // Known for / Philosophy — earned identities, chips like traits.
  const chipRow = (title, items) => {
    const vals = (items || []).map((x) => x && (x.name || x)).filter(Boolean);
    if (!vals.length) return;
    const sec = pfSection(title);
    const chips = el("div", "pf-chips");
    for (const v of vals) chips.appendChild(el("span", "pf-chip", esc(String(v))));
    sec.appendChild(chips);
    frag.appendChild(sec);
  };
  chipRow("Known for", c.known_for);
  chipRow("Philosophy", c.philosophies);

  // Honours -------------------------------------------------------------
  const titles = (c.titles || []).filter(Boolean);
  if (titles.length) {
    const sec = pfSection(`Honours (${titles.length})`);
    for (const h of titles) sec.appendChild(el("div", "pf-honor", `★ ${esc(h)}`));
    frag.appendChild(sec);
  }

  // Timeline — landmark chronicle entries, newest first, scrollable.
  const timeline = (c.timeline || []).slice().reverse();
  const sec = pfSection("Timeline");
  if (timeline.length) {
    const wrap = el("div", "card-scroll");
    wrap.style.setProperty("--scroll-max", "40vh");
    for (const e of timeline) {
      wrap.appendChild(el("div", `newsline pf-tl-${e.kind || "event"}`,
        `<span class="mono muted">S${e.season}·W${e.week}</span> ${esc(e.text)}`));
    }
    sec.appendChild(wrap);
  } else {
    sec.appendChild(pfEmpty("No landmark moments yet — the chronicle is waiting."));
  }
  frag.appendChild(sec);

  return frag;
}

window.openManagerProfile = (career, opts) => {
  if (!career) return;
  // Bumps pfSeq even though the render is synchronous, so any in-flight
  // fetch from an earlier open drops instead of clobbering this view.
  pfNavTo({ kind: "manager", id: career.id || "me", career }, opts);
  pfShow(renderManagerProfile(career));
};

// Back-stack re-entry: refetch for freshness, degrade to the stored payload.
async function pfReopenManager(entry) {
  const seq = pfNavTo(entry, { replace: true });
  pfShow(pfLoading());
  const data = await profileFetch("/api/career");
  if (seq !== pfSeq || !isProfileOpen()) return;
  const payload = data || entry.career;
  pfShow(payload ? renderManagerProfile(payload) : pfUnavailable());
}

/* -- overlay plumbing ------------------------------------------------------- */

let pfOverlayEl = null;

/* Back-stack + stale-response guard.
   pfSeq is a monotonically increasing open token: every open (or reopen)
   captures `const seq = ++pfSeq` BEFORE its fetch and only renders when
   `seq === pfSeq && isProfileOpen()` still holds — a newer open or a close
   invalidates it, so rapid clicks can't race a stale profile onto screen.
   pfStack holds the {kind, id} entries beneath the current view: opening a
   profile from INSIDE the overlay pushes the one being replaced; "← Back"
   pops and re-opens in replace mode (no push). closeProfile() clears the
   stack — the single choke point. Escape still closes the whole overlay. */
let pfSeq = 0;
const pfStack = [];
let pfCurrent = null; // {kind, id[, career]} currently showing (or loading)

function pfNavTo(entry, opts) {
  const replace = !!(opts && opts.replace);
  const same = pfCurrent && pfCurrent.kind === entry.kind
    && String(pfCurrent.id) === String(entry.id);
  // Push only when a DIFFERENT profile is already showing (a refresh of the
  // same entry — admin save, rein-in-streaming — must not stack on itself).
  if (!replace && !same && isProfileOpen() && pfCurrent) pfStack.push(pfCurrent);
  pfCurrent = entry;
  return ++pfSeq;
}

function pfGoBack() {
  const prev = pfStack.pop();
  if (!prev) return;
  if (prev.kind === "player") openPlayerProfile(prev.id, { replace: true });
  else if (prev.kind === "team") openTeamProfile(prev.id, { replace: true });
  else if (prev.kind === "staff") openStaffProfile(prev.id, { replace: true });
  else if (prev.kind === "manager") pfReopenManager(prev);
}

function pfEnsureOverlay() {
  if (pfOverlayEl) return pfOverlayEl;
  const ov = document.createElement("div");
  ov.id = "profile";
  ov.className = "overlay hidden";
  ov.innerHTML =
    `<div class="panel pf-panel">` +
    `<button class="pf-back btn btn-sm hidden" aria-label="Back to previous profile">← Back</button>` +
    `<button class="pf-close" aria-label="Close profile">✕</button>` +
    `<div id="profile-body" class="pf-body"></div>` +
    `</div>`;
  // Click-outside closes; clicks inside the panel do not reach here.
  ov.addEventListener("click", (e) => { if (e.target === ov) closeProfile(); });
  ov.querySelector(".pf-close").addEventListener("click", closeProfile);
  ov.querySelector(".pf-back").addEventListener("click", pfGoBack);
  document.body.appendChild(ov);
  pfOverlayEl = ov;
  return ov;
}

function pfShow(node) {
  const ov = pfEnsureOverlay();
  const body = ov.querySelector("#profile-body");
  body.replaceChildren(node);
  // The Back affordance tracks the stack on every render (incl. loading).
  ov.querySelector(".pf-back").classList.toggle("hidden", !pfStack.length);
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
  // Single choke point: closing the overlay resets navigation entirely and
  // invalidates any profile fetch still in flight.
  pfStack.length = 0;
  pfCurrent = null;
  pfSeq++;
  if (pfOverlayEl) {
    pfOverlayEl.classList.add("hidden");
    pfOverlayEl.querySelector(".pf-back").classList.add("hidden");
  }
}

function isProfileOpen() {
  return !!pfOverlayEl && !pfOverlayEl.classList.contains("hidden");
}

/* -- public entry points ---------------------------------------------------- */

async function openPlayerProfile(pid, opts) {
  if (pid == null) return;
  const seq = pfNavTo({ kind: "player", id: pid }, opts);
  pfShow(pfLoading());
  const data = await profileFetch(`/api/players/${encodeURIComponent(pid)}/profile`);
  if (seq !== pfSeq || !isProfileOpen()) return; // superseded or closed mid-flight
  pfShow(data ? renderPlayerProfile(data) : pfUnavailable());
}

async function openTeamProfile(tid, opts) {
  if (tid == null) return;
  const seq = pfNavTo({ kind: "team", id: tid }, opts);
  pfShow(pfLoading());
  const data = await profileFetch(`/api/teams/${encodeURIComponent(tid)}/profile`);
  if (seq !== pfSeq || !isProfileOpen()) return;
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
  const sl = node.closest("[data-sid]");
  if (sl) {
    e.stopPropagation();
    e.preventDefault();
    openStaffProfile(sl.getAttribute("data-sid"));
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

/* -- admin data-correction toggle -------------------------------------------
   Purely a client-side UI reveal (localStorage-persisted, per browser): it
   shows a "Correct data" control on player/team profiles that opens a small
   form hitting /api/admin/{player,team}/{id}. The server independently
   re-validates that the target is actually roster-pack-sourced (a generated
   fill player/team just 404s as not editable), so this toggle is a
   convenience, not a security boundary. */
const PF_ADMIN_KEY = "esports_admin_mode";
const PF_ROLES = ["duelist", "controller", "initiator", "sentinel", "flex"];
const PF_PLAYSTYLES = ["igl", "entry", "anchor", "lurker", "awper", "support"];

function isAdminMode() {
  return document.body.classList.contains("admin-mode");
}

(function pfAdminInit() {
  const btn = document.getElementById("admin-toggle");
  if (!btn) return;
  const on = localStorage.getItem(PF_ADMIN_KEY) === "1";
  document.body.classList.toggle("admin-mode", on);
  btn.setAttribute("aria-pressed", String(on));
  btn.classList.toggle("btn-primary", on);
  btn.onclick = () => {
    const next = !isAdminMode();
    document.body.classList.toggle("admin-mode", next);
    btn.setAttribute("aria-pressed", String(next));
    btn.classList.toggle("btn-primary", next);
    localStorage.setItem(PF_ADMIN_KEY, next ? "1" : "0");
    toast(next ? "Admin edit mode on — profiles show a data-correction control." : "Admin edit mode off.");
    if (isProfileOpen()) closeProfile(); // through the choke point: clears the back-stack too
  };
})();

function pfAdminOption(v) {
  return `<option value="${v}">${v}</option>`;
}

function pfAdminField(name, label, value, type) {
  const safe = value == null ? "" : String(value).replace(/"/g, "&quot;");
  return `<label class="pf-admin-field"><span>${label}</span><input name="${name}" type="${type || "text"}" value="${safe}"></label>`;
}

// Fetches admin-editability for a player/team, then swaps `slot`'s content
// for the correction form (or a quiet "not editable" line).
async function pfOpenAdminEdit(kind, id, slot) {
  slot.innerHTML = `<p class="muted">Checking roster-pack sheet…</p>`;
  const url = kind === "player"
    ? `/api/admin/player/${encodeURIComponent(id)}`
    : `/api/admin/team/${encodeURIComponent(id)}`;
  const info = await profileFetch(url);
  if (!info || !info.editable) {
    slot.innerHTML = `<p class="muted">${(info && info.reason) || "Not editable — no roster-pack sheet for this entry."}</p>`;
    return;
  }
  slot.replaceChildren(
    kind === "player"
      ? pfPlayerAdminForm(id, info.fields, slot)
      : pfTeamAdminForm(id, info.fields, info.note, slot)
  );
}

function pfAdminBox(note) {
  const box = el("div", "pf-admin-box");
  box.innerHTML =
    `<div class="pf-admin-title">Correct roster-pack data</div>` +
    `<p class="muted pf-admin-note">Writes to the pack's src sheet and rebuilds it. ` +
    `Campaign-managed fields (salary, contract, morale, form, finances) are left alone.` +
    (note ? ` ${note}` : "") + `</p>`;
  return box;
}

function pfPlayerAdminForm(pid, f, slot) {
  const box = pfAdminBox();
  const form = el("form", "pf-admin-form");
  form.innerHTML =
    pfAdminField("handle", "Handle", f.handle) +
    pfAdminField("real_name", "Real name", f.real_name) +
    pfAdminField("age", "Age", f.age, "number") +
    pfAdminField("country", "Country code", f.country) +
    pfAdminField("quality", "Quality (1-99)", f.quality, "number") +
    `<label class="pf-admin-field"><span>Role</span><select name="role">${PF_ROLES.map((r) => `<option value="${r}"${r === f.role ? " selected" : ""}>${r}</option>`).join("")}</select></label>` +
    `<label class="pf-admin-field"><span>Playstyle</span><select name="playstyle">${PF_PLAYSTYLES.map((s) => `<option value="${s}"${s === f.playstyle ? " selected" : ""}>${s}</option>`).join("")}</select></label>` +
    pfAdminField("agents", "Agents (comma-separated ids)", (f.agents || []).join(",")) +
    `<div class="pf-admin-actions"><button type="submit" class="btn btn-sm btn-primary">Save correction</button><button type="button" class="btn btn-sm pf-admin-cancel">Cancel</button></div>`;
  form.querySelector(".pf-admin-cancel").onclick = () => { slot.innerHTML = ""; };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const agentsRaw = String(fd.get("agents") || "").trim();
    const body = {
      handle: fd.get("handle") || undefined,
      real_name: fd.get("real_name"),
      age: fd.get("age") ? parseInt(fd.get("age"), 10) : undefined,
      country: fd.get("country"),
      quality: fd.get("quality") ? parseFloat(fd.get("quality")) : undefined,
      role: fd.get("role"),
      playstyle: fd.get("playstyle"),
      agents: agentsRaw ? agentsRaw.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
    };
    try {
      const r = await api(`/api/admin/player/${encodeURIComponent(pid)}`, body);
      toast(r.message || "Corrected.");
      openPlayerProfile(pid);
    } catch { /* api() already toasted the error */ }
  };
  box.appendChild(form);
  return box;
}

function pfTeamAdminForm(tid, f, note, slot) {
  const box = pfAdminBox(note);
  const form = el("form", "pf-admin-form");
  form.innerHTML =
    pfAdminField("name", "Team name", f.name) +
    pfAdminField("tag", "Tag", f.tag) +
    `<label class="pf-admin-field"><span>Tier</span><select name="tier"><option value="1"${f.tier === 1 ? " selected" : ""}>1 — franchised</option><option value="2"${f.tier === 2 ? " selected" : ""}>2 — challengers</option></select></label>` +
    pfAdminField("prestige", "Prestige (1-99)", f.prestige, "number") +
    `<div class="pf-admin-actions"><button type="submit" class="btn btn-sm btn-primary">Save correction</button><button type="button" class="btn btn-sm pf-admin-cancel">Cancel</button></div>`;
  form.querySelector(".pf-admin-cancel").onclick = () => { slot.innerHTML = ""; };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      name: fd.get("name") || undefined,
      tag: fd.get("tag") || undefined,
      tier: fd.get("tier") ? parseInt(fd.get("tier"), 10) : undefined,
      prestige: fd.get("prestige") ? parseFloat(fd.get("prestige")) : undefined,
    };
    try {
      const r = await api(`/api/admin/team/${encodeURIComponent(tid)}`, body);
      toast(r.message || "Corrected.");
      openTeamProfile(tid);
    } catch { /* api() already toasted the error */ }
  };
  box.appendChild(form);
  return box;
}
