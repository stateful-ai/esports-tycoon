/* Local, best-effort sidecar only. No bodies, query strings, text or credentials. */
(() => {
  const pageId = Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2, "0")).join("");
  let queue = [], serial = 0, current = "", since = performance.now(), pending = null;
  const emit = (event) => { if (queue.length < 128) queue.push(event); };
  async function flush() {
    if (pending) return pending;
    if (!queue.length) return;
    const events = queue.splice(0, 32);
    pending = (async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 500);
      try {
        // Raw fetch bypasses api(), so telemetry never instruments itself.
        await fetch("/api/usage/events", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({page_id: pageId, events}), keepalive: true, signal: controller.signal});
      } catch (_) { /* Dropped telemetry must never interrupt play. */ }
      finally { clearTimeout(timeout); }
    })();
    try { await pending; } finally { pending = null; }
  }
  async function boundary() {
    dwell();
    await flush();
    // At most four queued batches, each with a 500ms deadline; never retry.
    for (let n = 0; n < 4 && queue.length; n++) await flush();
  }
  function dwell() {
    const now = performance.now();
    if (current && !document.hidden) emit({kind: "visible_time", target: current,
      duration_ms: Math.min(60000, Math.max(0, Math.round(now - since)))});
    since = now;
  }
  function view(target) {
    if (target === current) return;
    dwell(); current = target;
    emit({kind: "view", target});
  }
  function request(path, mutation) {
    const parts = path.split("?")[0].split("/");
    const target = parts.slice(0, parts[2] === "actions" ? 4 : 3).join("/");
    if (!target.startsWith("/api/") || target.startsWith("/api/usage")) return null;
    const token = {target, id: ++serial, start: performance.now(), mutation};
    if (mutation) emit({kind: "attempt", target, request_id: token.id});
    return token;
  }
  function result(token, outcome, status) {
    if (!token || (!token.mutation && outcome === "success")) return;
    // Read failures get an attempt too, preserving pairing without logging polling reads.
    if (!token.mutation) emit({kind: "attempt", target: token.target, request_id: token.id});
    const event = {kind: "result", target: token.target, request_id: token.id, outcome,
      duration_ms: Math.min(3600000, Math.max(0, Math.round(performance.now()-token.start)))};
    if (status) event.status = status;
    emit(event);
    void flush();
  }
  let replayReturn = "";
  function replay(target) {
    emit({kind: "replay", target});
    if (target === "open") { replayReturn = current; view("replay"); }
    if (target === "close") view(replayReturn || "dashboard");
  }
  const interactions = new Set(["lobby/seed_change", "week/full_report_open",
    ...["player", "team", "staff", "manager"].flatMap(kind =>
      ["open", "close"].map(action => `profile/${kind}_${action}`)),
    "handbook/open", "handbook/close", "handbook/section_first_week",
    "handbook/section_screens", "handbook/section_glossary"]);
  function interaction(target) {
    if (interactions.has(target)) emit({kind: "interaction", target});
  }
  window.Usage = {view, request, result, boundary, replay, interaction, flush};
  emit({kind: "session_start"}); view("lobby");
  setInterval(() => { dwell(); void flush(); }, 15000);
  document.addEventListener("visibilitychange", () => {
    // visibilitychange fires after hidden is set; explicitly finish the visible slice.
    const now = performance.now();
    if (document.hidden && current) emit({kind: "visible_time", target: current,
      duration_ms: Math.min(60000, Math.max(0, Math.round(now-since)))});
    since = now;
    void flush();
  });
  window.addEventListener("pagehide", () => { dwell(); emit({kind: "session_end"}); void flush(); });
})();
