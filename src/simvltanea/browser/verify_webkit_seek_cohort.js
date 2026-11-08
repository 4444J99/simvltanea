/* Controlled native seek comparison only; never loaded by Studio or deployed. */
'use strict';
const crypto = require('node:crypto');
const {libraryClips} = require('./browser.studio.js');
const {observeSources} = require('./verify_webkit_held_sources.js');
const TARGETS = Object.freeze([
  {id: '2f949d8676d1', role: 'peer-1', slot: 'loop-1',
    sha256: 'be02c454b4943a7a33e8bfee57676e2974993a9ee1eba0d2318e195f97f11ae5',
    forwardSha256: '2f949d8676d16e63c5ccfdefd8b14ac5a5d64ccf87b4bfd5c3d963d8790850e3'},
  {id: 'efe8ffd8c723', role: 'peer-2', slot: 'loop-2',
    sha256: 'c370593f8071e82e45ce0028f84145b6a2c3d9dcca6fda0fac2e92511da42524',
    forwardSha256: 'efe8ffd8c723d3d017277a4aa7f4e9276094923c303eb60568046ef8e7f78398'},
  {id: '3ffa0d345ed1', role: 'sibling-resident', slot: 'loop-3',
    sha256: 'bd3b97fa7cf2a862045351d10ea62f1ac57041a3667487193c820f72e707a7bf',
    forwardSha256: '3ffa0d345ed119ffeded791c3d56c0925eae9de78b21f81d747bbfdd7ac0d838'},
  {id: '8356ed30a9fe', role: 'target', slot: 'loop-4',
    sha256: 'ec1f432fed9b3edcd83645f1269f7ea017579eed023e25a57ff841f017be4f0e',
    forwardSha256: '8356ed30a9fef07ef798b2d441cfccc4bf1615f92eb86caa39ccb943b3f0c5fb'},
  {id: '443fbc2c885a', role: 'predecessor', slot: 'loop-4',
    sha256: '714ec3a120ab952fd1625d83a0d52ec135e662178a3c71014475c10a5e1adce0',
    forwardSha256: '443fbc2c885a4a1ea24190ff7e73c56fee41b7a45ded92ef541c1de82ff9949a'},
  {id: '99835e485b6e', role: 'sibling-incoming', slot: 'loop-3',
    sha256: 'b120224722b97fa2686fd00c70dae0d75350a777fee4e94d0644505ba14da0f6',
    forwardSha256: '99835e485b6ec37131ca24ae8d29532f555123fb70480da03873b5ccf2333700'},
]);
const ORIGIN = Object.freeze({run: '42444130199', artifact: '13602957458',
  artifactSha256: '3eae6b8870706e0f5719f829af7108512e639aa10a83c7bb3baa73d3543ae522',
  head: '373e3870a82421ff99a1a3add283ddbece785697', sample: 'fresh.json',
  lastDecodedWall: 95119, attemptWall: 95754, nextDecodedWall: 98340, recoveredWall: 99080,
  cohortObservationWall: 95733, maxCriticalSampleGapMs: 335,
  sourceManifestSha256: '030d6446b3a57ea003ec056fdb7ed3e553c10f184b477346822eec5b4f9ca401',
  libraryUrl: 'https://75cafe28.loop-compositor-studio.pages.dev/library/'});
const ROLES = ['peer-1', 'peer-2', 'sibling-resident', 'target', 'predecessor', 'sibling-incoming'];
const SLOTS = ['loop-1', 'loop-2', 'loop-3', 'loop-4', 'loop-4', 'loop-3'];
const RAW_CHECKS = ['completed', 'noFailure', 'fullDuration', 'enoughSamples', 'observationCoverage',
  'jointProgress', 'decodedProgress', 'restingProgress', 'decodeBudget', 'validMedia',
  'noUnexpectedPause', 'succession', 'nativeWraps', 'noErrors'];
const COVERAGE_CHECKS = ['initialSet', 'targetSet', 'targetIsolation', 'siblingSet', 'siblingIsolation',
  'siblingIncomingOverlap', 'preludeResources', 'preludeNativeProgress', 'allSourcesDecodedAndWrapped',
  'finalSourcesSustained', 'heldComposition', 'strategiesMatch'];
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function buildManifest(original, readAsset, targets = TARGETS) {
  assert(libraryClips(original), 'Original library manifest failed the Studio schema gate');
  assert(targets.length === 6 && new Set(targets.map(target => target.id)).size === 6 &&
    ROLES.every((role, index) => targets.filter(target => target.role === role && target.slot === SLOTS[index]).length === 1),
  'Controlled seek cohort requires six distinct sources with fixed roles and slots');
  const clips = targets.map(target => {
    const clip = original.clips.find(entry => entry.id === target.id);
    assert(clip?.variants?.boomerang, 'Controlled seek source missing: ' + target.id);
    for (const [asset, expected] of [[clip, target.forwardSha256], [clip.variants.boomerang, target.sha256]]) {
      const bytes = readAsset(asset.file);
      assert(bytes.length === asset.bytes && digest(bytes) === expected, 'Controlled seek asset hash/size mismatch: ' + asset.file);
    }
    return clip;
  });
  const manifest = {...original, clips}, normalized = libraryClips(manifest);
  assert(normalized?.length === 6, 'Controlled seek subset failed the Studio schema gate');
  const initial = ['peer-1', 'peer-2', 'sibling-resident', 'predecessor'];
  const mix = initial.map(role => normalized.findIndex(clip => clip.id === targets.find(target => target.role === role).id));
  return {manifest, targets: targets.map(target => {
    const clip = clips.find(entry => entry.id === target.id);
    return {...target, file: clip.variants.boomerang.file, publishedUrl: ORIGIN.libraryUrl + clip.variants.boomerang.file};
  }), query: `?seed=528316659&mix=s${mix.join('.')}&evolve=0&loop=boomerang&proof=1`};
}

function controlledVerdict(raw, sourceCoverage) {
  const checks = Object.fromEntries(Object.entries(raw?.checks || {}).filter(([key]) => key !== 'succession'));
  const validRaw = RAW_CHECKS.every(key => typeof raw?.checks?.[key] === 'boolean');
  if (!validRaw) checks.rawCheckSchema = false;
  checks.sourceCoverage = sourceCoverage?.pass === true &&
    COVERAGE_CHECKS.every(key => sourceCoverage.checks?.[key] === true) &&
    Object.values(sourceCoverage.checks).every(value => value === true);
  const pass = Object.values(checks).every(value => value === true);
  return {pass, verdict: pass ? 'PASS' : 'FAIL', checks, sourceCoverage,
    rawVerdict: raw?.verdict, notApplicable: {
      succession: 'Fixed controlled cohort; natural succession is required by the original phases.'}};
}

function cohortIdentity(node) {
  const progress = node?.progress;
  if (typeof node?.id !== 'string' || typeof node.item !== 'string' ||
      !/^[a-f0-9]{64}$/.test(node.sha || '') || ![0, 1].includes(node.deck) ||
      !Number.isFinite(node.birth) || node.birth < 0 ||
      typeof progress?.url !== 'string' || !progress.url.startsWith('blob:') ||
      !Number.isSafeInteger(progress.epoch) || progress.epoch < 1) return null;
  return JSON.stringify([node.id, node.item, node.sha, node.deck, node.birth, progress.url, progress.epoch]);
}

function cohortSet(row, selected) {
  return Boolean(Array.isArray(row?.nodes) && row.nodes.length === 4 &&
    new Set(row.nodes.map(node => node.id)).size === 4 && selected.every(target => {
      const node = row.nodes.find(candidate => candidate.id === target.slot);
      return node?.item === target.id && node.sha === target.sha256 && cohortIdentity(node) !== null;
    }));
}

function cohortPeersStable(before, after, slots) {
  return Boolean(Array.isArray(before?.nodes) && Array.isArray(after?.nodes) && slots.every(slot => {
    const a = cohortIdentity(before.nodes.find(node => node.id === slot));
    const b = cohortIdentity(after.nodes.find(node => node.id === slot));
    return a !== null && a === b;
  }));
}

function cohortResources(row) {
  const bounded = (value, max) => Number.isSafeInteger(value) && value >= 0 && value <= max;
  return row?.foregroundLimit === 4 && Array.isArray(row.nodes) && row.nodes.length === 4 &&
    new Set(row.nodes.map(node => node.id)).size === 4 &&
    bounded(row.populated, 5) && bounded(row.playing, row.populated) &&
    bounded(row.standbys, 1) && bounded(row.maxStandbys, 1) && row.standbys <= row.maxStandbys;
}

function cohortNativeProgress(row) {
  const summary = row?.progressSummary;
  return Number.isFinite(row?.wall) && row.wall >= 0 && row.running === true &&
    row.hidden === false && row.audioState === 'running' &&
    summary?.schema === 1 && summary.supported === true &&
    Number.isFinite(summary.maxGapMs) && summary.maxGapMs >= 0 && summary.maxGapMs < 2000 &&
    summary.suspensionCount === 0;
}

const cohortOverlapKey = row => {
  const incoming = row?.incoming, p = incoming?.progress;
  return JSON.stringify([row?.wall, incoming?.id, incoming?.deck, incoming?.item, incoming?.sha,
    incoming?.src, incoming?.currentSrc, incoming?.ready, incoming?.paused, incoming?.decoded, incoming?.callbacks,
    p?.url, p?.epoch, p?.sourceChanges, p?.changes, p?.mediaTime]);
};

// Preserve normal priming observations without treating metadata or a single
// decoded frame as overlap proof. Errors and resource excess cannot be filtered
// out of the positive-evidence subset.
function cohortIncomingObservations(rows, qualified, afterTarget, afterSibling, targetCohort, incomingTarget) {
  const report = {pass: false, observations: Array.isArray(rows) ? rows.length : 0};
  const promoted = afterSibling?.nodes?.find(node => node.id === incomingTarget.slot);
  if (!Array.isArray(rows) || !rows.length || !Array.isArray(qualified) || !cohortIdentity(promoted)) return report;
  let previousWall;
  for (const row of rows) {
    const incoming = row?.incoming, p = incoming?.progress;
    if (!Number.isFinite(row?.wall) || row.wall < afterTarget?.wall || row.wall > afterSibling.wall ||
        (previousWall !== undefined && row.wall <= previousWall) || !cohortResources(row) ||
        row.running !== true || row.hidden !== false || row.audioState !== 'running' ||
        row.slotsStable !== true || row.peersStable !== true || !cohortSet(row, targetCohort) ||
        !cohortPeersStable(afterTarget, row, ['loop-1', 'loop-2', 'loop-3', 'loop-4']) ||
        row.nodes.some(node => node.nativeError || node.progress?.schema !== 1 || node.progress.supported !== true ||
          node.progress.live !== true || ![node.progress.currentGapMs, node.progress.maxGapMs]
            .every(gap => Number.isFinite(gap) && gap >= 0 && gap < 2000)) ||
        incoming?.id !== incomingTarget.slot || incoming.item !== incomingTarget.id || incoming.sha !== incomingTarget.sha256 ||
        incoming.deck !== promoted.deck || incoming.src !== promoted.progress.url ||
        (incoming.currentSrc !== '' && incoming.currentSrc !== incoming.src) || incoming.nativeError ||
        !Number.isInteger(incoming.ready) || incoming.ready < 0 || incoming.ready > 4 || typeof incoming.paused !== 'boolean' ||
        !Number.isSafeInteger(incoming.callbacks) || incoming.callbacks < 0 ||
        p?.schema !== 1 || p.supported !== true || p.live !== true || p.url !== incoming.src || p.epoch !== promoted.progress.epoch ||
        !Number.isSafeInteger(p.sourceChanges) || p.sourceChanges < 0 ||
        !Number.isSafeInteger(p.changes) || p.changes < p.sourceChanges ||
        ![p.currentGapMs, p.maxGapMs].every(gap => Number.isFinite(gap) && gap >= 0 && gap < 2000) ||
        p.maxGapMs < p.currentGapMs || (p.sourceChanges > 0 &&
          (!Number.isFinite(incoming.decoded) || incoming.decoded < 0 || p.mediaTime !== incoming.decoded ||
           !Number.isFinite(p.lastChangeWall) || p.lastChangeWall > row.wall || p.lastChangeWall < 0))) return report;
    previousWall = row.wall;
  }
  const recorded = new Set(rows.map(cohortOverlapKey));
  report.pass = qualified.every(row => recorded.has(cohortOverlapKey(row)));
  return report;
}

// The incoming standby is not foreground yet. Bind its own decoded evidence
// to the eventual active source without borrowing the outgoing media clock.
// FrameProgress.running gates foreground-gap accounting; an unpaused standby
// can decode while both progress.foreground and progress.running are false.
function overlapEvidence(rows, afterTarget, afterSibling, targetCohort, incomingTarget) {
  const result = {pass: false, observations: 0, advances: 0, evidence: []};
  const promoted = afterSibling?.nodes?.find(node => node.id === incomingTarget.slot);
  if (!Array.isArray(rows) || rows.length < 3 || !cohortIdentity(promoted)) return result;
  const promotedIdentity = JSON.stringify([promoted.id, promoted.deck, promoted.progress.url, promoted.progress.epoch]);
  let previous;
  for (const row of rows) {
    const incoming = row.incoming, p = incoming?.progress;
    if (!Number.isFinite(row.wall) || row.wall < afterTarget?.wall || row.wall > afterSibling.wall ||
        !cohortResources(row) || row.populated !== 5 || row.playing !== 5 || row.standbys !== 1 ||
        row.running !== true || row.hidden !== false || row.audioState !== 'running' ||
        row.slotsStable !== true || row.peersStable !== true ||
        !cohortSet(row, targetCohort) || !cohortPeersStable(afterTarget, row, ['loop-1', 'loop-2', 'loop-3', 'loop-4']) ||
        incoming?.id !== incomingTarget.slot || incoming.item !== incomingTarget.id || incoming.sha !== incomingTarget.sha256 ||
        ![0, 1].includes(incoming.deck) || incoming.paused !== false ||
        !Number.isInteger(incoming.ready) || incoming.ready < 1 || incoming.ready > 4 || incoming.nativeError ||
        typeof incoming.src !== 'string' || !incoming.src.startsWith('blob:') || incoming.src !== incoming.currentSrc ||
        !Number.isFinite(incoming.decoded) || incoming.decoded < 0 ||
        !Number.isSafeInteger(incoming.callbacks) || incoming.callbacks < 1 ||
        p?.schema !== 1 || p.supported !== true || p.live !== true || p.url !== incoming.src ||
        typeof p.foreground !== 'boolean' || typeof p.running !== 'boolean' || (p.foreground && !p.running) ||
        !Number.isSafeInteger(p.epoch) || p.epoch < 1 || !Number.isSafeInteger(p.sourceChanges) || p.sourceChanges < 2 ||
        !Number.isSafeInteger(p.changes) || p.changes < p.sourceChanges || p.mediaTime !== incoming.decoded ||
        !Number.isFinite(p.lastChangeWall) || p.lastChangeWall < 0 || p.lastChangeWall > row.wall ||
        ![p.currentGapMs, p.maxGapMs].every(gap => Number.isFinite(gap) && gap >= 0 && gap < 2000) ||
        p.maxGapMs < p.currentGapMs) return result;
    const identity = JSON.stringify([incoming.id, incoming.deck, p.url, p.epoch]);
    if (identity !== promotedIdentity) return result;
    if (previous) {
      const gap = row.wall - previous.wall;
      if (gap <= 0 || gap >= 2000 || identity !== previous.identity ||
          p.sourceChanges < previous.sourceChanges || incoming.callbacks < previous.callbacks) return result;
      if (p.sourceChanges > previous.sourceChanges && incoming.callbacks > previous.callbacks && incoming.decoded !== previous.decoded) {
        result.advances++;
        result.evidence.push({fromWall: previous.wall, wall: row.wall, id: incoming.id, deck: incoming.deck,
          url: p.url, epoch: p.epoch, fromDecoded: previous.decoded, decoded: incoming.decoded,
          sourceChanges: p.sourceChanges, callbacks: incoming.callbacks});
      }
    }
    result.observations++;
    previous = {wall: row.wall, identity, sourceChanges: p.sourceChanges,
      callbacks: incoming.callbacks, decoded: incoming.decoded};
  }
  result.pass = result.observations >= 3 && result.advances >= 2;
  return result;
}

function coverage(result, targets = TARGETS) {
  const checks = Object.fromEntries(COVERAGE_CHECKS.map(key => [key, false]));
  if (!Array.isArray(targets) || targets.length !== 6 || new Set(targets.map(target => target.id)).size !== 6 ||
      !ROLES.every((role, index) => targets.filter(target => target.role === role && target.slot === SLOTS[index]).length === 1))
    return {pass: false, checks, sources: [], sustained: []};
  const prelude = result?.prelude || {}, samples = Array.isArray(prelude.samples) ? prelude.samples : [];
  const baseline = Array.isArray(result?.samples) ? result.samples : [];
  const selected = roles => roles.map(role => targets.find(target => target.role === role));
  const initial = selected(['peer-1', 'peer-2', 'sibling-resident', 'predecessor']);
  const targetCohort = selected(['peer-1', 'peer-2', 'sibling-resident', 'target']);
  const finalCohort = selected(['peer-1', 'peer-2', 'sibling-incoming', 'target']);
  const sources = observeSources(samples, targets), sustained = observeSources(baseline, finalCohort);
  const overlap = overlapEvidence(prelude.siblingOverlap, prelude.afterTarget, prelude.afterSibling,
    targetCohort, targets.find(target => target.role === 'sibling-incoming'));
  const incomingObservations = cohortIncomingObservations(prelude.incomingObservations, prelude.siblingOverlap,
    prelude.afterTarget, prelude.afterSibling, targetCohort, targets.find(target => target.role === 'sibling-incoming'));
  const strategy = result?.cohortOptions?.pauseBeforeSeek, assignedAt = prelude.strategyStart?.assignedAt;
  Object.assign(checks, {
    initialSet: cohortSet(prelude.before, initial),
    targetSet: cohortSet(prelude.afterTarget, targetCohort),
    targetIsolation: prelude.targetIsolation?.slotsStable === true && prelude.targetIsolation?.peersStable === true &&
      cohortPeersStable(prelude.before, prelude.afterTarget, ['loop-1', 'loop-2', 'loop-3']),
    siblingSet: cohortSet(prelude.afterSibling, finalCohort),
    siblingIsolation: prelude.siblingIsolation?.slotsStable === true && prelude.siblingIsolation?.peersStable === true &&
      cohortPeersStable(prelude.afterTarget, prelude.afterSibling, ['loop-1', 'loop-2', 'loop-4']),
    siblingIncomingOverlap: overlap.pass && incomingObservations.pass,
    preludeResources: samples.length > 0 && samples.every(cohortResources),
    preludeNativeProgress: samples.length > 0 && samples.every(cohortNativeProgress),
    allSourcesDecodedAndWrapped: sources.length === 6 && sources.every(source => source.pass),
    finalSourcesSustained: sustained.length === 4 && sustained.every(source => source.pass),
    heldComposition: result?.initialStudio?.evolving === false && result?.initialStudio?.loopMode === 'boomerang' &&
      baseline.length > 0 && baseline.every(row => cohortSet(row, finalCohort) &&
        cohortPeersStable(prelude.afterSibling, row, ['loop-1', 'loop-2', 'loop-3', 'loop-4'])),
    strategiesMatch: typeof strategy === 'boolean' && prelude.strategyStart?.pauseBeforeSeek === strategy &&
      result?.strategyFinal?.pauseBeforeSeek === strategy && Number.isFinite(assignedAt) && assignedAt >= 0 &&
      samples.length > 0 && Number.isFinite(samples[0].wall) && assignedAt <= samples[0].wall,
  });
  return {pass: Object.values(checks).every(value => value === true), checks, sources, sustained, overlap, incomingObservations};
}

module.exports = {TARGETS, ORIGIN, buildManifest, controlledVerdict, coverage};
