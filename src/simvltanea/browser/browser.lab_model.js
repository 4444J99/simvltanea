/* Pure settings and modulation for the Effects Lab. No browser or audio clock. */
(function (root) {
  'use strict';
  const nodeCompiler = typeof module === 'object' && module.exports ? require('./browser.compiler.js') : null;
  const MAX_CLIPS = 8;
  const DEFAULT_LAYOUT = Object.freeze({family: 'strips', count: 3, orientation: 'landscape', framing: 'cover'});
  const BLENDS = Object.freeze(['normal', 'screen', 'multiply', 'overlay', 'soft-light',
    'difference', 'exclusion', 'color-dodge', 'lighten', 'darken']);
  const FILTER_MODES = Object.freeze(['presence', 'presence-reverse', 'lowpass', 'highpass', 'bandpass', 'off']);
  const DEFAULTS = Object.freeze({panel: 1, blend: 'screen', opacity: .85, brightness: 1, contrast: 1.15,
    saturation: 1.1, hue: 0, blur: 0, invert: 0, timelineStart: 0, attack: 2, videoLife: 24, audioLife: 36,
    audioGain: .65, filterMode: 'presence', cutoff: 1800, resonance: .8, combMix: .45,
    combFeedback: .35, combLow: 100, combHigh: 2400, combPeriod: 8,
    videoRate: 1, audioRate: 1, videoWander: .12, audioWander: .2,
    preservePitch: false, hold: false, videoEnabled: true, audioEnabled: true});
  const RANGES = Object.freeze({opacity: [0, 1], brightness: [0, 2], contrast: [0, 3],
    saturation: [0, 3], hue: [-180, 180], blur: [0, 12], invert: [0, 1],
    timelineStart: [0, 3600], attack: [.01, 60], videoLife: [.25, 600], audioLife: [.25, 900], audioGain: [0, 1],
    cutoff: [40, 16000], resonance: [.1, 8], combMix: [0, 1], combFeedback: [0, .75],
    combLow: [40, 2000], combHigh: [100, 8000], combPeriod: [.5, 30],
    videoRate: [.25, 3], audioRate: [.25, 3], videoWander: [0, .5], audioWander: [0, .5]});
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const unit = v => Number.isFinite(v) ? clamp(v, 0, 1) : 0;
  const geometric = (lo, hi, amount) => lo * Math.pow(hi / lo, unit(amount));

  function normalizeSettings(partial = {}, base = DEFAULTS) {
    const patch = partial && typeof partial === 'object' ? partial : {};
    const prior = base && typeof base === 'object' ? base : DEFAULTS;
    const result = {};
    for (const [name, fallback] of Object.entries(DEFAULTS)) {
      let value = Object.prototype.hasOwnProperty.call(patch, name) ? patch[name] : prior[name];
      if (name === 'panel') {
        if (!Number.isFinite(value)) value = Number.isFinite(prior[name]) ? prior[name] : fallback;
        result[name] = clamp(Math.round(value), 1, 12);
      } else if (RANGES[name]) {
        if (!Number.isFinite(value)) value = Number.isFinite(prior[name]) ? prior[name] : fallback;
        result[name] = clamp(value, ...RANGES[name]);
      } else if (typeof fallback === 'boolean') {
        result[name] = typeof value === 'boolean' ? value : (typeof prior[name] === 'boolean' ? prior[name] : fallback);
      } else {
        const choices = name === 'blend' ? BLENDS : FILTER_MODES;
        result[name] = choices.includes(value) ? value : (choices.includes(prior[name]) ? prior[name] : fallback);
      }
    }
    result.combHigh = Math.max(result.combLow, result.combHigh);
    return result;
  }

  function normalizeLayout(partial = {}, base = DEFAULT_LAYOUT) {
    const patch = partial && typeof partial === 'object' ? partial : {};
    const prior = base && typeof base === 'object' ? base : DEFAULT_LAYOUT;
    const choice = (key, choices) => choices.includes(patch[key]) ? patch[key] : choices.includes(prior[key]) ? prior[key] : DEFAULT_LAYOUT[key];
    const family = choice('family', ['strips', 'authored']);
    const count = Number.isFinite(patch.count) ? patch.count : Number.isFinite(prior.count) ? prior.count : DEFAULT_LAYOUT.count;
    let framing = choice('framing', ['cover', 'contain', 'slice']);
    if (family === 'authored' && framing === 'slice') framing = 'cover';
    return {family, count: clamp(Math.round(count), family === 'authored' ? 2 : 1, family === 'authored' ? 7 : 12),
      orientation: choice('orientation', ['landscape', 'portrait']), framing};
  }

  // Layout geometry stays owned by the existing compiler and authored bundle.
  // The lab changes bindings from loop IDs to stable panel numbers, not rectangles.
  function panelCells(layout = DEFAULT_LAYOUT, bundle = root.SimvltaneaLabLayoutBundle) {
    const compiler = nodeCompiler || root.SimvltaneaCompiler;
    if (!compiler) throw new Error('The canonical layout compiler has not loaded.');
    const settings = normalizeLayout(layout);
    const entry = settings.family === 'strips'
      ? {layouts: compiler.stripsLayouts(settings.count), slice: compiler.stripsSlice(settings.count)}
      : compiler.layoutEntry(bundle, 'authored', settings.count);
    const number = value => { const [n, d = 1] = String(value).split('/').map(Number); return n / d; };
    return entry.layouts[settings.orientation].cells.map(cell => {
      const index = Number(cell.loop.slice('loop-'.length));
      const focal = cell.focal.map(number);
      const size = settings.framing === 'slice' ? [number(entry.slice.width), number(entry.slice.height)] : null;
      return {number: index, id: `panel-${index}`, rect: cell.rect.map(number), focal,
        fit: settings.framing === 'contain' ? 'contain' : 'cover',
        slice: size ? [(1 - size[0]) * focal[0], (1 - size[1]) * focal[1], ...size] : null};
    });
  }

  function envelope(age, life, attack) {
    if (!Number.isFinite(age) || !Number.isFinite(life) || life <= 0 || age <= 0 || age >= life) return 0;
    const rise = Math.min(life / 2, Number.isFinite(attack) && attack > 0 ? attack : DEFAULTS.attack);
    // Work in normalized time so tiny positive lifetimes cannot underflow a divisor.
    const progress = age / life, peak = Math.min(.5, rise / life);
    return unit(progress <= peak ? progress / peak : (1 - progress) / (1 - peak));
  }

  function phase(age, life, attack) {
    if (!Number.isFinite(age) || age < 0) return 'waiting';
    if (!Number.isFinite(life) || life <= 0 || age >= life) return 'ended';
    const rise = Math.min(life / 2, Number.isFinite(attack) && attack > 0 ? attack : DEFAULTS.attack);
    return age < rise ? 'entering' : 'leaving';
  }

  function combFrequency(time, settings = DEFAULTS, offset = 0) {
    const s = normalizeSettings(settings);
    const t = Number.isFinite(time) ? time : 0, shift = Number.isFinite(offset) ? offset : 0;
    const p = ((t / s.combPeriod + shift) % 1 + 1) % 1;
    const triangle = p <= .5 ? p * 2 : (1 - p) * 2;
    return geometric(s.combLow, s.combHigh, triangle);
  }

  function filterTargets(presence, stage, settings = DEFAULTS, sampleRate = 48000) {
    const s = normalizeSettings(settings), p = unit(presence);
    const rate = Number.isFinite(sampleRate) && sampleRate > 0 ? sampleRate : 48000;
    const ceiling = Math.min(16000, rate * .45), floor = Math.min(25, ceiling);
    const low = Math.min(420, ceiling), thin = Math.min(6000, ceiling);
    const target = {lowpassHz: ceiling, highpassHz: floor,
      bandpassHz: Math.min(s.cutoff, ceiling), bandpassQ: s.resonance,
      lowpassEnabled: false, highpassEnabled: false, bandpassEnabled: false};
    const entering = stage === 'entering' || stage === 'waiting';
    if (s.filterMode === 'presence' || s.filterMode === 'presence-reverse') {
      const lowPass = s.filterMode === 'presence' ? entering : !entering;
      if (lowPass) {
        target.lowpassHz = geometric(low, ceiling, p);
        target.lowpassEnabled = true;
      } else {
        target.highpassHz = geometric(floor, thin, 1 - p);
        target.highpassEnabled = true;
      }
    } else if (s.filterMode === 'lowpass') {
      target.lowpassHz = Math.min(s.cutoff, ceiling);
      target.lowpassEnabled = true;
    } else if (s.filterMode === 'highpass') {
      target.highpassHz = Math.min(s.cutoff, ceiling);
      target.highpassEnabled = true;
    } else if (s.filterMode === 'bandpass') {
      target.bandpassEnabled = true;
    }
    return target;
  }

  function nextRate(current, wander, random = Math.random) {
    const rate = Number.isFinite(current) ? clamp(current, .25, 3) : 1;
    const amount = Number.isFinite(wander) ? clamp(wander, 0, .5) : 0;
    if (!amount) return rate;
    const draw = random(), r = Number.isFinite(draw) ? unit(draw) : .5;
    return clamp(rate * (1 + (2 * r - 1) * amount), .25, 3);
  }

  // Repeat-indexed draws make an arrangement seek recover its existing rate
  // history. The first repeat is index 1; audio and picture use different seeds.
  function repeatUnit(seed, loopIndex) {
    let value = (Number.isFinite(seed) ? seed : 1) >>> 0;
    const index = Number.isFinite(loopIndex) ? Math.max(0, Math.floor(loopIndex)) : 0;
    value ^= Math.imul(index >>> 0, 0x9e3779b9);
    value = Math.imul(value ^ (value >>> 16), 0x7feb352d);
    value = Math.imul(value ^ (value >>> 15), 0x846ca68b);
    return ((value ^ (value >>> 16)) >>> 0) / 4294967296;
  }

  function positionAt(age, duration, initialRate = 1, wander = 0, seed = 1) {
    let rate = Number.isFinite(initialRate) ? clamp(initialRate, .25, 3) : 1;
    const empty = {position: 0, loops: 0, rate};
    if (!Number.isFinite(age) || age <= 0 || !Number.isFinite(duration) || duration <= 0) return empty;
    const amount = Number.isFinite(wander) ? clamp(wander, 0, .5) : 0;
    if (!amount) {
      const elapsed = age * rate;
      const loops = Math.floor((elapsed + 1e-10) / duration);
      if (!Number.isSafeInteger(loops)) throw new RangeError('This region exceeds the supported repeat count.');
      return {position: Math.max(0, Math.min(duration, elapsed - loops * duration)), loops, rate};
    }
    let remaining = age, loops = 0;
    while (remaining + 1e-10 >= duration / rate) {
      remaining = Math.max(0, remaining - duration / rate);
      loops++;
      if (loops > 1000000) throw new RangeError('This region exceeds the supported repeat count.');
      rate = nextRate(rate, amount, () => repeatUnit(seed, loops));
    }
    return {position: Math.max(0, Math.min(duration, remaining * rate)), loops, rate};
  }

  const preset = (label, description, settings) => Object.freeze({label, description,
    settings: Object.freeze(normalizeSettings(settings))});
  const PRESETS = Object.freeze({
    drift: preset('Soft drift', 'Transparent pictures, slow comb motion, gently separating loops.', {}),
    interference: preset('Interference', 'Difference layers and a more resonant, faster comb sweep.',
      {blend: 'difference', contrast: 1.6, saturation: 1.5, combMix: .75, combFeedback: .6,
        combPeriod: 3.5, combLow: 120, combHigh: 3600, videoWander: .25, audioWander: .4}),
    afterimage: preset('Afterimage', 'The picture leaves early; its sound remains in the composition.',
      {blend: 'screen', opacity: .72, blur: 1.2, videoLife: 12, audioLife: 48,
        attack: 3, combPeriod: 14, audioRate: .7, videoRate: 1.2, audioWander: .15}),
    clean: preset('Clean layers', 'A steady reference with no spectral filtering or rate changes.',
      {blend: 'normal', opacity: 1, contrast: 1, saturation: 1, combMix: 0,
        filterMode: 'off', videoWander: 0, audioWander: 0, hold: true})
  });

  const api = {MAX_CLIPS, BLENDS, FILTER_MODES, DEFAULTS, DEFAULT_LAYOUT, RANGES, PRESETS,
    normalizeSettings, normalizeLayout, panelCells, envelope, phase, combFrequency, filterTargets, nextRate,
    repeatUnit, positionAt};
  root.SimvltaneaLabModel = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis === 'object' ? globalThis : this);
