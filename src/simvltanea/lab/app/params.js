// PARAMETER REGISTRY: single source of truth for every control, default, range and doc string.
// Pure (no DOM) so Node tests and the docs generator can import it.
import { SPEECH_POLICIES } from './speech.js';

export const MODULES = [
  { id: 'source', label: 'SOURCE', blurb: 'Which clips may play at all (privacy and pool filters).' },
  { id: 'order', label: 'ORDER', blurb: 'What clips are ranked by.' },
  { id: 'path', label: 'PATH', blurb: 'How each panel travels along that order.' },
  { id: 'relation', label: 'RELATION', blurb: 'How simultaneous panels relate: attract, ignore, repel.' },
  { id: 'timing', label: 'TIMING', blurb: 'When clips change and how fresh the picks are.' },
  { id: 'layout', label: 'LAYOUT', blurb: 'Edge-to-edge strips: count, direction, split, overlap.' },
  { id: 'zoom', label: 'ZOOM', blurb: 'How hard each strip is cropped in.' },
  { id: 'framing', label: 'FRAMING', blurb: 'Which part of each clip a strip shows: a window derived anew for every appearance.' },
  { id: 'audio', label: 'AUDIO', blurb: 'Every panel plays its own sound, simultaneously.' },
  { id: 'reveal', label: 'REVEAL', blurb: 'What tapping a panel shows.' },
];

export const AXES = ['none', 'captured_at', 'luma', 'saturation', 'hue', 'motion', 'duration', 'motion_level', 'shot', 'time_of_day', 'people'];
export const SHAPES = ['random', 'sequential', 'converge', 'diverge', 'pingpong', 'round', 'playlist', 'follow'];
export const PRIVACY_FLAGS = ['readable_text', 'license_plate', 'document_or_screen', 'location_identifiable'];
export const FRAMING_MODES = ['center', 'random', 'thirds', 'detail', 'blend', 'contrast', 'drift'];
export const PANEL_NUMBERS = Array.from({ length: 16 }, (_, i) => i + 1);

const F = (id, module, label, min, max, step, def, unit, description, extra = {}) =>
  ({ id, module, label, type: 'float', min, max, step, default: def, unit, description, modulatable: true, randomizable: true, ...extra });
const I = (id, module, label, min, max, step, def, unit, description, extra = {}) =>
  ({ id, module, label, type: 'int', min, max, step, default: def, unit, description, modulatable: false, randomizable: true, ...extra });
const E = (id, module, label, options, def, description, extra = {}) =>
  ({ id, module, label, type: 'enum', options, default: def, unit: '', description, modulatable: false, randomizable: true, ...extra });
const B = (id, module, label, def, description, extra = {}) =>
  ({ id, module, label, type: 'bool', default: def, unit: '', description, modulatable: false, randomizable: true, ...extra });
const M = (id, module, label, options, def, description, extra = {}) =>
  ({ id, module, label, type: 'multi', options, default: def, unit: '', description, modulatable: false, randomizable: true, ...extra });
const L = (id, module, label, item, def, description, extra = {}) =>
  ({ id, module, label, type: 'list', item, default: def, unit: '', description, modulatable: false, randomizable: true, ...extra });

const NR = { randomizable: false };

export const PARAMS = [
  // ---- SOURCE ----
  E('source.safety', 'source', 'Safety verdict', ['clear', 'any'], 'clear',
    'clear: only clips whose safety.verdict is "clear" (missing = unknown, see Untagged; anything else is excluded). any: ignore the verdict.', NR),
  E('source.max_sensitivity', 'source', 'Max sharing sensitivity', ['low', 'moderate', 'high'], 'high',
    'Clips whose privacy.sharing_sensitivity is above this level are excluded. high = no limit.', NR),
  M('source.exclude_privacy', 'source', 'Exclude privacy flags', PRIVACY_FLAGS, ['license_plate', 'document_or_screen'],
    'Clips flagged with any ticked privacy flag are excluded. Malformed flag values count as flagged.', NR),
  B('source.exclude_minors', 'source', 'Exclude minors', true,
    'Exclude clips where people.minors_apparent is true (or malformed).', NR),
  E('source.untagged', 'source', 'Untagged policy', ['include', 'exclude'], 'include',
    'What to do with clips that lack the information a filter needs (no tags, no safety verdict, no date...). Present-but-malformed values are always excluded when the filter is active.', NR),
  I('source.year_min', 'source', 'Year from', 1990, 2040, 1, 1990, 'year', 'Earliest capture year allowed.', NR),
  I('source.year_max', 'source', 'Year to', 1990, 2040, 1, 2040, 'year', 'Latest capture year allowed.', NR),
  L('source.tags_include', 'source', 'Tags include', 'string', [],
    'Comma-separated words; a clip must carry at least one (subjects, keywords, mood, palette, setting, environment, time of day, camera, shot, motion level). Empty = no constraint.', NR),
  L('source.tags_exclude', 'source', 'Tags exclude', 'string', [],
    'Comma-separated words; clips carrying any of them are excluded.', NR),
  I('source.seed', 'source', 'Seed', 0, 999999, 1, 0, '', 'Seed for every random decision. 0 = pick a new seed at each page load.', NR),

  // ---- ORDER ----
  E('order.axis', 'order', 'Axis', AXES, 'none', 'What clips are ranked by. none = a seeded shuffle.'),
  E('order.direction', 'order', 'Direction', ['asc', 'desc'], 'asc', 'asc: low to high (oldest first for captured_at). desc: reversed.'),

  // ---- PATH ----
  E('path.shape', 'path', 'Shape', SHAPES, 'random',
    'random: any clip. sequential: each panel walks the order from its own start. converge: two ends walk toward the middle. diverge: from the middle outward. pingpong: back and forth. round: canon, every panel plays the same sequence, each later. playlist: one shared queue dealt to whichever panel changes next. follow: each panel stays beside its left neighbour in the order.'),
  I('path.step', 'path', 'Step', 1, 64, 1, 1, 'positions', 'Positions advanced along the order at each change.'),
  B('path.wrap', 'path', 'Wrap', true, 'Sequential: wrap around at the ends. Off: apply "On meet" at the ends.'),
  E('path.on_meet', 'path', 'On meet / end', ['bounce', 'restart', 'hold', 'stop'], 'bounce',
    'What happens when travellers meet (converge) or reach an end: bounce back, restart, hold the last clip, or stop (freeze the panel).'),
  I('path.groups', 'path', 'Groups', 1, 8, 1, 1, '', 'Converge/diverge: split the order into this many segments, each with its own pair of travellers.'),
  I('path.delay_beats', 'path', 'Delay', 0, 16, 1, 2, 'beats', 'Round: panel k starts k x delay steps later. Converge/diverge: spacing of panels travelling on the same side.'),
  E('path.voice', 'path', 'Voice', ['clips', 'tags'], 'clips',
    'Round: clips = every panel plays the very same clips. tags = later panels play different clips that resemble the leader\'s clip from k x delay steps ago.'),
  I('path.window', 'path', 'Window', 0, 500, 1, 20, 'positions', 'Candidates are drawn from this many positions either side of the path target; relation then chooses among them. 0 = exactly the path.'),

  // ---- RELATION ----
  F('relation.strength', 'relation', 'Strength', -4, 4, 0.05, 0, '', 'Signed pull between simultaneous panels: positive attracts (similar clips together), 0 ignores, negative repels.'),
  F('relation.temperature', 'relation', 'Temperature', 0, 2, 0.01, 0.5, '', 'Randomness of the choice among candidates. 0 = always the best scoring; high = nearly uniform.'),
  F('relation.independence', 'relation', 'Independence', 0, 1, 0.01, 0, '', 'Probability that a panel ignores the others when it picks.'),
  F('relation.adjacency', 'relation', 'Adjacency', 0, 1, 0.01, 0, '', '0: every other panel counts equally. 1: only neighbouring panels count.'),
  F('relation.w_subjects', 'relation', 'Subjects', -1, 1, 0.01, 1, '', 'Signed weight of shared subjects.'),
  F('relation.w_keywords', 'relation', 'Keywords', -1, 1, 0.01, 1, '', 'Signed weight of shared keywords.'),
  F('relation.w_scene', 'relation', 'Scene', -1, 1, 0.01, 1, '', 'Signed weight of matching setting, environment and time of day.'),
  F('relation.w_mood', 'relation', 'Mood', -1, 1, 0.01, 1, '', 'Signed weight of shared mood.'),
  F('relation.w_colour', 'relation', 'Colour', -1, 1, 0.01, 1, '', 'Signed weight of similar hue.'),
  F('relation.w_tone', 'relation', 'Tone', -1, 1, 0.01, 1, '', 'Signed weight of similar brightness and saturation.'),
  F('relation.w_motion', 'relation', 'Motion', -1, 1, 0.01, 1, '', 'Signed weight of similar amount of motion.'),
  F('relation.w_framing', 'relation', 'Framing', -1, 1, 0.01, 1, '', 'Signed weight of similar shot size and camera movement.'),
  B('relation.contrast_environment', 'relation', 'Contrast environment', false, 'Prefer clips whose environment differs from the other panels (nature against urban).'),
  B('relation.contrast_shot', 'relation', 'Contrast shot', false, 'Prefer clips whose shot size differs (near against far).'),
  B('relation.contrast_orientation', 'relation', 'Contrast orientation', false, 'Prefer clips whose orientation differs (portrait against landscape).'),
  B('relation.contrast_time', 'relation', 'Contrast time of day', false, 'Prefer clips whose time of day differs (night against day).'),
  B('relation.contrast_motion', 'relation', 'Contrast motion', false, 'Prefer clips whose motion level differs (still against intense).'),

  // ---- TIMING ----
  F('timing.hold_min', 'timing', 'Hold min', 0.5, 60, 0.1, 4, 's', 'Shortest time a clip stays in a panel. If min > max the two are swapped.'),
  F('timing.hold_max', 'timing', 'Hold max', 0.5, 120, 0.1, 10, 's', 'Longest time a clip stays in a panel.'),
  F('timing.stagger', 'timing', 'Stagger', 0, 1, 0.01, 0.6, '', 'How far apart the panels\' first changes are spread. 0 = all together.'),
  B('timing.synchronized', 'timing', 'Synchronized', false, 'All panels change together on the beat grid.'),
  F('timing.beat', 'timing', 'Beat length', 0.25, 8, 0.05, 2, 's', 'Length of one beat; synchronized holds are rounded up to whole beats.'),
  F('timing.cooldown', 'timing', 'Cooldown', 0, 300, 1, 20, 's', 'A clip cannot return to any panel for this long after it was shown. Relaxed automatically if the pool is too small.'),
  F('timing.recency', 'timing', 'Recency', 0, 1, 0.01, 0.5, '', 'Soft penalty for clips shown recently.'),
  I('timing.recency_window', 'timing', 'Recency window', 0, 500, 1, 50, 'clips', 'How many recent clips the recency penalty remembers.'),
  F('timing.novelty', 'timing', 'Novelty', 0, 1, 0.01, 0.3, '', 'Bonus for clips not shown yet.'),
  F('timing.swap_interval', 'timing', 'Swap interval', 0, 60, 0.1, 0, 's', 'If above 0, a single panel (the one on screen longest) changes every interval instead of independent holds.'),
  F('timing.speed', 'timing', 'Speed', 0.25, 2, 0.01, 1, 'x', 'Playback rate of every video.'),

  // ---- LAYOUT ----
  I('layout.panels', 'layout', 'Panels', 1, 16, 1, 4, '', 'Number of simultaneous panels (N).', { rnd: [1, 10] }),
  E('layout.direction', 'layout', 'Strip direction', ['auto', 'rows', 'columns'], 'auto',
    'auto: strips are stacked along the screen\'s long axis (columns on wide screens, rows on tall ones).'),
  E('layout.split', 'layout', 'Split weights', ['equal', 'random', 'golden', 'custom'], 'equal', 'How the screen is divided among the strips.'),
  L('layout.split_custom', 'layout', 'Custom weights', 'number', [3, 2, 1], 'Comma-separated relative widths, cycled over the panels (used when split = custom).'),
  F('layout.overlap', 'layout', 'Overlap', 0, 40, 1, 3, 'px', 'Neighbouring strips overlap by this many pixels.'),
  F('layout.radius', 'layout', 'Corner radius', 0, 80, 1, 0, 'px', 'Rounded corners (0 keeps the screen perfectly filled).', { rnd: [0, 0] }),
  F('layout.jitter', 'layout', 'Sideways jitter', 0, 80, 1, 0, 'px', 'Strips sway sideways by up to this much; the video is over-scanned so nothing is left empty.'),
  F('layout.jitter_rate', 'layout', 'Jitter rate', 0.02, 2, 0.01, 0.2, 'Hz', 'Speed of the sideways sway.'),

  // ---- ZOOM ----
  F('zoom.z1', 'zoom', 'Z1 (zoom at one panel)', 1, 40, 0.1, 8, 'x', 'zoom(N) = max(floor, Z1 / N^gamma).', { rnd: [2, 16] }),
  F('zoom.gamma', 'zoom', 'Gamma', 0, 2, 0.01, 0.6, '', 'How quickly the zoom relaxes as panels are added.'),
  F('zoom.floor', 'zoom', 'Floor (1 = cover)', 1, 4, 0.01, 1, 'x', 'Minimum zoom. 1 is plain cover: the crop never gets looser than just filling the strip.', { rnd: [1, 1.5] }),
  F('zoom.manual', 'zoom', 'Manual override', 0, 60, 0.1, 0, 'x', 'If above 0, use this zoom for every N instead of the curve.', { rnd: [0, 0] }),
  E('zoom.focal_mode', 'zoom', 'Focal point', ['static', 'drift'], 'static', 'static: each strip looks at a fixed spot of its clip. drift: the spot wanders slowly.'),
  F('zoom.drift_speed', 'zoom', 'Drift speed', 0, 30, 0.1, 3, 'cycles/min', 'Speed of the wandering focal point.'),

  // ---- FRAMING ----
  E('framing.mode', 'framing', 'Mode', FRAMING_MODES, 'blend',
    'center: today\'s behaviour (the zoom module\'s focal point). random: a seeded window per appearance. thirds: snap to rule-of-thirds points. detail: prefer windows with more local colour variance (grid8). blend: choose the window whose edge colours best match the facing edge of the neighbouring panel. contrast: the opposite, maximise the edge difference. drift: a slow seeded pan/zoom path through the window range during the hold (Ken Burns style; still under reduced motion). Modes that need colour data fall back to random for clips without any.'),
  F('framing.spread', 'framing', 'Spread', 0, 1, 0.01, 0.85, '', 'How far the window may move from the centre of the clip. 0 = always centred, 1 = anywhere inside the clip.'),
  F('framing.zoom_jitter', 'framing', 'Zoom jitter', 0, 50, 1, 15, '%', 'Each window\'s zoom varies by up to this many percent either side of the zoom module\'s baseline (never below cover).'),
  I('framing.candidates', 'framing', 'Candidates (K)', 1, 256, 1, 48, '', 'How many candidate windows detail, blend and contrast compare (random modes draw until one is allowed by Memory).'),
  F('framing.temperature', 'framing', 'Temperature', 0, 2, 0.01, 0.2, '', 'Randomness of the pick among candidates. 0 = always the best candidate; higher = more varied; about 2 = nearly uniform.'),
  F('framing.neighbour_influence', 'framing', 'Neighbour influence', 0, 1, 0.01, 0.8, '', 'How much the neighbouring panels\' windows steer blend and contrast. 0 = ignore them.'),
  F('framing.edge_sample', 'framing', 'Edge sample width', 0.01, 0.5, 0.01, 0.1, 'of window', 'Width of the band along a window edge whose colours are compared (fraction of the window size across the edge).'),
  E('framing.match_on', 'framing', 'Match on', ['colour', 'luma', 'hue'], 'colour', 'What blend and contrast compare along facing edges: full colour, brightness only, or hue only (weighted by saturation).'),
  B('framing.vary_per_appearance', 'framing', 'Vary per appearance', true, 'On: every time a clip appears it gets a different window. Off: a clip always gets the same window.'),
  I('framing.memory', 'framing', 'Memory (M)', 1, 32, 1, 6, 'windows', 'A clip must show M different windows before a window repeats (per-clip history). 1 = no restriction. Best effort when the window range holds fewer than M distinct windows.'),
  F('framing.drift_speed', 'framing', 'Drift speed', 0.1, 30, 0.1, 2, 'cycles/min', 'Drift mode: one cycle is a pan/zoom out and back; a leg lasts 30 / speed seconds.'),

  // ---- AUDIO ----
  E('audio.speech_policy', 'audio', 'Speech policy', SPEECH_POLICIES, 'mute',
    'For clips whose audio screen found speech (audio.speech, or the flags number_sequence, email_like, introduces_self, possible_name, long_speech). play: sound as usual. mute: the picture plays, the sound does not (also in the reveal). exclude: such clips are never shown. Never randomized.', NR),
  B('audio.mute_unscreened', 'audio', 'Mute unscreened', true,
    'Mute clips whose audio.screened is not true (including clips with no audio record at all).', NR),
  F('audio.master', 'audio', 'Master', 0, 1.5, 0.01, 0.8, '', 'Master gain.', NR),
  B('audio.pan', 'audio', 'Spatial pan', true, 'Pan each panel by its position on screen (along the strip direction).'),
  F('audio.pan_width', 'audio', 'Pan width', 0, 1, 0.01, 0.8, '', '1 = outermost panels fully left/right.'),
  B('audio.normalize', 'audio', 'Loudness normalise', true, 'Gain each clip toward the target using its loudness_db (unknown loudness stays at unity).'),
  F('audio.norm_target_db', 'audio', 'Normalise target', -60, -6, 0.5, -30, 'dB', 'Target loudness for normalisation. Boost is capped at +20 dB.'),
  F('audio.size_gain', 'audio', 'Size to gain', 0, 1, 0.01, 0.5, '', 'Bigger panels are louder: gain = (panel share / mean share)^amount.'),
  B('audio.auto_trim', 'audio', 'Auto trim', true, 'Scale the master by 1/sqrt(N) so many panels do not clip.'),
  M('audio.muted_panels', 'audio', 'Muted panels', PANEL_NUMBERS, [], 'Panels (1-based) that are silent.', NR),
  M('audio.solo_panels', 'audio', 'Solo panels', PANEL_NUMBERS, [], 'If any panel is soloed only soloed panels sound.', NR),
  F('audio.fade', 'audio', 'Fade length', 0, 3, 0.01, 0.4, 's', 'Cross-fade when a panel changes clip (avoids clicks).'),
  B('audio.limiter', 'audio', 'Limiter', true, 'Compressor/limiter before the output.', NR),
  F('audio.limiter_ceiling', 'audio', 'Limiter ceiling', -24, 0, 0.5, -3, 'dB', 'Threshold of the limiter.', NR),

  // ---- REVEAL ----
  E('reveal.action', 'reveal', 'Tap action', ['still', 'video', 'both'], 'still', 'What tapping a panel shows: the original still, the full-frame video, or the still with the video inset.'),
  B('reveal.show_date', 'reveal', 'Show date', true, 'Show the capture date.'),
  B('reveal.show_tags', 'reveal', 'Show tags', true, 'Show tag chips on the reveal.'),
  B('reveal.show_window', 'reveal', 'Outline window', false, 'Outline, on the full still, the window the panel was showing ("where this panel was looking").'),
  B('reveal.pause_others', 'reveal', 'Pause others', false, 'Pause the other panels while a reveal is open.'),
  E('reveal.animation', 'reveal', 'Animation', ['none', 'zoom', 'fade'], 'zoom', 'zoom: expands from the panel\'s rectangle.'),
  F('reveal.anim_ms', 'reveal', 'Animation time', 0, 1500, 10, 350, 'ms', 'Duration of the reveal animation.'),
];

export const byId = Object.fromEntries(PARAMS.map((p) => [p.id, p]));
export const paramsOf = (moduleId) => PARAMS.filter((p) => p.module === moduleId);

export function defaults() {
  const v = {};
  for (const p of PARAMS) v[p.id] = Array.isArray(p.default) ? p.default.slice() : p.default;
  return v;
}

// ---- value coercion ------------------------------------------------------------------------
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
export const snap = (p, x) => {
  const d = (String(p.step).split('.')[1] || '').length;
  const s = Math.round((x - p.min) / p.step) * p.step + p.min;
  return Number(clamp(s, p.min, p.max).toFixed(Math.max(d, 0)));
};

export function parseList(text, item) {
  const parts = (Array.isArray(text) ? text : String(text).split(/[,;\n]/)).map((s) => String(s).trim()).filter(Boolean);
  return item === 'number' ? parts.map(Number).filter((n) => Number.isFinite(n)) : parts.map((s) => s.toLowerCase());
}

// Returns {ok, value}. Never throws. Out-of-range numbers are clamped, junk is rejected.
export function coerce(id, raw) {
  const p = byId[id];
  if (!p) return { ok: false };
  switch (p.type) {
    case 'float': case 'int': {
      const n = typeof raw === 'string' && raw.trim() !== '' ? Number(raw) : raw;
      if (typeof n !== 'number' || !Number.isFinite(n)) return { ok: false };
      return { ok: true, value: p.type === 'int' ? clamp(Math.round(n), p.min, p.max) : snap(p, n) };
    }
    case 'bool':
      if (typeof raw === 'boolean') return { ok: true, value: raw };
      return { ok: false };
    case 'enum':
      return p.options.includes(raw) ? { ok: true, value: raw } : { ok: false };
    case 'multi': {
      if (!Array.isArray(raw)) return { ok: false };
      const set = new Set(raw.map((x) => (typeof p.options[0] === 'number' ? Number(x) : x)));
      return { ok: true, value: p.options.filter((o) => set.has(o)) };
    }
    case 'list': {
      if (!Array.isArray(raw) && typeof raw !== 'string') return { ok: false };
      return { ok: true, value: parseList(raw, p.item) };
    }
  }
  return { ok: false };
}

export function sanitizeValues(input) {
  const out = defaults();
  const rejected = [];
  if (input && typeof input === 'object') {
    for (const [k, v] of Object.entries(input)) {
      const r = coerce(k, v);
      if (r.ok) out[k] = r.value; else rejected.push(k);
    }
  }
  return { values: out, rejected };
}

// ---- config = values + modulation + bypass + locks ----------------------------------------
export const LFO_SHAPES = ['sine', 'triangle', 'random', 'square'];
export const MOD_DEFAULT = { on: false, shape: 'sine', rate: 0.1, depth: 0.25 };

export function defaultConfig() {
  return { version: 1, values: defaults(), mods: {}, bypass: [], locks: [] };
}

export function cloneConfig(c) {
  return JSON.parse(JSON.stringify(c));
}

export function sanitizeMod(m) {
  const o = { ...MOD_DEFAULT };
  if (m && typeof m === 'object') {
    if (typeof m.on === 'boolean') o.on = m.on;
    if (LFO_SHAPES.includes(m.shape)) o.shape = m.shape;
    if (Number.isFinite(m.rate)) o.rate = clamp(m.rate, 0.01, 5);
    if (Number.isFinite(m.depth)) o.depth = clamp(m.depth, 0, 1);
  }
  return o;
}

export function sanitizeConfig(input) {
  const cfg = defaultConfig();
  if (!input || typeof input !== 'object') return cfg;
  cfg.values = sanitizeValues(input.values).values;
  if (input.mods && typeof input.mods === 'object') {
    for (const [id, m] of Object.entries(input.mods)) if (byId[id]?.modulatable) cfg.mods[id] = sanitizeMod(m);
  }
  if (Array.isArray(input.bypass)) cfg.bypass = input.bypass.filter((m) => MODULES.some((x) => x.id === m));
  if (Array.isArray(input.locks)) cfg.locks = input.locks.filter((id) => byId[id]);
  return cfg;
}

export const toJSON = (cfg) => JSON.stringify(cfg);
export const fromJSON = (text) => sanitizeConfig(JSON.parse(text));

// ---- LFOs (stateless, deterministic) -------------------------------------------------------
function hash01(key, i) {
  let h = 2166136261 ^ i;
  for (let c = 0; c < key.length; c++) { h ^= key.charCodeAt(c); h = Math.imul(h, 16777619); }
  h ^= h >>> 13; h = Math.imul(h, 0x5bd1e995); h ^= h >>> 15;
  return (h >>> 0) / 4294967296;
}

export function lfo(shape, t, rate, key = '') {
  const x = t * rate + hash01(key, 7);
  const ph = x - Math.floor(x);
  switch (shape) {
    case 'triangle': return ph < 0.5 ? ph * 4 - 1 : 3 - ph * 4;
    case 'square': return ph < 0.5 ? 1 : -1;
    case 'random': {
      const i = Math.floor(x), f = x - i, s = f * f * (3 - 2 * f);
      const a = hash01(key, i) * 2 - 1, b = hash01(key, i + 1) * 2 - 1;
      return a + (b - a) * s;
    }
    default: return Math.sin(ph * Math.PI * 2);
  }
}

// Effective values at time t (seconds): bypassed modules use defaults; modulated floats breathe.
export function effectiveValues(cfg, t = 0) {
  const def = defaults();
  const out = {};
  const bypass = new Set(cfg.bypass);
  for (const p of PARAMS) {
    let v = bypass.has(p.module) ? def[p.id] : cfg.values[p.id];
    const m = cfg.mods[p.id];
    if (m && m.on && p.modulatable && !bypass.has(p.module)) {
      v = clamp(v + m.depth * (p.max - p.min) * 0.5 * lfo(m.shape, t, m.rate, p.id), p.min, p.max);
    }
    out[p.id] = v;
  }
  return out;
}

// ---- randomize -----------------------------------------------------------------------------
export function randomizeValues(values, locks, rng) {
  const out = { ...values };
  const locked = new Set(locks);
  for (const p of PARAMS) {
    if (!p.randomizable || locked.has(p.id)) continue;
    switch (p.type) {
      case 'float': case 'int': {
        const [lo, hi] = p.rnd || [p.min, p.max];
        const x = lo + rng() * (hi - lo);
        out[p.id] = coerce(p.id, x).value;
        break;
      }
      case 'bool': out[p.id] = rng() < 0.5; break;
      case 'enum': out[p.id] = p.options[Math.floor(rng() * p.options.length)]; break;
      default: break;
    }
  }
  return out;
}

// ---- share URL hash ------------------------------------------------------------------------
const b64 = {
  enc(str) {
    const bytes = new TextEncoder().encode(str);
    let s = '';
    for (const b of bytes) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  },
  dec(text) {
    const s = atob(text.replace(/-/g, '+').replace(/_/g, '/'));
    return new TextDecoder().decode(Uint8Array.from(s, (c) => c.charCodeAt(0)));
  },
};

export function encodeShare(cfg) {
  const def = defaults();
  const values = {};
  for (const p of PARAMS) if (JSON.stringify(cfg.values[p.id]) !== JSON.stringify(def[p.id])) values[p.id] = cfg.values[p.id];
  const mods = {};
  for (const [id, m] of Object.entries(cfg.mods)) if (m.on) mods[id] = m;
  const payload = { v: 1, values, mods, bypass: cfg.bypass, locks: cfg.locks };
  return 'p=' + b64.enc(JSON.stringify(payload));
}

export function decodeShare(hash) {
  const m = /(?:^#?|&)p=([A-Za-z0-9_-]+)/.exec(hash || '');
  if (!m) return null;
  try {
    const payload = JSON.parse(b64.dec(m[1]));
    return sanitizeConfig({ values: payload.values, mods: payload.mods, bypass: payload.bypass, locks: payload.locks });
  } catch { return null; }
}

// ---- docs ----------------------------------------------------------------------------------
export function rangeText(p) {
  switch (p.type) {
    case 'float': case 'int': return `${p.min} to ${p.max}${p.step ? ` (step ${p.step})` : ''}`;
    case 'enum': return p.options.join(' / ');
    case 'multi': return `subset of ${p.options.join(', ')}`;
    case 'list': return `list of ${p.item}s`;
    default: return 'on / off';
  }
}

export function configReferenceMarkdown() {
  const lines = [];
  for (const m of MODULES) {
    lines.push(`### ${m.label}`, '', m.blurb, '', '| id | label | type | range / options | default | unit | MOD | description |', '|---|---|---|---|---|---|---|---|');
    for (const p of paramsOf(m.id)) {
      const d = Array.isArray(p.default) ? `[${p.default.join(', ')}]` : String(p.default);
      lines.push(`| \`${p.id}\` | ${p.label} | ${p.type} | ${rangeText(p).replace(/\|/g, '/')} | ${d} | ${p.unit || ''} | ${p.modulatable ? 'yes' : ''} | ${p.description.replace(/\|/g, '/')} |`);
    }
    lines.push('');
  }
  return lines.join('\n');
}
