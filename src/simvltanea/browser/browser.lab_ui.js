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
  const seconds = n => Number(n).toFixed(Number.isInteger(n) ? 0 : 1) + ' sec';
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
      clips: slotEntries(snapshot, slots).map(c => {
        const source = sources instanceof Map ? sources.get(c.id) : (sources || {})[c.id];
        const result = {name: String(c.name || 'Untitled').slice(0, 200), kind: c.kind,
          settings: Model.normalizeSettings(c.settings)};
        if (c.kind === 'demo') result.demo = source && DEMOS.includes(source.demo) ? source.demo : DEMOS.includes(c.demo) ? c.demo : 'tide';
        return result;
      })};
  }
  function parseSession(value) {
    const data = typeof value === 'string' ? JSON.parse(value) : value;
    if (!data || data.format !== FORMAT || data.version !== 1 || !Array.isArray(data.clips))
      throw new Error('Choose an Effects Lab session JSON (version 1).');
    if (data.clips.length > Model.MAX_CLIPS) throw new Error('A session can contain at most four layers.');
    const clips = data.clips.map(c => {
      if (!c || !['demo', 'video', 'audio'].includes(c.kind)) throw new Error('This session contains an unknown layer type.');
      if (c.kind === 'demo' && !DEMOS.includes(c.demo)) throw new Error('This session contains an unknown generated loop.');
      return {name: String(c.name || (c.demo ? title(c.demo) : 'Local file')).slice(0, 200),
        kind: c.kind, ...(c.kind === 'demo' ? {demo: c.demo} : {}), settings: Model.normalizeSettings(c.settings)};
    });
    return {format: FORMAT, version: 1, clips,
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
  const api = {FORMAT, STORAGE_KEY, sessionData, parseSession, selectedPatch, fileKind, envelopePath, slotEntries, alignEngineOrder};
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
      $('play-session').disabled = true; return;
    }
    let engine, selectedId = null, busy = false, hasPlayed = false;
    let layerSignature = '', inspectorSignature = '';
    let sources = new Map(), slots = [];
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
      ['motion','hold','Hold presence indefinitely','check'],
      ['motion','attack','Entrance',.1,seconds],
      ['motion','videoLife','Picture lifetime',1,seconds],
      ['motion','audioLife','Sound lifetime',1,seconds],
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
      if (type === 'check') holder.innerHTML = '<label for="' + id + '">' + label + '</label><input id="' + id + '" type="checkbox" data-setting="' + key + '">';
      else if (type === 'select') holder.innerHTML = '<div class="control-head"><label for="' + id + '">' + label + '</label></div><select id="' + id + '" data-setting="' + key + '">' + extra.map(v => '<option value="' + v + '">' + (filterLabels[v] || title(v)) + '</option>').join('') + '</select>';
      else {
        const [min, max] = Model.RANGES[key];
        holder.innerHTML = '<div class="control-head"><label for="' + id + '">' + label + '</label><output id="value-' + key + '" for="' + id + '"></output></div><input id="' + id + '" data-setting="' + key + '" type="range" min="' + min + '" max="' + max + '" step="' + type + '">';
      }
      $('panel-' + panel).appendChild(holder);
      if (helps[key]) { const help = document.createElement('p'); help.className = 'control-help'; help.id = 'help-' + key; help.textContent = helps[key]; holder.after(help); $(id).setAttribute('aria-describedby', help.id); }
      const input = $(id); controls.set(key, {input, output: $('value-' + key), format: typeof extra === 'function' ? extra : null, panel});
      input.addEventListener(type === 'check' || type === 'select' ? 'change' : 'input', () => {
        selectedPatch(engine, selectedId, key, type === 'check' ? input.checked : type === 'select' ? input.value : Number(input.value));
      });
    });
    $('panel-picture').insertAdjacentHTML('beforeend', '<button id="vanish-picture" class="vanish" aria-pressed="false">◌ Vanish picture</button><p class="tail-tip">The sound keeps moving. Bring the picture back while the layer is alive, or launch it again.</p><p id="picture-capability" class="scope-note"></p>');
    $('panel-motion').insertAdjacentHTML('beforeend', '<p class="scope-note">Rates change at each track’s own repeat boundary. Launch starts the pair together; their clocks then move independently.</p>');
    $('panel-sound').insertAdjacentHTML('beforeend', '<p class="scope-note">Every layer has its own filters and swept comb. Master volume sets the whole composition.</p>');
    function selected(snapshot = engine.snapshot()) { return snapshot.clips.find(c => c.id === selectedId); }
    function setSelected(id) { selectedId = id; inspectorSignature = ''; render(engine.snapshot()); }
    function newEngine() {
      engine = new root.SimvltaneaLabEngine.Engine($('lab-stage'), {onChange: render, onError: message => status(String(message), 'error')});
      api.engine = engine;
    }
    function setBusy(value) {
      busy = value; app.classList.toggle('busy', value);
      document.querySelectorAll('[data-async], .settings-actions button').forEach(button => { button.disabled = value; });
      $('add-layer').disabled = value || slots.length >= Model.MAX_CLIPS;
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
      if (!c) return;
      const signature = c.id + JSON.stringify(c.settings) + JSON.stringify(c.capabilities);
      if (signature === inspectorSignature) return;
      inspectorSignature = signature;
      const s = c.settings;
      controls.forEach(({input, output, format, panel}, key) => {
        if (input.type === 'checkbox') input.checked = s[key]; else input.value = String(s[key]);
        if (output) output.textContent = format(s[key]);
        input.disabled = panel === 'picture' && c.kind === 'audio';
        if (panel === 'picture' && key !== 'blend' && key !== 'opacity' && c.capabilities && c.capabilities.pictureEffects === false) input.disabled = true;
        if (key === 'preservePitch') input.disabled = !c.capabilities || !c.capabilities.preservePitch;
        if (key === 'cutoff') input.disabled = !['lowpass','highpass','bandpass'].includes(s.filterMode);
        if (key === 'resonance') input.disabled = s.filterMode === 'off';
        if (['attack','videoLife','audioLife'].includes(key)) input.disabled = s.hold;
        if (['videoRate','videoWander'].includes(key) && c.kind === 'audio') input.disabled = true;
        input.setAttribute('aria-disabled', String(input.disabled));
      });
      $('help-filterMode').textContent = s.filterMode === 'presence-reverse' ? 'Presence opens a high-pass filter on entrance, then warms the departing sound through a low-pass filter.' : s.filterMode === 'presence' ? helps.filterMode : s.filterMode === 'off' ? 'Presence filtering is bypassed. The swept comb has its own mix control below.' : 'Set the cutoff and resonance below to shape this pass filter.';
      $('help-preservePitch').textContent = c.capabilities && c.capabilities.preservePitch ? 'Keep pitch steady as the local media playback rate changes. Results depend on the browser.' : c.kind === 'demo' ? 'Generated sounds change pitch with speed. Pitch preservation is available for supported local media.' : 'This browser does not expose pitch preservation for this file.';
      const preset = Object.keys(Model.PRESETS).find(key => JSON.stringify(Model.PRESETS[key].settings) === JSON.stringify(s));
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
    function render(snapshot) {
      if (!snapshot) return;
      if (!snapshot.clips.some(c => c.id === selectedId)) selectedId = snapshot.clips[0] ? snapshot.clips[0].id : null;
      if (snapshot.playing) hasPlayed = true;
      $('welcome').hidden = hasPlayed;
      $('stage-panel').classList.toggle('playing', snapshot.playing);
      $('stage-state').textContent = snapshot.playing ? 'Session playing' : hasPlayed ? 'Paused' : 'Ready to play';
      $('transport-play').textContent = snapshot.playing ? 'Ⅱ Pause' : '▶ Play';
      $('transport-play').setAttribute('aria-label', snapshot.playing ? 'Pause session' : 'Play session');
      $('session-time').textContent = String(Math.floor(snapshot.time / 60)).padStart(2, '0') + ':' + String(Math.floor(snapshot.time % 60)).padStart(2, '0');
      $('stage-layer-count').textContent = String(slots.length).padStart(2, '0') + ' layers / 04 slots';
      $('active-count').textContent = String(snapshot.clips.filter(c => c.active).length);
      $('master-volume').value = String(snapshot.volume); $('master-volume-value').textContent = pct(snapshot.volume);
      $('master-mute').setAttribute('aria-pressed', String(snapshot.muted));
      $('master-mute').setAttribute('aria-label', snapshot.muted ? 'Unmute master sound' : 'Mute master sound');
      $('master-mute').title = snapshot.muted ? 'Unmute master sound' : 'Mute master sound';
      $('sequence-enabled').checked = snapshot.sequence.enabled;
      if (document.activeElement !== $('sequence-interval')) $('sequence-interval').value = String(snapshot.sequence.interval);
      $('add-layer').disabled = busy || slots.length >= Model.MAX_CLIPS;
      $('launch-selected').disabled = busy || !selectedId;
      renderLayers(snapshot); const c = selected(snapshot); renderInspector(c);
      if (!c) { $('layer-phase').textContent = 'No layer'; $('video-rate').textContent = '—'; $('audio-rate').textContent = '—'; $('video-detail').textContent = 'No picture'; $('audio-detail').textContent = 'No sound'; $('comb-hz').textContent = '— Hz'; return; }
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
      $('stage-caption').textContent = snapshot.clips.some(x => x.kind !== 'audio' && x.audio.active && !x.video.active) ? 'A picture has left. Its sound is still here.' : 'A living composition. Every layer has its own clock.';
    }
    async function addDemo(demo, settings, name) {
      const source = {name: name || title(demo), kind: 'demo', demo};
      const id = await engine.addClip(source, settings || Model.PRESETS.drift.settings);
      sources.set(id, source); slots.push({id}); layerSignature = ''; setSelected(id); return id;
    }
    async function defaults() {
      await addDemo('tide', Model.PRESETS.drift.settings);
      await addDemo('prism', {...Model.PRESETS.afterimage.settings, hue: 18, opacity: .68});
      await addDemo('grain', {...Model.PRESETS.drift.settings, blend: 'soft-light', audioGain: .35, opacity: .48});
      selectedId = engine.snapshot().clips[0].id;
      engine.setSequence({enabled: true, interval: 8}); render(engine.snapshot());
    }
    async function replaceSession(data) {
      engine.dispose(); sources = new Map(); slots = []; selectedId = null; hasPlayed = false; layerSignature = ''; inspectorSignature = '';
      newEngine(); engine.setMaster(data.master); engine.setSequence(data.sequence);
      for (const c of data.clips) {
        if (c.kind === 'demo') await addDemo(c.demo, c.settings, c.name); else slots.push({key: 'pending-' + slots.length, pending: c});
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
      selectedPatch(engine, c.id, 'videoEnabled', !c.settings.videoEnabled);
      status(c.settings.videoEnabled ? 'Picture hidden. This layer’s sound keeps its own clock and lifetime.' : 'Picture enabled. Launch the layer if its picture lifetime has already ended.');
    }
    function closeSources() { $('source-dialog').close(); $('add-layer').focus(); }
    function openSources() { if (!busy && slots.length < Model.MAX_CLIPS) $('source-dialog').showModal(); }
    $('play-session').addEventListener('click', togglePlay);
    $('transport-play').addEventListener('click', togglePlay);
    $('launch-selected').addEventListener('click', () => selectedId && run(() => engine.launch(selectedId)));
    $('master-mute').addEventListener('click', () => engine.setMaster({muted: !engine.snapshot().muted}));
    $('master-volume').addEventListener('input', event => engine.setMaster({volume: Number(event.target.value)}));
    $('sequence-enabled').addEventListener('change', event => engine.setSequence({enabled: event.target.checked}));
    $('sequence-interval').addEventListener('change', event => engine.setSequence({interval: clamp(Number(event.target.value), 2, 120, 8)}));
    $('vanish-picture').addEventListener('click', vanish);
    $('preset-select').addEventListener('change', event => { const preset = Model.PRESETS[event.target.value]; if (preset && selectedId) { engine.set(selectedId, preset.settings); status(preset.label + ' applied to ' + selected().name + '.'); } });
    $('add-layer').addEventListener('click', openSources);
    $('close-source-dialog').addEventListener('click', closeSources);
    $('source-dialog').addEventListener('click', event => { if (event.target === $('source-dialog')) closeSources(); });
    $('source-dialog').addEventListener('close', () => $('add-layer').focus());
    document.querySelectorAll('[data-demo]').forEach(button => button.addEventListener('click', () => { closeSources(); run(async () => { await addDemo(button.dataset.demo); status(title(button.dataset.demo) + ' added. Launch it to join the composition.', 'success'); }); }));
    $('choose-media').addEventListener('click', () => { closeSources(); $('media-input').click(); });
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
      if (action === 'launch') { setSelected(id); run(() => engine.launch(id)); }
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
    $('media-input').addEventListener('change', event => {
      const files = Array.from(event.target.files || []); event.target.value = ''; if (!files.length) return;
      run(async () => {
        let imported = 0; const errors = [];
        for (const file of files) {
          const kind = fileKind(file); if (!kind) { errors.push(file.name + ': choose a video or audio file.'); continue; }
          const restoreIndex = slots.findIndex(slot => slot.pending && slot.pending.name === file.name && slot.pending.kind === kind);
          const restore = restoreIndex >= 0 ? slots[restoreIndex].pending : null;
          if (slots.length >= Model.MAX_CLIPS && !restore) { errors.push(file.name + ': all four slots are occupied. Choose a missing file by its saved name, or remove a layer.'); continue; }
          const url = URL.createObjectURL(file), source = {name: file.name, kind, url, ownedURL: true};
          try {
            const id = await engine.addClip(source, restore ? restore.settings : {...Model.PRESETS.drift.settings, videoEnabled: kind !== 'audio'});
            sources.set(id, {name: file.name, kind});
            if (restore) slots[restoreIndex] = {id}; else slots.push({id});
            alignEngineOrder(engine, slots);
            imported++; layerSignature = ''; setSelected(id);
          } catch (error) { URL.revokeObjectURL(url); errors.push(file.name + ': ' + (error.message || 'This browser could not open the file.')); }
        }
        status((imported ? imported + ' local ' + (imported === 1 ? 'file added. ' : 'files added. ') + 'Press Launch to play. ' : '') + errors.join(' '), errors.length ? 'error' : 'success');
      });
    });
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
      newEngine(); await defaults(); status('Starter session restored. Your saved session is still available.', 'success');
    }).then(() => $('play-session').focus()));
    document.addEventListener('keydown', event => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.repeat || busy || $('source-dialog').open || /^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName) || event.target.isContentEditable) return;
      if (event.code === 'Space') { if (event.target.closest('button, a')) return; event.preventDefault(); togglePlay(); }
      else if (/^[1-4]$/.test(event.key)) { const c = slotEntries(engine.snapshot(), slots).slice().reverse()[Number(event.key) - 1]; if (c && !c.pending) setSelected(c.id); }
      else if (event.key.toLowerCase() === 'l' && selectedId) run(() => engine.launch(selectedId));
      else if (event.key.toLowerCase() === 'v') vanish();
    });
    root.addEventListener('pagehide', () => engine.pause());
    newEngine(); run(defaults);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true}); else boot();
})(typeof globalThis === 'object' ? globalThis : this);
