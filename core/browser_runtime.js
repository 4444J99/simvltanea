/* Native-media proof. Schema v1 remains silent; v1.1 audio requires a gesture.
 * Resize mutates geometry and spatial pan only, never source playback state.
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
  orientation: null, layoutIndex: 0, position: 0, generation: 0, starting: false,
  audio: {mode:'none', context:null, enabled:false, buffer:null, source:null, gain:null},
};
function record(type, id, details = {}) {
  runtime.events.push({type, id, frame: runtime.frame, wall: performance.now(), ...details});
}
function setStatus(status,message) {
  stage.dataset.status=status;
  const label=document.querySelector('#runtime-status');
  if(label) label.textContent=message;
}
function fail(error) {
  runtime.error = String(error); runtime.running = false; runtime.ready = false;
  for (const node of runtime.nodes.values()) node.media?.pause?.();
  stopSoundtrack();
  if (runtime.audio.context) runtime.audio.context.suspend().catch(() => {});
  setStatus('error',`Playback stopped: ${String(error)}`);
  record('error', null, {message: String(error)});
}
function compositionTime() {
  if (!runtime.running) return runtime.position;
  return runtime.audio.context ? runtime.audio.context.currentTime-runtime.origin :
    (performance.now()-runtime.origin)/1000;
}
function stopSoundtrack() {
  if (!runtime.audio.source) return;
  runtime.audio.source.onended = null;
  try { runtime.audio.source.stop(); } catch (_) { /* already ended */ }
  runtime.audio.source.disconnect(); runtime.audio.source = null;
}
function holdParameter(param, now) {
  if (param.cancelAndHoldAtTime) param.cancelAndHoldAtTime(now);
  else { const value=param.value; param.cancelScheduledValues(now); param.setValueAtTime(value,now); }
}
function connectLoopAudio(node) {
  if (runtime.audio.mode !== 'spatial_loops' || node.kind !== 'video' || node.audio) return;
  const context=runtime.audio.context;
  const source=context.createMediaElementSource(node.media);
  const pan=context.createStereoPanner(), gain=context.createGain();
  gain.gain.value=0;
  source.connect(pan); pan.connect(gain); gain.connect(context.destination);
  node.audio={source,pan,gain};
}
function scheduleLoopGain(node) {
  if (!node.audio) return;
  const config=runtime.plan.audio, context=runtime.audio.context, now=context.currentTime;
  const param=node.audio.gain.gain;
  const gain=number(config.master_volume)*number(config.per_loop[node.id].gain);
  holdParameter(param,now);
  param.setValueAtTime(node.span.held || !runtime.running ? 0 : gain,now);
  if (!runtime.running || node.span.held) return;
  // A native paused video emits no samples. Anticipate the authored hold by
  // fading its final 50ms, reaching zero exactly when its image freezes.
  const held=node.spans.slice(node.index+1).find(span=>span.held);
  if (held) {
    const until=held.frame/runtime.plan.fps-compositionTime();
    if (until>0) {
      if (until<.05) param.setValueAtTime(gain*until/.05,now);
      else param.setValueAtTime(gain,now+until-.05);
      param.linearRampToValueAtTime(0,now+until);
    }
  }
  param.setValueAtTime(0,runtime.origin+runtime.plan.frames/runtime.plan.fps);
}
function updatePan(node, cell, orientation, orientationChanged) {
  if (!node.audio) return;
  const [x,,width]=cell.rect.map(number);
  const target=runtime.plan.audio.spatial_panning && orientation==='landscape' ? 2*(x+width/2)-1 : 0;
  if (node.audio.panTarget===target) return;
  node.audio.panTarget=target;
  const now=runtime.audio.context.currentTime, param=node.audio.pan.pan;
  holdParameter(param,now);
  if (orientationChanged) param.linearRampToValueAtTime(target,now+.2);
  else param.setValueAtTime(target,now);
  record('audio-pan',node.id,{target,seconds:orientationChanged ? .2 : 0});
}
function startSoundtrack() {
  if (runtime.audio.mode!=='soundtrack') return;
  stopSoundtrack();
  const {context,buffer,gain}=runtime.audio, config=runtime.plan.audio;
  const now=context.currentTime, time=runtime.position, duration=number(config.duration);
  const end=Math.min(runtime.plan.frames/runtime.plan.fps,config.loop ? Infinity : duration);
  const param=gain.gain, volume=number(config.volume);
  const fadeIn=number(config.fade_in_seconds), fadeOut=number(config.fade_out_seconds);
  const level=t=>volume*Math.max(0,Math.min(1,fadeIn ? t/fadeIn : 1,
    fadeOut ? (end-t)/fadeOut : 1));
  holdParameter(param,now); param.setValueAtTime(level(time),now);
  if (time>=end) return;
  // Envelope=min(fade-in,unity,fade-out), including overlapping fades.
  const points=[fadeIn,end-fadeOut,end];
  if (fadeIn+fadeOut>0) points.push(end*fadeIn/(fadeIn+fadeOut));
  [...new Set(points)].filter(t=>t>time && t<=end).sort((a,b)=>a-b)
    .forEach(t=>param.linearRampToValueAtTime(level(t),now+t-time));
  const source=context.createBufferSource(); source.buffer=buffer;
  source.loop=config.loop; source.loopStart=0; source.loopEnd=duration;
  source.connect(gain); source.start(now,config.loop ? time%duration : time);
  source.stop(now+end-time); runtime.audio.source=source;
  source.onended=()=>{
    if (runtime.audio.source===source) {
      source.disconnect(); runtime.audio.source=null; record('soundtrack-ended',null);
    }
  };
  record('soundtrack-start',null,{time,offset:config.loop ? time%duration : time});
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
  const orientationChanged=runtime.orientation!==null && runtime.orientation!==orientation;
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
    updatePan(node,cell,orientation,orientationChanged);
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
    if (node.audio) {
      node.audio.source.disconnect(); node.audio.pan.disconnect(); node.audio.gain.disconnect(); node.audio=null;
    }
    node.media?.remove();
    node.media = document.createElement(span.kind === 'video' ? 'video' : 'img');
    node.media.dataset.loopId = node.id;
    node.media.setAttribute('aria-label', node.id);
    node.box.append(node.media); node.kind = span.kind;
    if (span.kind === 'video') {
      node.media.muted = true; node.media.defaultMuted = true;
      node.media.playsInline = true; node.media.preload = 'auto';
      node.media.preservesPitch = true;
      node.media.addEventListener('loadstart', () => record('loadstart', node.id));
      node.media.addEventListener('seeking', () => record('seeking', node.id));
      node.media.addEventListener('error', () => fail(new Error(`Media failure: ${node.id}`)));
      frameProbe(node);
      connectLoopAudio(node);
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
    node.media.muted = runtime.audio.mode !== 'spatial_loops' || !runtime.audio.enabled;
    node.media.pause();
    if (Math.abs(node.media.currentTime - target) > 0.00001) {
      record('seek-command', node.id, {target, reason: initial ? 'initial' : 'timeline-boundary'});
      await waitFor(node.media, 'seeked', () => { node.media.currentTime = target; });
    }
    if (!initial && runtime.running && !span.held) await node.media.play();
  }
  scheduleLoopGain(node);
  applyLayout();
}
function tick(generation) {
  if (!runtime.running || generation!==runtime.generation) return;
  const frame = Math.floor(compositionTime()*runtime.plan.fps);
  runtime.frame = Math.min(frame, runtime.plan.frames - 1);
  if (frame >= runtime.plan.frames) {
    runtime.running = false; runtime.finished = true;
    runtime.position=runtime.plan.frames/runtime.plan.fps;
    for (const node of runtime.nodes.values()) node.media?.pause?.();
    stopSoundtrack();
    record('finished', null); setStatus('finished','Composition finished.'); return;
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
  requestAnimationFrame(()=>tick(generation));
}
runtime.start = async () => {
  if (!runtime.ready || runtime.running || runtime.starting || runtime.finished || runtime.error) throw new Error('Runtime is not ready');
  runtime.starting=true;
  try {
    if (runtime.audio.context) {
      const context=runtime.audio.context;
      // Called synchronously by the stage gesture: no autoplay policy bypass.
      const resumed=context.resume();
      let timer;
      try { await Promise.race([resumed,new Promise((_,reject)=>{
        timer=setTimeout(()=>reject(new Error('Audio blocked: click or press Space to enable sound')),3000);
      })]); } finally { clearTimeout(timer); }
      if (context.state!=='running') throw new Error('Audio context did not start');
      runtime.audio.enabled=true;
      runtime.audio.blocked=null;
    }
    runtime.origin=runtime.audio.context ? runtime.audio.context.currentTime-runtime.position :
      performance.now()-runtime.position*1000;
    runtime.running=true; runtime.generation++;
    for (const node of runtime.nodes.values()) {
      if (node.kind==='video') node.media.muted=runtime.audio.mode!=='spatial_loops';
      scheduleLoopGain(node);
    }
    startSoundtrack();
    await Promise.all([...runtime.nodes.values()].filter(n => n.kind === 'video' && !n.span.held).map(n => n.media.play()));
    // A decoder error can arrive while play() promises are outstanding.
    // Never turn that terminal error back into an apparent playing state.
    if (runtime.error) throw new Error(runtime.error);
    setStatus('playing',runtime.audio.mode==='none' ? 'Playing · silent field · click or Space to pause' :
      'Playing with sound · click or Space to pause');
    const generation=runtime.generation; requestAnimationFrame(()=>tick(generation));
  } catch (error) {
    if (!runtime.error && runtime.audio.context &&
        (error.name==='NotAllowedError' || String(error).includes('Audio blocked:'))) {
      runtime.running=false; runtime.audio.enabled=false; runtime.audio.blocked=String(error);
      for(const node of runtime.nodes.values()) { node.media?.pause?.(); if(node.kind==='video')node.media.muted=true; }
      stopSoundtrack(); setStatus('audio-blocked','Sound is blocked. Click or press Space to enable playback.');
      record('audio-blocked',null,{message:String(error)});
    } else fail(error);
    throw error;
  }
  finally { runtime.starting=false; }
};
runtime.pause = () => {
  if (runtime.starting || [...runtime.nodes.values()].some(node=>node.busy)) throw new Error('Media transition is still pending');
  if (!runtime.running) return;
  runtime.position=compositionTime(); runtime.running=false; runtime.generation++;
  runtime.frame=Math.min(Math.floor(runtime.position*runtime.plan.fps),runtime.plan.frames-1);
  for (const node of runtime.nodes.values()) { node.media?.pause?.(); scheduleLoopGain(node); }
  stopSoundtrack(); setStatus('paused','Paused · click or Space to resume'); record('paused',null,{time:runtime.position});
};
runtime.resume = runtime.start;
runtime.seek = async seconds => {
  if (!runtime.ready || runtime.error || runtime.starting || [...runtime.nodes.values()].some(node=>node.busy))
    throw new Error('Runtime is not ready to seek');
  if (!Number.isFinite(seconds) || seconds<0 || seconds>=runtime.plan.frames/runtime.plan.fps)
    throw new Error('Seek must remain within composition duration');
  const wasRunning=runtime.running; runtime.pause();
  runtime.position=seconds; runtime.frame=Math.floor(seconds*runtime.plan.fps); runtime.finished=false;
  runtime.layoutIndex=runtime.plan.layout_keyframes.findLastIndex(item=>item.frame<=runtime.frame);
  await Promise.all([...runtime.nodes.values()].map(async node=>{
    node.index=node.spans.findLastIndex(span=>span.frame<=runtime.frame);
    node.busy=true;
    try { await activate(node,node.spans[node.index],seconds*runtime.plan.fps,true); }
    finally { node.busy=false; }
  })).catch(error=>{fail(error);throw error;});
  record('transport-seek',null,{time:seconds}); setStatus('paused','Paused · click or Space to resume');
  if (wasRunning) await runtime.start();
};
runtime.snapshot = () => ({
  frame: runtime.frame, wall: performance.now(), orientation: runtime.orientation,
  running: runtime.running, finished: runtime.finished, error: runtime.error,
  compositionTime:compositionTime(),
  audio:{mode:runtime.audio.mode,enabled:runtime.audio.enabled,contextState:runtime.audio.context?.state??null,
    blocked:runtime.audio.blocked??null,
    soundtrackPlaying:!!runtime.audio.source,gain:runtime.audio.gain?.gain.value??null},
  loops: [...runtime.nodes.values()].map(n => ({
    id:n.id, source:n.source, kind:n.kind, currentTime:n.media.currentTime ?? null,
    rate:n.media.playbackRate ?? 0, paused:n.media.paused ?? true, readyState:n.media.readyState ?? null,
    busy:n.busy, callbacks:n.callbacks, decoded:n.decoded,
    audio:n.audio ? {gain:n.audio.gain.gain.value,pan:n.audio.pan.pan.value}:null,
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
  need(plan && ((plan.plan_version===1 && plan.engine_version==='1.0.0' && plan.audio==='none') ||
    (plan.plan_version===2 && plan.engine_version==='1.1.0' && plan.audio &&
      ['none','soundtrack','spatial_loops'].includes(plan.audio.mode))), 'version/audio');
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
    if (plan.plan_version===2 && plan.audio.mode==='spatial_loops' && source.kind==='video') {
      need(source.audio_stream===null || (source.audio_stream?.codec==='aac' &&
        [1,2].includes(source.audio_stream.channels)), 'spatial source audio capability');
    }
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
  if (plan.plan_version===2) {
    const audio=plan.audio;
    const fields=allowed=>need(Object.keys(audio).every(key=>allowed.includes(key)), 'audio fields');
    const level=value=>number(value)>=0 && number(value)<=1;
    if (audio.mode==='none') {
      fields(['mode','routing','generative']);
      need(audio.routing===null && audio.generative===null,'silent audio');
    } else if (audio.mode==='soundtrack') {
      fields(['mode','source','sha256','duration','volume','loop','fade_in_seconds','fade_out_seconds','asset']);
      need(level(audio.volume) && typeof audio.loop==='boolean' && number(audio.duration)>0 && number(audio.duration)<=600 &&
        number(audio.fade_in_seconds)>=0 && number(audio.fade_out_seconds)>=0, 'soundtrack controls');
      const asset=audio.asset;
      need(asset && asset.id==='soundtrack' && asset.kind==='audio' && hash(asset.sha256) &&
        asset.sha256===audio.sha256 && asset.path===audio.source && asset.duration===audio.duration &&
        new RegExp(`^media/${asset.sha256}\\.(wav|mp3|m4a|ogg|flac)$`).test(asset.path) &&
        integer(asset.bytes,1,256*1024*1024), 'soundtrack asset');
      total+=asset.bytes; need(total<=256*1024*1024,'media memory guard');
    } else {
      fields(['mode','master_volume','spatial_panning','per_loop']);
      need(level(audio.master_volume) && typeof audio.spatial_panning==='boolean' &&
        audio.per_loop && Object.keys(audio.per_loop).length===ids.size,'spatial controls');
      for (const [id,settings] of Object.entries(audio.per_loop)) {
        need(ids.has(id) && settings && Object.keys(settings).every(key=>['gain','mute_on_hold'].includes(key)) &&
          level(settings.gain) && settings.mute_on_hold===true,'per-loop audio');
      }
    }
  }
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
  runtime.audio.mode=runtime.plan.plan_version===1 ? 'none' : runtime.plan.audio.mode;
  const assets=[...runtime.plan.sources];
  if (runtime.audio.mode==='soundtrack') assets.push(runtime.plan.audio.asset);
  let soundtrackBytes;
  for (const source of assets) {
    if (!/^media\/[a-f0-9]{64}\.[a-z0-9]+$/.test(source.path)) throw new Error('Unsafe media URL');
    total += source.bytes;
    if (total > 256*1024*1024) throw new Error('Media memory guard');
    const bytes = await io.bytes(source);
    const digest = await io.digest(bytes);
    if (digest !== source.sha256 || bytes.byteLength !== source.bytes) throw new Error(`Media integrity: ${source.id}`);
    if (source.kind==='audio') { soundtrackBytes=bytes; continue; }
    const type = source.kind === 'video' ? 'video/mp4' : (source.path.endsWith('.png') ? 'image/png' : 'image/jpeg');
    runtime.sources.set(source.id, {url:URL.createObjectURL(new Blob([bytes], {type}))});
  }
  if (runtime.audio.mode!=='none') {
    if (!window.AudioContext) throw new Error('Web Audio is required for this opted-in audio mode');
    runtime.audio.context=new AudioContext({sampleRate:48000});
    if (runtime.audio.mode==='soundtrack') {
      runtime.audio.buffer=await runtime.audio.context.decodeAudioData(soundtrackBytes);
      if (![1,2].includes(runtime.audio.buffer.numberOfChannels))
        throw new Error('Browser soundtrack requires mono or stereo audio');
      const duration=number(runtime.plan.audio.duration);
      if (Math.abs(runtime.audio.buffer.duration-duration)>1/runtime.plan.fps)
        throw new Error('Decoded soundtrack duration differs from verified duration');
      // Probe tolerance permits a partial video frame discrepancy. Pad/trim the
      // decoded PCM to the declared sample count so every loop still uses T.
      const decoded=runtime.audio.buffer, length=Math.round(duration*decoded.sampleRate);
      if (length!==decoded.length) {
        const normalized=runtime.audio.context.createBuffer(decoded.numberOfChannels,length,decoded.sampleRate);
        for(let channel=0;channel<decoded.numberOfChannels;channel++)
          normalized.copyToChannel(decoded.getChannelData(channel).subarray(0,length),channel);
        runtime.audio.buffer=normalized;
      }
      runtime.audio.gain=runtime.audio.context.createGain();
      runtime.audio.gain.gain.value=0;
      runtime.audio.gain.connect(runtime.audio.context.destination);
    }
    runtime.audio.context.addEventListener('statechange',()=>{
      if (runtime.running && !runtime.starting && runtime.audio.context.state!=='running')
        fail(new Error('Audio context interrupted; playback stopped'));
    });
  }
  for (const track of runtime.plan.tracks) {
    if (runtime.nodes.has(track.id)) throw new Error('Duplicate loop');
    const box = document.createElement('div'); box.className = 'loop'; box.dataset.loopId = track.id; stage.append(box);
    runtime.nodes.set(track.id, {id:track.id, box, media:null, kind:null, source:null,
      spans:track.spans, index:0, span:null, callbacks:0, decoded:null, busy:false});
  }
  await Promise.all([...runtime.nodes.values()].map(n => activate(n, n.spans[0], 0, true)));
  if (runtime.error) throw new Error(runtime.error);
  runtime.ready = true;
  setStatus('ready',runtime.audio.mode==='none' ? 'Click or press Space to play the silent field.' :
    'Click or press Space to play with sound.');
  applyLayout();
}
initialize().catch(fail);

// A local preview can be started directly without a developer console.
stage.tabIndex = 0;
stage.addEventListener('click', () => {
  if (!runtime.ready || runtime.starting || runtime.finished || runtime.error) return;
  if (runtime.running) { try { runtime.pause(); } catch (error) { record('transport-busy',null,{message:String(error)}); } }
  else runtime.start().catch(error=>{if(!runtime.audio.blocked)fail(error);});
});
stage.addEventListener('keydown', event => { if (event.code === 'Space') { event.preventDefault(); stage.click(); } });
