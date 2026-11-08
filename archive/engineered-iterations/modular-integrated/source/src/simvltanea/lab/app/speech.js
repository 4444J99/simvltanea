// Speech policy: pure helpers (no DOM). A clip's `audio` record comes from a local speech screen; it
// never contains a transcript and none is read here.
export const SPEECH_POLICIES = ['play', 'mute', 'exclude'];
// Flags that always count as speech content (number_sequence, email_like, introduces_self) plus the two
// that follow the same policy (possible_name, long_speech).
export const SPEECH_FLAGS = ['number_sequence', 'email_like', 'introduces_self', 'possible_name', 'long_speech'];

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

// Normalises clip.audio. Cautious on malformed data: a present `speech` that is not a boolean, or a
// present `flags` that is not an array, counts as speech. Only `screened === true` counts as screened.
export function parseAudioInfo(raw) {
  if (!isObj(raw)) return { present: false, screened: false, speech: false, flags: [], words: NaN, lowConfidence: false, malformed: raw !== undefined && raw !== null };
  const sp = raw.speech;
  const malformedSpeech = sp !== undefined && sp !== null && typeof sp !== 'boolean';
  const fl = raw.flags;
  const malformedFlags = fl !== undefined && fl !== null && !Array.isArray(fl);
  const flags = Array.isArray(fl) ? fl.filter((x) => typeof x === 'string').map((x) => x.trim().toLowerCase()).filter(Boolean) : [];
  return {
    present: true, screened: raw.screened === true, speech: sp === true || malformedSpeech, flags,
    words: typeof raw.words === 'number' && Number.isFinite(raw.words) ? raw.words : NaN,
    lowConfidence: raw.low_confidence === true, malformed: malformedSpeech || malformedFlags || (raw.screened !== undefined && typeof raw.screened !== 'boolean'),
    ...(malformedFlags ? { speech: true } : {}),
  };
}

// True when the policy applies to this clip: audio.speech, or any of the speech flags.
export function hasSpeech(rec) {
  const a = rec && rec.audio;
  if (!a) return false;
  return a.speech === true || a.flags.some((f) => SPEECH_FLAGS.includes(f));
}

// {excluded, muted, reason} for a clip under (policy, muteUnscreened).
export function speechVerdict(rec, policy = 'mute', muteUnscreened = true) {
  const speech = hasSpeech(rec);
  if (speech && policy === 'exclude') return { excluded: true, muted: true, reason: 'speech-excluded' };
  if (speech && policy === 'mute') return { excluded: false, muted: true, reason: 'speech' };
  if (muteUnscreened && !(rec && rec.audio && rec.audio.screened === true)) return { excluded: false, muted: true, reason: 'unscreened' };
  return { excluded: false, muted: false, reason: '' };
}

// Playback gain of one clip before panel size/pan/master: loudness normalisation, 0 when silent or
// muted by the speech policy. `e` is the effective parameter set.
export function clipGain(rec, e) {
  if (!rec || !rec.hasAudio) return 0;
  if (speechVerdict(rec, e['audio.speech_policy'], e['audio.mute_unscreened']).muted) return 0;
  if (!e['audio.normalize'] || !Number.isFinite(rec.loudness)) return 1;
  return Math.pow(10, Math.min(20, Math.max(-40, e['audio.norm_target_db'] - rec.loudness)) / 20);
}
