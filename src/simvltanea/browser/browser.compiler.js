/* Client-side composition compiler: visual-form-composition/v1 state to browser plan.
 *
 * A classic script (no modules, no dependencies). It publishes
 * globalThis.SimvltaneaCompiler and, under Node, module.exports. For a state in
 * the supported subset, compilePlan(state) returns exactly what Python's
 * browser_runtime.compile_plan(state) returns, and stagePreview(state, sizes)
 * performs build_preview's media rebasing so browser.runtime.js plays it unchanged.
 *
 * Supported subset (everything else throws CompilerError; nothing is approximated):
 *   - schema_version 1, engine_version "1.0.0", silent audio {mode: "none"};
 *   - 2..7 loops, each with exactly one source in its bank, every declared source
 *     bound to exactly one loop, distinct source IDs and media digests, and
 *     allow_source_reuse false (N independent loops, no filler, no duplication);
 *   - video and still sources; per-loop offset, rate, trim and initial held flag;
 *     any fps in 1..60 and frames in 1..14400;
 *   - no events, slice and seam absent or disabled.
 * Explicitly outside: hold/reroll/swap/move events, Audio v1.1, N outside 2..7,
 * multi-source banks (seeded selection), slices, seams and duplicate media.
 *
 * Rationals are integers or "n/d" strings (optionally negative) and use exact
 * BigInt arithmetic. Decimal spellings, floats, exponents and non-finite numbers
 * are rejected, as browser.runtime.js rejects them.
 */
(function (root) {
  'use strict';
  const ENGINE_VERSION = '1.0.0', RNG = 'sha256-counter-v1', PLAN_VERSION = 1;
  const MAX_FRAMES = 14400, MAX_SEGMENTS = 1024, MAX_MEDIA_BYTES = 256 * 1024 * 1024;
  const MIN_LOOPS = 2, MAX_LOOPS = 7;
  const ORIENTATIONS = ['portrait', 'landscape'], SEAM_MODES = ['blur', 'feather', 'morph'];
  const ID = /^[A-Za-z0-9_-]{1,80}$/, DIGEST = /^[0-9a-f]{64}$/, RATIONAL = /^-?\d+(?:\/\d+)?$/;
  const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;
  const STATE_FIELDS = ['schema_version', 'engine_version', 'rng', 'seed', 'fps', 'frames', 'sources',
    'loops', 'layouts', 'events', 'audio', 'allow_source_reuse'];
  const SOURCE_FIELDS = ['id', 'path', 'sha256', 'kind', 'duration'];
  const LOOP_FIELDS = ['id', 'bank', 'offset', 'rate', 'period', 'epoch', 'held'];
  const CELL_FIELDS = ['loop', 'rect', 'fit', 'focal'];

  class CompilerError extends Error {
    constructor(message, unsupported = false) {
      super(unsupported ? `outside the browser compiler subset: ${message}` : message);
      this.name = 'CompilerError';
      this.unsupported = unsupported;
    }
  }
  const need = (test, message) => { if (!test) throw new CompilerError(message); };
  const refuse = (test, message) => { if (test) throw new CompilerError(message, true); };
  const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const has = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

  // Exact rationals are normalized [numerator, denominator] BigInt pairs.
  const gcd = (a, b) => { while (b) [a, b] = [b, a % b]; return a < 0n ? -a : a; };
  const frac = (n, d = 1n) => {
    if (d < 0n) { n = -n; d = -d; }
    const g = gcd(n, d) || 1n;
    return [n / g, d / g];
  };
  const ZERO = [0n, 1n], ONE = [1n, 1n], EIGHT = [8n, 1n], BOUND = 10n ** 9n;
  const add = (x, y) => frac(x[0] * y[1] + y[0] * x[1], x[1] * y[1]);
  const sub = (x, y) => add(x, [-y[0], y[1]]);
  const mul = (x, y) => frac(x[0] * y[0], x[1] * y[1]);
  const cmp = (x, y) => { const v = x[0] * y[1] - y[0] * x[1]; return v < 0n ? -1 : v > 0n ? 1 : 0; };
  const floorDiv = (n, d) => (n % d !== 0n && (n < 0n) !== (d < 0n) ? n / d - 1n : n / d);
  const mod = (x, y) => sub(x, mul([floorDiv(x[0] * y[1], x[1] * y[0]), 1n], y));
  const text = ([n, d]) => (d === 1n ? String(n) : `${n}/${d}`);

  function rational(value, where) {
    let n, d = 1n;
    if (typeof value === 'number' && Number.isSafeInteger(value)) n = BigInt(value);
    else if (typeof value === 'string' && RATIONAL.test(value)) {
      const [a, b = '1'] = value.split('/');
      n = BigInt(a); d = BigInt(b);
    } else {
      throw new CompilerError(`${where} must be an integer or an exact "n/d" rational string; ` +
        'decimals, floats, exponents and non-finite numbers are rejected');
    }
    need(d !== 0n, `${where}: invalid rational`);
    const result = frac(n, d);
    need((result[0] < 0n ? -result[0] : result[0]) <= BOUND * result[1] && result[1] <= BOUND,
      `${where}: out of bounds`);
    return result;
  }
  const positive = value => cmp(value, ZERO) > 0;
  const unit = value => cmp(value, ZERO) >= 0 && cmp(value, ONE) <= 0;

  function fields(value, allowed, required, where) {
    need(isObject(value), `${where} must be an object`);
    const extra = Object.keys(value).filter(key => !allowed.includes(key)).sort();
    need(!extra.length, `${where}: unsupported fields ${JSON.stringify(extra)}`);
    const missing = required.filter(key => !has(value, key)).sort();
    need(!missing.length, `${where}: missing fields ${JSON.stringify(missing)}`);
  }
  const integer = (value, low, high, where) =>
    need(Number.isSafeInteger(value) && value >= low && value <= high,
      `${where} must be an integer in ${low}..${high}`);
  const identifier = (value, where) => need(typeof value === 'string' && ID.test(value), `${where}: invalid ID`);
  // Mirrors pathlib.PurePosixPath(path).suffix, lowercased.
  const suffix = path => {
    const name = path.split('/').filter(part => part && part !== '.').pop() || '';
    const dot = name.lastIndexOf('.');
    return dot > 0 && dot < name.length - 1 ? name.slice(dot).toLowerCase() : '';
  };

  function rectValues(rect) {
    need(Array.isArray(rect) && rect.length === 4, 'rect must be [x,y,width,height]');
    const [x, y, w, h] = rect.map(value => rational(value, 'rect'));
    need(cmp(x, ZERO) >= 0 && cmp(y, ZERO) >= 0 && positive(w) && positive(h) &&
      cmp(add(x, w), ONE) <= 0 && cmp(add(y, h), ONE) <= 0, 'rect must have positive area inside the unit canvas');
    return [x, y, w, h];
  }

  function validateLayouts(layouts, loopIds) {
    fields(layouts, ORIENTATIONS, ORIENTATIONS, 'layouts');
    for (const orientation of Object.keys(layouts)) {
      const layout = layouts[orientation];
      fields(layout, ['name', 'cells'], ['name', 'cells'], orientation);
      need(typeof layout.name === 'string' && layout.name !== '', 'layout name is required');
      need(Array.isArray(layout.cells), 'cells must be an array');
      const seen = [], boxes = [];
      for (const cell of layout.cells) {
        fields(cell, CELL_FIELDS, CELL_FIELDS, 'cell');
        identifier(cell.loop, 'cell.loop');
        seen.push(cell.loop);
        need(cell.fit === 'contain' || cell.fit === 'cover', 'only contain/cover fit is implemented');
        need(Array.isArray(cell.focal) && cell.focal.length === 2, 'focal needs two coordinates');
        need(cell.focal.every(value => unit(rational(value, 'focal'))), 'focal must be in 0..1');
        const box = rectValues(cell.rect), [x, y, w, h] = box;
        for (const [a, b, c, d] of boxes) {
          need(!(cmp(x, add(a, c)) < 0 && cmp(a, add(x, w)) < 0 && cmp(y, add(b, d)) < 0 && cmp(b, add(y, h)) < 0),
            'overlapping/occluded panels are not supported in schema v1');
        }
        boxes.push(box);
      }
      need(seen.length === loopIds.size && new Set(seen).size === loopIds.size && seen.every(id => loopIds.has(id)),
        'each orientation must map every loop exactly once');
    }
  }

  // Slice and seam are validated as composition.py does, then refused if enabled.
  function validateToggle(value, where, bounds) {
    fields(value, ['enabled', ...Object.keys(bounds)], ['enabled'], where);
    need(typeof value.enabled === 'boolean', `${where}.enabled must be boolean`);
    for (const [key, check] of Object.entries(bounds)) if (has(value, key)) check(value[key]);
    refuse(value.enabled, `${where} is enabled; slices and seams are compiled by Python only`);
  }
  const within = (where, high, inclusive) => value => {
    const result = rational(value, where);
    need(positive(result) && cmp(result, high) < (inclusive ? 1 : 0), `${where} is out of range`);
  };

  function validateState(state) {
    need(isObject(state), 'state must be an object');
    const extra = Object.keys(state).filter(key => ![...STATE_FIELDS, 'slice', 'seam'].includes(key)).sort();
    need(!extra.length, `state: unsupported fields ${JSON.stringify(extra)}`);
    need(STATE_FIELDS.every(key => has(state, key)), 'state: missing required fields');
    refuse(state.schema_version === '1.1', 'Audio v1.1 (schema_version "1.1") is compiled by Python only');
    need(state.schema_version === 1, 'unsupported schema_version');
    need(state.engine_version === ENGINE_VERSION, 'unsupported engine_version');
    need(state.rng === RNG, 'unsupported randomness algorithm');
    need(typeof state.seed === 'string' || Number.isSafeInteger(state.seed), 'seed must be a string or safe integer');
    integer(state.fps, 1, 60, 'fps');
    integer(state.frames, 1, MAX_FRAMES, 'frames');
    need(typeof state.allow_source_reuse === 'boolean', 'allow_source_reuse must be boolean');
    need(Array.isArray(state.sources) && state.sources.length > 0, 'sources must be a nonempty array');
    const sources = new Map();
    for (const source of state.sources) {
      fields(source, SOURCE_FIELDS, SOURCE_FIELDS, 'source');
      identifier(source.id, 'source.id');
      need(!sources.has(source.id), 'duplicate source ID');
      need(typeof source.path === 'string' && source.path !== '', 'source path is required');
      need(!source.path.startsWith('/') && !source.path.split('/').includes('..') && !source.path.includes(':'),
        'state source paths must be relative local paths without traversal or URLs');
      need(typeof source.sha256 === 'string' && DIGEST.test(source.sha256), 'source sha256 must be a lowercase digest');
      need(source.kind === 'video' || source.kind === 'still', 'only video and still sources are implemented');
      need(positive(rational(source.duration, 'source.duration')), 'source duration must be positive');
      if (source.kind === 'still') {
        need(['.png', '.jpg', '.jpeg'].includes(suffix(source.path)), 'still adapter supports PNG/JPEG only');
      }
      sources.set(source.id, source);
    }
    need(Array.isArray(state.loops) && state.loops.length >= 1 && state.loops.length <= 32,
      'loop count must be 1..32 (resource guard, not a claim that every count is proven)');
    refuse(state.loops.length < MIN_LOOPS || state.loops.length > MAX_LOOPS,
      `${state.loops.length} loops; authored layouts cover N=${MIN_LOOPS}..${MAX_LOOPS} independent loops ` +
      '(no filler, no implicit duplication)');
    const loopIds = new Set();
    for (const loop of state.loops) {
      fields(loop, [...LOOP_FIELDS, 'trim'], LOOP_FIELDS, 'loop');
      identifier(loop.id, 'loop.id');
      need(!loopIds.has(loop.id), 'duplicate loop ID');
      loopIds.add(loop.id);
      need(Array.isArray(loop.bank) && loop.bank.length > 0, 'bank must be an ordered nonempty array');
      need(loop.bank.every(item => typeof item === 'string' && sources.has(item)), 'bank references absent source');
      need(new Set(loop.bank).size === loop.bank.length, 'bank cannot repeat a source ID');
      need(cmp(rational(loop.offset, 'offset'), ZERO) >= 0, 'offset must be nonnegative');
      const rate = rational(loop.rate, 'rate');
      need(positive(rate) && cmp(rate, EIGHT) <= 0, 'rate must be in (0,8]');
      need(positive(rational(loop.period, 'period')), 'selection period must be positive');
      integer(loop.epoch, 0, 2 ** 31 - 1, 'epoch');
      need(typeof loop.held === 'boolean', 'held must be boolean');
      if (has(loop, 'trim')) {
        need(Array.isArray(loop.trim) && loop.trim.length === 2, 'trim needs in/out bounds');
        const [low, high] = loop.trim.map(value => rational(value, 'trim'));
        need(cmp(low, ZERO) >= 0 && cmp(low, high) < 0, 'trim must have positive duration');
        need(loop.bank.every(id => cmp(high, rational(sources.get(id).duration, 'duration')) <= 0),
          'trim exceeds a bank source duration');
      }
      refuse(loop.bank.length !== 1,
        `loop ${loop.id} has a ${loop.bank.length}-source bank; seeded bank selection is compiled by Python only`);
    }
    const audio = state.audio;
    need(isObject(audio), 'audio must be an object');
    need(Object.keys(audio).length === 3 && audio.mode === 'none' &&
      audio.routing === null && audio.generative === null,
      'versioned loop exports are silent in v1; Audio v1.1 requires schema_version "1.1"');
    validateLayouts(state.layouts, loopIds);
    if (has(state, 'slice')) {
      validateToggle(state.slice, 'slice', {width: within('slice.width', ONE, false),
        height: within('slice.height', ONE, false)});
    }
    if (has(state, 'seam')) {
      validateToggle(state.seam, 'seam', {width: within('seam.width', [3n, 20n], true),
        sigma: within('seam.sigma', [1n, 10n], true),
        mode: value => need(SEAM_MODES.includes(value), `seam.mode must be one of ${SEAM_MODES.join(', ')}`)});
    }
    need(Array.isArray(state.events), 'events must be an array');
    refuse(state.events.length > 0, 'hold/reroll/swap/move events are resolved by composition.py only');
    refuse(state.allow_source_reuse, 'allow_source_reuse must be false (no implicit duplication)');
    const bound = state.loops.map(loop => loop.bank[0]);
    need(new Set(bound).size === bound.length &&
      new Set(bound.map(id => sources.get(id).sha256)).size === bound.length,
      'source reuse must be explicit; no duplicated IDs or media bytes as filler');
    refuse(sources.size !== bound.length, 'every declared source must be bound to exactly one loop (no filler)');
    refuse(new Set(state.sources.map(source => source.sha256)).size !== sources.size,
      'two sources declare the same media digest (duplicate media)');
  }

  // json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).
  function canonicalJson(value) {
    if (value === null || typeof value === 'boolean') return String(value);
    if (typeof value === 'number') {
      need(Number.isSafeInteger(value), 'canonical JSON supports only safe integers');
      return String(value);
    }
    if (typeof value === 'string') {
      need(!LONE_SURROGATE.test(value), 'strings must be well-formed Unicode');
      return JSON.stringify(value);
    }
    if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
    need(isObject(value), 'canonical JSON supports only JSON values');
    return `{${Object.keys(value).sort().map(key => `${canonicalJson(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }

  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  const H0 = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const rotr = (x, n) => (x >>> n) | (x << (32 - n));

  // Synchronous FIPS 180-4 SHA-256; crypto.subtle is asynchronous and absent on insecure origins.
  function sha256Hex(bytes) {
    const words = new Uint32Array(((bytes.length + 72) >>> 6) << 4);
    for (let i = 0; i < bytes.length; i++) words[i >>> 2] |= bytes[i] << (24 - 8 * (i & 3));
    words[bytes.length >>> 2] |= 0x80 << (24 - 8 * (bytes.length & 3));
    words[words.length - 2] = Math.floor(bytes.length / 0x20000000);
    words[words.length - 1] = bytes.length * 8;
    const hash = H0.slice(), w = new Uint32Array(64);
    for (let block = 0; block < words.length; block += 16) {
      for (let t = 0; t < 64; t++) {
        if (t < 16) { w[t] = words[block + t]; continue; }
        const a = w[t - 15], b = w[t - 2];
        w[t] = (rotr(a, 7) ^ rotr(a, 18) ^ (a >>> 3)) + w[t - 7] + (rotr(b, 17) ^ rotr(b, 19) ^ (b >>> 10)) + w[t - 16];
      }
      let [a, b, c, d, e, f, g, h] = hash;
      for (let t = 0; t < 64; t++) {
        const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[t] + w[t]) >>> 0;
        const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        [h, g, f, e, d, c, b, a] = [g, f, e, (d + t1) >>> 0, c, b, a, (t1 + t2) >>> 0];
      }
      [a, b, c, d, e, f, g, h].forEach((value, i) => { hash[i] = (hash[i] + value) >>> 0; });
    }
    return hash.map(value => value.toString(16).padStart(8, '0')).join('');
  }
  const stateDigest = state => sha256Hex(new TextEncoder().encode(canonicalJson(state)));

  function compilePlan(state) {
    validateState(state);
    const fps = BigInt(state.fps), sources = new Map(state.sources.map(source => [source.id, source]));
    let spanCount = 0;
    const tracks = state.loops.map(loop => {
      const source = sources.get(loop.bank[0]), still = source.kind === 'still';
      const rate = rational(loop.rate, 'rate'), offset = rational(loop.offset, 'offset');
      need(still || (cmp(rate, [1n, 16n]) >= 0 && cmp(rate, EIGHT) <= 0),
        'browser video rate must be within 1/16..8; offline model unchanged');
      const [low, high] = (loop.trim || [0, source.duration]).map(value => rational(value, 'trim'));
      const length = sub(high, low), step = loop.held || still ? ZERO : mul(rate, [1n, fps]);
      const spans = [];
      let previous = null;
      for (let frame = 0; frame < state.frames; frame++) {
        const local = loop.held ? offset : add(offset, mul(frac(BigInt(frame), fps), rate));
        const sourceOffset = still ? ZERO : add(low, mod(local, length));
        if (previous === null || cmp(sourceOffset, add(previous, step)) !== 0) {
          spans.push({frame, id: loop.id, source: source.id, kind: source.kind, local: text(local),
            source_offset: text(sourceOffset), rate: text(rate), held: loop.held, epoch: loop.epoch});
        }
        previous = sourceOffset;
      }
      spanCount += spans.length;
      return {id: loop.id, spans};
    });
    need(spanCount <= MAX_SEGMENTS * tracks.length, 'browser span resource guard exceeded; no loops were dropped');
    const canonical = (values, where) => values.map(value => text(rational(value, where)));
    const layouts = {};
    for (const [orientation, layout] of Object.entries(state.layouts)) {
      layouts[orientation] = {...layout, cells: layout.cells.map(cell =>
        ({...cell, rect: canonical(cell.rect, 'rect'), focal: canonical(cell.focal, 'focal')}))};
    }
    return {plan_version: PLAN_VERSION, engine_version: state.engine_version, state_sha256: stateDigest(state),
      fps: state.fps, frames: state.frames, audio: 'none', tracks,
      layout_keyframes: [{frame: 0, layouts}],
      sources: state.sources.map(source => ({...source, duration: text(rational(source.duration, 'duration'))})),
      seam: structuredClone(has(state, 'seam') ? state.seam : {enabled: false}),
      slice: structuredClone(has(state, 'slice') ? state.slice : {enabled: false})};
  }

  // Caller data to a valid state; loops reference source IDs and layouts use loop IDs.
  function buildState(input) {
    fields(input, ['sources', 'loops', 'layouts', 'fps', 'frames', 'seed'], ['sources', 'loops', 'layouts', 'frames'],
      'compiler input');
    need(Array.isArray(input.sources) && input.sources.length > 0, 'sources must be a nonempty array');
    need(Array.isArray(input.loops), 'loops must be an array');
    const sources = input.sources.map(source => {
      fields(source, SOURCE_FIELDS, ['id', 'path', 'sha256', 'duration'], 'source');
      return {id: source.id, path: source.path, sha256: source.sha256, kind: source.kind ?? 'video',
        duration: source.duration};
    });
    const loops = input.loops.map(loop => {
      fields(loop, ['id', 'source', 'offset', 'rate', 'trim', 'held'], ['id', 'source'], 'loop');
      const source = sources.find(item => item.id === loop.source);
      need(source !== undefined, `loop ${loop.id} references absent source`);
      const item = {id: loop.id, bank: [loop.source], offset: loop.offset ?? '0', rate: loop.rate ?? '1',
        period: source.duration, epoch: 0, held: loop.held ?? false};
      if (loop.trim !== undefined) item.trim = structuredClone(loop.trim);
      return item;
    });
    const state = {schema_version: 1, engine_version: ENGINE_VERSION, rng: RNG, seed: input.seed ?? 0,
      fps: input.fps ?? 24, frames: input.frames, allow_source_reuse: false, sources, loops,
      layouts: structuredClone(input.layouts), events: [], audio: {mode: 'none', routing: null, generative: null}};
    validateState(state);
    return state;
  }

  // Relabel an authored pair (e.g. the layout bundle's entry for N) onto caller loop IDs,
  // in portrait cell order. Geometry is copied, never generated.
  function bindLayouts(pair, loopIds) {
    fields(pair, ORIENTATIONS, ORIENTATIONS, 'layouts');
    need(ORIENTATIONS.every(name => isObject(pair[name]) && Array.isArray(pair[name].cells)), 'cells must be an array');
    need(Array.isArray(loopIds) && loopIds.length === pair.portrait.cells.length,
      'authored layout cell count must equal the loop count (no filler, no duplication)');
    const mapping = new Map(pair.portrait.cells.map((cell, index) => [cell.loop, loopIds[index]]));
    need(mapping.size === loopIds.length && new Set(loopIds).size === loopIds.length,
      'cells and loop IDs must be unique');
    const bound = structuredClone(pair);
    for (const name of ORIENTATIONS) {
      for (const cell of bound[name].cells) {
        need(mapping.has(cell.loop), 'portrait and landscape must place the same loops');
        cell.loop = mapping.get(cell.loop);
      }
    }
    return bound;
  }

  // build_preview's rebasing: media/<sha256><suffix> paths, byte counts and a portable state hash.
  function stagePreview(state, sizes) {
    const plan = compilePlan(state);
    need(isObject(sizes), 'sizes must map source IDs to byte counts');
    let total = 0;
    for (const source of plan.sources) {
      const bytes = sizes[source.id];
      need(Number.isSafeInteger(bytes) && bytes > 0, `byte count required for source ${source.id}`);
      total += bytes;
    }
    need(total <= MAX_MEDIA_BYTES, 'preview media exceeds 256 MiB guard; no sources were omitted');
    for (const source of plan.sources) {
      need(source.kind !== 'video' || suffix(source.path) === '.mp4', 'browser preview currently requires H.264 MP4');
      source.path = `media/${source.sha256}${suffix(source.path)}`;
      source.bytes = sizes[source.id];
    }
    const portable = structuredClone(state);
    for (const source of portable.sources) source.path = plan.sources.find(item => item.id === source.id).path;
    plan.origin_state_sha256 = plan.state_sha256;
    plan.state_sha256 = stateDigest(portable);
    return {state: portable, plan};
  }

  const api = Object.freeze({
    compile: input => compilePlan(buildState(input)),
    compilePlan, buildState, bindLayouts, stagePreview, validateState, canonicalJson, stateDigest, sha256Hex,
    CompilerError, SUPPORTED_LOOP_COUNTS: Object.freeze([2, 3, 4, 5, 6, 7]),
  });
  root.SimvltaneaCompiler = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis === 'object' ? globalThis : this);
