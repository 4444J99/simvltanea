/* Studio's ecological scheduler. Pure state and scalar targets; no DOM, media or audio nodes.
 * Native playback and the live session's preparation lease remain authoritative.
 * A request is only an intention: settle() records whether the session could perform it.
 */
(function (root) {
  'use strict';
  const presence = root.SimvltaneaPresence ||
    (typeof module === 'object' && module.exports ? require('./browser.presence.js') : null);
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const finite = (value, fallback = 0) => Number.isFinite(value) ? value : fallback;
  const REGIMES = Object.freeze({
    STEADY_FLOW: [18, 35], SPARSE_BREATH: [8, 15], BURST_CHORUS: [6, 10],
  });
  const STEP = 1 / 60;

  // Exact solution of x'' + 2ωx' + ω²(x-target) = 0 for a constant target.
  // Unlike an Euler update, this remains stable at 30, 60 and 120 Hz.
  function criticalSpring(position, velocity, target, dt, omega = 4.5, result = [0, 0]) {
    const elapsed = Math.max(0, finite(dt)), error = position - target;
    const a = velocity + omega * error, decay = Math.exp(-omega * elapsed);
    result[0] = target + (error + a * elapsed) * decay;
    result[1] = (velocity - omega * a * elapsed) * decay;
    return result;
  }

  class Engine {
    constructor({seed = 1, maxSlots = 12} = {}) {
      if (!Number.isInteger(maxSlots) || maxSlots < 1 || maxSlots > 64)
        throw new RangeError('maxSlots must be an integer in 1..64');
      this.maxSlots = maxSlots;
      this._seed = Number(seed) >>> 0;
      this._states = new Map();
      this._ordered = new Array(maxSlots);
      this._raw = new Float64Array(maxSlots);
      this._shares = new Float64Array(maxSlots);
      this._targets = new Float64Array(maxSlots);
      this._spring = new Float64Array(2);
      this._time = null;
      this._accumulator = 0;
      this._serial = 0;
      this._nextArrival = 0;
      this._nextRegime = null;
      this._nextDensity = Infinity;
      this._density = 0;
      this._densityCount = -1;
      this.regime = 'STEADY_FLOW';
      this.output = {
        regime: this.regime, desiredActive: 0, count: 0, requests: [],
        weights: new Float64Array(maxSlots), gains: new Float64Array(maxSlots),
        prominence: new Float64Array(maxSlots), space: new Float64Array(maxSlots),
        fatigue: new Float64Array(maxSlots), presence: new Float64Array(maxSlots),
      };
      this.output.space.fill(1);
    }

    _random() {
      let t = this._seed += 0x6D2B79F5;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    }

    _range(low, high) { return low + this._random() * (high - low); }

    _resident(input, index, now, count) {
      const id = String(input.id ?? index), clipKey = String(input.clipKey ?? id);
      let state = this._states.get(id);
      if (!state || state.clipKey !== clipKey) {
        const duration = Math.max(1 / 30, finite(input.duration, 1));
        const age = Math.max(0, finite(input.age));
        const deadlineAge = Math.ceil(this._range(10, 24) / duration) * duration;
        state = {id, clipKey, index, duration, born: now - age, age,
          deadlineAge, presenceDeadlineAge: deadlineAge, presence: 0,
          lastTransition: now, awaiting: null, resting: Boolean(input.resting),
          restUntil: input.resting ? now + this._range(4, 7) : 0,
          fatigue: 0, prominence: 1 / Math.max(1, count), space: 1, velocity: 0};
        this._states.set(id, state);
      }
      state.index = index;
      state.age = Math.max(0, now - state.born);
      const resting = Boolean(input.resting);
      if (resting && !state.resting) state.restUntil = now + this._range(4, 7);
      if (!resting && state.resting) {
        // Waking an old clip gives it one more complete loop. Its age is not falsified.
        state.deadlineAge = (Math.floor(state.age / state.duration) + 1) * state.duration;
        state.lastTransition = now;
      }
      state.resting = resting;
      return state;
    }

    _enterRegime(next, when, count) {
      this.regime = next;
      const bounds = REGIMES[next];
      this._nextRegime = when + this._range(bounds[0], bounds[1]);
      this._densityCount = -1;
      if (next === 'SPARSE_BREATH') this._chooseDensity(when, count, true);
    }

    _chooseDensity(now, count, initial = false) {
      const floor = Math.min(2, count);
      const low = Math.max(floor, Math.floor(count * .5));
      const high = Math.max(low, Math.min(count - 1, Math.ceil(count * .65)));
      const pHigh = high === low ? 0 : clamp((count * .65 - low) / (high - low), 0, 1);
      if (initial || this._densityCount !== count)
        this._density = this._random() < pHigh ? high : low;
      else this._density = this._density === low ? high : low;
      this._densityCount = count;
      // N=4: q(2→3)=.3/s and q(3→2)=.2/s, hence stationary P(3)=.6.
      // This is the target duty cycle. Real readiness, lifetime and rest guards may delay it.
      const rate = high === low ? 0 : .5 * (this._density === low ? pHigh : 1 - pHigh);
      this._nextDensity = rate > 0 ? now - Math.log(1 - this._random()) / rate : Infinity;
    }

    _pacing(now, count) {
      if (this._nextRegime === null) this._enterRegime(this.regime, now, count);
      // The simulation clock freezes while hidden; this loop handles coarse test/caller ticks.
      while (now >= this._nextRegime) {
        const at = this._nextRegime, chance = this._random();
        this._enterRegime(this.regime === 'STEADY_FLOW'
          ? chance < .6 ? 'SPARSE_BREATH' : 'BURST_CHORUS'
          : this.regime === 'SPARSE_BREATH'
            ? chance < .7 ? 'BURST_CHORUS' : 'STEADY_FLOW'
            : chance < .8 ? 'STEADY_FLOW' : 'SPARSE_BREATH', at, count);
      }
      if (this.regime === 'SPARSE_BREATH') {
        if (this._densityCount !== count) this._chooseDensity(now, count, true);
        while (now >= this._nextDensity) this._chooseDensity(this._nextDensity, count);
      }
    }

    _emit(state, type, now) {
      const request = {type, id: state.id, index: state.index, clipKey: state.clipKey,
        token: ++this._serial, plannedAge: state.deadlineAge, duration: state.duration};
      state.awaiting = request.token;
      this.output.requests.push(request);
      const interval = this.regime === 'BURST_CHORUS' ? [.25, .65]
        : this.regime === 'SPARSE_BREATH' ? [2.5, 4.5] : [1.6, 3.2];
      this._nextArrival = now + this._range(interval[0], interval[1]);
    }

    // A rejected/failed candidate keeps the outgoing clip and advances its deadline by a loop.
    // Late completion after a manual edit or clip change is intentionally ignored.
    settle(request, accepted, simTime = this._time) {
      if (!request) return false;
      const state = this._states.get(String(request.id));
      if (!state || state.clipKey !== request.clipKey || state.awaiting !== request.token) return false;
      state.awaiting = null;
      const now = finite(simTime, this._time ?? 0);
      if (accepted) state.lastTransition = now;
      else {
        this._nextArrival = now + 1.4;
        if (request.type === 'replace') state.deadlineAge += state.duration;
      }
      return true;
    }

    _requests(now, residents, options) {
      const count = residents.length;
      const active = residents.reduce((sum, item) => sum + !item.resting, 0);
      const busy = residents.some((item, index) => item.pending || this._ordered[index].awaiting !== null);
      const guard = busy || now < this._nextArrival;
      // Missed retirement seams move by whole loops, not half loops or global-guard seconds.
      for (let index = 0; index < count; index++) {
        const state = this._ordered[index];
        if (!state.resting && !state.awaiting && state.age >= state.deadlineAge &&
            (guard || now - state.lastTransition < 1.4))
          state.deadlineAge += Math.max(1, Math.floor((state.age - state.deadlineAge) / state.duration) + 1) * state.duration;
      }
      if (guard) return;
      if (active < this.output.desiredActive && options.canRest !== false) {
        const wake = this._ordered.slice(0, count).find(state => state.resting && now >= state.restUntil &&
          now - state.lastTransition >= 1.4);
        if (wake) { this._emit(wake, 'wake', now); return; }
      }
      let oldest = null;
      for (let index = 0; index < count; index++) {
        const state = this._ordered[index];
        if (state.resting || residents[index].pending || state.age < 10 || state.age < state.deadlineAge ||
            now - state.lastTransition < 1.4) continue;
        if (!oldest || state.deadlineAge - state.age < oldest.deadlineAge - oldest.age) oldest = state;
      }
      if (!oldest) return;
      // Scarcity outranks density: do not retire into an unavailable replacement pool.
      if (options.canReplace === false) oldest.deadlineAge += oldest.duration;
      else if (active > this.output.desiredActive && options.canRest !== false && !options.manualCount) {
        this._emit(oldest, 'rest', now);
      } else this._emit(oldest, 'replace', now);
    }

    _ecology(residents, elapsed, enabled) {
      const count = residents.length, out = this.output;
      // Fixed interaction tick: fatigue and lateral inhibition do not depend on display refresh.
      this._accumulator += Math.min(.1, elapsed);
      const ticks = Math.floor((this._accumulator + 1e-10) / STEP);
      this._accumulator -= ticks * STEP;
      for (let tick = 0; tick < Math.max(1, ticks); tick++) {
        let total = 0, maximum = 0;
        for (let i = 0; i < count; i++) {
          const state = this._ordered[i], item = residents[i];
          const attack = clamp(state.age / 1.2, .01, 1);
          const remaining = state.deadlineAge - state.age;
          const release = enabled && remaining >= 0 ? clamp(remaining / 1.6, .18, 1) : 1;
          let inhibition = 0;
          for (let j = 0; j < count; j++) if (j !== i && !residents[j].resting) {
            const dx = Number.isFinite(item.x) && Number.isFinite(residents[j].x)
              ? (item.x - residents[j].x) * count : i - j;
            const dy = Number.isFinite(item.y) && Number.isFinite(residents[j].y)
              ? (item.y - residents[j].y) * count : 0;
            inhibition += this._ordered[j].prominence * Math.exp(-(dx * dx + dy * dy) / (2 * 1.35 ** 2));
          }
          this._raw[i] = state.resting ? 0 : (.18 + .82 * clamp(finite(item.energy, .5), 0, 1)) *
            attack * release * (1 - .85 * state.fatigue) / (1 + .65 * inhibition);
          maximum = Math.max(maximum, this._raw[i]);
        }
        for (let i = 0; i < count; i++) {
          const value = this._ordered[i].resting ? 0 : this._raw[i] * Math.exp((this._raw[i] - maximum) / .28);
          this._shares[i] = value;
          total += value;
        }
        for (let i = 0; i < count; i++) {
          const state = this._ordered[i], share = total > 0 ? this._shares[i] / total : 0;
          this._shares[i] = share;
          if (ticks > 0) {
            // Dominance is the L1 share of ecological prominence, never an L2 audio gain.
            state.fatigue = clamp(state.fatigue + (share > .32 ? .14 : -.09) * STEP, 0, 1);
            const tau = share > state.prominence ? 1.8 : 2.6;
            state.prominence += (share - state.prominence) * (1 - Math.exp(-STEP / tau));
          }
        }
      }
      let sum = 0, square = 0;
      for (let i = 0; i < count; i++) {
        const state = this._ordered[i];
        out.weights[i] = !state.resting && residents[i].hasAudio === true ? this._shares[i] : 0;
        sum += out.weights[i]; square += out.weights[i] ** 2;
        out.prominence[i] = state.prominence;
        out.fatigue[i] = state.fatigue;
        const target = clamp(1 + (state.prominence - 1 / Math.max(1, count)) * count * 1.3, .45, 2.35);
        this._targets[i] = target;
        const next = criticalSpring(state.space, state.velocity, target, elapsed, 4.5, this._spring);
        state.space = clamp(next[0], .45, 2.35);
        state.velocity = next[1];
        if (Math.abs(state.velocity) <= .0005 && Math.abs(state.space - target) <= .0005) {
          state.space = target; state.velocity = 0;
        }
        out.space[i] = state.space;
      }
      // alpha_corr=1: the coherent sum, as well as the Euclidean norm, stays <= .85.
      const scale = sum > 0 && square > 0 ? Math.min(.85 / sum, .85 / Math.sqrt(square)) : 0;
      for (let i = 0; i < count; i++) out.gains[i] = out.weights[i] * scale;
      for (let i = count; i < this.maxSlots; i++) {
        out.gains[i] = out.weights[i] = out.prominence[i] = out.fatigue[i] = out.presence[i] = 0;
        out.space[i] = 1;
      }
    }

    step(simTime, dt, residents, options = {}) {
      if (!Number.isFinite(simTime) || simTime < 0 || (this._time !== null && simTime < this._time))
        throw new RangeError('simTime must be finite, nonnegative and monotonic');
      if (!Number.isFinite(dt) || dt < 0) throw new RangeError('dt must be finite and nonnegative');
      if (!Array.isArray(residents) || residents.length > this.maxSlots)
        throw new RangeError('resident count exceeds maxSlots');
      this._time = simTime;
      if (this._effectSettingsInput !== options.effectSettings || !this._effectSettings) {
        this._effectSettingsInput = options.effectSettings;
        this._effectSettings = presence.normalizeSettings(options.effectSettings);
      }
      const count = residents.length, ids = new Set();
      for (let index = 0; index < count; index++) {
        const state = this._resident(residents[index], index, simTime, count);
        if (ids.has(state.id)) throw new Error('resident slot IDs must be unique');
        ids.add(state.id); this._ordered[index] = state;
      }
      for (const id of this._states.keys()) if (!ids.has(id)) this._states.delete(id);
      this.output.requests.length = 0;
      this.output.count = count;
      this._pacing(simTime, count);
      this.output.regime = this.regime;
      this.output.desiredActive = !options.manualCount && this.regime === 'SPARSE_BREATH' ? this._density : count;
      if (options.enabled !== false) this._requests(simTime, residents, options);
      this._ecology(residents, Math.min(.1, dt), options.enabled !== false);
      for (let i = 0; i < count; i++) {
        const state = this._ordered[i];
        // Scheduling retries must not restart the envelope's fall. Keep its
        // initial lifetime separate from the movable retirement deadline.
        state.presence = options.effects === false ? 1 : state.resting ? 0 : options.enabled === false
          ? presence.entranceEnvelope(state.age, this._effectSettings)
          : presence.presenceEnvelope(state.age, state.presenceDeadlineAge, this._effectSettings);
        this.output.presence[i] = state.presence;
      }
      return this.output;
    }

    snapshot() {
      return {regime: this.regime, desiredActive: this.output.desiredActive, simTime: this._time,
        nextRegime: this._nextRegime, nextArrival: this._nextArrival,
        residents: [...this._states.values()].map(state => ({id: state.id, clipKey: state.clipKey,
          duration: state.duration, born: state.born, age: state.age, deadlineAge: state.deadlineAge,
          resting: state.resting, restUntil: state.restUntil, pending: state.awaiting !== null,
          fatigue: state.fatigue, prominence: state.prominence, space: state.space,
          presence: state.presence, presenceDeadlineAge: state.presenceDeadlineAge}))};
    }
  }

  const api = {Engine, criticalSpring, REGIMES};
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SimvltaneaEcosystem = api;
})(typeof globalThis === 'object' ? globalThis : this);
