/* Separate, deliberately instrumented experiment. Never an acceptance verifier
 * or deployed Studio asset. No threshold, production observer or prototype edits.
 * node diagnose_webkit_wrap_plateau.js SITE OUTPUT [--mechanics]
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {sample, staticServer, ready, click, proofJournal} = require('./verify_webkit_sustained.js');
const {libraryClips} = require('./browser.studio.js');
const BASE = 'f3c724ecd7d4483e11e8d0b623a8e283cf0501a3';
const BASE_LIVE_SHA = '6b317d6951a9248faabdd8991a94f99174314ae757102e4b5a27e3ed351eb055';
const MANIFEST_SHA = '030d6446b3a57ea003ec056fdb7ed3e553c10f184b477346822eec5b4f9ca401';
const TARGETS = Object.freeze([
  ['8a8170c5c786', '0e584919d052d1b229ee4b13d6f9e7d3e38cb6422249b2cac945fdd7dc1633f3'],
  ['a7101c824f85', '78eab5da6fc98d39840b0975ab0be040c5953857bf54757f9559b6b655989fc0'],
  ['3ee882ccb693', 'a28f0626a8d70da8db717877bb1ca9992784648b4240d95b36bf62a291201f74'],
  ['443fbc2c885a', '714ec3a120ab952fd1625d83a0d52ec135e662178a3c71014475c10a5e1adce0'],
]);
const FRAME_FIELDS = ['callbackNow','readWall','registeredSource','currentSource','owned','mediaTime',
  'presentedFrames','presentationTime','expectedDisplayTime','processingDuration','currentTime',
  'seeking','paused','readyState','active','resting'];
const RAF_FIELDS = ['timestamp','readWall','simTime','audioTime'];
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const assert = (ok, why) => { if (!ok) throw Error(why); };
const save = (out, name, value) => fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2)+'\n');
const pause = ms => new Promise(resolve => setTimeout(resolve,ms));

function options(argv, platform = process.platform) {
  assert(argv.length >= 2 && argv.slice(2).every(x => x === '--mechanics') &&
    argv.filter(x => x === '--mechanics').length <= 1, 'SITE OUTPUT [--mechanics] only');
  const mechanics = argv.includes('--mechanics');
  assert(platform === 'darwin' || mechanics, 'Native diagnostic requires macOS; --mechanics is explicitly non-native');
  return {site:path.resolve(argv[0]),out:path.resolve(argv[1]),mechanics,durationMs:mechanics?8000:60000};
}

function fixture(site) {
  const raw=fs.readFileSync(path.join(site,'library/manifest.json'));
  assert(sha(raw)===MANIFEST_SHA,'Pinned library manifest mismatch');
  const original=JSON.parse(raw), clips=TARGETS.map(([id,digest])=>{
    const clip=original.clips.find(x=>x.id===id), asset=clip?.variants?.boomerang;
    assert(asset && asset.id===digest.slice(0,12),'Missing pinned boomerang '+id);
    const bytes=fs.readFileSync(path.join(site,'library',asset.file));
    assert(bytes.length===asset.bytes && sha(bytes)===digest,'Asset bytes mismatch '+id);
    return clip;
  });
  const manifest={...original,clips}, normalized=libraryClips(manifest);
  assert(normalized?.length===4,'Invalid four-source subset');
  return {manifest,query:'?seed=528316659&mix=s'+TARGETS.map(([id])=>normalized.findIndex(c=>c.id===id)).join('.')+
    '&evolve=0&loop=boomerang&proof=1', assets:clips.map((c,i)=>({clipId:c.id,...c.variants.boomerang,sha256:TARGETS[i][1]}))};
}

// Each observer belongs to one persistent deck and records the registration's
// source epoch separately from the callback's current owner. Stale callbacks
// stay in the raw record but cannot prove progress for a newly assigned source.
function installObservers() {
  const runtime=globalThis.compositionRuntime, sources=[], sourceIds=new Map();
  const frame=new Float64Array(4096*16), raf=new Float64Array(2048*4);
  let frames=0,rafs=0,droppedFrames=0,droppedRaf=0,sentSources=0,stopped=false,rafId;
  const observers=[];
  const sourceId=(node,deck,index)=>{
    const key=JSON.stringify([node.id,index,deck.url,deck.sourceEpoch]);
    if(!sourceIds.has(key)){
      sourceIds.set(key,sources.length);
      sources.push({id:sources.length,slot:node.id,deck:index,url:deck.url,epoch:deck.sourceEpoch,
        item:deck.item?.name,sha:deck.item?.sha256,observedWall:performance.now()});
    }
    return sourceIds.get(key);
  };
  for(const node of runtime.slots.values())node.decks.forEach((deck,index)=>{
    const media=deck.media;let registered=sourceId(node,deck,index),callbackId;
    const watch=(now,m)=>{
      if(stopped)return;
      const current=sourceId(node,deck,index), owner=sources[registered];
      if(frames<4096){
        let i=frames++*16;
        frame[i++]=now;frame[i++]=performance.now();frame[i++]=registered;frame[i++]=current;
        frame[i++]=Number(registered===current && Boolean(owner.url) && media.currentSrc===owner.url);
        frame[i++]=m.mediaTime;frame[i++]=m.presentedFrames;frame[i++]=m.presentationTime;
        frame[i++]=m.expectedDisplayTime;frame[i++]=m.processingDuration;frame[i++]=media.currentTime;
        frame[i++]=Number(media.seeking);frame[i++]=Number(media.paused);frame[i++]=media.readyState;
        frame[i++]=Number(node.active===deck);frame[i++]=Number(node.resting);
      }else droppedFrames++;
      registered=current;callbackId=media.requestVideoFrameCallback(watch);
    };
    callbackId=media.requestVideoFrameCallback(watch);
    observers.push(()=>media.cancelVideoFrameCallback(callbackId));
  });
  const heartbeat=timestamp=>{
    if(stopped)return;
    if(rafs<2048){let i=rafs++*4;raf[i++]=timestamp;raf[i++]=performance.now();
      raf[i++]=runtime.clock.simTime;raf[i++]=runtime.audio.context?.currentTime;}
    else droppedRaf++;
    rafId=requestAnimationFrame(heartbeat);
  };
  rafId=requestAnimationFrame(heartbeat);
  globalThis.__wrapDiagnostic={
    drain(){const begin=performance.now(),result={begin,frames:Array.from(frame.subarray(0,frames*16)),
      raf:Array.from(raf.subarray(0,rafs*4)),sources:sources.slice(sentSources),droppedFrames,droppedRaf};
      frames=rafs=0;sentSources=sources.length;result.end=performance.now();return result;},
    stop(){stopped=true;cancelAnimationFrame(rafId);observers.forEach(stop=>stop());}
  };
}

async function alignWraps(targets) {
  const runtime=compositionRuntime, before=performance.now();
  const nodes=targets.map(([id,digest],i)=>{
    const node=runtime.nodes.get('loop-'+(i+1));
    if(node?.item?.name!==id||node.item.sha256!==digest)throw Error('Wrong source in diagnostic slot');
    return node;
  });
  if(SimvltaneaStudio.snapshot().evolving)throw Error('Diagnostic requires Hold');
  // Deliberate setup only. Both arms use identical source positions; the raw
  // native callbacks, not these requested offsets, determine actual wraps.
  const untilWrap=[2.28,2.028,2,5.2];
  nodes.forEach(node=>node.media.pause());
  await Promise.all(nodes.map((node,i)=>new Promise((resolve,reject)=>{
    const media=node.media,timer=setTimeout(()=>{clean();reject(Error('Setup seek timed out'));},8000);
    const clean=()=>{clearTimeout(timer);media.removeEventListener('seeked',done);};
    const done=()=>{clean();resolve();};media.addEventListener('seeked',done);
    media.currentTime=Math.max(0,media.duration-untilWrap[i]);
  })));
  runtime.setResting('loop-2',true);
  await Promise.all(nodes.map(node=>node.media.play()));
  return {before,after:performance.now(),requestedUntilWrapSec:untilWrap,restingSlot:'loop-2',
    hold:true,setup:'Explicit pause/seek/play alignment before measurement; not natural user playback',
    nodes:nodes.map(n=>({id:n.id,item:n.item.name,sha:n.item.sha256,birth:n.birthTime,
      deck:n.decks.indexOf(n.active),url:n.active.url,epoch:n.active.sourceEpoch,
      current:n.media.currentTime,duration:n.media.duration,resting:n.resting}))};
}

function analyseFrames(chunks, finalSample = null) {
  const sources=new Map(), previous=new Map(), wraps=[], gaps=[], foregroundSlots=new Set();
  let maxRafGapMs=0,maximumObservedGapMs=0,lastRaf=null,invalid=0,dropped=0;
  for(const chunk of chunks){
    for(const source of chunk.sources)sources.set(source.id,source);
    dropped=Math.max(dropped,chunk.droppedFrames+chunk.droppedRaf);
    for(let i=0;i<chunk.raf.length;i+=4){const wall=chunk.raf[i+1];if(lastRaf!==null)maxRafGapMs=Math.max(maxRafGapMs,wall-lastRaf);lastRaf=wall;}
    for(let i=0;i<chunk.frames.length;i+=16){
      const row=chunk.frames.slice(i,i+16), id=row[2],source=sources.get(id);
      if(row[4]!==1||row[2]!==row[3]||!source?.url){invalid++;continue;}
      if(row[14]===1&&row[12]===0)foregroundSlots.add(source.slot);
      const old=previous.get(id);
      if(old && row[5]!==old[5] && old[14]===1 && row[14]===1 && old[12]===0 && row[12]===0){
        const gap={slot:source.slot,deck:source.deck,url:source.url,epoch:source.epoch,
          fromWall:old[1],wall:row[1],gapMs:row[1]-old[1],fromCallbackNow:old[0],callbackNow:row[0],
          fromDecoded:old[5],decoded:row[5],resting:row[15]===1};
        maximumObservedGapMs=Math.max(maximumObservedGapMs,gap.gapMs);
        if(gap.gapMs>=500)gaps.push(gap);
        if(row[5]+.05<old[5])wraps.push({...gap});
      }
      if(!old||row[5]!==old[5]||row[14]!==old[14]||row[12]!==old[12])previous.set(id,row);
    }
  }
  // An unresolved final foreground stall must not disappear merely because no
  // resuming callback closes its interval. Current source+epoch ownership is
  // mandatory; a retired or parked deck cannot supply this tail observation.
  for(const [id,old] of previous){
    const source=sources.get(id),deck=finalSample?.decks?.find(d=>d.id===source.slot&&d.deck===source.deck);
    if(!deck?.active||deck.paused||old[14]!==1||old[12]!==0||deck.currentSrc!==source.url||
      deck.progress?.url!==source.url||deck.progress?.epoch!==source.epoch)continue;
    const gapMs=finalSample.wall-old[1];
    maximumObservedGapMs=Math.max(maximumObservedGapMs,gapMs);
    if(gapMs>=500)gaps.push({slot:source.slot,deck:source.deck,url:source.url,epoch:source.epoch,
      fromWall:old[1],wall:finalSample.wall,gapMs,fromCallbackNow:old[0],fromDecoded:old[5],decoded:null,
      resting:old[15]===1,openAtEnd:true});
  }
  const first=slot=>wraps.find(w=>w.slot===slot),a=first('loop-2'),b=first('loop-3');
  const separation=a&&b?Math.abs(a.wall-b.wall):null;
  return {maximumObservedGapMs,maxRafGapMs,foregroundSlots:[...foregroundSlots],
    nearCoincidentFirstWraps:separation!==null&&separation<=150,firstWrapSeparationMs:separation,
    observedOverTwoSeconds:gaps.some(g=>g.gapMs>2000),gaps,wraps,invalidSourceCallbacks:invalid,
    droppedRecords:dropped,coverageComplete:dropped===0,
    interpretation:'Observed decoded callback intervals only; no acceptance verdict or causal inference from absence of reproduction.'};
}

function classify(result) {
  const attempt=result.final?.progressSummary?.nativeLoopSeek?.attempted;
  const guardStatus=!Number.isSafeInteger(attempt)||attempt<0?'UNKNOWN':attempt>0?'EXERCISED':'NOT_EXERCISED';
  const sourceError=Boolean(result.sourceErrors?.length||result.final?.lastFailure||
    result.final?.decks?.some(deck=>deck.nativeError)||
    result.events?.some(event=>event.type==='media-failure'));
  const diagnosticError=Boolean(result.errors?.length)||sourceError;
  const coverageComplete=result.observation.coverageComplete&&!diagnosticError&&
    result.observation.foregroundSlots.length===4;
  const outcome=!result.completed?'SETUP_OR_CAPTURE_FAILED':diagnosticError?'DIAGNOSTIC_ERROR':
    !coverageComplete?'COVERAGE_INCOMPLETE':result.observation.observedOverTwoSeconds?'REPRODUCED_GAP':
      !result.observation.nearCoincidentFirstWraps?'ALIGNMENT_NOT_OBSERVED':'NOT_REPRODUCED';
  return {outcome,guardStatus,coverageComplete,sourceError};
}

async function arm(browserType,launchOptions,device,base,out,name,runtimeBytes,query,durationMs) {
  const result={arm:name,diagnosticOnly:true,durationMs,completed:false,errors:[],sourceErrors:[],chunks:[],rpc:[],host:[]};
  const journal=proofJournal(out,name);let browser;
  try{
    browser=await browserType.launch(launchOptions);const context=await browser.newContext(device),page=await context.newPage();
    page.on('pageerror',e=>result.errors.push(String(e)));
    if(runtimeBytes)await page.route(base+'runtime.js',route=>route.fulfill({contentType:'application/javascript',body:runtimeBytes}));
    await page.goto(base+query,{waitUntil:'domcontentloaded',timeout:20000});await ready(page);
    await click(page,'#speaker');await page.waitForFunction(()=>compositionRuntime.audio.context?.state==='running');
    result.setup=await page.evaluate(alignWraps,TARGETS);
    await page.evaluate(installObservers); // setup seeks precede the complete observer registry
    result.documentClock=await page.evaluate(()=>({timeOrigin:performance.timeOrigin,wall:performance.now(),epochMs:Date.now()}));
    await journal.append('setup',{setup:result.setup,documentClock:result.documentClock});
    const began=performance.now();let lastCpu=process.cpuUsage();
    while(performance.now()-began<durationMs){
      const sent=performance.now(),chunk=await page.evaluate(()=>__wrapDiagnostic.drain()),returned=performance.now();
      const observation=await page.evaluate(sample,false);
      if(observation.lastFailure||observation.decks.some(deck=>deck.nativeError))result.sourceErrors.push({wall:observation.wall,
        lastFailure:observation.lastFailure,decks:observation.decks.filter(deck=>deck.nativeError)});
      result.chunks.push(chunk);result.rpc.push({sent,returned,roundTripMs:returned-sent,browserBegin:chunk.begin,browserEnd:chunk.end});
      await journal.append('observation',{chunk,rpc:result.rpc.at(-1),sample:observation});
      const cpu=process.cpuUsage(lastCpu);lastCpu=process.cpuUsage();
      const host={elapsedMs:performance.now()-began,cpuDeltaMicroseconds:cpu,memory:process.memoryUsage(),
        loadavg:os.loadavg(),freeMemory:os.freemem(),totalMemory:os.totalmem()};
      if(process.platform==='darwin')try{host.processes=execFileSync('ps',['-axo','pid,ppid,pcpu,rss,comm'],
        {encoding:'utf8',timeout:1000,maxBuffer:128*1024}).split('\n').filter(line=>/WebKit|WebContent|MiniBrowser|GPU|node/.test(line));}
      catch(error){host.processObservationError=String(error);}
      result.host.push(host);await journal.append('host',host);await pause(1000);
    }
    result.elapsedMs=performance.now()-began;
    const chunk=await page.evaluate(()=>__wrapDiagnostic.drain());result.chunks.push(chunk);await journal.append('final-frames',chunk);
    result.final=await page.evaluate(sample,true);result.events=await page.evaluate(()=>compositionRuntime.events);
    await journal.append('final',{sample:result.final,events:result.events});
    await page.evaluate(()=>__wrapDiagnostic.stop());result.completed=true;
  }catch(error){result.failure=String(error.stack||error);}
  finally{
    if(browser)try{await browser.close();}catch(error){result.closeError=String(error);result.completed=false;}
    try{await journal.close();}catch(error){result.journalError=String(error);result.completed=false;}
  }
  result.observation=analyseFrames(result.chunks,result.final);
  const classification=classify(result);
  result.outcome=classification.outcome;result.guardStatus=classification.guardStatus;
  result.observation.coverageComplete=classification.coverageComplete;
  result.observation.sourceError=classification.sourceError;
  save(out,name+'.json',result);return result;
}

async function main(argv=process.argv.slice(2)) {
  const config=options(argv);fs.mkdirSync(config.out,{recursive:true});let server;
  const receipt={diagnosticOnly:true,scope:config.mechanics?'NON_NATIVE_MECHANICS_ONLY':'macOS WebKit diagnostic; not physical iPhone or acceptance',
    durationPerArmMs:config.durationMs,baselineCommit:BASE,baselineLiveSha256:BASE_LIVE_SHA,
    frameFields:FRAME_FIELDS,rafFields:RAF_FIELDS,startedAt:new Date().toISOString()};
  try{
    const fixtureData=fixture(config.site), parts=['browser.audio.js','browser.presence.js','browser.ecosystem.js','browser.live.js'];
    const bytes=parts.map(n=>fs.readFileSync(path.join(__dirname,n))),candidate=Buffer.concat(bytes.flatMap((b,i)=>i?[Buffer.from('\n'),b]:[b]));
    assert(candidate.equals(fs.readFileSync(path.join(config.site,'runtime.js'))),'Stage differs from exact current source');
    // Python is already pinned by the workflow; urllib also honors the proxy
    // configuration used by local mechanics environments. No shell expansion.
    const baseline=execFileSync('python3',['-c',
      'import sys,urllib.request;sys.stdout.buffer.write(urllib.request.urlopen(sys.argv[1],timeout=15).read())',
      'https://raw.githubusercontent.com/4444J99/tool-video-loop-compositor/'+BASE+'/src/simvltanea/browser/browser.live.js'],
    {timeout:20000,maxBuffer:256*1024});
    assert(sha(baseline)===BASE_LIVE_SHA,'Immutable control source hash mismatch');
    const control=Buffer.concat([bytes[0],Buffer.from('\n'),bytes[1],Buffer.from('\n'),bytes[2],Buffer.from('\n'),baseline]);
    receipt.sourceHashes=Object.fromEntries(parts.map((n,i)=>[n,sha(bytes[i])]));
    receipt.candidateRuntimeSha256=sha(candidate);receipt.controlRuntimeSha256=sha(control);
    receipt.harnessSha256=sha(fs.readFileSync(__filename));
    receipt.workflowSha256=sha(fs.readFileSync('.github/workflows/macos-webkit.yml'));
    receipt.originalManifestSha256=MANIFEST_SHA;
    receipt.sharedComponents=parts.slice(0,3);receipt.assets=fixtureData.assets;
    receipt.head=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
    receipt.sourceStatus=execFileSync('git',['status','--short'],{encoding:'utf8'});
    receipt.workflowSha=process.env.GITHUB_SHA||null;
    assert(config.mechanics||receipt.sourceStatus==='','Native diagnostic requires a clean checked-out source');
    assert(config.mechanics||receipt.workflowSha===receipt.head,'Native diagnostic must bind the workflow checkout SHA');
    fs.writeFileSync(path.join(config.out,'control-browser.live.js'),baseline);
    save(config.out,'fixture-manifest.json',fixtureData.manifest);
    const {webkit,chromium,devices}=require('playwright'),{defaultBrowserType,...device}=devices['iPhone 13'];
    receipt.playwrightVersion=require('playwright/package.json').version;
    assert(config.mechanics||receipt.playwrightVersion==='1.65.0','Native diagnostic requires playwright1.65.0');
    // The local mode proves orchestration only. It deliberately uses the
    // installed Linux Chromium and can never satisfy the macOS gate above.
    const browserType=config.mechanics?chromium:webkit;
    const launchOptions=config.mechanics?{headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']}:{headless:true};
    receipt.browserEngine=config.mechanics?'Chromium (non-native mechanics only)':'macOS WebKit';
    server=staticServer(config.site,Buffer.from(JSON.stringify(fixtureData.manifest)));
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+server.address().port+'/';
    receipt.arms=[];receipt.completed=false;
    save(config.out,'receipt.json',receipt); // retain source bindings if the step is terminated
    for(const name of ['control','candidate']){
      const result=await arm(browserType,launchOptions,device,base,config.out,name,name==='control'?control:null,fixtureData.query,config.durationMs);
      receipt.arms.push({arm:name,completed:result.completed,elapsedMs:result.elapsedMs,outcome:result.outcome,
        pageErrorCount:result.errors.length,guardStatus:result.guardStatus,observation:result.observation,failure:result.failure});
      save(config.out,'receipt.json',receipt);
    }
    receipt.completed=receipt.arms.every(a=>a.completed);
    receipt.interpretation='No reproduction is not proof of cure. Controlled seek alignment and extra read-only observers are declared interventions; original acceptance captures remain separate.';
  }catch(error){receipt.failure=String(error.stack||error);receipt.completed=false;}
  finally{if(server){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
    receipt.finishedAt=new Date().toISOString();save(config.out,'receipt.json',receipt);}
  console.log(JSON.stringify({diagnosticOnly:true,scope:receipt.scope,completed:receipt.completed,
    arms:receipt.arms?.map(a=>({arm:a.arm,outcome:a.outcome,maximumObservedGapMs:a.observation.maximumObservedGapMs}))}));
  if(!receipt.completed)process.exitCode=1;
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={options,fixture,analyseFrames,classify,installObservers,TARGETS,BASE_LIVE_SHA,FRAME_FIELDS,RAF_FIELDS};
