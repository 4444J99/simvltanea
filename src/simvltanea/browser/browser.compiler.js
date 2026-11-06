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
 *   - 1..12 loops (the engine-wide browser subset; which counts a layout family
 *     offers comes from the layout bundle, never from a constant here), each with
 *     exactly one source in its bank, every declared source bound to exactly one
 *     loop, distinct source IDs and media digests, and allow_source_reuse false
 *     (N independent loops, no filler, no duplication);
 *   - video and still sources; per-loop offset, rate, trim and initial held flag;
 *     any fps in 1..60 and frames in 1..14400;
 *   - layouts with the optional full_bleed, presentation and cell lateral_offset
 *     declarations, checked as Python's layout_presets.validate_layout_pair checks them;
 *   - the state-wide slice, enabled or not: every span carries the slice_rect that
 *     composition.slice_rect picks (sha256-counter-v1, one window per loop per period);
 *   - no events, seam absent or disabled.
 * Explicitly outside: hold/reroll/swap/move events, Audio v1.1, N outside 1..12,
 * multi-source banks (seeded selection), per-loop slices, seams and duplicate media.
 *
 * Layout files (simvltanea.layout-preset/1 and simvltanea.layout-pair/1) are read by
 * loadLayoutFile with Python's json.loads strictness, validated as load_layout_file
 * validates them, and fail with the same LayoutError code. stripsLayouts and
 * stripsSlice expand a strips preset to the same canonical JSON as Python's
 * strips_layouts and strips_slice. layoutFamilies and layoutEntry read both layout
 * bundle formats (the legacy authored map and simvltanea.layout-bundle/2).
 *
 * Rationals are integers or "n/d" strings (optionally negative) and use exact
 * BigInt arithmetic. Decimal strings ("1.5"), exponent strings ("3e0"), non-integer
 * numbers and non-finite numbers are rejected in states, as browser.runtime.js
 * rejects them. Layout files accept every ASCII spelling Python's Fraction() reads.
 *
 * What the compiler can see: compilePlan receives JavaScript values, not JSON text.
 * JSON.parse turns the number spellings 8.0, 2.4e1 and 1e0 into the integers 8, 24
 * and 1 before this code runs, so they are invisible here (Python's json.loads keeps
 * them as floats and refuses the state). The plan and state_sha256 then describe the
 * re-spelled integer state, which is what Python compiles for that state. A caller
 * that needs Python's exact strictness must reject such spellings in the raw text
 * first. One line: if (/\d[.eE]/.test(text.replace(/"(?:[^"\\]|\\.)*"/g, '""'))) throw new Error('float spelling');
 * (loadLayoutFile parses the text itself and keeps such numbers as floats.)
 *
 * Only plain objects are accepted (prototype Object.prototype or null) and a key
 * counts only when it is an own enumerable property, so an inherited property can
 * never change a plan without changing state_sha256. Cross-realm objects (for
 * example from another iframe) must be copied with structuredClone first.
 *
 * Every refusal is a CompilerError and never a different plan. Inputs outside the
 * subset that Python compiles throw with error.unsupported === true. Inputs that
 * Python also accepts but this compiler refuses on spelling or range (strings such
 * as "+1/2", " 1/2", "1_0/3", non-ASCII digits, "1.5" or "3e0", and seeds beyond
 * 2^53) throw with unsupported === false. So does anything Python itself refuses.
 * Layout errors also carry error.code, the stable reason code of Python's LayoutError.
 */
(function (root) {
  'use strict';
  const ENGINE_VERSION = '1.0.0', RNG = 'sha256-counter-v1', PLAN_VERSION = 1;
  const MAX_FRAMES = 14400, MAX_SEGMENTS = 1024, MAX_MEDIA_BYTES = 256 * 1024 * 1024;
  // The engine-wide browser subset. Which counts a family offers is read from the layout bundle.
  const MIN_LOOPS = 1, MAX_LOOPS = 12;
  const SUPPORTED_LOOP_COUNTS = Object.freeze(Array.from({length: MAX_LOOPS - MIN_LOOPS + 1}, (_, i) => MIN_LOOPS + i));
  const ORIENTATIONS = ['portrait', 'landscape'], SEAM_MODES = ['blur', 'feather', 'morph'];
  const ID = /^[A-Za-z0-9_-]{1,80}$/, DIGEST = /^[0-9a-f]{64}$/, RATIONAL = /^-?\d+(?:\/\d+)?$/;
  const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;
  const STATE_FIELDS = ['schema_version', 'engine_version', 'rng', 'seed', 'fps', 'frames', 'sources',
    'loops', 'layouts', 'events', 'audio', 'allow_source_reuse'];
  const SOURCE_FIELDS = ['id', 'path', 'sha256', 'kind', 'duration'];
  const LOOP_FIELDS = ['id', 'bank', 'offset', 'rate', 'period', 'epoch', 'held'];
  // Layout keys, mirrored from authoring/layout_presets.py (LAYOUT_FIELDS, CELL_FIELDS, ...).
  const LAYOUT_FIELDS = ['name', 'cells', 'full_bleed', 'presentation'];
  const CELL_FIELDS = ['loop', 'rect', 'fit', 'focal', 'lateral_offset'], CELL_REQUIRED = ['loop', 'rect', 'fit', 'focal'];
  const PRESENTATION_FIELDS = ['overlap_px', 'corner_radius', 'lateral_jitter'];
  const PRESET_FIELDS = ['format', 'name', 'family', 'counts', 'orientations', 'weights', 'fit', 'focal',
    'full_bleed', 'overlap_px', 'zoom', 'style'];
  const PAIR_FIELDS = ['format', 'count', 'portrait', 'landscape'];
  const PRESET_FORMAT = 'simvltanea.layout-preset/1', PAIR_FORMAT = 'simvltanea.layout-pair/1';
  const BUNDLE_FORMAT = 'simvltanea.layout-bundle/2', LEGACY_BUNDLE_FORMAT = 'simvltanea.layout-bundle/1';
  const STRIPS_MIN_COUNT = 1, STRIPS_MAX_COUNT = 12, PAIR_MAX_COUNT = 32, OVERLAP_PX_MAX = 8;
  const DIRECTIONS = ['rows', 'columns'], ORDERS = ['forward', 'reverse'], ZOOM_CURVES = ['power'];
  const OPPOSITE = {top: 'bottom', bottom: 'top', left: 'right', right: 'left'};
  const QUANTUM_MAX = 10 ** 6, GAMMA_DENOMINATOR_MAX = 100n, JITTER_QUANTUM = 1000n;
  const MAX_LAYOUT_FILE_BYTES = 1024 * 1024;

  class CompilerError extends Error {
    constructor(message, unsupported = false, code = undefined) {
      super(unsupported ? `outside the browser compiler subset: ${message}` : message);
      this.name = 'CompilerError';
      this.unsupported = unsupported;
      if (code !== undefined) this.code = code;
    }
  }
  const need = (test, message) => { if (!test) throw new CompilerError(message); };
  const refuse = (test, message) => { if (test) throw new CompilerError(message, true); };
  // Plain objects only, and a key exists only when it is an own enumerable property: the same
  // set canonicalJson hashes, so no inherited or hidden property can alter a plan unhashed.
  const isObject = value => {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
  };
  const has = (value, key) => Object.prototype.propertyIsEnumerable.call(value, key);
  const MAX_INTEGER_DIGITS = 4300; // CPython's default int/str conversion limit; Fraction() refuses more.

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
  const div = (x, y) => frac(x[0] * y[1], x[1] * y[0]);
  const cmp = (x, y) => { const v = x[0] * y[1] - y[0] * x[1]; return v < 0n ? -1 : v > 0n ? 1 : 0; };
  const floorDiv = (n, d) => (n % d !== 0n && (n < 0n) !== (d < 0n) ? n / d - 1n : n / d);
  const mod = (x, y) => sub(x, mul([floorDiv(x[0] * y[1], x[1] * y[0]), 1n], y));
  const text = ([n, d]) => (d === 1n ? String(n) : `${n}/${d}`);
  // Fraction.limit_denominator (CPython 3.12+), for nonnegative and negative values alike.
  function limitDenominator(value, max) {
    if (value[1] <= max) return value;
    let [p0, q0, p1, q1] = [0n, 1n, 1n, 0n], [n, d] = value;
    for (;;) {
      const a = floorDiv(n, d), q2 = q0 + a * q1;
      if (q2 > max) break;
      [p0, q0, p1, q1] = [p1, q1, p0 + a * p1, q2];
      [n, d] = [d, n - a * d];
    }
    const k = floorDiv(max - q0, q1);
    return 2n * d * (q0 + k * q1) <= value[1] ? frac(p1, q1) : frac(p0 + k * p1, q0 + k * q1);
  }

  function rational(value, where) {
    let n, d = 1n;
    if (typeof value === 'number' && Number.isSafeInteger(value)) n = BigInt(value);
    else if (typeof value === 'string' && RATIONAL.test(value)) {
      const [a, b = '1'] = value.split('/');
      need(a.replace('-', '').length <= MAX_INTEGER_DIGITS && b.length <= MAX_INTEGER_DIGITS,
        `${where}: rational numerator or denominator exceeds ${MAX_INTEGER_DIGITS} digits (leading zeros count)`);
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

  // ---- Layouts: one validator, mirrored from authoring/layout_presets.validate_layout_pair ----
  //
  // Every error carries Python's LayoutError code. A location {source, count, orientation,
  // cell} prefixes new messages; without a file or count (state validation) the legacy
  // messages of composition.validate_layouts are emitted unchanged. The `read` argument is
  // the rational reader: strict for states (the runtime's wire spellings), Python's
  // Fraction() spellings for layout files.

  const fileContext = where => where.source != null || where.count != null;
  function locate(where, legacy) {
    if (legacy && !fileContext(where)) return '';
    const parts = [];
    if (where.source != null) parts.push(String(where.source));
    if (where.count != null) parts.push(`count ${where.count}`);
    if (where.orientation != null) parts.push(where.orientation);
    if (where.cell != null) parts.push(`cell ${where.cell}`);
    return parts.length ? `${parts.join(', ')}: ` : '';
  }
  const fail = (where, code, message, legacy = false) => {
    throw new CompilerError(locate(where, legacy) + message, false, code);
  };
  const check = (test, where, code, message, legacy = false) => { if (!test) fail(where, code, message, legacy); };

  // Floats as json.loads would keep them, so a layout file's 2.0 never passes as the integer 2.
  class JsonFloat {
    constructor(spelling) { this.spelling = spelling; this.value = Number(spelling); }
  }
  // Python dicts keep JSON key order; JavaScript objects move integer-like keys first. The
  // parser records the file order so errors surface in the order Python finds them.
  const keyOrder = new WeakMap();
  const entries = value => (keyOrder.get(value) || Object.keys(value)).filter(key => has(value, key))
    .map(key => [key, value[key]]);

  // repr() of the JSON values Python's messages quote.
  const NON_PRINTABLE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\p{Zs}]/u;
  function pyString(value) {
    const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
    let out = quote;
    for (const ch of value) {
      const code = ch.codePointAt(0);
      if (ch === quote || ch === '\\') out += `\\${ch}`;
      else if (ch === '\n') out += '\\n';
      else if (ch === '\r') out += '\\r';
      else if (ch === '\t') out += '\\t';
      else if (ch !== ' ' && NON_PRINTABLE.test(ch)) {
        out += code <= 0xff ? `\\x${code.toString(16).padStart(2, '0')}` : code <= 0xffff ?
          `\\u${code.toString(16).padStart(4, '0')}` : `\\U${code.toString(16).padStart(8, '0')}`;
      } else out += ch;
    }
    return out + quote;
  }
  function pyFloat(value) {
    if (Number.isNaN(value)) return 'nan';
    if (!Number.isFinite(value)) return value > 0 ? 'inf' : '-inf';
    if (value === 0) return Object.is(value, -0) ? '-0.0' : '0.0';
    const [mantissa, power] = Math.abs(value).toExponential().split('e');
    const digits = mantissa.replace('.', ''), exponent = Number(power), sign = value < 0 ? '-' : '';
    if (exponent >= -4 && exponent < 16) {
      if (exponent >= digits.length - 1) return `${sign}${digits}${'0'.repeat(exponent - digits.length + 1)}.0`;
      if (exponent >= 0) return `${sign}${digits.slice(0, exponent + 1)}.${digits.slice(exponent + 1)}`;
      return `${sign}0.${'0'.repeat(-exponent - 1)}${digits}`;
    }
    const head = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    return `${sign}${head}e${exponent < 0 ? '-' : '+'}${String(Math.abs(exponent)).padStart(2, '0')}`;
  }
  function pyRepr(value) {
    if (value === null || value === undefined) return 'None';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'bigint') return String(value);
    if (typeof value === 'number') return Number.isInteger(value) ? String(value) : pyFloat(value);
    if (value instanceof JsonFloat) return pyFloat(value.value);
    if (typeof value === 'string') return pyString(value);
    if (Array.isArray(value)) return `[${value.map(pyRepr).join(', ')}]`;
    if (isObject(value)) return `{${entries(value).map(([k, v]) => `${pyString(k)}: ${pyRepr(v)}`).join(', ')}}`;
    return String(value);
  }
  const pyTypeName = value => value === null || value === undefined ? 'NoneType' : typeof value === 'boolean' ? 'bool'
    : typeof value === 'string' ? 'str' : typeof value === 'bigint' ? 'int'
    : typeof value === 'number' ? (Number.isInteger(value) ? 'int' : 'float') : value instanceof JsonFloat ? 'float'
    : Array.isArray(value) ? 'list' : isObject(value) ? 'dict' : typeof value;
  // type(value) is int: JSON integers (safe numbers or BigInt), never floats or booleans.
  const isInt = value => (typeof value === 'number' && Number.isInteger(value)) || typeof value === 'bigint';

  // Python's Fraction(str) grammar (3.12+), ASCII digits; \s is Python's Unicode whitespace.
  const PY_SPACE = '[\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]';
  const PY_FRACTION = new RegExp(`^${PY_SPACE}*([-+]?)(?=[0-9]|\\.[0-9])([0-9]*|[0-9]+(?:_[0-9]+)*)` +
    `(?:(?:${PY_SPACE}*/${PY_SPACE}*([0-9]+(?:_[0-9]+)*))?|(?:\\.([0-9]*|[0-9]+(?:_[0-9]+)*))?` +
    `(?:[eE]([-+]?[0-9]+(?:_[0-9]+)*))?)${PY_SPACE}*$`);
  const MAX_EXPONENT = 100000; // beyond it a nonzero value is out of bounds either way (see pyFraction)
  function pyInt(digits) {
    const plain = digits.replace(/_/g, '');
    if (plain.replace('-', '').length > MAX_INTEGER_DIGITS) return null; // int() refuses, so Fraction() does
    return BigInt(plain);
  }
  function pyFraction(value) {
    const match = PY_FRACTION.exec(value);
    if (!match) return null;
    const [, sign, num, denom, decimal, exp] = match;
    let n = pyInt(num || '0'), d = 1n;
    if (n === null) return null;
    if (denom) {
      d = pyInt(denom);
      if (d === null || d === 0n) return null;
    } else {
      if (decimal) {
        const plain = decimal.replace(/_/g, ''), part = pyInt(plain);
        if (part === null) return null;
        const scale = 10n ** BigInt(plain.length);
        n = n * scale + part; d *= scale;
      }
      if (exp) {
        const power = pyInt(exp);
        if (power === null) return null;
        if (n !== 0n) {
          // |n| < 10**8601 has fewer than 28600 factors of two or five, so beyond 10**±100000
          // the value is either above 10**9 or keeps a denominator above 10**9: out of bounds.
          if (power > MAX_EXPONENT || power < -MAX_EXPONENT) return 'out of bounds';
          if (power >= 0n) n *= 10n ** power; else d *= 10n ** -power;
        }
      }
    }
    return frac(sign === '-' ? -n : n, d);
  }
  // composition.rational() through layout_presets._rational: str or int, Fraction() spelling, bounded.
  function pyRead(value, label, where, code = 'rational', legacy = false) {
    let result;
    if (typeof value === 'string') result = pyFraction(value);
    else if (isInt(value)) result = frac(BigInt(value));
    else fail(where, code, `${label} must be an integer or rational string, not a float`, legacy);
    if (result === null) fail(where, code, `${label}: invalid rational`, legacy);
    const bounded = result !== 'out of bounds' && (result[0] < 0n ? -result[0] : result[0]) <= BOUND * result[1] &&
      result[1] <= BOUND;
    if (!bounded) fail(where, code, `${label}: out of bounds`, legacy);
    return result;
  }
  // States keep the compiler's strict wire spellings; the error gains the layout code.
  function strictRead(value, label, where, code = 'rational') {
    try { return rational(value, label); } catch (error) { error.code = code; throw error; }
  }

  function keysOf(value, allowed, required, label, where, legacy = false) {
    check(isObject(value), where, 'wrong-type', `${label} must be an object`, legacy);
    const extra = Object.keys(value).filter(key => !allowed.includes(key)).sort(byCodePoint);
    check(!extra.length, where, 'unknown-key', `${label}: unsupported fields ${pyRepr(extra)}`, legacy);
    const missing = required.filter(key => !has(value, key)).sort(byCodePoint);
    check(!missing.length, where, 'missing-key', `${label}: missing fields ${pyRepr(missing)}`, legacy);
  }
  function integerIn(value, low, high, label, where, code) {
    check(isInt(value) && value >= low && value <= high, where, code, `${label} must be an integer in ${low}..${high}`);
    return Number(value);
  }

  function rectOf(rect, where, read) {
    check(Array.isArray(rect) && rect.length === 4, where, 'wrong-type', 'rect must be [x,y,width,height]', true);
    const [x, y, w, h] = rect.map(value => read(value, 'rect', where, 'rational', true));
    check(cmp(x, ZERO) >= 0 && cmp(y, ZERO) >= 0 && positive(w) && positive(h) && cmp(add(x, w), ONE) <= 0 &&
      cmp(add(y, h), ONE) <= 0, where, 'bounds', 'rect must have positive area inside the unit canvas', true);
    return [x, y, w, h];
  }
  const minimum = (a, b) => (cmp(a, b) <= 0 ? a : b), maximum = (a, b) => (cmp(a, b) >= 0 ? a : b);
  const same = (a, b) => cmp(a, b) === 0;

  function sharedEdges(boxes) {
    const result = [];
    boxes.forEach(([x, y, w, h], i) => {
      for (let j = i + 1; j < boxes.length; j++) {
        const [a, b, c, d] = boxes[j];
        const horizontal = [maximum(x, a), minimum(add(x, w), add(a, c))];
        const vertical = [maximum(y, b), minimum(add(y, h), add(b, d))];
        for (const [edge, touches, [lo, hi]] of [['bottom', same(add(y, h), b), horizontal],
          ['top', same(y, add(b, d)), horizontal], ['right', same(add(x, w), a), vertical],
          ['left', same(x, add(a, c)), vertical]]) {
          if (touches && cmp(lo, hi) < 0) result.push({a: i, b: j, edge, span: [text(lo), text(hi)]});
        }
      }
    });
    return result;
  }

  /* Exact shared edges between cells, in draw order: side `edge` of cell `a` coincides with
   * the opposite side of cell `b` over the positive-length `span`; a < b. */
  function adjacency(cells) {
    const where = {};
    check(Array.isArray(cells), where, 'wrong-type', 'cells must be an array');
    return sharedEdges(cells.map((cell, index) => {
      check(isObject(cell) && has(cell, 'rect'), {cell: index}, 'wrong-type', 'cell must be an object with a rect');
      return rectOf(cell.rect, {cell: index}, pyRead);
    }));
  }

  function cornerRule(boxes, edges, where) {
    check(edges.length, where, 'corner-rule',
      'presentation.corner_radius > 0 requires cells that share an edge; no corner can be rounded');
    // Python iterates sorted((index, side) -> spans): by cell index, then side name.
    const spans = new Map();
    for (const edge of edges) {
      const key = `${edge.b} ${OPPOSITE[edge.edge]}`;
      if (!spans.has(key)) spans.set(key, {index: edge.b, side: OPPOSITE[edge.edge], covered: []});
      spans.get(key).covered.push(edge.span.map(value => pyFraction(value)));
    }
    const ordered = [...spans.values()].sort((p, q) => p.index - q.index || (p.side < q.side ? -1 : p.side > q.side ? 1 : 0));
    for (const {index, side, covered} of ordered) {
      const [x, y, w, h] = boxes[index];
      const [low, high] = side === 'top' || side === 'bottom' ? [x, add(x, w)] : [y, add(y, h)];
      for (const corner of [low, high]) {
        check(covered.some(([a, b]) => cmp(a, corner) <= 0 && cmp(corner, b) <= 0), {...where, cell: index},
          'corner-rule', `rounded ${side} corner at ${text(corner)} has no earlier-drawn neighbour beneath it`);
      }
    }
  }

  const STYLE_MAX = [1n, 20n];
  const styleRange = value => cmp(value, ZERO) >= 0 && cmp(value, STYLE_MAX) <= 0;

  function validateLayout(layout, loopIds, where, read) {
    const label = fileContext(where) ? 'layout' : where.orientation;
    keysOf(layout, LAYOUT_FIELDS, ['name', 'cells'], label, where, true);
    check(typeof layout.name === 'string' && layout.name !== '', where, 'wrong-type', 'layout name is required', true);
    check(Array.isArray(layout.cells), where, 'wrong-type', 'cells must be an array', true);
    const cells = layout.cells, seen = [], boxes = [];
    // Count before geometry: the pairwise overlap loop is quadratic in cells.length.
    check(loopIds || where.count == null || cells.length === where.count, where, 'cell-count',
      `has ${cells.length} cells, expected ${where.count}`);
    cells.forEach((cell, index) => {
      const at = {...where, cell: index};
      keysOf(cell, CELL_FIELDS, CELL_REQUIRED, 'cell', at, true);
      check(typeof cell.loop === 'string' && ID.test(cell.loop), at, 'loop-id', 'cell.loop: invalid ID', true);
      seen.push(cell.loop);
      check(cell.fit === 'contain' || cell.fit === 'cover', at, 'fit', 'only contain/cover fit is implemented', true);
      check(Array.isArray(cell.focal) && cell.focal.length === 2, at, 'focal', 'focal needs two coordinates', true);
      check(cell.focal.every(value => unit(read(value, 'focal', at, 'focal', true))), at, 'focal',
        'focal must be in 0..1', true);
      const box = rectOf(cell.rect, at, read), [x, y, w, h] = box;
      for (const [a, b, c, d] of boxes) {
        check(!(cmp(x, add(a, c)) < 0 && cmp(a, add(x, w)) < 0 && cmp(y, add(b, d)) < 0 && cmp(b, add(y, h)) < 0),
          at, 'overlap', 'overlapping/occluded panels are not supported in schema v1', true);
      }
      boxes.push(box);
    });
    if (loopIds) {
      check(seen.length === loopIds.size && new Set(seen).size === loopIds.size && seen.every(id => loopIds.has(id)),
        where, 'mapping', 'each orientation must map every loop exactly once', true);
    } else {
      check(new Set(seen).size === seen.length, where, 'mapping', 'each loop must appear in exactly one cell');
    }
    if (has(layout, 'full_bleed') || has(layout, 'presentation')) {
      check(cells.length >= STRIPS_MIN_COUNT && cells.length <= STRIPS_MAX_COUNT, where, 'count-range',
        `full_bleed and presentation are supported for ${STRIPS_MIN_COUNT}..${STRIPS_MAX_COUNT} cells, ` +
        `not ${cells.length}`);
    }
    if (has(layout, 'full_bleed')) check(typeof layout.full_bleed === 'boolean', where, 'wrong-type', 'full_bleed must be boolean');
    if (has(layout, 'full_bleed') && layout.full_bleed === true) {
      cells.forEach((cell, index) => check(cell.fit === 'cover', {...where, cell: index}, 'full-bleed-fit',
        'full_bleed requires fit cover on every cell (contain exposes background)'));
      const area = boxes.reduce((sum, [, , w, h]) => add(sum, mul(w, h)), ZERO);
      check(same(area, ONE), where, 'full-bleed-coverage',
        `full_bleed requires the rects to tile the unit square exactly; they cover ${text(area)}`);
    }
    const edges = sharedEdges(boxes);
    let jitter = ZERO;
    if (has(layout, 'presentation')) {
      const presentation = layout.presentation;
      keysOf(presentation, PRESENTATION_FIELDS, PRESENTATION_FIELDS, 'presentation', where);
      const overlap = integerIn(presentation.overlap_px, 0, OVERLAP_PX_MAX, 'presentation.overlap_px (device pixels)',
        where, 'overlap-px');
      check(overlap === 0 || edges.length, where, 'overlap-px-no-shared-edge',
        'presentation.overlap_px > 0 is a bleed across shared edges; this layout has no shared edge');
      const radius = read(presentation.corner_radius, 'presentation.corner_radius', where, 'corner-radius');
      check(styleRange(radius), where, 'corner-radius',
        'presentation.corner_radius must be in 0..1/20 of the canvas minor dimension');
      if (radius[0] !== 0n) cornerRule(boxes, edges, where);
      jitter = read(presentation.lateral_jitter, 'presentation.lateral_jitter', where, 'lateral-jitter');
      check(styleRange(jitter), where, 'lateral-jitter',
        'presentation.lateral_jitter must be in 0..1/20 of the canvas extent along the strip');
    }
    cells.forEach((cell, index) => {
      const at = {...where, cell: index};
      if (jitter[0] === 0n) {
        check(!has(cell, 'lateral_offset'), at, 'lateral-offset', 'lateral_offset requires presentation.lateral_jitter > 0');
        return;
      }
      check(has(cell, 'lateral_offset'), at, 'lateral-offset',
        'presentation.lateral_jitter > 0 requires a resolved lateral_offset on every cell');
      const offset = read(cell.lateral_offset, 'lateral_offset', at, 'lateral-offset');
      check(cmp(offset[0] < 0n ? [-offset[0], offset[1]] : offset, jitter) <= 0, at, 'lateral-offset',
        `|lateral_offset| must not exceed lateral_jitter ${text(jitter)}, got ${text(offset)}`);
    });
    return seen;
  }

  /* validate_layout_pair: with loopIds (a Set) every orientation maps exactly those loops;
   * without them each orientation needs `count` distinct loops and both map the same loops. */
  function checkLayoutPair(pair, loopIds, source, count, read) {
    const where = {source: source ?? null, count: count ?? null};
    keysOf(pair, ORIENTATIONS, ORIENTATIONS, 'layouts', where, true);
    const mapped = {};
    for (const [orientation, layout] of entries(pair)) {
      mapped[orientation] = validateLayout(layout, loopIds, {...where, orientation}, read);
    }
    if (!loopIds) {
      const portrait = new Set(mapped.portrait), landscape = new Set(mapped.landscape);
      check(portrait.size === landscape.size && [...portrait].every(id => landscape.has(id)), where, 'mapping',
        'portrait and landscape must map the same loops');
    }
  }
  function validateLayoutPair(pair, loopIds = null, options = {}) {
    need(loopIds === null || Array.isArray(loopIds) || loopIds instanceof Set, 'loop IDs must be an array or a Set');
    checkLayoutPair(pair, loopIds === null ? null : new Set(loopIds), options.source, options.count, pyRead);
    return true;
  }

  // The slice is validated as composition.validate_slice does; the state-wide slice compiles.
  function validateSlice(value) {
    fields(value, ['enabled', 'width', 'height'], ['enabled'], 'slice');
    need(typeof value.enabled === 'boolean', 'slice.enabled must be boolean');
    for (const key of ['width', 'height']) if (has(value, key)) within(`slice.${key}`, ONE, false)(value[key]);
    if (value.enabled) {
      const [w, h] = sliceSize(value);
      need(cmp(mul(w, h), ONE) < 0, 'slice must not reveal full frame (area < 1)');
      need(cmp(w, ONE) < 0 || cmp(h, ONE) < 0, 'slice must crop at least one dimension');
    }
  }
  const sliceSize = value => ['width', 'height'].map(key => rational(has(value, key) ? value[key] : '1/2', `slice.${key}`));
  // The seam is validated as composition.py does, then refused if enabled.
  function validateSeam(value, bounds) {
    fields(value, ['enabled', ...Object.keys(bounds)], ['enabled'], 'seam');
    need(typeof value.enabled === 'boolean', 'seam.enabled must be boolean');
    for (const [key, test] of Object.entries(bounds)) if (has(value, key)) test(value[key]);
    refuse(value.enabled, 'seam is enabled; seams are compiled by Python only');
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
      `${state.loops.length} loops; the browser compiler covers N=${MIN_LOOPS}..${MAX_LOOPS} independent loops ` +
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
    need(Object.keys(audio).length === 3 && ['mode', 'routing', 'generative'].every(key => has(audio, key)) &&
      audio.mode === 'none' && audio.routing === null && audio.generative === null,
      'versioned loop exports are silent in v1; Audio v1.1 requires schema_version "1.1"');
    checkLayoutPair(state.layouts, loopIds, null, null, strictRead);
    if (has(state, 'slice')) validateSlice(state.slice);
    if (has(state, 'seam')) {
      validateSeam(state.seam, {width: within('seam.width', [3n, 20n], true),
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

  // Python sorts str keys by code point; the default JS sort compares UTF-16 units and
  // disagrees for non-BMP keys against U+E000..U+FFFF.
  const byCodePoint = (a, b) => {
    const x = Array.from(a, ch => ch.codePointAt(0)), y = Array.from(b, ch => ch.codePointAt(0));
    for (let i = 0; i < x.length && i < y.length; i++) if (x[i] !== y[i]) return x[i] - y[i];
    return x.length - y.length;
  };

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
    return `{${Object.keys(value).sort(byCodePoint).map(key => `${canonicalJson(key)}:${canonicalJson(value[key])}`).join(',')}}`;
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

  /* composition.slice_rect: a deterministic window per loop per selection period (it moves
   * at each wrap of local time over loop.period), sha256-counter-v1 in its own "slice" domain. */
  function sliceRect(state, loop, cycle, [w, h]) {
    const payload = `[${canonicalJson(RNG)},${canonicalJson(state.seed)},${canonicalJson(loop.id)},"slice",` +
      `${loop.epoch},${cycle},${canonicalJson(text(w))},${canonicalJson(text(h))}]`;
    const digest = sha256Hex(new TextEncoder().encode(payload));
    const sample = at => BigInt(parseInt(digest.slice(at, at + 4), 16) % 1000);
    const x = limitDenominator(mul([sample(0), 1000n], sub(ONE, w)), BOUND);
    const y = limitDenominator(mul([sample(4), 1000n], sub(ONE, h)), BOUND);
    return [text(x), text(y), text(w), text(h)];
  }

  function compilePlan(state) {
    validateState(state);
    const fps = BigInt(state.fps), sources = new Map(state.sources.map(source => [source.id, source]));
    const slice = has(state, 'slice') && state.slice.enabled ? sliceSize(state.slice) : null;
    let spanCount = 0;
    const tracks = state.loops.map(loop => {
      const source = sources.get(loop.bank[0]), still = source.kind === 'still';
      const rate = rational(loop.rate, 'rate'), offset = rational(loop.offset, 'offset');
      const period = rational(loop.period, 'period');
      need(still || (cmp(rate, [1n, 16n]) >= 0 && cmp(rate, EIGHT) <= 0),
        'browser video rate must be within 1/16..8; offline model unchanged');
      const [low, high] = (has(loop, 'trim') ? loop.trim : [0, source.duration]).map(value => rational(value, 'trim'));
      const length = sub(high, low), step = loop.held || still ? ZERO : mul(rate, [1n, fps]);
      const spans = [];
      let previous = null, previousRect = null, cycle = null, rect = null;
      for (let frame = 0; frame < state.frames; frame++) {
        const local = loop.held ? offset : add(offset, mul(frac(BigInt(frame), fps), rate));
        const sourceOffset = still ? ZERO : add(low, mod(local, length));
        if (slice) {
          const current = floorDiv(local[0] * period[1], local[1] * period[0]);
          if (current !== cycle) { cycle = current; rect = sliceRect(state, loop, cycle, slice); }
        }
        const key = rect && rect.join(' ');
        if (previous === null || cmp(sourceOffset, add(previous, step)) !== 0 || key !== previousRect) {
          const span = {frame, id: loop.id, source: source.id, kind: source.kind, local: text(local),
            source_offset: text(sourceOffset), rate: text(rate), held: loop.held, epoch: loop.epoch};
          if (rect) span.slice_rect = rect.slice();
          spans.push(span);
        }
        previous = sourceOffset;
        previousRect = key;
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
      slice: planSlice(state)};
  }
  // compile_plan copies the slice and, when enabled, writes canonical width then height.
  function planSlice(state) {
    const value = structuredClone(has(state, 'slice') ? state.slice : {enabled: false});
    if (value.enabled) [value.width, value.height] = sliceSize(state.slice).map(text);
    return value;
  }

  // Caller data to a valid state; loops reference source IDs and layouts use loop IDs.
  // The optional slice is the state-wide slice (for strips: the bundle's or stripsSlice's zoom).
  function buildState(input) {
    fields(input, ['sources', 'loops', 'layouts', 'fps', 'frames', 'seed', 'slice'],
      ['sources', 'loops', 'layouts', 'frames'], 'compiler input');
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
    if (has(input, 'slice') && input.slice !== null) state.slice = structuredClone(input.slice);
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

  // ---- Layout files: strict JSON, simvltanea.layout-pair/1 and simvltanea.layout-preset/1 ----

  /* json.loads with layout_presets._read_json's hooks: duplicate keys and NaN/Infinity are
   * errors, numbers spelled with a fraction or exponent stay floats (JsonFloat), integers stay
   * exact (BigInt beyond 2**53), and objects remember their key order. Every failure has
   * code "json" and names the file. Syntax messages follow json.JSONDecodeError's wording. */
  function parseLayoutJson(source, name = null) {
    need(typeof source === 'string', 'layout file text must be a string');
    const where = {source: name}, length = source.length;
    let at = 0;
    const position = pos => {
      const line = source.slice(0, pos).split('\n').length, last = source.lastIndexOf('\n', pos - 1);
      return `line ${line} column ${last < 0 ? pos + 1 : pos - last} (char ${pos})`;
    };
    const bad = (message, pos = at) => fail(where, 'json', `malformed JSON: ${message}: ${position(pos)}`);
    const skip = () => { while (at < length && ' \t\n\r'.includes(source[at])) at++; };
    const NUMBER = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/y;
    const ESCAPES = {'"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t'};
    function string() {
      const begin = at++;
      let out = '';
      for (;;) {
        if (at >= length) bad('Unterminated string starting at', begin);
        const ch = source[at];
        if (ch === '"') { at++; return out; }
        if (ch < ' ') bad('Invalid control character at');
        if (ch !== '\\') { out += ch; at++; continue; }
        const escape = source[at + 1];
        if (escape === undefined) bad('Unterminated string starting at', begin);
        if (escape !== 'u') {
          if (!(escape in ESCAPES)) bad('Invalid \\escape');
          out += ESCAPES[escape]; at += 2; continue;
        }
        const hex = source.slice(at + 2, at + 6);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) bad('Invalid \\uXXXX escape', at + 1);
        out += String.fromCharCode(parseInt(hex, 16)); // pairs and lone surrogates as Python keeps them
        at += 6;
      }
    }
    function value() {
      const ch = source[at];
      if (ch === '"') return string();
      if (ch === '{') return object();
      if (ch === '[') return array();
      for (const [word, result] of [['null', null], ['true', true], ['false', false]]) {
        if (source.startsWith(word, at)) { at += word.length; return result; }
      }
      NUMBER.lastIndex = at;
      const number = NUMBER.exec(source);
      if (number) {
        at += number[0].length;
        if (number[1] !== undefined || number[2] !== undefined) return new JsonFloat(number[0]);
        const integer = Number(number[0]);
        return Number.isSafeInteger(integer) ? integer : BigInt(number[0]);
      }
      for (const word of ['NaN', 'Infinity', '-Infinity']) {
        if (source.startsWith(word, at)) fail(where, 'json', `non-finite number ${word} is not allowed`);
      }
      return bad('Expecting value');
    }
    function object() {
      at++; skip();
      const pairs = [];
      if (source[at] === '}') { at++; return build(pairs); }
      for (;;) {
        if (source[at] !== '"') bad('Expecting property name enclosed in double quotes');
        const key = string();
        skip();
        if (source[at] !== ':') bad("Expecting ':' delimiter");
        at++; skip();
        pairs.push([key, value()]);
        skip();
        if (source[at] === '}') { at++; return build(pairs); }
        if (source[at] !== ',') bad("Expecting ',' delimiter");
        const comma = at++;
        skip();
        if (source[at] === '}') bad('Illegal trailing comma before end of object', comma);
      }
    }
    function build(pairs) {
      const result = Object.create(null), order = [];
      for (const [key, item] of pairs) {
        check(!Object.prototype.hasOwnProperty.call(result, key), where, 'json', `duplicate JSON key: ${key}`);
        result[key] = item; order.push(key);
      }
      keyOrder.set(result, order);
      return result;
    }
    function array() {
      at++; skip();
      const items = [];
      if (source[at] === ']') { at++; return items; }
      for (;;) {
        items.push(value());
        skip();
        if (source[at] === ']') { at++; return items; }
        if (source[at] !== ',') bad("Expecting ',' delimiter");
        const comma = at++;
        skip();
        if (source[at] === ']') bad('Illegal trailing comma before end of array', comma);
      }
    }
    if (source.startsWith('\ufeff')) bad('Unexpected UTF-8 BOM (decode using utf-8-sig)', 0);
    skip();
    const result = value();
    skip();
    if (at !== length) bad('Extra data');
    return result;
  }

  // The default preset, as data: Python's DEFAULT_STRIPS_PRESET and examples/layout-presets/strips.json.
  const deepFreeze = value => {
    if (value && typeof value === 'object') Object.values(value).forEach(deepFreeze);
    return Object.freeze(value);
  };
  const DEFAULT_STRIPS_PRESET = deepFreeze({
    format: PRESET_FORMAT, name: 'strips', family: 'strips', counts: {min: 1, max: 12},
    orientations: {portrait: {direction: 'rows', order: 'forward'}, landscape: {direction: 'columns', order: 'forward'}},
    weights: {default: 'equal', by_count: {}}, fit: 'cover', focal: {default: ['1/2', '1/2'], by_index: {}},
    full_bleed: true, overlap_px: 2,
    zoom: {curve: 'power', z1: '8', gamma: '3/5', min_zoom: '10/9', quantum: 1000, table: {}},
    style: {corner_radius: '0', lateral_jitter: '0'},
  });
  const presetDefault = key => structuredClone(DEFAULT_STRIPS_PRESET[key]);

  function section(raw, key, allowed, where) {
    if (!has(raw, key)) return presetDefault(key);
    keysOf(raw[key], allowed, [], key, where);
    return {...presetDefault(key), ...raw[key]};
  }
  // The length check comes first, as in Python, and the key excerpt in the message is bounded.
  function countKey(key, low, high, label, where, code) {
    check(key.length <= String(high).length && /^(?:0|[1-9][0-9]*)$/.test(key) && Number(key) >= low &&
      Number(key) <= high, where, code,
      `${label} key ${pyRepr(Array.from(key).slice(0, 40).join(''))} must be an integer string in ${low}..${high}`);
    return Number(key);
  }
  function focalPair(value, label, where) {
    check(Array.isArray(value) && value.length === 2, where, 'focal', `${label} needs two coordinates`);
    const pair = value.map(item => pyRead(item, label, where, 'focal'));
    check(pair.every(unit), where, 'focal', `${label} must be in 0..1`);
    return pair;
  }

  // layout_presets._resolve_preset: defaults filled in, every key and type checked.
  function resolvePreset(raw, source = null) {
    const where = {source};
    keysOf(raw, PRESET_FIELDS, ['format', 'name', 'family'], 'preset', where);
    check(raw.format === PRESET_FORMAT, where, 'format',
      `format must be ${pyRepr(PRESET_FORMAT)}, got ${pyRepr(raw.format)}`);
    const name = raw.name;
    check(typeof name === 'string' && ID.test(name), where, 'preset', 'name must match [A-Za-z0-9_-]{1,80}');
    check(raw.family === 'strips', where, 'preset',
      `family must be 'strips' (the authored family is build_artifact001), got ${pyRepr(raw.family)}`);

    const counts = section(raw, 'counts', ['min', 'max'], where);
    const low = integerIn(counts.min, STRIPS_MIN_COUNT, STRIPS_MAX_COUNT, 'counts.min', where, 'counts');
    const high = integerIn(counts.max, STRIPS_MIN_COUNT, STRIPS_MAX_COUNT, 'counts.max', where, 'counts');
    check(low <= high, where, 'counts', 'counts.min must not exceed counts.max');

    const orientationsRaw = section(raw, 'orientations', ORIENTATIONS, where), orientations = {};
    for (const orientation of ORIENTATIONS) {
      const label = `orientations.${orientation}`;
      keysOf(orientationsRaw[orientation], ['direction', 'order'], [], label, where);
      const value = {...DEFAULT_STRIPS_PRESET.orientations[orientation], ...orientationsRaw[orientation]};
      check(DIRECTIONS.includes(value.direction), where, 'orientation',
        `${label}.direction must be one of ${pyRepr(DIRECTIONS)}`);
      check(ORDERS.includes(value.order), where, 'orientation', `${label}.order must be one of ${pyRepr(ORDERS)}`);
      orientations[orientation] = [value.direction, value.order];
    }

    const weightsRaw = section(raw, 'weights', ['default', 'by_count'], where), weights = new Map();
    check(weightsRaw.default === 'equal', where, 'weights', "weights.default must be 'equal'");
    check(isObject(weightsRaw.by_count), where, 'wrong-type', 'weights.by_count must be an object');
    for (const [key, value] of entries(weightsRaw.by_count)) {
      const count = countKey(key, low, high, 'weights.by_count', where, 'weights'), at = {...where, count};
      check(Array.isArray(value) && value.length === count, at, 'weights', `weights.by_count needs exactly ${count} weights`);
      const parsed = value.map(item => pyRead(item, 'weights.by_count', at, 'weights'));
      check(parsed.every(positive), at, 'weights', 'weights must be positive');
      const total = parsed.reduce(add, ZERO), edges = [ZERO];
      for (const weight of parsed) edges.push(add(edges[edges.length - 1], weight));
      check(edges.map(edge => div(edge, total)).concat(parsed.map(weight => div(weight, total)))
        .every(value => value[1] <= BOUND), at, 'weights',
        'weights.by_count must give strip edges and sizes with denominators of at most 10**9');
      weights.set(count, parsed);
    }

    const fit = has(raw, 'fit') ? raw.fit : DEFAULT_STRIPS_PRESET.fit;
    check(fit === 'cover' || fit === 'contain', where, 'fit', "fit must be 'cover' or 'contain'");
    const fullBleed = has(raw, 'full_bleed') ? raw.full_bleed : DEFAULT_STRIPS_PRESET.full_bleed;
    check(typeof fullBleed === 'boolean', where, 'wrong-type', 'full_bleed must be boolean');
    check(!fullBleed || fit === 'cover', where, 'full-bleed-fit',
      "full_bleed requires fit 'cover' (contain exposes background)");

    const focalRaw = section(raw, 'focal', ['default', 'by_index'], where);
    const focal = focalPair(focalRaw.default, 'focal.default', where);
    check(isObject(focalRaw.by_index), where, 'wrong-type', 'focal.by_index must be an object');
    const focalByIndex = new Map();
    for (const [key, value] of entries(focalRaw.by_index)) {
      const index = countKey(key, 0, high - 1, 'focal.by_index', where, 'focal');
      focalByIndex.set(index, focalPair(value, `focal.by_index.${key}`, where));
    }

    const overlapPx = integerIn(has(raw, 'overlap_px') ? raw.overlap_px : DEFAULT_STRIPS_PRESET.overlap_px, 0,
      OVERLAP_PX_MAX, 'overlap_px (device pixels)', where, 'overlap-px');

    const zoom = section(raw, 'zoom', ['curve', 'z1', 'gamma', 'min_zoom', 'quantum', 'table'], where);
    check(ZOOM_CURVES.includes(zoom.curve), where, 'zoom', `zoom.curve must be one of ${pyRepr(ZOOM_CURVES)}`);
    const THOUSAND = [1000n, 1n];
    const z1 = pyRead(zoom.z1, 'zoom.z1', where, 'zoom');
    check(positive(z1) && cmp(z1, THOUSAND) <= 0, where, 'zoom', 'zoom.z1 must be in (0, 1000]');
    const gamma = pyRead(zoom.gamma, 'zoom.gamma', where, 'zoom');
    check(cmp(gamma, ZERO) >= 0 && cmp(gamma, [2n, 1n]) <= 0 && gamma[1] <= GAMMA_DENOMINATOR_MAX, where, 'zoom',
      'zoom.gamma must be in 0..2 with a denominator of at most 100');
    const minZoom = pyRead(zoom.min_zoom, 'zoom.min_zoom', where, 'zoom');
    check(cmp(minZoom, ONE) > 0 && cmp(minZoom, THOUSAND) <= 0, where, 'zoom',
      'zoom.min_zoom must be in (1, 1000] so no panel ever shows a full frame');
    const quantum = integerIn(zoom.quantum, 2, QUANTUM_MAX, 'zoom.quantum', where, 'zoom');
    check(isObject(zoom.table), where, 'wrong-type', 'zoom.table must be an object');
    const largest = frac(floorDiv(BigInt(quantum) * minZoom[1], minZoom[0]), BigInt(quantum)), table = new Map();
    for (const [key, value] of entries(zoom.table)) {
      const count = countKey(key, low, high, 'zoom.table', where, 'zoom');
      const size = pyRead(value, `zoom.table.${key}`, where, 'zoom');
      check(positive(size) && cmp(size, largest) <= 0 && mul(size, [BigInt(quantum), 1n])[1] === 1n,
        {...where, count}, 'zoom', `zoom.table.${key} must be a multiple of 1/${quantum} in (0, ${text(largest)}] ` +
        `(minimum zoom ${text(minZoom)})`);
      table.set(count, size);
    }

    const style = section(raw, 'style', ['corner_radius', 'lateral_jitter'], where);
    const cornerRadius = pyRead(style.corner_radius, 'style.corner_radius', where, 'corner-radius');
    check(styleRange(cornerRadius), where, 'corner-radius', 'style.corner_radius must be in 0..1/20');
    const lateralJitter = pyRead(style.lateral_jitter, 'style.lateral_jitter', where, 'lateral-jitter');
    check(styleRange(lateralJitter), where, 'lateral-jitter', 'style.lateral_jitter must be in 0..1/20');
    return {name, low, high, orientations, weights, fit, focal, focalByIndex, fullBleed, overlapPx, z1, gamma,
      minZoom, quantum, table, cornerRadius, lateralJitter, source};
  }

  function presetOf(preset, source) {
    if (typeof preset === 'string') {
      if (preset === 'authored') {
        fail({}, 'preset', "preset 'authored' is the authored family (N=2..7); use build_artifact001");
      }
      if (preset !== 'strips') {
        fail({}, 'preset', `unknown preset ${pyRepr(preset)}; built-ins are ['strips'] (pass your own file by path)`);
      }
      return resolvePreset(DEFAULT_STRIPS_PRESET, null);
    }
    if (isObject(preset)) return checkedPreset(preset, source ?? null);
    return fail({}, 'preset', 'preset must be a built-in name, a preset object or a file path');
  }
  // layout_presets._checked_preset: resolve, then expand every count the preset advertises.
  function checkedPreset(raw, source) {
    const preset = resolvePreset(raw, source);
    for (let count = preset.low; count <= preset.high; count++) {
      expandPreset(preset, count);
      presetSlice(preset, count);
    }
    return preset;
  }
  function presetCount(preset, count) {
    const where = {source: preset.source};
    check(isInt(count), where, 'count-range', `count must be an integer, not ${pyTypeName(count)}`);
    check(count >= preset.low && count <= preset.high, where, 'count-range',
      `strips preset ${pyRepr(preset.name)} supports N=${preset.low}..${preset.high}; count ${count} is refused ` +
      '(no filler, no duplication, never moved to another family)');
    return Number(count);
  }

  const power = (value, exponent) => [value[0] ** exponent, value[1] ** exponent];
  // Exact floor(x + 1/2) for x >= 0 with x**root == target (layout_presets._round_half_up_root).
  function roundHalfUpRoot(target, root, estimate) {
    const fits = k => k === 0n || cmp(power([2n * k - 1n, 2n], root), target) <= 0;
    let k = BigInt(Math.max(0, Math.floor(estimate + 0.5)));
    while (!fits(k)) k -= 1n;
    while (fits(k + 1n)) k += 1n;
    return k;
  }
  // zoom(N) = max(min_zoom, z1 / N**gamma); s = 1/zoom rounded half up to 1/quantum, exactly.
  function presetSlice(preset, count) {
    if (preset.table.has(count)) return preset.table.get(count);
    const [p, q] = preset.gamma, quantum = BigInt(preset.quantum);
    const target = mul(power(div([quantum, 1n], preset.z1), q), power([BigInt(count), 1n], p));
    const estimate = preset.quantum * count ** (Number(p) / Number(q)) / (Number(preset.z1[0]) / Number(preset.z1[1]));
    let steps = roundHalfUpRoot(target, q, estimate);
    const ceiling = floorDiv(quantum * preset.minZoom[1], preset.minZoom[0]);
    if (ceiling < steps) steps = ceiling;
    check(steps >= 1n, {source: preset.source, count}, 'zoom',
      `zoom rounds to an empty slice at quantum 1/${preset.quantum}`);
    return frac(steps, quantum);
  }

  // sha256-counter-v1 over [rng, preset name, N, orientation, "jitter", k], quantised to 1/1000.
  function lateralOffset(name, count, orientation, index, jitter) {
    const steps = floorDiv(jitter[0] * JITTER_QUANTUM, jitter[1]);
    if (steps === 0n) return ZERO;
    const digest = sha256Hex(new TextEncoder().encode(canonicalJson([RNG, name, count, orientation, 'jitter', index])));
    return frac(BigInt(`0x${digest.slice(0, 16)}`) % (2n * steps + 1n) - steps, JITTER_QUANTUM);
  }

  // layout_presets._expand: strip k is loop-{k+1}; the array order is the draw order.
  function expandPreset(preset, count) {
    const weights = preset.weights.get(count) || Array.from({length: count}, () => ONE);
    const total = weights.reduce(add, ZERO), edges = [ZERO];
    for (const weight of weights) edges.push(add(edges[edges.length - 1], div(weight, total)));
    const layouts = {}, shared = count > 1;
    for (const orientation of ORIENTATIONS) {
      const [direction, order] = preset.orientations[orientation], cells = [];
      for (let k = 0; k < count; k++) {
        const start = edges[k], size = sub(edges[k + 1], edges[k]);
        const rect = direction === 'rows' ? [ZERO, start, ONE, size] : [start, ZERO, size, ONE];
        const cell = {loop: `loop-${k + 1}`, rect: rect.map(text), fit: preset.fit,
          focal: (preset.focalByIndex.get(k) || preset.focal).map(text)};
        if (preset.lateralJitter[0] !== 0n) {
          cell.lateral_offset = text(lateralOffset(preset.name, count, orientation, k, preset.lateralJitter));
        }
        cells.push(cell);
      }
      if (order === 'reverse') cells.reverse();
      layouts[orientation] = {name: `${preset.name}-${count}-${orientation}`, full_bleed: preset.fullBleed,
        presentation: {overlap_px: shared ? preset.overlapPx : 0, corner_radius: text(shared ? preset.cornerRadius : ZERO),
          lateral_jitter: text(preset.lateralJitter)}, cells};
    }
    checkLayoutPair(layouts, new Set(Array.from({length: count}, (_, k) => `loop-${k + 1}`)), preset.source, count, pyRead);
    return layouts;
  }

  /* strips_layouts(count, preset): {portrait, landscape} for `count` strips. `preset` is
   * "strips" or a simvltanea.layout-preset/1 object; `source` names its file in errors. */
  function stripsLayouts(count, preset = 'strips', source = null) {
    const resolved = presetOf(preset, source);
    return expandPreset(resolved, presetCount(resolved, count));
  }
  // strips_slice(count, preset): the state-wide slice, width = height = s(N), zoom 1/s.
  function stripsSlice(count, preset = 'strips', source = null) {
    const resolved = presetOf(preset, source);
    const size = text(presetSlice(resolved, presetCount(resolved, count)));
    const value = {enabled: true, width: size, height: size};
    validateSlice(value);
    return value;
  }

  /* load_layout_file for text the caller has read: a preset has every count expanded and
   * validated, a pair is validated for its count. `source` (a file name) prefixes every error. */
  function loadLayoutFile(source, name = null) {
    const where = {source: name};
    const data = parseLayoutJson(source, name);
    check(isObject(data), where, 'wrong-type', 'layout file must be a JSON object');
    const kind = has(data, 'format') ? data.format : null;
    if (kind === PRESET_FORMAT) {
      checkedPreset(data, name);
    } else if (kind === PAIR_FORMAT) {
      keysOf(data, PAIR_FIELDS, PAIR_FIELDS, 'pair', where);
      const count = integerIn(data.count, 1, PAIR_MAX_COUNT, 'count', where, 'count-range');
      checkLayoutPair({portrait: data.portrait, landscape: data.landscape}, null, name, count, pyRead);
    } else {
      fail(where, 'format', `format must be ${pyRepr(PRESET_FORMAT)} or ${pyRepr(PAIR_FORMAT)}, got ${pyRepr(kind)}`);
    }
    return data;
  }
  // The same from bytes: strict UTF-8 (a BOM is kept, so JSON refuses it as Python does).
  function loadLayoutBytes(bytes, name = null) {
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    check(view.byteLength <= MAX_LAYOUT_FILE_BYTES, {source: name}, 'json',
      `layout file is larger than ${MAX_LAYOUT_FILE_BYTES / 1024 / 1024} MiB`);
    let source;
    try { source = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(view); } catch (error) {
      fail({source: name}, 'json', 'cannot read layout file: it is not UTF-8 text');
    }
    return loadLayoutFile(source, name);
  }

  // What a loaded layout file offers: its kind, name and loop counts.
  function describeLayoutFile(data, name = null) {
    if (isObject(data) && data.format === PAIR_FORMAT) {
      return {kind: 'pair', name: data.portrait.name, counts: [Number(data.count)]};
    }
    const preset = presetOf(data, name);
    return {kind: 'preset', name: preset.name,
      counts: Array.from({length: preset.high - preset.low + 1}, (_, i) => preset.low + i)};
  }
  /* The layouts (and the preset's slice) a loaded layout file gives `count` loops, with every
   * rational in canonical "n/d" form so the state compiles under the strict wire rules. */
  function layoutFromFile(data, count, name = null) {
    if (isObject(data) && data.format === PAIR_FORMAT) {
      const where = {source: name};
      check(Number(data.count) === count, where, 'count-range',
        `this layout pair places ${data.count} loops, not ${count} (no filler, no duplication)`);
      const canonical = (value, label) => text(pyRead(value, label, where));
      const layouts = {};
      for (const orientation of ORIENTATIONS) {
        const layout = structuredClone(data[orientation]);
        for (const cell of layout.cells) {
          cell.rect = cell.rect.map(value => canonical(value, 'rect'));
          cell.focal = cell.focal.map(value => canonical(value, 'focal'));
          if (has(cell, 'lateral_offset')) cell.lateral_offset = canonical(cell.lateral_offset, 'lateral_offset');
        }
        if (has(layout, 'presentation')) {
          for (const key of ['corner_radius', 'lateral_jitter']) {
            layout.presentation[key] = canonical(layout.presentation[key], `presentation.${key}`);
          }
        }
        layouts[orientation] = layout;
      }
      return {layouts, slice: null};
    }
    return {layouts: stripsLayouts(count, data, name), slice: stripsSlice(count, data, name)};
  }

  // ---- Layout bundles: the legacy authored map and simvltanea.layout-bundle/2 ----

  function bundleCounts(counts, label) {
    need(isObject(counts), `${label}: counts must be an object`);
    const result = [];
    for (const key of Object.keys(counts)) {
      need(/^[1-9][0-9]*$/.test(key), `${label}: count ${JSON.stringify(key)} is not a loop count`);
      const count = Number(key);
      refuse(count < MIN_LOOPS || count > MAX_LOOPS,
        `${label}: count ${count}; the browser compiler covers N=${MIN_LOOPS}..${MAX_LOOPS}`);
      const entry = counts[key];
      fields(entry, ['portrait', 'landscape', 'slice', 'adjacency'], ['portrait', 'landscape'], `${label} count ${key}`);
      result.push(count);
    }
    need(result.length > 0, `${label}: no loop counts`);
    return result.sort((a, b) => a - b);
  }
  /* The families a layout bundle offers: {format, default_family, families: {name: {counts,
   * preset}}}. A legacy bundle (count -> pair, no format key) is the authored family. */
  function layoutFamilies(bundle) {
    need(isObject(bundle), 'layout bundle must be an object');
    if (!has(bundle, 'format')) {
      return {format: LEGACY_BUNDLE_FORMAT, default_family: 'authored',
        families: {authored: {counts: bundleCounts(bundle, 'layout bundle'), preset: null}}};
    }
    fields(bundle, ['format', 'default_family', 'families'], ['format', 'default_family', 'families'], 'layout bundle');
    need(bundle.format === BUNDLE_FORMAT, `layout bundle format must be ${BUNDLE_FORMAT}`);
    need(isObject(bundle.families) && Object.keys(bundle.families).length > 0, 'layout bundle: families must be an object');
    const families = {};
    for (const [name, family] of Object.entries(bundle.families)) {
      identifier(name, 'layout bundle family');
      fields(family, ['preset', 'counts'], ['counts'], `layout bundle family ${name}`);
      families[name] = {counts: bundleCounts(family.counts, `layout bundle family ${name}`),
        preset: has(family, 'preset') ? structuredClone(family.preset) : null};
    }
    need(typeof bundle.default_family === 'string' && has(families, bundle.default_family),
      'layout bundle: default_family must name one of its families');
    return {format: BUNDLE_FORMAT, default_family: bundle.default_family, families};
  }
  /* {layouts, slice, adjacency} for `count` loops in `family`. A count the family lacks is
   * refused: it is never filled, duplicated or taken from another family. */
  function layoutEntry(bundle, family, count) {
    const described = layoutFamilies(bundle);
    need(typeof family === 'string' && has(described.families, family),
      `layout bundle has no family ${JSON.stringify(family)}`);
    const counts = described.families[family].counts;
    refuse(!counts.includes(count), `the ${family} family has no layout for ${count} loops; it covers ` +
      `${counts.join(', ')} (no filler, no duplication, never moved to another family)`);
    const entry = described.format === BUNDLE_FORMAT ? bundle.families[family].counts[String(count)] : bundle[String(count)];
    return {layouts: {portrait: structuredClone(entry.portrait), landscape: structuredClone(entry.landscape)},
      slice: has(entry, 'slice') ? structuredClone(entry.slice) : null,
      adjacency: has(entry, 'adjacency') ? structuredClone(entry.adjacency) : null};
  }

  const api = Object.freeze({
    compile: input => compilePlan(buildState(input)),
    compilePlan, buildState, bindLayouts, stagePreview, validateState, canonicalJson, stateDigest, sha256Hex,
    validateLayoutPair, adjacency, parseLayoutJson, loadLayoutFile, loadLayoutBytes, describeLayoutFile,
    layoutFromFile, stripsLayouts, stripsSlice, layoutFamilies, layoutEntry,
    CompilerError, SUPPORTED_LOOP_COUNTS, MIN_LOOPS, MAX_LOOPS, DEFAULT_STRIPS_PRESET,
    PRESET_FORMAT, PAIR_FORMAT, BUNDLE_FORMAT,
  });
  root.SimvltaneaCompiler = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis === 'object' ? globalThis : this);
