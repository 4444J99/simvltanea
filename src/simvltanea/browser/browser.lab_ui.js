/* Effects Lab interface. Media and audio clocks belong to the engine. */
(function (root) {
  'use strict';
  const Model = root.SimvltaneaLabModel || (typeof require === 'function' ? require('./browser.lab_model.js') : null);
  const FORMAT = 'independent-loop-compositor-effects-lab';
  const STORAGE_KEY = FORMAT + ':v1';
  const DEMOS = ['tide', 'prism', 'grain'];
  const title = value => String(value).replace(/(^|[- ])\w/g, s => s.toUpperCase().replace('-', ' '));
  const escape = value => String(value).replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const clamp = (n, lo, hi, fallback) => Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : fallback;
  const hz = n => n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + ' kHz' : Math.round(n) + ' Hz';
  const pct = n => Math.round(n * 100) + '%';
  const seconds = n => Number(Number(n).toFixed(2)) + ' s';
  const times = n => Number(n).toFixed(2) + '×';

  function slotEntries(snapshot, slots) {
    if (!slots) return snapshot.clips;
    return slots.map(slot => slot.pending ? {...slot.pending, id: slot.key, pending: true}
      : snapshot.clips.find(c => c.id === slot.id)).filter(Boolean);
  }
  function alignEngineOrder(engine, slots) {
    const ids = slots.filter(slot => slot.id).map(slot => slot.id);
    ids.forEach((id, index) => {
      const current = engine.snapshot().clips.findIndex(c => c.id === id);
      if (current >= 0 && current !== index) engine.move(id, index - current);
    });
  }
  // Export an allowlist of settings and file names only. Unresolved files keep their saved slots.
  function sessionData(snapshot, sources, slots) {
    return {format: FORMAT, version: 1,
      master: {volume: snapshot.volume, muted: !!snapshot.muted},
      sequence: {enabled: !!snapshot.sequence.enabled, interval: snapshot.sequence.interval},
      transport: transportData(snapshot.transport),
      clips: slotEntries(snapshot, slots).map(c => {
        const source = sources instanceof Map ? sources.get(c.id) : (sources || {})[c.id];
        const result = {clipId: String(c.pending ? c.clipId || c.id : c.id), name: String(c.name || 'Untitled').slice(0, 200), kind: c.kind,
          settings: Model.normalizeSettings(c.settings)};
        if (c.kind !== 'demo') result.fileName = String(source && source.fileName || c.fileName || c.name).slice(0, 200);
        if (c.kind === 'demo') result.demo = source && DEMOS.includes(source.demo) ? source.demo : DEMOS.includes(c.demo) ? c.demo : 'tide';
        return result;
      })};
  }
  function parseSession(value) {
    const data = typeof value === 'string' ? JSON.parse(value) : value;
    if (!data || data.format !== FORMAT || data.version !== 1 || !Array.isArray(data.clips))
      throw new Error('Choose an Effects Lab session JSON (version 1).');
    if (data.clips.length > Model.MAX_CLIPS) throw new Error('A project can contain at most ' + Model.MAX_CLIPS + ' clips.');
    const seenIds = new Set();
    const clips = data.clips.map(c => {
      if (!c || !['demo', 'video', 'audio'].includes(c.kind)) throw new Error('This session contains an unknown layer type.');
      if (c.clipId !== undefined) {
        if (typeof c.clipId !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(c.clipId) || seenIds.has(c.clipId)) throw new Error('Project clip identities must be unique safe strings.');
        seenIds.add(c.clipId);
      }
      if (c.kind === 'demo' && !DEMOS.includes(c.demo)) throw new Error('This session contains an unknown generated loop.');
      return {...(c.clipId ? {clipId: c.clipId} : {}), name: String(c.name || (c.demo ? title(c.demo) : 'Local file')).slice(0, 200),
        kind: c.kind, ...(c.kind === 'demo' ? {demo: c.demo} : {fileName: String(c.fileName || c.name || 'Local file').slice(0, 200)}), settings: Model.normalizeSettings(c.settings)};
    });
    return {format: FORMAT, version: 1, clips, transport: transportData(data.transport),
      master: {volume: clamp(data.master && data.master.volume, 0, 1, .45), muted: !!(data.master && data.master.muted)},
      sequence: {enabled: !!(data.sequence && data.sequence.enabled), interval: clamp(data.sequence && data.sequence.interval, 2, 120, 8)}};
  }
  function selectedPatch(engine, id, key, value) {
    if (!id || !Object.prototype.hasOwnProperty.call(Model.DEFAULTS, key)) return;
    engine.set(id, {[key]: value});
  }
  function fileKind(file) {
    if (/^audio\//i.test(file.type || '') || /\.(wav|mp3|m4a|aac|ogg|flac|aif|aiff|opus)$/i.test(file.name || '')) return 'audio';
    if (/^video\//i.test(file.type || '') || /\.(mov|mp4|m4v|webm|ogv|avi)$/i.test(file.name || '')) return 'video';
    return null;
  }
  function envelopePath(settings, life) {
    const end = Math.max(settings.videoLife, settings.audioLife);
    return 'M0 60 ' + Array.from({length: 101}, (_, i) => {
      const age = end * i / 100;
      const y = settings.hold ? (age > 0 ? 8 : 60) : 60 - 52 * Model.envelope(age, life, settings.attack);
      return 'L' + (3 * i).toFixed(1) + ' ' + y.toFixed(1);
    }).join(' ');
  }
  function availableClipId(snapshot, slots = []) {
    const reserved = new Set(snapshot.clips.map(c => c.id));
    slots.forEach(slot => { if (slot.id) reserved.add(slot.id); if (slot.pending) { if (slot.pending.clipId) reserved.add(slot.pending.clipId); if (slot.key) reserved.add(slot.key); } });
    let serial = 1; while (reserved.has('clip-' + serial)) serial++;
    return 'clip-' + serial;
  }
  function transportData(value = {}) {
    const v = value || {}, loopStart = clamp(v.loopStart, 0, 3600, 0);
    return {mode: v.mode === 'perform' ? 'perform' : 'arrange', looping: !!v.looping,
      loopStart, loopEnd: Math.max(loopStart + .25, clamp(v.loopEnd, .25, 4500, 60))};
  }
  function timelineEdit(settings, action, lane, deltaSeconds, deltaY = 0, snap = true) {
    const quantize = value => snap ? Math.round(value * 4) / 4 : value;
    const lifeKey = lane === 'video' ? 'videoLife' : 'audioLife';
    if (action === 'move') return {timelineStart: clamp(quantize((settings.timelineStart || 0) + deltaSeconds), 0, 3600, 0)};
    if (action === 'trim') {
      const bounds = Model.RANGES[lifeKey] || [.25, lane === 'video' ? 600 : 900];
      return {[lifeKey]: clamp(quantize(settings[lifeKey] + deltaSeconds), bounds[0], bounds[1], settings[lifeKey])};
    }
    if (action === 'peak') {
      const gainKey = lane === 'video' ? 'opacity' : 'audioGain';
      const peak = Math.min(settings.attack, settings[lifeKey] / 2);
      return {attack: clamp(quantize(peak + deltaSeconds), .01, Math.min(60, settings[lifeKey] / 2), peak),
        [gainKey]: clamp(settings[gainKey] - deltaY / 29, 0, 1, settings[gainKey])};
    }
    return {};
  }
  const api = {FORMAT, STORAGE_KEY, sessionData, parseSession, selectedPatch, fileKind, envelopePath, slotEntries, alignEngineOrder, transportData, timelineEdit, availableClipId};
  root.SimvltaneaLabUI = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (!root.document) return;

  function boot() {
    const $ = id => document.getElementById(id);
    const app = $('lab-app');
    if (!app) return;
    const status = (message, level = '') => { $('lab-status').textContent = message; $('lab-status').dataset.level = level; };
    if (!Model || !root.SimvltaneaLabEngine) {
      $('lab-error').hidden = false; $('lab-error').textContent = 'The lab could not load its playback modules. Reload this page to try again.';
      $('transport-play').disabled = true; return;
    }
    let engine, selectedId = null, busy = false, hasPlayed = false;
    let layerSignature = '', inspectorSignature = '';
    let sources = new Map(), slots = [], assets = new Map(), assetSerial = 0;
    let zoom = 14, timelineSignature = '', timelineTicks = '', gesture = null;
    let mode = 'arrange';
    const GUTTER = 144;
    const controls = new Map();
    const filterLabels = {presence: 'Presence · low in / high out', 'presence-reverse': 'Presence · high in / low out',
      lowpass: 'Low-pass', highpass: 'High-pass', bandpass: 'Band-pass', off: 'Off'};
    const definitions = [
      ['picture','blend','Blend mode','select',Model.BLENDS],
      ['picture','opacity','Opacity',.01,pct],
      ['picture','brightness','Brightness',.01,pct],
      ['picture','contrast','Contrast',.01,pct],
      ['picture','saturation','Saturation',.01,pct],
      ['picture','hue','Hue rotation',1,n => Math.round(n) + '°'],
      ['picture','blur','Blur',.1,n => n.toFixed(1) + ' px'],
      ['picture','invert','Invert',.01,pct],
      ['sound','audioEnabled','Sound enabled','check'],
      ['sound','audioGain','Voice level',.01,pct],
      ['sound','filterMode','Presence filter','select',Model.FILTER_MODES],
      ['sound','cutoff','Manual cutoff',10,hz],
      ['sound','resonance','Filter resonance',.1,n => n.toFixed(1) + ' Q'],
      ['sound','combMix','Swept comb mix',.01,pct],
      ['sound','combFeedback','Comb decay',.01,pct],
      ['sound','combLow','Sweep lower frequency',10,hz],
      ['sound','combHigh','Sweep upper frequency',10,hz],
      ['sound','combPeriod','Sweep period',.1,seconds],
      ['motion','timelineStart','Start on timeline',.25,seconds],
      ['motion','hold','Hold presence indefinitely','check'],
      ['motion','attack','Entrance',.01,seconds],
      ['motion','videoLife','Picture region duration',.25,seconds],
      ['motion','audioLife','Sound region duration',.25,seconds],
      ['motion','videoRate','Picture base rate',.01,times],
      ['motion','audioRate','Sound base rate',.01,times],
      ['motion','videoWander','Picture change per repeat',.01,pct],
      ['motion','audioWander','Sound change per repeat',.01,pct],
      ['motion','preservePitch','Preserve sound pitch','check']
    ];
    const helps = {
      filterMode: 'Presence opens a low-pass filter on entrance, then thins the departing sound through a high-pass filter.',
      combFeedback: 'A finite series of delayed echoes. Higher decay makes the moving spectral teeth more pronounced.',
      audioLife: 'Sound keeps its own lifetime when its picture disappears.',
      videoWander: 'Each repeat independently changes the current speed by up to this amount.',
      preservePitch: 'Available for local media when supported by this browser. Generated sounds change pitch with speed.'
    };
    definitions.forEach(([panel, key, label, type, extra]) => {
      const holder = document.createElement('div'); holder.className = type === 'check' ? 'switch-control' : 'control';
      const id = 'setting-' + key;
      const numeric = ['timelineStart','videoLife','audioLife','attack'].includes(key);
      if (type === 'check') holder.innerHTML = '<label for="' + id + '">' + label + '</label><input id="' + id + '" type="checkbox" data-setting="' + key + '">';
      else if (type === 'select') holder.innerHTML = '<div class="control-head"><label for="' + id + '">' + label + '</label></div><select id="' + id + '" data-setting="' + key + '">' + extra.map(v => '<option value="' + v + '">' + (filterLabels[v] || title(v)) + '</option>').join('') + '</select>';
      else {
        const [min, max] = Model.RANGES[key] || [0, 3600];
        holder.innerHTML = '<div class="control-head"><label for="' + id + '">' + label + '</label><output id="value-' + key + '" for="' + id + '"></output></div><input id="' + id + '" data-setting="' + key + '" type="' + (numeric ? 'number' : 'range') + '" min="' + min + '" max="' + max + '" step="' + type + '">';
      }
      $('panel-' + panel).appendChild(holder);
      if (helps[key]) { const help = document.createElement('p'); help.className = 'control-help'; help.id = 'help-' + key; help.textContent = helps[key]; holder.after(help); $(id).setAttribute('aria-describedby', help.id); }
      const input = $(id); controls.set(key, {input, output: $('value-' + key), format: typeof extra === 'function' ? extra : null, panel});
      input.addEventListener(type === 'check' || type === 'select' || numeric ? 'change' : 'input', () => {
        if (selectedId) applyClipPatch(selectedId, {[key]: type === 'check' ? input.checked : type === 'select' ? input.value : Number(input.value)});
      });
    });
    $('panel-picture').insertAdjacentHTML('beforeend', '<button id="vanish-picture" class="vanish" aria-pressed="false">◌ Vanish picture</button><p class="tail-tip">The sound keeps moving. Bring the picture back while the layer is alive, or launch it again.</p><p id="picture-capability" class="scope-note"></p>');
    $('panel-motion').insertAdjacentHTML('beforeend', '<p class="scope-note">Rates change at each track’s own repeat boundary. Launch starts the pair together; their clocks then move independently.</p>');
    $('panel-sound').insertAdjacentHTML('beforeend', '<p class="scope-note">Every layer has its own filters and swept comb. Master volume sets the whole composition.</p>');
    function selected(snapshot = engine.snapshot()) { return slotEntries(snapshot, slots).find(c => c.id === selectedId); }
    function applyClipPatch(id, patch) {
      const slot = slots.find(item => item.id === id || item.key === id);
      if (slot && slot.pending) { slot.pending.settings = Model.normalizeSettings(patch, slot.pending.settings); render(engine.snapshot()); }
      else engine.set(id, patch);
    }
    function setSelected(id) { selectedId = id; inspectorSignature = ''; render(engine.snapshot()); }
    function newEngine() {
      engine = new root.SimvltaneaLabEngine.Engine($('lab-stage'), {onChange: render, onError: message => status(String(message), 'error')});
      api.engine = engine;
    }
    function setBusy(value) {
      busy = value; app.classList.toggle('busy', value);
      document.querySelectorAll('[data-async], .settings-actions button').forEach(button => { button.disabled = value; });
      $('add-layer').disabled = value;
      $('bin-import').disabled = value; $('timeline-import').disabled = value;
    }
    async function run(action) {
      if (busy) return;
      setBusy(true);
      try { await action(); } catch (error) { status(error.message || String(error), 'error'); }
      finally { setBusy(false); render(engine.snapshot()); }
    }
    function clipPhase(c) {
      if (c.pending) return 'Choose local file';
      if (c.error) return 'Needs attention';
      if (c.kind === 'audio' && c.audio.active) return c.settings.hold ? 'Held sound' : 'Sound only';
      if (c.audio.active && !c.video.active) return 'Sound tail';
      if (c.active && c.settings.hold) return 'Held';
      if (c.active) return Model.phase(c.age, Math.max(c.settings.videoLife, c.settings.audioLife), c.settings.attack) === 'entering' ? 'Entering' : 'Fading';
      return c.age > 0 ? 'Resting' : 'Ready';
    }
    function renderLayers(snapshot) {
      const front = slotEntries(snapshot, slots).slice().reverse();
      const signature = front.map(c => c.id).join('|') + ':' + selectedId;
      if (signature !== layerSignature) {
        layerSignature = signature;
        $('layer-list').innerHTML = front.length ? front.map((c, index) => {
          const src = sources.get(c.id); const thumb = c.kind === 'demo' ? (src && src.demo || 'tide') : c.kind;
          return '<div class="layer' + (c.id === selectedId ? ' selected' : '') + (c.pending ? ' pending' : '') + '" data-layer="' + escape(c.id) + '"><button class="layer-select" data-action="' + (c.pending ? 'restore' : 'select') + '" aria-pressed="' + (c.id === selectedId) + '" aria-label="' + (c.pending ? 'Choose local file for layer ' : 'Select layer ') + (index + 1) + ': ' + escape(c.name) + '"><span class="thumb ' + thumb + '" aria-hidden="true"></span><span class="layer-copy"><span class="layer-name">' + escape(c.name) + '</span><span class="layer-status"><span class="layer-dot"></span><span data-layer-status>Ready</span></span></span></button><div class="layer-actions"><button class="launch" data-action="' + (c.pending ? 'restore' : 'launch') + '" aria-label="' + (c.pending ? 'Choose local file for ' : 'Launch ') + escape(c.name) + '" title="' + (c.pending ? 'Choose this local file again' : 'Restart this layer') + '">' + (c.pending ? 'Choose' : 'Launch') + '</button><button data-action="up" aria-label="Move ' + escape(c.name) + ' forward" title="Move forward"' + (index === 0 ? ' disabled' : '') + '>↑</button><button data-action="down" aria-label="Move ' + escape(c.name) + ' backward" title="Move backward"' + (index === front.length - 1 ? ' disabled' : '') + '>↓</button><button class="remove" data-action="remove" aria-label="Remove ' + escape(c.name) + '" title="Remove layer">×</button></div></div>';
        }).join('') : '<div class="empty-state">An open stage.<br>Add a generated loop or choose a local file to begin.</div>';
      }
      document.querySelectorAll('[data-layer]').forEach(row => {
        const c = front.find(item => item.id === row.dataset.layer); if (!c) return;
        row.classList.toggle('active', c.active); row.classList.toggle('tail', !!(c.audio && c.video && c.audio.active && !c.video.active));
        row.querySelector('[data-layer-status]').textContent = clipPhase(c) + ' · ' + (c.kind === 'demo' ? 'generated' : c.kind === 'audio' ? 'local sound' : 'local video');
        row.querySelector('.launch').disabled = busy;
      });
    }
    function renderInspector(c) {
      $('inspector-empty').hidden = !!c; $('inspector-body').hidden = !c;
      $('preset-select').disabled = !c;
      $('selected-name').textContent = c ? c.name : 'No layer selected';
      $('selected-number').textContent = c ? String(slotEntries(engine.snapshot(), slots).slice().reverse().findIndex(x => x.id === c.id) + 1).padStart(2, '0') : '—';
      if (!c) { $('preset-description').textContent = 'Select an imported clip to shape its picture and sound.'; return; }
      const signature = c.id + JSON.stringify(c.settings) + JSON.stringify(c.capabilities);
      if (signature === inspectorSignature) return;
      inspectorSignature = signature;
      const s = c.settings;
      controls.get('hold').input.previousElementSibling.textContent = mode === 'arrange' ? 'Hold level within each region' : 'Hold presence indefinitely';
      controls.forEach(({input, output, format, panel}, key) => {
        if (input.type === 'checkbox') input.checked = s[key]; else input.value = String(s[key]);
        if (output) output.textContent = format(s[key]);
        input.disabled = panel === 'picture' && c.kind === 'audio';
        if (panel === 'picture' && key !== 'blend' && key !== 'opacity' && c.capabilities && c.capabilities.pictureEffects === false) input.disabled = true;
                if (key === 'preservePitch') input.disabled = !c.capabilities || !c.capabilities.preservePitch;
        if (key === 'cutoff') input.disabled = !['lowpass','highpass','bandpass'].includes(s.filterMode);
        if (key === 'resonance') input.disabled = s.filterMode === 'off';
        if (key === 'attack') input.disabled = s.hold;
        if (['videoLife','audioLife'].includes(key)) input.disabled = mode === 'perform' && s.hold;
        if (['videoRate','videoWander'].includes(key) && c.kind === 'audio') input.disabled = true;
        input.setAttribute('aria-disabled', String(input.disabled));
      });
      $('help-filterMode').textContent = s.filterMode === 'presence-reverse' ? 'Presence opens a high-pass filter on entrance, then warms the departing sound through a low-pass filter.' : s.filterMode === 'presence' ? helps.filterMode : s.filterMode === 'off' ? 'Presence filtering is bypassed. The swept comb has its own mix control below.' : 'Set the cutoff and resonance below to shape this pass filter.';
      $('help-preservePitch').textContent = c.capabilities && c.capabilities.preservePitch ? 'Keep pitch steady as the local media playback rate changes. Results depend on the browser.' : c.kind === 'demo' ? 'Generated sounds change pitch with speed. Pitch preservation is available for supported local media.' : 'This browser does not expose pitch preservation for this file.';
      const preset = Object.keys(Model.PRESETS).find(key => JSON.stringify({...Model.PRESETS[key].settings, timelineStart: s.timelineStart}) === JSON.stringify(s));
      $('preset-select').value = preset || 'custom';
      $('preset-description').textContent = preset ? Model.PRESETS[preset].description : 'Your own settings, applied to this layer only.';
      $('vanish-picture').disabled = c.kind === 'audio';
      $('vanish-picture').setAttribute('aria-pressed', String(!s.videoEnabled));
      $('vanish-picture').textContent = s.videoEnabled ? '◌ Vanish picture' : '◉ Bring picture back';
      $('picture-capability').textContent = c.kind === 'audio' ? 'This layer contains sound only.' : c.capabilities && c.capabilities.pictureEffects === false ? 'Picture effects are unavailable in this browser.' : 'Blend order follows the stack: front layers combine with those below.';
      $('envelope-audio').setAttribute('d', s.audioEnabled ? envelopePath(s, s.audioLife) : 'M0 60H300');
      $('envelope-video').setAttribute('d', s.videoEnabled && c.kind !== 'audio' ? envelopePath(s, s.videoLife) : 'M0 60H300');
      $('envelope-end').textContent = s.hold ? 'Held until released' : seconds(Math.max(s.audioLife, s.videoLife));
      $('comb-low-label').textContent = hz(s.combLow); $('comb-high-label').textContent = hz(s.combHigh);
    }
    function setMode(next) {
      mode = next === 'perform' ? 'perform' : 'arrange';
      inspectorSignature = '';
      if (engine.setTransport) engine.setTransport({mode});
      else status('The arrangement playback module is unavailable. Reload this page.', 'error');
      render(engine.snapshot());
    }
    function seekTo(time) {
      if (!engine.seek) { status('Timeline seeking is unavailable. Reload this page.', 'error'); return; }
      if (mode !== 'arrange') setMode('arrange');
      const promise = engine.seek(clamp(time, 0, 4500, 0));
      if (promise && promise.catch) promise.catch(error => status(error.message, 'error'));
    }
    function timelineTime(clientX) {
      return Math.max(0, (clientX - $('timeline-canvas').getBoundingClientRect().left - GUTTER) / zoom);
    }
    function renderTimeline(snapshot) {
      const transport = transportData(snapshot.transport || {mode}); mode = transport.mode;
      ['arrange','perform'].forEach(view => {
        $('view-' + view).setAttribute('aria-selected', String(mode === view));
        $('view-' + view).tabIndex = mode === view ? 0 : -1;
        $(view + '-panel').hidden = mode !== view;
      });
      $('loop-enabled').checked = transport.looping;
      ['loop-enabled','loop-start','loop-end'].forEach(id => { $(id).disabled = mode === 'perform'; $(id).title = mode === 'perform' ? 'Loop range applies to Arrange mode' : id === 'loop-start' ? 'Loop start (seconds)' : id === 'loop-end' ? 'Loop end (seconds)' : 'Loop arrangement range'; });
      if (document.activeElement !== $('loop-start')) $('loop-start').value = String(transport.loopStart);
      if (document.activeElement !== $('loop-end')) $('loop-end').value = String(transport.loopEnd);
      const front = slotEntries(snapshot, slots).slice().reverse();
      $('timeline-empty').hidden = front.length > 0;
      const end = Math.max(60, transport.loopEnd, ...front.map(c => (c.settings.timelineStart || 0) + Math.max(c.settings.videoLife, c.settings.audioLife)));
      const extent = Math.ceil((end + 8) / 10) * 10;
      const width = GUTTER + extent * zoom;
      $('timeline-canvas').style.width = width + 'px';
      const step = zoom >= 35 ? 1 : zoom >= 10 ? 5 : 10;
      const tickSignature = extent + ':' + zoom;
      if (tickSignature !== timelineTicks) {
        timelineTicks = tickSignature;
        $('ruler-ticks').innerHTML = Array.from({length: Math.floor(extent / step) + 1}, (_, i) => '<span class="ruler-tick" style="left:' + (GUTTER + i * step * zoom) + 'px">' + (i * step) + 's</span>').join('');
      }
      const signature = front.map(c => c.id + ':' + !!c.pending).join('|');
      if (signature !== timelineSignature) {
        timelineSignature = signature;
        $('timeline-tracks').innerHTML = front.map((c, index) => '<div class="timeline-row" data-track="' + escape(c.id) + '"><div class="track-head"><button class="track-title" data-track-action="select" title="Select ' + escape(c.name) + '">' + String(index + 1).padStart(2, '0') + ' ' + escape(c.name) + '</button><span class="track-meta"></span><div class="track-actions"><button data-track-action="up" aria-label="Move ' + escape(c.name) + ' forward">↑</button><button data-track-action="down" aria-label="Move ' + escape(c.name) + ' backward">↓</button><button data-track-action="launch" aria-label="Play ' + escape(c.name) + '">▶</button><button data-track-action="remove" aria-label="Delete ' + escape(c.name) + '">×</button></div></div>' + ['video','audio'].map(lane => '<div class="track-lane ' + lane + '" data-lane="' + lane + '"><span class="lane-kind">' + (lane === 'video' ? 'PICTURE' : 'SOUND') + '</span><div class="timeline-clip ' + lane + '" data-clip="' + escape(c.id) + '" data-lane="' + lane + '" role="button" tabindex="0" aria-label="' + escape(c.name) + ' ' + (lane === 'video' ? 'picture' : 'sound') + ' region. Drag to move the pair."><span class="clip-label"></span><svg class="clip-envelope" aria-hidden="true" preserveAspectRatio="none"><path/></svg><button class="envelope-peak" data-edit="peak" aria-label="Adjust ' + (lane === 'video' ? 'picture opacity' : 'sound level') + ' and entrance" title="Drag: entrance / level. Arrow keys: entrance / level."></button><button class="trim-handle" data-edit="trim" aria-label="Trim ' + (lane === 'video' ? 'picture' : 'sound') + ' region duration" title="Drag to change region duration"></button></div></div>').join('') + '</div>').join('');
      }
      document.querySelectorAll('[data-track]').forEach(row => {
        const c = front.find(item => item.id === row.dataset.track); if (!c) return;
        row.classList.toggle('selected', c.id === selectedId);
        const sourceDuration = c.video && c.video.duration || c.audio && c.audio.duration;
        row.querySelector('.track-meta').textContent = c.pending ? 'Missing local media · choose file' : (c.kind === 'demo' ? 'Generated' : c.kind === 'audio' ? 'Audio' : 'Video') + (sourceDuration > 0 ? ' · ' + seconds(sourceDuration) + ' source' : ' · source duration unavailable');
        const index = front.indexOf(c);
        row.querySelector('[data-track-action="up"]').disabled = index === 0;
        row.querySelector('[data-track-action="down"]').disabled = index === front.length - 1;
        row.querySelector('[data-track-action="launch"]').textContent = c.pending ? '↥' : '▶';
        row.querySelectorAll('.track-lane').forEach(lane => { lane.style.backgroundSize = (step * zoom) + 'px 100%'; });
        row.querySelectorAll('[data-clip]').forEach(clip => {
          const lane = clip.dataset.lane, s = c.settings, life = s[lane === 'video' ? 'videoLife' : 'audioLife'];
          clip.hidden = lane === 'video' && c.kind === 'audio';
          clip.style.left = (s.timelineStart || 0) * zoom + 'px';
          const clipWidth = Math.max(6, life * zoom); clip.style.width = clipWidth + 'px';
          clip.classList.toggle('selected', c.id === selectedId); clip.classList.toggle('pending', !!c.pending);
          clip.classList.toggle('disabled', !s[lane === 'video' ? 'videoEnabled' : 'audioEnabled']);
          clip.querySelector('.clip-label').textContent = c.name + ' · ' + seconds(life);
          const gain = s[lane === 'video' ? 'opacity' : 'audioGain'], peakX = Math.min(s.attack, life / 2) * zoom, peakY = 39 - gain * 29;
          const svg = clip.querySelector('svg'); svg.setAttribute('viewBox', '0 0 ' + clipWidth + ' 46');
          svg.querySelector('path').setAttribute('d', s.hold ? 'M0 ' + peakY + 'H' + clipWidth : 'M0 40 L' + peakX + ' ' + peakY + ' L' + clipWidth + ' 40');
          const peak = clip.querySelector('.envelope-peak'); peak.style.left = peakX + 'px'; peak.style.top = peakY + 'px';
          peak.hidden = s.hold;
        });
      });
      $('timeline-playhead').style.left = GUTTER + snapshot.time * zoom + 'px';
      $('timeline-loop').hidden = !transport.looping;
      $('timeline-loop').style.left = GUTTER + transport.loopStart * zoom + 'px';
      $('timeline-loop').style.width = (transport.loopEnd - transport.loopStart) * zoom + 'px';
      if (!gesture) $('timeline-readout').textContent = snapshot.time.toFixed(2) + ' s';
    }
    function render(snapshot) {
      if (!snapshot) return;
      const allEntries = slotEntries(snapshot, slots);
      $('preview-empty').hidden = allEntries.length > 0;
      if (!allEntries.length) $('stage-caption').textContent = 'Your media stays on this device.';
      if (!allEntries.some(c => c.id === selectedId)) selectedId = allEntries[0] ? allEntries[0].id : null;
      if (snapshot.playing) hasPlayed = true;
      $('stage-panel').classList.toggle('playing', snapshot.playing);
      $('stage-state').textContent = snapshot.playing ? 'Preview · playing' : hasPlayed ? 'Preview · paused' : 'Preview · ready';
      $('transport-play').textContent = snapshot.playing ? 'Ⅱ Pause' : '▶ Play';
      $('transport-play').setAttribute('aria-label', snapshot.playing ? 'Pause playback' : 'Play ' + mode);
      $('session-time').textContent = String(Math.floor(snapshot.time / 60)).padStart(2, '0') + ':' + (snapshot.time % 60).toFixed(2).padStart(5, '0');
      $('stage-layer-count').textContent = String(slots.length).padStart(2, '0') + ' clips / ' + String(Model.MAX_CLIPS).padStart(2, '0') + ' slots';
      $('active-count').textContent = String(snapshot.clips.filter(c => c.active).length);
      $('master-volume').value = String(snapshot.volume); $('master-volume-value').textContent = pct(snapshot.volume);
      $('master-mute').setAttribute('aria-pressed', String(snapshot.muted));
      $('master-mute').setAttribute('aria-label', snapshot.muted ? 'Unmute master sound' : 'Mute master sound');
      $('master-mute').title = snapshot.muted ? 'Unmute master sound' : 'Mute master sound';
      $('sequence-enabled').checked = snapshot.sequence.enabled;
      if (document.activeElement !== $('sequence-interval')) $('sequence-interval').value = String(snapshot.sequence.interval);
      $('add-layer').disabled = busy;

      $('launch-selected').disabled = busy || !selectedId;
      renderLayers(snapshot); renderTimeline(snapshot);
      const c = selected(snapshot); renderInspector(c);
      $('duplicate-clip').disabled = busy || !c || slots.length >= Model.MAX_CLIPS; $('delete-clip').disabled = busy || !c;
      if (!c || c.pending) { $('envelope-audio').setAttribute('d', 'M0 60H300'); $('envelope-video').setAttribute('d', 'M0 60H300'); $('envelope-end').textContent = '—'; $('envelope-cursor').setAttribute('x1', 0); $('envelope-cursor').setAttribute('x2', 0); $('comb-cursor').style.left = '0%'; $('layer-phase').textContent = c && c.pending ? 'Choose file' : 'No clip'; $('video-rate').textContent = '—'; $('audio-rate').textContent = '—'; $('video-detail').textContent = 'No picture'; $('audio-detail').textContent = 'No sound'; $('comb-hz').textContent = '— Hz'; return; }
      $('layer-phase').textContent = clipPhase(c);
      ['video','audio'].forEach(key => {
        const t = c[key]; const enabled = key === 'video' ? c.settings.videoEnabled && c.kind !== 'audio' : c.settings.audioEnabled;
        $(key + '-rate').textContent = times(t.rate);
        $(key + '-detail').textContent = t.loops + ' repeats · ' + (enabled ? (t.active ? pct(t.presence) + ' presence' : 'resting') : 'off');
      });
      const frequency = c.audio.combHz || c.settings.combLow;
      $('comb-hz').textContent = hz(frequency) + (c.settings.combMix === 0 ? ' · bypassed' : '');
      const span = Math.log(c.settings.combHigh / c.settings.combLow);
      $('comb-cursor').style.left = (span > 0 ? clamp(Math.log(frequency / c.settings.combLow) / span * 100, 0, 100, 0) : 0) + '%';
      const cursor = c.settings.hold ? 0 : Math.min(300, c.age / Math.max(c.settings.videoLife, c.settings.audioLife) * 300);
      $('envelope-cursor').setAttribute('x1', cursor); $('envelope-cursor').setAttribute('x2', cursor);
      $('stage-caption').textContent = snapshot.clips.some(x => x.kind !== 'audio' && x.audio.active && !x.video.active) ? 'Sound continues beyond the picture region.' : 'Picture and sound share a start. Their ends are independent.';
    }
    async function addDemo(demo, settings, name, clipId) {
      const source = {name: name || title(demo), kind: 'demo', demo, id: clipId || availableClipId(engine.snapshot(), slots)};
      const id = await engine.addClip(source, settings || Model.PRESETS.drift.settings);
      sources.set(id, source); slots.push({id}); layerSignature = ''; setSelected(id); renderBin(); return id;
    }
    async function defaults() {
      selectedId = null;
      engine.setSequence({enabled: false, interval: 8});
      setMode('arrange');
      if (engine.setTransport) engine.setTransport({looping: false, loopStart: 0, loopEnd: 60});
      render(engine.snapshot()); renderBin();
      status('Import your own footage or found sounds. Files stay local.');
    }
    async function replaceSession(data) {
      engine.dispose(); sources = new Map(); slots = []; selectedId = null; hasPlayed = false; layerSignature = ''; inspectorSignature = '';
      newEngine(); engine.setMaster(data.master); engine.setSequence(data.sequence); setMode(data.transport.mode); if (engine.setTransport) engine.setTransport(data.transport);
      for (const c of data.clips) {
        if (c.kind === 'demo') await addDemo(c.demo, c.settings, c.name, c.clipId); else slots.push({key: 'pending-' + slots.length, pending: c});
      }
      selectedId = engine.snapshot().clips[0] ? engine.snapshot().clips[0].id : null;
      const pendingFiles = slots.filter(slot => slot.pending).map(slot => slot.pending);
      status(pendingFiles.length ? 'Settings loaded. Choose ' + pendingFiles.map(c => c.name).join(', ') + ' again to restore their local media.' : 'Session loaded. Press Play to begin.', 'success');
      render(engine.snapshot());
    }
    function togglePlay() {
      if (!engine.snapshot().clips.length) { if (slots.some(slot => slot.pending)) $('media-input').click(); else openSources(); return; }
      if (engine.snapshot().playing) { engine.pause(); return; }
      return run(() => engine.play());
    }
    function vanish() {
      const c = selected(); if (!c || c.kind === 'audio') return;
      applyClipPatch(c.id, {videoEnabled: !c.settings.videoEnabled});
      status(c.settings.videoEnabled ? 'Picture hidden. This layer’s sound keeps its own clock and lifetime.' : 'Picture enabled. Launch the layer if its picture lifetime has already ended.');
    }
    function openSources() { if (!busy) $('media-input').click(); }
    $('transport-stop').addEventListener('click', () => { if (engine.stop) engine.stop(); else { engine.pause(); seekTo(0); } });
    document.querySelectorAll('[data-view]').forEach(button => {
      button.addEventListener('click', () => setMode(button.dataset.view));
      button.addEventListener('keydown', event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); setMode(mode === 'arrange' ? 'perform' : 'arrange'); $('view-' + mode).focus(); } });
    });
    function updateLoop() { if (engine.setTransport) engine.setTransport({looping: $('loop-enabled').checked, loopStart: Number($('loop-start').value), loopEnd: Number($('loop-end').value)}); }
    ['loop-enabled','loop-start','loop-end'].forEach(id => $(id).addEventListener('change', updateLoop));
    $('timeline-zoom').addEventListener('input', event => { zoom = Number(event.target.value); renderTimeline(engine.snapshot()); });
    $('zoom-fit').addEventListener('click', () => {
      const entries = slotEntries(engine.snapshot(), slots);
      const end = Math.max(10, ...entries.map(c => (c.settings.timelineStart || 0) + Math.max(c.settings.videoLife, c.settings.audioLife)));
      zoom = Math.max(5, Math.min(80, Math.floor(($('timeline-scroll').clientWidth - GUTTER - 20) / end)));
      $('timeline-zoom').value = String(zoom); $('timeline-scroll').scrollLeft = 0; renderTimeline(engine.snapshot());
    });
    $('toggle-inspector').addEventListener('click', () => app.classList.toggle('inspector-open'));
    const timelineScroll = $('timeline-scroll');
    timelineScroll.addEventListener('pointerdown', event => {
      if (event.button !== 0 || busy || event.target.closest('.track-head')) return;
      const clip = event.target.closest('[data-clip]');
      if (clip) {
        const c = slotEntries(engine.snapshot(), slots).find(item => item.id === clip.dataset.clip); if (!c) return;
        setSelected(c.id);
        const handle = event.target.closest('[data-edit]');
        gesture = {id: c.id, lane: clip.dataset.lane, action: handle ? handle.dataset.edit : 'move', settings: {...c.settings}, x: event.clientX, y: event.clientY, scroll: timelineScroll.scrollLeft};
      } else {
        if (event.clientX - $('timeline-canvas').getBoundingClientRect().left < GUTTER) return;
        gesture = {action: 'scrub'}; seekTo(timelineTime(event.clientX));
      }
      event.preventDefault(); timelineScroll.setPointerCapture(event.pointerId); app.classList.add('dragging');
    });
    timelineScroll.addEventListener('pointermove', event => {
      if (!gesture) return;
      if (gesture.action === 'scrub') { seekTo(timelineTime(event.clientX)); return; }
      const delta = (event.clientX - gesture.x + timelineScroll.scrollLeft - gesture.scroll) / zoom;
      const patch = timelineEdit(gesture.settings, gesture.action, gesture.lane, delta, event.clientY - gesture.y, $('timeline-snap').checked && !event.shiftKey);
      applyClipPatch(gesture.id, patch);
      const c = selected(); if (c) $('timeline-readout').textContent = (c.settings.timelineStart || 0).toFixed(2) + ' s · P ' + seconds(c.settings.videoLife) + ' / S ' + seconds(c.settings.audioLife);
    });
    function endGesture(event) {
      if (!gesture) return;
      gesture = null; app.classList.remove('dragging');
      if (timelineScroll.hasPointerCapture(event.pointerId)) timelineScroll.releasePointerCapture(event.pointerId);
      renderTimeline(engine.snapshot());
    }
    timelineScroll.addEventListener('pointerup', endGesture); timelineScroll.addEventListener('pointercancel', endGesture);
    timelineScroll.addEventListener('keydown', event => {
      const clip = event.target.closest('[data-clip]'); if (!clip || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
      const c = slotEntries(engine.snapshot(), slots).find(item => item.id === clip.dataset.clip); if (!c) return;
      const handle = event.target.closest('[data-edit]'), action = handle ? handle.dataset.edit : 'move';
      event.preventDefault(); event.stopPropagation(); setSelected(c.id);
      const delta = event.key === 'ArrowRight' ? (event.shiftKey ? 1 : .25) : event.key === 'ArrowLeft' ? -(event.shiftKey ? 1 : .25) : 0;
      const dy = event.key === 'ArrowUp' ? -.58 : event.key === 'ArrowDown' ? .58 : 0;
      applyClipPatch(c.id, timelineEdit(c.settings, action, clip.dataset.lane, delta, dy, true));
    });
    $('timeline-tracks').addEventListener('click', event => {
      const button = event.target.closest('[data-track-action]'); if (!button || busy) return;
      const id = button.closest('[data-track]').dataset.track, action = button.dataset.trackAction;
      setSelected(id);
      if (action === 'launch') { const c = selected(); if (c.pending) $('media-input').click(); else run(() => engine.launch(id)); }
      if (action === 'remove') removeSelected();
      if (action === 'up' || action === 'down') {
        const index = slots.findIndex(slot => slot.id === id || slot.key === id), next = index + (action === 'up' ? 1 : -1);
        if (index >= 0 && next >= 0 && next < slots.length) { [slots[index], slots[next]] = [slots[next], slots[index]]; alignEngineOrder(engine, slots); render(engine.snapshot()); }
      }
    });
    function removeSelected() {
      const index = slots.findIndex(slot => slot.id === selectedId || slot.key === selectedId); if (index < 0) return;
      const [slot] = slots.splice(index, 1); if (slot.id) { engine.remove(slot.id); sources.delete(slot.id); }
      layerSignature = ''; timelineSignature = ''; render(engine.snapshot());
    }
    $('delete-clip').addEventListener('click', removeSelected);

    $('transport-play').addEventListener('click', togglePlay);
    $('launch-selected').addEventListener('click', () => { const c = selected(); if (c && c.pending) $('media-input').click(); else if (c) run(() => engine.launch(c.id)); });
    $('master-mute').addEventListener('click', () => engine.setMaster({muted: !engine.snapshot().muted}));
    $('master-volume').addEventListener('input', event => engine.setMaster({volume: Number(event.target.value)}));
    $('sequence-enabled').addEventListener('change', event => engine.setSequence({enabled: event.target.checked}));
    $('sequence-interval').addEventListener('change', event => engine.setSequence({interval: clamp(Number(event.target.value), 2, 120, 8)}));
    $('vanish-picture').addEventListener('click', vanish);
    $('preset-select').addEventListener('change', event => { const preset = Model.PRESETS[event.target.value]; if (preset && selectedId) { applyClipPatch(selectedId, {...preset.settings, timelineStart: selected().settings.timelineStart || 0}); status(preset.label + ' applied to ' + selected().name + '.'); } });
    $('add-layer').addEventListener('click', openSources);
    $('bin-import').addEventListener('click', openSources);
    $('timeline-import').addEventListener('click', openSources);
    function focusLayer(id, action = 'select') {
      const row = Array.from(document.querySelectorAll('[data-layer]')).find(element => element.dataset.layer === id);
      const desired = row && row.querySelector('[data-action="' + action + '"]');
      const target = desired && !desired.disabled ? desired : row && row.querySelector('.layer-select');
      (target || $('add-layer')).focus();
    }
    $('layer-list').addEventListener('click', event => {
      const button = event.target.closest('[data-action]'); const row = button && button.closest('[data-layer]'); if (!row || busy) return;
      const id = row.dataset.layer, action = button.dataset.action;
      const slotIndex = slots.findIndex(slot => slot.id === id || slot.key === id);
      if (action === 'select') { setSelected(id); focusLayer(id); }
      if (action === 'restore') { $('media-input').click(); return; }
      if (action === 'launch') { setSelected(id); setMode('perform'); run(() => engine.launch(id)); }
      if ((action === 'up' || action === 'down') && slotIndex >= 0) {
        const next = Math.max(0, Math.min(slots.length - 1, slotIndex + (action === 'up' ? 1 : -1)));
        [slots[slotIndex], slots[next]] = [slots[next], slots[slotIndex]];
        alignEngineOrder(engine, slots); render(engine.snapshot()); focusLayer(id, action);
      }
      if (action === 'remove' && slotIndex >= 0) {
        const [slot] = slots.splice(slotIndex, 1); if (slot.id) { engine.remove(id); sources.delete(id); }
        layerSignature = ''; render(engine.snapshot()); focusLayer(selectedId);
      }
    });
    const tabs = Array.from(document.querySelectorAll('[data-tab]'));
    function activateTab(tab, focus) {
      tabs.forEach(t => { const active = t === tab; t.setAttribute('aria-selected', String(active)); t.tabIndex = active ? 0 : -1; $('panel-' + t.dataset.tab).hidden = !active; });
      if (focus) tab.focus();
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activateTab(tab));
      tab.addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        activateTab(tabs[next], true);
      });
    });
    function renderBin() {
      $('media-bin-list').innerHTML = assets.size ? Array.from(assets.values()).map(asset => '<button class="bin-asset" draggable="true" data-asset="' + asset.id + '" title="Add ' + escape(asset.name) + ' at the playhead"><span class="thumb ' + asset.kind + '" aria-hidden="true"></span><span><strong>' + escape(asset.name) + '</strong><small>' + (asset.duration > 0 ? seconds(asset.duration) + ' source' : 'Local ' + asset.kind) + '</small></span></button>').join('') : '<p class="bin-note">No local media imported.</p>';
    }
    async function importFiles(files, at = engine.snapshot().time) {
      let imported = 0, binned = 0; const errors = [];
      for (const file of files) {
        const kind = fileKind(file); if (!kind) { errors.push(file.name + ': choose video or audio.'); continue; }
        const key = [file.name, file.size, file.lastModified, kind].join('|');
        let asset = assets.get(key);
        if (!asset) { asset = {id: 'asset-' + (++assetSerial), name: file.name, kind, file, duration: 0}; assets.set(key, asset); binned++; }
        const matches = slots.filter(slot => slot.pending && (slot.pending.fileName || slot.pending.name) === file.name && slot.pending.kind === kind);
        const targets = matches.length ? matches : slots.length < Model.MAX_CLIPS ? [null] : [];
        if (!targets.length) { errors.push(file.name + ' added to Media; all ' + Model.MAX_CLIPS + ' timeline slots are occupied.'); continue; }
        for (const slot of targets) {
          const restore = slot && slot.pending;
          const url = URL.createObjectURL(file);
          const source = {name: restore ? restore.name : file.name, kind, url, ownedURL: true, id: restore && restore.clipId || availableClipId(engine.snapshot(), slots)};
          try {
            const id = await engine.addClip(source, restore ? restore.settings : {...Model.PRESETS.drift.settings, timelineStart: at, videoEnabled: kind !== 'audio'});
            const admitted = engine.snapshot().clips.find(c => c.id === id);
            const videoDuration = admitted.video.duration || admitted.audio.duration, audioDuration = admitted.audio.duration || admitted.video.duration;
            asset.duration = Math.max(videoDuration || 0, audioDuration || 0);
            if (!restore && asset.duration > 0) engine.set(id, {videoLife: kind === 'audio' ? .25 : videoDuration, audioLife: audioDuration});
            sources.set(id, {name: source.name, fileName: file.name, kind, file, assetId: asset.id});
            if (slot) slots[slots.indexOf(slot)] = {id}; else slots.push({id});
            alignEngineOrder(engine, slots); imported++; layerSignature = ''; setSelected(id);
          } catch (error) { URL.revokeObjectURL(url); errors.push(file.name + ': ' + (error.message || 'This browser could not open the file.')); }
        }
      }
      renderBin();
      status((imported ? imported + ' ' + (imported === 1 ? 'clip' : 'clips') + ' placed. ' : binned ? binned + ' sources in Media. ' : '') + errors.join(' '), errors.length ? 'error' : 'success');
    }
    $('media-input').addEventListener('change', event => {
      const files = Array.from(event.target.files || []); event.target.value = ''; if (files.length) run(() => importFiles(files));
    });
    $('media-bin-list').addEventListener('click', event => {
      const button = event.target.closest('[data-asset]'); if (!button) return;
      const asset = Array.from(assets.values()).find(item => item.id === button.dataset.asset); if (asset) run(() => importFiles([asset.file]));
    });
    $('media-bin-list').addEventListener('dragstart', event => { const button = event.target.closest('[data-asset]'); if (button) { event.dataTransfer.setData('application/x-ilc-source', button.dataset.asset); event.dataTransfer.effectAllowed = 'copy'; } });
    function droppedSource(event, at) {
      event.preventDefault(); event.stopPropagation(); $('media-drop').classList.remove('drag-over');
      const files = Array.from(event.dataTransfer.files || []);
      if (files.length) { run(() => importFiles(files, at)); return; }
      const source = event.dataTransfer.getData('application/x-ilc-source');
      const asset = Array.from(assets.values()).find(item => item.id === source); if (asset) run(() => importFiles([asset.file], at));
    }
    $('timeline-scroll').addEventListener('dragover', event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; });
    $('timeline-scroll').addEventListener('drop', event => { let time = timelineTime(event.clientX); if ($('timeline-snap').checked) time = Math.round(time * 4) / 4; droppedSource(event, time); });
    $('media-drop').addEventListener('dragover', event => { event.preventDefault(); $('media-drop').classList.add('drag-over'); });
    $('media-drop').addEventListener('dragleave', event => { if (!$('media-drop').contains(event.relatedTarget)) $('media-drop').classList.remove('drag-over'); });
    app.addEventListener('dragover', event => { if (Array.from(event.dataTransfer.types || []).includes('Files')) event.preventDefault(); });
    app.addEventListener('drop', event => droppedSource(event, engine.snapshot().time));
    function duplicateSelected() {
      const c = selected(); if (!c || slots.length >= Model.MAX_CLIPS || busy) return;
      const settings = {...c.settings, timelineStart: Math.min(3600, (c.settings.timelineStart || 0) + 1)};
      if (c.pending) { const copy = {...c, name: c.name + ' copy', settings}; delete copy.clipId; delete copy.id; slots.push({key: 'pending-copy-' + Date.now(), pending: copy}); timelineSignature = ''; render(engine.snapshot()); return; }
      const source = sources.get(c.id);
      run(async () => {
        if (c.kind === 'demo') await addDemo(source.demo, settings, c.name + ' copy');
        else {
          if (!source || !source.file) throw new Error('Choose this local source again before duplicating it.');
          const url = URL.createObjectURL(source.file);
          try { const id = await engine.addClip({name: c.name + ' copy', kind: c.kind, url, ownedURL: true, id: availableClipId(engine.snapshot(), slots)}, settings); sources.set(id, {...source}); slots.push({id}); setSelected(id); }
          catch (error) { URL.revokeObjectURL(url); throw error; }
        }
      });
    }
    $('duplicate-clip').addEventListener('click', duplicateSelected);
    $('save-settings').addEventListener('click', () => {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sessionData(engine.snapshot(), sources, slots))); status('Session settings saved in this browser. Local media files are not stored.', 'success'); }
      catch (_) { status('This browser could not save locally. Use Export JSON to keep your settings.', 'error'); }
    });
    $('load-settings').addEventListener('click', () => run(async () => {
      let saved; try { saved = localStorage.getItem(STORAGE_KEY); } catch (_) { throw new Error('Saved browser storage is unavailable. You can import a session JSON.'); }
      if (!saved) throw new Error('No session is saved in this browser yet.');
      await replaceSession(parseSession(saved));
    }));
    $('export-settings').addEventListener('click', () => {
      try {
        const blob = new Blob([JSON.stringify(sessionData(engine.snapshot(), sources, slots), null, 2) + '\n'], {type: 'application/json'});
        const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'effects-lab-session.json'; document.body.appendChild(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000); status('Session JSON prepared for download. It contains settings and file names, never media.');
      } catch (_) { status('This browser could not prepare a download. Try Save session instead.', 'error'); }
    });
    $('import-settings').addEventListener('click', () => $('settings-input').click());
    $('settings-input').addEventListener('change', event => {
      const file = event.target.files && event.target.files[0]; event.target.value = ''; if (!file) return;
      run(async () => { if (file.size > 1000000) throw new Error('This file is too large for a session settings JSON.'); await replaceSession(parseSession(await file.text())); });
    });
    $('reset-session').addEventListener('click', () => run(async () => {
      engine.dispose(); sources = new Map(); slots = []; selectedId = null; hasPlayed = false; layerSignature = ''; inspectorSignature = '';
      assets.clear(); newEngine(); await defaults(); status('Empty project ready. Import your own footage or found sounds.', 'success');
    }).then(() => $('transport-play').focus()));
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd' && !/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) { event.preventDefault(); duplicateSelected(); return; }
      if (event.altKey || event.ctrlKey || event.metaKey || event.repeat || busy || /^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName) || event.target.isContentEditable) return;
      if (event.code === 'Space') { if (event.target.closest('button, a')) return; event.preventDefault(); togglePlay(); }
      else if (/^[1-8]$/.test(event.key)) { const c = slotEntries(engine.snapshot(), slots).slice().reverse()[Number(event.key) - 1]; if (c && !c.pending) setSelected(c.id); }
      else if (event.key.toLowerCase() === 'l' && selectedId) run(() => engine.launch(selectedId));
      else if (event.key.toLowerCase() === 'v') vanish();
      else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); removeSelected(); }
      else if (event.key === 'Home') { event.preventDefault(); if (engine.stop) engine.stop(); }
    });
    root.addEventListener('pagehide', () => engine.pause());
    newEngine(); run(defaults);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true}); else boot();
})(typeof globalThis === 'object' ? globalThis : this);
