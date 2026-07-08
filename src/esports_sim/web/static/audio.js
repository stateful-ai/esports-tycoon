/* audio.js — first audio: main theme + office ambiance.
   Self-contained: no edits to app.js/office.js. Loaded after app.js so the
   `App` global (top-level const) is in scope for the initial tab check. */
(function () {
  "use strict";

  var STORE_KEY = "es-audio";

  var theme = new Audio("/assets/audio/main_theme.mp3");
  theme.loop = true;
  theme.volume = 0.25;
  theme.preload = "none";

  var ambiance = new Audio("/assets/audio/office_ambiance.mp3");
  ambiance.loop = true;
  ambiance.volume = 0.4;
  ambiance.preload = "none";

  var enabled = false;

  function activeTab() {
    try {
      if (typeof App !== "undefined" && App && typeof App.tab === "string") return App.tab;
    } catch (e) { /* App not defined yet */ }
    var b = document.querySelector("#tabs .tab.active");
    return b ? b.dataset.tab : null;
  }

  function paint() {
    var btn = document.getElementById("audio-toggle");
    if (!btn) return;
    btn.textContent = enabled ? "🔊" : "🔇"; /* 🔊 / 🔇 */
    btn.title = enabled ? "Sound: on" : "Sound: off";
    btn.setAttribute("aria-pressed", enabled ? "true" : "false");
  }

  /* Reconcile playback with (enabled, active tab). Safe to call any time. */
  function sync() {
    if (enabled) {
      theme.play().catch(function () {
        /* Autoplay blocked (no user gesture yet) — silently fall back to off. */
        enabled = false;
        ambiance.pause();
        paint();
      });
      if (activeTab() === "office") {
        ambiance.play().catch(function () {});
      } else {
        ambiance.pause();
      }
    } else {
      theme.pause();
      ambiance.pause();
    }
    paint();
  }

  function setEnabled(on, persist) {
    enabled = on;
    if (persist) {
      try { localStorage.setItem(STORE_KEY, on ? "on" : "off"); } catch (e) {}
    }
    sync();
  }

  /* Toggle button — the click is our autoplay-unlocking user gesture. */
  var toggle = document.getElementById("audio-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      setEnabled(!enabled, true);
    });
  }

  /* Tab changes: delegated click on #tabs ... */
  var tabs = document.getElementById("tabs");
  if (tabs) {
    tabs.addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest("[data-tab]")) {
        setTimeout(sync, 0); /* let app.js update App.tab first */
      }
    });
    /* ... plus a class observer, since app.js also switches tabs
       programmatically (e.g. office "go to roster" shortcuts). */
    if (window.MutationObserver) {
      new MutationObserver(function () { sync(); })
        .observe(tabs, { attributes: true, subtree: true, attributeFilter: ["class"] });
    }
  }

  /* Restore persisted preference; if the browser blocks autoplay the
     play() rejection above flips us back to the off state silently. */
  var stored = null;
  try { stored = localStorage.getItem(STORE_KEY); } catch (e) {}
  if (stored === "on") {
    setEnabled(true, false);
  } else {
    paint();
  }
})();
