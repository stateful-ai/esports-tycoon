/**
 * Shared map transform library for esports-sim.
 * Defines canonical 2D top-down and 3D isometric coordinate mappings.
 */

const MapTransform = {
  /**
   * Projects 100x100 grid coordinates to 2D top-down screen coordinates.
   * Flipped Y-axis so defenders are at the top.
   * @param {number} x Grid X (0..100)
   * @param {number} y Grid Y (0..100)
   * @returns {[number, number]} [screenX, screenY]
   */
  projectGridTo2D(x, y) {
    return [x, 100 - y];
  },

  /**
   * Projects 100x100 grid coordinates to 3D isometric screen coordinates.
   * Elevation moves objects upward on the screen.
   * @param {number} x Grid X (0..100)
   * @param {number} y Grid Y (0..100)
   * @param {number} elevation Z height/elevation
   * @returns {[number, number]} [screenX, screenY]
   */
  projectGridToIso(x, y, elevation = 0) {
    const screenX = x + y - 100;
    const screenY = (x - y + 100) / 2 - elevation;
    return [screenX, screenY];
  },

  /**
   * General project function mimicking V.iso toggle.
   */
  project(x, y, elevation = 0, isIso = false) {
    return isIso
      ? this.projectGridToIso(x, y, elevation)
      : this.projectGridTo2D(x, y);
  }
};

// Node module support for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = MapTransform;
} else {
  window.MapTransform = MapTransform;
}
