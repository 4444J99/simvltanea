/* shared-engine adapter — simvltanea consumer.
 *
 * Thin by construction. It owns no timeline math: it compiles a choreography
 * score from the edition's panel layout, hands it to the shared engine's
 * evaluateSpatialScore, and translates the result into this composition's
 * orientation convention.
 *
 *   shared engine (score space)        simvltanea (panel space)
 *   ------------------------------     ---------------------------------
 *   azimuth   positive = turning left  panel azimuth, positive = left
 *   elevation positive = looking up     panel elevation, positive = up
 *
 * simvltanea reads azimuth the same way the score does, so unlike the
 * time-moment-brief adapter there is no sign flip here. Keeping that
 * difference explicit is the point: a consumer that quietly reused the other
 * adapter's negation would mirror the whole field.
 *
 * The shared engine is injected. src/simvltanea/browser/shared_engine.py
 * resolves it from the checkout, verifies its SHA-256 against
 * PROVENANCE.json, and emits the import; this file never carries a copy.
 */
(function (root) {
  'use strict';

  const BUILD_ID = 'shared-engine@time-moment-brief/agent7-shared-engine';
  const HALF_TURN = Math.PI;

  function assertSharedEngine(engine) {
    if (!engine || typeof engine.evaluateSpatialScore !== 'function') {
      throw new Error(
        'simvltanea shared-engine adapter: shared engine not found. Resolve it with ' +
        'simvltanea.browser.shared_engine.resolve_shared_engine() and inject the module; ' +
        'this composition has no local copy of the projection core.'
      );
    }
    return engine;
  }

  /**
   * Compile a choreography score covering the whole run.
   *
   * Each panel sweeps its own azimuth across the same duration with a per-panel
   * phase offset, which is what makes the field read as simultaneous rather
   * than stacked. Offsets are a pure function of panel index: no wall-clock, no
   * entropy, no state.
   *
   * @param {Object} layout
   * @param {number} layout.panels        - panel count (>= 1)
   * @param {number} layout.duration      - run duration in seconds (> 0)
   * @param {number} [layout.sweep]       - azimuth swept per panel, radians
   * @param {number} [layout.elevation]   - peak elevation, radians
   * @param {'smoothstep'|'linear'} [layout.easing='smoothstep']
   * @returns {{ blocks: Array }}
   */
  function compileScore(layout) {
    if (!layout || !Number.isFinite(layout.panels) || layout.panels < 1) {
      throw new Error('compileScore requires layout.panels >= 1');
    }
    if (!Number.isFinite(layout.duration) || layout.duration <= 0) {
      throw new Error('compileScore requires layout.duration > 0');
    }
    const sweep = Number.isFinite(layout.sweep) ? layout.sweep : HALF_TURN;
    const peak = Number.isFinite(layout.elevation) ? layout.elevation : 0;
    const easing = layout.easing === 'linear' ? 'linear' : 'smoothstep';
    const blocks = [];
    for (let index = 0; index < layout.panels; index++) {
      const start = (layout.duration * index) / layout.panels;
      const end = (layout.duration * (index + 1)) / layout.panels;
      const from = sweep * (index / layout.panels);
      blocks.push({
        start,
        end,
        azimuthStart: from,
        azimuthEnd: from + sweep,
        elevationStart: 0,
        elevationEnd: peak * (index % 2 === 0 ? 1 : -1),
        easing,
      });
    }
    return { blocks };
  }

  /**
   * Instantiate a panel orientation driver.
   *
   * @param {*} shared - the injected shared engine module
   * @param {Object} layout - see compileScore
   * @returns {PanelDriver}
   */
  function createPanelDriver(shared, layout) {
    assertSharedEngine(shared);
    const score = compileScore(layout);
    const panels = score.blocks.length;

    return {
      buildId: BUILD_ID,
      consumer: 'simvltanea',
      layout,
      score,

      /** Orientation of one panel at composition time `t`. Pure. */
      panelAt(index, t) {
        if (!Number.isInteger(index) || index < 0 || index >= panels) {
          throw new RangeError(`panel index ${index} outside 0..${panels - 1}`);
        }
        const pose = shared.evaluateSpatialScore(
          { blocks: [score.blocks[index]] },
          t - score.blocks[index].start
        );
        return { azimuth: pose.azimuth, elevation: pose.elevation, fov: pose.fov };
      },

      /** Every panel's orientation at `t`, in panel order. */
      evaluate(t) {
        const out = new Array(panels);
        for (let index = 0; index < panels; index++) out[index] = this.panelAt(index, t);
        return out;
      },
    };
  }

  const api = { BUILD_ID, assertSharedEngine, compileScore, createPanelDriver };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SimvltaneaSharedEngineAdapter = api;
})(typeof window !== 'undefined' ? window : globalThis);
