/* Persistent native-loop playback for the interactive Studio.
 * Authored timeline playback remains in browser.runtime.js. This classic script
 * consumes admitted local Blobs; it never fetches or uploads media itself.
 */
(function (root) {
  'use strict';
  const number = value => {
    const [n, d = 1] = String(value).split('/').map(Number);
    const result = n / d;
    if (!Number.isFinite(result)) throw new Error('Invalid layout coordinate');
    return result;
  };
  const setCssProp = (style, key, value) => style.setProperty(key, value);
  const removeCssProp = (style, key) => style.removeProperty(key);
  // The authored raster and crop mathematics are shared unchanged in this
  // standalone bundle, keeping Studio framing identical to authored exports.
function resolveSliceRect(node) {
  return (node.span && (node.span.slice_rect || node.span.sliceRect)) ||
                  node.slice_rect || node.sliceRect ||
                  (node.cell && (node.cell.slice_rect || node.cell.sliceRect)) ||
                  (node.item && (node.item.slice_rect || node.item.sliceRect || node.item.viewport));

}
function sliceValues(raw) {
  const coordinate = value => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    return number(value);
  };
  if (Array.isArray(raw)) {
    if (raw.length !== 4) throw new Error('Invalid slice rectangle');
    return raw.map(coordinate);
  }
  return [raw.x ?? 0, raw.y ?? 0, raw.width ?? raw.w ?? 1, raw.height ?? raw.h ?? 1].map(coordinate);
}
function isPartialSlice(raw) {
  if (!raw) return false;
  const [x,y,w,h] = sliceValues(raw);
  return !(Math.abs(x)<1e-5 && Math.abs(y)<1e-5 && Math.abs(w-1)<1e-5 && Math.abs(h-1)<1e-5);
}
/* Full-bleed raster (docs/plans/2026-11-05-full-bleed-layout-presets.md).
 * Exact rationals decide coverage and name shared edges; floats only place pixels. */
const EDGE_EPSILON = 1e-12;
const OPPOSITE_SIDE = {top:'bottom', bottom:'top', left:'right', right:'left'};
const SIDE_CORNERS = {top:['TopLeft','TopRight'], bottom:['BottomLeft','BottomRight'],
  left:['TopLeft','BottomLeft'], right:['TopRight','BottomRight']};
const CORNERS = ['TopLeft','TopRight','BottomRight','BottomLeft'];
const OVERLAP_PX_MAX = 8, STRIPS_MAX_CELLS = 12;
/* A cropped media element is sized to cover its target box plus this margin (CSS px)
 * on every side, so independent 1/64 px LayoutUnit rounding of its percentage
 * position and size can never leave a sliver of the box uncovered. */
const COVER_GUARD = 1/8;
function exactReduce(n, d) {
  if (d === 0n) throw new Error('Invalid compiled rational');
  if (d < 0n) { n = -n; d = -d; }
  let a = n < 0n ? -n : n, b = d;
  while (b) [a, b] = [b, a % b];
  return a ? [n / a, d / a] : [0n, 1n];
}
function exact(value) {
  const text = String(value);
  if ((typeof value !== 'string' && typeof value !== 'number') || !/^-?\d+(?:\/\d+)?$/.test(text))
    throw new Error('Invalid compiled rational');
  const [p, q = '1'] = text.split('/');
  return exactReduce(BigInt(p), BigInt(q));
}
const exactAdd = ([a, b], [c, d]) => exactReduce(a*d + c*b, b*d);
const exactMul = ([a, b], [c, d]) => exactReduce(a*c, b*d);
const exactCmp = ([a, b], [c, d]) => { const l = a*d, r = c*b; return l < r ? -1 : l > r ? 1 : 0; };
const exactText = ([n, d]) => d === 1n ? String(n) : `${n}/${d}`;
/* Shared edges in draw order, the same output as Python
 * simvltanea.authoring.adjacency: side `edge` of cell `a` lies on the opposite side
 * of the later cell `b` (exact rational equality) over the positive-length `span`. */
function adjacency(cells) {
  if (!Array.isArray(cells)) throw new Error('cells must be an array');
  const boxes = cells.map((cell, index) => {
    if (!cell || !Array.isArray(cell.rect) || cell.rect.length !== 4)
      throw new Error(`cell ${index}: rect must be [x,y,width,height]`);
    const [x, y, w, h] = cell.rect.map(exact), x2 = exactAdd(x, w), y2 = exactAdd(y, h);
    return {x, y, x2, y2};
  });
  const same = (p, q) => exactCmp(p, q) === 0;
  const larger = (p, q) => exactCmp(p, q) >= 0 ? p : q, smaller = (p, q) => exactCmp(p, q) <= 0 ? p : q;
  const result = [];
  boxes.forEach((A, i) => {
    for (let j = i + 1; j < boxes.length; j++) {
      const B = boxes[j];
      const horizontal = [larger(A.x, B.x), smaller(A.x2, B.x2)], vertical = [larger(A.y, B.y), smaller(A.y2, B.y2)];
      for (const [edge, touches, span] of [['bottom', same(A.y2, B.y), horizontal],
        ['top', same(A.y, B.y2), horizontal], ['right', same(A.x2, B.x), vertical],
        ['left', same(A.x, B.x2), vertical]]) {
        if (touches && exactCmp(span[0], span[1]) < 0)
          result.push({a:i, b:j, edge, span:span.map(exactText)});
      }
    }
  });
  return result;
}
/* Per-cell raster decisions for one layout at one stage size and pixel ratio.
 * Bleed: a side shared with later neighbours grows `overlap_px` device px (plus
 * ceil(radius) when corners are rounded) underneath them, clamped to half of the
 * thinnest such neighbour's pixel extent. A side that also touches an earlier cell
 * does not grow: it would paint over that cell. As in the export
 * (render_triptych.presentation_placements), a side grows only when the nominal
 * boxes of the later cells cover the whole bleed strip, and a grown corner square
 * must be covered too, so the bleed never changes a visible pixel. Corners on a
 * side shared with an earlier neighbour are rounded; all others stay square.
 * Layouts without `presentation` get no bleed and no rounding, exactly as before. */
const COVERAGE_EPSILON = 1e-9;
function bleedRegion([x, y, w, h], side, amount) {
  if (side === 'bottom') return [x, y + h, w, amount];
  if (side === 'top') return [x, y - amount, w, amount];
  if (side === 'right') return [x + w, y, amount, h];
  return [x - amount, y, amount, h];
}
/* True when `boxes` (pairwise disjoint, device px) cover `region`. */
function coveredBy([x, y, w, h], boxes) {
  let area = 0;
  for (const [bx, by, bw, bh] of boxes) {
    const dx = Math.min(x + w, bx + bw) - Math.max(x, bx), dy = Math.min(y + h, by + bh) - Math.max(y, by);
    if (dx > 0 && dy > 0) area += dx * dy;
  }
  return area >= w * h - COVERAGE_EPSILON * Math.max(1, w * h);
}
function rasterLayout(layout, width, height, ratio) {
  const cells = layout.cells.map(() => ({grow:{top:0, right:0, bottom:0, left:0}, rounded:new Set(), radius:0}));
  const presentation = layout.presentation;
  if (!presentation) return {cells, radius:0};
  const radiusFraction = number(presentation.corner_radius);
  const radius = radiusFraction * Math.min(width, height);
  const overlap = presentation.overlap_px;
  const edges = adjacency(layout.cells);
  const touchesEarlier = new Set(edges.map(edge => `${edge.b}:${OPPOSITE_SIDE[edge.edge]}`));
  const rects = layout.cells.map(cell => cell.rect.map(number));
  const boxes = rects.map(([x, y, w, h]) => [x * width * ratio, y * height * ratio, w * width * ratio, h * height * ratio]);
  const extentOf = (b, edge) => edge === 'top' || edge === 'bottom' ? boxes[b][3] : boxes[b][2];
  // Each side's bleed is capped at half of its thinnest later neighbour (device px).
  const caps = new Map(), later = new Map();
  for (const {a, b, edge} of edges) {
    const key = `${a}:${edge}`;
    caps.set(key, Math.min(caps.has(key) ? caps.get(key) : Infinity, extentOf(b, edge) / 2));
    later.set(key, [...(later.get(key) || []), b]);
  }
  /* The backing under a rounded corner is the earlier neighbour's bleed, capped as above, so a cell
   * next to a thin cell can only be backed behind a smaller radius: reduce it to what every backing
   * covers (overlap + radius must fit under each cap). Otherwise the cutout shows background. */
  const effective = layout.cells.map(() => radius);
  if (radius > 0) {
    for (const {a, b, edge} of edges) {
      effective[b] = Math.min(effective[b], Math.max(0, caps.get(`${a}:${edge}`) - overlap) / ratio);
    }
  }
  const device = layout.cells.map(() => ({}));
  for (const [key, neighbours] of later) {
    const want = overlap + Math.max(...neighbours.map(b => effective[b] > 0 ? Math.ceil(effective[b] * ratio - 1e-9) : 0));
    const amount = Math.min(want, caps.get(key));
    if (!(amount > 0) || touchesEarlier.has(key)) continue;
    const [index, side] = key.split(':');
    const a = Number(index);
    if (coveredBy(bleedRegion(boxes[a], side, amount), boxes.slice(a + 1))) device[a][side] = amount;
  }
  device.forEach((sides, index) => {
    // A grown corner square (two perpendicular grown sides) must be hidden too.
    const [x, y, w, h] = boxes[index];
    for (const vertical of ['top', 'bottom']) {
      for (const horizontal of ['left', 'right']) {
        if (!(vertical in sides && horizontal in sides)) continue;
        const corner = [horizontal === 'left' ? x - sides[horizontal] : x + w,
          vertical === 'top' ? y - sides[vertical] : y + h, sides[horizontal], sides[vertical]];
        if (!coveredBy(corner, boxes.slice(index + 1))) delete sides[horizontal];
      }
    }
    for (const [side, amount] of Object.entries(sides)) cells[index].grow[side] = amount / ratio;
  });
  /* Earlier cells are final here: a bleed that was dropped (the side or a corner square is not under
   * later cells) or never grown (the side touches an even earlier cell) backs no corner, so each cell's
   * radius shrinks to what every earlier neighbour's granted bleed covers, and it is rounded only if
   * something is left. This mirrors the export's presentation_placements. */
  if (radius > 0) {
    layout.cells.forEach((_, b) => {
      const shared = edges.filter(edge => edge.b === b);
      if (!shared.length) return;
      const backed = Math.min(...shared.map(({a, edge}) => Math.max(0, (device[a][edge] || 0) - overlap) / ratio));
      const final = Math.min(effective[b], backed);
      if (final > 0) {
        cells[b].radius = final;
        cells[b].rounded = new Set(shared.map(({edge}) => OPPOSITE_SIDE[edge]));
      }
    });
  }
  return {cells, radius};
}
/* Lateral jitter as overscan: the media target is the unchanged cell stretched by
 * 1+2J along the strip and shifted by the resolved offset, so it always contains
 * the cell. A cell spanning the full canvas width runs along x, one spanning the
 * full height along y; one spanning both (one strip) follows the orientation:
 * portrait x, landscape y. Any other cell uses its longer side in pixels (x when
 * width >= height), as render_triptych._jitter_axis does. J and the offset are
 * fractions of the drawn cell box along that axis; a strip bleeds only across, so
 * that is the canvas extent. */
function overscanFor(cell, layout, orientation, width, height) {
  const jitter = layout.presentation ? number(layout.presentation.lateral_jitter) : 0;
  if (!(jitter > 0) || cell.lateral_offset === undefined) return null;
  const [, , w, h] = cell.rect.map(number);
  const fullWidth = Math.abs(w - 1) <= EDGE_EPSILON, fullHeight = Math.abs(h - 1) <= EDGE_EPSILON;
  const axis = fullWidth && !fullHeight ? 'x' : fullHeight && !fullWidth ? 'y' :
    fullWidth && fullHeight ? (orientation === 'portrait' ? 'x' : 'y') : w * width >= h * height ? 'x' : 'y';
  return {axis, jitter, offset:number(cell.lateral_offset)};
}
function mediaTarget(geometry) {
  const target = {x:0, y:0, w:geometry.width, h:geometry.height};
  const overscan = geometry.overscan;
  if (overscan) {
    const {axis, jitter, offset} = overscan;
    if (axis === 'x') { target.x = (offset - jitter) * geometry.width; target.w = (1 + 2*jitter) * geometry.width; }
    else { target.y = (offset - jitter) * geometry.height; target.h = (1 + 2*jitter) * geometry.height; }
  }
  return target;
}
function boxGeometry(node) {
  if (node.geometry) return node.geometry;
  const rect = node.box?.getBoundingClientRect?.();
  return rect && rect.width > 0 && rect.height > 0 ? {width:rect.width, height:rect.height, overscan:null} : null;
}
const percent = (value, total) => `${100 * value / total}%`;
/* Place the media element inside its cell box. Without a slice the element is the
 * box (or its jitter overscan) and CSS object-fit does the fitting. With a slice
 * the renderer's semantics apply: crop the source to the slice window, then fit
 * that window to the box with the cell's fit, positioned by the cell focal point.
 * The element is the whole source at the window's scale, so its aspect is the
 * source aspect (no stretch). `origin` overrides the slice origin (panel driver). */
function placeMedia(node, origin) {
  const media = node.media;
  if (!media) return;
  const rawRect = resolveSliceRect(node);
  const geometry = boxGeometry(node);
  if (!isPartialSlice(rawRect)) {
    // A partial slice forced cover at 50% 50%; CSS object-fit fits a full frame, so restore the cell's.
    const fitting = node.cell ? {objectFit:node.cell.fit ?? 'cover',
      objectPosition:(node.cell.focal ?? ['1/2', '1/2']).map(v => `${number(v)*100}%`).join(' ')} : {};
    if (!geometry || !geometry.overscan) {
      Object.assign(media.style, {width:'100%', height:'100%', left:'0', top:'0', marginLeft:'0', marginTop:'0',
        position:'', transform:'', clipPath:'', visibility:'', ...fitting});
      return;
    }
    const target = mediaTarget(geometry), guard = COVER_GUARD;
    Object.assign(media.style, {position:'absolute', left:percent(target.x - guard, geometry.width),
      top:percent(target.y - guard, geometry.height), width:percent(target.w + 2*guard, geometry.width),
      height:percent(target.h + 2*guard, geometry.height), marginLeft:'0', marginTop:'0', transform:'',
      clipPath:'', visibility:'', ...fitting});
    return;
  }
  const [sliceX, sliceY, sw, sh] = sliceValues(rawRect);
  const [sx, sy] = origin ?? [sliceX, sliceY];
  const sourceWidth = media.videoWidth || media.naturalWidth || 0;
  const sourceHeight = media.videoHeight || media.naturalHeight || 0;
  if (!geometry || !(sourceWidth > 0 && sourceHeight > 0)) {
    // Size unknown until the media decodes; never show an unfitted full frame.
    Object.assign(media.style, {visibility:'hidden'});
    return;
  }
  const fit = node.cell?.fit ?? 'cover';
  const [fx, fy] = (node.cell?.focal ?? ['1/2', '1/2']).map(number);
  const target = mediaTarget(geometry);
  const guard = fit === 'cover' ? COVER_GUARD : 0;
  const tw = target.w + 2*guard, th = target.h + 2*guard;
  const windowWidth = sw * sourceWidth, windowHeight = sh * sourceHeight;
  const scale = (fit === 'cover' ? Math.max : Math.min)(tw / windowWidth, th / windowHeight);
  const windowLeft = target.x - guard + (tw - windowWidth*scale) * fx;
  const windowTop = target.y - guard + (th - windowHeight*scale) * fy;
  Object.assign(media.style, {
    position:'absolute',
    left:percent(windowLeft - sx*sourceWidth*scale, geometry.width),
    top:percent(windowTop - sy*sourceHeight*scale, geometry.height),
    width:percent(sourceWidth*scale, geometry.width), height:percent(sourceHeight*scale, geometry.height),
    marginLeft:'0', marginTop:'0', transform:'', visibility:'',
    // The element's aspect equals the source's; cover only absorbs sub-pixel rounding.
    objectFit:'cover', objectPosition:'50% 50%',
    // Contain shows only the window, letterboxed by the box background like the renderer's pad.
    clipPath: fit === 'cover' ? '' :
      `inset(${100*sy}% ${100*(1-sx-sw)}% ${100*(1-sy-sh)}% ${100*sx}%)`,
  });
}
function applySlice(node) {
  const rawRect = resolveSliceRect(node);
  const clear = element => {
    if (!element) return;
    if (element.dataset) delete element.dataset.sliceRect;
    for (const prop of ['--slice-x', '--slice-y', '--slice-w', '--slice-h']) removeCssProp(element.style, prop);
  };
  if (!isPartialSlice(rawRect)) {
    clear(node.box); clear(node.media);
    placeMedia(node);
    return;
  }
  const [sx,sy,sw,sh] = sliceValues(rawRect);
  const rectStr = `${sx},${sy},${sw},${sh}`;
  for (const element of [node.box, node.media]) {
    if (!element) continue;
    if (!element.dataset) element.dataset = {};
    element.dataset.sliceRect = rectStr;
    setCssProp(element.style, '--slice-x', String(sx));
    setCssProp(element.style, '--slice-y', String(sy));
    setCssProp(element.style, '--slice-w', String(sw));
    setCssProp(element.style, '--slice-h', String(sh));
  }
  placeMedia(node);
}

  // Proof-only accounting in the existing native frame callback. Comparing two
  // polled playheads aliases complete loops; counting callbacks alone mistakes
  // repeated presentation of one frame for progress. Keep both source-specific
  // changes and the longest foreground gap, including gaps recovered or retired
  // entirely between verifier polls. The callback writes a preallocated ring.
  class FrameProgress {
    constructor(supported, capacity = 128) {
      this.supported = Boolean(supported); this.capacity = capacity;
      this.points = new Float64Array(capacity * 3);
      this.epoch = 0; this.changes = 0; this.lifetimeMaxGapMs = 0;
      this.url = null; this.live = false; this.foreground = false; this.running = false;
      this.sourceChanges = 0; this.mediaTime = null; this.lastChangeWall = null;
      this.foregroundSince = null; this.lastForegroundChangeWall = null; this.pausedAt = null;
      this.maxGapMs = 0; this.assignedAt = 0; this.writeIndex = 0; this.traceLength = 0;
    }
    assign(url, wall) {
      this.retire(wall);
      this.url = url; this.epoch++; this.live = true; this.assignedAt = wall;
      this.sourceChanges = 0; this.mediaTime = null; this.lastChangeWall = null;
      this.foregroundSince = null; this.lastForegroundChangeWall = null; this.pausedAt = null;
      this.maxGapMs = 0; this.writeIndex = 0; this.traceLength = 0;
    }
    gap(wall) {
      return this.foreground && this.running ? Math.max(0, wall - this.lastForegroundChangeWall) : 0;
    }
    seal(wall) {
      this.maxGapMs = Math.max(this.maxGapMs, this.gap(wall));
      this.lifetimeMaxGapMs = Math.max(this.lifetimeMaxGapMs, this.maxGapMs);
    }
    observe(wall, mediaTime) {
      if (!this.live || !this.supported || !Number.isFinite(wall) || !Number.isFinite(mediaTime) ||
          wall < this.assignedAt || (this.lastChangeWall !== null && wall < this.lastChangeWall) ||
          mediaTime === this.mediaTime) return;
      this.seal(wall);
      this.changes++; this.sourceChanges++; this.mediaTime = mediaTime; this.lastChangeWall = wall;
      if (this.foreground)
        this.lastForegroundChangeWall = Math.max(this.lastForegroundChangeWall, this.running ? wall : Math.min(wall, this.pausedAt));
      const offset = this.writeIndex * 3;
      this.points[offset] = wall; this.points[offset + 1] = mediaTime; this.points[offset + 2] = this.changes;
      this.writeIndex = (this.writeIndex + 1) % this.capacity;
      this.traceLength = Math.min(this.traceLength + 1, this.capacity);
    }
    setForeground(value, wall, running = this.running) {
      if (!this.live || this.foreground === value) return;
      this.seal(wall); this.foreground = value;
      if (value) {
        this.foregroundSince = wall; this.lastForegroundChangeWall = wall; this.running = running;
        this.pausedAt = running ? null : wall;
      } else { this.running = false; this.pausedAt = null; }
    }
    setRunning(value, wall) {
      if (!this.foreground || this.running === value) return;
      this.seal(wall); this.running = value;
      // Remove exactly the deliberate pause duration, preserving active time
      // without progress on both sides. A frame delivered during pause records
      // progress at its frozen active-time boundary. REST never moves the anchor.
      if (value) {
        this.lastForegroundChangeWall += wall - this.pausedAt; this.pausedAt = null;
      } else this.pausedAt = wall;
    }
    retire(wall) {
      this.seal(wall); this.live = false; this.foreground = false; this.running = false;
    }
    snapshot(wall, includeTrace = false) {
      // Seal a polled ongoing gap too: subsequent recovery cannot erase it.
      this.seal(wall);
      const result = {schema: 1, supported: this.supported, url: this.url, epoch: this.epoch,
        live: this.live, changes: this.changes, sourceChanges: this.sourceChanges,
        lastChangeWall: this.lastChangeWall, mediaTime: this.mediaTime,
        foreground: this.foreground, running: this.running, foregroundSince: this.foregroundSince,
        lastForegroundChangeWall: this.lastForegroundChangeWall, maxGapMs: this.maxGapMs,
        currentGapMs: this.gap(wall), lifetimeMaxGapMs: this.lifetimeMaxGapMs};
      if (includeTrace) {
        result.trace = [];
        for (let i = 0; i < this.traceLength; i++) {
          const offset = ((this.writeIndex - this.traceLength + i + this.capacity) % this.capacity) * 3;
          result.trace.push({wall: this.points[offset], mediaTime: this.points[offset + 1], changes: this.points[offset + 2]});
        }
      }
      return result;
    }
  }

  class MasterSimClock {
    constructor({maxDeltaSec = .1, requestFrame = fn => root.requestAnimationFrame(fn),
      cancelFrame = id => root.cancelAnimationFrame(id), onError = error => console.error(error)} = {}) {
      this.simTime = 0; this.dt = 0; this.running = false;
      this.maxDeltaSec = maxDeltaSec; this.requestFrame = requestFrame; this.cancelFrame = cancelFrame;
      this.onError = onError; this.subscribers = new Set(); this.last = null; this.frameId = null;
      this.boundTick = timestamp => this.tick(timestamp);
    }
    subscribe(fn) { this.subscribers.add(fn); return () => this.subscribers.delete(fn); }
    start() {
      if (this.running) return;
      this.running = true; this.last = null; this.frameId = this.requestFrame(this.boundTick);
    }
    pause() {
      this.running = false; this.last = null; this.dt = 0;
      if (this.frameId !== null) this.cancelFrame(this.frameId);
      this.frameId = null;
    }
    tick(timestamp) {
      if (!this.running) return;
      this.dt = this.last === null ? 0 : Math.min(this.maxDeltaSec, Math.max(0, (timestamp - this.last) / 1000));
      this.last = timestamp; this.simTime += this.dt;
      for (const fn of this.subscribers) {
        try { fn(this.simTime, this.dt); } catch (error) { this.onError(error); }
      }
      if (this.running) this.frameId = this.requestFrame(this.boundTick);
    }
    dispose() { this.pause(); this.subscribers.clear(); }
  }

  const cancelled = () => new DOMException('Selection superseded', 'AbortError');
  class DeferredHandoffError extends Error {
    constructor(reason, detail = {}) {
      super(reason); this.name = 'DeferredHandoffError'; this.detail = detail;
    }
  }
  const nativePlayFailure = error => {
    if (error?.name !== 'AbortError') return error;
    const failure = new Error(`Native playback rejected (AbortError): ${String(error.message || error)}`);
    failure.cause = error; return failure;
  };

  // Conservative interaction profile, not a claim about hardware decoder
  // capacity: touch laptops and tablets share the mobile four-foreground cap.
  // any-pointer also catches a coarse touchscreen paired with a fine mouse.
  function foregroundLimit(environment = root) {
    const navigator = environment.navigator || {};
    const coarse = environment.matchMedia?.('(any-pointer: coarse)').matches ||
      environment.matchMedia?.('(pointer: coarse)').matches;
    const mobile = navigator.userAgentData?.mobile || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');
    return Number(navigator.maxTouchPoints) > 0 || coarse || mobile ? 4 : 12;
  }

  // The permit spans priming AND the entire fade. Admission probes use this
  // same queue: background metadata loading cannot add a second standby.
  class PreparationGate {
    constructor(changed) { this.active = 0; this.queue = []; this.changed = changed; }
    acquire(signal) {
      return new Promise((resolve, reject) => {
        const job = {signal, resolve, reject, abort: null};
        job.abort = () => {
          const index = this.queue.indexOf(job);
          if (index >= 0) this.queue.splice(index, 1);
          reject(cancelled());
        };
        if (signal?.aborted) { reject(cancelled()); return; }
        signal?.addEventListener('abort', job.abort, {once: true});
        this.queue.push(job); this.drain();
      });
    }
    drain() {
      if (this.active || !this.queue.length) return;
      const job = this.queue.shift();
      job.signal?.removeEventListener('abort', job.abort);
      if (job.signal?.aborted) { job.reject(cancelled()); this.drain(); return; }
      this.active = 1; this.changed(1);
      let released = false;
      job.resolve(() => {
        if (released) return;
        released = true; this.active = 0; this.changed(0); this.drain();
      });
    }
  }

  class Session {
    constructor(stage, options = {}) {
      this.stage = stage; this.options = options;
      Object.defineProperty(this, 'maxForeground', {value: foregroundLimit(root), enumerable: true});
      this.crossfadeSec = options.crossfadeSec ?? 1.2;
      this.effectsEnabled = Boolean(options.effects) && !options.reducedMotion;
      this.effectSettings = root.SimvltaneaPresence?.normalizeSettings(options.effectSettings) ?? null;
      this.primeTimeoutMs = options.primeTimeoutMs ?? 10000;
      this.progressTimeoutMs = options.progressTimeoutMs ?? 2000;
      this.nodes = new Map(); this.slots = new Map(); this.sources = new Map();
      this.plan = null; this.ready = false; this.running = false; this.finished = false;
      this.error = null; this.lastFailure = null; this.disposed = false;
      this.frame = 0; this.generation = 0; this.orientation = null; this.orientationOverride = null;
      this.starting = false; this.initializing = false; this.restarting = false;
      this.playingIntent = false; this.revision = 0; this.pending = null; this.draining = false;
      this.controller = null; this.fade = null; this.seam = null; this.promotion = null; this.handoff = null;
      this.territory = null; this.bindings = new WeakMap();
      this.audio = {context: null, mode: 'none', enabled: false, blocked: null, input: null};
      this.sound = {enabled: false, volume: .7}; this.master = null;
      this.events = []; this.activeStandbys = 0; this.maxConcurrentStandbys = 0;
      this.gate = new PreparationGate(active => {
        this.activeStandbys = active;
        this.maxConcurrentStandbys = Math.max(active, this.maxConcurrentStandbys);
      });
      this.clock = new MasterSimClock({onError: error => this.report(error)});
      this.clock.subscribe((time, dt) => this.tick(time, dt));
      this.resizeObserver = new ResizeObserver(() => this.applyLayout());
      this.resizeObserver.observe(stage);
      this.visibility = () => {
        if (document.hidden) this.suspend();
        else if (this.playingIntent) this.start().catch(error => this.report(error));
      };
      document.addEventListener('visibilitychange', this.visibility);
      this.proof = null;
      if (new URLSearchParams(root.location?.search || '').get('proof') === '1') {
        this.proof = document.createElement('pre'); this.proof.id = 'playback-proof';
        Object.assign(this.proof.style, {position: 'fixed', top: '8px', left: '8px', zIndex: '10000',
          color: '#fff', background: '#000b', fontSize: '10px', pointerEvents: 'none', padding: '8px'});
        document.body.append(this.proof);
      }
      this.proofAt = -1;
      this.proofRetired = this.proof ? [] : null;
      this.proofRetiredCount = 0; this.proofMaxGapMs = 0; this.proofSuspensionCount = 0;
    }
    get origin() { return (this.audio.context?.currentTime ?? 0) - this.clock.simTime; }
    record(type, id = null, detail = {}) {
      this.events.push({type, id, time: this.clock.simTime, wall: performance.now(), ...detail});
      if (this.events.length > 256) this.events.shift();
    }
    proofProgressSummary(wall, includeTrace = false) {
      if (!this.proof) return null;
      let supported = true;
      for (const node of this.slots.values()) for (const deck of node.decks) {
        if (!deck.progress) { supported = false; continue; }
        const progress = deck.progress.snapshot(wall);
        supported = supported && progress.supported;
        this.proofMaxGapMs = Math.max(this.proofMaxGapMs, progress.lifetimeMaxGapMs);
      }
      return {schema: 1, supported, maxGapMs: this.proofMaxGapMs,
        suspensionCount: this.proofSuspensionCount, retiredCount: this.proofRetiredCount,
        nativeLoopSeek: {attempted: this.loopSeekProof?.attempted ?? 0,
          recovered: this.loopSeekProof?.recovered ?? 0, rejected: this.loopSeekProof?.rejected ?? 0,
          interrupted: this.loopSeekProof?.interrupted ?? 0, dropped: this.loopSeekProof?.dropped ?? 0,
          receipts: includeTrace ? (this.loopSeekProof?.receipts || []).slice() : []},
        retired: includeTrace ? this.proofRetired.slice() : []};
    }
    report(error, node = null) {
      if (error?.name === 'AbortError') return;
      this.lastFailure = String(error?.message || error);
      this.record('media-failure', node?.id, {message: this.lastFailure});
      try { this.options.onError?.(error, node); }
      catch (_) { this.record('observer-failure', node?.id); }
    }
    notifyAudio(node) {
      try { this.options.onAudioNode?.(node, this.audio.context); }
      catch (error) { this.report(error, node); }
    }
    notifyDeckAudio(deck) {
      if (deck.enteredAt === null || !deck.binding || !deck.item) return;
      try { this.options.onDeckAudio?.(deck, this.audio.context); }
      catch (error) { this.report(error); }
    }
    status() {
      this.stage.dataset.status = this.running ? 'playing' : this.ready ? 'paused' : 'loading';
      try { this.options.onChange?.(this); } catch (error) { this.report(error); }
    }
    async withPreparation(task, {signal} = {}) {
      if (this.disposed) throw cancelled();
      const release = await this.gate.acquire(signal);
      try { if (this.disposed || signal?.aborted) throw cancelled(); return await task(); }
      finally { release(); }
    }
    createSlot(id, ordinal) {
      const box = document.createElement('div'); box.className = 'loop'; box.dataset.loopId = id;
      Object.assign(box.style, {position: 'absolute', overflow: 'hidden', display: 'none'});
      const node = {id, ordinal, box, decks: [], active: null, promoting: null, media: null, item: null, audio: null,
        source: null, kind: 'video', busy: false, callbacks: 0, decoded: null, stallCount: 0,
        targetGain: null, resting: false, phase: 'IDLE', span: null};
      for (let i = 0; i < 2; i++) {
        const media = document.createElement('video');
        media.dataset.loopId = id; media.dataset.deck = 'standby';
        media.muted = true; media.defaultMuted = true; media.playsInline = true;
        media.setAttribute('playsinline', ''); media.loop = true; media.preload = 'auto';
        media.setAttribute('aria-label', `Loop ${ordinal}`);
        Object.assign(media.style, {position: 'absolute', inset: '0', width: '100%', height: '100%',
          objectFit: 'cover', opacity: '0', pointerEvents: 'none', transition: 'none'});
        const deck = {media, url: null, item: null, binding: null, weight: 0, frameId: null, callbacks: 0, decoded: null,
          presence: 1, presenceTarget: null, spectralPriority: 1, enteredAt: null, sourceEpoch: 0, loopSeek: null};
        if (this.proof) {
          deck.progress = new FrameProgress(typeof media.requestVideoFrameCallback === 'function');
          deck.proofDeck = i;
        }
        let frameEpoch = deck.progress?.epoch, frameSourceEpoch = deck.sourceEpoch;
        const watch = (wall, metadata) => {
          deck.callbacks++; deck.decoded = {mediaTime: metadata.mediaTime, presentedFrames: metadata.presentedFrames, wall};
          // A callback registered before src changed cannot certify the new
          // source. The next registration belongs to its current epoch.
          if (deck.progress && deck.progress.epoch === frameEpoch && media.currentSrc === deck.url)
            deck.progress?.observe(wall, metadata.mediaTime);
          if (deck.sourceEpoch === frameSourceEpoch && media.currentSrc === deck.url) {
            const seek = deck.loopSeek;
            // The retained outgoing deck can recover while its slot is busy.
            // Preserve that fact independently of the active guard's eligibility.
            if (seek?.attempt && seek.epoch === deck.sourceEpoch && seek.url === deck.url &&
                Number.isFinite(metadata.mediaTime) && metadata.mediaTime !== seek.attempt.decoded)
              seek.attempt.progressed = true;
            deck.handoff?.observe(wall, metadata.mediaTime);
          }
          frameEpoch = deck.progress?.epoch;
          frameSourceEpoch = deck.sourceEpoch;
          if (node.active === deck) { node.callbacks++; node.decoded = deck.decoded; }
          if (!this.disposed) deck.frameId = media.requestVideoFrameCallback(watch);
        };
        if (media.requestVideoFrameCallback) deck.frameId = media.requestVideoFrameCallback(watch);
        media.addEventListener('loadedmetadata', () => { if (!this.disposed) this.applyLayout(); });
        media.addEventListener('waiting', () => { if (node.active === deck && this.running) node.stallCount++; });
        node.decks.push(deck); box.append(media);
      }
      this.slots.set(id, node); this.stage.append(box); return node;
    }
    reconcile({plan, items, playing = this.playingIntent, atLoopBoundary = false}) {
      if (this.disposed) return Promise.resolve(false);
      if (!plan || !Array.isArray(plan.tracks) || !plan.tracks.length || plan.tracks.length > this.maxForeground ||
          !Array.isArray(items) || items.length !== plan.tracks.length ||
          items.some(item => !(item.file instanceof Blob) || !item.sha256)) {
        return Promise.reject(new Error(`Live playback requires 1–${this.maxForeground} admitted media items and matching tracks`));
      }
      if (new Set(plan.tracks.map(track => track.id)).size !== items.length) {
        return Promise.reject(new Error('Duplicate live slot id'));
      }
      // Existing foregrounds remain alive until reconciliation finishes. Refuse
      // incompatible slot identities before aborting any current transaction.
      if (new Set([...this.nodes.keys(), ...plan.tracks.map(track => track.id)]).size > this.maxForeground) {
        return Promise.reject(new Error('Reuse the existing panels within this device\'s live panel limit'));
      }
      this.revision++;
      this.controller?.abort();
      if (this.pending) this.pending.resolve(false);
      const promise = new Promise(resolve => {
        this.pending = {plan, items, playing, atLoopBoundary, revision: this.revision, resolve};
      });
      if (!this.draining) this.drain();
      return promise;
    }
    async drain() {
      this.draining = true;
      try {
        while (this.pending && !this.disposed) {
          const request = this.pending; this.pending = null;
          const controller = this.controller = new AbortController();
          let success = true;
          try {
            if (request.playing && !this.playingIntent) await this.start();
            else if (!request.playing && this.playingIntent) this.pause();
            this.plan = request.plan; this.territory = null;
            const ids = new Set(request.plan.tracks.map(track => track.id));
            for (const [index, track] of request.plan.tracks.entries()) {
              if (controller.signal.aborted) throw cancelled();
              const node = this.slots.get(track.id) || this.createSlot(track.id, index + 1);
              this.nodes.set(track.id, node); node.ordinal = index + 1;
              node.span = track.spans?.[0] ?? null;
              const item = request.items[index], source = request.plan.sources[index];
              if (node.item?.sha256 !== item.sha256) {
                const more = request.items.slice(index + 1).some((other, j) =>
                  this.nodes.get(request.plan.tracks[index + j + 1].id)?.item?.sha256 !== other.sha256);
                try {
                  await this.replace(node, item, source.id, controller.signal,
                    more ? Math.min(.2, this.crossfadeSec) : this.crossfadeSec, request.atLoopBoundary);
                } catch (error) {
                  if (error.name === 'AbortError') throw error;
                  success = false;
                  if (error instanceof DeferredHandoffError)
                    this.record('handoff-deferred', node.id, {reason: error.message, ...error.detail});
                  else this.report(error, node);
                }
              } else {
                node.source = source.id;
              }
              if (controller.signal.aborted) throw cancelled();
              this.sources.set(source.id, {url: node.active?.url ?? null, sha256: node.item?.sha256});
            }
            for (const [id, node] of this.nodes) if (!ids.has(id)) {
              node.resting = false; node.targetGain = null;
              node.box.style.opacity = '1'; node.box.style.transition = '';
              for (const deck of node.decks) this.unload(deck);
              node.item = null; node.active = null; node.media = null; node.audio = null;
              node.box.style.display = 'none'; node.phase = 'IDLE'; this.nodes.delete(id);
            }
            this.sources = new Map([...this.nodes.values()].map(node =>
              [node.source, {url: node.active?.url ?? null, sha256: node.item?.sha256}]));
            this.ready = [...this.nodes.values()].every(node => Boolean(node.active));
            this.applyLayout(); this.updateAudio(); this.status();
          } catch (error) {
            success = false; this.report(error);
          } finally {
            if (this.controller === controller) this.controller = null;
            request.resolve(success && request.revision === this.revision);
          }
        }
      } finally { this.draining = false; }
    }
    async prime(deck, node, signal) {
      const media = deck.media;
      await new Promise((resolve, reject) => {
        let done = false, frame = null;
        const finish = error => {
          if (done) return; done = true; clearTimeout(timer);
          signal.removeEventListener('abort', abort);
          media.removeEventListener('error', failure); media.removeEventListener('loadeddata', fallback);
          if (frame !== null) media.cancelVideoFrameCallback?.(frame);
          error ? reject(error) : resolve();
        };
        const abort = () => finish(cancelled());
        const failure = () => finish(new Error('Incoming clip could not be decoded'));
        const fallback = () => { if (media.readyState >= 2 && media.videoWidth > 0) finish(); };
        const timer = setTimeout(() => finish(new Error('Incoming clip did not present a frame in time')), this.primeTimeoutMs);
        signal.addEventListener('abort', abort, {once: true});
        media.addEventListener('error', failure, {once: true});
        if (media.requestVideoFrameCallback) frame = media.requestVideoFrameCallback(() => finish());
        else media.addEventListener('loadeddata', fallback);
        if (signal.aborted) { abort(); return; }
        node.phase = 'PRIMING';
        // Request playback first. Passive canplay waits deadlock on mobile preload policies.
        try { media.play().catch(error => finish(error)); } catch (error) { finish(error); }
      });
    }
    waitForSeam(node, signal) {
      if (!this.running || node.resting || !node.media || node.media.currentTime < .04) return Promise.resolve();
      return new Promise((resolve, reject) => {
        const began = this.clock.simTime, allowance = this.progressTimeoutMs / 1000;
        const media = node.media, duration = media.duration;
        const deadline = began + allowance + (Number.isFinite(duration) && duration > 0 ? Math.max(0, duration - media.currentTime) : 0);
        let previous = media.currentTime, decodedTime = node.decoded?.mediaTime, progressAt = began, done = false;
        const finish = error => {
          if (done) return; done = true;
          unsubscribe(); signal.removeEventListener('abort', abort);
          if (this.seam?.node === node) this.seam = null;
          error ? reject(error) : resolve();
        };
        const abort = () => finish(cancelled());
        const unsubscribe = this.clock.subscribe(time => {
          const current = media.currentTime;
          if (current + .05 < previous) { finish(); return; }
          if (media.requestVideoFrameCallback ? node.decoded?.mediaTime !== decodedTime : current !== previous) progressAt = time;
          decodedTime = node.decoded?.mediaTime;
          previous = current;
          // WebKit can remain ready/playing while native looping stops presenting
          // frames. Such a source cannot produce the seam this permit waits for.
          if (time - progressAt >= allowance || time >= deadline) {
            node.stallCount++;
            this.record('seam-fallback', node.id, {reason: time - progressAt >= allowance ? 'no-frames' : 'no-wrap',
              waitedSec: time - began, currentTime: current, decodedTime});
            finish();
          }
        });
        this.seam = {node, finish};
        signal.addEventListener('abort', abort, {once: true});
        if (signal.aborted) abort();
      });
    }
    watchHandoff(node, incoming, outgoing, signal) {
      const media = incoming.media, url = incoming.url, epoch = incoming.sourceEpoch;
      const budget = Math.max(1, Math.min(800, this.progressTimeoutMs));
      let timer = null, playTask = null, done = false, previous = incoming.decoded?.mediaTime;
      const began = performance.now(), playGeneration = this.generation;
      let lastAt = began, frames = 0, pausedAt = null, played = false, fresh = false, resolveReady, rejectReady;
      const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
      // A later fade/promotion failure also rejects its own waiter. The initial
      // freshness promise may already have resolved by then.
      ready.catch(() => {});
      const owned = () => !this.disposed && this.nodes.get(node.id) === node && node.active === outgoing &&
        incoming.url === url && incoming.sourceEpoch === epoch && incoming.handoff === state;
      const stop = () => {
        if (done) return; done = true; clearTimeout(timer); clearTimeout(playTask);
        signal.removeEventListener('abort', abort); media.removeEventListener('error', decodeError);
        media.removeEventListener('timeupdate', fallback);
        if (incoming.handoff === state) incoming.handoff = null;
        if (this.handoff === state) this.handoff = null;
      };
      const fail = error => {
        if (done) return;
        state.error = error; stop(); rejectReady(error);
        if (this.fade?.incoming === incoming && this.fade.handoff === state) this.fade.finish(error);
        if (this.promotion?.deck === incoming && this.promotion.handoff === state) this.promotion.finish(error);
      };
      const defer = reason => {
        if (media.error) { fail(new Error('Incoming clip could not be decoded')); return; }
        fail(new DeferredHandoffError(reason,
          {url, sourceEpoch: epoch, phase: state.phase, visible: state.visible,
            noProgressMs: performance.now() - lastAt, waitedMs: performance.now() - began, budgetMs: budget}));
      };
      const abort = () => fail(cancelled());
      const decodeError = () => { if (media.error) fail(new Error('Incoming clip could not be decoded')); };
      const arm = () => {
        clearTimeout(timer);
        if (!done && pausedAt === null) timer = setTimeout(check,
          Math.max(1, Math.min(lastAt + budget, fresh ? Infinity : began + budget) - performance.now()));
      };
      const check = () => {
        if (done) return;
        if (!owned() || signal.aborted) { abort(); return; }
        if (media.error) { decodeError(); return; }
        if (!this.running || root.document?.hidden) { state.pause(); return; }
        if (!fresh && performance.now() - began >= budget) {
          defer(played ? 'Incoming frames did not become ready' : 'Incoming play did not settle'); return;
        }
        if (performance.now() - lastAt >= budget) { defer('Incoming frames did not keep advancing'); return; }
        arm();
      };
      const finishFresh = () => {
        if (done || fresh) return;
        if (!owned() || signal.aborted) { abort(); return; }
        if (media.error) { decodeError(); return; }
        if (!this.running || root.document?.hidden) { state.pause(); return; }
        if (performance.now() - began >= budget) {
          defer(played ? 'Incoming frames did not become ready' : 'Incoming play did not settle'); return;
        }
        if (played && frames >= 2 && !media.seeking && !media.paused) { fresh = true; resolveReady(); }
      };
      const state = {ready, visible: false, phase: 'freshness', error: null, stop,
        assert: () => { if (state.error) throw state.error; if (!owned()) throw cancelled(); },
        timeout: reason => {
          if (!owned()) { fail(cancelled()); return state.error || cancelled(); }
          defer(reason); return state.error;
        },
        observe: (wall, decoded) => {
          if (done || pausedAt !== null || !owned() || !Number.isFinite(decoded)) return;
          if (media.error) { decodeError(); return; }
          if (media.seeking || media.paused) frames = 0;
          if (decoded === previous) return;
          // Do not let a late callback erase an already-exceeded progress bound.
          if (wall - lastAt >= budget) { defer('Incoming frames did not keep advancing'); return; }
          previous = decoded; lastAt = Math.max(lastAt, wall);
          if (!media.seeking && !media.paused) frames++;
          finishFresh();
        },
        pause: () => {
          if (done || pausedAt !== null) return;
          if (!state.visible) { defer('Playback paused before fresh incoming frames'); return; }
          pausedAt = performance.now(); clearTimeout(timer);
        },
        resume: () => {
          if (done || pausedAt === null) return;
          lastAt += performance.now() - pausedAt; pausedAt = null; arm();
        }};
      const fallback = () => {
        if (media.currentSrc === url && media.readyState >= 2) state.observe(performance.now(), media.currentTime);
      };
      incoming.handoff = state; this.handoff = state;
      signal.addEventListener('abort', abort, {once: true});
      media.addEventListener('error', decodeError);
      if (!media.requestVideoFrameCallback) media.addEventListener('timeupdate', fallback);
      check();
      // Let the first frame's native callbacks settle, then reassert playback
      // once while hidden. This owns no new deadline and cannot revive a paused
      // or superseded request. Visible promotion still plays on its own stack.
      if (!done) playTask = setTimeout(() => {
        playTask = null;
        if (done || !owned() || state.visible || this.generation !== playGeneration ||
            !this.running || root.document?.hidden) return;
        try { Promise.resolve(media.play()).then(() => {
          if (done || !owned()) return;
          played = true; finishFresh();
        }, error => { if (owned()) fail(nativePlayFailure(error)); }); }
        catch (error) { fail(nativePlayFailure(error)); }
      }, 0);
      return state;
    }
    playPromoted(deck, signal, handoff = null) {
      // Some WebKit media pipelines present their primed frame but do not
      // advance after becoming visible until play() is requested again. Keep
      // this request on the promotion stack, with no intervening RAF.
      return new Promise((resolve, reject) => {
        const media = deck.media;
        const url = deck.url, epoch = deck.sourceEpoch, generation = this.generation;
        let done = false, fulfilled = false, frames = 0, frame = null, previous = deck.decoded?.mediaTime;
        const finish = (error, verified = false) => {
          if (done) return; done = true; clearTimeout(timer);
          signal.removeEventListener('abort', abort);
          media.removeEventListener('timeupdate', fallback);
          if (frame !== null) media.cancelVideoFrameCallback?.(frame);
          if (this.promotion === promotion) this.promotion = null;
          error ? reject(error) : resolve(verified);
        };
        const abort = () => finish(cancelled());
        const owned = () => !signal.aborted && !this.disposed && this.generation === generation &&
          deck.url === url && deck.sourceEpoch === epoch && media.currentSrc === url;
        const verify = () => {
          if (done) return;
          if (!owned()) { abort(); return; }
          if (media.error) { finish(new Error('Promoted clip could not be decoded')); return; }
          if (media.seeking || media.paused) { frames = 0; return; }
          if (fulfilled && frames >= 2) finish(null, true);
        };
        const progress = current => {
          if (done) return;
          if (!owned()) { abort(); return; }
          if (!Number.isFinite(current) || media.seeking || media.paused) {
            frames = 0;
            if (Number.isFinite(current)) previous = current;
            verify(); return;
          }
          if (current !== previous) { frames++; previous = current; }
          verify();
        };
        const decoded = (_, metadata) => {
          frame = null; progress(metadata.mediaTime);
          if (!done) frame = media.requestVideoFrameCallback(decoded);
        };
        const fallback = () => { if (media.readyState >= 2) progress(media.currentTime); };
        const timer = setTimeout(() => finish(handoff
          ? handoff.timeout('Promoted clip did not present new frames in time')
          : new Error('Promoted clip did not present new frames in time')),
          Math.min(this.primeTimeoutMs, this.progressTimeoutMs));
        const promotion = this.promotion = {deck, finish, handoff};
        signal.addEventListener('abort', abort, {once: true});
        if (signal.aborted) { abort(); return; }
        if (media.requestVideoFrameCallback) frame = media.requestVideoFrameCallback(decoded);
        else { previous = media.currentTime; media.addEventListener('timeupdate', fallback); }
        const rejected = error => finish(signal.aborted || this.disposed || this.generation !== generation ||
          deck.url !== url || deck.sourceEpoch !== epoch ? cancelled() : nativePlayFailure(error));
        try { media.play().then(() => { fulfilled = true; verify(); }, rejected); }
        catch (error) { rejected(error); }
      });
    }
    async replace(node, item, source, signal, duration, atLoopBoundary = false) {
      await this.withPreparation(async () => {
        if (signal.aborted) throw cancelled();
        const outgoing = node.active, incoming = node.decks.find(deck => deck !== outgoing);
        const previous = {active: node.active, media: node.media, item: node.item, source: node.source,
          audio: node.audio, birthTime: node.birthTime, callbacks: node.callbacks, decoded: node.decoded};
        const beganRunning = this.running;
        let handoff = null;
        node.busy = true; node.phase = 'LOADING';
        incoming.item = item; incoming.media.muted = true;
        incoming.presence = this.effectsEnabled ? 0 : 1;
        incoming.presenceTarget = null; incoming.spectralPriority = 1; incoming.enteredAt = null;
        this.applyDeckEffects(incoming, true);
        incoming.url = URL.createObjectURL(item.file);
        incoming.sourceEpoch++; incoming.loopSeek = null;
        incoming.progress?.assign(incoming.url, performance.now());
        incoming.media.src = incoming.url; incoming.media.load();
        node.box.style.display = '';
        this.applyLayout();
        try {
          await this.prime(incoming, node, signal);
          if (signal.aborted) throw cancelled();
          node.phase = 'READY';
          this.bind(incoming);
          if (atLoopBoundary && outgoing) {
            // A ready successor need not keep decoding throughout a future
            // outgoing seam. Park only the hidden deck, without seeking it;
            // the freshness gate below resumes it and verifies new frames.
            if (this.running && !node.resting && node.media.currentTime >= .04) incoming.media.pause();
            await this.waitForSeam(node, signal);
          }
          if (signal.aborted) throw cancelled();
          if (incoming.media.error) throw new Error('Incoming clip could not be decoded');
          if (outgoing && (beganRunning || this.running)) {
            if (!this.running) throw new DeferredHandoffError('Playback paused before fresh incoming frames',
              {url: incoming.url, sourceEpoch: incoming.sourceEpoch, phase: 'freshness', visible: false});
            handoff = this.watchHandoff(node, incoming, outgoing, signal);
            await handoff.ready; handoff.assert();
            handoff.visible = true; handoff.phase = 'fade';
          }
          // Priming can run for several native loops. The resident's entrance
          // begins when it is revealed, independently of the media playhead.
          incoming.enteredAt = this.clock.simTime;
          // Visible incoming frames count throughout the fade and pending
          // promotion, while outgoing frames remain covered until retirement.
          incoming.progress?.setForeground(true, performance.now(), this.running);
          incoming.presence = this.effectsEnabled ? 0 : 1;
          incoming.presenceTarget = null;
          this.applyDeckEffects(incoming);
          this.notifyDeckAudio(incoming);
          incoming.media.style.zIndex = '1';
          if (outgoing) outgoing.media.style.zIndex = '0';
          if (outgoing && this.running && !node.resting && duration > 0) {
            const seek = outgoing.loopSeek, attempt = seek?.attempt;
            // A native recovery request can fulfill without producing a frame.
            // Once the successor has passed freshness, use the existing rapid
            // fade instead of retaining that known frozen picture for 1.2 s.
            if (handoff && attempt && attempt.generation === this.generation &&
                seek.url === outgoing.url && seek.epoch === outgoing.sourceEpoch &&
                outgoing.media.currentSrc === outgoing.url && outgoing.media.seeking &&
                !outgoing.media.paused && !outgoing.media.error && !attempt.progressed &&
                Number.isFinite(attempt.decoded) && duration > .2) {
              this.record('handoff-expedited', node.id, {reason: 'outgoing-native-seek-stalled',
                url: outgoing.url, sourceEpoch: outgoing.sourceEpoch, attemptedAt: attempt.time,
                requestedDuration: duration, duration: .2});
              duration = .2;
            }
            node.phase = 'CROSSFADING';
            await new Promise((resolve, reject) => {
              let done = false;
              const finish = error => {
                if (done) return; done = true;
                if (this.fade === fade) this.fade = null;
                signal.removeEventListener('abort', abort);
                error ? reject(error) : resolve();
              };
              const abort = () => finish(cancelled());
              signal.addEventListener('abort', abort, {once: true});
              const fade = this.fade = {node, outgoing, incoming, handoff, began: this.clock.simTime, duration, finish};
              incoming.media.muted = !this.sound.enabled || !this.audio.enabled;
            });
          }
          if (signal.aborted) throw cancelled();
          handoff?.assert();
          if (handoff) handoff.phase = 'promotion';
          // Sound can unlock during the fade after the earlier bind attempt.
          // No audible resident may bypass the persistent master graph.
          this.bind(incoming);
          incoming.weight = 1; incoming.media.style.opacity = '1'; incoming.media.dataset.deck = 'active';
          if (outgoing) outgoing.weight = 0;
          node.promoting = incoming;
          if (!this.running) incoming.media.pause();
          incoming.media.muted = !incoming.binding || !this.sound.enabled || !this.audio.enabled;
          this.applyLayout(); this.updateAudio();
          // A pause settles the waiter without frame proof. If play resumes in
          // the same task, verify again before committing the visible deck.
          let verified = false;
          while (this.running && !verified && !signal.aborted) verified = await this.playPromoted(incoming, signal, handoff);
          if (signal.aborted) throw cancelled();
          handoff?.assert();
          if (!this.running) incoming.media.pause();
          // Promotion is now committed. Until this point the outgoing decoder,
          // Blob URL and ecological identity remain authoritative. Publishing
          // provisional node.item would destroy its lifetime on a late refusal.
          node.active = incoming; node.media = incoming.media; node.item = item; node.source = source;
          node.birthTime = incoming.enteredAt;
          node.audio = incoming.binding; node.callbacks = incoming.callbacks; node.decoded = incoming.decoded;
          node.promoting = null; node.phase = node.resting ? 'RESTING' : 'ACTIVE';
          if (outgoing) this.unload(outgoing);
          this.applyLayout(); this.updateAudio();
          if (node.audio) this.notifyAudio(node);
          this.record('resident', node.id);
        } catch (error) {
          handoff?.stop();
          node.promoting = null;
          Object.assign(node, previous);
          this.unload(incoming);
          if (outgoing) {
            outgoing.weight = 1; outgoing.media.style.opacity = '1'; outgoing.media.dataset.deck = 'active';
            node.callbacks = outgoing.callbacks; node.decoded = outgoing.decoded;
          }
          else node.box.style.display = 'none';
          node.phase = outgoing ? node.resting ? 'RESTING' : 'ACTIVE' : 'IDLE';
          this.applyLayout(); this.updateAudio();
          if (node.audio) this.notifyAudio(node);
          throw error;
        } finally { handoff?.stop(); node.busy = false; }
      }, {signal});
    }
    unload(deck) {
      this.interruptLoopSeek(deck, 'retired');
      deck.loopSeek = null;
      try { this.options.onDeckUnload?.(deck); }
      catch (error) { this.report(error); }
      deck.weight = 0;
      if (deck.binding) {
        const now = this.audio.context.currentTime;
        deck.binding.gain.gain.cancelScheduledValues(now);
        deck.binding.gain.gain.setValueAtTime(0, now);
        deck.binding.filter.frequency.cancelScheduledValues(now);
        deck.binding.target = 0; deck.binding.cutoff = null;
      }
      deck.media.style.opacity = '0'; deck.media.dataset.deck = 'standby'; deck.media.muted = true;
      deck.media.style.filter = ''; deck.presence = 1; deck.presenceTarget = null;
      deck.spectralPriority = 1; deck.enteredAt = null;
      if (deck.url) {
        if (deck.progress) {
          const wall = performance.now(), nativeError = deck.media.error;
          deck.progress.retire(wall);
          const progress = deck.progress.snapshot(wall, true);
          this.proofMaxGapMs = Math.max(this.proofMaxGapMs, progress.lifetimeMaxGapMs);
          this.proofRetiredCount++;
          this.proofRetired.push({id: deck.media.dataset.loopId, deck: deck.proofDeck, ...progress,
            retiredAt: wall, nativeError: nativeError ? {code: nativeError.code, message: nativeError.message} : null});
          if (this.proofRetired.length > 16) this.proofRetired.shift();
        }
        deck.media.pause(); deck.media.removeAttribute('src'); deck.media.load();
        if (this.proof) this.record('resource-retired', deck.media.dataset.loopId, {role: 'deck', url: deck.url,
          currentSrc: deck.media.currentSrc, readyState: deck.media.readyState, paused: deck.media.paused});
        URL.revokeObjectURL(deck.url); deck.url = null;
      }
      deck.item = null;
    }
    bind(deck) {
      const context = this.audio.context;
      if (!context) return deck.binding;
      if (deck.binding) { this.notifyDeckAudio(deck); return deck.binding; }
      let binding = this.bindings.get(deck.media);
      if (!binding) {
        const source = context.createMediaElementSource(deck.media), filter = context.createBiquadFilter();
        const pan = context.createStereoPanner(), gain = context.createGain();
        filter.type = this.effectsEnabled ? 'lowpass' : 'allpass';
        filter.frequency.value = Math.min(20000, context.sampleRate * .45); filter.Q.value = Math.SQRT1_2;
        gain.gain.value = 0; source.connect(filter); filter.connect(pan); pan.connect(gain); gain.connect(this.audio.input);
        binding = {source, filter, pan, gain, target: 0, cutoff: null}; this.bindings.set(deck.media, binding);
      }
      deck.binding = binding; this.applyDeckEffects(deck, true); this.notifyDeckAudio(deck); return binding;
    }
    async unlock(context = null) {
      if (this.disposed) return false;
      if (!this.audio.context) {
        const AudioContext = root.AudioContext || root.webkitAudioContext;
        if (!context && !AudioContext) throw new Error('Web Audio is unavailable');
        this.audio.context = context || new AudioContext();
        if (root.SimvltaneaLiveAudio) {
          this.master = root.SimvltaneaLiveAudio.createMasterBus(this.audio.context, this.sound);
        } else {
          const input = this.audio.context.createGain(), compressor = this.audio.context.createDynamicsCompressor();
          compressor.threshold.value = -12; compressor.knee.value = 10; compressor.ratio.value = 6;
          compressor.attack.value = .01; compressor.release.value = .25;
          input.gain.value = 0; input.connect(compressor); compressor.connect(this.audio.context.destination);
          this.master = {input, setVolume: (volume, enabled) => input.gain.setTargetAtTime(enabled ? volume : 0, this.audio.context.currentTime, .03)};
        }
        this.audio.input = this.master.input;
        this.audio.context.addEventListener('statechange', () => {
          this.audio.enabled = this.audio.context.state === 'running';
          this.updateAudio();
          this.record('audio-state', null, {state: this.audio.context.state});
        });
      }
      const pending = this.audio.context.resume();
      for (const node of this.nodes.values()) {
        for (const deck of node.decks) if (deck.url) this.bind(deck);
        if (node.active) {
          node.audio = node.active.binding;
          this.notifyAudio(node);
        }
      }
      try {
        await pending; this.audio.enabled = this.audio.context.state === 'running';
        this.audio.mode = 'spatial_loops'; this.audio.blocked = null;
        this.applyLayout(); this.updateAudio(); return this.audio.enabled;
      } catch (error) {
        this.audio.blocked = String(error); this.audio.enabled = false; this.updateAudio(); throw error;
      }
    }
    setSound({enabled = this.sound.enabled, volume = this.sound.volume} = {}) {
      this.sound.enabled = Boolean(enabled); this.sound.volume = Math.max(0, Math.min(1, Number(volume) || 0));
      this.master?.setVolume(this.sound.volume, this.sound.enabled);
      this.updateAudio();
    }
    setTargetGain(id, gain) {
      const node = this.nodes.get(id);
      if (!node) return;
      node.targetGain = Math.max(0, Math.min(1, Number(gain) || 0)); this.updateNodeAudio(node);
    }
    setEffects(enabled) {
      if (enabled && !root.SimvltaneaPresence) throw new Error('Clip presence filters are unavailable');
      this.effectsEnabled = Boolean(enabled) && !this.options.reducedMotion;
      for (const node of this.nodes.values()) {
        for (const deck of node.decks) this.applyDeckEffects(deck);
        this.updateNodeAudio(node);
      }
    }
    setEffectSettings(settings) {
      if (!root.SimvltaneaPresence) throw new Error('Clip presence filters are unavailable');
      this.effectSettings = root.SimvltaneaPresence.normalizeSettings({...this.effectSettings, ...settings});
      for (const node of this.nodes.values()) {
        for (const deck of node.decks) if (this.effectsEnabled) this.applyDeckEffects(deck);
        this.updateNodeAudio(node);
      }
      return this.effectSettings;
    }
    setPresence(id, value, spectralPriority = 1) {
      const node = this.nodes.get(id);
      if (!node?.active) return;
      const presence = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
      node.active.presence = node.active.presenceTarget = presence;
      node.active.spectralPriority = Number.isFinite(spectralPriority) ? Math.max(0, Math.min(1, spectralPriority)) : 0;
      if (this.effectsEnabled) this.applyDeckEffects(node.active);
      this.updateNodeAudio(node);
    }
    applyDeckEffects(deck, immediate = false) {
      const settings = this.effectSettings || root.SimvltaneaPresence?.DEFAULT_SETTINGS;
      const targets = this.effectsEnabled && root.SimvltaneaPresence
        ? root.SimvltaneaPresence.filterTargets(deck.presence, this.audio.context?.sampleRate, settings, deck.spectralPriority) : null;
      const decimal = value => Number(value.toFixed(3));
      const filters = [];
      if (targets) {
        if (settings.brightnessDepth > 0) filters.push(`brightness(${decimal(targets.brightness)})`);
        if (settings.saturationDepth > 0) filters.push(`saturate(${decimal(targets.saturation)})`);
        if (settings.blurPx > 0) filters.push(`blur(${decimal(targets.blurPx)}px)`);
      }
      const filter = filters.join(' ');
      if (deck.media.style.filter !== filter) deck.media.style.filter = filter;
      if (!deck.binding) return;
      const binding = deck.binding;
      const type = targets && settings.lowpassDepth > 0 ? 'lowpass' : 'allpass';
      if (binding.filter.type !== type) binding.filter.type = type;
      const cutoff = targets?.cutoffHz ?? Math.min(20000, this.audio.context.sampleRate * .45);
      if (immediate || binding.cutoff === null || binding.cutoff === undefined || Math.abs(binding.cutoff - cutoff) > .5) {
        binding.cutoff = cutoff;
        const now = this.audio.context.currentTime, frequency = binding.filter.frequency;
        if (immediate) {
          frequency.cancelScheduledValues(now); frequency.setValueAtTime(cutoff, now);
        } else frequency.setTargetAtTime(cutoff, now, .015);
      }
    }
    setResting(id, resting) {
      const node = this.nodes.get(id);
      if (!node || node.resting === Boolean(resting)) return;
      node.resting = Boolean(resting); node.phase = node.resting ? 'RESTING' : 'ACTIVE';
      node.box.style.transition = 'opacity 400ms linear'; node.box.style.opacity = node.resting ? '.35' : '1';
      // Ecological rest changes prominence, not the native playback lifecycle.
      // Keeping this foreground loop running avoids a WebKit pause/wake edge.
      this.updateNodeAudio(node);
    }
    updateNodeAudio(node) {
      const gain = node.resting || !this.running ? 0 : node.targetGain ?? 1 / Math.sqrt(Math.max(1, this.nodes.size));
      for (const deck of node.decks) {
        const audible = Boolean(deck.binding) && this.audio.enabled && this.sound.enabled &&
          (deck === node.active || deck === this.fade?.incoming || deck === node.promoting);
        if (deck.media.muted === audible) deck.media.muted = !audible;
        if (!deck.binding || this.audio.context.state !== 'running') continue;
        // Presence is applied after mix normalization. Otherwise normalization
        // turns a lone receding voice back up to the full mix ceiling.
        const modulation = this.effectsEnabled && root.SimvltaneaPresence
          ? root.SimvltaneaPresence.filterTargets(deck.presence, this.audio.context.sampleRate, this.effectSettings).gain : 1;
        const target = gain * deck.weight * modulation;
        if (Math.abs(deck.binding.target - target) > .00001) {
          deck.binding.target = target;
          deck.binding.gain.gain.setTargetAtTime(target, this.audio.context.currentTime, .015);
        }
      }
    }
    updateAudio() {
      this.master?.setVolume(this.sound.volume, this.sound.enabled && this.running);
      for (const node of this.nodes.values()) this.updateNodeAudio(node);
    }
    recordLoopSeek(type, id, detail) {
      this.record(type, id, detail);
      if (!this.proof) return;
      const proof = this.loopSeekProof ||= {attempted: 0, recovered: 0, rejected: 0, interrupted: 0,
        dropped: 0, receipts: []};
      const counter = {'native-loop-seek-recovery': 'attempted', 'native-loop-seek-recovered': 'recovered',
        'native-loop-seek-play-rejected': 'rejected', 'native-loop-seek-interrupted': 'interrupted'}[type];
      proof[counter]++;
      proof.receipts.push({type, id, time: this.clock?.simTime, wall: performance.now(), ...detail});
      if (proof.receipts.length > 16) { proof.receipts.shift(); proof.dropped++; }
    }
    interruptLoopSeek(deck, reason) {
      const state = deck.loopSeek;
      if (!state?.attempt || state.attempt.interrupted) return;
      state.attempt.interrupted = true;
      this.recordLoopSeek('native-loop-seek-interrupted', state.id,
        {url: state.url, sourceEpoch: state.epoch, attemptedAt: state.attempt.time,
          strategy: state.attempt.strategy, reason});
    }
    recoverNativeLoop(node, time, dt) {
      const deck = node.active, media = deck?.media;
      if (!media || !deck.url || this.options?.nativeLoopSeekRecovery === false) return;
      let state = deck.loopSeek;
      if (!state || state.url !== deck.url || state.epoch !== deck.sourceEpoch) {
        this.interruptLoopSeek(deck, 'source-changed');
        state = deck.loopSeek = {id: node.id, url: deck.url, epoch: deck.sourceEpoch, generation: this.generation,
          decoded: deck.decoded?.mediaTime, changes: 0, endSeen: false, seamCurrent: null,
          stalled: 0, attempt: null, recoveryFrames: 0};
      }
      const current = media.currentTime, duration = media.duration, fps = Number(deck.item?.asset?.fps);
      const foreground = this.nodes.get(node.id) === node && node.media === media;
      // A sibling's awaited replacement keeps drain() open. Only this slot's
      // transition may suspend recovery of its otherwise unchanged resident.
      const eligible = this.running && !this.disposed && !root.document?.hidden &&
        foreground && !node.busy && !node.resting && media.loop && !media.paused &&
        media.readyState >= 3 && !media.error && media.currentSrc === state.url &&
        Number.isFinite(duration) && duration > .1 && Number.isFinite(fps) && fps > 0 && 1 / fps < duration;
      const changed = Number.isFinite(deck.decoded?.mediaTime) && state.decoded !== deck.decoded.mediaTime;
      state.decoded = deck.decoded?.mediaTime;
      if (!eligible || state.generation !== this.generation) {
        this.interruptLoopSeek(deck, 'inactive-or-suspended');
        state.generation = this.generation; state.stalled = 0; state.endSeen = false; state.changes = 0;
        state.recoveryFrames = 0; return;
      }
      if (state.attempt && media.seeking) state.recoveryFrames = 0;
      if (changed) {
        state.changes++; state.stalled = 0;
        if (state.attempt && !media.seeking && current > .001) {
          state.recoveryFrames++;
          if (state.recoveryFrames >= 2) {
            if (!state.attempt.interrupted) this.recordLoopSeek('native-loop-seek-recovered', node.id,
              {url: state.url, sourceEpoch: state.epoch, attemptedAt: state.attempt.time,
                strategy: state.attempt.strategy, decodedChanges: state.recoveryFrames,
                current, decoded: state.decoded, seeking: media.seeking});
            state.attempt = null; state.endSeen = false; state.recoveryFrames = 0;
          }
        }
      }
      // Native currentTime reaches the seam even when the decoded texture is
      // stale mid-clip. Require that source's observed end, never a generic
      // quiet decoder or the first seek of a newly admitted source.
      if (!media.seeking && current >= duration - 2 / fps && state.changes >= 2) {
        state.endSeen = true; state.seamCurrent = current;
      } else if (changed && !media.seeking && current > .001) state.endSeen = false;
      if (!media.seeking || current > .001 || !state.endSeen || state.changes < 2 || state.attempt || changed) {
        state.stalled = 0; return;
      }
      // Count foreground simulation time, not a single delayed host callback.
      state.stalled += Math.max(0, Math.min(.1, Number(dt) || 0));
      if (state.stalled + 1e-9 < .6) return;
      const pauseBeforeSeek = this.options?.nativeLoopSeekPauseBeforeSeek !== false;
      const strategy = pauseBeforeSeek ? 'pause-seek-play' : 'seek-play';
      const attempt = state.attempt = {time, generation: this.generation, strategy,
        decoded: state.decoded, progressed: false};
      const detail = {url: state.url, sourceEpoch: state.epoch, current, seeking: media.seeking,
        decoded: state.decoded, priorSeamCurrent: state.seamCurrent, duration,
        stalledSimSec: state.stalled, target: 1 / fps, strategy, afterPause: null};
      const stillOwned = () => !this.disposed && this.nodes.get(node.id) === node && node.active === deck &&
        deck.loopSeek === state && deck.url === state.url && deck.sourceEpoch === state.epoch &&
        state.attempt === attempt && this.generation === attempt.generation && !attempt.interrupted;
      const failed = error => {
        if (stillOwned()) this.recordLoopSeek('native-loop-seek-play-rejected', node.id,
          {url: state.url, sourceEpoch: state.epoch, strategy, message: String(error?.message || error)});
      };
      // Experimental target-only recovery. Keep the resident, URL, decoder and
      // audio routing intact; a fulfilled play promise alone is not recovery.
      const nativeState = () => ({paused: media.paused, current: media.currentTime, seeking: media.seeking});
      let playing, operationError;
      try {
        if (pauseBeforeSeek) { media.pause(); detail.afterPause = nativeState(); }
        media.currentTime = 1 / fps; detail.afterSeek = nativeState();
        playing = media.play(); detail.afterPlay = nativeState();
      } catch (error) { operationError = error; }
      this.recordLoopSeek('native-loop-seek-recovery', node.id, detail);
      if (operationError) failed(operationError);
      else Promise.resolve(playing).then(() => {
        if (stillOwned()) this.record('native-loop-seek-play-fulfilled', node.id,
          {url: state.url, sourceEpoch: state.epoch, strategy, ...nativeState()});
      }, failed);
    }
    tick(time, dt = 0) {
      this.frame = Math.floor(time * (this.plan?.fps || 24));
      // Incoming media has an independent entrance while the scheduler still
      // observes the outgoing resident. Never copy its closing filter state.
      for (const node of this.nodes.values()) {
        this.recoverNativeLoop(node, time, dt);
        let changed = false;
        for (const deck of node.decks) {
          if (deck.enteredAt === null || deck.presenceTarget !== null ||
              (deck !== node.active && deck !== this.fade?.incoming && deck !== node.promoting)) continue;
          deck.presence = root.SimvltaneaPresence
            ? root.SimvltaneaPresence.entranceEnvelope(time - deck.enteredAt, this.effectSettings)
            : Math.max(0, Math.min(1, (time - deck.enteredAt) / 1.2));
          if (this.effectsEnabled) this.applyDeckEffects(deck);
          changed = true;
        }
        if (changed) this.updateNodeAudio(node);
      }
      if (this.fade) {
        const fade = this.fade, progress = Math.min(1, (time - fade.began) / fade.duration);
        fade.incoming.weight = progress; fade.outgoing.weight = 1 - progress;
        // CSS uses source-over, so fading both alpha values would expose the
        // black stage (25% at the midpoint). Keep the outgoing image opaque.
        fade.incoming.media.style.opacity = String(progress); fade.outgoing.media.style.opacity = '1';
        this.updateNodeAudio(fade.node);
        if (progress === 1) {
          // The ecology subscriber still runs before replace() can continue its
          // awaited fade. Keep audio ownership across that microtask boundary.
          fade.node.promoting = fade.incoming;
          this.fade = null; fade.finish();
        }
      }
      if (this.proof && time - this.proofAt >= .25) {
        this.proofAt = time;
        this.proof.textContent = `time ${time.toFixed(2)} | preparing ${this.activeStandbys}/${this.maxConcurrentStandbys}\n` +
          [...this.nodes.values()].map(node => `${node.id} ${node.phase} ready=${node.media?.readyState ?? 0} ` +
            `t=${(node.media?.currentTime || 0).toFixed(2)} frames=${node.callbacks} stalls=${node.stallCount}`).join('\n');
      }
    }
    suspend() {
      if (!this.running) return;
      this.running = false; this.generation++; this.clock.pause();
      this.handoff?.pause();
      for (const node of this.slots.values()) for (const deck of node.decks) this.interruptLoopSeek(deck, 'suspended');
      if (this.proof) {
        this.proofSuspensionCount++;
        const wall = performance.now();
        for (const node of this.slots.values()) for (const deck of node.decks) deck.progress?.setRunning(false, wall);
      }
      for (const node of this.nodes.values()) for (const deck of node.decks) if (deck.url && !deck.media.paused) deck.media.pause();
      // A deliberate pause freezes the pictures in their visible blend and
      // settles the handoff; it must not strand a semaphore until another click.
      if (this.fade) { const fade = this.fade; this.fade = null; fade.finish(); }
      if (this.seam) this.seam.finish();
      if (this.promotion) this.promotion.finish();
      this.updateAudio(); this.status();
    }
    pause() { this.playingIntent = false; if (this.pending) this.pending.playing = false; this.suspend(); }
    async start() {
      if (this.disposed) return;
      this.playingIntent = true;
      if (this.running || document.hidden) return;
      this.running = true; this.generation++; this.clock.start();
      this.handoff?.resume();
      if (this.proof) {
        const wall = performance.now();
        for (const node of this.slots.values()) for (const deck of node.decks) deck.progress?.setRunning(true, wall);
      }
      const jobs = [];
      for (const node of this.nodes.values()) {
        if (node.media && node.media.paused) jobs.push(node.media.play().catch(error => this.report(error, node)));
        // A pause can settle promotion before its resident identity commits.
        // A same-task resume must restart that deck as well as the outgoing one.
        const promoting = node.promoting;
        if (promoting?.url && promoting.media !== node.media && promoting.media.paused) {
          jobs.push(promoting.media.play().catch(error => this.report(error, node)));
        }
      }
      this.updateAudio(); this.status(); await Promise.all(jobs);
    }
    play() { return this.start(); }
    setOrientation(value) {
      if (value !== null && value !== 'portrait' && value !== 'landscape') throw new Error('Invalid orientation');
      this.orientationOverride = value; this.applyLayout();
    }
    applyTerritory(shares) {
      if (!Array.isArray(shares) && !ArrayBuffer.isView(shares)) return;
      if (shares.length !== this.plan?.tracks.length || [...shares].some(value => !Number.isFinite(value) || value <= 0)) return;
      const total = shares.reduce((sum, value) => sum + value, 0);
      this.territory = Array.from(shares, value => value / total);
      this.applyLayout();
    }
    applyLayout() {
      if (!this.plan) return;
      const {width, height} = this.stage.getBoundingClientRect();
      if (!(width > 0 && height > 0)) return;
      this.orientation = this.orientationOverride ?? (width >= height ? 'landscape' : 'portrait');
      let layout = this.plan.layout_keyframes?.[0]?.layouts?.[this.orientation];
      if (!layout) return;
      if (this.territory?.length === layout.cells.length) {
        const horizontal = layout.cells.every(cell => number(cell.rect[2]) === 1);
        const vertical = layout.cells.every(cell => number(cell.rect[3]) === 1);
        if (horizontal || vertical) {
          let edge = 0, weight = 0;
          const axis = horizontal ? 1 : 0;
          const order = layout.cells.map((cell, index) => index).sort((a, b) =>
            number(layout.cells[a].rect[axis]) - number(layout.cells[b].rect[axis]));
          const rectangles = [];
          order.forEach((index, position) => {
            weight += this.territory[index];
            const end = position === order.length - 1 ? 1000000 : Math.round(weight * 1000000);
            rectangles[index] = horizontal ? ['0', `${edge}/1000000`, '1', `${end - edge}/1000000`] :
              [`${edge}/1000000`, '0', `${end - edge}/1000000`, '1'];
            edge = end;
          });
          layout = {...layout, cells: layout.cells.map((cell, index) => ({...cell, rect: rectangles[index]}))};
        }
      }
      const raster = rasterLayout(layout, width, height, root.devicePixelRatio || 1);
      layout.cells.forEach((cell, index) => {
        const node = this.nodes.get(cell.loop); if (!node) return;
        const [x, y, w, h] = cell.rect.map(number), {grow, rounded, radius} = raster.cells[index];
        const start = (value, before) => before ? `calc(${value * 100}% - ${before}px)` : `${value * 100}%`;
        const size = (value, extra) => extra ? `calc(${value * 100}% + ${extra}px)` : `${value * 100}%`;
        Object.assign(node.box.style, {left: start(x, grow.left), top: start(y, grow.top),
          width: size(w, grow.left + grow.right), height: size(h, grow.top + grow.bottom), zIndex: String(index)});
        const corners = new Set([...rounded].flatMap(side => SIDE_CORNERS[side]));
        for (const corner of CORNERS) node.box.style[`border${corner}Radius`] = corners.has(corner) ? `${radius}px` : '';
        node.geometry = {width: w * width + grow.left + grow.right, height: h * height + grow.top + grow.bottom,
          overscan: overscanFor(cell, layout, this.orientation, width, height)};
        node.cell = cell;
        for (const deck of node.decks) {
          applySlice({...node, media: deck.media});
          deck.media.style.position = 'absolute';
          if (deck.binding && this.audio.context.state === 'running') {
            const pan = this.orientation === 'landscape' ? 2 * (x + w / 2) - 1 : 0;
            deck.binding.pan.pan.setTargetAtTime(pan, this.audio.context.currentTime, .05);
          }
        }
      });
    }
    snapshot() {
      return {frame: this.frame, compositionTime: this.clock.simTime, running: this.running, ready: this.ready,
        finished: false, error: this.error, orientation: this.orientation, orientationOverride: this.orientationOverride,
        activeStandbys: this.activeStandbys, maxConcurrentStandbys: this.maxConcurrentStandbys,
        pending: Boolean(this.pending) || this.draining, lastFailure: this.lastFailure,
        effects: this.effectsEnabled, effectSettings: this.effectSettings,
        audio: {mode: this.audio.mode, enabled: this.audio.enabled, contextState: this.audio.context?.state ?? null},
        loops: [...this.nodes.values()].map(node => ({id: node.id, source: node.source, kind: 'video',
          currentTime: node.media?.currentTime ?? 0, rate: 1, paused: node.media?.paused ?? true,
          readyState: node.media?.readyState ?? 0, busy: node.busy, callbacks: node.callbacks, decoded: node.decoded,
          phase: node.phase, presence: node.active?.presence ?? null,
          stalls: node.stallCount, rect: node.box.getBoundingClientRect().toJSON(),
          audio: node.audio ? {gain: node.audio.gain.gain.value, pan: node.audio.pan.pan.value,
            cutoffHz: node.audio.filter.frequency.value} : null}))};
    }
    dispose() {
      if (this.disposed) return;
      this.disposed = true; this.controller?.abort(); this.pending?.resolve(false); this.pending = null;
      this.pause(); this.clock.dispose(); this.resizeObserver.disconnect();
      document.removeEventListener('visibilitychange', this.visibility);
      for (const node of this.slots.values()) {
        for (const deck of node.decks) {
          this.unload(deck);
          if (deck.frameId !== null) deck.media.cancelVideoFrameCallback?.(deck.frameId);
          deck.binding?.source.disconnect(); deck.binding?.filter.disconnect(); deck.binding?.pan.disconnect(); deck.binding?.gain.disconnect();
        }
        node.box.remove();
      }
      this.nodes.clear(); this.slots.clear(); this.sources.clear(); this.proof?.remove();
      this.master?.dispose?.(); this.audio.context?.close().catch(() => {});
    }
  }
  const api = {Session, MasterSimClock, FrameProgress, foregroundLimit};
  root.SimvltaneaLive = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis === 'object' ? globalThis : this);
