/**
 * Map Studio visual editor script.
 */

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const humanize = (value) => String(value ?? "").trim().replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
const clone = (value) => JSON.parse(JSON.stringify(value));

const Editor = {
  maps: [],
  doc: null,          // Active MapStudioDocumentV1
  hash: null,         // If-Match source hash
  dirty: false,
  selectedTool: "select",
  isIso: false,       // 2D top-down vs 3D isometric toggle
  selectedItem: null, // { type: 'surface'|'zone'|'prop'|'link'|'player'|'wall', id: string, index: number }
  undoStack: [],
  redoStack: [],
  
  // Drawing temporary states
  drawingPoints: [],
  linkStart: null,
  dragState: null,    // { type, index, pointIndex, startX, startY }
  renderRequested: false, // Throttling helper
  
  // Probe states
  probePos: null,     // [x, y]
  probeRay: null,     // [x, y]
  probeResult: null,
  showOverlay: false,
  viewBox: null,      // Dynamic pan/zoom viewBox state
  panState: null,     // Mouse tracking for dynamic pan
  externalChangePending: false,
  pollingRevision: false,
  revisionTimer: null,
  snapStep: 0.5,
  showReference: true,
  referenceOpacity: 0.65,
  showRoutes: true,
  previewPlayers: {},
  previewTimer: null,
  previewGeneration: 0,
  floorComparison: null,
  comparisonGeneration: 0,
};

function toast(msg) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = msg;
  $("#toast").appendChild(node);
  setTimeout(() => node.remove(), 3000);
}

function requestErrorMessage(error, fallback = "Request failed") {
  const detail = error?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      const location = Array.isArray(item?.loc) ? item.loc.join(".") : "";
      const message = item?.msg || JSON.stringify(item);
      return `${location ? `${location}: ` : ""}${message}`;
    }).join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

async function request(path, options = {}) {
  const init = { method: options.method || "GET" };
  if (options.headers) init.headers = options.headers;
  if (options.body !== undefined) {
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    const requestError = new Error(requestErrorMessage(error, response.statusText));
    requestError.status = response.status;
    throw requestError;
  }
  return response.json();
}

function pushState() {
  stopPreview();
  clearFloorComparison();
  Editor.undoStack.push(JSON.stringify(Editor.doc));
  Editor.redoStack = [];
  Editor.dirty = true;
  paintSaveState();
}

function undo() {
  stopPreview();
  clearFloorComparison();
  if (document.activeElement && typeof document.activeElement.blur === "function") {
    document.activeElement.blur();
  }
  if (Editor.undoStack.length === 0) return;
  Editor.redoStack.push(JSON.stringify(Editor.doc));
  Editor.doc = JSON.parse(Editor.undoStack.pop());
  Editor.selectedItem = null;
  syncMetaFields();
  Editor.dirty = true;
  paintSaveState();
  renderCanvas();
  updateReferenceImage();
  updateInspector();
}

function redo() {
  stopPreview();
  clearFloorComparison();
  if (document.activeElement && typeof document.activeElement.blur === "function") {
    document.activeElement.blur();
  }
  if (Editor.redoStack.length === 0) return;
  Editor.undoStack.push(JSON.stringify(Editor.doc));
  Editor.doc = JSON.parse(Editor.redoStack.pop());
  Editor.selectedItem = null;
  syncMetaFields();
  Editor.dirty = true;
  paintSaveState();
  renderCanvas();
  updateReferenceImage();
  updateInspector();
}

function paintSaveState() {
  const chip = $("#save-state");
  chip.className = "status-chip";
  if (!Editor.doc) {
    chip.textContent = "No map open";
    return;
  }
  if (Editor.externalChangePending) {
    chip.textContent = "External changes";
    chip.classList.add("dirty");
    return;
  }
  if (Editor.dirty) {
    chip.textContent = "Unsaved changes";
    chip.classList.add("dirty");
  } else {
    chip.textContent = "Draft Saved";
    chip.classList.add("saved");
  }
}

function syncMetaFields() {
  if (!Editor.doc) return;
  $("#meta-name").value = Editor.doc.display_name;
  $("#meta-sites").value = (Editor.doc.sites || []).join(',');
  $("#meta-atk-spawn").value = Editor.doc.attacker_spawn;
  $("#meta-def-spawn").value = Editor.doc.defender_spawn;
}

// ---------------------------------------------------------------------------
// Canvas Projection & Event mapping

function getCanvasCoords(e) {
  const svg = $("#studio-canvas");
  const pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return [0, 0];
  const svgPt = pt.matrixTransform(ctm.inverse());
  const rawX = svgPt.x;
  const rawY = svgPt.y;
  
  if (Editor.isIso) {
    const x = (rawX + 2 * rawY) / 2;
    const y = rawX + 100 - x;
    return [x, y];
  } else {
    const x = rawX;
    const y = 100 - rawY;
    return [x, y];
  }
}

// ---------------------------------------------------------------------------
// Main UI Flow

async function initLibrary() {
  try {
    const res = await request("/api/map-studio/maps");
    Editor.maps = res.maps;
    paintMapList();
  } catch (err) {
    toast(`Failed to load maps list: ${err.message}`);
  }
}

function paintMapList() {
  const list = $("#map-list");
  list.innerHTML = Editor.maps.map(m => `
    <button class="pack-item ${Editor.doc && Editor.doc.id === m.id ? "active" : ""}" onclick="openMap('${esc(m.id)}')">
      <b>${esc(m.display_name)}</b>
      <span>ID: ${esc(m.id)} (${esc(m.status)})</span>
    </button>
  `).join("");
}

function closeOpenMap() {
  stopPreview();
  clearFloorComparison();
  Editor.doc = null;
  Editor.hash = null;
  Editor.dirty = false;
  Editor.externalChangePending = false;
  Editor.undoStack = [];
  Editor.redoStack = [];
  Editor.selectedItem = null;
  Editor.drawingPoints = [];
  Editor.linkStart = null;
  Editor.probePos = null;
  Editor.probeRay = null;
  Editor.probeResult = null;

  $("#editor").classList.add("hidden");
  $("#empty-state").classList.remove("hidden");
  $("#validate-btn").disabled = true;
  $("#preview-round-btn").disabled = true;
  $("#publish-btn").disabled = true;
  $("#delete-map-btn").disabled = true;
  $("#save-btn").disabled = true;
  $("#reload-btn").disabled = true;
  $("#hash-draft").textContent = "-";
  $("#hash-compiled").textContent = "-";
  $("#paint-status").textContent = "-";
  updateOverlayImage();
  paintMapList();
  paintSaveState();

  if (window.history?.replaceState && window.location) {
    const url = new URL(window.location.href);
    url.searchParams.delete("map");
    window.history.replaceState({}, "", url);
  }
}

async function openMap(mapId, options = {}) {
  stopPreview();
  clearFloorComparison();
  try {
    const preservedViewBox = options.preserveView ? clone(Editor.viewBox) : null;
    const res = await request(`/api/map-studio/maps/${encodeURIComponent(mapId)}`);
    Editor.doc = res.document;
    Editor.hash = res.hash;
    Editor.dirty = false;
    Editor.externalChangePending = false;
    Editor.undoStack = [];
    Editor.redoStack = [];
    Editor.selectedItem = null;
    
    $("#empty-state").classList.add("hidden");
    $("#editor").classList.remove("hidden");
    
    $("#meta-id").value = Editor.doc.id;
    $("#meta-name").value = Editor.doc.display_name;
    $("#meta-sites").value = (Editor.doc.sites || []).join(",");
    $("#meta-atk-spawn").value = Editor.doc.attacker_spawn || "attacker_spawn";
    $("#meta-def-spawn").value = Editor.doc.defender_spawn || "defender_spawn";

    // Keep library selections reloadable and shareable as the selected draft.
    if (window.history?.replaceState && window.location) {
      const url = new URL(window.location.href);
      url.searchParams.set("map", Editor.doc.id);
      window.history.replaceState({}, "", url);
    }
    
    // Enable top bar actions
    $("#validate-btn").disabled = false;
    $("#preview-round-btn").disabled = false;
    $("#publish-btn").disabled = false;
    $("#delete-map-btn").disabled = false;
    $("#save-btn").disabled = false;
    $("#reload-btn").disabled = true;
    
    // Update Art status
    $("#hash-draft").textContent = Editor.hash.substring(0, 8);
    $("#hash-compiled").textContent = "-";
    $("#paint-status").textContent = "unknown";
    
    Editor.drawingPoints = [];
    Editor.linkStart = null;
    Editor.dragState = null;
    // Initialize viewBox state
    if (preservedViewBox) {
      Editor.viewBox = preservedViewBox;
    } else if (Editor.isIso) {
      Editor.viewBox = { x: -110, y: -12, w: 220, h: 128 };
    } else {
      Editor.viewBox = { x: -6, y: -6, w: 112, h: 112 };
    }

    paintMapList();
    paintSaveState();
    renderCanvas();
    if (!preservedViewBox) fitMap();
    updateReferenceImage();
    updateInspector();
    
    if (Editor.showOverlay) {
      updateOverlayImage();
    }
    return true;
  } catch (err) {
    toast(`Failed to load map: ${err.message}`);
    return false;
  }
}

function markExternalChange() {
  if (!Editor.externalChangePending) {
    toast("This map changed outside the editor. Reload and reconcile before saving.");
  }
  Editor.externalChangePending = true;
  $("#reload-btn").disabled = false;
  paintSaveState();
}

async function checkExternalRevision() {
  if (!Editor.doc || Editor.pollingRevision) return;
  Editor.pollingRevision = true;
  const mapId = Editor.doc.id;
  try {
    const res = await request(`/api/map-studio/maps/${encodeURIComponent(mapId)}/revision`);
    if (!Editor.doc || Editor.doc.id !== mapId || res.hash === Editor.hash) return;
    if (Editor.dirty) {
      markExternalChange();
    } else {
      if (await openMap(mapId, { preserveView: true })) {
        toast("Reloaded external map changes.");
      }
    }
  } catch (err) {
    // A transient poll failure should not interrupt active editing.
  } finally {
    Editor.pollingRevision = false;
  }
}

async function reloadLatest() {
  if (!Editor.doc) return;
  if (Editor.dirty && !window.confirm("Discard your unsaved edits and reload the latest shared draft?")) {
    return;
  }
  const mapId = Editor.doc.id;
  if (await openMap(mapId, { preserveView: true })) {
    toast("Loaded the latest shared draft.");
  }
}

function startRevisionPolling() {
  if (Editor.revisionTimer !== null || typeof window.setInterval !== "function") return;
  Editor.revisionTimer = window.setInterval(checkExternalRevision, 3000);
  Editor.revisionTimer?.unref?.();
}

function updateOverlayImage() {
  const img = $("#backdrop-image");
  if (Editor.showOverlay && Editor.isIso && Editor.doc) {
    img.setAttribute("href", `/assets/maps/painted/${Editor.doc.id}.webp`);
    img.style.opacity = "0.5";
  } else {
    img.style.opacity = "0";
  }
}

function updateReferenceImage() {
  const img = $("#reference-image");
  const ref = Editor.doc?.reference;
  $("#reference-toggle").disabled = !ref;
  $("#reference-opacity").disabled = !ref;
  $("#reference-caption").textContent = ref
    ? `${ref.description}${Editor.isIso ? ' · Switch to 2D to trace.' : ''}` : "No calibrated reference attached.";
  if (!ref || !Editor.showReference || Editor.isIso) {
    img.style.opacity = "0";
    return;
  }
  img.setAttribute("href", ref.image_path);
  for (const key of ["x", "y", "width", "height"]) img.setAttribute(key, ref[key]);
  img.style.opacity = String(Editor.referenceOpacity);
}

function fitMap() {
  if (!Editor.doc) return;
  const points = Editor.doc.walkable_surfaces.flatMap(s =>
    surfacePolygons(s).flatMap(poly => poly.map(p => MapTransform.project(p[0], p[1], s.elevation, Editor.isIso))));
  const reference = Editor.doc.reference;
  if (reference && Editor.showReference && !Editor.isIso) {
    points.push(MapTransform.project(reference.x, reference.y, 0, false),
      MapTransform.project(reference.x + reference.width, reference.y + reference.height, 0, false));
  }
  if (!points.length) return;
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const x = Math.min(...xs) - 5, y = Math.min(...ys) - 5;
  Editor.viewBox = { x, y, w: Math.max(...xs) - x + 5, h: Math.max(...ys) - y + 5 };
  renderCanvas();
}

function createRoomRectangle(a, b) {
  const polygon = MapAuthoring.rectangle(a, b);
  if (polygon[0][0] === polygon[2][0] || polygon[0][1] === polygon[2][1]) {
    toast("Choose two different corners with non-zero width and height.");
    return;
  }
  pushState();
  const id = MapAuthoring.nextId(Editor.doc, "room");
  const surfaceId = `surf_${id}`;
  Editor.doc.walkable_surfaces.push({ id: surfaceId, polygon: clone(polygon), elevation: 0 });
  Editor.doc.semantic_zones.push({ id, display_name: humanize(id), kind: "callout", polygon,
    surface_ids: [surfaceId], label_position: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
    site_id: "none", legacy_zone: "mid" });
  Editor.selectedItem = { type: "zone", id, index: Editor.doc.semantic_zones.length - 1 };
  Editor.drawingPoints = [];
  Editor.selectedTool = "select";
  updateToolActive();
  renderCanvas();
  updateInspector();
}

// ---------------------------------------------------------------------------
// Event Handlers for Meta fields

function selectedFloorSurface() {
  const item = Editor.selectedItem;
  if (!item || !Editor.doc) return null;
  if (item.type === 'surface') return Editor.doc.walkable_surfaces[item.index];
  if (item.type === 'zone') {
    const zone = Editor.doc.semantic_zones[item.index];
    if (zone.kind !== 'plant') return Editor.doc.walkable_surfaces.find(s => zone.surface_ids.includes(s.id));
  }
  return null;
}

function createFloorExtension(a, b) {
  const surface = selectedFloorSurface();
  Editor.drawingPoints = [];
  if (!surface) { toast('Select the room to extend, then choose Floor Extension.'); return; }
  const polygon = MapAuthoring.rectangle(a,b);
  const [x,y] = polygon[0], w = polygon[1][0]-x, h = polygon[2][1]-y;
  if (w <= 0 || h <= 0) { toast('Choose two different corners.'); return; }
  const connected = surfacePolygons(surface).some(poly => {
    const xs = poly.map(p => p[0]), ys = poly.map(p => p[1]);
    const dx = Math.min(x+w,Math.max(...xs))-Math.max(x,Math.min(...xs));
    const dy = Math.min(y+h,Math.max(...ys))-Math.max(y,Math.min(...ys));
    return dx >= 0 && dy >= 0 && (dx > 0 || dy > 0);
  });
  if (!connected) { toast('The new floor must touch this room along an edge.'); return; }
  pushState();
  surface.floor_extensions ||= [];
  surface.floor_extensions.push({x,y,w,h});
  Editor.selectedTool = 'select';
  updateToolActive(); renderCanvas(); updateInspector();
}

function bindMetaEvents() {
  $("#meta-name").onchange = (e) => {
    if (!Editor.doc) return;
    pushState();
    Editor.doc.display_name = e.target.value;
    Editor.dirty = true;
    paintSaveState();
  };
  $("#meta-sites").onchange = (e) => {
    if (!Editor.doc) return;
    pushState();
    Editor.doc.sites = e.target.value.split(",").map(s => s.trim()).filter(Boolean);
    Editor.dirty = true;
    paintSaveState();
  };
  $("#meta-atk-spawn").onchange = (e) => {
    if (!Editor.doc) return;
    pushState();
    Editor.doc.attacker_spawn = e.target.value;
    Editor.dirty = true;
    paintSaveState();
  };
  $("#meta-def-spawn").onchange = (e) => {
    if (!Editor.doc) return;
    pushState();
    Editor.doc.defender_spawn = e.target.value;
    Editor.dirty = true;
    paintSaveState();
  };
}

// ---------------------------------------------------------------------------
// Canvas Event Handlers (Drawing & Editing)

function bindCanvasEvents() {
  const svg = $("#studio-canvas");
  
  svg.addEventListener("contextmenu", (e) => {
    e.preventDefault();
  });
  
  svg.addEventListener("mousedown", (e) => {
    if (!Editor.doc) return;
    
    // Right click for panning
    if (e.button === 2) {
      e.preventDefault();
      Editor.panState = {
        startX: e.clientX,
        startY: e.clientY,
        viewBoxX: Editor.viewBox.x,
        viewBoxY: Editor.viewBox.y
      };
      return;
    }
    
    const pt = MapAuthoring.snapPoint(getCanvasCoords(e), Editor.snapStep);
    
    if (Editor.selectedTool === "select") {
      // Find what point or handle we clicked
      const handle = findHandle(pt, e);
      if (handle) {
        Editor.dragState = {
          type: "point",
          itemType: handle.type,
          index: handle.index,
          pointIndex: handle.pointIndex,
          startX: pt[0],
          startY: pt[1]
        };
        return;
      }
      
      // Otherwise find element clicked
      const element = findElementAt(pt);
      if (element) {
        Editor.selectedItem = element;
        updateInspector();
        renderCanvas();
        
        // Setup dragging for whole element
        Editor.dragState = {
          type: "element",
          itemType: element.type,
          index: element.index,
          startX: pt[0],
          startY: pt[1]
        };
      } else {
        Editor.selectedItem = null;
        updateInspector();
        renderCanvas();
      }
    } else if (Editor.selectedTool === "surface" || Editor.selectedTool === "extension") {
      if (Editor.drawingPoints.length === 0) Editor.drawingPoints.push(pt);
      else if (Editor.selectedTool === "extension") createFloorExtension(Editor.drawingPoints[0], pt);
      else createRoomRectangle(Editor.drawingPoints[0], pt);
      renderCanvas();
    } else if (Editor.selectedTool === "zone" || Editor.selectedTool === "wall") {
      if (Editor.selectedTool === "wall" && Editor.drawingPoints.length) {
        const last = Editor.drawingPoints[Editor.drawingPoints.length - 1];
        if (Math.abs(pt[0] - last[0]) >= Math.abs(pt[1] - last[1])) pt[1] = last[1];
        else pt[0] = last[0];
      }
      // Add point to drawing points
      Editor.drawingPoints.push(pt);
      renderCanvas();
    } else if (Editor.selectedTool === "prop") {
      // Place default 3x3 prop
      pushState();
      const surfaces = Editor.doc.walkable_surfaces;
      const surf = surfaces.find(s => isPointInPolygon(pt, s.polygon)) || surfaces[0];
      const surfId = surf ? surf.id : "surf_none";
      const pid = `prop_${Date.now()}`;
      Editor.doc.props.push({
        id: pid,
        surface_id: surfId,
        footprint: [
          [pt[0] - 1.5, pt[1] - 1.5],
          [pt[0] + 1.5, pt[1] - 1.5],
          [pt[0] + 1.5, pt[1] + 1.5],
          [pt[0] - 1.5, pt[1] + 1.5]
        ],
        height: "half",
        collision: true,
        destructible: false
      });
      Editor.selectedItem = { type: "prop", id: pid, index: Editor.doc.props.length - 1 };
      Editor.selectedTool = "select";
      updateToolActive();
      renderCanvas();
      updateInspector();
    } else if (Editor.selectedTool === "link") {
      const surface = surfaceAt(pt);
      if (!surface) {
        toast("Traversal endpoints must be placed on walkable surfaces.");
        return;
      }
      if (!Editor.linkStart) {
        Editor.linkStart = [pt[0], pt[1], surface.id];
        toast("Traversal start set. Click the destination surface.");
      } else {
        pushState();
        const linkId = `link_${Date.now()}`;
        Editor.doc.traversal_links.push({
          id: linkId,
          kind: "ramp",
          from_pos: Editor.linkStart,
          to_pos: [pt[0], pt[1], surface.id],
          via: [],
          path_mode: "corridor",
          include_endpoints_in_path: true,
          noise_radius: 0.0,
          start_closed_prob: 0.0
        });
        Editor.selectedItem = {
          type: "link",
          id: linkId,
          index: Editor.doc.traversal_links.length - 1
        };
        Editor.linkStart = null;
        Editor.selectedTool = "select";
        updateToolActive();
        renderCanvas();
        updateInspector();
      }
    } else if (Editor.selectedTool === "player") {
      pushState();
      const pid = `player_${Date.now()}`;
      Editor.doc.editor_state.test_players.push({
        id: pid,
        x: pt[0],
        y: pt[1],
        radius: 1.0,
        heading: 90,
        vision_cone: 60
      });
      Editor.selectedItem = { type: "player", id: pid, index: Editor.doc.editor_state.test_players.length - 1 };
      Editor.selectedTool = "select";
      updateToolActive();
      renderCanvas();
      updateInspector();
    } else if (Editor.selectedTool === "probe") {
      if (!Editor.probePos) {
        Editor.probePos = pt;
      } else {
        Editor.probeRay = pt;
        runProbe();
      }
      renderCanvas();
    }
  });

  svg.addEventListener("mousemove", (e) => {
    if (!Editor.doc) return;
    
    if (Editor.panState) {
      const dxScreen = e.clientX - Editor.panState.startX;
      const dyScreen = e.clientY - Editor.panState.startY;
      const rect = svg.getBoundingClientRect();
      const svgDx = dxScreen * (Editor.viewBox.w / rect.width);
      const svgDy = dyScreen * (Editor.viewBox.h / rect.height);
      
      Editor.viewBox.x = Editor.panState.viewBoxX - svgDx;
      Editor.viewBox.y = Editor.panState.viewBoxY - svgDy;
      svg.setAttribute("viewBox", `${Editor.viewBox.x} ${Editor.viewBox.y} ${Editor.viewBox.w} ${Editor.viewBox.h}`);
      return;
    }
    
    const pt = MapAuthoring.snapPoint(getCanvasCoords(e), Editor.snapStep);
    $("#cursor-coords").textContent = `x ${pt[0].toFixed(2)} · y ${pt[1].toFixed(2)}`;
    
    if (Editor.dragState) {
      const dx = pt[0] - Editor.dragState.startX;
      const dy = pt[1] - Editor.dragState.startY;
      
      // Only pushState on the very first movement of the drag to preserve initial state
      if (!Editor.dragState.pushed) {
        pushState();
        Editor.dragState.pushed = true;
      }
      
      if (Editor.dragState.type === "point") {
        movePoint(Editor.dragState.itemType, Editor.dragState.index, Editor.dragState.pointIndex, dx, dy);
      } else if (Editor.dragState.type === "element") {
        moveElement(Editor.dragState.itemType, Editor.dragState.index, dx, dy);
      }
      
      Editor.dragState.startX = pt[0];
      Editor.dragState.startY = pt[1];
      
      if (!Editor.renderRequested) {
        Editor.renderRequested = true;
        requestAnimationFrame(() => {
          renderCanvas();
          Editor.renderRequested = false;
        });
      }
    }
  });

  svg.addEventListener("mouseup", (e) => {
    if (e?.button === 2) {
      if (Editor.panState) Editor.panState = null;
      return;
    }
    if (Editor.dragState) {
      Editor.dragState = null;
      renderCanvas();
      updateInspector();
    }
  });

  window.addEventListener("mouseup", (e) => {
    if (Editor.panState) {
      Editor.panState = null;
    }
  });

  svg.addEventListener("wheel", (e) => {
    if (!Editor.doc) return;
    e.preventDefault();
    
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    const rect = svg.getBoundingClientRect();
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const svgPt = pt.matrixTransform(ctm.inverse());
    const mx = svgPt.x;
    const my = svgPt.y;
    
    const oldW = Editor.viewBox.w;
    const oldH = Editor.viewBox.h;
    
    const nextW = oldW / zoomFactor;
    if (nextW < 5 || nextW > 1100) return;
    
    const newW = nextW;
    const newH = oldH / zoomFactor;
    
    const fractionX = (mx - Editor.viewBox.x) / oldW;
    const fractionY = (my - Editor.viewBox.y) / oldH;
    
    Editor.viewBox.x = mx - fractionX * newW;
    Editor.viewBox.y = my - fractionY * newH;
    Editor.viewBox.w = newW;
    Editor.viewBox.h = newH;
    
    svg.setAttribute("viewBox", `${Editor.viewBox.x} ${Editor.viewBox.y} ${Editor.viewBox.w} ${Editor.viewBox.h}`);
  }, { passive: false });

  // End polygon on Enter key
  window.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      e.shiftKey ? redo() : undo();
      return;
    }
    if (e.key.toLowerCase() === "f") fitMap();
    const minPoints = Editor.selectedTool === "wall" ? 2 : 3;
    if (e.key === "Enter" && Editor.drawingPoints.length >= minPoints) {
      pushState();
      if (Editor.selectedTool === "surface") {
        const sid = `surface_${Date.now()}`;
        Editor.doc.walkable_surfaces.push({
          id: sid,
          polygon: Editor.drawingPoints,
          elevation: 0.0
        });
        Editor.selectedItem = { type: "surface", id: sid, index: Editor.doc.walkable_surfaces.length - 1 };
      } else if (Editor.selectedTool === "zone") {
        const zid = `zone_${Date.now()}`;
        // compute center for label position
        const xs = Editor.drawingPoints.map(p => p[0]);
        const ys = Editor.drawingPoints.map(p => p[1]);
        const labelPos = [sum(xs)/xs.length, sum(ys)/ys.length];
        const surface = surfaceAt(labelPos);
        Editor.doc.semantic_zones.push({
          id: zid,
          display_name: humanize(zid),
          kind: "callout",
          polygon: Editor.drawingPoints,
          surface_ids: surface ? [surface.id] : [],
          label_position: labelPos,
          site_id: "none",
          legacy_zone: "mid"
        });
        Editor.selectedItem = { type: "zone", id: zid, index: Editor.doc.semantic_zones.length - 1 };
      } else if (Editor.selectedTool === "wall") {
        const wallId = `wall_${Date.now()}`;
        Editor.doc.walls.push({
          id: wallId,
          polyline: Editor.drawingPoints,
          thickness: 1.0,
          height: 3.2,
          penetrability: 1.0
        });
        Editor.selectedItem = { type: "wall", id: wallId, index: Editor.doc.walls.length - 1 };
      }
      Editor.drawingPoints = [];
      Editor.selectedTool = "select";
      updateToolActive();
      renderCanvas();
      updateInspector();
    } else if (e.key === "Escape") {
      Editor.drawingPoints = [];
      Editor.probePos = null;
      Editor.probeRay = null;
      Editor.probeResult = null;
      Editor.linkStart = null;
      renderCanvas();
    }
  });
}

function sum(arr) {
  return arr.reduce((a, b) => a + b, 0);
}

// ---------------------------------------------------------------------------
// SVG Canvas Rendering

function renderCanvas() {
  if (!Editor.doc) return;
  const isIso = Editor.isIso;

  // Set viewBox dynamically based on current zoom/pan state
  const svg = $("#studio-canvas");
  if (!Editor.viewBox) {
    if (isIso) {
      Editor.viewBox = { x: -110, y: -12, w: 220, h: 128 };
    } else {
      Editor.viewBox = { x: -6, y: -6, w: 112, h: 112 };
    }
  }
  svg.setAttribute("viewBox", `${Editor.viewBox.x} ${Editor.viewBox.y} ${Editor.viewBox.w} ${Editor.viewBox.h}`);

  // Clear layers
  const layers = ["surfaces", "zones", "walls", "props", "comparison", "links", "players", "probes", "handles"];
  layers.forEach(l => $(`#layer-${l}`).innerHTML = "");
  if (Editor.floorComparison && !isIso) {
    for (const kind of ["outside", "missing"]) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
      node.setAttribute("d", Editor.floorComparison[kind].map(r => {
        const points = [[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]];
        return points.map((p, i) => `${i ? 'L' : 'M'} ${MapTransform.project(...p, 0, false).join(' ')}`).join(' ') + ' Z';
      }).join(' '));
      node.setAttribute("class", `floor-comparison-${kind}`);
      $("#layer-comparison").appendChild(node);
    }
  }

  // Draw walkable surfaces
  Editor.doc.walkable_surfaces.forEach((surf, idx) => {
    const isSelected = Editor.selectedItem && Editor.selectedItem.type === "surface" && Editor.selectedItem.index === idx;
    const d = surfacePolygons(surf).map(poly => {
      const pts = poly.map(pt => MapTransform.project(pt[0], pt[1], surf.elevation, isIso));
      return pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0]} ${p[1]}`).join(" ") + " Z";
    }).join(" ");
    
    const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
    node.setAttribute("d", d);
    node.setAttribute("class", `walkable-surface ${isSelected ? "selected" : ""}`);
    // Draw the physical union once. Thousands of 0.5u tile seams otherwise
    // turn the tracing outline into a solid stroke and obscure the reference.
    node.style.stroke = "none";
    $("#layer-surfaces").appendChild(node);
    const outline = document.createElementNS("http://www.w3.org/2000/svg", "path");
    outline.setAttribute("d", MapAuthoring.floorOutline(surf).map(([a,b]) =>
      `M ${MapTransform.project(...a,surf.elevation,isIso).join(' ')} L ${MapTransform.project(...b,surf.elevation,isIso).join(' ')}`
    ).join(' '));
    outline.setAttribute("class", `walkable-surface-outline ${isSelected ? "selected" : ""}`);
    $("#layer-surfaces").appendChild(outline);
  });

  // Draw semantic zones
  Editor.doc.semantic_zones.forEach((zone, idx) => {
    const isSelected = Editor.selectedItem && Editor.selectedItem.type === "zone" && Editor.selectedItem.index === idx;
    const pts = zone.polygon.map(pt => MapTransform.project(pt[0], pt[1], 0, isIso));
    const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0]} ${p[1]}`).join(" ") + " Z";
    
    const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
    node.setAttribute("d", d);
    node.setAttribute("class", `semantic-zone ${isSelected ? "selected" : ""}`);
    $("#layer-zones").appendChild(node);
    
    // Draw label position indicator
    const lp = MapTransform.project(zone.label_position[0], zone.label_position[1], 0, isIso);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", lp[0]);
    circle.setAttribute("cy", lp[1]);
    circle.setAttribute("r", "1.2");
    circle.setAttribute("class", "zone-label-anchor");
    $("#layer-zones").appendChild(circle);
    
    // Draw text label
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", lp[0]);
    text.setAttribute("y", lp[1] - 2);
    text.setAttribute("fill", "var(--es-color-text-primary)");
    text.setAttribute("font-size", "3px");
    text.setAttribute("font-family", "var(--es-font-mono)");
    text.setAttribute("text-anchor", "middle");
    text.textContent = (zone.display_name || humanize(zone.id)).replace(/\b(Attacker|Defender) Side\b/g,'$1');
    $("#layer-zones").appendChild(text);
  });

  // Draw props
  Editor.doc.props.forEach((prop, idx) => {
    const isSelected = Editor.selectedItem && Editor.selectedItem.type === "prop" && Editor.selectedItem.index === idx;
    // find matching surface elevation
    const surf = Editor.doc.walkable_surfaces.find(s => s.id === prop.surface_id);
    const elev = surf ? surf.elevation : 0.0;
    const pts = prop.footprint.map(pt => MapTransform.project(pt[0], pt[1], elev, isIso));
    const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0]} ${p[1]}`).join(" ") + " Z";
    
    const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
    node.setAttribute("d", d);
    node.setAttribute("class", `prop-rect ${prop.role === 'wall' ? 'solid-wall' : ''} ${isSelected ? "selected" : ""}`);
    $("#layer-props").appendChild(node);
  });

  // Draw walls
  Editor.doc.walls.forEach((wall, idx) => {
    const isSelected = Editor.selectedItem && Editor.selectedItem.type === "wall" && Editor.selectedItem.index === idx;
    const poly = wall.polyline || [];
    for (let i = 1; i < poly.length; i++) {
      const p1 = MapTransform.project(poly[i-1][0], poly[i-1][1], 0, isIso);
      const p2 = MapTransform.project(poly[i][0], poly[i][1], 0, isIso);
      
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", p1[0]);
      line.setAttribute("y1", p1[1]);
      line.setAttribute("x2", p2[0]);
      line.setAttribute("y2", p2[1]);
      line.setAttribute("class", `wall-line ${isSelected ? "selected" : ""}`);
      line.setAttribute("stroke-width", wall.thickness || 1);
      $("#layer-walls").appendChild(line);
    }
  });

  // Draw traversal links
  Editor.doc.traversal_links.forEach((link, idx) => {
    if (!Editor.showRoutes) return;
    const isSelected = Editor.selectedItem && Editor.selectedItem.type === "link" && Editor.selectedItem.index === idx;
    // find elevations
    const fs = Editor.doc.walkable_surfaces.find(s => s.id === link.from_pos[2]);
    const ts = Editor.doc.walkable_surfaces.find(s => s.id === link.to_pos[2]);
    const fe = fs ? fs.elevation : 0.0;
    const te = ts ? ts.elevation : 0.0;
    
    const worldPoints = [link.from_pos, ...(link.via || []), link.to_pos];
    const projected = worldPoints.map((point, pointIndex) => {
      const progress = worldPoints.length === 1 ? 0 : pointIndex / (worldPoints.length - 1);
      const elevation = fe + (te - fe) * progress;
      return MapTransform.project(point[0], point[1], elevation, isIso);
    });

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", projected.map((point, pointIndex) =>
      `${pointIndex === 0 ? "M" : "L"} ${point[0]} ${point[1]}`
    ).join(" "));
    path.setAttribute("class", `traversal-link-line ${isSelected ? "selected" : ""}`);
    if (link.runtime_enabled === false) {
      path.setAttribute("stroke-dasharray", "1.5 1");
      path.setAttribute("opacity", "0.65");
    }
    path.setAttribute("fill", "none");
    $("#layer-links").appendChild(path);
    
    // Draw midpoint indicator of link type
    const mid = projected[Math.floor(projected.length / 2)];
    const indicator = document.createElementNS("http://www.w3.org/2000/svg", "text");
    indicator.setAttribute("x", mid[0]);
    indicator.setAttribute("y", mid[1] + 1);
    indicator.setAttribute("fill", "var(--es-color-brand)");
    indicator.setAttribute("font-size", "2.5px");
    indicator.setAttribute("font-family", "var(--es-font-mono)");
    indicator.setAttribute("text-anchor", "middle");
    indicator.textContent = link.kind.substring(0, 2).toUpperCase();
    $("#layer-links").appendChild(indicator);
  });

  // Draw test players
  Object.values(Editor.previewPlayers).forEach(player => {
    const surface = Editor.doc.walkable_surfaces.find(s => s.id === `surf_${player.callout_id}`);
    const p = MapTransform.project(player.x, player.y, surface?.elevation || 0, isIso);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", p[0]); circle.setAttribute("cy", p[1]); circle.setAttribute("r", "1.1");
    circle.setAttribute("fill", player.team_id === "team_nexus" ? "var(--es-color-accent)" : "var(--es-color-brand)");
    circle.setAttribute("stroke", "var(--es-color-text-primary)"); circle.setAttribute("stroke-width", "0.25");
    circle.style.pointerEvents = "none";
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = player.handle;
    circle.appendChild(title); $("#layer-players").appendChild(circle);
  });
  Editor.doc.editor_state.test_players.forEach((player, idx) => {
    const isSelected = Editor.selectedItem && Editor.selectedItem.type === "player" && Editor.selectedItem.index === idx;
    const p = MapTransform.project(player.x, player.y, 0, isIso);
    
    // Circle
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", p[0]);
    circle.setAttribute("cy", p[1]);
    circle.setAttribute("r", player.radius || 1);
    circle.setAttribute("class", `handle-circle ${isSelected ? "selected" : ""}`);
    $("#layer-players").appendChild(circle);
    
    // Vision cone
    if (player.vision_cone && player.heading !== undefined) {
      const radius = 25.0;
      const headingRad = (player.heading * Math.PI) / 180;
      const coneRad = (player.vision_cone * Math.PI) / 360;
      const p1Rad = headingRad - coneRad;
      const p2Rad = headingRad + coneRad;
      
      const v1 = MapTransform.project(player.x + Math.cos(p1Rad)*radius, player.y + Math.sin(p1Rad)*radius, 0, isIso);
      const v2 = MapTransform.project(player.x + Math.cos(p2Rad)*radius, player.y + Math.sin(p2Rad)*radius, 0, isIso);
      
      const d = `M ${p[0]} ${p[1]} L ${v1[0]} ${v1[1]} A ${radius} ${radius} 0 0 1 ${v2[0]} ${v2[1]} Z`;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      path.setAttribute("class", "vision-cone");
      $("#layer-players").appendChild(path);
    }
  });

  // Draw handles if select mode and active element selected
  if (Editor.selectedTool === "select" && Editor.selectedItem) {
    const item = Editor.selectedItem;
    let pts = [];
    let elevation = 0.0;
    if (item.type === "surface") {
      const surf = Editor.doc.walkable_surfaces[item.index];
      pts = surf.polygon;
      elevation = surf.elevation;
    } else if (item.type === "zone") {
      pts = Editor.doc.semantic_zones[item.index].polygon;
    } else if (item.type === "prop") {
      const prop = Editor.doc.props[item.index];
      pts = prop.footprint;
      const surf = Editor.doc.walkable_surfaces.find(s => s.id === prop.surface_id);
      elevation = surf ? surf.elevation : 0.0;
    } else if (item.type === "wall") {
      pts = Editor.doc.walls[item.index].polyline;
    } else if (item.type === "link") {
      pts = linkPoints(Editor.doc.traversal_links[item.index]);
    }
    
    pts.forEach((pt, pIdx) => {
      const p = MapTransform.project(pt[0], pt[1], elevation, isIso);
      const handle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      handle.setAttribute("cx", p[0]);
      handle.setAttribute("cy", p[1]);
      handle.setAttribute("r", "1.0");
      handle.setAttribute("fill", "var(--es-color-bg-page)");
      handle.setAttribute("stroke", "var(--es-color-brand)");
      handle.setAttribute("stroke-width", "0.4");
      handle.setAttribute("cursor", "move");
      $("#layer-handles").appendChild(handle);
    });
  }

  // Draw current drawing points
  if (Editor.drawingPoints.length > 0) {
    const pts = Editor.drawingPoints.map(pt => MapTransform.project(pt[0], pt[1], 0, isIso));
    for (let i = 0; i < pts.length; i++) {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", pts[i][0]);
      circle.setAttribute("cy", pts[i][1]);
      circle.setAttribute("r", "0.8");
      circle.setAttribute("fill", "var(--es-color-brand)");
      $("#layer-handles").appendChild(circle);
      
      if (i > 0) {
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", pts[i-1][0]);
        line.setAttribute("y1", pts[i-1][1]);
        line.setAttribute("x2", pts[i][0]);
        line.setAttribute("y2", pts[i][1]);
        line.setAttribute("stroke", "var(--es-color-brand)");
        line.setAttribute("stroke-width", "0.5");
        $("#layer-handles").appendChild(line);
      }
    }
  }

  // Draw Probes
  if (Editor.probePos) {
    const p = MapTransform.project(Editor.probePos[0], Editor.probePos[1], 0, isIso);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", p[0]);
    circle.setAttribute("cy", p[1]);
    circle.setAttribute("r", "1.2");
    circle.setAttribute("class", "probe-point");
    $("#layer-probes").appendChild(circle);
  }
  if (Editor.probePos && Editor.probeRay) {
    const p1 = MapTransform.project(Editor.probePos[0], Editor.probePos[1], 0, isIso);
    const p2 = MapTransform.project(Editor.probeRay[0], Editor.probeRay[1], 0, isIso);
    
    // Draw target line
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", p1[0]);
    line.setAttribute("y1", p1[1]);
    line.setAttribute("x2", p2[0]);
    line.setAttribute("y2", p2[1]);
    line.setAttribute("stroke", "var(--es-color-brand)");
    line.setAttribute("stroke-width", "0.6");
    line.setAttribute("stroke-dasharray", "1, 1");
    $("#layer-probes").appendChild(line);
    
    if (Editor.probeResult) {
      // Draw resolved pos
      const rp = MapTransform.project(Editor.probeResult.resolved_pos[0], Editor.probeResult.resolved_pos[1], 0, isIso);
      const rc = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      rc.setAttribute("cx", rp[0]);
      rc.setAttribute("cy", rp[1]);
      rc.setAttribute("r", "1.0");
      rc.setAttribute("fill", "var(--es-color-accent)");
      rc.setAttribute("stroke", "var(--es-color-bg-page)");
      rc.setAttribute("stroke-width", "0.4");
      $("#layer-probes").appendChild(rc);
      
      // If blocked, draw red line from collision to target
      if (Editor.probeResult.blocked_by) {
        const bline = document.createElementNS("http://www.w3.org/2000/svg", "line");
        bline.setAttribute("x1", rp[0]);
        bline.setAttribute("y1", rp[1]);
        bline.setAttribute("x2", p2[0]);
        bline.setAttribute("y2", p2[1]);
        bline.setAttribute("stroke", "var(--es-color-brand)");
        bline.setAttribute("stroke-width", "0.8");
        $("#layer-probes").appendChild(bline);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Handle & Element Pick Helpers

function findHandle(pt, e) {
  if (!Editor.selectedItem) return null;
  const isIso = Editor.isIso;
  const item = Editor.selectedItem;
  let pts = [];
  let elevation = 0.0;
  if (item.type === "surface") {
    const surf = Editor.doc.walkable_surfaces[item.index];
    pts = surf.polygon;
    elevation = surf.elevation;
  } else if (item.type === "zone") {
    pts = Editor.doc.semantic_zones[item.index].polygon;
  } else if (item.type === "prop") {
    const prop = Editor.doc.props[item.index];
    pts = prop.footprint;
    const surf = Editor.doc.walkable_surfaces.find(s => s.id === prop.surface_id);
    elevation = surf ? surf.elevation : 0.0;
  } else if (item.type === "wall") {
    pts = Editor.doc.walls[item.index].polyline;
  } else if (item.type === "link") {
    pts = linkPoints(Editor.doc.traversal_links[item.index]);
  }
  
  let mouseX, mouseY;
  if (e) {
    const svg = $("#studio-canvas");
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const svgPt = pt.matrixTransform(svg.getScreenCTM().inverse());
    mouseX = svgPt.x;
    mouseY = svgPt.y;
  } else {
    const rawP = MapTransform.project(pt[0], pt[1], 0, isIso);
    mouseX = rawP[0];
    mouseY = rawP[1];
  }
  
  for (let i = 0; i < pts.length; i++) {
    const p = MapTransform.project(pts[i][0], pts[i][1], elevation, isIso);
    if (Math.hypot(p[0] - mouseX, p[1] - mouseY) < 2.0) {
      return { type: item.type, index: item.index, pointIndex: i };
    }
  }
  return null;
}

function findElementAt(pt) {
  // Check players
  for (let i = 0; i < Editor.doc.editor_state.test_players.length; i++) {
    const player = Editor.doc.editor_state.test_players[i];
    if (Math.hypot(player.x - pt[0], player.y - pt[1]) < (player.radius || 1) + 0.5) {
      return { type: "player", id: player.id, index: i };
    }
  }
  
  // Check props
  for (let i = 0; i < Editor.doc.props.length; i++) {
    const prop = Editor.doc.props[i];
    if (isPointInPolygon(pt, prop.footprint)) {
      return { type: "prop", id: prop.id, index: i };
    }
  }

  // Links and walls must be picked before their containing zone/surface.
  for (let i = 0; Editor.showRoutes && i < Editor.doc.traversal_links.length; i++) {
    const link = Editor.doc.traversal_links[i];
    const points = linkPoints(link);
    for (let pointIndex = 1; pointIndex < points.length; pointIndex++) {
      if (pointSegmentDistance(pt, points[pointIndex - 1], points[pointIndex]) < 1.5) {
        return { type: "link", id: link.id, index: i };
      }
    }
  }

  for (let i = 0; i < Editor.doc.walls.length; i++) {
    const wall = Editor.doc.walls[i];
    const points = wall.polyline || [];
    for (let pointIndex = 1; pointIndex < points.length; pointIndex++) {
      if (pointSegmentDistance(pt, points[pointIndex - 1], points[pointIndex]) < Math.max(1.0, wall.thickness || 1.0)) {
        return { type: "wall", id: wall.id || `wall_${i}`, index: i };
      }
    }
  }

  // Check semantic zones
  for (let i = 0; i < Editor.doc.semantic_zones.length; i++) {
    const zone = Editor.doc.semantic_zones[i];
    if (isPointInPolygon(pt, zone.polygon)) {
      return { type: "zone", id: zone.id, index: i };
    }
  }

  // Check surfaces
  for (let i = 0; i < Editor.doc.walkable_surfaces.length; i++) {
    const surf = Editor.doc.walkable_surfaces[i];
    if (surfacePolygons(surf).some(poly => isPointInPolygon(pt, poly))) {
      return { type: "surface", id: surf.id, index: i };
    }
  }
  
  return null;
}

function isPointInPolygon(pt, poly) {
  const x = pt[0], y = pt[1];
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1];
    const xj = poly[j][0], yj = poly[j][1];
    const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function surfacePolygons(surface) {
  return [surface.polygon, ...(surface.floor_extensions || []).map(r =>
    [[r.x,r.y],[r.x+r.w,r.y],[r.x+r.w,r.y+r.h],[r.x,r.y+r.h]])];
}

function surfaceAt(pt) {
  return Editor.doc.walkable_surfaces.find(surface =>
    surfacePolygons(surface).some(poly => isPointInPolygon(pt, poly))
  ) || null;
}

function linkPoints(link) {
  return [link.from_pos, ...(link.via || []), link.to_pos];
}

function pointSegmentDistance(point, start, end) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  if (dx === 0 && dy === 0) return Math.hypot(point[0] - start[0], point[1] - start[1]);
  const t = Math.max(0, Math.min(1,
    ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
  ));
  return Math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy));
}

// ---------------------------------------------------------------------------
// Drags & Moves

function movePoint(type, index, ptIdx, dx, dy) {
  let pts = [];
  if (type === "surface") {
    pts = Editor.doc.walkable_surfaces[index].polygon;
  } else if (type === "zone") {
    pts = Editor.doc.semantic_zones[index].polygon;
  } else if (type === "prop") {
    pts = Editor.doc.props[index].footprint;
  } else if (type === "wall") {
    pts = Editor.doc.walls[index].polyline;
  } else if (type === "link") {
    const link = Editor.doc.traversal_links[index];
    pts = linkPoints(link);
  }
  if (pts[ptIdx]) {
    if (["surface", "zone", "prop"].includes(type) && MapAuthoring.isRectangle(pts)) {
      const resized = MapAuthoring.resizeRectangle(pts, ptIdx,
        MapAuthoring.snapPoint([pts[ptIdx][0] + dx, pts[ptIdx][1] + dy], Editor.snapStep));
      const collection = type === "surface" ? Editor.doc.walkable_surfaces : type === "zone" ? Editor.doc.semantic_zones : Editor.doc.props;
      const entity = collection[index];
      if (type === "surface" || (type === "zone" && entity.kind !== "plant")) {
        const surface = type === "surface" ? entity : Editor.doc.walkable_surfaces.find(s =>
          entity.surface_ids.includes(s.id) && JSON.stringify(s.polygon) === JSON.stringify(pts));
        if (surface) {
          Editor.doc.semantic_zones.filter(z => z.kind !== "plant" && z.surface_ids.includes(surface.id))
            .forEach(z => { z.polygon = clone(resized); });
          surface.polygon = clone(resized);
        }
      }
      entity[type === "prop" ? "footprint" : "polygon"] = clone(resized);
      return;
    }
    pts[ptIdx][0] = Math.round((pts[ptIdx][0] + dx) * 100) / 100;
    pts[ptIdx][1] = Math.round((pts[ptIdx][1] + dy) * 100) / 100;
    if (type === "link" && (ptIdx === 0 || ptIdx === pts.length - 1)) {
      const surface = surfaceAt(pts[ptIdx]);
      if (surface) pts[ptIdx][2] = surface.id;
    }
  }
}

function moveElement(type, index, dx, dy) {
  const zone = type === "zone" ? Editor.doc.semantic_zones[index] : null;
  const surface = type === "surface" ? Editor.doc.walkable_surfaces[index] :
    zone && zone.kind !== "plant" ? Editor.doc.walkable_surfaces.find(s =>
      zone.surface_ids.includes(s.id) && JSON.stringify(s.polygon) === JSON.stringify(zone.polygon)) : null;
  if (surface) {
    const shift = pts => pts.forEach(p => {
      p[0] = Math.round((p[0] + dx) * 100) / 100;
      p[1] = Math.round((p[1] + dy) * 100) / 100;
    });
    shift(surface.polygon);
    (surface.floor_extensions || []).forEach(r => { r.x += dx; r.y += dy; });
    Editor.doc.semantic_zones.filter(z => z.surface_ids.includes(surface.id)).forEach(z => {
      shift(z.polygon); shift([z.label_position]);
    });
    Editor.doc.props.filter(p => p.surface_id === surface.id).forEach(p => shift(p.footprint));
    Editor.doc.traversal_links.forEach(l => {
      if (l.from_pos[2] === surface.id) shift([l.from_pos]);
      if (l.to_pos[2] === surface.id) shift([l.to_pos]);
    });
    return;
  }
  if (type === "player") {
    const player = Editor.doc.editor_state.test_players[index];
    player.x = Math.round((player.x + dx) * 100) / 100;
    player.y = Math.round((player.y + dy) * 100) / 100;
    return;
  }
  
  let pts = [];
  if (type === "surface") {
    pts = Editor.doc.walkable_surfaces[index].polygon;
  } else if (type === "zone") {
    pts = Editor.doc.semantic_zones[index].polygon;
    // also move label pos
    const zone = Editor.doc.semantic_zones[index];
    zone.label_position[0] = Math.round((zone.label_position[0] + dx) * 100) / 100;
    zone.label_position[1] = Math.round((zone.label_position[1] + dy) * 100) / 100;
  } else if (type === "prop") {
    pts = Editor.doc.props[index].footprint;
  } else if (type === "wall") {
    pts = Editor.doc.walls[index].polyline;
  } else if (type === "link") {
    pts = linkPoints(Editor.doc.traversal_links[index]);
  }
  
  pts.forEach(pt => {
    pt[0] = Math.round((pt[0] + dx) * 100) / 100;
    pt[1] = Math.round((pt[1] + dy) * 100) / 100;
  });
  if (type === "link") {
    const link = Editor.doc.traversal_links[index];
    const fromSurface = surfaceAt(link.from_pos);
    const toSurface = surfaceAt(link.to_pos);
    if (fromSurface) link.from_pos[2] = fromSurface.id;
    if (toSurface) link.to_pos[2] = toSurface.id;
  }
}

// ---------------------------------------------------------------------------
// Right Panel (Inspector Panel)

function updateInspector() {
  const panel = $("#inspector-content");
  if (!Editor.selectedItem || !Editor.doc) {
    panel.innerHTML = `<p class="muted">Select an element on the canvas to inspect and edit details.</p>`;
    return;
  }
  
  const item = Editor.selectedItem;
  let html = "";
  const floorSurface = item.type === "surface" ? Editor.doc.walkable_surfaces[item.index] :
    item.type === "zone" && Editor.doc.semantic_zones[item.index].kind !== "plant" ?
    Editor.doc.walkable_surfaces.find(s => Editor.doc.semantic_zones[item.index].surface_ids.includes(s.id)) : null;
  
  if (item.type === "surface") {
    const surf = Editor.doc.walkable_surfaces[item.index];
    html = `
      <h3>Walkable Surface</h3>
      <div style="display: grid; gap: var(--es-space-4); margin-top: var(--es-space-4);">
        <label class="field"><span>Surface ID</span><input type="text" value="${esc(surf.id)}" onchange="updateSelectedField('id', this.value)"></label>
        <label class="field"><span>Elevation (Z)</span><input type="number" step="0.5" value="${surf.elevation}" onchange="updateSelectedField('elevation', parseFloat(this.value))"></label>
        <button class="btn" onclick="deleteSelectedItem()" style="border-color: var(--es-color-brand); color: var(--es-color-brand);">Delete Surface</button>
      </div>
    `;
  } else if (item.type === "zone") {
    const zone = Editor.doc.semantic_zones[item.index];
    html = `
      <h3>Semantic Zone</h3>
      <div style="display: grid; gap: var(--es-space-4); margin-top: var(--es-space-4);">
        <label class="field"><span>Zone ID</span><input type="text" value="${esc(zone.id)}" onchange="updateSelectedField('id', this.value)"></label>
        <label class="field"><span>Display Name</span><input type="text" value="${esc(zone.display_name || '')}" placeholder="Generated from ID" onchange="updateSelectedField('display_name', this.value || null)"></label>
        <label class="field"><span>Kind</span>
          <select onchange="updateSelectedField('kind', this.value)">
            <option value="callout" ${zone.kind === "callout" ? "selected" : ""}>Callout</option>
            <option value="site" ${zone.kind === "site" ? "selected" : ""}>Site</option>
            <option value="spawn" ${zone.kind === "spawn" ? "selected" : ""}>Spawn Zone</option>
            <option value="plant" ${zone.kind === "plant" ? "selected" : ""}>Plant Zone</option>
          </select>
        </label>
        <label class="field"><span>Site ID</span><input type="text" value="${esc(zone.site_id)}" onchange="updateSelectedField('site_id', this.value)"></label>
        <label class="field"><span>Tactical Runtime Zone</span>
          <select onchange="updateSelectedField('legacy_zone', this.value || null)">
            <option value="" ${!zone.legacy_zone ? "selected" : ""}>Select tactical zone...</option>
            ${["attacker_spawn", "defender_spawn", "attacker_side", "defender_side", "mid", "site"].map(value =>
              `<option value="${value}" ${zone.legacy_zone === value ? "selected" : ""}>${humanize(value)}</option>`
            ).join("")}
          </select>
        </label>
        <label class="field"><span>Walkable Surface IDs</span><input type="text" value="${esc((zone.surface_ids || []).join(', '))}" onchange="updateSelectedStringList('surface_ids', this.value)"></label>
        <button class="btn" onclick="deleteSelectedItem()" style="border-color: var(--es-color-brand); color: var(--es-color-brand);">Delete Zone</button>
      </div>
    `;
  } else if (item.type === "prop") {
    const prop = Editor.doc.props[item.index];
    html = `
      <h3>${prop.role === 'wall' ? 'Solid Wall Volume' : 'Cover Prop'}</h3>
      <div style="display: grid; gap: var(--es-space-4); margin-top: var(--es-space-4);">
        <label class="field"><span>Prop ID</span><input type="text" value="${esc(prop.id)}" onchange="updateSelectedField('id', this.value)"></label>
        <label class="field"><span>Role</span>
          <select onchange="updateSelectedField('role', this.value)">
            <option value="cover" ${(prop.role || 'cover') === 'cover' ? 'selected' : ''}>Cover / holding spot</option>
            <option value="wall" ${prop.role === 'wall' ? 'selected' : ''}>Solid wall volume</option>
          </select>
        </label>
        <label class="field"><span>Height</span>
          <select onchange="updateSelectedField('height', this.value)">
            <option value="half" ${prop.height === "half" ? "selected" : ""}>Half Height (Crate)</option>
            <option value="full" ${prop.height === "full" ? "selected" : ""}>Full Height (Wall block)</option>
          </select>
        </label>
        <label class="field"><span>Collision</span>
          <select onchange="updateSelectedField('collision', this.value === 'true')">
            <option value="true" ${prop.collision ? "selected" : ""}>Blocks movement</option>
            <option value="false" ${!prop.collision ? "selected" : ""}>No collision</option>
          </select>
        </label>
        <button class="btn" onclick="deleteSelectedItem()" style="border-color: var(--es-color-brand); color: var(--es-color-brand);">Delete Prop</button>
      </div>
    `;
  } else if (item.type === "wall") {
    const wall = Editor.doc.walls[item.index];
    html = `
      <h3>Wall Segment</h3>
      <div style="display: grid; gap: var(--es-space-4); margin-top: var(--es-space-4);">
        <label class="field"><span>Wall ID</span><input type="text" value="${esc(wall.id || `wall_${item.index}`)}" onchange="updateSelectedField('id', this.value)"></label>
        <label class="field"><span>Thickness</span><input type="number" step="0.2" value="${wall.thickness || 1.0}" onchange="updateSelectedField('thickness', parseFloat(this.value))"></label>
        <label class="field"><span>Height</span><input type="number" step="0.5" value="${wall.height || 3.2}" onchange="updateSelectedField('height', parseFloat(this.value))"></label>
        <button class="btn" onclick="deleteSelectedItem()" style="border-color: var(--es-color-brand); color: var(--es-color-brand);">Delete Wall</button>
      </div>
    `;
  } else if (item.type === "link") {
    const link = Editor.doc.traversal_links[item.index];
    const via = (link.via || []).map(point => `${point[0]}, ${point[1]}`).join("; ");
    html = `
      <h3>Traversal Link</h3>
      <div style="display: grid; gap: var(--es-space-4); margin-top: var(--es-space-4);">
        <label class="field"><span>Link ID</span><input type="text" value="${esc(link.id)}" onchange="updateSelectedField('id', this.value)"></label>
        <label class="field"><span>Simulation traversal</span><select onchange="updateSelectedField('runtime_enabled', this.value === 'true')">
          <option value="true" ${link.runtime_enabled !== false ? "selected" : ""}>Enabled</option>
          <option value="false" ${link.runtime_enabled === false ? "selected" : ""}>Recorded only</option>
        </select></label>
        <label class="field"><span>Traversal note</span><input value="${esc(link.description || '')}" onchange="updateSelectedField('description', this.value)"></label>
        <label class="field"><span>Kind</span>
          <select onchange="updateSelectedField('kind', this.value)">
            ${["ramp", "rope", "door", "rotating_door", "teleporter", "drop"].map(value =>
              `<option value="${value}" ${link.kind === value ? "selected" : ""}>${value}</option>`
            ).join("")}
          </select>
        </label>
        <label class="field"><span>Runtime Path</span>
          <select onchange="updateSelectedField('path_mode', this.value)">
            <option value="corridor" ${link.path_mode !== "portal" ? "selected" : ""}>Authored corridor</option>
            <option value="portal" ${link.path_mode === "portal" ? "selected" : ""}>Shared room portal</option>
          </select>
        </label>
        <label class="field"><span>Include link endpoints in route</span>
          <select onchange="updateSelectedField('include_endpoints_in_path', this.value === 'true')">
            <option value="true" ${link.include_endpoints_in_path !== false ? "selected" : ""}>Yes</option>
            <option value="false" ${link.include_endpoints_in_path === false ? "selected" : ""}>No (legacy route)</option>
          </select>
        </label>
        <label class="field"><span>Via points (x,y; x,y)</span><input type="text" value="${esc(via)}" onchange="updateLinkVia(this.value)"></label>
        <label class="field"><span>Doorway Span (low, high)</span><input value="${esc((link.opening_span || []).join(', '))}" placeholder="Open seam" onchange="updateOpeningSpan(this.value)"></label>
        <label class="field"><span>Noise Radius</span><input type="number" min="0" step="1" value="${link.noise_radius || 0}" onchange="updateSelectedField('noise_radius', parseFloat(this.value))"></label>
        <label class="field"><span>Setup-Close Probability (breakable: defenders switch it shut)</span><input type="number" min="0" max="1" step="0.05" value="${link.start_closed_prob || 0}" onchange="updateSelectedField('start_closed_prob', parseFloat(this.value))"></label>
        <button class="btn" onclick="deleteSelectedItem()" style="border-color: var(--es-color-brand); color: var(--es-color-brand);">Delete Link</button>
      </div>
    `;
  } else if (item.type === "player") {
    const player = Editor.doc.editor_state.test_players[item.index];
    html = `
      <h3>Test Player</h3>
      <div style="display: grid; gap: var(--es-space-4); margin-top: var(--es-space-4);">
        <label class="field"><span>Player ID</span><input type="text" value="${esc(player.id)}" onchange="updateSelectedField('id', this.value)"></label>
        <label class="field"><span>Heading (degrees)</span><input type="number" value="${player.heading || 90}" onchange="updateSelectedField('heading', parseInt(this.value))"></label>
        <label class="field"><span>Vision Cone (degrees)</span><input type="number" value="${player.vision_cone || 60}" onchange="updateSelectedField('vision_cone', parseInt(this.value))"></label>
        <button class="btn" onclick="deleteSelectedItem()" style="border-color: var(--es-color-brand); color: var(--es-color-brand);">Delete Player</button>
      </div>
    `;
  }
  
  if (floorSurface) html += `<label class="field"><span>Floor extensions (x, y, width, height)</span>
    <textarea aria-label="Floor extensions" rows="4" onchange="updateFloorExtensions(this.value)">${esc(
      (floorSurface.floor_extensions || []).map(r => [r.x,r.y,r.w,r.h].join(', ')).join('\n'))}</textarea></label>
    <p class="trace-help">Each rectangle adds physical floor to this room. Its navigation center stays fixed.</p>`;
  panel.innerHTML = html;
}

function updateFloorExtensions(value) {
  if (!Editor.doc || !Editor.selectedItem) return;
  const item = Editor.selectedItem;
  const surface = item.type === 'surface' ? Editor.doc.walkable_surfaces[item.index] :
    item.type === 'zone' ? Editor.doc.walkable_surfaces.find(s => Editor.doc.semantic_zones[item.index].surface_ids.includes(s.id)) : null;
  if (!surface) return;
  const rows = value.trim() ? value.trim().split('\n').map(row => row.split(',').map(v => v.trim() ? Number(v.trim()) : NaN)) : [];
  if (rows.some(row => row.length !== 4 || row.some(v => !Number.isFinite(v)) || row[2] <= 0 || row[3] <= 0)) {
    toast('Use one rectangle per line: x, y, positive width, positive height.'); return;
  }
  pushState();
  surface.floor_extensions = rows.map(([x,y,w,h]) => ({x,y,w,h}));
  renderCanvas();
}

function updateSelectedField(field, value) {
  if (!Editor.doc || !Editor.selectedItem) return;
  pushState();
  const item = Editor.selectedItem;
  if (item.type === "surface") {
    const surface = Editor.doc.walkable_surfaces[item.index];
    const oldId = surface.id;
    surface[field] = value;
    if (field === "id" && value !== oldId) {
      renameSurfaceReferences(oldId, value);
      Editor.selectedItem.id = value;
    }
  } else if (item.type === "zone") {
    const zone = Editor.doc.semantic_zones[item.index];
    const oldId = zone.id;
    zone[field] = value;
    if (field === "id" && value !== oldId) {
      renameZoneReferences(oldId, value);
      Editor.selectedItem.id = value;
    }
    if (field === "kind" && value === "site") zone.legacy_zone = "site";
  } else if (item.type === "prop") {
    Editor.doc.props[item.index][field] = value;
  } else if (item.type === "wall") {
    Editor.doc.walls[item.index][field] = value;
    if (field === "id") Editor.selectedItem.id = value;
  } else if (item.type === "link") {
    Editor.doc.traversal_links[item.index][field] = value;
  } else if (item.type === "player") {
    Editor.doc.editor_state.test_players[item.index][field] = value;
  }
  renderCanvas();
}

function updateOpeningSpan(value) {
  const span = value.trim() ? value.split(',').map(Number) : null;
  if (span && (span.length !== 2 || !span.every(Number.isFinite) || span[0] >= span[1])) {
    toast("Enter two finite numbers in ascending order, or leave blank for an open seam.");
    return;
  }
  if (Editor.selectedItem?.type !== 'link') return;
  pushState();
  const link = Editor.doc.traversal_links[Editor.selectedItem.index];
  link.opening_span = span;
  link.override_opening = true;
  renderCanvas();
}

function renameSurfaceReferences(oldId, newId) {
  Editor.doc.semantic_zones.forEach(zone => {
    zone.surface_ids = (zone.surface_ids || []).map(id => id === oldId ? newId : id);
  });
  Editor.doc.props.forEach(prop => {
    if (prop.surface_id === oldId) prop.surface_id = newId;
  });
  Editor.doc.traversal_links.forEach(link => {
    if (link.from_pos[2] === oldId) link.from_pos[2] = newId;
    if (link.to_pos[2] === oldId) link.to_pos[2] = newId;
  });
}

function renameZoneReferences(oldId, newId) {
  if (Editor.doc.attacker_spawn === oldId) Editor.doc.attacker_spawn = newId;
  if (Editor.doc.defender_spawn === oldId) Editor.doc.defender_spawn = newId;
  const adjacency = Editor.doc.legacy.adjacency_overrides || {};
  if (Object.hasOwn(adjacency, oldId)) {
    adjacency[newId] = adjacency[oldId];
    delete adjacency[oldId];
  }
  Object.keys(adjacency).forEach(fromZone => {
    adjacency[fromZone] = adjacency[fromZone].map(
      toZone => toZone === oldId ? newId : toZone
    );
  });
  (Editor.doc.legacy.sightline_overrides || []).forEach(sightline => {
    if (sightline.from_callout === oldId) sightline.from_callout = newId;
    if (sightline.to_callout === oldId) sightline.to_callout = newId;
  });
}

function updateSelectedStringList(field, value) {
  if (!Editor.doc || !Editor.selectedItem || Editor.selectedItem.type !== "zone") return;
  pushState();
  Editor.doc.semantic_zones[Editor.selectedItem.index][field] = value
    .split(",").map(item => item.trim()).filter(Boolean);
  renderCanvas();
}

function updateLinkVia(value) {
  if (!Editor.doc || !Editor.selectedItem || Editor.selectedItem.type !== "link") return;
  let invalidPoint = null;
  const via = value.trim() === "" ? [] : value.split(";").map(rawPoint => {
    const coordinates = rawPoint.split(",").map(raw => Number(raw.trim()));
    if (coordinates.length !== 2 || coordinates.some(coordinate => !Number.isFinite(coordinate))) {
      invalidPoint = rawPoint;
    }
    return coordinates;
  });
  if (invalidPoint !== null) {
    toast(`Invalid via point: ${invalidPoint}`);
    updateInspector();
    return;
  }
  pushState();
  Editor.doc.traversal_links[Editor.selectedItem.index].via = via;
  renderCanvas();
}

function deleteSelectedItem() {
  if (!Editor.doc || !Editor.selectedItem) return;
  pushState();
  const item = Editor.selectedItem;
  if (item.type === "surface") {
    Editor.doc.walkable_surfaces.splice(item.index, 1);
  } else if (item.type === "zone") {
    Editor.doc.semantic_zones.splice(item.index, 1);
  } else if (item.type === "prop") {
    Editor.doc.props.splice(item.index, 1);
  } else if (item.type === "wall") {
    Editor.doc.walls.splice(item.index, 1);
  } else if (item.type === "link") {
    Editor.doc.traversal_links.splice(item.index, 1);
  } else if (item.type === "player") {
    Editor.doc.editor_state.test_players.splice(item.index, 1);
  }
  Editor.selectedItem = null;
  renderCanvas();
  updateInspector();
}

// ---------------------------------------------------------------------------
// Server Audits & Probes

async function validateDraft() {
  if (!Editor.doc) return;
  try {
    const res = await request("/api/map-studio/validate", {
      method: "POST",
      body: Editor.doc
    });
    
    const list = $("#diagnostics-list");
    const dot = $("#validity-dot");
    dot.className = "validity-dot " + (res.valid ? "valid" : "invalid");
    
    if (res.valid) {
      list.innerHTML = `<p class="muted">All continuous audits and legacy compilation compatibility checks passed successfully!</p>`;
      list.innerHTML += Editor.doc.traversal_links.filter(link => link.runtime_enabled === false).map(link =>
        `<p class="muted"><b>Recorded traversal: ${esc(link.id)}</b> ${esc(link.description || 'This link is excluded from simulation.')}</p>`
      ).join("");
      toast("Map validation passed.");
    } else {
      $("#editor").classList.remove("focus-canvas");
      $("#focus-canvas-btn").textContent = "Focus Canvas";
      toast(`Map has ${res.errors.length} validation issue(s). See Audits & Warnings.`);
      list.innerHTML = res.errors.map(err => `
        <div class="newsline" style="color: var(--es-color-brand); border-color: color-mix(in srgb, var(--es-color-brand) 25%, transparent)">
          <b>${esc(err.path)}</b>: ${esc(err.message)}
        </div>
      `).join("");
    }
  } catch (err) {
    toast(`Validation failed: ${err.message}`);
  }
}

function clearFloorComparison() {
  Editor.comparisonGeneration++;
  Editor.floorComparison = null;
  $("#floor-comparison-status").textContent = "";
  $("#compare-floor-btn").textContent = "Compare Floor";
  $("#compare-floor-btn").disabled = false;
  $("#layer-comparison").innerHTML = "";
}

async function compareFloor() {
  if (!Editor.doc?.reference) { toast("Attach a calibrated reference to compare floor."); return; }
  if (Editor.floorComparison) { clearFloorComparison(); renderCanvas(); return; }
  const generation = ++Editor.comparisonGeneration;
  $("#compare-floor-btn").disabled = true;
  $("#floor-comparison-status").textContent = "Comparing floor to the reference…";
  try {
    const result = await request("/api/map-studio/compare-floor", { method: "POST", body: Editor.doc });
    if (generation !== Editor.comparisonGeneration) return;
    Editor.floorComparison = result;
    $("#compare-floor-btn").textContent = "Hide Comparison";
    $("#floor-comparison-status").textContent = `${Math.round(result.iou * 100)}% floor overlap · Red: floor outside reference (${Math.round(result.outside_area)}u²) · Green: missing floor (${Math.round(result.missing_area)}u²) · Approximate image trace, ${result.grid_step}u grid`;
    renderCanvas();
  } catch (error) {
    if (generation !== Editor.comparisonGeneration) return;
    $("#floor-comparison-status").textContent = `Comparison failed: ${error.message}`;
  } finally {
    if (generation === Editor.comparisonGeneration) $("#compare-floor-btn").disabled = false;
  }
}

function stopPreview() {
  Editor.previewGeneration++;
  if (Editor.previewTimer !== null) clearInterval(Editor.previewTimer);
  Editor.previewTimer = null;
  Editor.previewPlayers = {};
  $("#preview-status").textContent = "";
  $("#preview-round-btn").textContent = "Test Round";
  $("#preview-round-btn").disabled = !Editor.doc;
}

async function previewRound() {
  if (!Editor.doc) return;
  const seed = Number($("#round-preview-seed").value);
  if (!Number.isInteger(seed) || seed < 0 || seed > 2147483647) { toast('Choose a whole-number round seed from 0 to 2147483647.'); return; }
  if (Editor.previewTimer !== null) { stopPreview(); renderCanvas(); return; }
  stopPreview();
  const generation = Editor.previewGeneration;
  $("#preview-round-btn").disabled = true;
  $("#preview-status").textContent = "Simulating a test round on this draft…";
  try {
    const replay = await request("/api/map-studio/preview", { method: "POST", body: {doc: Editor.doc, seed} });
    if (generation !== Editor.previewGeneration) return;
    $("#preview-round-btn").disabled = false;
    $("#preview-round-btn").textContent = "Stop Preview";
    let index = 0;
    Editor.previewTimer = setInterval(() => {
      const tick = replay.events[index]?.tick;
      if (tick === undefined) {
        clearInterval(Editor.previewTimer); Editor.previewTimer = null;
        $("#preview-round-btn").textContent = "Test Round";
        return;
      }
      let ending = null;
      while (index < replay.events.length && replay.events[index].tick === tick) {
        const e = replay.events[index++];
        if (e.type === "round.control" || (e.type === "round.move" && e.from_callout === null && e.waypoints?.length)) {
          const [x, y] = e.type === "round.control" ? [e.x, e.y] : e.waypoints[0];
          Editor.previewPlayers[e.player_id] = { ...replay.players[e.player_id], x, y, callout_id: e.callout_id || e.to_callout };
        }
        if (e.type === "round.kill") delete Editor.previewPlayers[e.victim_id];
        if (e.type === "round.end") ending = e;
      }
      $("#preview-status").textContent = ending
        ? `Round 1: ${humanize(ending.winner_id)} won (${humanize(ending.reason)}). Seed ${replay.seed}.`
        : `Round 1 · seed ${replay.seed} · tick ${tick} · ${Object.keys(Editor.previewPlayers).length} players · recorded engine positions`;
      renderCanvas();
    }, 100);
  } catch (err) {
    if (generation !== Editor.previewGeneration) return;
    stopPreview();
    toast(`Preview failed: ${err.message}`);
  }
}

async function runProbe() {
  if (!Editor.doc || !Editor.probePos || !Editor.probeRay) return;
  try {
    const res = await request("/api/map-studio/probe", {
      method: "POST",
      body: {
        doc: Editor.doc,
        from_pos: Editor.probePos,
        to_pos: Editor.probeRay,
        radius: 1.0
      }
    });
    Editor.probeResult = res;
    
    // Render result details in Inspector
    const panel = $("#inspector-content");
    panel.innerHTML = `
      <h3>Probe Analysis</h3>
      <div class="stat-line"><span>Surface ID:</span> <b>${esc(res.surface_id || "-")}</b></div>
      <div class="stat-line"><span>Zone ID:</span> <b>${esc(res.zone_id || "-")}</b></div>
      <div class="stat-line"><span>Clearance:</span> <b>${res.clearance !== null ? res.clearance + "u" : "-"}</b></div>
      <div class="stat-line"><span>LOS result:</span> <b style="color: ${res.los ? "var(--es-color-accent)" : "var(--es-color-brand)"}">${res.los ? "Clear" : "Blocked"}</b></div>
      ${res.blocked_by ? `<div class="stat-line"><span>Blocked Movement By:</span> <b>${esc(res.blocked_by.id)} (${res.blocked_by.type})</b></div>` : ""}
      <div style="margin-top: var(--es-space-4);">
        <span class="eyebrow">Reachable Zones</span>
        <div class="newsline" style="max-height: 100px; overflow: auto;">
          ${(res.reachable_zones || []).map(z => `<span class="pill">${esc(z)}</span>`).join(" ")}
        </div>
      </div>
      <button class="btn" style="margin-top: var(--es-space-5); width: 100%;" onclick="clearProbe()">Clear Probe</button>
    `;
    
    renderCanvas();
  } catch (err) {
    toast(`Probe failed: ${err.message}`);
  }
}

function clearProbe() {
  Editor.probePos = null;
  Editor.probeRay = null;
  Editor.probeResult = null;
  renderCanvas();
  updateInspector();
}

// ---------------------------------------------------------------------------
// Header Topbar Actions

async function saveDraft() {
  if (!Editor.doc) return;
  try {
    const res = await request(`/api/map-studio/maps/${encodeURIComponent(Editor.doc.id)}`, {
      method: "PUT",
      headers: Editor.hash ? { "if-match": Editor.hash } : {},
      body: Editor.doc
    });
    if (res.valid) {
      Editor.hash = res.hash;
      Editor.dirty = false;
      Editor.externalChangePending = false;
      $("#reload-btn").disabled = true;
      paintSaveState();
      $("#hash-draft").textContent = Editor.hash.substring(0, 8);
      toast("Draft saved successfully.");
      validateDraft();
    } else {
      toast(`Failed to save: ${res.errors[0].message}`);
    }
  } catch (err) {
    if (err.status === 409) markExternalChange();
    toast(`Save failed: ${err.message}`);
  }
}

async function publishRuntime() {
  if (!Editor.doc) return;
  if (Editor.dirty || Editor.externalChangePending) {
    toast("Save or reconcile the shared draft before publishing.");
    return;
  }
  try {
    const res = await request(`/api/map-studio/maps/${encodeURIComponent(Editor.doc.id)}/publish`, {
      method: "POST",
      headers: Editor.hash ? { "if-match": Editor.hash } : {}
    });
    if (res.valid) {
      toast("Map published successfully! Legacy configs and guide regenerated.");
      $("#hash-compiled").textContent = res.compiled_revision.substring(0, 8);
      $("#paint-status").textContent = "current";
      $("#paint-status").className = "status-indicator";
    }
  } catch (err) {
    if (err.status === 409) markExternalChange();
    toast(`Publish failed: ${err.message}`);
  }
}

function openDeleteMapDialog() {
  if (!Editor.doc) return;
  $("#delete-map-name").textContent = Editor.doc.display_name || Editor.doc.id;
  $("#delete-map-id").textContent = Editor.doc.id;
  $("#delete-map-confirm").value = "";
  $("#confirm-delete-map-btn").disabled = true;
  $("#delete-map-dialog").showModal();
}

async function deleteMapPermanently() {
  if (!Editor.doc || !Editor.hash) return;
  const mapId = Editor.doc.id;
  const confirmation = $("#delete-map-confirm").value.trim();
  if (confirmation !== mapId) {
    toast(`Type ${mapId} exactly to confirm deletion.`);
    return;
  }

  $("#confirm-delete-map-btn").disabled = true;
  try {
    const res = await request(`/api/map-studio/maps/${encodeURIComponent(mapId)}`, {
      method: "DELETE",
      headers: { "if-match": Editor.hash },
      body: { confirm_map_id: confirmation },
    });
    if (res.valid) {
      $("#delete-map-dialog").close();
      closeOpenMap();
      await initLibrary();
      toast(`${mapId} was permanently deleted.`);
    }
  } catch (err) {
    if (err.status === 409) markExternalChange();
    toast(`Delete failed: ${err.message}`);
    $("#confirm-delete-map-btn").disabled = confirmation !== Editor.doc?.id;
  }
}

// ---------------------------------------------------------------------------
// Tool Switchers

function bindToolbarEvents() {
  document.querySelectorAll(".tool-btn").forEach(btn => {
    btn.onclick = () => {
      Editor.selectedTool = btn.dataset.tool;
      updateToolActive();
      
      // reset temp points
      Editor.drawingPoints = [];
      Editor.linkStart = null;
      Editor.probePos = null;
      Editor.probeRay = null;
      Editor.probeResult = null;
      renderCanvas();
    };
  });

  $("#view-toggle").onclick = () => {
    Editor.isIso = !Editor.isIso;
    $("#view-toggle").textContent = Editor.isIso ? "View: 3D Isometric" : "View: 2D Top-Down";
    if (Editor.isIso) {
      Editor.viewBox = { x: -110, y: -12, w: 220, h: 128 };
    } else {
      Editor.viewBox = { x: -6, y: -6, w: 112, h: 112 };
    }
    renderCanvas();
    fitMap();
    updateOverlayImage();
    updateReferenceImage();
  };

  $("#undo-btn").onclick = undo;
  $("#redo-btn").onclick = redo;
  $("#fit-map-btn").onclick = fitMap;
  $("#focus-canvas-btn").onclick = () => {
    const editor = $("#editor");
    const focused = editor.classList.contains("focus-canvas");
    focused ? editor.classList.remove("focus-canvas") : editor.classList.add("focus-canvas");
    $("#focus-canvas-btn").textContent = focused ? "Focus Canvas" : "Show Properties";
  };
  $("#snap-step").onchange = e => { Editor.snapStep = Number(e.target.value); };
  $("#reference-toggle").onchange = e => { Editor.showReference = e.target.checked; updateReferenceImage(); };
  $("#compare-floor-btn").onclick = compareFloor;
  $("#round-preview-seed").onchange = () => { stopPreview(); renderCanvas(); };
  $("#reference-opacity").oninput = e => { Editor.referenceOpacity = Number(e.target.value) / 100; updateReferenceImage(); };
  $("#routes-toggle").onchange = e => {
    Editor.showRoutes = e.target.checked;
    if (!Editor.showRoutes && Editor.selectedItem?.type === "link") Editor.selectedItem = null;
    renderCanvas(); updateInspector();
  };
  $("#trace-outline").onchange = e => {
    const classes = $("#studio-canvas").classList;
    e.target.checked ? classes.add("trace-outlines") : classes.remove("trace-outlines");
  };

  $("#save-btn").onclick = saveDraft;
  $("#reload-btn").onclick = reloadLatest;
  $("#validate-btn").onclick = validateDraft;
  $("#preview-round-btn").onclick = previewRound;
  $("#publish-btn").onclick = publishRuntime;
  $("#delete-map-btn").onclick = openDeleteMapDialog;

  $("#toggle-paint-btn").onclick = () => {
    Editor.showOverlay = !Editor.showOverlay;
    updateOverlayImage();
  };
}

function updateToolActive() {
  const help = { surface: "Click two opposite corners. A room and linked callout are created together.",
    extension: "Select a room, then click two opposite corners to add connected floor. The navigation center stays fixed.",
    zone: "Click polygon corners, then Enter. Plant zones must share the site's surface.",
    wall: "Click wall corners, then Enter. Segments stay horizontal or vertical.",
    link: "Click a start surface, then a destination. Edit bends and doorway span in Properties." };
  $("#trace-help").textContent = help[Editor.selectedTool] || "Select and drag to edit. Wheel to zoom · Right-drag to pan · F to fit · Ctrl+Z to undo.";
  document.querySelectorAll(".tool-btn").forEach(btn => {
    if (btn.dataset.tool === Editor.selectedTool) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

// ---------------------------------------------------------------------------
// Create Map Dialog

function bindDialogEvents() {
  $("#new-map-btn").onclick = () => {
    $("#new-map-dialog").showModal();
  };
  $("#empty-new").onclick = () => {
    $("#new-map-dialog").showModal();
  };
  
  $("#confirm-new-btn").onclick = async () => {
    const mapId = $("#new-map-id").value.trim();
    const mapName = $("#new-map-name").value.trim();
    if (!mapId) {
      toast("Map ID is required");
      return;
    }
    
    try {
      const res = await request("/api/map-studio/maps", {
        method: "POST",
        body: { id: mapId, display_name: mapName }
      });
      if (res.valid) {
        $("#new-map-dialog").close();
        toast("New map draft created.");
        await initLibrary();
        openMap(mapId);
      }
    } catch (err) {
      toast(`Failed to create map: ${err.message}`);
    }
  };

  $("#delete-map-confirm").oninput = (event) => {
    $("#confirm-delete-map-btn").disabled = event.target.value.trim() !== Editor.doc?.id;
  };
  $("#confirm-delete-map-btn").onclick = deleteMapPermanently;
}

// ---------------------------------------------------------------------------
// Init

window.onload = async () => {
  bindToolbarEvents();
  bindDialogEvents();
  bindCanvasEvents();
  bindMetaEvents();
  startRevisionPolling();
  await initLibrary();
  const requestedMap = new URLSearchParams(window.location?.search || "").get("map");
  if (requestedMap) await openMap(requestedMap);
};
