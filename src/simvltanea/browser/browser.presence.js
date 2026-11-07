/* A clip's shared audible/visible rise and fall. Pure targets, no playback clock.
 * The quiet tail persists until a decoded successor can complete the handoff.
 */
(function (root) {
  'use strict';
  const ATTACK_SECONDS = 1.2, TAIL = .12;
  const unit = value => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  const DEFAULT_SETTINGS = Object.freeze({attackSeconds: ATTACK_SECONDS, curve: 'linear', tail: TAIL,
    gainDepth: 1, lowpassDepth: 1, brightnessDepth: 1, saturationDepth: 1, blurPx: 2});
  const normalized = new WeakSet([DEFAULT_SETTINGS]);
  const bounds = Object.freeze({attackSeconds: [.1, 5], tail: [.05, .5], gainDepth: [0, 1],
    lowpassDepth: [0, 1], brightnessDepth: [0, 1], saturationDepth: [0, 1], blurPx: [0, 2]});

  function normalizeSettings(input = DEFAULT_SETTINGS) {
    if (normalized.has(input)) return input;
    if (!input || typeof input !== 'object' || Array.isArray(input)) return DEFAULT_SETTINGS;
    const settings = {...DEFAULT_SETTINGS};
    for (const [key, [low, high]] of Object.entries(bounds)) {
      if (Number.isFinite(input[key])) settings[key] = Math.max(low, Math.min(high, input[key]));
    }
    settings.curve = input.curve === 'smooth' ? 'smooth' : 'linear';
    Object.freeze(settings); normalized.add(settings); return settings;
  }
  const shape = (phase, settings) => settings.curve === 'smooth' ? phase * phase * (3 - 2 * phase) : phase;

  function entranceEnvelope(age, settings = DEFAULT_SETTINGS) {
    if (!Number.isFinite(age) || age <= 0) return 0;
    settings = normalizeSettings(settings);
    return shape(Math.min(1, age / settings.attackSeconds), settings);
  }

  function presenceEnvelope(age, lifetime, settings = DEFAULT_SETTINGS) {
    if (!Number.isFinite(age) || age <= 0) return 0;
    settings = normalizeSettings(settings);
    const attack = settings.attackSeconds, tail = settings.tail;
    const duration = Number.isFinite(lifetime) && lifetime > 0 ? lifetime : ATTACK_SECONDS * 2;
    if (age >= duration) return tail;
    // Normalized phase also handles subnormal positive durations without
    // underflowing a half-duration denominator to zero.
    if (duration <= attack * 2) {
      const phase = age / duration;
      return phase <= .5 ? shape(2 * phase, settings) : 1 - (1 - tail) * shape(2 * phase - 1, settings);
    }
    if (age <= attack) return entranceEnvelope(age, settings);
    return 1 - (1 - tail) * shape((age - attack) / (duration - attack), settings);
  }

  function filterTargets(presence, sampleRate = 48000, settings = DEFAULT_SETTINGS) {
    settings = normalizeSettings(settings);
    const p = unit(presence);
    const rate = Number.isFinite(sampleRate) && sampleRate > 0 ? sampleRate : 48000;
    const high = Math.min(16000, rate * .45), low = Math.min(420, high);
    const absent = 1 - p;
    return {gain: 1 - settings.gainDepth * absent,
      cutoffHz: high === low ? high : high * Math.pow(low / high, settings.lowpassDepth * absent),
      brightness: 1 - .45 * settings.brightnessDepth * absent,
      saturation: 1 - .7 * settings.saturationDepth * absent, blurPx: settings.blurPx * absent};
  }

  const api = {ATTACK_SECONDS, DEFAULT_SETTINGS, normalizeSettings, entranceEnvelope, presenceEnvelope, filterTargets};
  root.SimvltaneaPresence = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis === 'object' ? globalThis : this);
