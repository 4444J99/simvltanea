/* Standalone macOS verification. Never loaded by Studio or substituted for its runtime.
 * NODE_PATH must point to an isolated playwright@1.65.0 installation.
 * Usage: node src/simvltanea/browser/verify_webkit_sustained.js SITE OUTPUT
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {once} = require('node:events');
const DURATION_MS = 180000, SAMPLE_MS = 137, MAX_HOLD_MS = 2000;
const REGIMES = ['SPARSE_BREATH', 'STEADY_FLOW', 'BURST_CHORUS'];
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const save = (out, name, value) => fs.writeFileSync(path.join(out, name), JSON.stringify(value, null, 2) + '\n');
const assert = (condition, message) => { if (!condition) throw new Error(message); };

// Read-only observations: no init scripts, graph probes, pixel reads, retained
// media references or prototype patches are installed in the sustained runs.
function sample(includeTrace = false) {
  const runtime = globalThis.compositionRuntime, wall = performance.now();
  const decks = [...runtime.slots.values()].flatMap(node => node.decks.map((deck, index) => {
    const media = deck.media, quality = media.getVideoPlaybackQuality?.();
    return {id: node.id, deck: index, active: node.active === deck,
      populated: media.hasAttribute('src'), src: media.src, currentSrc: media.currentSrc,
      duration: media.duration, current: media.currentTime, decoded: deck.decoded?.mediaTime,
      callbacks: deck.callbacks, paused: media.paused, seeking: media.seeking, ready: media.readyState,
      muted: media.muted, weight: deck.weight, audio: deck.binding ? {
        target: deck.binding.target, gain: deck.binding.gain.gain.value,
        filterHz: deck.binding.filter.frequency.value, pan: deck.binding.pan.pan.value} : null,
      width: media.videoWidth, height: media.videoHeight,
      quality: quality ? {creationTime: Number(quality.creationTime),
        totalVideoFrames: Number(quality.totalVideoFrames), droppedVideoFrames: Number(quality.droppedVideoFrames),
        corruptedVideoFrames: Number(quality.corruptedVideoFrames)} : null,
      nativeError: media.error ? {code: media.error.code, message: media.error.message} : null,
      progress: deck.progress?.snapshot(wall, includeTrace)};
  }));
  return {wall, progressSummary: runtime.proofProgressSummary?.(wall, includeTrace), epochMs: Date.now(), timeOrigin: performance.timeOrigin, simTime: runtime.clock.simTime,
    running: runtime.running, hidden: document.hidden, draining: runtime.draining,
    lastFailure: runtime.lastFailure,
    foregroundLimit: runtime.maxForeground, standbys: runtime.activeStandbys,
    maxStandbys: runtime.maxConcurrentStandbys, audioState: runtime.audio.context?.state,
    audioCurrentTime: runtime.audio.context?.currentTime,
    audioSampleRate: runtime.audio.context?.sampleRate, masterGain: runtime.master?.volume?.gain.value,
    sound: {...runtime.sound}, audioEnabled: runtime.audio.enabled,
    populated: decks.filter(deck => deck.populated).length,
    playing: decks.filter(deck => deck.populated && !deck.paused).length, decks,
    nodes: [...runtime.nodes.values()].map(node => ({id: node.id, item: node.item?.name,
      sha: node.item?.sha256, birth: node.birthTime, deck: node.decks.indexOf(node.active),
      phase: node.phase, busy: node.busy, resting: node.resting, targetGain: node.targetGain,
      geometry: node.geometry, rect: node.cell?.rect,
      current: node.media?.currentTime, decoded: node.decoded?.mediaTime,
      callbacks: node.callbacks, progress: node.active?.progress?.snapshot(wall), paused: node.media?.paused, seeking: node.media?.seeking,
      ready: node.media?.readyState, nativeError: node.media?.error ?
        {code: node.media.error.code, message: node.media.error.message} : null}))};
}

function validProgress(progress, wall, foreground = false) {
  if (!Number.isFinite(wall) || wall < 0 || !progress || progress.schema !== 1 || progress.supported !== true || progress.live !== true ||
      typeof progress.url !== 'string' || !progress.url.startsWith('blob:') ||
      !Number.isSafeInteger(progress.epoch) || progress.epoch < 1 ||
      !Number.isSafeInteger(progress.changes) || !Number.isSafeInteger(progress.sourceChanges) ||
      progress.sourceChanges < 0 || progress.changes < progress.sourceChanges) return false;
  if (progress.sourceChanges > 0 && (!Number.isFinite(progress.lastChangeWall) || progress.lastChangeWall < 0 ||
      progress.lastChangeWall > wall || !Number.isFinite(progress.mediaTime) || progress.mediaTime < 0)) return false;
  if (![progress.maxGapMs, progress.currentGapMs, progress.lifetimeMaxGapMs].every(value => Number.isFinite(value) && value >= 0) ||
      progress.maxGapMs < progress.currentGapMs || progress.lifetimeMaxGapMs < progress.maxGapMs) return false;
  if (foreground && (progress.foreground !== true || progress.running !== true ||
      !Number.isFinite(progress.foregroundSince) || !Number.isFinite(progress.lastForegroundChangeWall) ||
      progress.foregroundSince < 0 || progress.lastForegroundChangeWall < 0 ||
      progress.foregroundSince > progress.lastForegroundChangeWall || progress.lastForegroundChangeWall > wall ||
      Math.abs(progress.currentGapMs - (wall - progress.lastForegroundChangeWall)) > .001)) return false;
  return true;
}

function traceFrames(result, url) {
  const frames = [], owners = new Set(), observedChanges = new Map();
  let invalid = false, nativeFailure = false;
  const inspect = (progress, id, deck, capturedAt, nativeError) => {
    if (progress?.url !== url) return;
    if (nativeError) nativeFailure = true;
    if (!Array.isArray(progress.trace)) return;
    if (progress.schema !== 1 || progress.supported !== true || typeof id !== 'string' ||
        ![0, 1].includes(deck) || !Number.isSafeInteger(progress.epoch) || progress.epoch < 1 ||
        !Number.isSafeInteger(progress.changes) || !Number.isSafeInteger(progress.sourceChanges) ||
        progress.sourceChanges < progress.trace.length || progress.changes < progress.sourceChanges ||
        progress.trace.length > 128 || !Number.isFinite(capturedAt)) {
      invalid = true; return;
    }
    owners.add(JSON.stringify([id, deck, progress.epoch]));
    let previous;
    for (const point of progress.trace) {
      if (!point || !Number.isFinite(point.wall) || point.wall < 0 || point.wall > capturedAt || !Number.isFinite(point.mediaTime) || point.mediaTime < 0 ||
          !Number.isSafeInteger(point.changes) || point.changes < 1 || point.changes > progress.changes ||
          (previous && (point.wall <= previous.wall || point.changes !== previous.changes + 1 || point.mediaTime === previous.mediaTime))) {
        invalid = true; break;
      }
      const identity = JSON.stringify([id, deck, progress.epoch, point.changes]), observed = observedChanges.get(identity);
      if (observed && (observed.wall !== point.wall || observed.mediaTime !== point.mediaTime)) { invalid = true; break; }
      observedChanges.set(identity, point);
      frames.push({wall: point.wall, id, deck, epoch: progress.epoch, decoded: point.mediaTime,
        changes: point.changes, nativeError: nativeError || null, origin: 'callback-trace'});
      previous = point;
    }
    if (previous && (previous.changes !== progress.changes || previous.wall !== progress.lastChangeWall ||
        previous.mediaTime !== progress.mediaTime)) invalid = true;
  };
  for (const row of result.samples || []) {
    for (const deck of row.decks || []) {
      if ((deck.src === url || deck.currentSrc === url) && deck.nativeError) nativeFailure = true;
      if (deck.progress?.url === url && deck.src === url && deck.currentSrc === url) {
        if (deck.progress.live !== true) invalid = true;
        inspect(deck.progress, deck.id, deck.deck, row.wall, deck.nativeError);
      }
    }
    for (const retired of row.progressSummary?.retired || []) {
      if (!retired) { invalid = true; continue; }
      if (retired.url !== url) continue;
      if (retired.live !== false || !Number.isFinite(retired.retiredAt) || retired.retiredAt < 0 || retired.retiredAt > row.wall)
        invalid = true;
      inspect(retired, retired.id, retired.deck, Math.min(row.wall, retired.retiredAt), retired.nativeError);
    }
  }
  return {frames: invalid || nativeFailure || owners.size > 1 ? [] : frames,
    invalid, nativeFailure, ambiguous: owners.size > 1};
}

function classifyResourceErrors(result) {
  const classified = {expectedRetirements: [], expectedAborts: [], recoveredReads: [], unexpected: []};
  const nativeBlobError = /^The operation couldn[’']t be completed\. \(WebKitBlobResource error 1\.\)$/;
  for (const kind of ['consoleErrors', 'requestFailures']) {
    for (const [index, error] of (result[kind] || []).entries()) {
      const reference = {kind, index, url: error?.url, wall: error?.wall};
      const url = error?.url, wall = error?.wall;
      const blob = typeof url === 'string' && url.startsWith('blob:') && Number.isFinite(wall);
      const cancelled = kind === 'requestFailures' && ['cancelled', 'net::ERR_ABORTED'].includes(error.failure?.errorText);
      const aborted = cancelled && error.resourceType === 'fetch' && typeof url === 'string' && /^https?:\/\//.test(url) &&
        Number.isFinite(wall) && (result.events || []).find(event => event.type === 'asset-request-aborted' &&
          event.url === url && Number.isFinite(event.wall) && wall >= event.wall && wall - event.wall <= 1000);
      if (aborted) {
        classified.expectedAborts.push({...reference, abortedAt: aborted.wall, lagMs: wall - aborted.wall});
        continue;
      }
      const expectedType = kind === 'consoleErrors'
        ? typeof error.message === 'string' && error.message.startsWith('Failed to load resource: ') &&
          nativeBlobError.test(error.message.slice('Failed to load resource: '.length))
        : cancelled || nativeBlobError.test(error.failure?.errorText || '');
      const retired = blob && expectedType && (result.events || []).find(event => {
        const lag = wall - event.wall;
        if (event.type !== 'resource-retired' || !['deck', 'metadata'].includes(event.role) || event.url !== url ||
            event.readyState !== 0 || event.paused !== true || !Number.isFinite(event.wall) || lag < 0) return false;
        // Cancellation delivery is asynchronous. Identity and confirmed disposal,
        // not runner receipt latency, determine whether this is the retired read.
        // Reject re-admission anywhere after disposal, including after the error.
        // A cleared inactive deck may retain a stale native currentSrc value.
        return !(result.samples || []).some(row => row.wall >= event.wall &&
          (row.decks || []).some(deck => deck.populated && (deck.src === url || (deck.active && deck.currentSrc === url))));
      });
      if (retired) {
        classified.expectedRetirements.push({...reference, role: retired.role, id: retired.id,
          retiredAt: retired.wall, lagMs: wall - retired.wall});
        continue;
      }
      // A cancelled internal read can coexist with successful decoding. Require
      // positive same-deck, same-native-source evidence; callback counts alone
      // or a future retirement are insufficient. Console failures never qualify.
      if (blob && cancelled) {
        const frames = [], previous = new Map();
        for (const row of result.samples || []) if (row.wall >= wall && row.wall <= wall + 1000) {
          for (const deck of row.decks || []) if (deck.src === url && deck.currentSrc === url) {
            if (result.progressSchema === 1 && (!validProgress(deck.progress, row.wall) || deck.progress.url !== url)) continue;
            frames.push({wall: row.wall, id: deck.id, deck: deck.deck, epoch: deck.progress?.epoch,
              decoded: deck.decoded, callbacks: deck.callbacks, nativeError: deck.nativeError});
          }
        }
        const trace = traceFrames(result, url);
        frames.push(...trace.frames.filter(frame => frame.wall >= wall && frame.wall <= wall + 1000));
        frames.sort((a, b) => a.wall - b.wall);
        if (!trace.invalid && !trace.nativeFailure && !trace.ambiguous && frames.length && frames.every(frame => !frame.nativeError)) {
          let proof;
          for (const frame of frames) {
            const sequence = frame.origin === 'callback-trace' ? frame.changes : frame.callbacks;
            if (typeof frame.id !== 'string' || !Number.isFinite(frame.deck) ||
                !Number.isFinite(frame.decoded) || !Number.isFinite(sequence)) continue;
            const identity = JSON.stringify([frame.id, frame.deck, frame.epoch, frame.origin]), old = previous.get(identity);
            const oldSequence = old?.origin === 'callback-trace' ? old.changes : old?.callbacks;
            if (old && frame.wall > old.wall && frame.decoded !== old.decoded && sequence > oldSequence) {
              proof = [old, frame]; break;
            }
            previous.set(identity, frame);
          }
          if (proof) { classified.recoveredReads.push({...reference, frames: proof}); continue; }
        }
      }
      classified.unexpected.push(reference);
    }
  }
  return classified;
}

// Progress maxima are recorded by the existing native frame callback, including
// source retirement. Host polling cannot infer a freeze from equal loop phases
// across a long observation gap, nor prove that an unseen interval was healthy.
function progressCoverage(result) {
  const native = result.progressSchema === 1, issues = [], invalidRows = new Set(), history = new Map();
  const hasProgress = result.samples.some(row => row.progressSummary != null ||
    row.nodes.some(node => node.progress != null) || (row.decks || []).some(deck => deck.progress != null));
  let issueCount = 0, maxSampleGapMs = 0, maxGapMs = 0, previousWall, previousSummary;
  let nativeErrors = 0, suspensions = 0;
  const issue = (index, reason) => {
    issueCount++; invalidRows.add(index);
    if (issues.length < 32) issues.push({index, wall: result.samples[index]?.wall, reason});
  };
  for (const [index, row] of result.samples.entries()) {
    if (!Number.isFinite(row.wall) || row.wall < 0 || (previousWall !== undefined && row.wall <= previousWall))
      issue(index, 'invalid sample clock');
    const gap = previousWall === undefined ? 0 : row.wall - previousWall;
    maxSampleGapMs = Math.max(maxSampleGapMs, gap); previousWall = row.wall;
    if (!native) {
      if (result.progressSchema !== undefined || hasProgress) issue(index, 'missing or unsupported progress schema');
      if (gap >= MAX_HOLD_MS) issue(index, 'observation gap without native progress coverage');
      continue;
    }
    const summary = row.progressSummary;
    if (!summary || summary.schema !== 1 || summary.supported !== true ||
        !Number.isFinite(summary.maxGapMs) || summary.maxGapMs < 0 ||
        !Number.isSafeInteger(summary.retiredCount) || summary.retiredCount < 0 ||
        !Number.isSafeInteger(summary.suspensionCount) || summary.suspensionCount < 0 ||
        !Array.isArray(summary.retired) || summary.retired.length > 16) {
      issue(index, 'missing or malformed native progress summary'); continue;
    }
    if (previousSummary && (summary.maxGapMs < previousSummary.maxGapMs ||
        summary.retiredCount < previousSummary.retiredCount || summary.suspensionCount < previousSummary.suspensionCount))
      issue(index, 'native session counters regressed');
    if (previousSummary) suspensions += Math.max(0, summary.suspensionCount - previousSummary.suspensionCount);
    previousSummary = summary;
    maxGapMs = Math.max(maxGapMs, summary.maxGapMs);
    const decks = new Map();
    if (!Array.isArray(row.decks) || row.decks.length > 8) issue(index, 'missing or unbounded deck observations');
    for (const deck of row.decks || []) {
      const key = JSON.stringify([deck.id, deck.deck]);
      if (typeof deck.id !== 'string' || ![0, 1].includes(deck.deck) || decks.has(key)) issue(index, 'invalid deck identity');
      decks.set(key, deck);
      if (!deck.populated) continue;
      const p = deck.progress;
      if (!validProgress(p, row.wall, !!p?.foreground) || p.url !== deck.src ||
          (p.foreground && (deck.currentSrc !== p.url || deck.paused)) ||
          summary.maxGapMs < p.lifetimeMaxGapMs) {
        issue(index, 'missing or inconsistent source progress'); continue;
      }
      const old = history.get(key);
      if (old && (p.epoch < old.epoch || p.changes < old.changes || p.lifetimeMaxGapMs < old.lifetimeMaxGapMs ||
          (p.epoch === old.epoch && (p.url !== old.url || p.sourceChanges < old.sourceChanges || p.maxGapMs < old.maxGapMs))))
        issue(index, 'source progress counters regressed or changed identity');
      history.set(key, p);
    }
    for (const node of row.nodes) {
      const deck = decks.get(JSON.stringify([node.id, node.deck])), p = node.progress;
      if (!deck?.active || !deck.populated || !validProgress(p, row.wall, true) || p.sourceChanges < 1 ||
          p.url !== deck.src || p.mediaTime !== node.decoded ||
          ['epoch', 'changes', 'sourceChanges', 'maxGapMs', 'currentGapMs', 'lifetimeMaxGapMs', 'mediaTime']
            .some(key => p[key] !== deck.progress?.[key])) issue(index, 'active node lacks matching native progress');
    }
    for (const retired of summary.retired) {
      if (retired?.nativeError) nativeErrors++;
      if (!retired || retired.schema !== 1 || retired.supported !== true || retired.live !== false ||
          !Number.isFinite(retired.maxGapMs) || retired.maxGapMs < 0 ||
          !Number.isFinite(retired.lifetimeMaxGapMs) || retired.lifetimeMaxGapMs < retired.maxGapMs ||
          summary.maxGapMs < retired.lifetimeMaxGapMs) issue(index, 'invalid retired-source progress');
    }
  }
  return {native, issueCount, issues, invalidRows, maxSampleGapMs, maxGapMs, nativeErrors, suspensions};
}

function analyse(result) {
  const trackers = new Map(), restTrackers = new Map(), births = new Set(), changedSlots = new Set(), holds = [];
  const coverage = progressCoverage(result); let previousWall;
  const expectedSlots = (result.samples[0]?.nodes || []).map(node => node.id).sort().join(',');
  let jointMs = 0, decodedMs = 0, wraps = 0, populated = 0, playing = 0, standbys = 0;
  let unexpectedPaused = 0, invalidMedia = 0, nativeErrors = 0, globalSuspensions = 0;
  let restingSamples = 0, restingDecodedMs = 0, restingJointMs = 0, restingPaused = 0, maxResting = 0;
  const runtimeFailures = new Set();
  for (const [index, row] of result.samples.entries()) {
    const native = coverage.native && !coverage.invalidRows.has(index);
    const unobserved = previousWall !== undefined && row.wall - previousWall >= MAX_HOLD_MS;
    previousWall = row.wall;
    populated = Math.max(populated, row.populated); playing = Math.max(playing, row.playing);
    standbys = Math.max(standbys, row.standbys, row.maxStandbys);
    if (!row.running || row.hidden || row.audioState !== 'running') globalSuspensions++;
    if (row.lastFailure) runtimeFailures.add(row.lastFailure);
    if (row.foregroundLimit !== 4 || row.nodes.length !== 4 ||
        row.nodes.map(node => node.id).sort().join(',') !== expectedSlots || new Set(row.nodes.map(node => node.id)).size !== 4) invalidMedia++;
    maxResting = Math.max(maxResting, row.nodes.filter(node => node.resting).length);
    const seen = new Set();
    for (const node of row.nodes) {
      seen.add(node.id);
      const identity = JSON.stringify([node.id, node.sha, node.deck, node.birth]);
      births.add(identity);
      if (node.resting && row.running) {
        restingSamples++;
        if (node.paused) restingPaused++;
        let rest = restTrackers.get(node.id);
        if (!rest || rest.identity !== identity || (unobserved && !native))
          rest = {identity, current: node.current, decoded: node.decoded, changes: node.progress?.changes, jointAt: row.wall, decodedAt: row.wall};
        const changed = native ? rest.changes !== node.progress.changes : rest.decoded !== node.decoded;
        if (rest.current !== node.current || changed) rest.jointAt = row.wall;
        if (changed) rest.decodedAt = row.wall;
        restingJointMs = Math.max(restingJointMs, row.wall - rest.jointAt);
        restingDecodedMs = Math.max(restingDecodedMs, row.wall - rest.decodedAt);
        Object.assign(rest, {current: node.current, decoded: node.decoded, changes: node.progress?.changes});
        restTrackers.set(node.id, rest);
      } else restTrackers.delete(node.id);
      if (node.nativeError) nativeErrors++;
      if (!Number.isFinite(node.current) || !Number.isFinite(node.decoded)) invalidMedia++;
      if (row.running && !node.resting && node.paused) unexpectedPaused++;
      const old = trackers.get(node.id);
      if (old && old.identity !== identity) changedSlots.add(node.id);
      const eligible = row.running && !row.hidden && !node.paused;
      if (!old || old.identity !== identity || !eligible || !old.eligible || (unobserved && !native)) {
        trackers.set(node.id, {identity, eligible, current: node.current, decoded: node.decoded,
          changes: node.progress?.changes, jointAt: row.wall, decodedAt: row.wall});
        continue;
      }
      if (node.current + .05 < old.current) wraps++;
      const changed = native ? node.progress.changes !== old.changes : node.decoded !== old.decoded;
      if (node.current !== old.current || changed) old.jointAt = row.wall;
      if (changed) old.decodedAt = row.wall;
      const joint = row.wall - old.jointAt, decoded = row.wall - old.decodedAt;
      jointMs = Math.max(jointMs, joint); decodedMs = Math.max(decodedMs, decoded);
      if ((joint >= MAX_HOLD_MS || decoded >= MAX_HOLD_MS) && !old.reported) {
        holds.push({id: node.id, item: node.item, identity, wall: row.wall,
          current: node.current, decoded: node.decoded, jointMs: joint, decodedMs: decoded,
          phase: node.phase, ready: node.ready, seeking: node.seeking});
        old.reported = true;
      }
      Object.assign(old, {current: node.current, decoded: node.decoded, changes: node.progress?.changes});
    }
    for (const id of trackers.keys()) if (!seen.has(id)) trackers.delete(id);
    for (const id of restTrackers.keys()) if (!seen.has(id)) restTrackers.delete(id);
  }
  decodedMs = Math.max(decodedMs, coverage.maxGapMs);
  nativeErrors += coverage.nativeErrors; globalSuspensions += coverage.suspensions;
  const regimes = [...new Set(result.coarse.map(row => row.studio.ecosystem.regime))];
  const initialCount = result.samples[0]?.nodes.length || 0;
  const resourceErrors = classifyResourceErrors(result);
  const checks = {
    completed: result.completed === true,
    noFailure: !result.failure,
    fullDuration: (result.elapsedMs || 0) >= DURATION_MS,
    enoughSamples: result.samples.length >= 600,
    observationCoverage: coverage.issueCount === 0,
    jointProgress: jointMs < MAX_HOLD_MS,
    decodedProgress: decodedMs < MAX_HOLD_MS,
    restingProgress: restingJointMs < MAX_HOLD_MS && restingDecodedMs < MAX_HOLD_MS && restingPaused === 0,
    decodeBudget: populated <= 5 && playing <= 5 && standbys <= 1,
    validMedia: invalidMedia === 0 && nativeErrors === 0,
    noUnexpectedPause: unexpectedPaused === 0 && globalSuspensions === 0,
    succession: initialCount === 4 && births.size >= initialCount * 2 && changedSlots.size === initialCount,
    nativeWraps: wraps > 0,
    noErrors: result.errors.length === 0 && result.httpErrors.length === 0 && resourceErrors.unexpected.length === 0 &&
      runtimeFailures.size === 0 && !(result.events || []).some(event => ['media-failure', 'observer-failure'].includes(event.type)),
  };
  const pass = Object.values(checks).every(Boolean);
  const verdict = pass ? 'PASS' : Object.entries(checks).some(([key, value]) => key !== 'observationCoverage' && !value) ? 'FAIL' : 'INCONCLUSIVE';
  return {pass, verdict, checks, samples: result.samples.length,
    progressCoverage: {schema: result.progressSchema ?? null, issues: coverage.issues, issueCount: coverage.issueCount,
      maxSampleGapMs: coverage.maxSampleGapMs, nativeMaximumGapMs: coverage.maxGapMs},
    longestJointHoldMs: jointMs, longestDecodedHoldMs: decodedMs, holds,
    births: births.size, changedSlots: [...changedSlots], regimes, wraps,
    maxPopulatedDecks: populated, maxPlayingDecks: playing, maxPreparationLeases: standbys,
    restingSamples, maxResting, restingPaused, longestRestingJointHoldMs: restingJointMs,
    longestRestingDecodedHoldMs: restingDecodedMs, runtimeFailures: [...runtimeFailures],
    unexpectedPaused, globalSuspensions, invalidMedia, nativeErrors, resourceErrors};
}

function staticServer(site) {
  const mime = {'.html': 'text/html', '.js': 'application/javascript', '.json': 'application/json', '.mp4': 'video/mp4'};
  return http.createServer((request, response) => {
    let file;
    try {
      const name = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
      file = path.resolve(site, '.' + (name === '/' ? '/index.html' : name));
    } catch (_) { response.writeHead(400).end(); return; }
    if (!file.startsWith(site + path.sep)) { response.writeHead(403).end(); return; }
    fs.readFile(file, (error, data) => {
      if (error) { response.writeHead(404).end(); return; }
      response.writeHead(200, {'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Content-Length': data.length});
      response.end(data);
    });
  });
}

async function ready(page) {
  await page.waitForFunction(() => {
    const runtime = globalThis.compositionRuntime, studio = globalThis.SimvltaneaStudio?.snapshot();
    return runtime?.ready && !runtime.draining && studio?.source === 'library' && !studio.busy &&
      [...runtime.nodes.values()].every((node, index) => node.item?.name === studio.selection[index] &&
        node.item.asset?.id === (studio.loopMode === 'boomerang' ? node.item.clip?.variants?.boomerang?.id : node.item.clip?.id));
  }, null, {timeout: 60000});
  assert(await page.evaluate(() => typeof HTMLVideoElement.prototype.requestVideoFrameCallback === 'function'),
    'Native decoded-frame observation is unavailable');
}

async function click(page, selector) {
  await page.mouse.move(3, 3); await page.mouse.move(9, 9);
  await page.locator(selector).click({timeout: 15000});
}

function observeErrors(page, result) {
  // These are runner receipt times, not precise browser emission times. Keep
  // both clocks so they can be aligned without evaluating the page per error.
  const stamp = () => {
    const epochMs = Date.now();
    return {epochMs, runnerTimeMs: performance.now(), phase: result.phase,
      wall: result.documentTimeOrigin == null ? null : epochMs - result.documentTimeOrigin};
  };
  page.on('pageerror', error => result.errors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') {
      const location = message.location();
      result.consoleErrors.push({...stamp(), message: message.text(), location, url: location.url});
    }
  });
  page.on('response', response => {
    if (response.status() >= 400) result.httpErrors.push({...stamp(), url: response.url(), status: response.status()});
  });
  page.on('requestfailed', request => result.requestFailures.push({...stamp(), url: request.url(),
    method: request.method(), resourceType: request.resourceType(), failure: request.failure()}));
}

async function documentClock(page, result) {
  result.documentTimeOrigin = await page.evaluate(() => performance.timeOrigin);
  result.errorTiming = 'Runner receipt time; wall = epochMs - documentTimeOrigin, not exact browser emission time';
  for (const error of [...result.consoleErrors, ...result.httpErrors, ...result.requestFailures]) {
    if (error.wall === null) error.wall = error.epochMs - result.documentTimeOrigin;
  }
}

function sampleControls(page, result) {
  let running = true;
  const task = (async () => {
    let nextTrace = 0;
    while (running) {
      try {
        const includeTrace = performance.now() >= nextTrace;
        result.samples.push(await page.evaluate(sample, includeTrace));
        if (includeTrace) nextTrace = performance.now() + 1000;
      } catch (error) { result.errors.push('Control metadata sampling failed: ' + error); break; }
      await pause(SAMPLE_MS);
    }
  })();
  return async () => { running = false; await task; };
}

// Append one bounded record asynchronously. Re-serializing the entire growing
// run on the measurement thread creates observation gaps of its own. This
// journal preserves partial evidence if the job terminates before final JSON.
function proofJournal(out, name, createStream = fs.createWriteStream) {
  const stream = createStream(path.join(out, name + '.ndjson'), {highWaterMark: 1024 * 1024});
  let failure;
  stream.on('error', error => { failure = error; });
  return {
    async append(type, value) {
      if (failure) throw failure;
      const record = JSON.stringify({type, value}) + '\n';
      if (Buffer.byteLength(record) > 2 * 1024 * 1024) throw new Error('Proof journal record exceeds 2 MiB');
      if (!stream.write(record)) await once(stream, 'drain');
      if (failure) throw failure;
    },
    async close() {
      if (failure) throw failure;
      const finished = once(stream, 'finish'); stream.end(); await finished;
      if (failure) throw failure;
    }
  };
}

async function sustained(webkit, device, base, out, name, query) {
  const result = {name, progressSchema: 1, requestedUrl: base + query, samples: [], coarse: [], errors: [], consoleErrors: [], httpErrors: [], requestFailures: []};
  let browser; const journal = proofJournal(out, name), errorOffsets = {};
  const journalErrors = async () => {
    for (const kind of ['errors', 'consoleErrors', 'httpErrors', 'requestFailures']) {
      for (let index = errorOffsets[kind] || 0; index < result[kind].length; index++)
        await journal.append(kind, {index, error: result[kind][index]});
      errorOffsets[kind] = result[kind].length;
    }
  };
  try {
    await journal.append('run', {name, progressSchema: result.progressSchema, requestedUrl: result.requestedUrl});
    browser = await webkit.launch({headless: true}); result.browserVersion = browser.version();
    const context = await browser.newContext(device), page = await context.newPage();
    page.setDefaultTimeout(15000); observeErrors(page, result);
    const initialAt = performance.now();
    result.phase = 'navigation';
    await page.goto(result.requestedUrl, {waitUntil: 'domcontentloaded'}); await documentClock(page, result); await ready(page);
    result.initialSeconds = (performance.now() - initialAt) / 1000;
    result.phase = 'sound-unlock'; await click(page, '#speaker');
    await page.waitForFunction(() => compositionRuntime.audio.context?.state === 'running' && SimvltaneaStudio.snapshot().sound === 'on');
    result.actualUrl = page.url(); result.initialStudio = await page.evaluate(() => SimvltaneaStudio.snapshot());
    result.phase = 'sustained';
    const began = performance.now(); let nextCoarse = 0, nextReport = 20000;
    while (performance.now() - began < DURATION_MS) {
      const includeTrace = performance.now() - began >= nextCoarse;
      const row = await page.evaluate(sample, includeTrace); result.samples.push(row);
      await journal.append('sample', row); await journalErrors();
      const elapsed = performance.now() - began;
      if (elapsed >= nextCoarse) {
        const coarse = {wall: row.wall, studio: await page.evaluate(() => SimvltaneaStudio.snapshot())};
        result.coarse.push(coarse); await journal.append('coarse', coarse);
        nextCoarse = elapsed + 1000;
      }
      if (elapsed >= nextReport) {
        console.log(`${name}: ${(elapsed / 1000).toFixed(1)}s, simulation ${row.simTime.toFixed(1)}s`);
        nextReport += 20000;
      }
      await pause(SAMPLE_MS);
    }
    result.elapsedMs = performance.now() - began;
    const finalSample = await page.evaluate(sample, true); result.samples.push(finalSample);
    await journal.append('sample', finalSample);
    result.events = await page.evaluate(() => compositionRuntime.events);
    await journal.append('events', result.events);
    result.completed = true;
  } catch (error) { result.failure = String(error.stack || error); }
  finally {
    result.phase = 'closing';
    try { if (browser) await browser.close(); } catch (error) { result.failure = String(error.stack || error); }
    try { await journalErrors(); } catch (error) { result.failure = String(error.stack || error); }
    try { await journal.close(); } catch (error) { result.failure = String(error.stack || error); }
  }
  result.summary = analyse(result); save(out, name + '.json', result);
  console.log(JSON.stringify({name, ...result.summary})); return result.summary;
}

async function audioProof(webkit, out) {
  const result = {kind: 'native OfflineAudioContext rendered sample peak; not true peak'};
  let browser;
  try {
    browser = await webkit.launch({headless: true}); const page = await browser.newPage();
    await page.addScriptTag({path: path.join(__dirname, 'browser.audio.js')});
    Object.assign(result, await page.evaluate(async () => {
      if (typeof OfflineAudioContext !== 'function') throw new Error('Native OfflineAudioContext unavailable');
      const context = new OfflineAudioContext(2, 24000, 48000);
      const bus = SimvltaneaLiveAudio.createMasterBus(context, {volume: 1, enabled: true});
      for (let index = 0; index < 4; index++) {
        const oscillator = context.createOscillator(), gain = context.createGain();
        oscillator.frequency.value = 440; gain.gain.value = .425;
        oscillator.connect(gain); gain.connect(bus.input); oscillator.start(0);
      }
      const rendered = await context.startRendering(); let peak = 0;
      for (let channel = 0; channel < rendered.numberOfChannels; channel++)
        for (const value of rendered.getChannelData(channel)) peak = Math.max(peak, Math.abs(value));
      return {peak, dbfs: 20 * Math.log10(peak), voices: 4, perVoiceGain: .425, rate: 48000, channels: 2};
    }));
    assert(result.peak > .1 && result.peak <= .891251, 'Native sample peak or nonzero floor failed');
    result.pass = true;
  } catch (error) { result.pass = false; result.failure = String(error.stack || error); }
  finally { if (browser) await browser.close(); }
  save(out, 'audio.json', result); return result;
}

// Intentional interactions and the post-master meter are isolated from both baselines.
async function controls(webkit, device, base, out) {
  const result = {progressSchema: 1, errors: [], consoleErrors: [], httpErrors: [], requestFailures: [], samples: [], checks: {}};
  let browser, page, stopSampling = async () => {};
  try {
    browser = await webkit.launch({headless: true});
    const context = await browser.newContext(device); page = await context.newPage();
    page.setDefaultTimeout(15000); observeErrors(page, result);
    result.phase = 'navigation';
    await page.goto(base + '?seed=528316659&mix=s0.1.2.3&evolve=0&proof=1');
    await documentClock(page, result); await ready(page); result.phase = 'controls';
    stopSampling = sampleControls(page, result);
    await click(page, '#speaker');
    await page.waitForFunction(() => SimvltaneaStudio.snapshot().sound === 'on');
    await page.evaluate(() => { globalThis.smokeMedia = [...compositionRuntime.nodes.values()].map(node => node.media); });
    const before = await page.evaluate(() => SimvltaneaStudio.snapshot().selection);
    await page.locator('#stage .loop[data-loop-id="loop-1"]').click(); await ready(page);
    const after = await page.evaluate(() => SimvltaneaStudio.snapshot().selection);
    result.checks.tap = before[0] !== after[0] && before.slice(1).every((value, i) => value === after[i + 1]) &&
      await page.evaluate(() => [...compositionRuntime.nodes.values()].slice(1).every((node, i) => node.media === smokeMedia[i + 1]));
    await click(page, '#shuffle'); await ready(page);
    result.checks.shuffle = (await page.evaluate(() => SimvltaneaStudio.snapshot().seed)) !== 528316659;
    for (let attempt = 0; attempt < 3 && await page.evaluate(() => compositionRuntime.nodes.size) < 4; attempt++) {
      await click(page, '#more'); await ready(page);
    }
    for (const mode of ['forward', 'boomerang']) {
      if (await page.evaluate(() => SimvltaneaStudio.snapshot().loopMode) !== mode) await click(page, '#loop-mode');
      await ready(page);
      result.checks[mode] = await page.evaluate(expected => SimvltaneaStudio.snapshot().loopMode === expected &&
        [...compositionRuntime.nodes.values()].every(node => node.item.asset.id ===
          (expected === 'boomerang' ? node.item.clip.variants.boomerang.id : node.item.clip.id)), mode);
    }
    await page.evaluate(() => { globalThis.smokeMedia = [...compositionRuntime.nodes.values()].map(node => node.media); });
    for (const [orientation, width, height] of [['landscape', 844, 390], ['portrait', 390, 844]]) {
      await page.setViewportSize({width, height});
      await page.waitForFunction(expected => compositionRuntime.orientation === expected, orientation);
      result.checks[orientation] = await page.evaluate(() => [...compositionRuntime.nodes.values()].every((node, i) => node.media === smokeMedia[i]));
    }
    for (const enabled of [false, true]) {
      if (await page.evaluate(() => SimvltaneaStudio.snapshot().filters) !== enabled) await click(page, '#effects');
      await page.waitForFunction(value => SimvltaneaStudio.snapshot().filters === value &&
        new URL(location.href).searchParams.get('fx') === (value ? '1' : '0') &&
        [...compositionRuntime.nodes.values()].every((node, i) => node.media === smokeMedia[i] &&
          (value ? node.media.style.filter !== '' : node.media.style.filter === '')), enabled);
      result.checks[enabled ? 'filtersOn' : 'filtersOff'] = true;
    }
    await click(page, '#play');
    await page.waitForFunction(() => !compositionRuntime.running);
    const pausedAt = await page.evaluate(() => compositionRuntime.clock.simTime); await pause(250);
    result.checks.pause = await page.evaluate(time => compositionRuntime.clock.simTime === time &&
      [...compositionRuntime.nodes.values()].every(node => node.media.paused), pausedAt);
    await click(page, '#play');
    await page.waitForFunction(() => compositionRuntime.running && [...compositionRuntime.nodes.values()].every(node => !node.media.paused));
    result.checks.resume = true;
    result.checks.mobileLimit = await page.locator('#more').isDisabled() &&
      await page.evaluate(() => compositionRuntime.maxForeground === 4 && compositionRuntime.nodes.size === 4 && compositionRuntime.maxConcurrentStandbys <= 1);
    if (await page.evaluate(() => SimvltaneaStudio.snapshot().sound) !== 'on') await click(page, '#speaker');
    await page.waitForFunction(() => SimvltaneaStudio.snapshot().sound === 'on');
    await page.evaluate(() => {
      const meter = compositionRuntime.audio.context.createAnalyser(); meter.fftSize = 2048;
      compositionRuntime.master.output.connect(meter);
      globalThis.smokeLevel = () => {
        const data = new Float32Array(meter.fftSize); meter.getFloatTimeDomainData(data);
        return data.reduce((peak, value) => Math.max(peak, Math.abs(value)), 0);
      };
    });
    await page.waitForFunction(() => smokeLevel() > .00001);
    result.audiblePeak = await page.evaluate(() => smokeLevel());
    await click(page, '#speaker');
    await page.waitForFunction(() => SimvltaneaStudio.snapshot().sound === 'off' && smokeLevel() < 1e-7);
    result.mutedPeak = await page.evaluate(() => smokeLevel());
    await click(page, '#speaker');
    await page.waitForFunction(() => SimvltaneaStudio.snapshot().sound === 'on' && smokeLevel() > .00001);
    result.unmutedPeak = await page.evaluate(() => smokeLevel()); result.checks.sound = true;
    result.final = await page.evaluate(sample, true);
    result.samples.push(result.final);
  } catch (error) { result.pass = false; result.failure = String(error.stack || error); }
  finally {
    await stopSampling();
    if (page && !page.isClosed()) {
      try { result.events = await page.evaluate(() => compositionRuntime.events); }
      catch (error) { result.errors.push('Control event collection failed: ' + error); }
    }
    result.phase = 'closing'; if (browser) await browser.close();
  }
  result.resourceErrors = classifyResourceErrors(result);
  result.checks.noErrors = !result.errors.length && !result.httpErrors.length && !result.resourceErrors.unexpected.length &&
    !result.final?.lastFailure && result.final?.nodes.every(node => !node.nativeError) &&
    result.samples.every(row => !row.lastFailure && row.decks.every(deck => !deck.nativeError)) &&
    !(result.events || []).some(event => ['media-failure', 'observer-failure'].includes(event.type));
  result.pass = !result.failure && Object.values(result.checks).every(Boolean);
  save(out, 'controls.json', result); return result;
}

async function main() {
  const site = path.resolve(process.argv[2] || 'var/site/macos-webkit');
  const out = path.resolve(process.argv[3] || 'var/proofs/macos-webkit');
  fs.mkdirSync(out, {recursive: true});
  const receipt = {startedAtUtc: new Date().toISOString(), platform: process.platform, arch: process.arch,
    scope: 'macOS WebKit with iPhone viewport; Apple desktop media backend, not a physical iPhone or true-peak proof',
    durationPerBaselineMs: DURATION_MS, sampleIntervalMs: SAMPLE_MS, maximumHoldMs: MAX_HOLD_MS,
    observation: 'Sustained phases only read native/app metadata. Controls and audio probes run afterward in separate browsers.',
    budgetScope: 'Sampled session decks and application preparation leases, not measured hardware decoder pipelines'};
  let server;
  try {
    assert(process.platform === 'darwin', 'This verification requires macOS; no alternative backend is allowed');
    receipt.head = execFileSync('git', ['rev-parse', 'HEAD'], {encoding: 'utf8'}).trim();
    receipt.gitStatus = execFileSync('git', ['status', '--short'], {encoding: 'utf8'});
    assert(!receipt.gitStatus, 'Checked-out source is dirty');
    receipt.os = execFileSync('sw_vers', {encoding: 'utf8'}).trim();
    receipt.stage = site;
    receipt.sha256 = Object.fromEntries(['index.html', 'runtime.js', 'studio.js', 'compiler.js', 'layouts.json',
      'lab.html', 'lab_model.js', 'lab_engine.js', 'lab_ui.js', 'lab_audio.js', 'library/manifest.json']
      .map(name => [name, sha256(path.join(site, name))]));
    receipt.audioSourceSha256 = sha256(path.join(__dirname, 'browser.audio.js'));
    receipt.libraryBuild = 'python3 -m tools.publishing.build_studio_site, checked-out pinned defaults';
    const {webkit, devices} = require('playwright');
    receipt.playwright = require('playwright/package.json').version;
    assert(receipt.playwright === '1.65.0', 'Expected isolated playwright@1.65.0');
    const core = path.dirname(require.resolve('playwright-core/package.json'));
    receipt.webkit = JSON.parse(fs.readFileSync(path.join(core, 'browsers.json'), 'utf8')).browsers.find(browser => browser.name === 'webkit');
    const {defaultBrowserType, ...device} = devices['iPhone 13']; receipt.device = device;
    save(out, 'receipt.json', receipt);
    server = staticServer(site); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}/`;
    receipt.seeded = await sustained(webkit, device, base, out, 'seeded', '?seed=528316659&proof=1');
    receipt.fresh = await sustained(webkit, device, base, out, 'fresh', '?proof=1');
    const seenRegimes = [...new Set([...receipt.seeded.regimes, ...receipt.fresh.regimes])];
    receipt.regimeCoverage = {seen: seenRegimes, pass: REGIMES.every(regime => seenRegimes.includes(regime))};
    receipt.controls = await controls(webkit, device, base, out);
    receipt.audio = await audioProof(webkit, out);
    receipt.pass = receipt.seeded.pass && receipt.fresh.pass && receipt.regimeCoverage.pass && receipt.controls.pass && receipt.audio.pass;
  } catch (error) { receipt.pass = false; receipt.failure = String(error.stack || error); }
  finally {
    if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
    receipt.finishedAtUtc = new Date().toISOString(); save(out, 'receipt.json', receipt);
    console.log(JSON.stringify({pass: receipt.pass, head: receipt.head, receipt: path.join(out, 'receipt.json')}));
    if (!receipt.pass) process.exitCode = 1;
  }
}

if (require.main === module) main();
module.exports = {analyse, classifyResourceErrors, proofJournal};
