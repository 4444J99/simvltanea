import { mulberry32, buildRecords } from '../../app/engine.js';
import { defaults } from '../../app/params.js';

const ENV = ['nature', 'urban', 'domestic', 'workplace', 'transit', 'event', 'studio'];
const TOD = ['day', 'golden_hour', 'dusk', 'night', 'artificial_light'];
const SHOT = ['close_up', 'medium', 'wide'];
const ML = ['still', 'subtle', 'moderate', 'intense'];
const SUBJ = ['tree', 'sky', 'car', 'street', 'dog', 'cake', 'sea', 'mountain', 'bike', 'window', 'river', 'crowd'];
const MOOD = ['calm', 'joyful', 'tense', 'nostalgic', 'quiet'];

export function makeRaw(n, seed = 7) {
  const rng = mulberry32(seed);
  const pick = (a) => a[Math.floor(rng() * a.length)];
  const clips = [];
  for (let i = 0; i < n; i++) {
    const t = Date.UTC(2012, 0, 1) + Math.floor(rng() * 10 * 365 * 86400000);
    const portrait = rng() < 0.5;
    const env = pick(ENV);
    clips.push({
      id: 'c' + String(i).padStart(5, '0'), video: `media/c${i}.mp4`, still: `still/c${i}.jpg`,
      duration: 1 + rng() * 4, width: portrait ? 540 : 720, height: portrait ? 720 : 540,
      orientation: portrait ? 'portrait' : 'landscape', has_audio: true, loudness_db: -50 + rng() * 30,
      captured_at: new Date(t).toISOString(),
      tags: {
        subjects: [pick(SUBJ), pick(SUBJ)], setting: env === 'nature' ? 'outdoor' : pick(['indoor', 'outdoor', 'mixed']),
        environment: env, time_of_day: pick(TOD), camera: pick(['locked', 'handheld', 'pan']), motion_level: pick(ML), shot: pick(SHOT),
        palette: [pick(['blue', 'green', 'red'])], mood: [pick(MOOD)], keywords: [pick(SUBJ), pick(SUBJ)],
        people: { count: pick(['0', '1', '2-3', '4+']), faces_visible: false, minors_apparent: false },
        privacy: { readable_text: false, license_plate: false, document_or_screen: false, location_identifiable: false, sharing_sensitivity: 'low' },
        safety: { verdict: 'clear' },
      },
      features: { luma: rng(), luma_spread: rng() * 0.3, saturation: rng(), hue: rng(), motion: rng() * 0.3 },
    });
  }
  return clips;
}

export const makeRecords = (n, seed) => buildRecords(makeRaw(n, seed));
export const params = (over = {}) => ({ ...defaults(), ...over });
