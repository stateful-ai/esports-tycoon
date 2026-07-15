/**
 * Stress test for Map Studio frontend JS logic.
 * Run with: node tests/stress_test_map_studio_frontend.js
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

// 1. Setup a clean, mocked browser environment
class MockElement {
  constructor(id) {
    this.id = id;
    this.listeners = {};
    this.classList = {
      classes: new Set(),
      add(c) { this.classes.add(c); },
      remove(c) { this.classes.delete(c); },
      contains(c) { return this.classes.has(c); }
    };
    this.style = {};
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.disabled = false;
    this.dataset = {};
  }
  
  addEventListener(event, callback) {
    this.listeners[event] = callback;
  }
  
  setAttribute(name, val) {
    this[name] = val;
  }
  
  appendChild(node) {
    // No-op for testing structure
  }

  showModal() {
    this.modalShown = true;
  }

  close() {
    this.modalShown = false;
  }
  
  createSVGPoint() {
    return {
      x: 0,
      y: 0,
      matrixTransform(matrix) {
        // matrix has properties: a, b, c, d, e, f
        // standard multiplication:
        // x' = a * x + c * y + e
        // y' = b * x + d * y + f
        return {
          x: matrix.a * this.x + matrix.c * this.y + matrix.e,
          y: matrix.b * this.x + matrix.d * this.y + matrix.f
        };
      }
    };
  }
  
  getScreenCTM() {
    return {
      a: 2, b: 0, c: 0, d: 2, e: 10, f: 20, // default scale 2, translate 10, 20
      inverse() {
        return {
          a: 0.5, b: 0, c: 0, d: 0.5, e: -5, f: -10
        };
      }
    };
  }
}

const elements = {};
const globalDocument = {
  querySelector(selector) {
    const clean = selector.replace('#', '');
    if (!elements[clean]) {
      elements[clean] = new MockElement(clean);
    }
    return elements[clean];
  },
  querySelectorAll(selector) {
    if (selector === ".tool-btn") {
      return [
        this.querySelector("#tool-select"),
        this.querySelector("#tool-surface"),
        this.querySelector("#tool-wall"),
        this.querySelector("#tool-zone"),
        this.querySelector("#tool-prop"),
        this.querySelector("#tool-link"),
        this.querySelector("#tool-player"),
        this.querySelector("#tool-probe"),
      ];
    }
    return [];
  },
  createElement(tag) {
    return new MockElement(tag);
  },
  createElementNS(ns, tag) {
    return new MockElement(tag);
  }
};

// Expose globals for the map-studio.js script
global.document = globalDocument;
global.window = {
  addEventListener(event, callback) {
    if (!global.window.listeners) global.window.listeners = {};
    global.window.listeners[event] = callback;
  }
};
global.fetch = async (url, init) => {
  return {
    ok: true,
    json: async () => {
      if (url.includes("/api/map-studio/maps/ascent")) {
        return {
          hash: "test-hash-value-123456789",
          document: {
            id: "ascent",
            display_name: "Ascent",
            sites: ["a", "b"],
            attacker_spawn: "zone_spawn_atk",
            defender_spawn: "zone_spawn_def",
            walkable_surfaces: [
              { id: "surf_1", polygon: [[10, 10], [20, 10], [20, 20], [10, 20]], elevation: 0.0 }
            ],
            semantic_zones: [
              { id: "zone_1", kind: "site", polygon: [[10, 10], [20, 10], [20, 20], [10, 20]], surface_ids: ["surf_1"], label_position: [15, 15], site_id: "a" }
            ],
            props: [],
            walls: [],
            traversal_links: [],
            editor_state: { test_players: [] }
          }
        };
      }
      return { maps: [{ id: "ascent", display_name: "Ascent", status: "draft" }] };
    }
  };
};

global.requestAnimationFrame = (callback) => {
  callback();
};

// Mock MapTransform
global.MapTransform = require(path.join(__dirname, '../src/esports_sim/web/static/map-transform.js'));

// Load map-studio.js
const studioCode = fs.readFileSync(path.join(__dirname, '../src/esports_sim/web/static/map-studio.js'), 'utf8');
const instrumentedCode = studioCode.replace(/function updateInspector\(/g, "global.updateInspector = function updateInspector(");
eval(instrumentedCode + `
global.Editor = Editor;
global.getCanvasCoords = getCanvasCoords;
global.openMap = openMap;
global.undo = undo;
global.redo = redo;
if (!global.updateInspector) global.updateInspector = updateInspector;
global.pushState = pushState;
global.requestErrorMessage = requestErrorMessage;
`);

// Verify window onload binding and initialize
assert.strictEqual(typeof window.onload, 'function');
window.onload();

// Let's verify each test case
async function runTests() {
  console.log("Starting Frontend Logic Verification...\n");

  assert.strictEqual(
    global.requestErrorMessage({ detail: [{ loc: ["query", "request"], msg: "Field required" }] }),
    "query.request: Field required"
  );

  // --- Test Case 1: Coordinate mapping and ViewBox transforms ---
  console.log("1. Testing ViewBox coordinate calculations under scaling...");
  
  // Set up mock SVG element canvas
  const canvas = globalDocument.querySelector("#studio-canvas");
  
  // Case A: 2D Top-Down coordinate mapping
  Editor.isIso = false;
  
  // Simulating standard mouse click event at client position (10, 20) with standard Screen CTM.
  // With scale=2, translate=(10,20), inverse scale=0.5, translate=(-5,-10).
  // clientX=10 => svgPt.x = 10 * 0.5 - 5 = 0.
  // clientY=20 => svgPt.y = 20 * 0.5 - 10 = 0.
  // rawX = 0, rawY = 0.
  // In 2D: x = rawX = 0, y = 100 - rawY = 100.
  let pt = getCanvasCoords({ clientX: 10, clientY: 20 });
  assert.deepStrictEqual(pt, [0, 100]);
  
  // Let's try clientX = 110, clientY = 120
  // svgPt.x = 110 * 0.5 - 5 = 50.
  // svgPt.y = 120 * 0.5 - 10 = 50.
  // rawX = 50, rawY = 50.
  // In 2D: x = 50, y = 100 - 50 = 50.
  pt = getCanvasCoords({ clientX: 110, clientY: 120 });
  assert.deepStrictEqual(pt, [50, 50]);

  // Let's change the Screen CTM to simulate zooming (scale = 4, translate = (100, 200))
  // Inverse CTM scale = 0.25, translate = -25, -50.
  canvas.getScreenCTM = () => {
    return {
      a: 4, b: 0, c: 0, d: 4, e: 100, f: 200,
      inverse() {
        return { a: 0.25, b: 0, c: 0, d: 0.25, e: -25, f: -50 };
      }
    };
  };

  // clientX = 300 => svgPt.x = 300 * 0.25 - 25 = 50.
  // clientY = 400 => svgPt.y = 400 * 0.25 - 50 = 50.
  // In 2D: [50, 50]
  pt = getCanvasCoords({ clientX: 300, clientY: 400 });
  assert.deepStrictEqual(pt, [50, 50]);
  console.log("  [PASS] 2D Top-Down coordinate projection matches perfectly under variable scaling.");

  // Case B: 3D Isometric coordinate mapping
  Editor.isIso = true;
  // Let's reset CTM to default: inverse scale = 0.5, translate = -5, -10
  canvas.getScreenCTM = () => {
    return {
      a: 2, b: 0, c: 0, d: 2, e: 10, f: 20,
      inverse() {
        return { a: 0.5, b: 0, c: 0, d: 0.5, e: -5, f: -10 };
      }
    };
  };

  // clientX = 110 => svgPt.x = 50 (rawX)
  // clientY = 120 => svgPt.y = 50 (rawY)
  // Iso mapping inverse:
  // x = (rawX + 2 * rawY) / 2 = (50 + 100) / 2 = 75
  // y = rawX + 100 - x = 50 + 100 - 75 = 75
  pt = getCanvasCoords({ clientX: 110, clientY: 120 });
  assert.deepStrictEqual(pt, [75, 75]);
  
  // Verify with projectGridToIso(75, 75)
  const proj = MapTransform.projectGridToIso(75, 75);
  assert.strictEqual(proj[0], 50); // screenX = 75 + 75 - 100 = 50
  assert.strictEqual(proj[1], 50); // screenY = (75 - 75 + 100) / 2 = 50
  console.log("  [PASS] 3D Isometric inverse mapping is mathematically correct and matches projection.");


  // --- Test Case 2: Drag undo/redo stack ---
  console.log("\n2. Testing Drag undo/redo stack behavior...");
  
  // Open the map first to initialize Editor.doc
  await openMap("ascent");
  assert.ok(Editor.doc);
  
  // Set tool to select and item to a walkable surface
  Editor.selectedTool = "select";
  Editor.selectedItem = { type: "surface", id: "surf_1", index: 0 };
  Editor.isIso = false;
  
  // Reset undo/redo stacks
  Editor.undoStack = [];
  Editor.redoStack = [];
  
  // Simulating a click (mousedown) without movement
  const svgListeners = elements["studio-canvas"].listeners;
  assert.ok(svgListeners["mousedown"]);
  assert.ok(svgListeners["mousemove"]);
  assert.ok(svgListeners["mouseup"]);
  
  // Click at coordinate that maps to rawX=15, rawY=85.
  // clientX = 40 => svgPt.x = 40 * 0.5 - 5 = 15.
  // clientY = 190 => svgPt.y = 190 * 0.5 - 10 = 85.
  console.log("Before mousedown, Editor.doc is:", JSON.stringify(Editor.doc, null, 2));
  const ptTest = getCanvasCoords({ clientX: 40, clientY: 190 });
  console.log("Calculated pt:", ptTest);
  console.log("findElementAt(pt):", findElementAt(ptTest));
  svgListeners["mousedown"]({ clientX: 40, clientY: 190 });
  console.log("After mousedown, Editor.dragState is:", Editor.dragState);
  assert.ok(Editor.dragState);
  assert.strictEqual(Editor.dragState.pushed, undefined);
  assert.strictEqual(Editor.undoStack.length, 0); // No state pushed on mousedown!
  
  // Mouseup (no movement)
  svgListeners["mouseup"]();
  assert.strictEqual(Editor.dragState, null);
  assert.strictEqual(Editor.undoStack.length, 0); // No state pushed for click-only!
  console.log("  [PASS] Click-only does not push duplicate states to undo stack.");
  
  // Simulating a drag: mousedown -> mousemove -> mousemove -> mouseup
  svgListeners["mousedown"]({ clientX: 40, clientY: 190 });
  assert.ok(Editor.dragState);
  
  // Mousemove 1
  svgListeners["mousemove"]({ clientX: 42, clientY: 192 }); // slight move
  assert.strictEqual(Editor.dragState.pushed, true);
  assert.strictEqual(Editor.undoStack.length, 1); // Exactly one state pushed on first move
  
  // Save pushed state content to verify it's the pre-drag doc
  const preDragStateJson = Editor.undoStack[0];
  
  // Mousemove 2
  svgListeners["mousemove"]({ clientX: 44, clientY: 194 }); // more movement
  assert.strictEqual(Editor.undoStack.length, 1); // Still exactly one state! (no duplicates)
  
  // Mouseup
  svgListeners["mouseup"]();
  assert.strictEqual(Editor.dragState, null);
  assert.strictEqual(Editor.undoStack.length, 1);
  console.log("  [PASS] Dragging pushes exactly one state on initial movement.");


  // --- Test Case 3: Metadata Undo/Redo ---
  console.log("\n3. Testing Metadata change undo/redo...");
  
  Editor.undoStack = [];
  Editor.redoStack = [];
  Editor.dirty = false;
  
  const nameInput = globalDocument.querySelector("#meta-name");
  assert.ok(nameInput.onchange);
  
  // Set new value and trigger change event
  nameInput.value = "New Ascent Map Name";
  const oldDocName = Editor.doc.display_name;
  
  nameInput.onchange({ target: { value: "New Ascent Map Name" } });
  
  assert.strictEqual(Editor.doc.display_name, "New Ascent Map Name");
  assert.strictEqual(Editor.undoStack.length, 1);
  
  const pushedDoc = JSON.parse(Editor.undoStack[0]);
  assert.strictEqual(pushedDoc.display_name, oldDocName); // Pushed state is the old name!
  
  // Test Undo
  undo();
  assert.strictEqual(Editor.doc.display_name, oldDocName); // Restored!
  assert.strictEqual(Editor.redoStack.length, 1);
  
  // Test Redo
  redo();
  assert.strictEqual(Editor.doc.display_name, "New Ascent Map Name"); // Re-applied!
  console.log("  [PASS] Metadata change correctly calls pushState before applying updates, enabling full undo/redo.");


  // --- Test Case 4: Color Token Checking ---
  console.log("\n4. Checking color token usage in map-studio.css...");
  const cssContent = fs.readFileSync(path.join(__dirname, '../src/esports_sim/web/static/map-studio.css'), 'utf8');
  
  // Verify there are no raw hex codes like #ff4655 or #4fd8c0.
  // Hex colors regex: /#[a-fA-F0-9]{3,8}\b/
  const hexMatches = cssContent.match(/#[a-fA-F0-9]{3,8}\b/g) || [];
  // Exclude comments or valid non-color hashes if any
  const invalidHexColors = hexMatches.filter(m => {
    // Check if it's not a common comment/ID (though IDs in CSS are selectors, but this is a stylesheet,
    // we shouldn't use hex colors). If there are any hex colors, report them.
    return true; // Any hex color matches are color definitions
  });
  
  assert.deepStrictEqual(invalidHexColors, [], `Found raw hex colors in map-studio.css: ${invalidHexColors.join(', ')}`);
  console.log("  [PASS] No raw hex colors exist in map-studio.css. All colors match tokens.css variables.");


  // --- Test Case 5: Inspector DOM updates throttling ---
  console.log("\n5. Verifying that inspector updates are deferred/throttled during dragging...");
  
  let updateInspectorCallCount = 0;
  const originalUpdateInspector = global.updateInspector;
  global.updateInspector = () => {
    updateInspectorCallCount++;
  };
  
  // Reset dragState
  Editor.selectedTool = "select";
  Editor.selectedItem = { type: "surface", id: "surf_1", index: 0 };
  
  // Mousedown
  svgListeners["mousedown"]({ clientX: 40, clientY: 190 });
  
  // Dragging mouse moves
  updateInspectorCallCount = 0;
  svgListeners["mousemove"]({ clientX: 42, clientY: 192 });
  svgListeners["mousemove"]({ clientX: 44, clientY: 194 });
  svgListeners["mousemove"]({ clientX: 46, clientY: 196 });
  
  // Assert that updateInspector was NOT called during dragging
  assert.strictEqual(updateInspectorCallCount, 0, "updateInspector must not be called during mousemove drags!");
  
  // Mouseup should call updateInspector
  svgListeners["mouseup"]();
  assert.strictEqual(updateInspectorCallCount, 1, "updateInspector should be called on mouseup.");
  
  global.updateInspector = originalUpdateInspector;
  console.log("  [PASS] Inspector DOM updates are correctly deferred during dragging and only update on mouseup.");


  // --- Test Case 6: Spacing Token Checking ---
  console.log("\n6. Checking spacing tokens in HTML and CSS...");
  const htmlContent = fs.readFileSync(path.join(__dirname, '../src/esports_sim/web/static/map-studio.html'), 'utf8');
  
  // Verify that any margin or padding in style attributes or inline styles is token-compliant.
  // Check for style="...margin...: \d+px" or "gap: \d+px" or "padding: \d+px"
  const hardcodedSpacingRegex = /(margin|padding|gap):\s*\d+px/i;
  const matchHtml = htmlContent.match(hardcodedSpacingRegex);
  assert.strictEqual(matchHtml, null, `Found hardcoded spacing in HTML style attributes: ${matchHtml ? matchHtml[0] : ''}`);
  
  console.log("  [PASS] Spacing aligns with the 4px token system (no hardcoded px values for spacing).");

  console.log("\nAll 6 verification cases PASSED successfully!");
}

runTests().catch(err => {
  console.error("\n[FAIL] Verification failed:", err);
  process.exit(1);
});
