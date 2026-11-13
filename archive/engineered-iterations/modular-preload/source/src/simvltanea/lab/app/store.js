// Observable configuration store (values + modulation + bypass + locks). No DOM.
import { defaultConfig, cloneConfig, sanitizeConfig, coerce, byId, defaults, paramsOf, sanitizeMod, MOD_DEFAULT, effectiveValues } from './params.js';

export class Store {
  constructor(cfg = defaultConfig()) {
    this.cfg = sanitizeConfig(cfg);
    this.fns = new Set();
  }
  on(fn) { this.fns.add(fn); return () => this.fns.delete(fn); }
  _emit(ev) { for (const f of this.fns) f(ev); }
  get(id) { return this.cfg.values[id]; }
  effective(t = 0) { return effectiveValues(this.cfg, t); }

  set(id, raw) {
    const r = coerce(id, raw);
    if (!r.ok) return false;
    if (JSON.stringify(this.cfg.values[id]) === JSON.stringify(r.value)) return true;
    this.cfg.values[id] = r.value;
    this._emit({ type: 'param', id, module: byId[id].module, value: r.value });
    return true;
  }
  setMany(values, ev = 'config') {
    for (const [id, v] of Object.entries(values)) { const r = coerce(id, v); if (r.ok) this.cfg.values[id] = r.value; }
    this._emit({ type: ev });
  }
  mod(id, patch) {
    if (!byId[id]?.modulatable) return;
    this.cfg.mods[id] = sanitizeMod({ ...(this.cfg.mods[id] || MOD_DEFAULT), ...patch });
    this._emit({ type: 'mod', id, module: byId[id].module });
  }
  bypass(moduleId, on) {
    const s = new Set(this.cfg.bypass);
    on ? s.add(moduleId) : s.delete(moduleId);
    this.cfg.bypass = [...s];
    this._emit({ type: 'bypass', module: moduleId });
  }
  lock(id, on) {
    const s = new Set(this.cfg.locks);
    on ? s.add(id) : s.delete(id);
    this.cfg.locks = [...s];
    this._emit({ type: 'lock', id });
  }
  resetModule(moduleId) {
    const d = defaults();
    for (const p of paramsOf(moduleId)) { this.cfg.values[p.id] = d[p.id]; delete this.cfg.mods[p.id]; }
    this.cfg.bypass = this.cfg.bypass.filter((m) => m !== moduleId);
    this._emit({ type: 'config', module: moduleId });
  }
  resetAll() { this.cfg = defaultConfig(); this._emit({ type: 'config' }); }
  load(cfg) { this.cfg = sanitizeConfig(cfg); this._emit({ type: 'config' }); }
  snapshot() { return cloneConfig(this.cfg); }
}
