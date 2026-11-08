/* Controlled native diagnostic only; never loaded by Studio or deployed. */
'use strict';
const crypto = require('node:crypto');
const {libraryClips} = require('./browser.studio.js');
const TARGETS = Object.freeze([
  {id: '107936da1aae', role: 'held', sha256: '114d579e74bce64d59232b017a29584c5c6226d33e73f1965208bb7027ccce65',
    forwardSha256: '107936da1aae2c87657072e72487b74c3ec15e647304a3e974bc10b93d015b5d'},
  {id: '2f00e7f10d19', role: 'held', sha256: '6ce069d9b8fce7ef623021e7cb06205c5b794ea189af5ddbce7e63242e1f9062',
    forwardSha256: '2f00e7f10d194e19599f683cb2261a151c323d6eb6ff64a4ed5f59e4689875e5'},
  {id: '443fbc2c885a', role: 'held', sha256: '714ec3a120ab952fd1625d83a0d52ec135e662178a3c71014475c10a5e1adce0',
    forwardSha256: '443fbc2c885a4a1ea24190ff7e73c56fee41b7a45ded92ef541c1de82ff9949a'},
  {id: 'c1d21417eede', role: 'held', sha256: 'b8d233295b6c68c937310d7b59cdc6edef4474e1a92f1891e5f5a64db582a506',
    forwardSha256: 'c1d21417eedea36d1f50166d020eec5999f8ba384995f8594ad6c1a0d9a50b52'},
  {id: '37b398494e0d', role: 'predecessor', sha256: '83e5a36f7b84948bb702d07ecf7991c6febe930064f9df523265d885868d37d7',
    forwardSha256: '37b398494e0de645ced7593ffb3490bea3aa2ec76b7de99d1780784a6146e66c'},
]);
const ORIGIN = Object.freeze({run: '42431559354', artifact: '13597902240',
  artifactSha256: 'da5959ad179bf7bb4a942605edac0f859df70cf6fd0dfd76097d8d572a88d193',
  head: '5dc225a87684012a529bad97770e10a8883d3585', sample: 'seeded.json',
  holdStartWall: 131094, holdEndWall: 133742, observations: 17, maxSampleGapMs: 294,
  sourceManifestSha256: '030d6446b3a57ea003ec056fdb7ed3e553c10f184b477346822eec5b4f9ca401',
  libraryUrl: 'https://75cafe28.loop-compositor-studio.pages.dev/library/'});
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const assert = (condition, message) => { if (!condition) throw new Error(message); };

function buildManifest(original, readAsset, targets = TARGETS) {
  assert(libraryClips(original), 'Original library manifest failed the Studio schema gate');
  assert(targets.length === 5 && new Set(targets.map(t => t.id)).size === 5 &&
    targets.filter(t => t.role === 'held').length === 4 && targets.filter(t => t.role === 'predecessor').length === 1,
  'Diagnostic requires four held sources and one predecessor');
  const clips = targets.map(target => {
    const clip = original.clips.find(entry => entry.id === target.id);
    assert(clip?.variants?.boomerang, 'Diagnostic target missing: ' + target.id);
    for (const [asset, expected] of [[clip, target.forwardSha256], [clip.variants.boomerang, target.sha256]]) {
      const bytes = readAsset(asset.file);
      assert(bytes.length === asset.bytes && digest(bytes) === expected,
        'Diagnostic asset hash/size mismatch: ' + asset.file);
    }
    return clip; // Preserve the complete original entry, including tags and envelopes.
  });
  const manifest = {...original, clips}, normalized = libraryClips(manifest);
  assert(normalized?.length === 5, 'Subset library failed the Studio schema gate');
  const held = targets.filter(t => t.role === 'held'), predecessor = targets.find(t => t.role === 'predecessor');
  const before = [predecessor, ...held.slice(1)];
  const mix = before.map(t => normalized.findIndex(clip => clip.id === t.id)).join('.');
  return {manifest, targets: targets.map(target => {
    const clip = clips.find(entry => entry.id === target.id);
    return {...target, file: clip.variants.boomerang.file,
      publishedUrl: ORIGIN.libraryUrl + clip.variants.boomerang.file};
  }), query: `?seed=528316659&mix=s${mix}&evolve=0&loop=boomerang&proof=1`};
}

// Positive decoded evidence, never a media-clock-only wrap. A source identity
// change or a missing observation cannot connect two samples into a proven wrap.
function observeSources(samples, targets = TARGETS) {
  const records = new Map(targets.map(t => [t.id, {...t, observations: 0, advances: 0, wraps: 0,
    firstWall: null, lastWall: null, wrapEvidence: [], invalid: 0}]));
  const previous = new Map();
  for (const row of samples) {
    const present = new Set((row.nodes || []).map(node => node.id));
    for (const [id, old] of previous) if (!present.has(id)) {
      records.get(old.item).invalid++; previous.delete(id);
    }
    for (const node of row.nodes || []) {
      const report = records.get(node.item); if (!report) continue;
      const p = node.progress;
      // Native loop seeking can briefly report HAVE_METADATA while the last
      // decoded texture remains valid. Advancing callback evidence, rather
      // than HAVE_FUTURE_DATA, establishes subsequent decoded progress.
      const valid = row.running === true && row.hidden === false && row.audioState === 'running' && node.paused === false && node.ready >= 1 &&
        !node.nativeError && node.sha === report.sha256 && Number.isFinite(row.wall) && Number.isFinite(node.decoded) &&
        p?.schema === 1 && p.supported === true && p.live === true && p.foreground === true && p.running === true &&
        typeof p.url === 'string' && p.url.startsWith('blob:') && Number.isSafeInteger(p.epoch) && p.epoch >= 1 &&
        Number.isSafeInteger(p.sourceChanges) && p.sourceChanges >= 1 && Number.isSafeInteger(p.changes) &&
        p.changes >= p.sourceChanges && p.mediaTime === node.decoded &&
        [p.currentGapMs, p.maxGapMs].every(gap => Number.isFinite(gap) && gap >= 0 && gap < 2000) &&
        Number.isSafeInteger(node.callbacks) && node.callbacks >= 1;
      if (!valid) { report.invalid++; previous.delete(node.id); continue; }
      report.observations++; report.firstWall ??= row.wall; report.lastWall = row.wall;
      const identity = JSON.stringify([node.id, node.item, node.sha, node.deck, node.birth, p.url, p.epoch]);
      const old = previous.get(node.id);
      if (old?.identity === identity) {
        const gap = row.wall - old.wall;
        if (gap < 0 || gap >= 2000) report.invalid++;
        else if (gap > 0 && p.sourceChanges > old.changes && node.callbacks > old.callbacks && node.decoded !== old.decoded) {
          report.advances++;
          if (node.decoded + .05 < old.decoded) {
            report.wraps++;
            if (report.wrapEvidence.length < 8) report.wrapEvidence.push({id: node.id, deck: node.deck, birth: node.birth,
              epoch: p.epoch, url: p.url, fromWall: old.wall, wall: row.wall, fromDecoded: old.decoded,
              decoded: node.decoded, sourceChanges: p.sourceChanges});
          }
        }
      }
      previous.set(node.id, {identity, item: node.item, wall: row.wall,
        changes: p.sourceChanges, callbacks: node.callbacks, decoded: node.decoded});
    }
  }
  return [...records.values()].map(record => ({...record,
    pass: record.observations >= 3 && record.advances >= 2 && record.wraps >= 1 && record.invalid === 0}));
}

const identity = node => [node.id, node.item, node.sha, node.deck, node.birth, node.progress?.url, node.progress?.epoch];
function transitionChecks(before, after, targets = TARGETS) {
  const held = targets.filter(t => t.role === 'held'), predecessor = targets.find(t => t.role === 'predecessor');
  const matches = (row, expected) => row?.nodes?.length === 4 && expected.every((target, index) => {
    const node = row.nodes.find(node => node.id === `loop-${index + 1}`);
    return node?.item === target.id && node.sha === target.sha256;
  });
  return {predecessorSet: matches(before, [predecessor, ...held.slice(1)]), heldSet: matches(after, held),
    siblingIdentities: Boolean(before && after && [2, 3, 4].every(index => {
      const a = before.nodes.find(node => node.id === `loop-${index}`), b = after.nodes.find(node => node.id === `loop-${index}`);
      return a && b && JSON.stringify(identity(a)) === JSON.stringify(identity(b));
    }))};
}

function coverage(result, targets = TARGETS) {
  const prelude = result.prelude || {}, sources = observeSources(prelude.samples || [], targets);
  const sustained = observeSources(result.samples || [], targets);
  const bounded = (value, max) => Number.isSafeInteger(value) && value >= 0 && value <= max;
  const checks = {...transitionChecks(prelude.before, prelude.after, targets),
    preludeResources: Boolean(prelude.samples?.length && prelude.samples.every(row =>
      row.foregroundLimit === 4 && row.nodes?.length === 4 && new Set(row.nodes.map(node => node.id)).size === 4 &&
      bounded(row.populated, 5) && bounded(row.playing, row.populated) &&
      bounded(row.standbys, 1) && bounded(row.maxStandbys, 1) && row.standbys <= row.maxStandbys)),
    preludeNativeProgress: Boolean(prelude.samples?.length && prelude.samples.every(row => {
      const summary = row.progressSummary;
      return summary?.schema === 1 && summary.supported === true && Number.isFinite(summary.maxGapMs) &&
        summary.maxGapMs >= 0 && summary.maxGapMs < 2000 && summary.suspensionCount === 0;
    })),
    allSourcesDecodedAndWrapped: sources.every(source => source.pass),
    heldSourcesSustained: sustained.filter(source => source.role === 'held').every(source => source.pass),
    evolutionEnabled: result.initialStudio?.evolving === true && result.initialStudio?.loopMode === 'boomerang'};
  return {pass: Object.values(checks).every(Boolean), checks, sources, sustained};
}

async function prepare(page, {sample, click, ready, pause, journal}, targets = TARGETS, result = {}) {
  Object.assign(result, {scope: 'Controlled four-active source/transition replay; manual mix suppresses sparse resting. '
    + 'This does not reproduce original wall timing, deck ages or ecological history.', origin: ORIGIN, samples: []});
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
    throw new Error('Diagnostic did not positively decode and wrap its required residents');
  };
  const held = targets.filter(t => t.role === 'held'), predecessor = targets.find(t => t.role === 'predecessor');
  await waitForSources([predecessor, ...held.slice(1)]);
  result.before = await capture();
  assert(transitionChecks(result.before, null, targets).predecessorSet, 'Diagnostic initial resident set differs');
  // The only unoccupied item in this five-source manifest is the held successor.
  // This public tap supplies deterministic admission without modifying runtime state.
  let finished = false, failure;
  const transition = (async () => {
    try { await click(page, '#stage .loop[data-loop-id="loop-1"]'); await ready(page); }
    catch (error) { failure = error; }
    finally { finished = true; }
  })();
  while (!finished) { await capture(); await pause(137); }
  await transition; if (failure) throw failure;
  result.after = await capture();
  assert(Object.values(transitionChecks(result.before, result.after, targets)).every(Boolean),
    'Diagnostic handoff changed the wrong source or a sibling identity');
  await waitForSources(held);
  await click(page, '#activity');
  await page.waitForFunction(() => SimvltaneaStudio.snapshot().evolving === true);
  return result;
}

module.exports = {TARGETS, ORIGIN, buildManifest, observeSources, transitionChecks, coverage, prepare};
