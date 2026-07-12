/* Roster Studio. Draft state is local editor state; validation and compilation
   live on the server in registry/roster_workbench.py. */

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const clone = (value) => JSON.parse(JSON.stringify(value));

const Studio = {
  bundle: null,
  packs: [],
  doc: null,
  installedId: null,
  selectedKind: "team",
  selectedIndex: 0,
  selectedPlayer: 0,
  validation: null,
  dirty: false,
  timer: null,
};

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  $("#toast").appendChild(node);
  setTimeout(() => node.remove(), 3800);
}

async function request(path, options = {}) {
  const init = { method: options.method || "GET" };
  if (options.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

function normalizeDraft(raw) {
  const doc = clone(raw || {});
  doc.schema_version ??= 1;
  doc.id ??= "my-roster-pack";
  doc.name ??= "My Roster Pack";
  doc.description ??= "";
  doc.world ??= {};
  doc.world.league_regions ??= ["americas", "emea", "pacific"];
  doc.world.teams_per_region ??= 8;
  doc.world.tier2_per_region ??= 4;
  doc.teams = Array.isArray(doc.teams) ? doc.teams : [];
  doc.free_agents = Array.isArray(doc.free_agents) ? doc.free_agents : [];
  for (const team of doc.teams) {
    team.players = Array.isArray(team.players) ? team.players : [];
    team.partial ??= false;
  }
  return doc;
}

function playerDefaults(igl = false) {
  return {
    handle: "new-player", real_name: "", age: 20, country: "",
    languages: [{ lang: "en", level: 100 }], role: igl ? "controller" : "flex",
    playstyle: igl ? "igl" : "support", igl, quality: 60, agents: [],
    attr_overrides: {},
  };
}

function setDirty() {
  Studio.dirty = true;
  localStorage.setItem("roster-studio-draft", JSON.stringify(Studio.doc));
  paintSaveState();
  clearTimeout(Studio.timer);
  Studio.timer = setTimeout(validate, 260);
}

function paintSaveState() {
  const chip = $("#save-state");
  chip.className = "status-chip";
  if (!Studio.doc) {
    chip.textContent = "No pack loaded";
    return;
  }
  if (Studio.dirty) {
    chip.textContent = "Draft changes";
    chip.classList.add("dirty");
  } else {
    chip.textContent = Studio.installedId ? "Installed" : "Draft";
    chip.classList.add("saved");
  }
}

function options(values, selected) {
  return values.map((value) =>
    `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(value)}</option>`
  ).join("");
}

function download(text, filename, type = "application/json") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function refreshPacks() {
  const response = await request("/api/roster-studio/packs");
  Studio.packs = response.packs;
  renderPackList();
}

function renderPackList() {
  const list = $("#pack-list");
  list.innerHTML = Studio.packs.map((pack) => `
    <button class="pack-item${Studio.installedId === pack.id ? " active" : ""}" data-pack="${esc(pack.id)}">
      <b>${esc(pack.name)}</b>
      <span>${esc(pack.regions.join(" / "))} - ${pack.teams_per_region} per region</span>
    </button>
  `).join("") || '<p class="muted">No installed packs yet.</p>';
  for (const button of list.querySelectorAll("[data-pack]")) {
    button.onclick = () => loadPack(button.dataset.pack);
  }
}

async function loadPack(packId) {
  if (Studio.dirty && !confirm("Open another pack and replace the current local draft?")) return;
  try {
    const response = await request(`/api/roster-studio/packs/${encodeURIComponent(packId)}`);
    openDocument(response.document, packId, false);
  } catch (error) {
    toast(error.message);
  }
}

function openDocument(raw, installedId = null, dirty = true) {
  Studio.doc = normalizeDraft(raw);
  Studio.installedId = installedId;
  Studio.selectedKind = "team";
  Studio.selectedIndex = 0;
  Studio.selectedPlayer = 0;
  Studio.dirty = dirty;
  $("#empty-state").classList.add("hidden");
  $("#editor").classList.remove("hidden");
  renderAll();
  validate();
}

function renderAll() {
  renderPackList();
  renderMeta();
  renderEntities();
  renderDetail();
  paintSaveState();
  $("#draft-btn").disabled = !Studio.doc;
  $("#export-btn").disabled = !Studio.installedId;
}

function renderMeta() {
  const doc = Studio.doc;
  $("#meta-id").value = doc.id || "";
  $("#meta-name").value = doc.name || "";
  $("#meta-description").value = doc.description || "";
  $("#meta-regions").value = (doc.world.league_regions || []).join(", ");
  $("#meta-t1").value = doc.world.teams_per_region ?? 8;
  $("#meta-t2").value = doc.world.tier2_per_region ?? 4;
  const bind = (selector, apply, event = "input") => {
    $(selector)[`on${event}`] = (e) => { apply(e.target.value); setDirty(); };
  };
  bind("#meta-id", (v) => { doc.id = v; });
  bind("#meta-name", (v) => { doc.name = v; });
  bind("#meta-description", (v) => { doc.description = v; });
  bind("#meta-t1", (v) => { doc.world.teams_per_region = Number(v); });
  bind("#meta-t2", (v) => { doc.world.tier2_per_region = Number(v); });
  bind("#meta-regions", (v) => {
    doc.world.league_regions = v.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
    renderEntities();
    renderDetail();
  }, "change");
}

function renderEntities() {
  const grouped = new Map();
  for (const region of Studio.doc.world.league_regions || []) grouped.set(region, []);
  Studio.doc.teams.forEach((team, index) => {
    if (!grouped.has(team.region)) grouped.set(team.region || "unassigned", []);
    grouped.get(team.region || "unassigned").push([team, index]);
  });
  const html = [];
  for (const [region, teams] of grouped) {
    html.push(`<div class="region-label">${esc(region)}</div>`);
    for (const [team, index] of teams) {
      const active = Studio.selectedKind === "team" && Studio.selectedIndex === index;
      html.push(`
        <button class="entity-item${active ? " active" : ""}" data-team-index="${index}">
          <b>${esc(team.name || "Untitled team")}</b>
          <span>${esc(team.tag || "---")} - Tier ${esc(team.tier ?? 1)} - ${(team.players || []).length}/5 players</span>
        </button>
      `);
    }
  }
  $("#entity-list").innerHTML = html.join("");
  for (const button of $("#entity-list").querySelectorAll("[data-team-index]")) {
    button.onclick = () => {
      Studio.selectedKind = "team";
      Studio.selectedIndex = Number(button.dataset.teamIndex);
      Studio.selectedPlayer = 0;
      renderEntities();
      renderDetail();
    };
  }
  const fa = $("#free-agents-nav");
  fa.className = `free-agent-nav${Studio.selectedKind === "free_agents" ? " active" : ""}`;
  fa.textContent = `Free agents (${Studio.doc.free_agents.length})`;
  fa.onclick = () => {
    Studio.selectedKind = "free_agents";
    Studio.selectedPlayer = 0;
    renderEntities();
    renderDetail();
  };
}

function renderDetail() {
  if (Studio.selectedKind === "free_agents") renderFreeAgents();
  else renderTeam();
}

function renderTeam() {
  const panel = $("#detail-panel");
  const team = Studio.doc.teams[Studio.selectedIndex];
  if (!team) {
    panel.innerHTML = `
      <div class="empty-state"><h2>No team selected</h2><p>Add a team to begin.</p>
      <button id="detail-add-team" class="btn primary">Add team</button></div>`;
    $("#detail-add-team").onclick = addTeam;
    return;
  }
  const regions = Studio.doc.world.league_regions || [];
  panel.innerHTML = `
    <div class="detail-head">
      <div><span class="eyebrow">Team ${Studio.selectedIndex + 1}</span><h2>${esc(team.name || "Untitled team")}</h2></div>
      <div class="spacer"></div>
      <div class="detail-actions"><button id="duplicate-team" class="btn">Duplicate</button><button id="delete-team" class="btn danger">Delete</button></div>
    </div>
    <div class="form-grid">
      <label class="field span2"><span>Team name</span><input id="team-name" value="${esc(team.name || "")}"></label>
      <label class="field"><span>Tag</span><input id="team-tag" value="${esc(team.tag || "")}"></label>
      <label class="field"><span>Region</span><select id="team-region">${options(regions, team.region)}</select></label>
      <label class="field"><span>Tier</span><select id="team-tier">${options([1, 2], team.tier ?? 1)}</select></label>
      <label class="field"><span>Prestige</span><input id="team-prestige" type="number" min="1" max="99" value="${esc(team.prestige ?? 50)}"></label>
      <label class="field span2"><span>Partial research sheet</span><select id="team-partial">${options(["false", "true"], String(!!team.partial))}</select></label>
    </div>
    <div class="section-rule"><b>Starting five</b></div>
    <div id="player-strip" class="player-strip"></div>
    <div id="player-editor"></div>
  `;
  const bind = (selector, key, numeric = false) => {
    $(selector).oninput = (e) => {
      team[key] = numeric ? Number(e.target.value) : e.target.value;
      setDirty();
      if (key === "name" || key === "tag") renderEntities();
    };
  };
  bind("#team-name", "name");
  bind("#team-tag", "tag");
  bind("#team-region", "region");
  bind("#team-tier", "tier", true);
  bind("#team-prestige", "prestige", true);
  $("#team-partial").onchange = (e) => { team.partial = e.target.value === "true"; setDirty(); };
  $("#delete-team").onclick = () => {
    if (!confirm(`Delete ${team.name || "this team"}?`)) return;
    Studio.doc.teams.splice(Studio.selectedIndex, 1);
    Studio.selectedIndex = Math.max(0, Studio.selectedIndex - 1);
    Studio.selectedPlayer = 0;
    setDirty(); renderEntities(); renderDetail();
  };
  $("#duplicate-team").onclick = () => {
    const copy = clone(team);
    copy.name = `${copy.name} Copy`;
    Studio.doc.teams.splice(Studio.selectedIndex + 1, 0, copy);
    Studio.selectedIndex += 1;
    setDirty(); renderEntities(); renderDetail();
  };
  renderPlayerStrip(team.players, true);
}

function renderPlayerStrip(players, canAdd) {
  const strip = $("#player-strip");
  Studio.selectedPlayer = Math.min(Studio.selectedPlayer, Math.max(0, players.length - 1));
  strip.innerHTML = players.map((player, index) => `
    <button class="player-card${Studio.selectedPlayer === index ? " active" : ""}" data-player-index="${index}">
      <b>${esc(player.handle || "New player")}${player.igl ? " (IGL)" : ""}</b>
      <span>${esc(player.role || "flex")} - Q${esc(player.quality ?? 60)}</span>
    </button>
  `).join("") + (canAdd && players.length < 5 ? '<button id="add-player" class="player-card"><b>+ Add player</b><span>Fill this roster</span></button>' : "");
  for (const button of strip.querySelectorAll("[data-player-index]")) {
    button.onclick = () => {
      Studio.selectedPlayer = Number(button.dataset.playerIndex);
      renderPlayerStrip(players, canAdd);
    };
  }
  if ($("#add-player")) {
    $("#add-player").onclick = () => {
      players.push(playerDefaults(players.length === 0));
      Studio.selectedPlayer = players.length - 1;
      setDirty(); renderEntities(); renderPlayerStrip(players, canAdd);
    };
  }
  const editor = $("#player-editor");
  if (editor) {
    editor.innerHTML = players.length ? playerForm(players[Studio.selectedPlayer], false) : '<p class="muted">Add a player to edit their profile.</p>';
    if (players.length) bindPlayerForm(players, Studio.selectedPlayer, false);
  }
}

function renderFreeAgents() {
  const panel = $("#detail-panel");
  const players = Studio.doc.free_agents;
  panel.innerHTML = `
    <div class="detail-head"><div><span class="eyebrow">Open market</span><h2>Free agents</h2></div><div class="spacer"></div><button id="add-fa" class="btn primary">Add free agent</button></div>
    <div id="player-strip" class="player-strip"></div><div id="player-editor"></div>
  `;
  $("#add-fa").onclick = () => {
    players.push({ ...playerDefaults(false), region: Studio.doc.world.league_regions[0] || "americas" });
    Studio.selectedPlayer = players.length - 1;
    setDirty(); renderEntities(); renderFreeAgents();
  };
  Studio.selectedPlayer = Math.min(Studio.selectedPlayer, Math.max(0, players.length - 1));
  const strip = $("#player-strip");
  strip.innerHTML = players.map((player, index) => `
    <button class="player-card${Studio.selectedPlayer === index ? " active" : ""}" data-player-index="${index}">
      <b>${esc(player.handle || "New player")}</b><span>${esc(player.region || "")} - Q${esc(player.quality ?? 60)}</span>
    </button>
  `).join("") || '<p class="muted">No free agents. Add notable unsigned players if you want them in the opening market.</p>';
  for (const button of strip.querySelectorAll("[data-player-index]")) {
    button.onclick = () => { Studio.selectedPlayer = Number(button.dataset.playerIndex); renderFreeAgents(); };
  }
  if (players.length) {
    $("#player-editor").innerHTML = playerForm(players[Studio.selectedPlayer], true);
    bindPlayerForm(players, Studio.selectedPlayer, true);
  }
}

function playerForm(player, isFreeAgent) {
  const catalog = Studio.bundle.catalog;
  const languages = (player.languages || []).map((x) => `${x.lang}:${x.level}`).join(", ");
  const attrs = Object.entries(player.attr_overrides || {}).map(([key, value]) => `${key}:${value}`).join(", ");
  const region = isFreeAgent ? `
    <label class="field"><span>Region</span><select id="player-region">${options(Studio.doc.world.league_regions || [], player.region)}</select></label>` : "";
  return `
    <div class="section-rule"><b>Player profile</b></div>
    <div class="form-grid">
      <label class="field"><span>Handle</span><input id="player-handle" value="${esc(player.handle || "")}"></label>
      <label class="field span2"><span>Real name</span><input id="player-real-name" value="${esc(player.real_name || "")}"></label>
      <label class="field"><span>Age</span><input id="player-age" type="number" min="14" max="45" value="${esc(player.age ?? 20)}"></label>
      ${region}
      <label class="field"><span>Country</span><input id="player-country" value="${esc(player.country || "")}" placeholder="US"></label>
      <label class="field"><span>Role</span><select id="player-role">${options(catalog.roles, player.role)}</select></label>
      <label class="field"><span>Playstyle</span><select id="player-style">${options(catalog.playstyles, player.playstyle)}</select></label>
      <label class="field"><span>Quality</span><input id="player-quality" type="number" min="1" max="99" value="${esc(player.quality ?? 60)}"></label>
      <label class="field"><span>IGL</span><select id="player-igl">${options(["false", "true"], String(!!player.igl))}</select></label>
      <label class="field span2"><span>Signature agents (comma separated)</span><input id="player-agents" class="mono" value="${esc((player.agents || []).join(", "))}" placeholder="jett, raze"></label>
      <label class="field span2"><span>Languages (code:level)</span><input id="player-languages" class="mono" value="${esc(languages)}" placeholder="en:100, es:70"></label>
      <label class="field span4"><span>Attribute overrides (optional id:value)</span><input id="player-attrs" class="mono" value="${esc(attrs)}" placeholder="aim_precision:90, game_sense:75"></label>
    </div>
    <div class="detail-actions" style="margin-top:16px"><button id="delete-player" class="btn danger">Remove player</button></div>
  `;
}

function parsePairs(value, objectMode = false) {
  if (!value.trim()) return objectMode ? {} : [];
  const pairs = value.split(",").map((part) => part.trim()).filter(Boolean).map((part) => {
    const [key, raw] = part.split(":").map((x) => x.trim());
    if (!key || raw === undefined || Number.isNaN(Number(raw))) throw new Error(`Use id:value pairs; could not read '${part}'`);
    return [key, Number(raw)];
  });
  return objectMode ? Object.fromEntries(pairs) : pairs.map(([lang, level]) => ({ lang, level }));
}

function bindPlayerForm(players, index, isFreeAgent) {
  const player = players[index];
  const bind = (selector, key, numeric = false) => {
    $(selector).oninput = (e) => {
      player[key] = numeric ? Number(e.target.value) : e.target.value;
      setDirty();
      if (key === "handle" || key === "quality") renderEntities();
    };
  };
  bind("#player-handle", "handle");
  bind("#player-real-name", "real_name");
  bind("#player-age", "age", true);
  bind("#player-country", "country");
  bind("#player-role", "role");
  bind("#player-style", "playstyle");
  bind("#player-quality", "quality", true);
  if (isFreeAgent) bind("#player-region", "region");
  $("#player-igl").onchange = (e) => { player.igl = e.target.value === "true"; setDirty(); };
  $("#player-agents").onchange = (e) => {
    player.agents = e.target.value.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
    setDirty();
  };
  $("#player-languages").onchange = (e) => {
    try { player.languages = parsePairs(e.target.value); setDirty(); }
    catch (error) { toast(error.message); }
  };
  $("#player-attrs").onchange = (e) => {
    try { player.attr_overrides = parsePairs(e.target.value, true); setDirty(); }
    catch (error) { toast(error.message); }
  };
  $("#delete-player").onclick = () => {
    players.splice(index, 1);
    Studio.selectedPlayer = Math.max(0, index - 1);
    setDirty(); renderEntities(); renderDetail();
  };
}

function addTeam() {
  Studio.doc.teams.push({
    name: "New Team", tag: "NEW", region: Studio.doc.world.league_regions[0] || "americas",
    tier: 1, prestige: 50, partial: false, players: [],
  });
  Studio.selectedKind = "team";
  Studio.selectedIndex = Studio.doc.teams.length - 1;
  Studio.selectedPlayer = 0;
  setDirty(); renderEntities(); renderDetail();
}

async function validate() {
  if (!Studio.doc) return;
  try {
    Studio.validation = await request("/api/roster-studio/validate", { method: "POST", body: Studio.doc });
    renderValidation();
  } catch (error) {
    toast(error.message);
  }
}

function renderValidation() {
  const result = Studio.validation;
  const dot = $("#validity-dot");
  dot.className = `validity-dot ${result?.valid ? "ok" : "bad"}`;
  const summary = result?.summary;
  $("#summary").innerHTML = summary ? [
    [summary.tier1_teams, "Tier-1 teams"], [summary.tier2_teams, "Tier-2 teams"],
    [summary.players, "Rostered players"], [summary.free_agents, "Free agents"],
  ].map(([value, label]) => `<div class="summary-cell"><b>${esc(value)}</b><span>${esc(label)}</span></div>`).join("") : "";
  const messages = [];
  for (const error of result?.errors || []) messages.push(`<div class="validation-item"><b>${esc(error.path)}</b>${esc(error.message)}</div>`);
  for (const warning of result?.warnings || []) messages.push(`<div class="validation-item warn">${esc(warning)}</div>`);
  if (!messages.length) messages.push('<div class="validation-item" style="border-color:var(--es-color-fill-success-strong);background:var(--es-color-fill-success)">Ready to compile and install.</div>');
  $("#validation").innerHTML = messages.join("");
  $("#save-btn").disabled = !result?.valid;
}

async function save() {
  await validate();
  if (!Studio.validation?.valid) return toast("Fix the build-check errors before installing.");
  const button = $("#save-btn");
  button.disabled = true;
  button.textContent = "Compiling...";
  try {
    const result = await request(`/api/roster-studio/packs/${encodeURIComponent(Studio.doc.id)}`, {
      method: "PUT", body: Studio.doc,
    });
    Studio.installedId = Studio.doc.id;
    Studio.dirty = false;
    localStorage.removeItem("roster-studio-draft");
    Studio.validation = result;
    await refreshPacks();
    renderAll();
    renderValidation();
    toast("Roster pack installed. It is ready in the Play lobby.");
  } catch (error) {
    toast(error.message);
  } finally {
    button.textContent = "Save & install";
    button.disabled = !Studio.validation?.valid;
  }
}

function makeAiBrief() {
  return `${Studio.bundle.agent_instructions}\n\n` +
    `Useful endpoints while the game server is running:\n` +
    `- GET /api/roster-studio/schema\n- POST /api/roster-studio/validate\n` +
    `- PUT /api/roster-studio/packs/{id}\n\n` +
    `Current RosterPackDocument (return the complete edited document):\n` +
    `${JSON.stringify(Studio.doc || Studio.bundle.example, null, 2)}\n`;
}

async function importFile(file) {
  try {
    const response = await request("/api/roster-studio/parse", {
      method: "POST", body: { text: await file.text() },
    });
    openDocument(response.document, null, true);
    Studio.validation = response.validation;
    renderValidation();
    toast(response.validation.valid ? "File loaded and ready." : "File loaded with issues to fix.");
  } catch (error) {
    toast(error.message);
  }
}

async function boot() {
  try {
    Studio.bundle = await request("/api/roster-studio/schema");
    await refreshPacks();
    const requested = new URLSearchParams(location.search).get("pack");
    const local = localStorage.getItem("roster-studio-draft");
    if (requested) await loadPack(requested);
    else if (local) openDocument(JSON.parse(local), null, true);
  } catch (error) {
    toast(error.message);
  }
}

$("#new-btn").onclick = $("#empty-new").onclick = () => {
  if (Studio.dirty && !confirm("Replace the current local draft?")) return;
  openDocument(Studio.bundle.example, null, true);
};
$("#add-team").onclick = addTeam;
$("#save-btn").onclick = save;
$("#import-btn").onclick = () => $("#file-input").click();
$("#file-input").onchange = (event) => {
  if (event.target.files[0]) importFile(event.target.files[0]);
  event.target.value = "";
};
$("#draft-btn").onclick = () => download(
  JSON.stringify(Studio.doc, null, 2) + "\n",
  `${Studio.doc?.id || "roster-pack"}.roster-pack.json`
);
$("#export-btn").onclick = () => {
  if (Studio.installedId) location.href = `/api/roster-studio/packs/${encodeURIComponent(Studio.installedId)}/export`;
};
$("#schema-btn").onclick = () => download(
  JSON.stringify(Studio.bundle, null, 2) + "\n", "roster-pack-schema.json"
);
$("#ai-brief").onclick = () => {
  $("#ai-text").value = makeAiBrief();
  $("#ai-dialog").showModal();
};
$("#copy-ai").onclick = async () => {
  await navigator.clipboard.writeText($("#ai-text").value);
  toast("AI brief copied.");
};
window.addEventListener("beforeunload", (event) => {
  if (!Studio.dirty) return;
  event.preventDefault();
  event.returnValue = "";
});

boot();
