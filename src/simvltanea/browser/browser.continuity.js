/* Test-only observer. No compositionRuntime reads, clock writes or media mocks.
 * Arm after initial load/seek/play events settle. An arm window must not cross
 * an authored span boundary; legitimate holds/releases/wraps need new windows.
 */
(() => {
  'use strict';
  if (window.continuityProbe) return;
  let armed = false, stage, initial = [], samples = [], events = [], serial = 0;
  const tokens = new WeakMap(), frames = new WeakMap();
  const token = node => {
    if (!tokens.has(node)) tokens.set(node, ++serial);
    return tokens.get(node);
  };
  const relevant = node => node instanceof Element &&
    (node.matches('#stage,.loop,video,source') || node.querySelector('#stage,.loop,video,source'));
  function record(type, node, detail = null) {
    if (armed) events.push({type, wall: performance.now(), token: token(node),
      id: node.dataset?.loopId ?? null, detail});
  }
  for (const property of ['currentTime', 'src', 'playbackRate']) {
    const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, property);
    if (!descriptor?.set) throw Error(`Missing native media setter: ${property}`);
    Object.defineProperty(HTMLMediaElement.prototype, property, {
      ...descriptor, set(value) { record(`set:${property}`, this, String(value));
        return descriptor.set.call(this, value); },
    });
  }
  for (const method of ['load', 'play', 'pause', 'fastSeek']) {
    const native = HTMLMediaElement.prototype[method];
    if (!native) continue;
    HTMLMediaElement.prototype[method] = function (...args) {
      record(`call:${method}`, this); return native.apply(this, args);
    };
  }
  const observer = new MutationObserver(records => {
    for (const mutation of records) {
      if (mutation.type === 'childList') {
        for (const node of mutation.addedNodes) if (relevant(node)) record('dom:add', node);
        for (const node of mutation.removedNodes) if (relevant(node)) record('dom:remove', node);
      } else if (relevant(mutation.target)) {
        record(`attr:${mutation.attributeName}`, mutation.target, mutation.oldValue);
      }
    }
  });
  observer.observe(document, {subtree: true, childList: true, attributes: true,
    attributeOldValue: true, attributeFilter: ['src', 'data-loop-id']});
  for (const event of ['loadstart','emptied','seeking','seeked','pause','play',
                        'ratechange','ended','error','abort']) {
    document.addEventListener(event, e => {
      if (e.target instanceof HTMLMediaElement) record(`event:${event}`, e.target);
    }, true);
  }
  function track(video) {
    if (frames.has(video)) return;
    if (!video.requestVideoFrameCallback) throw Error('Native decoded-frame callbacks required');
    const stats = {callbacks: 0, mediaTime: null, presentedFrames: null};
    frames.set(video, stats);
    function callback(now, metadata) {
      stats.callbacks += 1; stats.mediaTime = metadata.mediaTime;
      stats.presentedFrames = metadata.presentedFrames;
      if (video.isConnected) video.requestVideoFrameCallback(callback);
    }
    video.requestVideoFrameCallback(callback);
  }
  function pixels(video) {
    const canvas = document.createElement('canvas'); canvas.width = 48; canvas.height = 48;
    const context = canvas.getContext('2d', {willReadFrequently:true});
    context.drawImage(video, 0, 0, 48, 48);
    const data = context.getImageData(0, 0, 48, 48).data;
    let hash = 2166136261;
    for (const byte of data) hash = Math.imul(hash ^ byte, 16777619) >>> 0;
    const index = (6*48+6)*4;
    return {backgroundRGB:[...data.slice(index,index+3)], hash:hash.toString(16)};
  }
  function row(video, includePixels) {
    const box = video.parentElement, rect = box.getBoundingClientRect();
    const quality = video.getVideoPlaybackQuality();
    return {id: video.dataset.loopId, token: token(video), boxToken: token(box),
      src: video.currentSrc, attrSrc: video.getAttribute('src'),
      time: video.currentTime, rate: video.playbackRate, paused: video.paused,
      seeking: video.seeking, readyState: video.readyState,
      connected: video.isConnected, boxId: box.dataset.loopId,
      rect: {x:rect.x,y:rect.y,width:rect.width,height:rect.height},
      fit: getComputedStyle(video).objectFit, display: getComputedStyle(video).display,
      pixels: includePixels ? pixels(video) : null,
      decoded: {...frames.get(video)}, totalFrames: quality.totalVideoFrames,
      droppedFrames: quality.droppedVideoFrames};
  }
  function snapshot(includePixels = false) {
    const videos = [...document.querySelectorAll('#stage video')];
    videos.forEach(track);
    return {wall:performance.now(), viewport:{width:innerWidth,height:innerHeight},
      stageToken:token(document.querySelector('#stage')), stage:stage.getBoundingClientRect().toJSON(),
      boxCount:document.querySelectorAll('#stage > .loop').length,
      loops:videos.map(video => row(video, includePixels))};
  }
  function sample() {
    if (!armed) return;
    samples.push(snapshot()); requestAnimationFrame(sample);
  }
  window.continuityProbe = {
    prepare() {
      stage = document.querySelector('#stage');
      if (!stage) throw Error('Missing stage');
      [...stage.querySelectorAll('video')].forEach(track);
    },
    arm() {
      this.prepare(); observer.takeRecords(); events = []; samples = [];
      initial = snapshot(true); armed = true; sample(); return initial;
    },
    checkpoint() { return snapshot(true); },
    finish() {
      samples.push(snapshot()); armed = false;
      return {initial, samples, events};
    },
  };
})();
