// Presets as DATA. A preset resets the modules it lists in `resets` to their defaults and then
// applies `values`. Plain presets reset ORDER/PATH/RELATION/TIMING; scenes also set layout, zoom and
// framing. No preset or scene touches the speech policy (AUDIO > Speech policy, Mute unscreened): that
// choice is only ever changed by hand (see tests/unit/presets.test.mjs). Every id/value is validated against the registry (see tests/unit).
import { byId, coerce, paramsOf } from './params.js';

const CORE = ['order', 'path', 'relation', 'timing'];
const P = (id, label, description, values, extra = {}) => ({ id, label, description, kind: 'preset', resets: CORE, values, ...extra });
const S = (id, label, description, values, resets) => ({ id, label, description, kind: 'scene', resets: resets || [...CORE, 'layout', 'zoom', 'framing'], values });

const CANON = { 'timing.synchronized': true, 'timing.beat': 2, 'timing.hold_min': 2, 'timing.hold_max': 2, 'timing.cooldown': 0,
  'timing.recency': 0, 'timing.novelty': 0, 'relation.temperature': 0, 'path.window': 0, 'path.shape': 'round' };

export const PRESETS = [
  P('random', 'Random', 'Totally random: any clip anywhere, no relations.', { 'path.shape': 'random' }),
  P('chronological', 'Chronological', 'Every panel walks forward through time from its own starting year.',
    { 'order.axis': 'captured_at', 'path.shape': 'sequential', 'path.window': 3, 'timing.cooldown': 0 }),
  P('reverse_chronological', 'Reverse chronological', 'Every panel walks backward through time.',
    { 'order.axis': 'captured_at', 'order.direction': 'desc', 'path.shape': 'sequential', 'path.window': 3, 'timing.cooldown': 0 }),
  P('oldest_meets_newest', 'Oldest meets newest', 'The oldest and the newest clips converge and meet in the middle, then bounce back.',
    { 'order.axis': 'captured_at', 'path.shape': 'converge', 'path.on_meet': 'bounce', 'path.window': 2, 'timing.cooldown': 0 }),
  P('newest_meets_oldest', 'Newest meets oldest', 'Panel 1 starts on the newest clip; the two ends converge and restart when they meet.',
    { 'order.axis': 'captured_at', 'order.direction': 'desc', 'path.shape': 'converge', 'path.on_meet': 'restart', 'path.window': 2, 'timing.cooldown': 0 }),
  P('round_clips', 'Round (clips)', 'A canon: every panel plays the same chronological sequence, each two beats later.',
    { ...CANON, 'order.axis': 'captured_at', 'path.voice': 'clips', 'path.delay_beats': 2 }),
  P('round_tags', 'Round (tags)', 'A canon of character: later panels play different clips that resemble what the leader played earlier.',
    { ...CANON, 'order.axis': 'captured_at', 'path.voice': 'tags', 'path.delay_beats': 2, 'path.window': 25, 'relation.temperature': 0.2 }),
  P('opposites', 'Opposites', 'Panels repel each other: city against nature, near against far, night against day.',
    { 'relation.strength': -2.5, 'relation.temperature': 0.3, 'relation.contrast_environment': true, 'relation.contrast_shot': true,
      'relation.contrast_time': true, 'timing.cooldown': 30 }),
  P('city_vs_nature', 'City vs nature', 'Neighbouring panels pick environments from opposite ends of urban and nature.',
    { 'relation.contrast_environment': true, 'relation.temperature': 0.25, 'timing.cooldown': 30 }),
  P('near_vs_far', 'Near vs far', 'Close-ups against wide shots.',
    { 'relation.contrast_shot': true, 'relation.temperature': 0.25, 'timing.cooldown': 30 }),
  P('drift', 'Drift', 'Panels drift slowly through the chronology, wandering within a wide window.',
    { 'order.axis': 'captured_at', 'path.shape': 'sequential', 'path.window': 60, 'path.step': 1, 'timing.hold_min': 6, 'timing.hold_max': 14, 'relation.temperature': 1 }),
  P('sticky', 'Sticky', 'Neighbouring panels cling to related clips and hold on for a long time.',
    { 'relation.strength': 2.5, 'relation.adjacency': 1, 'relation.temperature': 0.3, 'timing.hold_min': 8, 'timing.hold_max': 20 }),
  P('magnetic', 'Magnetic (gravity)', 'Related clips attract: every panel is pulled toward what the others show.',
    { 'relation.strength': 3.5, 'relation.temperature': 0.25, 'timing.hold_min': 5, 'timing.hold_max': 12 }),
  P('calm_to_intense', 'Calm to intense', 'Ranked by motion, from still to restless.',
    { 'order.axis': 'motion', 'path.shape': 'sequential', 'path.window': 6, 'timing.cooldown': 0 }),
  P('dark_to_light', 'Dark to light', 'Ranked by brightness, from dark to light.',
    { 'order.axis': 'luma', 'path.shape': 'sequential', 'path.window': 6, 'timing.cooldown': 0 }),
  P('rainbow', 'Rainbow', 'Ranked by hue; the panels spread across the colour wheel.',
    { 'order.axis': 'hue', 'path.shape': 'sequential', 'path.window': 4, 'timing.cooldown': 0 }),

  S('scene_triptych_time', 'Scene: time triptych', 'Three golden-ratio strips; the oldest and newest walk toward each other.',
    { 'order.axis': 'captured_at', 'path.shape': 'converge', 'path.window': 2, 'timing.cooldown': 0, 'layout.panels': 3, 'layout.split': 'golden', 'zoom.z1': 6, 'framing.mode': 'thirds' }),
  S('scene_rainbow_mosaic', 'Scene: rainbow mosaic', 'Twelve thin strips along the colour wheel.',
    { 'order.axis': 'hue', 'path.shape': 'sequential', 'path.window': 4, 'timing.cooldown': 0, 'layout.panels': 12, 'layout.overlap': 0, 'zoom.gamma': 0.5, 'framing.mode': 'blend', 'framing.neighbour_influence': 1 }),
  S('scene_slow_gravity', 'Scene: slow gravity', 'Six panels that cling to related clips while their focus drifts.',
    { 'relation.strength': 2.5, 'relation.adjacency': 1, 'relation.temperature': 0.3, 'timing.hold_min': 8, 'timing.hold_max': 20,
      'layout.panels': 6, 'zoom.focal_mode': 'drift', 'zoom.drift_speed': 4, 'framing.mode': 'drift', 'framing.drift_speed': 3 }),
  S('scene_canon_wall', 'Scene: canon wall', 'Eight panels in a chronological canon with a little sideways sway.',
    { ...CANON, 'order.axis': 'captured_at', 'path.voice': 'clips', 'path.delay_beats': 1, 'layout.panels': 8, 'layout.jitter': 12, 'framing.mode': 'random', 'framing.memory': 8 }),
  S('scene_one_big', 'Scene: one big', 'A single, extremely zoomed-in panel: unrecognisable by design.',
    { 'path.shape': 'random', 'timing.hold_min': 6, 'timing.hold_max': 12, 'layout.panels': 1, 'framing.mode': 'detail', 'framing.temperature': 0.4 }),
  S('scene_contrast_duet', 'Scene: contrast duet', 'Two panels, city against nature.',
    { 'relation.contrast_environment': true, 'relation.temperature': 0.2, 'timing.cooldown': 30, 'layout.panels': 2, 'zoom.z1': 5, 'framing.mode': 'contrast' }),
  S('scene_seamless', 'Scene: seamless', 'Six strips whose windows are chosen so neighbouring edges share colour: one image from many.',
    { 'layout.panels': 6, 'layout.overlap': 0, 'framing.mode': 'blend', 'framing.neighbour_influence': 1, 'framing.temperature': 0.05, 'framing.candidates': 96 }),
  S('scene_clash', 'Scene: clash', 'Five strips whose windows are chosen so neighbouring edges differ as much as possible.',
    { 'layout.panels': 5, 'framing.mode': 'contrast', 'framing.neighbour_influence': 1, 'framing.temperature': 0.05, 'framing.match_on': 'hue' }),
  S('scene_ken_burns', 'Scene: Ken Burns', 'Three panels that slowly pan and zoom through each clip during the hold.',
    { 'timing.hold_min': 8, 'timing.hold_max': 16, 'layout.panels': 3, 'framing.mode': 'drift', 'framing.drift_speed': 2, 'framing.zoom_jitter': 30 }),
  S('scene_plain_centre', 'Scene: plain centre', 'Today\'s look: every clip shown by the zoom module\'s own focal point, no derived windows.',
    { 'framing.mode': 'center' }),
];

export const presetById = Object.fromEntries(PRESETS.map((p) => [p.id, p]));

export function validatePreset(preset) {
  const errors = [];
  for (const [id, v] of Object.entries(preset.values)) {
    if (!byId[id]) { errors.push(`${preset.id}: unknown parameter ${id}`); continue; }
    const r = coerce(id, v);
    if (!r.ok) errors.push(`${preset.id}: invalid value for ${id}: ${JSON.stringify(v)}`);
    else if (JSON.stringify(r.value) !== JSON.stringify(v)) errors.push(`${preset.id}: ${id}=${JSON.stringify(v)} outside registry range`);
  }
  for (const m of preset.resets) if (!paramsOf(m).length) errors.push(`${preset.id}: unknown module ${m}`);
  return errors;
}

// Returns a new values object (does not touch modules outside `resets`).
export function applyPreset(values, preset) {
  const out = { ...values };
  for (const m of preset.resets) for (const p of paramsOf(m)) out[p.id] = Array.isArray(p.default) ? p.default.slice() : p.default;
  for (const [id, v] of Object.entries(preset.values)) out[id] = Array.isArray(v) ? v.slice() : v;
  return out;
}
