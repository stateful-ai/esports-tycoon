/* Guided tour — a spotlight walkthrough of the weekly loop.
 *
 * Presentation only. The tour navigates with dashGoTab (the same call the
 * first-week guide's "Open X" buttons use) and never reads or mutates game
 * state, so it cannot drift from the engine. Copy follows the weekly loop
 * described by the handbook.
 *
 * Launch: the "Take the tour" button in the first-week guide, or
 * window.startTour() from anywhere. Stores completion per world in localStorage.
 */
(function () {
  "use strict";

  function tourSeenKey() {
    // This classic script loads before app.js's module initializes window.App.
    const App = window.App || {};
    const world = (App.mp && App.mp.code) || (App.state && App.state.user_team && App.state.user_team.id) || "local";
    return `esports-sim:guided-tour:${world}`;
  }

  /* The weekly-loop steps. Each names a top-nav tab (via the same ids the
     first-week guide uses) plus the selector to spotlight on that screen.
     `target` is resolved AFTER navigating, so it can point at content the tab
     renders. Fall back to the nav button when a specific selector is absent. */
  const STEPS = [
    {
      tab: "dashboard",
      title: "Start on the Dashboard",
      body: "This is home base. The 'Needs you' card lists every decision waiting on you — start each week here.",
      target: "#view [data-tour-needs]",
      nav: true,
    },
    {
      tab: "inbox",
      title: "Clear the Inbox",
      body: "Actionable Items are decisions with deadlines — offers, contracts, urgent talks. The League Feed is context, not a to-do list.",
      nav: true,
    },
    {
      tab: "club",
      title: "Set your five",
      body: "Confirm the dressed five, check condition and confidence, and set training. A settled lineup plays above its ratings.",
      nav: true,
    },
    {
      tab: "tactics",
      title: "Prepare the match",
      body: "The Match tab is the single home for prep. Read the opponent report, then adjust only the dials you have a reason to change — 50 is always neutral.",
      nav: true,
    },
    {
      tab: "market",
      title: "Know your options",
      body: "Scout before you buy. Compare role, languages, ceiling, salary, and contract cost together — a higher OVR is not always a better fit.",
      nav: true,
    },
    {
      tab: "dashboard",
      title: "Advance when ready",
      body: "Review outstanding decisions, then use Advance when ready. In shared worlds, each manager must mark ready before the host advances.",
      target: "#advance-btn",
      advanceBtn: true,
    },
  ];

  let els = null;      // {backdrop, spot, card}
  let idx = 0;
  let active = false;
  let placementTimer = null;
  let opener = null;
  let viewObserver = null;

  function buildDom() {
    if (els) return els;
    const el = window.el || ((tag, cls, html) => {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (html != null) n.innerHTML = html;
      return n;
    });
    const backdrop = el("div"); backdrop.id = "tour-backdrop";
    const spot = el("div"); spot.id = "tour-spot";
    const card = el("div"); card.id = "tour-card"; card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-labelledby", "tour-title");
    card.setAttribute("aria-describedby", "tour-body");
    backdrop.hidden = spot.hidden = card.hidden = true;
    document.body.append(backdrop, spot, card);
    els = { backdrop, spot, card };
    // Click the dimmed area to end the tour.
    backdrop.addEventListener("click", () => endTour(false));
    return els;
  }

  function findTarget(step) {
    // Prefer an explicit on-screen target; else spotlight the nav button.
    if (step.target) {
      const t = document.querySelector(step.target);
      if (t && t.getBoundingClientRect().width > 0) return t;
    }
    const tabName = ({ match: "tactics" })[step.tab] || step.tab;
    return document.querySelector(`#tabs [data-tab="${tabName}"]`);
  }

  function place(step) {
    if (!active) return;
    const { spot, card } = els;
    const target = findTarget(step);
    const pad = 6;
    let r;
    if (target) {
      target.scrollIntoView({ block: "nearest", behavior: "instant" });
      r = target.getBoundingClientRect();
    } else {
      r = { left: innerWidth / 2 - 40, top: 90, width: 80, height: 40 };
    }
    spot.style.left = `${r.left - pad}px`;
    spot.style.top = `${r.top - pad}px`;
    spot.style.width = `${r.width + pad * 2}px`;
    spot.style.height = `${r.height + pad * 2}px`;

    // Card: below the spot if there's room, else above, clamped to viewport.
    const cw = Math.min(340, innerWidth - 32);
    const ch = card.offsetHeight || 170;
    let left = Math.max(12, Math.min(r.left, innerWidth - cw - 12));
    let top = r.top + r.height + pad + 12;
    if (top + ch > innerHeight - 12) top = Math.max(12, r.top - pad - ch - 12);
    card.style.left = `${left}px`;
    card.style.top = `${top}px`;
  }

  function render() {
    const { card } = els;
    const step = STEPS[idx];
    const last = idx === STEPS.length - 1;
    const dots = STEPS.map((_, i) => `<i class="${i === idx ? "on" : ""}"></i>`).join("");
    const esc = window.esc;
    card.innerHTML =
      `<div class="tour-kicker"><span class="tour-step-of">Step ${idx + 1} of ${STEPS.length}</span>` +
      `<span class="tour-dots">${dots}</span></div>` +
      `<h3 id="tour-title">${esc(step.title)}</h3><p id="tour-body">${esc(step.body)}</p>` +
      `<div class="tour-actions">` +
      `<button class="btn btn-sm" data-tour="skip">Skip tour</button>` +
      `<span class="spacer"></span>` +
      (idx > 0 ? `<button class="btn btn-sm" data-tour="back">Back</button>` : "") +
      `<button class="btn btn-sm btn-primary" data-tour="next">${last ? "Finish" : "Next ▸"}</button>` +
      `</div>`;
    card.querySelector('[data-tour="skip"]').onclick = () => endTour(false);
    const back = card.querySelector('[data-tour="back"]');
    if (back) back.onclick = () => go(idx - 1);
    card.querySelector('[data-tour="next"]').onclick = () => (last ? endTour(true) : go(idx + 1));
    card.querySelector('[data-tour="next"]').focus({ preventScroll: true });
  }

  function go(n) {
    idx = Math.max(0, Math.min(n, STEPS.length - 1));
    const step = STEPS[idx];
    // Navigate to the step's tab (sub-tab resolved via TAB_ALIASES inside
    // dashGoTab), then place the spotlight once the render has settled.
    if (window.dashGoTab) window.dashGoTab(step.tab);
    render();
    // Let the tab render + smooth scroll settle before measuring the target.
    clearTimeout(placementTimer);
    placementTimer = setTimeout(() => { if (active && STEPS[idx] === step) place(step); }, 120);
  }

  function startTour() {
    if (active) return;
    if (!window.App || !window.esc || !window.dashGoTab) return;
    // The handbook can launch this tour; another modal retains its keyboard
    // ownership until its user closes it.
    if (document.querySelector('.overlay:not(.hidden):not(#help)')) return;
    opener = document.activeElement;
    // Close the handbook if it's open so the tour owns the modal layer.
    if (window.closeHelp) window.closeHelp();
    buildDom();
    active = true;
    els.backdrop.hidden = els.spot.hidden = els.card.hidden = false;
    els.backdrop.classList.add("on");
    go(0);
    const view = document.getElementById("view");
    if (view) {
      // Screens populate asynchronously; remeasure when the live target arrives.
      viewObserver = new MutationObserver(() => { if (active) place(STEPS[idx]); });
      viewObserver.observe(view, { childList: true, subtree: true });
    }
    window.addEventListener("resize", onResize);
    document.addEventListener("keydown", onKey, true);
  }

  function endTour(completed) {
    if (!active) return;
    active = false;
    clearTimeout(placementTimer);
    viewObserver?.disconnect();
    viewObserver = null;
    els.backdrop.classList.remove("on");
    els.backdrop.hidden = els.spot.hidden = els.card.hidden = true;
    window.removeEventListener("resize", onResize);
    document.removeEventListener("keydown", onKey, true);
    if (completed === true) { try { localStorage.setItem(tourSeenKey(), "1"); } catch (_e) {} }
    const restore = opener?.isConnected && !opener.closest('.hidden, [hidden]')
      ? opener : document.getElementById("help-open");
    restore?.focus({ preventScroll: true });
    opener = null;
  }

  function onResize() { if (active) place(STEPS[idx]); }
  function onKey(e) {
    if (!active) return;
    if (!["Escape", "ArrowRight", "ArrowLeft", "Tab"].includes(e.key)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (e.key === "Escape") endTour(false);
    else if (e.key === "ArrowRight") idx === STEPS.length - 1 ? endTour(true) : go(idx + 1);
    else if (e.key === "ArrowLeft") go(idx - 1);
    else {
      const controls = [...els.card.querySelectorAll("button")];
      const current = controls.indexOf(document.activeElement);
      const next = current < 0 ? (e.shiftKey ? controls.length - 1 : 0)
        : (current + (e.shiftKey ? -1 : 1) + controls.length) % controls.length;
      controls[next]?.focus({ preventScroll: true });
    }
  }

  window.startTour = startTour;
  window.endTour = endTour;
  window._tour = { get active() { return active; }, get idx() { return idx; }, STEPS };
})();
