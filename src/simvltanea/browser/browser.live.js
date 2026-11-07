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
      this.primeTimeoutMs = options.primeTimeoutMs ?? 10000;
      this.progressTimeoutMs = options.progressTimeoutMs ?? 2000;
      this.nodes = new Map(); this.slots = new Map(); this.sources = new Map();
      this.plan = null; this.ready = false; this.running = false; this.finished = false;
      this.error = null; this.lastFailure = null; this.disposed = false;
      this.frame = 0; this.generation = 0; this.orientation = null; this.orientationOverride = null;
      this.starting = false; this.initializing = false; this.restarting = false;
      this.playingIntent = false; this.revision = 0; this.pending = null; this.draining = false;
      this.controller = null; this.fade = null; this.seam = null; this.promotion = null;
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
    }
    get origin() { return (this.audio.context?.currentTime ?? 0) - this.clock.simTime; }
    record(type, id = null, detail = {}) {
      this.events.push({type, id, time: this.clock.simTime, wall: performance.now(), ...detail});
      if (this.events.length > 256) this.events.shift();
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
      const node = {id, ordinal, box, decks: [], active: null, media: null, item: null, audio: null,
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
        const deck = {media, url: null, item: null, binding: null, weight: 0, frameId: null, callbacks: 0, decoded: null};
        const watch = (wall, metadata) => {
          deck.callbacks++; deck.decoded = {mediaTime: metadata.mediaTime, presentedFrames: metadata.presentedFrames, wall};
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
                  success = false; this.report(error, node);
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
    playPromoted(deck, signal) {
      // Some WebKit media pipelines present their primed frame but do not
      // advance after becoming visible until play() is requested again. Keep
      // this request on the promotion stack, with no intervening RAF.
      return new Promise((resolve, reject) => {
        const media = deck.media;
        let done = false, fulfilled = false, frames = 0, frame = null, previous = deck.decoded?.mediaTime;
        const finish = error => {
          if (done) return; done = true; clearTimeout(timer);
          signal.removeEventListener('abort', abort);
          media.removeEventListener('timeupdate', fallback);
          if (frame !== null) media.cancelVideoFrameCallback?.(frame);
          if (this.promotion?.deck === deck) this.promotion = null;
          error ? reject(error) : resolve();
        };
        const abort = () => finish(cancelled());
        const progress = current => {
          if (current !== previous) { frames++; previous = current; }
          if (fulfilled && frames >= 2) finish();
        };
        const decoded = (_, metadata) => {
          frame = null; progress(metadata.mediaTime);
          if (!done) frame = media.requestVideoFrameCallback(decoded);
        };
        const fallback = () => { if (media.readyState >= 2) progress(media.currentTime); };
        const timer = setTimeout(() => finish(new Error('Promoted clip did not present new frames in time')),
          Math.min(this.primeTimeoutMs, this.progressTimeoutMs));
        this.promotion = {deck, finish};
        signal.addEventListener('abort', abort, {once: true});
        if (signal.aborted) { abort(); return; }
        if (media.requestVideoFrameCallback) frame = media.requestVideoFrameCallback(decoded);
        else { previous = media.currentTime; media.addEventListener('timeupdate', fallback); }
        try { media.play().then(() => { fulfilled = true; if (frames >= 2) finish(); }, finish); }
        catch (error) { finish(error); }
      });
    }
    async replace(node, item, source, signal, duration, atLoopBoundary = false) {
      await this.withPreparation(async () => {
        if (signal.aborted) throw cancelled();
        const outgoing = node.active, incoming = node.decks.find(deck => deck !== outgoing);
        const previous = {active: node.active, media: node.media, item: node.item, source: node.source,
          audio: node.audio, birthTime: node.birthTime, callbacks: node.callbacks, decoded: node.decoded};
        node.busy = true; node.phase = 'LOADING';
        incoming.item = item; incoming.media.muted = true;
        incoming.url = URL.createObjectURL(item.file);
        incoming.media.src = incoming.url; incoming.media.load();
        node.box.style.display = '';
        this.applyLayout();
        try {
          await this.prime(incoming, node, signal);
          if (signal.aborted) throw cancelled();
          node.phase = 'READY';
          this.bind(incoming);
          if (atLoopBoundary && outgoing) await this.waitForSeam(node, signal);
          if (signal.aborted) throw cancelled();
          if (outgoing && this.running && !node.resting && duration > 0) {
            node.phase = 'CROSSFADING';
            incoming.media.style.zIndex = '1'; outgoing.media.style.zIndex = '0';
            await new Promise((resolve, reject) => {
              const abort = () => {
                if (this.fade?.incoming === incoming) this.fade = null;
                signal.removeEventListener('abort', abort); reject(cancelled());
              };
              signal.addEventListener('abort', abort, {once: true});
              this.fade = {node, outgoing, incoming, began: this.clock.simTime, duration,
                finish: () => { signal.removeEventListener('abort', abort); resolve(); }};
              incoming.media.muted = !this.sound.enabled || !this.audio.enabled;
            });
          }
          if (signal.aborted) throw cancelled();
          // Sound can unlock during the fade after the earlier bind attempt.
          // No audible resident may bypass the persistent master graph.
          this.bind(incoming);
          incoming.weight = 1; incoming.media.style.opacity = '1'; incoming.media.dataset.deck = 'active';
          node.active = incoming; node.media = incoming.media; node.item = item; node.source = source;
          node.birthTime = this.clock.simTime - incoming.media.currentTime;
          node.audio = incoming.binding; node.callbacks = incoming.callbacks; node.decoded = incoming.decoded;
          node.phase = node.resting ? 'RESTING' : 'ACTIVE';
          if (!this.running) incoming.media.pause();
          incoming.media.muted = !incoming.binding || !this.sound.enabled || !this.audio.enabled;
          this.applyLayout(); this.updateAudio();
          if (this.running) await this.playPromoted(incoming, signal);
          if (signal.aborted) throw cancelled();
          if (!this.running) incoming.media.pause();
          // Promotion is now committed. Until this point the outgoing decoder,
          // Blob URL and resident state remain available for a fail-open rollback.
          if (outgoing) this.unload(outgoing);
          if (node.audio) this.notifyAudio(node);
          this.record('resident', node.id);
        } catch (error) {
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
        } finally { node.busy = false; }
      }, {signal});
    }
    unload(deck) {
      deck.weight = 0;
      if (deck.binding) { deck.binding.gain.gain.value = 0; deck.binding.target = 0; }
      deck.media.style.opacity = '0'; deck.media.dataset.deck = 'standby'; deck.media.muted = true;
      if (deck.url) {
        deck.media.pause(); deck.media.removeAttribute('src'); deck.media.load();
        URL.revokeObjectURL(deck.url); deck.url = null;
      }
      deck.item = null;
    }
    bind(deck) {
      const context = this.audio.context;
      if (!context || deck.binding) return deck.binding;
      let binding = this.bindings.get(deck.media);
      if (!binding) {
        const source = context.createMediaElementSource(deck.media), filter = context.createBiquadFilter();
        const pan = context.createStereoPanner(), gain = context.createGain();
        filter.type = 'lowpass'; filter.frequency.value = Math.min(20000, context.sampleRate * .45); filter.Q.value = Math.SQRT1_2;
        gain.gain.value = 0; source.connect(filter); filter.connect(pan); pan.connect(gain); gain.connect(this.audio.input);
        binding = {source, filter, pan, gain, target: 0}; this.bindings.set(deck.media, binding);
      }
      deck.binding = binding; return binding;
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
          (deck === node.active || deck === this.fade?.incoming);
        if (deck.media.muted === audible) deck.media.muted = !audible;
        if (!deck.binding || this.audio.context.state !== 'running') continue;
        const target = gain * deck.weight;
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
    tick(time) {
      this.frame = Math.floor(time * (this.plan?.fps || 24));
      if (this.fade) {
        const fade = this.fade, progress = Math.min(1, (time - fade.began) / fade.duration);
        fade.incoming.weight = progress; fade.outgoing.weight = 1 - progress;
        // CSS uses source-over, so fading both alpha values would expose the
        // black stage (25% at the midpoint). Keep the outgoing image opaque.
        fade.incoming.media.style.opacity = String(progress); fade.outgoing.media.style.opacity = '1';
        this.updateNodeAudio(fade.node);
        if (progress === 1) { this.fade = null; fade.finish(); }
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
      const jobs = [];
      for (const node of this.nodes.values()) if (node.media && node.media.paused) {
        jobs.push(node.media.play().catch(error => this.report(error, node)));
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
        audio: {mode: this.audio.mode, enabled: this.audio.enabled, contextState: this.audio.context?.state ?? null},
        loops: [...this.nodes.values()].map(node => ({id: node.id, source: node.source, kind: 'video',
          currentTime: node.media?.currentTime ?? 0, rate: 1, paused: node.media?.paused ?? true,
          readyState: node.media?.readyState ?? 0, busy: node.busy, callbacks: node.callbacks, decoded: node.decoded,
          phase: node.phase, stalls: node.stallCount, rect: node.box.getBoundingClientRect().toJSON(),
          audio: node.audio ? {gain: node.audio.gain.gain.value, pan: node.audio.pan.pan.value} : null}))};
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
  const api = {Session, MasterSimClock, foregroundLimit};
  root.SimvltaneaLive = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis === 'object' ? globalThis : this);
