/* Persistent Studio audio bus. The final guard bounds rendered sample peaks;
 * this is not a true-peak or lookahead limiter. No audio context is created here.
 */
(function (root) {
  'use strict';
  if (root.SimvltaneaLiveAudio) {
    if (typeof module !== 'undefined' && module.exports) module.exports = root.SimvltaneaLiveAudio;
    return;
  }

  const SAMPLE_CEILING = Math.pow(10, -1 / 20);
  const SOFT_KNEE = Math.pow(10, -3 / 20);
  const buses = new WeakMap();
  const unit = value => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;

  function normalizeGains(weights, ceiling = 0.85) {
    const gains = new Float32Array(weights.length);
    let largest = 0;
    for (const weight of weights) {
      if (Number.isFinite(weight) && weight > largest) largest = weight;
    }
    if (!largest) return gains;
    let sum = 0, squares = 0;
    for (let i = 0; i < weights.length; i++) {
      const weight = Number.isFinite(weights[i]) && weights[i] > 0 ? weights[i] / largest : 0;
      gains[i] = weight;
      sum += weight;
      squares += weight * weight;
    }
    // L1 constrains fully coherent voices; L2 alone only balances their power.
    // Scaling by the largest weight first avoids overflow on finite inputs.
    const scalar = Math.min(0.85 / Math.sqrt(squares), unit(ceiling) / sum);
    for (let i = 0; i < gains.length; i++) gains[i] *= scalar;
    return gains;
  }

  function buildSoftClipCurve(samples = 16385) {
    if (!Number.isInteger(samples) || samples < 3 || samples > 65537) {
      throw new RangeError('Soft clip curve needs 3 to 65537 samples');
    }
    const curve = new Float32Array(samples), headroom = SAMPLE_CEILING - SOFT_KNEE;
    for (let i = 0; i < samples; i++) {
      // The Web Audio lookup domain remains [-1, 1]. createMasterBus applies
      // a 0.5 input gain to compensate this physical [-2, 2] transfer range.
      const x = (2 * i / (samples - 1) - 1) * 2, absolute = Math.abs(x);
      curve[i] = absolute <= SOFT_KNEE ? x : Math.sign(x) *
        (SOFT_KNEE + headroom * Math.tanh((absolute - SOFT_KNEE) / headroom));
    }
    return curve;
  }

  function createMasterBus(context, {volume = 0.7, enabled = false} = {}) {
    if (buses.has(context)) return buses.get(context);
    const input = context.createGain(), masterVolume = context.createGain();
    const compressor = context.createDynamicsCompressor();
    compressor.threshold.value = -12;
    compressor.knee.value = 6;
    compressor.ratio.value = 8;
    compressor.attack.value = 0.003;
    compressor.release.value = 0.15;
    const attenuation = context.createGain(), soft = context.createWaveShaper();
    attenuation.gain.value = 0.5;
    soft.curve = buildSoftClipCurve();
    soft.oversample = '4x';
    const output = context.createWaveShaper(), guard = new Float32Array(16385);
    for (let i = 0; i < guard.length; i++) {
      const x = 2 * i / (guard.length - 1) - 1;
      guard[i] = Math.max(-SAMPLE_CEILING, Math.min(SAMPLE_CEILING, x));
    }
    output.curve = guard;
    // Oversampling reconstruction can exceed a soft-clip table's extrema.
    // This last, non-oversampled guard catches those rendered-sample peaks.
    output.oversample = 'none';
    masterVolume.gain.value = enabled ? unit(volume) : 0;
    input.connect(masterVolume);
    masterVolume.connect(compressor);
    compressor.connect(attenuation);
    attenuation.connect(soft);
    soft.connect(output);
    output.connect(context.destination);
    let disposed = false;
    const bus = {
      input, volume: masterVolume, output,
      setVolume(value, audible) {
        if (disposed || context.state === 'closed') return;
        const now = context.currentTime, parameter = masterVolume.gain;
        const target = audible ? unit(value) : 0;
        if (typeof parameter.cancelAndHoldAtTime === 'function') {
          parameter.cancelAndHoldAtTime(now);
        } else {
          parameter.cancelScheduledValues(now);
          parameter.setValueAtTime(parameter.value, now);
        }
        parameter.setTargetAtTime(target, now, 0.015);
      },
      dispose() {
        if (disposed) return;
        disposed = true;
        for (const node of [input, masterVolume, compressor, attenuation, soft, output]) node.disconnect();
        buses.delete(context);
      },
    };
    buses.set(context, bus);
    return bus;
  }

  const api = {buildSoftClipCurve, createMasterBus, normalizeGains};
  root.SimvltaneaLiveAudio = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
