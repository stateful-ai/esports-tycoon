/* Menu-based facility upgrades. All benefits, costs, and availability are
   server-computed; this file only presents the /api/facilities contract. */

function facilityEffects(effects, next = false) {
  return (effects ?? []).map((effect) => `
    <div class="facility-benefit${next ? " next" : ""}" title="${esc(effect.detail)}">
      <div>
        <b>${esc(effect.label)}</b>
        <small>${esc(effect.detail)}</small>
      </div>
      <strong>${esc(effect.value)}</strong>
    </div>`).join("");
}

function facilityLevelPips(facility) {
  return Array.from({ length: facility.max_level }, (_, index) =>
    `<i class="${index < facility.level ? "on" : ""}"></i>`
  ).join("");
}

function facilityOperator(facility) {
  const who = facility.operator
    ? slink(facility.operator.id, facility.operator.name)
    : esc(facility.operator_detail);
  const score = facility.operator
    ? `<span class="mono">${facility.operator.effectiveness}</span>`
    : "";
  return `
    <div class="facility-operator">
      <span><small>${esc(facility.operator_label)}</small>${who}</span>
      ${score}
    </div>`;
}

function facilityCard(facility) {
  const card = el("article", "card facility-card");
  card.dataset.facility = facility.id;
  card.innerHTML = `
    <div class="facility-card-head">
      <div>
        <span class="microlabel">${esc(facility.status)}</span>
        <h2>${esc(facility.label)}</h2>
        <span class="facility-level-name">${esc(facility.level_name)}</span>
      </div>
      <div class="facility-level-badge">
        <strong class="mono">${facility.level}</strong><span>/${facility.max_level}</span>
      </div>
    </div>
    <div class="facility-level-pips">${facilityLevelPips(facility)}</div>
    <p class="facility-description">${esc(facility.description)}</p>
    ${facilityOperator(facility)}
    <section class="facility-benefits">
      <span class="microlabel">Current benefits</span>
      ${facilityEffects(facility.current_effects)}
    </section>
    ${facility.maxed ? `
      <div class="facility-maxed">
        <b>Fully developed</b>
        <span>${money(facility.current_upkeep)}/wk upkeep</span>
      </div>
    ` : `
      <section class="facility-next">
        <div class="facility-next-head">
          <span class="microlabel">Next upgrade</span>
          <b>L${facility.next_level} · ${esc(facility.next_level_name)}</b>
        </div>
        ${facilityEffects(facility.next_effects, true)}
      </section>
      <div class="facility-upgrade-row">
        <span>
          <b>${money(facility.next_cost)}</b>
          <small>${money(facility.next_upkeep)}/wk total upkeep</small>
        </span>
        <button class="btn btn-primary facility-upgrade" ${facility.affordable ? "" : "disabled"}>
          ${facility.level ? "Upgrade" : "Build"}
        </button>
      </div>
      ${facility.affordable ? "" : `<small class="facility-shortfall">Insufficient funds for this project.</small>`}
    `}`;

  const upgrade = card.querySelector(".facility-upgrade");
  if (upgrade) {
    upgrade.onclick = async () => {
      upgrade.disabled = true;
      upgrade.textContent = "Building...";
      try {
        const result = await api("/api/actions/facility_upgrade", {
          facility: facility.id,
        });
        toast(result.message);
        await refresh();
      } catch (error) {
        upgrade.disabled = false;
        upgrade.textContent = facility.level ? "Upgrade" : "Build";
      }
    };
  }
  return card;
}

async function facilitiesScreen(v) {
  v.innerHTML = `<div class="loading">Loading facilities...</div>`;
  const data = await api("/api/facilities");
  v.innerHTML = "";
  v.appendChild(screenHead("Facilities", {
    sub: `${money(data.balance)} banked · ${money(data.total_upkeep)}/wk upkeep`,
  }));

  const intro = el("div", "card facilities-intro");
  intro.innerHTML = `
    <div>
      <span class="microlabel">Club infrastructure</span>
      <h2>Build the operation behind the team</h2>
      <p>Invest in permanent departments that strengthen development, analysis, recovery, wellbeing, and commercial growth. Every level raises weekly upkeep.</p>
    </div>
    <div class="facilities-summary">
      <span><b class="mono">${data.built_count}/${data.facilities.length}</b><small>built</small></span>
      <span><b class="mono">${data.total_levels}</b><small>total levels</small></span>
    </div>`;
  v.appendChild(intro);

  const grid = el("div", "facilities-grid");
  for (const facility of data.facilities) grid.appendChild(facilityCard(facility));
  v.appendChild(grid);
}

window.facilitiesScreen = facilitiesScreen;
