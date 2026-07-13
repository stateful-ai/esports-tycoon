import { h, render } from 'https://esm.sh/preact@10.19.2';
import { useState, useEffect, useMemo, useRef } from 'https://esm.sh/preact@10.19.2/hooks';
import htm from 'https://esm.sh/htm@3.1.1';

const html = htm.bind(h);

/* Player & team profile screens — modal overlays over the campaign hub.
   Pure API consumer, like every other screen: the UI holds NO sim state.
   The overlay renders whatever the profile endpoints return and degrades
   gracefully when a section is empty or the endpoint is absent. */

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

function pfNum(v, digits = 0) {
  if (v == null || (typeof v === "number" && isNaN(v))) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  return digits ? n.toFixed(digits) : String(Math.round(n));
}

function pfStars(v) {
  if (v == null || isNaN(v)) return "";
  const full = Math.floor(v);
  return "★".repeat(full) + (v % 1 >= 0.5 ? "½" : "");
}

function pfPct(v) {
  if (v == null || isNaN(v)) return null;
  const n = Number(v);
  return Math.round(n <= 1 ? n * 100 : n);
}

const pfWk = (w) => `S${w.season}·W${w.week}`;

/* -- Preact Sub-components -------------------------------------------------- */

const PfBar = ({ value, max = 100 }) => {
  const w = Math.max(2, Math.min(100, (Number(value) / max) * 100));
  return html`<span class="pf-hbar"><i style=${{ '--target-width': `${w}%` }}></i></span>`;
};

const ProfileLoading = () => html`<div class="pf-loading muted">Loading profile…</div>`;

const Unavailable = () => html`
  <div class="pf-unavailable">
    <div class="pf-unavailable-mark">◌</div>
    <p class="pf-unavailable-title">Profile unavailable</p>
    <p class="muted">This profile can't be loaded right now.</p>
  </div>
`;

const AcsSparkline = ({ weekly }) => {
  const pts = useMemo(() => (weekly || []).filter((w) => w && w.acs != null && !isNaN(w.acs)), [weekly]);
  if (!pts.length) return null;
  const W = 280, H = 64, ml = 6, mr = 6, mt = 12, mb = 10;
  const pw = W - ml - mr, ph = H - mt - mb;
  const vals = useMemo(() => pts.map((w) => +w.acs), [pts]);
  let mn = Math.min(...vals), mx = Math.max(...vals);
  if (mn === mx) { mn -= 1; mx += 1; }
  const x = (i) => (pts.length === 1 ? ml + pw / 2 : ml + (i / (pts.length - 1)) * pw);
  const y = (v) => mt + ph - ((v - mn) / (mx - mn)) * ph;
  const coords = pts.map((w, i) => [x(i), y(+w.acs)]);
  const polyPoints = coords.map((c) => `${c[0].toFixed(1)},${c[1].toFixed(1)}`).join(" ");

  return html`
    <svg class="pf-chart pf-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="ACS by week">
      ${pts.length > 1 ? html`<polyline class="pf-spark-line" points=${polyPoints} />` : null}
      ${coords.map((c, i) => html`
        <circle key=${i} class="pf-spark-dot" cx=${c[0].toFixed(1)} cy=${c[1].toFixed(1)} r="2.6">
          <title>${pfWk(pts[i])}: ${Math.round(pts[i].acs)} ACS</title>
        </circle>
      `)}
      <text class="pf-axis" x=${ml} y=${mt - 3}>${Math.round(mx)}</text>
      <text class="pf-axis" x=${ml} y=${H - 2}>${Math.round(mn)}</text>
    </svg>
  `;
};

const KdMirrorBars = ({ weekly }) => {
  const pts = useMemo(() => (weekly || []).filter((w) => w && (w.kills != null || w.deaths != null)), [weekly]);
  if (!pts.length) return null;
  const W = 280, H = 88, mt = 6, mb = 6, ml = 6, mr = 6;
  const pw = W - ml - mr;
  const half = (H - mt - mb) / 2;
  const cy = mt + half;
  const mx = Math.max(1, ...pts.map((w) => Math.max(w.kills || 0, w.deaths || 0)));
  const slot = pw / pts.length;
  const bw = Math.min(18, slot * 0.6);

  return html`
    <svg class="pf-chart pf-mirror" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Kills and deaths by week">
      <line class="pf-bar-axis" x1=${ml} y1=${cy} x2=${W - mr} y2=${cy} />
      ${pts.map((w, i) => {
        const cx = ml + slot * i + slot / 2;
        const kh = ((w.kills || 0) / mx) * half;
        const dh = ((w.deaths || 0) / mx) * half;
        return html`
          <g key=${i}>
            <rect class="pf-bar-k" x=${(cx - bw / 2).toFixed(1)} y=${(cy - kh).toFixed(1)} width=${bw.toFixed(1)} height=${kh.toFixed(1)} rx="0.8">
              <title>${pfWk(w)}: ${w.kills || 0} kills</title>
            </rect>
            <rect class="pf-bar-d" x=${(cx - bw / 2).toFixed(1)} y=${cy.toFixed(1)} width=${bw.toFixed(1)} height=${dh.toFixed(1)} rx="0.8">
              <title>${pfWk(w)}: ${w.deaths || 0} deaths</title>
            </rect>
          </g>
        `;
      })}
    </svg>
  `;
};

const MetricLine = ({ series, getValue, formatValue, ariaLabel }) => {
  const pts = useMemo(() => (series || []).filter((w) => w && getValue(w) != null && !isNaN(getValue(w))), [series, getValue]);
  if (!pts.length) return null;
  const W = 280, H = 64, ml = 6, mr = 6, mt = 12, mb = 10;
  const pw = W - ml - mr, ph = H - mt - mb;
  const vals = useMemo(() => pts.map(getValue).map(Number), [pts, getValue]);
  let mn = Math.min(...vals), mx = Math.max(...vals);
  if (mn === mx) { mn -= 1; mx += 1; }
  const x = (i) => (pts.length === 1 ? ml + pw / 2 : ml + (i / (pts.length - 1)) * pw);
  const y = (v) => mt + ph - ((v - mn) / (mx - mn)) * ph;
  const coords = vals.map((v, i) => [x(i), y(v)]);
  const polyPoints = coords.map((c) => `${c[0].toFixed(1)},${c[1].toFixed(1)}`).join(" ");

  return html`
    <svg class="pf-chart pf-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label=${ariaLabel}>
      ${pts.length > 1 ? html`<polyline class="pf-spark-line" points=${polyPoints} />` : null}
      ${coords.map((c, i) => html`
        <circle key=${i} class="pf-spark-dot" cx=${c[0].toFixed(1)} cy=${c[1].toFixed(1)} r="2.6">
          <title>${pfWk(pts[i])}: ${formatValue(vals[i])}</title>
        </circle>
      `)}
      <text class="pf-axis" x=${ml} y=${mt - 3}>${formatValue(mx)}</text>
      <text class="pf-axis" x=${ml} y=${H - 2}>${formatValue(mn)}</text>
    </svg>
  `;
};

const DevChart = ({ series }) => {
  const pts = useMemo(() => (series || []).filter((w) => w && w.ca != null), [series]);
  if (!pts.length) return null;
  const W = 280, H = 88, ml = 6, mr = 6, mt = 12, mb = 10;
  const pw = W - ml - mr, ph = H - mt - mb;
  const caVals = useMemo(() => pts.map((w) => +w.ca), [pts]);
  const cfVals = useMemo(() => pts.map((w) => +(w.confidence ?? 50)), [pts]);
  let mn = Math.min(...caVals, ...cfVals), mx = Math.max(...caVals, ...cfVals);
  if (mx - mn < 4) { mn -= 2; mx += 2; }
  const x = (i) => (pts.length === 1 ? ml + pw / 2 : ml + (i / (pts.length - 1)) * pw);
  const y = (v) => mt + ph - ((v - mn) / (mx - mn)) * ph;

  const polyCA = pts.length > 1 ? caVals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ") : null;
  const polyCF = pts.length > 1 ? cfVals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ") : null;

  return html`
    <svg class="pf-chart pf-dev" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Ability and confidence over time">
      ${pts.length > 1 ? html`
        <polyline class="pf-spark-line" points=${polyCA} />
        <polyline class="pf-spark-line pf-line-alt" points=${polyCF} />
      ` : html`
        <circle class="pf-spark-dot" cx=${x(0)} cy=${y(caVals[0])} r="2.6" />
      `}
      ${pts.map((w, i) => html`
        <circle key=${i} class="pf-spark-dot" cx=${x(i).toFixed(1)} cy=${y(caVals[i]).toFixed(1)} r="2.4">
          <title>${pfWk(w)}: CA ${caVals[i].toFixed(1)} / conf ${Math.round(cfVals[i])}</title>
        </circle>
      `)}
      <text class="pf-axis" x=${ml} y=${mt - 3}>${Math.round(mx)}</text>
      <text class="pf-axis" x=${ml} y=${H - 2}>${Math.round(mn)}</text>
    </svg>
  `;
};

const TeammateCompare = ({ playerId, teamId, attributes }) => {
  const [teammates, setTeammates] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [comparison, setComparison] = useState(null);

  useEffect(() => {
    if (teamId) {
      api(`/api/roster/${teamId}`)
        .then((rd) => {
          setTeammates((rd.players || []).filter((q) => q.id !== playerId));
        })
        .catch(() => {});
    }
  }, [teamId, playerId]);

  useEffect(() => {
    if (!selectedId) {
      setComparison(null);
      return;
    }
    api(`/api/compare?a=${playerId}&b=${selectedId}`)
      .then((c) => setComparison(c))
      .catch(() => setComparison(null));
  }, [selectedId, playerId]);

  const better = (x, y) => x != null && y != null && x > y;

  return html`
    <div class="pf-section">
      <h3 class="pf-section-title">Compare</h3>
      <select class="pf-compare-sel" value=${selectedId} onChange=${(e) => setSelectedId(e.target.value)}>
        <option value="">compare with a teammate…</option>
        ${teammates.map((t) => html`<option key=${t.id} value=${t.id}>${t.handle}</option>`)}
      </select>
      <div class="pf-compare">
        ${comparison && html`
          <table class="pf-table cmp">
            <thead>
              <tr>
                <th class="num">${comparison.a.handle}</th>
                <th></th>
                <th class="num">${comparison.b.handle}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class=${`num ${better(comparison.a.overall, comparison.b.overall) ? 'cmp-win' : ''}`}>${comparison.a.overall ?? '—'}</td>
                <th>Overall</th>
                <td class=${`num ${better(comparison.b.overall, comparison.a.overall) ? 'cmp-win' : ''}`}>${comparison.b.overall ?? '—'}</td>
              </tr>
              <tr>
                <td class=${`num ${better(comparison.a.rating, comparison.b.rating) ? 'cmp-win' : ''}`}>${comparison.a.rating ?? '—'}</td>
                <th>Rating</th>
                <td class=${`num ${better(comparison.b.rating, comparison.a.rating) ? 'cmp-win' : ''}`}>${comparison.b.rating ?? '—'}</td>
              </tr>
              <tr>
                <td class=${`num ${better(comparison.a.kd, comparison.b.kd) ? 'cmp-win' : ''}`}>${comparison.a.kd ?? '—'}</td>
                <th>K/D</th>
                <td class=${`num ${better(comparison.b.kd, comparison.a.kd) ? 'cmp-win' : ''}`}>${comparison.b.kd ?? '—'}</td>
              </tr>
              ${(comparison.a.attributes || []).map((a) => {
                const b = (comparison.b.attributes || []).find((x) => x.key === a.key);
                return html`
                  <tr key=${a.key}>
                    <td class=${`num ${better(a.value, b?.value) ? 'cmp-win' : ''}`}>${a.value ?? '—'}</td>
                    <th>${a.label}</th>
                    <td class=${`num ${better(b?.value, a.value) ? 'cmp-win' : ''}`}>${b?.value ?? '—'}</td>
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

const FloatingBadge = ({ text }) => {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => {
      setVisible(false);
    }, 1600);
    return () => clearTimeout(t);
  }, []);

  if (!visible) return null;

  return html`
    <div class="floating-badge fade-out-badge" style=${{ 
      position: "absolute", 
      top: "40%", 
      left: "50%", 
      transform: "translate(-50%, -50%)", 
      backgroundColor: "var(--es-color-accent-warm, #ffb000)", 
      color: "#000", 
      padding: "12px 24px", 
      borderRadius: "6px", 
      fontWeight: "bold", 
      fontSize: "1.2em", 
      boxShadow: "0 8px 24px rgba(0,0,0,0.6)", 
      zIndex: 10000 
    }}>
      ${text}
    </div>
  `;
};


const AdminSlot = ({ kind, id, onDone }) => {
  const [loading, setLoading] = useState(true);
  const [editable, setEditable] = useState(false);
  const [fields, setFields] = useState(null);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    profileFetch(`/api/admin/${kind}/${encodeURIComponent(id)}`)
      .then((info) => {
        setLoading(false);
        if (info && info.editable) {
          setEditable(true);
          setFields(info.fields);
          setNote(info.note || "");
        } else {
          setReason((info && info.reason) || "Not editable — no roster-pack sheet for this entry.");
        }
      })
      .catch(() => {
        setLoading(false);
        setReason("Not editable — check API.");
      });
  }, [kind, id]);

  if (loading) return html`<p class="muted">Checking roster-pack sheet…</p>`;
  if (!editable) return html`<p class="muted">${reason}</p>`;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    let body = {};
    if (kind === 'player') {
      const agentsRaw = String(fd.get("agents") || "").trim();
      body = {
        handle: fd.get("handle") || undefined,
        real_name: fd.get("real_name"),
        age: fd.get("age") ? parseInt(fd.get("age"), 10) : undefined,
        country: fd.get("country"),
        quality: fd.get("quality") ? parseFloat(fd.get("quality")) : undefined,
        role: fd.get("role"),
        playstyle: fd.get("playstyle"),
        agents: agentsRaw ? agentsRaw.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
      };
    } else {
      body = {
        name: fd.get("name") || undefined,
        tag: fd.get("tag") || undefined,
        tier: fd.get("tier") ? parseInt(fd.get("tier"), 10) : undefined,
        prestige: fd.get("prestige") ? parseFloat(fd.get("prestige")) : undefined,
      };
    }

    try {
      const r = await api(`/api/admin/${kind}/${encodeURIComponent(id)}`, body);
      toast(r.message || "Corrected.");
      onDone();
    } catch {}
  };

  return html`
    <div class="pf-admin-box">
      <div class="pf-admin-title">Correct roster-pack data</div>
      <p class="muted pf-admin-note">
        Writes to the pack's src sheet and rebuilds it. Campaign-managed fields (salary, contract, morale, form, finances) are left alone.
        ${note ? ` ${note}` : ""}
      </p>
      <form class="pf-admin-form" onSubmit=${handleSubmit}>
        ${kind === 'player' ? html`
          <label class="pf-admin-field"><span>Handle</span><input name="handle" type="text" value=${fields.handle || ""} /></label>
          <label class="pf-admin-field"><span>Real name</span><input name="real_name" type="text" value=${fields.real_name || ""} /></label>
          <label class="pf-admin-field"><span>Age</span><input name="age" type="number" value=${fields.age || ""} /></label>
          <label class="pf-admin-field"><span>Country code</span><input name="country" type="text" value=${fields.country || ""} /></label>
          <label class="pf-admin-field"><span>Quality (1-99)</span><input name="quality" type="number" step="any" value=${fields.quality || ""} /></label>
          <label class="pf-admin-field">
            <span>Role</span>
            <select name="role">
              ${PF_ROLES.map((r) => html`<option key=${r} value=${r} selected=${r === fields.role}>${r}</option>`)}
            </select>
          </label>
          <label class="pf-admin-field">
            <span>Playstyle</span>
            <select name="playstyle">
              ${PF_PLAYSTYLES.map((s) => html`<option key=${s} value=${s} selected=${s === fields.playstyle}>${s}</option>`)}
            </select>
          </label>
          <label class="pf-admin-field"><span>Agents (comma-separated ids)</span><input name="agents" type="text" value=${(fields.agents || []).join(",")} /></label>
        ` : html`
          <label class="pf-admin-field"><span>Team name</span><input name="name" type="text" value=${fields.name || ""} /></label>
          <label class="pf-admin-field"><span>Tag</span><input name="tag" type="text" value=${fields.tag || ""} /></label>
          <label class="pf-admin-field">
            <span>Tier</span>
            <select name="tier">
              <option value="1" selected=${fields.tier === 1}>1 — franchised</option>
              <option value="2" selected=${fields.tier === 2}>2 — challengers</option>
            </select>
          </label>
          <label class="pf-admin-field"><span>Prestige (1-99)</span><input name="prestige" type="number" step="any" value=${fields.prestige || ""} /></label>
        `}
        <div class="pf-admin-actions">
          <button type="submit" class="btn btn-sm btn-primary">Save correction</button>
          <button type="button" class="btn btn-sm" onClick=${onDone}>Cancel</button>
        </div>
      </form>
    </div>
  `;
};

/* -- Main Profiles ---------------------------------------------------------- */

const PlayerProfile = ({ data }) => {
  const p = data.player || {};
  const ov = data.overview || {};
  const [showAdminEdit, setShowAdminEdit] = useState(false);

  const portrait = p.portrait
    ? html`<img class="pf-portrait" src=${p.portrait} alt="" onError=${(e) => { e.target.style.visibility = 'hidden'; }} />`
    : html`<span class="pf-portrait pf-portrait-blank"></span>`;

  const teamBit = !p.is_free_agent && p.team_id
    ? html`
        <span class="pf-team tlink" data-tid=${p.team_id} title="View team">
          ${p.team_logo && html`<img class="pf-team-logo" src=${p.team_logo} alt="" onError=${(e) => { e.target.style.display = 'none'; }} />`}
          <span>${p.team_name ?? "—"}</span>
        </span>`
    : html`<span class="pill">free agent</span>`;

  const langBit = (p.languages || [])
    .map((l) => `${(l.lang || "").toUpperCase()} ${l.level}`)
    .join(" · ");

  const hierarchyLabel = (p.hierarchy_role || "core").replace(/_/g, " ");
  let hierarchyColor = "var(--es-color-muted, #808080)";
  if (["incumbent_leader", "council_member"].includes(p.hierarchy_role)) {
    hierarchyColor = "var(--es-color-accent, #00f0ff)";
  } else if (["volatile_rebel", "outcast"].includes(p.hierarchy_role)) {
    hierarchyColor = "var(--es-color-danger, #ff4655)";
  } else if (["key_influencer", "loyal_lieutenant"].includes(p.hierarchy_role)) {
    hierarchyColor = "var(--es-color-accent-warm, #ffb000)";
  }

  const hierarchyBadge = html`
    <span class="pill" style=${{
      border: `1px solid ${hierarchyColor}`,
      color: hierarchyColor,
      textTransform: "uppercase",
      fontSize: "0.75em",
      marginLeft: "8px",
      verticalAlign: "middle"
    }}>${hierarchyLabel}</span>
  `;

  const contract = p.is_free_agent
    ? "Free agent — unsigned"
    : `${ov.contract_weeks != null ? ov.contract_weeks + "w left" : "—"} · ${money(ov.salary)}/wk`;

  const contractDetail = ov.contract_terms;
  const contractTerms = (!p.is_free_agent && contractDetail)
    ? `${contractDetail.stream_share}% streams · ${money(contractDetail.release_fee)} release · ` +
      `${contractDetail.buyout ? money(contractDetail.buyout) + " buyout" : "no buyout"} · ${contractDetail.roster_role}` +
      `${contractDetail.no_transfer ? " · no-transfer" : ""}`
    : "";

  const handleMakeOffer = () => {
    closeProfile();
    openOffer({ id: p.id, handle: p.handle, ask: p.transfer_ask, team_name: p.team_name });
  };

  const handleReinStreaming = async () => {
    const confirmed = confirm(
      `Rein in ${p.handle}'s streaming? This spends your only 1:1 for the week, ` +
      "reduces their streaming revenue, and may lower their morale. In return, " +
      "they will spend more time practicing and develop faster."
    );
    if (!confirmed) return;
    try {
      await api("/api/actions/rein_streaming", { player_id: p.id });
      openPlayerProfile(p.id, { replace: true });
    } catch {}
  };

  const handleScout = async () => {
    const r = await api("/api/actions/scout", { player_id: p.id });
    toast(r.message);
    openPlayerProfile(p.id, { replace: true });
  };

  const ovrSub = ov.fogged ? "scouted" : pfStars(ov.ovr_stars);
  const caBand = ov.current_ability_band;
  const potIsNum = typeof ov.potential === "number";
  const potBand = ov.potential_band;

  const season = data.season || {};
  const xdAct = season.xduel_actual_wins;
  const xdExp = season.xduel_expected_wins;
  const xdEdge = season.xde;
  const xdActStr = xdAct != null ? pfNum(xdAct) : "—";
  const xdExpStr = xdExp != null ? pfNum(xdExp, 1) : "—";
  const xdEdgeStr = xdEdge != null ? (xdEdge >= 0 ? "+" : "") + pfNum(xdEdge, 2) : "—";

  const scoutCtx = data.scouting || {};
  const guide = scoutCtx.guidance;
  const report = scoutCtx.report;

  const badges = data.badges || [];
  const attrs = data.attributes || [];
  const traits = (data.traits || []).filter(Boolean);
  const agents = data.agents || [];

  const [agentsExpanded, setAgentsExpanded] = useState(false);

  const pRole = (p.role || "").toLowerCase();
  const roled = pRole && pRole !== "flex";
  const primaryAgents = roled ? agents.filter((a) => (a.role || "").toLowerCase() === pRole) : agents;
  const visibleAgentIds = useMemo(() => new Set(primaryAgents.slice(0, 5).map((a) => a.agent_id)), [primaryAgents]);
  const hiddenAgentsCount = agents.length - visibleAgentIds.size;

  const splits = data.splits || {};
  const mapSplits = splits.maps || [];
  const agentSplits = splits.agents || [];

  const rels = data.relationships || [];

  const ct = data.career_totals;
  const arc = data.career_arc || [];
  const honours = data.honours || [];
  const mems = data.memories || [];
  const career = data.career || [];

  const promList = p.promises || [];

  const devSeries = (data.charts && data.charts.development) || [];
  const perf = (data.charts && data.charts.performance) || [];
  const weekly = data.weekly || [];

  return html`
    <div>
      <div class="pf-header">
        ${portrait}
        <div class="pf-id">
          <div class="pf-handle">${p.handle ?? "Unknown"}${hierarchyBadge}</div>
          ${data.epithet && html`<div class="pf-epithet">${data.epithet}</div>`}
          <div class="pf-meta">
            ${p.role && html`<span class="pill">${p.role}</span>`}
            ${p.is_igl && html`<span class="pill">IGL</span>`}
            ${ov.playstyle && html`<span class="pill">${ov.playstyle}</span>`}
            ${p.country && html`<span class="pill" title="nationality">${p.country}</span>`}
            ${langBit && html`<span class="pill" title="spoken languages (fluency)">${langBit}</span>`}
            ${p.age != null && html`<span class="pf-age">age ${p.age}</span>`}
            ${p.is_starter === false && html`<span class="pill">bench</span>`}
            ${p.followers != null && typeof fmtFollowers === "function" && html`
              <span class="pill" title="social reach">${fmtFollowers(p.followers)} followers</span>
            `}
            ${p.stream_load != null && p.stream_load > 5 && html`
              <span class="pill" title=${`org cut ${money(p.stream_income)}/wk · heavy streaming slows development to ×${p.stream_growth_mult}`}>🎥 ${p.stream_status} · ${money(p.stream_income)}/wk</span>
            `}
            ${p.mentor_id && html`
              <span class="pill" title=${`Mentored by ${p.mentor_id}`}>Mentor: ${p.mentor_id}${p.mentor_progress != null ? " (" + Math.round(p.mentor_progress) + "%)" : ""}</span>
            `}
            ${p.tenure_weeks != null && p.tenure_weeks >= 26 && html`
              <span class="pill" title="long tenure builds loyalty — affects transfer asks and renewals">${pfNum(p.tenure_weeks)}w at club</span>
            `}
            ${p.dev_focus && html`
              <span class="pill" title="development plan">${p.dev_focus} · ${p.training_intensity}</span>
            `}
            ${teamBit}
          </div>
          <div class="pf-contract muted">${contract}</div>
          ${contractTerms && html`<div class="pf-contract muted">${contractTerms}</div>`}
        </div>

        ${!p.is_free_agent && !p.is_user_team && p.transfer_ask != null && typeof openOffer === "function" && html`
          <button class="btn btn-sm" onClick=${handleMakeOffer}>Make an offer…</button>
        `}
        ${p.is_user_team && p.can_rein_streaming && html`
          <button class="btn btn-sm" title="Spend this week's 1:1 telling them to stream less and practice more" onClick=${handleReinStreaming}>Rein in streaming…</button>
        `}
        ${p.can_change_assignment && html`
          <button class="btn btn-sm" title="A new assignment changes current ability and starts at low comfort" onClick=${() => pfChangeAssignment(p)}>Change role/style…</button>
        `}
        ${p.can_assign_igl && !p.is_igl && html`
          <button class="btn btn-sm" title="Assign shot-calling to this player; effectiveness uses skills and match experience" onClick=${() => pfAssignIgl(p)}>Make IGL</button>
        `}
        <button class="btn btn-sm" disabled=${!!scoutCtx.active} title=${p.is_user_team ? "Retask the scout to map this player's development path and weekly training fit" : "Retask the scout to build a full information book; external uncertainty remains"} onClick=${handleScout}>
          ${scoutCtx.active ? `Deep-diving ${Math.round((scoutCtx.progress || 0) * 100)}%` : (p.is_user_team ? "Scout development" : "Deep-dive player")}
        </button>
        ${isAdminMode() && html`
          <button class="btn btn-sm" onClick=${() => setShowAdminEdit(!showAdminEdit)}>🛠 Correct data</button>
        `}
      </div>

      ${showAdminEdit && html`
        <${AdminSlot} kind="player" id=${p.id} onDone=${() => { setShowAdminEdit(false); openPlayerProfile(p.id, { replace: true }); }} />
      `}

      <div class="pf-tiles">
        <div class="pf-tile" data-tooltip="<h4>Overall Rating (OVR)</h4><div class='tooltip-desc'>A quick-glance aggregation of this player's active attributes. Higher is better.</div>">
          <div class="pf-tile-val mono">${(ov.fogged && ov.ovr != null ? "~" : "") + pfNum(ov.ovr)}</div>
          <div class="pf-tile-label">OVR</div>
          <div class="pf-tile-sub">${ovrSub}</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>Current Ability (CA)</h4><div class='tooltip-desc'>The player's active skill level in matches. Comfort modulates this based on role and playstyle alignment.</div>">
          <div class="pf-tile-val mono">${Array.isArray(caBand) ? `${Math.round(caBand[0])}–${Math.round(caBand[1])}` : "—"}</div>
          <div class="pf-tile-label">Current ability</div>
          <div class="pf-tile-sub">${ov.comfort != null ? `${Math.round(ov.comfort)} comfort` : "scouted"}</div>
        </div>
        ${ov.igl_effectiveness != null && html`
          <div class="pf-tile" data-tooltip="<h4>IGL Effectiveness</h4><div class='tooltip-desc'>How effectively this player calls strategies when set as the In-Game Leader. Scales with calling experience and tactical/comms skills.</div>">
            <div class="pf-tile-val mono">${pfNum(ov.igl_effectiveness)}</div>
            <div class="pf-tile-label">IGL effectiveness</div>
            <div class="pf-tile-sub">${Math.round(ov.igl_experience || 0)} calling experience</div>
          </div>
        `}
        <div class="pf-tile" data-tooltip="<h4>Potential (PA)</h4><div class='tooltip-desc'>A projection of the player's peak capability. Dynamic; players can fall short or exceed their forecast based on training, development focus, and play time.</div>">
          <div class="pf-tile-val mono">${potBand ? `${potBand[0]}–${potBand[1]}` : (potIsNum ? pfNum(ov.potential) : (ov.potential || "—"))}</div>
          <div class="pf-tile-label">Potential</div>
          <div class="pf-tile-sub">${potBand ? "peak forecast" : (potIsNum ? pfStars(ov.potential_stars) : "scouted")}</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>Form</h4><div class='tooltip-desc'>Recent match performance rating on a 0-100 scale. Affects short-term confidence and training growth rate.</div>">
          <div class="pf-tile-val mono">${pfNum(ov.form)}</div>
          <div class="pf-tile-label">Form</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>Morale</h4><div class='tooltip-desc'>How happy the player is. High morale accelerates attribute growth; low morale slows growth and makes them more prone to tilt.</div>">
          <div class="pf-tile-val mono">${pfNum(ov.morale)}</div>
          <div class="pf-tile-label">Morale</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>Condition</h4><div class='tooltip-desc'>Physical fitness. Heavy training intensity and playing back-to-back matches drains condition. Rest them when low to prevent exhaustion or injury.</div>">
          <div class="pf-tile-val mono">${pfNum(ov.condition)}</div>
          <div class="pf-tile-label">Condition</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>Confidence</h4><div class='tooltip-desc'>The player's mental state in round duels. Stacks with aim; confident players win more 50-50 duels and clutch scenarios. Regresses towards 50 weekly.</div>">
          <div class="pf-tile-val mono">${pfNum(p.confidence)}</div>
          <div class="pf-tile-label">Confidence</div>
          <div class="pf-tile-sub">drives duels & nerve</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>xDuel (Expected Duel Wins)</h4><div class='tooltip-desc'>The player's actual round duel wins compared to their expected wins based on statistical matchups.</div>">
          <div class="pf-tile-val mono">${xdActStr} / ${xdExpStr}</div>
          <div class="pf-tile-label">xDuel</div>
          <div class="pf-tile-sub">actual / expected wins</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>xDE (Expected Duel Edge)</h4><div class='tooltip-desc'>Calculated as actual duel wins minus expected duel wins. A positive edge indicates that the player outperforms statistical expectations.</div>">
          <div class="pf-tile-val mono">${xdEdgeStr}</div>
          <div class="pf-tile-label">xDE</div>
          <div class="pf-tile-sub">expected duel edge</div>
        </div>
        <div class="pf-tile" data-tooltip="<h4>Market Value</h4><div class='tooltip-desc'>Estimated valuation on the transfer market. Unsigned free agents have no valuation. Rival teams will demand more or less than this based on their stance.</div>">
          <div class="pf-tile-val mono">${ov.market_value != null ? money(ov.market_value) : "—"}</div>
          <div class="pf-tile-label">Value</div>
        </div>
      </div>

      ${p.is_user_team && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Scout development guidance</h3>
          ${guide ? html`
            <p><span class="pill">${guide.focus}</span> ${guide.reason}</p>
            <p class=${guide.bonus_active ? "trend-up" : "muted"}>
              ${scoutCtx.active
                ? (guide.bonus_active
                    ? `Active this week: matching focus earns ×${guide.bonus_mult.toFixed(2)} development.`
                    : `Set this player's focus to ${guide.focus} to earn ×${guide.bonus_mult.toFixed(2)} development this week.`)
                : "Keep the scout assigned to this player to activate the matching-focus weekly bonus."}
            </p>
          ` : html`
            <p class="pf-empty muted">
              Deep-dive this player to ${Math.round((scoutCtx.guidance_unlock || 0) * 100)}% for a contextual training recommendation and ×${(scoutCtx.bonus_mult || 1).toFixed(2)} weekly bonus.
            </p>
          `}
        </div>
      `}

      ${!p.is_user_team && scoutCtx.report && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Scouting book · ${Math.round(scoutCtx.progress * 100)}% information</h3>
          <div>
            ${report.style_read && html`<p><b>Style:</b> ${report.style_read}</p>`}
            ${report.mental_read && html`<p><b>Mentality:</b> ${report.mental_read}</p>`}
            ${report.curve_read && html`<p><b>Development path:</b> ${report.curve_read}</p>`}
            ${report.training_hint && html`<p><b>Development fit:</b> <span class="pill">${report.training_hint.focus}</span> ${report.training_hint.reason}</p>`}
            ${(report.ceiling_reads || []).length > 0 && html`
              <p><b>Skill ceilings:</b> ${report.ceiling_reads.map((c) => html`<span class="pill" key=${c.attr}>${humanize(c.attr)}: ${c.read}</span>`)}</p>
            `}
            ${report.verdict && html`<p><b>Verdict:</b> ${report.verdict}</p>`}
            ${(!report.style_read && !report.mental_read && !report.curve_read && !report.training_hint && (!report.ceiling_reads || !report.ceiling_reads.length) && !report.verdict) && html`
              <p class="muted">Broader reads unlock as information moves toward 75% and a full deep dive.</p>
            `}
          </div>
        </div>
      `}

      ${badges.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Badges</h3>
          <div class="pf-chips">
            ${badges.map((bd, i) => {
              const icon = bd.art
                ? html`<img class="pf-badge-art" src=${bd.art} alt="" />`
                : html`<span class="pf-badge-emoji">${bd.emoji}</span>`;
              return html`
                <span key=${i} class=${`pf-chip pf-badge ${bd.polarity < 0 ? 'pf-badge-neg' : 'pf-badge-pos'}`} title=${bd.blurb + (bd.season ? ` — earned S${bd.season}` : "")}>
                  ${icon} ${bd.name}
                </span>
              `;
            })}
          </div>
        </div>
      `}

      <div class="pf-grid2">
        <div class="pf-section">
          <h3 class="pf-section-title">Attributes</h3>
          ${attrs.length > 0 ? html`
            <div class="pf-attrs">
              ${attrs.map((a) => {
                const lbl = a.label || a.key || "";
                const tooltipText = `<h4>${lbl}</h4><div class='tooltip-desc'>${a.description || ""}</div>`;
                if (a.value != null) {
                  const ceil = (ov.skill_ceilings || {})[a.key];
                  const ceilHi = Array.isArray(ceil) ? ceil[1] : ceil;
                  const ceilLabel = Array.isArray(ceil) ? `${ceil[0]}–${ceil[1]}` : ceil;
                  const ceilTxt = (ceilHi != null && ceilHi > Math.round(a.value) + 1)
                    ? html` <span class="muted" title="projected outcome range for this skill">→${ceilLabel}</span>`
                    : "";
                  return html`
                    <div key=${a.key} class="pf-attr" data-tooltip=${tooltipText}>
                      <span class="pf-attr-label">${lbl}</span>
                      <span class="pf-attr-bar"><${PfBar} value=${a.value} /></span>
                      <span class="pf-attr-val mono">${Math.round(a.value)}${ceilTxt}</span>
                    </div>
                  `;
                } else {
                  return html`
                    <div key=${a.key} class="pf-attr" data-tooltip=${tooltipText + "<br><div class='tooltip-sub'>Estimate is based on scout observations. Deep-dive to improve accuracy.</div>"}>
                      <span class="pf-attr-label">${lbl}</span>
                      <span class="pf-attr-band"><span class="pf-band">${a.band ?? "?"}</span></span>
                    </div>
                  `;
                }
              })}
            </div>
          ` : html`<p class="pf-empty muted">Attributes not scouted yet.</p>`}
        </div>

        <div class="pf-col">
          <div class="pf-section">
            <h3 class="pf-section-title">Traits</h3>
            ${traits.length > 0 ? html`
              <div class="pf-chips">
                ${traits.map((t, i) => {
                  if (t.revealed === false) {
                    return html`<span key=${i} class="pf-chip pf-chip-locked">?</span>`;
                  } else {
                    return html`<span key=${i} class="pf-chip" title=${t.desc || ""}>${humanize(t.name ?? "")}</span>`;
                  }
                })}
              </div>
            ` : html`<p class="pf-empty muted">No traits revealed.</p>`}
          </div>

          <div class="pf-section">
            <h3 class="pf-section-title">Agent pool</h3>
            ${agents.length > 0 ? html`
              <div>
                <div class=${`pf-agents ${agentsExpanded ? 'pf-agents-expanded' : ''}`}>
                  ${agents.map((a) => {
                    const shown = visibleAgentIds.has(a.agent_id);
                    const icon = a.icon
                      ? html`<img class="pf-agent-icon" src=${a.icon} alt="" onError=${(e) => { e.target.style.visibility = 'hidden'; }} />`
                      : html`<span class="pf-agent-icon"></span>`;
                    return html`
                      <div key=${a.agent_id} class=${`pf-agent ${shown ? '' : 'pf-agent-extra'}`}>
                        ${icon}
                        <span class="pf-agent-name">${a.name || a.agent_id || ""}</span>
                        <span class="pf-agent-bar"><${PfBar} value=${a.mastery} /></span>
                        <span class="pf-agent-mv mono">${pfNum(a.mastery)}</span>
                      </div>
                    `;
                  })}
                </div>
                ${hiddenAgentsCount > 0 && html`
                  <button class="pf-agent-toggle" onClick=${() => setAgentsExpanded(!agentsExpanded)}>
                    ${agentsExpanded ? "Show fewer" : `Show all (${agents.length})`}
                  </button>
                `}
              </div>
            ` : html`<p class="pf-empty muted">No agent pool data.</p>`}
          </div>
        </div>
      </div>

      ${(season.matches != null || weekly.length > 0) && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Season — analytics</h3>
          ${season.matches != null && html`
            <div>
              <div class="pf-tiles pf-tiles-sm">
                <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(season.rating, 2)}</div><div class="pf-tile-label">Rating</div></div>
                <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(season.kd, 2)}</div><div class="pf-tile-label">K/D</div></div>
                <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(season.acs)}</div><div class="pf-tile-label">ACS</div></div>
                <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(season.kast_pct)}</div><div class="pf-tile-label">KAST%</div></div>
                <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(season.hs_pct)}</div><div class="pf-tile-label">HS%</div></div>
                <div class="pf-tile">
                  <div class="pf-tile-val mono">${season.first_deaths != null ? `${pfNum(season.first_kills)} : ${pfNum(season.first_deaths)}` : pfNum(season.first_kills)}</div>
                  <div class="pf-tile-label">FK : FD</div>
                  ${season.fk_fd != null && html`<div class="pf-tile-sub">ratio ${pfNum(season.fk_fd, 2)}</div>`}
                </div>
                <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(season.clutches)}</div><div class="pf-tile-label">Clutches</div></div>
              </div>
              
              ${season.clutch_1v1 != null && html`
                <p class="pf-season-line muted">
                  Clutches: ${pfNum(season.clutch_1v1)}x 1v1, ${pfNum(season.clutch_1v2)}x 1v2, ${pfNum(season.clutch_1v3)}x 1vX
                  / Kills: ${pfNum(season.pistol_kills)} pistol, ${pfNum(season.eco_kills)} eco, ${pfNum(season.save_kills)} save
                  ${season.trade_kills != null ? `, ${pfNum(season.trade_kills)} trades` : ""}
                </p>
              `}
              
              ${season.kills_by_weapon && Object.keys(season.kills_by_weapon).length > 0 && html`
                <div class="pf-chips">
                  ${Object.entries(season.kills_by_weapon).slice(0, 8).map(([w, n]) => html`
                    <span key=${w} class="pf-chip" title=${`kills with ${w}`}>${w} ${n}</span>
                  `)}
                </div>
              `}
              
              ${(season.analytics_tier ?? 0) < 2 && html`
                <p class="pf-empty muted">Deeper numbers (KAST, trades, weapons, eco/save splits, trend charts) need a stronger analytics department.</p>
              `}
              
              <p class="pf-season-line muted">
                ${pfNum(season.matches)} matches · ${pfNum(season.kills)} / ${pfNum(season.deaths)} / ${pfNum(season.assists)} K / D / A
              </p>
            </div>
          `}

          ${(() => {
            const chartPerf = (data.charts && data.charts.performance) || [];
            const hasSpark = chartPerf.length > 0 || weekly.length > 0;
            const hasRating = chartPerf.length > 0;
            const hasMirror = weekly.length > 0;
            return html`
              <g>
                ${hasSpark && html`
                  <div class="pf-chart-box">
                    <div class="pf-chart-cap">ACS by week</div>
                    <${AcsSparkline} weekly=${chartPerf.length ? chartPerf : weekly} />
                  </div>
                `}
                ${hasRating && html`
                  <div class="pf-chart-box">
                    <div class="pf-chart-cap">Rating by week</div>
                    <${MetricLine} series=${chartPerf} getValue=${(w) => w.rating} formatValue=${(v) => Number(v).toFixed(2)} ariaLabel="Rating by week" />
                  </div>
                `}
                ${hasMirror && html`
                  <div class="pf-chart-box">
                    <div class="pf-chart-cap">
                      Kills &amp; deaths by week
                      <span class="pf-legend"><span class="pf-sw pf-sw-k"></span>K<span class="pf-sw pf-sw-d"></span>D</span>
                    </div>
                    <${KdMirrorBars} weekly=${weekly} />
                  </div>
                `}
              </g>
            `;
          })()}
        </div>
      `}

      ${devSeries.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Development</h3>
          <div class="pf-chart-box">
            <div class="pf-chart-cap">
              Ability &amp; confidence over time
              <span class="pf-legend"><span class="pf-sw pf-sw-k"></span>CA<span class="pf-sw pf-sw-d"></span>Conf</span>
            </div>
            <${DevChart} series=${devSeries} />
          </div>
          ${(() => {
            const first = devSeries[0], last = devSeries[devSeries.length - 1];
            return html`
              <p class="pf-season-line muted">
                CA ${pfNum(first.ca, 1)} to ${pfNum(last.ca, 1)} over ${devSeries.length} weeks
                ${typeof fmtFollowers === "function" ? ` / ${fmtFollowers(last.followers)} followers` : ""}
              </p>
            `;
          })()}
        </div>
      `}

      ${(mapSplits.length > 0 || agentSplits.length > 0) && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Splits</h3>
          <div class="pf-grid2">
            ${mapSplits.length > 0 && html`
              <div>
                <table class="pf-table">
                  <thead>
                    <tr><th>Map</th><th class="num">Maps</th><th class="num">Rating</th><th class="num">ACS</th><th class="num">K/D</th><th class="num">KAST%</th></tr>
                  </thead>
                  <tbody>
                    ${mapSplits.map((r, i) => html`
                      <tr key=${i}>
                        <td>${r.label}</td><td class="num">${r.maps}</td>
                        <td class="num">${pfNum(r.rating, 2)}</td><td class="num">${pfNum(r.acs)}</td>
                        <td class="num">${pfNum(r.kd, 2)}</td><td class="num">${pfNum(r.kast_pct)}</td>
                      </tr>
                    `)}
                  </tbody>
                </table>
              </div>
            `}
            ${agentSplits.length > 0 && html`
              <div>
                <table class="pf-table">
                  <thead>
                    <tr><th>Agent</th><th class="num">Maps</th><th class="num">Rating</th><th class="num">ACS</th><th class="num">K/D</th><th class="num">KAST%</th></tr>
                  </thead>
                  <tbody>
                    ${agentSplits.map((r, i) => html`
                      <tr key=${i}>
                        <td>${r.label}</td><td class="num">${r.maps}</td>
                        <td class="num">${pfNum(r.rating, 2)}</td><td class="num">${pfNum(r.acs)}</td>
                        <td class="num">${pfNum(r.kd, 2)}</td><td class="num">${pfNum(r.kast_pct)}</td>
                      </tr>
                    `)}
                  </tbody>
                </table>
              </div>
            `}
          </div>
        </div>
      `}

      ${rels.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Relationships</h3>
          <div class="pf-chips">
            ${rels.map((r, i) => html`
              <span key=${i} class=${`pf-rel-chip plink rel-${r.kind || 'neutral'}`} data-pid=${r.pid} title=${r.strength != null ? `${r.kind ?? "bond"} · strength ${Math.round(r.strength)}` : ""}>
                ${r.handle ?? "—"}<span class="pf-rel-kind">${r.kind ?? ""}</span>
              </span>
            `)}
          </div>
        </div>
      `}

      ${(ct || arc.length > 0 || honours.length > 0 || mems.length > 0 || career.length > 0) && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Career</h3>
          
          ${ct && html`
            <div class="pf-tiles pf-tiles-sm">
              <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(ct.seasons)}</div><div class="pf-tile-label">Seasons</div></div>
              <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(ct.maps)}</div><div class="pf-tile-label">Maps</div></div>
              <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(ct.kills)}</div><div class="pf-tile-label">Kills</div></div>
              <div class="pf-tile"><div class="pf-tile-val mono">${ct.kd.toFixed(2)}</div><div class="pf-tile-label">K/D</div></div>
              <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(ct.honours)}</div><div class="pf-tile-label">Honours</div></div>
              <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(ct.mvps)}</div><div class="pf-tile-label">MVPs</div></div>
              <div class="pf-tile"><div class="pf-tile-val mono">${pfNum(ct.all_stars)}</div><div class="pf-tile-label">All-Star</div></div>
            </div>
          `}

          ${arc.length > 0 && html`
            <div>
              <div class="pf-career-sub muted">Timeline</div>
              <div class="pf-arc">
                ${arc.map((yr) => html`
                  <div key=${yr.season} class="pf-arc-row">
                    <span class="pf-arc-season mono">S${yr.season}</span>
                    <div class="pf-arc-evs">
                      ${yr.events.map((e, idx) => html`
                        <span key=${idx} class=${`pf-arc-ev arc-${e.kind}`}>${e.text}</span>
                      `)}
                    </div>
                  </div>
                `)}
              </div>
            </div>
          `}

          ${honours.length > 0 && html`
            <div>
              <div class="pf-career-sub muted">Honours (${honours.length})</div>
              <ul class="pf-honours" style=${{ margin: 0, padding: 0, listStyle: "none" }}>
                ${honours.map((h, i) => html`
                  <li key=${i} class="pf-honour">
                    <span class="pf-honour-award">S${h.season} · ${h.award}</span>
                    ${h.detail && html`<span class="pf-honour-detail muted">${h.detail}</span>`}
                  </li>
                `)}
              </ul>
            </div>
          `}

          ${mems.length > 0 && html`
            <div>
              <div class="pf-career-sub muted">Memories</div>
              <ul class="pf-memories" style=${{ margin: 0, paddingLeft: "18px" }}>
                ${mems.map((m, i) => html`<li key=${i} class="muted">${m}</li>`)}
              </ul>
            </div>
          `}

          ${career.length > 0 && html`
            <div>
              <div class="pf-career-sub muted">Season by season</div>
              <table class="pf-table">
                <thead>
                  <tr><th>Season</th><th>Team</th><th class="num">Maps</th><th class="num">K/D</th><th class="num">ACS</th></tr>
                </thead>
                <tbody>
                  ${career.map((c, i) => html`
                    <tr key=${i}>
                      <td>S${c.season ?? "—"}</td><td>${c.team ?? "—"}</td>
                      <td class="num">${pfNum(c.matches)}</td>
                      <td class="num">${pfNum(c.kd, 2)}</td>
                      <td class="num">${pfNum(c.acs)}</td>
                    </tr>
                  `)}
                </tbody>
              </table>
            </div>
          `}
        </div>
      `}

      ${promList.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Active Promises</h3>
          <div class="pf-promises-container">
            ${promList.map((prom, idx) => {
              const duration = prom.initial_duration || 1;
              const pct = Math.max(0, Math.min(100, Math.round((prom.weeks_left / duration) * 100)));
              let progressInfo = "";
              if (prom.promise_type === "play_time") {
                progressInfo = ` · Dressed ${prom.dressed_count} weeks`;
              }
              return html`
                <div key=${idx} class="pf-promise-item">
                  <div style=${{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <strong>${prom.promise_type.replace(/_/g, " ").toUpperCase()}</strong>
                    <span class="muted">${prom.weeks_left} weeks left</span>
                  </div>
                  <div style=${{ fontSize: "0.9em", marginBottom: "4px" }}>Target: ${prom.target_value || "N/A"}${progressInfo}</div>
                  <div class="pf-hbar" style=${{ height: "6px", background: "var(--es-color-bg-alt, #151b26)", borderRadius: "3px", overflow: "hidden" }}>
                    <i style=${{ display: "block", height: "100%", width: `${pct}%`, '--target-width': `${pct}%`, background: "var(--es-color-accent, #00f0ff)", borderRadius: "3px" }}></i>
                  </div>
                </div>
              `;
            })}
          </div>
      `}

      ${p.team_id && html`<${TeammateCompare} playerId=${p.id} teamId=${p.team_id} attributes=${attrs} />`}
    </div>
  `;
};

const TeamProfile = ({ data }) => {
  const t = data.team || {};
  const rec = data.record || {};
  const [showAdminEdit, setShowAdminEdit] = useState(false);

  const logo = t.logo
    ? html`<img class="pf-team-badge" src=${t.logo} alt="" onError=${(e) => { e.target.style.visibility = 'hidden'; }} />`
    : html`<span class="pf-team-badge pf-portrait-blank"></span>`;

  const tierBits = [t.region ? String(t.region).toUpperCase() : "", t.league_tier]
    .filter((x) => x != null && x !== "")
    .join(" · ");

  const recBits = [];
  if (rec.wins != null || rec.losses != null) recBits.push(`${pfNum(rec.wins)}–${pfNum(rec.losses)}`);
  if (rec.position != null) recBits.push(`#${rec.position}`);
  if (rec.round_diff != null) recBits.push(`${rec.round_diff > 0 ? "+" : ""}${rec.round_diff} rd`);
  if (rec.streak) recBits.push(String(rec.streak));

  const handleViewRoster = () => {
    closeProfile();
    if (t.is_user_team) {
      if (typeof App === "object") { App.rosterTeam = null; App.clubTab = "squad"; }
      const tab = document.querySelector('#tabs [data-tab="club"]');
      if (tab) tab.click();
    } else if (typeof App === "object") {
      App.rosterTeam = t.id;
      App.tab = "roster";
      if (typeof window.render === "function") window.render();
    }
  };

  const handleAssignScout = async () => {
    try {
      const r = await api("/api/actions/scout", { team_id: t.id });
      toast(r.message || "Scout assigned.");
    } catch {}
  };

  const tend = data.tendencies || [];

  const sp = data.splits || {};
  const atk = pfPct(sp.attack_round_rate);
  const def = pfPct(sp.defense_round_rate);

  const maps = data.maps || [];
  const players = data.players || [];
  const maxAcs = useMemo(() => Math.max(1, ...players.map((pl) => pl.acs || 0)), [players]);

  const form = data.form || [];

  const rivals = data.rivals || [];
  const chem = data.chemistry;
  const dev = data.dev_progress || [];

  const strength = data.strength || [];
  const pool = data.agent_pool;
  const know = data.knowledge;
  const honors = (data.honors || []).filter(Boolean);

  return html`
    <div>
      <div class="pf-header">
        ${logo}
        <div class="pf-id">
          <div class="pf-handle">${t.name ?? "Unknown"}</div>
          ${(tierBits || data.identity) && html`
            <div class="pf-meta">
              ${tierBits && html`<span class="pill">${tierBits}</span>`}
              ${data.identity && html` <span class="pill pf-identity">${data.identity}</span>`}
            </div>
          `}
          ${recBits.length > 0 && html`<div class="pf-contract mono">${recBits.join("  ·  ")}</div>`}
        </div>
        <button class="btn btn-sm" onClick=${handleViewRoster}>View roster ▸</button>
        ${!t.is_user_team && t.id && html`
          <button class="btn btn-sm" title="Retask your scout onto this org (replaces the current assignment)" onClick=${handleAssignScout}>Assign scout</button>
        `}
        ${isAdminMode() && html`
          <button class="btn btn-sm" onClick=${() => setShowAdminEdit(!showAdminEdit)}>🛠 Correct data</button>
        `}
      </div>

      ${showAdminEdit && html`
        <${AdminSlot} kind="team" id=${t.id} onDone=${() => { setShowAdminEdit(false); openTeamProfile(t.id, { replace: true }); }} />
      `}

      ${tend.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Playstyle</h3>
          <p class="muted">${tend.join(" · ")}</p>
        </div>
      `}

      ${(atk != null || def != null) && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Round-win split</h3>
          <div class="pf-split">
            <div class="pf-split-lab pf-split-atk">ATK <b class="mono">${atk != null ? atk + "%" : "—"}</b></div>
            <div class="pf-split-bar">
              <div class="pf-split-fill atk" style=${{ width: `${(atk ?? 0) / 2}%`, '--target-width': `${(atk ?? 0) / 2}%` }}></div>
              <div class="pf-split-fill def" style=${{ width: `${(def ?? 0) / 2}%`, '--target-width': `${(def ?? 0) / 2}%` }}></div>
              <span class="pf-split-mid"></span>
            </div>
            <div class="pf-split-lab pf-split-def"><b class="mono">${def != null ? def + "%" : "—"}</b> DEF</div>
          </div>
        </div>
      `}

      ${maps.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Map winrate</h3>
          <div class="pf-maps">
            ${maps.map((m, i) => {
              const wr = m.played ? Math.round((m.wins / m.played) * 100) : null;
              const cls = wr == null ? "" : wr >= 55 ? "good" : wr >= 45 ? "warn" : "bad";
              return html`
                <div class="pf-map" key=${i}>
                  <span class="pf-map-name">${m.map ?? "—"}</span>
                  <span class="pf-map-bar"><span class=${`pf-hbar ${cls}`}><i style=${{ width: `${wr ?? 0}%`, '--target-width': `${wr ?? 0}%` }}></i></span></span>
                  <span class="pf-map-rec mono muted">${pfNum(m.wins)}–${pfNum(m.losses)}</span>
                  <span class="pf-map-wr mono">${wr != null ? wr + "%" : "—"}</span>
                </div>
              `;
            })}
          </div>
        </div>
      `}

      ${players.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Roster</h3>
          <table class="pf-table pf-roster">
            <thead>
              <tr><th>Player</th><th>Role</th><th class="num">Maps</th><th class="num">K/D</th><th>ACS</th></tr>
            </thead>
            <tbody>
              ${players.map((pl) => html`
                <tr key=${pl.pid} class="pf-rrow plink" data-pid=${pl.pid}>
                  <td><b>${pl.handle ?? "—"}</b>${pl.retirement_risk && html` <span class="pill retire-pill" title="A veteran carrying real retirement odds this offseason">TWILIGHT</span>`}</td>
                  <td>${pl.role && html`<span class="pill">${pl.role}</span>`}</td>
                  <td class="num">${pfNum(pl.matches)}</td>
                  <td class="num">${pfNum(pl.kd, 2)}</td>
                  <td class="pf-acs-cell">
                    <span class="pf-hbar">
                      <i style=${{ width: `${Math.max(2, Math.min(100, ((pl.acs || 0) / maxAcs) * 100))}%`, '--target-width': `${Math.max(2, Math.min(100, ((pl.acs || 0) / maxAcs) * 100))}%` }}></i>
                    </span>
                    <span class="mono pf-acs-val">${pfNum(pl.acs)}</span>
                  </td>
                </tr>
              `)}
            </tbody>
          </table>
        </div>
      `}

      ${form.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Form</h3>
          <div class="pf-form">
            ${form.map((f, i) => {
              const res = (f.result || "").toString().toUpperCase();
              const cls = res.startsWith("W") ? "w" : res.startsWith("L") ? "l" : "d";
              return html`
                <span key=${i} class=${`pf-form-sq ${cls}`} title=${`${f.opponent ? 'vs ' + f.opponent : ''}${f.score ? ' · ' + f.score : ''}`.trim() || "—"}>
                  ${res.slice(0, 1) || "·"}
                </span>
              `;
            })}
          </div>
        </div>
      `}

      ${rivals.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Rivalries</h3>
          <div class="pf-chips">
            ${rivals.map((r, i) => html`
              <span key=${i} class="pf-rel-chip tlink rel-clash" data-tid=${r.team_id}>
                ${r.name}<span class="pf-rel-kind">heat ${Math.round(r.intensity)}</span>
              </span>
            `)}
          </div>
        </div>
      `}

      ${chem && chem.cohesion != null && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Squad chemistry · cohesion ${Math.round(chem.cohesion)}</h3>
          <div class="pf-chips">
            ${chem.bonds.map((b, i) => html`
              <span key=${`bond-${i}`} class="pf-rel-chip rel-duo">
                <span class="plink" data-pid=${b.a_id}>${b.a}</span> + <span class="plink" data-pid=${b.b_id}>${b.b}</span>
                <span class="pf-rel-kind">${Math.round(b.strength)}</span>
              </span>
            `)}
            ${chem.frictions.map((f, i) => html`
              <span key=${`fric-${i}`} class="pf-rel-chip rel-feud">
                <span class="plink" data-pid=${f.a_id}>${f.a}</span> + <span class="plink" data-pid=${f.b_id}>${f.b}</span>
                <span class="pf-rel-kind">${Math.round(f.strength)}</span>
              </span>
            `)}
            ${!chem.bonds.length && !chem.frictions.length && html`
              <span class="muted">a settled, unremarkable dressing room</span>
            `}
          </div>
        </div>
      `}

      ${dev.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Development</h3>
          <div class="pf-dev">
            ${dev.map((d) => {
              const arrow = d.overperforming ? "★" : d.maxed ? "◆" : d.trajectory === "climbing" ? "▲" : d.trajectory === "declining" ? "▼" : "—";
              const acls = d.overperforming ? "trend-up" : d.maxed ? "trend-flat" : d.trajectory === "climbing" ? "trend-up" : d.trajectory === "declining" ? "trend-down" : "muted";
              const ceilTxt = d.potential_band ? `${d.potential_band[0]}–${d.potential_band[1]}` : d.potential;
              const teach = d.mentor_skill >= 55 ? html` · <span title="strong mentor — worth pairing with a prospect">🎓${d.mentor_skill}</span>` : "";
              const above = d.overperforming ? html` · <span class="trend-up">above original projection</span>` : "";
              const support = d.support_bonus > 0 ? html` · support +${d.support_bonus.toFixed(1)}` : "";
              return html`
                <div key=${d.id} class="pf-dev-row">
                  <span class="plink pf-dev-name" data-pid=${d.id}>${d.handle}</span>
                  <span class="muted pf-dev-meta" title=${d.curve_read}>${d.age}y · CA ${d.ca} · peak ${ceilTxt}${above}${support}${teach}</span>
                  <span class="pf-dev-bar"><span class="pf-dev-fill" style=${{ width: `${d.progress_pct}%`, '--target-width': `${d.progress_pct}%` }}></span></span>
                  <span class=${`mono ${acls}`}>${d.progress_pct}% ${arrow}</span>
                </div>
              `;
            })}
          </div>
        </div>
      `}

      ${strength.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Squad strength</h3>
          <div class="pf-str">
            ${strength.map((a, i) => {
              const w = a.value != null ? a.value : { elite: 92, strong: 78, solid: 62, average: 48, weak: 32 }[a.band] || 50;
              return html`
                <div class="pf-str-row" key=${i}>
                  <span class="pf-str-lab">${a.label}</span>
                  <span class="pf-str-bar"><span class="pf-str-fill" style=${{ width: `${w}%`, '--target-width': `${w}%` }}></span></span>
                  <span class=${`mono ${a.value == null ? 'muted' : ''}`}>${a.value != null ? a.value : a.band}</span>
                </div>
              `;
            })}
          </div>
        </div>
      `}

      ${pool && (pool.covered?.length > 0 || pool.meta_gaps?.length > 0) && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Agent pool</h3>
          ${pool.covered.length > 0 && html`
            <div class="pf-chips">
              ${pool.covered.map((a, i) => html`
                <span key=${i} class="pf-pool-chip">
                  ${a.name} <span class="pf-rel-kind">${a.players}x·${a.mastery}</span>
                </span>
              `)}
            </div>
          `}
          ${pool.meta_gaps.length > 0 && html`
            <div class="muted pf-pool-gaps">Meta gaps: ${pool.meta_gaps.map((g) => g.name).join(", ")}</div>
          `}
        </div>
      `}

      ${know && (know.methodology != null || (know.playbooks || []).length > 0 || (know.antistrats || []).length > 0) && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Playbook &amp; knowledge</h3>
          ${know.methodology != null && html`
            <p class="pf-season-line muted">
              Methodology <b class="mono">${pfNum(know.methodology, 1)}</b> — training-ground know-how that survives roster churn
            </p>
          `}
          ${(know.playbooks || []).length > 0 && html`
            <div>
              <div class="pf-career-sub muted">Map playbooks</div>
              <div class="pf-chips">
                ${know.playbooks.map((pb, i) => html`
                  <span key=${i} class="pf-chip" title="playbook depth on this map">
                    ${humanize(pb.map)}<span class="pf-rel-kind">${pfNum(pb.depth, 1)}</span>
                  </span>
                `)}
              </div>
            </div>
          `}
          ${(know.antistrats || []).length > 0 && html`
            <div>
              <div class="pf-career-sub muted">Anti-strat books</div>
              <div class="pf-chips">
                ${know.antistrats.map((a, i) => html`
                  <span key=${i} class="pf-chip" title="opponent book depth — feeds prep edge through a set game plan">
                    <span class="tlink" data-tid=${a.team_id}>${a.name || a.team_id}</span>
                    <span class="pf-rel-kind">${pfNum(a.depth, 1)}</span>
                  </span>
                `)}
              </div>
            </div>
          `}
        </div>
      `}

      ${honors.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Honours</h3>
          ${honors.map((h, i) => html`<div key=${i} class="pf-honor">★ ${h}</div>`)}
        </div>
      `}
    </div>
  `;
};

const StaffProfile = ({ data }) => {
  const m = data.member || {};
  const initial = (m.name || "?").charAt(0).toUpperCase();

  const meta = [
    m.role ? html`<span class="pill" key="role">${m.role}</span>` : "",
    m.specialty ? html`<span class="pill" title=${m.specialty_blurb || ""} key="spec">${m.specialty}</span>` : "",
    m.age != null ? html`<span class="pf-age" key="age">age ${m.age}</span>` : "",
    m.region ? html`<span class="pill" key="region">${m.region}</span>` : "",
  ].filter(Boolean);

  const employ = m.employer_name
    ? html`<span><span class="tlink" data-tid=${m.employer_id}>${m.employer_name}</span>${data.is_yours ? " (your org)" : ""}</span>`
    : "Free agent";

  const effects = data.effects || [];
  const traits = (m.traits || []).filter(Boolean);
  const honors = (m.titles || []).filter(Boolean);
  const history = (m.history || []).filter(Boolean);

  return html`
    <div>
      <div class="pf-header">
        <span class="pf-portrait pf-portrait-blank pf-staff-initial">${initial}</span>
        <div class="pf-id">
          <div class="pf-handle">${m.name ?? "Unknown"}</div>
          <div class="pf-meta">${meta}</div>
          <div class="pf-contract muted">${employ} · ${money(m.salary)}/wk</div>
        </div>
      </div>

      <div class="pf-tiles">
        <div class="pf-tile">
          <div class="pf-tile-val mono">${pfNum(m.quality)}</div>
          <div class="pf-tile-label">Quality</div>
        </div>
        <div class="pf-tile">
          <div class="pf-tile-val mono">${pfNum(m.seasons_experience)}s</div>
          <div class="pf-tile-label">Experience</div>
        </div>
        <div class="pf-tile">
          <div class="pf-tile-val mono">${pfNum(honors.length)}</div>
          <div class="pf-tile-label">Titles</div>
        </div>
      </div>

      <div class="pf-section">
        <h3 class="pf-section-title">What they do</h3>
        ${effects.map((line, i) => html`<div key=${i} class="pf-honor">▸ ${line}</div>`)}
        ${data.in_pool && data.hire_cost_note && html`
          <p class="muted">Hire from the Market tab (${data.hire_cost_note}).</p>
        `}
      </div>

      ${traits.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Style</h3>
          <div class="pf-chips">
            ${traits.map((t, i) => html`<span key=${i} class="pf-chip">${t.replaceAll("_", " ")}</span>`)}
          </div>
        </div>
      `}

      ${honors.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Honours</h3>
          ${honors.map((h, i) => html`<div key=${i} class="pf-honor">★ ${h}</div>`)}
        </div>
      `}

      <div class="pf-section">
        <h3 class="pf-section-title">Career</h3>
        ${history.length > 0 ? html`
          ${history.map((h, i) => html`<div key=${i} class="newsline">${h}</div>`)}
        ` : html`
          <p class="pf-empty muted">No paper trail — a newcomer to the scene.</p>
        `}
      </div>
    </div>
  `;
};

const ManagerProfile = ({ career }) => {
  const c = career || {};
  const initial = (c.name || "?").charAt(0).toUpperCase();

  const meta = [
    c.archetype ? html`<span class="pill" key="arch">${esc(humanize(c.archetype))}</span>` : "",
    c.team_id && c.team_name
      ? html`<span class="tlink" data-tid=${c.team_id} key="team">${c.team_name}</span>`
      : html`<span class="pill" key="noclub">between clubs</span>`,
  ].filter(Boolean);

  const conBits = [];
  const con = c.contract;
  if (con) {
    if (con.goal) {
      const st = con.goal_status && con.goal_status.state;
      conBits.push(`Board goal: ${esc(con.goal)}` + (st ? ` (${esc(String(st).replace(/_/g, " "))})` : ""));
    }
    if (con.patience != null) conBits.push(`patience ${pfNum(con.patience)}`);
    if (con.seasons != null && con.start_season != null) {
      conBits.push(`S${con.start_season}–S${con.start_season + con.seasons - 1}`);
    }
  }

  const titles = (c.titles || []).filter(Boolean);
  const rep = c.reputation || {};
  const timeline = (c.timeline || []).slice().reverse();

  return html`
    <div>
      <div class="pf-header">
        <span class="pf-portrait pf-portrait-blank pf-staff-initial">${initial}</span>
        <div class="pf-id">
          <div class="pf-handle">${esc(c.name ?? "Manager")}</div>
          <div class="pf-meta">${meta}</div>
          <div class="pf-contract muted">${conBits.length ? conBits.join(" · ") : "No active contract"}</div>
        </div>
      </div>

      <div class="pf-tiles">
        <div class="pf-tile">
          <div class="pf-tile-val mono">${pfNum(titles.length)}</div>
          <div class="pf-tile-label">Titles</div>
        </div>
        <div class="pf-tile">
          <div class="pf-tile-val mono">${pfNum(c.players_developed)}</div>
          <div class="pf-tile-label">Developed</div>
        </div>
        <div class="pf-tile">
          <div class="pf-tile-val mono">${pfNum(c.debuts_given)}</div>
          <div class="pf-tile-label">Debuts</div>
        </div>
        <div class="pf-tile">
          <div class="pf-tile-val mono">${pfNum(c.signings)}</div>
          <div class="pf-tile-label">Signings</div>
        </div>
      </div>

      ${Object.keys(rep).length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Reputation</h3>
          <div class="pf-attrs">
            ${Object.entries(rep).map(([axis, val]) => html`
              <div class="pf-attr" key=${axis}>
                <span class="pf-attr-label">${esc(humanize(axis))}</span>
                <span class="pf-attr-bar"><${PfBar} value=${val} /></span>
                <span class="pf-attr-val mono">${pfNum(val)}</span>
              </div>
            `)}
          </div>
        </div>
      `}

      ${c.known_for && c.known_for.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Known for</h3>
          <div class="pf-chips">
            ${c.known_for.map((x, i) => html`<span class="pf-chip" key=${i}>${esc(x?.name || x)}</span>`)}
          </div>
        </div>
      `}

      ${c.philosophies && c.philosophies.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Philosophy</h3>
          <div class="pf-chips">
            ${c.philosophies.map((x, i) => html`<span class="pf-chip" key=${i}>${esc(x?.name || x)}</span>`)}
          </div>
        </div>
      `}

      ${titles.length > 0 && html`
        <div class="pf-section">
          <h3 class="pf-section-title">Honours (${titles.length})</h3>
          ${titles.map((h, i) => html`<div class="pf-honor" key=${i}>★ ${esc(h)}</div>`)}
        </div>
      `}

      <div class="pf-section">
        <h3 class="pf-section-title">Timeline</h3>
        ${timeline.length > 0 ? html`
          <div class="card-scroll" style=${{ "--scroll-max": "40vh" }}>
            ${timeline.map((e, i) => html`
              <div key=${i} class=${`newsline pf-tl-${e.kind || 'event'}`}>
                <span class="mono muted">S${e.season}·W${e.week}</span> ${esc(e.text)}
              </div>
            `)}
          </div>
        ` : html`
          <p class="pf-empty muted">No landmark moments yet — the chronicle is waiting.</p>
        `}
      </div>
    </div>
  `;
};

/* -- Actions & Assignments ------------------------------------------------- */

async function pfChangeAssignment(p) {
  const roles = ["duelist", "controller", "initiator", "sentinel", "flex"];
  const styles = ["entry", "igl", "anchor", "lurker", "awper", "support"];
  const role = window.prompt(`Role (${roles.join(", ")})`, p.role || "");
  if (role == null) return;
  const style = window.prompt(`Style (${styles.join(", ")})`, p.playstyle || "");
  if (style == null) return;
  const normalizedRole = role.trim().toLowerCase();
  const normalizedStyle = style.trim().toLowerCase();
  if (!roles.includes(normalizedRole) || !styles.includes(normalizedStyle)) {
    toast("Choose one of the listed roles and styles.");
    return;
  }
  try {
    const res = await api("/api/actions/assignment", {
      player_id: p.id, role: normalizedRole, playstyle: normalizedStyle,
    });
    toast(res.message || "Assignment updated.");
    openPlayerProfile(p.id);
  } catch {}
}

async function pfAssignIgl(p) {
  if (!window.confirm(`Make ${p.handle || "this player"} the team's IGL? Their calling experience will build only in matches they play.`)) return;
  try {
    const res = await api("/api/actions/igl", { player_id: p.id });
    toast(res.message || "IGL updated.");
    openPlayerProfile(p.id);
  } catch {}
}

/* -- overlay plumbing ------------------------------------------------------- */

let pfOverlayEl = null;
let pfSeq = 0;
const pfStack = [];
let pfCurrent = null; // {kind, id[, career]} currently showing (or loading)

function pfNavTo(entry, opts) {
  const replace = !!(opts && opts.replace);
  const same = pfCurrent && pfCurrent.kind === entry.kind
    && String(pfCurrent.id) === String(entry.id);
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
  ov.addEventListener("click", (e) => { if (e.target === ov) closeProfile(); });
  ov.querySelector(".pf-close").addEventListener("click", closeProfile);
  ov.querySelector(".pf-back").addEventListener("click", pfGoBack);
  document.body.appendChild(ov);
  pfOverlayEl = ov;
  return ov;
}

function pfShow(vnode) {
  const ov = pfEnsureOverlay();
  const body = ov.querySelector("#profile-body");
  render(vnode, body);
  ov.querySelector(".pf-back").classList.toggle("hidden", !pfStack.length);
  body.scrollTop = 0;
  ov.classList.remove("hidden");
}

function closeProfile() {
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
  pfShow(html`<${ProfileLoading} />`);
  const data = await profileFetch(`/api/players/${encodeURIComponent(pid)}/profile`);
  if (seq !== pfSeq || !isProfileOpen()) return;
  if (data) {
    pfShow(html`<${PlayerProfile} data=${data} />`);
  } else {
    pfShow(html`<${Unavailable} />`);
  }
}

async function openTeamProfile(tid, opts) {
  if (tid == null) return;
  const seq = pfNavTo({ kind: "team", id: tid }, opts);
  pfShow(html`<${ProfileLoading} />`);
  const data = await profileFetch(`/api/teams/${encodeURIComponent(tid)}/profile`);
  if (seq !== pfSeq || !isProfileOpen()) return;
  if (data) {
    pfShow(html`<${TeamProfile} data=${data} />`);
  } else {
    pfShow(html`<${Unavailable} />`);
  }
}

async function openStaffProfile(sid, opts) {
  if (sid == null) return;
  const seq = pfNavTo({ kind: "staff", id: sid }, opts);
  pfShow(html`<${ProfileLoading} />`);
  const data = await profileFetch(`/api/staff/${encodeURIComponent(sid)}/profile`);
  if (seq !== pfSeq || !isProfileOpen()) return;
  if (data) {
    pfShow(html`<${StaffProfile} data=${data} />`);
  } else {
    pfShow(html`<${Unavailable} />`);
  }
}

window.openManagerProfile = (career, opts) => {
  if (!career) return;
  pfNavTo({ kind: "manager", id: career.id || "me", career }, opts);
  pfShow(html`<${ManagerProfile} career=${career} />`);
};

async function pfReopenManager(entry) {
  const seq = pfNavTo(entry, { replace: true });
  pfShow(html`<${ProfileLoading} />`);
  const data = await profileFetch("/api/career");
  if (seq !== pfSeq || !isProfileOpen()) return;
  const payload = data || entry.career;
  if (payload) {
    pfShow(html`<${ManagerProfile} career=${payload} />`);
  } else {
    pfShow(html`<${Unavailable} />`);
  }
}

/* -- one delegated listener for the whole app ------------------------------ */

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

/* -- admin data-correction toggle ------------------------------------------- */

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
    if (isProfileOpen()) closeProfile();
  };
})();

// Module Bridge / Exports to Window
window.openPlayerProfile = openPlayerProfile;
window.openTeamProfile = openTeamProfile;
window.openStaffProfile = openStaffProfile;
window.closeProfile = closeProfile;
window.isProfileOpen = isProfileOpen;
window.isAdminMode = isAdminMode;
