/* A clip's shared audible/visible rise and fall. Pure targets, no playback clock.
 * The quiet tail persists until a decoded successor can complete the handoff.
 */
(function (root) {
  'use strict';
  const ATTACK_SECONDS = 1.2, TAIL = .12;
  const unit = value => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;

  function presenceEnvelope(age, lifetime) {
    if (!Number.isFinite(age) || age <= 0) return 0;
    const duration = Number.isFinite(lifetime) && lifetime > 0 ? lifetime : ATTACK_SECONDS * 2;
    if (age >= duration) return TAIL;
    // Normalized phase also handles subnormal positive durations without
    // underflowing a half-duration denominator to zero.
    if (duration <= ATTACK_SECONDS * 2) {
      const phase = age / duration;
      return phase <= .5 ? 2 * phase : 1 - (1 - TAIL) * (2 * phase - 1);
    }
    if (age <= ATTACK_SECONDS) return age / ATTACK_SECONDS;
    return 1 - (1 - TAIL) * ((age - ATTACK_SECONDS) / (duration - ATTACK_SECONDS));
  }

  function filterTargets(presence, sampleRate = 48000) {
    const p = unit(presence);
    const rate = Number.isFinite(sampleRate) && sampleRate > 0 ? sampleRate : 48000;
    const high = Math.min(16000, rate * .45), low = Math.min(420, high);
    return {gain: p, cutoffHz: high === low ? high : low * Math.pow(high / low, p),
      brightness: .55 + .45 * p, saturation: .3 + .7 * p, blurPx: 2 * (1 - p)};
  }

  const api = {ATTACK_SECONDS, presenceEnvelope, filterTargets};
  root.SimvltaneaPresence = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis === 'object' ? globalThis : this);
