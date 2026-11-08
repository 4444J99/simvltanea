/* Opt-in native experiment setup. Never loaded by Studio or deployed. */
'use strict';
const {observeSources} = require('./verify_webkit_held_sources.js');
const {ORIGIN, RESCUE_POLICY, rescueAudit} = require('./verify_webkit_seek_cohort.js');
const assert = (condition, message) => { if (!condition) throw new Error(message); };

// Runs before Studio executes. The setter receives its newly constructed
// Session before the assignment expression returns and before initial media.
// No runtime methods, native prototypes, counters or media properties change.
function installStrategy({pauseBeforeSeek}) {
  if (typeof pauseBeforeSeek !== 'boolean' || globalThis.compositionRuntime)
    throw new Error('Install the diagnostic strategy before Session assignment');
  Object.defineProperty(globalThis, 'compositionRuntime', {configurable: true,
    set(value) {
      if (!value?.options || value.nodes?.size) throw new Error('Strategy assignment occurred after media admission');
      if (value.options.nativeLoopStandbyRescue === false) throw new Error('Production standby rescue must remain enabled');
      value.options.nativeLoopSeekPauseBeforeSeek = pauseBeforeSeek;
      globalThis.__seekCohort = {assignedAt: performance.now(), pauseBeforeSeek, beforeMedia: true};
      Object.defineProperty(globalThis, 'compositionRuntime', {value, writable: true, configurable: true, enumerable: true});
    }});
}

function strategySnapshot() {
  const state = globalThis.__seekCohort;
  return {pauseBeforeSeek: globalThis.compositionRuntime?.options.nativeLoopSeekPauseBeforeSeek,
    standbyRescue: globalThis.compositionRuntime?.options.nativeLoopStandbyRescue !== false,
    rescuePolicy: globalThis.compositionRuntime?.nativeLoopRescuePolicy?.(),
    assignedAt: state?.assignedAt, beforeMedia: state?.beforeMedia};
}

async function initialize(page, result, options) {
  result.cohortOptions = {pauseBeforeSeek: options.pauseBeforeSeek, standbyRescue: true,
    recoveryChain: 1, rescuePolicy: {...RESCUE_POLICY}};
  await page.addInitScript(installStrategy, result.cohortOptions);
}

// Bytes are independently hash checked in Node and here. The adapter uses the
// original normalized manifest metadata; Session.reconcile performs native
// priming and decoded-frame admission with its ordinary one-standby lease.
async function admitPinned({targets, manifestSha256}) {
  const state = globalThis.__seekCohort, api = globalThis.SimvltaneaStudio;
  if (!state || !api) throw new Error('Controlled cohort initialization missing');
  const digest = async buffer => [...new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))]
    .map(value => value.toString(16).padStart(2, '0')).join('');
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('library/manifest.json', {signal: controller.signal});
    if (!response.ok) throw new Error('Controlled manifest fetch failed');
    const text = await response.text();
    if (await digest(new TextEncoder().encode(text)) !== manifestSha256) throw new Error('Controlled manifest hash mismatch');
    const clips = api.libraryClips(JSON.parse(text));
    if (!clips || clips.length !== 6) throw new Error('Controlled manifest schema mismatch');
    state.items = new Map(); state.admitted = [];
    for (const target of targets.filter(item => ['target', 'sibling-incoming'].includes(item.role))) {
      const clip = clips.find(item => item.id === target.id), asset = clip?.variants?.boomerang;
      if (!asset || asset.file !== target.file) throw new Error('Controlled source metadata mismatch');
      const media = await fetch('library/' + asset.file, {signal: controller.signal});
      if (!media.ok) throw new Error('Controlled source fetch failed');
      const buffer = await media.arrayBuffer();
      if (buffer.byteLength !== asset.bytes || await digest(buffer) !== target.sha256)
        throw new Error('Controlled source hash/size mismatch');
      const item = {name: clip.id, index: clips.indexOf(clip), clip, asset, file: new Blob([buffer], {type: 'video/mp4'}),
        type: 'video/mp4', suffix: 'mp4', size: asset.bytes, sha256: target.sha256,
        audioStream: api.audioStream(buffer), width: asset.width, height: asset.height,
        duration: asset.duration_seconds, quantized: api.quantizeDuration(asset.duration_seconds, api.FPS)};
      state.items.set(target.id, item);
      state.admitted.push({id: target.id, file: asset.file, bytes: buffer.byteLength, sha256: target.sha256});
    }
    return {manifestSha256, sources: state.admitted};
  } finally { clearTimeout(timer); }
}

function rememberSlots() {
  const runtime = globalThis.compositionRuntime;
  globalThis.__seekCohort.remembered = new Map([...runtime.nodes].map(([id, node]) => [id,
    {node, box: node.box, decks: node.decks.slice(), media: node.decks.map(deck => deck.media),
      active: node.active, binding: node.active?.binding, item: node.item, source: node.source,
      birth: node.birthTime, residentIdentity: node.residentIdentity}]));
}

function isolation(changedSlot) {
  const runtime = globalThis.compositionRuntime, remembered = globalThis.__seekCohort.remembered;
  return {slotsStable: remembered?.size === 4 && runtime.nodes.size === 4 && [...remembered].every(([id, old]) => {
    const node = runtime.nodes.get(id);
    return node === old.node && node.box === old.box && node.decks.length === 2 &&
      node.decks.every((deck, index) => deck === old.decks[index] && deck.media === old.media[index]);
  }), peersStable: [...remembered].filter(([id]) => id !== changedSlot).every(([id, old]) => {
    const node = runtime.nodes.get(id);
    return node?.active === old.active && node.item === old.item && node.active?.binding === old.binding;
  }), logicalPeersStable: [...remembered].filter(([id]) => id !== changedSlot).every(([id, old]) => {
    const node = runtime.nodes.get(id);
    return node?.item === old.item && node.source === old.source && node.birthTime === old.birth &&
      node.residentIdentity === old.residentIdentity && (node.active !== old.active || node.active?.binding === old.binding);
  })};
}

async function replacePinned({id, slot}) {
  const runtime = globalThis.compositionRuntime, item = globalThis.__seekCohort.items.get(id);
  if (!item) throw new Error('Controlled replacement was not hash admitted');
  const plan = structuredClone(runtime.plan);
  const items = plan.tracks.map(track => track.id === slot ? item : runtime.nodes.get(track.id)?.item);
  const index = plan.tracks.findIndex(track => track.id === slot);
  if (index < 0) throw new Error('Controlled replacement slot missing');
  Object.assign(plan.sources[index], {path: `media/${item.sha256}.${item.suffix}`, sha256: item.sha256,
    bytes: item.size, duration: item.quantized.duration, audio_stream: item.audioStream});
  return runtime.reconcile({plan, items, playing: true, atLoopBoundary: true});
}

function overlapSnapshot() {
  const runtime = globalThis.compositionRuntime, wall = performance.now();
  const node = runtime.nodes.get('loop-3'), incoming = node?.decks.find(deck => deck !== node.active && deck.item);
  if (!incoming) return null;
  const native = (owner, deck) => ({id: owner.id, deck: owner.decks.indexOf(deck), item: deck.item?.name,
    sha: deck.item?.sha256, birth: owner.birthTime, src: deck.media.src, currentSrc: deck.media.currentSrc,
    paused: deck.media.paused, ready: deck.media.readyState, decoded: deck.decoded?.mediaTime,
    callbacks: deck.callbacks, nativeError: deck.media.error ? {code: deck.media.error.code} : null,
    progress: deck.progress?.snapshot(wall, true)});
  const decks = [...runtime.slots.values()].flatMap(owner => owner.decks);
  const remembered = globalThis.__seekCohort.remembered;
  const slotsStable = remembered.size === 4 && runtime.nodes.size === 4 && [...remembered].every(([id, old]) => {
    const current = runtime.nodes.get(id);
    return current === old.node && current.box === old.box && current.decks.every((deck, i) =>
      deck === old.decks[i] && deck.media === old.media[i]);
  });
  const peersStable = [...remembered].filter(([id]) => id !== 'loop-3').every(([id, old]) => {
    const current = runtime.nodes.get(id);
    return current.active === old.active && current.item === old.item && current.active.binding === old.binding;
  });
  const logicalPeersStable = [...remembered].filter(([id]) => id !== 'loop-3').every(([id, old]) => {
    const current = runtime.nodes.get(id);
    return current.item === old.item && current.source === old.source && current.birthTime === old.birth &&
      current.residentIdentity === old.residentIdentity && (current.active !== old.active || current.active.binding === old.binding);
  });
  return {wall, running: runtime.running, hidden: document.hidden, audioState: runtime.audio.context?.state,
    foregroundLimit: runtime.maxForeground, populated: decks.filter(deck => deck.media.hasAttribute('src')).length,
    playing: decks.filter(deck => deck.media.hasAttribute('src') && !deck.media.paused).length,
    standbys: runtime.activeStandbys, maxStandbys: runtime.maxConcurrentStandbys,
    nodes: [...runtime.nodes.values()].map(owner => native(owner, owner.active)),
    phase: node.phase, incoming: native(node, incoming), slotsStable, peersStable, logicalPeersStable};
}

async function prepare(page, {sample, pause, journal}, targets, result = {}, options) {
  Object.assign(result, {scope: 'Pinned six-source native reconcile replay in Hold. Initial A/B/C/predecessor; '
    + 'replace predecessor with target, then C with incoming sibling. This controls source identity and transition order, '
    + 'not the original wall timing, deck ages or ecological history.', origin: ORIGIN, samples: [],
    incomingObservations: [], siblingOverlap: []});
  result.strategyStart = await page.evaluate(strategySnapshot);
  assert(result.strategyStart.beforeMedia && result.strategyStart.pauseBeforeSeek === options.pauseBeforeSeek &&
    result.strategyStart.standbyRescue === true && Object.entries(RESCUE_POLICY)
      .every(([key, value]) => result.strategyStart.rescuePolicy?.[key] === value),
    'Controlled strategy was not installed before initial media');
  const capture = async () => {
    const row = await page.evaluate(sample, true); result.samples.push(row);
    await journal.append('diagnostic-prelude-sample', row); return row;
  };
  const waitForSources = async selected => {
    const deadline = performance.now() + 30000;
    while (performance.now() < deadline) {
      await capture();
      if (observeSources(result.samples, selected).every(source => source.pass)) return;
      await pause(137);
    }
    throw new Error('Controlled cohort did not decode and wrap every required source');
  };
  // Keep all fetch/admission time observable, without adding another decoder.
  let loading = true, loaded, loadError;
  const admission = page.evaluate(admitPinned, {targets, manifestSha256: options.manifestSha256})
    .then(value => {loaded = value;}, error => {loadError = error;}).finally(() => {loading = false;});
  while (loading) { await capture(); await pause(137); }
  await admission; if (loadError) throw loadError; result.admission = loaded;
  const byRole = role => targets.find(target => target.role === role);
  await waitForSources(['peer-1', 'peer-2', 'sibling-resident', 'predecessor'].map(byRole));
  result.before = await capture();
  const transition = async (target, overlap) => {
    await page.evaluate(rememberSlots);
    let done = false, succeeded = false, failure;
    const began = performance.now();
    const pending = page.evaluate(replacePinned, target).then(value => {succeeded = value;}, error => {failure = error;})
      .finally(() => {done = true;});
    while (!done && performance.now() - began < 30000) {
      await capture();
      if (overlap) {
        const row = await page.evaluate(overlapSnapshot);
        if (row) {
          result.incomingObservations.push(row); await journal.append('diagnostic-sibling-incoming', row);
          const incoming = row.incoming, p = incoming.progress;
          if (['READY', 'CROSSFADING'].includes(row.phase) && p?.sourceChanges >= 2 &&
              Number.isFinite(incoming.decoded) && incoming.ready >= 1 && incoming.ready <= 4 &&
              !incoming.paused && incoming.src === incoming.currentSrc &&
              incoming.item === target.id && incoming.sha === target.sha256 &&
              row.nodes.some(node => node.id === 'loop-3' && node.item === byRole('sibling-resident').id) &&
              row.nodes.some(node => node.id === 'loop-4' && node.item === byRole('target').id)) {
            result.siblingOverlap.push(row);
          }
        }
      }
      await pause(137);
    }
    assert(done, 'Controlled reconciliation exceeded setup deadline');
    await pending; if (failure) throw failure;
    assert(succeeded, 'Controlled native reconciliation did not admit its replacement');
    return page.evaluate(isolation, target.slot);
  };
  result.targetIsolation = await transition(byRole('target'), false);
  result.afterTarget = await capture();
  await waitForSources([byRole('target')]);
  // Observe a new outgoing C phrase so its ordinary seam wait exposes the
  // incoming E standby concurrently with the target. Never seek it to arrange timing.
  const deadline = performance.now() + 12000;
  let nearStart = false;
  while (performance.now() < deadline) {
    const row = await capture(), outgoing = row.nodes.find(node => node.id === 'loop-3');
    if (outgoing && !outgoing.seeking && outgoing.current > .05 && outgoing.current < .75) { nearStart = true; break; }
    await pause(137);
  }
  assert(nearStart, 'Controlled sibling did not naturally reach its next phrase');
  result.siblingIsolation = await transition(byRole('sibling-incoming'), true);
  result.afterSibling = await capture();
  await waitForSources([byRole('sibling-incoming')]);
  return result;
}

async function finalize(page, result) { result.strategyFinal = await page.evaluate(strategySnapshot); }

function interventions(result, targets) {
  const rows = [...(result.prelude?.samples || []), ...(result.samples || [])];
  const assignedAt = result.prelude?.strategyStart?.assignedAt;
  const strategy = result.cohortOptions?.pauseBeforeSeek === false ? 'seek-play' : 'pause-seek-play';
  const ownership = new Map(), events = new Map();
  const key = event => JSON.stringify([event.id, event.url, event.sourceEpoch]);
  for (const row of [...rows, ...(result.prelude?.siblingOverlap || [])]) {
    for (const node of [...(row.nodes || []), ...(row.incoming ? [row.incoming] : [])]) {
      const target = targets.find(item => item.id === node.item && item.slot === node.id && item.sha256 === node.sha);
      if (target && typeof node.progress?.url === 'string' && Number.isSafeInteger(node.progress.epoch))
        ownership.set(key({id: node.id, url: node.progress.url, sourceEpoch: node.progress.epoch}),
          {id: target.id, sha256: target.sha256, slot: target.slot, url: node.progress.url, epoch: node.progress.epoch});
    }
  }
  const counters = {'native-loop-seek-recovery': 'attempted', 'native-loop-seek-recovered': 'recovered',
    'native-loop-seek-play-rejected': 'rejected', 'native-loop-seek-interrupted': 'interrupted'};
  // The event ring and proof receipt use two performance.now() calls for one
  // intervention. Count the authoritative proof receipts only; the complete
  // unmodified event ring remains separately preserved in result.events.
  for (const event of rows.flatMap(row => row.progressSummary?.nativeLoopSeek?.receipts || [])) {
    if (counters[event.type]) events.set(JSON.stringify([event.type, event.id, event.url, event.sourceEpoch, event.wall]), event);
  }
  const all = [...events.values()].sort((a, b) => a.wall - b.wall);
  const attributed = [], excluded = [];
  for (const event of all) {
    const source = ownership.get(key(event));
    if (source && Number.isFinite(event.wall) && event.wall >= assignedAt && event.strategy === strategy)
      attributed.push({...event, source});
    else excluded.push({...event, reason: !source ? 'unknown-source-epoch' : event.wall < assignedAt ?
      'before-strategy-assignment' : 'strategy-mismatch'});
  }
  const attempts = attributed.filter(event => event.type === 'native-loop-seek-recovery');
  const recoveries = attributed.filter(event => event.type === 'native-loop-seek-recovered' &&
    event.decodedChanges >= 2 && event.seeking === false && attempts.some(attempt => key(attempt) === key(event) &&
      attempt.time === event.attemptedAt && attempt.wall < event.wall));
  const aggregateEnd = rows.at(-1)?.progressSummary?.nativeLoopSeek;
  const complete = aggregateEnd && Object.entries(counters).every(([type, counter]) =>
    Number.isSafeInteger(aggregateEnd[counter]) && aggregateEnd[counter] >= 0 &&
    aggregateEnd[counter] === all.filter(event => event.type === type).length);
  const pass = Boolean(Number.isFinite(assignedAt) && complete && !excluded.length &&
    recoveries.length === attributed.filter(event => event.type === 'native-loop-seek-recovered').length);
  const rescue = rescueAudit(result, targets);
  return {pass: pass && rescue.pass, strategy, assignedAt, rescue,
    status: attempts.length ? (recoveries.length ? 'RECOVERY_OBSERVED' : 'ATTEMPTED') : 'NOT_EXERCISED',
    receiptSource: 'proofProgressSummary.nativeLoopSeek.receipts',
    scope: 'Only exact cohort source epochs after strategy assignment. Native seek recovery and verified cached-source '
      + 'rescue are reported separately; both arms retain the same rescue chain. Decoded recovery is observation, not a causal comparison.',
    aggregateEnd, complete: Boolean(complete), attempts, recoveries, excluded, receipts: attributed};
}

module.exports = {installStrategy, strategySnapshot, initialize, admitPinned, rememberSlots, isolation,
  replacePinned, overlapSnapshot, prepare, finalize, interventions};
