// Keep the application address in sync with the embedded Watch session.
if (typeof window !== 'undefined' && typeof history !== 'undefined') {
  const originalReplace = history.replaceState.bind(history);
  history.replaceState = function(...args) {
    const result = originalReplace(...args);
    if (window.parent !== window) window.parent.postMessage({type:'simvltanea:watch-url',search:location.search},location.origin);
    return result;
  };
}
/* SIMVLTANEA studio: loops on their own clocks, colliding by accident.
 *
 * A classic script without dependencies, staged as studio.js beside compiler.js,
 * runtime.js and layouts.json by browser_studio.stage_studio. It loads after
 * compiler.js and the persistent Studio runtime modules. Compiled plans retain
 * layout/export metadata; native-loop residents own continuous playback.
 *
 * The page plays at once. Twelve generative pictures (canvas drawings with
 * integer-cycle motion, so the last frame meets the first) are drawn live while
 * MediaRecorder records each one, once, into a blob; then the recordings play
 * through the compiler and runtime like any video loop. Without MediaRecorder the
 * live canvases remain the panels. Each built-in loop has its own Web Audio voice,
 * scheduled on that loop's clock and fed into the runtime's per-loop gain and pan.
 *
 * Each roll (rollComposition) picks a family, a panel count it offers, distinct
 * loops in some order and, for strips, a zoom and lateral jitter within the preset
 * ranges. ?seed=<uint32> reproduces a roll; ?rv=2 marks the current roll version (a link without it
 * replays its original draw, see ROLL_VERSION); ?mix= records hand edits on top of it.
 *
 * Sound is gated by the browser until the first gesture. Before it the plan is the
 * silent v1 field (muted video autoplays); after it persistent audio bindings
 * provide each loop's own sound without recreating or restarting the videos.
 *
 * Library mode: when library/manifest.json (simvltanea.public-demo/1) sits beside the page and
 * validates, its clips replace the generated loops (?gen=1 forces the generated ones). A roll
 * picks clips by their tags (no palette+shot twice when avoidable, a portrait/landscape mix), and
 * only those clips are fetched, checked against their manifest and kept in a small LRU; the next
 * shuffle's clips are prefetched when idle. Real decoding is verified at standby admission.
 * The clips' own audio plays in the spatial mix.
 *
 * A visitor's own files are optional. Each one is gated before it becomes a loop:
 * a total-size cap, a container/codec sniff checked with video.canPlayType(), a
 * real metadata load that must yield a decoded frame, a duration quantized down to
 * whole composition frames, and one crypto.subtle SHA-256 digest that the
 * runtime's integrity check reuses. Files never leave the device.
 *
 * The pure helpers are exported for Node tests through module.exports and
 * published as globalThis.SimvltaneaStudio in the browser.
 */
(function (root) {
  'use strict';
  const FPS = 24, DEFAULT_SECONDS = 120, MAX_FRAMES = 14400, DEFAULT_PANELS = 5, OWN_FAMILY = 'file';
  const MIB = 1024 * 1024, MAX_TOTAL_BYTES = 512 * MIB;
  const MIN_FRAMES = 6; // a quarter second at 24 fps; spanVerdict checks the span guard for the piece length
  const MAX_SPANS_PER_TRACK = 1024; // browser.compiler.js MAX_SEGMENTS: at most this many spans per track on average
  const METADATA_TIMEOUT_MS = 15000;
  // Tolerates float spellings such as 0.7 * 30 = 20.999999999999996 (about 40 ns at 24 fps).
  const FRAME_EPSILON = 1e-6;
  const EXTENSION_TYPES = {mp4: 'video/mp4', m4v: 'video/mp4', mov: 'video/quicktime', qt: 'video/quicktime',
    webm: 'video/webm', mkv: 'video/x-matroska'};
  const CONTAINER_TYPES = {quicktime: 'video/quicktime', isobmff: 'video/mp4', matroska: 'video/webm'};
  const CONTAINER_SUFFIXES = {quicktime: 'mov', isobmff: 'mp4', matroska: 'webm'};

  // ---- Pure helpers ------------------------------------------------------

  const gcd = (a, b) => { while (b) [a, b] = [b, a % b]; return a; };

  /* Floor a float duration in seconds to whole frames of the composition and
   * return the exact rational frames/fps (reduced). Flooring means a loop's
   * declared period never exceeds the media, so no seek lands past its end. */
  function quantizeDuration(seconds, fps = FPS) {
    if (!Number.isSafeInteger(fps) || fps < 1 || fps > 60) throw new RangeError('fps must be an integer in 1..60');
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) {
      throw new RangeError('duration must be a positive finite number of seconds');
    }
    const frames = Math.floor(seconds * fps + FRAME_EPSILON);
    if (!Number.isSafeInteger(frames)) throw new RangeError('duration is too long');
    if (frames < 1) throw new RangeError('duration is shorter than one frame');
    const g = gcd(frames, fps) || 1;
    const [n, d] = [frames / g, fps / g];
    return {frames, fps, duration: d === 1 ? String(n) : `${n}/${d}`, seconds: frames / fps};
  }

  const formatMiB = bytes => `${(bytes / MIB).toFixed(bytes < 10 * MIB ? 1 : 0)} MiB`;

  /* Returns null when a file of `size` bytes fits beside `total` bytes already
   * accepted, otherwise the visitor-facing reason. */
  function admitSize(name, size, total, cap = MAX_TOTAL_BYTES) {
    if (!Number.isSafeInteger(size) || size <= 0) return `${name} is empty, so it cannot be a loop.`;
    if (total + size <= cap) return null;
    return `${name} was not added: the chosen videos would total ${formatMiB(total + size)}, over the ` +
      `${formatMiB(cap)} limit for this page (the browser holds about twice that in memory).`;
  }

  const plural = (count, noun) => `${count} ${noun}${count === 1 ? '' : 's'}`;

  /* Live validation of the loop count against the chosen panel count: one independent
   * loop per panel, no filler, no duplication. `available` lists the counts the chosen
   * layout offers, so the message only suggests a panel count that exists. */
  function countVerdict(count, panels, available = []) {
    const rule = 'Every panel plays one of your loops; nothing is padded, repeated or duplicated.';
    if (!Number.isSafeInteger(panels) || panels < 1) {
      return {ok: false, message: `Choose a layout and a panel count first. ${rule}`};
    }
    if (count === 0) return {ok: false, message: `No loops chosen yet. Choose ${plural(panels, 'video')} for ${plural(panels, 'panel')}. ${rule}`};
    if (count === panels) return {ok: true, message: `${plural(count, 'loop')} chosen. Ready to play.`};
    const other = available.includes(count) ? `, or set Panels to ${count}` : '';
    const chosen = `${plural(count, 'loop')} chosen for ${plural(panels, 'panel')}.`;
    if (count < panels) return {ok: false, message: `${chosen} Add ${panels - count} more${other}. ${rule}`};
    return {ok: false, message: `${chosen} Remove ${plural(count - panels, 'loop')}${other}. ${rule}`};
  }

  /* The offered count closest to `wanted` (the smaller one on a tie); null when none is offered. */
  function nearestCount(counts, wanted) {
    let best = null;
    for (const count of counts) {
      if (best === null || Math.abs(count - wanted) < Math.abs(best - wanted) ||
        (Math.abs(count - wanted) === Math.abs(best - wanted) && count < best)) best = count;
    }
    return best;
  }

  const FAMILY_LABELS = {strips: 'Strips', authored: 'Authored'};
  function familyLabel(name, file = null) {
    if (name === OWN_FAMILY && file) return `My file: ${file}`;
    return FAMILY_LABELS[name] || name.charAt(0).toUpperCase() + name.slice(1);
  }

  // A visitor-facing error on one line, naming the file it is about.
  function oneLine(message, file = null) {
    const text = String(message).replace(/\s*[\r\n]+\s*/g, ' ').trim();
    return file && !text.startsWith(file) ? `${file}: ${text}` : text;
  }

  const fourcc = (bytes, at) => String.fromCharCode(bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]);
  const u32 = (bytes, at) => ((bytes[at] << 24) | (bytes[at + 1] << 16) | (bytes[at + 2] << 8) | bytes[at + 3]) >>> 0;
  const hex2 = value => value.toString(16).padStart(2, '0').toUpperCase();

  // ISO/IEC 14496-12 boxes in [start, end): [{type, start (payload), end}].
  function boxes(bytes, start, end) {
    const found = [];
    let at = start;
    while (at + 8 <= end) {
      let size = u32(bytes, at), header = 8;
      const type = fourcc(bytes, at + 4);
      if (size === 1) {
        if (at + 16 > end) break;
        size = u32(bytes, at + 8) * 2 ** 32 + u32(bytes, at + 12); header = 16;
      } else if (size === 0) size = end - at;
      if (size < header || at + size > end) break;
      found.push({type, start: at + header, end: at + size});
      at += size;
    }
    return found;
  }
  const child = (bytes, box, type) => box && boxes(bytes, box.start, box.end).find(item => item.type === type);

  // RFC 6381 codec parameter from the avcC/hvcC configuration record, when present.
  function codecString(bytes, entry, sampleType) {
    const VISUAL_SAMPLE_ENTRY = 78;
    const config = boxes(bytes, entry.start + VISUAL_SAMPLE_ENTRY, entry.end);
    const avcC = config.find(box => box.type === 'avcC');
    if ((sampleType === 'avc1' || sampleType === 'avc3') && avcC && avcC.end - avcC.start >= 4) {
      const at = avcC.start;
      return `${sampleType}.${hex2(bytes[at + 1])}${hex2(bytes[at + 2])}${hex2(bytes[at + 3])}`;
    }
    const hvcC = config.find(box => box.type === 'hvcC');
    if ((sampleType === 'hvc1' || sampleType === 'hev1') && hvcC && hvcC.end - hvcC.start >= 13) {
      const at = hvcC.start, first = bytes[at + 1];
      const space = ['', 'A', 'B', 'C'][first >> 6], tier = first & 0x20 ? 'H' : 'L', profile = first & 0x1f;
      let compat = u32(bytes, at + 2), reversed = 0;
      for (let bit = 0; bit < 32; bit++) { reversed = (reversed << 1) | (compat & 1); compat >>>= 1; }
      const constraints = Array.from(bytes.subarray(at + 6, at + 12));
      while (constraints.length && constraints[constraints.length - 1] === 0) constraints.pop();
      return [`${sampleType}`, `${space}${profile}`, (reversed >>> 0).toString(16).toUpperCase(),
        `${tier}${bytes[at + 12]}`, ...constraints.map(hex2)].join('.');
    }
    return null;
  }
  const CODEC_LABELS = {avc1: 'H.264', avc3: 'H.264', hvc1: 'HEVC', hev1: 'HEVC', av01: 'AV1', vp09: 'VP9',
    vp08: 'VP8', mp4v: 'MPEG-4 Part 2', apcn: 'ProRes 422', apch: 'ProRes 422 HQ', apcs: 'ProRes 422 LT',
    apco: 'ProRes 422 Proxy', ap4h: 'ProRes 4444', jpeg: 'Motion JPEG'};
  // Sample entries whose RFC 6381 string needs details this sniff does not parse.
  const OPEN_CODECS = new Set(['av01', 'vp09', 'vp08', 'mp4v']);

  /* Identify the container and the first video track's codec from the file bytes.
   * QuickTime and MP4 share the ISO base media box structure, which browsers
   * demux with the same parser, so both report RFC 6381 codec strings. */
  function sniffContainer(input) {
    const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
    if (bytes.length >= 4 && u32(bytes, 0) === 0x1a45dfa3) return {container: 'matroska', brand: null, codec: null};
    const top = boxes(bytes, 0, bytes.length);
    const known = ['ftyp', 'moov', 'mdat', 'wide', 'free', 'skip', 'pnot', 'uuid'];
    if (!top.length || !known.includes(top[0].type)) return {container: 'unknown', brand: null, codec: null};
    const ftyp = top.find(box => box.type === 'ftyp');
    const brand = ftyp && ftyp.end - ftyp.start >= 4 ? fourcc(bytes, ftyp.start) : null;
    const container = brand === null || brand === 'qt  ' ? 'quicktime' : 'isobmff';
    const moov = top.find(box => box.type === 'moov');
    const tracks = moov ? boxes(bytes, moov.start, moov.end).filter(box => box.type === 'trak') : [];
    let codec = null;
    for (const trak of tracks) {
      const mdia = child(bytes, trak, 'mdia'), hdlr = child(bytes, mdia, 'hdlr');
      if (!hdlr || hdlr.end - hdlr.start < 12 || fourcc(bytes, hdlr.start + 8) !== 'vide') continue;
      const stsd = child(bytes, child(bytes, child(bytes, mdia, 'minf'), 'stbl'), 'stsd');
      if (!stsd) continue;
      const entry = boxes(bytes, stsd.start + 8, stsd.end)[0];
      if (!entry) continue;
      const sampleType = fourcc(bytes, entry.start - 4);
      const exact = codecString(bytes, entry, sampleType);
      codec = {fourcc: sampleType, string: exact ?? (OPEN_CODECS.has(sampleType) ? null : sampleType.trim()),
        label: CODEC_LABELS[sampleType] || sampleType.trim()};
      break;
    }
    return {container, brand, codec};
  }

  /* MIME strings worth asking video.canPlayType() about, most specific first.
   * A codec-qualified answer is decisive; otherwise any non-empty answer passes
   * and the real metadata load decides. Chrome answers '' for video/quicktime
   * yet plays QuickTime through its MP4 demuxer, hence the MP4 spelling. */
  function playbackQueries(type, sniff) {
    const iso = sniff.container === 'quicktime' || sniff.container === 'isobmff';
    if (iso && sniff.codec && sniff.codec.string) {
      return {decisive: true, queries: [`video/mp4; codecs="${sniff.codec.string}"`]};
    }
    const queries = [type];
    if (iso && type !== 'video/mp4') queries.push('video/mp4');
    if (sniff.container === 'matroska' && type !== 'video/webm') queries.push('video/webm');
    return {decisive: false, queries};
  }

  const extensionOf = name => {
    const dot = name.lastIndexOf('.');
    return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
  };

  /* The Blob type for a chosen file: what the browser reported, else the name's
   * extension, else the sniffed container, else MP4. */
  function blobType(name, declared, sniff) {
    if (typeof declared === 'string' && /^video\/[a-z0-9.+-]+$/i.test(declared)) return declared.toLowerCase();
    return EXTENSION_TYPES[extensionOf(name)] || CONTAINER_TYPES[sniff && sniff.container] || 'video/mp4';
  }

  // Suffix of the runtime's media/<sha256>.<suffix> path; the runtime only uses it as a Blob-type fallback.
  function mediaSuffix(name, sniff) {
    const extension = extensionOf(name);
    if (/^[a-z0-9]{1,8}$/.test(extension)) return extension;
    return CONTAINER_SUFFIXES[sniff && sniff.container] || 'mp4';
  }

  function compositionFrames(search, fps = FPS) {
    const value = new URLSearchParams(search || '').get('seconds');
    const requested = value !== null && /^\d{1,5}$/.test(value) ? Number(value) : 0;
    const seconds = requested >= 1 ? requested : DEFAULT_SECONDS;
    return Math.min(MAX_FRAMES, seconds * fps);
  }

  /* The compiler's span guard for the chosen loops: a loop of L frames at rate 1
   * from offset 0 opens ceil(frames / L) spans, and the total must not exceed
   * MAX_SPANS_PER_TRACK per loop. When it would, name the longest piece that fits. */
  function spanVerdict(frames, loopFrames, fps = FPS) {
    const spans = length => loopFrames.reduce((sum, each) => sum + Math.ceil(length / each), 0);
    const budget = MAX_SPANS_PER_TRACK * loopFrames.length;
    if (spans(frames) <= budget) return {ok: true, message: ''};
    let seconds = Math.floor(frames / fps);
    while (seconds > 1 && spans(seconds * fps) > budget) seconds -= 1;
    return {ok: false, message: `These loops are too short for a ${frames / fps}-second piece: the player ` +
      `can start them at most ${budget} times in all. Choose longer loops, or open the page with ` +
      `?seconds=${seconds} or less.`};
  }

  // ---- Accidents: seeded rolls, reproducible from ?seed and ?mix ---------------

  /* mulberry32: a small, fast, well-spread 32-bit generator; the same seed yields the same roll everywhere. */
  function seededRandom(seed) {
    let state = seed >>> 0;
    return () => {
      state = (state + 0x6d2b79f5) >>> 0;
      let t = state;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const pick = (list, random) => list[Math.floor(random() * list.length)];
  function shuffled(list, random) {
    const out = list.slice();
    for (let index = out.length - 1; index > 0; index--) {
      const other = Math.floor(random() * (index + 1));
      [out[index], out[other]] = [out[other], out[index]];
    }
    return out;
  }

  // A seed is a decimal uint32; anything else is ignored (a fresh roll).
  function parseSeed(search) {
    const value = new URLSearchParams(search || '').get('seed');
    return value !== null && /^\d{1,10}$/.test(value) && Number(value) <= 0xffffffff ? Number(value) : null;
  }

  // Strips zoom (z1 of the power curve) and lateral jitter: tasteful subsets of the preset's allowed ranges.
  const ROLL_Z1 = ['5/4', '3/2', '2', '5/2', '3'];
  const ROLL_JITTER = ['0', '0', '1/100', '1/50', '1/40', '1/20'];

  /* Roll versions. A seed alone must keep producing the roll it produced when it was shared, so the
   * counts a roll may pick from are part of its identity. Version 1 (every link without ?rv) draws the
   * authored family from 2..7 only, exactly as before authored mosaics for 8..12 existed; version 2
   * (?rv=2, written for every fresh roll) draws from every count the family offers. Strips and
   * visitor layouts are unchanged by the version. Hand edits (panel count, family) are not rolls and
   * may use any offered count under either version. */
  const ROLL_VERSION = 2;
  const LEGACY_ROLL_MAX = {authored: 7};
  function rollCounts(family, counts, version = 1) {
    const limit = version >= 2 ? Infinity : LEGACY_ROLL_MAX[family] ?? Infinity;
    return counts.filter(count => count <= limit);
  }
  // ?rv=2 is the current roll; a seed without it is a version 1 link; no seed at all is a fresh roll.
  function parseRollVersion(search) {
    if (new URLSearchParams(search || '').get('rv') === '2') return ROLL_VERSION;
    return parseSeed(search) === null ? ROLL_VERSION : 1;
  }

  /* One accident: a family, a panel count it supports (at most `pool` loops), which loops in
   * which order, and the strips framing. `families` maps a family name to its counts. */
  function rollComposition(seed, families, pool, version = 1) {
    const random = seededRandom(seed);
    const counts = name => rollCounts(name, families[name], version).filter(count => count <= pool);
    const names = Object.keys(families).sort().filter(name => counts(name).length);
    if (!names.length) return null;
    const family = pick(names, random);
    const panels = pick(counts(family), random);
    const loops = shuffled(Array.from({length: pool}, (_, index) => index), random).slice(0, panels);
    const style = {z1: pick(ROLL_Z1, random), jitter: pick(ROLL_JITTER, random), reverse: random() < 0.5};
    return {seed: seed >>> 0, family, panels, loops, style};
  }

  // ?mix=s3.7.1: the family's initial and the built-in loops by index, after hand edits to a roll.
  const FAMILY_CODES = {s: 'strips', a: 'authored'};
  function formatMix(family, loops) {
    const code = Object.keys(FAMILY_CODES).find(key => FAMILY_CODES[key] === family);
    return code ? `${code}${loops.join('.')}` : null;
  }
  function parseMix(text, families, pool) {
    // Up to four digits per index, so a library of thousands of clips is still addressable.
    const match = /^([a-z])(\d{1,4}(?:\.\d{1,4}){0,11})$/.exec(text || '');
    if (!match || !FAMILY_CODES[match[1]]) return null;
    const family = FAMILY_CODES[match[1]], loops = match[2].split('.').map(Number);
    if (!families[family] || !families[family].includes(loops.length)) return null;
    if (new Set(loops).size !== loops.length || loops.some(index => index >= pool)) return null;
    return {family, loops};
  }

  // Strips preset for a roll's framing; every value lies within the preset format's ranges.
  function stripsPreset(style, format = 'simvltanea.layout-preset/1') {
    const order = style.reverse ? 'reverse' : 'forward';
    return {format, name: 'roll', family: 'strips', counts: {min: 1, max: 12},
      orientations: {portrait: {direction: 'rows', order}, landscape: {direction: 'columns', order}},
      weights: {default: 'equal', by_count: {}}, fit: 'cover', focal: {default: ['1/2', '1/2'], by_index: {}},
      full_bleed: true, overlap_px: 2,
      zoom: {curve: 'power', z1: style.z1, gamma: '3/5', min_zoom: '10/9', quantum: 1000, table: {}},
      style: {corner_radius: '0', lateral_jitter: style.jitter}};
  }

  // Each loop's level in the mix: about 1/sqrt(N), so twelve loops are no louder than one.
  function loopGain(count) {
    return `${Math.max(1, Math.round(1000 / Math.sqrt(Math.max(1, count))))}/1000`;
  }

  /* The first audio track of an ISO/QuickTime file, as the runtime's audio_stream declaration:
   * {codec: 'aac', channels} for AAC, otherwise null (no declared stream). */
  function audioStream(input) {
    const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
    const top = boxes(bytes, 0, bytes.length), moov = top.find(box => box.type === 'moov');
    if (!moov) return null;
    for (const trak of boxes(bytes, moov.start, moov.end).filter(box => box.type === 'trak')) {
      const mdia = child(bytes, trak, 'mdia'), hdlr = child(bytes, mdia, 'hdlr');
      if (!hdlr || hdlr.end - hdlr.start < 12 || fourcc(bytes, hdlr.start + 8) !== 'soun') continue;
      const stsd = child(bytes, child(bytes, child(bytes, mdia, 'minf'), 'stbl'), 'stsd');
      const entry = stsd && boxes(bytes, stsd.start + 8, stsd.end)[0];
      if (!entry || fourcc(bytes, entry.start - 4) !== 'mp4a' || entry.end - entry.start < 20) return null;
      const channels = (bytes[entry.start + 16] << 8) | bytes[entry.start + 17];
      return {codec: 'aac', channels: channels === 1 ? 1 : 2};
    }
    return null;
  }

  // ---- Library: the published demo clips, chosen by their tags -----------------------

  const LIBRARY_SCHEMA = 'simvltanea.public-demo/1';
  const LIBRARY_FILE = /^clips\/[0-9a-f]{12}\.mp4$/;
  // The same bounds tools/publishing/stage_library_site.py applies before deploying a library.
  const LIBRARY_MAX_CLIPS = 5000, LIBRARY_MAX_BYTES = 64 * MIB, LIBRARY_MAX_SIDE = 4096, LIBRARY_MAX_SECONDS = 600;
  const LIBRARY_CACHE = 24;

  const words = value => (Array.isArray(value) ? value.filter(item => typeof item === 'string') : []);
  /* A clip's look for variety: its palette and shot together (null when neither is known). Only
   * these comparison keys are kept from the tags; nothing from them is ever shown. */
  function lookKey(tags) {
    const palette = words(tags.palette).slice().sort().join(','), shot = typeof tags.shot === 'string' ? tags.shot : '';
    return palette || shot ? `${palette}|${shot}` : null;
  }

  /* The clips of a simvltanea.public-demo/1 manifest, sorted by id, or null when anything is off:
   * a wrong schema, no clips, a file outside clips/<id>.mp4, a duplicate id, or a size, orientation
   * or duration out of bounds. A null manifest means the generated loops play instead. */
  function libraryAsset(clip, variant = false) {
    if (!clip || typeof clip !== 'object' || Array.isArray(clip)) return null;
    const size = (value, max) => Number.isSafeInteger(value) && value >= 1 && value <= max;
    const {id, file, width, height, orientation, bytes} = clip, seconds = clip.duration_seconds;
    if (typeof id !== 'string' || !/^[0-9a-f]{12}$/.test(id)) return null;
    if (typeof file !== 'string' || !LIBRARY_FILE.test(file) || file !== `clips/${id}.mp4`) return null;
    if (!size(width, LIBRARY_MAX_SIDE) || !size(height, LIBRARY_MAX_SIDE) || !size(bytes, LIBRARY_MAX_BYTES)) return null;
    if (orientation !== (height > width ? 'portrait' : 'landscape')) return null;
    if (!Number.isFinite(seconds) || seconds < MIN_FRAMES / FPS || seconds > LIBRARY_MAX_SECONDS) return null;
    const asset = {id, file, bytes, orientation, width, height, duration_seconds: seconds};
    if (variant) {
      if (clip.fps !== 30 || !size(clip.frame_count, 18000) ||
          Math.abs(clip.frame_count / 30 - seconds) >= 0.001 ||
          !Number.isFinite(clip.seam_offset_seconds) || clip.seam_offset_seconds < 0 ||
          clip.seam_offset_seconds > seconds) return null;
      for (const key of ['fps', 'frame_count', 'seam_offset_seconds']) asset[key] = clip[key];
    }
    const audioFields = ['has_audio', 'envelope_hz', 'rms_envelope', 'lufs_integrated', 'peak_dbfs'];
    if (variant || audioFields.some(key => clip[key] !== undefined)) {
      if (typeof clip.has_audio !== 'boolean' || clip.envelope_hz !== 10 ||
          !Array.isArray(clip.rms_envelope) || clip.rms_envelope.length !== Math.ceil(seconds * 10) ||
          clip.rms_envelope.some(value => !Number.isFinite(value) || value < 0 || value > 1)) return null;
      if (clip.lufs_integrated !== null && (!Number.isFinite(clip.lufs_integrated) ||
          clip.lufs_integrated < -160 || clip.lufs_integrated > 12)) return null;
      if (clip.has_audio ? (!Number.isFinite(clip.peak_dbfs) || clip.peak_dbfs < -160 || clip.peak_dbfs > 24) :
          (clip.peak_dbfs !== null || clip.lufs_integrated !== null)) return null;
      for (const key of audioFields) asset[key] = clip[key];
    }
    return asset;
  }
  function libraryClips(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data) || data.schema !== LIBRARY_SCHEMA) return null;
    if (!Array.isArray(data.clips) || !data.clips.length || data.clips.length > LIBRARY_MAX_CLIPS) return null;
    const seen = new Set(), assets = new Map(), clips = [];
    const rememberAsset = asset => {
      const facts = JSON.stringify(asset), previous = assets.get(asset.id);
      if (previous !== undefined && previous !== facts) return false;
      assets.set(asset.id, facts); return true;
    };
    for (const clip of data.clips) {
      const asset = libraryAsset(clip);
      if (!asset || seen.has(asset.id) || !rememberAsset(asset)) return null;
      const tags = clip.tags === undefined ? {} : clip.tags;
      if (!tags || typeof tags !== 'object' || Array.isArray(tags)) return null;
      seen.add(asset.id);
      if (clip.variants !== undefined) {
        if (!clip.variants || typeof clip.variants !== 'object' || Array.isArray(clip.variants) ||
            Object.keys(clip.variants).some(mode => mode !== 'boomerang')) return null;
        if (clip.variants.boomerang !== undefined) {
          const boomerang = libraryAsset(clip.variants.boomerang, true);
          if (!boomerang || boomerang.id === asset.id || !rememberAsset(boomerang)) return null;
          asset.variants = {boomerang};
        }
      }
      clips.push({...asset, look: lookKey(tags), mood: words(tags.mood)});
    }
    return clips.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  }

  /* How many of `count` panels should be portrait: a mix whenever the library has both shapes.
   * Authored layouts mix tall and wide cells, so they aim for half; strips follow the library's
   * own share. Never depends on the viewport, so a seed picks the same clips everywhere. */
  function portraitTarget(clips, count, family, exclude = []) {
    const usable = clips.filter((_, index) => !exclude.includes(index));
    const portraits = usable.filter(clip => clip.orientation === 'portrait').length;
    const landscapes = usable.length - portraits;
    const share = family === 'strips' && usable.length ? portraits / usable.length : 0.5;
    let target = Math.round(count * share);
    if (count >= 2 && portraits && landscapes) target = Math.min(count - 1, Math.max(1, target));
    return Math.max(0, Math.min(portraits, Math.max(count - landscapes, target)));
  }

  /* Pick `count` more clips (indexes) beside `keep`, never one in `exclude`. Candidates are taken
   * in a seeded random order and scored: a palette+shot not yet on screen (4) outweighs the
   * wanted orientation (2), which outweighs a mood not yet on screen (1); the first best wins. */
  function chooseClips(clips, count, family, random, keep = [], exclude = []) {
    const picked = keep.slice(), total = keep.length + count;
    const want = portraitTarget(clips, total, family, exclude);
    const order = shuffled(clips.map((_, index) => index).filter(index => !picked.includes(index) &&
      !exclude.includes(index)), random);
    for (let step = 0; step < count && order.length; step++) {
      const looks = new Set(picked.map(index => clips[index].look).filter(look => look !== null));
      const moods = new Set(picked.flatMap(index => clips[index].mood));
      const portraits = picked.filter(index => clips[index].orientation === 'portrait').length;
      const needs = {portrait: portraits < want, landscape: picked.length - portraits < total - want};
      let best = 0, bestScore = -1;
      order.forEach((index, at) => {
        const clip = clips[index];
        const score = (clip.look === null || !looks.has(clip.look) ? 4 : 0) + (needs[clip.orientation] ? 2 : 0) +
          (clip.mood.some(mood => moods.has(mood)) ? 0 : 1);
        if (score > bestScore) { best = at; bestScore = score; }
      });
      picked.push(order.splice(best, 1)[0]);
    }
    return picked.slice(keep.length);
  }

  /* One accident from the library: a family and a count it offers, the strips framing, then clips
   * chosen by their tags and placed in a seeded order. Same seed and same manifest, same clips. */
  function rollLibrary(seed, families, clips, exclude = [], version = 1) {
    const random = seededRandom(seed), available = clips.length - new Set(exclude).size;
    const counts = name => rollCounts(name, families[name], version).filter(count => count <= available);
    const names = Object.keys(families).sort().filter(name => counts(name).length);
    if (!names.length) return null;
    const family = pick(names, random);
    const panels = pick(counts(family), random);
    const style = {z1: pick(ROLL_Z1, random), jitter: pick(ROLL_JITTER, random), reverse: random() < 0.5};
    const loops = shuffled(chooseClips(clips, panels, family, random, [], exclude), random);
    return {seed: seed >>> 0, family, panels, loops, style};
  }

  // ---- Built-in loops: twelve generative pictures, each with its own voice --------------

  const TAU = Math.PI * 2;
  const wave = (theta, cycles = 1, offset = 0) => Math.sin(TAU * (theta * cycles + offset));
  // Integer cycles of theta only, so frame 0 follows the last frame of every loop seamlessly.
  const VISUALS = {
    drift(g, s, t) {
      g.fillStyle = '#0b1026'; g.fillRect(0, 0, s, s);
      g.globalCompositeOperation = 'lighter';
      [[32, 90, 58], [322, 70, 52], [184, 60, 42]].forEach(([hue, sat, light], index) => {
        const x = s * (0.5 + 0.3 * Math.cos(TAU * (t + index / 3))), y = s * (0.5 + 0.26 * wave(t, 2, index / 3));
        const glow = g.createRadialGradient(x, y, 0, x, y, s * 0.6);
        glow.addColorStop(0, `hsla(${hue},${sat}%,${light}%,0.85)`); glow.addColorStop(1, `hsla(${hue},${sat}%,${light}%,0)`);
        g.fillStyle = glow; g.fillRect(0, 0, s, s);
      });
      g.globalCompositeOperation = 'source-over';
    },
    bands(g, s, t) {
      const count = 16, height = s / count;
      for (let index = 0; index < count; index++) {
        const light = 16 + 22 * (0.5 + 0.5 * wave(t, 1, index * 0.137)) + 8 * wave(t, 2, index * 0.31);
        g.fillStyle = `hsl(${172 + index * 2},42%,${light}%)`;
        g.fillRect(0, index * height, s, height + 1);
      }
      g.fillStyle = 'rgba(255,255,255,0.05)';
      for (let index = 0; index < count; index++) g.fillRect(0, index * height + height * (0.5 + 0.4 * wave(t, 1, index / count)), s, 1);
    },
    sweep(g, s, t) {
      g.fillStyle = '#120d09'; g.fillRect(0, 0, s, s);
      g.save(); g.translate(s / 2, s / 2); g.rotate(TAU * t / 6);
      for (let index = 0; index < 24; index++) {
        g.fillStyle = `hsl(${28 + (index % 4) * 6},${55 + (index % 4) * 8}%,${12 + (index % 4) * 9}%)`;
        g.beginPath(); g.moveTo(0, 0); g.arc(0, 0, s, index * TAU / 24, (index + 1) * TAU / 24 + 0.004); g.fill();
      }
      g.restore();
      const shade = g.createRadialGradient(s / 2, s / 2, s * 0.05, s / 2, s / 2, s * 0.75);
      shade.addColorStop(0, 'rgba(0,0,0,0.65)'); shade.addColorStop(0.4, 'rgba(0,0,0,0)'); shade.addColorStop(1, 'rgba(0,0,0,0.55)');
      g.fillStyle = shade; g.fillRect(0, 0, s, s);
    },
    grain(g, s, t, period) {
      const base = g.createLinearGradient(0, 0, 0, s), lift = 0.5 + 0.5 * wave(t);
      base.addColorStop(0, `hsl(28,14%,${18 + 14 * lift}%)`); base.addColorStop(1, `hsl(220,10%,${10 + 6 * (1 - lift)}%)`);
      g.fillStyle = base; g.fillRect(0, 0, s, s);
      const frame = Math.floor(t * period * FPS), tile = noiseTile();
      const x = (frame * 97) % tile.width, y = (frame * 61) % tile.height;
      g.globalAlpha = 0.28; g.globalCompositeOperation = 'overlay';
      for (let dx = -x; dx < s; dx += tile.width) for (let dy = -y; dy < s; dy += tile.height) g.drawImage(tile, dx, dy);
      g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
    },
    tide(g, s, t) {
      g.fillStyle = '#04121d'; g.fillRect(0, 0, s, s);
      for (let layer = 0; layer < 5; layer++) {
        g.fillStyle = `hsla(${198 + layer * 7},${50 + layer * 4}%,${20 + layer * 9}%,0.82)`;
        g.beginPath(); g.moveTo(0, s);
        for (let x = 0; x <= s; x += s / 48) {
          const y = s * (0.3 + 0.13 * layer) + s * 0.05 * wave(x / s, layer % 2 ? 2 : 1, -t * (layer % 3 + 1));
          g.lineTo(x, y);
        }
        g.lineTo(s, s); g.closePath(); g.fill();
      }
    },
    lattice(g, s, t) {
      g.fillStyle = '#131313'; g.fillRect(0, 0, s, s);
      const n = 9, step = s / n;
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        const dx = (i - (n - 1) / 2) / n, dy = (j - (n - 1) / 2) / n, distance = Math.hypot(dx, dy);
        const swell = 0.5 + 0.5 * wave(t, 1, -distance * 1.6);
        g.fillStyle = `hsl(${22 + 14 * swell},${70 + 15 * swell}%,${30 + 32 * swell}%)`;
        g.beginPath(); g.arc((i + 0.5) * step, (j + 0.5) * step, step * (0.08 + 0.3 * swell), 0, TAU); g.fill();
      }
    },
    orbit(g, s, t) {
      g.fillStyle = '#07070c'; g.fillRect(0, 0, s, s);
      for (let body = 0; body < 5; body++) {
        const speed = (body % 3 + 1) * (body % 2 ? -1 : 1), radius = s * (0.14 + body * 0.065);
        for (let trail = 11; trail >= 0; trail--) {
          const angle = TAU * (speed * (t - trail * 0.006) + body / 5);
          g.fillStyle = `hsla(${190 + body * 12},70%,${70 + body * 4}%,${(1 - trail / 12) * 0.7})`;
          g.beginPath(); g.arc(s / 2 + radius * Math.cos(angle), s / 2 + radius * Math.sin(angle), s * 0.012 * (1 - trail / 14), 0, TAU); g.fill();
        }
      }
    },
    bloom(g, s, t) {
      g.fillStyle = '#1a0e1c'; g.fillRect(0, 0, s, s);
      g.lineWidth = s * 0.03;
      for (let ring = 0; ring < 9; ring++) {
        const r = ((ring + t) / 9) * s * 0.75;
        g.strokeStyle = `hsla(${300 + ring * 6},55%,${68 - ring * 3}%,${0.9 * (1 - r / (s * 0.75))})`;
        g.beginPath(); g.arc(s / 2, s / 2, r, 0, TAU); g.stroke();
      }
    },
    moire(g, s, t) {
      g.fillStyle = '#0c0c0c'; g.fillRect(0, 0, s, s);
      g.strokeStyle = 'rgba(232,228,220,0.5)'; g.lineWidth = Math.max(1, s / 320);
      for (const angle of [0.16 * wave(t), -0.16 * wave(t) + 0.05]) {
        g.save(); g.translate(s / 2, s / 2); g.rotate(angle);
        g.beginPath();
        for (let line = -36; line <= 36; line++) { g.moveTo(line * s / 40, -s); g.lineTo(line * s / 40, s); }
        g.stroke(); g.restore();
      }
    },
    aurora(g, s, t) {
      g.fillStyle = '#050a12'; g.fillRect(0, 0, s, s);
      const width = s / 72;
      for (let x = 0; x < s; x += width) {
        const height = s * (0.35 + 0.18 * wave(x / s, 2, t) + 0.08 * wave(x / s, 5, -2 * t));
        const curtain = g.createLinearGradient(0, s - height - s * 0.1, 0, s);
        curtain.addColorStop(0, 'hsla(160,70%,55%,0)');
        curtain.addColorStop(0.5, `hsla(${150 + 70 * x / s},70%,55%,0.55)`);
        curtain.addColorStop(1, 'hsla(260,60%,30%,0.2)');
        g.fillStyle = curtain; g.fillRect(x, s - height - s * 0.1, width + 0.5, height + s * 0.1);
      }
    },
    weave(g, s, t) {
      g.fillStyle = '#0f1418'; g.fillRect(0, 0, s, s);
      const span = s / 8;
      [[Math.PI / 4, 'hsla(205,30%,62%,0.32)'], [-Math.PI / 4, 'hsla(15,45%,58%,0.28)']].forEach(([angle, color], set) => {
        g.save(); g.translate(s / 2, s / 2); g.rotate(angle); g.fillStyle = color;
        const shift = (set ? -1 : 1) * t * span * 2;
        for (let k = -12; k <= 12; k++) g.fillRect(k * span * 2 + shift, -s, span, 2 * s);
        g.restore();
      });
    },
    pulse(g, s, t) {
      g.fillStyle = '#0e0e11'; g.fillRect(0, 0, s, s);
      const size = s * (0.42 + 0.12 * wave(t)), hue = 210 + 36 * wave(t, 1, 0.25);
      g.save(); g.shadowColor = `hsla(${hue},70%,60%,0.9)`; g.shadowBlur = s * 0.12;
      g.fillStyle = `hsl(${hue},45%,${46 + 10 * wave(t)}%)`;
      g.beginPath();
      if (g.roundRect) g.roundRect((s - size) / 2, (s - size) / 2, size, size, size * 0.18);
      else g.rect((s - size) / 2, (s - size) / 2, size, size);
      g.fill(); g.restore();
      g.strokeStyle = `hsla(${hue},40%,70%,0.25)`; g.lineWidth = s / 200;
      g.beginPath(); g.arc(s / 2, s / 2, size * 0.95, 0, TAU); g.stroke();
    },
  };
  let grainTile = null;
  function noiseTile() {
    if (grainTile) return grainTile;
    grainTile = document.createElement('canvas'); grainTile.width = grainTile.height = 192;
    const g = grainTile.getContext('2d'), image = g.createImageData(192, 192), random = seededRandom(7);
    for (let index = 0; index < image.data.length; index += 4) {
      const value = Math.floor(random() * 256);
      image.data[index] = image.data[index + 1] = image.data[index + 2] = value; image.data[index + 3] = 255;
    }
    g.putImageData(image, 0, 0);
    return grainTile;
  }

  /* Voices: D major pentatonic, each loop in its own register, quiet, soft attacks.
   * Event times are fractions of the loop's period, so the sound loops with the picture. */
  const VOICES = {
    drift: [{at: 0, type: 'pad', notes: [50, 57], cutoff: 900, level: 0.05}],
    bands: [{at: 0, type: 'swell', freq: 520, q: 1.4, level: 0.05}],
    sweep: [62, 66, 69].map((note, index) => ({at: index / 3, type: 'pluck', note, level: 0.05, decay: 1.4, cutoff: 2200})),
    grain: Array.from({length: 8}, (_, index) => ({at: index / 8 + 0.03 * (index % 3), type: 'tick', freq: 3800 + 400 * (index % 4), level: 0.02})),
    tide: [{at: 0, type: 'pad', notes: [45], cutoff: 420, level: 0.06}, {at: 0.5, type: 'swell', freq: 260, q: 0.9, level: 0.03}],
    lattice: [{at: 0, type: 'pluck', note: 74, level: 0.04, decay: 0.9, cutoff: 3000}, {at: 0.5, type: 'pluck', note: 81, level: 0.03, decay: 0.8, cutoff: 3000}],
    orbit: [{at: 0, type: 'bell', note: 78, level: 0.025, decay: 2.2}, {at: 0.62, type: 'bell', note: 76, level: 0.02, decay: 2}],
    bloom: [{at: 0, type: 'pad', notes: [69, 74], cutoff: 1800, level: 0.025}],
    moire: [{at: 0.25, type: 'swell', freq: 2400, q: 7, level: 0.025}],
    aurora: [{at: 0, type: 'pad', notes: [57, 62, 66], cutoff: 1300, level: 0.03}],
    weave: [62, 64, 62, 69].map((note, index) => ({at: index / 4, type: 'pluck', note, level: 0.03, decay: 0.6, cutoff: 1500})),
    pulse: [{at: 0, type: 'breath', note: 38, level: 0.09}],
  };
  // Twelve distinct periods (frames at 24 fps): 2.5 s to 5.25 s.
  const BUILTINS = ['drift', 'bands', 'sweep', 'grain', 'tide', 'lattice', 'orbit', 'bloom', 'moire', 'aurora', 'weave', 'pulse']
    .map((name, index) => ({name, frames: [96, 66, 108, 60, 126, 72, 114, 84, 120, 102, 78, 90][index]}));

  // Separate seeded successor selection from pacing, with logical-clip cooldown.
  function createSuccession(seed) {
    const departed = new Map();
    return {random: seededRandom(seed),
      depart: (id, time) => departed.set(id, time),
      eligible: (id, time) => !departed.has(id) || time - departed.get(id) >= 10};
  }

  const EFFECT_PARAMS = Object.freeze({attackSeconds: 'fx_attack', curve: 'fx_curve', tail: 'fx_tail',
    gainDepth: 'fx_gain', lowpassDepth: 'fx_lowpass', brightnessDepth: 'fx_brightness',
    saturationDepth: 'fx_saturation', blurPx: 'fx_blur'});
  const presenceApi = () => root.SimvltaneaPresence ||
    (typeof module === 'object' && module.exports ? require('./browser.presence.js') : null);
  function effectSettingsFromSearch(search) {
    const params = new URLSearchParams(search), values = {};
    for (const [key, name] of Object.entries(EFFECT_PARAMS)) {
      const value = params.get(name);
      if (value !== null && value.trim() !== '') values[key] = key === 'curve' ? value : Number(value);
    }
    return presenceApi().normalizeSettings(values);
  }
  function effectSettingsSearch(search, settings) {
    const params = new URLSearchParams(search), P = presenceApi(), values = P.normalizeSettings(settings);
    for (const [key, name] of Object.entries(EFFECT_PARAMS)) {
      if (values[key] === P.DEFAULT_SETTINGS[key]) params.delete(name);
      else params.set(name, String(values[key]));
    }
    return params.toString();
  }

  const api = {
    FPS, DEFAULT_SECONDS, DEFAULT_PANELS, MAX_TOTAL_BYTES, MIN_FRAMES, MAX_SPANS_PER_TRACK, OWN_FAMILY,
    quantizeDuration, admitSize, countVerdict, spanVerdict, nearestCount, familyLabel, oneLine, sniffContainer,
    playbackQueries, blobType, mediaSuffix, compositionFrames, formatMiB, seededRandom, parseSeed, createSuccession,
    rollComposition, formatMix, parseMix, stripsPreset, loopGain, audioStream,
    ROLL_VERSION, rollCounts, parseRollVersion,
    libraryClips, chooseClips, rollLibrary, LIBRARY_CACHE,
    effectSettingsFromSearch, effectSettingsSearch,
    BUILTINS: BUILTINS.map(item => ({name: item.name, frames: item.frames})),
  };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SimvltaneaStudio = api;
  if (typeof document === 'undefined' || !document.querySelector('#studio')) return;

  // ---- Page controller -----------------------------------------------------


  const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;
  const ICONS = {
    strips: svg('<rect x="3.5" y="4" width="4.2" height="16" rx="1"/><rect x="9.9" y="4" width="4.2" height="16" rx="1"/><rect x="16.3" y="4" width="4.2" height="16" rx="1"/>'),
    authored: svg('<rect x="3.5" y="4" width="9" height="16" rx="1"/><rect x="14.5" y="4" width="6" height="7" rx="1"/><rect x="14.5" y="13" width="6" height="7" rx="1"/>'),
    file: svg('<path d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10A.5.5 0 0 1 7 20z"/><path d="M14 3.5V8h4"/><path d="M10 13h5M10 16h5"/>'),
  };
  const $ = selector => document.querySelector(selector);
  const studio = $('#studio'), stage = $('#stage');
  const ui = {
    frame: $('#frame'), preview: $('#preview'), ghost: $('#ghost'), bar: $('#bar'), play: $('#play'), start: $('#start'),
    corner: $('#corner'), activity: $('#activity'), effects: $('#effects'), loopMode: $('#loop-mode'),
    filterTune: $('#filter-tune'), filterDialog: $('#filter-settings'),
    shuffle: $('#shuffle'), fewer: $('#fewer'), more: $('#more'), panels: $('#panel-count'),
    families: $('#families'), speaker: $('#speaker'), volume: $('#volume'), add: $('#add'), files: $('#files'),
    fullscreen: $('#fullscreen'), help: $('#help'), about: $('#about'), toast: $('#toast'),
  };
  const search = root.location ? root.location.search : '';
  const frames = compositionFrames(search);
  let loopMode = new URLSearchParams(search).get('loop') === 'forward' ? 'forward' : 'boomerang';
  let evolving = new URLSearchParams(search).get('evolve') !== '0';
  let manualPopulation = new URLSearchParams(search).has('mix');
  const reduced = Boolean(root.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  let filtersEnabled = !reduced && new URLSearchParams(search).get('fx') !== '0';
  let effectSettings = effectSettingsFromSearch(search);
  const FADE_MS = reduced ? 0 : 220, IDLE_MS = 3000, TOAST_MS = 4200;
  const compiler = () => root.SimvltaneaCompiler;
  const runtime = () => root.compositionRuntime;
  const hex = buffer => Array.from(new Uint8Array(buffer), value => value.toString(16).padStart(2, '0')).join('');
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const until = (test, limit = 20000) => new Promise((resolve, reject) => {
    const began = performance.now();
    (function poll() {
      if (test()) resolve();
      else if (performance.now() - began > limit) reject(new Error('The player did not settle'));
      else setTimeout(poll, 30);
    })();
  });

  const layout = {bundle: null, families: {}, own: null, loading: true};
  // The loops on offer: the twelve built-ins until the visitor adds their own.
  const builtins = BUILTINS.map((item, index) => ({...item, index, ready: null, quantized: quantizeDuration(item.frames / FPS)}));
  const own = [];
  /* Library mode: library/manifest.json beside the page lists published clips, which replace the
   * built-ins. Only the clips a roll uses are fetched; a small LRU keeps recent ones for rerolls. */
  const library = {active: false, clips: [], items: [], broken: new Set(), failedAssets: new Set(), cache: new Map(), inflight: new Map(),
    requested: 0, next: null, prefetch: [], probe: null};
  const digests = new WeakMap();
  const sound = {unlocked: false, muted: false, volume: 0.7, mixer: null};
  let selection = null, session = null, exportFailure = null, waiting = [], launches = 0, hold = reduced, paused = false;
  let lastRefusals = [], busy = 0, recordMode = 'pending', builtinRecording = null, previewClock = null;
  const liveVoices = new Map();
  let liveVoiceClock = null;
  // Which counts a seed's roll draws from: a link without ?rv keeps its original roll (see ROLL_VERSION).
  let rollVersion = parseRollVersion(search);
  // The version of a roll that has been drawn but not yet accepted: rollVersion (what the URL names) only
  // changes once that roll is on screen, so a refused shuffle leaves the previous composition's link intact.
  let pendingRollVersion = null;
  let ecosystem = new root.SimvltaneaEcosystem.Engine({seed: parseSeed(search) ?? 1});
  let succession = createSuccession(parseSeed(search) ?? 1), pendingSelection = false;
  const residentModels = new WeakMap(), residents = [];
  let ecologicalRequest = null, lastSpaceTime = -1;
  let previousLogicalIds = new Set(), currentLogicalIds = new Set();
  const live = root.compositionRuntime = new root.SimvltaneaLive.Session(stage, {
    crossfadeSec: reduced ? 0 : 1.2,
    effects: filtersEnabled, reducedMotion: reduced, effectSettings,
    onAudioNode: attachLiveVoice,
    onDeckAudio: attachDeckVoice,
    onDeckUnload: detachLiveVoice,
    onError: () => toast('That loop could not start. The current picture keeps playing.'),
  });

  live.clock.subscribe(ecologyTick);

  const usingLibrary = () => library.active && !own.length;
  const filtersAvailable = () => !reduced && (recordMode !== 'canvas' || own.length > 0 || library.active);
  const pool = () => (own.length ? own : library.active ? library.items : builtins);
  // How many loops a roll may use: the library's clips minus any that failed to load.
  const available = () => (usingLibrary() ? library.items.length - library.broken.size : pool().length);
  const familyCounts = () => Object.fromEntries(Object.entries(layout.families).map(([name, family]) => [name, family.counts]));
  const allowedCounts = counts => counts.filter(count => count <= live.maxForeground);
  function boundedSelection(value) {
    if (!value) return value;
    const fits = family => (layout.families[family]?.counts || []).filter(count =>
      count <= value.loops.length && count <= available());
    const family = fits(value.family).length ? value.family : 'strips';
    const count = nearestCount(fits(family), Math.min(value.loops.length, live.maxForeground));
    if (count === null) return null;
    return family === value.family && count === value.loops.length ? value :
      {...value, family, panels: count, loops: value.loops.slice(0, count),
        retained: new Map([...(value.retained || [])].filter(([slot]) => slot < count))};
  }

  // ---- Toast, idle chrome, about ------------------------------------------------

  let toastTimer = null;
  function toast(text) {
    clearTimeout(toastTimer);
    ui.toast.textContent = text;
    ui.toast.classList.add('on');
    toastTimer = setTimeout(() => ui.toast.classList.remove('on'), TOAST_MS);
  }

  let idleTimer = null;
  function wake() {
    studio.classList.remove('idle');
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      const active = document.activeElement;
      const focused = active && active !== document.body && (ui.bar.contains(active) || ui.corner.contains(active));
      if (!focused && ui.about.hidden && !ui.filterDialog.open && !hold) studio.classList.add('idle');
    }, IDLE_MS);
  }
  for (const type of ['pointermove', 'pointerdown', 'keydown', 'focusin']) document.addEventListener(type, wake, true);

  function setAbout(open) {
    ui.about.hidden = !open;
    ui.help.setAttribute('aria-expanded', String(open));
    if (open) ui.about.focus(); else if (ui.about.contains(document.activeElement)) ui.help.focus();
    wake();
  }
  ui.help.addEventListener('click', () => setAbout(ui.about.hidden));
  ui.about.addEventListener('click', () => setAbout(false));

  // ---- Sound: gated until the first gesture, then each loop's own audio -----------

  const soundState = () => (!sound.unlocked ? 'locked' : sound.muted ? 'off' : 'on');
  const wantSound = () => soundState() === 'on';
  const SPEAKER_LABELS = {locked: 'Tap for sound', on: 'Mute', off: 'Unmute'};
  function renderSound() {
    const state = soundState();
    studio.dataset.sound = state;
    ui.speaker.setAttribute('aria-label', SPEAKER_LABELS[state]);
    ui.speaker.setAttribute('aria-pressed', String(state === 'off'));
    ui.volume.value = String(Math.round(sound.volume * 100));
  }

  // The canvas fallback shares the same persistent, protected master bus.
  function mixer(context) {
    if (sound.mixer && sound.mixer.context === context) return sound.mixer;
    const bus = root.SimvltaneaLiveAudio.createMasterBus(context, {enabled: wantSound(), volume: sound.volume});
    sound.mixer = {context, input: bus.input, volume: bus.volume};
    return sound.mixer;
  }
  function applyVolume() {
    const mix = sound.mixer;
    if (mix && mix.context.state !== 'closed') {
      const now = mix.context.currentTime, param = mix.volume.gain;
      param.cancelScheduledValues(now); param.setValueAtTime(param.value, now);
      param.linearRampToValueAtTime(wantSound() ? sound.volume : 0, now + 0.18);
    }
    const r = runtime();
    if (r) r.setSound({enabled: wantSound(), volume: sound.volume});
  }
  // A video element is unmuted only after the gesture and only while the speaker is on.
  function guardMute(media) {
    if (!media || media.tagName !== 'VIDEO') return;
    if (!media.dataset.guarded) {
      media.dataset.guarded = '1';
      media.addEventListener('volumechange', () => { if (!media.muted && !wantSound()) media.muted = true; });
    }
    if (!wantSound()) media.muted = true;
  }

  function promoteAudioPlan(current = session) {
    if (!current || !sound.unlocked) return;
    const {plan, bySha} = current;
    Object.assign(plan, {plan_version: 2, engine_version: '1.1.0', audio: {
      mode: 'spatial_loops', master_volume: '1', spatial_panning: true,
      per_loop: Object.fromEntries(plan.tracks.map(track => [track.id,
        {gain: loopGain(plan.tracks.length), mute_on_hold: true}]))}});
    plan.sources.forEach(source => {
      source.audio_stream = bySha.get(source.sha256)?.audioStream || null;
    });
    current.sound = true;
  }
  function unlock() {
    if (sound.unlocked) {
      const r = runtime();
      if (r.audio.context && r.audio.context.state !== 'running') {
        r.unlock().then(applyVolume).catch(() => toast('Tap the speaker to resume sound.'));
        return true;
      }
      return false;
    }
    sound.unlocked = true;
    renderSound();
    applyVolume();
    // Create/resume on the gesture stack; media nodes and simulation keep running.
    runtime().unlock().then(() => { promoteAudioPlan(); applyVolume(); }).catch(() => {
      sound.unlocked = false; renderSound(); applyVolume();
      toast('Tap the speaker to enable sound.');
    });
    if (recordMode === 'canvas') fallbackAudio();
    return true;
  }
  function toggleSound() {
    if (unlock()) return;
    sound.muted = !sound.muted;
    renderSound();
    applyVolume();
    if (recordMode === 'canvas') fallbackAudio();
  }
  ui.speaker.addEventListener('click', toggleSound);
  ui.volume.addEventListener('input', () => {
    sound.volume = Number(ui.volume.value) / 100;
    if (sound.unlocked && sound.muted && sound.volume > 0) { sound.muted = false; renderSound(); }
    applyVolume();
  });

  const voiceNoise = new WeakMap();
  function noiseBuffer(context) {
    if (!voiceNoise.has(context)) {
      const buffer = context.createBuffer(1, context.sampleRate * 2, context.sampleRate), data = buffer.getChannelData(0);
      const random = seededRandom(11);
      for (let index = 0; index < data.length; index++) data[index] = random() * 2 - 1;
      voiceNoise.set(context, buffer);
    }
    return voiceNoise.get(context);
  }
  const hz = note => 440 * 2 ** ((note - 69) / 12);

  // Schedule one voice event at context time `when`; every envelope starts and ends at zero.
  function sing(context, out, event, when, period) {
    const env = context.createGain(), param = env.gain;
    param.setValueAtTime(0, when);
    env.connect(out);
    const stop = [];
    const osc = (type, frequency, detune = 0) => {
      const node = context.createOscillator(); node.type = type; node.frequency.value = frequency; node.detune.value = detune;
      stop.push(node); return node;
    };
    const filter = (type, frequency, q = 0.7) => {
      const node = context.createBiquadFilter(); node.type = type; node.frequency.value = frequency; node.Q.value = q;
      return node;
    };
    let end;
    if (event.type === 'pad') {
      const length = period * 1.3, low = filter('lowpass', event.cutoff);
      low.connect(env);
      for (const note of event.notes) for (const cents of [-5, 5]) osc(cents < 0 ? 'triangle' : 'sine', hz(note), cents).connect(low);
      param.linearRampToValueAtTime(event.level, when + length * 0.35);
      param.setValueAtTime(event.level, when + length * 0.6);
      param.linearRampToValueAtTime(0, when + length);
      end = when + length;
    } else if (event.type === 'breath') {
      const length = period, low = filter('lowpass', 220);
      low.connect(env); osc('sine', hz(event.note)).connect(low); osc('sine', hz(event.note + 12), 3).connect(low);
      param.linearRampToValueAtTime(event.level, when + length * 0.5);
      param.linearRampToValueAtTime(0, when + length);
      end = when + length;
    } else if (event.type === 'swell') {
      const length = period * 0.9, source = context.createBufferSource(), band = filter('bandpass', event.freq, event.q);
      source.buffer = noiseBuffer(context); source.loop = true; source.connect(band); band.connect(env); stop.push(source);
      param.linearRampToValueAtTime(event.level, when + length * 0.55);
      param.linearRampToValueAtTime(0, when + length);
      end = when + length;
    } else if (event.type === 'tick') {
      const source = context.createBufferSource(), band = filter('bandpass', event.freq, 3);
      source.buffer = noiseBuffer(context); source.connect(band); band.connect(env); stop.push(source);
      param.linearRampToValueAtTime(event.level, when + 0.006);
      param.exponentialRampToValueAtTime(0.0001, when + 0.07); param.linearRampToValueAtTime(0, when + 0.08);
      end = when + 0.09;
    } else {
      const low = filter('lowpass', event.cutoff || 2600);
      low.connect(env);
      osc(event.type === 'bell' ? 'sine' : 'triangle', hz(event.note)).connect(low);
      if (event.type === 'bell') { const partial = osc('sine', hz(event.note) * 2.76); const quiet = context.createGain(); quiet.gain.value = 0.25; partial.connect(quiet); quiet.connect(low); }
      param.linearRampToValueAtTime(event.level, when + 0.012);
      param.exponentialRampToValueAtTime(0.0001, when + event.decay); param.linearRampToValueAtTime(0, when + event.decay + 0.02);
      end = when + event.decay + 0.05;
    }
    for (const node of stop) { node.start(when); node.stop(end); }
    stop[stop.length - 1].onended = () => env.disconnect();
  }

  /* The built-in loops' voices, aligned to each loop's own clock: a loop at rate 1 from offset 0
   * sits at (composition time mod period), so events repeat with the picture. */
  function pumpVoices(clock) {
    if (!clock || !clock.running() || !wantSound()) return;
    const context = clock.context, now = context.currentTime, horizon = now + 0.45;
    const clockOrigin = clock.origin();
    if (clock.generation !== clock.epoch()) {
      clock.generation = clock.epoch();
      for (const voice of clock.voices) voice.until = now - 0.15;
    }
    for (const voice of clock.voices) {
      const period = voice.period, origin = clockOrigin + (voice.offset || 0);
      for (let cycle = Math.floor((voice.until - origin) / period); origin + cycle * period < horizon; cycle++) {
        for (const event of voice.events) {
          const when = origin + (cycle + event.at) * period;
          if (when >= voice.until && when < horizon) sing(context, voice.input, event, Math.max(when, now), period);
        }
      }
      voice.until = horizon;
    }
  }
  setInterval(() => {
    try {
      if (liveVoiceClock && !live.disposed) pumpVoices(liveVoiceClock);
      if (previewClock && previewClock.audio) pumpVoices(previewClock.audio);
    } catch (_) { /* a closed context; the next launch rebuilds the voices */ }
  }, 120);

  // Native analysis remains attached to the resident source. Generated voices
  // instead follow each persistent deck, including both sides of a handoff.
  function attachLiveVoice(node, context) {
    if (!node.audio.analyser) {
      node.audio.analyser = context.createAnalyser(); node.audio.analyser.fftSize = 256;
      node.audio.samples = new Float32Array(256);
      node.audio.source.connect(node.audio.analyser);
    }
    attachDeckVoice(node.active, context);
  }
  function attachDeckVoice(deck, context) {
    if (!deck || !deck.binding || deck.enteredAt === null || !context) return;
    const item = deck.item, old = liveVoices.get(deck);
    if (old && old.item === item && old.binding === deck.binding) {
      refreshVoiceClock(); return;
    }
    if (old) { old.input.disconnect(); liveVoices.delete(deck); }
    if (builtins.includes(item)) {
      const input = context.createGain(); input.connect(deck.binding.filter || deck.binding.pan);
      liveVoices.set(deck, {item, binding: deck.binding, period: item.quantized.seconds,
        events: VOICES[item.name], input, until: context.currentTime - 0.15,
        offset: live.clock.simTime - deck.media.currentTime});
    }
    refreshVoiceClock();
  }
  function detachLiveVoice(deck) {
    const voice = liveVoices.get(deck);
    if (!voice) return;
    liveVoices.delete(deck); voice.input.disconnect();
    refreshVoiceClock();
  }
  function refreshVoiceClock() {
    if (!live.audio.context) return;
    const decks = new Set([...live.nodes.values()].flatMap(node => node.decks));
    for (const [deck, voice] of liveVoices) if (!decks.has(deck) || deck.item !== voice.item) {
      voice.input.disconnect(); liveVoices.delete(deck);
    }
    // Adding a voice must not replay the lookahead window of its siblings. Only
    // an actual live clock epoch change resets their scheduling horizons.
    if (!liveVoiceClock || liveVoiceClock.context !== live.audio.context) {
      liveVoiceClock = {context: live.audio.context, voices: [], generation: live.generation,
        running: () => live.running, origin: () => live.origin, epoch: () => live.generation};
    }
    liveVoiceClock.voices = [...liveVoices.values()];
    if (session) session.clock = liveVoiceClock;
  }

  // ---- The runtime hook ------------------------------------------------------

  root.__sharedEngineUnavailable =
    'The studio plays every loop with its authored framing; the panel framing sweep is not included.';
  // Export consumers keep the plan's source objects through their asynchronous
  // reads. Their files must survive a later selection without a strong cache.
  const exportedMedia = new WeakMap();
  function exportPlan(current) {
    const plan = structuredClone(current.plan);
    for (const source of plan.sources) {
      const item = current.bySha.get(source.sha256);
      exportedMedia.set(source, {file: item.file, type: item.type, sha256: item.sha256});
    }
    return plan;
  }
  root.compositionIO = {
    maxMediaBytes: MAX_TOTAL_BYTES,
    plan() {
      if (pendingSelection || (!session && !exportFailure))
        return new Promise((resolve, reject) => { waiting.push({resolve, reject}); });
      return exportFailure ? Promise.reject(exportFailure) : Promise.resolve(exportPlan(session));
    },
    async bytes(source) {
      const item = exportedMedia.get(source);
      if (!item) throw new Error(`Missing media: ${source.id}`);
      const buffer = await item.file.arrayBuffer();
      digests.set(buffer, item.sha256);
      return buffer;
    },
    async digest(buffer) {
      return digests.get(buffer) ?? hex(await crypto.subtle.digest('SHA-256', buffer));
    },
    type(source) {
      const item = exportedMedia.get(source);
      return item ? item.type : null;
    },
  };

  // ---- Composition: selection -> plan ----------------------------------------------

  /* {layouts, slice} for the selection. A roll frames strips with its own preset values;
   * the authored family and a visitor's layout file come from their sources unchanged. */
  function arrangement(sel) {
    const C = compiler(), count = sel.loops.length;
    if (sel.family === OWN_FAMILY) return C.layoutFromFile(layout.own.data, count, layout.own.name);
    if (sel.family === 'strips' && sel.style) {
      const preset = stripsPreset(sel.style, C.PRESET_FORMAT);
      return {layouts: C.stripsLayouts(count, preset), slice: C.stripsSlice(count, preset)};
    }
    return C.layoutEntry(layout.bundle, sel.family, count);
  }

  let pendingCompilation = null;
  function compileInput(input) {
    // Keep controls and the currently playing field responsive while resolving the full timeline.
    if (typeof root.Worker !== 'function') return Promise.resolve(compiler().compile(input));
    let worker;
    try { worker = new Worker('compiler.js'); }
    catch (_) { return Promise.resolve(compiler().compile(input)); }
    return new Promise((resolve, reject) => {
      const job = {cancel: () => {
        finish(); reject(new DOMException('Compilation superseded', 'AbortError'));
      }};
      const finish = () => {
        worker.terminate();
        if (pendingCompilation === job) pendingCompilation = null;
      };
      pendingCompilation = job;
      worker.onmessage = ({data}) => {
        finish();
        if (data.error) reject(new Error(data.error)); else resolve(data.plan);
      };
      worker.onerror = event => {
        event.preventDefault(); finish();
        // A browser or host may forbid workers; retain the existing local compiler in that case.
        try { resolve(compiler().compile(input)); } catch (error) { reject(error); }
      };
      worker.postMessage(input);
    });
  }

  // Loop k (k-th panel) plays in cell loop-k; with sound, the plan carries the spatial mix.
  async function compile(sel, items, withSound) {
    const C = compiler();
    const ids = items.map((_, index) => `loop-${index + 1}`);
    const sources = items.map((item, index) => ({id: `source-${index + 1}`,
      path: `media/${item.sha256}.${item.suffix}`, sha256: item.sha256, kind: 'video',
      duration: item.quantized.duration}));
    const entry = arrangement(sel);
    const named = new Set(entry.layouts.portrait.cells.map(cell => cell.loop));
    const layouts = named.size === ids.length && ids.every(id => named.has(id)) ? entry.layouts :
      C.bindLayouts(entry.layouts, ids);
    const input = {sources, frames, fps: FPS, layouts,
      loops: sources.map((source, index) => ({id: ids[index], source: source.id}))};
    if (entry.slice) input.slice = entry.slice;
    const plan = await compileInput(input);
    for (const [index, source] of plan.sources.entries()) {
      source.bytes = items[index].size;
      if (withSound) source.audio_stream = items[index].audioStream || null;
    }
    if (withSound) {
      Object.assign(plan, {plan_version: 2, engine_version: '1.1.0', audio: {mode: 'spatial_loops',
        master_volume: '1', spatial_panning: true,
        per_loop: Object.fromEntries(plan.tracks.map(track => [track.id, {gain: loopGain(items.length), mute_on_hold: true}]))}});
    }
    return plan;
  }

  const selectedItems = (sel = selection, sourcePool = pool()) => (sel ?
    sel.loops.map((index, slot) => sel.retained?.get(slot) || sourcePool[index]).filter(Boolean) : []);
  const itemsReady = items => items.length > 0 && items.every(item => item.sha256);

  function replaceSelectionItem(sel, slot, index) {
    const retained = new Map(sel.retained);
    retained.delete(slot);
    return {...sel, loops: sel.loops.map((old, at) => at === slot ? index : old), retained};
  }

  function residentSelection(requested, items, sourcePool) {
    const retained = new Map();
    const loops = items.map((item, slot) => {
      let index = sourcePool.indexOf(item);
      if (index < 0) index = sourcePool.findIndex(candidate =>
        item.clip && candidate.clip ? item.clip.id === candidate.clip.id :
          Boolean(item.sha256) && item.sha256 === candidate.sha256);
      // A deferred old variant or a resident from the previous source pool
      // remains exact. Never put its bytes into the newly requested pool item.
      if (sourcePool[index] !== item) retained.set(slot, item);
      return index < 0 ? null : index;
    });
    return {...requested, loops, retained};
  }

  function residentAdmission(items, r) {
    const current = items.map((_, index) => r.nodes.get(`loop-${index + 1}`)?.item);
    const residentHashes = new Set([...r.nodes.values()].map(node => node.item?.sha256));
    const wanted = new Set(items.map(item => item.sha256));
    const aligned = current.map(item => item && wanted.has(item.sha256) ? item : null);
    const used = new Set(aligned.filter(Boolean).map(item => item.sha256));
    const fresh = items.filter(item => !residentHashes.has(item.sha256));
    // Keep existing ownership even for a permutation or a shrinking shuffle.
    // Moving an occupied source can otherwise leave duplicate residents when
    // its old slot's replacement fails or a later intent cancels retirement.
    items.forEach((item, index) => {
      if (!aligned[index] && fresh.includes(item) && !used.has(item.sha256)) {
        aligned[index] = item; used.add(item.sha256);
      }
    });
    aligned.forEach((item, index) => {
      if (item) return;
      const next = fresh.find(candidate => !used.has(candidate.sha256)) || current[index];
      if (next && !used.has(next.sha256)) { aligned[index] = next; used.add(next.sha256); }
    });
    return aligned.every(Boolean) ? aligned : null;
  }

  /* Compile layout/export metadata, then reconcile residents in place. The live
   * session owns native loops; editing metadata never restarts its global clock. */
  async function launch({atLoopBoundary = false, shareMix} = {}) {
    const bounded = boundedSelection(selection);
    if (bounded !== selection) { selection = bounded; renderControls(); }
    const token = ++launches, r = runtime(), requested = selection, sourcePool = pool();
    const items = selectedItems(requested, sourcePool);
    const ownsIntent = () => token === launches && selection === requested && pool() === sourcePool;
    let published = false, attempted = false, settledCohort = null;
    const ownsCohort = value => value && r.revision === value.revision && r.plan === value.plan &&
      r.nodes.size === value.cohort.length && value.cohort.every(({id, node, deck, item, source, url, epoch, residentIdentity}) =>
        r.nodes.get(id) === node && node.item === item && node.source === source &&
        ((node.active === deck && deck.url === url && deck.sourceEpoch === epoch) ||
          // A verified decoder rescue transfers this opaque identity without
          // changing the resident or its bytes. A new admission cannot inherit
          // it, and still has to satisfy the revision and intent fences above.
          (residentIdentity && node.residentIdentity === residentIdentity &&
            node.active?.residentIdentity === residentIdentity)));
    const finish = () => {
      if (token !== launches) return;
      if (!published && !ownsIntent()) return;
      const previousCurrent = session && r.plan === session.plan && r.nodes.size === session.byTrack.size &&
        [...session.byTrack].every(([id, item]) => r.nodes.get(id)?.active && r.nodes.get(id).item === item);
      // A compiler/admission refusal may leave the previous accepted cohort
      // entirely intact. Restore its metadata, never a superseding user intent.
      if (!published && previousCurrent) {
        pendingRollVersion = null;
        selection = residentSelection(session.selection, [...session.byTrack.values()], sourcePool);
        writeUrl(session.mix);
        renderControls();
      } else if (!published && ownsCohort(settledCohort)) {
        // Even if export compilation fails, describe the actual mixed field.
        if (pendingRollVersion) { rollVersion = pendingRollVersion; pendingRollVersion = null; }
        selection = residentSelection(requested, settledCohort.cohort.map(({item}) => item), sourcePool);
        writeUrl(formatMix(selection.family, selection.loops));
        renderControls();
      }
      pendingSelection = false;
      if (published || previousCurrent) {
        exportFailure = null;
        waiting.splice(0).forEach(({resolve}) => resolve(exportPlan(session)));
      } else if (attempted) {
        // A prior export remains readable, but it cannot represent a field
        // changed by partial admission whose new metadata did not compile.
        exportFailure = new Error('The current composition is not ready to export. Try another edit.');
        waiting.splice(0).forEach(({reject}) => reject(exportFailure));
      }
      renderPreview(); sync();
    };
    pendingSelection = true;
    if (pendingCompilation) pendingCompilation.cancel();
    renderPreview();
    if ((!layout.bundle && !layout.own) || !selection) { finish(); return false; }
    if (!itemsReady(items)) {
      if (sourcePool === builtins && builtinRecording) {
        // Recording is preparation, not a refused edit. Keep this intent and
        // its export waiters pending, just as for a library fetch below.
        await builtinRecording;
        if (!ownsIntent()) return false;
        if (itemsReady(items)) return launch({atLoopBoundary, shareMix});
      } else if (usingLibrary() && items.length) {
        const ok = await loadClips(items);
        if (token !== launches) return false;
        // A local import can change pools while this library fetch is pending.
        // Its completed batch owns the next launch, never the partial pool.
        if (pool() !== sourcePool) { finish(); return false; }
        if (ok) return launch({atLoopBoundary, shareMix});
        repairSelection();
      }
      finish();
      return false;
    }
    attempted = true;
    try {
      let admission = residentAdmission(items, r), plan;
      while (ownsIntent()) {
        if (!admission) return false;
        plan = await compile(requested, admission, sound.unlocked);
        if (!ownsIntent()) return false;
        // An older handoff can finish while the compiler is working. Recheck
        // ownership before submitting this intent to the serialized runtime.
        const latest = residentAdmission(items, r);
        if (latest && latest.every((item, index) => item === admission[index])) break;
        admission = latest;
      }
      if (!ownsIntent()) return false;
      const reordered = admission.some((item, index) => item !== items[index]);
      r.setSound({enabled: wantSound(), volume: sound.volume});
      const completed = await r.reconcile({plan, items: admission, playing: !hold && !paused, atLoopBoundary});
      if (!ownsIntent()) return false;
      const revision = r.revision;
      const cohort = plan.tracks.map(track => {
        const node = r.nodes.get(track.id), deck = node?.active;
        return {id: track.id, node, deck, item: node?.item, source: node?.source,
          url: deck?.url, epoch: deck?.sourceEpoch, residentIdentity: node?.residentIdentity};
      });
      // Initial admission may have no outgoing resident to keep. Do not export
      // a requested source which never became a real resident.
      if (cohort.some(({node, deck, item}) => !node || !deck || !item)) return false;
      settledCohort = {plan, revision, cohort};
      const actualItems = cohort.map(({item}) => item);
      const changed = actualItems.some((item, index) => item !== admission[index]);
      const acceptedSelection = residentSelection(requested, actualItems, sourcePool);
      const acceptedPlan = changed ? await compile(acceptedSelection, actualItems, sound.unlocked) : plan;
      if (!ownsIntent() || !ownsCohort(settledCohort)) return false;
      // Reconciliation can retain one outgoing clip and admit its siblings.
      // Repair only metadata, including compiled loop spans, from that cohort.
      r.plan = acceptedPlan;
      acceptedPlan.tracks.forEach((track, index) => { cohort[index].node.span = track.spans?.[0] ?? null; });
      session = {plan: acceptedPlan, selection: acceptedSelection, sound: sound.unlocked, token, clock: null,
        bySha: new Map(actualItems.map(item => [item.sha256, item])),
        byTrack: new Map(cohort.map(({id, item}) => [id, item]))};
      selection = acceptedSelection;
      if (pendingRollVersion) { rollVersion = pendingRollVersion; pendingRollVersion = null; }
      promoteAudioPlan(); refreshVoiceClock();
      if (shareMix !== undefined || changed || reordered)
        writeUrl(shareMix || changed || reordered ? formatMix(selection.family, selection.loops) : null);
      session.mix = new URLSearchParams(root.location.search).get('mix');
      published = true;
      renderControls();
      if (r.ready) studio.dataset.phase = 'playing';
      if (usingLibrary()) prefetchNext();
      return completed;
    } catch (error) {
      if (token === launches && error.name !== 'AbortError') toast(oneLine(error.message || error));
      return false;
    } finally {
      finish();
    }
  }
  function guardAll() { const r = runtime(); if (r) for (const node of r.nodes.values()) guardMute(node.media); }

  // ---- Rolls and edits ------------------------------------------------------------

  function writeUrl(mix) {
    if (!root.history || !history.replaceState || !selection) return;
    const params = new URLSearchParams(root.location.search);
    params.set('seed', String(selection.seed));
    params.delete('rv');
    if (mix && !own.length && selection.loops.every(Number.isInteger) &&
        new Set(selection.loops).size === selection.loops.length) params.set('mix', mix);
    else params.delete('mix');
    // ?rv sits right after ?seed: the two together name a roll.
    const ordered = new URLSearchParams();
    for (const [key, value] of params) {
      ordered.append(key, value);
      if (key === 'seed' && rollVersion >= 2) ordered.append('rv', String(rollVersion));
    }
    history.replaceState(null, '', `${root.location.pathname}?${ordered}`);
  }
  function freshSeed() {
    const value = new Uint32Array(1);
    if (root.crypto && crypto.getRandomValues) crypto.getRandomValues(value); else value[0] = Math.random() * 2 ** 32;
    return value[0];
  }

  const rollFor = (seed, version = rollVersion) => (usingLibrary() ?
    rollLibrary(seed, familyCounts(), library.clips, [...library.broken], version) :
    rollComposition(seed, familyCounts(), pool().length, version));
  // A shuffle takes the seed whose clips were prefetched, when there is one. A fresh seed is a current roll.
  function nextSeed() {
    const seed = library.next ?? freshSeed();
    library.next = null;
    return seed;
  }

  // `count` loops not in `loops`: chosen by their tags from the library, else at random.
  function moreLoops(loops, count, family, exclude = [], random = seededRandom(freshSeed())) {
    if (usingLibrary()) {
      return chooseClips(library.clips, count, family, random, loops, [...library.broken, ...exclude]);
    }
    return shuffled(pool().map((_, index) => index).filter(index => !loops.includes(index) && !exclude.includes(index)),
      random).slice(0, count);
  }

  // A shuffle (no seed given) is a fresh draw and therefore a current roll; an explicit seed replays
  // under the version its link named.
  function roll(seed) {
    const fresh = seed === undefined, version = fresh ? ROLL_VERSION : rollVersion;
    if (fresh) seed = nextSeed();
    let rolled = rollFor(seed, version);
    if (!rolled) { toast('Add one more video to play.'); return; }
    pendingRollVersion = version;
    if (manualPopulation && selection) {
      const count = selection.loops.length;
      const family = layout.families[rolled.family].counts.includes(count) ? rolled.family : selection.family;
      rolled = {...rolled, family, loops: moreLoops([], count, family)};
    }
    selection = rolled;
    renderControls();
    launch({shareMix: manualPopulation});
  }
  function edited() {
    renderControls();
    launch({shareMix: true});
  }

  function setCount(target) {
    if (!selection) return;
    manualPopulation = true;
    for (const node of live.nodes.values()) live.setResting(node.id, false);
    const counts = layout.families[selection.family].counts;
    const offered = counts.filter(count => count <= available());
    if (!offered.length) return;
    const wanted = Math.max(offered[0], Math.min(offered[offered.length - 1], target));
    if (wanted !== target) {
      if (target > live.maxForeground && live.maxForeground === 4) toast('Up to four panels on this device.');
      else if (target > available() && counts.includes(target)) toast(own.length ? 'Add more videos for more panels.' : 'That is every loop.');
      else toast(`${familyLabel(selection.family, layout.own && layout.own.name)}: ${offered[0]} to ${offered[offered.length - 1]} panels.`);
      return;
    }
    const step = target > selection.loops.length ? 1 : -1;
    let count = selection.loops.length;
    while (count !== target) { count += step; if (offered.includes(count)) break; }
    if (count === selection.loops.length) return;
    selection = {...selection, loops: count > selection.loops.length ?
      selection.loops.concat(moreLoops(selection.loops, count - selection.loops.length, selection.family)) :
      selection.loops.slice(0, count), retained: new Map([...(selection.retained || [])].filter(([slot]) => slot < count))};
    edited();
  }

  function setFamily(family) {
    if (!selection || !layout.families[family]) return;
    const counts = layout.families[family].counts.filter(count => count <= available());
    if (!counts.length) { toast(`${familyLabel(family)} needs ${layout.families[family].counts[0]} loops.`); return; }
    const count = nearestCount(counts, selection.loops.length);
    if (count !== selection.loops.length) toast(`${familyLabel(family, layout.own && layout.own.name)}: ${count} panels.`);
    selection = {...selection, family, loops: count <= selection.loops.length ? selection.loops.slice(0, count) :
      selection.loops.concat(moreLoops(selection.loops, count - selection.loops.length, family)),
      retained: new Map([...(selection.retained || [])].filter(([slot]) => slot < count))};
    edited();
  }

  // Tapping replaces only this resident when a spare logical clip is available.
  function rerollPanel(index) {
    if (!selection || index < 0 || index >= selection.loops.length) return;
    const others = selection.loops.filter((_, at) => at !== index);
    const [fresh] = moreLoops(others, 1, selection.family, [selection.loops[index]]);
    if (fresh === undefined) { toast('Every available clip is already on screen.'); return; }
    selection = replaceSelectionItem(selection, index, fresh);
    edited();
  }

  // ---- Preview: the built-in pictures drawn live until their recordings are ready ----

  const PREVIEW_SIZE = 384;
  const orientationNow = () => (ui.frame.clientWidth >= ui.frame.clientHeight ? 'landscape' : 'portrait');
  const fraction = value => { const [n, d = 1] = String(value).split('/').map(Number); return n / d; };

  function renderPreview() {
    // The generated pictures stand in only for the built-ins; library clips need no preview.
    const showing = !own.length && !library.active && selection && (recordMode === 'canvas' || !itemsReady(selectedItems()) ||
      studio.dataset.phase !== 'playing');
    if (!showing) {
      if (ui.preview.childElementCount) {
        ui.preview.classList.remove('on');
        setTimeout(() => { if (!ui.preview.classList.contains('on')) ui.preview.replaceChildren(); }, FADE_MS + 60);
      }
      previewClock = null;
      return;
    }
    let entry;
    try { entry = arrangement(selection); } catch (_) { return; }
    const orientation = orientationNow(), cells = entry.layouts[orientation].cells;
    const key = `${orientation}|${selection.family}|${selection.loops.join('.')}|${JSON.stringify(selection.style)}`;
    if (ui.preview.dataset.key !== key) {
      ui.preview.dataset.key = key;
      ui.preview.replaceChildren(...cells.map((cell, index) => {
        const box = document.createElement('div'), canvas = document.createElement('canvas');
        const [x, y, w, h] = cell.rect.map(fraction);
        box.className = 'loop'; box.dataset.loopId = `loop-${index + 1}`;
        Object.assign(box.style, {left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%`});
        canvas.width = canvas.height = PREVIEW_SIZE;
        canvas.dataset.loop = builtins[selection.loops[index]].name;
        box.append(canvas);
        return box;
      }));
      if (!previewClock) previewClock = {start: performance.now(), audio: null};
      if (recordMode === 'canvas') fallbackAudio();
    }
    ui.preview.classList.add('on');
  }

  // Without MediaRecorder the preview is the composition; its voices play through a studio context.
  function fallbackAudio() {
    if (recordMode !== 'canvas' || !previewClock || !wantSound() || !root.AudioContext) return;
    if (!previewClock.context) previewClock.context = live.audio.context;
    const context = previewClock.context;
    if (!context) return;
    if (!hold && !paused && !live.running) live.start().catch(() => {});
    context.resume().catch(() => {});
    const mix = mixer(context), origin = context.currentTime - (performance.now() - previewClock.start) / 1000;
    if (previewClock.audio) previewClock.audio.voices.forEach(voice => voice.input.disconnect());
    const landscape = orientationNow() === 'landscape';
    const voices = Array.from(ui.preview.querySelectorAll('canvas'), (canvas, index) => {
      const item = builtins.find(entry => entry.name === canvas.dataset.loop);
      const box = canvas.parentElement, pan = context.createStereoPanner(), gain = context.createGain();
      pan.pan.value = landscape ? 2 * (box.offsetLeft + box.offsetWidth / 2) / ui.preview.clientWidth - 1 : 0;
      gain.gain.value = fraction(loopGain(selection.loops.length));
      pan.connect(gain); gain.connect(mix.input);
      return {period: item.quantized.seconds, events: VOICES[item.name], input: pan, until: 0, index};
    });
    previewClock.audio = {context, voices, generation: -1, running: () => !hold && !paused,
      origin: () => origin, epoch: () => 0};
  }

  // ---- Built-in recordings: each picture recorded once, at load, into a media blob ---

  const RECORD_SIZE = 512;
  const recordable = () => typeof MediaRecorder === 'function' && typeof HTMLCanvasElement !== 'undefined' &&
    typeof HTMLCanvasElement.prototype.captureStream === 'function' && root.isSecureContext &&
    root.crypto && crypto.subtle;
  function recorderType() {
    const types = ['video/webm;codecs=vp8', 'video/webm;codecs=vp9', 'video/webm', 'video/mp4;codecs=avc1', 'video/mp4'];
    return types.find(type => MediaRecorder.isTypeSupported(type)) || null;
  }

  // Position within a period as a fraction in [0, 1), also for times just before the start.
  const phase = (seconds, period) => (((seconds / period) % 1) + 1) % 1;
  const drawing = new Set();  // {canvas, name, period, start}
  function frameLoop(now) {
    for (const job of drawing) {
      VISUALS[job.name](job.context, job.canvas.width, phase((now - job.start) / 1000, job.period), job.period);
    }
    const still = hold || paused || reduced;
    for (const canvas of ui.preview.querySelectorAll('canvas')) {
      const item = builtins.find(entry => entry.name === canvas.dataset.loop);
      const elapsed = still ? 0 : (now - (previewClock ? previewClock.start : 0)) / 1000;
      if (still && canvas.dataset.drawn) continue;
      canvas.dataset.drawn = '1';
      VISUALS[item.name](canvas.getContext('2d'), canvas.width, phase(elapsed, item.quantized.seconds), item.quantized.seconds);
    }
    requestAnimationFrame(frameLoop);
  }
  requestAnimationFrame(frameLoop);

  async function recordOne(item, type) {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = RECORD_SIZE;
    const context = canvas.getContext('2d'), period = item.quantized.seconds;
    VISUALS[item.name](context, RECORD_SIZE, 0, period);
    const recorder = new MediaRecorder(canvas.captureStream(30), {mimeType: type, videoBitsPerSecond: 2500000});
    const chunks = [];
    let hidden = document.hidden;
    const onHide = () => { if (document.hidden) hidden = true; };
    document.addEventListener('visibilitychange', onHide);
    recorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
    const stopped = new Promise(resolve => { recorder.onstop = resolve; });
    const job = {canvas, context, name: item.name, period, start: performance.now()};
    drawing.add(job);
    recorder.start();
    job.start = performance.now();
    await delay(period * 1000 + 350);
    recorder.stop();
    await stopped;
    drawing.delete(job);
    recorder.stream.getTracks().forEach(track => track.stop());
    document.removeEventListener('visibilitychange', onHide);
    if (hidden) return false;  // a hidden tab stalls drawing; record again when visible
    const blob = new Blob(chunks, {type: recorder.mimeType || type});
    const buffer = await blob.arrayBuffer();
    Object.assign(item, {file: blob, type: blob.type.split(';')[0], suffix: blob.type.includes('mp4') ? 'mp4' : 'webm',
      size: blob.size, sha256: hex(await crypto.subtle.digest('SHA-256', buffer)), audioStream: null});
    return true;
  }

  async function recordBuiltins() {
    const type = recordable() && recorderType();
    if (!type) { recordMode = 'canvas'; renderActivity(); renderPreview(); return; }
    recordMode = 'recording';
    let todo = builtins.slice();
    while (todo.length) {
      if (document.hidden) await new Promise(resolve => document.addEventListener('visibilitychange', resolve, {once: true}));
      const results = await Promise.all(todo.map(item => recordOne(item, type).catch(() => false)));
      todo = todo.filter((_, index) => !results[index]);
      if (todo.length && results.every(ok => !ok) && !document.hidden) {
        recordMode = 'canvas'; renderActivity(); renderPreview(); return;
      }
    }
    recordMode = 'recorded';
  }

  // ---- The visitor's own files ----------------------------------------------------

  function metadata(file, type) {
    return live.withPreparation(() => new Promise(resolve => {
      const video = document.createElement('video');
      const url = URL.createObjectURL(file.slice(0, file.size, type));
      let timer = null;
      const finish = result => {
        clearTimeout(timer);
        video.onloadeddata = video.onerror = null;
        video.pause();
        video.removeAttribute('src');
        video.load();
        if (live.proof) live.record('resource-retired', null, {role: 'metadata', url,
          currentSrc: video.currentSrc, readyState: video.readyState, paused: video.paused});
        URL.revokeObjectURL(url);
        resolve(result);
      };
      video.muted = true; video.defaultMuted = true; video.playsInline = true; video.preload = 'auto';
      video.onloadeddata = () => finish(video.videoWidth > 0 && video.videoHeight > 0 &&
        Number.isFinite(video.duration) && video.duration > 0 ?
        {width: video.videoWidth, height: video.videoHeight, duration: video.duration} : null);
      video.onerror = () => finish(null);
      timer = setTimeout(() => finish(null), METADATA_TIMEOUT_MS);
      video.src = url;
      // Some mobile preload policies defer loadeddata until a muted play request.
      video.play().catch(() => {});
    }));
  }

  /* Container, codec and duration checks for both sources. Personal files decode
   * their metadata here; byte-checked library assets supply validated manifest
   * facts and wait for their real standby admission to allocate a decoder. */
  async function inspect(file, buffer, name, declared, probe, publishedFacts = null) {
    const sniff = sniffContainer(buffer);
    const type = blobType(name, declared, sniff);
    const described = sniff.codec ? `${type}, ${sniff.codec.label}${sniff.codec.string &&
      sniff.codec.string !== sniff.codec.label ? ` ${sniff.codec.string}` : ''}` : type;
    const cannot = `This browser cannot play ${name} (${described}).` +
      (sniff.codec && sniff.codec.label === 'HEVC' ? ' HEVC needs a browser with HEVC decoding (for example ' +
        'Safari, or Chrome on a Mac); an H.264 ("Most Compatible") export plays almost everywhere.' : '');
    const {decisive, queries} = playbackQueries(type, sniff);
    const answers = queries.map(query => probe.canPlayType(query));
    if (decisive ? answers[0] === '' : answers.every(answer => answer === '')) return {refusal: cannot};
    const facts = publishedFacts || await metadata(file, type);
    if (!facts) return {refusal: cannot};
    let quantized = null;
    try { quantized = quantizeDuration(facts.duration, FPS); } catch (_) { /* shorter than one frame */ }
    if (!quantized || quantized.frames < MIN_FRAMES) {
      return {refusal: `${name} was not added: it lasts ${facts.duration.toFixed(2)} s, and a loop must last at ` +
        `least ${(MIN_FRAMES / FPS).toFixed(2)} s.`};
    }
    return {sniff, type, facts, quantized};
  }

  async function admit(file, probe, refuse) {
    const name = file.name || 'unnamed video';
    const total = own.reduce((sum, loop) => sum + loop.size, 0);
    const oversized = admitSize(name, file.size, total);
    if (oversized) return refuse(oversized);
    let buffer;
    try { buffer = await file.arrayBuffer(); } catch (error) {
      return refuse(`${name} could not be read (${error.name || error}).`);
    }
    const checked = await inspect(file, buffer, name, file.type, probe);
    if (checked.refusal) return refuse(checked.refusal);
    const {sniff, type, facts, quantized} = checked;
    if (!root.crypto || !crypto.subtle) return refuse(`${name} could not be checked: this page needs HTTPS or localhost.`);
    const sha256 = hex(await crypto.subtle.digest('SHA-256', buffer));
    const twin = own.find(loop => loop.sha256 === sha256);
    if (twin) {
      return refuse(`${name} was not added: it is the same video as ${twin.name}. Each loop needs its own ` +
        'video; nothing is duplicated.');
    }
    own.push({file, name, type, suffix: mediaSuffix(name, sniff), size: file.size, sha256,
      codec: sniff.codec ? sniff.codec.label : null, container: sniff.container, audioStream: audioStream(buffer),
      ...facts, quantized});
    return null;
  }

  async function useLayoutFile(file) {
    const name = file.name || 'layout file';
    try {
      const C = compiler(), data = C.loadLayoutBytes(await file.arrayBuffer(), name);
      const info = C.describeLayoutFile(data, name);
      const counts = allowedCounts(info.counts);
      if (!counts.length) throw new Error(`This layout needs more than ${live.maxForeground} panels. Choose a smaller layout on this device.`);
      layout.own = {name, data, info};
      layout.families[OWN_FAMILY] = {counts, sourceCounts: info.counts, label: familyLabel(OWN_FAMILY, name)};
      renderControls();
      setFamily(OWN_FAMILY);
      toast(`Layout ${name} in use.`);
    } catch (error) {
      toast(oneLine(error.message || error, name));
    }
  }

  // Batches are checked one at a time, so the size cap counts every loop accepted before them.
  let admissions = Promise.resolve();
  async function addFiles(list) {
    const files = Array.from(list || []);
    const layouts = files.filter(file => /\.json$/i.test(file.name || '') || file.type === 'application/json');
    const videos = files.filter(file => !layouts.includes(file));
    for (const file of layouts) await useLayoutFile(file);
    if (!videos.length) return;
    busy += 1; renderControls();
    const previous = admissions;
    let release;
    admissions = new Promise(resolve => { release = resolve; });
    try {
      await previous;
      const refusals = [], before = own.length;
      const probe = document.createElement('video');
      for (const file of videos) {
        try { await admit(file, probe, message => { refusals.push(message); }); } catch (error) {
          refusals.push(`${file.name} could not be checked (${error.message || error}).`);
        }
      }
      lastRefusals = refusals;
      const added = own.length - before;
      if (refusals.length) toast(refusals[0] + (refusals.length > 1 ? ` (+${refusals.length - 1} more not added)` : ''));
      else if (added) toast(`${plural(added, 'loop')} added. Nothing was uploaded.`);
      if (added) {
        // Retain the entire local pool; the live device limit bounds its residents.
        const family = selection && layout.families[selection.family] &&
          layout.families[selection.family].counts.includes(Math.min(own.length, live.maxForeground)) ? selection.family : 'strips';
        const count = nearestCount(layout.families[family].counts.filter(value => value <= own.length), own.length);
        if (count !== null) {
          selection = {seed: freshSeed(), family, loops: own.map((_, index) => index).slice(-count),
            style: selection ? selection.style : {z1: '2', jitter: '0', reverse: false}};
          rollVersion = ROLL_VERSION; pendingRollVersion = null;
          writeUrl(null);
          launch();
        }
      }
    } finally {
      release();
      busy -= 1; renderControls();
    }
  }

  ui.add.addEventListener('click', () => ui.files.click());
  ui.files.addEventListener('change', () => {
    const chosen = Array.from(ui.files.files);
    ui.files.value = '';
    addFiles(chosen);
  });
  let dragDepth = 0;
  document.addEventListener('dragenter', event => { event.preventDefault(); dragDepth += 1; studio.classList.add('dragging'); });
  document.addEventListener('dragover', event => event.preventDefault());
  document.addEventListener('dragleave', () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) studio.classList.remove('dragging'); });
  document.addEventListener('drop', event => {
    event.preventDefault();
    dragDepth = 0; studio.classList.remove('dragging');
    addFiles(event.dataTransfer && event.dataTransfer.files);
  });

  // ---- Library clips: fetched per roll, checked like the visitor's files, kept in a small LRU ----

  const assetFor = item => loopMode === 'boomerang' && item.clip.variants &&
    !library.failedAssets.has(item.clip.variants.boomerang.id) ? item.clip.variants.boomerang : item.clip;

  function useLibrary(clips) {
    library.active = true;
    library.clips = clips;
    library.items = clips.map((clip, index) => ({name: clip.id, index, clip, file: null, sha256: null}));
    recordMode = 'library';
  }

  // Clips the page must keep: on screen, in the playing plan, or prefetched for the next shuffle.
  function keptIds() {
    const ids = new Set(library.prefetch);
    if (selection && usingLibrary()) for (const item of selectedItems()) ids.add(item.name);
    if (session) for (const item of session.bySha.values()) ids.add(item.name);
    for (const node of live.nodes.values()) for (const deck of node.decks) if (deck.item) ids.add(deck.item.name);
    return ids;
  }

  function remember(item) {
    library.cache.delete(item.name);
    library.cache.set(item.name, item);
    if (library.cache.size <= LIBRARY_CACHE) return;
    const kept = keptIds();
    for (const [id, old] of library.cache) {
      if (library.cache.size <= LIBRARY_CACHE) break;
      if (kept.has(id)) continue;
      library.cache.delete(id);
      Object.assign(old, {file: null, sha256: null});
    }
  }

  // A newer roll no longer wants these in-flight fetches.
  function abortStale(wanted) {
    for (const [id, job] of library.inflight) if (!wanted.has(id)) job.controller.abort();
  }

  /* Prefetch verifies the published asset's bytes, SHA-256 prefix and browser
   * codec support, using its already validated manifest dimensions and duration.
   * Actual decoding is checked by the persistent standby's admission gates, so
   * caching a spare clip does not allocate another temporary video decoder. */
  let activeFetches = 0;
  const fetchQueue = [];
  function boundedFetch(task) {
    return new Promise((resolve, reject) => {
      fetchQueue.push({task, resolve, reject});
      pumpFetches();
    });
  }
  function pumpFetches() {
    while (activeFetches < 2 && fetchQueue.length) {
      const job = fetchQueue.shift(); activeFetches++;
      Promise.resolve().then(job.task).then(job.resolve, job.reject).finally(() => {
        activeFetches--; pumpFetches();
      });
    }
  }
  async function fetchAsset(item, asset, controller) {
    if (controller.signal.aborted) return false;
    library.requested += 1;
    const requestUrl = new URL(`library/${asset.file}`, document.baseURI).href;
    const recordAbort = () => live.record('asset-request-aborted', null, {url: requestUrl});
    if (live.proof) controller.signal.addEventListener('abort', recordAbort, {once: true});
    let buffer;
    try {
      const response = await fetch(requestUrl, {signal: controller.signal, redirect: 'error'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      buffer = await response.arrayBuffer();
    } finally {
      if (live.proof) controller.signal.removeEventListener('abort', recordAbort);
    }
    if (buffer.byteLength !== asset.bytes) throw new Error('size differs from the manifest');
    const sha256 = hex(await crypto.subtle.digest('SHA-256', buffer));
    if (!sha256.startsWith(asset.id)) throw new Error('digest differs from the manifest');
    const file = new Blob([buffer], {type: 'video/mp4'});
    if (!library.probe) library.probe = document.createElement('video');
    const checked = await inspect(file, buffer, `${item.name}.mp4`, 'video/mp4', library.probe,
      {width: asset.width, height: asset.height, duration: asset.duration_seconds});
    if (checked.refusal) throw new Error('not playable');
    if (controller.signal.aborted) return false;
    Object.assign(item, {file, type: checked.type, suffix: 'mp4', size: buffer.byteLength, sha256,
      audioStream: audioStream(buffer), asset, ...checked.facts, quantized: checked.quantized});
    remember(item);
    return true;
  }
  function loadClip(item) {
    if (item.sha256) { remember(item); return Promise.resolve(true); }
    const running = library.inflight.get(item.name);
    if (running) return running.promise;
    const controller = new AbortController(), asset = assetFor(item);
    const job = {controller, promise: null};
    job.promise = boundedFetch(async () => {
      try { return await fetchAsset(item, asset, controller); }
      catch (error) {
        if (controller.signal.aborted || asset === item.clip) throw error;
        // A failed derivative does not exclude its admitted forward source.
        library.failedAssets.add(asset.id);
        return fetchAsset(item, item.clip, controller);
      }
    }).catch(() => {
      if (!controller.signal.aborted) library.broken.add(item.index);
      return false;
    }).finally(() => { if (library.inflight.get(item.name) === job) library.inflight.delete(item.name); });
    library.inflight.set(item.name, job);
    return job.promise;
  }

  async function loadClips(items) {
    abortStale(new Set([...items.map(item => item.name), ...library.prefetch]));
    const results = await Promise.all(items.map(loadClip));
    return results.every(Boolean);
  }

  // A clip that failed is left out from now on: its panels get other clips, or the built-ins return.
  function repairSelection() {
    if (!selection || !usingLibrary()) return;
    const bad = selection.loops.filter(index => library.broken.has(index));
    if (!bad.length) { launch({fade: false}); return; }
    const counts = familyCounts()[selection.family].filter(count => count <= available());
    if (!counts.length || available() < 1) { fallbackToGenerated(); return; }
    let kept = selection.loops.map((index, slot) => ({index, retained: selection.retained?.get(slot)}))
      .filter(({index}) => !library.broken.has(index));
    const count = counts.includes(selection.loops.length) ? selection.loops.length : nearestCount(counts, selection.loops.length);
    if (kept.length > count) kept = kept.slice(0, count);
    const loops = kept.map(({index}) => index);
    selection = {...selection, loops: loops.concat(moreLoops(loops, count - loops.length, selection.family)),
      retained: new Map(kept.flatMap(({retained}, slot) => retained ? [[slot, retained]] : []))};
    edited();
  }

  function fallbackToGenerated() {
    for (const job of library.inflight.values()) job.controller.abort();
    library.active = false;
    library.prefetch = [];
    library.next = null;
    recordMode = 'pending';
    rollVersion = ROLL_VERSION; pendingRollVersion = null;
    selection = rollFor(selection ? selection.seed : freshSeed());
    writeUrl(null);
    renderControls();
    renderPreview();
    sync();
    builtinRecording = recordBuiltins();
    launch();
  }

  /* After a roll plays, the next shuffle's seed is chosen and its clips fetched while the page is
   * idle, so the shuffle crossfades at once. Skipped when the visitor asked to save data. */
  const PREFETCH_BYTES = 8 * MIB;
  function prefetchNext() {
    if (!usingLibrary() || (root.navigator && navigator.connection && navigator.connection.saveData)) return;
    if (library.next === null) library.next = freshSeed();
    const rolled = rollFor(library.next, ROLL_VERSION);
    if (!rolled) return;
    const items = rolled.loops.map(index => library.items[index]);
    if (items.reduce((sum, item) => sum + (item.sha256 ? 0 : item.clip.bytes), 0) > PREFETCH_BYTES) return;
    library.prefetch = items.map(item => item.name);
    const idle = root.requestIdleCallback ? callback => requestIdleCallback(callback, {timeout: 2000}) :
      callback => setTimeout(callback, 300);
    idle(() => {
      if (!usingLibrary() || library.prefetch.join() !== items.map(item => item.name).join()) return;
      items.forEach(item => { loadClip(item); });
    });
  }

  // ---- Finite lives and ecological competition ------------------------------------

  function sourceEnergy(node) {
    const asset = node.item.asset;
    if (asset && Array.isArray(asset.rms_envelope) && asset.rms_envelope.length) {
      if (node.energyAsset !== asset) {
        node.energyAsset = asset;
        node.energyMaximum = Math.max(0.00001, ...asset.rms_envelope);
      }
      const index = Math.min(asset.rms_envelope.length - 1,
        Math.floor(node.media.currentTime * asset.envelope_hz));
      return asset.rms_envelope[Math.max(0, index)] / node.energyMaximum;
    }
    const audio = node.audio;
    if (audio && audio.analyser && sound.unlocked) {
      audio.analyser.getFloatTimeDomainData(audio.samples);
      let power = 0;
      for (const value of audio.samples) power += value * value;
      const rms = Math.sqrt(power / audio.samples.length);
      node.energyMaximum = Math.max(0.01, rms, (node.energyMaximum || .1) * .995);
      return rms / node.energyMaximum;
    }
    return .4;
  }

  function ecologyTick(time, dt) {
    if (!live.ready || !selection) return;
    const published = usingLibrary(), automaticSources = published || own.length > 0;
    residents.length = 0; currentLogicalIds.clear();
    for (const node of live.nodes.values()) {
      if (!node.item || !node.media) continue;
      let model = residentModels.get(node);
      if (!model) { model = {}; residentModels.set(node, model); }
      // Equal uploaded bytes may reuse a library resident and its metadata.
      // Personal cooldowns still follow the admitted content digest.
      const logicalId = published ? node.item.clip?.id || node.item.sha256 : node.item.sha256;
      currentLogicalIds.add(logicalId); model.logicalId = logicalId;
      model.id = node.id; model.index = node.ordinal - 1; model.clipKey = node.item.sha256;
      model.duration = node.media.duration || node.item.duration || node.item.quantized.seconds;
      model.age = node.birthTime === undefined ? node.media.currentTime : time - node.birthTime;
      model.energy = sourceEnergy(node);
      model.hasAudio = builtins.includes(node.item) || (node.item.asset?.has_audio ?? Boolean(node.item.audioStream));
      model.resting = node.resting; model.pending = node.busy || live.draining || pendingSelection;
      if (node.cell) {
        const rect = node.cell.rect.map(fraction);
        model.x = rect[0] + rect[2] / 2; model.y = rect[1] + rect[3] / 2;
      }
      residents.push(model);
    }
    for (const id of previousLogicalIds) if (!currentLogicalIds.has(id)) succession.depart(id, time);
    const spareIds = previousLogicalIds; previousLogicalIds = currentLogicalIds; currentLogicalIds = spareIds;
    const eligible = automaticSources && pool().some((item, index) => !selection.loops.includes(index) &&
      (!published || !library.broken.has(index)) && succession.eligible(item.clip?.id || item.sha256, time));
    const out = ecosystem.step(time, dt, residents, {
      enabled: evolving && !hold && !reduced && automaticSources, manualCount: manualPopulation,
      effects: filtersEnabled, effectSettings,
      // Admission grows the local pool before its final selection is ready.
      canReplace: eligible && !ecologicalRequest && !pendingSelection && busy === 0,
      canRest: !ecologicalRequest && busy === 0,
    });
    let leadingProminence = 0;
    for (let i = 0; i < residents.length; i++) {
      if (residents[i].hasAudio && !residents[i].resting)
        leadingProminence = Math.max(leadingProminence, out.prominence[i]);
    }
    for (let i = 0; i < residents.length; i++) {
      const node = live.nodes.get(residents[i].id);
      // Solo/tied leaders stay open; quieter rivals yield spectral space.
      const spectralPriority = !residents[i].hasAudio || residents[i].resting ? 0
        : leadingProminence > 0 ? out.prominence[i] / leadingProminence : 1;
      live.setTargetGain(node.id, out.gains[i]);
      live.setPresence(node.id, out.presence[i], spectralPriority);
    }
    if (selection.family === 'strips' && !reduced && time - lastSpaceTime >= .05 &&
        residents.length === selection.loops.length && !live.draining) {
      live.applyTerritory?.(out.space.subarray(0, residents.length));
      lastSpaceTime = time;
    }
    if (out.requests.length && !ecologicalRequest) {
      const request = out.requests[0];
      ecologicalRequest = request;
      if (request.type === 'replace') {
        const index = request.index, previous = selection;
        const others = previous.loops.filter((_, at) => at !== index);
        const cooling = [];
        pool().forEach((item, index) => {
          if (!succession.eligible(item.clip?.id || item.sha256, time)) cooling.push(index);
        });
        const [fresh] = moreLoops(others, 1, previous.family, [previous.loops[index], ...cooling], succession.random);
        if (fresh === undefined) {
          ecosystem.settle(request, false, time); ecologicalRequest = null; return;
        }
        const next = replaceSelectionItem(previous, index, fresh);
        selection = next; renderControls();
        launch({atLoopBoundary: true}).then(ok => {
          ecosystem.settle(request, ok, live.clock.simTime);
        }).finally(() => { if (ecologicalRequest === request) ecologicalRequest = null; });
      } else {
        live.setResting(request.id, request.type === 'rest');
        ecosystem.settle(request, true, time); ecologicalRequest = null;
      }
    }
  }

  function renderActivity() {
    ui.effects.setAttribute('aria-pressed', String(filtersEnabled && filtersAvailable()));
    ui.effects.disabled = !filtersAvailable();
    ui.filterTune.disabled = !filtersAvailable();
    ui.effects.title = reduced ? 'Filters paused for reduced motion' : !filtersAvailable() ?
      'Filters unavailable for this preview' : filtersEnabled ? 'Filters on' : 'Filters off';
    ui.activity.setAttribute('aria-label', evolving ? 'Hold changes' : 'Let it evolve');
    ui.activity.setAttribute('aria-pressed', String(!evolving));
    ui.activity.title = evolving ? 'Hold changes' : 'Let it evolve';
    ui.activity.textContent = evolving ? '∞' : 'Ⅱ';
    ui.loopMode.hidden = !usingLibrary() || !library.clips.some(clip => clip.variants);
    ui.loopMode.setAttribute('aria-label', loopMode === 'boomerang' ? 'Play forward loops' : 'Play boomerang loops');
    ui.loopMode.title = loopMode === 'boomerang' ? 'Boomerang loops' : 'Forward loops';
    ui.loopMode.textContent = loopMode === 'boomerang' ? '↔' : '→';
  }
  ui.activity.addEventListener('click', () => { evolving = !evolving; renderActivity(); });
  ui.effects.addEventListener('click', () => {
    if (!filtersAvailable()) return;
    filtersEnabled = !filtersEnabled;
    live.setEffects(filtersEnabled);
    const params = new URLSearchParams(root.location.search); params.set('fx', filtersEnabled ? '1' : '0');
    history.replaceState(null, '', `${root.location.pathname}?${params}`);
    renderActivity();
  });
  const filterControls = [
    ['attackSeconds', 'fx-attack', 1, ' s'], ['tail', 'fx-tail', 100, '%'],
    ['gainDepth', 'fx-gain', 100, '%'], ['lowpassDepth', 'fx-lowpass', 100, '%'],
    ['brightnessDepth', 'fx-brightness', 100, '%'], ['saturationDepth', 'fx-saturation', 100, '%'],
    ['blurPx', 'fx-blur', 1, ' px'],
  ];
  function renderFilterSettings() {
    for (const [key, id, scale, unit] of filterControls) {
      const value = Number((effectSettings[key] * scale).toFixed(2));
      $(`#${id}`).value = String(value); $(`#${id}-value`).textContent = `${value}${unit}`;
    }
    $('#fx-curve').value = effectSettings.curve;
  }
  function applyFilterSettings(patch) {
    effectSettings = live.setEffectSettings(patch);
    const query = effectSettingsSearch(root.location.search, effectSettings);
    history.replaceState(null, '', `${root.location.pathname}${query ? `?${query}` : ''}`);
    renderFilterSettings();
  }
  for (const [key, id, scale] of filterControls) {
    $(`#${id}`).addEventListener('input', event => applyFilterSettings({[key]: Number(event.target.value) / scale}));
  }
  $('#fx-curve').addEventListener('change', event => applyFilterSettings({curve: event.target.value}));
  $('#fx-reset').addEventListener('click', () => applyFilterSettings(root.SimvltaneaPresence.DEFAULT_SETTINGS));
  $('#fx-close').addEventListener('click', () => ui.filterDialog.close());
  ui.filterTune.addEventListener('click', () => {
    if (!filtersAvailable()) return;
    setAbout(false); renderFilterSettings(); ui.filterDialog.showModal();
    ui.filterTune.setAttribute('aria-expanded', 'true'); wake();
  });
  ui.filterDialog.addEventListener('close', () => {
    ui.filterTune.setAttribute('aria-expanded', 'false'); ui.filterTune.focus(); wake();
  });
  ui.loopMode.addEventListener('click', () => {
    loopMode = loopMode === 'boomerang' ? 'forward' : 'boomerang';
    for (const job of library.inflight.values()) job.controller.abort();
    library.inflight.clear(); library.cache.clear(); library.broken.clear(); library.prefetch = []; library.next = null;
    library.items = library.clips.map((clip, index) => ({name: clip.id, index, clip, file: null, sha256: null}));
    if (selection) selection = {...selection, retained: new Map()};
    const params = new URLSearchParams(root.location.search); params.set('loop', loopMode);
    history.replaceState(null, '', `${root.location.pathname}?${params}`);
    renderActivity(); launch({shareMix: true});
  });

  // ---- Controls -------------------------------------------------------------------

  function renderControls() {
    renderActivity();
    const families = Object.keys(layout.families);
    const current = Array.from(ui.families.children, button => button.dataset.family).join(' ');
    if (current !== families.join(' ')) {
      ui.families.replaceChildren(...families.map(name => {
        const button = document.createElement('button');
        button.type = 'button'; button.dataset.family = name; button.setAttribute('role', 'radio');
        button.setAttribute('aria-label', layout.families[name].label);
        button.innerHTML = ICONS[name] || ICONS.file;
        return button;
      }));
    }
    for (const button of ui.families.children) {
      const on = Boolean(selection) && button.dataset.family === selection.family;
      button.setAttribute('aria-checked', String(on)); button.tabIndex = on || !selection ? 0 : -1;
    }
    const count = selection ? selection.loops.length : 0;
    const counts = selection ? layout.families[selection.family].counts.filter(value => value <= available()) : [];
    ui.panels.textContent = String(count || '');
    ui.panels.setAttribute('aria-label', `${plural(count, 'panel')}`);
    ui.fewer.disabled = !counts.some(value => value < count);
    ui.more.disabled = !counts.some(value => value > count) && !(own.length && selection &&
      layout.families[selection.family].counts.some(value => value > count));
    studio.dataset.family = selection ? selection.family : '';
    studio.dataset.panels = String(count);
    studio.dataset.busy = busy > 0 ? 'true' : 'false';
  }
  ui.families.addEventListener('click', event => {
    const button = event.target.closest('button[data-family]');
    if (!button || !selection) return;
    // The checked family cycles to the next, so one visible icon suffices on a narrow phone.
    const names = Object.keys(layout.families);
    setFamily(button.dataset.family !== selection.family ? button.dataset.family :
      names[(names.indexOf(selection.family) + 1) % names.length]);
  });
  ui.families.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const buttons = Array.from(ui.families.children), at = buttons.indexOf(document.activeElement);
    const next = buttons[(at + (event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length];
    setFamily(next.dataset.family); next.focus();
  });
  ui.shuffle.addEventListener('click', () => roll());
  ui.fewer.addEventListener('click', () => selection && setCount(selection.loops.length - 1));
  ui.more.addEventListener('click', () => selection && setCount(selection.loops.length + 1));
  ui.fullscreen.hidden = !document.fullscreenEnabled;
  function toggleFullscreen() {
    if (!document.fullscreenEnabled) return;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen().catch(() => {});
  }
  ui.fullscreen.addEventListener('click', toggleFullscreen);
  document.addEventListener('fullscreenchange', () => {
    ui.fullscreen.setAttribute('aria-label', document.fullscreenElement ? 'Exit full screen' : 'Full screen');
  });

  function togglePlay() {
    const r = runtime();
    if (hold) { hold = false; paused = false; studio.classList.remove('held'); unlock(); launch({fade: false}); sync(); return; }
    if (!r || !r.ready) {
      paused = !paused;
      if (r) { if (paused) r.pause(); else r.play().catch(() => {}); }
      sync(); return;
    }
    if (r.running) { paused = true; r.pause(); }
    else { paused = false; r.play().catch(() => {}); }
    sync();
  }
  window.addEventListener('message', event => {
    if (event.source !== window.parent || event.origin !== location.origin || event.data?.type !== 'simvltanea:pause') return;
    paused = true; const r = runtime(); if (r) r.pause(); sync();
  });
  ui.play.addEventListener('click', togglePlay);
  ui.start.addEventListener('click', togglePlay);

  // Every first gesture turns the sound on; the page itself never needs one to play.
  const firstGesture = event => {
    if (sound.unlocked && (!live.audio.context || live.audio.context.state === 'running')) return;
    if (event.target.closest && event.target.closest('#speaker, #about, #help, #filter-settings, #filter-tune')) return;
    if (event.type === 'keydown' && (event.ctrlKey || event.metaKey || event.altKey || event.key === 'Tab' ||
      event.key === 'Shift' || event.key === 'Escape')) return;
    if (event.type === 'keydown' && (event.key === 'm' || event.key === 'M')) return;  // M itself turns sound on
    unlock();
    if (event.type === 'pointerdown' && ui.frame.contains(event.target)) consumeClick = true;
    // The first Space only turns the sound on; it does not also pause.
    if (event.type === 'keydown' && event.code === 'Space' && !hold &&
      !(event.target.closest && event.target.closest(INTERACTIVE))) { event.preventDefault(); event.stopImmediatePropagation(); }
  };
  let consumeClick = false;
  window.addEventListener('pointerdown', firstGesture, true);
  window.addEventListener('keydown', firstGesture, true);

  // A tap on a panel rerolls that panel; the runtime's own stage click (play/pause) never fires.
  ui.frame.addEventListener('click', event => {
    event.stopPropagation();
    if (hold) { consumeClick = false; togglePlay(); return; }
    if (consumeClick) { consumeClick = false; return; }
    // The preview layer ignores the pointer, so its panels are found by position.
    const box = event.target.closest('.loop') || Array.from(ui.preview.children).find(item => {
      const rect = item.getBoundingClientRect();
      return event.clientX >= rect.left && event.clientX < rect.right && event.clientY >= rect.top && event.clientY < rect.bottom;
    });
    const index = box ? Number(String(box.dataset.loopId || '').replace('loop-', '')) - 1 : -1;
    if (index >= 0) rerollPanel(index);
  }, true);

  const INTERACTIVE = 'button,input,select,textarea,a[href],[role="radio"],[role="slider"]';
  document.addEventListener('keydown', event => {
    if (ui.filterDialog.open) return;
    if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
    const inControl = event.target.closest && event.target.closest(INTERACTIVE);
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    if (key === 'Escape' && !ui.about.hidden) { setAbout(false); return; }
    if (event.code === 'Space') {
      if (inControl) return;
      event.preventDefault();
      if (!event.repeat) togglePlay();
      return;
    }
    if (event.repeat && key !== 'ArrowLeft' && key !== 'ArrowRight') return;
    const actions = {r: () => roll(), f: toggleFullscreen, m: toggleSound,
      ArrowRight: () => selection && setCount(selection.loops.length + 1),
      ArrowUp: () => selection && setCount(selection.loops.length + 1),
      ArrowLeft: () => selection && setCount(selection.loops.length - 1),
      ArrowDown: () => selection && setCount(selection.loops.length - 1)};
    if (!actions[key] || (key.startsWith('Arrow') && event.target.closest && event.target.closest('input'))) return;
    event.preventDefault();
    actions[key]();
  }, true);

  // ---- Status --------------------------------------------------------------------

  function sync() {
    const r = runtime(), status = stage.dataset.status || '';
    const playing = Boolean(r && r.running) || (recordMode !== 'recorded' && !own.length && !hold && !paused);
    ui.play.setAttribute('aria-label', playing ? 'Pause' : 'Play');
    ui.play.dataset.state = playing ? 'playing' : 'paused';
    studio.dataset.status = status;
    studio.classList.toggle('held', hold);
    if (status === 'finished' && !paused && !hold) {
      until(() => { const x = runtime(); return x && !x.starting && !x.restarting && ![...x.nodes.values()].some(node => node.busy); })
        .then(() => { const x = runtime(); if (x.finished && !paused) return x.play(); }).catch(() => {});
    }
    if (status === 'audio-blocked' && session && session.sound) {
      sound.unlocked = false; renderSound(); applyVolume();
    }
    if (status === 'playing') guardAll();
  }
  new MutationObserver(sync).observe(stage, {attributes: true, attributeFilter: ['data-status']});
  new ResizeObserver(() => { if (ui.preview.childElementCount) { ui.preview.dataset.key = ''; renderPreview(); } }).observe(ui.frame);

  // ---- Start ----------------------------------------------------------------------

  const layoutsLoaded = fetch('layouts.json').then(response => {
    if (!response.ok) throw new Error(`layouts.json: HTTP ${response.status}`);
    return response.json();
  }).then(bundle => {
    const described = compiler().layoutFamilies(bundle);
    layout.bundle = bundle;
    for (const [name, family] of Object.entries(described.families)) {
      const counts = allowedCounts(family.counts);
      if (counts.length) layout.families[name] = {counts, sourceCounts: family.counts, label: familyLabel(name)};
    }
  }).catch(error => {
    toast(oneLine(`The layouts could not be loaded (${error.message || error}).`));
  });
  // The library is optional and silent: absent, unreadable or invalid, the generated loops play.
  // ?gen=1 skips it without a request; clips are checked with crypto.subtle, so it needs a secure context.
  const forceGenerated = new URLSearchParams(search).get('gen') === '1';
  const manifestLoaded = forceGenerated || !root.isSecureContext || !(root.crypto && crypto.subtle) ? Promise.resolve(null) :
    fetch('library/manifest.json', {redirect: 'error'})
      .then(response => (response.ok ? response.json() : null)).then(libraryClips).catch(() => null);

  Promise.all([layoutsLoaded, manifestLoaded]).then(([, clips]) => {
    layout.loading = false;
    if (!Object.keys(layout.families).length) return;
    if (clips && Object.values(familyCounts()).some(counts => counts.some(count => count <= clips.length))) useLibrary(clips);
    let seed = parseSeed(search) ?? freshSeed();
    selection = rollFor(seed);
    // Find a reproducible modest initial roll within this device's live limit.
    if (usingLibrary() && parseSeed(search) === null && !new URLSearchParams(search).has('mix')) {
      const wanted = Math.min(4, available());
      for (let attempt = 0; attempt < 256 && selection &&
          (selection.loops.length !== wanted || selection.family !== 'strips'); attempt++) {
        seed = (seed + 1) >>> 0; selection = rollFor(seed);
      }
    }
    ecosystem = new root.SimvltaneaEcosystem.Engine({seed});
    succession = createSuccession(seed);
    const sourceCounts = Object.fromEntries(Object.entries(layout.families).map(([name, family]) => [name, family.sourceCounts]));
    const mix = parseMix(new URLSearchParams(search).get('mix'), sourceCounts, pool().length);
    if (selection && mix) selection = boundedSelection({...selection, ...mix});
    writeUrl(mix ? formatMix(selection.family, selection.loops) : null);
    renderControls();
    renderPreview();
    sync();
    if (library.active) launch();
    else { builtinRecording = recordBuiltins(); launch(); }
  });

  renderSound();
  wake();
  if (reduced) studio.classList.add('held');

  root.SimvltaneaStudio = Object.assign({}, api, {
    snapshot: () => ({
      busy: busy > 0, frames, loading: layout.loading, seed: selection ? selection.seed : null,
      family: selection ? selection.family : null, panels: selection ? selection.loops.length : null,
      counts: selection ? layout.families[selection.family].counts.slice() : [],
      families: Object.entries(layout.families).map(([name, family]) => ({name, label: family.label, counts: family.counts.slice()})),
      source: own.length ? 'own' : library.active ? 'library' : 'builtin', record: recordMode, held: hold, paused,
      // Clip ids and counts only; the clips' tags are never exposed.
      library: library.active ? {clips: library.items.length, broken: library.broken.size,
        cached: [...library.cache.keys()], inflight: [...library.inflight.keys()], prefetch: library.prefetch.slice(),
        next: library.next, requested: library.requested} : null,
      builtinsReady: builtins.filter(item => item.sha256).length,
      selection: selectedItems().map(item => item.name), style: selection ? selection.style : null,
      sound: soundState(), volume: sound.volume, evolving, filters: filtersEnabled && filtersAvailable(), effectSettings, loopMode,
      ecosystem: ecosystem.snapshot(), refusals: lastRefusals.slice(), toast: ui.toast.textContent,
      toastShown: ui.toast.classList.contains('on'), phase: studio.dataset.phase || 'preview',
      layoutFile: layout.own ? {name: layout.own.name, kind: layout.own.info.kind, layout: layout.own.info.name} : null,
      loops: own.map(loop => ({name: loop.name, type: loop.type, suffix: loop.suffix, size: loop.size,
        sha256: loop.sha256, codec: loop.codec, container: loop.container, width: loop.width,
        height: loop.height, duration: loop.duration, declared: loop.quantized.duration,
        frames: loop.quantized.frames, audio: loop.audioStream})),
    }),
  });
})(typeof globalThis === 'object' ? globalThis : this);
