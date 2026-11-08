// Pure, seeded, deterministic engine: clip normalisation, pool filtering, ordering, affinity,
// path strategies and the panel scheduler. No DOM, no clocks: time is always passed in.

import { parseAudioInfo, speechVerdict } from './speech.js';

// ---- RNG / hashing -------------------------------------------------------------------------
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function rng() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b); h ^= h >>> 13;
  return h >>> 0;
}
const mix = (a, b) => {
  let h = (a ^ Math.imul(b | 0, 0x9e3779b1)) >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b); h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  return ((h ^ (h >>> 16)) >>> 0);
};
const floorMod = (a, m) => ((a % m) + m) % m;

// ---- clip normalisation (robust against wrong types / missing fields) ----------------------
const ORD = {
  motion_level: { still: 0, subtle: 1, moderate: 2, intense: 3 },
  shot: { close_up: 0, medium: 1, wide: 2 },
  time_of_day: { night: 0, artificial_light: 1, dusk: 2, golden_hour: 3, day: 4 },
  people: { '0': 0, '1': 1, '2-3': 2, '4+': 3 },
};
const ENV_POLARITY = { nature: 0, domestic: 0.55, studio: 0.6, workplace: 0.8, event: 0.85, transit: 0.9, urban: 1 };
const ENV_ALIAS = { city: 'urban' };
const str = (v) => (typeof v === 'string' ? v.trim().toLowerCase() : '');
const finite = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : NaN);
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

// 'yes' | 'no' | 'unknown' (absent) | 'bad' (present but unusable)
export function tri(v) {
  if (v === undefined || v === null) return 'unknown';
  if (v === true || v === 1) return 'yes';
  if (v === false || v === 0) return 'no';
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    if (['true', 'yes', 'y', '1'].includes(s)) return 'yes';
    if (['false', 'no', 'n', '0'].includes(s)) return 'no';
  }
  return 'bad';
}

const strList = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === 'string').map(str).filter(Boolean) : []);

const intern = new Map();
const tokenId = (s) => { let id = intern.get(s); if (id === undefined) { id = intern.size; intern.set(s, id); } return id; };
const idSet = (list) => Int32Array.from(new Set(list.map(tokenId))).sort();

export function normalizeClip(raw, index = 0) {
  if (!isObj(raw)) return null;
  if (typeof raw.id !== 'string' || !raw.id.trim()) return null;
  if (typeof raw.video !== 'string' || !raw.video.trim()) return null;
  const tagsRaw = raw.tags;
  const tagsBad = tagsRaw !== undefined && tagsRaw !== null && !isObj(tagsRaw);
  const tags = isObj(tagsRaw) ? tagsRaw : null;
  const feat = isObj(raw.features) ? raw.features : {};
  const priv = tags ? tags.privacy : undefined;
  const safety = tags ? tags.safety : undefined;

  let safetyState = 'unknown';
  if (tagsBad) safetyState = 'bad';
  else if (tags) {
    if (safety === undefined || safety === null) safetyState = 'unknown';
    else if (!isObj(safety)) safetyState = 'bad';
    else if (safety.verdict === undefined || safety.verdict === null) safetyState = 'unknown';
    else if (typeof safety.verdict !== 'string') safetyState = 'bad';
    else safetyState = str(safety.verdict) === 'clear' ? 'clear' : 'other';
  }

  let sens = -1; // -1 unknown, -2 bad
  if (tagsBad) sens = -2;
  else if (isObj(priv) && priv.sharing_sensitivity !== undefined && priv.sharing_sensitivity !== null) {
    const s = str(priv.sharing_sensitivity);
    sens = s === 'low' ? 0 : s === 'moderate' ? 1 : s === 'high' ? 2 : -2;
  } else if (priv !== undefined && priv !== null && !isObj(priv)) sens = -2;

  const flags = {};
  for (const f of ['readable_text', 'license_plate', 'document_or_screen', 'location_identifiable']) {
    flags[f] = tagsBad ? 'bad' : isObj(priv) ? tri(priv[f]) : priv === undefined || priv === null ? 'unknown' : 'bad';
  }
  const people = tags && isObj(tags.people) ? tags.people : null;
  const minors = tagsBad ? 'bad' : people ? tri(people.minors_apparent) : tags && tags.people !== undefined && tags.people !== null ? 'bad' : 'unknown';

  const subjects = tags ? strList(tags.subjects) : [];
  const keywords = tags ? strList(tags.keywords) : [];
  const mood = tags ? strList(tags.mood) : [];
  const palette = tags ? strList(tags.palette) : [];
  const setting = tags ? str(tags.setting) : '';
  let environment = tags ? str(tags.environment) : '';
  environment = ENV_ALIAS[environment] || environment;
  const tod = tags ? str(tags.time_of_day) : '';
  const camera = tags ? str(tags.camera) : '';
  const shot = tags ? str(tags.shot) : '';
  const mlevel = tags ? str(tags.motion_level) : '';
  const pcount = people ? str(String(people.count ?? '')) : '';
  const unclear = (s) => (s && s !== 'unclear' ? s : '');

  let capturedMs = NaN, dateState = 'unknown';
  if (raw.captured_at !== undefined && raw.captured_at !== null) {
    const t = typeof raw.captured_at === 'string' ? Date.parse(raw.captured_at) : NaN;
    if (Number.isFinite(t)) { capturedMs = t; dateState = 'ok'; } else dateState = 'bad';
  }

  const tokens = new Set([...subjects, ...keywords, ...mood, ...palette, setting, environment, tod, camera, shot, mlevel].filter(Boolean));
  const w = finite(raw.width), h = finite(raw.height);
  let orientation = str(raw.orientation);
  if (orientation !== 'portrait' && orientation !== 'landscape') orientation = w > 0 && h > 0 ? (h > w ? 'portrait' : 'landscape') : '';
  const env = unclear(environment);

  return {
    i: index, id: raw.id, video: raw.video, still: typeof raw.still === 'string' ? raw.still : '',
    duration: finite(raw.duration), width: w, height: h, orientation,
    hasAudio: raw.has_audio === false ? false : true, loudness: finite(raw.loudness_db), audio: parseAudioInfo(raw.audio),
    capturedMs, dateState, year: Number.isFinite(capturedMs) ? new Date(capturedMs).getUTCFullYear() : NaN,
    tagsPresent: !!tags && Object.keys(tags).length > 0, tagsBad,
    safetyState, sens, flags, minors, tokens,
    subjectsIds: idSet(subjects), keywordsIds: idSet(keywords), moodIds: idSet(mood),
    setting: unclear(setting), environment: env, tod: unclear(tod), camera: unclear(camera), shot: unclear(shot),
    ord: {
      motion_level: ORD.motion_level[unclear(mlevel)] ?? NaN, shot: ORD.shot[unclear(shot)] ?? NaN,
      time_of_day: ORD.time_of_day[unclear(tod)] ?? NaN, people: ORD.people[pcount] ?? NaN,
    },
    luma: finite(feat.luma), sat: finite(feat.saturation), hue: finite(feat.hue), motion: finite(feat.motion),
    r: { luma: NaN, sat: NaN, motion: NaN, duration: NaN },
    tie: hashString(raw.id),
    raw,
  };
}

function addRanks(records) {
  for (const [key, getter] of [['luma', (r) => r.luma], ['sat', (r) => r.sat], ['motion', (r) => r.motion], ['duration', (r) => r.duration]]) {
    const known = records.filter((r) => Number.isFinite(getter(r))).sort((a, b) => getter(a) - getter(b));
    const n = known.length;
    known.forEach((r, i) => { r.r[key] = n > 1 ? i / (n - 1) : 0.5; });
  }
}

export function buildRecords(rawClips) {
  const records = [];
  const seen = new Set();
  let rejected = 0;
  for (const raw of Array.isArray(rawClips) ? rawClips : []) {
    const rec = normalizeClip(raw, records.length);
    if (!rec || seen.has(rec.id)) { rejected++; continue; }
    seen.add(rec.id);
    records.push(rec);
  }
  addRanks(records);
  records.rejected = rejected;
  return records;
}

// ---- pool filtering ------------------------------------------------------------------------
const SENS = { low: 0, moderate: 1, high: 2 };

export function clipAllowed(rec, p) {
  if (p['audio.speech_policy'] === 'exclude' && speechVerdict(rec, 'exclude', false).excluded) return false;
  const policyInclude = p['source.untagged'] !== 'exclude';
  const unknownOk = policyInclude;
  if (!rec.tagsPresent && !rec.tagsBad && !policyInclude) return false;
  if (p['source.safety'] === 'clear') {
    if (rec.safetyState === 'other' || rec.safetyState === 'bad') return false;
    if (rec.safetyState === 'unknown' && !unknownOk) return false;
  }
  const maxS = SENS[p['source.max_sensitivity']] ?? 2;
  if (maxS < 2) {
    if (rec.sens === -2) return false;
    if (rec.sens === -1 && !unknownOk) return false;
    if (rec.sens > maxS) return false;
  }
  for (const f of p['source.exclude_privacy'] || []) {
    const s = rec.flags[f];
    if (s === 'yes' || s === 'bad') return false;
    if (s === 'unknown' && !unknownOk) return false;
  }
  if (p['source.exclude_minors']) {
    if (rec.minors === 'yes' || rec.minors === 'bad') return false;
    if (rec.minors === 'unknown' && !unknownOk) return false;
  }
  const y0 = p['source.year_min'], y1 = p['source.year_max'];
  if (y0 > 1990 || y1 < 2040) {
    if (rec.dateState === 'bad') return false;
    if (rec.dateState === 'unknown') { if (!unknownOk) return false; }
    else if (rec.year < Math.min(y0, y1) || rec.year > Math.max(y0, y1)) return false;
  }
  const inc = p['source.tags_include'] || [], exc = p['source.tags_exclude'] || [];
  for (const t of exc) if (rec.tokens.has(t)) return false;
  if (inc.length && rec.tagsPresent) {
    let hit = false;
    for (const t of inc) if (rec.tokens.has(t)) { hit = true; break; }
    if (!hit) return false;
  } else if (inc.length && !rec.tagsPresent && !unknownOk) return false;
  return true;
}

export function filterPool(records, p) {
  const out = [];
  for (let i = 0; i < records.length; i++) if (clipAllowed(records[i], p)) out.push(i);
  return Int32Array.from(out);
}

// ---- ordering ------------------------------------------------------------------------------
export function axisValue(rec, axis) {
  switch (axis) {
    case 'captured_at': return rec.capturedMs;
    case 'luma': return rec.luma;
    case 'saturation': return rec.sat;
    case 'hue': return rec.hue;
    case 'motion': return rec.motion;
    case 'duration': return rec.duration;
    case 'motion_level': return rec.ord.motion_level;
    case 'shot': return rec.ord.shot;
    case 'time_of_day': return rec.ord.time_of_day;
    case 'people': return rec.ord.people;
    default: return NaN;
  }
}

// Returns Int32Array of record indices, position 0 first. Unknown axis values go last.
export function orderPool(records, pool, axis, direction, seed) {
  const sgn = direction === 'desc' ? -1 : 1;
  const keyed = Array.from(pool, (ri) => {
    const r = records[ri];
    return { ri, v: axis === 'none' ? NaN : axisValue(r, axis), t: mix(r.tie, seed) };
  });
  keyed.sort((a, b) => {
    const ka = Number.isFinite(a.v), kb = Number.isFinite(b.v);
    if (ka !== kb) return ka ? -1 : 1;
    if (ka && a.v !== b.v) return sgn * (a.v - b.v);
    return a.t - b.t || a.ri - b.ri;
  });
  return Int32Array.from(keyed, (k) => k.ri);
}

// ---- affinity ------------------------------------------------------------------------------
export const COMPONENTS = ['subjects', 'keywords', 'scene', 'mood', 'colour', 'tone', 'motion', 'framing'];

function jaccard(a, b) {
  if (!a.length || !b.length) return -1;
  let i = 0, j = 0, inter = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { inter++; i++; j++; } else if (a[i] < b[j]) i++; else j++;
  }
  return inter / (a.length + b.length - inter);
}
const eqKnown = (a, b) => (a && b ? (a === b ? 1 : 0) : -1);
const mean = (xs) => { const k = xs.filter((x) => x >= 0); return k.length ? k.reduce((s, x) => s + x, 0) / k.length : -1; };
const simRank = (a, b) => (Number.isFinite(a) && Number.isFinite(b) ? 1 - Math.abs(a - b) : -1);

// Component similarities in [0,1]; -1 = unknown for either clip.
export function componentSims(a, b, out = new Float64Array(8)) {
  out[0] = jaccard(a.subjectsIds, b.subjectsIds);
  out[1] = jaccard(a.keywordsIds, b.keywordsIds);
  out[2] = mean([eqKnown(a.setting, b.setting), eqKnown(a.environment, b.environment), eqKnown(a.tod, b.tod)]);
  out[3] = jaccard(a.moodIds, b.moodIds);
  out[4] = Number.isFinite(a.hue) && Number.isFinite(b.hue) ? 1 - 2 * Math.min(Math.abs(a.hue - b.hue) % 1, 1 - (Math.abs(a.hue - b.hue) % 1)) : -1;
  out[5] = mean([simRank(a.r.luma, b.r.luma), simRank(a.r.sat, b.r.sat)]);
  out[6] = mean([simRank(a.r.motion, b.r.motion),
    Number.isFinite(a.ord.motion_level) && Number.isFinite(b.ord.motion_level) ? 1 - Math.abs(a.ord.motion_level - b.ord.motion_level) / 3 : -1]);
  out[7] = mean([Number.isFinite(a.ord.shot) && Number.isFinite(b.ord.shot) ? 1 - Math.abs(a.ord.shot - b.ord.shot) / 2 : -1, eqKnown(a.camera, b.camera)]);
  return out;
}

const _tmp = new Float64Array(8);
// Signed affinity in [-1, 1]: weights are signed, unknown components contribute 0.
export function affinity(a, b, weights) {
  componentSims(a, b, _tmp);
  let num = 0, den = 0;
  for (let c = 0; c < 8; c++) {
    den += Math.abs(weights[c]);
    if (_tmp[c] >= 0) num += weights[c] * (2 * _tmp[c] - 1);
  }
  return den > 0 ? num / den : 0;
}

export function weightsFrom(p) {
  return COMPONENTS.map((c) => p['relation.w_' + c] ?? 1);
}

const CONTRAST_KEYS = [
  ['relation.contrast_environment', (r) => (r.environment in ENV_POLARITY ? ENV_POLARITY[r.environment] : NaN)],
  ['relation.contrast_shot', (r) => (Number.isFinite(r.ord.shot) ? r.ord.shot / 2 : NaN)],
  ['relation.contrast_orientation', (r) => (r.orientation === 'portrait' ? 0 : r.orientation === 'landscape' ? 1 : NaN)],
  ['relation.contrast_time', (r) => (Number.isFinite(r.ord.time_of_day) ? r.ord.time_of_day / 4 : NaN)],
  ['relation.contrast_motion', (r) => (Number.isFinite(r.ord.motion_level) ? r.ord.motion_level / 3 : NaN)],
];
export const polarity = Object.fromEntries(CONTRAST_KEYS.map(([k, f]) => [k, f]));

// ---- path strategies (pure) ----------------------------------------------------------------
function endBehaviour(raw, L, wrap, onMeet) {
  // raw >= 0 position along [0, L-1]; returns {pos, stopped}
  if (L <= 1) return { pos: 0, stopped: false };
  if (wrap || onMeet === 'restart') return { pos: floorMod(raw, L), stopped: false };
  if (onMeet === 'bounce') {
    const period = 2 * (L - 1), r = floorMod(raw, period);
    return { pos: r <= L - 1 ? r : period - r, stopped: false };
  }
  return { pos: Math.min(raw, L - 1), stopped: onMeet === 'stop' && raw > L - 1 };
}

function travel(d, D, onMeet) {
  // distance travelled -> distance along [0, D], per end behaviour
  if (D <= 0) return { u: 0, stopped: onMeet === 'stop' && d > 0 };
  if (onMeet === 'restart') return { u: d % (D + 1), stopped: false };
  if (onMeet === 'bounce') { const r = d % (2 * D); return { u: r <= D ? r : 2 * D - r, stopped: false }; }
  return { u: Math.min(d, D), stopped: onMeet === 'stop' && d > D };
}

// Position along the order for panel k at its n-th clip. pos === null means "not determined by
// the path alone" (random, playlist, follow).
export function pathPosition({ shape, k, n, L, N, step = 1, wrap = true, onMeet = 'bounce', groups = 1, delay = 2 }) {
  if (L <= 0) return { pos: null, stopped: false };
  switch (shape) {
    case 'sequential': {
      const start = Math.floor((k * L) / Math.max(1, N));
      return endBehaviour(start + n * step, L, wrap, onMeet);
    }
    case 'pingpong': {
      const start = Math.floor((k * L) / Math.max(1, N));
      return endBehaviour(start + n * step, L, false, 'bounce');
    }
    case 'round': {
      const m = n - k * delay;
      return { pos: floorMod(m * step, L), stopped: false };
    }
    case 'converge': case 'diverge': {
      const g = Math.max(1, Math.min(groups, L));
      const gi = k % g, slot = Math.floor(k / g), side = slot % 2, rank = Math.floor(slot / 2);
      const a = Math.floor((gi * L) / g), b = Math.floor(((gi + 1) * L) / g) - 1;
      const S = b - a + 1, D = Math.floor((S - 1) / 2);
      const d = (n + rank * delay) * step;
      const { u, stopped } = travel(d, D, onMeet);
      const off = shape === 'converge' ? u : D - u;
      return { pos: side === 0 ? a + off : b - off, stopped };
    }
    case 'follow':
      return k === 0 ? endBehaviour(n * step, L, true, 'restart') : { pos: null, stopped: false, follow: true };
    default:
      return { pos: null, stopped: false };
  }
}

const gcd = (a, b) => (b ? gcd(b, a % b) : a);
export function playlistPosition(c, L, step = 1) {
  if (L <= 0) return 0;
  let s = Math.max(1, step);
  while (gcd(s, L) !== 1) s++;
  return floorMod(c * s, L);
}

// ---- scheduler -----------------------------------------------------------------------------
const SAMPLE = 48;
const poolSig = (p) => JSON.stringify([
  p['source.safety'], p['source.max_sensitivity'], p['source.exclude_privacy'], p['source.exclude_minors'], p['source.untagged'],
  p['source.year_min'], p['source.year_max'], p['source.tags_include'], p['source.tags_exclude'], p['audio.speech_policy']]);
const orderSig = (p) => `${p['order.axis']}|${p['order.direction']}`;

export class Scheduler {
  constructor(records, params, nPanels, seed = 1) {
    this.records = records;
    this.seed = seed >>> 0;
    this.rng = mulberry32(this.seed);
    this.panels = [];
    this.pool = new Int32Array(0);
    this.order = new Int32Array(0);
    this.posOf = new Int32Array(records.length).fill(-1);
    this.lastEnd = new Float64Array(records.length).fill(-Infinity);
    this.shown = new Uint16Array(records.length);
    this.hist = new Int32Array(records.length).fill(-1); // serial of last pick
    this.serial = 0;
    this.playlistPtr = 0;
    this.nextSwap = null;
    this.syncNext = null;
    this.regime = 'STEADY_FLOW';
    this.regimeChangedAt = 0;
    this.lastArrival = -Infinity;
    this.bad = new Set();
    this.sig = {};
    this.P = null;
    this.setParams(params, true);
    this.resize(nPanels);
  }

  // New seed = a fresh, reproducible run: history is forgotten and every panel is picked again.
  reseed(seed) {
    this.seed = seed >>> 0; this.rng = mulberry32(this.seed);
    this.lastEnd.fill(-Infinity); this.shown.fill(0); this.hist.fill(-1); this.serial = 0;
    this.regime = 'STEADY_FLOW'; this.regimeChangedAt = 0; this.lastArrival = -Infinity;
    for (const pn of this.panels) pn.clip = -1;
    this._rebuildOrder();
    this.reset(this.now || 0);
  }

  setParams(p, force = false) {
    const prev = this.P;
    this.P = p;
    this.weights = weightsFrom(p);
    const ps = poolSig(p), os = orderSig(p);
    let poolChanged = false;
    if (force || ps !== this.sig.pool) { this.sig.pool = ps; this._rebuildPool(); poolChanged = true; }
    if (poolChanged || os !== this.sig.order) { this.sig.order = os; this._rebuildOrder(); }
    return prev !== null;
  }

  _rebuildPool() {
    const allowed = filterPool(this.records, this.P);
    this.pool = this.bad.size ? allowed.filter((i) => !this.bad.has(i)) : allowed;
    const inPool = new Uint8Array(this.records.length);
    for (const i of this.pool) inPool[i] = 1;
    this.inPool = inPool;
    for (const pn of this.panels) if (pn.clip >= 0 && !inPool[pn.clip]) pn.due = -Infinity;
  }

  _rebuildOrder() {
    this.order = orderPool(this.records, this.pool, this.P['order.axis'], this.P['order.direction'], this.seed);
    this.posOf.fill(-1);
    for (let i = 0; i < this.order.length; i++) this.posOf[this.order[i]] = i;
  }

  markBad(recIndex) {
    this.bad.add(recIndex);
    this._rebuildPool(); this._rebuildOrder();
    for (const pn of this.panels) if (pn.clip === recIndex) pn.due = -Infinity;
  }

  resize(N) {
    while (this.panels.length < N) this.panels.push({ clip: -1, n: 0, since: 0, due: -Infinity, stopped: false });
    if (this.panels.length > N) {
      for (const pn of this.panels.splice(N)) if (pn.clip >= 0) this.lastEnd[pn.clip] = this.now || 0;
    }
  }

  // Restart every panel's path from step 0 and re-pick everything (staggered a little).
  reset(now, { keepSteps = false } = {}) {
    this.playlistPtr = 0;
    this.panels.forEach((pn, k) => {
      if (!keepSteps) pn.n = 0;
      pn.stopped = false;
      pn.due = pn.clip < 0 ? -Infinity : now + k * 0.05 - 1e-9;
      pn.forced = true;
    });
    this.nextSwap = null; this.syncNext = null;
  }

  onScreen() { return this.panels.map((p) => p.clip); }

  _holdSeconds() {
    let a = this.P['timing.hold_min'], b = this.P['timing.hold_max'];
    if (a > b) [a, b] = [b, a];
    return a + this.rng() * (b - a);
  }
  _quant(h) { const beat = this.P['timing.beat']; return Math.max(beat, Math.ceil(h / beat - 1e-9) * beat); }
  _snapHold(h, rec) {
    const P = this.P;
    if (!P['timing.snap_to_loop']) return h;
    const d = rec?.duration;
    if (!Number.isFinite(d) || d <= 0) return h;
    const lo = Math.max(1, P['timing.life_min'] ?? 10);
    const hi = Math.max(lo, P['timing.life_max'] ?? 24);
    const kMin = Math.max(1, Math.ceil(lo / d));
    const kMax = Math.max(kMin, Math.floor(hi / d));
    let bestK = kMin, bestDiff = Infinity;
    for (let k = kMin; k <= kMax; k++) {
      const diff = Math.abs(k * d - h);
      if (diff < bestDiff) { bestDiff = diff; bestK = k; }
    }
    let out = bestK * d;
    const mult = this._regimeMultiplier();
    out = out * mult;
    // re-snap after multiplier? keep within bounds
    const k2 = Math.min(kMax, Math.max(kMin, Math.round(out / d)));
    return k2 * d;
  }
  _regimeMultiplier() {
    switch (this.regime) {
      case 'SPARSE_BREATH': return 1.5;
      case 'BURST_CHORUS': return 0.7;
      default: return 1.0;
    }
  }
  _updateRegime(now) {
    const P = this.P;
    const mode = P['timing.macro_regime'];
    if (!mode || mode === 'off') { this.regime = 'STEADY_FLOW'; return; }
    const m = String(mode).toLowerCase();
    if (m !== 'markov') {
      if (m.includes('sparse')) this.regime = 'SPARSE_BREATH';
      else if (m.includes('burst')) this.regime = 'BURST_CHORUS';
      else if (m.includes('steady')) this.regime = 'STEADY_FLOW';
      else this.regime = 'STEADY_FLOW';
      return;
    }
    if (now - this.regimeChangedAt < 20) return;
    const r = this.rng();
    if (this.regime === 'STEADY_FLOW') this.regime = r < 0.33 ? 'SPARSE_BREATH' : r < 0.66 ? 'BURST_CHORUS' : 'STEADY_FLOW';
    else if (this.regime === 'SPARSE_BREATH') this.regime = r < 0.5 ? 'STEADY_FLOW' : r < 0.75 ? 'BURST_CHORUS' : 'SPARSE_BREATH';
    else this.regime = r < 0.5 ? 'STEADY_FLOW' : r < 0.75 ? 'SPARSE_BREATH' : 'BURST_CHORUS';
    this.regimeChangedAt = now;
  }

  // Advance time. Returns [{panel, clip(record index), prev}] for panels whose clip changed.
  tick(now) {
    this.now = now;
    this._updateRegime(now);
    const changes = [];
    if (this.pool.length === 0) {
      this.panels.forEach((pn, panel) => {
        const prev = pn.clip;
        if (prev < 0) return;
        this.lastEnd[prev] = now;
        pn.clip = -1;
        pn.due = -Infinity;
        pn.stopped = false;
        changes.push({ panel, clip: -1, prev });
      });
      return changes;
    }
    const P = this.P;
    const sync = P['timing.synchronized'];
    const swapI = P['timing.swap_interval'];
    const dueList = [];
    if (sync || swapI > 0) {
      // initial / forced fill first
      this.panels.forEach((pn, k) => { if (pn.clip < 0 || pn.forced || pn.due === -Infinity) dueList.push(k); });
      if (sync) {
        if (this.syncNext === null) this.syncNext = now + this._quant(this._holdSeconds());
        if (now >= this.syncNext) {
          this.panels.forEach((pn, k) => { if (!pn.stopped && !dueList.includes(k)) dueList.push(k); });
          this.syncNext = now + this._quant(this._holdSeconds());
        }
      } else {
        if (this.nextSwap === null) this.nextSwap = now + swapI;
        if (now >= this.nextSwap) {
          let best = -1, bs = Infinity;
          this.panels.forEach((pn, k) => { if (!pn.stopped && pn.since < bs && !dueList.includes(k)) { bs = pn.since; best = k; } });
          if (best >= 0) dueList.push(best);
          this.nextSwap = now + swapI;
        }
      }
      dueList.sort((a, b) => a - b);
    } else {
      this.panels.forEach((pn, k) => { if (!pn.stopped && now >= pn.due) dueList.push(k); });
      const delta = this.P['timing.delta_min'] || 0;
      if (delta > 0 && dueList.length > 1 && now - this.lastArrival < delta) {
        // inter-arrival guard: defer all but the earliest-due panel
        dueList.length = 0;
      }
    }
    for (const k of dueList) {
      const pn = this.panels[k];
      if (!pn) continue;
      const first = pn.clip < 0;
      const prev = pn.clip;
      const r = this._pick(k, now);
      pn.forced = false;
      if (r.stopped) pn.stopped = true;
      if (r.clip !== prev && r.clip >= 0) {
        if (prev >= 0) this.lastEnd[prev] = now;
        pn.clip = r.clip; pn.since = now;
        this.shown[r.clip] = Math.min(65535, this.shown[r.clip] + 1);
        this.hist[r.clip] = ++this.serial;
        changes.push({ panel: k, clip: r.clip, prev });
      }
      pn.n++;
      if (r.clip >= 0 && changes.length >= 0) { this.lastArrival = now; }
      if (sync || swapI > 0) pn.due = now;
      else {
        let h = this._holdSeconds();
        if (first) {
          const phase = P['timing.stagger'] * ((k * 0.6180339887) % 1);
          h *= 1 - phase;
        }
        if (r.clip >= 0) h = this._snapHold(h, this.records[r.clip]);
        pn.due = now + Math.max(0.05, h);
      }
    }
    return changes;
  }

  _blockedFor(k, ri, now, cooldown, allowDup) {
    if (!allowDup) for (let j = 0; j < this.panels.length; j++) if (j !== k && this.panels[j].clip === ri) return true;
    if (cooldown > 0 && now - this.lastEnd[ri] < cooldown && this.panels[k].clip !== ri) return true;
    return false;
  }

  _target(k) {
    const P = this.P, pn = this.panels[k], L = this.order.length, N = this.panels.length;
    const shape = P['path.shape'];
    if (shape === 'playlist') return { pos: null, playlist: true };
    const r = pathPosition({
      shape, k, n: pn.n, L, N, step: P['path.step'], wrap: P['path.wrap'], onMeet: P['path.on_meet'],
      groups: P['path.groups'], delay: P['path.delay_beats'],
    });
    if (r.follow) {
      const left = this.panels[k - 1].clip;
      const lp = left >= 0 ? this.posOf[left] : -1;
      return lp >= 0 ? { pos: floorMod(lp + P['path.step'], L), stopped: false } : { pos: null, stopped: false };
    }
    return r;
  }

  _pick(k, now) {
    const P = this.P, pn = this.panels[k], L = this.order.length;
    const tgt = this._target(k);
    const shape = P['path.shape'];
    const tagsVoice = shape === 'round' && P['path.voice'] === 'tags' && k > 0 && P['path.delay_beats'] > 0;
    const refClip = tagsVoice && tgt.pos !== null ? this.order[tgt.pos] : -1;
    const cooldown = P['timing.cooldown'];

    const exactStay = tgt.pos !== null && this.order[tgt.pos] === pn.clip;
    const skipSelf = L > 1 && !exactStay;
    const self = pn.clip;
    const okFn = (ri, cd, dup) => ri !== refClip && !(skipSelf && !dup && ri === self) && !this._blockedFor(k, ri, now, cd, dup);
    let ok = this._candidates(k, tgt, tagsVoice, L).filter((ri) => okFn(ri, cooldown, false));
    if (!ok.length) ok = this._expand(k, tgt, L, (ri) => okFn(ri, cooldown, false));
    if (!ok.length) ok = this._expand(k, tgt, L, (ri) => okFn(ri, 0, false));
    if (!ok.length && pn.clip >= 0 && this.inPool[pn.clip]) return { clip: pn.clip, stopped: tgt.stopped }; // nothing free: keep what is on screen rather than duplicate
    if (!ok.length) ok = this._expand(k, tgt, L, (ri) => okFn(ri, 0, true));
    if (!ok.length) return { clip: pn.clip, stopped: tgt.stopped };

    // Exact path with no choice: stay put when the path says stay.
    if (tgt.pos !== null && !tagsVoice && P['path.window'] === 0) {
      const exact = this.order[tgt.pos];
      if (exact === pn.clip) return { clip: pn.clip, stopped: tgt.stopped };
    }
    if (ok.length === 1) return { clip: ok[0], stopped: tgt.stopped };
    const clip = this._choose(k, ok, tgt, refClip, now);
    return { clip, stopped: tgt.stopped };
  }

  _candidates(k, tgt, tagsVoice, L) {
    const P = this.P, order = this.order;
    const out = [];
    if (tgt.playlist) {
      // next unblocked queue entries
      let c = this.playlistPtr, tries = 0;
      while (out.length < 1 && tries < L) {
        const ri = order[playlistPosition(c, L, P['path.step'])];
        c++; tries++;
        if (!this._blockedFor(k, ri, this.now, P['timing.cooldown'], false)) { out.push(ri); break; }
      }
      this.playlistPtr = c;
      return out;
    }
    if (tgt.pos === null) {
      const seen = new Set();
      const want = Math.min(SAMPLE, L);
      let tries = 0;
      while (seen.size < want && tries < want * 4) { seen.add(Math.floor(this.rng() * L)); tries++; }
      for (const p of seen) out.push(order[p]);
      return out;
    }
    const w = P['path.window'];
    const t = tgt.pos;
    const shape = P['path.shape'];
    const cyclic = shape === 'round' || shape === 'follow' || (shape === 'sequential' && P['path.wrap']);
    const clampPos = (p) => (cyclic ? floorMod(p, L) : Math.min(L - 1, Math.max(0, p)));
    if (w === 0) { out.push(order[t]); return out; }
    const span = 2 * w + 1;
    const seen = new Set([clampPos(t)]);
    if (span <= SAMPLE) for (let d = -w; d <= w; d++) seen.add(clampPos(t + d));
    else { let tries = 0; while (seen.size < SAMPLE && tries < SAMPLE * 4) { seen.add(clampPos(t - w + Math.floor(this.rng() * span))); tries++; } }
    for (const p of seen) out.push(order[p]);
    return out;
  }

  // Nearest-eligible search outward from the target (or a random start when random).
  _expand(k, tgt, L, accept) {
    const out = [];
    const t = tgt.pos === null ? Math.floor(this.rng() * L) : tgt.pos;
    for (let d = 0; d < L && out.length < 8; d++) {
      for (const p of d === 0 ? [t] : [t + d, t - d]) {
        const ri = this.order[floorMod(p, L)];
        if (accept(ri)) out.push(ri);
      }
      if (tgt.pos !== null && out.length && this.P['path.window'] === 0) break;
    }
    return out;
  }

  _choose(k, cands, tgt, refClip, now) {
    const P = this.P, recs = this.records;
    const S = P['relation.strength'];
    const T = P['relation.temperature'];
    const adj = P['relation.adjacency'];
    const recencyW = P['timing.recency'], win = P['timing.recency_window'];
    const novW = P['timing.novelty'];
    const w = this.weights;
    const ignore = P['relation.independence'] > 0 && this.rng() < P['relation.independence'];
    const others = [];
    this.panels.forEach((pn, j) => { if (j !== k && pn.clip >= 0) others.push({ rec: recs[pn.clip], wt: (1 - adj) + adj * (Math.abs(j - k) === 1 ? 1 : 0) }); });
    const contrastFns = CONTRAST_KEYS.filter(([id]) => P[id]).map(([, f]) => f);
    const L = this.order.length, wdt = P['path.window'];
    const ref = refClip >= 0 ? recs[refClip] : null;
    const scores = new Float64Array(cands.length);
    for (let c = 0; c < cands.length; c++) {
      const rec = recs[cands[c]];
      let s = 0;
      if (!ignore && others.length) {
        let tw = 0, aff = 0;
        for (const o of others) { if (o.wt > 0) { aff += o.wt * affinity(rec, o.rec, w); tw += o.wt; } }
        if (tw > 0) s += 2 * S * (aff / tw);
        if (contrastFns.length) {
          let cs = 0;
          for (const f of contrastFns) {
            const pa = f(rec);
            if (!Number.isFinite(pa)) continue;
            let tw2 = 0, acc = 0;
            for (const o of others) { const pb = f(o.rec); if (o.wt > 0 && Number.isFinite(pb)) { acc += o.wt * Math.abs(pa - pb); tw2 += o.wt; } }
            if (tw2 > 0) cs += acc / tw2;
          }
          s += 3 * (cs / contrastFns.length) * 1.0;
        }
      }
      if (ref) { s += 4 * affinity(rec, ref, w.map(Math.abs)); }
      if (novW > 0 && this.shown[cands[c]] === 0) s += 1.5 * novW;
      if (recencyW > 0 && win > 0 && this.hist[cands[c]] >= 0) {
        const age = this.serial - this.hist[cands[c]];
        if (age < win) s -= 3 * recencyW * (1 - age / win);
      }
      if (tgt.pos !== null && wdt > 0) {
        const pp = this.posOf[cands[c]];
        let d = Math.abs(pp - tgt.pos); d = Math.min(d, L - d);
        s -= 0.5 * (d / (wdt + 1));
      }
      scores[c] = s;
    }
    if (T <= 1e-3) {
      let b = 0;
      for (let c = 1; c < cands.length; c++) if (scores[c] > scores[b]) b = c;
      return cands[b];
    }
    let mx = -Infinity;
    for (const s of scores) if (s > mx) mx = s;
    let tot = 0;
    const pr = Array.from(scores, (s) => { const e = Math.exp((s - mx) / T); tot += e; return e; });
    let u = this.rng() * tot;
    for (let c = 0; c < cands.length; c++) { u -= pr[c]; if (u <= 0) return cands[c]; }
    return cands[cands.length - 1];
  }
}
