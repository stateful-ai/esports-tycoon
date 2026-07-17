/* audio.js — first audio: the main theme.
   (The office ambiance track retired with the parked office screen — no tab
   plays it any more.) Self-contained: no edits to app.js. */
(function () {
  "use strict";

  var STORE_KEY = "es-audio";

  var theme = new Audio("/assets/audio/main_theme.mp3");
  theme.loop = true;
  theme.volume = 0.25;
  theme.preload = "none";

  var enabled = false;

  function paint() {
    var btn = document.getElementById("audio-toggle");
    if (!btn) return;
    btn.textContent = enabled ? "🔊" : "🔇"; /* 🔊 / 🔇 */
    btn.title = enabled ? "Sound: on" : "Sound: off";
    btn.setAttribute("aria-pressed", enabled ? "true" : "false");
  }

  /* Reconcile playback with the enabled flag. Safe to call any time. */
  function sync() {
    if (enabled) {
      theme.play().catch(function () {
        /* Autoplay blocked (no user gesture yet) — silently fall back to off. */
        enabled = false;
        paint();
      });
    } else {
      theme.pause();
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
