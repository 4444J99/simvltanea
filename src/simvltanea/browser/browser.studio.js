/* SIMVLTANEA studio: a visitor's own loops, played at once on independent clocks.
 *
 * A classic script without dependencies, staged as studio.js beside compiler.js,
 * runtime.js and layouts.json by browser_studio.stage_studio. It must load after
 * compiler.js and before runtime.js: it installs window.compositionIO, through
 * which the unmodified runtime receives the compiled plan and the chosen bytes.
 *
 * Files never leave the device. Each one is gated before it becomes a loop:
 * a total-size cap, a container/codec sniff checked with video.canPlayType(),
 * a real metadata load that must yield a decoded frame, a duration quantized
 * down to whole composition frames, and one crypto.subtle SHA-256 digest that
 * the runtime's integrity check reuses instead of hashing the bytes again.
 *
 * The layout is chosen, not inferred. The families (strips, authored) and the
 * panel counts each offers are read from layouts.json (simvltanea.layout-bundle/2,
 * or the legacy authored map); nothing here caps the count. The page opens on the
 * bundle's default family (strips) at five panels. "Use my own layout file" reads
 * a simvltanea.layout-preset/1 or simvltanea.layout-pair/1 file on the device and
 * offers it as one more family. Play needs exactly one loop per panel; any other
 * count is refused, never padded or duplicated.
 *
 * The pure helpers (quantizeDuration, admitSize, countVerdict, spanVerdict,
 * nearestCount, familyLabel, oneLine, sniffContainer, playbackQueries, blobType,
 * mediaSuffix) are exported for Node tests through module.exports and published as
 * globalThis.SimvltaneaStudio in the browser.
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

  const api = {
    FPS, DEFAULT_SECONDS, DEFAULT_PANELS, MAX_TOTAL_BYTES, MIN_FRAMES, MAX_SPANS_PER_TRACK, OWN_FAMILY,
    quantizeDuration, admitSize, countVerdict, spanVerdict, nearestCount, familyLabel, oneLine, sniffContainer,
    playbackQueries, blobType, mediaSuffix, compositionFrames, formatMiB,
  };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SimvltaneaStudio = api;
  if (typeof document === 'undefined' || !document.querySelector('#studio')) return;

  // ---- Page controller -----------------------------------------------------

  const $ = selector => document.querySelector(selector);
  const studio = $('#studio'), stage = $('#stage');
  const ui = {
    files: $('#files'), drop: $('#drop'), progress: $('#progress'), refusals: $('#refusals'), count: $('#count'),
    loops: $('#loops'), start: $('#start'), setup: $('#setup'), player: $('#player'), toggle: $('#toggle'),
    restart: $('#restart'), repeat: $('#repeat'), change: $('#change'), status: $('#runtime-status'),
    length: $('#length'), families: $('#families'), panels: $('#panels'), layoutFile: $('#layout-file'),
    layoutStatus: $('#layout-status'), layoutError: $('#layout-error'),
  };
  const frames = compositionFrames(root.location && root.location.search);
  const loops = [];
  const digests = new WeakMap();
  let nextId = 1, busy = 0, session = null, waiting = [], orientation = 'auto', repeating = false;
  // The layout choice: a family from layouts.json (or the visitor's own file) and a panel count.
  const layout = {bundle: null, families: {}, order: [], family: null, panels: null, own: null, loading: true};
  const compiler = () => root.SimvltaneaCompiler;
  const layoutsReady = fetch('layouts.json').then(response => {
    if (!response.ok) throw new Error(`layouts.json: HTTP ${response.status}`);
    return response.json();
  }).then(bundle => {
    const described = compiler().layoutFamilies(bundle);
    layout.bundle = bundle;
    for (const [name, family] of Object.entries(described.families)) {
      layout.families[name] = {counts: family.counts, label: familyLabel(name)};
      layout.order.push(name);
    }
    if (layout.family === null) choose(described.default_family, DEFAULT_PANELS);
    return bundle;
  }).catch(error => {
    say(ui.layoutError, oneLine(`The built-in layouts could not be loaded (${error.message || error}); ` +
      'you can still use your own layout file.', 'layouts.json'));
    throw error;
  }).finally(() => { layout.loading = false; renderLayout(); render(); });
  layoutsReady.catch(() => {});

  const hex = buffer => Array.from(new Uint8Array(buffer), value => value.toString(16).padStart(2, '0')).join('');
  const until = (test, limit = 20000) => new Promise((resolve, reject) => {
    const began = performance.now();
    (function poll() {
      if (test()) resolve();
      else if (performance.now() - began > limit) reject(new Error('The player did not settle'));
      else setTimeout(poll, 30);
    })();
  });
  const runtime = () => root.compositionRuntime;
  const idle = () => {
    const r = runtime();
    return r && !r.starting && !r.restarting && ![...r.nodes.values()].some(node => node.busy);
  };

  // The runtime reads media through this hook. Its first, automatic
  // initialization waits here until the visitor starts a session.
  root.__sharedEngineUnavailable =
    'The studio plays every loop with its authored framing; the panel framing sweep is not included.';
  root.compositionIO = {
    maxMediaBytes: MAX_TOTAL_BYTES,
    plan() {
      return session ? Promise.resolve(session.plan) : new Promise(resolve => { waiting.push(resolve); });
    },
    async bytes(source) {
      const loop = session && session.bySha.get(source.sha256);
      if (!loop) throw new Error(`Missing media: ${source.id}`);
      const buffer = await loop.file.arrayBuffer();
      digests.set(buffer, loop.sha256);
      return buffer;
    },
    // A chosen file is hashed once, with crypto.subtle, when it is added. The
    // runtime's integrity check receives that digest for the re-read bytes.
    async digest(buffer) {
      return digests.get(buffer) ?? hex(await crypto.subtle.digest('SHA-256', buffer));
    },
    type(source) {
      const loop = session && session.bySha.get(source.sha256);
      return loop ? loop.type : null;
    },
  };

  function say(element, text) { element.textContent = text; }
  function refuse(message) {
    const item = document.createElement('li');
    item.textContent = message;
    ui.refusals.append(item);
  }

  // ---- Layout family, panel count and the visitor's own layout file -----------

  const counts = () => (layout.families[layout.family] || {counts: []}).counts;

  /* Select `family` and the offered panel count nearest to `panels`. Returns the note to
   * show when the count had to change, so a switch never alters the panel count silently. */
  function choose(family, panels) {
    const offered = (layout.families[family] || {counts: []}).counts;
    const chosen = nearestCount(offered, panels);
    layout.family = family;
    layout.panels = chosen;
    return chosen !== null && chosen !== panels ?
      `${layout.families[family].label} layouts cover ${describeCounts(offered)} panels; Panels is now ${chosen}.` : '';
  }
  function describeCounts(offered) {
    const contiguous = offered.every((count, index) => index === 0 || count === offered[index - 1] + 1);
    return offered.length === 1 ? String(offered[0]) : contiguous ? `${offered[0]} to ${offered[offered.length - 1]}`
      : offered.join(', ');
  }

  function renderLayout() {
    const names = layout.order.concat(layout.own ? [OWN_FAMILY] : []);
    // Values and labels both: a second own file keeps the value 'file' but changes its label.
    const current = Array.from(ui.families.querySelectorAll('label'),
      label => `${label.querySelector('input').value}\n${label.textContent}`).join('\n\n');
    if (current !== names.map(name => `${name}\n${layout.families[name].label}`).join('\n\n')) {
      ui.families.replaceChildren(...names.map(name => {
        const label = document.createElement('label'), input = document.createElement('input');
        input.type = 'radio'; input.name = 'family'; input.value = name;
        label.append(input, layout.families[name].label);
        return label;
      }));
    }
    for (const input of ui.families.querySelectorAll('input')) {
      input.checked = input.value === layout.family;
      input.disabled = busy > 0;
    }
    const offered = counts();
    const options = Array.from(ui.panels.options, option => Number(option.value)).join(' ');
    if (options !== offered.join(' ')) {
      ui.panels.replaceChildren(...offered.map(count => {
        const option = document.createElement('option');
        option.value = String(count); option.textContent = String(count);
        return option;
      }));
    }
    if (layout.panels !== null) ui.panels.value = String(layout.panels);
    ui.panels.disabled = !offered.length || busy > 0;
    studio.dataset.family = layout.family || '';
    studio.dataset.panels = layout.panels === null ? '' : String(layout.panels);
  }

  ui.families.addEventListener('change', event => {
    const input = event.target.closest('input[name="family"]');
    if (!input || !input.checked) return;
    say(ui.layoutStatus, choose(input.value, layout.panels ?? DEFAULT_PANELS));
    renderLayout(); render();
  });
  ui.panels.addEventListener('change', () => {
    layout.panels = Number(ui.panels.value);
    say(ui.layoutStatus, '');
    renderLayout(); render();
  });

  async function useLayoutFile(file) {
    const name = file.name || 'layout file';
    say(ui.layoutError, '');
    try {
      const C = compiler(), data = C.loadLayoutBytes(await file.arrayBuffer(), name);
      const info = C.describeLayoutFile(data, name);
      layout.own = {name, data, info};
      layout.families[OWN_FAMILY] = {counts: info.counts, label: familyLabel(OWN_FAMILY, name)};
      const note = choose(OWN_FAMILY, layout.panels ?? DEFAULT_PANELS);
      say(ui.layoutStatus, `Using ${name}: ${info.kind === 'preset' ?
        `the strips preset ${info.name} for ${describeCounts(info.counts)} panels` :
        `a layout pair for ${plural(info.counts[0], 'panel')}`}. It stays on this device.${note ? ` ${note}` : ''}`);
    } catch (error) {
      say(ui.layoutError, oneLine(error.message || error, name));
    }
    renderLayout(); render();
  }
  ui.layoutFile.addEventListener('change', () => {
    const [file] = Array.from(ui.layoutFile.files);
    ui.layoutFile.value = '';
    if (file) useLayoutFile(file);
  });

  // {layouts, slice} for `count` loops in the chosen family; refused if the family lacks it.
  function arrangement(count) {
    const C = compiler();
    if (layout.family === OWN_FAMILY) return C.layoutFromFile(layout.own.data, count, layout.own.name);
    return C.layoutEntry(layout.bundle, layout.family, count);
  }

  function metadata(file, type) {
    return new Promise(resolve => {
      const video = document.createElement('video');
      const url = URL.createObjectURL(file.slice(0, file.size, type));
      let timer = null;
      const finish = result => {
        clearTimeout(timer);
        video.onloadeddata = video.onerror = null;
        video.removeAttribute('src');
        video.load();
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
    });
  }

  async function admit(file, probe) {
    const name = file.name || 'unnamed video';
    const total = loops.reduce((sum, loop) => sum + loop.size, 0);
    const oversized = admitSize(name, file.size, total);
    if (oversized) return refuse(oversized);
    let buffer;
    try { buffer = await file.arrayBuffer(); } catch (error) {
      return refuse(`${name} could not be read (${error.name || error}).`);
    }
    const sniff = sniffContainer(buffer);
    const type = blobType(name, file.type, sniff);
    const described = sniff.codec ? `${type}, ${sniff.codec.label}${sniff.codec.string &&
      sniff.codec.string !== sniff.codec.label ? ` ${sniff.codec.string}` : ''}` : type;
    const cannot = `This browser cannot play ${name} (${described}).` +
      (sniff.codec && sniff.codec.label === 'HEVC' ? ' HEVC needs a browser with HEVC decoding (for example ' +
        'Safari, or Chrome on a Mac); an H.264 ("Most Compatible") export plays almost everywhere.' : '');
    const {decisive, queries} = playbackQueries(type, sniff);
    const answers = queries.map(query => probe.canPlayType(query));
    if (decisive ? answers[0] === '' : answers.every(answer => answer === '')) return refuse(cannot);
    const facts = await metadata(file, type);
    if (!facts) return refuse(cannot);
    let quantized = null;
    try { quantized = quantizeDuration(facts.duration, FPS); } catch (_) { /* shorter than one frame */ }
    if (!quantized || quantized.frames < MIN_FRAMES) {
      return refuse(`${name} was not added: it lasts ${facts.duration.toFixed(2)} s, and a loop must last at ` +
        `least ${(MIN_FRAMES / FPS).toFixed(2)} s.`);
    }
    if (!root.crypto || !crypto.subtle) return refuse(`${name} could not be checked: this page needs HTTPS or localhost.`);
    const sha256 = hex(await crypto.subtle.digest('SHA-256', buffer));
    const twin = loops.find(loop => loop.sha256 === sha256);
    if (twin) {
      return refuse(`${name} was not added: it is the same video as ${twin.name}. Each loop needs its own ` +
        'video; nothing is duplicated.');
    }
    loops.push({key: nextId++, file, name, type, suffix: mediaSuffix(name, sniff), size: file.size, sha256,
      codec: sniff.codec ? sniff.codec.label : null, container: sniff.container, ...facts, quantized});
  }

  // Batches are checked one at a time, so the size cap counts every loop
  // accepted before them, including those of a batch still being checked.
  let admissions = Promise.resolve();
  async function addFiles(list) {
    const files = Array.from(list || []);
    if (!files.length) return;
    busy += 1; render();
    const previous = admissions;
    let release;
    admissions = new Promise(resolve => { release = resolve; });
    try {
      await previous;
      ui.refusals.replaceChildren();
      const probe = document.createElement('video');
      for (const [index, file] of files.entries()) {
        say(ui.progress, `Checking ${index + 1} of ${files.length}: ${file.name}. Nothing is uploaded.`);
        try { await admit(file, probe); } catch (error) {
          refuse(`${file.name} could not be checked (${error.message || error}).`);
        }
        render();
      }
      const added = files.length - ui.refusals.children.length;
      say(ui.progress, `Checked ${files.length} file${files.length === 1 ? '' : 's'}: ${added} added` +
        `${ui.refusals.children.length ? `, ${ui.refusals.children.length} not added` : ''}.`);
    } finally {
      release();
      busy -= 1; render();
    }
  }

  function button(label, name, action, disabled) {
    const element = document.createElement('button');
    element.type = 'button';
    element.textContent = label;
    element.setAttribute('aria-label', name);
    element.dataset.action = action;
    element.disabled = disabled;
    return element;
  }

  // Ready only when the panel count matches and the loops are long enough for the piece length.
  function selectionVerdict() {
    const verdict = countVerdict(loops.length, layout.panels, counts());
    if (!verdict.ok) return verdict;
    const spans = spanVerdict(frames, loops.map(loop => loop.quantized.frames));
    return spans.ok ? verdict : spans;
  }

  function render(focus) {
    const verdict = selectionVerdict();
    say(ui.count, layout.loading ? 'Loading the layouts…' : verdict.message);
    studio.dataset.count = String(loops.length);
    ui.start.disabled = !verdict.ok || busy > 0 || layout.loading;
    renderLayout();
    ui.loops.replaceChildren(...loops.map((loop, index) => {
      const item = document.createElement('li');
      item.dataset.key = String(loop.key);
      const title = document.createElement('span');
      title.className = 'loop-name';
      title.textContent = loop.name;
      const facts = document.createElement('span');
      facts.className = 'loop-facts';
      facts.textContent = `${loop.width}×${loop.height} · ${loop.quantized.seconds.toFixed(2)} s loop` +
        `${loop.codec ? ` · ${loop.codec}` : ''} · ${formatMiB(loop.size)}`;
      const actions = document.createElement('span');
      actions.className = 'loop-actions';
      actions.append(
        button('Up', `Move ${loop.name} up`, 'up', index === 0),
        button('Down', `Move ${loop.name} down`, 'down', index === loops.length - 1),
        button('Remove', `Remove ${loop.name}`, 'remove', false));
      item.append(title, facts, actions);
      return item;
    }));
    if (focus) {
      const target = ui.loops.querySelector(`li[data-key="${focus.key}"] [data-action="${focus.action}"]`);
      if (target && !target.disabled) target.focus();
      else (ui.loops.querySelector(`li[data-key="${focus.key}"] button:not(:disabled)`) || ui.files).focus();
    }
  }

  ui.loops.addEventListener('click', event => {
    const control = event.target.closest('button[data-action]');
    if (!control) return;
    const key = Number(control.closest('li').dataset.key), index = loops.findIndex(loop => loop.key === key);
    if (index < 0) return;
    const action = control.dataset.action;
    if (action === 'remove') {
      const [removed] = loops.splice(index, 1);
      say(ui.progress, `Removed ${removed.name}.`);
      const neighbour = loops[Math.min(index, loops.length - 1)];
      render(neighbour ? {key: neighbour.key, action: 'remove'} : undefined);
      if (!neighbour) ui.files.focus();
      return;
    }
    const target = action === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= loops.length) return;
    [loops[index], loops[target]] = [loops[target], loops[index]];
    say(ui.progress, `Moved ${loops[target].name} to position ${target + 1}.`);
    render({key, action});
  });

  ui.files.addEventListener('change', () => {
    const chosen = Array.from(ui.files.files);
    ui.files.value = '';
    addFiles(chosen);
  });
  for (const type of ['dragenter', 'dragover']) {
    ui.drop.addEventListener(type, event => { event.preventDefault(); ui.drop.classList.add('over'); });
  }
  ui.drop.addEventListener('dragleave', () => ui.drop.classList.remove('over'));
  ui.drop.addEventListener('drop', event => {
    event.preventDefault();
    ui.drop.classList.remove('over');
    addFiles(event.dataTransfer && event.dataTransfer.files);
  });
  // A file dropped beside the zone must not navigate away from the page.
  for (const type of ['dragover', 'drop']) document.addEventListener(type, event => event.preventDefault());

  /* Loop k (the k-th listed file) plays in strip or cell loop-k. A pair whose cells use
   * other loop names is relabelled in portrait cell order. A strips layout also carries
   * the state-wide slice: its zoom for this panel count. */
  function compile() {
    const C = compiler();
    const ids = loops.map((_, index) => `loop-${index + 1}`);
    const sources = loops.map((loop, index) => ({id: `source-${index + 1}`,
      path: `media/${loop.sha256}.${loop.suffix}`, sha256: loop.sha256, kind: 'video',
      duration: loop.quantized.duration}));
    const entry = arrangement(loops.length);
    const named = new Set(entry.layouts.portrait.cells.map(cell => cell.loop));
    const layouts = named.size === ids.length && ids.every(id => named.has(id)) ? entry.layouts :
      C.bindLayouts(entry.layouts, ids);
    const input = {sources, frames, fps: FPS, layouts,
      loops: sources.map((source, index) => ({id: ids[index], source: source.id}))};
    if (entry.slice) input.slice = entry.slice;
    const state = C.buildState(input);
    const plan = C.compilePlan(state);
    for (const [index, source] of plan.sources.entries()) source.bytes = loops[index].size;
    return plan;
  }

  function show(view) {
    studio.dataset.view = view;
    ui.setup.hidden = view !== 'setup';
    ui.player.hidden = view !== 'player';
  }

  function applyOrientation() {
    ui.player.dataset.orientation = orientation;
    const r = runtime();
    if (r && typeof r.setOrientation === 'function') r.setOrientation(orientation === 'auto' ? null : orientation);
  }

  async function startSession() {
    const verdict = selectionVerdict();
    if (!verdict.ok || busy > 0 || layout.loading) { say(ui.count, verdict.message); return; }
    const r = runtime();
    if (!r) { say(ui.count, 'The player did not load. Reload the page and try again.'); return; }
    let plan;
    try {
      plan = compile();
    } catch (error) {
      say(ui.count, oneLine(`These loops cannot be arranged: ${error.message || error}`));
      return;
    }
    session = {plan, bySha: new Map(loops.map(loop => [loop.sha256, loop]))};
    show('player');
    applyOrientation();
    say(ui.status, 'Loading your loops on this device…');
    ui.toggle.focus();
    const pending = waiting; waiting = [];
    try {
      const initialized = r.initialize();
      // Release the automatic first initialization; it is already superseded.
      pending.forEach(resolve => resolve(plan));
      await initialized;
      applyOrientation();
      await r.start();
    } catch (error) {
      if (!r.error) say(ui.status, `Playback could not start: ${error.message || error}. Press Play to try again.`);
    }
    sync();
  }

  function sync() {
    const r = runtime(), status = stage.dataset.status || '';
    const playing = Boolean(r && r.running);
    ui.toggle.textContent = playing ? 'Pause' : 'Play';
    ui.toggle.setAttribute('aria-label', playing ? 'Pause' : 'Play');
    studio.dataset.status = status;
    if (status === 'finished' && ui.repeat.checked && !ui.player.hidden) repeat();
  }

  // Auto-repeat replays through the runtime's restart-after-finish gesture path.
  async function repeat() {
    if (repeating) return;
    repeating = true;
    try {
      await until(idle);
      const r = runtime();
      if (r.finished && ui.repeat.checked && !ui.player.hidden) stage.click();
    } catch (_) { /* a later status change retries */ } finally { repeating = false; }
  }

  ui.start.addEventListener('click', startSession);
  // Play/Pause is the same gesture as a click on the stage or Space on the page.
  ui.toggle.addEventListener('click', () => {
    const r = runtime();
    if (r && !r.ready && !r.initializing && session) {
      r.initialize().then(() => r.start()).catch(() => {}).finally(sync);
      return;
    }
    stage.click();
  });
  ui.restart.addEventListener('click', async () => {
    const r = runtime();
    if (!r || !r.ready) return;
    try {
      r.pause();
      await until(idle);
      r.pause();
      await r.seek(0);
      await r.play();
    } catch (error) {
      if (!r.error) say(ui.status, `Restart failed: ${error.message || error}`);
    }
    sync();
  });
  for (const input of document.querySelectorAll('input[name="orientation"]')) {
    input.addEventListener('change', () => { if (input.checked) { orientation = input.value; applyOrientation(); } });
  }
  ui.repeat.addEventListener('change', sync);
  ui.change.addEventListener('click', () => {
    const r = runtime();
    if (r) r.dispose();
    session = null;
    show('setup');
    render();
    ui.files.focus();
  });

  new MutationObserver(sync).observe(stage, {attributes: true, attributeFilter: ['data-status']});
  const note = $('#runtime-note');
  if (note && !note.textContent) say(note, root.__sharedEngineUnavailable);
  if (ui.length) {
    const seconds = frames / FPS;
    say(ui.length, seconds >= 60 && seconds % 60 === 0 ?
      `The piece lasts ${seconds / 60} minute${seconds === 60 ? '' : 's'}; with Auto-repeat on it starts again.` :
      `The piece lasts ${seconds} seconds; with Auto-repeat on it starts again.`);
  }
  if (!root.isSecureContext || !root.crypto || !crypto.subtle) {
    ui.files.disabled = true;
    say(ui.count, 'This page needs a secure connection (HTTPS or localhost) to check your videos.');
  } else {
    render();
  }
  show('setup');

  root.SimvltaneaStudio = Object.assign({}, api, {
    snapshot: () => ({
      view: studio.dataset.view, busy: busy > 0, frames, orientation, repeat: ui.repeat.checked,
      count: ui.count.textContent, refusals: Array.from(ui.refusals.children, item => item.textContent),
      family: layout.family, panels: layout.panels, counts: counts().slice(), loading: layout.loading,
      families: layout.order.concat(layout.own ? [OWN_FAMILY] : []).map(name => ({name,
        label: layout.families[name].label, counts: layout.families[name].counts.slice()})),
      layoutFile: layout.own ? {name: layout.own.name, kind: layout.own.info.kind, layout: layout.own.info.name} : null,
      layoutStatus: ui.layoutStatus.textContent, layoutError: ui.layoutError.textContent,
      loops: loops.map(loop => ({name: loop.name, type: loop.type, suffix: loop.suffix, size: loop.size,
        sha256: loop.sha256, codec: loop.codec, container: loop.container, width: loop.width,
        height: loop.height, duration: loop.duration, declared: loop.quantized.duration,
        frames: loop.quantized.frames})),
    }),
  });
})(typeof globalThis === 'object' ? globalThis : this);
