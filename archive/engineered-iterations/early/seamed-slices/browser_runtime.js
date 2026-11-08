/* Silent native-media proof. Resize mutates geometry only, never media state.
 * Source/event/clock decisions are compiled by composition.py, not duplicated here.
 * All boundary seeks, loads and decoded-frame callbacks remain inspectable.
 */
'use strict';
const number = value => {
  if ((typeof value !== 'string' && typeof value !== 'number') ||
      !/^-?\d+(?:\/\d+)?$/.test(String(value))) throw new Error('Invalid compiled rational');
  const parts = String(value).split('/').map(Number);
  const result = parts.length === 1 ? parts[0] : parts[0] / parts[1];
  if (!Number.isFinite(result)) throw new Error('Invalid compiled rational');
  return result;
};
const stage = document.querySelector('#stage');
const runtime = window.compositionRuntime = {
  ready: false, running: false, finished: false, error: null, frame: 0,
  events: [], nodes: new Map(), sources: new Map(), plan: null, origin: 0,
  orientation: null, layoutIndex: 0,
};
function record(type, id, details = {}) {
  runtime.events.push({type, id, frame: runtime.frame, wall: performance.now(), ...details});
}
function fail(error) {
  runtime.error = String(error); runtime.running = false; runtime.ready = false;
  for (const node of runtime.nodes.values()) node.media?.pause?.();
  stage.dataset.status = 'error';
  record('error', null, {message: String(error)});
}
function waitFor(media, event, action) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error(`Media timeout: ${event}`)), 10000);
    const good = () => finish();
    const bad = () => finish(new Error('Media decode failed'));
    function finish(error) {
      clearTimeout(timer); media.removeEventListener(event, good);
      media.removeEventListener('error', bad); error ? reject(error) : resolve();
    }
    media.addEventListener(event, good, {once: true});
    media.addEventListener('error', bad, {once: true});
    try { action(); } catch (error) { finish(error); }
  });
}
function frameProbe(node) {
  if (typeof node.media.requestVideoFrameCallback !== 'function') return;
  node.media.requestVideoFrameCallback((now, metadata) => {
    node.decoded = {wall: now, mediaTime: metadata.mediaTime, presentedFrames: metadata.presentedFrames};
    node.callbacks += 1;
    if (node.media.isConnected) frameProbe(node);
  });
}
function applySlice(node) {
  if (!node.span || !node.span.slice_rect) {
    Object.assign(node.media.style, {width:'100%', height:'100%', left:'0', top:'0', marginLeft:'0', marginTop:'0', position:'', transform:''});
    return;
  }
  const [sx, sy, sw, sh] = node.span.slice_rect.map(number);
  // Deterministic source crop: show only slice region stretched to fill placement via overflow:hidden
  // Loop box is overflow:hidden; media is scaled 1/w,1/h and offset -x/w, -y/h
  Object.assign(node.media.style, {
    position:'absolute', left:'0', top:'0',
    width:`${100/sw}%`, height:`${100/sh}%`,
    marginLeft:`${-100*sx/sw}%`, marginTop:`${-100*sy/sh}%`,
    objectFit:'fill'
  });
}
function renderSeams() {
  // Clear old seam overlays
  [...stage.querySelectorAll('.seam')].forEach(el=>el.remove());
  const seam = runtime.plan && runtime.plan.seam;
  if (!seam || !seam.enabled) return;
  const {width, height} = stage.getBoundingClientRect();
  if (width<=0||height<=0) return;
  const seamW = Math.max(4, Math.round(number(seam.width) * width));
  const seamH = Math.max(4, Math.round(number(seam.width) * height));
  const sigma = seam.sigma ? number(seam.sigma) * Math.min(width,height) : 6;
  const layout = runtime.plan.layout_keyframes[runtime.layoutIndex].layouts[runtime.orientation];
  if (!layout) return;
  const cells = layout.cells.map(c=>({loop:c.loop, rect:c.rect.map(number)}));
  for (let i=0;i<cells.length;i++) for(let j=i+1;j<cells.length;j++){
    const a=cells[i], b=cells[j];
    const [ax,ay,aw,ah]=a.rect, [bx,by,bw,bh]=b.rect;
    const axpx=ax*width, aypx=ay*height, awpx=aw*width, ahpx=ah*height;
    const bxpx=bx*width, bypx=by*height, bwpx=bw*width, bhpx=bh*height;
    const vertOverlap = Math.min(aypx+ahpx, bypx+bhpx) - Math.max(aypx, bypx);
    const horizOverlap = Math.min(axpx+awpx, bxpx+bwpx) - Math.max(axpx, bxpx);
    let el=null;
    if (vertOverlap>0 && Math.abs((axpx+awpx)-bxpx)<=seamW*2) {
      const x=(axpx+awpx+bxpx)/2;
      el=document.createElement('div'); el.className='seam';
      Object.assign(el.style,{left:`${x-seamW/2}px`, top:`${Math.max(aypx,bypx)}px`, width:`${seamW}px`, height:`${vertOverlap}px`, position:'absolute', background:'rgba(0,0,0,0)', backdropFilter:`blur(${Math.max(2,sigma/2)}px)`, WebkitBackdropFilter:`blur(${Math.max(2,sigma/2)}px)`, filter: seam.mode==='morph'?`blur(${Math.max(2,sigma/3)}px) contrast(1.05)`:`blur(${Math.max(2,sigma/2)}px)`, pointerEvents:'none', zIndex:'10', mixBlendMode: seam.mode==='morph'?'screen':'normal', opacity: seam.mode==='feather'?'0.95':'0.85'});
    } else if (vertOverlap>0 && Math.abs((bxpx+bwpx)-axpx)<=seamW*2) {
      const x=(bxpx+bwpx+axpx)/2;
      el=document.createElement('div'); el.className='seam';
      Object.assign(el.style,{left:`${x-seamW/2}px`, top:`${Math.max(aypx,bypx)}px`, width:`${seamW}px`, height:`${vertOverlap}px`, position:'absolute', background:'rgba(0,0,0,0)', backdropFilter:`blur(${Math.max(2,sigma/2)}px)`, WebkitBackdropFilter:`blur(${Math.max(2,sigma/2)}px)`, filter:`blur(${Math.max(2,sigma/2)}px)`, pointerEvents:'none', zIndex:'10'});
    } else if (horizOverlap>0 && Math.abs((aypx+ahpx)-bypx)<=seamH*2) {
      const y=(aypx+ahpx+bypx)/2;
      el=document.createElement('div'); el.className='seam';
      Object.assign(el.style,{left:`${Math.max(axpx,bxpx)}px`, top:`${y-seamH/2}px`, width:`${horizOverlap}px`, height:`${seamH}px`, position:'absolute', background:'rgba(0,0,0,0)', backdropFilter:`blur(${Math.max(2,sigma/2)}px)`, WebkitBackdropFilter:`blur(${Math.max(2,sigma/2)}px)`, filter:`blur(${Math.max(2,sigma/2)}px)`, pointerEvents:'none', zIndex:'10'});
    } else if (horizOverlap>0 && Math.abs((bypx+bhpx)-aypx)<=seamH*2) {
      const y=(bypx+bhpx+aypx)/2;
      el=document.createElement('div'); el.className='seam';
      Object.assign(el.style,{left:`${Math.max(axpx,bxpx)}px`, top:`${y-seamH/2}px`, width:`${horizOverlap}px`, height:`${seamH}px`, position:'absolute', background:'rgba(0,0,0,0)', backdropFilter:`blur(${Math.max(2,sigma/2)}px)`, WebkitBackdropFilter:`blur(${Math.max(2,sigma/2)}px)`, filter:`blur(${Math.max(2,sigma/2)}px)`, pointerEvents:'none', zIndex:'10'});
    }
    if (el) stage.append(el);
  }
  // Fallback N=2 gap case
  if (stage.querySelectorAll('.seam').length===0 && cells.length===2) {
    const a=cells[0], b=cells[1];
    const ax=ax=>ax*width, ay=ay=>ay*height; // dummy to avoid lint
    if (Math.abs(a.rect[0]-b.rect[0])<0.01 && a.rect[1]!==b.rect[1]) {
      const y=(a.rect[1]+a.rect[3]+b.rect[1])/2*height;
      const el=document.createElement('div'); el.className='seam';
      Object.assign(el.style,{left:`${Math.max(a.rect[0],b.rect[0])*width}px`, top:`${y-seamH/2}px`, width:`${Math.min(a.rect[2],b.rect[2])*width}px`, height:`${seamH}px`, position:'absolute', backdropFilter:`blur(${Math.max(2,sigma/2)}px)`, filter:`blur(${Math.max(2,sigma/2)}px)`, zIndex:'10', pointerEvents:'none'});
      stage.append(el);
    } else if (Math.abs(a.rect[1]-b.rect[1])<0.01 && a.rect[0]!==b.rect[0]) {
      const x=(a.rect[0]+a.rect[2]+b.rect[0])/2*width;
      const el=document.createElement('div'); el.className='seam';
      Object.assign(el.style,{left:`${x-seamW/2}px`, top:`${a.rect[1]*height}px`, width:`${seamW}px`, height:`${a.rect[3]*height}px`, position:'absolute', backdropFilter:`blur(${Math.max(2,sigma/2)}px)`, filter:`blur(${Math.max(2,sigma/2)}px)`, zIndex:'10', pointerEvents:'none'});
      stage.append(el);
    }
  }
}
function applyLayout() {
  if (!runtime.plan || runtime.nodes.size !== runtime.plan.tracks.length) return;
  const {width, height} = stage.getBoundingClientRect();
  if (width <= 0 || height <= 0) return;
  const orientation = width >= height ? 'landscape' : 'portrait';
  const layout = runtime.plan.layout_keyframes[runtime.layoutIndex].layouts[orientation];
  runtime.orientation = orientation;
  layout.cells.forEach((cell, z) => {
    const node = runtime.nodes.get(cell.loop);
    const [x,y,w,h] = cell.rect.map(number);
    Object.assign(node.box.style, {left:`${x*100}%`, top:`${y*100}%`,
      width:`${w*100}%`, height:`${h*100}%`, zIndex:String(z), overflow:'hidden'});
    // Default focal/cover; slice overrides via applySlice per span
    if (!node.span || !node.span.slice_rect) {
      node.media.style.objectFit = cell.fit;
      node.media.style.objectPosition = cell.focal.map(v => `${number(v)*100}%`).join(' ');
    }
  });
  // Apply per-loop slice if active
  for (const node of runtime.nodes.values()) applySlice(node);
  renderSeams();
  record('layout', null, {orientation, width, height});
}
new ResizeObserver(applyLayout).observe(stage);

async function activate(node, span, frame, initial = false) {
  const source = runtime.sources.get(span.source);
  const kindChange = node.kind !== span.kind;
  if (kindChange) {
    node.media?.pause?.();
    node.media?.remove();
    node.media = document.createElement(span.kind === 'video' ? 'video' : 'img');
    node.media.dataset.loopId = node.id;
    node.media.setAttribute('aria-label', node.id);
    node.box.append(node.media); node.kind = span.kind;
    if (span.kind === 'video') {
      node.media.muted = true; node.media.defaultMuted = true;
      node.media.playsInline = true; node.media.preload = 'auto';
      node.media.addEventListener('loadstart', () => record('loadstart', node.id));
      node.media.addEventListener('seeking', () => record('seeking', node.id));
      node.media.addEventListener('error', () => fail(new Error(`Media failure: ${node.id}`)));
      frameProbe(node);
    }
  }
  const sourceChanged = node.source !== span.source || kindChange;
  node.span = span; node.source = span.source; node.slice_rect = span.slice_rect;
  if (sourceChanged) {
    record('source', node.id, {source: span.source});
    if (span.kind === 'video') await waitFor(node.media, 'loadeddata', () => { node.media.src = source.url; });
    else await waitFor(node.media, 'load', () => { node.media.src = source.url; });
  }
  if (span.kind === 'video') {
    const elapsed = (frame - span.frame) / runtime.plan.fps;
    const target = number(span.source_offset) + (span.held ? 0 : elapsed * number(span.rate));
    node.media.playbackRate = number(span.rate);
    node.media.pause();
    if (Math.abs(node.media.currentTime - target) > 0.00001) {
      record('seek-command', node.id, {target, reason: initial ? 'initial' : 'timeline-boundary'});
      await waitFor(node.media, 'seeked', () => { node.media.currentTime = target; });
    }
    if (!initial && runtime.running && !span.held) await node.media.play();
  }
  applyLayout();
}
function tick() {
  if (!runtime.running) return;
  const frame = Math.floor((performance.now() - runtime.origin) * runtime.plan.fps / 1000);
  runtime.frame = Math.min(frame, runtime.plan.frames - 1);
  if (frame >= runtime.plan.frames) {
    runtime.running = false; runtime.finished = true;
    for (const node of runtime.nodes.values()) node.media?.pause?.();
    record('finished', null); stage.dataset.status = 'finished'; return;
  }
  try {
    const layouts = runtime.plan.layout_keyframes;
    while (runtime.layoutIndex + 1 < layouts.length && layouts[runtime.layoutIndex + 1].frame <= frame) {
      runtime.layoutIndex += 1; applyLayout();
    }
    for (const node of runtime.nodes.values()) {
      if (node.busy) continue;
      let next = node.index;
      while (next + 1 < node.spans.length && node.spans[next + 1].frame <= frame) next += 1;
      if (next !== node.index) {
        node.index = next; node.busy = true;
        activate(node, node.spans[next], frame).catch(fail).finally(() => { node.busy = false; });
      }
    }
  } catch (error) { fail(error); }
  requestAnimationFrame(tick);
}
runtime.start = async () => {
  if (!runtime.ready || runtime.running || runtime.finished || runtime.error) throw new Error('Runtime is not ready');
  runtime.origin = performance.now(); runtime.running = true;
  try {
    await Promise.all([...runtime.nodes.values()].filter(n => n.kind === 'video' && !n.span.held).map(n => n.media.play()));
    // A decoder error can arrive while play() promises are outstanding.
    // Never turn that terminal error back into an apparent playing state.
    if (runtime.error) throw new Error(runtime.error);
    stage.dataset.status = 'playing'; requestAnimationFrame(tick);
  } catch (error) { fail(error); throw error; }
};
runtime.snapshot = () => ({
  frame: runtime.frame, wall: performance.now(), orientation: runtime.orientation,
  running: runtime.running, finished: runtime.finished, error: runtime.error,
  loops: [...runtime.nodes.values()].map(n => ({
    id:n.id, source:n.source, kind:n.kind, currentTime:n.media.currentTime ?? null,
    rate:n.media.playbackRate ?? 0, paused:n.media.paused ?? true, readyState:n.media.readyState ?? null,
    busy:n.busy, callbacks:n.callbacks, decoded:n.decoded,
    rect:n.box.getBoundingClientRect().toJSON(),
    quality:n.media.getVideoPlaybackQuality?.().toJSON?.() ?? (n.kind === 'video' ? {
      totalVideoFrames:n.media.getVideoPlaybackQuality().totalVideoFrames,
      droppedVideoFrames:n.media.getVideoPlaybackQuality().droppedVideoFrames} : null),
  })),
  eventCount: runtime.events.length,
});
// Tests may supply file-backed IO without enabling network access. Playback,
// layout, integrity comparisons and event handling use the identical code path.
const io = window.compositionIO || {
  async plan() {
    const response = await fetch('plan.json');
    if (!response.ok) throw new Error('Cannot load compiled plan');
    return response.json();
  },
  async bytes(source) {
    const response = await fetch(source.path);
    if (!response.ok) throw new Error(`Missing media: ${source.id}`);
    return response.arrayBuffer();
  },
  async digest(bytes) {
    if (!crypto.subtle) throw new Error('Secure context required for media hashing');
    return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2,'0')).join('');
  },
};
// Validate the transport document before IO or DOM mutation. This checks the
// compiled envelope and references; it does not choose media or resolve events.
function validatePlan(plan) {
  const need = (test, reason) => { if (!test) throw new Error(`Invalid compiled plan: ${reason}`); };
  const integer = (value, low, high) => Number.isSafeInteger(value) && value >= low && value <= high;
  const ident = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  need(plan && plan.plan_version === 1 && plan.engine_version === '1.0.0' && plan.audio === 'none', 'version/audio');
  need(hash(plan.state_sha256), 'state hash');
  need(integer(plan.fps, 1, 60) && integer(plan.frames, 1, 14400), 'time bounds');
  need(Array.isArray(plan.tracks) && integer(plan.tracks.length, 1, 32), 'loop guard');
  need(Array.isArray(plan.sources) && plan.sources.length > 0, 'sources');
  const sources = new Map(); let total = 0;
  for (const source of plan.sources) {
    need(source && ident(source.id) && !sources.has(source.id), 'source identity');
    need(hash(source.sha256) && integer(source.bytes, 1, 256*1024*1024), 'media metadata');
    const extension = source.kind === 'video' ? 'mp4' : '(?:png|jpe?g)';
    need(['video','still'].includes(source.kind) &&
      new RegExp(`^media/${source.sha256}\\.${extension}$`).test(source.path), 'media path/kind');
    need(number(source.duration) > 0, 'source duration');
    total += source.bytes; need(total <= 256*1024*1024, 'media memory guard');
    sources.set(source.id, source);
  }
  const ids = new Set(); let spanCount = 0;
  for (const track of plan.tracks) {
    need(track && ident(track.id) && !ids.has(track.id), 'loop identity'); ids.add(track.id);
    need(Array.isArray(track.spans) && integer(track.spans.length, 1, plan.frames), 'spans');
    let last = -1;
    for (const span of track.spans) {
      need(span && span.id === track.id && integer(span.frame, 0, plan.frames-1) &&
        span.frame > last && (last !== -1 || span.frame === 0), 'span order/identity');
      last = span.frame;
      const source = sources.get(span.source);
      need(source && span.kind === source.kind && typeof span.held === 'boolean', 'span source/kind/hold');
      const rate = number(span.rate), offset = number(span.source_offset);
      need(rate > 0 && rate <= 8 && (span.kind !== 'video' || rate >= 1/16), 'browser video rate');
      need(offset >= 0 && offset < number(source.duration), 'source offset');
      spanCount++;
    }
  }
  need(spanCount <= 1024 * plan.tracks.length, 'span resource guard');
  need(Array.isArray(plan.layout_keyframes) && integer(plan.layout_keyframes.length, 1, plan.frames), 'layouts');
  let last = -1;
  for (const keyframe of plan.layout_keyframes) {
    need(keyframe && integer(keyframe.frame, 0, plan.frames-1) && keyframe.frame > last &&
      (last !== -1 || keyframe.frame === 0), 'layout order'); last = keyframe.frame;
    for (const orientation of ['portrait','landscape']) {
      const cells = keyframe.layouts?.[orientation]?.cells;
      need(Array.isArray(cells) && cells.length === ids.size, 'paired layout cells');
      const mapped = new Set(), rectangles = [];
      for (const cell of cells) {
        need(cell && ids.has(cell.loop) && !mapped.has(cell.loop), 'one cell per loop'); mapped.add(cell.loop);
        need(['contain','cover'].includes(cell.fit) && Array.isArray(cell.rect) && cell.rect.length === 4 &&
          Array.isArray(cell.focal) && cell.focal.length === 2, 'geometry/fit');
        const [x,y,w,h] = cell.rect.map(number), focal = cell.focal.map(number);
        need(x >= 0 && y >= 0 && w > 0 && h > 0 && x+w <= 1+1e-12 && y+h <= 1+1e-12 &&
          focal.every(v => v >= 0 && v <= 1), 'visible geometry');
        for (const [a,b,c,d] of rectangles)
          need(Math.min(x+w,a+c)-Math.max(x,a) <= 1e-12 ||
            Math.min(y+h,b+d)-Math.max(y,b) <= 1e-12, 'overlapping cells');
        rectangles.push([x,y,w,h]);
      }
    }
  }
}
async function initialize() {
  runtime.plan = await io.plan();
  validatePlan(runtime.plan);
  let total = 0;
  for (const source of runtime.plan.sources) {
    if (!/^media\/[a-f0-9]{64}\.[a-z0-9]+$/.test(source.path)) throw new Error('Unsafe media URL');
    total += source.bytes;
    if (total > 256*1024*1024) throw new Error('Media memory guard');
    const bytes = await io.bytes(source);
    const digest = await io.digest(bytes);
    if (digest !== source.sha256 || bytes.byteLength !== source.bytes) throw new Error(`Media integrity: ${source.id}`);
    const type = source.kind === 'video' ? 'video/mp4' : (source.path.endsWith('.png') ? 'image/png' : 'image/jpeg');
    runtime.sources.set(source.id, {url:URL.createObjectURL(new Blob([bytes], {type}))});
  }
  for (const track of runtime.plan.tracks) {
    if (runtime.nodes.has(track.id)) throw new Error('Duplicate loop');
    const box = document.createElement('div'); box.className = 'loop'; box.dataset.loopId = track.id; stage.append(box);
    runtime.nodes.set(track.id, {id:track.id, box, media:null, kind:null, source:null,
      spans:track.spans, index:0, span:null, callbacks:0, decoded:null, busy:false});
  }
  await Promise.all([...runtime.nodes.values()].map(n => activate(n, n.spans[0], 0, true)));
  if (runtime.error) throw new Error(runtime.error);
  runtime.ready = true; stage.dataset.status = 'ready'; applyLayout();
}
initialize().catch(fail);

// A local preview can be started directly without a developer console.
stage.tabIndex = 0;
stage.addEventListener('click', () => { if (runtime.ready && !runtime.running && !runtime.finished && !runtime.error) runtime.start().catch(fail); });
stage.addEventListener('keydown', event => { if (event.code === 'Space') { event.preventDefault(); stage.click(); } });
